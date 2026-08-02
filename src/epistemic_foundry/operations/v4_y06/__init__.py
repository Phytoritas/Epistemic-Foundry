"""2,000-document evolution qualification and cost/latency integration gate (Y06).

Composes the sealed E05 three-way count reconciliation, the Y05 bounded-budget
attestation, the surrogate ordering surface and the canonical promotion-commit
capability into one integration gate over a production-scale qualification run:
counts reconcile exactly, cost and latency stay inside the declared budget, the
surrogate stays within its ceiling, and the scale run never becomes a
promotion-authority path — with every decision resolving to an immutable,
re-derivable receipt.
"""

from __future__ import annotations

from .qualification import (
    COST_DIMENSION,
    FINDING_CODES,
    OperationsQualificationError,
    QUAL_AUTHORITY_PREFIX,
    QUAL_BUDGET_PREFIX,
    QUAL_COUNT_PREFIX,
    QUAL_SURROGATE_PREFIX,
    QUAL_VERDICT_PREFIX,
    qualify_evolution_run,
    reconcile_qualification_counts,
    require_bounded_qualification_budget,
    require_no_scale_authority_capture,
    require_surrogate_within_ceiling,
    surrogate_acceptance_token,
)

__all__ = [
    "COST_DIMENSION",
    "FINDING_CODES",
    "OperationsQualificationError",
    "QUAL_AUTHORITY_PREFIX",
    "QUAL_BUDGET_PREFIX",
    "QUAL_COUNT_PREFIX",
    "QUAL_SURROGATE_PREFIX",
    "QUAL_VERDICT_PREFIX",
    "qualify_evolution_run",
    "reconcile_qualification_counts",
    "require_bounded_qualification_budget",
    "require_no_scale_authority_capture",
    "require_surrogate_within_ceiling",
    "surrogate_acceptance_token",
]
