"""Shared concurrency fixtures built from the real receipt builders.

Nothing here hand-writes a receipt: effect receipts come from
``noetic_ledger.receipts.build_effect_receipt`` and mutation receipts from
``evolution_chamber.mutation.build_mutation_receipt``, both of which validate
against the canonical schemas.  A gate that admitted hand-made dictionaries
would prove it agrees with the test author rather than with the ledger.

The interleaving helpers exist so a test names a *schedule* rather than a list
of event dictionaries: ``serial(a, b)`` and ``interleaved(a, b)`` are the two
schedules every concurrency claim in this package is stated against, and a
test that has to spell out six events to say "these two lanes overlapped" hides
what it is actually asserting.
"""

from __future__ import annotations

from typing import Any, get_args

from epistemic_foundry.effects.v4_e06 import BEGIN, COMMIT, EFFECT
from epistemic_foundry.evolution_chamber.mutation import build_mutation_receipt
from epistemic_foundry.noetic_ledger.receipts import EffectStatus, build_effect_receipt

STARTED = "2026-08-02T00:00:00Z"
FINISHED = "2026-08-02T00:00:05Z"
RUN_ID = "ER-E06-1"
OPERATOR = "OP-MUTATE"
#: Read from the declaring module so a contract change surfaces here first.
STATUSES: tuple[str, ...] = tuple(get_args(EffectStatus))
SUCCEEDED, FAILED, UNKNOWN, ROLLED_BACK, NOT_EXECUTED = STATUSES

#: The two targets every scenario writes to, and where they start.
TARGET_A = "workspace/W-1/hypothesis/H-1"
TARGET_B = "workspace/W-1/hypothesis/H-2"
REV_0 = "rev-0"
REV_1 = "rev-1"
REV_2 = "rev-2"
INITIAL_REVISIONS: dict[str, str] = {TARGET_A: REV_0, TARGET_B: REV_0}


def genome(candidate_id: str, *, claim: str = "root-zone warming reduces set") -> dict:
    return {
        "genome_id": candidate_id,
        "claim": claim,
        "scope": {"population": "cultivar-A"},
        "predictions": ["fruit set declines"],
    }


def effect_receipt(
    intent_id: str,
    idempotency_key: str,
    status: str = SUCCEEDED,
    *,
    result_ids: tuple[str, ...] = ("ART-1",),
) -> dict[str, Any]:
    """A real EffectReceipt; `reconciliation_required` is derived, not passed."""

    return build_effect_receipt(
        intent_id=intent_id,
        run_id=RUN_ID,
        status=status,  # type: ignore[arg-type]
        idempotency_key=idempotency_key,
        started_at=STARTED,
        finished_at=FINISHED,
        result_artifact_ids=list(result_ids) if status == SUCCEEDED else [],
    )


def mutation(
    candidate_id: str, effect_receipt_id: str, *, parent_id: str = "CAND-0"
) -> dict[str, Any]:
    """A real MutationReceipt whose changed paths are diff-derived."""

    return build_mutation_receipt(
        evolution_run_id=RUN_ID,
        operator_id=OPERATOR,
        input_candidates=[genome(parent_id)],
        output_candidate=genome(candidate_id, claim="root-zone warming delays set"),
        effect_receipt_id=effect_receipt_id,
    )


