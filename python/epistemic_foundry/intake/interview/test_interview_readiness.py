from __future__ import annotations

import pytest

from .engine import (
    ContradictionDisposition,
    ContradictionRecord,
    ContradictionSeverity,
    InterviewContractError,
    InterviewDimension,
    InterviewNeed,
    InterviewReadiness,
    InterviewRule,
    KnownFact,
    NeedCriticality,
    PriorQuestionRecord,
    PriorQuestionState,
    QuestionTargetType,
    build_interview_plan,
    question_id_for,
)


def need(
    identifier: str,
    rule: InterviewRule,
    dimension: InterviewDimension,
    *,
    criticality: NeedCriticality = NeedCriticality.DECISION_CRITICAL,
) -> InterviewNeed:
    return InterviewNeed(
        need_id=identifier,
        rule=rule,
        dimension=dimension,
        criticality=criticality,
        decision_impact=f"decision impact for {identifier}",
    )


def contradiction(
    identifier: str,
    *,
    severity: ContradictionSeverity = ContradictionSeverity.CRITICAL,
    disposition: ContradictionDisposition = ContradictionDisposition.UNRESOLVED,
    resolution_artifact_id: str | None = None,
    blocker_id: str | None = None,
) -> ContradictionRecord:
    return ContradictionRecord(
        contradiction_id=identifier,
        dimension=InterviewDimension.SCOPE,
        statement_ids=(f"STMT-{identifier}-B", f"STMT-{identifier}-A"),
        severity=severity,
        disposition=disposition,
        resolution_artifact_id=resolution_artifact_id,
        blocker_id=blocker_id,
    )


def test_interview_readiness_test_complete_contract_is_ready() -> None:
    plan = build_interview_plan(
        request_id="REQ-I01-READY",
        request_revision=1,
        needs=(
            need(
                "N-GOAL",
                InterviewRule.MISSING_GOAL_OR_DECISION,
                InterviewDimension.GOAL_AND_DECISION,
            ),
            need(
                "N-SCOPE",
                InterviewRule.MISSING_SCOPE,
                InterviewDimension.SCOPE,
            ),
        ),
        known_facts=(
            KnownFact("FACT-GOAL", InterviewDimension.GOAL_AND_DECISION),
            KnownFact("FACT-SCOPE", InterviewDimension.SCOPE),
        ),
        contradictions=(
            contradiction(
                "C-RESOLVED",
                disposition=ContradictionDisposition.RESOLVED,
                resolution_artifact_id="HD-I01-C-RESOLVED",
            ),
        ),
    )

    assert plan.readiness is InterviewReadiness.READY
    assert plan.questions == ()
    assert plan.readiness_reasons == ("READY:DECISION_CONTRACT_COMPLETE",)
    assert plan.recorded_contradictions[0].statement_ids == (
        "STMT-C-RESOLVED-A",
        "STMT-C-RESOLVED-B",
    )


def test_interview_readiness_test_asks_only_missing_decision_critical_dimensions() -> (
    None
):
    plan = build_interview_plan(
        request_id="REQ-I01-MISSING",
        request_revision=0,
        needs=(
            need(
                "N-SCOPE",
                InterviewRule.MISSING_SCOPE,
                InterviewDimension.SCOPE,
            ),
            need(
                "N-OUTPUT",
                InterviewRule.AMBIGUOUS_SIGNAL,
                InterviewDimension.OUTPUT_FORM,
                criticality=NeedCriticality.NON_CRITICAL,
            ),
            need(
                "N-GOAL",
                InterviewRule.MISSING_GOAL_OR_DECISION,
                InterviewDimension.GOAL_AND_DECISION,
            ),
        ),
        known_facts=(KnownFact("FACT-GOAL", InterviewDimension.GOAL_AND_DECISION),),
    )

    assert plan.readiness is InterviewReadiness.NEEDS_INPUT
    assert [question.target_id for question in plan.questions] == ["SCOPE"]
    assert plan.deferred_noncritical_need_ids == ("N-OUTPUT",)
    assert "population or system" in plan.questions[0].prompt


