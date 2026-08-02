"""Shared fan-out fixtures built from the real receipt builders.

Nothing here hand-writes a receipt: effect receipts come from
``noetic_ledger.receipts.build_effect_receipt`` and mutation receipts from
``evolution_chamber.mutation.build_mutation_receipt``, both of which validate
against the canonical schemas.  A test that reconciled hand-made dictionaries
would prove the engine agrees with the test author rather than with the ledger.
"""

from __future__ import annotations

from typing import Any, get_args

from epistemic_foundry.evolution_chamber.mutation import build_mutation_receipt
from epistemic_foundry.noetic_ledger.receipts import EffectStatus, build_effect_receipt

STARTED = "2026-08-02T00:00:00Z"
FINISHED = "2026-08-02T00:00:05Z"
RUN_ID = "ER-E05-1"
OPERATOR = "OP-MUTATE"
#: Read from the declaring module so a contract change surfaces here first.
STATUSES: tuple[str, ...] = tuple(get_args(EffectStatus))
SUCCEEDED, FAILED, UNKNOWN, ROLLED_BACK, NOT_EXECUTED = STATUSES


def genome(candidate_id: str, *, claim: str = "root-zone warming reduces set") -> dict:
    return {
        "genome_id": candidate_id,
        "claim": claim,
        "scope": {"population": "cultivar-A"},
        "predictions": ["fruit set declines"],
    }


def effect(
    intent_id: str,
    status: str = SUCCEEDED,
    *,
    result_ids: tuple[str, ...] = ("ART-1",),
) -> dict[str, Any]:
    """A real EffectReceipt; `reconciliation_required` is derived, not passed."""

    return build_effect_receipt(
        intent_id=intent_id,
        run_id=RUN_ID,
        status=status,  # type: ignore[arg-type]
        idempotency_key=f"IDEM-{intent_id}",
        started_at=STARTED,
        finished_at=FINISHED,
        result_artifact_ids=list(result_ids) if status == SUCCEEDED else [],
    )


def mutation(
    candidate_id: str,
    effect_receipt_id: str,
    *,
    parent_id: str = "CAND-0",
) -> dict[str, Any]:
    """A real MutationReceipt whose changed paths are diff-derived."""

    return build_mutation_receipt(
        evolution_run_id=RUN_ID,
        operator_id=OPERATOR,
        input_candidates=[genome(parent_id)],
        output_candidate=genome(candidate_id, claim="root-zone warming delays set"),
        effect_receipt_id=effect_receipt_id,
    )


def clean_fanout() -> dict[str, Any]:
    """Two candidates proposed, generated, evaluated and persisted."""

    effects = [effect("INT-1"), effect("INT-2")]
    mutations = [
        mutation("CAND-1", effects[0]["receipt_id"]),
        mutation("CAND-2", effects[1]["receipt_id"]),
    ]
    return {
        "proposed": ["CAND-1", "CAND-2"],
        "generated": ["CAND-1", "CAND-2"],
        "evaluated": ["CAND-1", "CAND-2"],
        "persisted": ["CAND-1", "CAND-2"],
        "effect_receipts": effects,
        "mutation_receipts": mutations,
    }
