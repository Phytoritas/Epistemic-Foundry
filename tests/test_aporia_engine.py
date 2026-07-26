"""Open questions stay visible; a proof cannot rest on unsettled ground."""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.aporia_engine import (
    AporiaViolation,
    build_argument_graph,
    is_resolved,
    reasoning_mode_separation_holds,
)
from epistemic_foundry.aporia_engine.argument import open_questions
from epistemic_foundry.contracts import repo_root


def _sample() -> dict:
    return json.loads(
        (repo_root() / "examples" / "sample_argument-graph.json").read_text(encoding="utf-8")
    )


def _graph(**overrides) -> dict:
    sample = _sample()
    kwargs = dict(
        run_id=sample["run_id"],
        hypothesis_id=sample["hypothesis_id"],
        nodes=sample["nodes"],
        edges=sample["edges"],
        proof_trace_artifact_id=sample["proof_trace_artifact_id"],
        hidden_assumption_ids=sample["hidden_assumption_ids"],
        unresolved_objection_ids=sample["unresolved_objection_ids"],
    )
    kwargs.update(overrides)
    return build_argument_graph(**kwargs)


# -- construction -------------------------------------------------------


def test_graph_matches_the_canonical_schema() -> None:
    graph = _graph()
    assert graph["graph_hash"].startswith("sha256:")
    assert graph["nodes"]


def test_empty_graph_is_refused() -> None:
    with pytest.raises(AporiaViolation):
        _graph(nodes=[])


def test_dangling_edge_endpoint_is_refused() -> None:
    """An edge to a missing node makes the graph unreviewable."""
    sample = _sample()
    broken = list(sample["edges"]) + [
        {
            "edge_id": "AE-999",
            "from_id": "AN-does-not-exist",
            "to_id": str(sample["nodes"][0]["argument_node_id"]),
            "edge_type": "supports",
            "rule_ref": None,
            "confidence": None,
        }
    ]
    with pytest.raises(AporiaViolation) as excinfo:
        _graph(edges=broken)
    assert "not nodes in this graph" in str(excinfo.value)


# -- aporia visibility --------------------------------------------------


def test_open_objection_means_unresolved() -> None:
    """A clean conclusion may not be bought by closing an objection quietly."""
    graph = _graph(unresolved_objection_ids=["OBJ-1"], hidden_assumption_ids=[])
    assert is_resolved(graph) is False


def test_hidden_assumption_also_means_unresolved() -> None:
    graph = _graph(unresolved_objection_ids=[], hidden_assumption_ids=["ASM-1"])
    assert is_resolved(graph) is False


def test_fully_closed_graph_is_resolved() -> None:
    graph = _graph(unresolved_objection_ids=[], hidden_assumption_ids=[])
    assert is_resolved(graph) is True


def test_open_questions_reports_both_kinds() -> None:
    """A reporting surface must not be able to show only one kind."""
    graph = _graph(unresolved_objection_ids=["OBJ-1"], hidden_assumption_ids=["ASM-1"])
    assert open_questions(graph) == ["ASM-1", "OBJ-1"]


# -- inference separation ----------------------------------------------


def _node(node_id: str, node_type: str, status: str) -> dict:
    sample = _sample()
    template = dict(sample["nodes"][0])
    template["argument_node_id"] = node_id
    template["node_type"] = node_type
    template["status"] = status
    return template


def _edge(from_id: str, to_id: str, edge_type: str) -> dict:
    return {
        "edge_id": f"AE-{from_id}-{to_id}",
        "from_id": from_id,
        "to_id": to_id,
        "edge_type": edge_type,
        "rule_ref": None,
        "confidence": None,
    }


def test_deduction_from_an_accepted_premise_holds() -> None:
    nodes = [_node("AN-1", "premise", "accepted"), _node("AN-2", "conclusion", "accepted")]
    edges = [_edge("AN-1", "AN-2", "deductively_implies")]
    assert reasoning_mode_separation_holds(nodes, edges) is True


def test_deduction_from_an_unresolved_premise_fails() -> None:
    """A proof cannot stand on an open premise."""
    nodes = [_node("AN-1", "premise", "unresolved"), _node("AN-2", "conclusion", "accepted")]
    edges = [_edge("AN-1", "AN-2", "deductively_implies")]
    assert reasoning_mode_separation_holds(nodes, edges) is False


def test_deduction_from_a_challenged_premise_fails() -> None:
    nodes = [_node("AN-1", "premise", "challenged"), _node("AN-2", "conclusion", "accepted")]
    edges = [_edge("AN-1", "AN-2", "deductively_implies")]
    assert reasoning_mode_separation_holds(nodes, edges) is False


def test_undeclared_assumption_dependency_fails() -> None:
    """A deduction resting on an assumption must declare the dependency."""
    nodes = [_node("AN-1", "assumption", "accepted"), _node("AN-2", "conclusion", "accepted")]
    edges = [_edge("AN-1", "AN-2", "deductively_implies")]
    assert reasoning_mode_separation_holds(nodes, edges) is False


def test_declared_assumption_dependency_holds() -> None:
    nodes = [_node("AN-1", "assumption", "accepted"), _node("AN-2", "conclusion", "accepted")]
    edges = [
        _edge("AN-1", "AN-2", "deductively_implies"),
        _edge("AN-1", "AN-2", "depends_on_assumption"),
    ]
    assert reasoning_mode_separation_holds(nodes, edges) is True


def test_defeasible_support_from_an_open_premise_is_allowed() -> None:
    """Inductive support from a challenged premise is honest, not a violation."""
    nodes = [_node("AN-1", "premise", "challenged"), _node("AN-2", "claim", "accepted")]
    edges = [_edge("AN-1", "AN-2", "inductively_supports")]
    assert reasoning_mode_separation_holds(nodes, edges) is True
