"""Deterministic I01 bounded-interview planning.

The upstream detector may propose missing-contract needs, but it does not own
question selection or readiness.  This module validates a closed vocabulary,
asks only decision-critical questions, preserves every supplied contradiction,
and prevents the same question from being emitted twice for one immutable
request revision.

The types here are a component-local execution contract.  They do not create a
new canonical JSON Schema or pretend that a ``ResearchBrief`` has already been
standardized by C-phase contract authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final, Iterable


INTERVIEW_ENGINE_VERSION: Final = "4.0.0-i01.1"


class InterviewContractError(ValueError):
    """Typed fail-closed error at the I01 component boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> None:
    raise InterviewContractError(code, message, details)


class InterviewRule(str, Enum):
    AMBIGUOUS_SIGNAL = "I01_AMBIGUOUS_SIGNAL"
    CONFLICTING_REQUIREMENTS = "I02_CONFLICTING_REQUIREMENTS"
    MISSING_GOAL_OR_DECISION = "I03_MISSING_GOAL_OR_DECISION"
    MISSING_SCOPE = "I04_MISSING_SCOPE"
    MISSING_FALSIFIER = "I05_MISSING_FALSIFIER"
    MISSING_AUTHORITY = "I06_MISSING_AUTHORITY"
    MISSING_HIGH_RISK_CONTRACT = "I07_MISSING_HIGH_RISK_CONTRACT"
    MISSING_NOVELTY_BOUNDARY = "I08_MISSING_NOVELTY_BOUNDARY"
    UNBOUNDED_COST = "I09_UNBOUNDED_COST"


class InterviewDimension(str, Enum):
    GOAL_AND_DECISION = "GOAL_AND_DECISION"
    CLAIM_AND_OVERCLAIM = "CLAIM_AND_OVERCLAIM"
    SCOPE = "SCOPE"
    SUCCESS_AND_FALSIFICATION = "SUCCESS_AND_FALSIFICATION"
    DATA_AUTHORITY_AND_LICENSING = "DATA_AUTHORITY_AND_LICENSING"
    TIME_AND_NOVELTY = "TIME_AND_NOVELTY"
    OUTPUT_FORM = "OUTPUT_FORM"
    PRIVACY_SAFETY_APPROVAL = "PRIVACY_SAFETY_APPROVAL"
    ONTOLOGY_AND_MEASUREMENT = "ONTOLOGY_AND_MEASUREMENT"
    BUDGET_AND_RESOURCES = "BUDGET_AND_RESOURCES"
    REQUIREMENT_CONFLICT = "REQUIREMENT_CONFLICT"


class NeedCriticality(str, Enum):
    DECISION_CRITICAL = "DECISION_CRITICAL"
    NON_CRITICAL = "NON_CRITICAL"


class ContradictionSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    NON_CRITICAL = "NON_CRITICAL"


