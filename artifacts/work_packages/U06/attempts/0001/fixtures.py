"""Fixtures for the U06 operator usability gate suites.

The gate composes the sealed U05 console, which projects real sealed artifacts,
so every surface fixture here is a document its canonical schema accepts: a
fixture the schema would refuse would test the fixture rather than the gate. The
niches are built by the sealed M05 cartographer and the challenge genomes and
results by the sealed Red Queen lab, so each self-referential hash is sealed with
the same canonicalization the console re-derives. Enum-valued fields are read out
of the schema that declares them; these tests may name canonical values as
literals because they live outside ``src`` and are not scanned by the
wire-literal discipline.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.cartography.v4_m05.mapper import build_niche
from epistemic_foundry.console.v4_u05 import (
    SURFACE_CHALLENGE_BOARD,
    SURFACE_LINEAGES,
    SURFACE_NICHE_MAP,
    SURFACE_PARETO_FRONT,
)
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.red_queen_lab.challenges import (
    build_challenge_genome,
    build_challenge_result,
)

#: The caller-supplied timestamp. The gate reads no clock, so a receipt is a pure
#: function of its content including this value; two runs over equal inputs and
#: this timestamp are byte-equal.
CREATED_AT = "2026-08-02T00:00:00.000Z"

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
    seal: bool = True,
) -> dict[str, Any]:
    """A Pareto-front snapshot the canonical schema accepts, sealed by default."""
    snapshot: dict[str, Any] = {
        "snapshot_id": "PFS-1",
        "evolution_run_id": "RUN-1",
        "generation": 3,
        "candidate_ids": candidate_ids or ["cand-b", "cand-a"],
        "fitness_vector_ids": fitness_vector_ids or ["fv-b", "fv-a"],
        "objective_dimensions": ["novelty", "quality"],
        "constraint_policy_version": "cp-v1",
        "hypervolume": 0.42,
        "reference_point": [0.0, 0.0],
    }
    if seal:
        snapshot["snapshot_hash"] = hash_excluding(snapshot, "snapshot_hash")
    return snapshot


def _axis_values(suffix: str) -> dict[str, str]:
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
    occupant_ids: list[str] | None = None,
    elite_id: str | None = "cand-a",
) -> dict[str, Any]:
    """One sealed niche cell built by the M05 cartographer."""
    return build_niche(
        axis_values=_axis_values(suffix),
        capacity=2,
        occupant_ids=occupant_ids if occupant_ids is not None else ["cand-a"],
        elite_id=elite_id,
        coverage_debt=0.25,
    )


def two_niches() -> list[dict[str, Any]]:
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
        "island_id": "island-1",
        "ancestor_hashes": [],
        "created_at": CREATED_AT,
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


def challenge_genome(*, challenge_genome_id: str = "CG-1") -> dict[str, Any]:
    """A challenge genome sealed by the Red Queen lab."""
    return build_challenge_genome(
        target_genome_id="TG-1",
        challenge_class=enum_of(CHALLENGE_GENOME_SCHEMA, "challenge_class")[0],
        construction="perturb the mechanism and measure the effect",
        success_criterion="candidate effect vanishes under the perturbation",
        required_capabilities=[],
        lineage_id="CL-1",
        safety_class=enum_of(CHALLENGE_GENOME_SCHEMA, "safety_class")[0],
        challenge_genome_id=challenge_genome_id,
    )


def challenge_result(
    *, challenge_result_id: str = "CR-1", challenge_genome_id: str = "CG-1"
) -> dict[str, Any]:
    """A challenge result sealed by the Red Queen lab (survival by default)."""
    return build_challenge_result(
        challenge_genome_id=challenge_genome_id,
        target_candidate_id="cand-a",
        stage_result_id="SR-1",
        outcome=enum_of(CHALLENGE_RESULT_SCHEMA, "outcome")[0],
        severity=enum_of(CHALLENGE_RESULT_SCHEMA, "severity")[2],
        observed_effect="the candidate withstood the perturbation",
        challenge_result_id=challenge_result_id,
    )


# -- payloads the gate consumes -------------------------------------------


def pareto_payload() -> dict[str, Any]:
    return {"snapshot": pareto_snapshot()}


def niche_payload() -> dict[str, Any]:
    return {"niches": two_niches()}


def lineage_payload() -> dict[str, Any]:
    return {"lineages": two_lineages()}


def challenge_payload() -> dict[str, Any]:
    return {
        "genomes": [challenge_genome()],
        "challenge_results": [challenge_result()],
    }


def empty_challenge_payload() -> dict[str, Any]:
    """A challenge board that projects cleanly and holds nothing."""
    return {"genomes": [], "challenge_results": []}


SURFACES = {
    "pareto": SURFACE_PARETO_FRONT,
    "niche": SURFACE_NICHE_MAP,
    "lineages": SURFACE_LINEAGES,
    "challenge": SURFACE_CHALLENGE_BOARD,
}
