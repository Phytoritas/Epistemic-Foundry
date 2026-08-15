"""Quality-diversity scaling, surrogate triage, budgets and production load (Y05).

Composes the sealed archive quality-diversity coverage, the surrogate triage
surface, the Y01 budget envelope, the N05 schedule fan-in gate and the Q05
admissibility gate into one operations surface that keeps a production-scale run
diverse, its surrogate triage-only, its spend bounded and its load shedding
honest, with every decision resolving to an immutable, re-derivable receipt.
"""

from __future__ import annotations

from .scaling import (
    FINDING_CODES,
    OperationsScalingError,
    QD_MAP_KIND,
    REBALANCE_KIND,
    SURROGATE_KIND,
    bind_triage_to_gate,
    build_scaled_quality_diversity_map,
    plan_diversity_preserving_rebalance,
    reconcile_shed_load,
    require_bounded_production_budget,
    require_surrogate_never_promotes,
    surrogate_hard_gate_reject_token,
    triage_at_scale,
)

__all__ = [
    "FINDING_CODES",
    "OperationsScalingError",
    "QD_MAP_KIND",
    "REBALANCE_KIND",
    "SURROGATE_KIND",
    "bind_triage_to_gate",
    "build_scaled_quality_diversity_map",
    "plan_diversity_preserving_rebalance",
    "reconcile_shed_load",
    "require_bounded_production_budget",
    "require_surrogate_never_promotes",
    "surrogate_hard_gate_reject_token",
    "triage_at_scale",
]
