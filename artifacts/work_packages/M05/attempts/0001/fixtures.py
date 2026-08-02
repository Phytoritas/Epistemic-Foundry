"""Fixtures for the M05 cartography suites.

Axis names are never typed out: coordinates are built over the axis vocabulary
the engine reads from the canonical niche schema, so a schema change breaks
these fixtures instead of letting them drift.  Lineage records validate on
construction through the sealed L05 memory.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.cartography.v4_m05 import axis_vocabulary, build_niche
from epistemic_foundry.memory.v4_l05 import LineageMemory

AXES = axis_vocabulary()
RECORDED_AT = "2026-08-02T00:00:00.000Z"
RUN_ID = "ER-M05-1"
THRESHOLDS = {
    "dominant_lineage_share_max": 0.5,
    "effective_lineage_count_min": 2.0,
}


def lineage_record(
    candidate_id: str,
    parent_ids: list[str],
    generation: int,
    *,
    operators: tuple[str, ...] = ("MO-POINT-1",),
    crossover: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "lineage_id": f"LIN-{candidate_id}",
        "candidate_id": candidate_id,
        "parent_ids": list(parent_ids),
        "inspiration_ids": [],
        "mutation_operator_ids": list(operators),
        "crossover_parent_ids": list(crossover),
        "generation": generation,
        "island_id": "IS-1",
        "ancestor_hashes": ["sha256:" + "a" * 64],
        "created_at": RECORDED_AT,
    }


def coordinates(marker: str) -> dict[str, str]:
    """One cell, distinguished from every other cell by its first axis."""
    values = {axis: f"{axis}-baseline" for axis in AXES}
    values[AXES[0]] = marker
    return values


def niche(
    marker: str,
    occupants: list[str],
    *,
    capacity: int = 3,
    elite_id: str | None = None,
    coverage_debt: float = 0.0,
) -> dict[str, Any]:
    return build_niche(
        axis_values=coordinates(marker),
        capacity=capacity,
        occupant_ids=occupants,
        elite_id=elite_id,
        coverage_debt=coverage_debt,
    )


def population() -> LineageMemory:
    """Two founder lineages plus a crossover child of a single lineage.

    C1 founds the dominant lineage (children C2 and C3, and X1 crossing C2
    with C3); D1 founds the minority lineage.
    """
    return LineageMemory(
        [
            lineage_record("C1", [], 1),
            lineage_record("C2", ["C1"], 2),
            lineage_record("C3", ["C1"], 2),
            lineage_record("D1", [], 1),
            lineage_record("X1", ["C2", "C3"], 3, crossover=("C2", "C3")),
        ]
    )


def models(memory: LineageMemory, name: str = "model-a") -> dict[str, str]:
    return {candidate: name for candidate in memory.candidates()}
