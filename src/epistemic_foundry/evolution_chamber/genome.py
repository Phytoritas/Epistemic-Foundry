"""Hypothesis genome completeness (EF4-I42).

Contract source: `schemas/hypothesis-genome.schema.json`.

An evolvable hypothesis must carry scope, mechanism, predictions, falsifiers,
alternatives, measurement contracts, evidence, a validation plan, and immutable
lineage. The falsifier and the alternatives are the two that make evolution
meaningful rather than decorative: without a falsifier a mutation cannot be shown
wrong, and without named alternatives a surviving candidate has beaten nothing.

`ELIGIBLE` is therefore not a status a caller may assert. It is derived from
completeness, so a draft genome cannot enter the population by relabeling.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Fields whose absence makes a genome unevolvable rather than merely incomplete.
EVOLVABILITY_REQUIRED: tuple[str, ...] = (
    "scope_vector_id",
    "mechanism_graph_id",
    "prediction_gene_ids",
    "falsifier_gene_ids",
    "alternative_hypothesis_ids",
    "measurement_contract_ids",
    "evidence_pack_id",
    "validation_plan_id",
    "lineage_id",
)


class GenomeIncomplete(ValueError):
    """A genome lacks what evolution needs to test it."""


def evolvability_gaps(genome: Mapping[str, Any]) -> list[str]:
    """Required elements this genome does not carry.

    List-valued fields must be non-empty: an empty falsifier list is the same
    unevolvable state as a missing one, and treating them differently would let a
    genome pass by declaring the field and leaving it blank.
    """
    gaps: list[str] = []
    for field in EVOLVABILITY_REQUIRED:
        value = genome.get(field)
        if value is None or value == "" or value == []:
            gaps.append(field)
    return gaps


def build_hypothesis_genome(
    *,
    canonical_claim: str,
    scope_vector_id: str,
    mechanism_graph_id: str,
    prediction_gene_ids: Sequence[str],
    falsifier_gene_ids: Sequence[str],
    alternative_hypothesis_ids: Sequence[str],
    measurement_contract_ids: Sequence[str],
    evidence_pack_id: str,
    validation_plan_id: str,
    lineage_id: str,
    complexity_budget: int,
    uncertainty_notes: Sequence[str],
    provenance_hash: str,
    revision: int = 1,
    genome_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a genome whose status is derived from its completeness.

    `status` is not a parameter: a caller able to assert `ELIGIBLE` could put an
    untestable draft into the population.

    The schema independently requires non-empty prediction and falsifier lists, so
    `build_hypothesis_genome` cannot even represent an unevolvable genome. That
    makes the status derivation a second line rather than the only one, and
    `evolvability_gaps` remains useful for genomes arriving from elsewhere.
    """
    genome: dict[str, Any] = {
        "genome_id": genome_id or new_id("HG"),
        "revision": int(revision),
        "status": "DRAFT",
        "canonical_claim": canonical_claim,
        "scope_vector_id": scope_vector_id,
        "mechanism_graph_id": mechanism_graph_id,
        "prediction_gene_ids": list(prediction_gene_ids),
        "falsifier_gene_ids": list(falsifier_gene_ids),
        "alternative_hypothesis_ids": list(alternative_hypothesis_ids),
        "measurement_contract_ids": list(measurement_contract_ids),
        "evidence_pack_id": evidence_pack_id,
        "validation_plan_id": validation_plan_id,
        "lineage_id": lineage_id,
        "complexity_budget": int(complexity_budget),
        "uncertainty_notes": list(uncertainty_notes),
        "provenance_hash": provenance_hash,
        "created_at": created_at or utc_now_iso(),
    }
    gaps = evolvability_gaps(genome)
    genome["status"] = "DRAFT" if gaps else "ELIGIBLE"
    validate_artifact("hypothesis-genome", genome)
    return genome


def require_evolvable(genome: Mapping[str, Any]) -> None:
    """Raise `GenomeIncomplete` unless the genome can actually be tested."""
    gaps = evolvability_gaps(genome)
    if gaps:
        raise GenomeIncomplete(
            f"genome {genome.get('genome_id')} cannot enter the population: missing {gaps}. "
            "Without a falsifier a mutation cannot be shown wrong, and without alternatives a "
            "survivor has beaten nothing"
        )


def is_evolvable(genome: Mapping[str, Any]) -> bool:
    """Non-raising completeness check."""
    return not evolvability_gaps(genome)
