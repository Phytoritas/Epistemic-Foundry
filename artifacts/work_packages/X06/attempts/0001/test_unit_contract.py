"""unit_and_contract_tests — the happy paths hold their contracts.

Every surface produces a receipt that re-derives its own identifier and hash and
is a pure function of its inputs.  These tests exercise the compositions the way
a real run would: attest a diverse, cost-accounted routed set, attribute a
validated reward through the safe bandit, keep a fallback provider-neutral and a
backend advisory, and bind the sealed sub-decisions into one integration receipt.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evaluation import bandits
from epistemic_foundry.providers.v4_x06 import (
    assert_composed_neutrality,
    attest_provider_diversity,
    attribute_provider_reward,
    integrate_provider_gate,
    refuse_backend_provider_authority,
)
from fixtures import (
    DELAYED_HOLDOUT,
    ELIGIBLE,
    REPLICATION,
    diverse_receipts,
    fallback_receipt,
    reference_result,
    routing_receipt,
    safe_bandit_state,
    statistical_correction,
)


def _rederives(record: dict[str, object], hash_field: str) -> bool:
    return hash_excluding(dict(record), hash_field) == record[hash_field]


def _attestation() -> dict[str, object]:
    return attest_provider_diversity(routing_receipts=diverse_receipts())


def _reward(receipt: dict[str, object]) -> dict[str, object]:
    return attribute_provider_reward(
        routing_receipt=receipt,
        arm_id=ELIGIBLE[0],
        proxy_score=0.9,
        validated_utility=0.7,
        safety_passed=True,
        replication_confirmed=True,
        statistical_correction=statistical_correction(),
    )


def test_attest_provider_diversity_accounts_cost_and_providers() -> None:
    receipts = diverse_receipts()
    attestation = attest_provider_diversity(routing_receipts=receipts)
    assert attestation["attestation_id"].startswith("XPD-")
    assert attestation["provider_count"] == len(ELIGIBLE)
    assert attestation["total_estimated_cost"] == 0.25 + 0.4
    assert attestation["selected_provider_set"] == sorted({ELIGIBLE[0], ELIGIBLE[1]})
    assert attestation["routing_receipt_ids"] == sorted(
        r["receipt_id"] for r in receipts
    )
    assert _rederives(attestation, "attestation_hash")


def test_attestation_is_a_pure_function_of_its_inputs() -> None:
    assert _attestation() == _attestation()


def test_attribute_reward_draws_from_validated_utility() -> None:
    reward = _reward(routing_receipt(reward_basis=REPLICATION))
    assert reward["reward"] == 0.7
    assert reward["drives_promotion"] is False
    assert reward["receipt_id"].startswith("XBR-")
    assert _rederives(reward, "receipt_hash")


def test_composed_neutrality_reports_provider_local_differences() -> None:
    receipt = assert_composed_neutrality(
        reference_result=reference_result(),
        fallback_result=reference_result(
            model="provider-b", provider="provider-b", latency_ms=87
        ),
        eligible_model_ids=list(ELIGIBLE),
        primary_model_id=ELIGIBLE[0],
        fallback_model_id=ELIGIBLE[1],
    )
    assert receipt["semantics_preserved"] is True
    assert "latency_ms" in receipt["provider_local_differences"]
    assert receipt["receipt_id"].startswith("XFN-")


def test_refuse_backend_provider_authority_keeps_a_clean_backend_advisory() -> None:
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
    gate = refuse_backend_provider_authority(imported=imported, bindings={})
    assert gate["authoritative"] is False


def test_integrate_provider_gate_binds_the_sealed_sub_decisions() -> None:
    attestation = _attestation()
    receipt = diverse_receipts()[0]
    reward = _reward(receipt)
    state = safe_bandit_state()
    integration = integrate_provider_gate(
        run_id="RUN-1",
        diversity_attestation=attestation,
        reward_attribution=reward,
        bandit_state=state,
        fallback_receipts=[fallback_receipt()],
    )
    assert integration["receipt_id"].startswith("XIG-")
    assert integration["run_id"] == "RUN-1"
    assert (
        integration["components"]["diversity_attestation_id"]
        == (attestation["attestation_id"])
    )
    assert integration["components"]["reward_attribution_id"] == reward["receipt_id"]
    assert integration["components"]["bandit_state_id"] == state["state_id"]
    assert integration["components"]["total_estimated_cost"] == 0.65
    assert "fallback_provider_neutrality" in integration["concerns_gated"]
    assert bandits.policy_bounds_safety(state) is True
    assert _rederives(integration, "receipt_hash")


def test_integration_without_fallbacks_gates_the_core_three_concerns() -> None:
    integration = integrate_provider_gate(
        run_id="RUN-2",
        diversity_attestation=_attestation(),
        reward_attribution=_reward(routing_receipt(reward_basis=DELAYED_HOLDOUT)),
        bandit_state=safe_bandit_state(),
    )
    assert integration["concerns_gated"] == [
        "provider_diversity_and_cost",
        "safe_bandit_policy",
        "safe_reward_attribution",
    ]
