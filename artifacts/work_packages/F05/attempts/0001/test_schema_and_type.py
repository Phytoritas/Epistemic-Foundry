"""schema_and_type_check — the machine reads its vocabulary, never restates it.

The node graph and terminal states come from the workflow that declares them,
the stop-reason classification from the module that owns it, and the machine
source is scanned for canonical schema enum values because EF4-I22 is what stops
a second copy of a wire vocabulary from drifting.  A workflow that renames or
drops a node must break this suite rather than leave a machine describing a
graph that no longer exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from epistemic_foundry.evolution.v4_f05 import (
    FINDING_CODES,
    WORKFLOW_PATH,
    EvolveStateError,
    load_graph,
    load_loop_bound,
    stop_reasons,
)
from epistemic_foundry.evolution_chamber.checkpoint import ADVERSE_STOPS, ORDERLY_STOPS
from fixtures import GRAPH, LOOP_ENTRY, LOOP_EXIT, ROOT, loop_contract

MACHINE = ROOT / "src/epistemic_foundry/evolution/v4_f05/machine.py"


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_the_graph_matches_the_workflow_that_declares_it() -> None:
    document = yaml.safe_load((ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"))
    declared = [node["node_id"] for node in document["nodes"]]

    assert list(GRAPH.nodes) == declared
    assert len(GRAPH.nodes) == 26


def test_every_dependency_matches_the_workflow() -> None:
    document = yaml.safe_load((ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"))

    for node in document["nodes"]:
        assert list(GRAPH.depends_on(node["node_id"])) == list(
            node.get("depends_on") or []
        ), node["node_id"]


def test_the_cycle_has_exactly_one_entry_node() -> None:
    assert GRAPH.entry_nodes == ("qualify_evolution_run",)


def test_the_terminal_states_come_from_the_workflow() -> None:
    document = yaml.safe_load((ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"))

    assert list(GRAPH.terminal_states) == document["terminal_states"]


def test_the_stop_vocabulary_comes_from_the_declaring_module() -> None:
    assert set(stop_reasons()) == set(ORDERLY_STOPS) | set(ADVERSE_STOPS)
    assert not set(ORDERLY_STOPS) & set(ADVERSE_STOPS)
    assert len(stop_reasons()) == 9


def test_the_machine_holds_no_stop_reason_literal() -> None:
    held = string_literals(MACHINE) & set(stop_reasons())

    assert held == set(), held


def test_the_machine_holds_no_node_id_literal_except_the_workflow_path() -> None:
    held = string_literals(MACHINE) & set(GRAPH.nodes)

    assert held == set(), held


def test_the_machine_holds_no_terminal_state_literal() -> None:
    held = string_literals(MACHINE) & set(GRAPH.terminal_states)

    assert held == set(), held


def test_an_unknown_node_has_no_dependency() -> None:
    with pytest.raises(EvolveStateError) as caught:
        GRAPH.depends_on("invent_a_node")

    assert caught.value.code == "NODE_UNDECLARED"


def test_a_loop_contract_missing_a_bound_is_refused() -> None:
    contract = loop_contract()
    del contract["max_iterations"]

    with pytest.raises(EvolveStateError) as caught:
        load_loop_bound(contract, GRAPH)
    assert caught.value.code == "LOOP_CONTRACT_INCOMPLETE"
    assert caught.value.context["missing"] == ["max_iterations"]


def test_a_loop_endpoint_outside_the_workflow_is_refused() -> None:
    contract = loop_contract()
    contract["entry_node_id"] = "invent_a_node"

    with pytest.raises(EvolveStateError) as caught:
        load_loop_bound(contract, GRAPH)
    assert caught.value.code == "LOOP_ENDPOINT_UNDECLARED"


def test_a_loop_that_encloses_nothing_is_refused() -> None:
    contract = loop_contract()
    contract["entry_node_id"] = contract["exit_node_id"]

    with pytest.raises(EvolveStateError) as caught:
        load_loop_bound(contract, GRAPH)
    assert caught.value.code == "LOOP_ENDPOINT_INVALID"


@pytest.mark.parametrize("value", [0, -1, "three", True])
def test_a_non_positive_iteration_limit_is_refused(value: object) -> None:
    contract = loop_contract()
    contract["max_iterations"] = value

    with pytest.raises(EvolveStateError) as caught:
        load_loop_bound(contract, GRAPH)
    assert caught.value.code == "INPUT_INVALID"


def test_a_negative_dry_round_requirement_is_refused() -> None:
    contract = loop_contract()
    contract["dry_rounds_required"] = -1

    with pytest.raises(EvolveStateError) as caught:
        load_loop_bound(contract, GRAPH)
    assert caught.value.code == "INPUT_INVALID"


def test_the_loop_binds_the_cycle_the_workflow_actually_closes() -> None:
    bound = load_loop_bound(loop_contract(), GRAPH)

    assert bound.exit_node_id == LOOP_EXIT
    assert bound.entry_node_id == LOOP_ENTRY
    # The exit node is the checkpoint commit, which is what makes a return edge
    # crossable at all.
    assert LOOP_EXIT in GRAPH.nodes
    assert LOOP_ENTRY in GRAPH.dependencies


def test_an_unreadable_workflow_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(EvolveStateError) as caught:
        load_graph(tmp_path)

    assert caught.value.code == "WORKFLOW_UNREADABLE"


def test_a_workflow_with_a_dangling_dependency_is_refused(tmp_path: Path) -> None:
    document = yaml.safe_load((ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"))
    document["nodes"][1]["depends_on"] = ["a_node_that_was_removed"]
    target = tmp_path / WORKFLOW_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(EvolveStateError) as caught:
        load_graph(tmp_path)
    assert caught.value.code == "WORKFLOW_UNREADABLE"
    assert caught.value.context["unknown"] == ["a_node_that_was_removed"]


def test_a_workflow_with_a_duplicate_node_is_refused(tmp_path: Path) -> None:
    document = yaml.safe_load((ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"))
    document["nodes"].append(dict(document["nodes"][0]))
    target = tmp_path / WORKFLOW_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(EvolveStateError) as caught:
        load_graph(tmp_path)
    assert caught.value.code == "WORKFLOW_UNREADABLE"


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 4
    for code, message in FINDING_CODES.values():
        assert code.isupper()
        assert len(message) > 50


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = EvolveStateError("RETURN_EDGE_UNCHECKPOINTED", "message", {"a": 1})

    assert error.code == "RETURN_EDGE_UNCHECKPOINTED"
    assert str(error) == "message"
    assert error.context == {"a": 1}
