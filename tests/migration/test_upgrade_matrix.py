"""Z03 upgrade_matrix_test: fail-closed upgrade/downgrade and hook re-trust proofs.

This required-check module reads the declaring source
``tests/migration/fixtures/upgrade_rollback_matrix.yaml`` and proves, through the
deterministic :mod:`z03_migration_harness`, that every declared v2->v4 and
v3->v4 upgrade path reconciles its declared terminal against the terminal
recomputed from its declared per-step outcomes, that an upgraded host must
re-establish hook trust rather than silently inheriting it, and that a downgrade
is refused fail-closed because the composed contract claims no forward
compatibility. It executes no real cross-version migration; the semantics of
``migrations/contracts/compatibility-matrix.json`` are composed by citation.
"""

from __future__ import annotations

import copy

import pytest

import z03_migration_harness as harness

FIXED_TS = "1970-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def matrix() -> dict:
    return harness.load_matrix()


@pytest.fixture(scope="module")
def report(matrix: dict) -> dict:
    return harness.build_upgrade_matrix_report(matrix, generated_at=FIXED_TS)


def test_matrix_is_fail_closed_reference(matrix: dict) -> None:
    assert matrix["status"] == "UNVERIFIED_REFERENCE_MATRIX"
    assert matrix["target_version"] == "4.0.0"
    assert matrix["write_version"] == "v4"


def test_matrix_is_the_only_declaring_source_of_paths(matrix: dict) -> None:
    assert matrix["paths"], "matrix declares no upgrade/downgrade paths"
    sources_targets = {(p["source"], p["target"]) for p in matrix["paths"]}
    assert ("v2", "v4") in sources_targets
    assert ("v3", "v4") in sources_targets


def test_report_composes_contract_window_by_citation(report: dict) -> None:
    # The write window and silent-fallback stance come from the read-only
    # contract, not restated here; the report must echo them verbatim.
    assert report["write_window"] == "v4 only"
    assert report["silent_fallback"] is False
    assert report["migration_change_class"] == "BREAKING"
    assert report["composed_contract"] == (
        "migrations/contracts/compatibility-matrix.json"
    )


def test_report_is_deterministic_and_hash_rederivable(
    matrix: dict, report: dict
) -> None:
    again = harness.build_upgrade_matrix_report(matrix, generated_at=FIXED_TS)
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = harness.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]


def test_every_upgrade_path_reconciles_to_migrated_explicitly(report: dict) -> None:
    upgrades = [p for p in report["paths"] if p["kind"] == "upgrade"]
    assert upgrades, "expected upgrade paths"
    assert report["all_upgrades_migrated"] is True
    for path in upgrades:
        assert path["reconciled"] is True
        assert path["declared_terminal"] == "MIGRATED_EXPLICITLY"
        assert path["computed_terminal"] == "MIGRATED_EXPLICITLY"
        assert "refusal" not in path


def test_v2_to_v4_upgrade_is_a_two_step_path(report: dict) -> None:
    path = next(p for p in report["paths"] if p["path_id"] == "upgrade_v2_to_v4")
    step_edges = [(s["from"], s["to"]) for s in path["steps"]]
    assert step_edges == [("v2", "v3"), ("v3", "v4")]


def test_every_path_reconciles_declared_and_computed_terminal(report: dict) -> None:
    assert report["all_paths_reconciled"] is True


def test_missing_step_evidence_blocks_reconciliation(matrix: dict) -> None:
    # Drop one required evidence item from the first upgrade step: the path can no
    # longer reconcile to MIGRATED_EXPLICITLY, proving the gate is not vacuous.
    mutated = copy.deepcopy(matrix)
    path = next(p for p in mutated["paths"] if p["path_id"] == "upgrade_v3_to_v4")
    path["steps"][0]["evidence"] = path["steps"][0]["evidence"][:-1]
    result = harness.evaluate_upgrade_path(mutated, path)
    assert result["computed_terminal"] == "BLOCKED"
    assert result["reconciled"] is False
    assert result["refusal"]["code"] == "EF_Z03_TERMINAL_RECONCILIATION_MISMATCH"
    codes = {r["code"] for r in result["steps"][0]["refusals"]}
    assert "EF_Z03_STEP_EVIDENCE_INCOMPLETE" in codes


def test_hook_retrust_is_required_on_upgrade(matrix: dict) -> None:
    # An upgrade step that changed hooks but did not re-establish trust is refused;
    # this is the "hook re-trust tested" exit criterion.
    step = {
        "step_id": "changed_hooks_silently_inherited",
        "from": "v3",
        "to": "v4",
        "hooks_changed": True,
        "hook_trust_reestablished": False,
    }
    decision = harness.hook_retrust_decision(step)
    assert decision["decision"] == "REFUSED"
    assert decision["code"] == "EF_Z03_HOOK_TRUST_NOT_REESTABLISHED"
    assert len(decision["reason"]) > 50


def test_hook_retrust_accepts_reestablished_trust(matrix: dict) -> None:
    step = {
        "step_id": "changed_hooks_retrusted",
        "from": "v3",
        "to": "v4",
        "hooks_changed": True,
        "hook_trust_reestablished": True,
    }
    decision = harness.hook_retrust_decision(step)
    assert decision["decision"] == "OK"


def test_declared_upgrade_steps_all_reestablish_hook_trust(report: dict) -> None:
    for path in report["paths"]:
        if path["kind"] != "upgrade":
            continue
        for step in path["steps"]:
            assert step["hook_retrust"]["decision"] == "OK"
            assert step["hook_retrust"]["trust_reestablished"] is True


def test_downgrade_is_refused_fail_closed(report: dict) -> None:
    downgrades = [p for p in report["paths"] if p["kind"] == "downgrade"]
    assert downgrades, "expected at least one downgrade path"
    assert report["all_downgrades_unsupported"] is True
    for path in downgrades:
        assert path["declared_terminal"] == "UNSUPPORTED"
        assert path["computed_terminal"] == "UNSUPPORTED"
        assert path["reconciled"] is True
        for step in path["steps"]:
            assert step["decision"] == "REFUSED"
            assert step["code"] == "EF_Z03_DOWNGRADE_UNSUPPORTED"
            assert len(step["reason"]) > 50


def test_every_refusal_reason_exceeds_fifty_characters(report: dict) -> None:
    for path in report["paths"]:
        if "refusal" in path:
            assert len(path["refusal"]["reason"]) > 50
        for step in path["steps"]:
            for entry in step.get("refusals", []):
                assert len(entry["reason"]) > 50
            if "reason" in step:
                assert len(step["reason"]) > 50
