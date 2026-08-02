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


REQUEST_ID = "REQ-I01-NO-REPEAT"
REVISION = 3


def missing_scope(identifier: str = "N-SCOPE") -> InterviewNeed:
    return InterviewNeed(
        need_id=identifier,
        rule=InterviewRule.MISSING_SCOPE,
        dimension=InterviewDimension.SCOPE,
        criticality=NeedCriticality.DECISION_CRITICAL,
        decision_impact="scope changes the admissible evidence and conclusion",
    )


def scope_question_id(revision: int = REVISION) -> str:
    return question_id_for(
        REQUEST_ID,
        revision,
        QuestionTargetType.DIMENSION,
        InterviewDimension.SCOPE.value,
    )


def prior_scope(
    state: PriorQuestionState,
    *,
    revision: int = REVISION,
) -> PriorQuestionRecord:
    return PriorQuestionRecord(
        question_id=scope_question_id(revision),
        target_type=QuestionTargetType.DIMENSION,
        target_id=InterviewDimension.SCOPE.value,
        state=state,
        answer_artifact_id="HD-I01-SCOPE"
        if state is PriorQuestionState.ANSWERED
        else None,
        blocker_id="BLOCK-I01-SCOPE"
        if state is PriorQuestionState.ACCEPTED_AS_BLOCKER
        else None,
    )


def test_no_repeat_question_test_known_fact_is_not_reasked() -> None:
    plan = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(missing_scope(),),
        known_facts=(KnownFact("FACT-SCOPE", InterviewDimension.SCOPE),),
    )

    assert plan.readiness is InterviewReadiness.READY
    assert plan.questions == ()


def test_no_repeat_question_test_open_prior_question_is_pending_not_reemitted() -> None:
    history = prior_scope(PriorQuestionState.ASKED)
    plan = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(missing_scope(),),
        prior_questions=(history,),
    )

    assert plan.readiness is InterviewReadiness.NEEDS_INPUT
    assert plan.questions == ()
    assert plan.suppressed_question_ids == (history.question_id,)
    assert plan.pending_question_ids == (history.question_id,)


def test_no_repeat_question_test_answered_prior_question_resolves_dimension() -> None:
    history = prior_scope(PriorQuestionState.ANSWERED)
    plan = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(missing_scope(),),
        prior_questions=(history,),
    )

    assert plan.readiness is InterviewReadiness.READY
    assert plan.questions == ()
    assert plan.suppressed_question_ids == ()


def test_no_repeat_question_test_prior_blocker_is_sticky_for_same_revision() -> None:
    history = prior_scope(PriorQuestionState.ACCEPTED_AS_BLOCKER)
    plan = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(missing_scope(),),
        prior_questions=(history,),
    )

    assert plan.readiness is InterviewReadiness.BLOCKED
    assert plan.questions == ()
    assert plan.blocker_ids == ("BLOCK-I01-SCOPE",)


def test_no_repeat_question_test_duplicate_needs_share_one_stable_question() -> None:
    plan = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(
            missing_scope("N-SCOPE-B"),
            InterviewNeed(
                need_id="N-SCOPE-A",
                rule=InterviewRule.AMBIGUOUS_SIGNAL,
                dimension=InterviewDimension.SCOPE,
                criticality=NeedCriticality.DECISION_CRITICAL,
                decision_impact="ambiguous scope changes the decision",
            ),
        ),
    )

    assert len(plan.questions) == 1
    assert plan.questions[0].question_id == scope_question_id()
    assert plan.questions[0].need_ids == ("N-SCOPE-A", "N-SCOPE-B")
    assert plan.questions[0].rule_ids == (
        "I01_AMBIGUOUS_SIGNAL",
        "I04_MISSING_SCOPE",
    )


def test_no_repeat_question_test_same_revision_replay_is_identical() -> None:
    arguments = {
        "request_id": REQUEST_ID,
        "request_revision": REVISION,
        "needs": (missing_scope(),),
    }
    assert build_interview_plan(**arguments) == build_interview_plan(**arguments)


def test_no_repeat_question_test_new_revision_has_new_question_identity() -> None:
    first = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(missing_scope(),),
    )
    revised = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION + 1,
        needs=(missing_scope(),),
    )

    assert first.questions[0].question_id != revised.questions[0].question_id


def test_no_repeat_question_test_forged_prior_question_id_fails_closed() -> None:
    forged = PriorQuestionRecord(
        question_id="IQ-" + "0" * 64,
        target_type=QuestionTargetType.DIMENSION,
        target_id=InterviewDimension.SCOPE.value,
        state=PriorQuestionState.ASKED,
    )
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id=REQUEST_ID,
            request_revision=REVISION,
            needs=(missing_scope(),),
            prior_questions=(forged,),
        )

    assert raised.value.code == "PRIOR_QUESTION_ID_MISMATCH"


