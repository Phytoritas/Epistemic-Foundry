"""Fixtures for the R06 crossover safety gate suites.

Every genome, mechanism graph, scope vector and compatibility report here is a
document its canonical schema accepts, because the gate operates on real sealed
artifacts: a fixture the schema would refuse would test the fixture rather than
the gate. Enum-valued fields and the scalar scope fields are read out of the
schema that declares them, the crossover report is built by the Evolution
Chamber itself, and every self-referential hash is sealed with the same
canonicalization the gate re-derives, so a canonical change breaks these
fixtures instead of letting them drift.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution_chamber.crossover import build_crossover_report
from epistemic_foundry.intake.v4_i05 import GENOME_KIND
from epistemic_foundry.reasoning.v4_r06 import gate as engine

_registry = default_registry()

MECHANISM_KIND = engine.MECHANISM_KIND
SCOPE_KIND = engine.SCOPE_KIND
MEASUREMENT_KIND = engine.MEASUREMENT_REPORT_KIND
CROSSOVER_KIND = engine.CROSSOVER_REPORT_KIND

CREATED_AT = "2026-08-02T00:00:00.000Z"
A_HASH = "sha256:" + "a" * 64


def _first_enum(schema_name: str, field: str) -> str:
    """The first value the named schema declares for that field."""
    return str(_registry.document(schema_name)["properties"][field]["enum"][0])


#: The first declared genome status: a splice combines candidates that have not
#: been evaluated, and the value comes from the schema that declares it.
DRAFT_STATUS = _first_enum(GENOME_KIND, "status")
#: The compatible token every crossover axis shares, read from the schema.
COMPATIBLE = _first_enum(CROSSOVER_KIND, "scope_compatibility")
#: The single identification value a compatible splice requires of both parents.
IDENTIFIED = engine.IDENTIFIED
NOT_ASSESSED = engine.NOT_ASSESSED


def _seal_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Stamp a mechanism graph with the sealed hash the gate re-derives."""
    graph["graph_hash"] = hash_excluding(graph, "graph_hash")
    return graph


def mechanism_graph(
    graph_id: str = "MG-1",
    *,
    identification_status: str = IDENTIFIED,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid, sealed MechanismGraph carrying one identification status.

    The status is what R04 already derived and pinned; the gate reads it rather
    than re-deriving it, so the fixture stands in for an R04-sealed graph.
    """
    graph: dict[str, Any] = {
        "mechanism_graph_id": graph_id,
        "nodes": [
            {"node_id": "N-CAUSE", "concept_id": "C-EC", "role": "cause"},
            {"node_id": "N-OUT", "concept_id": "C-GS", "role": "outcome"},
        ],
        "edges": [
            {
                "edge_id": "E-1",
                "source": "N-CAUSE",
                "target": "N-OUT",
                "relation": "causes",
                "sign": "negative",
                "lag": "PT1H",
            }
        ],
        "assumptions": [],
        "identification_status": identification_status,
        "graph_hash": A_HASH,
    }
    graph.update(overrides)
    return _seal_graph(graph)


def scope_vector(**overrides: Any) -> dict[str, Any]:
    """A schema-valid ScopeVector that declares at least one boundary."""
    document: dict[str, Any] = {
        "domain": "controlled-environment-agriculture",
        "population": "greenhouse tomato under drip fertigation",
        "entity_type": "plant",
        "entity_subtype": None,
        "unit_of_analysis": "individual plant",
        "setting": "glasshouse",
        "geography": None,
        "jurisdiction": None,
        "language": None,
        "lifecycle_stage": "vegetative",
        "spatial_scale": None,
        "temporal_scale": "diurnal",
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


def empty_scope_vector() -> dict[str, Any]:
    """A ScopeVector that declares no boundary of any kind."""
    return scope_vector(
        domain=None,
        population=None,
        entity_type=None,
        unit_of_analysis=None,
        setting=None,
        lifecycle_stage=None,
        temporal_scale=None,
    )


def genome(
    genome_id: str = "HG-1",
    *,
    mechanism: str = "MG-1",
    scope: str = "SV-1",
    measurement: str = "MC-HG-1",
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid hypothesis genome referencing one of each artifact."""
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
        "prediction_gene_ids": [f"PG-{genome_id}-1"],
        "falsifier_gene_ids": [f"FG-{genome_id}"],
        "alternative_hypothesis_ids": [],
        "measurement_contract_ids": [measurement],
        "evidence_pack_id": f"EP-{genome_id}",
        "validation_plan_id": f"VP-{genome_id}",
        "lineage_id": f"LIN-{genome_id}",
        "complexity_budget": 4,
        "uncertainty_notes": [],
        "provenance_hash": A_HASH,
        "created_at": CREATED_AT,
    }
    document.update(overrides)
    return document


