"""Human authority is recorded, scoped, expiring, and cannot waive a hard gate."""

from __future__ import annotations

import pytest

from epistemic_foundry.governance.approvals import (
    ApprovalRefused,
    approval_is_current,
    build_approval_record,
    build_human_decision,
    downstream_invalidated_by,
)


def _approval(**overrides) -> dict:
    kwargs = dict(
        run_id="RUN-1",
        subject_id="HYP-1",
        approval_type="high_risk_validation",
        decision="APPROVE",
        authority_id="HUMAN-1",
        authority_role="research_integrity_officer",
        reason="cascade evidence reviewed against the preregistered threshold",
        evidence_artifact_ids=["ART-1"],
        expires_at="2026-12-31T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return build_approval_record(**kwargs)


def _decision(**overrides) -> dict:
    kwargs = dict(
        run_id="RUN-1",
        subject_id="HYP-1",
        decision_type="correct",
        decision="corrected scope to adult learners only",
        authority_id="HUMAN-1",
        authority_role="research_integrity_officer",
        rationale="population was overstated relative to the sampled cohort",
        evidence_artifact_ids=["ART-1"],
        affected_artifact_ids=["EV-1", "EV-2"],
    )
    kwargs.update(overrides)
    return build_human_decision(**kwargs)


# -- approvals ----------------------------------------------------------


def test_approval_records_authority_and_evidence() -> None:
    approval = _approval()
    assert approval["authority_id"] == "HUMAN-1"
    assert approval["evidence_artifact_ids"] == ["ART-1"]
    assert approval["record_hash"].startswith("sha256:")


def test_granting_approval_without_evidence_is_refused() -> None:
    """An auditor must be able to tell what the approver reviewed."""
    with pytest.raises(ApprovalRefused) as excinfo:
        _approval(evidence_artifact_ids=[])
    assert "what the approver reviewed" in str(excinfo.value)


def test_granting_approval_without_a_reason_is_refused() -> None:
    with pytest.raises(ApprovalRefused):
        _approval(reason="  ")


def test_open_ended_approval_is_refused() -> None:
    """A grant with no expiry is a standing permission nobody re-examines."""
    with pytest.raises(ApprovalRefused) as excinfo:
        _approval(expires_at="")
    assert "standing permission" in str(excinfo.value)


def test_denial_needs_no_evidence_artifacts() -> None:
    """Refusing permission is always allowed; only granting needs support."""
    denial = _approval(decision="DENY", evidence_artifact_ids=[], reason="insufficient replication")
    assert denial["decision"] == "DENY"


# -- consent scope ------------------------------------------------------


def test_approval_covers_only_the_reviewed_revision() -> None:
    """Consent is to a specific state of the work, not to the work forever."""
    approval = _approval()
    assert approval_is_current(approval, reviewed_revision=7, current_revision=7) is True
    assert approval_is_current(approval, reviewed_revision=7, current_revision=8) is False


def test_a_denial_is_never_current_consent() -> None:
    denial = _approval(decision="DENY", evidence_artifact_ids=[], reason="denied")
    assert approval_is_current(denial, reviewed_revision=1, current_revision=1) is False


# -- overrides ----------------------------------------------------------


def test_human_cannot_override_a_non_waivable_gate() -> None:
    with pytest.raises(ApprovalRefused) as excinfo:
        _decision(
            decision_type="override_waivable_gate",
            decision="waived",
            gate_is_non_waivable=True,
        )
    assert "not a hard one" in str(excinfo.value)


def test_human_may_override_a_waivable_gate() -> None:
    record = _decision(
        decision_type="override_waivable_gate",
        decision="waived cosmetic lint gate",
        gate_is_non_waivable=False,
    )
    assert record["decision_type"] == "override_waivable_gate"


def test_decision_must_acknowledge_non_mutation() -> None:
    """A decision records a judgment about state; it is not a mutation channel."""
    with pytest.raises(ApprovalRefused) as excinfo:
        _decision(non_mutation_acknowledgement=False)
    assert "non-mutation" in str(excinfo.value)


def test_decision_requires_a_rationale() -> None:
    with pytest.raises(ApprovalRefused):
        _decision(rationale="")


# -- downstream invalidation -------------------------------------------


def test_correction_invalidates_live_downstream_artifacts() -> None:
    record = _decision()
    assert downstream_invalidated_by(record, ["EV-1", "EV-3"]) == ["EV-1"]


def test_acceptance_does_not_invalidate_downstream() -> None:
    record = _decision(decision_type="accept", decision="accepted as stated")
    assert downstream_invalidated_by(record, ["EV-1", "EV-2"]) == []


@pytest.mark.parametrize("kind", ["correct", "reject", "withdraw", "narrow_scope"])
def test_every_corrective_decision_type_propagates(kind: str) -> None:
    record = _decision(decision_type=kind, decision=f"{kind} applied")
    assert downstream_invalidated_by(record, ["EV-1"]) == ["EV-1"]