def test_no_repeat_question_test_missing_contradiction_target_fails_closed() -> None:
    target_id = "C-NOT-IN-REQUEST"
    prior = PriorQuestionRecord(
        question_id=question_id_for(
            REQUEST_ID,
            REVISION,
            QuestionTargetType.CONTRADICTION,
            target_id,
        ),
        target_type=QuestionTargetType.CONTRADICTION,
        target_id=target_id,
        state=PriorQuestionState.ASKED,
    )
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id=REQUEST_ID,
            request_revision=REVISION,
            needs=(),
            prior_questions=(prior,),
        )

    assert raised.value.code == "PRIOR_QUESTION_TARGET_INVALID"


def test_no_repeat_question_test_duplicate_target_history_fails_closed() -> None:
    asked = prior_scope(PriorQuestionState.ASKED)
    answered = prior_scope(PriorQuestionState.ANSWERED)
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id=REQUEST_ID,
            request_revision=REVISION,
            needs=(missing_scope(),),
            prior_questions=(asked, answered),
        )

    assert raised.value.code == "INTERVIEW_INPUT_DUPLICATE"


def test_no_repeat_question_test_unresolved_answered_conflict_stays_pending() -> None:
    conflict = ContradictionRecord(
        contradiction_id="C-CONFLICT",
        dimension=InterviewDimension.SCOPE,
        statement_ids=("STMT-A", "STMT-B"),
        severity=ContradictionSeverity.CRITICAL,
        disposition=ContradictionDisposition.UNRESOLVED,
    )
    question_id = question_id_for(
        REQUEST_ID,
        REVISION,
        QuestionTargetType.CONTRADICTION,
        conflict.contradiction_id,
    )
    answered = PriorQuestionRecord(
        question_id=question_id,
        target_type=QuestionTargetType.CONTRADICTION,
        target_id=conflict.contradiction_id,
        state=PriorQuestionState.ANSWERED,
        answer_artifact_id="HD-I01-CONFLICT-ANSWER",
    )
    plan = build_interview_plan(
        request_id=REQUEST_ID,
        request_revision=REVISION,
        needs=(),
        contradictions=(conflict,),
        prior_questions=(answered,),
    )

    assert plan.questions == ()
    assert plan.readiness is InterviewReadiness.NEEDS_INPUT
    assert plan.pending_question_ids == (question_id,)


def test_no_repeat_question_test_contradiction_blocker_must_match_history() -> None:
    conflict = ContradictionRecord(
        contradiction_id="C-BLOCK",
        dimension=InterviewDimension.SCOPE,
        statement_ids=("STMT-A", "STMT-B"),
        severity=ContradictionSeverity.CRITICAL,
        disposition=ContradictionDisposition.UNRESOLVED,
    )
    history = PriorQuestionRecord(
        question_id=question_id_for(
            REQUEST_ID,
            REVISION,
            QuestionTargetType.CONTRADICTION,
            conflict.contradiction_id,
        ),
        target_type=QuestionTargetType.CONTRADICTION,
        target_id=conflict.contradiction_id,
        state=PriorQuestionState.ACCEPTED_AS_BLOCKER,
        blocker_id="BLOCK-I01-CONFLICT",
    )
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id=REQUEST_ID,
            request_revision=REVISION,
            needs=(),
            contradictions=(conflict,),
            prior_questions=(history,),
        )

    assert raised.value.code == "CONTRADICTION_BLOCKER_MISMATCH"


def test_no_repeat_question_test_noncritical_blocker_must_match_history() -> None:
    conflict = ContradictionRecord(
        contradiction_id="C-MINOR-BLOCK",
        dimension=InterviewDimension.SCOPE,
        statement_ids=("STMT-A", "STMT-B"),
        severity=ContradictionSeverity.NON_CRITICAL,
        disposition=ContradictionDisposition.UNRESOLVED,
    )
    history = PriorQuestionRecord(
        question_id=question_id_for(
            REQUEST_ID,
            REVISION,
            QuestionTargetType.CONTRADICTION,
            conflict.contradiction_id,
        ),
        target_type=QuestionTargetType.CONTRADICTION,
        target_id=conflict.contradiction_id,
        state=PriorQuestionState.ACCEPTED_AS_BLOCKER,
        blocker_id="BLOCK-I01-MINOR-CONFLICT",
    )

    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id=REQUEST_ID,
            request_revision=REVISION,
            needs=(),
            contradictions=(conflict,),
            prior_questions=(history,),
        )

    assert raised.value.code == "CONTRADICTION_BLOCKER_MISMATCH"


@pytest.mark.parametrize("bad_revision", [-1, True, 1.5, "1"])
def test_no_repeat_question_test_invalid_revision_fails_closed(
    bad_revision: object,
) -> None:
    with pytest.raises(InterviewContractError) as raised:
        build_interview_plan(
            request_id=REQUEST_ID,
            request_revision=bad_revision,  # type: ignore[arg-type]
            needs=(missing_scope(),),
        )

    assert raised.value.code == "INTERVIEW_INPUT_INVALID"
