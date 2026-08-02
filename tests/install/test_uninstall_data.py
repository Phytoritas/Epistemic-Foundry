"""Z01 uninstall_data_test: fail-closed uninstall residue and data preservation.

This required-check module reads the declaring source
``manifests/compatibility_matrix.yaml`` and proves, through the deterministic
:mod:`z01_matrix_harness`, that the declared uninstall removes the plugin
payload with zero orphaned residue, that user data (profile, ledger and
artifacts) is preserved and disjoint from removable state, and that a partial
uninstall or a plan that would delete user data is DETECTED as a failure rather
than silently accepted.  It spawns no host and removes nothing on disk; the
removal plan is evaluated as a pure function.
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
    return harness.build_uninstall_report(matrix, generated_at=FIXED_TS)


def test_lifecycle_declares_preserve_user_data_policy(report: dict) -> None:
    assert report["user_data_policy"] == "preserve"
    assert report["preserves_user_data"] is True
    assert report["orphan_residue_allowed"] == 0


def test_user_data_covers_profile_ledger_and_artifacts(report: dict) -> None:
    joined = " ".join(report["user_data_locations"])
    assert "profile.sqlite3" in joined
    assert "ledger" in joined
    assert "artifacts" in joined


def test_report_is_deterministic_and_hash_rederivable(
    matrix: dict, report: dict
) -> None:
    again = harness.build_uninstall_report(matrix, generated_at=FIXED_TS)
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = harness.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]


def test_complete_uninstall_leaves_zero_residue_and_preserves_user_data(
    report: dict,
) -> None:
    complete = report["complete_uninstall"]
    assert complete["residue_count"] == 0
    assert complete["undeclared_targets"] == []
    assert complete["user_data_deleted"] == []
    assert complete["refusals"] == []
    assert complete["final_status"] == "PASS"


def test_removable_state_and_user_data_are_disjoint(report: dict) -> None:
    assert report["removable_and_user_data_disjoint"] is True


def test_partial_uninstall_is_detected_as_failure(report: dict) -> None:
    partial = report["partial_uninstall_negative_proof"]
    assert partial["residue_count"] >= 1
    assert partial["final_status"] == "FAIL"
    codes = {r["code"] for r in partial["refusals"]}
    assert "EF_Z01_UNINSTALL_RESIDUE" in codes
    for entry in partial["refusals"]:
        assert len(entry["reason"]) > 50


def test_user_data_deleting_plan_is_refused_as_policy_violation(report: dict) -> None:
    rogue = report["user_data_deletion_negative_proof"]
    assert rogue["user_data_deleted"], "expected a modelled user-data deletion"
    assert rogue["final_status"] == "FAIL"
    codes = {r["code"] for r in rogue["refusals"]}
    assert "EF_Z01_UNINSTALL_DELETES_USER_DATA" in codes


def test_uninstall_plan_targets_only_declared_removable_state(matrix: dict) -> None:
    lifecycle = matrix["lifecycle"]
    removable = {
        entry["id"]: entry["location"] for entry in lifecycle["removable_state"]
    }
    removes = set(lifecycle["uninstall"]["removes"])
    assert removes <= set(removable), "plan targets undeclared removable state"
    assert set(removable) <= removes, "plan misses declared removable state"


def test_undeclared_removal_target_is_refused(matrix: dict) -> None:
    lifecycle = matrix["lifecycle"]
    removable = {
        entry["id"]: entry["location"] for entry in lifecycle["removable_state"]
    }
    decision = harness.uninstall_decision(
        removable,
        [*lifecycle["uninstall"]["removes"], "rogue_target"],
        lifecycle["user_data_locations"],
    )
    codes = {r["code"] for r in decision["refusals"]}
    assert "EF_Z01_UNINSTALL_UNDECLARED_TARGET" in codes
    assert decision["final_status"] == "FAIL"


def test_user_data_locations_live_outside_the_plugin_cache(matrix: dict) -> None:
    cache_template = matrix["install"]["target_layout_template"]
    prefix = cache_template.split("{marketplace}")[0] + "plugins/cache"
    for location in matrix["lifecycle"]["user_data_locations"]:
        assert not location.startswith(prefix)
        assert "plugins/cache" not in location
