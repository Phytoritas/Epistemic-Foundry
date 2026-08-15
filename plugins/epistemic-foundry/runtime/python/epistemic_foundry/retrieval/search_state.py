"""Typed search state and adversarial lane coverage.

Invariant EF4-I05 keeps four coverage states distinct:

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
from types import MappingProxyType
from typing import Iterable, Mapping


class SearchState(str, Enum):
    """The four distinct coverage outcomes of querying one retrieval lane.

    This is the coverage vocabulary, not the receipt wire vocabulary: the
    receipt schema declares six states, and the three inconclusive ones
    (`PARTIAL`, `BLOCKED`, `FAILED`) all project onto `SEARCH_FAILED` here,
    because none of them answered the lane. See `RECEIPT_STATE_*` below for the
    wire values and `v4_o05.coverage_state` for the projection.
    """

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
QUERY_FAMILY_REVERSE = "REVERSE"
QUERY_FAMILY_NULL = "NULL"
QUERY_FAMILY_BOUNDARY = "BOUNDARY"
QUERY_FAMILY_METHOD = "METHOD"
QUERY_FAMILY_NOVELTY = "NOVELTY"

#: Which query families each lane binds. `workflows/evidence_retrieval.workflow.yaml`
#: states this explicitly for the four adversarial lanes (counterevidence at
#: :429, null at :477, boundary at :525, method at :573); the full eleven-lane
#: mapping is O01's, in `python/epistemic_foundry/retrieval/planning/contracts.py`.
#: The adversarial lanes are not FORWARD searches wearing a different name: a
#: NULL lane answered with a FORWARD query would report a different search than
#: the one the lane owes, and counterevidence is complete only when both
#: directions run. Immutable, because these values are hashed into sealed
#: receipts and a runtime edit would silently change past query bindings.
LANE_QUERY_FAMILIES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    LANE_LEXICAL: (QUERY_FAMILY_FORWARD,),
    LANE_SEMANTIC: (QUERY_FAMILY_FORWARD,),
    LANE_CITATION: (QUERY_FAMILY_FORWARD,),
    LANE_ENTITY_VARIABLE: (QUERY_FAMILY_FORWARD,),
    LANE_MECHANISM: (QUERY_FAMILY_FORWARD,),
    LANE_COUNTEREVIDENCE: (QUERY_FAMILY_FORWARD, QUERY_FAMILY_REVERSE),
    LANE_NULL: (QUERY_FAMILY_NULL,),
    LANE_BOUNDARY: (QUERY_FAMILY_BOUNDARY,),
    LANE_METHOD: (QUERY_FAMILY_METHOD,),
    LANE_TEMPORAL: (QUERY_FAMILY_FORWARD,),
    LANE_EXTERNAL_NOVELTY: (QUERY_FAMILY_NOVELTY,),
})

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
STOP_REASON_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_REASON_TIME_EXHAUSTED = "time_exhausted"
STOP_REASON_MANUAL_STOP = "manual_stop"
STOP_REASON_POLICY_BLOCKED = "policy_blocked"
STOP_REASON_CREDENTIAL_UNAVAILABLE = "credential_unavailable"
STOP_REASON_BACKEND_UNAVAILABLE = "backend_unavailable"

# ---------------------------------------------------------------------------
# Receipt wire states (`schemas/search-lane-receipt.schema.json`). Six values,
# against the four coverage states above. `RECEIPT_STATE_BLOCKED` is the one a
# selected lane owes when no backend can serve it: the plan promised a search,
# so reporting `UNSEARCHED` would silently retract the obligation instead of
# recording that it went unmet.
# ---------------------------------------------------------------------------

RECEIPT_STATE_UNSEARCHED = "UNSEARCHED"
RECEIPT_STATE_SEARCHED_NONE = "SEARCHED_NONE"
RECEIPT_STATE_SEARCHED_WITH_RESULTS = "SEARCHED_WITH_RESULTS"
RECEIPT_STATE_PARTIAL = "PARTIAL"
RECEIPT_STATE_BLOCKED = "BLOCKED"
RECEIPT_STATE_FAILED = "FAILED"

#: Stop reasons the schema admits for a `BLOCKED` receipt.
BLOCKED_STOP_REASONS: frozenset[str] = frozenset(
    {
        STOP_REASON_POLICY_BLOCKED,
        STOP_REASON_CREDENTIAL_UNAVAILABLE,
        STOP_REASON_BACKEND_UNAVAILABLE,
    }
)
#: Stop reasons the schema admits for a `PARTIAL` receipt.
PARTIAL_STOP_REASONS: frozenset[str] = frozenset(
    {
        STOP_REASON_BUDGET_EXHAUSTED,
        STOP_REASON_TIME_EXHAUSTED,
        STOP_REASON_MANUAL_STOP,
    }
)

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
