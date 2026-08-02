"""negative_and_adversarial_tests — every refusal fires for its stated reason.

The gate's value is in what it will not pass.  Each test here drives one
declared failure across the three integration surfaces — backpressure, the
missing worker, and the resource lock — and asserts that ``require_integrated_run``
raises with exactly the finding code that names it.  A future change that
silences a guard, swallows a partial fan-in, or renames a code fails here rather
than shipping a run that shed work in silence, stalled a worker unseen, or
overcommitted a resource it declared exclusive.

Two things are asserted about the layering, because they are what keeps this
gate composed with the sealed scheduler rather than duplicating it.  A schedule
that does not add up is refused by N05's own ``ScheduleError`` carrying N05's own
code — the crash/resume prefix is exactly that.  A schedule that adds up but was
integrated badly is refused by this gate's ``IntegrationError``.  A caller can
tell the two layers apart because the exception types are different.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.scheduler.v4_n05 import (
    EVALUATION_LANE,
    LANE_CONCLUDE,
    LANE_ENQUEUE,
    LANE_START,
    PERSISTENCE_LANE,
    PROPOSAL_LANE,
    LaneEvent,
    ScheduleError,
)
from epistemic_foundry.scheduler.v4_n06 import (
    ADMISSION_DEFERRAL,
    ADMISSION_RECEIPTED_REFUSAL,
    LOCK_ACQUIRE,
    LOCK_RELINQUISH,
    IntegrationError,
    LockEvent,
    WaitEdge,
    require_integrated_run,
    verify_integration,
)
from fixtures import (
    ARCHIVE_RESOURCE,
    LEDGER_RESOURCE,
    PAIR,
    PERSISTENCE_START,
    ROOT,
    SOLO_LENGTH,
    WORKERS,
    capacities,
    deadlock_locks,
    deferral_burst_events,
    integration_arguments,
    limits,
    pass_through,
    refusal,
    refusal_arguments,
    requirements,
    stall_arguments,
    stall_events,
)


def _integration_refused(code: str, **arguments: object) -> None:
    report = verify_integration(ROOT, **arguments)  # type: ignore[arg-type]
    with pytest.raises(IntegrationError) as caught:
        require_integrated_run(report)
    assert caught.value.code == code, (
        f"expected {code}, got {caught.value.code}: {caught.value}"
    )


def _rejected_at_call(code: str, **arguments: object) -> None:
    with pytest.raises(IntegrationError) as caught:
        verify_integration(ROOT, **arguments)  # type: ignore[arg-type]
    assert caught.value.code == code, (
        f"expected {code}, got {caught.value.code}: {caught.value}"
    )


# --- backpressure ---------------------------------------------------------


def _shed_events() -> list[LaneEvent]:
    """The second candidate is offered to a full lane and then abandoned.

    Nothing starts it, no receipt names it, and it is in no failure ledger, so
    the run has shed it in silence — the one backpressure outcome the gate exists
    to refuse.
    """

    first, second = PAIR
    events = [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, first),
        LaneEvent(PROPOSAL_LANE, LANE_START, first),
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, second),
        LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, first),
    ]
    for lane in (EVALUATION_LANE, PERSISTENCE_LANE):
        events.extend(pass_through(lane, first))
    return events


def test_work_shed_from_a_full_lane_is_refused() -> None:
    _integration_refused(
        "ADMISSION_SILENTLY_SHED",
        proposed=list(PAIR),
        events=_shed_events(),
        lane_limits=limits(proposal=1),
        admission_policy=ADMISSION_DEFERRAL,
        progress_horizon=50,
        worker_assignments=dict(WORKERS),
    )


def test_a_deferral_promise_contradicted_by_a_refusal_is_refused() -> None:
    # The run promised a receipted refusal but the schedule queued and started
    # the second candidate, which is the deferral behaviour; the operator's model
    # of what a full lane does is false.
    _integration_refused(
        "ADMISSION_POLICY_CONTRADICTED",
        proposed=list(PAIR),
        events=deferral_burst_events(),
        lane_limits=limits(proposal=1),
        admission_policy=ADMISSION_RECEIPTED_REFUSAL,
        progress_horizon=50,
        worker_assignments=dict(WORKERS),
    )


def test_a_refusal_with_nothing_handed_back_is_refused() -> None:
    _integration_refused(
        "ADMISSION_REFUSAL_UNRECEIPTED",
        **refusal_arguments(
            refusal_ledger=[
                {"candidate_id": PAIR[1], "instant": 2, "lane": PROPOSAL_LANE}
            ]
        ),
    )


def test_a_refusal_at_an_instant_the_lane_was_not_full_is_refused() -> None:
    _integration_refused(
        "ADMISSION_REFUSAL_UNWARRANTED",
        **refusal_arguments(refusal_ledger=[refusal(PAIR[1], instant=0)]),
    )


def test_a_backpressure_policy_that_was_never_declared_is_refused() -> None:
    _rejected_at_call(
        "ADMISSION_POLICY_UNDECLARED",
        **integration_arguments(admission_policy="drop"),
    )


# --- missing worker -------------------------------------------------------


def test_a_lane_that_stalls_past_the_horizon_is_refused() -> None:
    _integration_refused("LANE_PROGRESS_STALLED", **stall_arguments())


def test_in_flight_work_no_declared_worker_holds_is_refused() -> None:
    # One candidate is stuck in flight; with no worker assigned to it, a stall
    # could never be attributed to anyone, so the run is refused before it even
    # counts as stalled.
    _integration_refused(
        "WORKER_ATTRIBUTION_MISSING",
        proposed=list(PAIR),
        events=stall_events(),
        lane_limits=limits(),
        admission_policy=ADMISSION_DEFERRAL,
        progress_horizon=50,
        worker_assignments={PAIR[0]: WORKERS[PAIR[0]]},
    )


# --- resource locks -------------------------------------------------------


def test_more_holders_than_a_resource_declared_is_refused() -> None:
    over = [
        LockEvent(0, LEDGER_RESOURCE, "HOLDER-1", LOCK_ACQUIRE),
        LockEvent(0, LEDGER_RESOURCE, "HOLDER-2", LOCK_ACQUIRE),
        LockEvent(SOLO_LENGTH, LEDGER_RESOURCE, "HOLDER-1", LOCK_RELINQUISH),
        LockEvent(SOLO_LENGTH, LEDGER_RESOURCE, "HOLDER-2", LOCK_RELINQUISH),
    ]
    _integration_refused(
        "RESOURCE_OVERCOMMITTED",
        **integration_arguments(resource_capacities=capacities(), lock_events=over),
    )


def test_progress_without_a_required_lock_is_refused() -> None:
    _integration_refused(
        "LOCK_REQUIREMENT_UNMET",
        **integration_arguments(
            resource_capacities=capacities(),
            lock_requirements=requirements(),
            lock_events=(),
        ),
    )


def test_a_resource_still_held_at_the_end_is_refused() -> None:
    _integration_refused(
        "LOCK_RETAINED_AT_END",
        **integration_arguments(
            resource_capacities=capacities(),
            lock_events=[
                LockEvent(PERSISTENCE_START, LEDGER_RESOURCE, "CAND-1", LOCK_ACQUIRE)
            ],
        ),
    )


def test_a_holder_taking_a_lock_it_already_holds_is_refused() -> None:
    _integration_refused(
        "LOCK_SEQUENCE_IMPOSSIBLE",
        **integration_arguments(
            resource_capacities=capacities(),
            lock_events=[
                LockEvent(0, LEDGER_RESOURCE, "HOLDER-1", LOCK_ACQUIRE),
                LockEvent(1, LEDGER_RESOURCE, "HOLDER-1", LOCK_ACQUIRE),
                LockEvent(SOLO_LENGTH, LEDGER_RESOURCE, "HOLDER-1", LOCK_RELINQUISH),
            ],
        ),
    )


def test_a_declared_wait_cycle_is_refused_as_a_deadlock() -> None:
    worker_a, worker_b = WORKERS["CAND-1"], WORKERS["CAND-2"]
    waits = [
        WaitEdge(0, worker_a, ARCHIVE_RESOURCE),
        WaitEdge(0, worker_b, LEDGER_RESOURCE),
    ]
    _integration_refused(
        "WAIT_CYCLE_DEADLOCKED",
        **integration_arguments(
            resource_capacities=capacities(),
            lock_events=deadlock_locks(),
            wait_edges=waits,
        ),
    )


def test_a_lock_on_an_undeclared_resource_is_refused() -> None:
    _rejected_at_call(
        "RESOURCE_UNDECLARED",
        **integration_arguments(lock_requirements=requirements()),
    )


# --- crash / resume: the sealed scheduler still owns the schedule ----------


def test_a_prefix_that_never_fanned_in_is_refused_by_the_scheduler() -> None:
    # A run cut short mid-schedule ends with a lane still holding work; that is
    # N05's FANIN_INCOMPLETE, and the gate re-raises it under N05's own exception
    # type rather than a code of its own, so the defect keeps one name.
    from fixtures import serial_schedule

    report = verify_integration(
        ROOT, **integration_arguments(events=serial_schedule()[:5], progress_horizon=50)
    )
    assert report["integrated"] is False
    with pytest.raises(ScheduleError) as caught:
        require_integrated_run(report)
    assert caught.value.code == "FANIN_INCOMPLETE"


def test_a_schedule_longer_than_the_gate_re_derives_is_refused() -> None:
    long_schedule = [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, f"CAND-{index}") for index in range(600)
    ]
    _rejected_at_call(
        "SCHEDULE_LENGTH_UNSUPPORTED",
        **integration_arguments(events=long_schedule),
    )
