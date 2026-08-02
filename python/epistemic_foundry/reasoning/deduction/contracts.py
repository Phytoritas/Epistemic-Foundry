"""R02 deterministic proof-trace and assumption-ledger contracts.

The engine turns a declared ArgumentGraph into a checked deductive proof trace
plus an exhaustive assumption ledger.  It proves nothing on its own: it refuses
graphs that would let a conclusion rest on something neither bound to a source
nor recorded as an assumption, and it refuses conclusions that hold in a wider
scope than their premises.

Premise binding.  A ``premise`` node must cite evidence.  A statement with no
evidence is an ``assumption`` and is entered in the ledger, so a conclusion can
never quietly depend on an unsupported statement.  The engine derives the set of
load-bearing assumptions itself and requires the graph's declared
``hidden_assumption_ids`` to match exactly, which is what makes an undeclared
assumption a failure rather than an omission.

Scope discipline.  A deduction may narrow a ScopeVector but never widen it.
Dropping a boundary the premises carried, or moving to a value no premise
covers, is rejected rather than reported as a weaker conclusion.
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


class NodeType(str, Enum):
    """Canonical ArgumentGraph node types (schemas/argument-graph.schema.json)."""

    PREMISE = "premise"
    ASSUMPTION = "assumption"
    RULE = "rule"
    CLAIM = "claim"
    PREDICTION = "prediction"
    FALSIFIER = "falsifier"
    ALTERNATIVE = "alternative"
    OBJECTION = "objection"
    RESPONSE = "response"
    CONCLUSION = "conclusion"


class EdgeType(str, Enum):
    SUPPORTS = "supports"
    DEDUCTIVELY_IMPLIES = "deductively_implies"
    INDUCTIVELY_SUPPORTS = "inductively_supports"
    ATTACKS = "attacks"
    REBUTS = "rebuts"
    UNDERCUTS = "undercuts"
    EXPLAINS = "explains"
    COMPETES_WITH = "competes_with"
    PREDICTS = "predicts"
    FALSIFIED_BY = "falsified_by"
    DEPENDS_ON_ASSUMPTION = "depends_on_assumption"


class NodeStatus(str, Enum):
    ASSERTED = "asserted"
    ACCEPTED = "accepted"
    CHALLENGED = "challenged"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class Grounding(str, Enum):
    """How much support an assumption actually has."""

    UNGROUNDED = "UNGROUNDED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"


class TraceStatus(str, Enum):
    VALID = "VALID"
    CONDITIONAL = "CONDITIONAL"
    BROKEN = "BROKEN"


NODE_TYPES: Final = tuple(entry.value for entry in NodeType)
EDGE_TYPES: Final = tuple(entry.value for entry in EdgeType)
NODE_STATUSES: Final = tuple(entry.value for entry in NodeStatus)
#: Edges that carry deductive force and therefore need a stated rule.
DEDUCTIVE_EDGE_TYPES: Final = (EdgeType.DEDUCTIVELY_IMPLIES.value,)
#: Edges that make the target depend on the source for its support.
SUPPORTING_EDGE_TYPES: Final = (
    EdgeType.SUPPORTS.value,
    EdgeType.DEDUCTIVELY_IMPLIES.value,
    EdgeType.INDUCTIVELY_SUPPORTS.value,
    EdgeType.DEPENDS_ON_ASSUMPTION.value,
)
#: Node types that must cite evidence to stand as given.
SOURCE_BOUND_TYPES: Final = (NodeType.PREMISE.value,)
#: Node types that are conclusions of a trace.
CONCLUDING_TYPES: Final = (NodeType.CONCLUSION.value, NodeType.CLAIM.value)
#: Statuses that disqualify a node from carrying support.
UNUSABLE_STATUSES: Final = (NodeStatus.REJECTED.value,)

GRAPH_FIELDS: Final = frozenset(
    {
        "argument_graph_id",
        "run_id",
        "hypothesis_id",
        "nodes",
        "edges",
        "hidden_assumption_ids",
        "unresolved_objection_ids",
        "proof_trace_artifact_id",
        "graph_hash",
        "created_at",
    }
)
NODE_FIELDS: Final = frozenset(
    {"argument_node_id", "node_type", "statement", "evidence_ids", "scope", "status"}
)
EDGE_FIELDS: Final = frozenset(
    {"edge_id", "from_id", "to_id", "edge_type", "rule_ref", "confidence"}
)
TRACE_FIELDS: Final = frozenset(
    {
        "proof_trace_id",
        "argument_graph_id",
        "run_id",
        "hypothesis_id",
        "created_at",
        "status",
        "conclusions",
        "assumption_ledger",
        "broken_edges",
        "unresolved_objection_ids",
        "scope_checks",
        "trace_hash",
    }
)

#: ScopeVector scalar fields; ``null`` means unconstrained, so a conclusion
#: that nulls a field its premises constrained has widened.
SCOPE_SCALAR_FIELDS: Final = (
    "comparator",
    "domain",
    "entity_subtype",
    "entity_type",
    "geography",
    "jurisdiction",
    "language",
    "lifecycle_stage",
    "measurement_time",
    "population",
    "setting",
    "spatial_scale",
    "temporal_scale",
    "time_period",
    "unit_of_analysis",
)
#: Criteria lists; more entries means a narrower scope.
SCOPE_SET_FIELDS: Final = ("exclusion_criteria", "inclusion_criteria")
#: Key/value maps; a dropped or altered key widens or moves the scope.
SCOPE_MAP_FIELDS: Final = ("conditions", "domain_extensions")


class ProofTraceError(ValueError):
    """Typed fail-closed R02 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise ProofTraceError(code, message, context)


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


