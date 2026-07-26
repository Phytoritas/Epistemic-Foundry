"""Negative knowledge survives capacity pressure."""

from __future__ import annotations

import pytest

from epistemic_foundry.epistemic_species_archive import (
    PROTECTED_ENTRY_CLASSES,
    ArchivePolicyViolation,
    build_archive_entry,
    build_quality_diversity_map,
    evictable_entries,
)
from epistemic_foundry.epistemic_species_archive.archive import protected_count


def _entry(entry_class: str, *, archived_at: str = "2026-07-27T00:00:00+00:00", candidate: str | None = None) -> dict:
    return build_archive_entry(
        candidate_id=candidate or f"CAND-{entry_class}",
        entry_class=entry_class,
        niche_id="NICHE-1",
        fitness_vector_id="FV-1",
        lineage_id="LIN-1",
        retention_reason=f"retained as {entry_class}",
        replacement_policy="replace only within the same class",
        artifact_payload={"class": entry_class},
        archived_at=archived_at,
    )


# -- entry contracts ----------------------------------------------------


def test_entry_matches_the_canonical_schema() -> None:
    entry = _entry("null")
    assert entry["entry_class"] == "null"
    assert entry["artifact_hash"].startswith("sha256:")


def test_entry_without_a_retention_reason_is_refused() -> None:
    with pytest.raises(ArchivePolicyViolation):
        build_archive_entry(
            candidate_id="CAND-1",
            entry_class="null",
            niche_id="NICHE-1",
            fitness_vector_id="FV-1",
            lineage_id="LIN-1",
            retention_reason="   ",
            replacement_policy="none",
            artifact_payload={},
        )


def test_protected_classes_cover_the_constitutional_list() -> None:
    for entry_class in ("null", "counterexample", "failed_replication", "minority_lineage", "unsafe"):
        assert entry_class in PROTECTED_ENTRY_CLASSES


# -- eviction -----------------------------------------------------------


def test_nothing_is_evicted_under_capacity() -> None:
    entries = [_entry("elite"), _entry("diverse")]
    assert evictable_entries(entries, capacity=5) == []


def test_elites_are_evictable_when_over_capacity() -> None:
    entries = [
        _entry("elite", archived_at="2026-07-01T00:00:00+00:00"),
        _entry("diverse", archived_at="2026-07-02T00:00:00+00:00"),
        _entry("superseded", archived_at="2026-07-03T00:00:00+00:00"),
    ]
    evicted = evictable_entries(entries, capacity=2)
    assert len(evicted) == 1
    assert evicted[0]["entry_class"] == "elite"  # oldest first


def test_null_results_are_never_evicted() -> None:
    """An archive that drops nulls re-opens dead ends already paid for."""
    entries = [_entry("null"), _entry("null"), _entry("null")]
    assert evictable_entries(entries, capacity=1) == []


def test_failed_replications_are_never_evicted() -> None:
    entries = [_entry("failed_replication") for _ in range(4)]
    assert evictable_entries(entries, capacity=1) == []


def test_minority_lineages_survive_capacity_pressure() -> None:
    entries = [_entry("minority_lineage"), _entry("elite")]
    evicted = evictable_entries(entries, capacity=1)
    assert [item["entry_class"] for item in evicted] == ["elite"]


def test_counterexamples_and_unsafe_entries_survive() -> None:
    entries = [_entry("counterexample"), _entry("unsafe")]
    assert evictable_entries(entries, capacity=0) == []


def test_overflow_of_protected_entries_evicts_nothing() -> None:
    """The caller must raise capacity rather than delete negative knowledge."""
    entries = [_entry("null") for _ in range(5)]
    assert evictable_entries(entries, capacity=2) == []
    assert protected_count(entries) == 5


def test_negative_capacity_is_refused() -> None:
    with pytest.raises(ArchivePolicyViolation):
        evictable_entries([_entry("elite")], capacity=-1)


# -- coverage map -------------------------------------------------------


def test_coverage_ratio_is_derived_from_the_niche_sets() -> None:
    record = build_quality_diversity_map(
        evolution_run_id="ERS-1",
        generation=2,
        niche_ids=["N1", "N2", "N3", "N4"],
        occupied_niche_ids=["N1", "N2"],
        lineage_entropy=1.5,
    )
    assert record["total_niches"] == 4
    assert record["occupied_niches"] == 2
    assert record["coverage_ratio"] == 0.5


def test_coverage_ratio_is_not_a_parameter() -> None:
    """A reported figure must not drift from the occupied niches."""
    import inspect

    params = inspect.signature(build_quality_diversity_map).parameters
    assert "coverage_ratio" not in params
    assert "occupied_niches" not in params


def test_duplicate_occupancy_counts_once() -> None:
    record = build_quality_diversity_map(
        evolution_run_id="ERS-1",
        generation=2,
        niche_ids=["N1", "N2"],
        occupied_niche_ids=["N1", "N1"],
        lineage_entropy=0.0,
    )
    assert record["occupied_niches"] == 1


def test_unknown_occupied_niche_is_refused() -> None:
    with pytest.raises(ArchivePolicyViolation):
        build_quality_diversity_map(
            evolution_run_id="ERS-1",
            generation=1,
            niche_ids=["N1"],
            occupied_niche_ids=["N9"],
            lineage_entropy=0.0,
        )


def test_empty_niche_map_is_refused() -> None:
    with pytest.raises(ArchivePolicyViolation):
        build_quality_diversity_map(
            evolution_run_id="ERS-1",
            generation=1,
            niche_ids=[],
            occupied_niche_ids=[],
            lineage_entropy=0.0,
        )