def action(
    action_id: str,
    *,
    candidate_id: str,
    idempotency_key: str,
    receipt: dict[str, Any],
    target_ref: str = TARGET_A,
    base_revision: str = REV_0,
    new_revision: str = REV_1,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One candidate action as the gate expects it."""

    return {
        "action_id": action_id,
        "base_revision": base_revision,
        "candidate_id": candidate_id,
        "effect_receipt": receipt,
        "idempotency_key": idempotency_key,
        "new_revision": new_revision,
        "payload": payload if payload is not None else {"claim": candidate_id},
        "target_ref": target_ref,
    }


def lane(lane_id: str, action_id: str) -> list[dict[str, str]]:
    """One lane running one action from begin to commit."""

    return [
        {"action_id": action_id, "lane": lane_id, "phase": phase}
        for phase in (BEGIN, EFFECT, COMMIT)
    ]


def serial(first: str, second: str) -> list[dict[str, str]]:
    """Lane 1 finishes entirely before lane 2 begins."""

    return lane("L1", first) + lane("L2", second)


def interleaved(first: str, second: str) -> list[dict[str, str]]:
    """Both lanes begin, then run their effect and commit in turn."""

    return [
        {"action_id": first, "lane": "L1", "phase": BEGIN},
        {"action_id": second, "lane": "L2", "phase": BEGIN},
        {"action_id": first, "lane": "L1", "phase": EFFECT},
        {"action_id": second, "lane": "L2", "phase": EFFECT},
        {"action_id": first, "lane": "L1", "phase": COMMIT},
        {"action_id": second, "lane": "L2", "phase": COMMIT},
    ]


def schedules(first: str, second: str) -> list[dict[str, Any]]:
    """The three schedules two lanes over two actions can actually produce."""

    return [
        {"events": serial(first, second), "interleaving_id": "IL-SERIAL"},
        {"events": serial(second, first), "interleaving_id": "IL-REVERSED"},
        {"events": interleaved(first, second), "interleaving_id": "IL-CROSSED"},
    ]


def disjoint_actions() -> list[dict[str, Any]]:
    """Two candidates writing two different targets: no schedule can collide."""

    first = effect_receipt("INT-1", "IDEM-1")
    second = effect_receipt("INT-2", "IDEM-2")
    return [
        action(
            "ACT-1",
            candidate_id="CAND-1",
            idempotency_key="IDEM-1",
            receipt=first,
            target_ref=TARGET_A,
        ),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=second,
            target_ref=TARGET_B,
        ),
    ]


def disjoint_gate() -> dict[str, Any]:
    """A whole gate call over two non-colliding candidates, ready to run."""

    actions = disjoint_actions()
    return {
        "actions": actions,
        "evaluated": ["CAND-1", "CAND-2"],
        "generated": ["CAND-1", "CAND-2"],
        "initial_revisions": INITIAL_REVISIONS,
        "interleavings": schedules("ACT-1", "ACT-2"),
        "mutation_receipts": [
            mutation("CAND-1", actions[0]["effect_receipt"]["receipt_id"]),
            mutation("CAND-2", actions[1]["effect_receipt"]["receipt_id"]),
        ],
        "persisted": ["CAND-1", "CAND-2"],
        "proposed": ["CAND-1", "CAND-2"],
    }


def retry_actions() -> list[dict[str, Any]]:
    """One candidate action and its retry: same key, same payload, one receipt.

    The retry carries the *same* receipt object because that is what an
    idempotency reservation returns — a second receipt for one key would be the
    duplicated external effect the key exists to prevent.
    """

    receipt = effect_receipt("INT-1", "IDEM-1")
    payload = {"claim": "CAND-1"}
    return [
        action(
            "ACT-1",
            candidate_id="CAND-1",
            idempotency_key="IDEM-1",
            receipt=receipt,
            payload=payload,
        ),
        action(
            "ACT-1R",
            candidate_id="CAND-1",
            idempotency_key="IDEM-1",
            receipt=receipt,
            payload=payload,
        ),
    ]


def retry_gate() -> dict[str, Any]:
    """A candidate action retried under one key, across every schedule."""

    actions = retry_actions()
    return {
        "actions": actions,
        "evaluated": ["CAND-1"],
        "generated": ["CAND-1"],
        "initial_revisions": INITIAL_REVISIONS,
        "interleavings": schedules("ACT-1", "ACT-1R"),
        "mutation_receipts": [
            mutation("CAND-1", actions[0]["effect_receipt"]["receipt_id"])
        ],
        "persisted": ["CAND-1"],
        "proposed": ["CAND-1"],
    }
