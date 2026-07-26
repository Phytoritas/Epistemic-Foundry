"""Epistemic Species Archive: quality-diversity with negative knowledge kept.

`AGENTS.md`: quality-diversity archives preserve negative knowledge, failed
replications, unsafe candidates, and minority lineages where policy permits.

That makes the archive the memory of what did not work. An archive that evicts
nulls and failed replications to make room for elites destroys exactly the
evidence that prevents the same dead end being re-explored, so eviction here is
class-aware rather than fitness-ordered.

EF4-I50 adds the spatial half of the same idea: islands specialize on a typed
axis, and migration between them is compatibility-gated and recorded on both
sides, so a migrant never reads as native to the island it arrived at.
"""

from __future__ import annotations

from .archive import (
    ArchivePolicyViolation,
    PROTECTED_ENTRY_CLASSES,
    build_archive_entry,
    build_quality_diversity_map,
    evictable_entries,
)
from .islands import (
    SPECIALIZATION_AXES,
    IslandPolicyViolation,
    MigrationRefused,
    build_island_state,
    migrate_candidate,
    migration_blockers,
    migration_history_preserved,
    specialization,
)

__all__ = [
    "ArchivePolicyViolation",
    "IslandPolicyViolation",
    "MigrationRefused",
    "PROTECTED_ENTRY_CLASSES",
    "SPECIALIZATION_AXES",
    "build_archive_entry",
    "build_island_state",
    "build_quality_diversity_map",
    "evictable_entries",
    "migrate_candidate",
    "migration_blockers",
    "migration_history_preserved",
    "specialization",
]
