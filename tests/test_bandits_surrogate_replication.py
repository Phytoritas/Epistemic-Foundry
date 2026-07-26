"""Bandits learn from validated outcomes; surrogates order but never skip."""

from __future__ import annotations

import inspect

import pytest

from epistemic_foundry.evaluation.bandits import (
    BanditRewardRefused,
    build_bandit_state,
    policy_bounds_safety,
    validated_reward,
)
from epistemic_foundry.evaluation.surrogate import (
    SurrogateOverreach,
    build_surrogate_triage,
    defers_only,
    require_direct_stage_intact,
)
from epistemic_foundry.validation_bay.replication import (
    ReplicationPlanRefused,
    build_replication_plan,
    promotion_ceiling_after_search,
    replication_qualifies,
)


# -- EF4-I53 bandits learn from validated utility ------------------------


def test_i53_safety_failure_zeroes_the_reward() -> None:
    """Averaging safety in would let a dangerous high scorer keep its pull."""
    reward = validated_reward(
        proxy_score=0.99, validated_utility=0.9, safety_passed=False, replication_confirmed=True
    )
    assert reward == 0.0


def test_i53_proxy_only_reward_is_refused() -> None:
    with pytest.raises(BanditRewardRefused) as excinfo:
        validated_reward(
            proxy_score=0.95, validated_utility=None, safety_passed=True, replication_confirmed=False
        )
    assert "maximizes the proxy" in str(excinfo.value)


def test_i53_unreplicated_utility_is_discounted() -> None:
    """Selection pressure inflates an unreplicated result."""
    replicated = validated_reward(
        proxy_score=0.9, validated_utility=0.8, safety_passed=True, replication_confirmed=True
    )
    unreplicated = validated_reward(
        proxy_score=0.9, validated_utility=0.8, safety_passed=True, replication_confirmed=False
    )
    assert replicated == pytest.approx(0.8)
    assert unreplicated < replicated


def test_i53_high_proxy_cannot_raise_a_low_validated_reward() -> None:
    low = validated_reward(
        proxy_score=1.0, validated_utility=0.1, safety_passed=True, replication_confirmed=True
    )
    assert low == pytest.approx(0.1)


def _arm(**overrides) -> dict:
    arm = {
        "arm_id": "OP-tighten",
        "pulls": 12,
        "immediate_reward_mean": 0.71,
        "delayed_reward_mean": 0.42,
        "mean_cost": 3.5,
        "failures": 1,
        "safety_violations": 0,
    }
    arm.update(overrides)
    return arm


def test_i53_proxy_only_arm_is_refused_at_seal_time() -> None:
    """Detecting this at seal beats discovering it after convergence."""
    with pytest.raises(BanditRewardRefused) as excinfo:
        build_bandit_state(
            evolution_run_id="ERS-1",
            policy="safe_ucb",
            arms=[
                _arm(),
                {
                    "arm_id": "OP-proxy",
                    "pulls": 5,
                    "immediate_reward_mean": 0.9,
                    "mean_cost": 1.0,
                    "failures": 0,
                    "safety_violations": 0,
                },
            ],
            exploration_budget=0.2,
        )
    assert "converges on the proxy" in str(excinfo.value)


def test_i53_safety_violating_arm_cannot_keep_a_positive_reward() -> None:
    """Averaging safety against reward would preserve the arm's pull probability."""
    with pytest.raises(BanditRewardRefused) as excinfo:
        build_bandit_state(
            evolution_run_id="ERS-1",
            policy="safe_ucb",
            arms=[_arm(safety_violations=2, delayed_reward_mean=0.8)],
            exploration_budget=0.2,
        )
    assert "zeroes the reward" in str(excinfo.value)


def test_i53_validated_arms_seal() -> None:
    state = build_bandit_state(
        evolution_run_id="ERS-1",
        policy="safe_ucb",
        arms=[_arm()],
        exploration_budget=0.2,
    )
    assert policy_bounds_safety(state) is True
    assert policy_bounds_safety({"policy": "ucb"}) is False


def test_i53_empty_arm_set_is_refused() -> None:
    with pytest.raises(BanditRewardRefused):
        build_bandit_state(
            evolution_run_id="ERS-1", policy="ucb", arms=[], exploration_budget=0.1
        )


# -- EF4-I56 surrogate may order, never skip -----------------------------


def _triage(**overrides) -> dict:
    kwargs = dict(
        candidate_id="CAND-1",
        surrogate_model_id="SURR-1",
        predicted_utility=0.8,
        predictive_uncertainty=0.1,
        ood_score=0.2,
        calibration_window_id="CW-1",
    )
    kwargs.update(overrides)
    return build_surrogate_triage(**kwargs)


def test_i56_direct_evaluation_is_always_required() -> None:
    """A caller able to set this false could skip the hidden stage."""
    params = inspect.signature(build_surrogate_triage).parameters
    assert "direct_evaluation_required" not in params
    assert "triage_decision" not in params
    assert _triage()["direct_evaluation_required"] is True


