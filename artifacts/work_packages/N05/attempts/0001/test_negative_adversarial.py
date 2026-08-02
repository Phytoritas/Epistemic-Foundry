"""negative_and_adversarial_tests — every refusal names its own failure class.

The adversary here is not a malicious caller so much as an optimistic one: a
runtime that reports the counts it wanted, a schedule assembled after the fact to
look tidy, a lane that quietly started work early because the queue was full.
Each of those produces a schedule that would pass a gate checking only totals, so
each is given its own test and its own typed code.

Two refusals are deliberately not this package's to name.  When the lane ledgers
do not reconcile, the engine that owns reconciliation raises, because giving the
same defect a second name under a scheduler code would send a reader to the wrong
module.
"""

from __future__ import annotations

import json

import pytest
from fixtures import (
    CANDIDATES,
    ROOT,
    effect,
    limits,
    pass_through,
    receipted_arguments,
    schedule_arguments,
    serial_schedule,
    staged_schedule,
)

from epistemic_foundry.effects.v4_e05 import EffectReconciliationError
from epistemic_foundry.evolution_chamber.reconciliation import ReconciliationFailed
from epistemic_foundry.scheduler.v4_n05 import (
    BINDING_PATH,
    CANDIDATE_LEDGER_SCOPE,
    CONCURRENCY_DIMENSION,
    EVALUATION_LANE,
    LANE_CONCLUDE,
    LANE_ENQUEUE,
    LANE_FAIL,
    LANE_START,
    LANES,
    PERSISTENCE_LANE,
    PROPOSAL_LANE,
    LaneEvent,
    ScheduleError,
    load_lane_bounds,
    load_phase_binding,
    require_valid_schedule,
    verify_schedule,
)


def refuse(**overrides: object) -> ScheduleError:
    """Verify a schedule and return the refusal ``require`` raised for it."""

    report = verify_schedule(ROOT, **schedule_arguments(**overrides))  # type: ignore[arg-type]
    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    return caught.value


def binding_refusal(mutate) -> ScheduleError:  # type: ignore[no-untyped-def]
    """Apply ``mutate`` to the binding document; the file is always restored."""

    original = BINDING_PATH.read_bytes()
    document = json.loads(original.decode("utf-8"))
    mutate(document)
    try:
        BINDING_PATH.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(ScheduleError) as caught:
            load_phase_binding(ROOT)
        return caught.value
    finally:
        BINDING_PATH.write_bytes(original)


def test_a_lane_over_its_bound_is_refused_at_the_named_instant() -> None:
    report = verify_schedule(
        ROOT,
        **schedule_arguments(events=staged_schedule(), lane_limits=limits(1, 2, 2)),
    )
    breach = report["lane_bound_breaches"][0]

    assert breach["lane"] == PROPOSAL_LANE
    assert breach["bound"] == 1
    assert breach["in_flight"] == 2
    assert isinstance(breach["instant"], int)

    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "LANE_BOUND_EXCEEDED"


def test_the_breach_instant_locates_the_event_that_caused_it() -> None:
    events = staged_schedule()
    report = verify_schedule(
        ROOT, **schedule_arguments(events=events, lane_limits=limits(1, 2, 2))
    )
    breach = report["lane_bound_breaches"][0]

    culprit = events[breach["instant"]]
    assert culprit.action == LANE_START
    assert culprit.candidate_id == breach["candidate_id"]


def test_starting_evaluation_before_the_proposal_concluded_is_refused() -> None:
    events = [
        LaneEvent(EVALUATION_LANE, LANE_ENQUEUE, CANDIDATES[0]),
        LaneEvent(EVALUATION_LANE, LANE_START, CANDIDATES[0]),
    ]
    error = refuse(events=events, proposed=[CANDIDATES[0]])

    assert error.code == "LANE_ORDER_VIOLATED"
    assert error.context["lane_order_violations"][0]["upstream_lane"] == PROPOSAL_LANE