def challenge_genome(challenge_id: str = "CG-1", **overrides: Any) -> dict[str, Any]:
    """A schema-valid challenge genome, used as a wrong-kind parent.

    It is a real genome the registry accepts, so the gate refuses it for being
    the wrong kind rather than for being malformed.
    """
    document: dict[str, Any] = {
        "challenge_genome_id": challenge_id,
        "target_genome_id": "HG-1",
        "challenge_class": _first_enum("challenge-genome", "challenge_class"),
        "construction": "withhold irrigation on the matched control block",
        "success_criterion": "the predicted direction reverses under the control",
        "required_capabilities": [],
        "safety_class": _first_enum("challenge-genome", "safety_class"),
        "lineage_id": "LIN-CG-1",
    }
    document.update(overrides)
    return document


def measurement(measurement_id: str = "MC-HG-1", **overrides: Any) -> dict[str, Any]:
    """One measurement descriptor for a compatibility report side."""
    document: dict[str, Any] = {
        "measurement_id": measurement_id,
        "construct_id": "CONS-stomatal-conductance",
        "method_id": "METH-porometer",
        "protocol_version": "1.0",
        "unit": "mmol m-2 s-1",
        "timing": "midday",
        "calibration_ref": "CAL-2026-01",
    }
    document.update(overrides)
    return document


def measurement_report(
    *,
    left_id: str = "MC-HG-1",
    right_id: str = "MC-HG-2",
    compatibility_status: str = "DIRECTLY_COMPARABLE",
    construct_equivalence: str = "SAME",
    left: dict[str, Any] | None = None,
    right: dict[str, Any] | None = None,
    required_transformations: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid, sealed MeasurementCompatibilityReport over two measures."""
    document: dict[str, Any] = {
        "report_id": "MCR-R06-1",
        "run_id": "RUN-R06-1",
        "left": left if left is not None else measurement(left_id),
        "right": right if right is not None else measurement(right_id),
        "compatibility_status": compatibility_status,
        "construct_equivalence": construct_equivalence,
        "required_transformations": required_transformations or [],
        "method_threats": [],
        "promotion_ceiling": "NO_RESTRICTION",
        "domain_pack_id": None,
        "domain_pack_version": None,
        "reviewer_ref": "REV-R06",
        "reviewed_at": CREATED_AT,
    }
    document.update(overrides)
    document["report_hash"] = hash_excluding(document, "report_hash")
    return document


def crossover_report(
    candidate_ids: tuple[str, ...] = ("HG-1", "HG-2"),
    *,
    scope_compatibility: str = COMPATIBLE,
    measurement_compatibility: str = COMPATIBLE,
    causal_compatibility: str = COMPATIBLE,
    unit_compatibility: str = COMPATIBLE,
    conflicts: list[str] | None = None,
    required_repairs: list[str] | None = None,
) -> dict[str, Any]:
    """A Chamber-built report whose decision is derived from its four axes."""
    return build_crossover_report(
        candidate_ids=list(candidate_ids),
        scope_compatibility=scope_compatibility,
        measurement_compatibility=measurement_compatibility,
        causal_compatibility=causal_compatibility,
        unit_compatibility=unit_compatibility,
        conflicts=conflicts or [],
        required_repairs=required_repairs or [],
        report_id="CCR-R06-1",
    )


def gate_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound, compatible crossover the gate should allow.

    Two distinct parents share one scope, carry identified mechanisms, and are
    compared by a directly-comparable measurement report over matching units.
    """
    arguments: dict[str, Any] = {
        "parents": [
            genome("HG-1", mechanism="MG-1", scope="SV-1", measurement="MC-HG-1"),
            genome("HG-2", mechanism="MG-2", scope="SV-1", measurement="MC-HG-2"),
        ],
        "mechanism_graphs": [
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2"),
        ],
        "scope_vectors": {"SV-1": scope_vector()},
        "measurement_report": measurement_report(),
        "crossover_report": crossover_report(),
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
