"""Deterministic gate evaluation.

Contract source: `schemas/gate-decision.schema.json`.

Two invariants shape this module:

* A gate decision is deterministic. The same inputs must yield the same
  `decision_hash`, so `input_hash` is computed over canonicalized inputs and
  the decision digest covers the whole record.
* `non_waivable` means what it says. A waiver applied to a non-waivable gate is
  rejected here rather than recorded as `WAIVE`, because a gate that can be
  waived by the party it constrains is not a gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from ..contracts import ContractViolation, validate_artifact
from ..domain.hashing import hash_excluding, sha256_of_payload
from ..domain.ids import new_id
from ..domain.status import GateStatus
from ..domain.time import utc_now_iso

EvaluatorType = Literal["deterministic", "human", "model_assisted", "formal_verifier"]

#: Gate statuses that count as satisfied. Declared once here and imported by
#: every consumer: three independent copies of this set would drift the moment a
#: status is added, and the copy that lagged would silently accept or reject the
#: wrong outcome.
SATISFIED_GATE_STATUSES: frozenset[str] = frozenset(
    {GateStatus.PASS.value, GateStatus.WAIVE.value}
)


class WaiverRefused(PermissionError):
    """A waiver was attempted against a non-waivable gate."""


@dataclass(frozen=True)
class GateEvaluation:
    """Outcome of one deterministic gate check."""

    name: str
    status: GateStatus
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    non_waivable: bool = True


@dataclass(frozen=True)
class GateSpec:
    """A named requirement evaluated against a candidate payload."""

    name: str
    required_keys: tuple[str, ...] = ()
    non_waivable: bool = True
    evidence_ids: tuple[str, ...] = field(default=())


def evaluate_gate(spec: GateSpec, candidate: dict[str, Any]) -> GateEvaluation:
    """Check that `candidate` carries every required key with a real value.

    Absent, None, and empty values are all failures: an empty evidence list
    satisfying a gate is precisely the "narrative completion" the spec forbids.
    """
    missing = [
        key
        for key in spec.required_keys
        if key not in candidate or candidate[key] is None or candidate[key] == "" or candidate[key] == []
    ]
    if missing:
        return GateEvaluation(
            name=spec.name,
            status=GateStatus.FAIL,
            reasons=tuple(f"missing required input: {key}" for key in sorted(missing)),
            evidence_ids=spec.evidence_ids,
            non_waivable=spec.non_waivable,
        )
    return GateEvaluation(
        name=spec.name,
        status=GateStatus.PASS,
        reasons=("all required inputs present",),
        evidence_ids=spec.evidence_ids,
        non_waivable=spec.non_waivable,
    )


def gate_decision(
    evaluation: GateEvaluation,
    *,
    run_id: str,
    policy_version: str,
    inputs: Any,
    gate_version: str,
    input_artifact_ids: Sequence[str],
    policy_bundle_hash: str,
    blocker_ids: Sequence[str],
    evaluator_type: EvaluatorType = "deterministic",
    waiver_authority: str | None = None,
    waiver_reason: str | None = None,
    gate_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Render a schema-valid `GateDecision` from an evaluation.

    The caller must supply every immutable authority binding.  In particular,
    input artifacts, policy content, blockers, and the gate contract version
    are never inferred from ambient state.  Supplying a waiver flips the
    recorded status to `WAIVE`, but only for a waivable gate and only with both
    an authority and a reason: an anonymous or unexplained waiver leaves no
    accountable party in the audit trail.
    """
    status = evaluation.status
    reasons = list(evaluation.reasons)

    if waiver_authority or waiver_reason:
        if evaluation.non_waivable:
            raise WaiverRefused(
                f"gate {evaluation.name!r} is non-waivable; refusing waiver by {waiver_authority!r}"
            )
        if not (waiver_authority and waiver_reason):
            raise ValueError("a waiver requires both waiver_authority and waiver_reason")
        status = GateStatus.WAIVE
        reasons.append(f"waived by {waiver_authority}: {waiver_reason}")

    timestamp = evaluated_at or utc_now_iso()
    decision: dict[str, Any] = {
        "gate_id": gate_id or new_id("GD"),
        "gate_version": gate_version,
        "run_id": run_id,
        "name": evaluation.name,
        "status": status.value,
        "reasons": reasons,
        "evidence_ids": list(evaluation.evidence_ids),
        "input_artifact_ids": list(input_artifact_ids),
        "policy_bundle_hash": policy_bundle_hash,
        "decision": status.value,
        "blocker_ids": list(blocker_ids),
        "waiver_authority": waiver_authority,
        "waiver_reason": waiver_reason,
        "evaluated_at": timestamp,
        "created_at": timestamp,
        "policy_version": policy_version,
        "non_waivable": evaluation.non_waivable,
        "evaluator_type": evaluator_type,
        "input_hash": sha256_of_payload(inputs),
    }
    decision["decision_hash"] = hash_excluding(decision, "decision_hash")
    validate_artifact("gate-decision", decision)
    return decision


def all_passed(decisions: Sequence[dict[str, Any]]) -> bool:
    """True only when every decision is PASS or a legitimate WAIVE.

    FAIL and BLOCK are never absorbed: a blocked gate is a truthful stop.
    """
    for decision in decisions:
        try:
            validate_artifact("gate-decision", decision)
        except ContractViolation:
            return False
        if decision["decision_hash"] != hash_excluding(decision, "decision_hash"):
            return False
        if decision["status"] not in SATISFIED_GATE_STATUSES:
            return False
    return True
