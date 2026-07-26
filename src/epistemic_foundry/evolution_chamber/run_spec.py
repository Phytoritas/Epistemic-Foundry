"""Evolution run specification.

Contract source: `schemas/evolution-run-spec.schema.json`.

MASTER_EXECUTION_PROMPT section 5 requires every run to pin its evaluator
bundle and holdout before search starts. Pinning them in the spec, with a
`spec_hash` over the whole record, is what makes a later evaluator swap
detectable as drift rather than absorbed as a new configuration.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id


def build_evolution_run_spec(
    *,
    base_run_spec_id: str,
    objective: str,
    population_types: Sequence[str],
    seed_genome_ids: Sequence[str],
    evaluator_bundle_id: str,
    holdout_manifest_id: str,
    operator_registry_version: str,
    max_generations: int,
    max_candidates: int,
    budget_envelope_id: str,
    selection_policy: str,
    stop_policy: str,
    random_seed: int,
    evolution_run_id: str | None = None,
) -> dict[str, Any]:
    """Pin one evolution run.

    Budgets are required to be positive and finite: an unbounded run has no stop
    certificate, and "search until something passes" is how a multiplicity
    problem becomes a false discovery.
    """
    if max_generations < 1 or max_candidates < 1:
        raise ValueError(
            "max_generations and max_candidates must both be >= 1; an unbounded run "
            "cannot produce a stop certificate"
        )
    if not seed_genome_ids:
        raise ValueError("an evolution run must pin at least one seed genome")

    spec: dict[str, Any] = {
        "evolution_run_id": evolution_run_id or new_id("ERS"),
        "base_run_spec_id": base_run_spec_id,
        "objective": objective,
        "population_types": list(population_types),
        "seed_genome_ids": list(seed_genome_ids),
        "evaluator_bundle_id": evaluator_bundle_id,
        "holdout_manifest_id": holdout_manifest_id,
        "operator_registry_version": operator_registry_version,
        "max_generations": int(max_generations),
        "max_candidates": int(max_candidates),
        "budget_envelope_id": budget_envelope_id,
        "selection_policy": selection_policy,
        "stop_policy": stop_policy,
        "random_seed": int(random_seed),
    }
    spec["spec_hash"] = hash_excluding(spec, "spec_hash")
    validate_artifact("evolution-run-spec", spec)
    return spec


def evaluator_binding_changed(spec: dict[str, Any], other: dict[str, Any]) -> bool:
    """True when two specs disagree about the evaluator or holdout binding."""
    return (
        spec["evaluator_bundle_id"] != other["evaluator_bundle_id"]
        or spec["holdout_manifest_id"] != other["holdout_manifest_id"]
    )
