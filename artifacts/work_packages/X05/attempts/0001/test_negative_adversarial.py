"""negative_and_adversarial_tests — every refusal fires under attack.

Each declared ``FINDING_CODES`` entry is provoked at least once, and the
adversarial cases are the ones this package exists to stop: a provider smuggled
in outside the eligible set, a fallback that quietly rewrites a verdict, a reward
drawn from the gameable proxy, a reward routed at a promotion, a safety failure
paired with a high proxy score, and an external backend reaching for authority.
A refusal that fired under the wrong code would be as much a defect as no refusal
at all, so every case asserts the exact code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.providers.v4_x05 import (
    admit_bandit_reward,
    assert_fallback_neutral,
    reconcile_routed_fanin,
    route_external_backend_neutral,
    route_mutation,
    seal_safe_bandit_state,
)
from epistemic_foundry.providers.v4_x05 import routing as mod
from epistemic_foundry.scheduler.v4_n05 import LANES, LaneEvent
from fixtures import (
    BANDIT_UCB,
    DELAYED_HOLDOUT,
    ELIGIBLE,
    IMMEDIATE_PROXY,
    LAST_UPDATED,
    MANUAL,
    REPLICATION,
    REWARD_NONE,
    THOMPSON,
    UCB,
    VALIDATED_IMPROVEMENT,
    bandit_arm,
    imported_backend_envelope,
    lane_limits,
    neutral_fallback_result,
    reference_result,
    repo_root,
    routing_receipt,
    statistical_correction,
)


# --- input integrity ----------------------------------------------------------


def test_empty_eligible_set_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        route_mutation(
            task_class="mut",
            eligible_model_ids=[],
            selected_model_id="provider-a",
            policy="safe_bandit",
            reward_basis=DELAYED_HOLDOUT,
            estimated_cost=0.1,
            estimated_latency_ms=10,
            exploration_probability=0.1,
        )
    assert caught.value.code == "INPUT_INVALID"


def test_enum_reader_refuses_a_reshaped_vocabulary() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        mod._enum(mod.ROUTING_KIND, "policy", 3)
    assert caught.value.code == "VOCABULARY_DRIFT"


# --- provider neutrality: routing ---------------------------------------------


def test_selecting_a_provider_outside_the_eligible_set_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        routing_receipt(selected_model_id="provider-z")
    assert caught.value.code == "ROUTING_SELECTION_NOT_ELIGIBLE"


def test_unbounded_bandit_policy_is_refused() -> None:
    for policy in (UCB, THOMPSON):
        with pytest.raises(mod.MutationRoutingError) as caught:
            routing_receipt(policy=policy)
        assert caught.value.code == "ROUTING_POLICY_UNSAFE"


def test_learning_policy_on_the_proxy_basis_is_incoherent() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        routing_receipt(reward_basis=IMMEDIATE_PROXY)
    assert caught.value.code == "ROUTING_REWARD_BASIS_INCOHERENT"


def test_non_learning_policy_claiming_a_reward_basis_is_incoherent() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        routing_receipt(
            policy=MANUAL, reward_basis=VALIDATED_IMPROVEMENT, exploration_probability=0
        )
    assert caught.value.code == "ROUTING_REWARD_BASIS_INCOHERENT"


def test_non_learning_policy_claiming_exploration_is_incoherent() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        routing_receipt(
            policy=MANUAL, reward_basis=REWARD_NONE, exploration_probability=0.3
        )
    assert caught.value.code == "ROUTING_EXPLORATION_INCOHERENT"


# --- provider neutrality: fallback --------------------------------------------


def test_fallback_to_an_ineligible_provider_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        assert_fallback_neutral(
            reference_result=reference_result(),
            fallback_result=neutral_fallback_result(),
            eligible_model_ids=list(ELIGIBLE),
            primary_model_id=ELIGIBLE[0],
            fallback_model_id="provider-z",
        )
    assert caught.value.code == "FALLBACK_TARGET_NOT_ELIGIBLE"


def test_fallback_to_the_same_provider_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        assert_fallback_neutral(
            reference_result=reference_result(),
            fallback_result=neutral_fallback_result(),
            eligible_model_ids=list(ELIGIBLE),
            primary_model_id=ELIGIBLE[0],
            fallback_model_id=ELIGIBLE[0],
        )
    assert caught.value.code == "FALLBACK_SOURCE_EQUALS_TARGET"


def test_fallback_that_rewrites_a_verdict_is_refused() -> None:
    """A provider that changes a canonical field is claiming authority over meaning."""
    with pytest.raises(mod.MutationRoutingError) as caught:
        assert_fallback_neutral(
            reference_result=reference_result(verdict="supported"),
            fallback_result=neutral_fallback_result(verdict="refuted"),
            eligible_model_ids=list(ELIGIBLE),
            primary_model_id=ELIGIBLE[0],
            fallback_model_id=ELIGIBLE[1],
        )
    assert caught.value.code == "PROVIDER_SEMANTICS_ALTERED"


# --- safe delayed-reward bandit -----------------------------------------------


def _proxy_basis_receipt() -> dict:
    """A schema-valid routing receipt whose reward basis is the gameable proxy.

    ``route_mutation`` refuses to build one, so the adversary is modelled by
    mutating a valid receipt: the schema still accepts the immediate-proxy basis,
    which is exactly why the bandit gate must catch it downstream.
    """
    receipt = dict(routing_receipt())
    receipt["reward_basis"] = IMMEDIATE_PROXY
    return receipt


def test_reward_on_the_immediate_proxy_basis_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        admit_bandit_reward(
            routing_receipt=_proxy_basis_receipt(),
            arm_id=ELIGIBLE[0],
            proxy_score=0.99,
            validated_utility=0.9,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(),
        )
    assert caught.value.code == "BANDIT_REWARD_PROXY_BASIS"


def test_reward_with_no_basis_is_refused() -> None:
    receipt = routing_receipt(
        policy="fixed", reward_basis=REWARD_NONE, exploration_probability=0
    )
    with pytest.raises(mod.MutationRoutingError) as caught:
        admit_bandit_reward(
            routing_receipt=receipt,
            arm_id=ELIGIBLE[0],
            proxy_score=0.9,
            validated_utility=0.7,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(),
        )
    assert caught.value.code == "BANDIT_REWARD_BASIS_ABSENT"


def test_reward_with_no_statistical_correction_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        admit_bandit_reward(
            routing_receipt=routing_receipt(reward_basis=REPLICATION),
            arm_id=ELIGIBLE[0],
            proxy_score=0.9,
            validated_utility=0.7,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(correction_applied=False),
        )
    assert caught.value.code == "BANDIT_STATISTICAL_CORRECTION_ABSENT"


def test_reward_routed_at_a_promotion_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        admit_bandit_reward(
            routing_receipt=routing_receipt(reward_basis=REPLICATION),
            arm_id=ELIGIBLE[0],
            proxy_score=0.9,
            validated_utility=0.7,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(),
            drives_promotion=True,
        )
    assert caught.value.code == "BANDIT_REWARD_DRIVES_PROMOTION"


def test_reward_with_no_validated_utility_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        admit_bandit_reward(
            routing_receipt=routing_receipt(reward_basis=DELAYED_HOLDOUT),
            arm_id=ELIGIBLE[0],
            proxy_score=0.95,
            validated_utility=None,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(),
        )
    assert caught.value.code == "BANDIT_REWARD_UNVALIDATED"


def test_admit_reward_refuses_a_malformed_routing_receipt() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        admit_bandit_reward(
            routing_receipt={"receipt_id": "X"},
            arm_id=ELIGIBLE[0],
            proxy_score=0.9,
            validated_utility=0.7,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(),
        )
    assert caught.value.code == "ROUTING_CONTRACT_VIOLATED"


def test_unsafe_bandit_policy_is_refused_at_seal() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        seal_safe_bandit_state(
            evolution_run_id="ER-1",
            arms=[bandit_arm()],
            exploration_budget=1.0,
            last_updated=LAST_UPDATED,
            policy=BANDIT_UCB,
        )
    assert caught.value.code == "BANDIT_POLICY_UNSAFE"


def test_arm_with_safety_violation_beside_positive_reward_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        seal_safe_bandit_state(
            evolution_run_id="ER-1",
            arms=[bandit_arm(safety_violations=1, delayed_reward_mean=0.6)],
            exploration_budget=1.0,
            last_updated=LAST_UPDATED,
        )
    assert caught.value.code == "BANDIT_STATE_REFUSED"


# --- exact fan-in and backend isolation ---------------------------------------


def test_incomplete_provider_fanin_is_refused() -> None:
    """A candidate proposed but never concluded is a partial fan-out."""
    events = [
        LaneEvent(LANES[0], "enqueue", "C-1"),
        LaneEvent(LANES[0], "start", "C-1"),
    ]
    with pytest.raises(mod.MutationRoutingError) as caught:
        reconcile_routed_fanin(
            repo_root(),
            proposed=["C-1"],
            events=events,
            lane_limits=lane_limits(),
            schedule_id="SCH-1",
        )
    assert caught.value.code == "ROUTING_FANIN_UNACCOUNTED"


def test_external_backend_reaching_for_authority_is_refused() -> None:
    with pytest.raises(mod.MutationRoutingError) as caught:
        route_external_backend_neutral(
            imported=imported_backend_envelope(),
            bindings={"bandit_state": "promotion_decision"},
        )
    assert caught.value.code == "BACKEND_PROVIDER_AUTHORITY_LEAK"
