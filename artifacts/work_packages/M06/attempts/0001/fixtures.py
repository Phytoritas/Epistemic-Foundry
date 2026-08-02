"""Fixtures for the M06 cartography integration suites.

Nothing here hand-writes a niche, a coverage map or a diversity report: cells
come from M05's ``build_niche``, coverage from M05's ``build_coverage_map``,
diversity from M05's ``build_lineage_diversity_report`` and the blast radius
from M05's ``compute_blast_radius``, so the gate is exercised against records
the sealed builders actually emit rather than against a plausible shape.

Axis names come from the canonical niche schema and the archive entry class
from the sealed vocabulary check, so a schema change breaks these fixtures
instead of letting them drift.  The class chosen is deliberately an ordinary
one: M06 does not interpret an entry's class, and picking a meaningful-looking
value here would suggest it does.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.cartography.v4_m05 import (
    NicheMap,
    axis_vocabulary,
    build_coverage_map,
    build_lineage_diversity_report,
    build_niche,
    compute_blast_radius,
)
from epistemic_foundry.cartography.v4_m06 import (
    bind_derived_record,
    build_map_revision,
)
from epistemic_foundry.epistemic_species_archive.archive import (
    EVICTABLE_ENTRY_CLASSES,
    build_archive_entry,
)
from epistemic_foundry.memory.v4_l05 import LineageMemory, entry_class_vocabulary

AXES = axis_vocabulary()
RECORDED_AT = "2026-08-02T00:00:00.000Z"
RUN_ID = "ER-M06-1"
THRESHOLDS = {
    "dominant_lineage_share_max": 0.5,
    "effective_lineage_count_min": 2.0,
}

#: An entry class the archive treats as ordinary. Read from the sealed
#: partition rather than typed out, so the canonical vocabulary stays the only
#: place the value is declared (EF4-I22).
ENTRY_CLASS = sorted(set(entry_class_vocabulary()) & EVICTABLE_ENTRY_CLASSES)[0]

#: A canonical schema the gate does not treat as carrying promotion authority,
#: used to prove a citation to a real artifact is still not authority.
NON_AUTHORITY_SCHEMA = "fitness-vector"


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


def board() -> NicheMap:
    """Three cells holding the whole population, each with an elite."""
    return NicheMap(
        [
            niche("a", ["C1", "C2"], elite_id="C1"),
            niche("b", ["C3", "X1"], elite_id="X1"),
            niche("c", ["D1"], elite_id="D1"),
        ]
    )


def entry(
    candidate_id: str,
    niche_id: str,
    *,
    entry_class: str = ENTRY_CLASS,
    archive_entry_id: str | None = None,
) -> dict[str, Any]:
    return build_archive_entry(
        candidate_id=candidate_id,
        entry_class=entry_class,
        niche_id=niche_id,
        fitness_vector_id=f"FV-{candidate_id}",
        lineage_id=f"LIN-{candidate_id}",
        retention_reason="fixture entry retained so the map has something to agree with",
        replacement_policy="never",
        artifact_payload={"candidate_id": candidate_id},
        archive_entry_id=archive_entry_id or f"AE-{candidate_id}",
        archived_at=RECORDED_AT,
    )


def entries(niche_map: NicheMap) -> list[dict[str, Any]]:
    """One archive entry per occupant, filed against the cell it occupies."""
    return [
        entry(candidate_id, niche_id)
        for candidate_id, niche_id in sorted(niche_map.occupants().items())
    ]


def coverage(
    niche_map: NicheMap,
    *,
    generation: int = 3,
    lineage_entropy: float = 0.5,
    map_id: str = "QDM-M06-1",
) -> dict[str, Any]:
    return build_coverage_map(
        niche_map=niche_map,
        evolution_run_id=RUN_ID,
        generation=generation,
        lineage_entropy=lineage_entropy,
        map_id=map_id,
    )


def diversity(
    memory: LineageMemory | None = None,
    *,
    generation: int = 3,
    report_id: str = "LDR-M06-1",
) -> dict[str, Any]:
    resolved = memory or population()
    return build_lineage_diversity_report(
        lineage=resolved,
        evolution_run_id=RUN_ID,
        generation=generation,
        model_attribution=models(resolved),
        thresholds=dict(THRESHOLDS),
        report_id=report_id,
    )


def radius(
    niche_map: NicheMap,
    memory: LineageMemory | None = None,
    *,
    candidate_id: str = "C1",
) -> dict[str, Any]:
    return compute_blast_radius(
        lineage=memory or population(),
        niche_map=niche_map,
        candidate_id=candidate_id,
    )


def revision(
    niche_map: NicheMap,
    *,
    generation: int = 3,
    revision_id: str = "MRV-M06-1",
) -> dict[str, Any]:
    return build_map_revision(
        niche_map=niche_map,
        evolution_run_id=RUN_ID,
        generation=generation,
        revision_id=revision_id,
    )


def derived(niche_map: NicheMap, source: dict[str, Any]) -> list[dict[str, Any]]:
    """The two records a map revision propagates into, bound to that revision."""
    return [
        bind_derived_record(
            record=coverage(niche_map, generation=int(source["generation"])),
            record_kind="coverage_map",
            revision=source,
        ),
        bind_derived_record(
            record=radius(niche_map),
            record_kind="blast_radius",
            revision=source,
        ),
    ]


def figure_citation(source_id: str, figure: str, value: Any) -> dict[str, Any]:
    return {"figure": figure, "source_id": source_id, "value": value}


def authority_citation(
    artifact_id: str = "GD-M06-1", schema: str = "gate-decision"
) -> dict[str, Any]:
    return {"artifact_id": artifact_id, "schema": schema}


def promotion_request(
    citations: list[dict[str, Any]],
    *,
    candidate_id: str = "C1",
    request_id: str = "PR-M06-1",
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "citations": list(citations),
        "request_id": request_id,
    }
