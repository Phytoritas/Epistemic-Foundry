"""Fixtures for the U05 Evolution Chamber console suites.

Every record here is a document its canonical schema accepts, because the
console projects real sealed artifacts: a fixture the schema would refuse would
test the fixture rather than the console.  The niches are built by the sealed
M05 cartographer and the challenge genomes and results by the sealed Red Queen
lab, so each self-referential hash is sealed with the same canonicalization the
console re-derives, and a canonical change breaks these fixtures instead of
letting them drift.  Enum-valued fields are read out of the schema that declares
them; the tests may name canonical values as literals because they live outside
``src`` and are not scanned by the wire-literal discipline.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.cartography.v4_m05.mapper import build_niche
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.red_queen_lab.challenges import (
    build_challenge_genome,
    build_challenge_result,
)

_registry = default_registry()

CHALLENGE_GENOME_SCHEMA = "challenge-genome"
CHALLENGE_RESULT_SCHEMA = "challenge-result"


def enum_of(schema_name: str, field: str) -> list[str]:
    """Every value the named schema declares for a scalar enum field."""
    return [
        str(value)
        for value in _registry.document(schema_name)["properties"][field]["enum"]
    ]


def pareto_snapshot(
    *,
    candidate_ids: list[str] | None = None,
    fitness_vector_ids: list[str] | None = None,
    objective_dimensions: list[str] | None = None,
    reference_point: list[float] | None = None,
    generation: int = 3,
    seal: bool = True,
) -> dict[str, Any]:
    """A Pareto-front snapshot the canonical schema accepts, sealed by default."""
    snapshot: dict[str, Any] = {
        "snapshot_id": "PFS-1",
        "evolution_run_id": "RUN-1",
        "generation": generation,
        "candidate_ids": candidate_ids or ["cand-b", "cand-a"],
        "fitness_vector_ids": fitness_vector_ids or ["fv-b", "fv-a"],
        "objective_dimensions": objective_dimensions or ["novelty", "quality"],
        "constraint_policy_version": "cp-v1",
        "hypervolume": 0.42,
        "reference_point": reference_point
        if reference_point is not None
        else [0.0, 0.0],
    }
    if seal:
        snapshot["snapshot_hash"] = hash_excluding(snapshot, "snapshot_hash")
    return snapshot


def axis_values(suffix: str = "1") -> dict[str, str]:
    """A full set of the five declared niche axes."""
    return {
        "mechanism_family": f"mech-{suffix}",
        "scope_class": f"scope-{suffix}",
        "evidence_state": f"evidence-{suffix}",
        "testability_band": f"test-{suffix}",
        "causal_status": f"causal-{suffix}",
    }


def niche(
    *,
    suffix: str = "1",
    capacity: int = 2,
    occupant_ids: list[str] | None = None,
    elite_id: str | None = "cand-a",
    coverage_debt: float = 0.25,
) -> dict[str, Any]:
    """One sealed niche cell built by the M05 cartographer."""
    return build_niche(
        axis_values=axis_values(suffix),
        capacity=capacity,
        occupant_ids=occupant_ids if occupant_ids is not None else ["cand-a"],
        elite_id=elite_id,
        coverage_debt=coverage_debt,
    )


def two_niches() -> list[dict[str, Any]]:
    """Two distinct cells with disjoint occupants."""
    return [
        niche(suffix="1", occupant_ids=["cand-a"], elite_id="cand-a"),
        niche(suffix="2", occupant_ids=["cand-b", "cand-c"], elite_id="cand-b"),
    ]


def lineage(
    *,
    candidate_id: str = "cand-a",
    lineage_id: str = "LIN-a",
    parent_ids: list[str] | None = None,
    generation: int = 0,
    island_id: str = "island-1",
) -> dict[str, Any]:
    """A candidate-lineage record the canonical schema accepts."""
    return {
        "lineage_id": lineage_id,
        "candidate_id": candidate_id,
        "parent_ids": parent_ids or [],
        "inspiration_ids": [],
        "mutation_operator_ids": ["op-1"],
        "crossover_parent_ids": [],
        "generation": generation,
        "island_id": island_id,
        "ancestor_hashes": [],
        "created_at": "2026-08-02T00:00:00.000Z",
    }


def two_lineages() -> list[dict[str, Any]]:
    return [
        lineage(candidate_id="cand-a", lineage_id="LIN-a"),
        lineage(
            candidate_id="cand-b",
            lineage_id="LIN-b",
            parent_ids=["cand-a"],
            generation=1,
        ),
    ]


def challenge_genome(
    *,
    challenge_genome_id: str = "CG-1",
    target_genome_id: str = "TG-1",
    challenge_class: str | None = None,
    safety_class: str | None = None,
) -> dict[str, Any]:
    """A challenge genome sealed by the Red Queen lab."""
    return build_challenge_genome(
        target_genome_id=target_genome_id,
        challenge_class=challenge_class
        or enum_of(CHALLENGE_GENOME_SCHEMA, "challenge_class")[0],
        construction="perturb the mechanism and measure the effect",
        success_criterion="candidate effect vanishes under the perturbation",
        required_capabilities=[],
        lineage_id="CL-1",
        safety_class=safety_class
        or enum_of(CHALLENGE_GENOME_SCHEMA, "safety_class")[0],
        challenge_genome_id=challenge_genome_id,
    )


def challenge_result(
    *,
    challenge_result_id: str = "CR-1",
    challenge_genome_id: str = "CG-1",
    target_candidate_id: str = "cand-a",
    outcome: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    """A challenge result sealed by the Red Queen lab (survival by default)."""
    return build_challenge_result(
        challenge_genome_id=challenge_genome_id,
        target_candidate_id=target_candidate_id,
        stage_result_id="SR-1",
        outcome=outcome or enum_of(CHALLENGE_RESULT_SCHEMA, "outcome")[0],
        severity=severity or enum_of(CHALLENGE_RESULT_SCHEMA, "severity")[2],
        observed_effect="the candidate withstood the perturbation",
        challenge_result_id=challenge_result_id,
    )
