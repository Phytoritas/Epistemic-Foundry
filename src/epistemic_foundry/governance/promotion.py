"""Promotion authority.

Contract source: `schemas/promotion-decision.schema.json`.

MASTER_EXECUTION_PROMPT section 8 is unambiguous: no scalar score, vote, model
confidence, novelty label, or backend `correct` flag can promote. Promotion
requires grounded evidence, scope/method compatibility, dependency correction,
the hard validation cascade, leakage/OOD qualification, multiplicity
accounting, challenge survival, independent adjudication, replication where
required, and human/policy gates.

This module therefore takes named requirement inputs, never a score. A missing
requirement yields `UNDERDETERMINED` or `BLOCKED` — truthful non-answers — and
never a downgraded-but-still-positive verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

PromotionLevel = str
Decision = Literal["PROMOTE", "CONDITIONAL", "REJECT", "UNDERDETERMINED", "BLOCKED"]
HardGateStatus = Literal["PASS", "FAIL", "PARTIAL"]

#: `promotion-decision.schema.json` types the adjudication and
#: selective-inference references as non-empty strings, so "absent" cannot be
#: encoded as null. An explicit sentinel keeps the record schema-valid while
#: still reading as missing evidence — the alternative (inventing a plausible
#: id) would fabricate the very artifact the gate is checking for.
ABSENT_REFERENCE = "ABSENT-not-produced"


class PromotionRefused(PermissionError):
    """A promotion was attempted on an authority the caller does not hold."""


@dataclass(frozen=True)
class PromotionRequest:
    """Named evidence inputs for one promotion decision.

    Every field is an artifact reference or a typed status. There is
    deliberately no `score`, `confidence`, or `novelty` field: adding one would
    make a scalar representable as promotion input.
    """

    candidate_id: str
    requested_level: PromotionLevel
    hard_gate_status: HardGateStatus
    fitness_vector_id: str
    parliament_adjudication_id: str | None
    selective_inference_report_id: str | None
    replication_result_ids: tuple[str, ...] = ()
    minority_report_ids: tuple[str, ...] = ()
    approval_record_ids: tuple[str, ...] = ()
    grounded_evidence_ids: tuple[str, ...] = ()
    dependency_cluster_ids: tuple[str, ...] = ()
    challenge_survived: bool = False
    leakage_detected: bool = False
    replication_required: bool = True
    human_approval_required: bool = True
    method_compatible: bool = True
    reasons: tuple[str, ...] = field(default=())


def _blocking_conditions(request: PromotionRequest) -> list[str]:
    """Conditions that stop promotion outright."""
    blocked: list[str] = []
    if request.leakage_detected:
        blocked.append(
            "hidden-holdout leakage detected: affected comparisons are INVALIDATED, not scored"
        )
    if request.hard_gate_status == "FAIL":
        blocked.append("hard validation cascade FAILED")
    return blocked


def _missing_requirements(request: PromotionRequest) -> list[str]:
    """Requirements whose absence leaves the decision underdetermined."""
    missing: list[str] = []
    if not request.grounded_evidence_ids:
        missing.append("no grounded source evidence: a promoted claim must resolve to source")
    if not request.dependency_cluster_ids:
        missing.append("no evidence-dependency correction recorded")
    if not request.parliament_adjudication_id:
        missing.append("no independent Parliament adjudication")
    if not request.selective_inference_report_id:
        missing.append("no selective-inference/multiplicity accounting")
    if not request.challenge_survived:
        missing.append("candidate has not survived Red Queen challenge")
    if not request.method_compatible:
        missing.append("scope/method compatibility not established")
    if request.replication_required and not request.replication_result_ids:
        missing.append("independent replication required but absent")
    if request.human_approval_required and not request.approval_record_ids:
        missing.append("human approval gate required but absent")
    return missing


def decide_promotion(request: PromotionRequest) -> dict[str, Any]:
    """Render a schema-valid `PromotionDecision`.

    Outcome order is fixed so a stronger verdict can never outrank a blocker:
    BLOCKED, then UNDERDETERMINED, then CONDITIONAL for a PARTIAL cascade, then
    PROMOTE only when every requirement is satisfied.
    """
    blockers = _blocking_conditions(request)
    missing = _missing_requirements(request)

    if blockers:
        decision: Decision = "BLOCKED"
        granted = "NONE"
        reasons = blockers + missing
    elif missing:
        decision = "UNDERDETERMINED"
        granted = "NONE"
        reasons = missing
    elif request.hard_gate_status == "PARTIAL":
        decision = "CONDITIONAL"
        granted = "NONE"
        reasons = [
            "every named requirement satisfied but the hard cascade is PARTIAL; "
            "promotion stays conditional pending full validation"
        ]
    else:
        decision = "PROMOTE"
        granted = request.requested_level
        reasons = ["all promotion requirements satisfied with resolving artifacts"]

    record: dict[str, Any] = {
        "decision_id": new_id("PD"),
        "candidate_id": request.candidate_id,
        "requested_level": request.requested_level,
        "granted_level": granted,
        "hard_gate_status": request.hard_gate_status,
        "fitness_vector_id": request.fitness_vector_id,
        "parliament_adjudication_id": request.parliament_adjudication_id or ABSENT_REFERENCE,
        "replication_result_ids": list(request.replication_result_ids),
        "selective_inference_report_id": request.selective_inference_report_id or ABSENT_REFERENCE,
        "minority_report_ids": list(request.minority_report_ids),
        "decision": decision,
        "rationale": "; ".join(list(request.reasons) + reasons),
        "approval_record_ids": list(request.approval_record_ids),
    }
    record["decision_hash"] = hash_excluding(record, "decision_hash")
    validate_artifact("promotion-decision", record)
    return record


def promoted(decision: dict[str, Any]) -> bool:
    """True only for an actual PROMOTE verdict.

    `CONDITIONAL` is not promotion. Treating it as such is how a conditional
    result becomes an overclaim downstream.
    """
    return decision.get("decision") == "PROMOTE"
