"""unit_and_contract_tests — a well-formed schedule is accounted for exactly.

The happy path here is not "it did not raise".  A schedule that passes must
produce lane ledgers that feed the reconciliation the run actually needs, bounds
read from the declared budget rather than from the scheduler's own opinion, and a
report that is byte-identical on a second pass over the same events.  Anything
less would let a gate pass while proving nothing about the run it judged.

The two interleavings exercised here are the two that matter: one candidate at a
time, where no bound can ever bite, and every candidate clearing a lane together,
where the bound is exactly what stands between the run and unbounded fan-out.
"""

from __future__ import annotations

import copy
import json

from fixtures import (
    CANDIDATES,
    ROOT,
    limits,
    pass_through,
    receipted_arguments,
    schedule_arguments,
    serial_schedule,
    staged_schedule,
)

from epistemic_foundry.scheduler.v4_n05 import (
    CANDIDATE_LEDGER_SCOPE,
    CONCURRENCY_DIMENSION,
    EFFECT_LEDGER_SCOPE,
    EVALUATION_LANE,
    LANE_CONCLUDE,
    LANE_ENQUEUE,
    LANE_FAIL,
    LANE_START,
    LANES,
    PERSISTENCE_LANE,
    PROPOSAL_LANE,
    LaneEvent,
    load_lane_bounds,
    load_phase_binding,
    require_valid_schedule,
    verify_schedule,
)


def test_a_serial_schedule_is_accounted_for() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())

    assert report["valid"] is True
    require_valid_schedule(report)


def test_a_staged_schedule_within_its_bounds_is_accounted_for() -> None:
    report = verify_schedule(ROOT, **schedule_arguments(events=staged_schedule()))

    assert report["valid"] is True
    assert report["lane_bound_breaches"] == []
    require_valid_schedule(report)


def test_a_lane_exactly_at_its_bound_is_not_a_breach() -> None:
    """The bound is a ceiling, not a strict inequality; two lanes at two is fine."""

    report = verify_schedule(
        ROOT,
        **schedule_arguments(events=staged_schedule(), lane_limits=limits(2, 2, 2)),
    )

    assert report["lane_bound_breaches"] == []


def test_every_lane_ledger_holds_every_candidate() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())

    for lane in LANES:
        assert report["lane_ledgers"][lane] == sorted(CANDIDATES)


def test_the_lane_ledgers_are_keyed_by_the_pipeline_stages() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())

    assert tuple(report["lane_ledgers"]) == LANES


def test_without_receipts_only_the_candidate_fanout_reconciles() -> None:
    """The weaker check is named rather than implied to be the stronger one."""

    report = verify_schedule(ROOT, **schedule_arguments())

    assert report["reconciliation_scope"] == CANDIDATE_LEDGER_SCOPE
    assert "effect_receipts" not in report["reconciliation"]["counts"]


def test_with_receipts_the_effect_ledger_engine_reconciles() -> None:
    report = verify_schedule(ROOT, **receipted_arguments())

    assert report["reconciliation_scope"] == EFFECT_LEDGER_SCOPE
    assert report["reconciliation"]["counts"]["effect_receipts"] == len(CANDIDATES)
    assert report["reconciliation"]["counts"]["mutation_receipts"] == len(CANDIDATES)
    assert report["valid"] is True
    require_valid_schedule(report)


def test_the_bounds_are_read_from_the_declared_budget_limits() -> None:
    bounds = load_lane_bounds(limits(3, 2, 1))

    assert bounds == {PROPOSAL_LANE: 3, EVALUATION_LANE: 2, PERSISTENCE_LANE: 1}


def test_an_unspecified_budget_dimension_does_not_become_a_bound() -> None:
    """The envelope normalizer fills the rest with explicit nulls, not defaults."""

    bounds = load_lane_bounds(
        {lane: {CONCURRENCY_DIMENSION: 4, "tokens": None} for lane in LANES}
    )

    assert set(bounds) == set(LANES)
    assert set(bounds.values()) == {4}


def test_the_report_counts_the_events_and_the_lanes() -> None:
    events = serial_schedule()
    report = verify_schedule(ROOT, **schedule_arguments(events=events))

    assert report["counts"]["events"] == len(events)
    assert report["counts"]["lanes"] == len(LANES)
    assert report["counts"]["observed_failures"] == 0


def test_the_report_carries_the_phase_binding_it_verified() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())

    assert report["phase_binding"] == load_phase_binding(ROOT).as_report()


def test_a_declared_failure_reconciles_without_a_gap() -> None:
    """A candidate that fails is terminal, not missing."""

    lost, kept = CANDIDATES[1], CANDIDATES[0]
    events = pass_through(PROPOSAL_LANE, kept) + [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, lost),
        LaneEvent(PROPOSAL_LANE, LANE_START, lost),
        LaneEvent(PROPOSAL_LANE, LANE_FAIL, lost),
    ]
    events += pass_through(EVALUATION_LANE, kept)
    events += pass_through(PERSISTENCE_LANE, kept)

    report = verify_schedule(
        ROOT, **schedule_arguments(events=events, failure_ledger=[lost])
    )

    assert report["silent_losses"] == []
    assert report["counts"]["observed_failures"] == 1
    assert report["valid"] is True
    require_valid_schedule(report)


def test_an_empty_run_is_accounted_for_rather_than_assumed_broken() -> None:
    report = verify_schedule(ROOT, **schedule_arguments(proposed=[], events=[]))

    assert report["valid"] is True
    require_valid_schedule(report)


def test_the_report_is_serialisable_evidence() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

    assert json.loads(encoded) == report


def test_the_same_schedule_produces_the_same_report() -> None:
    """Event order is the only clock, so a replay must be byte-equal."""

    first = verify_schedule(ROOT, **schedule_arguments(events=staged_schedule()))
    second = verify_schedule(ROOT, **schedule_arguments(events=staged_schedule()))

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_gate_mutates_nothing_it_was_given() -> None:
    arguments = schedule_arguments(events=staged_schedule(), failure_ledger=[])
    before = copy.deepcopy(arguments)

    verify_schedule(ROOT, **arguments)

    assert arguments == before


def test_a_completed_single_lane_pass_leaves_nothing_in_flight() -> None:
    events = pass_through(PROPOSAL_LANE, CANDIDATES[0])
    report = verify_schedule(
        ROOT, **schedule_arguments(proposed=[CANDIDATES[0]], events=events)
    )

    assert report["lane_ledgers"][PROPOSAL_LANE] == [CANDIDATES[0]]
    assert report["incomplete_fanin"] == []


def test_a_candidate_reaches_the_persistence_ledger_only_through_both_lanes() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())

    assert report["lane_order_violations"] == []
    assert report["lane_ledgers"][PERSISTENCE_LANE] == sorted(CANDIDATES)
    assert report["reconciliation"]["reconciled"] is True


def test_a_concluding_event_removes_the_candidate_from_flight() -> None:
    events = [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
        LaneEvent(PROPOSAL_LANE, LANE_START, CANDIDATES[0]),
        LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, CANDIDATES[0]),
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[1]),
        LaneEvent(PROPOSAL_LANE, LANE_START, CANDIDATES[1]),
    ]
    report = verify_schedule(
        ROOT, **schedule_arguments(events=events, lane_limits=limits(1, 1, 1))
    )

    assert report["lane_bound_breaches"] == []