def test_persisting_before_the_evaluation_concluded_is_refused() -> None:
    """The persistence ledger is exactly what a skipped evaluation would forge."""

    events = pass_through(PROPOSAL_LANE, CANDIDATES[0])
    events += pass_through(PERSISTENCE_LANE, CANDIDATES[0])
    report = verify_schedule(
        ROOT, **schedule_arguments(events=events, proposed=[CANDIDATES[0]])
    )

    assert report["lane_ledgers"][PERSISTENCE_LANE] == [CANDIDATES[0]]
    assert report["lane_ledgers"][EVALUATION_LANE] == []
    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "LANE_ORDER_VIOLATED"


def test_a_failure_absent_from_the_accounting_is_refused() -> None:
    events = [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
        LaneEvent(PROPOSAL_LANE, LANE_START, CANDIDATES[0]),
        LaneEvent(PROPOSAL_LANE, LANE_FAIL, CANDIDATES[0]),
    ]
    error = refuse(events=events, proposed=[CANDIDATES[0]], failure_ledger=[])

    assert error.code == "SILENT_LOSS"
    assert error.context["silent_losses"] == [CANDIDATES[0]]


def test_a_failure_the_schedule_never_produced_is_refused() -> None:
    """Reconciliation accepts the claim; only the schedule can contradict it."""

    report = verify_schedule(ROOT, **schedule_arguments(failure_ledger=["CAND-GHOST"]))

    assert report["reconciliation"]["reconciled"] is True
    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "FAILURE_UNOBSERVED"


def test_a_lane_still_holding_queued_work_is_refused() -> None:
    error = refuse(
        events=[LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0])],
        proposed=[CANDIDATES[0]],
    )

    assert error.code == "FANIN_INCOMPLETE"
    assert error.context["incomplete_fanin"][0]["queued"] == [CANDIDATES[0]]


def test_a_lane_still_holding_in_flight_work_is_refused() -> None:
    error = refuse(
        events=[
            LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
            LaneEvent(PROPOSAL_LANE, LANE_START, CANDIDATES[0]),
        ],
        proposed=[CANDIDATES[0]],
    )

    assert error.code == "FANIN_INCOMPLETE"
    assert error.context["incomplete_fanin"][0]["in_flight"] == [CANDIDATES[0]]


def test_starting_work_that_was_never_queued_is_refused() -> None:
    error = refuse(
        events=[LaneEvent(PROPOSAL_LANE, LANE_START, CANDIDATES[0])],
        proposed=[CANDIDATES[0]],
    )

    assert error.code == "EVENT_UNSEQUENCED"
    assert error.context["unsequenced_events"][0]["expected"] == LANE_ENQUEUE


def test_concluding_work_that_never_started_is_refused() -> None:
    error = refuse(
        events=[
            LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
            LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, CANDIDATES[0]),
        ],
        proposed=[CANDIDATES[0]],
    )

    assert error.code == "EVENT_UNSEQUENCED"
    assert error.context["unsequenced_events"][0]["expected"] == LANE_START


def test_failing_work_that_never_started_is_refused() -> None:
    error = refuse(
        events=[
            LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
            LaneEvent(PROPOSAL_LANE, LANE_FAIL, CANDIDATES[0]),
        ],
        proposed=[CANDIDATES[0]],
        failure_ledger=[CANDIDATES[0]],
    )

    assert error.code == "EVENT_UNSEQUENCED"


def test_queueing_the_same_candidate_twice_is_refused() -> None:
    error = refuse(
        events=[
            LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
            LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, CANDIDATES[0]),
        ],
        proposed=[CANDIDATES[0]],
    )

    assert error.code == "EVENT_UNSEQUENCED"


def test_a_candidate_that_was_never_proposed_is_refused() -> None:
    events = pass_through(PROPOSAL_LANE, "CAND-SMUGGLED")
    error = refuse(events=events, proposed=[])

    assert error.code == "CANDIDATE_UNPROPOSED"
    assert error.context["unproposed_candidates"][0]["candidate_id"] == "CAND-SMUGGLED"


def test_unproposed_work_still_reaches_the_ledger_it_polluted() -> None:
    """Dropping it would hide the pollution instead of naming it."""

    report = verify_schedule(
        ROOT,
        **schedule_arguments(events=pass_through(PROPOSAL_LANE, "CAND-X"), proposed=[]),
    )

    assert report["lane_ledgers"][PROPOSAL_LANE] == ["CAND-X"]
    assert report["reconciliation"]["unknown_identities"]


