"""Fixtures for the I06 genome intake integration-gate suites.

Every genome, scope vector, falsifier gene and prediction gene here is a
document the canonical schema accepts, because the gate resolves references
across real documents: a fixture the schema would refuse would test the fixture
rather than the gate.  Enum-valued fields are read out of the schema that
declares them and the intake status is read through the gate's own accessor, so
a canonical change breaks these fixtures instead of letting them drift.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.intake.v4_i05 import GENOME_KIND
from epistemic_foundry.intake.v4_i06 import gate as gate_module

_registry = default_registry()

GENOME_ID = "HG-I06-1"
SCOPE_ID = "SV-I06-1"
OTHER_SCOPE_ID = "SV-I06-2"
PREDICTION_ID = "PG-I06-1"
FALSIFIER_ID = "FG-I06-1"
DECIDED_AT = "2026-08-02T00:00:00.000Z"
A_HASH = "sha256:" + "a" * 64

#: The lifecycle status a genome must carry at intake, read through the gate.
INTAKE_STATUS = gate_module.intake_status()


def _first_enum(schema_name: str, field: str) -> str:
    """The first value the named schema declares for that field."""
    return str(_registry.document(schema_name)["properties"][field]["enum"][0])


TRIGGER_TYPE = _first_enum(gate_module.FALSIFIER_KIND, "trigger_type")
SEVERITY = _first_enum(gate_module.FALSIFIER_KIND, "severity")
DIRECTION = _first_enum(gate_module.PREDICTION_KIND, "expected_direction")


def scope_vector(**overrides: Any) -> dict[str, Any]:
    """The domain-neutral scope vector the genome's scope_vector_id names."""
    document: dict[str, Any] = {
        "domain": None,
        "population": None,
        "entity_type": None,
        "entity_subtype": None,
        "unit_of_analysis": None,
        "setting": None,
        "geography": None,
        "jurisdiction": None,
        "language": None,
        "lifecycle_stage": None,
        "spatial_scale": None,
        "temporal_scale": None,
        "time_period": None,
        "measurement_time": None,
        "intervention_or_exposure": None,
        "comparator": None,
        "inclusion_criteria": [],
        "exclusion_criteria": [],
        "conditions": {},
        "domain_extensions": {},
    }
    document.update(overrides)
    return document


def prediction_gene(
    prediction_id: str = PREDICTION_ID,
    *,
    genome_id: str = GENOME_ID,
    scope_id: str = SCOPE_ID,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid prediction gene of the genome, scoped to its scope vector."""
    document: dict[str, Any] = {
        "prediction_gene_id": prediction_id,
        "genome_id": genome_id,
        "statement": "stomatal conductance falls within one diurnal cycle",
        "scope_vector_id": scope_id,
        "observable_id": f"OB-{prediction_id}",
        "expected_direction": DIRECTION,
        "expected_range": "a measurable decrease",
        "time_horizon": "one diurnal cycle",
        "discrimination_targets": [f"DT-{prediction_id}"],
        "pre_registered": True,
    }
    document.update(overrides)
    return document


def falsifier_gene(
    falsifier_id: str = FALSIFIER_ID,
    *,
    genome_id: str = GENOME_ID,
    linked_prediction_ids: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid falsifier gene of the genome, linking its prediction."""
    document: dict[str, Any] = {
        "falsifier_gene_id": falsifier_id,
        "genome_id": genome_id,
        "statement": "the predicted direction reverses under the matched control",
        "trigger_type": TRIGGER_TYPE,
        "observable_condition": "withhold irrigation on the control block",
        "decision_rule": "reject the hypothesis if the direction reverses",
        "severity": SEVERITY,
        "linked_prediction_ids": (
            [PREDICTION_ID] if linked_prediction_ids is None else linked_prediction_ids
        ),
    }
    document.update(overrides)
    return document


def genome(
    genome_id: str = GENOME_ID,
    *,
    scope_id: str = SCOPE_ID,
    prediction_ids: list[str] | None = None,
    falsifier_ids: list[str] | None = None,
    status: str = INTAKE_STATUS,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid hypothesis genome that declares its scope and falsifier."""
    document: dict[str, Any] = {
        "genome_id": genome_id,
        "revision": 1,
        "status": status,
        "canonical_claim": (
            "raising root-zone electrical conductivity lowers stomatal "
            "conductance within one diurnal cycle"
        ),
        "scope_vector_id": scope_id,
        "mechanism_graph_id": f"MG-{genome_id}",
        "prediction_gene_ids": (
            [PREDICTION_ID] if prediction_ids is None else prediction_ids
        ),
        "falsifier_gene_ids": (
            [FALSIFIER_ID] if falsifier_ids is None else falsifier_ids
        ),
        "alternative_hypothesis_ids": [],
        "measurement_contract_ids": [f"MC-{genome_id}"],
        "evidence_pack_id": f"EP-{genome_id}",
        "validation_plan_id": f"VP-{genome_id}",
        "lineage_id": f"LIN-{genome_id}",
        "complexity_budget": 4,
        "uncertainty_notes": [],
        "provenance_hash": A_HASH,
        "created_at": DECIDED_AT,
    }
    document.update(overrides)
    return document


def submission(**overrides: Any) -> dict[str, Any]:
    """The I05 intake envelope: a declared kind and the genome document."""
    envelope: dict[str, Any] = {
        "genome_kind": GENOME_KIND,
        "genome": genome(),
    }
    envelope.update(overrides)
    return envelope


def gate_arguments(**overrides: Any) -> dict[str, Any]:
    """One fully-bound intake decision, replayable from its own arguments."""
    arguments: dict[str, Any] = {
        "submission": submission(),
        "scope_vector": scope_vector(),
        "falsifier_genes": [falsifier_gene()],
        "prediction_genes": [prediction_gene()],
        "decided_at": DECIDED_AT,
        "receipt_id": "GIR-I06-1",
    }
    arguments.update(overrides)
    return arguments


def request(**overrides: Any) -> dict[str, Any]:
    """One intake-batch request envelope carrying a submission and its artifacts."""
    envelope: dict[str, Any] = {
        "submission": submission(),
        "scope_vector": scope_vector(),
        "falsifier_genes": [falsifier_gene()],
        "prediction_genes": [prediction_gene()],
    }
    envelope.update(overrides)
    return envelope


def coherent_request(
    genome_id: str, *, scope_id: str | None = None, **overrides: Any
) -> dict[str, Any]:
    """A self-consistent request for a distinct genome id.

    The falsifier and prediction genes are re-attributed to ``genome_id`` and
    given ids namespaced to it, so a batch of several genomes binds cleanly
    rather than tripping the cross-attribution refusals.
    """
    scope = scope_id or f"SV-{genome_id}"
    prediction_id = f"PG-{genome_id}"
    falsifier_id = f"FG-{genome_id}"
    envelope: dict[str, Any] = {
        "submission": submission(
            genome=genome(
                genome_id,
                scope_id=scope,
                prediction_ids=[prediction_id],
                falsifier_ids=[falsifier_id],
            )
        ),
        "scope_vector": scope_vector(),
        "falsifier_genes": [
            falsifier_gene(
                falsifier_id,
                genome_id=genome_id,
                linked_prediction_ids=[prediction_id],
            )
        ],
        "prediction_genes": [
            prediction_gene(prediction_id, genome_id=genome_id, scope_id=scope)
        ],
    }
    envelope.update(overrides)
    return envelope
