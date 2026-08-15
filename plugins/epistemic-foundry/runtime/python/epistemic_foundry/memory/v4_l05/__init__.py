"""Evolution memory retention, forget planning and export scoping (L05).

The archive owns eviction and the memory policy owns recall; this package owns
what survives an actual forget and what an export may carry out.
"""

from __future__ import annotations

from .retention import (
    CAPACITY_GROUND,
    EvolutionMemoryError,
    FINDING_CODES,
    FORGET_GROUNDS,
    FORGET_OUTCOMES,
    LineageMemory,
    build_export_manifest,
    entry_class_vocabulary,
    plan_forget,
    require_executable_forget,
)

__all__ = [
    "CAPACITY_GROUND",
    "EvolutionMemoryError",
    "FINDING_CODES",
    "FORGET_GROUNDS",
    "FORGET_OUTCOMES",
    "LineageMemory",
    "build_export_manifest",
    "entry_class_vocabulary",
    "plan_forget",
    "require_executable_forget",
]