def test_an_undeclared_lane_in_the_schedule_is_refused() -> None:
    with pytest.raises(ScheduleError) as caught:
        verify_schedule(
            ROOT,
            **schedule_arguments(
                events=[LaneEvent("shipping", LANE_ENQUEUE, CANDIDATES[0])]
            ),
        )
    assert caught.value.code == "LANE_UNDECLARED"
    assert caught.value.context["instant"] == 0


def test_an_undeclared_action_is_refused() -> None:
    with pytest.raises(ScheduleError) as caught:
        verify_schedule(
            ROOT,
            **schedule_arguments(
                events=[LaneEvent(PROPOSAL_LANE, "abandon", CANDIDATES[0])]
            ),
        )
    assert caught.value.code == "ACTION_UNDECLARED"


def test_an_event_that_is_not_a_lane_event_is_refused() -> None:
    with pytest.raises(ScheduleError) as caught:
        verify_schedule(
            ROOT,
            **schedule_arguments(events=[{"lane": PROPOSAL_LANE}]),
        )
    assert caught.value.code == "INPUT_INVALID"


def test_a_blank_candidate_identity_is_refused() -> None:
    with pytest.raises(ScheduleError) as caught:
        verify_schedule(
            ROOT,
            **schedule_arguments(events=[LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, "  ")]),
        )
    assert caught.value.code == "INPUT_INVALID"


def test_a_budget_that_omits_a_lane_is_refused() -> None:
    incomplete = limits()
    incomplete.pop(PERSISTENCE_LANE)

    with pytest.raises(ScheduleError) as caught:
        load_lane_bounds(incomplete)
    assert caught.value.code == "LANE_SET_INVALID"
    assert caught.value.context["missing"] == [PERSISTENCE_LANE]


def test_a_budget_naming_a_lane_that_does_not_exist_is_refused() -> None:
    extra = limits()
    extra["shipping"] = {CONCURRENCY_DIMENSION: 1}

    with pytest.raises(ScheduleError) as caught:
        load_lane_bounds(extra)
    assert caught.value.code == "LANE_SET_INVALID"
    assert caught.value.context["unknown"] == ["shipping"]


def test_a_misnamed_limit_dimension_is_refused() -> None:
    """A typo would sit in the schedule looking like a bound and enforce nothing."""

    misnamed = {lane: {"max_concurrency": 2} for lane in LANES}

    with pytest.raises(ScheduleError) as caught:
        load_lane_bounds(misnamed)
    assert caught.value.code == "LANE_LIMIT_INVALID"


@pytest.mark.parametrize("bound", [None, 0, -1, True, "2", 1.5])
def test_a_lane_without_a_usable_bound_is_refused(bound: object) -> None:
    with pytest.raises(ScheduleError) as caught:
        load_lane_bounds({lane: {CONCURRENCY_DIMENSION: bound} for lane in LANES})
    assert caught.value.code == "LANE_UNBOUNDED"


def test_a_binding_missing_a_lane_is_refused() -> None:
    def drop(document: dict) -> None:
        document["lanes"].pop(PERSISTENCE_LANE)

    error = binding_refusal(drop)

    assert error.code == "BINDING_DRIFT"
    assert error.context["missing"] == [PERSISTENCE_LANE]


def test_a_binding_naming_a_lane_that_does_not_exist_is_refused() -> None:
    def add(document: dict) -> None:
        document["lanes"]["shipping"] = {"node_ids": ["x"], "reason": "y"}

    error = binding_refusal(add)

    assert error.code == "BINDING_DRIFT"
    assert error.context["unknown"] == ["shipping"]


def test_a_binding_claiming_an_undeclared_node_is_refused() -> None:
    def invent(document: dict) -> None:
        document["lanes"][PROPOSAL_LANE]["node_ids"].append("invent_candidates")

    error = binding_refusal(invent)

    assert error.code == "PHASE_NODE_UNDECLARED"
    assert error.context["nodes"] == ["invent_candidates"]


