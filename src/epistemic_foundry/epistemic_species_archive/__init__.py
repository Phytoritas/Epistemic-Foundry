"""Epistemic Species Archive: quality-diversity with negative knowledge kept.

`AGENTS.md`: quality-diversity archives preserve negative knowledge, failed
replications, unsafe candidates, and minority lineages where policy permits.

That makes the archive the memory of what did not work. An archive that evicts
nulls and failed replications to make room for elites destroys exactly the
evidence that prevents the same dead end being re-explored, so eviction here is
class-aware rather than fitness-ordered.
"""

from __future__ import annotations

from .archive import (
    ArchivePolicyViolation,
    PROTECTED_ENTRY_CLASSES,
    build_archive_entry,
    build_quality_diversity_map,
    evictable_entries,
)

__all__ = [
    "ArchivePolicyViolation",
    "PROTECTED_ENTRY_CLASSES",
    "build_archive_entry",
    "build_quality_diversity_map",
    "evictable_entries",
]
