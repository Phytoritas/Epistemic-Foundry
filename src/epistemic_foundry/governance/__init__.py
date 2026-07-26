"""Promotion authority and evidence-dependency correction.

This package holds the rule the whole architecture exists to protect: no
scalar score, vote, model confidence, novelty label, or backend `correct` flag
can promote a candidate (MASTER_EXECUTION_PROMPT section 8, invariant EF4-I09).
"""

from __future__ import annotations

from .dependency import build_dependency_cluster, adjusted_support_count
from .promotion import (
    PromotionRefused,
    PromotionRequest,
    decide_promotion,
)
from .separation import (
    RelabelingRefused,
    SelfApprovalRefused,
    require_independent_approval,
    require_no_empirical_relabeling,
)

__all__ = [
    "PromotionRefused",
    "PromotionRequest",
    "RelabelingRefused",
    "SelfApprovalRefused",
    "adjusted_support_count",
    "build_dependency_cluster",
    "decide_promotion",
    "require_independent_approval",
    "require_no_empirical_relabeling",
]
