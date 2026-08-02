"""unit_and_contract_tests — the gate integrates a run the way N06 claims.

A run with no pressure, no stall and no locks integrates and carries the sealed
schedule verdict inside its report rather than beside it; a proposal lane that
admits one candidate and defers the other under a deferral promise integrates
and names the deferral; a persistence lane that holds the resource it declares
integrates; and every one of these passes ``require_integrated_run`` without a
refusal.  The gate composes N05: the schedule verdict in the report is the same
verdict N05 would return for that interleaving.
"""

from __future__ import annotations

from epistemic_foundry.scheduler.v4_n05 import (
    PROPOSAL_LANE,
    verify_schedule,
)
from epistemic_foundry.scheduler.v4_n06 import (
    require_integrated_run,
    verify_integration,
)
from fixtures import (
    BURST_INSTANT,
    PAIR,
    ROOT,
    deferral_arguments,
    integration_arguments,
    lock_arguments,
    serial_schedule,
)


def test_a_clean_run_integrates_with_no_findings() -> None:
    report = verify_integration(ROOT, **integration_arguments())

    assert report["integrated"] is True
    for field in (
        "shed_admissions",
        "stalled_lanes",
        "unattributed_in_flight",
        "resource_overcommitments",
        "wait_cycles",
        "retained_locks",
    ):
        assert report[field] == []
    require_integrated_run(report)


def test_the_report_carries_the_sealed_schedule_verdict_it_gated() -> None:
    # The gate does not re-walk the interleaving; the verdict it reports is the
    # one the sealed scheduler produces for the same schedule.
    arguments = integration_arguments()
    report = verify_integration(ROOT, **arguments)
    direct = verify_schedule(
        ROOT,
        proposed=arguments["proposed"],
        events=arguments["events"],
        lane_limits=arguments["lane_limits"],
    )

    assert report["schedule"] == direct
    assert report["schedule"]["valid"] is True


def test_a_deferred_admission_integrates_and_is_named() -> None:
    report = verify_integration(ROOT, **deferral_arguments())

    assert report["integrated"] is True
    assert report["counts"]["deferred_admissions"] == 1
    (deferred,) = report["deferred_admissions"]
    assert deferred["candidate_id"] == PAIR[1]
    assert deferred["lane"] == PROPOSAL_LANE
    assert deferred["instant"] == BURST_INSTANT
    assert deferred["start_instant"] is not None
    assert report["shed_admissions"] == []
    require_integrated_run(report)


def test_the_declared_admission_policy_is_echoed_in_the_report() -> None:
    report = verify_integration(ROOT, **deferral_arguments())

    assert report["admission_policy"] == deferral_arguments()["admission_policy"]


def test_a_run_that_holds_its_declared_lock_integrates() -> None:
    report = verify_integration(ROOT, **lock_arguments())

    assert report["integrated"] is True
    assert report["unheld_progress"] == []
    assert report["retained_locks"] == []
    assert report["resource_overcommitments"] == []
    assert report["counts"]["resources"] == 2
    require_integrated_run(report)


def test_a_run_declaring_no_locks_carries_no_lock_findings() -> None:
    report = verify_integration(ROOT, **integration_arguments())

    assert report["counts"]["declared_locks"] == 0
    assert report["counts"]["declared_waits"] == 0
    assert report["resource_capacities"] == {}


def test_the_progress_horizon_is_echoed_in_the_report() -> None:
    arguments = integration_arguments(progress_horizon=7)
    report = verify_integration(ROOT, **arguments)

    assert report["progress_horizon"] == 7


def test_a_two_candidate_serial_run_integrates() -> None:
    # Both candidates walk all three lanes to completion, so nothing is deferred,
    # stalled or held; the gate must find a clean run clean.
    report = verify_integration(
        ROOT,
        **integration_arguments(
            proposed=list(PAIR),
            events=serial_schedule(PAIR),
            worker_assignments={PAIR[0]: "WORKER-A", PAIR[1]: "WORKER-B"},
            progress_horizon=len(serial_schedule(PAIR)),
        ),
    )

    assert report["integrated"] is True
    require_integrated_run(report)
