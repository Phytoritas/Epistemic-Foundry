"""A05 post-commit reconciliation and G14 completion.

G14 completes only after the committed transaction actually reconciles to its
ledger event, effect receipt, and artifact receipt.  An interrupted dispatch
stays ``OUTCOME_UNKNOWN`` and is resolved by re-asking the port about the same
bound operation identity; it is never retried blindly and never inferred to
have succeeded.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...contracts import ContractViolation
from ...contracts.validation import validate_artifact
from ...domain.hashing import hash_excluding
from ..promotion import CANONICAL_GATE_IDS
from .cas import require_commit_port, validate_commit_operation
from .errors import EvolutionAuthorityError
from .models import OUTCOME_UNKNOWN, RESOLVED_DISPOSITIONS
from .promotion import build_commit_request
from .registry import schema_enum_token

G14_GATE_ID = CANONICAL_GATE_IDS[14]


#: The only EffectReceipt status that resolves an effect as durably succeeded.
#: A failed, rolled-back, or not-executed effect is a truthful outcome, but it
#: is not a committed promotion and may never complete G14.
_SUCCEEDED_RECEIPT_STATUS = schema_enum_token("effect-receipt", "status", "SUCCEEDED")
#: The only GateDecision status that completes a gate.
_PASSING_GATE_STATUS = schema_enum_token("gate-decision", "status", "PASS")
#: The waiver status, which G14 may never carry.
_WAIVED_GATE_STATUS = schema_enum_token("gate-decision", "status", "WAIVE")


def _payload(value: Mapping[str, Any], key: str) -> Any:
    if not isinstance(value, Mapping) or key not in value:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", f"sealed node payload lacks {key}"
        )
    return value[key]


def _require_g14_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision = _payload(payload, "gate_decision")
    if not isinstance(decision, Mapping):
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", "gate_decision must be an object"
        )
    record = dict(decision)
    try:
        validate_artifact("gate-decision", record)
    except ContractViolation as error:
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{G14_GATE_ID}: {error}"
        ) from error
    if record.get("name") != G14_GATE_ID:
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID",
            f"node is bound to {G14_GATE_ID}, not {record.get('name')!r}",
        )
    if record.get("decision_hash") != hash_excluding(record, "decision_hash"):
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{G14_GATE_ID} decision_hash mismatch"
        )
    for field in ("input_hash", "policy_version"):
        if not record.get(field):
            raise EvolutionAuthorityError(
                "GATE_DECISION_INVALID", f"{G14_GATE_ID} lacks {field}"
            )
    if not record.get("evidence_ids"):
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID",
            f"{G14_GATE_ID} must cite resolving evidence IDs",
        )
    status = record.get("status")
    if status == _WAIVED_GATE_STATUS:
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{G14_GATE_ID} cannot be waived"
        )
    if status != _PASSING_GATE_STATUS:
        # A FAIL or BLOCK is a truthful gate outcome, but it is not completion.
        # Returning a resolving receipt for it would report a promotion the
        # gate actually refused.
        raise EvolutionAuthorityError(
            "GATE_DECISION_REFUSED",
            f"{G14_GATE_ID} status {status!r} does not complete the promotion",
        )
    return record


def resolve_unknown_outcome(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Ask the port to resolve one previously unknown commit operation."""

    request = build_commit_request(payload)
    port = require_commit_port(request.port_binding_id, request.port_binding_hash)
    identity = request.as_invocation()
    resolved = port.reconcile_promotion(identity)
    if not isinstance(resolved, Mapping):
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_INVALID", "the commit port must return an object"
        )
    result = dict(resolved)
    for field in ("operation_id", "request_hash", "port_binding_id", "port_binding_hash"):
        if result.get(field) != identity.get(field):
            raise EvolutionAuthorityError(
                "COMMIT_RESULT_UNBOUND",
                f"reconciled result {field} does not resolve the original operation",
            )
    validate_commit_operation(identity, result)
    return result


