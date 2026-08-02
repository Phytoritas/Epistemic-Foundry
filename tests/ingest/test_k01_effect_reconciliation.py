from __future__ import annotations

from dataclasses import replace

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.ingest.registry import (
    ActionIntentEvidence,
    EffectReceiptEvidence,
)
from tests.ingest.test_k01_document_registration import (
    RegistrationHarness,
    assert_code,
)


@pytest.mark.parametrize("status", ["FAILED", "UNKNOWN", "ROLLED_BACK", "NOT_EXECUTED"])
def test_non_success_effect_receipts_never_commit(status: str) -> None:
    harness = RegistrationHarness()
    harness.effect_status = status

    assert_code("DOCUMENT_SOURCE_EFFECT_UNRESOLVED", harness.run)
    assert harness.calls["compare_and_swap_registration"] == 0


def test_missing_effect_receipt_never_commits() -> None:
    harness = RegistrationHarness()
    harness.effect_missing = True

    assert_code("DOCUMENT_EFFECT_RECEIPT_MISSING", harness.run)
    assert harness.calls["compare_and_swap_registration"] == 0


def test_effect_requiring_reconciliation_never_commits() -> None:
    harness = RegistrationHarness()
    harness.effect_reconciliation_required = True

    assert_code("DOCUMENT_SOURCE_EFFECT_UNRESOLVED", harness.run)
    assert harness.calls["compare_and_swap_registration"] == 0


def test_effect_receipt_hash_mismatch_never_commits() -> None:
    class CorruptReceiptHarness(RegistrationHarness):
        def record_source_registration_effect(self, **kwargs):  # type: ignore[no-untyped-def]
            receipt = super().record_source_registration_effect(**kwargs)
            assert receipt is not None
            return replace(receipt, receipt_hash="sha256:" + "0" * 64)

    harness = CorruptReceiptHarness()
    assert_code("DOCUMENT_SOURCE_EFFECT_UNRESOLVED", harness.run)
    assert harness.calls["compare_and_swap_registration"] == 0


def test_effect_receipt_bound_to_another_intent_never_commits() -> None:
    class OtherIntentHarness(RegistrationHarness):
        def record_source_registration_effect(self, **kwargs):  # type: ignore[no-untyped-def]
            receipt = super().record_source_registration_effect(**kwargs)
            assert receipt is not None
            payload = receipt.to_dict()
            payload["intent_id"] = "INTENT-OTHER-K01-0001"
            payload["receipt_hash"] = hash_excluding(payload, "receipt_hash")
            return EffectReceiptEvidence.from_payload(payload)

    harness = OtherIntentHarness()
    assert_code("DOCUMENT_SOURCE_EFFECT_UNRESOLVED", harness.run)
    assert harness.calls["compare_and_swap_registration"] == 0


def test_incomplete_existing_commit_requires_shared_reconciliation() -> None:
    harness = RegistrationHarness()
    harness.run()
    key = str(harness.request["idempotency_key"])
    committed = harness.committed_by_key[key]
    harness.committed_by_key[key] = replace(
        committed,
        source_publication=replace(
            committed.source_publication,
            effect=replace(
                committed.source_publication.effect,
                status="UNKNOWN",
            ),
        ),
    )

    assert_code("DOCUMENT_RECONCILIATION_REQUIRED", lambda: harness.run(attempt=2))
    assert harness.calls["reconcile_registration"] == 1


def test_valid_shared_reconciliation_reopens_all_evidence() -> None:
    harness = RegistrationHarness()
    first = harness.run()
    key = str(harness.request["idempotency_key"])
    valid = harness.committed_by_key[key]
    harness.committed_by_key[key] = replace(
        valid,
        cas=replace(valid.cas, ok=False, status="CONFLICT"),
    )
    harness.reconciled_by_key[key] = valid

    replay = harness.run(attempt=2)

    assert replay["status"] == "success"
    assert replay["metrics"]["replayed"] is True
    assert replay["output_artifact_ids"] == first["output_artifact_ids"]
    assert harness.calls["reconcile_registration"] == 1
    assert harness.calls["publish_source_blob"] == 1
    assert harness.calls["compare_and_swap_registration"] == 1


@pytest.mark.parametrize("current_revision_offset", [0, 2])
def test_replay_requires_exactly_one_committed_revision_advance(
    current_revision_offset: int,
) -> None:
    harness = RegistrationHarness()
    harness.run()
    key = str(harness.request["idempotency_key"])
    committed = harness.committed_by_key[key]
    harness.committed_by_key[key] = replace(
        committed,
        cas=replace(
            committed.cas,
            current_revision=(
                committed.cas.expected_revision + current_revision_offset
            ),
        ),
    )

    assert_code("DOCUMENT_RECONCILIATION_REQUIRED", lambda: harness.run(attempt=2))
    assert harness.calls["reconcile_registration"] == 1
    assert harness.calls["publish_source_blob"] == 1
    assert harness.calls["compare_and_swap_registration"] == 1


def test_replay_fails_when_e02_cannot_resolve_the_original_action_intent() -> None:
    harness = RegistrationHarness()
    harness.run()
    harness.action_intents.clear()

    assert_code("DOCUMENT_RECONCILIATION_REQUIRED", lambda: harness.run(attempt=2))


def test_replay_fails_when_resolved_action_intent_payload_was_mutated() -> None:
    harness = RegistrationHarness()
    harness.run()
    intent_id = next(iter(harness.action_intents))
    payload = harness.action_intents[intent_id].to_dict()
    payload["target_ref"] = "ART-SOURCE-OTHER-K01"
    payload["intent_hash"] = hash_excluding(payload, "intent_hash")
    harness.action_intents[intent_id] = ActionIntentEvidence.from_payload(payload)

    assert_code("DOCUMENT_RECONCILIATION_REQUIRED", lambda: harness.run(attempt=2))