def test_i56_confident_high_utility_evaluates_now() -> None:
    assert _triage()["triage_decision"] == "EVALUATE_NOW"


def test_i56_low_utility_defers_rather_than_rejecting() -> None:
    """Deferring reorders work; rejecting would remove it."""
    report = _triage(predicted_utility=0.2)
    assert report["triage_decision"] == "DEFER"
    assert defers_only(report) is True


def test_i56_out_of_distribution_candidate_is_sampled_for_calibration() -> None:
    """An uninformative prediction must not order the queue."""
    assert _triage(ood_score=0.9)["triage_decision"] == "SAMPLE_FOR_CALIBRATION"


def test_i56_high_uncertainty_is_sampled_for_calibration() -> None:
    assert _triage(predictive_uncertainty=0.8)["triage_decision"] == "SAMPLE_FOR_CALIBRATION"


def test_i56_only_a_hard_gate_can_reject() -> None:
    report = _triage(hard_gate_failed=True)
    assert report["triage_decision"] == "REJECT_ONLY_ON_HARD_GATE"
    assert report["direct_evaluation_required"] is True


@pytest.mark.parametrize("stage", ["holdout", "replication", "evidence"])
def test_i56_surrogate_cannot_stand_in_for_a_required_stage(stage: str) -> None:
    with pytest.raises(SurrogateOverreach) as excinfo:
        require_direct_stage_intact(_triage(), stage_class=stage)
    assert "cannot stand in for" in str(excinfo.value)


def test_i56_surrogate_may_inform_a_cheap_stage() -> None:
    require_direct_stage_intact(_triage(), stage_class="static")


# -- EF4-I57 preregistered independent replication -----------------------


def _plan(**overrides) -> dict:
    kwargs = dict(
        candidate_id="CAND-1",
        replication_class="independent_team",
        executor_independence="independent_team",
        environment_ids=["ENV-1"],
        data_ids=["DS-1"],
        seeds=[7, 11],
        preregistered_metrics=["delayed_recall_smd"],
        success_rule="smd >= 0.2 with lower CI bound above 0",
        failure_rule="lower CI bound at or below 0",
    )
    kwargs.update(overrides)
    return build_replication_plan(**kwargs)


def test_i57_preregistered_independent_plan_qualifies() -> None:
    assert replication_qualifies(_plan()) is True


def test_i57_plan_without_preregistered_metrics_is_refused() -> None:
    """Choosing the metric afterwards re-runs the search on the replication."""
    with pytest.raises(ReplicationPlanRefused) as excinfo:
        _plan(preregistered_metrics=[])
    assert "re-runs the adaptive search" in str(excinfo.value)


def test_i57_plan_without_a_failure_rule_is_refused() -> None:
    """Without a stated way to fail, any outcome can be read as support."""
    with pytest.raises(ReplicationPlanRefused) as excinfo:
        _plan(failure_rule="   ")
    assert "read as support" in str(excinfo.value)


def test_i57_unpinned_seeds_are_refused() -> None:
    with pytest.raises(ReplicationPlanRefused) as excinfo:
        _plan(seeds=[])
    assert "unreproducible" in str(excinfo.value)


def test_i57_self_replication_does_not_qualify() -> None:
    """A same-team repeat shares assumptions, tooling and blind spots."""
    assert replication_qualifies(_plan(executor_independence="same_team")) is False


def test_i57_multi_seed_alone_does_not_qualify() -> None:
    """A stable result can be wrong for the same reason every time."""
    assert replication_qualifies(_plan(replication_class="multi_seed")) is False


def test_i57_unknown_replication_class_is_refused() -> None:
    with pytest.raises(ReplicationPlanRefused) as excinfo:
        _plan(replication_class="direct")
    assert "known classes" in str(excinfo.value)


def test_i57_adaptive_search_without_replication_caps_promotion() -> None:
    ceiling = promotion_ceiling_after_search(adaptive_search_used=True, replication_plan=None)
    assert ceiling == "EMPIRICALLY_TESTED"


def test_i57_adaptive_search_with_qualifying_replication_lifts_the_cap() -> None:
    ceiling = promotion_ceiling_after_search(adaptive_search_used=True, replication_plan=_plan())
    assert ceiling == "REPLICATED"


def test_i57_non_independent_replication_still_caps_promotion() -> None:
    ceiling = promotion_ceiling_after_search(
        adaptive_search_used=True, replication_plan=_plan(executor_independence="same_team")
    )
    assert ceiling == "EMPIRICALLY_TESTED"


def test_i57_no_adaptive_search_is_unconstrained_by_this_rule() -> None:
    ceiling = promotion_ceiling_after_search(adaptive_search_used=False, replication_plan=None)
    assert ceiling == "REPLICATED"
