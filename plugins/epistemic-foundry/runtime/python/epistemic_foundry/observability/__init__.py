"""Result-state honesty and ranking integrity.

* EF4-I23: `EMPTY_CONFIRMED`, `DEGRADED`, and `UNAVAILABLE` are distinct, and a
  backend failure never appears as empty research state. Rendering a timeout as
  "no results" is the single most misleading thing a research tool can do: the
  reader concludes nothing exists when in fact nothing was looked at.
* EF4-I24: a map labeled ranked uses an actual algorithm, and baseline
  centrality, query relevance, and risk stay separate signals.
"""

from __future__ import annotations

from .result_state import (
    ResultState,
    ResultStateViolation,
    classify_result,
    is_empty_research_finding,
)
from .ranking import RankingIntegrityError, require_declared_ranking

__all__ = [
    "RankingIntegrityError",
    "ResultState",
    "ResultStateViolation",
    "classify_result",
    "is_empty_research_finding",
    "require_declared_ranking",
]
