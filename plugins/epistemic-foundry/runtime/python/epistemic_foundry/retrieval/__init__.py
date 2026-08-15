"""Retrieval: typed search state and mandatory adversarial lanes.

Invariants implemented here:

* EF4-I05 (search-state type safety): `UNSEARCHED`, `SEARCHED_NONE`,
  `SEARCHED_WITH_RESULTS`, and a failed search are four distinct states. The
  distinction matters because collapsing "we looked and found nothing" into
  "we did not look" — or worse, into "nothing exists" — is how an absence of
  evidence becomes evidence of absence.
* EF4-I06 (adversarial retrieval): counter, null, boundary, and method lanes are
  mandatory when applicable, so a plan omitting them is refused.
"""

from __future__ import annotations

from .search_state import (
    MANDATORY_LANES,
    LaneCoverageFailure,
    SearchState,
    is_absence_of_evidence,
    missing_lanes,
    require_lane_coverage,
)

__all__ = [
    "MANDATORY_LANES",
    "LaneCoverageFailure",
    "SearchState",
    "is_absence_of_evidence",
    "missing_lanes",
    "require_lane_coverage",
]
