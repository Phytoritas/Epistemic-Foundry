"""Shared schedule fixtures for the N05 lane suites.

Nothing here names a lane, a stage or an action of its own: the lane identities
come from the scheduler's derivation and the action vocabulary from the module
that declares it, so a change to either breaks these fixtures instead of letting
a test keep asserting a vocabulary the runtime no longer uses.

The receipts used by the effect-ledger fixtures come from the real builders in
``noetic_ledger.receipts`` and ``evolution_chamber.mutation``.  A schedule
reconciled against hand-written receipts would prove the scheduler agrees with
the test author rather than with the ledger.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

from epistemic_foundry.evolution_chamber.mutation import build_mutation_receipt
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

ROOT = Path(__file__).resolve().parents[5]
LANES_MODULE = ROOT / "src/epistemic_foundry/scheduler/v4_n05/lanes.py"

RUN_ID = "ER-N05-1"
OPERATOR = "OP-MUTATE"
STARTED = "2026-08-02T00:00:00Z"
FINISHED = "2026-08-02T00:00:05Z"
#: Read from the declaring module so a contract change surfaces here first.
STATUSES: tuple[str, ...] = tuple(get_args(EffectStatus))
SUCCEEDED = STATUSES[0]

#: Two candidates is the smallest population in which one can overtake another,
#: which is what every bound and ordering finding needs to be observable.
CANDIDATES: tuple[str, ...] = ("CAND-1", "CAND-2")


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


def serial_schedule(candidates: tuple[str, ...] = CANDIDATES) -> list[LaneEvent]:
    """Each candidate walks all three lanes before the next one starts."""

    return [
        event
        for candidate in candidates
        for lane in LANES
        for event in pass_through(lane, candidate)
    ]


def staged_schedule(candidates: tuple[str, ...] = CANDIDATES) -> list[LaneEvent]:
    """Every candidate clears a lane before any candidate enters the next.

    This is the interleaving a real runtime produces, and the one where a bound
    matters: two candidates are in flight in the same lane at the same instant.
    """

    events: list[LaneEvent] = []
    for lane in LANES:
        for candidate in candidates:
            events.append(LaneEvent(lane, LANE_ENQUEUE, candidate))
        for candidate in candidates:
            events.append(LaneEvent(lane, LANE_START, candidate))
        for candidate in candidates:
            events.append(LaneEvent(lane, LANE_CONCLUDE, candidate))
    return events


def schedule_arguments(**overrides: Any) -> dict[str, Any]:
    """Keyword arguments for a clean, fully fanned-in schedule."""

    arguments: dict[str, Any] = {
        "proposed": list(CANDIDATES),
        "events": serial_schedule(),
        "lane_limits": limits(),
    }
    arguments.update(overrides)
    return arguments


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


def genome(candidate_id: str, *, claim: str = "root-zone warming reduces set") -> dict:
    return {
        "genome_id": candidate_id,
        "claim": claim,
        "scope": {"population": "cultivar-A"},
        "predictions": ["fruit set declines"],
    }


def mutation(candidate_id: str, effect_receipt_id: str) -> dict[str, Any]:
    """A real MutationReceipt whose changed paths are diff-derived."""

    return build_mutation_receipt(
        evolution_run_id=RUN_ID,
        operator_id=OPERATOR,
        input_candidates=[genome("CAND-0")],
        output_candidate=genome(candidate_id, claim="root-zone warming delays set"),
        effect_receipt_id=effect_receipt_id,
    )


def receipted_arguments(**overrides: Any) -> dict[str, Any]:
    """A clean schedule plus the receipts that let the E05 engine reconcile it."""

    effects = [effect(f"INT-{index}") for index, _ in enumerate(CANDIDATES, start=1)]
    mutations = [
        mutation(candidate, effects[index]["receipt_id"])
        for index, candidate in enumerate(CANDIDATES)
    ]
    arguments = schedule_arguments(effect_receipts=effects, mutation_receipts=mutations)
    arguments.update(overrides)
    return arguments
