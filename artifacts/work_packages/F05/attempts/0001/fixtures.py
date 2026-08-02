"""Run fixtures built from the workflow's own declared graph.

The node ids are never typed out here: they are read from
``workflows/evolution_chamber_cycle.workflow.yaml`` through the machine's own
loader, so a workflow that renames a node breaks these fixtures instead of
letting them drift into describing a graph that no longer exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_foundry.evolution.v4_f05 import Transition, load_graph

ROOT = Path(__file__).resolve().parents[5]
GRAPH = load_graph(ROOT)
#: The loop the EVOLVE cycle actually closes: scoring returns to selection.
LOOP_EXIT = "commit_evolution_checkpoint"
LOOP_ENTRY = "select_epistemic_parents"
RUN_ID = "ER-F05-1"


def checkpoint(index: int = 1) -> dict[str, Any]:
    """A complete checkpoint payload, every declared component present."""

    return {
        "population_artifact_ids": [f"POP-{index}"],
        "archive_snapshot_id": f"ARCH-{index}",
        "island_state_ids": [f"ISL-{index}"],
        "operator_bandit_state_id": f"BANDIT-{index}",
        "evaluator_bundle_hash": "sha256:" + "a" * 64,
        "budget_state_id": f"BUDGET-{index}",
        "sequential_testing_ledger_id": f"LEDGER-{index}",
    }


def loop_contract(max_iterations: int = 3, dry_rounds_required: int = 1) -> dict:
    return {
        "loop_id": "LOOP-EVOLVE-1",
        "workflow_id": "evolution_chamber_cycle",
        "entry_node_id": LOOP_ENTRY,
        "exit_node_id": LOOP_EXIT,
        "max_iterations": max_iterations,
        "dry_rounds_required": dry_rounds_required,
    }


def forward_path() -> list[Transition]:
    """One legal forward move per node that declares a dependency."""

    moves: list[Transition] = []
    for node in GRAPH.nodes:
        for upstream in GRAPH.depends_on(node):
            moves.append(Transition(source=upstream, target=node))
    return moves


def loop_back(index: int = 1, *, complete: bool = True) -> Transition:
    return Transition(
        source=LOOP_EXIT,
        target=LOOP_ENTRY,
        checkpoint_id=f"CP-{index}",
        checkpoint=checkpoint(index) if complete else {"archive_snapshot_id": "A"},
    )


def stop_certificate(
    reason: str = "dry_rounds",
    *,
    conditions: tuple[str, ...] = ("no fresh candidates for two rounds",),
    partial_visible: bool = True,
    checkpoint_id: str = "CP-1",
    unresolved: tuple[str, ...] = ("CAND-9",),
    unassessed: tuple[str, ...] = ("NICHE-3",),
) -> dict[str, Any]:
    """A stop certificate shaped like the canonical contract."""

    return {
        "certificate_id": "ESC-1",
        "evolution_run_id": RUN_ID,
        "stop_reason": reason,
        "conditions_observed": list(conditions),
        "unresolved_candidates": list(unresolved),
        "unassessed_niches": list(unassessed),
        "partial_results_visible": partial_visible,
        "checkpoint_id": checkpoint_id,
    }


def clean_run(iterations: int = 2) -> dict[str, Any]:
    """A run that loops within budget and stops with a certificate."""

    moves = forward_path()
    for index in range(1, iterations + 1):
        moves.append(loop_back(index))
    return {
        "transitions": moves,
        "loop_contract": loop_contract(),
        "stop_certificate": stop_certificate(),
        "dry_rounds_observed": 2,
    }
