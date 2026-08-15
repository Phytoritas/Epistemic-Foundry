"""Evolution Chamber console (U05): read-only projections of sealed state.

This package projects the four sealed Evolution Chamber surfaces — the Pareto
front of non-dominated candidates, the M05 quality-diversity niche map, the
candidate lineages, and the Red Queen challenge board — into deep-frozen,
deterministic, hash-re-derivable view records.  It is read-only over the sealed
surfaces: it validates and re-derives what it is given, refuses malformed or
undeclared input, invents nothing, and confers no evaluator, holdout or
promotion authority on anyone.  It holds no canonical enum vocabulary of its
own; challenge outcomes and severities are read from the schema that declares
them (EF4-I22).
"""

from __future__ import annotations

from .projection import (
    CHALLENGE_GENOME_SCHEMA,
    CHALLENGE_RESULT_SCHEMA,
    DEFAULT_REQUESTING_ROLE,
    FINDING_CODES,
    LINEAGE_SCHEMA,
    NICHE_SCHEMA,
    PARETO_SNAPSHOT_SCHEMA,
    SURFACE_CHALLENGE_BOARD,
    SURFACE_LINEAGES,
    SURFACE_NICHE_MAP,
    SURFACE_PARETO_FRONT,
    VIEW_ID_PREFIX,
    ConsoleProjectionRefused,
    SchemaNotFound,
    build_console_projection,
    challenge_outcome_vocabulary,
    challenge_severity_vocabulary,
    declared_surfaces,
    project_challenge_board,
    project_lineages,
    project_niche_map,
    project_pareto_front,
    require_view_identity,
)

__all__ = [
    "CHALLENGE_GENOME_SCHEMA",
    "CHALLENGE_RESULT_SCHEMA",
    "DEFAULT_REQUESTING_ROLE",
    "FINDING_CODES",
    "LINEAGE_SCHEMA",
    "NICHE_SCHEMA",
    "PARETO_SNAPSHOT_SCHEMA",
    "SURFACE_CHALLENGE_BOARD",
    "SURFACE_LINEAGES",
    "SURFACE_NICHE_MAP",
    "SURFACE_PARETO_FRONT",
    "VIEW_ID_PREFIX",
    "ConsoleProjectionRefused",
    "SchemaNotFound",
    "build_console_projection",
    "challenge_outcome_vocabulary",
    "challenge_severity_vocabulary",
    "declared_surfaces",
    "project_challenge_board",
    "project_lineages",
    "project_niche_map",
    "project_pareto_front",
    "require_view_identity",
]
