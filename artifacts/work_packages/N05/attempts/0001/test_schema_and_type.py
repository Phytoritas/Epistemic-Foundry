"""schema_and_type_check — the scheduler restates no vocabulary it does not own.

Three vocabularies meet in this package and none of them belong to it.  The lane
identities are the chamber's pipeline stages, the phase nodes are the EVOLVE
workflow's node identities, and the in-flight bound is a budget envelope limit
dimension.  Each is read from its declaring surface here, and the lane module is
scanned for every one of them, because EF4-I22 is what stops a second copy of a
vocabulary from drifting away from the contract that owns it.

The lane-to-node binding is data rather than Python literals for the same
reason, and it is checked against the graph the F05 loader reads: a lane may
only claim nodes the workflow declares, and a lane's nodes must descend from the
previous lane's nodes, so the phase progression is derived from the graph rather
than asserted by this package.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import get_args

import pytest
from fixtures import LANES_MODULE, ROOT

from epistemic_foundry.budgets.envelope import LIMIT_DIMENSIONS
from epistemic_foundry.evolution.v4_f05 import load_graph, stop_reasons
from epistemic_foundry.evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
)
from epistemic_foundry.noetic_ledger.receipts import EffectStatus
from epistemic_foundry.scheduler.v4_n05 import (
    ACTIONS,
    BINDING_PATH,
    CANDIDATE_LEDGER_SCOPE,
    CONCURRENCY_DIMENSION,
    EFFECT_LEDGER_SCOPE,
    EVALUATION_LANE,
    FINDING_CODES,
    LANE_COUNT,
    LANES,
    PERSISTENCE_LANE,
    PROPOSAL_LANE,
    ScheduleError,
    load_phase_binding,
    upstream_lane,
)


def string_literals(path: Path) -> set[str]:
    """Every string constant in a module, docstrings excluded."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
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


def test_the_lanes_are_derived_from_the_declared_pipeline() -> None:
    assert LANES == STAGES[1:]


def test_the_lane_count_matches_the_derivation() -> None:
    assert len(LANES) == LANE_COUNT == 3


def test_each_lane_is_named_for_the_stage_it_concludes() -> None:
    assert (PROPOSAL_LANE, EVALUATION_LANE, PERSISTENCE_LANE) == LANES
    assert PROPOSAL_LANE == STAGES[1]
    assert PERSISTENCE_LANE == STAGES[-1]


def test_upstream_lane_follows_the_pipeline_order() -> None:
    assert upstream_lane(PROPOSAL_LANE) is None
    assert upstream_lane(EVALUATION_LANE) == PROPOSAL_LANE
    assert upstream_lane(PERSISTENCE_LANE) == EVALUATION_LANE


def test_an_undeclared_lane_has_no_upstream() -> None:
    with pytest.raises(ScheduleError) as caught:
        upstream_lane("shipping")
    assert caught.value.code == "LANE_UNDECLARED"


def test_the_module_holds_no_pipeline_stage_literal() -> None:
    held = string_literals(LANES_MODULE) & {*STAGES, *TERMINAL_DISPOSITIONS}

    assert held == set(), held


def test_the_module_holds_no_effect_status_literal() -> None:
    held = string_literals(LANES_MODULE) & set(get_args(EffectStatus))

    assert held == set(), held


def test_the_module_holds_no_workflow_node_literal() -> None:
    held = string_literals(LANES_MODULE) & set(load_graph(ROOT).nodes)

    assert held == set(), held


def test_the_module_holds_no_stop_reason_literal() -> None:
    held = string_literals(LANES_MODULE) & set(stop_reasons())

    assert held == set(), held


def test_the_binding_covers_the_derived_lanes_exactly() -> None:
    binding = load_phase_binding(ROOT)

    assert set(binding.nodes_by_lane) == set(LANES)


def test_every_bound_node_is_declared_by_the_workflow() -> None:
    declared = set(load_graph(ROOT).nodes)
    binding = load_phase_binding(ROOT)

    for lane in LANES:
        assert set(binding.nodes_of(lane)) <= declared, lane


def test_no_workflow_node_is_claimed_by_two_lanes() -> None:
    binding = load_phase_binding(ROOT)
    claimed = [node for lane in LANES for node in binding.nodes_of(lane)]

    assert len(claimed) == len(set(claimed))


def test_each_lane_descends_from_the_previous_lane() -> None:
    """The phase order is the graph's, not this package's."""

    graph = load_graph(ROOT)
    binding = load_phase_binding(ROOT)

    def ancestors(node: str) -> set[str]:
        seen: set[str] = set()
        stack = list(graph.dependencies.get(node, ()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(graph.dependencies.get(current, ()))
        return seen

    for lane in LANES:
        previous = upstream_lane(lane)
        if previous is None:
            continue
        required = set(binding.nodes_of(previous))
        for node in binding.nodes_of(lane):
            assert ancestors(node) & required, (lane, node)


def test_every_lane_states_why_it_drives_its_nodes() -> None:
    binding = load_phase_binding(ROOT)

    for lane in LANES:
        assert len(binding.reasons[lane]) > 50, lane


def test_the_binding_declares_its_contract() -> None:
    document = json.loads(BINDING_PATH.read_text(encoding="utf-8"))

    assert document["binding_contract"] == "epistemic-foundry-lane-phase-binding/v1"
    assert "EF4-I22" in document["$comment"]


def test_the_binding_file_is_canonical_json_on_disk() -> None:
    raw = BINDING_PATH.read_text(encoding="utf-8")

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )


def test_the_bound_dimension_is_one_the_budget_contract_declares() -> None:
    assert CONCURRENCY_DIMENSION in LIMIT_DIMENSIONS


def test_the_action_vocabulary_is_closed() -> None:
    assert len(ACTIONS) == len(set(ACTIONS)) == 4


def test_the_two_reconciliation_scopes_are_distinguishable() -> None:
    assert EFFECT_LEDGER_SCOPE != CANDIDATE_LEDGER_SCOPE


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 7
    for field, (code, message) in FINDING_CODES.items():
        assert "_" in field
        assert code.isupper()
        assert len(message) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = ScheduleError("LANE_BOUND_EXCEEDED", "message", {"lane": "x"})

    assert error.code == "LANE_BOUND_EXCEEDED"
    assert str(error) == "message"
    assert error.context == {"lane": "x"}


def test_the_binding_refuses_an_undeclared_lane() -> None:
    binding = load_phase_binding(ROOT)

    with pytest.raises(ScheduleError) as caught:
        binding.nodes_of("shipping")
    assert caught.value.code == "LANE_UNDECLARED"
