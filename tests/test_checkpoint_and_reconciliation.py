"""Resume points bind atomically; fan-out accounts for every identity."""

from __future__ import annotations

import inspect

import pytest

from epistemic_foundry.evolution_chamber.checkpoint import (
    CHECKPOINT_COMPONENTS,
    CheckpointIncomplete,
    build_evolution_checkpoint,
    build_stop_certificate,
    missing_components,
    search_exhausted_within_scope,
    stop_was_orderly,
)
from epistemic_foundry.evolution_chamber.reconciliation import (
    ReconciliationFailed,
    reconcile_candidates,
    require_reconciled,
)

HASH = "sha256:" + "a" * 64


def _checkpoint(**overrides) -> dict:
    kwargs = dict(
        evolution_run_id="ERS-1",
        generation=4,
        population_artifact_ids=["HG-1", "HG-2"],
        archive_snapshot_id="AE-snap-1",
        island_state_ids=["IS-1"],
        operator_bandit_state_id="OBS-1",
        evaluator_bundle_hash=HASH,
        budget_state_id="BE-1",
        sequential_testing_ledger_id="STL-1",
    )
    kwargs.update(overrides)
    return build_evolution_checkpoint(**kwargs)


# -- EF4-I60 atomic resume point ----------------------------------------


def test_i60_complete_checkpoint_binds_every_component() -> None:
    checkpoint = _checkpoint()
    for component in CHECKPOINT_COMPONENTS:
        assert checkpoint[component]
    assert checkpoint["checkpoint_hash"].startswith("sha256:")


@pytest.mark.parametrize("component", CHECKPOINT_COMPONENTS)
def test_i60_partial_capture_is_refused(component: str) -> None:
    """Resuming from a partial capture yields a configuration that never existed."""
    blank: object = [] if component.endswith("_ids") else ""
    with pytest.raises(CheckpointIncomplete) as excinfo:
        _checkpoint(**{component: blank})
    assert component in str(excinfo.value)
    assert "never existed" in str(excinfo.value)


def test_i60_missing_components_are_reportable() -> None:
    """Gaps are reported in component order, not alphabetically.

    Declaration order matches the pipeline, so a reader sees which stage of the
    capture broke first rather than an alphabetized list.
    """
    gaps = missing_components({"archive_snapshot_id": "AE-1"})
    assert gaps == [name for name in CHECKPOINT_COMPONENTS if name != "archive_snapshot_id"]
    assert gaps[0] == "population_artifact_ids"


def test_i60_evaluator_hash_is_bound_into_the_resume_point() -> None:
    """Resuming under a different evaluator would silently change the judge."""
    assert _checkpoint()["evaluator_bundle_hash"] == HASH


# -- EF4-I61 stop certificate preserves partial work ---------------------


def _certificate(**overrides) -> dict:
    kwargs = dict(
        evolution_run_id="ERS-1",
        stop_reason="budget_exhausted",
        conditions_observed=["token budget reached 100% of HARD_METERED limit"],
        unresolved_candidates=["HG-7"],
        unassessed_niches=["NICHE-4"],
        checkpoint_id="ECP-1",
    )
    kwargs.update(overrides)
    return build_stop_certificate(**kwargs)


def test_i61_partial_results_are_always_visible() -> None:
    """Hiding where the search got to discards its most reusable output."""
    params = inspect.signature(build_stop_certificate).parameters
    assert "partial_results_visible" not in params
    assert _certificate()["partial_results_visible"] is True


def test_i61_unresolved_work_is_carried_on_the_certificate() -> None:
    certificate = _certificate()
    assert certificate["unresolved_candidates"] == ["HG-7"]
    assert certificate["unassessed_niches"] == ["NICHE-4"]


def test_i61_unexplained_stop_is_refused() -> None:
    """An unexplained stop cannot be distinguished from a crash."""
    with pytest.raises(ValueError) as excinfo:
        _certificate(conditions_observed=[])
    assert "distinguished from a crash" in str(excinfo.value)