class ContradictionDisposition(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    ACCEPTED_AS_BLOCKER = "ACCEPTED_AS_BLOCKER"


class QuestionTargetType(str, Enum):
    DIMENSION = "DIMENSION"
    CONTRADICTION = "CONTRADICTION"


class PriorQuestionState(str, Enum):
    ASKED = "ASKED"
    ANSWERED = "ANSWERED"
    ACCEPTED_AS_BLOCKER = "ACCEPTED_AS_BLOCKER"


class InterviewReadiness(str, Enum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"


RULE_ORDER: Final = tuple(InterviewRule)
DIMENSION_ORDER: Final = tuple(InterviewDimension)
_RULE_INDEX = MappingProxyType({value: index for index, value in enumerate(RULE_ORDER)})
_DIMENSION_INDEX = MappingProxyType(
    {value: index for index, value in enumerate(DIMENSION_ORDER)}
)


_ALLOWED_RULE_DIMENSIONS: Final = MappingProxyType(
    {
        InterviewRule.AMBIGUOUS_SIGNAL: frozenset(
            dimension
            for dimension in InterviewDimension
            if dimension is not InterviewDimension.REQUIREMENT_CONFLICT
        ),
        InterviewRule.CONFLICTING_REQUIREMENTS: frozenset(
            {InterviewDimension.REQUIREMENT_CONFLICT}
        ),
        InterviewRule.MISSING_GOAL_OR_DECISION: frozenset(
            {InterviewDimension.GOAL_AND_DECISION}
        ),
        InterviewRule.MISSING_SCOPE: frozenset({InterviewDimension.SCOPE}),
        InterviewRule.MISSING_FALSIFIER: frozenset(
            {InterviewDimension.SUCCESS_AND_FALSIFICATION}
        ),
        InterviewRule.MISSING_AUTHORITY: frozenset(
            {
                InterviewDimension.DATA_AUTHORITY_AND_LICENSING,
                InterviewDimension.PRIVACY_SAFETY_APPROVAL,
            }
        ),
        InterviewRule.MISSING_HIGH_RISK_CONTRACT: frozenset(
            {
                InterviewDimension.GOAL_AND_DECISION,
                InterviewDimension.SUCCESS_AND_FALSIFICATION,
                InterviewDimension.PRIVACY_SAFETY_APPROVAL,
                InterviewDimension.BUDGET_AND_RESOURCES,
            }
        ),
        InterviewRule.MISSING_NOVELTY_BOUNDARY: frozenset(
            {InterviewDimension.TIME_AND_NOVELTY}
        ),
        InterviewRule.UNBOUNDED_COST: frozenset(
            {InterviewDimension.BUDGET_AND_RESOURCES}
        ),
    }
)


_DIMENSION_PROMPTS: Final = MappingProxyType(
    {
        InterviewDimension.GOAL_AND_DECISION: (
            "What decision will this research inform, and what result would change "
            "that decision?"
        ),
        InterviewDimension.CLAIM_AND_OVERCLAIM: (
            "What exact claim may be evaluated, and which stronger interpretation "
            "must not be asserted?"
        ),
        InterviewDimension.SCOPE: (
            "Which population or system, conditions, jurisdiction, and time range are "
            "inside the decision scope?"
        ),
        InterviewDimension.SUCCESS_AND_FALSIFICATION: (
            "What observation counts as success, and what observation would falsify "
            "or materially revise the claim?"
        ),
        InterviewDimension.DATA_AUTHORITY_AND_LICENSING: (
            "Which corpus or data source is authoritative here, and what access or "
            "license limits apply?"
        ),
        InterviewDimension.TIME_AND_NOVELTY: (
            "What prior-art corpus, time boundary, external-search scope, claim level, "
            "and stop rule bound the novelty assessment?"
        ),
        InterviewDimension.OUTPUT_FORM: (
            "What output form is required, for whom, and what decision may it support?"
        ),
        InterviewDimension.PRIVACY_SAFETY_APPROVAL: (
            "Who owns the risk and approval decision, and what privacy, safety, "
            "consent, or release restrictions apply?"
        ),
        InterviewDimension.ONTOLOGY_AND_MEASUREMENT: (
            "Which construct definitions and measurement conventions are authoritative "
            "for this request?"
        ),
        InterviewDimension.BUDGET_AND_RESOURCES: (
            "What resource limit, material-cost threshold, and approver bound this work?"
        ),
    }
)


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value or "\x00" in value:
        _fail("INTERVIEW_INPUT_INVALID", f"{label} must be a non-empty NUL-free string")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise InterviewContractError(
            "INTERVIEW_INPUT_INVALID",
            f"{label} must contain only Unicode scalar values",
        ) from error
    return value


def _require_optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, label)


def _require_exact_enum(value: object, enum_type: type[Enum], label: str) -> None:
    if type(value) is not enum_type:
        _fail(
            "INTERVIEW_INPUT_INVALID",
            f"{label} must use the closed {enum_type.__name__} vocabulary",
        )


def _require_string_tuple(
    value: object, label: str, *, minimum: int = 0
) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) < minimum:
        _fail(
            "INTERVIEW_INPUT_INVALID",
            f"{label} must be a tuple with at least {minimum} entries",
        )
    normalized = tuple(
        _require_text(entry, f"{label}[{index}]") for index, entry in enumerate(value)
    )
    if len(set(normalized)) != len(normalized):
        _fail("INTERVIEW_INPUT_INVALID", f"{label} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class InterviewNeed:
    need_id: str
    rule: InterviewRule
    dimension: InterviewDimension
    criticality: NeedCriticality
    decision_impact: str

    def __post_init__(self) -> None:
        _require_text(self.need_id, "InterviewNeed.need_id")
        _require_exact_enum(self.rule, InterviewRule, "InterviewNeed.rule")
        _require_exact_enum(
            self.dimension, InterviewDimension, "InterviewNeed.dimension"
        )
        _require_exact_enum(
            self.criticality, NeedCriticality, "InterviewNeed.criticality"
        )
        _require_text(self.decision_impact, "InterviewNeed.decision_impact")
        if self.dimension not in _ALLOWED_RULE_DIMENSIONS[self.rule]:
            _fail(
                "INTERVIEW_RULE_DIMENSION_MISMATCH",
                "Interview need does not match the canonical rule-to-dimension boundary",
                {
                    "need_id": self.need_id,
                    "rule": self.rule.value,
                    "dimension": self.dimension.value,
                },
            )


@dataclass(frozen=True, slots=True)
class KnownFact:
    fact_id: str
    dimension: InterviewDimension

    def __post_init__(self) -> None:
        _require_text(self.fact_id, "KnownFact.fact_id")
        _require_exact_enum(self.dimension, InterviewDimension, "KnownFact.dimension")
        if self.dimension is InterviewDimension.REQUIREMENT_CONFLICT:
            _fail(
                "INTERVIEW_INPUT_INVALID",
                "requirement conflicts must be resolved through contradiction records",
            )


@dataclass(frozen=True, slots=True)
class ContradictionRecord:
    contradiction_id: str
    dimension: InterviewDimension
    statement_ids: tuple[str, ...]
    severity: ContradictionSeverity
    disposition: ContradictionDisposition
    resolution_artifact_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.contradiction_id, "ContradictionRecord.contradiction_id")
        _require_exact_enum(
            self.dimension,
            InterviewDimension,
            "ContradictionRecord.dimension",
        )
        statement_ids = _require_string_tuple(
            self.statement_ids,
            "ContradictionRecord.statement_ids",
            minimum=2,
        )
        object.__setattr__(self, "statement_ids", tuple(sorted(statement_ids)))
        _require_exact_enum(
            self.severity,
            ContradictionSeverity,
            "ContradictionRecord.severity",
        )
        _require_exact_enum(
            self.disposition,
            ContradictionDisposition,
            "ContradictionRecord.disposition",
        )
        resolution = _require_optional_text(
            self.resolution_artifact_id,
            "ContradictionRecord.resolution_artifact_id",
        )
        blocker = _require_optional_text(
            self.blocker_id, "ContradictionRecord.blocker_id"
        )
        if self.disposition is ContradictionDisposition.UNRESOLVED:
            valid = resolution is None and blocker is None
        elif self.disposition is ContradictionDisposition.RESOLVED:
            valid = resolution is not None and blocker is None
        else:
            valid = resolution is None and blocker is not None
        if not valid:
            _fail(
                "CONTRADICTION_DISPOSITION_INVALID",
                "contradiction resolution and blocker linkage do not match its disposition",
                {
                    "contradiction_id": self.contradiction_id,
                    "disposition": self.disposition.value,
                },
            )


