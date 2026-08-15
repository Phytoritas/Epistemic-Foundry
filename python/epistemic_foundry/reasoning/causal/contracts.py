"""R04 deterministic causal identification and ArgumentGraph gate contracts.

Identification is derived here, never declared.  The caller supplies a
MechanismGraph, what it adjusted for, and what it conditioned on; the engine
assesses confounding, collider conditioning, and temporal order, and computes
the identification status those assessments actually support.  A declared
status stronger than the derived one is an overclaim and is refused.

The three inference modes stay separate.  An inductive association from R01, a
deductive trace from R02, and an unresolved aporia from R03 each contribute
their own verdict to the gate and none of them is allowed to stand in for
identification.  A live competing explanation caps the result below
``IDENTIFIED`` no matter how strong the association is, and a payload that
merges the modes into one score is refused rather than scored.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from ..deduction.contracts import TraceStatus
from ..induction.contracts import CAUSAL_IDENTIFICATION, SynthesisStatus

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class NodeRole(str, Enum):
    """Canonical MechanismGraph roles (schemas/mechanism-graph.schema.json)."""

    CAUSE = "cause"
    MEDIATOR = "mediator"
    MODERATOR = "moderator"
    OUTCOME = "outcome"
    CONFOUNDER = "confounder"
    MEASUREMENT = "measurement"


class Relation(str, Enum):
    CAUSES = "causes"
    MEDIATES = "mediates"
    MODERATES = "moderates"
    INHIBITS = "inhibits"
    ENABLES = "enables"
    CORRELATES = "correlates"
    MEASURES = "measures"


class Sign(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class Identification(str, Enum):
    """Canonical identification ladder, weakest first."""

    NOT_ASSESSED = "NOT_ASSESSED"
    NOT_IDENTIFIED = "NOT_IDENTIFIED"
    ASSUMPTION_DEPENDENT = "ASSUMPTION_DEPENDENT"
    IDENTIFIED = "IDENTIFIED"


class ConfounderState(str, Enum):
    ADJUSTED = "ADJUSTED"
    UNADJUSTED = "UNADJUSTED"
    UNMEASURED = "UNMEASURED"


class TimeOrderState(str, Enum):
    ESTABLISHED = "ESTABLISHED"
    SIMULTANEOUS = "SIMULTANEOUS"
    UNKNOWN = "UNKNOWN"


class InferenceMode(str, Enum):
    """The three modes the gate keeps apart."""

    INDUCTIVE = "INDUCTIVE"
    DEDUCTIVE = "DEDUCTIVE"
    ABDUCTIVE = "ABDUCTIVE"


NODE_ROLES: Final = tuple(entry.value for entry in NodeRole)
RELATIONS: Final = tuple(entry.value for entry in Relation)
SIGNS: Final = tuple(entry.value for entry in Sign)
INFERENCE_MODES: Final = tuple(entry.value for entry in InferenceMode)
#: Weakest to strongest; a declared status above the derived one is an overclaim.
IDENTIFICATION_LADDER: Final = (
    Identification.NOT_ASSESSED.value,
    Identification.NOT_IDENTIFIED.value,
    Identification.ASSUMPTION_DEPENDENT.value,
    Identification.IDENTIFIED.value,
)
#: Every assessment the exit criterion requires; a missing one fails closed.
REQUIRED_ASSESSMENTS: Final = ("collider", "confounding", "time_order")
#: Explicit non-establishing lag labels.  The schema currently authorizes no
#: positive lag grammar, so every other raw string also remains UNKNOWN.
NON_ESTABLISHING_LAGS: Final = ("unknown", "simultaneous", "none", "not_reported")
#: Relations that carry causal force and therefore need temporal order.
CAUSAL_RELATIONS: Final = (Relation.CAUSES.value, Relation.INHIBITS.value)

GRAPH_FIELDS: Final = frozenset(
    {
        "mechanism_graph_id",
        "nodes",
        "edges",
        "assumptions",
        "identification_status",
        "graph_hash",
    }
)
_NODE_FIELDS: Final = frozenset({"node_id", "concept_id", "role"})
_EDGE_FIELDS: Final = frozenset(
    {"edge_id", "source", "target", "relation", "sign", "lag"}
)
MODE_VERDICT_FIELDS: Final = frozenset({"mode", "artifact_id", "verdict", "detail"})
_INDUCTIVE_DETAIL_FIELDS: Final = frozenset({"causal_identification", "status"})
_DEDUCTIVE_DETAIL_FIELDS: Final = frozenset({"status"})
_ABDUCTIVE_DETAIL_FIELDS: Final = frozenset(
    {"selected_explanation_id", "standing_conflict_count"}
)
_ASSESSMENT_BINDING_FIELDS: Final = frozenset(
    {"assessment", "mechanism_graph_hash", "mechanism_graph_id", "satisfied"}
)
_CONFOUNDING_ASSESSMENT_FIELDS: Final = _ASSESSMENT_BINDING_FIELDS | frozenset(
    {"confounder_states", "open_confounder_ids"}
)
_COLLIDER_ASSESSMENT_FIELDS: Final = _ASSESSMENT_BINDING_FIELDS | frozenset(
    {"collider_ids", "conditioned_collider_ids"}
)
_TIME_ORDER_ASSESSMENT_FIELDS: Final = _ASSESSMENT_BINDING_FIELDS | frozenset(
    {"edge_states", "unestablished_edge_ids"}
)
GATE_FIELDS: Final = frozenset(
    {
        "gate_id",
        "mechanism_graph_hash",
        "mechanism_graph_id",
        "subject_id",
        "created_at",
        "identification_status",
        "declared_identification_status",
        "assessments",
        "mode_verdicts",
        "identification_ceiling",
        "ceiling_reasons",
        "assumptions",
        "argument_graph_id",
        "gate_hash",
    }
)


class CausalGateError(ValueError):
    """Typed fail-closed R04 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise CausalGateError(code, message, context)