def test_a_node_claimed_by_two_lanes_is_refused() -> None:
    def share(document: dict) -> None:
        stolen = document["lanes"][PROPOSAL_LANE]["node_ids"][0]
        document["lanes"][EVALUATION_LANE]["node_ids"].append(stolen)

    error = binding_refusal(share)

    assert error.code == "PHASE_NODE_SHARED"


def test_a_lane_that_does_not_descend_from_its_predecessor_is_refused() -> None:
    """The phase order must be the graph's, not the scheduler's assertion."""

    def detach(document: dict) -> None:
        document["lanes"][EVALUATION_LANE]["node_ids"] = ["qualify_evolution_run"]

    error = binding_refusal(detach)

    assert error.code == "PHASE_ORDER_UNSUPPORTED"
    assert error.context["upstream_lane"] == PROPOSAL_LANE


def test_a_lane_binding_no_node_is_refused() -> None:
    def empty(document: dict) -> None:
        document["lanes"][PROPOSAL_LANE]["node_ids"] = []

    assert binding_refusal(empty).code == "BINDING_UNREADABLE"


def test_a_lane_without_a_reason_is_refused() -> None:
    def blank(document: dict) -> None:
        document["lanes"][PROPOSAL_LANE]["reason"] = "   "

    assert binding_refusal(blank).code == "BINDING_UNREASONED"


def test_a_binding_without_a_contract_is_refused() -> None:
    def strip(document: dict) -> None:
        document.pop("binding_contract")

    assert binding_refusal(strip).code == "BINDING_UNREADABLE"


def test_an_unreadable_binding_fails_closed() -> None:
    original = BINDING_PATH.read_bytes()
    try:
        BINDING_PATH.write_text("{not json", encoding="utf-8")
        with pytest.raises(ScheduleError) as caught:
            load_phase_binding(ROOT)
        assert caught.value.code == "BINDING_UNREADABLE"
    finally:
        BINDING_PATH.write_bytes(original)


def test_a_report_without_a_reconciliation_is_refused() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())
    report.pop("reconciliation")

    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "RECONCILIATION_ABSENT"


def test_a_report_that_hides_which_reconciliation_ran_is_refused() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())
    report["reconciliation_scope"] = "thorough"

    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "RECONCILIATION_SCOPE_UNKNOWN"


def test_a_report_marked_invalid_without_a_finding_is_refused() -> None:
    """A hand-assembled report cannot claim a failure it does not evidence."""

    report = verify_schedule(ROOT, **schedule_arguments())
    report["valid"] = False

    with pytest.raises(ScheduleError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "SCHEDULE_UNACCOUNTED"


def test_an_unreconciled_fanout_is_refused_by_the_engine_that_owns_it() -> None:
    report = verify_schedule(
        ROOT,
        **schedule_arguments(
            proposed=[*CANDIDATES, "CAND-3"], events=serial_schedule()
        ),
    )

    assert report["reconciliation_scope"] == CANDIDATE_LEDGER_SCOPE
    with pytest.raises(ReconciliationFailed):
        require_valid_schedule(report)


def test_an_orphan_effect_receipt_is_refused_by_the_effect_engine() -> None:
    arguments = receipted_arguments()
    arguments["effect_receipts"] = [*arguments["effect_receipts"], effect("INT-ORPHAN")]
    report = verify_schedule(ROOT, **arguments)

    with pytest.raises(EffectReconciliationError) as caught:
        require_valid_schedule(report)
    assert caught.value.code == "ORPHAN_SIDE_EFFECT"


def test_provenance_is_named_before_the_findings_it_explains() -> None:
    """A candidate with no provenance makes every later count meaningless."""

    events = pass_through(PROPOSAL_LANE, "CAND-SMUGGLED")
    events.append(LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, "CAND-SMUGGLED"))
    error = refuse(events=events, proposed=[])

    assert error.code == "CANDIDATE_UNPROPOSED"


def test_a_malformed_schedule_is_named_before_the_bound_it_distorts() -> None:
    events = [
        LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, CANDIDATES[0]),
        *staged_schedule(),
    ]
    error = refuse(events=events, lane_limits=limits(1, 2, 2))

    assert error.code == "EVENT_UNSEQUENCED"