def test_interview_readiness_test_records_and_routes_critical_contradiction() -> None:
    conflict = contradiction("C-SCOPE")
    plan = build_interview_plan(
        request_id="REQ-I01-CONFLICT",
        request_revision=4,
        needs=(
            need(
                "N-CONFLICT",
                InterviewRule.CONFLICTING_REQUIREMENTS,
                InterviewDimension.REQUIREMENT_CONFLICT,
            ),
        ),
        contradictions=(conflict,),
    )

    assert plan.readiness is InterviewReadiness.NEEDS_INPUT
    assert plan.recorded_contradictions == (conflict,)
    assert len(plan.questions) == 1
    assert plan.questions[0].target_id == "C-SCOPE"
    assert plan.questions[0].rule_ids == ("I02_CONFLICTING_REQUIREMENTS",)


def test_interview_readiness_test_accepted_contradiction_is_explicit_blocker() -> None:
    plan = build_interview_plan(
        request_id="REQ-I01-BLOCKED",
        request_revision=2,
        needs=(),
        contradictions=(
            contradiction(
                "C-BLOCK",
                disposition=ContradictionDisposition.ACCEPTED_AS_BLOCKER,
                blocker_id="BLOCK-I01-C-BLOCK",
            ),
        ),
    )

    assert plan.readiness is InterviewReadiness.BLOCKED
    assert plan.questions == ()
    assert plan.blocker_ids == ("BLOCK-I01-C-BLOCK",)
    assert plan.readiness_reasons == ("BLOCKER:BLOCK-I01-C-BLOCK",)


def test_interview_readiness_test_noncritical_contradiction_is_recorded_not_gated() -> (
    None
):
    minor = contradiction("C-MINOR", severity=ContradictionSeverity.NON_CRITICAL)
    plan = build_interview_plan(
        request_id="REQ-I01-MINOR",
        request_revision=0,
        needs=(),
        contradictions=(minor,),
    )

    assert plan.readiness is InterviewReadiness.READY
    assert plan.recorded_contradictions == (minor,)
    assert plan.questions == ()


def test_interview_readiness_test_explicit_blocker_is_never_silently_downgraded() -> (
    None
):
    plan = build_interview_plan(
        request_id="REQ-I01-MINOR-BLOCKER",
        request_revision=0,
        needs=(),
        contradictions=(
            contradiction(
                "C-MINOR-BLOCKER",
                severity=ContradictionSeverity.NON_CRITICAL,
                disposition=ContradictionDisposition.ACCEPTED_AS_BLOCKER,
                blocker_id="BLOCK-I01-MINOR",
            ),
        ),
    )

    assert plan.readiness is InterviewReadiness.BLOCKED
    assert plan.blocker_ids == ("BLOCK-I01-MINOR",)
    assert plan.questions == ()


def test_interview_readiness_test_conflict_need_requires_recorded_critical_conflict() -> (
    None
):
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id="REQ-I01-NO-CONFLICT",
            request_revision=0,
            needs=(
                need(
                    "N-CONFLICT",
                    InterviewRule.CONFLICTING_REQUIREMENTS,
                    InterviewDimension.REQUIREMENT_CONFLICT,
                ),
            ),
        )

    assert raised.value.code == "CONTRADICTION_EVIDENCE_REQUIRED"


def test_interview_readiness_test_rule_dimension_mismatch_fails_closed() -> None:
    with pytest.raises(InterviewContractError) as raised:
        need(
            "N-WRONG",
            InterviewRule.MISSING_SCOPE,
            InterviewDimension.GOAL_AND_DECISION,
        )

    assert raised.value.code == "INTERVIEW_RULE_DIMENSION_MISMATCH"