@dataclass(frozen=True, slots=True)
class PriorQuestionRecord:
    question_id: str
    target_type: QuestionTargetType
    target_id: str
    state: PriorQuestionState
    answer_artifact_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.question_id, "PriorQuestionRecord.question_id")
        _require_exact_enum(
            self.target_type,
            QuestionTargetType,
            "PriorQuestionRecord.target_type",
        )
        _require_text(self.target_id, "PriorQuestionRecord.target_id")
        _require_exact_enum(self.state, PriorQuestionState, "PriorQuestionRecord.state")
        answer = _require_optional_text(
            self.answer_artifact_id,
            "PriorQuestionRecord.answer_artifact_id",
        )
        blocker = _require_optional_text(
            self.blocker_id, "PriorQuestionRecord.blocker_id"
        )
        if self.state is PriorQuestionState.ASKED:
            valid = answer is None and blocker is None
        elif self.state is PriorQuestionState.ANSWERED:
            valid = answer is not None and blocker is None
        else:
            valid = answer is None and blocker is not None
        if not valid:
            _fail(
                "PRIOR_QUESTION_STATE_INVALID",
                "prior question linkage does not match its state",
                {"question_id": self.question_id, "state": self.state.value},
            )


@dataclass(frozen=True, slots=True)
class InterviewQuestion:
    question_id: str
    target_type: QuestionTargetType
    target_id: str
    rule_ids: tuple[str, ...]
    need_ids: tuple[str, ...]
    prompt: str