@dataclass(frozen=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed artifact is not an object")
        return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail("CANONICALIZATION_FAILED", f"value is not canonical JSON: {error}")
        raise  # pragma: no cover - _fail always raises


def _json_snapshot(
    value: object,
    label: str,
    memo: dict[int, object],
    active: set[int],
) -> object:
    """Detach caller-owned JSON without invoking coercion hooks."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, int):
        return int.__int__(value)
    if isinstance(value, float):
        plain = float.__float__(value)
        if not math.isfinite(plain):
            _fail("CANONICALIZATION_FAILED", f"{label} contains a non-finite number")
        return plain
    if isinstance(value, (bytes, bytearray, memoryview)):
        _fail("CANONICALIZATION_FAILED", f"{label} contains a byte-like value")
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            _fail("CANONICALIZATION_FAILED", f"{label} contains a cycle")
        if identity in memo:
            return memo[identity]
        detached: dict[str, object] = {}
        memo[identity] = detached
        active.add(identity)
        try:
            for key, entry in value.items():
                if not isinstance(key, str):
                    _fail("INPUT_INVALID", f"{label} keys must be strings")
                plain_key = str.__str__(key)
                if plain_key in detached:
                    _fail("INPUT_INVALID", f"{label} keys must be unique")
                detached[plain_key] = _json_snapshot(
                    entry, f"{label}.{plain_key}", memo, active
                )
        finally:
            active.remove(identity)
        return detached
    if isinstance(value, Sequence):
        identity = id(value)
        if identity in active:
            _fail("CANONICALIZATION_FAILED", f"{label} contains a cycle")
        if identity in memo:
            return memo[identity]
        detached_list: list[object] = []
        memo[identity] = detached_list
        active.add(identity)
        try:
            for index, entry in enumerate(value):
                detached_list.append(
                    _json_snapshot(entry, f"{label}[{index}]", memo, active)
                )
        finally:
            active.remove(identity)
        return detached_list
    _fail("CANONICALIZATION_FAILED", f"{label} contains a non-JSON value")


def _detached_json_object(value: object, label: str) -> dict[str, Any]:
    detached = _json_snapshot(value, label, {}, set())
    if type(detached) is not dict:
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    _canonical_json(detached)
    return detached


def _detached_json_array(value: object, label: str) -> list[Any]:
    detached = _json_snapshot(value, label, {}, set())
    if type(detached) is not list:
        _fail("INPUT_INVALID", f"{label} must be an array")
    _canonical_json(detached)
    return detached


def _hex_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _digest(value: object) -> str:
    return "sha256:" + _hex_digest(value)


def _hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings")
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    return list(value)  # type: ignore[arg-type]


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"missing": missing, "unknown": unknown},
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str.__str__(value)


def _string_array(value: object, label: str) -> list[str]:
    return [
        _text(entry, f"{label}[{index}]")
        for index, entry in enumerate(_sequence(value, label))
    ]


def _detached_string_set(value: object, label: str) -> tuple[str, ...]:
    detached = _detached_json_array(value, label)
    return tuple(sorted(set(_string_array(detached, label))))


def _month_length(year: int, month: int) -> int:
    leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return (
        31,
        29 if leap_year else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    )[month - 1]


def _shift_calendar_day(
    year: int, month: int, day: int, day_delta: int
) -> tuple[int, int, int]:
    while day_delta > 0:
        day += 1
        if day > _month_length(year, month):
            day = 1
            month += 1
            if month > 12:
                month = 1
                year += 1
        day_delta -= 1
    while day_delta < 0:
        day -= 1
        if day < 1:
            month -= 1
            if month < 1:
                month = 12
                year -= 1
            day = _month_length(year, month)
        day_delta += 1
    return year, month, day


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if (
        month < 1
        or month > 12
        or day < 1
        or day > _month_length(year, month)
        or hour > 23
        or minute > 59
        or second > 60
    ):
        _fail("INPUT_INVALID", f"{label} must be a real RFC3339 timestamp")
    offset_minutes = 0
    if not text.endswith("Z"):
        offset_hour = int(text[-5:-3])
        offset_minute = int(text[-2:])
        if offset_hour > 23 or offset_minute > 59:
            _fail("INPUT_INVALID", f"{label} must be a real RFC3339 timestamp")
        offset_minutes = offset_hour * 60 + offset_minute
        if text[-6] == "-":
            offset_minutes = -offset_minutes
    if second == 60:
        utc_day_delta, utc_minute = divmod(
            hour * 60 + minute - offset_minutes,
            1440,
        )
        utc_year, utc_month, utc_day = _shift_calendar_day(
            year,
            month,
            day,
            utc_day_delta,
        )
        if utc_minute != 1439 or utc_day != _month_length(utc_year, utc_month):
            _fail(
                "INPUT_INVALID",
                f"{label} leap second must be at a UTC month end",
            )
    return text


def _validate_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _detached_json_object(payload, "MechanismGraph")
    return _validate_detached_graph(value)


def _validate_detached_graph(value: Mapping[str, Any]) -> dict[str, Any]:
    _exact_fields(value, GRAPH_FIELDS, "MechanismGraph")
    graph_id = _text(value["mechanism_graph_id"], "mechanism_graph_id")
    nodes: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(_sequence(value["nodes"], "nodes")):
        node = _mapping(entry, f"nodes[{index}]")
        _exact_fields(node, _NODE_FIELDS, f"nodes[{index}]")
        node_id = _text(node["node_id"], "node_id")
        if node["role"] not in NODE_ROLES:
            _fail("NODE_ROLE_INVALID", f"{node_id} has a non-canonical role")
        if node_id in nodes:
            _fail("DUPLICATE_NODE", "node ids must be unique", {"node_id": node_id})
        nodes[node_id] = {
            "concept_id": _text(node["concept_id"], "concept_id"),
            "node_id": node_id,
            "role": str(node["role"]),
        }
    if not nodes:
        _fail("INPUT_INVALID", "a MechanismGraph must declare at least one node")
    edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    for index, entry in enumerate(_sequence(value["edges"], "edges")):
        edge = _mapping(entry, f"edges[{index}]")
        _exact_fields(edge, _EDGE_FIELDS, f"edges[{index}]")
        edge_id = _text(edge["edge_id"], "edge_id")
        if edge_id in edge_ids:
            _fail("DUPLICATE_EDGE", "edge ids must be unique", {"edge_id": edge_id})
        edge_ids.add(edge_id)
        source = _text(edge["source"], "source")
        target = _text(edge["target"], "target")
        for endpoint in (source, target):
            if endpoint not in nodes:
                _fail(
                    "EDGE_UNRESOLVED",
                    "an edge endpoint must reference a declared node",
                    {"edge_id": edge_id, "node_id": endpoint},
                )
        if edge["relation"] not in RELATIONS:
            _fail("RELATION_INVALID", f"{edge_id} has a non-canonical relation")
        if edge["sign"] not in SIGNS:
            _fail("SIGN_INVALID", f"{edge_id} has a non-canonical sign")
        edges.append(
            {
                "edge_id": edge_id,
                "lag": _text(edge["lag"], "lag"),
                "relation": str(edge["relation"]),
                "sign": str(edge["sign"]),
                "source": source,
                "target": target,
            }
        )
    if not edges:
        _fail("INPUT_INVALID", "a MechanismGraph must declare at least one edge")
    if value["identification_status"] not in IDENTIFICATION_LADDER:
        _fail("INPUT_INVALID", "identification_status is not canonical")
    graph_hash = _text(value["graph_hash"], "graph_hash")
    if SHA256_PATTERN.fullmatch(graph_hash) is None:
        _fail("INPUT_INVALID", "graph_hash must be a sha256 digest")
    if _hash_excluding(value, "graph_hash") != graph_hash:
        _fail("GRAPH_HASH_MISMATCH", "graph_hash does not match its content")
    return {
        "assumptions": sorted(
            {
                _text(entry, "assumption")
                for entry in _sequence(value["assumptions"], "assumptions")
            }
        ),
        "declared_identification_status": str(value["identification_status"]),
        "edges": edges,
        "graph_hash": graph_hash,
        "mechanism_graph_id": graph_id,
        "nodes": nodes,
    }


def assess_confounding(
    graph: Mapping[str, Any],
    adjustment_set: Sequence[str],
    unmeasured: Sequence[str] = (),
) -> dict[str, Any]:
    """Every declared confounder's adjustment state, and whether any is open.

    A confounder is open when it is neither adjusted for nor honestly declared
    unmeasured, because silence about a known backdoor is the failure mode this
    assessment exists to catch.
    """

    adjusted = set(_string_array(adjustment_set, "adjustment_set"))
    unmeasured_set = set(_string_array(unmeasured, "unmeasured_confounders"))
    node_ids = set(graph["nodes"])
    unknown_adjustments = sorted(adjusted - node_ids)
    unknown_unmeasured = sorted(unmeasured_set - node_ids)
    if unknown_adjustments or unknown_unmeasured:
        _fail(
            "ADJUSTMENT_UNRESOLVED",
            "confounder assessment identifiers must reference declared nodes",
            {
                "adjustment_node_ids": unknown_adjustments,
                "unmeasured_node_ids": unknown_unmeasured,
            },
        )
    non_confounders = sorted(
        node_id
        for node_id in unmeasured_set
        if graph["nodes"][node_id]["role"] != NodeRole.CONFOUNDER.value
    )
    if non_confounders:
        _fail(
            "ADJUSTMENT_UNRESOLVED",
            "unmeasured confounder identifiers must name confounder nodes",
            {"unmeasured_node_ids": non_confounders},
        )
    contradictory = sorted(adjusted & unmeasured_set)
    if contradictory:
        _fail(
            "INPUT_INVALID",
            "a confounder cannot be both adjusted and unmeasured",
            {"node_ids": contradictory},
        )
    states: dict[str, str] = {}
    for node_id, node in sorted(graph["nodes"].items()):
        if node["role"] != NodeRole.CONFOUNDER.value:
            continue
        if node_id in unmeasured_set:
            states[node_id] = ConfounderState.UNMEASURED.value
        elif node_id in adjusted:
            states[node_id] = ConfounderState.ADJUSTED.value
        else:
            states[node_id] = ConfounderState.UNADJUSTED.value
    open_confounders = sorted(
        node_id
        for node_id, state in states.items()
        if state != ConfounderState.ADJUSTED.value
    )
    return {
        "assessment": "confounding",
        "confounder_states": states,
        "mechanism_graph_hash": graph["graph_hash"],
        "mechanism_graph_id": graph["mechanism_graph_id"],
        "open_confounder_ids": open_confounders,
        "satisfied": not open_confounders,
    }


def assess_colliders(
    graph: Mapping[str, Any], conditioned_on: Sequence[str]
) -> dict[str, Any]:
    """Colliders in the graph, and any that conditioning has opened.

    Conditioning on a collider induces association between its causes, so it is
    reported as a distinct failure rather than folded into confounding.
    """

    incoming: dict[str, list[str]] = {node_id: [] for node_id in graph["nodes"]}
    for edge in graph["edges"]:
        if edge["relation"] in CAUSAL_RELATIONS:
            incoming[edge["target"]].append(edge["source"])
    colliders = sorted(
        node_id for node_id, sources in incoming.items() if len(set(sources)) >= 2
    )
    conditioned = set(_string_array(conditioned_on, "conditioned_on"))
    unknown = sorted(conditioned - set(graph["nodes"]))
    if unknown:
        _fail(
            "CONDITIONING_UNRESOLVED",
            "the conditioning set must reference declared nodes",
            {"node_ids": unknown},
        )
    opened = sorted(set(colliders) & conditioned)
    return {
        "assessment": "collider",
        "collider_ids": colliders,
        "conditioned_collider_ids": opened,
        "mechanism_graph_hash": graph["graph_hash"],
        "mechanism_graph_id": graph["mechanism_graph_id"],
        "satisfied": not opened,
    }


def assess_time_order(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Whether every causal edge establishes that its cause precedes its effect."""

    states: dict[str, str] = {}
    for edge in sorted(graph["edges"], key=lambda entry: str(entry["edge_id"])):
        if edge["relation"] not in CAUSAL_RELATIONS:
            continue
        lag = str(edge["lag"]).strip().lower()
        states[str(edge["edge_id"])] = (
            TimeOrderState.SIMULTANEOUS.value
            if lag == "simultaneous"
            else TimeOrderState.UNKNOWN.value
        )
    unestablished = sorted(
        edge_id
        for edge_id, state in states.items()
        if state != TimeOrderState.ESTABLISHED.value
    )
    return {
        "assessment": "time_order",
        "edge_states": states,
        "mechanism_graph_hash": graph["graph_hash"],
        "mechanism_graph_id": graph["mechanism_graph_id"],
        "satisfied": bool(states) and not unestablished,
        "unestablished_edge_ids": unestablished,
    }


def _validate_mode_verdict(value: object, index: int) -> dict[str, Any]:
    verdict = _mapping(value, f"mode_verdicts[{index}]")
    _exact_fields(verdict, MODE_VERDICT_FIELDS, f"mode_verdicts[{index}]")
    mode = _text(verdict["mode"], "mode")
    if mode not in INFERENCE_MODES:
        _fail(
            "MODE_INVALID",
            "mode must be one of the three canonical inference modes",
            {"value": mode},
        )
    artifact_id = _text(verdict["artifact_id"], "artifact_id")
    detail = _mapping(verdict["detail"], "detail")
    if mode == InferenceMode.INDUCTIVE.value:
        _exact_fields(detail, _INDUCTIVE_DETAIL_FIELDS, "inductive detail")
        if detail["causal_identification"] != CAUSAL_IDENTIFICATION:
            _fail(
                "MODE_COLLAPSE",
                "an inductive synthesis may not carry a causal verdict",
                {"artifact_id": artifact_id},
            )
        if detail["status"] not in tuple(item.value for item in SynthesisStatus):
            _fail("INPUT_INVALID", "inductive status is not canonical")
    elif mode == InferenceMode.DEDUCTIVE.value:
        _exact_fields(detail, _DEDUCTIVE_DETAIL_FIELDS, "deductive detail")
        if detail["status"] not in tuple(item.value for item in TraceStatus):
            _fail("INPUT_INVALID", "deductive status is not canonical")
    else:
        _exact_fields(detail, _ABDUCTIVE_DETAIL_FIELDS, "abductive detail")
        if detail["selected_explanation_id"] is not None:
            _fail(
                "MODE_COLLAPSE",
                "an aporia record may not arrive with an explanation selected",
                {"artifact_id": artifact_id},
            )
        count = detail["standing_conflict_count"]
        if type(count) is not int or count < 0:
            _fail(
                "INPUT_INVALID",
                "standing_conflict_count must be a non-negative integer",
            )
    return {
        "artifact_id": artifact_id,
        "detail": detail,
        "mode": mode,
        "verdict": _text(verdict["verdict"], "verdict"),
    }


def _validated_mode_verdicts(value: object) -> list[dict[str, Any]]:
    seen: set[str] = set()
    verdicts: list[dict[str, Any]] = []
    for index, entry in enumerate(_sequence(value, "mode_verdicts")):
        verdict = _validate_mode_verdict(entry, index)
        if verdict["mode"] in seen:
            _fail(
                "MODE_DUPLICATED",
                "each inference mode contributes exactly one verdict",
                {"mode": verdict["mode"]},
            )
        seen.add(verdict["mode"])
        verdicts.append(verdict)
    absent = sorted(set(INFERENCE_MODES) - seen)
    if absent:
        _fail(
            "MODE_MISSING",
            "the gate requires a separate verdict from every inference mode",
            {"modes": absent},
        )
    return sorted(verdicts, key=lambda entry: entry["mode"])


def _identification_ceiling_from_validated(
    mode_verdicts: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    ceiling = Identification.IDENTIFIED.value
    reasons: list[str] = []
    for verdict in mode_verdicts:
        mode = verdict["mode"]
        detail = verdict["detail"]
        if mode == InferenceMode.INDUCTIVE.value:
            if detail["status"] != SynthesisStatus.COMPLETE.value:
                ceiling = Identification.ASSUMPTION_DEPENDENT.value
                reasons.append("inductive synthesis is not complete")
        elif mode == InferenceMode.DEDUCTIVE.value:
            status = detail["status"]
            if status == TraceStatus.BROKEN.value:
                ceiling = Identification.NOT_IDENTIFIED.value
                reasons.append("the deductive trace rests on rejected support")
            elif status == TraceStatus.CONDITIONAL.value:
                if ceiling == Identification.IDENTIFIED.value:
                    ceiling = Identification.ASSUMPTION_DEPENDENT.value
                reasons.append("the deductive trace depends on ledgered assumptions")
        elif detail["standing_conflict_count"] > 0:
            if ceiling == Identification.IDENTIFIED.value:
                ceiling = Identification.ASSUMPTION_DEPENDENT.value
            reasons.append(
                f"{detail['standing_conflict_count']} conflict(s) still carry "
                "competing explanations"
            )
    return ceiling, sorted(set(reasons))


def identification_ceiling(
    mode_verdicts: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    """The strongest identification the separate modes leave available.

    No mode can raise the ceiling; each can only lower it.  A live competing
    explanation from R03 is the clearest case: while an alternative account of
    the same evidence still stands, the association cannot be the identified
    cause however strong or however deductively tidy it is.
    """

    detached = _detached_json_array(mode_verdicts, "mode_verdicts")
    return _identification_ceiling_from_validated(
        _validated_mode_verdicts(detached)
    )


def _rank(status: str) -> int:
    return IDENTIFICATION_LADDER.index(status)


def _derived_identification(
    assessments: Mapping[str, Mapping[str, Any]],
    assumptions: Sequence[str],
    ceiling: str,
) -> tuple[str, list[str]]:
    failures = sorted(
        name for name, record in assessments.items() if not record["satisfied"]
    )
    if failures:
        derived = Identification.NOT_IDENTIFIED.value
    elif assumptions:
        derived = Identification.ASSUMPTION_DEPENDENT.value
    else:
        derived = Identification.IDENTIFIED.value
    if _rank(ceiling) < _rank(derived):
        derived = ceiling
    return derived, failures


def _gate_id(payload: Mapping[str, Any]) -> str:
    return "CG-" + _hex_digest(
        {
            "assessments": payload["assessments"],
            "created_at": payload["created_at"],
            "graph_hash": payload["mechanism_graph_hash"],
            "identification_status": payload["identification_status"],
            "subject_id": payload["subject_id"],
        }
    )


def evaluate_causal_gate(
    graph: Mapping[str, Any],
    mode_verdicts: Sequence[Mapping[str, Any]],
    *,
    subject_id: str,
    argument_graph_id: str,
    created_at: str,
    adjustment_set: Sequence[str] = (),
    conditioned_on: Sequence[str] = (),
    unmeasured_confounders: Sequence[str] = (),
) -> SealedArtifact:
    """Derive identification from the assessments and the separated modes."""

    subject_id = _text(_json_snapshot(subject_id, "subject_id", {}, set()), "subject_id")
    argument_graph_id = _text(
        _json_snapshot(argument_graph_id, "argument_graph_id", {}, set()),
        "argument_graph_id",
    )
    created_at = _timestamp(
        _json_snapshot(created_at, "created_at", {}, set()), "created_at"
    )
    validated = _validate_graph(graph)
    adjustment_ids = _detached_string_set(adjustment_set, "adjustment_set")
    conditioned_ids = _detached_string_set(conditioned_on, "conditioned_on")
    unmeasured_ids = _detached_string_set(
        unmeasured_confounders, "unmeasured_confounders"
    )
    detached_modes = _detached_json_array(mode_verdicts, "mode_verdicts")

    assessments = {
        "collider": assess_colliders(validated, conditioned_ids),
        "confounding": assess_confounding(
            validated, adjustment_ids, unmeasured_ids
        ),
        "time_order": assess_time_order(validated),
    }
    missing = sorted(set(REQUIRED_ASSESSMENTS) - set(assessments))
    if missing:  # pragma: no cover - constructed above, kept as a live guard
        _fail(
            "ASSESSMENT_INCOMPLETE",
            "colliders, confounders, and time order must all be assessed",
            {"missing": missing},
        )

    verdicts = _validated_mode_verdicts(detached_modes)
    ceiling, ceiling_reasons = _identification_ceiling_from_validated(verdicts)
    derived, failures = _derived_identification(
        assessments, validated["assumptions"], ceiling
    )

    declared = validated["declared_identification_status"]
    if _rank(declared) > _rank(derived):
        _fail(
            "CAUSAL_OVERCLAIM",
            "the declared identification status exceeds what the assessments support",
            {
                "ceiling": ceiling,
                "declared": declared,
                "derived": derived,
                "failed_assessments": failures,
            },
        )

    payload: dict[str, Any] = {
        "argument_graph_id": argument_graph_id,
        "assessments": assessments,
        "assumptions": validated["assumptions"],
        "ceiling_reasons": ceiling_reasons,
        "created_at": created_at,
        "declared_identification_status": declared,
        "identification_ceiling": ceiling,
        "identification_status": derived,
        "mechanism_graph_hash": validated["graph_hash"],
        "mechanism_graph_id": validated["mechanism_graph_id"],
        "mode_verdicts": verdicts,
        "subject_id": subject_id,
    }
    payload["gate_id"] = _gate_id(payload)
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")
    return validate_causal_gate(payload)


def _canonical_string_list(value: object, label: str) -> list[str]:
    entries = _string_array(value, label)
    if entries != sorted(set(entries)):
        _fail("INPUT_INVALID", f"{label} must be sorted and unique")
    return entries


def _validate_assessment_binding(
    record: Mapping[str, Any],
    *,
    name: str,
    mechanism_graph_id: str,
    mechanism_graph_hash: str,
) -> None:
    if record["assessment"] != name:
        _fail("INPUT_INVALID", f"{name} assessment label is not canonical")
    if (
        record["mechanism_graph_id"] != mechanism_graph_id
        or record["mechanism_graph_hash"] != mechanism_graph_hash
    ):
        _fail(
            "ASSESSMENT_BINDING_MISMATCH",
            "an assessment is bound to a different MechanismGraph",
            {"assessment": name},
        )
    if type(record["satisfied"]) is not bool:
        _fail("INPUT_INVALID", f"{name}.satisfied must be a boolean")


def _validate_assessment(
    value: object,
    *,
    name: str,
    mechanism_graph_id: str,
    mechanism_graph_hash: str,
) -> dict[str, Any]:
    record = _mapping(value, f"assessments.{name}")
    expected_fields = {
        "confounding": _CONFOUNDING_ASSESSMENT_FIELDS,
        "collider": _COLLIDER_ASSESSMENT_FIELDS,
        "time_order": _TIME_ORDER_ASSESSMENT_FIELDS,
    }[name]
    _exact_fields(record, expected_fields, f"assessments.{name}")
    _validate_assessment_binding(
        record,
        name=name,
        mechanism_graph_id=mechanism_graph_id,
        mechanism_graph_hash=mechanism_graph_hash,
    )
    if name == "confounding":
        states = _mapping(record["confounder_states"], "confounder_states")
        normalized_states: dict[str, str] = {}
        for node_id, state in states.items():
            node_id = _text(node_id, "confounder_id")
            if state not in tuple(item.value for item in ConfounderState):
                _fail("INPUT_INVALID", "confounder state is not canonical")
            normalized_states[node_id] = state
        opened = _canonical_string_list(
            record["open_confounder_ids"], "open_confounder_ids"
        )
        expected_opened = sorted(
            node_id
            for node_id, state in normalized_states.items()
            if state != ConfounderState.ADJUSTED.value
        )
        if opened != expected_opened or record["satisfied"] != (not opened):
            _fail(
                "ASSESSMENT_INCONSISTENT",
                "confounding assessment state is internally inconsistent",
            )
        record["confounder_states"] = normalized_states
        record["open_confounder_ids"] = opened
    elif name == "collider":
        colliders = _canonical_string_list(record["collider_ids"], "collider_ids")
        conditioned = _canonical_string_list(
            record["conditioned_collider_ids"], "conditioned_collider_ids"
        )
        if not set(conditioned) <= set(colliders) or record["satisfied"] != (
            not conditioned
        ):
            _fail(
                "ASSESSMENT_INCONSISTENT",
                "collider assessment state is internally inconsistent",
            )
        record["collider_ids"] = colliders
        record["conditioned_collider_ids"] = conditioned
    else:
        states = _mapping(record["edge_states"], "edge_states")
        normalized_states: dict[str, str] = {}
        for edge_id, state in states.items():
            edge_id = _text(edge_id, "edge_id")
            if state not in tuple(item.value for item in TimeOrderState):
                _fail("INPUT_INVALID", "time-order state is not canonical")
            if state == TimeOrderState.ESTABLISHED.value:
                _fail(
                    "TIME_ORDER_UNQUALIFIED",
                    "no positive lag grammar currently authorizes established order",
                )
            normalized_states[edge_id] = state
        unestablished = _canonical_string_list(
            record["unestablished_edge_ids"], "unestablished_edge_ids"
        )
        expected_unestablished = sorted(
            edge_id
            for edge_id, state in normalized_states.items()
            if state != TimeOrderState.ESTABLISHED.value
        )
        expected_satisfied = bool(normalized_states) and not unestablished
        if (
            unestablished != expected_unestablished
            or record["satisfied"] != expected_satisfied
        ):
            _fail(
                "ASSESSMENT_INCONSISTENT",
                "time-order assessment state is internally inconsistent",
            )
        record["edge_states"] = normalized_states
        record["unestablished_edge_ids"] = unestablished
    return record


def validate_causal_gate(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one gate record shape, vocabulary, ladder order, and self-hash."""

    value = _detached_json_object(payload, "CausalGate")
    _exact_fields(value, GATE_FIELDS, "CausalGate")
    _text(value["gate_id"], "gate_id")
    mechanism_graph_id = _text(value["mechanism_graph_id"], "mechanism_graph_id")
    mechanism_graph_hash = _text(
        value["mechanism_graph_hash"], "mechanism_graph_hash"
    )
    if SHA256_PATTERN.fullmatch(mechanism_graph_hash) is None:
        _fail("INPUT_INVALID", "mechanism_graph_hash must be a sha256 digest")
    _text(value["subject_id"], "subject_id")
    _text(value["argument_graph_id"], "argument_graph_id")
    _timestamp(value["created_at"], "created_at")
    for field in (
        "identification_status",
        "declared_identification_status",
        "identification_ceiling",
    ):
        if value[field] not in IDENTIFICATION_LADDER:
            _fail("INPUT_INVALID", f"{field} is not a canonical identification status")
    raw_assessments = _mapping(value["assessments"], "assessments")
    if sorted(raw_assessments) != sorted(REQUIRED_ASSESSMENTS):
        _fail(
            "ASSESSMENT_INCOMPLETE",
            "colliders, confounders, and time order must all be assessed",
            {"present": sorted(raw_assessments)},
        )
    assessments = {
        name: _validate_assessment(
            raw_assessments[name],
            name=name,
            mechanism_graph_id=mechanism_graph_id,
            mechanism_graph_hash=mechanism_graph_hash,
        )
        for name in REQUIRED_ASSESSMENTS
    }
    assumptions = _canonical_string_list(value["assumptions"], "assumptions")
    verdicts = _validated_mode_verdicts(value["mode_verdicts"])
    if verdicts != value["mode_verdicts"]:
        _fail("INPUT_INVALID", "mode_verdicts must be sorted canonically")
    expected_ceiling, expected_reasons = _identification_ceiling_from_validated(
        verdicts
    )
    if value["identification_ceiling"] != expected_ceiling:
        _fail("CEILING_MISMATCH", "identification ceiling is not re-derivable")
    reasons = _canonical_string_list(value["ceiling_reasons"], "ceiling_reasons")
    if reasons != expected_reasons:
        _fail("CEILING_MISMATCH", "ceiling reasons are not re-derivable")
    expected_identification, failures = _derived_identification(
        assessments, assumptions, expected_ceiling
    )
    if value["identification_status"] != expected_identification:
        _fail(
            "IDENTIFICATION_STATUS_MISMATCH",
            "identification status is not re-derivable",
            {"expected": expected_identification, "failed_assessments": failures},
        )
    if _rank(value["declared_identification_status"]) > _rank(
        expected_identification
    ):
        _fail(
            "CAUSAL_OVERCLAIM",
            "the declared identification status exceeds the derived one",
        )
    if value["gate_id"] != _gate_id(value):
        _fail(
            "GATE_ID_MISMATCH",
            "gate_id is not bound to the causal gate derivation",
        )
    if _hash_excluding(value, "gate_hash") != value["gate_hash"]:
        _fail("GATE_HASH_MISMATCH", "gate_hash does not match its content")
    return SealedArtifact("CausalGate", _canonical_json(value))


def seal_mechanism_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp a MechanismGraph with its canonical content hash."""

    value = _detached_json_object(payload, "MechanismGraph")
    _exact_fields(value, GRAPH_FIELDS, "MechanismGraph")
    value["graph_hash"] = _hash_excluding(value, "graph_hash")
    _validate_detached_graph(value)
    return value
