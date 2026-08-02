"""veto_fixture_test — only the method auditor may stop a promotion.

The veto is the one power that overrides agreement: three auditors satisfied
does not outweigh the one that found the measurement cannot support the claim.
It is therefore narrow by construction — only the method auditor holds it, it
must carry a reason, and a withdrawn veto stops constraining while staying on
the record.
"""

from __future__ import annotations

import pytest

from .contracts import (
    VETO_CAPABLE_AUDITORS,
    Auditor,
    AuditorContractError,
    VetoStatus,
    validate_audit,
    validate_verdict,
)
from .test_promotion_ceiling import ROOT, audit, panel, verdict


def sustained_method_veto(ceiling: str = "EMPIRICALLY_TESTED") -> dict[str, object]:
    return verdict(
        Auditor.METHOD.value,
        ceiling,
        findings=[
            {
                "code": "MEASUREMENT_INVALID",
                "evidence_ids": ["EVN-method-1"],
                "statement": "the instrument was never calibrated for this range",
            }
        ],
        strata={"randomized": ceiling},
        veto_reason="the measurement cannot support the claim at any level",
        veto_status=VetoStatus.SUSTAINED.value,
    )


def test_only_the_method_auditor_holds_the_veto() -> None:
    assert VETO_CAPABLE_AUDITORS == ("method_auditor",)


def test_a_sustained_veto_drops_the_ceiling_to_the_floor() -> None:
    record = audit(panel(**{Auditor.METHOD.value: sustained_method_veto()})).payload

    assert record["combined_ceiling"] == "INBOX"
    assert record["veto"]["floor_applied"] is True
    assert record["veto"]["sustained_by"] == ["method_auditor"]


def test_a_veto_overrides_three_satisfied_auditors() -> None:
    optimistic = panel(
        **{
            Auditor.METHOD.value: sustained_method_veto("REPLICATED"),
            Auditor.SCOPE.value: verdict(Auditor.SCOPE.value, "REPLICATED"),
            Auditor.CAUSAL.value: verdict(Auditor.CAUSAL.value, "REPLICATED"),
            Auditor.NOVELTY.value: verdict(Auditor.NOVELTY.value, "REPLICATED"),
        }
    )

    record = audit(optimistic).payload

    assert record["auditor_ceilings"][Auditor.METHOD.value] == "REPLICATED"
    assert record["combined_ceiling"] == "INBOX"


def test_a_withdrawn_veto_stops_constraining_but_stays_on_the_record() -> None:
    withdrawn = verdict(
        Auditor.METHOD.value,
        "EMPIRICALLY_TESTED",
        strata={"randomized": "EMPIRICALLY_TESTED"},
        veto_reason="calibration record was located after the first pass",
        veto_status=VetoStatus.WITHDRAWN.value,
    )

    record = audit(panel(**{Auditor.METHOD.value: withdrawn})).payload

    assert record["combined_ceiling"] == "EMPIRICALLY_TESTED"
    assert record["veto"]["floor_applied"] is False
    assert record["veto"]["withdrawn_by"] == ["method_auditor"]
    assert record["verdicts"][1]["veto_status"] == VetoStatus.WITHDRAWN.value


@pytest.mark.parametrize(
    "auditor",
    [Auditor.SCOPE.value, Auditor.CAUSAL.value, Auditor.NOVELTY.value],
)
def test_no_other_auditor_may_veto(auditor: str) -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(
            ROOT,
            verdict(
                auditor,
                "CANDIDATE",
                veto_reason="I disagree",
                veto_status=VetoStatus.SUSTAINED.value,
            ),
        )

    assert caught.value.code == "VETO_UNAUTHORIZED"
    assert caught.value.context["auditor"] == auditor


@pytest.mark.parametrize(
    "auditor",
    [Auditor.SCOPE.value, Auditor.CAUSAL.value, Auditor.NOVELTY.value],
)
def test_no_other_auditor_may_even_withdraw_a_veto_it_never_had(auditor: str) -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(
            ROOT,
            verdict(
                auditor,
                "CANDIDATE",
                veto_reason="never mind",
                veto_status=VetoStatus.WITHDRAWN.value,
            ),
        )

    assert caught.value.code == "VETO_UNAUTHORIZED"


