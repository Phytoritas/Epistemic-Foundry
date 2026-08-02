"""Fixtures for the R05 scientific operator suites.

Every genome, lineage, argument graph and compatibility report here is a
document the canonical schema accepts, because the registry operates on real
documents: a fixture the schema would refuse would test the fixture rather than
the operator.  Enum-valued fields are read out of the schema that declares them
and the argument graph and the compatibility report are built by the Aporia
Engine and the Evolution Chamber themselves, so a canonical change breaks these
fixtures instead of letting them drift.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.aporia_engine import build_argument_graph
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evolution_chamber.crossover import build_crossover_report
from epistemic_foundry.intake.v4_i05 import GENOME_KIND
from epistemic_foundry.reasoning.v4_r05 import operators as engine

_registry = default_registry()
CROSSOVER_KIND = "crossover-compatibility-report"


def _first_enum(schema_name: str, field: str) -> str:
    """The first value the named schema declares for that field."""
    return str(_registry.document(schema_name)["properties"][field]["enum"][0])


#: The first declared genome status: an operator mutates candidates that have
#: not been evaluated, and the value comes from the schema that declares it.
DRAFT_STATUS = _first_enum(GENOME_KIND, "status")
#: The first declared compatibility value on every axis, which is the one the
#: Chamber turns into an unconditional allow.
COMPATIBLE = _first_enum(CROSSOVER_KIND, "scope_compatibility")
CHALLENGE_CLASS = _first_enum(engine.CHALLENGE_KIND, "challenge_class")
SAFETY_CLASS = _first_enum(engine.CHALLENGE_KIND, "safety_class")
DESIGN_TYPE = _first_enum(engine.EXPERIMENT_KIND, "design_type")
RISK_CLASS = _first_enum(engine.EXPERIMENT_KIND, "risk_class")

CREATED_AT = "2026-08-02T00:00:00.000Z"
CHILD_AT = "2026-08-02T02:00:00.000Z"
ISLAND = "IS-R05-1"
LINE = "LIN-R05-1"
OTHER_LINE = "LIN-R05-2"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64
OBJECTION = "OBJ-R05-1"


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


def challenge_genome(
    challenge_id: str = "CG-1", *, lineage_id: str = LINE, **overrides: Any
) -> dict[str, Any]:
    """A schema-valid challenge genome aimed at one hypothesis."""
    document: dict[str, Any] = {
        "challenge_genome_id": challenge_id,
        "target_genome_id": "HG-1",
        "challenge_class": CHALLENGE_CLASS,
        "construction": "withhold irrigation on the matched control block",
        "success_criterion": "the predicted direction reverses under the control",
        "required_capabilities": [],
        "safety_class": SAFETY_CLASS,
        "lineage_id": lineage_id,
    }
    document.update(overrides)
    return document


def experiment_genome(experiment_id: str = "EG-1", **overrides: Any) -> dict[str, Any]:
    """A schema-valid experiment genome discriminating one hypothesis."""
    document: dict[str, Any] = {
        "experiment_genome_id": experiment_id,
        "target_hypothesis_ids": ["HG-1"],
        "design_type": DESIGN_TYPE,
        "intervention": "step the root-zone conductivity by one unit",
        "comparator": "the unstepped adjacent block",
        "outcomes": ["stomatal conductance"],
        "controls": [],
        "sample_or_compute_budget": "24 plants over one diurnal cycle",
        "expected_information_gain": 0.4,
        "risk_class": RISK_CLASS,
        "validation_plan_id": "VP-EG-1",
    }
    document.update(overrides)
    return document


def lineage(
    candidate_id: str = "HG-1",
    *,
    lineage_id: str = LINE,
    generation: int = 1,
    ancestor_hashes: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid lineage record describing one candidate."""
    record: dict[str, Any] = {
        "ancestor_hashes": [] if ancestor_hashes is None else list(ancestor_hashes),
        "candidate_id": candidate_id,
        "created_at": CREATED_AT,
        "crossover_parent_ids": [],
        "generation": generation,
        "inspiration_ids": [],
        "island_id": ISLAND,
        "lineage_id": lineage_id,
        "mutation_operator_ids": [],
        "parent_ids": [],
    }
    record.update(overrides)
    return record


