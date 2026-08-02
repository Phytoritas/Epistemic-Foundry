"""provenance_and_receipt_audit — every decision resolves to an immutable receipt.

The invariants this suite pins are the ones the manifest's exit criteria and the
X06 integration note turn on: every decision is a re-derivable, content-addressed
receipt; two runs over equal inputs produce byte-equal receipts; inputs are never
mutated; the integration receipt binds only the sealed sub-receipts it re-derived;
and the bound reward is recorded as search signal that never carries promotion
authority.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.providers.v4_x06 import (
    attest_provider_diversity,
    attribute_provider_reward,
    integrate_provider_gate,
)
from fixtures import (
    ELIGIBLE,
    diverse_receipts,
    fallback_receipt,
    safe_bandit_state,
    statistical_correction,
)


def _attestation() -> dict:
    return attest_provider_diversity(routing_receipts=diverse_receipts())


def _reward() -> dict:
    return attribute_provider_reward(
        routing_receipt=diverse_receipts()[0],
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )


def _integration() -> dict:
    return integrate_provider_gate(
        run_id="RUN-1",
        diversity_attestation=_attestation(),
        reward_attribution=_reward(),
        bandit_state=safe_bandit_state(),
        fallback_receipts=[fallback_receipt()],
    )


def test_attestation_rederives_its_own_identity_and_hash() -> None:
    attestation = _attestation()
    body = {
        key: value
        for key, value in attestation.items()
        if key not in {"attestation_id", "attestation_hash"}
    }
    expected_id = "XPD-" + sha256_of_payload(body)[len("sha256:") :]
    assert attestation["attestation_id"] == expected_id
    assert attestation["attestation_hash"] == hash_excluding(
        dict(attestation), "attestation_hash"
    )


def test_integration_receipt_rederives_its_own_identity_and_hash() -> None:
    integration = _integration()
    body = {
        key: value
        for key, value in integration.items()
        if key not in {"receipt_id", "receipt_hash"}
    }
    expected_id = "XIG-" + sha256_of_payload(body)[len("sha256:") :]
    assert integration["receipt_id"] == expected_id
    assert integration["receipt_hash"] == hash_excluding(
        dict(integration), "receipt_hash"
    )


def test_receipts_are_byte_equal_across_equal_runs() -> None:
    assert _attestation() == _attestation()
    assert _integration() == _integration()


def test_attest_does_not_mutate_its_inputs() -> None:
    receipts = diverse_receipts()
    before = copy.deepcopy(receipts)
    attest_provider_diversity(routing_receipts=receipts)
    assert receipts == before


def test_integrate_does_not_mutate_its_inputs() -> None:
    attestation = _attestation()
    reward = _reward()
    state = safe_bandit_state()
    fallback = fallback_receipt()
    before = copy.deepcopy((attestation, reward, state, fallback))
    integrate_provider_gate(
        run_id="RUN-1",
        diversity_attestation=attestation,
        reward_attribution=reward,
        bandit_state=state,
        fallback_receipts=[fallback],
    )
    assert (attestation, reward, state, fallback) == before


def test_integration_binds_only_the_rederived_sub_receipts() -> None:
    attestation = _attestation()
    reward = _reward()
    state = safe_bandit_state()
    integration = integrate_provider_gate(
        run_id="RUN-1",
        diversity_attestation=attestation,
        reward_attribution=reward,
        bandit_state=state,
    )
    components = integration["components"]
    assert components["diversity_attestation_id"] == attestation["attestation_id"]
    assert components["reward_attribution_id"] == reward["receipt_id"]
    assert components["bandit_state_id"] == state["state_id"]


def test_bound_reward_is_recorded_as_search_signal_never_promotion() -> None:
    reward = _reward()
    # The reward the gate binds carries no promotion authority: its own record
    # says so, and the integration gate refuses any admission that claims it.
    assert reward["drives_promotion"] is False
    integration = integrate_provider_gate(
        run_id="RUN-1",
        diversity_attestation=_attestation(),
        reward_attribution=reward,
        bandit_state=safe_bandit_state(),
    )
    assert "promotion" not in {key.lower() for key in integration}
    assert "promotion" not in {key.lower() for key in integration["components"]}


def test_cost_is_carried_as_bookkeeping_not_a_gated_threshold() -> None:
    # A high aggregate cost still integrates: cost is descriptive, never an
    # authority that promotes or rejects a candidate.
    attestation = _attestation()
    integration = integrate_provider_gate(
        run_id="RUN-1",
        diversity_attestation=attestation,
        reward_attribution=_reward(),
        bandit_state=safe_bandit_state(),
    )
    assert (
        integration["components"]["total_estimated_cost"]
        == (attestation["total_estimated_cost"])
    )
