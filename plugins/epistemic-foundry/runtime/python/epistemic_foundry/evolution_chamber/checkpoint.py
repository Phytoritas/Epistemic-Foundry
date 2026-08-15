"""Atomic resume checkpoints and stop certificates (EF4-I61, EF4-I62).

Contract sources: `schemas/evolution-checkpoint.schema.json` and
`schemas/evolution-stop-certificate.schema.json`.

A resume point is only safe if every component was captured at the same instant.
A checkpoint holding this generation's population beside last generation's bandit
state would resume into a configuration that never existed, and the resulting run
would be neither the original nor a clean restart. So `build_evolution_checkpoint`
requires all seven components and refuses a partial capture.

A stop certificate must preserve partial work. Stopping is normal — budget runs
out, rounds go dry, a human intervenes — and discarding the unresolved candidates
and unassessed niches at that moment throws away the map of where the search had
got to.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: The seven components a resume point must bind together.
CHECKPOINT_COMPONENTS: tuple[str, ...] = (
    "population_artifact_ids",
    "archive_snapshot_id",
    "island_state_ids",
    "operator_bandit_state_id",
    "evaluator_bundle_hash",
    "budget_state_id",
    "sequential_testing_ledger_id",
)

#: Stop reasons that indicate the search ended on its own terms.
ORDERLY_STOPS: frozenset[str] = frozenset(
    {
        "budget_exhausted",
        "max_generations",
        "dry_rounds",
        "pareto_stability",
        "coverage_saturation",
        "human_stop",
    }
)

#: Stop reasons that indicate something went wrong.
ADVERSE_STOPS: frozenset[str] = frozenset({"safety_stop", "blocked", "failed"})


class CheckpointIncomplete(ValueError):
    """A checkpoint would resume into a configuration that never existed."""


def missing_components(payload: Mapping[str, Any]) -> list[str]:
    """Checkpoint components absent or empty in `payload`."""
    gaps: list[str] = []
    for name in CHECKPOINT_COMPONENTS:
        value = payload.get(name)
        if value is None or value == "" or value == []:
            gaps.append(name)
    return gaps


def build_evolution_checkpoint(
    *,
    evolution_run_id: str,
    generation: int,
    population_artifact_ids: Sequence[str],
    archive_snapshot_id: str,
    island_state_ids: Sequence[str],
    operator_bandit_state_id: str,
    evaluator_bundle_hash: str,
    budget_state_id: str,
    sequential_testing_ledger_id: str,
    checkpoint_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Bind all seven components into one resume point.

    A partial capture is refused rather than stored as a best-effort checkpoint:
    resuming from one would produce a run that is neither a continuation of the
    original nor a clean restart, and the difference would be invisible.
    """
    payload: dict[str, Any] = {
        "checkpoint_id": checkpoint_id or new_id("ECP"),
        "evolution_run_id": evolution_run_id,
        "generation": int(generation),
        "population_artifact_ids": list(population_artifact_ids),
        "archive_snapshot_id": archive_snapshot_id,
        "island_state_ids": list(island_state_ids),
        "operator_bandit_state_id": operator_bandit_state_id,
        "evaluator_bundle_hash": evaluator_bundle_hash,
        "budget_state_id": budget_state_id,
        "sequential_testing_ledger_id": sequential_testing_ledger_id,
        "created_at": created_at or utc_now_iso(),
    }
    gaps = missing_components(payload)
    if gaps:
        raise CheckpointIncomplete(
            f"checkpoint for run {evolution_run_id} generation {generation} is missing {gaps}; "
            "resuming from a partial capture produces a configuration that never existed"
        )
    payload["checkpoint_hash"] = hash_excluding(payload, "checkpoint_hash")
    validate_artifact("evolution-checkpoint", payload)
    return payload


def build_stop_certificate(
    *,
    evolution_run_id: str,
    stop_reason: str,
    conditions_observed: Sequence[str],
    unresolved_candidates: Sequence[str],
    unassessed_niches: Sequence[str],
    checkpoint_id: str,
    certificate_id: str | None = None,
) -> dict[str, Any]:
    """Certify a stop while preserving the partial work.

    `partial_results_visible` is forced true. A caller able to set it false could
    stop a run and hide where the search had got to, which discards the most
    reusable output of an incomplete search: the map of what remains unexplored.
    """
    if not conditions_observed:
        raise ValueError(
            f"stop certificate for {evolution_run_id} records no observed conditions; an "
            "unexplained stop cannot be distinguished from a crash"
        )

    certificate: dict[str, Any] = {
        "certificate_id": certificate_id or new_id("ESC"),
        "evolution_run_id": evolution_run_id,
        "stop_reason": stop_reason,
        "conditions_observed": list(conditions_observed),
        "unresolved_candidates": list(unresolved_candidates),
        "unassessed_niches": list(unassessed_niches),
        "partial_results_visible": True,
        "checkpoint_id": checkpoint_id,
    }
    certificate["certificate_hash"] = hash_excluding(certificate, "certificate_hash")
    validate_artifact("evolution-stop-certificate", certificate)
    return certificate


def stop_was_orderly(certificate: Mapping[str, Any]) -> bool:
    """Whether the search ended on its own terms rather than by failure."""
    return str(certificate.get("stop_reason")) in ORDERLY_STOPS


def search_exhausted_within_scope(certificate: Mapping[str, Any]) -> bool:
    """True only for an orderly stop with nothing left unassessed.

    This is the one condition that supports the claim that the searched scope was
    covered. An orderly stop with unassessed niches remaining means the budget ran
    out first, which is a different statement.
    """
    return stop_was_orderly(certificate) and not certificate.get("unassessed_niches")
