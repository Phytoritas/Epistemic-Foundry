"""unit_and_contract_tests — the gate composes a coherent recovery on the happy path.

A crash recovery whose every surface agrees on one run is accepted, its receipt
re-derives its own digest, and two runs over one declaration produce byte-equal
records.  The reconciliation composes the sealed EF4-I60 owner and adds the crash
boundary; the replay is honest byte-for-byte; the schedule verdict is bound to the
recovered run by construction; and a qualified evaluator update may reach a
different future run.
"""

from __future__ import annotations

import fixtures as fx
from epistemic_foundry.recovery.v4_w06 import (
    reconcile_recovery,
    recovery_hash_matches,
    require_evaluator_update_future_only,
    require_recovered,
    require_recovered_reconciliation,
    verify_crash_recovery,
)


def test_a_coherent_crash_recovery_is_accepted() -> None:
    record = verify_crash_recovery(
        fx.ROOT, integration_report=fx.integration_report(), **fx.recovery_arguments()
    )

    assert record["recovered"] is True
    assert record["evolution_run_id"] == fx.RUN_ID
    require_recovered(record)


def test_the_recovery_receipt_re_derives_its_own_digest() -> None:
    record = verify_crash_recovery(fx.ROOT, **fx.recovery_arguments())

    assert recovery_hash_matches(record)
    tampered = dict(record)
    tampered["recovered_at"] = "2026-08-03T09:99:99.000Z"
    assert not recovery_hash_matches(tampered)


def test_the_recovery_is_deterministic_over_one_declaration() -> None:
    first = verify_crash_recovery(
        fx.ROOT, integration_report=fx.integration_report(), **fx.recovery_arguments()
    )
    second = verify_crash_recovery(
        fx.ROOT, integration_report=fx.integration_report(), **fx.recovery_arguments()
    )

    assert first == second


def test_the_recovery_mutates_none_of_its_inputs() -> None:
    arguments = fx.recovery_arguments()
    snapshots = {
        key: list(arguments[key])
        for key in ("proposed", "generated", "evaluated", "persisted")
    }

    verify_crash_recovery(fx.ROOT, **arguments)

    for key, before in snapshots.items():
        assert arguments[key] == before


def test_the_schedule_verdict_is_bound_to_the_recovered_run() -> None:
    record = verify_crash_recovery(
        fx.ROOT, integration_report=fx.integration_report(), **fx.recovery_arguments()
    )
    from epistemic_foundry.domain.hashing import hash_excluding
    from epistemic_foundry.scheduler.v4_n06 import seal_integration_record

    expected = seal_integration_record(fx.integration_report(), run_id=fx.RUN_ID)
    assert record["schedule_integration_hash"] == expected["integration_hash"]
    # The stored hash re-derives from the sealed record it names.
    assert hash_excluding(expected, "integration_hash") == expected["integration_hash"]


def test_a_recovery_without_a_schedule_carries_no_schedule_hash() -> None:
    record = verify_crash_recovery(fx.ROOT, **fx.recovery_arguments())

    assert record["schedule_integration_hash"] is None
    assert record["recovered"] is True


def test_the_reconciliation_reports_no_lost_or_double_counted_candidate() -> None:
    report = reconcile_recovery(**fx.reconcile_arguments())

    assert report["recovered"] is True
    assert report["lost"] == []
    assert report["double_counted"] == []
    assert report["counts"]["expected"] == len(fx.EXPECTED)
    require_recovered_reconciliation(report)


def test_the_reconciliation_composes_the_sealed_fanout_owner() -> None:
    # The fan-out report is the reconciliation module's own, carried verbatim so
    # a reader can tell an ordinary pipeline gap from a crash-boundary defect.
    from epistemic_foundry.evolution_chamber.reconciliation import reconcile_candidates

    report = reconcile_recovery(**fx.reconcile_arguments())
    expected = reconcile_candidates(
        proposed=list(fx.EXPECTED),
        generated=list(fx.EXPECTED),
        evaluated=list(fx.EXPECTED),
        persisted=list(fx.EXPECTED),
    )
    assert report["fan_out"] == expected


def test_the_counts_reconcile_expected_across_the_crash_boundary() -> None:
    report = reconcile_recovery(
        **fx.reconcile_arguments(
            expected_candidate_ids=["CAND-1", "CAND-2", "CAND-3"],
            persisted=["CAND-1", "CAND-2"],
            failed=["CAND-3"],
        )
    )

    # Two persisted, one failed: every expected identity reached a state, none
    # lost, none counted twice.
    assert report["lost"] == []
    assert report["double_counted"] == []
    assert report["recovered"] is True


def test_a_qualified_evaluator_update_may_reach_a_different_future_run() -> None:
    # The recovered run may never be re-scored, but a *different* future run may
    # apply an approved proposal — that is the forward-only path.
    require_evaluator_update_future_only(
        fx.reassessment_for(fx.RUN_ID),
        fx.approved_proposal_for(fx.RUN_ID),
        recovered_run_id=fx.OTHER_RUN_ID,
    )
