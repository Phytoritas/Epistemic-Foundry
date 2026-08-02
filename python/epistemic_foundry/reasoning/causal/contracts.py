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
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

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
#: Lag values that do not establish that the cause precedes the effect.  A
#: blank lag never reaches here: the schema requires a non-empty string.
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
GATE_FIELDS: Final = frozenset(
    {
        "gate_id",
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
    return str(value)


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    return text


def _validate_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(payload, "MechanismGraph")
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
    for index, entry in enumerate(_sequence(value["edges"], "edges")):
        edge = _mapping(entry, f"edges[{index}]")
        _exact_fields(edge, _EDGE_FIELDS, f"edges[{index}]")
        edge_id = _text(edge["edge_id"], "edge_id")
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

    adjusted = set(adjustment_set)
    unmeasured_set = set(unmeasured)
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
    unknown_adjustments = sorted(adjusted - set(graph["nodes"]))
    if unknown_adjustments:
        _fail(
            "ADJUSTMENT_UNRESOLVED",
            "the adjustment set must reference declared nodes",
            {"node_ids": unknown_adjustments},
        )
    return {
        "assessment": "confounding",
        "confounder_states": states,
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
    conditioned = set(conditioned_on)
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
        "satisfied": not opened,
    }


def assess_time_order(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Whether every causal edge establishes that its cause precedes its effect."""

    states: dict[str, str] = {}
    for edge in sorted(graph["edges"], key=lambda entry: str(entry["edge_id"])):
        if edge["relation"] not in CAUSAL_RELATIONS:
            continue
        lag = str(edge["lag"]).strip().lower()
        if lag in NON_ESTABLISHING_LAGS:
            states[str(edge["edge_id"])] = (
                TimeOrderState.SIMULTANEOUS.value
                if lag == "simultaneous"
                else TimeOrderState.UNKNOWN.value
            )
        else:
            states[str(edge["edge_id"])] = TimeOrderState.ESTABLISHED.value
    unestablished = sorted(
        edge_id
        for edge_id, state in states.items()
        if state != TimeOrderState.ESTABLISHED.value
    )
    return {
        "assessment": "time_order",
        "edge_states": states,
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
    return {
        "artifact_id": _text(verdict["artifact_id"], "artifact_id"),
        "detail": _mapping(verdict["detail"], "detail"),
        "mode": mode,
        "verdict": _text(verdict["verdict"], "verdict"),
    }


def identification_ceiling(
    mode_verdicts: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    """The strongest identification the separate modes leave available.

    No mode can raise the ceiling; each can only lower it.  A live competing
    explanation from R03 is the clearest case: while an alternative account of
    the same evidence still stands, the association cannot be the identified
    cause however strong or however deductively tidy it is.
    """

    ceiling = Identification.IDENTIFIED.value
    reasons: list[str] = []
    for verdict in mode_verdicts:
        mode = str(verdict["mode"])
        detail = verdict["detail"]
        if mode == InferenceMode.INDUCTIVE.value:
            if str(detail.get("causal_identification", "")) != "NOT_ASSESSED":
                _fail(
                    "MODE_COLLAPSE",
                    "an inductive synthesis may not carry a causal verdict",
                    {"artifact_id": verdict["artifact_id"]},
                )
            if str(detail.get("status")) != "COMPLETE":
                ceiling = Identification.ASSUMPTION_DEPENDENT.value
                reasons.append("inductive synthesis is not complete")
        elif mode == InferenceMode.DEDUCTIVE.value:
            status = str(detail.get("status"))
            if status == "BROKEN":
                ceiling = Identification.NOT_IDENTIFIED.value
                reasons.append("the deductive trace rests on rejected support")
            elif status == "CONDITIONAL":
                if ceiling == Identification.IDENTIFIED.value:
                    ceiling = Identification.ASSUMPTION_DEPENDENT.value
                reasons.append("the deductive trace depends on ledgered assumptions")
        elif mode == InferenceMode.ABDUCTIVE.value:
            if str(detail.get("selected_explanation_id") or "") != "":
                _fail(
                    "MODE_COLLAPSE",
                    "an aporia record may not arrive with an explanation selected",
                    {"artifact_id": verdict["artifact_id"]},
                )
            standing = int(detail.get("standing_conflict_count", 0))
            if standing > 0:
                if ceiling == Identification.IDENTIFIED.value:
                    ceiling = Identification.ASSUMPTION_DEPENDENT.value
                reasons.append(
                    f"{standing} conflict(s) still carry competing explanations"
                )
    return ceiling, sorted(set(reasons))


def _rank(status: str) -> int:
    return IDENTIFICATION_LADDER.index(status)


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

    subject_id = _text(subject_id, "subject_id")
    argument_graph_id = _text(argument_graph_id, "argument_graph_id")
    created_at = _timestamp(created_at, "created_at")
    validated = _validate_graph(graph)

    assessments = {
        "collider": assess_colliders(validated, conditioned_on),
        "confounding": assess_confounding(
            validated, adjustment_set, unmeasured_confounders
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

    seen_modes: set[str] = set()
    verdicts: list[dict[str, Any]] = []
    for index, entry in enumerate(mode_verdicts):
        verdict = _validate_mode_verdict(entry, index)
        if verdict["mode"] in seen_modes:
            _fail(
                "MODE_DUPLICATED",
                "each inference mode contributes exactly one verdict",
                {"mode": verdict["mode"]},
            )
        seen_modes.add(verdict["mode"])
        verdicts.append(verdict)
    verdicts.sort(key=lambda entry: entry["mode"])
    absent = sorted(set(INFERENCE_MODES) - seen_modes)
    if absent:
        _fail(
            "MODE_MISSING",
            "the gate requires a separate verdict from every inference mode",
            {"modes": absent},
        )

    ceiling, ceiling_reasons = identification_ceiling(verdicts)
    failures = sorted(
        name for name, record in assessments.items() if not record["satisfied"]
    )
    if failures:
        derived = Identification.NOT_IDENTIFIED.value
    elif validated["assumptions"]:
        derived = Identification.ASSUMPTION_DEPENDENT.value
    else:
        derived = Identification.IDENTIFIED.value
    if _rank(ceiling) < _rank(derived):
        derived = ceiling

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
        "mechanism_graph_id": validated["mechanism_graph_id"],
        "mode_verdicts": verdicts,
        "subject_id": subject_id,
    }
    payload["gate_id"] = "CG-" + _hex_digest(
        {
            "assessments": assessments,
            "created_at": created_at,
            "graph_hash": validated["graph_hash"],
            "identification_status": derived,
            "subject_id": subject_id,
        }
    )
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")
    return validate_causal_gate(payload)


def validate_causal_gate(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one gate record shape, vocabulary, ladder order, and self-hash."""

    value = _mapping(payload, "CausalGate")
    _exact_fields(value, GATE_FIELDS, "CausalGate")
    _text(value["gate_id"], "gate_id")
    _text(value["mechanism_graph_id"], "mechanism_graph_id")
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
    assessments = _mapping(value["assessments"], "assessments")
    if sorted(assessments) != sorted(REQUIRED_ASSESSMENTS):
        _fail(
            "ASSESSMENT_INCOMPLETE",
            "colliders, confounders, and time order must all be assessed",
            {"present": sorted(assessments)},
        )
    failures = sorted(
        name
        for name, record in assessments.items()
        if not _mapping(record, name)["satisfied"]
    )
    if (
        failures
        and value["identification_status"] != Identification.NOT_IDENTIFIED.value
    ):
        _fail(
            "CAUSAL_OVERCLAIM",
            "a failed assessment cannot coexist with an identified cause",
            {"failed_assessments": failures},
        )
    if (
        value["assumptions"]
        and value["identification_status"] == Identification.IDENTIFIED.value
    ):
        _fail(
            "CAUSAL_OVERCLAIM",
            "a graph carrying assumptions cannot be identified unconditionally",
        )
    if _rank(str(value["identification_status"])) > _rank(
        str(value["identification_ceiling"])
    ):
        _fail(
            "CAUSAL_OVERCLAIM",
            "identification exceeds the ceiling the inference modes leave available",
        )
    if _rank(str(value["declared_identification_status"])) > _rank(
        str(value["identification_status"])
    ):
        _fail(
            "CAUSAL_OVERCLAIM",
            "the declared identification status exceeds the derived one",
        )
    modes = [
        str(_mapping(entry, "mode verdict")["mode"])
        for entry in _sequence(value["mode_verdicts"], "mode_verdicts")
    ]
    if sorted(modes) != sorted(INFERENCE_MODES) or modes != sorted(modes):
        _fail(
            "MODE_MISSING",
            "the gate must carry exactly one sorted verdict per inference mode",
            {"modes": modes},
        )
    if _hash_excluding(value, "gate_hash") != value["gate_hash"]:
        _fail("GATE_HASH_MISMATCH", "gate_hash does not match its content")
    return SealedArtifact("CausalGate", _canonical_json(value))


def seal_mechanism_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp a MechanismGraph with its canonical content hash."""

    value = _mapping(payload, "MechanismGraph")
    _exact_fields(value, GRAPH_FIELDS, "MechanismGraph")
    value["graph_hash"] = _hash_excluding(value, "graph_hash")
    return value
