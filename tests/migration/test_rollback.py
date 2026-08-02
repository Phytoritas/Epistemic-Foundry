"""Z03 rollback_test: fail-closed rollback and backfill data-preservation proofs.

This required-check module reads the declaring source
``tests/migration/fixtures/upgrade_rollback_matrix.yaml`` and proves, through the
deterministic :mod:`z03_migration_harness`, that a FAILED migration rolls back to
the exact prior state -- the same source payload (exact source hash retained),
retained migration records, and untouched append-only promotion/effect history --
and that any plan which discards the source, changes its hash, drops migration
records, rewrites history, or leaves unresolved records is refused fail-closed.
Backfill batches are evaluated against the composed contract's ``backfill`` block.
Nothing is restored, written, or deleted on disk; the plans are pure functions.
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
    return harness.build_rollback_report(matrix, generated_at=FIXED_TS)


def _case(report: dict, case_id: str) -> dict:
    return next(c for c in report["rollback_cases"] if c["case_id"] == case_id)


def test_report_composes_contract_rollback_policy_by_citation(report: dict) -> None:
    # These come verbatim from the read-only contract, not restated by the harness.
    assert report["contract_rollback_policy"] == {
        "v3_source_retained": True,
        "exact_source_hash_required": True,
        "migration_records_retained": True,
        "promotion_or_effect_history_rewritten": False,
    }
    assert report["contract_backfill_policy"]["dry_run_before_write"] is True
    assert report["contract_backfill_policy"]["unresolved_records_fail_closed"] is True
    assert (
        report["contract_backfill_policy"]["partial_success_is_not_batch_success"]
        is True
    )


def test_report_is_deterministic_and_hash_rederivable(
    matrix: dict, report: dict
) -> None:
    again = harness.build_rollback_report(matrix, generated_at=FIXED_TS)
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = harness.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]


def test_failed_migration_restores_exact_prior_state(report: dict) -> None:
    case = _case(report, "failed_v3_to_v4_restores_exact_prior_state")
    assert case["migration_status"] == "FAILED"
    assert case["final_status"] == "PASS"
    assert case["refusals"] == []
    assert case["restores_exact_prior_state"] is True
    # Exact source hash retained: restored payload hash equals the prior source
    # hash, and the whole restored state hashes to the prior state hash.
    assert case["restored_hash"] == case["source_hash"]
    assert case["restored_state_hash"] == case["prior_state_hash"]


def test_rollback_that_discards_source_is_refused(report: dict) -> None:
    case = _case(report, "rollback_that_discards_source_is_refused")
    assert case["final_status"] == "FAIL"
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_ROLLBACK_SOURCE_DISCARDED" in codes


def test_rollback_with_inexact_source_hash_is_refused(report: dict) -> None:
    case = _case(report, "rollback_with_inexact_source_hash_is_refused")
    assert case["final_status"] == "FAIL"
    assert case["restored_hash"] != case["source_hash"]
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_ROLLBACK_HASH_MISMATCH" in codes


def test_rollback_that_drops_migration_records_is_refused(report: dict) -> None:
    case = _case(report, "rollback_that_drops_migration_records_is_refused")
    assert case["final_status"] == "FAIL"
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_ROLLBACK_MIGRATION_RECORDS_LOST" in codes


def test_rollback_that_rewrites_history_is_refused(report: dict) -> None:
    case = _case(report, "rollback_that_rewrites_history_is_refused")
    assert case["final_status"] == "FAIL"
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_ROLLBACK_HISTORY_REWRITTEN" in codes


def test_unresolved_records_fail_closed(report: dict) -> None:
    case = _case(report, "rollback_with_unresolved_records_fails_closed")
    assert case["final_status"] == "FAIL"
    assert case["unresolved_records"]
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_UNRESOLVED_RECORDS_FAIL_CLOSED" in codes


def test_only_the_positive_case_restores_exact_prior_state(report: dict) -> None:
    passing = [c for c in report["rollback_cases"] if c["final_status"] == "PASS"]
    assert len(passing) == 1
    assert passing[0]["restores_exact_prior_state"] is True
    for case in report["rollback_cases"]:
        if case["final_status"] == "FAIL":
            assert case["restores_exact_prior_state"] is False


def test_every_rollback_refusal_reason_exceeds_fifty_characters(report: dict) -> None:
    for case in report["rollback_cases"]:
        for entry in case["refusals"]:
            assert len(entry["reason"]) > 50


def test_rollback_decision_is_a_pure_function(matrix: dict) -> None:
    # Evaluating the same declared case twice yields byte-identical results, and
    # the source case dict is not mutated by evaluation.
    case = copy.deepcopy(matrix["rollback_cases"][0])
    snapshot = copy.deepcopy(case)
    first = harness.rollback_decision(case)
    second = harness.rollback_decision(case)
    assert first == second
    assert case == snapshot


def test_clean_backfill_batch_commits(report: dict) -> None:
    case = next(
        c
        for c in report["backfill_cases"]
        if c["case_id"] == "clean_batch_with_dry_run_and_all_resolved"
    )
    assert case["final_status"] == "PASS"
    assert case["committed_as_batch"] is True


def test_backfill_without_dry_run_is_refused(report: dict) -> None:
    case = next(
        c
        for c in report["backfill_cases"]
        if c["case_id"] == "batch_without_dry_run_is_refused"
    )
    assert case["final_status"] == "FAIL"
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_BACKFILL_DRY_RUN_MISSING" in codes


def test_backfill_partial_success_is_not_batch_success(report: dict) -> None:
    case = next(
        c
        for c in report["backfill_cases"]
        if c["case_id"] == "batch_with_one_unresolved_record_fails_closed"
    )
    assert case["final_status"] == "FAIL"
    assert case["committed_as_batch"] is False
    codes = {r["code"] for r in case["refusals"]}
    assert "EF_Z03_BACKFILL_UNRESOLVED_RECORD" in codes
