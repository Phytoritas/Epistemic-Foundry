"""unit_and_contract_tests — the happy paths hold their contracts.

Every surface produces a receipt or a canonical artifact that satisfies its
schema and re-derives its own identifier and hash, and every receipt is a pure
function of its inputs.  These tests exercise the compositions the way a real
run would: route a mutation, fail a provider over neutrally, admit a validated
reward, seal a safe bandit state, reconcile the routed fan-out, and keep an
external backend advisory.
"""

from __future__ import annotations

from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evaluation import bandits
from epistemic_foundry.providers.v4_x05 import (
    admit_bandit_reward,
    assert_fallback_neutral,
    reconcile_routed_fanin,
    route_external_backend_neutral,
    seal_safe_bandit_state,
)
from fixtures import (
    DELAYED_HOLDOUT,
    ELIGIBLE,
    FIXED,
    LAST_UPDATED,
    MANUAL,
    REPLICATION,
    REWARD_NONE,
    SAFE_BANDIT,
    SAFE_UCB,
    VALIDATED_IMPROVEMENT,
    bandit_arm,
    imported_backend_envelope,
    lane_limits,
    neutral_fallback_result,
    reference_result,
    repo_root,
    routing_receipt,
    schedule_events,
    statistical_correction,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_route_mutation_produces_a_valid_routing_receipt() -> None:
    receipt = routing_receipt()
    validate_artifact("model-routing-receipt", dict(receipt))
    assert receipt["selected_model_id"] in receipt["eligible_model_ids"]
    assert receipt["policy"] == SAFE_BANDIT
    assert receipt["reward_basis"] == DELAYED_HOLDOUT
    assert receipt["receipt_id"].startswith("XMR-")
    assert _rederives(receipt)


def test_routing_receipt_is_a_pure_function_of_its_inputs() -> None:
    first = routing_receipt()
    second = routing_receipt()
    assert first == second


def test_route_mutation_admits_every_validated_reward_basis() -> None:
    for basis in (VALIDATED_IMPROVEMENT, DELAYED_HOLDOUT, REPLICATION):
        receipt = routing_receipt(reward_basis=basis)
        assert receipt["reward_basis"] == basis


def test_non_learning_policies_carry_no_reward_and_no_exploration() -> None:
    for policy in (FIXED, MANUAL):
        receipt = routing_receipt(
            policy=policy, reward_basis=REWARD_NONE, exploration_probability=0
        )
        assert receipt["policy"] == policy
        assert receipt["reward_basis"] == REWARD_NONE
        assert receipt["exploration_probability"] == 0


def test_fallback_is_neutral_when_canonical_fields_are_preserved() -> None:
    receipt = assert_fallback_neutral(
        reference_result=reference_result(),
        fallback_result=neutral_fallback_result(),
        eligible_model_ids=list(ELIGIBLE),
        primary_model_id=ELIGIBLE[0],
        fallback_model_id=ELIGIBLE[1],
    )
    assert receipt["semantics_preserved"] is True
    # Provider-local differences are reported, never refused.
    assert "latency_ms" in receipt["provider_local_differences"]
    assert receipt["receipt_id"].startswith("XFN-")
    assert _rederives(receipt)


def test_admit_bandit_reward_derives_reward_from_validated_utility() -> None:
    receipt = routing_receipt(reward_basis=REPLICATION)
    admission = admit_bandit_reward(
        routing_receipt=receipt,
        arm_id=ELIGIBLE[0],
        proxy_score=0.95,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )
    assert admission["reward"] == 0.7
    assert admission["drives_promotion"] is False
    assert admission["statistical_correction_id"] == "ADJ-0001"
    assert admission["receipt_id"].startswith("XBR-")
    assert _rederives(admission)


def test_unreplicated_validated_utility_is_discounted_not_taken_whole() -> None:
    admission = admit_bandit_reward(
        routing_receipt=routing_receipt(reward_basis=DELAYED_HOLDOUT),
        arm_id=ELIGIBLE[0],
        proxy_score=0.95,
        validated_utility=0.8,
        safety_passed=True,
        replication_confirmed=False,
        statistical_correction=statistical_correction(),
    )
    # bandits.validated_reward halves an unreplicated utility.
    assert admission["reward"] == 0.4


def test_safety_failure_zeroes_the_reward() -> None:
    admission = admit_bandit_reward(
        routing_receipt=routing_receipt(reward_basis=REPLICATION),
        arm_id=ELIGIBLE[0],
        proxy_score=0.99,
        validated_utility=0.9,
        safety_passed=False,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )
    assert admission["reward"] == 0.0


def test_seal_safe_bandit_state_runs_under_a_safe_policy() -> None:
    state = seal_safe_bandit_state(
        evolution_run_id="ER-0001",
        arms=[bandit_arm()],
        exploration_budget=1.0,
        last_updated=LAST_UPDATED,
    )
    validate_artifact("operator-bandit-state", dict(state))
    assert state["policy"] == SAFE_UCB
    assert bandits.policy_bounds_safety(state) is True


def test_reconcile_routed_fanin_seals_a_verdict_for_a_complete_schedule() -> None:
    verdict = reconcile_routed_fanin(
        repo_root(),
        proposed=["C-1"],
        events=schedule_events("C-1"),
        lane_limits=lane_limits(),
        schedule_id="SCH-0001",
    )
    assert verdict["valid"] is True
    assert verdict["reconciled"] is True
    assert verdict["schedule_id"] == "SCH-0001"


def test_external_backend_stays_advisory_with_no_authority_binding() -> None:
    gate = route_external_backend_neutral(
        imported=imported_backend_envelope(),
        bindings={},
    )
    assert gate["authoritative"] is False


def test_registry_documents_carry_titles() -> None:
    registry = default_registry()
    assert registry.document("model-routing-receipt")["title"]
    assert registry.document("operator-bandit-state")["title"]
