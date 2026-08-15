"""O01 deterministic QueryPlan and search-completeness contracts.

The component does not execute retrieval.  It compiles the class-bound lane
selection, validates immutable execution receipts, and reconciles all eleven
canonical lanes without interpreting an unsearched lane as a zero result.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_SCOPE_VECTOR_SCHEMA_PATH: Final = (
    Path(__file__).resolve().parents[4] / "schemas/scope-vector.schema.json"
)


class Lane(str, Enum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    CITATION = "citation"
    ENTITY_VARIABLE = "entity_variable"
    MECHANISM = "mechanism"
    COUNTEREVIDENCE = "counterevidence"
    NULL = "null"
    BOUNDARY = "boundary"
    METHOD = "method"
    TEMPORAL = "temporal"
    EXTERNAL_NOVELTY = "external_novelty"


class WorkClass(str, Enum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"


class SearchState(str, Enum):
    UNSEARCHED = "UNSEARCHED"
    SEARCHED_NONE = "SEARCHED_NONE"
    SEARCHED_WITH_RESULTS = "SEARCHED_WITH_RESULTS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


CANONICAL_LANES: Final = tuple(lane.value for lane in Lane)
_LANE_RANK: Final = {lane: index for index, lane in enumerate(CANONICAL_LANES)}

CLASS_LANE_FLOORS: Final = MappingProxyType(
    {
        WorkClass.E0.value: (),
        WorkClass.E1.value: (
            Lane.LEXICAL.value,
            Lane.SEMANTIC.value,
            Lane.CITATION.value,
            Lane.TEMPORAL.value,
        ),
        WorkClass.E2.value: (
            Lane.LEXICAL.value,
            Lane.SEMANTIC.value,
            Lane.CITATION.value,
            Lane.ENTITY_VARIABLE.value,
            Lane.COUNTEREVIDENCE.value,
            Lane.NULL.value,
            Lane.BOUNDARY.value,
            Lane.METHOD.value,
            Lane.TEMPORAL.value,
        ),
        WorkClass.E3.value: CANONICAL_LANES[:-1],
        WorkClass.E4.value: CANONICAL_LANES[:-1],
        WorkClass.E5.value: CANONICAL_LANES,
    }
)

_LANE_QUERY_FAMILY_FIELDS: Final[
    Mapping[str, tuple[tuple[str, str], ...]]
] = MappingProxyType(
    {
        Lane.LEXICAL.value: (("FORWARD", "forward_queries"),),
        Lane.SEMANTIC.value: (("FORWARD", "forward_queries"),),
        Lane.CITATION.value: (("FORWARD", "forward_queries"),),
        Lane.ENTITY_VARIABLE.value: (("FORWARD", "forward_queries"),),
        Lane.MECHANISM.value: (("FORWARD", "forward_queries"),),
        Lane.COUNTEREVIDENCE.value: (
            ("FORWARD", "forward_queries"),
            ("REVERSE", "reverse_queries"),
        ),
        Lane.NULL.value: (("NULL", "null_queries"),),
        Lane.BOUNDARY.value: (("BOUNDARY", "boundary_queries"),),
        Lane.METHOD.value: (("METHOD", "method_queries"),),
        Lane.TEMPORAL.value: (("FORWARD", "forward_queries"),),
        Lane.EXTERNAL_NOVELTY.value: (("NOVELTY", "novelty_queries"),),
    }
)

_PLAN_DERIVED_FIELDS: Final = frozenset(
    {"retrieval_requirement", "required_lanes", "lane_decisions", "plan_hash"}
)
_PLAN_BASE_FIELDS: Final = frozenset(
    {
        "query_plan_id",
        "request_id",
        "request_revision",
        "request_input_hash",
        "classification_id",
        "classification_revision",
        "classification_hash",
        "work_class",
        "classifier_version",
        "policy_bundle_hash",
        "insight_id",
        "insight_revision",
        "canonical_relation",
        "forward_queries",
        "reverse_queries",
        "null_queries",
        "boundary_queries",
        "method_queries",
        "novelty_queries",
        "scope_partitions",
        "budget",
        "stop_rules",
        "planner_prompt_hash",
        "created_at",
    }
)
_PLAN_FIELDS: Final = _PLAN_BASE_FIELDS | _PLAN_DERIVED_FIELDS
_LANE_DECISION_FIELDS: Final = frozenset(
    {"lane", "disposition", "decision_reason", "evidence_ids"}
)
_RECEIPT_FIELDS: Final = frozenset(
    {
        "receipt_id",
        "run_id",
        "query_plan_id",
        "plan_hash",
        "lane",
        "receipt_kind",
        "sentinel_reason",
        "lane_decision_evidence_ids",
        "query_text",
        "query_hash",
        "scope_filter",
        "corpus_snapshot_hash",
        "index_versions",
        "result_ids",
        "result_count",
        "excluded_count",
        "stop_reason",
        "search_state",
        "recall_proxy",
        "errors",
        "started_at",
        "finished_at",
        "receipt_hash",
    }
)
_CERTIFICATE_FIELDS: Final = frozenset(
    {
        "certificate_id",
        "run_id",
        "subject_ref",
        "query_plan_id",
        "plan_hash",
        "work_class",
        "required_lanes",
        "lane_receipt_ids",
        "lane_reconciliations",
        "completed_lanes",
        "partial_lanes",
        "blocked_lanes",
        "failed_lanes",
        "unsearched_lanes",
        "searched_scope",
        "unsearched_scope",
        "completion_state",
        "absence_claim_ceiling",
        "novelty_claim_ceiling",
        "known_failures",
        "generated_at",
        "certificate_hash",
    }
)


class PlanningContractError(ValueError):
    """Typed fail-closed O01 contract error."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.run_status = "FAIL"
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise PlanningContractError(code, message, details)


