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


# ---------------------------------------------------------------------------
# Canonical retrieval vocabulary (EF4-I22: declared once, imported everywhere).
#
# These values are enum members of `schemas/search-lane-receipt.schema.json`,
# `schemas/retrieval-candidate.schema.json`, and `schemas/query-plan.schema.json`.
# They live here rather than in each retrieval module because a second copy is
# how a wire literal drifts from the contract it claims to satisfy.
# ---------------------------------------------------------------------------

LANE_LEXICAL = "lexical"
LANE_SEMANTIC = "semantic"
LANE_CITATION = "citation"
LANE_ENTITY_VARIABLE = "entity_variable"
LANE_MECHANISM = "mechanism"
LANE_COUNTEREVIDENCE = "counterevidence"
LANE_NULL = "null"
LANE_BOUNDARY = "boundary"
LANE_METHOD = "method"
LANE_TEMPORAL = "temporal"
LANE_EXTERNAL_NOVELTY = "external_novelty"

#: The closed lane vocabulary in canonical order (O01, via
#: `workflows/evidence_retrieval.workflow.yaml`). Order is part of the contract:
#: `query-plan.schema.json` pins lane_decisions positionally.
CANONICAL_LANES: tuple[str, ...] = (
    LANE_LEXICAL,
    LANE_SEMANTIC,
    LANE_CITATION,
    LANE_ENTITY_VARIABLE,
    LANE_MECHANISM,
    LANE_COUNTEREVIDENCE,
    LANE_NULL,
    LANE_BOUNDARY,
    LANE_METHOD,
    LANE_TEMPORAL,
    LANE_EXTERNAL_NOVELTY,
)
#: `completeness_contract.all_lane_reconciliation_count`.
ALL_LANE_RECONCILIATION_COUNT = 11

CHANNEL_LEXICAL = "LEXICAL"
CHANNEL_SEMANTIC = "SEMANTIC"
CHANNEL_CITATION_GRAPH = "CITATION_GRAPH"
CHANNEL_RELATION_GRAPH = "RELATION_GRAPH"
CHANNEL_EXTERNAL_INDEX = "EXTERNAL_INDEX"

#: RetrievalCandidate `retrieval_channel` vocabulary, in canonical order.
RETRIEVAL_CHANNELS: tuple[str, ...] = (
    CHANNEL_LEXICAL,
    CHANNEL_SEMANTIC,
    CHANNEL_CITATION_GRAPH,
    CHANNEL_RELATION_GRAPH,
    CHANNEL_EXTERNAL_INDEX,
)
#: `retrieval_candidate_contract.non_vector_release_origins`. A release drawn
#: only from outside this set is a vector-only release, which the workflow caps
#: at PARTIAL because vector similarity may never be the sole retrieval channel.
NON_VECTOR_RELEASE_ORIGINS: frozenset[str] = frozenset(
    {
        CHANNEL_LEXICAL,
        CHANNEL_CITATION_GRAPH,
        CHANNEL_RELATION_GRAPH,
        CHANNEL_EXTERNAL_INDEX,
    }
)

QUERY_FAMILY_FORWARD = "FORWARD"

FUSION_SINGLE_CHANNEL = "SINGLE_CHANNEL"
FUSION_RRF_K60 = "RRF_K60"
#: `lane-local exact deduplication precedes deterministic RRF k=60 fusion`.
RRF_K = 60

RELATION_DIRECTION_NONE = "NO_DIRECTION"
RELATION_DIRECTION_UNRESOLVED = "UNRESOLVED"

RECEIPT_KIND_EXECUTION = "EXECUTION"
RECEIPT_KIND_SENTINEL = "SENTINEL"
SENTINEL_NOT_REQUIRED_FOR_CLASS = "NOT_REQUIRED_FOR_CLASS"
SENTINEL_NOT_APPLICABLE = "NOT_APPLICABLE"
SENTINEL_REASONS: frozenset[str] = frozenset(
    {SENTINEL_NOT_REQUIRED_FOR_CLASS, SENTINEL_NOT_APPLICABLE}
)

STOP_REASON_EXHAUSTED_QUERY_PLAN = "exhausted_query_plan"

RUN_CEILING_PASS = "PASS"
RUN_CEILING_PARTIAL = "PARTIAL"


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
    return SearchState(state) in {
        SearchState.SEARCHED_NONE,
        SearchState.SEARCHED_WITH_RESULTS,
    }


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