@pytest.mark.parametrize(
    "reason", ["budget_exhausted", "max_generations", "dry_rounds", "human_stop"]
)
def test_i61_orderly_stops_are_classified_as_such(reason: str) -> None:
    assert stop_was_orderly(_certificate(stop_reason=reason)) is True


@pytest.mark.parametrize("reason", ["safety_stop", "blocked", "failed"])
def test_i61_adverse_stops_are_not_orderly(reason: str) -> None:
    assert stop_was_orderly(_certificate(stop_reason=reason)) is False


def test_i61_budget_exhaustion_does_not_prove_scope_coverage() -> None:
    """Running out of budget is a different statement from covering the scope."""
    assert search_exhausted_within_scope(_certificate()) is False


def test_i61_coverage_saturation_with_no_gaps_proves_scope_coverage() -> None:
    certificate = _certificate(stop_reason="coverage_saturation", unassessed_niches=[])
    assert search_exhausted_within_scope(certificate) is True


def test_i61_adverse_stop_never_proves_coverage() -> None:
    certificate = _certificate(stop_reason="failed", unassessed_niches=[])
    assert search_exhausted_within_scope(certificate) is False


# -- EF4-I59 fan-out reconciliation -------------------------------------


def test_i59_clean_fan_out_reconciles() -> None:
    report = reconcile_candidates(
        proposed=["C1", "C2"],
        generated=["C1", "C2"],
        evaluated=["C1", "C2"],
        persisted=["C1", "C2"],
    )
    assert report["reconciled"] is True
    require_reconciled(report)


def test_i59_terminal_dispositions_account_for_a_candidate() -> None:
    report = reconcile_candidates(
        proposed=["C1", "C2"],
        generated=["C1"],
        evaluated=["C1"],
        persisted=["C1"],
        failed=["C2"],
    )
    assert report["reconciled"] is True


def test_i59_vanished_candidate_is_reported_as_missing() -> None:
    """A silently dropped candidate is indistinguishable from an empty result."""
    report = reconcile_candidates(
        proposed=["C1", "C2"], generated=["C1"], evaluated=["C1"], persisted=["C1"]
    )
    assert report["missing"] == ["C2"]
    with pytest.raises(ReconciliationFailed) as excinfo:
        require_reconciled(report)
    assert "vanished" in str(excinfo.value)


def test_i59_storage_failure_is_distinct_from_a_generator_failure() -> None:
    """Each gap names a different failure class and must stay separate."""
    storage = reconcile_candidates(
        proposed=["C1"], generated=["C1"], evaluated=["C1"], persisted=[]
    )
    generator = reconcile_candidates(
        proposed=["C1"], generated=[], evaluated=[], persisted=[]
    )
    assert "evaluated_not_persisted" in storage["gaps"]
    assert "proposed_not_generated" in generator["gaps"]
    assert "evaluated_not_persisted" not in generator["gaps"]


def test_i59_scheduling_failure_is_named_separately() -> None:
    report = reconcile_candidates(
        proposed=["C1"], generated=["C1"], evaluated=[], persisted=[]
    )
    assert "generated_not_evaluated" in report["gaps"]


def test_i59_candidate_appearing_without_provenance_is_refused() -> None:
    """A result with no proposal upstream has no provenance."""
    report = reconcile_candidates(
        proposed=["C1"], generated=["C1", "GHOST"], evaluated=["C1"], persisted=["C1"]
    )
    assert report["unknown_identities"]["generated"] == ["GHOST"]
    with pytest.raises(ReconciliationFailed) as excinfo:
        require_reconciled(report)
    assert "no provenance" in str(excinfo.value)


def test_i59_report_uses_identity_sets_not_only_counts() -> None:
    report = reconcile_candidates(
        proposed=["C1", "C2"], generated=["C1"], evaluated=["C1"], persisted=["C1"]
    )
    assert report["counts"]["proposed"] == 2
    assert report["missing"] == ["C2"]