@dataclass(frozen=True, slots=True)
class InterviewPlan:
    request_id: str
    request_revision: int
    engine_version: str
    readiness: InterviewReadiness
    questions: tuple[InterviewQuestion, ...]
    recorded_contradictions: tuple[ContradictionRecord, ...]
    suppressed_question_ids: tuple[str, ...]
    pending_question_ids: tuple[str, ...]
    blocker_ids: tuple[str, ...]
    deferred_noncritical_need_ids: tuple[str, ...]
    readiness_reasons: tuple[str, ...]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def question_id_for(
    request_id: str,
    request_revision: int,
    target_type: QuestionTargetType,
    target_id: str,
) -> str:
    """Return the stable question identity for one immutable request revision."""

    request = _require_text(request_id, "request_id")
    if type(request_revision) is not int or request_revision < 0:
        _fail(
            "INTERVIEW_INPUT_INVALID", "request_revision must be a non-negative integer"
        )
    _require_exact_enum(target_type, QuestionTargetType, "target_type")
    target = _require_text(target_id, "target_id")
    preimage = {
        "engine_version": INTERVIEW_ENGINE_VERSION,
        "request_id": request,
        "request_revision": request_revision,
        "target_id": target,
        "target_type": target_type.value,
    }
    digest = hashlib.sha256(_canonical_json(preimage)).hexdigest()
    return f"IQ-{digest}"


def _require_record_tuple(
    value: object,
    expected_type: type,
    label: str,
) -> tuple:
    if type(value) is not tuple:
        _fail("INTERVIEW_INPUT_INVALID", f"{label} must be an immutable tuple")
    for index, entry in enumerate(value):
        if type(entry) is not expected_type:
            _fail(
                "INTERVIEW_INPUT_INVALID",
                f"{label}[{index}] must be exactly {expected_type.__name__}",
            )
    return value


