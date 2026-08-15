"""Workflow node entrypoints binding evolution promotion to bounded helpers.

Every deterministic, policy, or human-gate node of the canonical
``evolution_promotion`` workflow resolves here, and every entrypoint delegates
to the bounded authority helpers in :mod:`epistemic_foundry.governance.promotion`
or validates a sealed artifact fail-closed.  No entrypoint mutates an
evaluator, holdout, policy, or prior revision, and none can be reached by a
candidate, model, prompt, or backend identity (EF4-I41).

The three commit-phase nodes live in :mod:`.promotion` and :mod:`.reconciliation`
because they orchestrate a Kernel lease-protected transaction through an
injected port.  They are re-exported here so ``resolve_node_executor`` still
resolves every canonical node from one table, with exactly one implementation
per node.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

from ...contracts import ContractViolation
from ...contracts.registry import default_registry
from ...contracts.validation import validate_artifact
from ...domain.hashing import hash_excluding
from ..promotion import (
    CANONICAL_GATE_IDS,
)
from .approval import verify_approval_independence
from .attestation import verify_attestor_independence
from .promotion import (
    acquire_promotion_commit_lease,
    commit_promotion_atomically,
)
from .reconciliation import reconcile_commit_receipts
from .registry import (
    EvolutionAuthorityError,
    resolve_references,
    schema_enum_token,
)


#: The waiver status no promotion gate may carry.  It is read back from the
#: canonical GateDecision vocabulary rather than restated here (EF4-I22).
_WAIVED_GATE_STATUS: Final = schema_enum_token("gate-decision", "status", "WAIVE")
#: G12 accepts only the canonical passing attestation status.
_PASSING_ATTESTATION_STATUS: Final = schema_enum_token(
    "attestation", "overall_status", "PASS"
)
#: G13 accepts only the canonical positive approval decision.
_APPROVED_RECORD_DECISION: Final = schema_enum_token(
    "approval-record", "decision", "APPROVE"
)


def _phase_e_promotion_pack_contract() -> tuple[
    tuple[str, ...], frozenset[str], str, str
]:
    """Read core/conditional kind, phase, and status rules from the schema."""

    document = default_registry().document("phase-artifact-set")
    annotation = document.get("x-phase-e-promotion-pack")
    if not isinstance(annotation, Mapping):
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            "phase-artifact-set lacks x-phase-e-promotion-pack",
        )
    core = annotation.get("core_required_kinds")
    conditional = annotation.get("conditional_required_kinds")
    if (
        not isinstance(core, list)
        or not core
        or any(not isinstance(kind, str) or not kind for kind in core)
        or len(core) != len(set(core))
        or not isinstance(conditional, Mapping)
    ):
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            "phase-E promotion-pack kind annotation is malformed",
        )
    conditional_kinds: list[str] = []
    for rule_name, kinds in conditional.items():
        if (
            not isinstance(rule_name, str)
            or not rule_name
            or not isinstance(kinds, list)
            or not kinds
            or any(not isinstance(kind, str) or not kind for kind in kinds)
            or len(kinds) != len(set(kinds))
        ):
            raise EvolutionAuthorityError(
                "PROMOTION_PACK_INVALID",
                "phase-E conditional required-kind annotation is malformed",
            )
        conditional_kinds.extend(kinds)
    declared_kinds = (*core, *conditional_kinds)
    if len(declared_kinds) != len(set(declared_kinds)):
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            "phase-E required kinds are not unique across annotation rules",
        )

    properties = document.get("properties")
    required_artifacts = (
        properties.get("required_artifacts")
        if isinstance(properties, Mapping)
        else None
    )
    items = (
        required_artifacts.get("items")
        if isinstance(required_artifacts, Mapping)
        else None
    )
    item_properties = items.get("properties") if isinstance(items, Mapping) else None
    status = (
        item_properties.get("status")
        if isinstance(item_properties, Mapping)
        else None
    )
    statuses = status.get("enum") if isinstance(status, Mapping) else None
    phases = (
        properties.get("phase", {}).get("enum")
        if isinstance(properties, Mapping)
        and isinstance(properties.get("phase"), Mapping)
        else None
    )
    if (
        not isinstance(statuses, list)
        or "VALID" not in statuses
        or not isinstance(phases, list)
        or "E" not in phases
    ):
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            "phase-E promotion-pack phase/status vocabulary is malformed",
        )
    return tuple(core), frozenset(conditional_kinds), "E", "VALID"


def _payload(value: Mapping[str, Any], key: str) -> Any:
    if key not in value:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", f"sealed node payload lacks {key}"
        )
    return value[key]


def _context_or_spec_gap(
    payload: Mapping[str, Any], key: str, *, gate_id: str
) -> Any:
    """Require security context only where no node payload contract ratifies it."""

    if key not in payload:
        raise EvolutionAuthorityError(
            "SPEC_GAP",
            f"{gate_id} cannot be accepted until the node input contract "
            f"ratifies {key}",
        )
    return payload[key]


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
    if record.get("status") == _WAIVED_GATE_STATUS:
        raise EvolutionAuthorityError(
            "GATE_DECISION_INVALID", f"{gate_id} cannot be waived"
        )
    return record


def gate_g01_policy_authority(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G01_POLICY_AUTHORITY cannot be accepted until the node input contract "
        "ratifies its gate-evidence carrier/resolver for the sealed PolicyBundle "
        "body, principal capability grants, approval policy, authority-separation "
        "identities, and registered non-waivable gate set; caller-supplied "
        "GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g02_evaluator_holdout_firewall(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G02_EVALUATOR_HOLDOUT_FIREWALL cannot be accepted until the node input "
        "contract ratifies its gate-evidence carrier/resolver for the sealed "
        "EvaluatorBundle and qualification body, HoldoutManifest ACL/access "
        "audit, evaluator immutability proof, and candidate/model/prompt/backend "
        "identity set; caller-supplied GateDecision verdicts and evidence IDs "
        "are not authority",
    )


def gate_g03_schema_lineage_count(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G03_SCHEMA_LINEAGE_COUNT cannot be accepted until the node input "
        "contract ratifies its gate-evidence carrier/resolver for the candidate "
        "schema and lineage bodies plus expected/generated/evaluated/persisted/"
        "failed/cancelled/missing count reconciliation; caller-supplied "
        "GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g04_source_provenance(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G04_SOURCE_PROVENANCE cannot be accepted until the node input contract "
        "ratifies its gate-evidence carrier/resolver for SourceSpan bodies, "
        "ArtifactReceipts, evidence-linkage records, and trust labels; caller-"
        "supplied GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g05_search_coverage(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G05_SEARCH_COVERAGE cannot be accepted until the node input contract "
        "ratifies its gate-evidence carrier/resolver for EvidencePack and "
        "SearchCompletenessCertificate bodies covering support/counter/null/"
        "boundary/method/prior-art lane states and searched-scope accounting; "
        "caller-supplied GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g06_method_scope_dependency(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G06_METHOD_SCOPE_DEPENDENCY cannot be accepted until the node input "
        "contract ratifies its gate-evidence carrier/resolver for measurement-"
        "compatibility, ScopeVector, evidence-dependency-cluster, method-veto, "
        "and promotion-ceiling evidence; caller-supplied GateDecision verdicts "
        "and evidence IDs are not authority",
    )


def gate_g07_validation_leakage(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G07_VALIDATION_LEAKAGE cannot be accepted until the node input contract "
        "ratifies its gate-evidence carrier/resolver for "
        "EvaluatorQualificationReport, hidden/OOD/adversarial/metamorphic "
        "StageEvaluationResults, LeakageAudit, and evaluator-gaming evidence; "
        "caller-supplied GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g08_adaptive_statistics(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G08_ADAPTIVE_STATISTICS cannot be accepted until the node input contract "
        "ratifies its gate-evidence carrier/resolver for SequentialTestingLedger, "
        "MultipleTestingAdjustment, SelectiveInferenceReport, winner-selection "
        "path, and holdout-consumption records; caller-supplied GateDecision "
        "verdicts and evidence IDs are not authority",
    )


def gate_g09_red_queen(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G09_RED_QUEEN cannot be accepted until the node input contract ratifies "
        "its gate-evidence carrier/resolver for the strongest relevant "
        "RedQueen/ChallengeResult body and its reproducibility evidence; caller-"
        "supplied GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g10_replication_ceiling(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G10_REPLICATION_CEILING cannot be accepted until the node input contract "
        "ratifies its gate-evidence carrier/resolver for the requested-level "
        "replication requirement, claim/reproducibility class, ReplicationResult "
        "or explicit status, and computed maximum grantable level; caller-"
        "supplied GateDecision verdicts and evidence IDs are not authority",
    )


def gate_g11_parliament(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G11_PARLIAMENT cannot be accepted until the node input contract ratifies "
        "its gate-evidence carrier/resolver for sealed Parliament blind briefs, "
        "prosecutor/method/scope/causal/novelty/dependency audits, adjudication, "
        "strongest counterevidence, MinorityReports, and prior deterministic gate "
        "outcomes; caller-supplied GateDecision verdicts and evidence IDs are not "
        "authority",
    )


def gate_g13_human_policy_approval(
    _payload: Mapping[str, Any],
) -> dict[str, Any]:
    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G13_HUMAN_POLICY_APPROVAL cannot be accepted until the node input "
        "contract ratifies its gate-evidence carrier/resolver for valid unexpired "
        "ApprovalRecord bodies or the exact sealed PolicyBundle NOT_REQUIRED "
        "rule, maker/authority independence context, and applicable ceiling "
        "inputs; caller-supplied GateDecision verdicts and evidence IDs are not "
        "authority",
    )


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
    """Validate the sealed, complete phase-E pack and its required kinds."""

    raw_pack = _payload(payload, "phase_artifact_set")
    if not isinstance(raw_pack, Mapping):
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID", "phase_artifact_set must be an object"
        )
    pack = dict(raw_pack)
    try:
        validate_artifact("phase-artifact-set", pack)
    except ContractViolation as error:
        raise EvolutionAuthorityError("PROMOTION_PACK_INVALID", str(error)) from error
    core_kinds, conditional_kinds, phase_e, valid_status = (
        _phase_e_promotion_pack_contract()
    )
    if pack.get("set_hash") != hash_excluding(pack, "set_hash"):
        raise EvolutionAuthorityError("PROMOTION_PACK_INVALID", "set_hash mismatch")
    if pack.get("phase") != phase_e:
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID", "promotion pack must be phase E"
        )
    if pack.get("complete") is not True or pack.get("missing_kinds"):
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            "phase-E promotion pack must be complete with no missing kinds",
        )

    required_artifacts = pack["required_artifacts"]
    actual_kinds = [artifact["kind"] for artifact in required_artifacts]
    missing_core_kinds = [kind for kind in core_kinds if kind not in actual_kinds]
    if missing_core_kinds:
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID", f"missing core kinds: {missing_core_kinds}"
        )
    unknown_kinds = [
        kind
        for kind in actual_kinds
        if kind not in core_kinds and kind not in conditional_kinds
    ]
    if unknown_kinds:
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            f"undeclared required kinds: {unknown_kinds}",
        )
    invalid_artifacts = [
        artifact["artifact_id"]
        for artifact in required_artifacts
        if artifact["status"] != valid_status
    ]
    if invalid_artifacts:
        raise EvolutionAuthorityError(
            "PROMOTION_PACK_INVALID",
            f"required artifacts must be VALID: {invalid_artifacts}",
        )
    return pack


def verify_promotion_pack_receipts(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the supplied receipt and stop if other required receipts remain."""

    pack = build_promotion_pack(
        {
            "phase_artifact_set": _context_or_spec_gap(
                payload,
                "phase_artifact_set",
                gate_id="verify_promotion_pack_receipts",
            )
        }
    )
    raw_receipt = _payload(payload, "artifact_receipt")
    if not isinstance(raw_receipt, Mapping):
        raise EvolutionAuthorityError(
            "ARTIFACT_RECEIPT_INVALID", "artifact_receipt must be an object"
        )
    receipt = dict(raw_receipt)
    try:
        validate_artifact("artifact-receipt", receipt)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ARTIFACT_RECEIPT_INVALID", str(error)) from error
    if receipt.get("receipt_hash") != hash_excluding(receipt, "receipt_hash"):
        raise EvolutionAuthorityError(
            "ARTIFACT_RECEIPT_INVALID", "receipt_hash mismatch"
        )

    required_artifacts = pack["required_artifacts"]
    receipt_binding = (
        receipt["artifact_id"],
        receipt["receipt_id"],
        receipt["content_hash"],
    )
    matching = [
        artifact
        for artifact in required_artifacts
        if (
            artifact["artifact_id"],
            artifact["receipt_id"],
            artifact["content_hash"],
        )
        == receipt_binding
    ]
    if not matching:
        raise EvolutionAuthorityError(
            "ARTIFACT_RECEIPT_INVALID",
            "ArtifactReceipt does not exactly resolve a required promotion-pack "
            "artifact by artifact_id, receipt_id, and content_hash",
        )

    unresolved = [
        artifact["receipt_id"]
        for artifact in required_artifacts
        if (
            artifact["artifact_id"],
            artifact["receipt_id"],
            artifact["content_hash"],
        )
        != receipt_binding
    ]
    if unresolved:
        _context_or_spec_gap(
            payload,
            "artifact_receipts",
            gate_id="verify_promotion_pack_receipts for unresolved required "
            f"receipt IDs {unresolved}",
        )
        raise EvolutionAuthorityError(
            "SPEC_GAP",
            "artifact_receipts was supplied outside the closed NodeInvocation "
            "contract, but no ratified receipt-collection input/output or trusted "
            "artifact-resolution port exists for this node",
        )
    return receipt


