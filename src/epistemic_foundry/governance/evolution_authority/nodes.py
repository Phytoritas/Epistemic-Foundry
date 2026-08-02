"""Workflow node entrypoints binding evolution promotion to bounded helpers.

Every deterministic, policy, or human-gate node of the canonical
``evolution_promotion`` workflow resolves here, and every entrypoint delegates
to the bounded authority helpers in :mod:`epistemic_foundry.governance.promotion`
or validates a sealed artifact fail-closed.  No entrypoint mutates an
evaluator, holdout, policy, or prior revision, and none can be reached by a
candidate, model, prompt, or backend identity (EF4-I41).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

from ...contracts import ContractViolation
from ...contracts.validation import validate_artifact
from ...domain.hashing import hash_excluding
from ..promotion import (
    CANONICAL_GATE_IDS,
    PromotionCommitter,
    PromotionRequest,
    decide_promotion,
)
from .registry import (
    EvolutionAuthorityError,
    resolve_references,
)


def _payload(value: Mapping[str, Any], key: str) -> Any:
    if key not in value:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", f"sealed node payload lacks {key}"
        )
    return value[key]


def _require_gate_decision(gate_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return the sealed GateDecision this node must emit."""

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
            "GATE_DECISION_INVALID", f"{gate_id}: {error}"
        ) from error
    if record.get("name") != gate_id:
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID",
            f"node is bound to {gate_id}, not {record.get('name')!r}",
        )
    if record.get("decision_hash") != hash_excluding(record, "decision_hash"):
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{gate_id} decision_hash mismatch"
        )
    for field in ("input_hash", "policy_version"):
        if not record.get(field):
            raise EvolutionAuthorityError(
                "GATE_DECISION_INVALID", f"{gate_id} lacks {field}"
            )
    if not record.get("evidence_ids"):
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{gate_id} must cite resolving evidence IDs"
        )
    if record.get("status") == "WAIVE":
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{gate_id} cannot be waived"
        )
    return record


def _gate_node(gate_id: str) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    def run(payload: Mapping[str, Any]) -> dict[str, Any]:
        return _require_gate_decision(gate_id, payload)

    run.__name__ = f"run_{gate_id.lower()}"
    return run


def record_promotion_request_intent(payload: Mapping[str, Any]) -> dict[str, Any]:
    intent = dict(_payload(payload, "action_intent"))
    try:
        validate_artifact("action-intent", intent)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ACTION_INTENT_INVALID", str(error)) from error
    if intent.get("action_type") != "request_promotion":
        raise EvolutionAuthorityError(
            "ACTION_INTENT_INVALID",
            "the request node records action_type=request_promotion",
        )
    return intent


def build_promotion_pack(payload: Mapping[str, Any]) -> dict[str, Any]:
    pack = dict(_payload(payload, "phase_artifact_set"))
    try:
        validate_artifact("phase-artifact-set", pack)
    except ContractViolation as error:
        raise EvolutionAuthorityError("PROMOTION_PACK_INVALID", str(error)) from error
    return pack