def _unique_by(values: Iterable[object], attribute: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        identifier = str(getattr(value, attribute))
        if identifier in seen:
            _fail("INTERVIEW_INPUT_DUPLICATE", f"duplicate {label}: {identifier}")
        seen.add(identifier)


def _prior_records_by_target(
    request_id: str,
    request_revision: int,
    records: tuple[PriorQuestionRecord, ...],
    contradictions: dict[str, ContradictionRecord],
) -> dict[tuple[QuestionTargetType, str], PriorQuestionRecord]:
    result: dict[tuple[QuestionTargetType, str], PriorQuestionRecord] = {}
    for record in records:
        if record.target_type is QuestionTargetType.DIMENSION:
            try:
                dimension = InterviewDimension(record.target_id)
            except ValueError:
                _fail(
                    "PRIOR_QUESTION_TARGET_INVALID",
                    "prior question names an unknown Interview dimension",
                    {"question_id": record.question_id},
                )
            if dimension is InterviewDimension.REQUIREMENT_CONFLICT:
                _fail(
                    "PRIOR_QUESTION_TARGET_INVALID",
                    "requirement-conflict questions must bind a contradiction ID",
                    {"question_id": record.question_id},
                )
        elif record.target_id not in contradictions:
            _fail(
                "PRIOR_QUESTION_TARGET_INVALID",
                "prior question names a contradiction absent from the current request revision",
                {"question_id": record.question_id, "target_id": record.target_id},
            )
        expected_id = question_id_for(
            request_id,
            request_revision,
            record.target_type,
            record.target_id,
        )
        if record.question_id != expected_id:
            _fail(
                "PRIOR_QUESTION_ID_MISMATCH",
                "prior question ID does not bind its request revision and target",
                {"expected": expected_id, "actual": record.question_id},
            )
        key = (record.target_type, record.target_id)
        if key in result:
            _fail(
                "INTERVIEW_INPUT_DUPLICATE",
                "multiple prior question records target the same decision",
                {
                    "target_type": record.target_type.value,
                    "target_id": record.target_id,
                },
            )
        result[key] = record
    return result


def _dimension_question(
    request_id: str,
    request_revision: int,
    dimension: InterviewDimension,
    needs: tuple[InterviewNeed, ...],
) -> InterviewQuestion:
    rules = tuple(
        rule.value for rule in RULE_ORDER if any(need.rule is rule for need in needs)
    )
    need_ids = tuple(sorted(need.need_id for need in needs))
    return InterviewQuestion(
        question_id=question_id_for(
            request_id,
            request_revision,
            QuestionTargetType.DIMENSION,
            dimension.value,
        ),
        target_type=QuestionTargetType.DIMENSION,
        target_id=dimension.value,
        rule_ids=rules,
        need_ids=need_ids,
        prompt=_DIMENSION_PROMPTS[dimension],
    )


def _contradiction_question(
    request_id: str,
    request_revision: int,
    contradiction: ContradictionRecord,
) -> InterviewQuestion:
    return InterviewQuestion(
        question_id=question_id_for(
            request_id,
            request_revision,
            QuestionTargetType.CONTRADICTION,
            contradiction.contradiction_id,
        ),
        target_type=QuestionTargetType.CONTRADICTION,
        target_id=contradiction.contradiction_id,
        rule_ids=(InterviewRule.CONFLICTING_REQUIREMENTS.value,),
        need_ids=(),
        prompt=(
            "Which requirement has authority for contradiction "
            f"{contradiction.contradiction_id}, or should it remain an explicit blocker?"
        ),
    )


def build_interview_plan(
    *,
    request_id: str,
    request_revision: int,
    needs: tuple[InterviewNeed, ...],
    known_facts: tuple[KnownFact, ...] = (),
    contradictions: tuple[ContradictionRecord, ...] = (),
    prior_questions: tuple[PriorQuestionRecord, ...] = (),
) -> InterviewPlan:
    """Build a deterministic, no-repeat Interview plan and readiness verdict."""

    request = _require_text(request_id, "request_id")
    if type(request_revision) is not int or request_revision < 0:
        _fail(
            "INTERVIEW_INPUT_INVALID", "request_revision must be a non-negative integer"
        )
    need_records = _require_record_tuple(needs, InterviewNeed, "needs")
    facts = _require_record_tuple(known_facts, KnownFact, "known_facts")
    contradiction_records = _require_record_tuple(
        contradictions,
        ContradictionRecord,
        "contradictions",
    )
    history = _require_record_tuple(
        prior_questions,
        PriorQuestionRecord,
        "prior_questions",
    )
    _unique_by(need_records, "need_id", "need_id")
    _unique_by(facts, "fact_id", "fact_id")
    _unique_by(contradiction_records, "contradiction_id", "contradiction_id")
    _unique_by(history, "question_id", "question_id")

    contradiction_by_id = {
        contradiction.contradiction_id: contradiction
        for contradiction in contradiction_records
    }
    critical_contradictions = tuple(
        contradiction
        for contradiction in contradiction_records
        if contradiction.severity is ContradictionSeverity.CRITICAL
    )
    if (
        any(
            need.rule is InterviewRule.CONFLICTING_REQUIREMENTS
            and need.criticality is NeedCriticality.DECISION_CRITICAL
            for need in need_records
        )
        and not critical_contradictions
    ):
        _fail(
            "CONTRADICTION_EVIDENCE_REQUIRED",
            "a critical conflicting-requirements need requires a recorded critical contradiction",
        )

    prior_by_target = _prior_records_by_target(
        request,
        request_revision,
        history,
        contradiction_by_id,
    )
    known_dimensions = {fact.dimension for fact in facts}
    for record in history:
        if (
            record.target_type is QuestionTargetType.DIMENSION
            and record.state is PriorQuestionState.ANSWERED
        ):
            known_dimensions.add(InterviewDimension(record.target_id))

    critical_by_dimension: dict[InterviewDimension, list[InterviewNeed]] = {}
    deferred_noncritical = []
    for need in need_records:
        if need.criticality is NeedCriticality.NON_CRITICAL:
            deferred_noncritical.append(need.need_id)
            continue
        if need.rule is InterviewRule.CONFLICTING_REQUIREMENTS:
            continue
        critical_by_dimension.setdefault(need.dimension, []).append(need)

    candidates: list[tuple[int, int, str, InterviewQuestion]] = []
    for dimension, dimension_needs in critical_by_dimension.items():
        if dimension in known_dimensions:
            continue
        ordered_needs = tuple(
            sorted(
                dimension_needs,
                key=lambda need: (_RULE_INDEX[need.rule], need.need_id),
            )
        )
        question = _dimension_question(
            request,
            request_revision,
            dimension,
            ordered_needs,
        )
        priority = min(_RULE_INDEX[need.rule] for need in ordered_needs)
        candidates.append(
            (priority, _DIMENSION_INDEX[dimension], dimension.value, question)
        )

    for contradiction in critical_contradictions:
        if contradiction.disposition is ContradictionDisposition.UNRESOLVED:
            question = _contradiction_question(request, request_revision, contradiction)
            candidates.append(
                (
                    _RULE_INDEX[InterviewRule.CONFLICTING_REQUIREMENTS],
                    _DIMENSION_INDEX[InterviewDimension.REQUIREMENT_CONFLICT],
                    contradiction.contradiction_id,
                    question,
                )
            )

    emitted: list[InterviewQuestion] = []
    suppressed: set[str] = set()
    pending: set[str] = set()
    blockers: set[str] = set()

    for record in history:
        if record.state is PriorQuestionState.ACCEPTED_AS_BLOCKER:
            assert record.blocker_id is not None
            blockers.add(record.blocker_id)

    for contradiction in contradiction_records:
        if contradiction.disposition is ContradictionDisposition.ACCEPTED_AS_BLOCKER:
            assert contradiction.blocker_id is not None
            blockers.add(contradiction.blocker_id)
        target = (QuestionTargetType.CONTRADICTION, contradiction.contradiction_id)
        prior = prior_by_target.get(target)
        if prior is not None and prior.state is PriorQuestionState.ACCEPTED_AS_BLOCKER:
            if (
                contradiction.disposition
                is not ContradictionDisposition.ACCEPTED_AS_BLOCKER
                or contradiction.blocker_id != prior.blocker_id
            ):
                _fail(
                    "CONTRADICTION_BLOCKER_MISMATCH",
                    "prior blocker acceptance is not reflected in the contradiction record",
                    {"contradiction_id": contradiction.contradiction_id},
                )

    for _priority, _dimension_priority, _target, question in sorted(candidates):
        key = (question.target_type, question.target_id)
        prior = prior_by_target.get(key)
        if prior is None:
            emitted.append(question)
            continue
        suppressed.add(question.question_id)
        if prior.state in (PriorQuestionState.ASKED, PriorQuestionState.ANSWERED):
            if question.target_type is QuestionTargetType.CONTRADICTION:
                contradiction = contradiction_by_id[question.target_id]
                if contradiction.disposition is ContradictionDisposition.UNRESOLVED:
                    pending.add(question.question_id)
            elif prior.state is PriorQuestionState.ASKED:
                pending.add(question.question_id)

    if blockers:
        readiness = InterviewReadiness.BLOCKED
        reasons = tuple(f"BLOCKER:{identifier}" for identifier in sorted(blockers))
    elif emitted or pending:
        readiness = InterviewReadiness.NEEDS_INPUT
        reasons = tuple(
            [f"QUESTION:{question.question_id}" for question in emitted]
            + [f"PENDING:{identifier}" for identifier in sorted(pending)]
        )
    else:
        readiness = InterviewReadiness.READY
        reasons = ("READY:DECISION_CONTRACT_COMPLETE",)

    return InterviewPlan(
        request_id=request,
        request_revision=request_revision,
        engine_version=INTERVIEW_ENGINE_VERSION,
        readiness=readiness,
        questions=tuple(emitted),
        recorded_contradictions=tuple(
            sorted(
                contradiction_records,
                key=lambda contradiction: contradiction.contradiction_id,
            )
        ),
        suppressed_question_ids=tuple(sorted(suppressed)),
        pending_question_ids=tuple(sorted(pending)),
        blocker_ids=tuple(sorted(blockers)),
        deferred_noncritical_need_ids=tuple(sorted(deferred_noncritical)),
        readiness_reasons=reasons,
    )


__all__ = [
    "INTERVIEW_ENGINE_VERSION",
    "ContradictionDisposition",
    "ContradictionRecord",
    "ContradictionSeverity",
    "InterviewContractError",
    "InterviewDimension",
    "InterviewNeed",
    "InterviewPlan",
    "InterviewQuestion",
    "InterviewReadiness",
    "InterviewRule",
    "KnownFact",
    "NeedCriticality",
    "PriorQuestionRecord",
    "PriorQuestionState",
    "QuestionTargetType",
    "build_interview_plan",
    "question_id_for",
]
