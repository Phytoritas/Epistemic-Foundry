"""Epistemic niche mapper, lineage diversity and blast-radius cartography (M05).

The map answers where a candidate sits, how concentrated the population is,
and what a change would touch — it never promotes, evicts or erases.
"""

from __future__ import annotations

from .mapper import (
    CartographyError,
    FINDING_CODES,
    INBREEDING_RULES,
    NicheMap,
    axis_vocabulary,
    build_coverage_map,
    build_lineage_diversity_report,
    build_niche,
    canonical_axis_values,
    compute_blast_radius,
    niche_id_for,
)

__all__ = [
    "CartographyError",
    "FINDING_CODES",
    "INBREEDING_RULES",
    "NicheMap",
    "axis_vocabulary",
    "build_coverage_map",
    "build_lineage_diversity_report",
    "build_niche",
    "canonical_axis_values",
    "compute_blast_radius",
    "niche_id_for",
]
