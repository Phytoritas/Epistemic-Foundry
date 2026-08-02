"""Shared declarations for the N06 integration gate suites.

Nothing here names a lane, a lane action, a backpressure policy or a lock
action of its own.  The lane vocabulary comes from the sealed N05 scheduler
that derives it and the integration vocabulary from the N06 module that
declares it, so a change to either breaks these fixtures instead of leaving a
test asserting a vocabulary the runtime no longer uses.

The schedules are deliberately short.  The gate re-derives every lane state by
asking N05 for the verdict on each prefix of the schedule, which is quadratic
by design, so a fixture that added events for realism would buy nothing and
cost every test that uses it.

Refusal receipts come from the real builder in ``noetic_ledger.receipts``.  A
refusal accounting checked against a hand-written identifier would prove the
gate agrees with the test author rather than with the ledger.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

from epistemic_foundry.noetic_ledger.receipts import EffectStatus, build_effect_receipt
from epistemic_foundry.scheduler.v4_n05 import (
    CONCURRENCY_DIMENSION,
    EVALUATION_LANE,
    LANE_CONCLUDE,
    LANE_ENQUEUE,
    LANE_START,
    LANES,
    PERSISTENCE_LANE,
    PROPOSAL_LANE,
    LaneEvent,
)
from epistemic_foundry.scheduler.v4_n06 import (
    ADMISSION_DEFERRAL,
    ADMISSION_RECEIPTED_REFUSAL,
    LOCK_ACQUIRE,
    LOCK_RELINQUISH,
    LockEvent,
)

ROOT = Path(__file__).resolve().parents[5]
GATE_MODULE = ROOT / "src/epistemic_foundry/scheduler/v4_n06/integration.py"

RUN_ID = "ER-N06-1"
STARTED = "2026-08-02T00:00:00Z"
FINISHED = "2026-08-02T00:00:05Z"
#: Read from the declaring module so a contract change surfaces here first.
STATUSES: tuple[str, ...] = tuple(get_args(EffectStatus))
SUCCEEDED = STATUSES[0]

#: One candidate is enough for the lock and stall declarations; two is the
#: smallest population in which one can be offered to a lane the other filled,
#: which is what backpressure needs to be observable at all.
SOLO: tuple[str, ...] = ("CAND-1",)
PAIR: tuple[str, ...] = ("CAND-1", "CAND-2")

#: The resource the persistence lane is declared to need, and a second one so a
#: wait cycle has two edges to close over.
LEDGER_RESOURCE = "RES-LEDGER"
ARCHIVE_RESOURCE = "RES-ARCHIVE"

WORKERS: dict[str, str] = {"CAND-1": "WORKER-A", "CAND-2": "WORKER-B"}


def limits(proposal: Any = 2, evaluation: Any = 2, persistence: Any = 2) -> dict:
    """Per-lane hard limits, keyed by the scheduler's own lane identities."""

    return {
        PROPOSAL_LANE: {CONCURRENCY_DIMENSION: proposal},
        EVALUATION_LANE: {CONCURRENCY_DIMENSION: evaluation},
        PERSISTENCE_LANE: {CONCURRENCY_DIMENSION: persistence},
    }


def pass_through(lane: str, candidate: str) -> list[LaneEvent]:
    """One candidate queued, started and concluded in one lane."""

    return [
        LaneEvent(lane, LANE_ENQUEUE, candidate),
        LaneEvent(lane, LANE_START, candidate),
        LaneEvent(lane, LANE_CONCLUDE, candidate),
    ]


def serial_schedule(candidates: tuple[str, ...] = SOLO) -> list[LaneEvent]:
    """Each candidate walks all three lanes before the next one starts."""

    return [
        event
        for candidate in candidates
        for lane in LANES
        for event in pass_through(lane, candidate)
    ]


#: Where the solo schedule's persistence lane starts and concludes, derived
#: rather than counted by hand so a change to the lane derivation moves it.
PERSISTENCE_START = 3 * (len(LANES) - 1) + 1
PERSISTENCE_END = PERSISTENCE_START + 1
SOLO_LENGTH = 3 * len(LANES)


def integration_arguments(**overrides: Any) -> dict[str, Any]:
    """A clean run: one candidate, no pressure, no locks, no stall."""

    arguments: dict[str, Any] = {
        "proposed": list(SOLO),
        "events": serial_schedule(),
        "lane_limits": limits(),
        "admission_policy": ADMISSION_DEFERRAL,
        "progress_horizon": SOLO_LENGTH,
        "worker_assignments": {"CAND-1": WORKERS["CAND-1"]},
    }
    arguments.update(overrides)
    return arguments