def scope_vector() -> dict[str, Any]:
    """The domain-neutral scope vector every argument node has to carry."""
    return {
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


def argument_graph(
    *,
    hypothesis_id: str = "HG-1",
    objection_id: str = OBJECTION,
    resolved: bool = False,
) -> dict[str, Any]:
    """An argument graph built by the Aporia Engine, with an open objection.

    ``resolved`` produces the same graph with nothing left open, which is what
    an Aporia operator must not be able to cite.
    """
    nodes = [
        {
            "argument_node_id": "AN-CLAIM",
            "node_type": "claim",
            "statement": "conductivity lowers stomatal conductance",
            "evidence_ids": [],
            "scope": scope_vector(),
            "status": "asserted",
        },
        {
            "argument_node_id": objection_id,
            "node_type": "objection",
            "statement": "the effect may be a vapour pressure deficit artifact",
            "evidence_ids": [],
            "scope": scope_vector(),
            "status": "accepted" if resolved else "unresolved",
        },
    ]
    edges = [
        {
            "edge_id": "AE-1",
            "from_id": objection_id,
            "to_id": "AN-CLAIM",
            "edge_type": "rebuts",
            "rule_ref": None,
            "confidence": None,
        }
    ]
    return build_argument_graph(
        run_id="RUN-R05-1",
        hypothesis_id=hypothesis_id,
        nodes=nodes,
        edges=edges,
        proof_trace_artifact_id=None,
        unresolved_objection_ids=[] if resolved else [objection_id],
        argument_graph_id="AG-R05-1",
        created_at=CREATED_AT,
    )


def citation(**overrides: Any) -> dict[str, Any]:
    """The envelope an Aporia operator has to hand over."""
    envelope: dict[str, Any] = {
        "argument_graph": argument_graph(),
        "open_question_ids": [OBJECTION],
    }
    envelope.update(overrides)
    return envelope


def compatibility_report(
    candidate_ids: tuple[str, ...] = ("HG-1", "HG-2"), **overrides: Any
) -> dict[str, Any]:
    """A Chamber-built report whose decision is derived from its four axes."""
    arguments: dict[str, Any] = {
        "candidate_ids": list(candidate_ids),
        "scope_compatibility": COMPATIBLE,
        "measurement_compatibility": COMPATIBLE,
        "causal_compatibility": COMPATIBLE,
        "unit_compatibility": COMPATIBLE,
        "conflicts": [],
        "required_repairs": [],
        "report_id": "CCR-R05-1",
    }
    arguments.update(overrides)
    return build_crossover_report(**arguments)


def mutation_arguments(**overrides: Any) -> dict[str, Any]:
    """One declared mutation, fully identified so the result is replayable."""
    arguments: dict[str, Any] = {
        "operator_id": "mechanism-refinement",
        "parent": genome(),
        "parent_lineage": lineage(),
        "changes": {"mechanism_graph_id": "MG-2"},
        "created_at": CHILD_AT,
        "child_genome_id": "HG-CHILD",
    }
    arguments.update(overrides)
    return arguments


def crossover_arguments(**overrides: Any) -> dict[str, Any]:
    """One declared splice of two mechanism-sharing parents."""
    arguments: dict[str, Any] = {
        "operator_id": "mechanism-preserving-splice",
        "parents": [genome("HG-1"), genome("HG-2", lineage_id=OTHER_LINE)],
        "parent_lineages": [
            lineage("HG-1"),
            lineage("HG-2", lineage_id=OTHER_LINE, generation=3),
        ],
        "inherited_fields": ["falsifier_gene_ids"],
        "compatibility_report": compatibility_report(),
        "created_at": CHILD_AT,
        "child_genome_id": "HG-SPLICE",
    }
    arguments.update(overrides)
    return arguments
