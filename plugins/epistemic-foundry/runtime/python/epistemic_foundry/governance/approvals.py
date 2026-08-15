"""Human approvals and overrides as immutable records (EF4-I17).

Contract sources: `schemas/approval-record.schema.json` and
`schemas/human-decision.schema.json`.

Three properties matter:

* An approval is scoped to a subject and expires. An open-ended approval is a
  standing permission nobody re-examines.
* An override of a *non-waivable* gate is refused outright. `override_waivable_gate`
  is the only override decision type the schema offers, and this module holds
  that line rather than trusting the caller's classification.
* A human decision records the revision it reviewed. When the subject drifts past
  that revision the approval is stale, so `approval_is_current` compares them
  instead of treating any past approval as permanent consent.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Decision types that change what a gate concluded.
OVERRIDE_DECISION_TYPES: frozenset[str] = frozenset({"override_waivable_gate"})

#: Approval decisions that grant rather than withdraw permission.
GRANTING_DECISIONS: frozenset[str] = frozenset({"APPROVE"})


class ApprovalRefused(PermissionError):
    """An approval or override violates the human-authority contract."""


def build_approval_record(
    *,
    run_id: str,
    subject_id: str,
    approval_type: str,
    decision: str,
    authority_id: str,
    authority_role: str,
    reason: str,
    evidence_artifact_ids: Sequence[str],
    expires_at: str,
    conditions: Sequence[str] = (),
    approval_id: str | None = None,
    issued_at: str | None = None,
) -> dict[str, Any]:
    """Record one human approval.

    A granting decision requires supporting evidence and a reason: an approval
    with neither is a signature on an empty page, and a later auditor cannot tell
    what the approver actually saw.
    """
    if decision in GRANTING_DECISIONS:
        if not evidence_artifact_ids:
            raise ApprovalRefused(
                f"approval of {subject_id} grants permission with no evidence artifacts; "
                "an auditor could not tell what the approver reviewed"
            )
        if not reason.strip():
            raise ApprovalRefused("a granting approval requires a reason")
    if not expires_at.strip():
        raise ApprovalRefused(
            "an approval must expire; an open-ended grant is a standing permission "
            "nobody re-examines"
        )

    record: dict[str, Any] = {
        "approval_id": approval_id or new_id("APR"),
        "run_id": run_id,
        "subject_id": subject_id,
        "approval_type": approval_type,
        "decision": decision,
        "authority_id": authority_id,
        "authority_role": authority_role,
        "reason": reason,
        "evidence_artifact_ids": list(evidence_artifact_ids),
        "conditions": list(conditions),
        "issued_at": issued_at or utc_now_iso(),
        "expires_at": expires_at,
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    validate_artifact("approval-record", record)
    return record


def build_human_decision(
    *,
    run_id: str,
    subject_id: str,
    decision_type: str,
    decision: str,
    authority_id: str,
    authority_role: str,
    rationale: str,
    evidence_artifact_ids: Sequence[str],
    affected_artifact_ids: Sequence[str],
    non_mutation_acknowledgement: bool = True,
    supersedes_decision_id: str | None = None,
    decision_id: str | None = None,
    created_at: str | None = None,
    gate_is_non_waivable: bool = False,
) -> dict[str, Any]:
    """Record one human decision, refusing an override of a hard gate.

    `non_mutation_acknowledgement` must be true: a human decision records a
    judgment about state, it does not rewrite prior state. Accepting a false
    acknowledgement would make the decision a mutation channel.
    """
    if decision_type in OVERRIDE_DECISION_TYPES and gate_is_non_waivable:
        raise ApprovalRefused(
            f"refusing human override of a non-waivable gate on {subject_id}: human authority "
            "can waive a waivable gate, not a hard one"
        )
    if not non_mutation_acknowledgement:
        raise ApprovalRefused(
            "a human decision must acknowledge non-mutation; it records a judgment about state "
            "rather than rewriting it"
        )
    if not rationale.strip():
        raise ApprovalRefused("a human decision requires a rationale")

    record: dict[str, Any] = {
        "decision_id": decision_id or new_id("HD"),
        "run_id": run_id,
        "subject_id": subject_id,
        "decision_type": decision_type,
        "decision": decision,
        "authority_id": authority_id,
        "authority_role": authority_role,
        "rationale": rationale,
        "evidence_artifact_ids": list(evidence_artifact_ids),
        "affected_artifact_ids": list(affected_artifact_ids),
        "supersedes_decision_id": supersedes_decision_id,
        "non_mutation_acknowledgement": bool(non_mutation_acknowledgement),
        "created_at": created_at or utc_now_iso(),
    }
    record["decision_hash"] = hash_excluding(record, "decision_hash")
    validate_artifact("human-decision", record)
    return record


def approval_is_current(
    approval: Mapping[str, Any],
    *,
    reviewed_revision: int,
    current_revision: int,
) -> bool:
    """False when the subject drifted past the revision the human reviewed.

    Consent is to a specific state of the work, not to the work forever.
    """
    if str(approval.get("decision")) not in GRANTING_DECISIONS:
        return False
    return int(current_revision) <= int(reviewed_revision)


def downstream_invalidated_by(
    decision: Mapping[str, Any],
    downstream_artifact_ids: Sequence[str],
) -> list[str]:
    """Downstream artifacts invalidated by a corrective human decision.

    A correction that leaves dependents untouched has not been applied; the
    affected set is intersected with the live downstream ids so a caller cannot
    mistake a stale reference for a current dependency.
    """
    if str(decision.get("decision_type")) not in {"correct", "reject", "withdraw", "narrow_scope"}:
        return []
    affected = {str(item) for item in decision.get("affected_artifact_ids", [])}
    return sorted(affected & {str(item) for item in downstream_artifact_ids})