def reconcile_commit_receipts(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile the commit's receipts, then emit the G14 GateDecision.

    The EffectReceipt records an effect that was already attempted; it is not a
    precondition of the compare-and-swap.  Completion requires that the receipt,
    ledger event, and artifact receipt all resolve the same committed
    transaction.
    """

    # Ask the trusted adapter what actually happened instead of trusting a
    # commit result carried in this node's payload.  A payload-supplied result
    # is a claim; only the port can answer for the Kernel transaction, so a
    # fabricated COMMITTED can never substitute for an unresolved dispatch.
    request = build_commit_request(payload)
    commit_result = resolve_unknown_outcome(payload)
    disposition = commit_result.get("disposition")
    if disposition == OUTCOME_UNKNOWN:
        raise EvolutionAuthorityError(
            "COMMIT_OUTCOME_UNKNOWN",
            "the commit outcome is unresolved; reconcile the original operation "
            "before completing G14",
        )
    if disposition not in RESOLVED_DISPOSITIONS:
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_INVALID",
            f"unknown commit disposition {disposition!r}",
        )
    validate_commit_operation(request.as_invocation(), commit_result)
    for field, expected in (
        ("operation_id", request.operation_id),
        ("request_hash", request.request_hash),
        ("port_binding_id", request.port_binding_id),
        ("port_binding_hash", request.port_binding_hash),
        ("capability_lease_id", request.capability_lease_id),
        ("fencing_token", request.fencing_token),
        ("observed_candidate_revision", request.expected_candidate_revision),
        ("observed_passport_revision", request.expected_passport_revision),
    ):
        if commit_result.get(field) != expected:
            raise EvolutionAuthorityError(
                "COMMIT_RESULT_UNBOUND",
                f"commit result {field} does not resolve the authorized operation",
            )

    receipt = dict(_payload(payload, "effect_receipt"))
    try:
        validate_artifact("effect-receipt", receipt)
    except ContractViolation as error:
        raise EvolutionAuthorityError("EFFECT_RECEIPT_INVALID", str(error)) from error
    if receipt.get("receipt_hash") != hash_excluding(dict(receipt), "receipt_hash"):
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_INVALID", "EffectReceipt receipt_hash mismatch"
        )
    if receipt.get("reconciliation_required"):
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_UNRESOLVED",
            "an unreconciled EffectReceipt cannot complete G14",
        )
    if receipt.get("status") != _SUCCEEDED_RECEIPT_STATUS:
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_UNRESOLVED",
            f"an effect with status {receipt.get('status')!r} did not commit a "
            "promotion and cannot complete G14",
        )
    if receipt.get("run_id") != request.run_id:
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_INVALID",
            "EffectReceipt belongs to a different run",
        )
    if receipt.get("intent_id") != request.action_intent_id:
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_INVALID",
            "EffectReceipt does not resolve the commit ActionIntent",
        )
    if receipt.get("idempotency_key") != request.idempotency_key:
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_INVALID",
            "EffectReceipt does not carry the authorized idempotency key",
        )

    # The decision is derived once, by the commit node, and carried forward.
    # Re-deriving it here would mint a new identifier and never match what the
    # Kernel actually committed.  What reconciliation must prove is that the
    # committed transaction, the receipts, and this decision all describe the
    # same authorized operation.
    decision = dict(_payload(payload, "promotion_decision"))
    try:
        validate_artifact("promotion-decision", decision)
    except ContractViolation as error:
        raise EvolutionAuthorityError(
            "PROMOTION_DECISION_INVALID", str(error)
        ) from error
    if decision.get("decision_hash") != hash_excluding(dict(decision), "decision_hash"):
        raise EvolutionAuthorityError(
            "PROMOTION_DECISION_INVALID",
            "PromotionDecision decision_hash mismatch",
        )
    if receipt.get("receipt_id") != decision.get("effect_receipt_id"):
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_INVALID",
            "EffectReceipt does not resolve the committed PromotionDecision",
        )
    if commit_result.get("promotion_decision_id") != decision.get("decision_id"):
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the committed transaction does not resolve this PromotionDecision",
        )
    if commit_result.get("promotion_decision_hash") != decision.get("decision_hash"):
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the committed transaction bound different PromotionDecision bytes",
        )
    if decision.get("candidate_id") != request.candidate_id:
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the PromotionDecision targets a different candidate",
        )
    if decision.get("candidate_revision") != request.expected_candidate_revision:
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the PromotionDecision targets a different candidate revision",
        )

    artifact_receipt = dict(_payload(payload, "artifact_receipt"))
    try:
        validate_artifact("artifact-receipt", artifact_receipt)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ARTIFACT_RECEIPT_INVALID", str(error)) from error
    if artifact_receipt.get("receipt_hash") != hash_excluding(
        dict(artifact_receipt), "receipt_hash"
    ):
        raise EvolutionAuthorityError(
            "ARTIFACT_RECEIPT_INVALID", "ArtifactReceipt receipt_hash mismatch"
        )
    # The ArtifactReceipt must belong to this operation's commit intent;
    # otherwise an unrelated receipt could stand in for the missing one.
    if artifact_receipt.get("action_intent_id") != request.action_intent_id:
        raise EvolutionAuthorityError(
            "ARTIFACT_RECEIPT_INVALID",
            "ArtifactReceipt does not resolve the commit ActionIntent",
        )
    # The committed decision must actually cite this receipt, so a valid but
    # unrelated receipt cannot stand in for the one the commit recorded.
    cited = tuple(str(value) for value in decision.get("artifact_receipt_ids", ()) or ())
    if str(artifact_receipt.get("receipt_id")) not in cited:
        raise EvolutionAuthorityError(
            "ARTIFACT_RECEIPT_INVALID",
            "the committed PromotionDecision does not cite this ArtifactReceipt",
        )

    # G14 must actually hold before this node completes, but the canonical node
    # output is the resolving EffectReceipt the workflow declares.
    _require_g14_decision(payload)
    return receipt


__all__ = [
    "G14_GATE_ID",
    "reconcile_commit_receipts",
    "resolve_unknown_outcome",
]
