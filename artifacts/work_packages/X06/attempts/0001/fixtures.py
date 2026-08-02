"""Shared fixtures for the X06 provider-diversity integration-gate suite.

The canonical tokens are restated here as test constants and pinned against the
schemas by ``test_schema_and_type``: if a ladder reorders, that suite fails at
the assertion rather than letting a test silently exercise the wrong token.  The
builders return the smallest valid inputs each surface accepts, so a negative
test can perturb exactly one field and attribute the refusal to it, and the
forging helpers re-derive a sealed sub-receipt's own identity so a tamper test
can prove the gate refuses a laundered decision rather than a malformed one.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.evaluation import bandits
from epistemic_foundry.providers.v4_x05 import (
    assert_fallback_neutral,
    route_mutation,
)

# --- routing policy ladder (model-routing-receipt.policy) ---------------------
FIXED = "fixed"
UCB = "ucb"
THOMPSON = "thompson"
SAFE_BANDIT = "safe_bandit"
MANUAL = "manual"

# --- reward-basis ladder (model-routing-receipt.reward_basis) -----------------
IMMEDIATE_PROXY = "immediate_proxy"
VALIDATED_IMPROVEMENT = "validated_improvement"
DELAYED_HOLDOUT = "delayed_holdout"
REPLICATION = "replication"
REWARD_NONE = "none"

# --- bandit policy ladder (operator-bandit-state.policy) ----------------------
BANDIT_UCB = "ucb"
SAFE_UCB = "safe_ucb"

ELIGIBLE = ("provider-a", "provider-b", "provider-c")
LAST_UPDATED = "2026-08-01T00:00:00+00:00"


def routing_receipt(**overrides: Any) -> dict[str, Any]:
    """A valid, safe-bandit routing receipt; override any keyword to perturb it."""
    kwargs: dict[str, Any] = {
        "task_class": "hypothesis_mutation",
        "eligible_model_ids": list(ELIGIBLE),
        "selected_model_id": ELIGIBLE[0],
        "policy": SAFE_BANDIT,
        "reward_basis": DELAYED_HOLDOUT,
        "estimated_cost": 0.25,
        "estimated_latency_ms": 1200,
        "exploration_probability": 0.2,
        "safety_constraints": ["no-network"],
    }
    kwargs.update(overrides)
    return route_mutation(**kwargs)


def diverse_receipts() -> list[dict[str, Any]]:
    """Two routing receipts spanning the eligible provider set."""
    return [
        routing_receipt(selected_model_id=ELIGIBLE[0], reward_basis=DELAYED_HOLDOUT),
        routing_receipt(
            selected_model_id=ELIGIBLE[1],
            reward_basis=REPLICATION,
            estimated_cost=0.4,
            estimated_latency_ms=900,
            exploration_probability=0.1,
        ),
    ]


def single_provider_receipt() -> dict[str, Any]:
    """A routing receipt whose eligible set offers no alternative provider."""
    return routing_receipt(
        eligible_model_ids=[ELIGIBLE[0]], selected_model_id=ELIGIBLE[0]
    )


def statistical_correction(**overrides: Any) -> dict[str, Any]:
    correction: dict[str, Any] = {
        "adjustment_id": "ADJ-0001",
        "correction_applied": True,
    }
    correction.update(overrides)
    return correction


def bandit_arm(**overrides: Any) -> dict[str, Any]:
    arm: dict[str, Any] = {
        "arm_id": ELIGIBLE[0],
        "pulls": 4,
        "immediate_reward_mean": 0.8,
        "delayed_reward_mean": 0.6,
        "mean_cost": 0.25,
        "failures": 0,
        "safety_violations": 0,
    }
    arm.update(overrides)
    return arm


def safe_bandit_state(**overrides: Any) -> dict[str, Any]:
    """A schema-valid bandit state under the safe policy."""
    kwargs: dict[str, Any] = {
        "evolution_run_id": "ER-0001",
        "policy": SAFE_UCB,
        "arms": [bandit_arm()],
        "exploration_budget": 1.0,
        "state_id": "OBS-0001",
        "last_updated": LAST_UPDATED,
    }
    kwargs.update(overrides)
    return bandits.build_bandit_state(**kwargs)


def unsafe_bandit_state() -> dict[str, Any]:
    """A schema-valid, correctly-hashed bandit state under an unsafe policy."""
    return bandits.build_bandit_state(
        evolution_run_id="ER-0001",
        policy=BANDIT_UCB,
        arms=[bandit_arm()],
        exploration_budget=1.0,
        state_id="OBS-0002",
        last_updated=LAST_UPDATED,
    )


def reference_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "PASS",
        "verdict": "supported",
        "content_hash": "sha256:" + "a" * 64,
        "model": "provider-a",
        "latency_ms": 10,
        "provider": "provider-a",
    }
    result.update(overrides)
    return result


def neutral_fallback_result(**overrides: Any) -> dict[str, Any]:
    result = reference_result(model="provider-b", provider="provider-b", latency_ms=87)
    result.update(overrides)
    return result


def fallback_receipt(**overrides: Any) -> dict[str, Any]:
    """A sealed, neutral fallback receipt from the X05 surface."""
    kwargs: dict[str, Any] = {
        "reference_result": reference_result(),
        "fallback_result": neutral_fallback_result(),
        "eligible_model_ids": list(ELIGIBLE),
        "primary_model_id": ELIGIBLE[0],
        "fallback_model_id": ELIGIBLE[1],
    }
    kwargs.update(overrides)
    return assert_fallback_neutral(**kwargs)


def reseal(
    record: dict[str, Any], prefix: str, id_field: str, hash_field: str
) -> dict[str, Any]:
    """Re-derive a record's identity under a prefix, forging a sealed sub-receipt.

    The scheme is the sealed X05/X06 surface's own, so a forged record passes the
    tamper check and is refused (or admitted) on its *content* — which is exactly
    what a laundering test needs.
    """
    body = {
        key: value for key, value in record.items() if key not in {id_field, hash_field}
    }
    record[id_field] = prefix + sha256_of_payload(body)[len("sha256:") :]
    record[hash_field] = hash_excluding(record, hash_field)
    return record