def deferral_burst_events() -> list[LaneEvent]:
    """A second candidate offered to a proposal lane already at its bound.

    The first candidate is running when the second is enqueued, so the lane
    cannot start it at that instant; it starts once the first concludes, which
    is what a deferral is.  Both candidates then finish the remaining lanes, so
    the run fans in completely and the only thing under test is the admission.
    """

    first, second = PAIR
    events = [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, first),
        LaneEvent(PROPOSAL_LANE, LANE_START, first),
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, second),
        LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, first),
        LaneEvent(PROPOSAL_LANE, LANE_START, second),
        LaneEvent(PROPOSAL_LANE, LANE_CONCLUDE, second),
    ]
    for candidate in PAIR:
        for lane in (EVALUATION_LANE, PERSISTENCE_LANE):
            events.extend(pass_through(lane, candidate))
    return events


#: The instant the burst schedule offers the second candidate to a full lane.
BURST_INSTANT = 2


def deferral_arguments(**overrides: Any) -> dict[str, Any]:
    """A run whose proposal lane admits one candidate and defers the other."""

    return integration_arguments(
        proposed=list(PAIR),
        events=deferral_burst_events(),
        lane_limits=limits(proposal=1),
        worker_assignments=dict(WORKERS),
        progress_horizon=len(deferral_burst_events()),
        **overrides,
    )


def refusal_arguments(**overrides: Any) -> dict[str, Any]:
    """A run that turns the second candidate away instead of queueing it.

    The refused candidate never enters the lane, so it is accounted as work the
    run chose not to produce rather than as work still sitting in a queue.
    """

    arguments = integration_arguments(
        proposed=list(PAIR),
        lane_limits=limits(proposal=1),
        admission_policy=ADMISSION_RECEIPTED_REFUSAL,
        refusal_ledger=[refusal(PAIR[1])],
        cancelled=[PAIR[1]],
    )
    arguments.update(overrides)
    return arguments


def refusal(candidate: str, *, instant: int = 2, receipt_id: str | None = None) -> dict:
    """One refusal ledger entry, receipted by the real effect receipt builder."""

    identifier = (
        receipt_id
        if receipt_id is not None
        else effect(f"INT-{candidate}")["receipt_id"]
    )
    return {
        "candidate_id": candidate,
        "instant": instant,
        "lane": PROPOSAL_LANE,
        "receipt_id": identifier,
    }


def stall_events() -> list[LaneEvent]:
    """One candidate started in the proposal lane and then abandoned there."""

    stuck = PAIR[1]
    return [
        LaneEvent(PROPOSAL_LANE, LANE_ENQUEUE, stuck),
        LaneEvent(PROPOSAL_LANE, LANE_START, stuck),
        *serial_schedule(SOLO),
    ]


def stall_arguments(**overrides: Any) -> dict[str, Any]:
    """A run in which one worker stops while the rest of the run continues."""

    return integration_arguments(
        proposed=list(PAIR),
        events=stall_events(),
        worker_assignments=dict(WORKERS),
        progress_horizon=3,
        **overrides,
    )


def capacities(ledger: int = 1, archive: int = 1) -> dict[str, int]:
    """How many holders each declared resource may carry at one instant."""

    return {ARCHIVE_RESOURCE: archive, LEDGER_RESOURCE: ledger}


def requirements() -> dict[str, list[str]]:
    """The persistence lane may only write while it holds the ledger."""

    return {PERSISTENCE_LANE: [LEDGER_RESOURCE]}


def held_locks(candidate: str = SOLO[0]) -> list[LockEvent]:
    """Taken immediately before the write and given back once it concluded."""

    return [
        LockEvent(PERSISTENCE_START, LEDGER_RESOURCE, candidate, LOCK_ACQUIRE),
        LockEvent(SOLO_LENGTH, LEDGER_RESOURCE, candidate, LOCK_RELINQUISH),
    ]


def lock_arguments(**overrides: Any) -> dict[str, Any]:
    """A clean run whose persistence lane holds the resource it declares."""

    return integration_arguments(
        resource_capacities=capacities(),
        lock_requirements=requirements(),
        lock_events=held_locks(),
        **overrides,
    )


def deadlock_locks() -> list[LockEvent]:
    """Two workers each holding the resource the other one is waiting for."""

    first, second = WORKERS["CAND-1"], WORKERS["CAND-2"]
    return [
        LockEvent(0, LEDGER_RESOURCE, first, LOCK_ACQUIRE),
        LockEvent(0, ARCHIVE_RESOURCE, second, LOCK_ACQUIRE),
        LockEvent(SOLO_LENGTH, LEDGER_RESOURCE, first, LOCK_RELINQUISH),
        LockEvent(SOLO_LENGTH, ARCHIVE_RESOURCE, second, LOCK_RELINQUISH),
    ]


def effect(intent_id: str, status: str = SUCCEEDED) -> dict[str, Any]:
    """A real EffectReceipt; ``reconciliation_required`` is derived, not passed."""

    return build_effect_receipt(
        intent_id=intent_id,
        run_id=RUN_ID,
        status=status,  # type: ignore[arg-type]
        idempotency_key=f"IDEM-{intent_id}",
        started_at=STARTED,
        finished_at=FINISHED,
        result_artifact_ids=["ART-1"] if status == SUCCEEDED else [],
    )
