"""Archive entries, eviction policy, and quality-diversity coverage.

Contract sources: `schemas/epistemic-archive-entry.schema.json`,
`schemas/quality-diversity-map.schema.json`.

The eviction rule is the substance of this module. A conventional archive keeps
the fittest and drops the rest, which would quietly delete nulls,
counterexamples, failed replications, and minority lineages — the negative
knowledge the v4 constitution requires retaining. `evictable_entries` therefore
never returns a protected class, even when the archive is over capacity.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, sha256_of_payload
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Entry classes that carry negative or minority knowledge. These are never
#: evicted for capacity: losing them re-opens dead ends already paid for.
PROTECTED_ENTRY_CLASSES: frozenset[str] = frozenset(
    {
        "null",
        "counterexample",
        "failed_replication",
        "minority_lineage",
        "unsafe",
    }
)

#: Classes that may be evicted once capacity is exceeded.
EVICTABLE_ENTRY_CLASSES: frozenset[str] = frozenset({"elite", "diverse", "superseded"})


class ArchivePolicyViolation(ValueError):
    """An archive operation would discard knowledge the policy retains."""


def build_archive_entry(
    *,
    candidate_id: str,
    entry_class: str,
    niche_id: str,
    fitness_vector_id: str,
    lineage_id: str,
    retention_reason: str,
    replacement_policy: str,
    artifact_payload: Any,
    archive_entry_id: str | None = None,
    archived_at: str | None = None,
) -> dict[str, Any]:
    """Archive one candidate with an explicit retention reason.

    `retention_reason` is required and non-empty: an entry nobody can justify is
    the first thing a future cleanup deletes, protected class or not.
    """
    if not retention_reason.strip():
        raise ArchivePolicyViolation(
            "an archive entry must state a retention_reason; an unjustified entry will be "
            "deleted by the next cleanup"
        )
    entry: dict[str, Any] = {
        "archive_entry_id": archive_entry_id or new_id("AE"),
        "candidate_id": candidate_id,
        "entry_class": entry_class,
        "niche_id": niche_id,
        "fitness_vector_id": fitness_vector_id,
        "lineage_id": lineage_id,
        "retention_reason": retention_reason,
        "replacement_policy": replacement_policy,
        "artifact_hash": sha256_of_payload(artifact_payload),
        "archived_at": archived_at or utc_now_iso(),
    }
    validate_artifact("epistemic-archive-entry", entry)
    return entry


def evictable_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    capacity: int,
) -> list[Mapping[str, Any]]:
    """Entries that may be dropped to reach `capacity`.

    Protected classes are excluded unconditionally. When the protected set alone
    exceeds capacity, nothing is evicted and the caller must raise capacity or
    rebalance niches: silently dropping negative knowledge to satisfy a number
    is the failure this function exists to prevent.
    """
    if capacity < 0:
        raise ArchivePolicyViolation("capacity cannot be negative")
    overflow = len(entries) - capacity
    if overflow <= 0:
        return []
    candidates = [
        entry for entry in entries if str(entry.get("entry_class")) in EVICTABLE_ENTRY_CLASSES
    ]
    # Oldest-first among evictable classes keeps recent exploration available.
    candidates.sort(key=lambda entry: str(entry.get("archived_at", "")))
    return candidates[:overflow]


def protected_count(entries: Sequence[Mapping[str, Any]]) -> int:
    """How many entries the policy refuses to evict."""
    return sum(1 for entry in entries if str(entry.get("entry_class")) in PROTECTED_ENTRY_CLASSES)


def build_quality_diversity_map(
    *,
    evolution_run_id: str,
    generation: int,
    niche_ids: Sequence[str],
    occupied_niche_ids: Sequence[str],
    lineage_entropy: float,
    stagnant_niche_ids: Sequence[str] = (),
    map_id: str | None = None,
) -> dict[str, Any]:
    """Summarize niche coverage for one generation.

    `coverage_ratio` is derived from the niche sets rather than supplied, so a
    reported coverage figure cannot drift from the niches that are actually
    occupied.
    """
    total = len(niche_ids)
    if total == 0:
        raise ArchivePolicyViolation("a quality-diversity map must define at least one niche")
    unknown = sorted(set(occupied_niche_ids) - set(niche_ids))
    if unknown:
        raise ArchivePolicyViolation(f"occupied niches not present in the map: {unknown}")
    occupied = len(set(occupied_niche_ids))

    record: dict[str, Any] = {
        "map_id": map_id or new_id("QDM"),
        "evolution_run_id": evolution_run_id,
        "generation": int(generation),
        "niche_ids": list(niche_ids),
        "occupied_niches": occupied,
        "total_niches": total,
        "coverage_ratio": round(occupied / total, 6),
        "lineage_entropy": float(lineage_entropy),
        "stagnant_niche_ids": list(stagnant_niche_ids),
    }
    record["map_hash"] = hash_excluding(record, "map_hash")
    validate_artifact("quality-diversity-map", record)
    return record
