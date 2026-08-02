"""Z04 final_release_gate: reconcile the 156-package A-Z set against the ledger.

This required-check module composes the deterministic :mod:`z04_release_gate`
engine against the declaring sources ``manifests/development_manifest.yaml`` and
``.rah/ralph/evidence_ledger.json``.  It proves that every A-Z package is either
sealed-PASS in the ledger or a named remaining item with a designated owner, that
the 156-package accounting balances exactly, and that the manifest dependency
graph resolves and is acyclic.  It seals nothing and mutates no canonical file.
"""

from __future__ import annotations

import copy

import pytest

import z04_release_gate as engine

FIXED_TS = "1970-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def report() -> dict:
    return engine.build_release_reconciliation(generated_at=FIXED_TS)


def test_gate_passes_fail_closed(report: dict) -> None:
    assert report["final_status"] == "PASS"
    assert report["refusals"] == []


def test_expected_package_count_is_156(report: dict) -> None:
    assert report["expected_package_count"] == 156
    assert report["manifest_package_count"] == 156


def test_counts_balance_exactly(report: dict) -> None:
    assert report["counts_balance"] is True
    assert (
        report["sealed_package_count"] + report["remaining_package_count"]
        == report["expected_package_count"]
    )


def test_remaining_set_is_exactly_z04_z05_z06(report: dict) -> None:
    assert report["remaining_packages"] == ["Z04", "Z05", "Z06"]
    assert report["remaining_package_count"] == 3
    assert report["sealed_package_count"] == 153


def test_every_remaining_item_has_an_owner_and_reason(report: dict) -> None:
    assert report["remaining_unowned"] == []
    assert set(report["remaining_owned"]) == set(report["remaining_packages"])
    for package, owner in report["remaining_owned"].items():
        assert owner["owner"] == "primary session (Parent Architect) serial delivery"
        assert len(owner["reason"]) > 50, package


def test_no_orphans_and_nothing_unaccounted(report: dict) -> None:
    assert report["ledger_orphans"] == []
    assert report["unaccounted_packages"] == []
    assert report["orphan_owners"] == []


def test_dependency_graph_is_resolvable_and_acyclic(report: dict) -> None:
    dag = report["dependency_graph"]
    assert dag["package_count"] == 156
    assert dag["unresolved_dependencies"] == []
    assert dag["cycle_detected"] is False
    assert dag["topologically_sortable"] is True
    assert dag["refusals"] == []


def test_record_is_deterministic_and_hash_rederivable(report: dict) -> None:
    again = engine.build_release_reconciliation(generated_at=FIXED_TS)
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = engine.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]


def test_missing_owner_makes_a_remaining_package_unaccounted() -> None:
    # Drop Z05 from the owner map: the gate must refuse rather than sign off.
    original = engine.REMAINING_OWNERS
    patched = {k: v for k, v in original.items() if k != "Z05"}
    engine.REMAINING_OWNERS = patched
    try:
        broken = engine.build_release_reconciliation(generated_at=FIXED_TS)
    finally:
        engine.REMAINING_OWNERS = original
    assert broken["final_status"] == "FAIL"
    assert "Z05" in broken["remaining_unowned"]
    codes = {entry["code"] for entry in broken["refusals"]}
    assert "EF_Z04_REMAINING_UNOWNED" in codes


def test_a_cycle_is_detected_fail_closed() -> None:
    packages = copy.deepcopy(engine.manifest_packages())
    by_id = {package["id"]: package for package in packages}
    by_id["A01"]["depends_on"] = ["A02"]
    by_id["A02"]["depends_on"] = ["A01"]
    dag = engine.dag_report(packages)
    assert dag["cycle_detected"] is True
    assert dag["topologically_sortable"] is False
    codes = {entry["code"] for entry in dag["refusals"]}
    assert "EF_Z04_DAG_CYCLE" in codes


def test_an_unresolved_dependency_is_refused() -> None:
    packages = copy.deepcopy(engine.manifest_packages())
    packages[0]["depends_on"] = ["ZZ9"]
    dag = engine.dag_report(packages)
    assert dag["unresolved_dependencies"] == ["A01->ZZ9"]
    codes = {entry["code"] for entry in dag["refusals"]}
    assert "EF_Z04_DAG_UNRESOLVED_DEPENDENCY" in codes


def test_every_refusal_reason_exceeds_fifty_characters(report: dict) -> None:
    for entry in report["dependency_graph"]["refusals"]:
        assert len(entry["reason"]) > 50
    for code, reason in engine.REFUSAL_REASONS.items():
        assert len(reason) > 50, code