@dataclass(frozen=True, slots=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, object]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed artifact is not an object")
        return value


@dataclass(frozen=True, slots=True)
class LaneQueryProjection:
    """Immutable exact QueryPlan projection for one selected retrieval lane."""

    query_plan_id: str
    plan_hash: str
    lane: str
    query_families: tuple[str, ...]
    _query_batch_bytes: bytes

    @property
    def query_batch(self) -> dict[str, object]:
        """Return a fresh mutable projection of the canonical query batch."""

        value = json.loads(self._query_batch_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("lane query batch is not an object")
        return value

    @property
    def query_batch_bytes(self) -> bytes:
        return self._query_batch_bytes

    @property
    def query_text(self) -> str:
        return self._query_batch_bytes.decode("utf-8")

    @property
    def query_hash(self) -> str:
        return _digest_bytes(self._query_batch_bytes)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise PlanningContractError(
            "CANONICAL_JSON_INVALID",
            "value must be finite canonical UTF-8 JSON",
        ) from error


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    return _digest_bytes(_canonical_json(value))


def _hash_excluding(payload: Mapping[str, object], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be an object")
    result: dict[str, object] = {}
    for key, entry in value.items():
        if type(key) is not str or not key or "\x00" in key:
            _fail("INPUT_INVALID", f"{label} keys must be non-empty strings")
        result[key] = entry
    _canonical_json(result)
    return result


@lru_cache(maxsize=1)
def _scope_vector_validator() -> Draft202012Validator:
    try:
        schema = json.loads(_SCOPE_VECTOR_SCHEMA_PATH.read_text(encoding="utf-8"))
        if type(schema) is not dict:
            raise ValueError("ScopeVector schema must be an object")
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, ValueError, SchemaError) as error:
        raise PlanningContractError(
            "SCHEMA_UNREADABLE", "canonical ScopeVector schema is unavailable"
        ) from error
    return Draft202012Validator(schema)


def _scope_vector(value: object, label: str) -> dict[str, object]:
    scope = _mapping(value, label)
    errors = sorted(
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in _scope_vector_validator().iter_errors(scope)
    )
    if errors:
        _fail(
            "INPUT_INVALID",
            f"{label} must be a canonical ScopeVector",
            {"errors": errors},
        )
    return scope


def _exact_fields(payload: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is not canonical",
            {"missing": missing, "unknown": unknown},
        )


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        _fail("INPUT_INVALID", f"{label} must be a non-empty NUL-free string")
    return value.strip()


def _integer(value: object, label: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        _fail("INPUT_INVALID", f"{label} must be an integer >= {minimum}")
    return value


def _hash(value: object, label: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        _fail("HASH_FORMAT_INVALID", f"{label} must be sha256:<64 lowercase hex>")
    return value


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str or RFC3339_PATTERN.fullmatch(value) is None:
        _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PlanningContractError("TIMESTAMP_INVALID", f"{label} is not a real timestamp") from error
    return value


def _strings(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    result = [_text(entry, f"{label}[]") for entry in value]
    if not allow_empty and not result:
        _fail("INPUT_INVALID", f"{label} must not be empty")
    if len(result) != len(set(result)):
        _fail("DUPLICATE_VALUE", f"{label} must not contain duplicates")
    return result


def _lane(value: object, label: str = "lane") -> str:
    if type(value) is not str:
        _fail("LANE_UNKNOWN", f"{label} must be a canonical lane")
    try:
        return Lane(value).value
    except ValueError as error:
        code = "LEGACY_LANE_REQUIRES_MIGRATION" if value in {"counter", "novelty"} else "LANE_UNKNOWN"
        raise PlanningContractError(code, f"{value!r} is not accepted on canonical writes") from error


def _work_class(value: object) -> str:
    if type(value) is not str:
        _fail("WORK_CLASS_INVALID", "work_class must be E0-E5")
    try:
        return WorkClass(value).value
    except ValueError as error:
        raise PlanningContractError("WORK_CLASS_INVALID", "work_class must be E0-E5") from error


def _lanes(value: object, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    result = [_lane(entry, f"{label}[]") for entry in value]
    if len(result) != len(set(result)):
        _fail("LANE_DUPLICATE", f"{label} must not contain duplicate lanes")
    if result != sorted(result, key=_LANE_RANK.__getitem__):
        _fail("LANE_ORDER_INVALID", f"{label} must use canonical lane order")
    return result


def _sealed(artifact_type: str, payload: Mapping[str, object]) -> SealedArtifact:
    return SealedArtifact(artifact_type, _canonical_json(dict(payload)))


def _artifact_payload(value: Mapping[str, object] | SealedArtifact, label: str) -> dict[str, object]:
    if isinstance(value, SealedArtifact):
        return value.payload
    return _mapping(value, label)


def _lane_evidence(
    mapping: Mapping[str, Sequence[str]] | None,
    lane: str,
    label: str,
) -> list[str] | None:
    if mapping is None or lane not in mapping:
        return None
    return _strings(mapping[lane], f"{label}.{lane}", allow_empty=False)


def compile_query_plan(
    proposal: Mapping[str, object],
    *,
    selected_optional_lanes: Sequence[str] = (),
    not_applicable_lanes: Sequence[str] = (),
    selection_evidence: Mapping[str, Sequence[str]] | None = None,
    applicability_evidence: Mapping[str, Sequence[str]] | None = None,
) -> SealedArtifact:
    """Compile and hash one immutable class-bound QueryPlan."""

    base = _mapping(proposal, "proposal")
    if set(base) & _PLAN_DERIVED_FIELDS:
        _fail("DERIVED_FIELD_PROVIDED", "QueryPlan derived fields are owned by the compiler")
    _exact_fields(base, _PLAN_BASE_FIELDS, "QueryPlan proposal")
    work_class = _work_class(base["work_class"])
    selected_optional = set(_lanes(selected_optional_lanes, "selected_optional_lanes"))
    not_applicable = set(_lanes(not_applicable_lanes, "not_applicable_lanes"))
    floor = set(CLASS_LANE_FLOORS[work_class])
    if selected_optional & floor:
        _fail("CLASS_FLOOR_REDECLARED", "class-floor lanes are already selected and non-waivable")
    if not_applicable & floor:
        _fail("CLASS_FLOOR_WAIVER_FORBIDDEN", "class-floor lanes cannot be not applicable")
    if selected_optional & not_applicable:
        _fail("LANE_DECISION_CONFLICT", "a lane cannot be selected and not applicable")
    if work_class == WorkClass.E0.value and selected_optional:
        _fail("E0_RETRIEVAL_FORBIDDEN", "E0 requires an explicit no-retrieval plan")

    classification_id = _text(base["classification_id"], "classification_id")
    policy_hash = _hash(base["policy_bundle_hash"], "policy_bundle_hash")
    decisions: list[dict[str, object]] = []
    selected: list[str] = []
    for lane in CANONICAL_LANES:
        if lane in floor:
            selected.append(lane)
            decisions.append(
                {
                    "lane": lane,
                    "disposition": "SELECTED",
                    "decision_reason": "CLASS_FLOOR",
                    "evidence_ids": [classification_id],
                }
            )
        elif lane in selected_optional:
            selected.append(lane)
            evidence = _lane_evidence(selection_evidence, lane, "selection_evidence") or [policy_hash]
            decisions.append(
                {
                    "lane": lane,
                    "disposition": "SELECTED",
                    "decision_reason": "POLICY_SELECTED",
                    "evidence_ids": evidence,
                }
            )
        elif lane in not_applicable:
            evidence = _lane_evidence(applicability_evidence, lane, "applicability_evidence")
            if evidence is None:
                _fail(
                    "APPLICABILITY_EVIDENCE_REQUIRED",
                    f"NOT_APPLICABLE lane {lane} requires typed deterministic evidence",
                )
            decisions.append(
                {
                    "lane": lane,
                    "disposition": "NOT_APPLICABLE",
                    "decision_reason": "NOT_APPLICABLE",
                    "evidence_ids": evidence,
                }
            )
        else:
            decisions.append(
                {
                    "lane": lane,
                    "disposition": "NOT_REQUIRED_FOR_CLASS",
                    "decision_reason": "NOT_REQUIRED_FOR_CLASS",
                    "evidence_ids": [classification_id],
                }
            )

    plan = dict(base)
    plan.update(
        {
            "retrieval_requirement": "NOT_REQUIRED" if work_class == "E0" else "REQUIRED",
            "required_lanes": selected,
            "lane_decisions": decisions,
        }
    )
    _validate_query_plan_shape(plan, check_hash=False)
    plan["plan_hash"] = _hash_excluding(plan, "plan_hash")
    return validate_query_plan(plan)


def _validate_query_plan_shape(payload: Mapping[str, object], *, check_hash: bool) -> None:
    expected = _PLAN_FIELDS if check_hash else _PLAN_FIELDS - {"plan_hash"}
    _exact_fields(payload, expected, "QueryPlan")
    for field in (
        "query_plan_id",
        "request_id",
        "classification_id",
        "classifier_version",
        "insight_id",
        "canonical_relation",
    ):
        _text(payload[field], field)
    for field in ("request_revision", "classification_revision", "insight_revision"):
        _integer(payload[field], field, 1)
    for field in (
        "request_input_hash",
        "classification_hash",
        "policy_bundle_hash",
        "planner_prompt_hash",
    ):
        _hash(payload[field], field)
    work_class = _work_class(payload["work_class"])
    _timestamp(payload["created_at"], "created_at")

    query_fields = (
        "forward_queries",
        "reverse_queries",
        "null_queries",
        "boundary_queries",
        "method_queries",
        "novelty_queries",
    )
    queries = {field: _strings(payload[field], field) for field in query_fields}
    scopes = payload["scope_partitions"]
    if not isinstance(scopes, Sequence) or isinstance(scopes, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", "scope_partitions must be an array")
    for index, scope in enumerate(scopes):
        _scope_vector(scope, f"scope_partitions[{index}]")

    budget = _mapping(payload["budget"], "budget")
    _exact_fields(budget, frozenset({"max_queries", "max_documents", "max_seconds"}), "budget")
    minimum = 0 if work_class == "E0" else 1
    for field in ("max_queries", "max_documents", "max_seconds"):
        _integer(budget[field], f"budget.{field}", minimum)
    _strings(payload["stop_rules"], "stop_rules", allow_empty=False)

    required_lanes = _lanes(payload["required_lanes"], "required_lanes")
    floor = set(CLASS_LANE_FLOORS[work_class])
    if not floor.issubset(required_lanes):
        _fail(
            "CLASS_FLOOR_VIOLATION",
            "required_lanes omit one or more non-waivable class-floor lanes",
            {"missing": sorted(floor - set(required_lanes), key=_LANE_RANK.__getitem__)},
        )
    requirement = payload["retrieval_requirement"]
    if work_class == "E0":
        if requirement != "NOT_REQUIRED" or required_lanes:
            _fail("E0_RETRIEVAL_FORBIDDEN", "E0 must be NOT_REQUIRED with no selected lane")
        if any(queries.values()) or any(budget.values()):
            _fail("E0_EXECUTION_INPUT_FORBIDDEN", "E0 query arrays and budget must be empty/zero")
    else:
        if requirement != "REQUIRED" or not required_lanes:
            _fail("RETRIEVAL_REQUIRED", "E1-E5 require selected retrieval lanes")
        if not queries["forward_queries"]:
            _fail("QUERY_REQUIRED", "E1-E5 require at least one forward query")
        conditional_query_lanes = {
            "counterevidence": "reverse_queries",
            "null": "null_queries",
            "boundary": "boundary_queries",
            "method": "method_queries",
            "external_novelty": "novelty_queries",
        }
        for lane, field in conditional_query_lanes.items():
            if lane in required_lanes and not queries[field]:
                _fail("QUERY_REQUIRED", f"selected lane {lane} requires {field}")

    decisions = payload["lane_decisions"]
    if not isinstance(decisions, Sequence) or isinstance(
        decisions, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "lane_decisions must be an array")
    if len(decisions) != len(CANONICAL_LANES):
        _fail("LANE_RECONCILIATION_COUNT", "lane_decisions must reconcile all eleven lanes")
    selected_from_decisions: list[str] = []
    for expected_lane, value in zip(CANONICAL_LANES, decisions, strict=True):
        decision = _mapping(value, f"lane_decisions.{expected_lane}")
        _exact_fields(decision, _LANE_DECISION_FIELDS, f"lane decision {expected_lane}")
        if _lane(decision["lane"]) != expected_lane:
            _fail("LANE_ORDER_INVALID", "lane_decisions must use exact canonical order")
        disposition = decision["disposition"]
        reason = decision["decision_reason"]
        evidence = _strings(decision["evidence_ids"], "evidence_ids", allow_empty=False)
        if not evidence:  # pragma: no cover - enforced above
            _fail("LANE_DECISION_EVIDENCE_REQUIRED", "lane decision evidence is required")
        if expected_lane in floor:
            if disposition != "SELECTED" or reason != "CLASS_FLOOR":
                _fail("CLASS_FLOOR_WAIVER_FORBIDDEN", f"class-floor lane {expected_lane} must be selected")
        elif disposition == "SELECTED":
            if reason != "POLICY_SELECTED":
                _fail("LANE_DECISION_INVALID", "optional selected lanes require POLICY_SELECTED")
        elif disposition in {"NOT_REQUIRED_FOR_CLASS", "NOT_APPLICABLE"}:
            if reason != disposition:
                _fail("LANE_DECISION_INVALID", "unselected lane reason must equal its disposition")
        else:
            _fail("LANE_DECISION_INVALID", "lane disposition is not canonical")
        if disposition == "SELECTED":
            selected_from_decisions.append(expected_lane)
    if selected_from_decisions != required_lanes:
        _fail("LANE_SELECTION_MISMATCH", "required_lanes must exactly equal selected lane decisions")

    if check_hash:
        asserted = _hash(payload["plan_hash"], "plan_hash")
        computed = _hash_excluding(payload, "plan_hash")
        if asserted != computed:
            _fail("PLAN_HASH_MISMATCH", "plan_hash does not match canonical QueryPlan content")


def validate_query_plan(payload: Mapping[str, object]) -> SealedArtifact:
    value = _mapping(payload, "QueryPlan")
    _validate_query_plan_shape(value, check_hash=True)
    return _sealed("QueryPlan", value)


def project_lane_query(
    query_plan: Mapping[str, object] | SealedArtifact,
    lane: str,
) -> LaneQueryProjection:
    """Project the exact canonical query batch for one selected lane."""

    plan = validate_query_plan(_artifact_payload(query_plan, "query_plan")).payload
    canonical_lane = _lane(lane)
    decisions = plan["lane_decisions"]
    if not isinstance(decisions, Sequence) or isinstance(
        decisions, (str, bytes, bytearray)
    ):
        raise AssertionError("validated QueryPlan lane decision invariant violated")
    decision = decisions[_LANE_RANK[canonical_lane]]
    if not isinstance(decision, Mapping):
        raise AssertionError("validated QueryPlan lane decision invariant violated")
    if decision["disposition"] != "SELECTED":
        _fail(
            "LANE_SELECTION_MISMATCH",
            f"lane {canonical_lane} must be SELECTED before query projection",
        )

    families: list[dict[str, object]] = []
    query_families: list[str] = []
    for family, field in _LANE_QUERY_FAMILY_FIELDS[canonical_lane]:
        queries = plan[field]
        if not isinstance(queries, Sequence) or isinstance(
            queries, (str, bytes, bytearray)
        ):
            raise AssertionError("validated QueryPlan query array invariant violated")
        families.append({"family": family, "queries": list(queries)})
        query_families.append(family)
    query_batch_bytes = _canonical_json(
        {"families": families, "lane": canonical_lane}
    )
    query_plan_id = plan["query_plan_id"]
    plan_hash = plan["plan_hash"]
    if type(query_plan_id) is not str or type(plan_hash) is not str:
        raise AssertionError("validated QueryPlan identity invariant violated")
    return LaneQueryProjection(
        query_plan_id=query_plan_id,
        plan_hash=plan_hash,
        lane=canonical_lane,
        query_families=tuple(query_families),
        _query_batch_bytes=query_batch_bytes,
    )


def _expected_lane_query_text(plan: Mapping[str, object], lane: str) -> str:
    return project_lane_query(plan, lane).query_text


def _validate_receipt_plan_binding(
    receipt: Mapping[str, object],
    plan: Mapping[str, object],
) -> None:
    if (
        receipt["query_plan_id"] != plan["query_plan_id"]
        or receipt["plan_hash"] != plan["plan_hash"]
    ):
        _fail(
            "RECEIPT_PLAN_MISMATCH",
            "receipt does not bind the exact QueryPlan revision",
        )
    if receipt["receipt_kind"] == "SENTINEL":
        return
    lane = str(receipt["lane"])
    query_text = receipt["query_text"]
    if not isinstance(query_text, str):  # pragma: no cover - receipt shape invariant
        raise AssertionError("validated execution receipt query_text invariant violated")
    projection = project_lane_query(plan, lane)
    if query_text.encode("utf-8") != projection.query_batch_bytes:
        _fail(
            "RECEIPT_QUERY_MISMATCH",
            "receipt query_text does not match the canonical QueryPlan lane projection",
        )


def seal_search_lane_receipt(
    proposal: Mapping[str, object],
    *,
    query_plan: Mapping[str, object] | SealedArtifact,
) -> SealedArtifact:
    plan = validate_query_plan(_artifact_payload(query_plan, "query_plan")).payload
    value = _mapping(proposal, "SearchLaneReceipt proposal")
    allowed = _RECEIPT_FIELDS - {"query_hash", "receipt_hash"}
    _exact_fields(value, allowed, "SearchLaneReceipt proposal")
    query_text = value["query_text"]
    if query_text is None:
        value["query_hash"] = None
    else:
        _text(query_text, "query_text")
        # Bind the exact persisted UTF-8 string.  Validation may reject an
        # empty/blank query, but it must not silently hash a trimmed surrogate
        # while retaining different bytes in the canonical receipt.
        value["query_hash"] = _digest_bytes(query_text.encode("utf-8"))
    _validate_receipt_shape(value, check_hash=False)
    value["receipt_hash"] = _hash_excluding(value, "receipt_hash")
    receipt = validate_search_lane_receipt(value)
    _validate_receipt_plan_binding(receipt.payload, plan)
    return receipt


def _nullable_hash(value: object, label: str) -> str | None:
    return None if value is None else _hash(value, label)


def _nullable_timestamp(value: object, label: str) -> str | None:
    return None if value is None else _timestamp(value, label)


def _validate_receipt_shape(payload: Mapping[str, object], *, check_hash: bool) -> None:
    expected = _RECEIPT_FIELDS if check_hash else _RECEIPT_FIELDS - {"receipt_hash"}
    _exact_fields(payload, expected, "SearchLaneReceipt")
    for field in ("receipt_id", "run_id", "query_plan_id"):
        _text(payload[field], field)
    _hash(payload["plan_hash"], "plan_hash")
    _lane(payload["lane"])
    state_value = payload["search_state"]
    try:
        state = SearchState(state_value) if type(state_value) is str else None
    except ValueError as error:
        raise PlanningContractError("SEARCH_STATE_INVALID", "search_state is not canonical") from error
    if state is None:
        _fail("SEARCH_STATE_INVALID", "search_state is not canonical")
    evidence = _strings(payload["lane_decision_evidence_ids"], "lane_decision_evidence_ids", allow_empty=False)
    if not evidence:  # pragma: no cover - enforced above
        _fail("LANE_DECISION_EVIDENCE_REQUIRED", "receipt must bind its lane decision evidence")
    errors = _strings(payload["errors"], "errors")
    recall = payload["recall_proxy"]
    if recall is not None and (
        type(recall) not in {int, float}
        or isinstance(recall, bool)
        or not math.isfinite(float(recall))
        or not 0 <= float(recall) <= 1
    ):
        _fail("INPUT_INVALID", "recall_proxy must be null or a finite number in [0,1]")

    if state is SearchState.UNSEARCHED:
        if payload["receipt_kind"] != "SENTINEL":
            _fail("UNSEARCHED_SENTINEL_REQUIRED", "UNSEARCHED must be a sentinel receipt")
        if payload["sentinel_reason"] not in {"NOT_REQUIRED_FOR_CLASS", "NOT_APPLICABLE"}:
            _fail("UNSEARCHED_REASON_REQUIRED", "UNSEARCHED requires a typed sentinel reason")
        for field in (
            "query_text",
            "query_hash",
            "scope_filter",
            "corpus_snapshot_hash",
            "index_versions",
            "result_ids",
            "result_count",
            "excluded_count",
            "stop_reason",
            "recall_proxy",
            "started_at",
            "finished_at",
        ):
            if payload[field] is not None:
                _fail("UNSEARCHED_EXECUTION_FIELD_PRESENT", f"UNSEARCHED field {field} must be null")
        if errors:
            _fail("UNSEARCHED_ERROR_FORBIDDEN", "UNSEARCHED sentinel errors must be empty")
    else:
        if payload["receipt_kind"] != "EXECUTION" or payload["sentinel_reason"] is not None:
            _fail("EXECUTION_RECEIPT_REQUIRED", "executed states require EXECUTION with null sentinel_reason")
        query_value = payload["query_text"]
        _text(query_value, "query_text")
        assert isinstance(query_value, str)  # narrowed by _text
        asserted_query_hash = _hash(payload["query_hash"], "query_hash")
        if asserted_query_hash != _digest_bytes(query_value.encode("utf-8")):
            _fail("QUERY_HASH_MISMATCH", "query_hash does not match UTF-8 query_text")
        _scope_vector(payload["scope_filter"], "scope_filter")

        if state in {SearchState.SEARCHED_NONE, SearchState.SEARCHED_WITH_RESULTS, SearchState.PARTIAL}:
            _hash(payload["corpus_snapshot_hash"], "corpus_snapshot_hash")
            indexes = _mapping(payload["index_versions"], "index_versions")
            if not indexes:
                _fail("INDEX_VERSION_REQUIRED", "executed search requires at least one index version")
            for key, item in indexes.items():
                _text(key, "index_versions key")
                _text(item, f"index_versions.{key}")
            result_ids = _strings(payload["result_ids"], "result_ids")
            result_count = _integer(payload["result_count"], "result_count", 0)
            _integer(payload["excluded_count"], "excluded_count", 0)
            if result_count != len(result_ids):
                _fail("RESULT_COUNT_MISMATCH", "result_count must equal the number of result_ids")
            started_at = _timestamp(payload["started_at"], "started_at")
            finished_at = _timestamp(payload["finished_at"], "finished_at")
        else:
            _nullable_hash(payload["corpus_snapshot_hash"], "corpus_snapshot_hash")
            if payload["index_versions"] is not None:
                _mapping(payload["index_versions"], "index_versions")
            if payload["result_ids"] is not None or payload["result_count"] is not None or payload["excluded_count"] is not None:
                _fail("FAILED_RESULT_COUNT_FORBIDDEN", "BLOCKED/FAILED cannot assert result counts")
            started_at = _nullable_timestamp(payload["started_at"], "started_at")
            finished_at = _nullable_timestamp(payload["finished_at"], "finished_at")

        if started_at is not None and finished_at is not None:
            started_suffix_length = 1 if started_at.endswith("Z") else 6
            finished_suffix_length = 1 if finished_at.endswith("Z") else 6
            started_offset = "+00:00" if started_suffix_length == 1 else started_at[-6:]
            finished_offset = "+00:00" if finished_suffix_length == 1 else finished_at[-6:]
            started_whole = datetime.fromisoformat(started_at[:19] + started_offset)
            finished_whole = datetime.fromisoformat(finished_at[:19] + finished_offset)
            started_fraction = started_at[20:-started_suffix_length] if started_at[19] == "." else ""
            finished_fraction = finished_at[20:-finished_suffix_length] if finished_at[19] == "." else ""
            fraction_width = max(len(started_fraction), len(finished_fraction))
            if finished_whole < started_whole or (
                finished_whole == started_whole
                and finished_fraction.ljust(fraction_width, "0")
                < started_fraction.ljust(fraction_width, "0")
            ):
                _fail("TIMESTAMP_DISORDERED", "finished_at must not precede started_at")

        stop = payload["stop_reason"]
        if state is SearchState.SEARCHED_NONE:
            if payload["result_count"] != 0 or payload["result_ids"] != [] or errors:
                _fail("SEARCHED_NONE_INVALID", "SEARCHED_NONE requires zero results and no errors")
            allowed_stops = {"exhausted_query_plan", "saturation_reached"}
        elif state is SearchState.SEARCHED_WITH_RESULTS:
            if type(payload["result_count"]) is not int or payload["result_count"] < 1 or errors:
                _fail("SEARCHED_RESULTS_INVALID", "SEARCHED_WITH_RESULTS requires results and no errors")
            allowed_stops = {"exhausted_query_plan", "saturation_reached"}
        elif state is SearchState.PARTIAL:
            allowed_stops = {"budget_exhausted", "time_exhausted", "manual_stop"}
        elif state is SearchState.BLOCKED:
            allowed_stops = {"policy_blocked", "credential_unavailable", "backend_unavailable"}
            if not errors:
                _fail("BLOCKED_REASON_REQUIRED", "BLOCKED requires at least one error/reason")
            if recall is not None:
                _fail("BLOCKED_RECALL_FORBIDDEN", "BLOCKED cannot assert recall")
        else:
            allowed_stops = {"provider_failure", "integrity_failure", "invalid_response"}
            if not errors:
                _fail("FAILURE_REASON_REQUIRED", "FAILED requires at least one error")
            if recall is not None:
                _fail("FAILED_RECALL_FORBIDDEN", "FAILED cannot assert recall")
        if stop not in allowed_stops:
            _fail("STOP_REASON_STATE_MISMATCH", f"{state.value} is incompatible with stop_reason {stop!r}")

    if check_hash:
        asserted = _hash(payload["receipt_hash"], "receipt_hash")
        if asserted != _hash_excluding(payload, "receipt_hash"):
            _fail("RECEIPT_HASH_MISMATCH", "receipt_hash does not match canonical receipt content")


def validate_search_lane_receipt(payload: Mapping[str, object]) -> SealedArtifact:
    value = _mapping(payload, "SearchLaneReceipt")
    _validate_receipt_shape(value, check_hash=True)
    return _sealed("SearchLaneReceipt", value)


_STATE_PRECEDENCE: Final = (
    SearchState.FAILED.value,
    SearchState.BLOCKED.value,
    SearchState.PARTIAL.value,
    SearchState.SEARCHED_WITH_RESULTS.value,
    SearchState.SEARCHED_NONE.value,
)


def _reconciled_state(states: Sequence[str]) -> str:
    for state in _STATE_PRECEDENCE:
        if state in states:
            return state
    _fail("LANE_RECONCILIATION_INVALID", "selected lane has no executed state")


def _scope_id(lane: str, scope: Mapping[str, object]) -> str:
    return f"lane:{lane}:scope:{_digest(scope)}"


def _completion_state(work_class: str, reconciled: Mapping[str, str], selected: Sequence[str]) -> str:
    if work_class == "E0":
        return "NOT_REQUIRED"
    states = {reconciled[lane] for lane in selected}
    if SearchState.FAILED.value in states:
        return "FAIL"
    if SearchState.BLOCKED.value in states:
        return "BLOCKED"
    if SearchState.PARTIAL.value in states:
        return "PARTIAL"
    return "PASS"


def _claim_ceilings(
    completion: str,
    reconciliations: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    executed = {
        str(row["lane"]): str(row["reconciled_state"])
        for row in reconciliations
        if row["reconciled_state"]
        in {
            SearchState.SEARCHED_NONE.value,
            SearchState.SEARCHED_WITH_RESULTS.value,
            SearchState.PARTIAL.value,
        }
    }
    if not executed:
        absence = "NONE"
    elif completion == "PASS" and Lane.EXTERNAL_NOVELTY.value in executed:
        absence = "EXTERNAL_CONDITIONAL"
    elif completion == "PASS":
        absence = "CORPUS_CONDITIONAL"
    else:
        absence = "LOCAL_CORPUS_ONLY"

    novelty_state = next(
        (
            str(row["reconciled_state"])
            for row in reconciliations
            if row["lane"] == Lane.EXTERNAL_NOVELTY.value
        ),
        SearchState.UNSEARCHED.value,
    )
    if novelty_state == SearchState.SEARCHED_WITH_RESULTS.value:
        novelty = "PRIOR_ART_FOUND"
    elif novelty_state == SearchState.SEARCHED_NONE.value:
        novelty = "SEARCH_CONDITIONAL"
    elif novelty_state == SearchState.PARTIAL.value:
        novelty = "CORPUS_NOVEL_ONLY"
    else:
        novelty = "NOT_ASSESSED"
    return absence, novelty


def reconcile_search_run(
    query_plan: Mapping[str, object] | SealedArtifact,
    receipts: Sequence[Mapping[str, object] | SealedArtifact],
    *,
    certificate_id: str,
    run_id: str,
    subject_ref: str,
    generated_at: str,
) -> SealedArtifact:
    """Reconcile exactly eleven lanes and seal a completeness certificate."""

    plan = validate_query_plan(_artifact_payload(query_plan, "query_plan")).payload
    certificate_id = _text(certificate_id, "certificate_id")
    run_id = _text(run_id, "run_id")
    subject_ref = _text(subject_ref, "subject_ref")
    generated_at = _timestamp(generated_at, "generated_at")
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", "receipts must be an array")

    validated: list[dict[str, object]] = []
    ids: set[str] = set()
    by_lane: dict[str, list[dict[str, object]]] = {lane: [] for lane in CANONICAL_LANES}
    for index, receipt in enumerate(receipts):
        value = validate_search_lane_receipt(_artifact_payload(receipt, f"receipts[{index}]")).payload
        receipt_id = str(value["receipt_id"])
        if receipt_id in ids:
            _fail("RECEIPT_ID_DUPLICATE", f"duplicate receipt_id {receipt_id}")
        ids.add(receipt_id)
        if value["run_id"] != run_id:
            _fail("RECEIPT_RUN_MISMATCH", "all receipts must bind the reconciled run_id")
        _validate_receipt_plan_binding(value, plan)
        lane = str(value["lane"])
        by_lane[lane].append(value)
        validated.append(value)

    decisions = {str(row["lane"]): row for row in plan["lane_decisions"]}  # type: ignore[union-attr]
    selected = list(plan["required_lanes"])  # type: ignore[arg-type]
    reconciliations: list[dict[str, object]] = []
    reconciled_states: dict[str, str] = {}
    completed: list[str] = []
    partial: list[str] = []
    blocked: list[str] = []
    failed: list[str] = []
    unsearched: list[str] = []
    searched_scope: set[str] = set()
    unsearched_scope: set[str] = set()
    known_failures: set[str] = set()
    plan_scopes = [_mapping(scope, "scope_partitions[]") for scope in plan["scope_partitions"]]  # type: ignore[arg-type]

    for lane in CANONICAL_LANES:
        lane_receipts = sorted(by_lane[lane], key=lambda item: str(item["receipt_id"]))
        decision = decisions[lane]
        lane_selected = lane in selected
        evidence = list(decision["evidence_ids"])  # type: ignore[arg-type]
        if lane_selected:
            if not lane_receipts:
                _fail("LANE_RECONCILIATION_MISSING", f"selected lane {lane} has no execution receipt")
            if any(row["search_state"] == SearchState.UNSEARCHED.value for row in lane_receipts):
                _fail("SELECTED_LANE_UNSEARCHED", f"selected lane {lane} cannot use UNSEARCHED")
            if any(row["receipt_kind"] != "EXECUTION" for row in lane_receipts):
                _fail("LANE_SENTINEL_EXECUTION_CONFLICT", f"selected lane {lane} contains a sentinel")
        else:
            if len(lane_receipts) != 1:
                _fail("UNSEARCHED_SENTINEL_COUNT", f"unselected lane {lane} requires exactly one sentinel")
            row = lane_receipts[0]
            if row["search_state"] != SearchState.UNSEARCHED.value or row["receipt_kind"] != "SENTINEL":
                _fail("UNSELECTED_LANE_EXECUTED", f"unselected lane {lane} must have one UNSEARCHED sentinel")
            if row["sentinel_reason"] != decision["disposition"]:
                _fail("SENTINEL_REASON_MISMATCH", f"sentinel reason for {lane} differs from the plan")
        for row in lane_receipts:
            if list(row["lane_decision_evidence_ids"]) != evidence:  # type: ignore[arg-type]
                _fail("LANE_DECISION_EVIDENCE_MISMATCH", f"receipt for {lane} does not bind plan evidence")

        states = sorted(
            {str(row["search_state"]) for row in lane_receipts},
            key=lambda state: (SearchState.UNSEARCHED.value != state, _STATE_PRECEDENCE.index(state) if state in _STATE_PRECEDENCE else -1),
        )
        reconciled = SearchState.UNSEARCHED.value if not lane_selected else _reconciled_state(states)
        reconciled_states[lane] = reconciled
        executed_ids: set[str] = set()
        unsearched_ids: set[str] = set()
        for row in lane_receipts:
            state = str(row["search_state"])
            scope = row["scope_filter"]
            if state in {
                SearchState.SEARCHED_NONE.value,
                SearchState.SEARCHED_WITH_RESULTS.value,
                SearchState.PARTIAL.value,
            } and isinstance(scope, Mapping):
                identifier = _scope_id(lane, scope)
                executed_ids.add(identifier)
                searched_scope.add(identifier)
            elif isinstance(scope, Mapping):
                identifier = _scope_id(lane, scope)
                unsearched_ids.add(identifier)
                unsearched_scope.add(identifier)
            else:
                for plan_scope in plan_scopes:
                    identifier = _scope_id(lane, plan_scope)
                    unsearched_ids.add(identifier)
                    unsearched_scope.add(identifier)
            if state in {SearchState.PARTIAL.value, SearchState.BLOCKED.value, SearchState.FAILED.value}:
                row_errors = list(row["errors"])  # type: ignore[arg-type]
                if row_errors:
                    known_failures.update(f"{lane}:{state}:{error}" for error in row_errors)
                else:
                    known_failures.add(f"{lane}:{state}:{row['stop_reason']}")

        if reconciled in {SearchState.SEARCHED_NONE.value, SearchState.SEARCHED_WITH_RESULTS.value}:
            completed.append(lane)
        elif reconciled == SearchState.PARTIAL.value:
            partial.append(lane)
        elif reconciled == SearchState.BLOCKED.value:
            blocked.append(lane)
        elif reconciled == SearchState.FAILED.value:
            failed.append(lane)
        else:
            unsearched.append(lane)
        reconciliations.append(
            {
                "lane": lane,
                "selected": lane_selected,
                "plan_disposition": decision["disposition"],
                "receipt_ids": [str(row["receipt_id"]) for row in lane_receipts],
                "receipt_states": states,
                "reconciled_state": reconciled,
                "executed_scope_ids": sorted(executed_ids),
                "unsearched_scope_ids": sorted(unsearched_ids),
            }
        )

    completion = _completion_state(str(plan["work_class"]), reconciled_states, selected)
    absence, novelty = _claim_ceilings(completion, reconciliations)
    ordered_receipts = sorted(
        validated,
        key=lambda row: (_LANE_RANK[str(row["lane"])], str(row["receipt_id"])),
    )
    certificate: dict[str, object] = {
        "certificate_id": certificate_id,
        "run_id": run_id,
        "subject_ref": subject_ref,
        "query_plan_id": plan["query_plan_id"],
        "plan_hash": plan["plan_hash"],
        "work_class": plan["work_class"],
        "required_lanes": selected,
        "lane_receipt_ids": [str(row["receipt_id"]) for row in ordered_receipts],
        "lane_reconciliations": reconciliations,
        "completed_lanes": completed,
        "partial_lanes": partial,
        "blocked_lanes": blocked,
        "failed_lanes": failed,
        "unsearched_lanes": unsearched,
        "searched_scope": sorted(searched_scope),
        "unsearched_scope": sorted(unsearched_scope),
        "completion_state": completion,
        "absence_claim_ceiling": absence,
        "novelty_claim_ceiling": novelty,
        "known_failures": sorted(known_failures),
        "generated_at": generated_at,
    }
    certificate["certificate_hash"] = _hash_excluding(certificate, "certificate_hash")
    return _validate_certificate_shape(certificate)


def _validate_certificate_shape(payload: Mapping[str, object]) -> SealedArtifact:
    _exact_fields(payload, _CERTIFICATE_FIELDS, "SearchCompletenessCertificate")
    for field in ("certificate_id", "run_id", "subject_ref", "query_plan_id"):
        _text(payload[field], field)
    _hash(payload["plan_hash"], "plan_hash")
    _work_class(payload["work_class"])
    _lanes(payload["required_lanes"], "required_lanes")
    _strings(payload["lane_receipt_ids"], "lane_receipt_ids", allow_empty=False)
    for field in ("completed_lanes", "partial_lanes", "blocked_lanes", "failed_lanes", "unsearched_lanes"):
        _lanes(payload[field], field)
    _strings(payload["searched_scope"], "searched_scope")
    _strings(payload["unsearched_scope"], "unsearched_scope")
    _strings(payload["known_failures"], "known_failures")
    _timestamp(payload["generated_at"], "generated_at")
    asserted = _hash(payload["certificate_hash"], "certificate_hash")
    if asserted != _hash_excluding(payload, "certificate_hash"):
        _fail("CERTIFICATE_HASH_MISMATCH", "certificate_hash does not match canonical content")
    reconciliations = payload["lane_reconciliations"]
    if not isinstance(reconciliations, Sequence) or isinstance(reconciliations, (str, bytes, bytearray)) or len(reconciliations) != 11:
        _fail("LANE_RECONCILIATION_COUNT", "certificate must reconcile exactly eleven lanes")
    for lane, row in zip(CANONICAL_LANES, reconciliations, strict=True):
        mapping = _mapping(row, f"lane_reconciliations.{lane}")
        if mapping.get("lane") != lane:
            _fail("LANE_ORDER_INVALID", "certificate reconciliation order is not canonical")
    return _sealed("SearchCompletenessCertificate", payload)


def validate_search_completeness_certificate(
    query_plan: Mapping[str, object] | SealedArtifact,
    receipts: Sequence[Mapping[str, object] | SealedArtifact],
    certificate: Mapping[str, object],
) -> SealedArtifact:
    """Recompute a certificate from its bound plan/receipts and require identity."""

    asserted = _mapping(certificate, "SearchCompletenessCertificate")
    _validate_certificate_shape(asserted)
    rebuilt = reconcile_search_run(
        query_plan,
        receipts,
        certificate_id=_text(asserted["certificate_id"], "certificate_id"),
        run_id=_text(asserted["run_id"], "run_id"),
        subject_ref=_text(asserted["subject_ref"], "subject_ref"),
        generated_at=_timestamp(asserted["generated_at"], "generated_at"),
    )
    if rebuilt.canonical_bytes != _canonical_json(asserted):
        _fail("CERTIFICATE_RECONCILIATION_MISMATCH", "certificate is not the deterministic plan/receipt reconciliation")
    return rebuilt