def _validate_scope(value: object, label: str) -> dict[str, Any]:
    scope = _mapping(value, label)
    expected = frozenset(
        (
            *SCOPE_SCALAR_FIELDS,
            *SCOPE_SET_FIELDS,
            *SCOPE_MAP_FIELDS,
            "intervention_or_exposure",
        )
    )
    _exact_fields(scope, expected, label)
    for field in SCOPE_SET_FIELDS:
        entries = _sequence(scope[field], f"{label}.{field}")
        scope[field] = sorted({_text(entry, f"{label}.{field}") for entry in entries})
    for field in SCOPE_MAP_FIELDS:
        scope[field] = _mapping(scope[field], f"{label}.{field}")
    return scope


def _validate_node(value: object, index: int) -> dict[str, Any]:
    node = _mapping(value, f"nodes[{index}]")
    _exact_fields(node, NODE_FIELDS, f"nodes[{index}]")
    node_id = _text(node["argument_node_id"], "argument_node_id")
    if node["node_type"] not in NODE_TYPES:
        _fail("NODE_TYPE_INVALID", f"{node_id} has a non-canonical node type")
    if node["status"] not in NODE_STATUSES:
        _fail("NODE_STATUS_INVALID", f"{node_id} has a non-canonical status")
    evidence = _sequence(node["evidence_ids"], "evidence_ids")
    return {
        "argument_node_id": node_id,
        "evidence_ids": sorted({_text(entry, "evidence_id") for entry in evidence}),
        "node_type": str(node["node_type"]),
        "scope": _validate_scope(node["scope"], f"{node_id}.scope"),
        "statement": _text(node["statement"], "statement"),
        "status": str(node["status"]),
    }


def _validate_edge(
    value: object, index: int, nodes: Mapping[str, Any]
) -> dict[str, Any]:
    edge = _mapping(value, f"edges[{index}]")
    _exact_fields(edge, EDGE_FIELDS, f"edges[{index}]")
    edge_id = _text(edge["edge_id"], "edge_id")
    if edge["edge_type"] not in EDGE_TYPES:
        _fail("EDGE_TYPE_INVALID", f"{edge_id} has a non-canonical edge type")
    from_id = _text(edge["from_id"], "from_id")
    to_id = _text(edge["to_id"], "to_id")
    for endpoint in (from_id, to_id):
        if endpoint not in nodes:
            _fail(
                "EDGE_UNRESOLVED",
                "an edge endpoint must reference a declared node",
                {"edge_id": edge_id, "node_id": endpoint},
            )
    if from_id == to_id:
        _fail("PROOF_CYCLE", "a node may not imply itself", {"edge_id": edge_id})
    rule_ref = edge["rule_ref"]
    if rule_ref is not None:
        rule_ref = _text(rule_ref, "rule_ref")
    if edge["edge_type"] in DEDUCTIVE_EDGE_TYPES and rule_ref is None:
        _fail(
            "RULE_UNDECLARED",
            "a deductive edge must name the rule it applies",
            {"edge_id": edge_id},
        )
    confidence = edge["confidence"]
    if confidence is not None:
        if type(confidence) not in (int, float) or isinstance(confidence, bool):
            _fail("INPUT_INVALID", f"{edge_id} confidence must be a number or null")
        if not 0.0 <= float(confidence) <= 1.0:
            _fail("INPUT_INVALID", f"{edge_id} confidence must be within [0, 1]")
        confidence = float(confidence)
    return {
        "confidence": confidence,
        "edge_id": edge_id,
        "edge_type": str(edge["edge_type"]),
        "from_id": from_id,
        "rule_ref": rule_ref,
        "to_id": to_id,
    }


