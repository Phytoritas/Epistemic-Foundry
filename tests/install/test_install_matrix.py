"""Z01 install_matrix_test: fail-closed fresh-install and compatibility matrix.

This required-check module reads the declaring source
``manifests/compatibility_matrix.yaml`` and proves, through the deterministic
:mod:`z01_matrix_harness`, that a fresh install of the declared payload is
reproducible, that every declared host/OS/capability cell is fail-closed
refused until it is SUPPORTED-with-evidence AND sealed-cited, and that the
provenance of every host row traces to a sealed Z01 dependency.  It spawns no
host and installs nothing; these are declared-matrix lifecycle proofs, not real
multi-OS installs.  The one real single-host marketplace lifecycle is composed
from the sealed ``G04-0001`` gate, not duplicated here.
"""

from __future__ import annotations

import pytest

import z01_matrix_harness as harness

FIXED_TS = "1970-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def matrix() -> dict:
    return harness.load_matrix()


@pytest.fixture(scope="module")
def report(matrix: dict) -> dict:
    return harness.build_install_matrix_report(matrix, generated_at=FIXED_TS)


def test_matrix_is_fail_closed_reference(matrix: dict) -> None:
    assert matrix["version"] == "4.0.0"
    assert matrix["status"] == "UNVERIFIED_REFERENCE_MATRIX"
    assert matrix["plugin"]["runtime_capabilities"] == []


def test_matrix_is_the_only_declaring_source_of_hosts_and_platforms(
    matrix: dict,
) -> None:
    # The harness reads host and platform lists from the matrix; this module must
    # not restate them. Prove they come from the matrix and are non-empty.
    assert matrix["hosts"], "matrix declares no hosts"
    assert matrix["known_platforms"], "matrix declares no known platforms"
    for host in matrix["hosts"]:
        assert host["platforms"], f"{host['host']} offers no platforms"
        assert set(host["platforms"]) <= set(matrix["known_platforms"])


def test_plugin_identity_and_payload_match_actual_package(report: dict) -> None:
    assert report["plugin_identity_matches_manifest"] is True
    assert report["payload_top_level_matches"] is True
    assert report["fresh_install_file_count"] > 0


def test_fresh_install_inventory_is_deterministic_and_hash_rederivable(
    matrix: dict, report: dict
) -> None:
    again = harness.build_install_matrix_report(matrix, generated_at=FIXED_TS)
    assert (
        report["fresh_install_inventory_sha256"]
        == (again["fresh_install_inventory_sha256"])
    )
    # The whole record is hash-re-derivable with the same matrix + timestamp.
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = harness.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]


def test_sealed_dependencies_are_exactly_the_declared_z01_dependencies(
    report: dict,
) -> None:
    assert report["sealed_dependencies_match_expected"] is True
    assert report["sealed_dependencies"] == sorted(
        harness.EXPECTED_SEALED_DEPENDENCIES.values()
    )


def test_every_host_row_cites_sealed_evidence(report: dict) -> None:
    citations = report["row_citations"]["hosts"]
    assert citations, "no host rows to audit"
    for host in citations:
        assert host["cited_attempts"], f"{host['host']} cites no sealed evidence"
        assert host["refusals"] == [], f"{host['host']} has citation refusals"
        for attempt in host["cited_attempts"]:
            assert attempt in set(harness.EXPECTED_SEALED_DEPENDENCIES.values())


def test_uncited_row_is_refused_with_typed_code(matrix: dict) -> None:
    # Remove all citations from the first host: the row must be refused, proving
    # the citation gate is genuine and not vacuous.
    import copy

    mutated = copy.deepcopy(matrix)
    mutated["hosts"][0]["establishing_evidence"] = []
    report = harness.row_citation_report(mutated)
    refusals = report["hosts"][0]["refusals"]
    assert any(r["code"] == "EF_Z01_ROW_UNCITED" for r in refusals)


def test_non_sealed_citation_is_refused(matrix: dict) -> None:
    import copy

    mutated = copy.deepcopy(matrix)
    mutated["hosts"][0]["establishing_evidence"] = [
        {"attempt_id": "ZZ99-9999", "package": "ZZ99", "capabilities": ["manifest"]}
    ]
    report = harness.row_citation_report(mutated)
    refusals = report["hosts"][0]["refusals"]
    assert any(r["code"] == "EF_Z01_CITATION_NOT_SEALED" for r in refusals)


def test_every_declared_cell_is_refused_fail_closed(report: dict) -> None:
    assert report["cell_count"] > 0
    assert report["allow_count"] == 0
    assert report["refuse_count"] == report["cell_count"]
    for cell in report["cells"]:
        assert cell["decision"] == "REFUSED"
        assert cell["code"].startswith("EF_Z01_")
        assert len(cell["reason"]) > 50


def test_uncited_capabilities_are_refused_before_status(report: dict) -> None:
    # upgrade and rollback have no sealed establisher (Z03 owns them); they must
    # be refused for lacking a citation, never silently allowed.
    uncited = [
        cell
        for cell in report["cells"]
        if cell["capability"] in {"upgrade", "rollback"}
    ]
    assert uncited, "expected upgrade/rollback cells"
    for cell in uncited:
        assert cell["code"] == "EF_Z01_CAP_UNCITED"


def test_unknown_host_platform_and_capability_are_refused(matrix: dict) -> None:
    first_host = matrix["hosts"][0]["host"]
    assert (
        harness.resolve_cell(matrix, "no-such-host", "windows-x64", "manifest")["code"]
        == "EF_Z01_UNKNOWN_HOST"
    )
    assert (
        harness.resolve_cell(matrix, first_host, "solaris-sparc", "manifest")["code"]
        == "EF_Z01_UNKNOWN_PLATFORM"
    )
    assert (
        harness.resolve_cell(matrix, first_host, "windows-x64", "no-such-cap")["code"]
        == "EF_Z01_UNKNOWN_CAPABILITY"
    )


def test_supported_cell_without_full_evidence_is_refused(matrix: dict) -> None:
    import copy

    mutated = copy.deepcopy(matrix)
    host = mutated["hosts"][0]
    host["manifest"] = "SUPPORTED"
    host["evidence"] = list(matrix["required_evidence"])[:-1]
    decision = harness.resolve_cell(mutated, host["host"], "windows-x64", "manifest")
    assert decision["decision"] == "REFUSED"
    assert decision["code"] == "EF_Z01_EVIDENCE_INCOMPLETE"


def test_fully_supported_and_cited_cell_is_allowed(matrix: dict) -> None:
    # The gate is genuine, not vacuously always-refusing: a SUPPORTED, fully
    # evidenced, sealed-cited cell is allowed. No real cell is in this state,
    # which is why every real cell above is refused.
    import copy

    mutated = copy.deepcopy(matrix)
    host = mutated["hosts"][0]
    host["manifest"] = "SUPPORTED"
    host["evidence"] = list(matrix["required_evidence"])
    decision = harness.resolve_cell(mutated, host["host"], "windows-x64", "manifest")
    assert decision == {"decision": "ALLOW"}


def test_marketplace_install_is_composed_from_sealed_g04(report: dict) -> None:
    composition = report["marketplace_install_composition"]
    assert composition["mode"] == "sealed_evidence_citation"
    assert composition["attempt_id"] == "G04-0001"
    assert composition["composed_module"] == (
        "tests/install/local-marketplace/g04-lifecycle.test.mjs"
    )
