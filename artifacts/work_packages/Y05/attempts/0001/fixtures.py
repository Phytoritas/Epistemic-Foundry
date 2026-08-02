"""Shared fixtures for the Y05 scaling, triage, budget and load suite.

The canonical tokens are restated here as test constants and pinned against the
schemas by ``test_schema_and_type``: if a ladder reorders, that suite fails at
the assertion rather than letting a test silently exercise the wrong token.  The
builders return the smallest valid inputs each surface accepts, so a negative
test can perturb exactly one field and attribute the refusal to it.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.budgets.envelope import build_budget_envelope
from epistemic_foundry.contracts import repo_root as _repo_root
from epistemic_foundry.epistemic_species_archive.archive import build_archive_entry
from epistemic_foundry.operations.v4_y05 import (
    build_scaled_quality_diversity_map,
    triage_at_scale,
)
from epistemic_foundry.scheduler.v4_n05 import LANES, LaneEvent

# --- surrogate triage decision ladder (surrogate-triage-report.triage_decision) -
EVALUATE_NOW = "EVALUATE_NOW"
DEFER = "DEFER"
SAMPLE_FOR_CALIBRATION = "SAMPLE_FOR_CALIBRATION"
REJECT_ONLY_ON_HARD_GATE = "REJECT_ONLY_ON_HARD_GATE"

# --- budget enforcement ladder (budget-envelope.enforcement) -------------------
HARD_METERED = "HARD_METERED"
HARD_PREALLOCATED = "HARD_PREALLOCATED"
SOFT_ESTIMATE = "SOFT_ESTIMATE"
UNMETERED = "UNMETERED"

# --- budget breach policy ladder (budget-envelope.breach_policy) ---------------
CANCEL = "CANCEL"
PAUSE_AND_ESCALATE = "PAUSE_AND_ESCALATE"
MARK_PARTIAL = "MARK_PARTIAL"
WARN = "WARN"

# --- archive entry classes (epistemic-archive-entry.entry_class) ---------------
ELITE = "elite"
DIVERSE = "diverse"
NULL = "null"
COUNTEREXAMPLE = "counterexample"
FAILED_REPLICATION = "failed_replication"
MINORITY_LINEAGE = "minority_lineage"
UNSAFE = "unsafe"
SUPERSEDED = "superseded"

# --- Q05 admissibility gate verdict tokens (not schema enums) ------------------
GATE_ADMIT = "ADMIT"
GATE_REFUSE = "REFUSE"

STAMP = "2026-08-01T00:00:00+00:00"
EMPTY_LIMITS = {
    "tokens": None,
    "calls": None,
    "wall_seconds": None,
    "concurrency": None,
    "storage_bytes": None,
    "network_bytes": None,
}


def repo_root() -> Any:
    return _repo_root()


def qd_map(**overrides: Any) -> dict[str, Any]:
    """A three-niche map with two occupied and one stagnant niche."""
    kwargs: dict[str, Any] = {
        "evolution_run_id": "ER-0001",
        "generation": 5,
        "niche_ids": ["niche-a", "niche-b", "niche-c"],
        "occupied_niche_ids": ["niche-a", "niche-b"],
        "lineage_entropy": 1.75,
        "stagnant_niche_ids": ["niche-c"],
    }
    kwargs.update(overrides)
    return build_scaled_quality_diversity_map(**kwargs)


def archive_entry(
    identity: str,
    entry_class: str,
    niche_id: str,
    archived_at: str,
) -> dict[str, Any]:
    return build_archive_entry(
        candidate_id=identity,
        entry_class=entry_class,
        niche_id=niche_id,
        fitness_vector_id=f"FV-{identity}",
        lineage_id=f"LIN-{identity}",
        retention_reason="kept for the test population",
        replacement_policy="oldest_first",
        artifact_payload={"candidate": identity},
        archive_entry_id=f"AE-{identity}",
        archived_at=archived_at,
    )


def archive_population() -> list[dict[str, Any]]:
    """Two evictable elites in niche-a, one protected null in niche-b."""
    return [
        archive_entry("c1", ELITE, "niche-a", "2026-01-01T00:00:00+00:00"),
        archive_entry("c2", DIVERSE, "niche-a", "2026-01-02T00:00:00+00:00"),
        archive_entry("c3", NULL, "niche-b", "2026-01-03T00:00:00+00:00"),
    ]


def triage_report(**overrides: Any) -> dict[str, Any]:
    """A valid EVALUATE_NOW triage report; override any keyword to perturb it."""
    kwargs: dict[str, Any] = {
        "candidate_id": "c1",
        "surrogate_model_id": "surrogate-v1",
        "predicted_utility": 0.8,
        "predictive_uncertainty": 0.1,
        "ood_score": 0.1,
        "calibration_window_id": "CAL-0001",
    }
    kwargs.update(overrides)
    return triage_at_scale(**kwargs)


def gate_receipt(
    decision: str = GATE_ADMIT, candidate_id: str = "c1"
) -> dict[str, Any]:
    """A minimal stand-in for a sealed Q05 admissibility receipt.

    ``bind_triage_to_gate`` reads only the decision and candidate identity, so a
    full gate run is not needed to prove that the promotion authority rests on the
    gate's verdict rather than on the surrogate.
    """
    return {"decision": decision, "candidate_id": candidate_id}


def bounded_budget(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "enforcement": HARD_METERED,
        "hard_limits": {"tokens": 100_000},
        "soft_cost_currency": "USD",
        "soft_cost_amount": 12.5,
        "metering_authority": "kernel-meter",
        "breach_policy": MARK_PARTIAL,
        "budget_id": "BE-Y05-01",
        "created_at": STAMP,
    }
    kwargs.update(overrides)
    return build_budget_envelope(**kwargs)


def soft_budget(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "enforcement": SOFT_ESTIMATE,
        "hard_limits": dict(EMPTY_LIMITS),
        "soft_cost_currency": "USD",
        "soft_cost_amount": 12.5,
        "metering_authority": "kernel-meter",
        "breach_policy": WARN,
        "budget_id": "BE-Y05-02",
        "created_at": STAMP,
    }
    kwargs.update(overrides)
    return build_budget_envelope(**kwargs)


def schedule_events(candidate_id: str = "C-1") -> list[LaneEvent]:
    events: list[LaneEvent] = []
    for lane in LANES:
        events.append(LaneEvent(lane, "enqueue", candidate_id))
        events.append(LaneEvent(lane, "start", candidate_id))
        events.append(LaneEvent(lane, "conclude", candidate_id))
    return events


def lane_limits(concurrency: int = 2) -> dict[str, dict[str, Any]]:
    return {lane: {"concurrency": concurrency} for lane in LANES}