def scope_widening(
    premise_scopes: Sequence[Mapping[str, Any]],
    conclusion_scope: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Every way the conclusion's scope exceeds what the premises establish.

    A deduction is sound only where all its premises hold, so the conclusion
    may narrow a boundary but never drop one, and may not move to a value no
    premise covers.  An empty result means the conclusion stays inside the
    premises' scope.
    """

    findings: list[dict[str, Any]] = []
    if not premise_scopes:
        return findings
    for field in SCOPE_SCALAR_FIELDS:
        premise_values = {scope[field] for scope in premise_scopes}
        constrained = {value for value in premise_values if value is not None}
        conclusion_value = conclusion_scope[field]
        if conclusion_value is None and constrained:
            findings.append(
                {
                    "field": field,
                    "kind": "DROPPED_BOUNDARY",
                    "premise_values": sorted(str(value) for value in constrained),
                }
            )
        elif (
            conclusion_value is not None
            and constrained
            and conclusion_value not in constrained
        ):
            findings.append(
                {
                    "field": field,
                    "kind": "UNCOVERED_VALUE",
                    "premise_values": sorted(str(value) for value in constrained),
                }
            )
    for field in SCOPE_SET_FIELDS:
        required: set[str] = set()
        for scope in premise_scopes:
            required.update(scope[field])
        dropped = sorted(required - set(conclusion_scope[field]))
        if dropped:
            findings.append(
                {"dropped": dropped, "field": field, "kind": "DROPPED_CRITERIA"}
            )
    for field in SCOPE_MAP_FIELDS:
        for scope in premise_scopes:
            for key, value in scope[field].items():
                if key not in conclusion_scope[field]:
                    findings.append(
                        {"field": f"{field}.{key}", "kind": "DROPPED_CONDITION"}
                    )
                elif conclusion_scope[field][key] != value:
                    findings.append(
                        {"field": f"{field}.{key}", "kind": "ALTERED_CONDITION"}
                    )
    unique: list[dict[str, Any]] = []
    for finding in findings:
        if finding not in unique:
            unique.append(finding)
    return sorted(unique, key=lambda entry: (entry["field"], entry["kind"]))


def _supporting_ancestors(
    node_id: str,
    incoming: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Every node the target rests on, following supporting edges backwards."""

    seen: set[str] = set()
    order: list[str] = []
    stack = [node_id]
    while stack:
        current = stack.pop()
        for edge in incoming.get(current, ()):
            if edge["edge_type"] not in SUPPORTING_EDGE_TYPES:
                continue
            source = str(edge["from_id"])
            if source in seen:
                continue
            seen.add(source)
            order.append(source)
            stack.append(source)
    return sorted(order)


def _assert_acyclic(
    nodes: Mapping[str, Any], edges: Sequence[Mapping[str, Any]]
) -> None:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        if edge["edge_type"] in SUPPORTING_EDGE_TYPES:
            adjacency[str(edge["from_id"])].append(str(edge["to_id"]))
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(nodes, WHITE)
    for start in sorted(nodes):
        if colour[start] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        colour[start] = GREY
        while stack:
            current, index = stack.pop()
            if index < len(adjacency[current]):
                stack.append((current, index + 1))
                target = sorted(adjacency[current])[index]
                if colour[target] == GREY:
                    _fail(
                        "PROOF_CYCLE",
                        "the supporting graph must be acyclic",
                        {"node_id": target},
                    )
                if colour[target] == WHITE:
                    colour[target] = GREY
                    stack.append((target, 0))
            else:
                colour[current] = BLACK


def build_proof_trace(graph: Mapping[str, Any]) -> SealedArtifact:
    """Check one ArgumentGraph and seal its proof trace and assumption ledger."""

    value = _mapping(graph, "ArgumentGraph")
    _exact_fields(value, GRAPH_FIELDS, "ArgumentGraph")
    graph_id = _text(value["argument_graph_id"], "argument_graph_id")
    run_id = _text(value["run_id"], "run_id")
    hypothesis_id = _text(value["hypothesis_id"], "hypothesis_id")
    created_at = _timestamp(value["created_at"], "created_at")
    graph_hash = _text(value["graph_hash"], "graph_hash")
    if SHA256_PATTERN.fullmatch(graph_hash) is None:
        _fail("INPUT_INVALID", "graph_hash must be a sha256 digest")
    if _hash_excluding(value, "graph_hash") != graph_hash:
        _fail("GRAPH_HASH_MISMATCH", "graph_hash does not match its content")

    raw_nodes = _sequence(value["nodes"], "nodes")
    if not raw_nodes:
        _fail("INPUT_INVALID", "an ArgumentGraph must declare at least one node")
    nodes: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(raw_nodes):
        node = _validate_node(entry, index)
        if node["argument_node_id"] in nodes:
            _fail(
                "DUPLICATE_NODE",
                "argument node ids must be unique",
                {"node_id": node["argument_node_id"]},
            )
        nodes[node["argument_node_id"]] = node
    edges = [
        _validate_edge(entry, index, nodes)
        for index, entry in enumerate(_sequence(value["edges"], "edges"))
    ]
    edge_ids = [edge["edge_id"] for edge in edges]
    if len(edge_ids) != len(set(edge_ids)):
        _fail("DUPLICATE_EDGE", "edge ids must be unique")
    _assert_acyclic(nodes, edges)

    incoming: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        incoming[edge["to_id"]].append(edge)

    # --- premises are source-bound, everything else is ledgered ------------
    for node in nodes.values():
        if node["node_type"] in SOURCE_BOUND_TYPES and not node["evidence_ids"]:
            _fail(
                "PREMISE_UNGROUNDED",
                "a premise must cite evidence; an unevidenced statement is an assumption",
                {"node_id": node["argument_node_id"]},
            )

    conclusions: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    scope_checks: list[dict[str, Any]] = []
    load_bearing_assumptions: set[str] = set()
    for node_id in sorted(nodes):
        node = nodes[node_id]
        if node["node_type"] not in CONCLUDING_TYPES:
            continue
        ancestors = _supporting_ancestors(node_id, incoming)
        if not ancestors:
            _fail(
                "CONCLUSION_UNSUPPORTED",
                "a conclusion must rest on at least one premise or assumption",
                {"node_id": node_id},
            )
        premises = [
            nodes[ancestor]
            for ancestor in ancestors
            if nodes[ancestor]["node_type"] in SOURCE_BOUND_TYPES
        ]
        assumptions = [
            nodes[ancestor]
            for ancestor in ancestors
            if nodes[ancestor]["node_type"] == NodeType.ASSUMPTION.value
        ]
        ungrounded = [
            nodes[ancestor]["argument_node_id"]
            for ancestor in ancestors
            if nodes[ancestor]["node_type"]
            not in (*SOURCE_BOUND_TYPES, NodeType.ASSUMPTION.value, NodeType.RULE.value)
            and not nodes[ancestor]["evidence_ids"]
        ]
        if ungrounded:
            _fail(
                "SUPPORT_UNGROUNDED",
                "a conclusion may only rest on evidence or a declared assumption",
                {"node_id": node_id, "unsupported": sorted(ungrounded)},
            )
        if not premises and not assumptions:
            _fail(
                "CONCLUSION_UNSUPPORTED",
                "a conclusion must rest on at least one premise or assumption",
                {"node_id": node_id},
            )
        load_bearing_assumptions.update(
            assumption["argument_node_id"] for assumption in assumptions
        )
        rejected = sorted(
            ancestor
            for ancestor in ancestors
            if nodes[ancestor]["status"] in UNUSABLE_STATUSES
        )
        for ancestor in rejected:
            broken.append(
                {
                    "conclusion_id": node_id,
                    "node_id": ancestor,
                    "reason": "REJECTED_SUPPORT",
                }
            )
        if rejected and node["status"] == NodeStatus.ACCEPTED.value:
            _fail(
                "BROKEN_EDGE",
                "a conclusion resting on rejected support cannot be accepted",
                {"node_id": node_id, "rejected": rejected},
            )
        widening = scope_widening(
            [premise["scope"] for premise in premises], node["scope"]
        )
        scope_checks.append(
            {
                "conclusion_id": node_id,
                "findings": widening,
                "premise_count": len(premises),
            }
        )
        if widening:
            _fail(
                "SCOPE_WIDENED",
                "a deduction may narrow a scope but never widen it",
                {"findings": widening, "node_id": node_id},
            )
        conclusions.append(
            {
                "assumption_ids": sorted(
                    assumption["argument_node_id"] for assumption in assumptions
                ),
                "conclusion_id": node_id,
                "premise_ids": sorted(
                    premise["argument_node_id"] for premise in premises
                ),
                "rule_refs": sorted(
                    {
                        str(edge["rule_ref"])
                        for edge in edges
                        if edge["rule_ref"] is not None
                        and edge["to_id"] in (*ancestors, node_id)
                    }
                ),
                "status": node["status"],
                "support_is_complete": not rejected,
            }
        )

    if not conclusions:
        _fail("INPUT_INVALID", "an ArgumentGraph must declare at least one conclusion")

    declared_hidden = sorted(
        {
            _text(entry, "hidden_assumption_id")
            for entry in _sequence(
                value["hidden_assumption_ids"], "hidden_assumption_ids"
            )
        }
    )
    unknown_hidden = sorted(set(declared_hidden) - set(nodes))
    if unknown_hidden:
        _fail(
            "HIDDEN_ASSUMPTION_UNKNOWN",
            "hidden_assumption_ids must reference declared nodes",
            {"node_ids": unknown_hidden},
        )
    derived_hidden = sorted(
        assumption_id
        for assumption_id in load_bearing_assumptions
        if not nodes[assumption_id]["evidence_ids"]
    )
    if declared_hidden != derived_hidden:
        _fail(
            "HIDDEN_ASSUMPTION_UNDECLARED",
            "the declared hidden assumptions must equal the load-bearing unevidenced ones",
            {"declared": declared_hidden, "derived": derived_hidden},
        )

    ledger = [
        {
            "assumption_id": assumption_id,
            "dependents": sorted(
                entry["conclusion_id"]
                for entry in conclusions
                if assumption_id in entry["assumption_ids"]
            ),
            "evidence_ids": nodes[assumption_id]["evidence_ids"],
            "grounding": (
                Grounding.PARTIALLY_SUPPORTED.value
                if nodes[assumption_id]["evidence_ids"]
                else Grounding.UNGROUNDED.value
            ),
            "statement": nodes[assumption_id]["statement"],
            "status": nodes[assumption_id]["status"],
        }
        for assumption_id in sorted(load_bearing_assumptions)
    ]

    declared_objections = sorted(
        {
            _text(entry, "unresolved_objection_id")
            for entry in _sequence(
                value["unresolved_objection_ids"], "unresolved_objection_ids"
            )
        }
    )
    derived_objections = sorted(
        node_id
        for node_id, node in nodes.items()
        if node["node_type"] == NodeType.OBJECTION.value
        and node["status"] != NodeStatus.REJECTED.value
        and not any(
            edge["from_id"] == node_id and edge["edge_type"] == EdgeType.REBUTS.value
            for edge in edges
        )
        and not any(
            edge["to_id"] == node_id and edge["edge_type"] == EdgeType.REBUTS.value
            for edge in edges
        )
    )
    if declared_objections != derived_objections:
        _fail(
            "OBJECTION_UNDECLARED",
            "the declared unresolved objections must equal the standing ones",
            {"declared": declared_objections, "derived": derived_objections},
        )

    if broken:
        status = TraceStatus.BROKEN.value
    elif ledger:
        status = TraceStatus.CONDITIONAL.value
    else:
        status = TraceStatus.VALID.value

    trace: dict[str, Any] = {
        "argument_graph_id": graph_id,
        "assumption_ledger": ledger,
        "broken_edges": sorted(
            broken, key=lambda entry: (entry["conclusion_id"], entry["node_id"])
        ),
        "conclusions": conclusions,
        "created_at": created_at,
        "hypothesis_id": hypothesis_id,
        "run_id": run_id,
        "scope_checks": scope_checks,
        "status": status,
        "unresolved_objection_ids": declared_objections,
    }
    trace["proof_trace_id"] = "PT-" + _hex_digest(
        {
            "argument_graph_id": graph_id,
            "assumption_ledger": ledger,
            "conclusions": conclusions,
            "created_at": created_at,
            "graph_hash": graph_hash,
        }
    )
    trace["trace_hash"] = _hash_excluding(trace, "trace_hash")
    return validate_proof_trace(trace)


def validate_proof_trace(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one proof-trace record shape, vocabulary, and self-hash."""

    value = _mapping(payload, "ProofTrace")
    _exact_fields(value, TRACE_FIELDS, "ProofTrace")
    _text(value["proof_trace_id"], "proof_trace_id")
    _text(value["argument_graph_id"], "argument_graph_id")
    _text(value["run_id"], "run_id")
    _text(value["hypothesis_id"], "hypothesis_id")
    _timestamp(value["created_at"], "created_at")
    if value["status"] not in tuple(entry.value for entry in TraceStatus):
        _fail("INPUT_INVALID", "status must be a canonical trace status")
    conclusions = _sequence(value["conclusions"], "conclusions")
    if not conclusions:
        _fail("INPUT_INVALID", "a proof trace must record at least one conclusion")
    ledger = _sequence(value["assumption_ledger"], "assumption_ledger")
    ledger_ids = [
        str(_mapping(entry, "ledger entry")["assumption_id"]) for entry in ledger
    ]
    if ledger_ids != sorted(ledger_ids) or len(ledger_ids) != len(set(ledger_ids)):
        _fail("INPUT_INVALID", "the assumption ledger must be unique and sorted")
    for entry in ledger:
        record = _mapping(entry, "ledger entry")
        if record["grounding"] not in tuple(item.value for item in Grounding):
            _fail("INPUT_INVALID", "an assumption grounding is not canonical")
        if not record["dependents"]:
            _fail(
                "ASSUMPTION_ORPHANED",
                "a ledgered assumption must carry the conclusions that rest on it",
                {"assumption_id": record["assumption_id"]},
            )
    cited = {
        assumption_id
        for entry in conclusions
        for assumption_id in _mapping(entry, "conclusion")["assumption_ids"]
    }
    missing = sorted(cited - set(ledger_ids))
    if missing:
        _fail(
            "ASSUMPTION_UNLEDGERED",
            "every assumption a conclusion rests on must appear in the ledger",
            {"assumption_ids": missing},
        )
    for entry in _sequence(value["scope_checks"], "scope_checks"):
        check = _mapping(entry, "scope check")
        if _sequence(check["findings"], "findings"):
            _fail(
                "SCOPE_WIDENED",
                "a sealed trace may not record an unresolved scope widening",
                {"conclusion_id": check["conclusion_id"]},
            )
    if value["broken_edges"] and value["status"] != TraceStatus.BROKEN.value:
        _fail(
            "BROKEN_EDGE",
            "a trace with broken support must be reported as BROKEN",
        )
    if _hash_excluding(value, "trace_hash") != value["trace_hash"]:
        _fail("TRACE_HASH_MISMATCH", "trace_hash does not match its content")
    return SealedArtifact("ProofTrace", _canonical_json(value))


def seal_argument_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp an ArgumentGraph with its canonical content hash."""

    value = _mapping(payload, "ArgumentGraph")
    _exact_fields(value, GRAPH_FIELDS, "ArgumentGraph")
    value["graph_hash"] = _hash_excluding(value, "graph_hash")
    return value
