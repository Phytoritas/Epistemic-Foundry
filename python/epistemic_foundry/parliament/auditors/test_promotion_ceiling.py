"""promotion_ceiling_test — the combined ceiling is derived and deterministic.

Exit criteria under test: "promotion ceilings deterministic" and "method
incompatibility not pooled".  The ceiling is the lowest any auditor set, no
auditor can raise it, a declared ceiling above the derived one is refused, and
the method auditor must report per-stratum rather than a single blended figure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .contracts import (
    AUDITORS,
    Auditor,
    AuditorContractError,
    VetoStatus,
    combined_ceiling,
    evaluate_audit,
    ladder_rank,
    promotion_ladder,
    validate_audit,
    validate_verdict,
)

ROOT = Path(__file__).resolve().parents[4]
CREATED_AT = "2026-08-01T16:00:00Z"
SUBJECT = "HYP-1"
RUN = "RUN-1"
LADDER = promotion_ladder(str(ROOT))


def verdict(
    auditor: str,
    ceiling: str,
    *,
    findings: list[dict[str, object]] | None = None,
    strata: dict[str, str] | None = None,
    veto_status: str = VetoStatus.NONE.value,
    veto_reason: str | None = None,
) -> dict[str, object]:
    return {
        "auditor": auditor,
        "ceiling": ceiling,
        "findings": list(findings or []),
        "provenance_ref": f"prov:{auditor}",
        "stratum_ceilings": dict(strata or {}),
        "veto_reason": veto_reason,
        "veto_status": veto_status,
    }


def panel(**overrides: dict[str, object]) -> list[dict[str, object]]:
    base = {
        Auditor.METHOD.value: verdict(
            Auditor.METHOD.value,
            "EMPIRICALLY_TESTED",
            strata={
                "observational": "LITERATURE_GROUNDED",
                "randomized": "EMPIRICALLY_TESTED",
            },
        ),
        Auditor.SCOPE.value: verdict(Auditor.SCOPE.value, "EMPIRICALLY_TESTED"),
        Auditor.CAUSAL.value: verdict(Auditor.CAUSAL.value, "EMPIRICALLY_TESTED"),
        Auditor.NOVELTY.value: verdict(Auditor.NOVELTY.value, "EMPIRICALLY_TESTED"),
    }
    base.update(overrides)
    return list(base.values())


def audit(verdicts=None, **kwargs):
    return evaluate_audit(
        ROOT,
        verdicts if verdicts is not None else panel(),
        created_at=CREATED_AT,
        run_id=RUN,
        subject_id=SUBJECT,
        **kwargs,
    )


def test_the_ladder_is_read_from_the_passport_schema() -> None:
    assert LADDER == (
        "INBOX",
        "CANDIDATE",
        "LITERATURE_GROUNDED",
        "VALIDATION_SCREENED",
        "EMPIRICALLY_TESTED",
        "REPLICATED",
    )
    assert ladder_rank(ROOT, "INBOX") == 0
    assert ladder_rank(ROOT, "REPLICATED") == len(LADDER) - 1


def test_a_level_the_ladder_does_not_declare_fails_closed() -> None:
    with pytest.raises(AuditorContractError) as caught:
        ladder_rank(ROOT, "PROVEN")

    assert caught.value.code == "LEVEL_UNKNOWN"


def test_agreeing_auditors_yield_their_shared_ceiling() -> None:
    record = audit().payload

    assert record["combined_ceiling"] == "EMPIRICALLY_TESTED"
    assert record["declared_ceiling"] == "EMPIRICALLY_TESTED"
    assert record["veto"]["floor_applied"] is False


def test_the_lowest_ceiling_wins() -> None:
    record = audit(
        panel(
            **{
                Auditor.SCOPE.value: verdict(
                    Auditor.SCOPE.value,
                    "CANDIDATE",
                    findings=[
                        {
                            "code": "SCOPE_EXTRAPOLATED",
                            "evidence_ids": ["EVN-1"],
                            "statement": "tested indoors, claimed for field",
                        }
                    ],
                )
            }
        )
    ).payload

    assert record["combined_ceiling"] == "CANDIDATE"
    assert record["auditor_ceilings"][Auditor.METHOD.value] == "EMPIRICALLY_TESTED"


def test_three_agreeing_auditors_cannot_overrule_the_fourth() -> None:
    record = audit(
        panel(
            **{
                Auditor.CAUSAL.value: verdict(
                    Auditor.CAUSAL.value,
                    "LITERATURE_GROUNDED",
                    findings=[
                        {
                            "code": "IDENTIFICATION_UNSUPPORTED",
                            "evidence_ids": [],
                            "statement": "no identification strategy",
                        }
                    ],
                )
            }
        )
    ).payload

    assert record["combined_ceiling"] == "LITERATURE_GROUNDED"


def test_the_ceiling_is_deterministic_across_verdict_order() -> None:
    forward = audit(panel()).payload
    reversed_order = audit(list(reversed(panel()))).payload

    assert forward == reversed_order


def test_declaring_a_higher_ceiling_than_derived_is_refused() -> None:
    with pytest.raises(AuditorContractError) as caught:
        audit(declared_ceiling="REPLICATED")

    assert caught.value.code == "CEILING_OVERCLAIM"
    assert caught.value.context["derived"] == "EMPIRICALLY_TESTED"


def test_declaring_a_lower_ceiling_than_derived_is_allowed() -> None:
    record = audit(declared_ceiling="CANDIDATE").payload

    assert record["declared_ceiling"] == "CANDIDATE"
    assert record["combined_ceiling"] == "EMPIRICALLY_TESTED"


def test_the_method_auditor_reports_one_ceiling_per_stratum() -> None:
    record = audit().payload

    assert record["stratification"]["stratum_count"] == 2
    assert record["stratification"]["strata"] == {
        "observational": "LITERATURE_GROUNDED",
        "randomized": "EMPIRICALLY_TESTED",
    }
    assert record["stratification"]["pooled"] is False


def test_the_method_ceiling_is_the_strongest_stratum_not_a_blend() -> None:
    record = audit().payload

    assert record["stratification"]["strongest_stratum_ceiling"] == "EMPIRICALLY_TESTED"
    assert record["auditor_ceilings"][Auditor.METHOD.value] == "EMPIRICALLY_TESTED"


def test_a_blended_method_ceiling_is_refused_as_pooling() -> None:
    pooled = panel(
        **{
            Auditor.METHOD.value: verdict(
                Auditor.METHOD.value,
                "VALIDATION_SCREENED",
                strata={
                    "observational": "LITERATURE_GROUNDED",
                    "randomized": "EMPIRICALLY_TESTED",
                },
            )
        }
    )

    with pytest.raises(AuditorContractError) as caught:
        audit(pooled)

    assert caught.value.code == "METHOD_POOLED"
    assert caught.value.context["strongest_stratum"] == "EMPIRICALLY_TESTED"


def test_the_method_auditor_must_declare_its_strata() -> None:
    unstratified = panel(
        **{Auditor.METHOD.value: verdict(Auditor.METHOD.value, "EMPIRICALLY_TESTED")}
    )

    with pytest.raises(AuditorContractError) as caught:
        audit(unstratified)

    assert caught.value.code == "METHOD_STRATA_MISSING"


def test_only_the_method_auditor_stratifies() -> None:
    stratified_scope = panel(
        **{
            Auditor.SCOPE.value: verdict(
                Auditor.SCOPE.value, "EMPIRICALLY_TESTED", strata={"field": "CANDIDATE"}
            )
        }
    )

    with pytest.raises(AuditorContractError) as caught:
        audit(stratified_scope)

    assert caught.value.code == "STRATA_UNEXPECTED"


def test_a_single_stratum_is_still_reported_explicitly() -> None:
    single = panel(
        **{
            Auditor.METHOD.value: verdict(
                Auditor.METHOD.value,
                "EMPIRICALLY_TESTED",
                strata={"randomized": "EMPIRICALLY_TESTED"},
            )
        }
    )

    record = audit(single).payload

    assert record["stratification"]["stratum_count"] == 1
    assert record["combined_ceiling"] == "EMPIRICALLY_TESTED"


def test_every_auditor_must_return_a_verdict() -> None:
    with pytest.raises(AuditorContractError) as caught:
        audit(panel()[:3])

    assert caught.value.code == "AUDIT_INCOMPLETE"
    assert len(caught.value.context["auditors"]) == 1


def test_a_duplicated_auditor_is_refused() -> None:
    with pytest.raises(AuditorContractError) as caught:
        audit([*panel(), verdict(Auditor.SCOPE.value, "CANDIDATE")])

    assert caught.value.code == "AUDITOR_DUPLICATED"


def test_an_unknown_auditor_is_refused() -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(ROOT, verdict("vibes_auditor", "CANDIDATE"))

    assert caught.value.code == "AUDITOR_UNKNOWN"
    assert sorted(AUDITORS) == [
        "causal_auditor",
        "method_auditor",
        "novelty_examiner",
        "scope_auditor",
    ]


def test_a_finding_must_carry_a_canonical_reason_code() -> None:
    with pytest.raises(AuditorContractError) as caught:
        validate_verdict(
            ROOT,
            verdict(
                Auditor.SCOPE.value,
                "CANDIDATE",
                findings=[
                    {"code": "seems_off", "evidence_ids": [], "statement": "hmm"}
                ],
            ),
        )

    assert caught.value.code == "FINDING_CODE_INVALID"


def test_combined_ceiling_is_callable_on_its_own() -> None:
    verdicts = [
        validate_verdict(ROOT, entry, index) for index, entry in enumerate(panel())
    ]

    ceiling, veto = combined_ceiling(ROOT, verdicts)

    assert ceiling == "EMPIRICALLY_TESTED"
    assert veto["floor_applied"] is False


def test_a_sealed_audit_cannot_have_its_ceiling_raised() -> None:
    from .contracts import _hash_excluding

    payload = audit().payload
    payload["combined_ceiling"] = "REPLICATED"
    payload["audit_hash"] = _hash_excluding(payload, "audit_hash")

    with pytest.raises(AuditorContractError) as caught:
        validate_audit(ROOT, payload)

    assert caught.value.code == "CEILING_MISMATCH"


def test_a_sealed_audit_cannot_be_relabelled_as_pooled() -> None:
    from .contracts import _hash_excluding

    payload = audit().payload
    payload["stratification"]["pooled"] = True
    payload["audit_hash"] = _hash_excluding(payload, "audit_hash")

    with pytest.raises(AuditorContractError) as caught:
        validate_audit(ROOT, payload)

    assert caught.value.code == "METHOD_POOLED"


def test_a_tampered_audit_is_rejected() -> None:
    payload = audit().payload
    payload["subject_id"] = "HYP-other"

    with pytest.raises(AuditorContractError) as caught:
        validate_audit(ROOT, payload)

    assert caught.value.code == "AUDIT_HASH_MISMATCH"


def test_the_audit_is_deterministic_and_content_addressed() -> None:
    first = audit()
    second = audit()

    assert first.canonical_bytes == second.canonical_bytes
    assert first.payload["audit_id"].startswith("PA-")
