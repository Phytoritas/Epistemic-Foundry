"""Typed search state and adversarial lane coverage.

Invariant EF4-I05 keeps four states distinct:

* `UNSEARCHED` — the lane was never queried.
* `SEARCHED_NONE` — queried, nothing found. This is a real result.
* `SEARCHED_WITH_RESULTS` — queried, results returned.
* `SEARCH_FAILED` — the query errored; its outcome is unknown.

`is_absence_of_evidence` returns True only for `SEARCHED_NONE`. `UNSEARCHED` and
`SEARCH_FAILED` are ignorance, not absence, and treating them as absence is the
specific inference this module exists to block.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping


class SearchState(str, Enum):
    """The four distinct outcomes of querying one retrieval lane."""

    UNSEARCHED = "UNSEARCHED"
    SEARCHED_NONE = "SEARCHED_NONE"
    SEARCHED_WITH_RESULTS = "SEARCHED_WITH_RESULTS"
    SEARCH_FAILED = "SEARCH_FAILED"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


#: Lanes that must be searched whenever they apply (EF4-I06).
MANDATORY_LANES: tuple[str, ...] = ("support", "counter", "null", "boundary", "method")


class LaneCoverageFailure(ValueError):
    """A retrieval plan omits a mandatory adversarial lane."""


def is_absence_of_evidence(state: SearchState | str) -> bool:
    """True only when a lane was actually searched and returned nothing.

    An unsearched or failed lane yields False: those are states of ignorance,
    and reporting them as absence would license an unearned negative claim.
    """
    return SearchState(state) is SearchState.SEARCHED_NONE


def is_conclusive(state: SearchState | str) -> bool:
    """True when the lane produced a usable result, empty or not."""
    return SearchState(state) in {SearchState.SEARCHED_NONE, SearchState.SEARCHED_WITH_RESULTS}


def missing_lanes(
    lane_states: Mapping[str, SearchState | str],
    *,
    applicable: Iterable[str] = MANDATORY_LANES,
) -> list[str]:
    """Applicable lanes that were never conclusively searched.

    A lane present but `UNSEARCHED` or `SEARCH_FAILED` counts as missing: the
    plan claims the lane exists while contributing no information from it.
    """
    gaps: list[str] = []
    for lane in applicable:
        state = lane_states.get(lane)
        if state is None or not is_conclusive(state):
            gaps.append(lane)
    return sorted(gaps)


def require_lane_coverage(
    lane_states: Mapping[str, SearchState | str],
    *,
    applicable: Iterable[str] = MANDATORY_LANES,
) -> None:
    """Raise `LaneCoverageFailure` when a mandatory lane is not covered."""
    gaps = missing_lanes(lane_states, applicable=applicable)
    if gaps:
        raise LaneCoverageFailure(
            f"mandatory retrieval lane(s) {gaps} were not conclusively searched; "
            "an unsearched counter or null lane cannot support a confident verdict"
        )


def coverage_summary(lane_states: Mapping[str, SearchState | str]) -> dict[str, int]:
    """Counts per state, for a coverage surface that shows gaps before verdicts."""
    summary = {state.value: 0 for state in SearchState}
    for state in lane_states.values():
        summary[SearchState(state).value] += 1
    return summary
