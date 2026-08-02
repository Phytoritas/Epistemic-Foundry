"""Fixtures for the F06 lifecycle+replay gate suites.

The gate is an integration surface, so a fixture that the composed F05, I05 and
R05 surfaces would themselves refuse would test the fixture rather than the gate.
Every document here is therefore one those surfaces accept: the EVOLVE run is a
clean run the F05 machine walks without complaint, built from the workflow's own
declared graph; the seed submissions are genomes I05 intake admits; the FORGE
session and the replay report are read out of their canonical schemas so a
canonical change breaks these fixtures instead of letting them drift.

The happy case is assembled once and every negative case is one deviation from
it, so a refusal test isolates exactly the axis it names.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f05 import Transition, load_graph
from epistemic_foundry.evolution.v4_f06 import evolve_handoff_phase
from epistemic_foundry.intake.v4_i05 import GENOME_KIND

_registry = default_registry()
ROOT = Path(__file__).resolve().parents[5]
GRAPH = load_graph(ROOT)

#: The loop the EVOLVE cycle closes: the committed checkpoint returns to parent
#: selection. Read from the workflow through the machine's own loader.
LOOP_EXIT = "commit_evolution_checkpoint"
LOOP_ENTRY = "select_epistemic_parents"

RUN_ID = "ER-F06-1"
RUN_SPEC_ID = "RS-F06-1"
SESSION_ID = "FS-F06-1"
WORKSPACE_ID = "WS-F06-1"
ISLAND = "IS-F06-1"
LINE = "LIN-F06-1"
CREATED_AT = "2026-08-02T00:00:00.000Z"
SCREENED_AT = "2026-08-02T00:05:00.000Z"
GATE_AT = "2026-08-02T02:00:00.000Z"
EVALUATOR_HASH = "sha256:" + "a" * 64
OTHER_EVALUATOR_HASH = "sha256:" + "b" * 64
A_HASH = "sha256:" + "c" * 64


def _first_enum(schema_name: str, field: str) -> str:
    return str(_registry.document(schema_name)["properties"][field]["enum"][0])


def _phases() -> list[str]:
    return [
        str(v)
        for v in _registry.document("forge-session-state")["properties"]["phase"][
            "enum"
        ]
    ]


DRAFT_STATUS = _first_enum(GENOME_KIND, "status")
WORK_CLASS = _first_enum("forge-session-state", "work_class")
SESSION_STATUS = _first_enum("forge-session-state", "status")
STRICT_MODE = str(_registry.document("replay-report")["properties"]["mode"]["enum"][0])
EXACT = str(
    _registry.document("replay-report")["properties"]["event_equivalence"]["enum"][0]
)
NO_DRIFT = str(
    _registry.document("replay-report")["properties"]["drift_classification"]["enum"][0]
)


# --------------------------------------------------------------------------- #
# I05 seed submissions
# --------------------------------------------------------------------------- #
def genome(
    genome_id: str = "HG-1",
    *,
    mechanism: str = "MG-1",
    scope: str = "SV-1",
    lineage_id: str = LINE,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid hypothesis genome with a declared falsifier and scope."""
    document: dict[str, Any] = {
        "genome_id": genome_id,
        "revision": 1,
        "status": DRAFT_STATUS,
        "canonical_claim": (
            "raising root-zone electrical conductivity lowers stomatal "
            "conductance within one diurnal cycle"
        ),
        "scope_vector_id": scope,
        "mechanism_graph_id": mechanism,
        "prediction_gene_ids": [f"PG-{genome_id}-1", f"PG-{genome_id}-2"],
        "falsifier_gene_ids": [f"FG-{genome_id}"],
        "alternative_hypothesis_ids": [],
        "measurement_contract_ids": [f"MC-{genome_id}"],
        "evidence_pack_id": f"EP-{genome_id}",
        "validation_plan_id": f"VP-{genome_id}",
        "lineage_id": lineage_id,
        "complexity_budget": 4,
        "uncertainty_notes": [],
        "provenance_hash": A_HASH,
        "created_at": CREATED_AT,
    }
    document.update(overrides)
    return document


def submission(genome_id: str = "HG-1", **overrides: Any) -> dict[str, Any]:
    """One I05 intake envelope carrying a hypothesis genome."""
    return {"genome_kind": GENOME_KIND, "genome": genome(genome_id, **overrides)}


# --------------------------------------------------------------------------- #
# F05 EVOLVE run
# --------------------------------------------------------------------------- #
def checkpoint(
    index: int = 1, *, evaluator_hash: str = EVALUATOR_HASH
) -> dict[str, Any]:
    """A complete checkpoint component map, every declared component present."""
    return {
        "population_artifact_ids": [f"POP-{index}"],
        "archive_snapshot_id": f"ARCH-{index}",
        "island_state_ids": [f"ISL-{index}"],
        "operator_bandit_state_id": f"BANDIT-{index}",
        "evaluator_bundle_hash": evaluator_hash,
        "budget_state_id": f"BUDGET-{index}",
        "sequential_testing_ledger_id": f"LEDGER-{index}",
    }


def loop_contract(
    max_iterations: int = 3, dry_rounds_required: int = 1
) -> dict[str, Any]:
    return {
        "loop_id": "LOOP-EVOLVE-1",
        "workflow_id": "evolution_chamber_cycle",
        "entry_node_id": LOOP_ENTRY,
        "exit_node_id": LOOP_EXIT,
        "max_iterations": max_iterations,
        "dry_rounds_required": dry_rounds_required,
    }


def forward_path() -> list[Transition]:
    """One legal forward move per declared dependency edge."""
    moves: list[Transition] = []
    for node in GRAPH.nodes:
        for upstream in GRAPH.depends_on(node):
            moves.append(Transition(source=upstream, target=node))
    return moves


