"""provenance_and_receipt_audit — every effect resolves to an immutable receipt.

The invariants this suite pins are the ones the manifest's exit criteria and the
X05 integrity note turn on: every decision is a re-derivable, content-addressed
receipt; two runs over equal inputs produce byte-equal receipts; inputs are never
mutated; and a bandit reward is recorded as search signal that never carries
promotion authority.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.providers.v4_x05 import (
    admit_bandit_reward,
    assert_fallback_neutral,
    reconcile_routed_fanin,
    route_mutation,
    seal_safe_bandit_state,
)
from fixtures import (
    DELAYED_HOLDOUT,
    ELIGIBLE,
    LAST_UPDATED,
    REPLICATION,
    bandit_arm,
    lane_limits,
    neutral_fallback_result,
    reference_result,
    repo_root,
    routing_receipt,
    schedule_events,
    statistical_correction,
)


def test_routing_receipt_rederives_its_own_identity_and_hash() -> None:
    receipt = routing_receipt()
    body = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_id", "receipt_hash"}
    }
    expected_id = "XMR-" + sha256_of_payload(body)[len("sha256:") :]
    assert receipt["receipt_id"] == expected_id
    assert receipt["receipt_hash"] == hash_excluding(dict(receipt), "receipt_hash")


def test_receipts_are_byte_equal_across_equal_runs() -> None:
    assert routing_receipt() == routing_receipt()

    reward_kwargs = dict(
        routing_receipt=routing_receipt(reward_basis=REPLICATION),
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )
    assert admit_bandit_reward(**reward_kwargs) == admit_bandit_reward(**reward_kwargs)


def test_fallback_receipt_is_content_addressed() -> None:
    receipt = assert_fallback_neutral(
        reference_result=reference_result(),
        fallback_result=neutral_fallback_result(),
        eligible_model_ids=list(ELIGIBLE),
        primary_model_id=ELIGIBLE[0],
        fallback_model_id=ELIGIBLE[1],
    )
    assert receipt["receipt_id"].startswith("XFN-")
    assert receipt["receipt_hash"] == hash_excluding(dict(receipt), "receipt_hash")


def test_route_mutation_does_not_mutate_its_inputs() -> None:
    eligible = list(ELIGIBLE)
    constraints = ["no-network"]
    before_eligible = copy.deepcopy(eligible)
    before_constraints = copy.deepcopy(constraints)
    route_mutation(
        task_class="mut",
        eligible_model_ids=eligible,
        selected_model_id=ELIGIBLE[0],
        policy="safe_bandit",
        reward_basis=DELAYED_HOLDOUT,
        estimated_cost=0.2,
        estimated_latency_ms=100,
        exploration_probability=0.1,
        safety_constraints=constraints,
    )
    assert eligible == before_eligible
    assert constraints == before_constraints


def test_admit_reward_does_not_mutate_the_routing_receipt_or_correction() -> None:
    receipt = routing_receipt(reward_basis=REPLICATION)
    correction = statistical_correction()
    before_receipt = copy.deepcopy(receipt)
    before_correction = copy.deepcopy(correction)
    admit_bandit_reward(
        routing_receipt=receipt,
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=correction,
    )
    assert receipt == before_receipt
    assert correction == before_correction


def test_bandit_reward_is_recorded_as_search_signal_never_promotion() -> None:
    admission = admit_bandit_reward(
        routing_receipt=routing_receipt(reward_basis=REPLICATION),
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )
    # The admission carries no promotion authority: it is a pull-probability
    # input, and its own record says so.
    assert admission["drives_promotion"] is False
    assert "promotion" not in {
        key.lower() for key in admission if key != "drives_promotion"
    }


def test_bandit_state_rederives_its_own_hash() -> None:
    state = seal_safe_bandit_state(
        evolution_run_id="ER-1",
        arms=[bandit_arm()],
        exploration_budget=1.0,
        last_updated=LAST_UPDATED,
    )
    assert state["state_hash"] == hash_excluding(dict(state), "state_hash")


def test_fanin_verdict_rederives_and_is_stable() -> None:
    kwargs = dict(
        proposed=["C-1"],
        events=schedule_events("C-1"),
        lane_limits=lane_limits(),
        schedule_id="SCH-1",
    )
    first = reconcile_routed_fanin(repo_root(), **kwargs)
    second = reconcile_routed_fanin(repo_root(), **kwargs)
    assert first == second
    assert first["verdict_hash"] == hash_excluding(dict(first), "verdict_hash")
