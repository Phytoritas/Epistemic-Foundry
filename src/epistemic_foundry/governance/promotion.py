"""Receipt-bound scientific promotion authority.

Contract source: :mod:`schemas/promotion-decision.schema.json`.

The module accepts named evidence and gate artifacts, never a scalar score.
Decision construction is separate from the compare-and-swap commit: a valid
decision without a resolving ``EffectReceipt`` cannot mutate candidate state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Mapping

from ..contracts import ContractViolation, validate_artifact
from ..domain.hashing import hash_excluding, is_schema_digest, sha256_of_payload
from ..domain.ids import new_id
from ..domain.vocabularies import PROMOTION_LADDER, promotion_rank

PromotionLevel = StrEnum(
    "PromotionLevel",
    {level: level for level in PROMOTION_LADDER},
)


Decision = Literal["PROMOTE", "CONDITIONAL", "REJECT", "UNDERDETERMINED", "BLOCKED"]
HardGateStatus = Literal["PASS", "FAIL", "PARTIAL"]
ReplicationStatus = Literal[
    "NOT_RUN",
    "REPLICATED",
    "PARTIAL",
    "FAILED",
    "INCONCLUSIVE",
    "BLOCKED",
    "FORMAL_EQUIVALENT",
]

ABSENT_REFERENCE = "ABSENT-not-produced"
LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED = "LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED"

CANONICAL_GATE_IDS: tuple[str, ...] = (
    "G00_PIN_RESOLUTION",
    "G01_POLICY_AUTHORITY",
    "G02_EVALUATOR_HOLDOUT_FIREWALL",
    "G03_SCHEMA_LINEAGE_COUNT",
    "G04_SOURCE_PROVENANCE",
    "G05_SEARCH_COVERAGE",
    "G06_METHOD_SCOPE_DEPENDENCY",
    "G07_VALIDATION_LEAKAGE",
    "G08_ADAPTIVE_STATISTICS",
    "G09_RED_QUEEN",
    "G10_REPLICATION_CEILING",
    "G11_PARLIAMENT",
    "G12_INDEPENDENT_ATTESTATION",
    "G13_HUMAN_POLICY_APPROVAL",
    "G14_ATOMIC_PROMOTION_COMMIT",
)
NON_GRANTING_DECISIONS = frozenset({"REJECT", "UNDERDETERMINED", "BLOCKED"})

# Highest requested level at which A05 permits a substantive gate check to be
# represented by a policy-backed NOT_REQUIRED PASS.  The gate is never omitted:
# its GateDecision must still be present, hash-valid, PASS, and cite sealed
# policy evidence.  G13 is conditional at every level and is handled against
# ``human_approval_required`` below.
_NOT_REQUIRED_MAX_LEVEL: dict[str, PromotionLevel] = {
    "G03_SCHEMA_LINEAGE_COUNT": PromotionLevel.INBOX,
    "G05_SEARCH_COVERAGE": PromotionLevel.CANDIDATE,
    "G06_METHOD_SCOPE_DEPENDENCY": PromotionLevel.CANDIDATE,
    "G07_VALIDATION_LEAKAGE": PromotionLevel.LITERATURE_GROUNDED,
    "G08_ADAPTIVE_STATISTICS": PromotionLevel.CANDIDATE,
    "G09_RED_QUEEN": PromotionLevel.CANDIDATE,
    "G11_PARLIAMENT": PromotionLevel.CANDIDATE,
    "G12_INDEPENDENT_ATTESTATION": PromotionLevel.LITERATURE_GROUNDED,
}


class PromotionRefused(PermissionError):
    """A promotion request violates a non-waivable authority contract."""


class PromotionRevisionConflict(PromotionRefused):
    """The candidate revision changed before the atomic commit."""


class PromotionIdempotencyConflict(PromotionRefused):
    """One idempotency key was reused for a different logical request."""


class MissingEffectReceipt(PromotionRefused):
    """A commit was attempted without a resolving effect receipt."""


class ReassessmentRequired(PromotionRefused):
    """A promotion request attempted to encode a downgrade or invalidation."""


class LegacyPromotionLevelReviewRequired(PromotionRefused):
    """A legacy value has no safe repository-wide automatic mapping."""

    code = LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED


def promotion_idempotency_key(
    *,
    candidate_id: str,
    candidate_revision: int,
    requested_level: str,
    promotion_pack_hash: str,
    policy_bundle_hash: str,
) -> str:
    """Return the minimum A05 idempotency-key composition."""
    return ":".join(
        (
            candidate_id,
            str(candidate_revision),
            requested_level,
            promotion_pack_hash.removeprefix("sha256:"),
            policy_bundle_hash.removeprefix("sha256:"),
        )
    )


def _level_rank(level: object, *, field_name: str) -> int:
    if not isinstance(level, str):
        raise PromotionRefused(
            f"{field_name}={level!r} is not a canonical v4 promotion level"
        )
    try:
        return promotion_rank(level)
    except ValueError as exc:
        raise PromotionRefused(
            f"{field_name}={level!r} is not a canonical v4 promotion level"
        ) from exc


def migrate_legacy_promotion_level(
    legacy_level: str,
    *,
    migration_record: Mapping[str, Any] | None = None,
) -> str:
    """Accept a legacy level only after an explicit record-specific review.

    This is deliberately not an alias table. A noncanonical historical value
    has no repository-wide one-to-one meaning; the caller must provide a
    complete, hash-bound MigrationRecord that justifies this one conversion.
    """
    try:
        _level_rank(legacy_level, field_name="legacy_level")
        return legacy_level
    except PromotionRefused:
        pass
    if not isinstance(migration_record, Mapping):
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: {legacy_level!r} requires "
            "evidence-backed human/policy migration review"
        )

    required = (
        "record_type",
        "migration_id",
        "source_schema_version",
        "target_schema_version",
        "source_level",
        "target_level",
        "source_value_hash",
        "target_value_hash",
        "review_status",
        "review_authority_id",
        "review_evidence_artifact_ids",
        "rationale",
        "recorded_at",
        "migration_hash",
    )
    missing = [field for field in required if field not in migration_record]
    if missing:
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: MigrationRecord is missing {missing}"
        )
    if migration_record.get("record_type") != "PromotionLevelMigrationRecord":
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: wrong MigrationRecord type"
        )
    if migration_record.get("source_level") != legacy_level:
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: record does not bind source value"
        )
    target_level = migration_record.get("target_level")
    _level_rank(target_level, field_name="MigrationRecord.target_level")
    if migration_record.get("review_status") != "APPROVED":
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: migration review is not APPROVED"
        )
    if not migration_record.get("review_authority_id") or not migration_record.get(
        "review_evidence_artifact_ids"
    ):
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: review authority and evidence are required"
        )
    if migration_record.get("source_value_hash") != sha256_of_payload(legacy_level):
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: source value hash mismatch"
        )
    if migration_record.get("target_value_hash") != sha256_of_payload(target_level):
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: target value hash mismatch"
        )
    if migration_record.get("migration_hash") != hash_excluding(
        dict(migration_record), "migration_hash"
    ):
        raise LegacyPromotionLevelReviewRequired(
            f"{LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED}: MigrationRecord hash mismatch"
        )
    return str(target_level)


@dataclass(frozen=True)
class PromotionRequest:
    """Sealed inputs for one deterministic promotion decision."""

    candidate_id: str
    candidate_revision: int
    current_level: PromotionLevel
    requested_level: PromotionLevel
    policy_promotion_ceiling: PromotionLevel
    hard_gate_status: HardGateStatus
    fitness_vector_id: str
    phase_e_artifact_set_id: str
    promotion_pack_artifact_ids: tuple[str, ...]
    promotion_pack_hash: str
    gate_decision_ids: tuple[str, ...]
    artifact_receipt_ids: tuple[str, ...]
    effect_receipt_id: str
    request_action_intent_id: str
    commit_action_intent_id: str
    policy_bundle_hash: str
    idempotency_key: str
    parliament_adjudication_id: str | None
    attestation_id: str | None
    replication_status: ReplicationStatus
    selective_inference_report_id: str | None
    gate_decisions: tuple[Mapping[str, Any], ...]
    replication_result_ids: tuple[str, ...] = ()
    minority_report_ids: tuple[str, ...] = ()
    approval_record_ids: tuple[str, ...] = ()
    grounded_evidence_ids: tuple[str, ...] = ()
    dependency_cluster_ids: tuple[str, ...] = ()
    unresolved_limitations: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default=())
    conditional_grant_level: PromotionLevel | None = None
    challenge_survived: bool = False
    leakage_detected: bool = False
    human_approval_required: bool = True
    method_compatible: bool = True
    parliament_rejected: bool = False


def _replication_ceiling(status: str) -> str:
    if status in {"NOT_RUN", "PARTIAL", "INCONCLUSIVE", "BLOCKED"}:
        return PromotionLevel.EMPIRICALLY_TESTED
    if status == "FAILED":
        return PromotionLevel.LITERATURE_GROUNDED
    if status in {"REPLICATED", "FORMAL_EQUIVALENT"}:
        return PromotionLevel.REPLICATED
    raise PromotionRefused(f"unknown replication_status {status!r}")


def _effective_ceiling(request: PromotionRequest) -> str:
    policy_rank = _level_rank(
        request.policy_promotion_ceiling, field_name="policy_promotion_ceiling"
    )
    replication_level = _replication_ceiling(request.replication_status)
    replication_rank = _level_rank(replication_level, field_name="replication_ceiling")
    return PROMOTION_LADDER[min(policy_rank, replication_rank)]


def _blocking_conditions(request: PromotionRequest) -> list[str]:
    blocked: list[str] = []
    if request.leakage_detected:
        blocked.append(
            "hidden-holdout leakage detected: affected comparisons are INVALIDATED, not scored"
        )
    if request.hard_gate_status == "FAIL":
        blocked.append("hard validation cascade FAILED")
    failed_gates = [
        str(decision.get("name"))
        for decision in request.gate_decisions
        if decision.get("status") in {"FAIL", "BLOCK"}
    ]
    if failed_gates:
        blocked.append(
            "canonical promotion gates failed or blocked: " + ", ".join(failed_gates)
        )
    return blocked


def _is_policy_not_required(request: PromotionRequest, gate_id: str) -> bool:
    for decision in request.gate_decisions:
        if decision.get("name") != gate_id:
            continue
        return decision.get("status") == "PASS" and any(
            "NOT_REQUIRED" in str(reason) for reason in decision.get("reasons", ())
        )
    return False


def _missing_requirements(request: PromotionRequest) -> list[str]:
    missing: list[str] = []
    requested_rank = _level_rank(request.requested_level, field_name="requested_level")
    if not request.grounded_evidence_ids:
        missing.append("no grounded source evidence: a promoted claim must resolve to source")
    if not request.dependency_cluster_ids and not _is_policy_not_required(
        request, "G06_METHOD_SCOPE_DEPENDENCY"
    ):
        missing.append("no evidence-dependency correction recorded")
    if not request.parliament_adjudication_id and not _is_policy_not_required(
        request, "G11_PARLIAMENT"
    ):
        missing.append("no independent Parliament adjudication")
    if not request.selective_inference_report_id and not _is_policy_not_required(
        request, "G08_ADAPTIVE_STATISTICS"
    ):
        missing.append("no selective-inference/multiplicity accounting")
    if not request.challenge_survived and not _is_policy_not_required(
        request, "G09_RED_QUEEN"
    ):
        missing.append("candidate has not survived Red Queen challenge")
    if not request.method_compatible and not _is_policy_not_required(
        request, "G06_METHOD_SCOPE_DEPENDENCY"
    ):
        missing.append("scope/method compatibility not established")
    if request.replication_status == "NOT_RUN":
        missing.append("independent replication has not run")
    elif not request.replication_result_ids:
        missing.append("replication status has no resolving ReplicationResult")
    if (
        requested_rank
        >= _level_rank(
            PromotionLevel.VALIDATION_SCREENED,
            field_name="attestation_threshold",
        )
        and not request.attestation_id
    ):
        missing.append("independent attestation required but absent")
    elif (
        requested_rank
        < _level_rank(
            PromotionLevel.VALIDATION_SCREENED,
            field_name="attestation_threshold",
        )
        and not request.attestation_id
        and not _is_policy_not_required(request, "G12_INDEPENDENT_ATTESTATION")
    ):
        missing.append("G12 has no policy-backed NOT_REQUIRED determination")
    if request.human_approval_required and not request.approval_record_ids:
        missing.append("human approval gate required but absent")
    if (
        not request.human_approval_required
        and not request.approval_record_ids
        and not _is_policy_not_required(request, "G13_HUMAN_POLICY_APPROVAL")
    ):
        missing.append("G13 has no policy-backed NOT_REQUIRED determination")
    return missing


def _validate_gate_decisions(request: PromotionRequest) -> None:
    decisions = tuple(request.gate_decisions)
    if len(decisions) != len(CANONICAL_GATE_IDS):
        raise PromotionRefused(
            "gate_decisions must contain exactly one structured decision for G00-G14"
        )

    policy_versions: set[str] = set()
    artifact_ids: set[str] = set()
    requested_rank = _level_rank(request.requested_level, field_name="requested_level")
    for expected_gate_id, decision in zip(CANONICAL_GATE_IDS, decisions, strict=True):
        try:
            validate_artifact("gate-decision", dict(decision))
        except ContractViolation as exc:
            raise PromotionRefused(
                f"{expected_gate_id} is not a valid GateDecision: {exc}"
            ) from exc
        if decision.get("name") != expected_gate_id:
            raise PromotionRefused(
                f"gate_decisions must follow canonical semantic order; expected {expected_gate_id}"
            )
        artifact_id = decision.get("gate_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise PromotionRefused(
                f"{expected_gate_id} must have a non-empty opaque GateDecision artifact ID"
            )
        if artifact_id in artifact_ids:
            raise PromotionRefused(
                f"{expected_gate_id} reuses GateDecision artifact ID {artifact_id!r}"
            )
        artifact_ids.add(artifact_id)
        if decision.get("decision_hash") != hash_excluding(
            dict(decision), "decision_hash"
        ):
            raise PromotionRefused(f"{expected_gate_id} decision_hash mismatch")
        if not decision.get("evidence_ids"):
            raise PromotionRefused(f"{expected_gate_id} must cite resolving evidence IDs")
        if not decision.get("reasons"):
            raise PromotionRefused(f"{expected_gate_id} must record a reason")
        if decision.get("status") == "WAIVE":
            raise PromotionRefused(
                f"{expected_gate_id} uses WAIVE; applicability requires policy-backed "
                "NOT_REQUIRED PASS instead"
            )
        policy_versions.add(str(decision.get("policy_version")))

        is_not_required = any(
            "NOT_REQUIRED" in str(reason) for reason in decision.get("reasons", ())
        )
        if not is_not_required:
            continue
        if decision.get("status") != "PASS":
            raise PromotionRefused(
                f"{expected_gate_id} NOT_REQUIRED determination must have status PASS"
            )
        if expected_gate_id == "G13_HUMAN_POLICY_APPROVAL":
            if request.human_approval_required:
                raise PromotionRefused(
                    "G13 cannot be NOT_REQUIRED when the sealed request requires human approval"
                )
            continue
        max_level = _NOT_REQUIRED_MAX_LEVEL.get(expected_gate_id)
        if max_level is None or requested_rank > _level_rank(
            max_level, field_name=f"{expected_gate_id}_not_required_ceiling"
        ):
            raise PromotionRefused(
                f"{expected_gate_id} is substantively required for requested level "
                f"{request.requested_level}; NOT_REQUIRED is forbidden"
            )

    if len(policy_versions) != 1 or "None" in policy_versions or "" in policy_versions:
        raise PromotionRefused(
            "all G00-G14 GateDecisions must bind one explicit policy_version"
        )


def _validate_request(request: PromotionRequest) -> None:
    current_rank = _level_rank(request.current_level, field_name="current_level")
    requested_rank = _level_rank(request.requested_level, field_name="requested_level")
    _level_rank(request.policy_promotion_ceiling, field_name="policy_promotion_ceiling")
    if requested_rank <= current_rank:
        raise ReassessmentRequired(
            "promotion must advance the current level; retention, downgrade, retraction, and "
            "invalidation require the separate reassessment workflow"
        )
    if request.candidate_revision < 1:
        raise PromotionRefused("candidate_revision must be >= 1")
    if request.hard_gate_status not in {"PASS", "FAIL", "PARTIAL"}:
        raise PromotionRefused(f"unknown hard_gate_status {request.hard_gate_status!r}")
    if tuple(request.gate_decision_ids) != CANONICAL_GATE_IDS:
        raise PromotionRefused("gate_decision_ids must be the canonical ordered G00-G14 set")
    _validate_gate_decisions(request)
    if not request.promotion_pack_artifact_ids or not request.artifact_receipt_ids:
        raise PromotionRefused("promotion pack and resolving ArtifactReceipt IDs are required")
    if not request.effect_receipt_id:
        raise PromotionRefused("PromotionDecision requires an EffectReceipt reference")
    for field_name, digest in (
        ("promotion_pack_hash", request.promotion_pack_hash),
        ("policy_bundle_hash", request.policy_bundle_hash),
    ):
        if not is_schema_digest(digest):
            raise PromotionRefused(f"{field_name} must be sha256:<64 lowercase hex>")
    expected_key = promotion_idempotency_key(
        candidate_id=request.candidate_id,
        candidate_revision=request.candidate_revision,
        requested_level=request.requested_level,
        promotion_pack_hash=request.promotion_pack_hash,
        policy_bundle_hash=request.policy_bundle_hash,
    )
    if request.idempotency_key != expected_key:
        raise PromotionRefused(
            "idempotency_key is not bound to candidate, revision, requested level, pack, and policy"
        )
    if request.replication_status == "NOT_RUN" and request.replication_result_ids:
        raise PromotionRefused("replication_status NOT_RUN cannot cite ReplicationResult IDs")
    if request.conditional_grant_level is not None:
        _level_rank(request.conditional_grant_level, field_name="conditional_grant_level")


def decide_promotion(request: PromotionRequest) -> dict[str, Any]:
    """Create and validate an immutable canonical ``PromotionDecision``."""
    _validate_request(request)
    blockers = _blocking_conditions(request)
    missing = _missing_requirements(request)
    ceiling = _effective_ceiling(request)

    if blockers:
        if request.replication_status in {"NOT_RUN", "PARTIAL", "INCONCLUSIVE", "BLOCKED"}:
            # The canonical schema reserves these replication states for
            # CONDITIONAL/UNDERDETERMINED.  Do not launder a non-waivable
            # blocker into either verdict.
            raise PromotionRefused(
                "a non-waivable blocker cannot be encoded under this replication status; "
                "reconcile the replication state before issuing a decision"
            )
        decision: Decision = "BLOCKED"
        granted: str | None = None
        reasons = blockers + missing
    elif request.parliament_rejected or request.replication_status == "FAILED":
        decision = "REJECT"
        granted = None
        reasons = [
            "Evidence Parliament rejected the promotion request"
            if request.parliament_rejected
            else "independent replication FAILED; promotion request rejected without demotion"
        ]
    elif missing:
        decision = "UNDERDETERMINED"
        granted = None
        reasons = missing
    else:
        requested_rank = _level_rank(request.requested_level, field_name="requested_level")
        ceiling_rank = _level_rank(ceiling, field_name="promotion_ceiling")
        conditional_needed = (
            request.hard_gate_status == "PARTIAL" or requested_rank > ceiling_rank
        )
        if conditional_needed:
            grant = request.conditional_grant_level
            if grant is None:
                decision = "UNDERDETERMINED"
                granted = None
                reasons = [
                    "the requested level is not fully grantable and no evidence-backed lower "
                    "conditional grant was supplied"
                ]
            else:
                current_rank = _level_rank(request.current_level, field_name="current_level")
                grant_rank = _level_rank(grant, field_name="conditional_grant_level")
                if not current_rank < grant_rank < requested_rank:
                    raise PromotionRefused(
                        "CONDITIONAL requires current_level < granted_level < requested_level"
                    )
                if grant_rank > ceiling_rank:
                    raise PromotionRefused(
                        "conditional_grant_level exceeds the deterministic promotion ceiling"
                    )
                decision = "CONDITIONAL"
                granted = grant
                reasons = [
                    f"requested {request.requested_level}; deterministic ceiling {ceiling} and "
                    f"remaining conditions limit this decision to {grant}"
                ]
        else:
            if request.hard_gate_status != "PASS":
                raise PromotionRefused("PROMOTE requires hard_gate_status PASS")
            decision = "PROMOTE"
            granted = request.requested_level
            reasons = ["all promotion requirements satisfied with resolving artifacts"]

    limitations = list(dict.fromkeys((*request.unresolved_limitations, *missing)))
    if decision == "CONDITIONAL" and not limitations:
        limitations = ["requested level remains above the currently satisfied promotion boundary"]

    high_requested = _level_rank(
        request.requested_level, field_name="requested_level"
    ) >= _level_rank(
        PromotionLevel.VALIDATION_SCREENED,
        field_name="attestation_threshold",
    )
    record: dict[str, Any] = {
        "decision_id": new_id("PD"),
        "candidate_id": request.candidate_id,
        "candidate_revision": request.candidate_revision,
        "requested_level": request.requested_level,
        "granted_level": granted,
        "promotion_ceiling": ceiling,
        "hard_gate_status": request.hard_gate_status,
        "fitness_vector_id": request.fitness_vector_id,
        "phase_e_artifact_set_id": request.phase_e_artifact_set_id,
        "promotion_pack_artifact_ids": list(request.promotion_pack_artifact_ids),
        "promotion_pack_hash": request.promotion_pack_hash,
        "gate_decision_ids": list(request.gate_decision_ids),
        "artifact_receipt_ids": list(request.artifact_receipt_ids),
        "effect_receipt_id": request.effect_receipt_id,
        "request_action_intent_id": request.request_action_intent_id,
        "commit_action_intent_id": request.commit_action_intent_id,
        "policy_bundle_hash": request.policy_bundle_hash,
        "idempotency_key": request.idempotency_key,
        "parliament_adjudication_id": request.parliament_adjudication_id or ABSENT_REFERENCE,
        "attestation_id": request.attestation_id or (ABSENT_REFERENCE if high_requested else None),
        "replication_status": request.replication_status,
        "replication_result_ids": list(request.replication_result_ids),
        "selective_inference_report_id": request.selective_inference_report_id
        or ABSENT_REFERENCE,
        "minority_report_ids": list(request.minority_report_ids),
        "decision": decision,
        "rationale": "; ".join((*request.reasons, *reasons)),
        "unresolved_limitations": limitations,
        "approval_record_ids": list(request.approval_record_ids),
    }
    record["decision_hash"] = hash_excluding(record, "decision_hash")
    validate_promotion_decision_semantics(record, current_level=request.current_level)
    return record


def validate_promotion_decision_semantics(
    decision: Mapping[str, Any], *, current_level: str
) -> None:
    """Enforce the decision-scoped null, order, ceiling, and hash rules."""
    try:
        validate_artifact("promotion-decision", dict(decision))
    except ContractViolation as exc:
        raise PromotionRefused(str(exc)) from exc
    if decision.get("decision_hash") != hash_excluding(dict(decision), "decision_hash"):
        raise PromotionRefused("PromotionDecision decision_hash mismatch")
    current_rank = _level_rank(current_level, field_name="current_level")
    requested_rank = _level_rank(decision.get("requested_level"), field_name="requested_level")
    ceiling_rank = _level_rank(decision.get("promotion_ceiling"), field_name="promotion_ceiling")
    verdict = str(decision.get("decision"))
    granted = decision.get("granted_level")

    if verdict == "PROMOTE":
        grant_rank = _level_rank(granted, field_name="granted_level")
        if granted != decision.get("requested_level"):
            raise PromotionRefused("PROMOTE requires granted_level == requested_level")
        if not current_rank < grant_rank <= ceiling_rank:
            raise PromotionRefused("PROMOTE must advance current state without exceeding its ceiling")
        if decision.get("hard_gate_status") != "PASS":
            raise PromotionRefused("PROMOTE requires hard_gate_status PASS")
    elif verdict == "CONDITIONAL":
        grant_rank = _level_rank(granted, field_name="granted_level")
        if not current_rank < grant_rank < requested_rank:
            raise PromotionRefused(
                "CONDITIONAL requires current_level < granted_level < requested_level"
            )
        if grant_rank > ceiling_rank:
            raise PromotionRefused("CONDITIONAL granted_level exceeds promotion_ceiling")
        if not decision.get("unresolved_limitations"):
            raise PromotionRefused("CONDITIONAL requires unresolved limitations")
    elif verdict in NON_GRANTING_DECISIONS:
        if granted is not None:
            raise PromotionRefused(f"{verdict} requires granted_level null")
    else:
        raise PromotionRefused(f"unknown promotion decision {verdict!r}")

    expected_key = promotion_idempotency_key(
        candidate_id=str(decision["candidate_id"]),
        candidate_revision=int(decision["candidate_revision"]),
        requested_level=str(decision["requested_level"]),
        promotion_pack_hash=str(decision["promotion_pack_hash"]),
        policy_bundle_hash=str(decision["policy_bundle_hash"]),
    )
    if decision.get("idempotency_key") != expected_key:
        raise PromotionRefused("PromotionDecision idempotency_key composition mismatch")
    if tuple(decision.get("gate_decision_ids", ())) != CANONICAL_GATE_IDS:
        raise PromotionRefused("PromotionDecision does not contain canonical ordered G00-G14")
    required_authority_fields: list[str] = []
    if requested_rank > _level_rank(PromotionLevel.CANDIDATE, field_name="threshold"):
        required_authority_fields.extend(
            ("parliament_adjudication_id", "selective_inference_report_id")
        )
    if requested_rank >= _level_rank(
        PromotionLevel.VALIDATION_SCREENED, field_name="threshold"
    ):
        required_authority_fields.append("attestation_id")
    if verdict in {"PROMOTE", "CONDITIONAL"} and any(
        decision.get(field) in {None, ABSENT_REFERENCE}
        for field in required_authority_fields
    ):
        raise PromotionRefused("a granting decision cannot contain an absent authority reference")


def _logical_request_hash(decision: Mapping[str, Any]) -> str:
    stable = {
        key: value
        for key, value in decision.items()
        if key not in {"decision_id", "decision_hash"}
    }
    return sha256_of_payload(stable)


class PromotionCommitter:
    """In-memory reference authority for CAS and idempotent promotion commits.

    Durable implementations replace the in-memory replay map with Foundry
    Kernel/Noetic Ledger storage, but must preserve the same fail-closed rules.
    """

    def __init__(self) -> None:
        self._replays: dict[str, tuple[str, dict[str, Any]]] = {}

    def commit(
        self,
        candidate: Mapping[str, Any],
        decision: Mapping[str, Any],
        *,
        expected_revision: int,
        effect_receipt: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            validate_artifact("promotion-decision", dict(decision))
        except ContractViolation as exc:
            raise PromotionRefused(str(exc)) from exc
        if decision.get("decision_hash") != hash_excluding(dict(decision), "decision_hash"):
            raise PromotionRefused("PromotionDecision decision_hash mismatch")

        request_hash = _logical_request_hash(decision)
        key = str(decision["idempotency_key"])
        prior = self._replays.get(key)
        if prior is not None:
            prior_hash, prior_result = prior
            if prior_hash != request_hash:
                raise PromotionIdempotencyConflict(
                    "same idempotency key was reused with a different canonical request hash"
                )
            replay = copy.deepcopy(prior_result)
            replay["replayed"] = True
            return replay

        current_level = str(candidate.get("promotion_level", ""))
        validate_promotion_decision_semantics(decision, current_level=current_level)
        candidate_revision = int(candidate.get("revision", -1))
        if (
            expected_revision != candidate_revision
            or int(decision["candidate_revision"]) != candidate_revision
        ):
            raise PromotionRevisionConflict(
                f"expected candidate revision {expected_revision} and decision revision "
                f"{decision['candidate_revision']} must both equal current {candidate_revision}"
            )
        if candidate.get("candidate_id") != decision.get("candidate_id"):
            raise PromotionRefused("PromotionDecision targets a different candidate")
        if effect_receipt is None:
            raise MissingEffectReceipt(
                "crash or interruption before EffectReceipt reconciliation cannot promote"
            )
        try:
            validate_artifact("effect-receipt", dict(effect_receipt))
        except ContractViolation as exc:
            raise MissingEffectReceipt(str(exc)) from exc
        if effect_receipt.get("receipt_id") != decision.get("effect_receipt_id"):
            raise MissingEffectReceipt("EffectReceipt ID does not resolve PromotionDecision")
        if effect_receipt.get("intent_id") != decision.get("commit_action_intent_id"):
            raise MissingEffectReceipt("EffectReceipt does not resolve commit ActionIntent")
        if effect_receipt.get("idempotency_key") != key:
            raise MissingEffectReceipt("EffectReceipt idempotency key does not match decision")

        verdict = str(decision["decision"])
        state_changed = verdict in {"PROMOTE", "CONDITIONAL"}
        allowed_statuses = {"SUCCEEDED"} if state_changed else {"SUCCEEDED", "NOT_EXECUTED"}
        if effect_receipt.get("status") not in allowed_statuses:
            raise MissingEffectReceipt(
                f"EffectReceipt status {effect_receipt.get('status')!r} does not resolve commit"
            )

        new_candidate = copy.deepcopy(dict(candidate))
        if state_changed:
            previous_level = current_level
            new_candidate["revision"] = candidate_revision + 1
            new_candidate["promotion_level"] = decision["granted_level"]
            new_candidate["promotion_history"] = list(
                new_candidate.get("promotion_history", [])
            ) + [
                {
                    "decision_id": decision["decision_id"],
                    "from_level": previous_level,
                    "to_level": decision["granted_level"],
                    "candidate_revision": candidate_revision + 1,
                    "effect_receipt_id": effect_receipt["receipt_id"],
                }
            ]

        result = {
            "candidate": new_candidate,
            "decision_id": decision["decision_id"],
            "effect_receipt_id": effect_receipt["receipt_id"],
            "request_hash": request_hash,
            "state_changed": state_changed,
            "replayed": False,
        }
        self._replays[key] = (request_hash, copy.deepcopy(result))
        return result


def promoted(decision: Mapping[str, Any]) -> bool:
    """True only when this immutable decision newly grants a level."""
    return decision.get("decision") in {"PROMOTE", "CONDITIONAL"} and decision.get(
        "granted_level"
    ) is not None