def test_a_veto_must_carry_a_reason() -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(
            ROOT,
            verdict(
                Auditor.METHOD.value,
                "CANDIDATE",
                strata={"randomized": "CANDIDATE"},
                veto_status=VetoStatus.SUSTAINED.value,
            ),
        )

    assert caught.value.code == "INPUT_INVALID"


def test_a_verdict_with_no_veto_may_not_carry_a_reason() -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(
            ROOT,
            verdict(Auditor.SCOPE.value, "CANDIDATE", veto_reason="just in case"),
        )

    assert caught.value.code == "VETO_REASON_UNEXPECTED"


def test_a_non_canonical_veto_status_is_refused() -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(
            ROOT,
            verdict(
                Auditor.METHOD.value,
                "CANDIDATE",
                strata={"randomized": "CANDIDATE"},
                veto_reason="maybe",
                veto_status="PROBABLY",
            ),
        )

    assert caught.value.code == "VETO_STATUS_INVALID"


def test_a_veto_still_requires_the_method_auditor_to_stratify() -> None:
    unstratified = verdict(
        Auditor.METHOD.value,
        "CANDIDATE",
        veto_reason="cannot support the claim",
        veto_status=VetoStatus.SUSTAINED.value,
    )

    with pytest.raises(AuditorContractError) as caught:
        audit(panel(**{Auditor.METHOD.value: unstratified}))

    assert caught.value.code == "METHOD_STRATA_MISSING"


def test_a_vetoed_audit_still_records_what_each_auditor_found() -> None:
    record = audit(panel(**{Auditor.METHOD.value: sustained_method_veto()})).payload

    assert record["auditor_ceilings"] == {
        "causal_auditor": "EMPIRICALLY_TESTED",
        "method_auditor": "EMPIRICALLY_TESTED",
        "novelty_examiner": "EMPIRICALLY_TESTED",
        "scope_auditor": "EMPIRICALLY_TESTED",
    }
    method = record["verdicts"][1]
    assert method["findings"][0]["code"] == "MEASUREMENT_INVALID"
    assert method["findings"][0]["evidence_ids"] == ["EVN-method-1"]


def test_declaring_above_a_vetoed_floor_is_refused() -> None:
    with pytest.raises(AuditorContractError) as caught:
        audit(
            panel(**{Auditor.METHOD.value: sustained_method_veto()}),
            declared_ceiling="CANDIDATE",
        )

    assert caught.value.code == "CEILING_OVERCLAIM"
    assert caught.value.context["derived"] == "INBOX"


def test_removing_a_veto_from_a_rehashed_audit_fails_closed() -> None:
    from .contracts import _hash_excluding

    payload = audit(panel(**{Auditor.METHOD.value: sustained_method_veto()})).payload
    payload["veto"] = {"floor_applied": False, "sustained_by": [], "withdrawn_by": []}
    payload["combined_ceiling"] = "EMPIRICALLY_TESTED"
    payload["audit_hash"] = _hash_excluding(payload, "audit_hash")

    with pytest.raises(AuditorContractError) as caught:
        validate_audit(ROOT, payload)

    assert caught.value.code == "CEILING_MISMATCH"


def test_a_recorded_veto_state_must_match_the_verdicts() -> None:
    from .contracts import _hash_excluding

    payload = audit().payload
    payload["veto"]["sustained_by"] = ["method_auditor"]
    payload["audit_hash"] = _hash_excluding(payload, "audit_hash")

    with pytest.raises(AuditorContractError) as caught:
        validate_audit(ROOT, payload)

    assert caught.value.code == "VETO_MISMATCH"


def test_a_vetoed_audit_is_deterministic_and_content_addressed() -> None:
    first = audit(panel(**{Auditor.METHOD.value: sustained_method_veto()}))
    second = audit(panel(**{Auditor.METHOD.value: sustained_method_veto()}))

    assert first.canonical_bytes == second.canonical_bytes
    assert validate_audit(ROOT, first.payload).canonical_bytes == first.canonical_bytes
