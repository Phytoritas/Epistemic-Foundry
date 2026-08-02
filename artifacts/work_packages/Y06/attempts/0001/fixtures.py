"""Shared fixtures for the Y06 qualification integration-gate suite.

Nothing here hand-writes a canonical receipt: effect receipts come from
``noetic_ledger.receipts.build_effect_receipt``, mutation receipts from
``evolution_chamber.mutation.build_mutation_receipt``, budget envelopes from
``budgets.envelope.build_budget_envelope`` and triage reports from Y05's
``triage_at_scale``, so a test reconciles what the real builders emit rather than
what the test author guessed.  The canonical tokens are restated here as test
constants and pinned against the schemas and declaring modules by
``test_schema_and_type``: if a ladder reorders or a capability is renamed, that
suite fails at the assertion rather than letting a test exercise the wrong token.
"""

from __future__ import annotations

from typing import Any, get_args

from epistemic_foundry.budgets.envelope import build_budget_envelope
from epistemic_foundry.evolution_chamber.mutation import build_mutation_receipt
from epistemic_foundry.governance.evolution_authority.registry import (
    PROMOTION_COMMIT_CAPABILITY,
)
from epistemic_foundry.noetic_ledger.receipts import EffectStatus, build_effect_receipt
from epistemic_foundry.operations.v4_y05 import triage_at_scale

# --- surrogate triage decision ladder (surrogate-triage-report.triage_decision) -
EVALUATE_NOW = "EVALUATE_NOW"
DEFER = "DEFER"
SAMPLE_FOR_CALIBRATION = "SAMPLE_FOR_CALIBRATION"
REJECT_ONLY_ON_HARD_GATE = "REJECT_ONLY_ON_HARD_GATE"

# --- budget enforcement ladder (budget-envelope.enforcement) -------------------
HARD_METERED = "HARD_METERED"
HARD_PREALLOCATED = "HARD_PREALLOCATED"
SOFT_ESTIMATE = "SOFT_ESTIMATE"
UNMETERED = "UNMETERED"

# --- budget breach policy ladder (budget-envelope.breach_policy) ---------------
CANCEL = "CANCEL"
PAUSE_AND_ESCALATE = "PAUSE_AND_ESCALATE"
MARK_PARTIAL = "MARK_PARTIAL"
WARN = "WARN"

# --- effect status vocabulary (read from the declaring module) -----------------
STATUSES: tuple[str, ...] = tuple(get_args(EffectStatus))
SUCCEEDED, EFFECT_FAILED, UNKNOWN, ROLLED_BACK, NOT_EXECUTED = STATUSES

# --- the canonical promotion-commit capability (imported, never restated) ------
PROMOTION_CAPABILITY = PROMOTION_COMMIT_CAPABILITY

STARTED = "2026-08-02T00:00:00Z"
FINISHED = "2026-08-02T00:00:05Z"
RUN_ID = "ER-Y06-1"
OPERATOR = "OP-MUTATE"
STAMP = "2026-08-01T00:00:00+00:00"
EMPTY_LIMITS = {
    "tokens": None,
    "calls": None,
    "wall_seconds": None,
    "concurrency": None,
    "storage_bytes": None,
    "network_bytes": None,
}


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
    """A real EffectReceipt; ``reconciliation_required`` is derived, not passed."""
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
    """Two candidates proposed, generated, evaluated and persisted, fully receipted."""
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


def expected_counts(**overrides: Any) -> dict[str, int]:
    """The counts the qualification declares it expects, matching ``clean_fanout``."""
    counts = {"proposed": 2, "generated": 2, "evaluated": 2, "persisted": 2}
    counts.update(overrides)
    return counts


def bounded_budget(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "enforcement": HARD_METERED,
        "hard_limits": {"tokens": 100_000, "wall_seconds": 3_600},
        "soft_cost_currency": "USD",
        "soft_cost_amount": 50.0,
        "metering_authority": "kernel-meter",
        "breach_policy": MARK_PARTIAL,
        "budget_id": "BE-Y06-01",
        "created_at": STAMP,
    }
    kwargs.update(overrides)
    return build_budget_envelope(**kwargs)


def soft_budget(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "enforcement": SOFT_ESTIMATE,
        "hard_limits": dict(EMPTY_LIMITS),
        "soft_cost_currency": "USD",
        "soft_cost_amount": 50.0,
        "metering_authority": "kernel-meter",
        "breach_policy": WARN,
        "budget_id": "BE-Y06-02",
        "created_at": STAMP,
    }
    kwargs.update(overrides)
    return build_budget_envelope(**kwargs)


def measured_usage(**overrides: Any) -> dict[str, float]:
    usage = {"tokens": 90_000.0, "wall_seconds": 3_000.0}
    usage.update(overrides)
    return usage


def triage(candidate_id: str = "CAND-1", **overrides: Any) -> dict[str, Any]:
    """A valid EVALUATE_NOW triage report; override any keyword to perturb it."""
    kwargs: dict[str, Any] = {
        "candidate_id": candidate_id,
        "surrogate_model_id": "surrogate-v1",
        "predicted_utility": 0.8,
        "predictive_uncertainty": 0.1,
        "ood_score": 0.1,
        "calibration_window_id": "CAL-0001",
    }
    kwargs.update(overrides)
    return triage_at_scale(**kwargs)


def deferred_triage(candidate_id: str = "CAND-9") -> dict[str, Any]:
    """A triage report the surrogate defers rather than accepts for evaluation."""
    return triage(
        candidate_id=candidate_id,
        predicted_utility=0.1,
        predictive_uncertainty=0.9,
        ood_score=0.9,
    )


def qualification_kwargs(**overrides: Any) -> dict[str, Any]:
    """The smallest whole-run manifest ``qualify_evolution_run`` accepts."""
    fanout = clean_fanout()
    kwargs: dict[str, Any] = {
        "qualification_run_id": "QUAL-Y06-0001",
        "expected_counts": expected_counts(),
        "proposed": fanout["proposed"],
        "generated": fanout["generated"],
        "evaluated": fanout["evaluated"],
        "persisted": fanout["persisted"],
        "effect_receipts": fanout["effect_receipts"],
        "mutation_receipts": fanout["mutation_receipts"],
        "budget_envelope": bounded_budget(),
        "measured_cost": 40.0,
        "measured_usage": measured_usage(),
        "triage_reports": [triage("CAND-1")],
        "surrogate_ceiling": 5,
        "authority_claims": [
            {
                "capability_id": "foundry:read",
                "holder_id": "CAND-1",
                "holder_is_search_space": True,
            }
        ],
    }
    kwargs.update(overrides)
    return kwargs
