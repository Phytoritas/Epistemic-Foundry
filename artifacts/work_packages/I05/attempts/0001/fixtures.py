"""Fixtures for the I05 genome intake suites.

Every genome here is a document the canonical schema accepts, because the
engine screens real documents: a fixture the schema would refuse would test the
fixture rather than the screen.  The status value and the genome kind are read
from the schema and from the engine's own sealed lookup rather than typed out,
so a canonical change breaks these fixtures instead of letting them drift.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.intake.v4_i05 import GENOME_KIND

#: The first declared genome status: intake screens documents that have not yet
#: been evaluated, and the value comes from the schema that declares it.
DRAFT_STATUS = default_registry().document(GENOME_KIND)["properties"]["status"]["enum"][
    0
]

CREATED_AT = "2026-08-02T00:00:00.000Z"
SCREENED_AT = "2026-08-02T01:00:00.000Z"
ISLAND = "IS-I05-1"
A_HASH = "sha256:" + "a" * 64


def genome(
    genome_id: str = "HG-1",
    *,
    mechanism: str = "MG-1",
    scope: str = "SV-1",
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
        "prediction_gene_ids": [f"PG-{genome_id}"],
        "falsifier_gene_ids": [f"FG-{genome_id}"],
        "alternative_hypothesis_ids": [],
        "measurement_contract_ids": [f"MC-{genome_id}"],
        "evidence_pack_id": f"EP-{genome_id}",
        "validation_plan_id": f"VP-{genome_id}",
        "lineage_id": f"LIN-{genome_id}",
        "complexity_budget": 3,
        "uncertainty_notes": [],
        "provenance_hash": A_HASH,
        "created_at": CREATED_AT,
    }
    document.update(overrides)
    return document


def submission(document: Any = None, *, kind: str | None = None) -> dict[str, Any]:
    """One intake envelope: a declared kind and the document it claims to be."""
    return {
        "genome_kind": GENOME_KIND if kind is None else kind,
        "genome": genome() if document is None else document,
    }


def diverse_batch() -> list[dict[str, Any]]:
    """Three genomes over three distinct mechanism-and-scope signatures."""
    return [
        submission(genome("HG-1", mechanism="MG-1", scope="SV-1")),
        submission(genome("HG-2", mechanism="MG-2", scope="SV-1")),
        submission(genome("HG-3", mechanism="MG-2", scope="SV-2")),
    ]


def monoculture_batch() -> list[dict[str, Any]]:
    """Three differently named genomes proposing one mechanism over one scope."""
    return [
        submission(genome("HG-1", mechanism="MG-1", scope="SV-1")),
        submission(genome("HG-2", mechanism="MG-1", scope="SV-1")),
        submission(
            genome(
                "HG-3",
                mechanism="MG-1",
                scope="SV-1",
                canonical_claim="the same mechanism, worded differently",
            )
        ),
    ]


def bootstrap_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "submissions": diverse_batch(),
        "minimum_signature_diversity": 3,
        "island_id": ISLAND,
        "created_at": CREATED_AT,
        "screened_at": SCREENED_AT,
        "population_id": "SPB-I05-1",
        "report_id": "GSR-I05-1",
    }
    arguments.update(overrides)
    return arguments
