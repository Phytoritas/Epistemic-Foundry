"""Argument graphs with explicit aporia.

Contract source: `schemas/argument-graph.schema.json`.

Invariant EF4-I10 (inference separation): induction, deduction, abduction,
causal identification, simulation, and empirical observation stay typed and
separate. In this schema the inference strength is carried by `edge_type`, not
by the node, so the separation check is edge-based: a `deductively_implies` edge
may not originate from an unresolved or challenged node, and it may not rest on
an assumption node unless a `depends_on_assumption` edge declares that
dependency. Otherwise the graph presents a defeasible chain as a proof.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Edge types that assert a strict (non-defeasible) inference.
STRICT_EDGE_TYPES: frozenset[str] = frozenset({"deductively_implies"})

#: Edge types whose support is defeasible.
DEFEASIBLE_EDGE_TYPES: frozenset[str] = frozenset(
    {"supports", "inductively_supports", "explains", "predicts"}
)

#: Node statuses that leave a premise open. A strict inference from one of
#: these is a proof resting on an unsettled premise.
OPEN_NODE_STATUSES: frozenset[str] = frozenset({"challenged", "unresolved"})


class AporiaViolation(ValueError):
    """An argument graph misreports its own open questions."""


def build_argument_graph(
    *,
    run_id: str,
    hypothesis_id: str,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    proof_trace_artifact_id: str,
    hidden_assumption_ids: Sequence[str] = (),
    unresolved_objection_ids: Sequence[str] = (),
    argument_graph_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build an argument graph that records its own aporia.

    Edges are checked against the node set: an edge to a node that does not
    exist would make the graph unreviewable, and a reader could not tell whether
    the missing node was dropped or never written.
    """
    if not nodes:
        raise AporiaViolation("an argument graph must contain at least one node")
    node_ids = {str(node.get("argument_node_id")) for node in nodes}
    dangling: list[str] = []
    for edge in edges:
        for endpoint in ("from_id", "to_id"):
            value = edge.get(endpoint)
            if isinstance(value, str) and value and value not in node_ids:
                dangling.append(value)
    if dangling:
        raise AporiaViolation(
            f"edge endpoint(s) {sorted(set(dangling))} are not nodes in this graph"
        )

    graph: dict[str, Any] = {
        "argument_graph_id": argument_graph_id or new_id("AG"),
        "run_id": run_id,
        "hypothesis_id": hypothesis_id,
        "nodes": [dict(node) for node in nodes],
        "edges": [dict(edge) for edge in edges],
        "hidden_assumption_ids": list(hidden_assumption_ids),
        "unresolved_objection_ids": list(unresolved_objection_ids),
        "proof_trace_artifact_id": proof_trace_artifact_id,
        "created_at": created_at or utc_now_iso(),
    }
    graph["graph_hash"] = hash_excluding(graph, "graph_hash")
    validate_artifact("argument-graph", graph)
    return graph


def is_resolved(graph: Mapping[str, Any]) -> bool:
    """True only when no objection and no hidden assumption remains open.

    Feeds the epistemic status of a passport. A graph carrying an unresolved
    objection is `UNDERDETERMINED`, which is a truthful answer rather than a
    failure to reach one.
    """
    return not graph.get("unresolved_objection_ids") and not graph.get("hidden_assumption_ids")


def open_questions(graph: Mapping[str, Any]) -> list[str]:
    """Every open item, so a reporting surface cannot show only one kind."""
    return sorted(
        [*graph.get("hidden_assumption_ids", []), *graph.get("unresolved_objection_ids", [])]
    )


def reasoning_mode_separation_holds(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> bool:
    """False when a strict inference rests on unsettled or undeclared ground.

    Two violations are detected:

    * a `deductively_implies` edge whose source node is `challenged` or
      `unresolved` — a proof cannot stand on an open premise;
    * a `deductively_implies` edge from an `assumption` node without a
      corresponding `depends_on_assumption` edge declaring that dependency.
    """
    node_type = {str(node.get("argument_node_id")): str(node.get("node_type", "")) for node in nodes}
    node_status = {str(node.get("argument_node_id")): str(node.get("status", "")) for node in nodes}
    declared_assumption_edges = {
        str(edge.get("from_id"))
        for edge in edges
        if str(edge.get("edge_type")) == "depends_on_assumption"
    }
    for edge in edges:
        if str(edge.get("edge_type")) not in STRICT_EDGE_TYPES:
            continue
        source = str(edge.get("from_id") or "")
        if node_status.get(source) in OPEN_NODE_STATUSES:
            return False
        if node_type.get(source) == "assumption" and source not in declared_assumption_edges:
            return False
    return True