def test_interview_readiness_test_raw_enum_alias_fails_closed() -> None:
    with pytest.raises(InterviewContractError) as raised:
        InterviewNeed(
            need_id="N-RAW-ENUM",
            rule="I04_MISSING_SCOPE",  # type: ignore[arg-type]
            dimension=InterviewDimension.SCOPE,
            criticality=NeedCriticality.DECISION_CRITICAL,
            decision_impact="scope changes the decision",
        )

    assert raised.value.code == "INTERVIEW_INPUT_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("needs", []),
        ("known_facts", []),
        ("contradictions", []),
        ("prior_questions", []),
    ],
)
def test_interview_readiness_test_mutable_record_collections_fail_closed(
    field: str,
    value: list[object],
) -> None:
    arguments: dict[str, object] = {
        "request_id": "REQ-I01-MUTABLE",
        "request_revision": 0,
        "needs": (),
    }
    arguments[field] = value

    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(**arguments)  # type: ignore[arg-type]

    assert raised.value.code == "INTERVIEW_INPUT_INVALID"


def test_interview_readiness_test_duplicate_identifiers_fail_closed() -> None:
    duplicate = need(
        "N-DUPLICATE",
        InterviewRule.MISSING_SCOPE,
        InterviewDimension.SCOPE,
    )
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id="REQ-I01-DUPLICATE",
            request_revision=0,
            needs=(duplicate, duplicate),
        )

    assert raised.value.code == "INTERVIEW_INPUT_DUPLICATE"


def test_interview_readiness_test_unknown_prior_dimension_fails_closed() -> None:
    prior = PriorQuestionRecord(
        question_id=question_id_for(
            "REQ-I01-UNKNOWN-TARGET",
            0,
            QuestionTargetType.DIMENSION,
            "UNREGISTERED_DIMENSION",
        ),
        target_type=QuestionTargetType.DIMENSION,
        target_id="UNREGISTERED_DIMENSION",
        state=PriorQuestionState.ASKED,
    )
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id="REQ-I01-UNKNOWN-TARGET",
            request_revision=0,
            needs=(),
            prior_questions=(prior,),
        )

    assert raised.value.code == "PRIOR_QUESTION_TARGET_INVALID"


@pytest.mark.parametrize(
    ("disposition", "resolution", "blocker"),
    [
        (ContradictionDisposition.UNRESOLVED, "HD-INVALID", None),
        (ContradictionDisposition.RESOLVED, None, None),
        (ContradictionDisposition.ACCEPTED_AS_BLOCKER, None, None),
    ],
)
def test_interview_readiness_test_invalid_disposition_linkage_fails_closed(
    disposition: ContradictionDisposition,
    resolution: str | None,
    blocker: str | None,
) -> None:
    with pytest.raises(InterviewContractError) as raised:
        contradiction(
            "C-INVALID",
            disposition=disposition,
            resolution_artifact_id=resolution,
            blocker_id=blocker,
        )

    assert raised.value.code == "CONTRADICTION_DISPOSITION_INVALID"


def test_interview_readiness_test_question_order_is_canonical_not_input_order() -> None:
    ordered_needs = (
        need(
            "N-NOVELTY",
            InterviewRule.MISSING_NOVELTY_BOUNDARY,
            InterviewDimension.TIME_AND_NOVELTY,
        ),
        need(
            "N-GOAL",
            InterviewRule.MISSING_GOAL_OR_DECISION,
            InterviewDimension.GOAL_AND_DECISION,
        ),
        need(
            "N-SCOPE",
            InterviewRule.MISSING_SCOPE,
            InterviewDimension.SCOPE,
        ),
    )
    first = build_interview_plan(
        request_id="REQ-I01-ORDER",
        request_revision=7,
        needs=ordered_needs,
    )
    second = build_interview_plan(
        request_id="REQ-I01-ORDER",
        request_revision=7,
        needs=tuple(reversed(ordered_needs)),
    )

    assert first.questions == second.questions
    assert [question.target_id for question in first.questions] == [
        "GOAL_AND_DECISION",
        "SCOPE",
        "TIME_AND_NOVELTY",
    ]
