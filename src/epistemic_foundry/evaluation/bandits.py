"""Operator and model bandits with delayed reward routing (EF4-I54).

Contract source: `schemas/operator-bandit-state.schema.json`.

"Bandits learn from validated holdout/replication utility and safety, not only
immediate proxy score." A bandit rewarded on a cheap proxy will converge on
whatever maximizes the proxy, which is the reward-hacking failure in miniature:
the search gets very good at scoring well and no better at being right.

So `record_arm_outcome` refuses a reward that carries no validated utility, and a
safety failure zeroes the reward outright rather than being averaged against a
high proxy score. Averaging would let a dangerous-but-high-scoring operator keep
its pull probability.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Policies that bound exploration explicitly. `fixed` does not learn at all and
#: is included so a run can opt out of adaptation without faking a bandit.
SAFE_POLICIES: frozenset[str] = frozenset({"safe_ucb"})

#: The schema separates `immediate_reward_mean` from `delayed_reward_mean`, which
#: is precisely the distinction this invariant turns on: the immediate figure is
#: the proxy, the delayed figure is validated holdout or replication utility. An
#: arm may track both, but the delayed one is what learning must be driven by.
PROXY_REWARD_FIELD = "immediate_reward_mean"
VALIDATED_REWARD_FIELD = "delayed_reward_mean"

#: Arm fields the schema requires. Named so a caller filling only the proxy is
#: caught with a message about the invariant rather than a raw schema error.
REQUIRED_ARM_FIELDS: tuple[str, ...] = (
    "arm_id",
    "pulls",
    PROXY_REWARD_FIELD,
    VALIDATED_REWARD_FIELD,
    "mean_cost",
    "failures",
    "safety_violations",
)


class BanditRewardRefused(ValueError):
    """A reward would train the bandit on an unvalidated signal."""


def validated_reward(
    *,
    proxy_score: float,
    validated_utility: float | None,
    safety_passed: bool,
    replication_confirmed: bool,
) -> float:
    """Reward derived from validated outcomes rather than the proxy.

    A safety failure returns 0.0 regardless of the other inputs: averaging safety
    into a scalar would let a dangerous operator retain its pull probability
    because it also scored well. Unreplicated validated utility is discounted
    rather than taken at face value, since selection pressure inflates it.
    """
    if not safety_passed:
        return 0.0
    if validated_utility is None:
        raise BanditRewardRefused(
            "no validated utility supplied; training a bandit on the proxy score alone converges "
            "on whatever maximizes the proxy rather than on being right"
        )
    return float(validated_utility) if replication_confirmed else float(validated_utility) * 0.5


def build_bandit_state(
    *,
    evolution_run_id: str,
    policy: str,
    arms: Sequence[Mapping[str, Any]],
    exploration_budget: float,
    state_id: str | None = None,
    last_updated: str | None = None,
) -> dict[str, Any]:
    """Seal a bandit state.

    Every arm must carry a validated-reward field. An arm tracking only the proxy
    is the state this invariant forbids, and detecting it at seal time beats
    discovering it after the search has converged.
    """
    if not arms:
        raise BanditRewardRefused("a bandit state must define at least one arm")
    proxy_only = [
        str(arm.get("arm_id")) for arm in arms if VALIDATED_REWARD_FIELD not in arm
    ]
    if proxy_only:
        raise BanditRewardRefused(
            f"arm(s) {sorted(proxy_only)} track no {VALIDATED_REWARD_FIELD}; a proxy-only arm "
            "converges on the proxy rather than on validated utility"
        )
    unsafe = [
        str(arm.get("arm_id"))
        for arm in arms
        if int(arm.get("safety_violations", 0)) > 0
        and float(arm.get(VALIDATED_REWARD_FIELD, 0.0)) > 0.0
    ]
    if unsafe:
        raise BanditRewardRefused(
            f"arm(s) {sorted(unsafe)} carry safety violations alongside a positive validated "
            "reward; a safety failure zeroes the reward rather than being averaged against it"
        )
    if exploration_budget < 0:
        raise BanditRewardRefused("exploration_budget cannot be negative")

    state: dict[str, Any] = {
        "state_id": state_id or new_id("OBS"),
        "evolution_run_id": evolution_run_id,
        "policy": policy,
        "arms": [dict(arm) for arm in arms],
        "exploration_budget": float(exploration_budget),
        "last_updated": last_updated or utc_now_iso(),
    }
    state["state_hash"] = hash_excluding(state, "state_hash")
    validate_artifact("operator-bandit-state", state)
    return state


def policy_bounds_safety(state: Mapping[str, Any]) -> bool:
    """Whether the policy itself constrains unsafe exploration."""
    return str(state.get("policy")) in SAFE_POLICIES
