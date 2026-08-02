"""negative_and_adversarial_tests — every refusal fires under attack.

Each declared ``FINDING_CODES`` entry is provoked at least once, and the
adversarial cases are the ones this gate exists to stop: a routed set with no
alternative provider, a provider selected outside its eligible set, a reward
attributed to a routing decision outside the attested set, a laundered reward
that claims promotion authority, a laundered fallback that quietly says semantics
were not preserved, a bandit state under an unsafe policy, and a backend reaching
for authority.  A refusal that fired under the wrong code would be as much a
defect as no refusal at all, so every case asserts the exact code — and the
laundering cases re-seal a forged sub-receipt's own identity so the gate refuses
it on its *content*, not on a broken hash.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.providers.v4_x06 import (
    assert_composed_neutrality,
    attest_provider_diversity,
    attribute_provider_reward,
    integrate_provider_gate,
    refuse_backend_provider_authority,
)
from epistemic_foundry.providers.v4_x06 import gate as mod
from fixtures import (
    ELIGIBLE,
    IMMEDIATE_PROXY,
    REPLICATION,
    diverse_receipts,
    fallback_receipt,
    reference_result,
    reseal,
    routing_receipt,
    safe_bandit_state,
    single_provider_receipt,
    statistical_correction,
    unsafe_bandit_state,
)


def _attestation() -> dict:
    return attest_provider_diversity(routing_receipts=diverse_receipts())


def _reward_in_set() -> dict:
    return attribute_provider_reward(
        routing_receipt=diverse_receipts()[0],
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )


# --- input integrity ----------------------------------------------------------


def test_empty_routing_receipt_set_is_refused() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        attest_provider_diversity(routing_receipts=[])
    assert caught.value.code == "INPUT_INVALID"


def test_empty_run_id_is_refused() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=safe_bandit_state(),
        )
    assert caught.value.code == "INPUT_INVALID"


# --- provider diversity and cost ----------------------------------------------


def test_malformed_routing_receipt_is_refused_by_schema() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        attest_provider_diversity(routing_receipts=[{"receipt_id": "X"}])
    assert caught.value.code == "ROUTING_CONTRACT_VIOLATED"


def test_tampered_routing_receipt_is_refused() -> None:
    receipt = routing_receipt()
    receipt["estimated_cost"] = 0.99  # schema-valid, but identity no longer holds
    with pytest.raises(mod.ProviderGateError) as caught:
        attest_provider_diversity(routing_receipts=[receipt, diverse_receipts()[1]])
    assert caught.value.code == "ROUTING_RECEIPT_TAMPERED"


def test_selecting_a_provider_outside_the_eligible_set_is_refused() -> None:
    forged = dict(routing_receipt())
    forged["selected_model_id"] = "provider-z"
    reseal(forged, "XMR-", "receipt_id", "receipt_hash")
    with pytest.raises(mod.ProviderGateError) as caught:
        attest_provider_diversity(routing_receipts=[forged])
    assert caught.value.code == "ROUTING_SELECTION_NOT_ELIGIBLE"


def test_single_provider_set_has_no_diversity() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        attest_provider_diversity(routing_receipts=[single_provider_receipt()])
    assert caught.value.code == "PROVIDER_DIVERSITY_ABSENT"


# --- safe reward attribution --------------------------------------------------


def test_reward_on_the_immediate_proxy_basis_is_refused() -> None:
    proxy = dict(routing_receipt())
    proxy["reward_basis"] = IMMEDIATE_PROXY  # route_mutation refuses to build one
    with pytest.raises(mod.ProviderGateError) as caught:
        attribute_provider_reward(
            routing_receipt=proxy,
            arm_id=ELIGIBLE[0],
            proxy_score=0.99,
            validated_utility=0.9,
            safety_passed=True,
            replication_confirmed=True,
            statistical_correction=statistical_correction(),
        )
    assert caught.value.code == "REWARD_ATTRIBUTION_REFUSED"
    assert caught.value.context["routing_finding_code"] == "BANDIT_REWARD_PROXY_BASIS"


def test_tampered_reward_admission_is_refused_at_integration() -> None:
    reward = _reward_in_set()
    reward["reward"] = 0.99  # keep the sealed id/hash: identity no longer re-derives
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=reward,
            bandit_state=safe_bandit_state(),
        )
    assert caught.value.code == "REWARD_ATTRIBUTION_TAMPERED"


def test_laundered_reward_claiming_promotion_authority_is_refused() -> None:
    reward = _reward_in_set()
    reward["drives_promotion"] = True
    reseal(reward, "XBR-", "receipt_id", "receipt_hash")
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=reward,
            bandit_state=safe_bandit_state(),
        )
    assert caught.value.code == "REWARD_DRIVES_PROMOTION"


def test_reward_for_an_unlisted_routing_decision_is_refused() -> None:
    outside = attribute_provider_reward(
        routing_receipt=routing_receipt(estimated_cost=0.99, reward_basis=REPLICATION),
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=outside,
            bandit_state=safe_bandit_state(),
        )
    assert caught.value.code == "REWARD_ROUTING_UNLISTED"


# --- composition tamper and safety --------------------------------------------


def test_tampered_diversity_attestation_is_refused() -> None:
    attestation = _attestation()
    attestation["total_estimated_cost"] = 9.99
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=attestation,
            reward_attribution=_reward_in_set(),
            bandit_state=safe_bandit_state(),
        )
    assert caught.value.code == "DIVERSITY_ATTESTATION_TAMPERED"


def test_fallback_that_rewrites_a_verdict_is_refused() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        assert_composed_neutrality(
            reference_result=reference_result(verdict="supported"),
            fallback_result=reference_result(
                verdict="refuted", model="provider-b", provider="provider-b"
            ),
            eligible_model_ids=list(ELIGIBLE),
            primary_model_id=ELIGIBLE[0],
            fallback_model_id=ELIGIBLE[1],
        )
    assert caught.value.code == "NEUTRALITY_REFUSED"
    assert caught.value.context["routing_finding_code"] == "PROVIDER_SEMANTICS_ALTERED"


def test_tampered_fallback_receipt_is_refused() -> None:
    fallback = fallback_receipt()
    fallback["primary_model_id"] = "provider-c"  # keep sealed id/hash
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=safe_bandit_state(),
            fallback_receipts=[fallback],
        )
    assert caught.value.code == "FALLBACK_RECEIPT_TAMPERED"


def test_laundered_fallback_denying_neutrality_is_refused() -> None:
    fallback = fallback_receipt()
    fallback["semantics_preserved"] = False
    reseal(fallback, "XFN-", "receipt_id", "receipt_hash")
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=safe_bandit_state(),
            fallback_receipts=[fallback],
        )
    assert caught.value.code == "FALLBACK_SEMANTICS_ALTERED"


def test_malformed_bandit_state_is_refused_by_schema() -> None:
    state = safe_bandit_state()
    del state["arms"]  # drop a required field
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=state,
        )
    assert caught.value.code == "BANDIT_STATE_CONTRACT_VIOLATED"


def test_tampered_bandit_state_is_refused() -> None:
    state = safe_bandit_state()
    state["last_updated"] = "2099-01-01T00:00:00+00:00"  # keep the sealed hash
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=state,
        )
    assert caught.value.code == "BANDIT_STATE_TAMPERED"


def test_unsafe_bandit_policy_is_refused() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=unsafe_bandit_state(),
        )
    assert caught.value.code == "BANDIT_POLICY_UNSAFE"


# --- backend non-authority ----------------------------------------------------


def test_external_backend_reaching_for_authority_is_refused() -> None:
    from epistemic_foundry.adapters.v4_t05 import import_shinka_run
    from epistemic_foundry.evolution_chamber.reconciliation import STAGES

    imported = import_shinka_run(
        import_id="IMP-0001",
        source_run_id="SRC-0001",
        target_session_id="SESS-0001",
        source_version="1.0.0",
        target_version="1.0.0",
        source_snapshot_hash="sha256:" + "0" * 64,
        migration_plan_id="MIG-0001",
        unconverted_fields=[],
        imported_at="2026-08-01T00:00:00+00:00",
        candidate_identities={stage: ["C-1"] for stage in STAGES},
    )
    with pytest.raises(mod.ProviderGateError) as caught:
        refuse_backend_provider_authority(
            imported=imported, bindings={"bandit_state": "promotion_decision"}
        )
    assert caught.value.code == "BACKEND_PROVIDER_AUTHORITY_LEAK"


def test_authoritative_backend_is_refused_at_integration() -> None:
    with pytest.raises(mod.ProviderGateError) as caught:
        integrate_provider_gate(
            run_id="RUN-1",
            diversity_attestation=_attestation(),
            reward_attribution=_reward_in_set(),
            bandit_state=safe_bandit_state(),
            backend_neutrality={"authoritative": True},
        )
    assert caught.value.code == "BACKEND_PROVIDER_AUTHORITY_LEAK"