def gate_g00_pin_resolution(payload: Mapping[str, Any]) -> dict[str, Any]:
    resolution = resolve_references(_payload(payload, "resolved_refs"))
    if resolution["status"] != "PASS":
        raise EvolutionAuthorityError(
            f"G00_{resolution['status']}",
            "; ".join(resolution["reasons"]) or "pin resolution failed",
        )
    return _require_gate_decision(CANONICAL_GATE_IDS[0], payload)


def gate_g12_independent_attestation(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Accept G12 only with a sealed PASS from an independent attestor."""

    gate = _require_gate_decision(CANONICAL_GATE_IDS[12], payload)
    raw_attestation = _context_or_spec_gap(
        payload, "attestation", gate_id="G12_INDEPENDENT_ATTESTATION"
    )
    if not isinstance(raw_attestation, Mapping):
        raise EvolutionAuthorityError(
            "ATTESTATION_INVALID", "attestation must be an object"
        )
    attestation = dict(raw_attestation)
    try:
        validate_artifact("attestation", attestation)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ATTESTATION_INVALID", str(error)) from error
    if attestation.get("attestation_hash") != hash_excluding(
        attestation, "attestation_hash"
    ):
        raise EvolutionAuthorityError(
            "ATTESTATION_INVALID", "attestation_hash mismatch"
        )
    if attestation.get("overall_status") != _PASSING_ATTESTATION_STATUS:
        raise EvolutionAuthorityError(
            "ATTESTATION_INVALID", "G12 requires a PASS attestation"
        )
    attestation_id = attestation.get("attestation_id")
    if not attestation_id or attestation_id not in tuple(gate.get("evidence_ids", ())):
        raise EvolutionAuthorityError(
            "ATTESTATION_INVALID",
            "the G12 GateDecision must cite the validated attestation",
        )
    verify_attestor_independence(
        attestation.get("attestor_id"),
        _context_or_spec_gap(
            payload,
            "independence_context",
            gate_id="G12_INDEPENDENT_ATTESTATION",
        ),
    )
    return gate


def resolve_human_policy_approval(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_record = _payload(payload, "approval_record")
    if not isinstance(raw_record, Mapping):
        raise EvolutionAuthorityError(
            "APPROVAL_RECORD_INVALID", "approval_record must be an object"
        )
    record = dict(raw_record)
    try:
        validate_artifact("approval-record", record)
    except ContractViolation as error:
        raise EvolutionAuthorityError("APPROVAL_RECORD_INVALID", str(error)) from error
    if record.get("record_hash") != hash_excluding(record, "record_hash"):
        raise EvolutionAuthorityError(
            "APPROVAL_RECORD_INVALID", "record_hash mismatch"
        )
    if record.get("decision") != _APPROVED_RECORD_DECISION:
        raise EvolutionAuthorityError(
            "APPROVAL_RECORD_INVALID", "promotion requires an APPROVE record"
        )
    # The current node contract has no trusted current_time input, so A05 must
    # not invent wall-clock authority here.  Expiry enforcement remains a
    # C01/C03 SPEC_GAP; canonical fields and maker independence still fail
    # closed with the context this payload already carries.
    verify_approval_independence(
        record.get("authority_id"),
        _context_or_spec_gap(
            payload, "maker_ids", gate_id="G13_HUMAN_POLICY_APPROVAL"
        ),
    )
    return record


NODE_ENTRYPOINTS: Final[dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]]] = {
    "record_promotion_request_intent": record_promotion_request_intent,
    "build_promotion_pack": build_promotion_pack,
    "verify_promotion_pack_receipts": verify_promotion_pack_receipts,
    "gate_g00_pin_resolution": gate_g00_pin_resolution,
    "gate_g01_policy_authority": gate_g01_policy_authority,
    "gate_g02_evaluator_holdout_firewall": gate_g02_evaluator_holdout_firewall,
    "gate_g03_schema_lineage_count": gate_g03_schema_lineage_count,
    "gate_g04_source_provenance": gate_g04_source_provenance,
    "gate_g05_search_coverage": gate_g05_search_coverage,
    "gate_g06_method_scope_dependency": gate_g06_method_scope_dependency,
    "gate_g07_validation_leakage": gate_g07_validation_leakage,
    "gate_g08_adaptive_statistics": gate_g08_adaptive_statistics,
    "gate_g09_red_queen": gate_g09_red_queen,
    "gate_g10_replication_ceiling": gate_g10_replication_ceiling,
    "gate_g11_parliament": gate_g11_parliament,
    "gate_g12_independent_attestation": gate_g12_independent_attestation,
    "resolve_human_policy_approval": resolve_human_policy_approval,
    "gate_g13_human_policy_approval": gate_g13_human_policy_approval,
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
