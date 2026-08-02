"""Shared fixtures for the X05 cross-provider routing and safe-bandit suite.

The canonical tokens are restated here as test constants and pinned against the
schemas by ``test_schema_and_type``: if a ladder reorders, that suite fails at
the assertion rather than letting a test silently exercise the wrong token.  The
builders return the smallest valid inputs each surface accepts, so a negative
test can perturb exactly one field and attribute the refusal to it.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.contracts import repo_root as _repo_root
from epistemic_foundry.evolution_chamber.reconciliation import STAGES
from epistemic_foundry.providers.v4_x05 import route_mutation
from epistemic_foundry.scheduler.v4_n05 import LANES, LaneEvent

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

# --- bandit policy ladder (operator-bandit-state.policy) -----------------------
BANDIT_UCB = "ucb"
BANDIT_THOMPSON = "thompson"
SAFE_UCB = "safe_ucb"
BANDIT_FIXED = "fixed"

ELIGIBLE = ("provider-a", "provider-b", "provider-c")
LAST_UPDATED = "2026-08-01T00:00:00+00:00"


def repo_root() -> Any:
    return _repo_root()


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
    """A fallback result that preserves every canonical field of the reference."""
    result = reference_result(
        model="provider-b",
        provider="provider-b",
        latency_ms=87,
    )
    result.update(overrides)
    return result


def schedule_events(candidate_id: str = "C-1") -> list[LaneEvent]:
    events: list[LaneEvent] = []
    for lane in LANES:
        events.append(LaneEvent(lane, "enqueue", candidate_id))
        events.append(LaneEvent(lane, "start", candidate_id))
        events.append(LaneEvent(lane, "conclude", candidate_id))
    return events


def lane_limits(concurrency: int = 2) -> dict[str, dict[str, Any]]:
    return {lane: {"concurrency": concurrency} for lane in LANES}


def imported_backend_envelope(candidate_id: str = "C-1") -> dict[str, Any]:
    """A minimal, reconciling imported ShinkaEvolve run via the sealed T05 adapter."""
    from epistemic_foundry.adapters.v4_t05 import import_shinka_run

    candidate_identities = {stage: [candidate_id] for stage in STAGES}
    return import_shinka_run(
        import_id="IMP-0001",
        source_run_id="SRC-0001",
        target_session_id="SESS-0001",
        source_version="1.0.0",
        target_version="1.0.0",
        source_snapshot_hash="sha256:" + "0" * 64,
        migration_plan_id="MIG-0001",
        unconverted_fields=[],
        imported_at=LAST_UPDATED,
        candidate_identities=candidate_identities,
    )