def verify_promotion_pack_receipts(payload: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(_payload(payload, "artifact_receipt"))
    try:
        validate_artifact("artifact-receipt", receipt)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ARTIFACT_RECEIPT_INVALID", str(error)) from error
    return receipt


def gate_g00_pin_resolution(payload: Mapping[str, Any]) -> dict[str, Any]:
    resolution = resolve_references(_payload(payload, "resolved_refs"))
    if resolution["status"] != "PASS":
        raise EvolutionAuthorityError(
            f"G00_{resolution['status']}",
            "; ".join(resolution["reasons"]) or "pin resolution failed",
        )
    return _require_gate_decision(CANONICAL_GATE_IDS[0], payload)


def resolve_human_policy_approval(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(_payload(payload, "approval_record"))
    try:
        validate_artifact("approval-record", record)
    except ContractViolation as error:
        raise EvolutionAuthorityError("APPROVAL_RECORD_INVALID", str(error)) from error
    return record


def acquire_promotion_commit_lease(payload: Mapping[str, Any]) -> dict[str, Any]:
    lease = dict(_payload(payload, "capability_lease"))
    try:
        validate_artifact("capability-lease", lease)
    except ContractViolation as error:
        raise EvolutionAuthorityError("CAPABILITY_LEASE_INVALID", str(error)) from error
    intent = dict(_payload(payload, "commit_action_intent"))
    try:
        validate_artifact("action-intent", intent)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ACTION_INTENT_INVALID", str(error)) from error
    if intent.get("action_type") != "commit_promotion":
        raise EvolutionAuthorityError(
            "ACTION_INTENT_INVALID",
            "the lease node records action_type=commit_promotion",
        )
    return lease


def commit_promotion_atomically(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = _payload(payload, "promotion_request")
    if not isinstance(request, PromotionRequest):
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", "promotion_request must be a sealed PromotionRequest"
        )
    decision = decide_promotion(request)
    committer = payload.get("committer")
    if committer is None:
        committer = PromotionCommitter()
    if not isinstance(committer, PromotionCommitter):
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", "committer must be the bounded PromotionCommitter"
        )
    result = committer.commit(
        dict(_payload(payload, "candidate")),
        decision,
        expected_revision=int(_payload(payload, "expected_revision")),
        effect_receipt=payload.get("effect_receipt"),
    )
    return {"decision": decision, "commit": result}


def reconcile_commit_receipts(payload: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(_payload(payload, "effect_receipt"))
    try:
        validate_artifact("effect-receipt", receipt)
    except ContractViolation as error:
        raise EvolutionAuthorityError("EFFECT_RECEIPT_INVALID", str(error)) from error
    decision = dict(_payload(payload, "promotion_decision"))
    if receipt.get("receipt_id") != decision.get("effect_receipt_id"):
        raise EvolutionAuthorityError(
            "EFFECT_RECEIPT_INVALID",
            "EffectReceipt does not resolve the committed PromotionDecision",
        )
    return _require_gate_decision(CANONICAL_GATE_IDS[14], payload)


NODE_ENTRYPOINTS: Final[dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]]] = {
    "record_promotion_request_intent": record_promotion_request_intent,
    "build_promotion_pack": build_promotion_pack,
    "verify_promotion_pack_receipts": verify_promotion_pack_receipts,
    "gate_g00_pin_resolution": gate_g00_pin_resolution,
    "gate_g01_policy_authority": _gate_node(CANONICAL_GATE_IDS[1]),
    "gate_g02_evaluator_holdout_firewall": _gate_node(CANONICAL_GATE_IDS[2]),
    "gate_g03_schema_lineage_count": _gate_node(CANONICAL_GATE_IDS[3]),
    "gate_g04_source_provenance": _gate_node(CANONICAL_GATE_IDS[4]),
    "gate_g05_search_coverage": _gate_node(CANONICAL_GATE_IDS[5]),
    "gate_g06_method_scope_dependency": _gate_node(CANONICAL_GATE_IDS[6]),
    "gate_g07_validation_leakage": _gate_node(CANONICAL_GATE_IDS[7]),
    "gate_g08_adaptive_statistics": _gate_node(CANONICAL_GATE_IDS[8]),
    "gate_g09_red_queen": _gate_node(CANONICAL_GATE_IDS[9]),
    "gate_g10_replication_ceiling": _gate_node(CANONICAL_GATE_IDS[10]),
    "gate_g11_parliament": _gate_node(CANONICAL_GATE_IDS[11]),
    "gate_g12_independent_attestation": _gate_node(CANONICAL_GATE_IDS[12]),
    "resolve_human_policy_approval": resolve_human_policy_approval,
    "gate_g13_human_policy_approval": _gate_node(CANONICAL_GATE_IDS[13]),
    "acquire_promotion_commit_lease": acquire_promotion_commit_lease,
    "commit_promotion_atomically": commit_promotion_atomically,
    "reconcile_commit_receipts": reconcile_commit_receipts,
}


def resolve_node_executor(
    node_id: str,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Return the bounded executor for one canonical promotion node."""

    try:
        return NODE_ENTRYPOINTS[node_id]
    except KeyError:
        raise EvolutionAuthorityError(
            "NODE_UNKNOWN", f"no evolution-authority executor for {node_id!r}"
        ) from None