def loop_back(index: int = 1, *, evaluator_hash: str = EVALUATOR_HASH) -> Transition:
    return Transition(
        source=LOOP_EXIT,
        target=LOOP_ENTRY,
        checkpoint_id=f"CP-{index}",
        checkpoint=checkpoint(index, evaluator_hash=evaluator_hash),
    )


def stop_certificate(
    *,
    reason: str = "dry_rounds",
    checkpoint_id: str = "CP-1",
    evolution_run_id: str = RUN_ID,
    partial_visible: bool = True,
) -> dict[str, Any]:
    return {
        "certificate_id": "ESC-1",
        "evolution_run_id": evolution_run_id,
        "stop_reason": reason,
        "conditions_observed": ["no fresh candidates for two rounds"],
        "unresolved_candidates": ["CAND-9"],
        "unassessed_niches": ["NICHE-3"],
        "partial_results_visible": partial_visible,
        "checkpoint_id": checkpoint_id,
    }


def transitions(
    iterations: int = 2, *, evaluator_hashes: list[str] | None = None
) -> list[Transition]:
    """A forward walk plus `iterations` committed return edges."""
    moves = forward_path()
    hashes = evaluator_hashes or [EVALUATOR_HASH] * iterations
    for index in range(1, iterations + 1):
        moves.append(loop_back(index, evaluator_hash=hashes[index - 1]))
    return moves


def run(**overrides: Any) -> dict[str, Any]:
    """A clean EVOLVE run: seeded, looped within budget, stopped and reconciled."""
    document: dict[str, Any] = {
        "evolution_run_id": RUN_ID,
        "run_spec_id": RUN_SPEC_ID,
        "seed_submissions": [submission("HG-1")],
        "minimum_signature_diversity": 1,
        "island_id": ISLAND,
        "transitions": transitions(2),
        "loop_contract": loop_contract(),
        "stop_certificate": stop_certificate(),
        "dry_rounds_observed": 2,
        "operator_applications": [
            {"operator_id": "mechanism-refinement", "child_genome_id": "HG-CHILD-1"}
        ],
        "seed_genome_ids": ["HG-1"],
        "candidate_genome_ids": ["HG-1", "HG-CHILD-1"],
    }
    document.update(overrides)
    return document


# --------------------------------------------------------------------------- #
# FORGE session
# --------------------------------------------------------------------------- #
def forge_session(**overrides: Any) -> dict[str, Any]:
    """A schema-valid FORGE session that reached the EVOLVE handoff phase."""
    phases = _phases()
    evolve_phase = evolve_handoff_phase()
    previous = phases[-2]
    session: dict[str, Any] = {
        "session_id": SESSION_ID,
        "workspace_id": WORKSPACE_ID,
        "revision": 3,
        "phase": evolve_phase,
        "work_class": WORK_CLASS,
        "status": SESSION_STATUS,
        "run_spec_id": RUN_SPEC_ID,
        "hypothesis_revision_ids": ["HR-1"],
        "artifact_ids": ["ART-1"],
        "open_blockers": [],
        "phase_history": [
            {
                "from": previous,
                "to": evolve_phase,
                "event_id": "EV-HANDOFF-1",
                "at": CREATED_AT,
            }
        ],
        "policy_hash": "sha256:" + "d" * 64,
        "corpus_snapshot_hash": "sha256:" + "e" * 64,
        "updated_at": CREATED_AT,
    }
    session.update(overrides)
    session["state_hash"] = hash_excluding(session, "state_hash")
    return session


# --------------------------------------------------------------------------- #
# Replay report
# --------------------------------------------------------------------------- #
def replay_report(**overrides: Any) -> dict[str, Any]:
    """A schema-valid ReplayReport describing a strict, exact, drift-free replay."""
    report: dict[str, Any] = {
        "replay_id": "RPL-F06-1",
        "source_run_id": RUN_ID,
        "replay_run_id": "ER-F06-1-REPLAY",
        "mode": STRICT_MODE,
        "pinned_artifacts": ["PIN-1", "PIN-2"],
        "unavailable_pins": [],
        "event_equivalence": EXACT,
        "artifact_hash_matches": 12,
        "artifact_hash_mismatches": 0,
        "gate_differences": [],
        "verdict_differences": [],
        "drift_classification": NO_DRIFT,
        "created_at": CREATED_AT,
    }
    report.update(overrides)
    report["report_hash"] = hash_excluding(report, "report_hash")
    return report


# --------------------------------------------------------------------------- #
# Assembled cases
# --------------------------------------------------------------------------- #
def happy_case(**overrides: Any) -> dict[str, Any]:
    """The full set of arguments the gate admits, ready to be perturbed."""
    case: dict[str, Any] = {
        "forge_session": forge_session(),
        "run": run(),
        "replay_report": replay_report(),
        "created_at": GATE_AT,
        "screened_at": SCREENED_AT,
        "repository_root": ROOT,
    }
    case.update(overrides)
    return case


def deep_copy_case(case: dict[str, Any]) -> dict[str, Any]:
    """A copy in which every mapping/list can be perturbed without side effects.

    ``run.transitions`` holds frozen F05 ``Transition`` dataclasses, which are
    immutable and shared safely, so only the surrounding containers are copied.
    """
    clone = dict(case)
    clone["forge_session"] = copy.deepcopy(case["forge_session"])
    clone["replay_report"] = copy.deepcopy(case["replay_report"])
    source_run = case["run"]
    run_clone = {
        key: copy.deepcopy(value)
        for key, value in source_run.items()
        if key != "transitions"
    }
    run_clone["transitions"] = list(source_run["transitions"])
    clone["run"] = run_clone
    return clone
