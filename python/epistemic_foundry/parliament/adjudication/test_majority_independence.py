"""majority_independence_test — a majority cannot promote.

Exit criterion under test: "majority cannot promote".  Agreement among briefs
is recorded and carries no weight: the recommendation is bounded above by the
deterministic P02 ceiling, a sustained veto or an unanswered challenge forces
BLOCK, and an attempt to override a deterministic gate is refused.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .contracts import (
    BLOCK,
    AdjudicationError,
    majority_verdict,
    promotion_bound,
    recommendation_rank,
    recommendations,
    seal_judgment,
    seal_record,
    validate_judgment,
    verdicts,
)

ROOT = Path(__file__).resolve().parents[4]
CREATED_AT = "2026-08-01T18:00:00Z"
RUN = "RUN-1"
HYPOTHESIS = "HYP-1"
JUDGE = "principal-judge"
ATTESTOR = "principal-attestor"


def adjudication(
    *,
    recommendation: str = "EMPIRICALLY_TESTED",
    verdict: str = "SUPPORTED",
    unresolved: list[str] | None = None,
    minority_ids: list[str] | None = None,
    override: bool = False,
) -> dict[str, object]:
    return seal_record(
        {
            "adjudication_hash": "sha256:" + "0" * 64,
            "adjudication_id": "ADJ-1",
            "brief_ids": ["CB-defender", "CB-prosecutor"],
            "created_at": CREATED_AT,
            "cross_examination_ids": ["CX-1"],
            "deterministic_gate_override_attempted": override,
            "gate_decision_ids": ["GD-1"],
            "hypothesis_id": HYPOTHESIS,
            "minority_report_ids": ["MR-1"] if minority_ids is None else minority_ids,
            "promotion_recommendation": recommendation,
            "rationale": "the support survives cross-examination within its scope",
            "run_id": RUN,
            "scope_narrowing": "greenhouse only",
            "strongest_counterevidence_id": "EVN-counter",
            "strongest_support_id": "EVN-support",
            "unresolved_issue_ids": [] if unresolved is None else list(unresolved),
            "verdict": verdict,
        },
        "adjudication_hash",
    )


def attestation(
    pack_id: str,
    *,
    attestor: str = ATTESTOR,
    status: str = "PASS",
    inputs: list[str] | None = None,
    subject: str = "ADJ-1",
    checks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return seal_record(
        {
            "attestation_hash": "sha256:" + "0" * 64,
            "attestation_id": "ATT-1",
            "attestor_id": attestor,
            "attestor_type": "model",
            "checks": (
                [{"check_id": "C1", "reason": "hashes recomputed", "status": "PASS"}]
                if checks is None
                else checks
            ),
            "created_at": CREATED_AT,
            "independence_statement": "no authorship of the adjudication under review",
            "input_artifact_ids": [pack_id] if inputs is None else list(inputs),
            "model_or_identity_version": "attestor-4.0.0",
            "overall_status": status,
            "run_id": RUN,
            "signature": "sig:deadbeef",
            "subject_artifact_id": subject,
        },
        "attestation_hash",
    )


def brief_verdicts(*values: str) -> list[dict[str, object]]:
    return [{"verdict_candidate": value} for value in values]


def seal(
    *,
    adj: dict[str, object] | None = None,
    ceiling: str = "EMPIRICALLY_TESTED",
    veto: list[str] | None = None,
    open_ids: list[str] | None = None,
    dissent: str | None = "MR-1",
    briefs: list[dict[str, object]] | None = None,
    att: dict[str, object] | None = None,
    judge: str = JUDGE,
):
    record = adj if adj is not None else adjudication()
    from .contracts import build_attestation_pack

    pack = build_attestation_pack(
        ROOT,
        record,
        audit_id="PA-1",
        combined_ceiling=ceiling,
        created_at=CREATED_AT,
        cross_exam_round_id="CX-round-1",
        open_challenge_ids=[] if open_ids is None else open_ids,
        strongest_dissent_id=dissent,
        veto_sustained_by=[] if veto is None else veto,
    ).payload
    return seal_judgment(
        ROOT,
        record,
        att if att is not None else attestation(pack["attestation_pack_id"]),
        briefs if briefs is not None else brief_verdicts("SUPPORTED", "CONDITIONAL"),
        audit_id="PA-1",
        combined_ceiling=ceiling,
        created_at=CREATED_AT,
        cross_exam_round_id="CX-round-1",
        judge_id=judge,
        open_challenge_ids=[] if open_ids is None else open_ids,
        strongest_dissent_id=dissent,
        veto_sustained_by=[] if veto is None else veto,
    )


def test_the_vocabularies_are_read_from_the_declaring_schema() -> None:
    assert verdicts(ROOT)[0] == "ENTAILED"
    assert recommendations(ROOT)[0] == BLOCK
    assert recommendations(ROOT)[-1] == "REPLICATED"
    assert recommendation_rank(ROOT, BLOCK) == 0


def test_an_unknown_recommendation_fails_closed() -> None:
    with pytest.raises(AdjudicationError) as caught:
        recommendation_rank(ROOT, "PROVEN")

    assert caught.value.code == "RECOMMENDATION_UNKNOWN"


def test_a_recommendation_within_the_ceiling_seals() -> None:
    record = seal().payload

    assert record["adjudication"]["promotion_recommendation"] == "EMPIRICALLY_TESTED"
    assert record["promotion_bound"]["maximum_recommendation"] == "EMPIRICALLY_TESTED"
    assert record["gate_id"].startswith("PJ-")


def test_a_recommendation_above_the_ceiling_is_refused() -> None:
    with pytest.raises(AdjudicationError) as caught:
        seal(adj=adjudication(recommendation="REPLICATED"))

    assert caught.value.code == "MAJORITY_CANNOT_PROMOTE"
    assert caught.value.context["maximum"] == "EMPIRICALLY_TESTED"


def test_a_unanimous_majority_cannot_lift_the_ceiling() -> None:
    with pytest.raises(AdjudicationError) as caught:
        seal(
            adj=adjudication(recommendation="REPLICATED", verdict="ENTAILED"),
            briefs=brief_verdicts("ENTAILED", "ENTAILED", "ENTAILED", "ENTAILED"),
        )

    assert caught.value.code == "MAJORITY_CANNOT_PROMOTE"


def test_the_majority_is_recorded_but_never_load_bearing() -> None:
    record = seal(briefs=brief_verdicts("ENTAILED", "ENTAILED", "CONDITIONAL")).payload

    assert record["majority"]["majority_verdict"] == "ENTAILED"
    assert record["majority"]["brief_count"] == 3
    assert record["majority"]["is_unanimous"] is False
    assert record["majority"]["majority_influenced_recommendation"] is False


def test_a_unanimous_panel_is_reported_as_such() -> None:
    summary = majority_verdict(ROOT, brief_verdicts("SUPPORTED", "SUPPORTED"))

    assert summary["is_unanimous"] is True
    assert summary["majority_verdict"] == "SUPPORTED"


def test_a_tied_panel_has_no_majority_verdict() -> None:
    summary = majority_verdict(ROOT, brief_verdicts("SUPPORTED", "CONTRADICTED"))

    assert summary["majority_verdict"] is None
    assert summary["verdict_counts"] == {"CONTRADICTED": 1, "SUPPORTED": 1}


def test_a_non_canonical_brief_verdict_is_refused() -> None:
    with pytest.raises(AdjudicationError) as caught:
        majority_verdict(ROOT, brief_verdicts("PROBABLY"))

    assert caught.value.code == "VERDICT_INVALID"


def test_a_sustained_veto_forces_block() -> None:
    bound = promotion_bound(
        ROOT,
        combined_ceiling="EMPIRICALLY_TESTED",
        open_challenge_ids=[],
        veto_sustained_by=["method_auditor"],
    )

    assert bound["maximum_recommendation"] == BLOCK
    assert bound["block_reasons"] == ["a method veto is sustained"]


def test_an_unanswered_challenge_forces_block() -> None:
    bound = promotion_bound(
        ROOT,
        combined_ceiling="EMPIRICALLY_TESTED",
        open_challenge_ids=["CX-9"],
        veto_sustained_by=[],
    )

    assert bound["maximum_recommendation"] == BLOCK
    assert bound["block_reasons"] == ["a cross-examination is unanswered"]


def test_a_vetoed_run_cannot_recommend_anything_above_block() -> None:
    with pytest.raises(AdjudicationError) as caught:
        seal(adj=adjudication(recommendation="INBOX"), veto=["method_auditor"])

    assert caught.value.code == "MAJORITY_CANNOT_PROMOTE"
    assert caught.value.context["reasons"] == ["a method veto is sustained"]


def test_a_vetoed_run_may_still_seal_when_it_blocks() -> None:
    record = seal(
        adj=adjudication(recommendation=BLOCK), veto=["method_auditor"]
    ).payload

    assert record["adjudication"]["promotion_recommendation"] == BLOCK
    assert record["promotion_bound"]["veto_sustained_by"] == ["method_auditor"]


def test_an_unanswered_challenge_must_appear_as_an_unresolved_issue() -> None:
    with pytest.raises(AdjudicationError) as caught:
        seal(adj=adjudication(recommendation=BLOCK), open_ids=["CX-9"])

    assert caught.value.code == "UNRESOLVED_ISSUE_DROPPED"
    assert caught.value.context["cross_exam_ids"] == ["CX-9"]


def test_an_acknowledged_unanswered_challenge_seals_at_block() -> None:
    record = seal(
        adj=adjudication(recommendation=BLOCK, unresolved=["CX-9"]),
        open_ids=["CX-9"],
    ).payload

    assert record["adjudication"]["unresolved_issue_ids"] == ["CX-9"]
    assert record["promotion_bound"]["maximum_recommendation"] == BLOCK


def test_the_strongest_dissent_must_be_cited() -> None:
    with pytest.raises(AdjudicationError) as caught:
        seal(adj=adjudication(minority_ids=["MR-other"]), dissent="MR-1")

    assert caught.value.code == "DISSENT_UNCITED"


def test_a_gate_override_attempt_is_refused() -> None:
    with pytest.raises(AdjudicationError) as caught:
        seal(adj=adjudication(override=True))

    assert caught.value.code == "GATE_OVERRIDE_ATTEMPTED"


def test_a_sealed_gate_cannot_have_its_recommendation_raised() -> None:
    from .contracts import _hash_excluding

    payload = seal().payload
    payload["adjudication"]["promotion_recommendation"] = "REPLICATED"
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(AdjudicationError) as caught:
        validate_judgment(ROOT, payload)

    assert caught.value.code == "MAJORITY_CANNOT_PROMOTE"


def test_a_sealed_gate_cannot_declare_the_majority_load_bearing() -> None:
    from .contracts import _hash_excluding

    payload = seal().payload
    payload["majority"]["majority_influenced_recommendation"] = True
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(AdjudicationError) as caught:
        validate_judgment(ROOT, payload)

    assert caught.value.code == "MAJORITY_CANNOT_PROMOTE"


def test_a_sealed_gate_cannot_soften_a_veto_bound() -> None:
    from .contracts import _hash_excluding

    payload = seal(
        adj=adjudication(recommendation=BLOCK), veto=["method_auditor"]
    ).payload
    payload["promotion_bound"]["maximum_recommendation"] = "REPLICATED"
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(AdjudicationError) as caught:
        validate_judgment(ROOT, payload)

    assert caught.value.code == "PROMOTION_BOUND_MISMATCH"


def test_a_tampered_gate_is_rejected() -> None:
    payload = seal().payload
    payload["run_id"] = "RUN-other"

    with pytest.raises(AdjudicationError) as caught:
        validate_judgment(ROOT, payload)

    assert caught.value.code == "GATE_HASH_MISMATCH"


def test_the_gate_is_deterministic_and_content_addressed() -> None:
    first = seal()
    second = seal()

    assert first.canonical_bytes == second.canonical_bytes
    assert (
        validate_judgment(ROOT, first.payload).canonical_bytes == first.canonical_bytes
    )
