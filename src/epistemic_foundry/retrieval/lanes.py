"""Canonical retrieval lanes over the local lexical index.

`workflows/evidence_retrieval.workflow.yaml` fixes a closed vocabulary of eleven
lanes and requires that all eleven be reconciled on every run
(``all_lane_reconciliation_count: 11``). This module executes the lanes the
local index can genuinely serve and reports the rest as explicit UNSEARCHED
sentinels. That distinction is the point: a lane reported as an empty result set
licenses an absence claim, while a lane reported as unsearched does not, and
collapsing the two is the specific error `search_state` exists to prevent.

Executed lanes and why each is supportable here:

* ``lexical`` → ``LEXICAL``. SQLite FTS5 BM25 over the indexed corpus. Exact
  terms, identifiers, and phrases, which is precisely the lane's stated purpose.
* ``citation`` → ``CITATION_GRAPH``. Bibliographic coupling over author-year
  citation keys extracted at index time. Two papers citing the same work share a
  real edge, computed with no external index.
* ``entity_variable`` → ``RELATION_GRAPH``. Windowed co-occurrence of two or more
  term groups inside one document. Co-occurrence establishes shared entities and
  variables; it does not establish direction, so every candidate from this lane
  carries ``relation_direction: UNRESOLVED`` rather than a guessed orientation.

The remaining eight lanes are sentinels with a stated reason (see
``ABSENT_LANE_REASONS``). None of them is faked as "searched, nothing found".

Because all three executed channels are in the workflow's
``non_vector_release_origins``, a release built from them never depends on
vector similarity — the invariant the eleven-lane contract is written to protect.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import lexical_index
from .lexical_index import LexicalIndexError, QueryTerm
from .search_state import (
    ALL_LANE_RECONCILIATION_COUNT,
    CANONICAL_LANES,
    CHANNEL_CITATION_GRAPH,
    CHANNEL_LEXICAL,
    CHANNEL_RELATION_GRAPH,
    FUSION_RRF_K60,
    FUSION_SINGLE_CHANNEL,
    LANE_BOUNDARY,
    LANE_CITATION,
    LANE_COUNTEREVIDENCE,
    LANE_ENTITY_VARIABLE,
    LANE_EXTERNAL_NOVELTY,
    LANE_LEXICAL,
    LANE_MECHANISM,
    LANE_METHOD,
    LANE_NULL,
    LANE_SEMANTIC,
    LANE_TEMPORAL,
    NON_VECTOR_RELEASE_ORIGINS,
    QUERY_FAMILY_FORWARD,
    RECEIPT_KIND_EXECUTION,
    RECEIPT_KIND_SENTINEL,
    RELATION_DIRECTION_NONE,
    RELATION_DIRECTION_UNRESOLVED,
    RETRIEVAL_CHANNELS,
    RRF_K,
    RUN_CEILING_PARTIAL,
    RUN_CEILING_PASS,
    SENTINEL_NOT_APPLICABLE,
    SENTINEL_REASONS,
    STOP_REASON_EXHAUSTED_QUERY_PLAN,
    SearchState,
    coverage_summary,
    is_absence_of_evidence,
    require_lane_coverage,
)

#: Canonical channel order, re-exported so lane code reads in one namespace.
CHANNEL_ORDER: tuple[str, ...] = RETRIEVAL_CHANNELS
#: `retrieval_candidate_contract.vector_only_run_ceiling`.
VECTOR_ONLY_RUN_CEILING = RUN_CEILING_PARTIAL

#: The single retrieval channel each executed lane actually uses.
LANE_CHANNEL: dict[str, str] = {
    LANE_LEXICAL: CHANNEL_LEXICAL,
    LANE_CITATION: CHANNEL_CITATION_GRAPH,
    LANE_ENTITY_VARIABLE: CHANNEL_RELATION_GRAPH,
}
EXECUTED_LANES: tuple[str, ...] = tuple(
    lane for lane in CANONICAL_LANES if lane in LANE_CHANNEL
)

#: Why each unimplemented lane is a sentinel rather than an empty result.
ABSENT_LANE_REASONS: dict[str, str] = {
    LANE_SEMANTIC: (
        "no vector backend is configured; the workflow forbids vector similarity as "
        "a sole retrieval channel, so the non-vector lanes are built first and this "
        "lane is declared unsearched rather than approximated lexically"
    ),
    LANE_MECHANISM: (
        "requires a mechanism relation graph with intermediate links; no relation "
        "extraction exists over this corpus, and term proximity is not a mechanism"
    ),
    LANE_COUNTEREVIDENCE: (
        "the lane is complete only when both FORWARD and REVERSE query families "
        "execute against a canonical relation; no relation direction is extracted "
        "here, so a forward-only result would misreport the lane as covered"
    ),
    LANE_NULL: (
        "accepts only the NULL query family; no null-result, failed-replication, or "
        "equivalence classifier exists over this corpus"
    ),
    LANE_BOUNDARY: (
        "accepts only the BOUNDARY query family; no moderator, threshold, or "
        "non-monotonicity extraction exists over this corpus"
    ),
    LANE_METHOD: (
        "accepts only the METHOD query family; no measurement-validity or design "
        "extraction exists over this corpus"
    ),
    LANE_TEMPORAL: (
        "requires approved external search and a sealed versioned date and "
        "correction filter; the corpus carries no publication-date field and no "
        "correction or retraction records, so body-text years would be a date proxy "
        "and not a correction path"
    ),
    LANE_EXTERNAL_NOVELTY: (
        "requires an approved corpus-external index and a sealed external scope and "
        "stop rule; no external index is configured"
    ),
}
ABSENT_LANES: tuple[str, ...] = tuple(
    lane for lane in CANONICAL_LANES if lane not in LANE_CHANNEL
)

BACKEND_ID = "epistemic_foundry.retrieval.lexical_index"
BACKEND_VERSION = f"fts5-schema-{lexical_index.SCHEMA_VERSION}"
ADAPTER_ID = "epistemic_foundry.retrieval.lanes"
ADAPTER_VERSION = "1"

DEFAULT_MAX_CANDIDATES = 25
DEFAULT_COOCCURRENCE_WINDOW = 420

#: Every lane executed here takes the FORWARD family, which is what the
#: RetrievalCandidate schema requires for lexical, citation, and entity_variable.
FORWARD = QUERY_FAMILY_FORWARD

_RANKING_FEATURE_FIELDS: tuple[str, ...] = (
    "scope_overlap",
    "relation_direction_match",
    "source_directness",
    "method_compatibility",
    "publication_version_status",
    "extraction_grounding_confidence",
)

_CANDIDATE_IDENTITY_FIELDS: tuple[str, ...] = (
    "plan_hash",
    "lane",
    "query_hash",
    "canonical_source_key",
    "source_version",
    "source_snapshot_hash",
)

_CANDIDATE_HASH_FIELDS: tuple[str, ...] = (
    "run_id",
    "query_plan_id",
    "plan_hash",
    "lane",
    "query_family",
    "query_text",
    "query_hash",
    "scope_filter",
    "corpus_snapshot_hash",
    "index_versions",
    "backend_id",
    "backend_version",
    "backend_adapter_id",
    "backend_adapter_version",
    "backend_request_hash",
    "backend_response_hash",
    "backend_receipt_id",
    "canonical_source_key",
    "source_record_id",
    "source_artifact_id",
    "source_locator",
    "source_version",
    "source_snapshot_hash",
    "source_span_id",
    "raw_rank",
    "raw_scores",
    "channel_ranks",
    "retrieval_channels",
    "fusion_method",
    "fusion_score",
    "ranking_features",
    "matched_terms",
    "matched_edges",
    "relation_direction",
    "scope_estimate",
    "duplicate_candidate_ids",
    "multi_channel_verified",
    "retrieval_explanation",
)

_SCOPE_VECTOR_NULL_FIELDS: tuple[str, ...] = (
    "domain",
    "population",
    "entity_type",
    "entity_subtype",
    "unit_of_analysis",
    "setting",
    "geography",
    "jurisdiction",
    "language",
    "lifecycle_stage",
    "spatial_scale",
    "temporal_scale",
    "time_period",
    "measurement_time",
    "intervention_or_exposure",
    "comparator",
)


class LaneContractError(ValueError):
    """A lane was asked to do something the contract does not allow."""


def canonical_json(value: Any) -> bytes:
    """RFC 8785 JCS-equivalent deterministic UTF-8 bytes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_object(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def empty_scope_vector(**overrides: Any) -> dict[str, Any]:
    """A schema-valid ScopeVector whose unknown fields are null, not invented.

    Retrieval scope that has not been established is left null on purpose:
    a fabricated population or setting would later be compared against real
    evidence scope and silently widen an extrapolation.
    """
    scope: dict[str, Any] = {
        field_name: None for field_name in _SCOPE_VECTOR_NULL_FIELDS
    }
    scope["inclusion_criteria"] = []
    scope["exclusion_criteria"] = []
    scope["conditions"] = {}
    scope["domain_extensions"] = {}
    unknown = sorted(set(overrides) - set(scope))
    if unknown:
        raise LaneContractError(f"ScopeVector has no field(s): {unknown}")
    scope.update(overrides)
    return scope


@dataclass(frozen=True)
class LaneContext:
    """Everything a lane must bind into its request, receipt, and candidates.

    Timestamps are caller-supplied. Nothing in this module reads a clock, so a
    replay of the same inputs reproduces the same artifacts byte for byte.
    """

    run_id: str
    query_plan_id: str
    plan_hash: str
    policy_bundle_hash: str
    capability_lease_id: str
    cutoff_policy_id: str
    corpus_snapshot_hash: str
    index_versions: Mapping[str, str]
    lane_decision_evidence_ids: Sequence[str]
    started_at: str
    finished_at: str
    scope_filter: Mapping[str, Any] = field(default_factory=empty_scope_vector)
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    deterministic_seed: int = 0

    def __post_init__(self) -> None:
        if not self.lane_decision_evidence_ids:
            raise LaneContractError(
                "lane_decision_evidence_ids must name at least one decision record; "
                "a lane decision without evidence is not auditable"
            )
        if self.max_candidates < 1:
            raise LaneContractError("max_candidates must be a positive integer")

    @classmethod
    def from_index_stats(
        cls,
        stats: Mapping[str, Any],
        *,
        run_id: str,
        query_plan_id: str,
        plan_hash: str,
        policy_bundle_hash: str,
        capability_lease_id: str,
        cutoff_policy_id: str,
        lane_decision_evidence_ids: Sequence[str],
        started_at: str,
        finished_at: str,
        scope_filter: Mapping[str, Any] | None = None,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
        deterministic_seed: int = 0,
    ) -> LaneContext:
        """Bind a context to the exact snapshot and index versions of a build."""
        return cls(
            run_id=run_id,
            query_plan_id=query_plan_id,
            plan_hash=plan_hash,
            policy_bundle_hash=policy_bundle_hash,
            capability_lease_id=capability_lease_id,
            cutoff_policy_id=cutoff_policy_id,
            corpus_snapshot_hash=str(stats["corpus_snapshot_hash"]),
            index_versions=dict(stats["index_versions"]),
            lane_decision_evidence_ids=tuple(lane_decision_evidence_ids),
            started_at=started_at,
            finished_at=finished_at,
            scope_filter=dict(scope_filter) if scope_filter else empty_scope_vector(),
            max_candidates=max_candidates,
            deterministic_seed=deterministic_seed,
        )


@dataclass(frozen=True)
class LaneResult:
    """One lane's typed outcome, candidates, receipt, and honest diagnostics."""

    lane: str
    search_state: SearchState
    candidates: tuple[dict[str, Any], ...]
    receipt: dict[str, Any]
    documents: tuple[dict[str, Any], ...]
    duplicate_count: int
    cutoff_count: int
    diagnostics: dict[str, Any]

    @property
    def channel(self) -> str | None:
        return LANE_CHANNEL.get(self.lane)

    @property
    def is_absence_of_evidence(self) -> bool:
        """True only for a lane that was searched and returned nothing."""
        return is_absence_of_evidence(self.search_state)

    def ranked_document_ids(self) -> tuple[str, ...]:
        return tuple(document["document_id"] for document in self.documents)


def _query_batch(lane: str, queries: Sequence[str]) -> dict[str, Any]:
    ordered: list[str] = []
    for item in queries:
        text = str(item).strip()
        if text and text not in ordered:
            ordered.append(text)
    if not ordered:
        raise LaneContractError(f"lane {lane!r} was given no query text to execute")
    return {"lane": lane, "families": [{"family": FORWARD, "queries": ordered}]}


def _query_text_and_hash(batch: Mapping[str, Any]) -> tuple[str, str]:
    text = canonical_json(batch).decode("utf-8")
    return text, sha256_bytes(text.encode("utf-8"))


def _backend_request(
    context: LaneContext,
    lane: str,
    batch: Mapping[str, Any],
    query_hash: str,
) -> dict[str, Any]:
    """Exactly the `provider_request_binding` field list from the workflow."""
    return {
        "run_id": context.run_id,
        "query_plan_id": context.query_plan_id,
        "plan_hash": context.plan_hash,
        "lane": lane,
        "query_families": [FORWARD],
        "canonical_query_batch": copy.deepcopy(dict(batch)),
        "query_hash": query_hash,
        "scope_filter": copy.deepcopy(dict(context.scope_filter)),
        "corpus_snapshot_hash": context.corpus_snapshot_hash,
        "index_versions": dict(context.index_versions),
        "max_candidates": context.max_candidates,
        "cutoff_policy_id": context.cutoff_policy_id,
        "deterministic_seed": context.deterministic_seed,
        "policy_bundle_hash": context.policy_bundle_hash,
        "capability_lease_id": context.capability_lease_id,
        "backend_id": BACKEND_ID,
        "backend_version": BACKEND_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
    }


def _hit_identity(hit: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(hit["canonical_source_key"]),
        str(hit["source_version"]),
        str(hit["source_snapshot_hash"]),
        str(hit["source_locator"]),
    )


def deduplicate_exact(
    hits: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Drop exact provenance duplicates and restamp stable ranks from 1.

    This runs per channel and before any fusion, as the workflow requires: RRF
    over a list containing the same source twice would count one document as two
    independent retrievals and inflate its fused score.
    """
    ordered = sorted(
        (dict(hit) for hit in hits),
        key=lambda hit: (int(hit["raw_rank"]), str(hit["canonical_source_key"])),
    )
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    duplicate_count = 0
    for hit in ordered:
        identity = _hit_identity(hit)
        if identity in seen:
            duplicate_count += 1
            continue
        seen.add(identity)
        unique.append(hit)
    for stable_rank, hit in enumerate(unique, start=1):
        hit["raw_rank"] = stable_rank
    return unique, duplicate_count


def rrf_fuse(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Reciprocal rank fusion with the contract's ``k`` (60 by default).

    ``score(d) = sum over channels of 1 / (k + rank_channel(d))``, ranks being
    1-based. Ties break on the fused key, so the ordering is total and does not
    depend on dict or input order. Fusion combines rank positions only: it never
    compares raw scores across channels, which are not commensurable.
    """
    if k < 1:
        raise LaneContractError("RRF k must be a positive integer")
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for channel in sorted(rankings):
        for position, key in enumerate(rankings[channel], start=1):
            if channel in ranks.get(key, {}):
                raise LaneContractError(
                    f"channel {channel!r} ranks {key!r} twice; deduplicate before fusion"
                )
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + position)
            ranks.setdefault(key, {})[channel] = position
    fused = [
        {
            "key": key,
            "rrf_score": scores[key],
            "channel_ranks": dict(sorted(ranks[key].items())),
            "channel_count": len(ranks[key]),
        }
        for key in scores
    ]
    fused.sort(key=lambda row: (-row["rrf_score"], row["key"]))
    for rank, row in enumerate(fused, start=1):
        row["rank"] = rank
    return fused


def _ranking_features(*, grounded: bool) -> dict[str, float | None]:
    features: dict[str, float | None] = {name: None for name in _RANKING_FEATURE_FIELDS}
    # The only feature this backend can actually measure: whether the emitted
    # span re-extracts byte-exactly from the indexed text. Everything else is
    # left null rather than filled with a plausible-looking number.
    features["extraction_grounding_confidence"] = 1.0 if grounded else None
    return features


def _candidate_from_channel_hits(
    context: LaneContext,
    lane: str,
    query_text: str,
    query_hash: str,
    request_hash: str,
    response_hash: str,
    backend_receipt_id: str,
    channel_hits: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    channels = sorted(channel_hits, key=CHANNEL_ORDER.index)
    primary = channel_hits[channels[0]]
    raw_scores: dict[str, float | None] = {name: None for name in CHANNEL_ORDER}
    channel_ranks: dict[str, int | None] = {name: None for name in CHANNEL_ORDER}
    for channel in channels:
        raw_scores[channel] = float(channel_hits[channel]["raw_score"])
        channel_ranks[channel] = int(channel_hits[channel]["raw_rank"])
    fusion_method = FUSION_SINGLE_CHANNEL
    fusion_score: float | None = None
    if len(channels) > 1:
        fusion_method = FUSION_RRF_K60
        fusion_score = sum(
            1.0 / (RRF_K + int(channel_ranks[channel])) for channel in channels
        )
    span_id = primary.get("source_span_id")
    candidate: dict[str, Any] = {
        "run_id": context.run_id,
        "query_plan_id": context.query_plan_id,
        "plan_hash": context.plan_hash,
        "lane": lane,
        "query_family": FORWARD,
        "query_text": query_text,
        "query_hash": query_hash,
        "scope_filter": copy.deepcopy(dict(context.scope_filter)),
        "corpus_snapshot_hash": context.corpus_snapshot_hash,
        "index_versions": dict(context.index_versions),
        "backend_id": BACKEND_ID,
        "backend_version": BACKEND_VERSION,
        "backend_adapter_id": ADAPTER_ID,
        "backend_adapter_version": ADAPTER_VERSION,
        "backend_request_hash": request_hash,
        "backend_response_hash": response_hash,
        "backend_receipt_id": backend_receipt_id,
        "canonical_source_key": str(primary["canonical_source_key"]),
        "source_record_id": str(primary["source_record_id"]),
        "source_artifact_id": None,
        "source_locator": str(primary["source_locator"]),
        "source_version": str(primary["source_version"]),
        "source_snapshot_hash": str(primary["source_snapshot_hash"]),
        "source_span_id": span_id,
        "raw_rank": min(int(hit["raw_rank"]) for hit in channel_hits.values()),
        "raw_scores": raw_scores,
        "channel_ranks": channel_ranks,
        "retrieval_channels": channels,
        "fusion_method": fusion_method,
        "fusion_score": fusion_score,
        "ranking_features": _ranking_features(grounded=span_id is not None),
        "matched_terms": sorted(
            {
                term
                for hit in channel_hits.values()
                for term in hit.get("matched_terms", ())
            }
        ),
        "matched_edges": sorted(
            {
                edge
                for hit in channel_hits.values()
                for edge in hit.get("matched_edges", ())
            }
        ),
        "relation_direction": str(primary["relation_direction"]),
        "scope_estimate": None,
        "duplicate_candidate_ids": [],
        "multi_channel_verified": len(channels) > 1,
        "retrieval_explanation": str(primary["retrieval_explanation"]),
    }
    identity = {name: candidate[name] for name in _CANDIDATE_IDENTITY_FIELDS}
    candidate["candidate_id"] = (
        "RC-" + hashlib.sha256(canonical_json(identity)).hexdigest()
    )
    candidate["candidate_hash"] = _sha256_object(
        {name: candidate[name] for name in _CANDIDATE_HASH_FIELDS}
    )
    return candidate


def build_lane_candidates(
    context: LaneContext,
    lane: str,
    queries: Sequence[str],
    channel_hits: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deduplicate per channel, fuse with RRF k=60, cut off, and seal candidates.

    ``channel_hits`` maps a retrieval channel to that channel's raw hit list.
    A lane serving one channel produces SINGLE_CHANNEL candidates; a lane serving
    several produces RRF_K60 candidates whose fused score is exactly
    ``sum(1 / (60 + channel_rank))``, as the RetrievalCandidate contract states.
    """
    unknown = sorted(set(channel_hits) - set(CHANNEL_ORDER))
    if unknown:
        raise LaneContractError(f"unknown retrieval channel(s): {unknown}")
    batch = _query_batch(lane, queries)
    query_text, query_hash = _query_text_and_hash(batch)
    request = _backend_request(context, lane, batch, query_hash)
    request_hash = _sha256_object(request)

    deduplicated: dict[str, list[dict[str, Any]]] = {}
    duplicate_count = 0
    for channel in sorted(channel_hits, key=CHANNEL_ORDER.index):
        unique, duplicates = deduplicate_exact(channel_hits[channel])
        duplicate_count += duplicates
        deduplicated[channel] = unique

    response = {
        "request_hash": request_hash,
        "channels": {
            channel: [
                {
                    "canonical_source_key": hit["canonical_source_key"],
                    "raw_rank": hit["raw_rank"],
                    "raw_score": hit["raw_score"],
                    "source_version": hit["source_version"],
                    "source_snapshot_hash": hit["source_snapshot_hash"],
                    "source_locator": hit["source_locator"],
                    "source_span_id": hit.get("source_span_id"),
                }
                for hit in hits
            ]
            for channel, hits in sorted(deduplicated.items())
        },
    }
    response_hash = _sha256_object(response)
    backend_receipt_id = (
        "BR-"
        + hashlib.sha256(f"{request_hash}|{response_hash}".encode("utf-8")).hexdigest()[
            :32
        ]
    )

    grouped: dict[tuple[str, str, str, str], dict[str, Mapping[str, Any]]] = {}
    for channel, hits in deduplicated.items():
        for hit in hits:
            grouped.setdefault(_hit_identity(hit), {})[channel] = hit

    candidates = [
        _candidate_from_channel_hits(
            context,
            lane,
            query_text,
            query_hash,
            request_hash,
            response_hash,
            backend_receipt_id,
            per_channel,
        )
        for _, per_channel in sorted(grouped.items())
    ]

    def ranking_score(candidate: Mapping[str, Any]) -> float:
        if candidate["fusion_score"] is not None:
            return float(candidate["fusion_score"])
        channel = candidate["retrieval_channels"][0]
        return 1.0 / (RRF_K + int(candidate["channel_ranks"][channel]))

    candidates.sort(key=lambda item: (-ranking_score(item), item["candidate_id"]))
    cutoff_count = max(0, len(candidates) - context.max_candidates)
    candidates = candidates[: context.max_candidates]
    metadata = {
        "query_text": query_text,
        "query_hash": query_hash,
        "backend_request_hash": request_hash,
        "backend_response_hash": response_hash,
        "backend_receipt_id": backend_receipt_id,
        "duplicate_count": duplicate_count,
        "cutoff_count": cutoff_count,
    }
    return candidates, metadata


def _receipt_id(context: LaneContext, lane: str) -> str:
    preimage = {
        "run_id": context.run_id,
        "query_plan_id": context.query_plan_id,
        "plan_hash": context.plan_hash,
        "lane": lane,
    }
    return "SLR-" + hashlib.sha256(canonical_json(preimage)).hexdigest()[:32]


def _seal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    preimage = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    receipt["receipt_hash"] = _sha256_object(preimage)
    return receipt


def build_execution_receipt(
    context: LaneContext,
    lane: str,
    *,
    search_state: SearchState,
    query_text: str,
    query_hash: str,
    result_ids: Sequence[str],
    excluded_count: int,
    stop_reason: str = STOP_REASON_EXHAUSTED_QUERY_PLAN,
) -> dict[str, Any]:
    """Seal a schema-valid EXECUTION receipt for a lane that actually ran."""
    if search_state not in {
        SearchState.SEARCHED_WITH_RESULTS,
        SearchState.SEARCHED_NONE,
    }:
        raise LaneContractError(
            f"{search_state} is not an execution outcome this backend can seal"
        )
    return _seal_receipt(
        {
            "receipt_id": _receipt_id(context, lane),
            "run_id": context.run_id,
            "query_plan_id": context.query_plan_id,
            "plan_hash": context.plan_hash,
            "lane": lane,
            "receipt_kind": RECEIPT_KIND_EXECUTION,
            "sentinel_reason": None,
            "lane_decision_evidence_ids": list(context.lane_decision_evidence_ids),
            "query_text": query_text,
            "query_hash": query_hash,
            "scope_filter": copy.deepcopy(dict(context.scope_filter)),
            "corpus_snapshot_hash": context.corpus_snapshot_hash,
            "index_versions": dict(context.index_versions),
            "result_ids": list(result_ids),
            "result_count": len(result_ids),
            "excluded_count": int(excluded_count),
            "stop_reason": stop_reason,
            "search_state": search_state.value,
            # Recall cannot be estimated without a labelled pool; asserting a
            # number here would dress an unknown up as a measurement.
            "recall_proxy": None,
            "errors": [],
            "started_at": context.started_at,
            "finished_at": context.finished_at,
        }
    )


def absent_lane_receipt(
    context: LaneContext,
    lane: str,
    *,
    sentinel_reason: str = SENTINEL_NOT_APPLICABLE,
) -> dict[str, Any]:
    """Seal the single UNSEARCHED sentinel a lane that never ran is entitled to.

    Every execution field is null. An unselected lane performs no backend call,
    and a sentinel that carried a result count of zero would be indistinguishable
    from a genuine `SEARCHED_NONE` — the exact confusion the receipt contract
    forbids.
    """
    if sentinel_reason not in SENTINEL_REASONS:
        raise LaneContractError(f"unknown sentinel reason: {sentinel_reason!r}")
    return _seal_receipt(
        {
            "receipt_id": _receipt_id(context, lane),
            "run_id": context.run_id,
            "query_plan_id": context.query_plan_id,
            "plan_hash": context.plan_hash,
            "lane": lane,
            "receipt_kind": RECEIPT_KIND_SENTINEL,
            "sentinel_reason": sentinel_reason,
            "lane_decision_evidence_ids": list(context.lane_decision_evidence_ids),
            "query_text": None,
            "query_hash": None,
            "scope_filter": None,
            "corpus_snapshot_hash": None,
            "index_versions": None,
            "result_ids": None,
            "result_count": None,
            "excluded_count": None,
            "stop_reason": None,
            "search_state": SearchState.UNSEARCHED.value,
            "recall_proxy": None,
            "errors": [],
            "started_at": None,
            "finished_at": None,
        }
    )


def absent_lane_result(
    context: LaneContext,
    lane: str,
    *,
    sentinel_reason: str = SENTINEL_NOT_APPLICABLE,
) -> LaneResult:
    """An explicitly unsearched lane, carrying the reason it was not run."""
    return LaneResult(
        lane=lane,
        search_state=SearchState.UNSEARCHED,
        candidates=(),
        receipt=absent_lane_receipt(context, lane, sentinel_reason=sentinel_reason),
        documents=(),
        duplicate_count=0,
        cutoff_count=0,
        diagnostics={
            "sentinel_reason": sentinel_reason,
            "absence_explanation": ABSENT_LANE_REASONS.get(
                lane, "this backend does not implement the lane"
            ),
        },
    )


def _lane_result(
    context: LaneContext,
    lane: str,
    queries: Sequence[str],
    channel_hits: Mapping[str, Sequence[Mapping[str, Any]]],
    documents: Sequence[Mapping[str, Any]],
    diagnostics: Mapping[str, Any],
) -> LaneResult:
    candidates, metadata = build_lane_candidates(context, lane, queries, channel_hits)
    state = (
        SearchState.SEARCHED_WITH_RESULTS if candidates else SearchState.SEARCHED_NONE
    )
    receipt = build_execution_receipt(
        context,
        lane,
        search_state=state,
        query_text=metadata["query_text"],
        query_hash=metadata["query_hash"],
        result_ids=[candidate["candidate_id"] for candidate in candidates],
        excluded_count=metadata["duplicate_count"] + metadata["cutoff_count"],
    )
    return LaneResult(
        lane=lane,
        search_state=state,
        candidates=tuple(candidates),
        receipt=receipt,
        documents=tuple(dict(document) for document in documents),
        duplicate_count=metadata["duplicate_count"],
        cutoff_count=metadata["cutoff_count"],
        diagnostics={
            **dict(diagnostics),
            **{
                "backend_request_hash": metadata["backend_request_hash"],
                "backend_response_hash": metadata["backend_response_hash"],
                "backend_receipt_id": metadata["backend_receipt_id"],
            },
        },
    )


def _span_id(document_id: str, start: int, end: int, quote: str) -> str:
    preimage = f"{document_id}:{start}:{end}:{hashlib.sha256(quote.encode('utf-8')).hexdigest()}"
    return "SPAN-" + hashlib.sha256(preimage.encode("utf-8")).hexdigest()[:32]


def lexical(
    db_path: Path,
    context: LaneContext,
    *,
    expression: str,
    limit: int | None = None,
    snippets_per_document: int = lexical_index.DEFAULT_SNIPPETS_PER_DOCUMENT,
) -> LaneResult:
    """Exact terms, identifiers, and phrases via SQLite FTS5 BM25.

    The lane is span-bearing: each candidate points at a re-extractable quote, so
    a downstream EvidenceNode can be grounded rather than asserted. A hit with no
    locatable span keeps a null ``source_span_id`` and is therefore metadata-only,
    which the contract excludes from direct evidence.
    """
    limit = context.max_candidates if limit is None else limit
    rows = lexical_index.query(
        db_path,
        expression,
        limit=limit,
        snippets_per_document=snippets_per_document,
    )
    hits: list[dict[str, Any]] = []
    for row in rows:
        snippets = row["snippets"]
        best = snippets[0] if snippets else None
        locator = row["source_path"]
        span_id = None
        if best is not None:
            locator = (
                f"{row['source_path']}#char={best['char_start']}-{best['char_end']}"
            )
            span_id = _span_id(
                row["document_id"], best["char_start"], best["char_end"], best["text"]
            )
        hits.append(
            {
                "canonical_source_key": row["document_id"],
                "source_record_id": row["document_id"],
                "source_locator": locator,
                "source_version": row["content_sha256"],
                "source_snapshot_hash": f"sha256:{row['content_sha256']}",
                "source_span_id": span_id,
                "raw_rank": row["rank"],
                "raw_score": row["bm25_score"],
                "matched_terms": row["matched_terms"],
                "matched_edges": [],
                "relation_direction": RELATION_DIRECTION_NONE,
                "retrieval_explanation": (
                    f"FTS5 BM25 rank {row['rank']} for the sealed lexical query; "
                    f"{len(snippets)} span(s) re-extract byte-exactly from the "
                    "indexed text. Retrieval rank is not evidence strength."
                ),
            }
        )
    return _lane_result(
        context,
        LANE_LEXICAL,
        [expression],
        {CHANNEL_LEXICAL: hits},
        rows,
        {
            "expression": expression,
            "limit": limit,
            "documents_returned": len(rows),
        },
    )


def citation(
    db_path: Path,
    context: LaneContext,
    *,
    seed_document_ids: Sequence[str] = (),
    citation_keys: Sequence[str] = (),
    limit: int | None = None,
) -> LaneResult:
    """Bibliographic coupling over author-year citation keys.

    Two documents citing the same work share a real edge in the corpus citation
    graph. Seeds are excluded from their own result set, and the shared keys are
    reported as ``matched_edges`` so the coupling is inspectable rather than a
    bare score.

    Seeds whose text uses numeric reference markers yield no extractable keys.
    That is reported as `SEARCHED_NONE` with the derived-key count in the
    diagnostics: the citation index was queried and returned nothing, which is
    different from not having looked.
    """
    limit = context.max_candidates if limit is None else limit
    seeds = sorted({str(item) for item in seed_document_ids})
    explicit_keys = sorted({str(item) for item in citation_keys})
    if not seeds and not explicit_keys:
        raise LaneContractError(
            "the citation lane needs at least one seed document or citation key"
        )
    derived = lexical_index.citation_keys_for(db_path, seeds) if seeds else {}
    all_keys = sorted(
        {key for keys in derived.values() for key in keys} | set(explicit_keys)
    )
    rows = (
        lexical_index.documents_sharing_citation_keys(
            db_path, all_keys, exclude=seeds, limit=limit
        )
        if all_keys
        else []
    )
    hits: list[dict[str, Any]] = []
    for row in rows:
        spans = row["citation_spans"]
        best = spans[0] if spans else None
        locator = row["source_path"]
        span_id = None
        if best is not None:
            locator = (
                f"{row['source_path']}#char={best['char_start']}-{best['char_end']}"
            )
            span_id = _span_id(
                row["document_id"],
                best["char_start"],
                best["char_end"],
                best["citation_key"],
            )
        hits.append(
            {
                "canonical_source_key": row["document_id"],
                "source_record_id": row["document_id"],
                "source_locator": locator,
                "source_version": row["content_sha256"],
                "source_snapshot_hash": f"sha256:{row['content_sha256']}",
                "source_span_id": span_id,
                "raw_rank": row["rank"],
                "raw_score": float(row["shared_key_count"]),
                "matched_terms": [],
                "matched_edges": [
                    f"BIBLIOGRAPHIC_COUPLING:{key}"
                    for key in row["shared_citation_keys"]
                ],
                "relation_direction": RELATION_DIRECTION_NONE,
                "retrieval_explanation": (
                    f"Shares {row['shared_key_count']} cited work(s) with the seed set; "
                    "bibliographic coupling is a citation-graph edge and not a claim "
                    "about agreement."
                ),
            }
        )
    return _lane_result(
        context,
        LANE_CITATION,
        [*seeds, *explicit_keys],
        {CHANNEL_CITATION_GRAPH: hits},
        rows,
        {
            "seed_document_ids": seeds,
            "derived_citation_key_count": len(all_keys),
            "seeds_without_citation_keys": sorted(
                seed for seed, keys in derived.items() if not keys
            ),
            "limit": limit,
        },
    )


def _cooccurrences(
    body: str,
    group_positions: Sequence[Mapping[str, list[tuple[int, int]]]],
    *,
    window_chars: int,
    max_pairs: int,
) -> list[dict[str, Any]]:
    """Windowed co-occurrence pairs between the first two term groups."""
    left, right = group_positions[0], group_positions[1]
    pairs: list[dict[str, Any]] = []
    for left_term in sorted(left):
        for left_start, left_end in left[left_term]:
            for right_term in sorted(right):
                for right_start, right_end in right[right_term]:
                    if abs(right_start - left_start) > window_chars:
                        continue
                    start = min(left_start, right_start)
                    end = max(left_end, right_end)
                    pairs.append(
                        {
                            "left_term": left_term,
                            "right_term": right_term,
                            "char_start": start,
                            "char_end": end,
                            "text": body[start:end],
                        }
                    )
    pairs.sort(
        key=lambda pair: (pair["char_start"], pair["char_end"], pair["left_term"])
    )
    return pairs[:max_pairs]


def entity_variable(
    db_path: Path,
    context: LaneContext,
    *,
    term_groups: Sequence[Sequence[str]],
    window_chars: int = DEFAULT_COOCCURRENCE_WINDOW,
    limit: int | None = None,
    candidate_pool: int | None = None,
    max_pairs_per_document: int = 4,
) -> LaneResult:
    """Shared entities and variables via windowed co-occurrence of term groups.

    FTS5 narrows the corpus to documents containing every group; the window check
    then requires the terms to appear near each other rather than merely in the
    same paper, which is the difference between a shared variable and a shared
    subject area.

    Co-occurrence is symmetric and carries no orientation, so candidates report
    ``relation_direction: UNRESOLVED``. Per the RetrievalCandidate contract,
    ``UNRESOLVED`` is not a direction match and must not be read as one.
    """
    groups = [
        tuple(str(term) for term in group if str(term).strip()) for group in term_groups
    ]
    groups = [group for group in groups if group]
    if len(groups) < 2:
        raise LaneContractError(
            "the entity_variable lane needs at least two term groups; a single group "
            "is a lexical query, not a co-occurrence"
        )
    limit = context.max_candidates if limit is None else limit
    pool = candidate_pool if candidate_pool is not None else max(limit * 4, limit)

    expression = " AND ".join(
        "(" + " OR ".join(f'"{term}"' for term in group) + ")" for group in groups
    )
    rows = lexical_index.query(db_path, expression, limit=pool, snippets_per_document=1)
    document_ids = [row["document_id"] for row in rows]
    bodies = lexical_index.fetch_documents(db_path, document_ids)

    scored: list[dict[str, Any]] = []
    for row in rows:
        record = bodies.get(row["document_id"])
        if record is None:
            continue
        body = record["body"]
        group_positions = [
            lexical_index.locate_term_positions(
                body,
                tuple(
                    QueryTerm(text=term, is_phrase=True, is_prefix=False)
                    for term in group
                ),
            )
            for group in groups
        ]
        if any(not positions for positions in group_positions):
            continue
        pairs = _cooccurrences(
            body,
            group_positions,
            window_chars=window_chars,
            max_pairs=max_pairs_per_document,
        )
        if not pairs:
            continue
        scored.append(
            {
                "document_id": row["document_id"],
                "source_path": record["source_path"],
                "content_sha256": record["content_sha256"],
                "char_count": record["char_count"],
                "cooccurrence_count": len(pairs),
                "bm25_score": row["bm25_score"],
                "matched_terms": sorted(
                    {term for positions in group_positions for term in positions}
                ),
                "cooccurrence_spans": pairs,
            }
        )
    scored.sort(
        key=lambda item: (
            -item["cooccurrence_count"],
            -item["bm25_score"],
            item["document_id"],
        )
    )
    scored = scored[:limit]
    for rank, row in enumerate(scored, start=1):
        row["rank"] = rank

    hits: list[dict[str, Any]] = []
    for row in scored:
        best = row["cooccurrence_spans"][0]
        hits.append(
            {
                "canonical_source_key": row["document_id"],
                "source_record_id": row["document_id"],
                "source_locator": (
                    f"{row['source_path']}#char={best['char_start']}-{best['char_end']}"
                ),
                "source_version": row["content_sha256"],
                "source_snapshot_hash": f"sha256:{row['content_sha256']}",
                "source_span_id": _span_id(
                    row["document_id"],
                    best["char_start"],
                    best["char_end"],
                    best["text"],
                ),
                "raw_rank": row["rank"],
                "raw_score": float(row["cooccurrence_count"]),
                "matched_terms": row["matched_terms"],
                "matched_edges": sorted(
                    {
                        f"COOCCURRENCE:{pair['left_term']}~{pair['right_term']}"
                        f"@{window_chars}"
                        for pair in row["cooccurrence_spans"]
                    }
                ),
                "relation_direction": RELATION_DIRECTION_UNRESOLVED,
                "retrieval_explanation": (
                    f"{row['cooccurrence_count']} windowed co-occurrence(s) within "
                    f"{window_chars} characters; proximity shows shared variables and "
                    "does not establish direction or mechanism."
                ),
            }
        )
    return _lane_result(
        context,
        LANE_ENTITY_VARIABLE,
        [expression],
        {CHANNEL_RELATION_GRAPH: hits},
        scored,
        {
            "expression": expression,
            "term_groups": [list(group) for group in groups],
            "window_chars": window_chars,
            "candidate_pool": pool,
            "documents_prefiltered": len(rows),
            "documents_with_cooccurrence": len(scored),
        },
    )


def fuse_lane_documents(
    results: Iterable[LaneResult],
    *,
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Fuse executed lanes into one document ranking with RRF ``k``.

    This is a cross-lane reading view, not a RetrievalCandidate: candidates stay
    bound to the lane that produced them. Each executed lane contributes exactly
    one channel ranking, already deduplicated lane-locally.
    """
    rankings: dict[str, list[str]] = {}
    for result in results:
        channel = result.channel
        if channel is None or result.search_state is SearchState.UNSEARCHED:
            continue
        rankings.setdefault(channel, []).extend(result.ranked_document_ids())
    fused = rrf_fuse(
        {channel: list(dict.fromkeys(ids)) for channel, ids in rankings.items()}, k=k
    )
    for row in fused:
        row["document_id"] = row.pop("key")
    return fused


def reconcile_lanes(
    context: LaneContext,
    results: Iterable[LaneResult],
    *,
    sentinel_reasons: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Reconcile all eleven canonical lanes in canonical order.

    Lanes not present in ``results`` are filled in as UNSEARCHED sentinels, so
    the reconciliation count is always eleven and a lane can never go missing
    quietly. The run ceiling follows the workflow: a release with no non-vector
    origin cannot exceed PARTIAL.
    """
    reasons = dict(sentinel_reasons or {})
    by_lane: dict[str, LaneResult] = {}
    for result in results:
        if result.lane not in CANONICAL_LANES:
            raise LaneContractError(f"{result.lane!r} is not a canonical lane")
        if result.lane in by_lane:
            raise LaneContractError(f"lane {result.lane!r} produced two receipts")
        by_lane[result.lane] = result

    ordered: list[LaneResult] = []
    for lane in CANONICAL_LANES:
        ordered.append(
            by_lane.get(lane)
            or absent_lane_result(
                context,
                lane,
                sentinel_reason=reasons.get(lane, SENTINEL_NOT_APPLICABLE),
            )
        )
    if len(ordered) != ALL_LANE_RECONCILIATION_COUNT:
        raise LaneContractError(
            f"reconciled {len(ordered)} lanes, contract requires "
            f"{ALL_LANE_RECONCILIATION_COUNT}"
        )

    lane_states = {result.lane: result.search_state for result in ordered}
    observed_channels = {
        channel
        for result in ordered
        for candidate in result.candidates
        for channel in candidate["retrieval_channels"]
    }
    # Canonical channel order, not alphabetical: the candidate contract requires
    # retrieval_channels to be reported in the canonical order.
    released_channels = [
        channel for channel in CHANNEL_ORDER if channel in observed_channels
    ]
    non_vector_origins = [
        channel
        for channel in released_channels
        if channel in NON_VECTOR_RELEASE_ORIGINS
    ]
    candidate_count = sum(len(result.candidates) for result in ordered)
    if candidate_count and not non_vector_origins:
        run_ceiling = VECTOR_ONLY_RUN_CEILING
    elif candidate_count:
        run_ceiling = RUN_CEILING_PASS
    else:
        run_ceiling = (
            RUN_CEILING_PASS
            if any(result.is_absence_of_evidence for result in ordered)
            else VECTOR_ONLY_RUN_CEILING
        )
    return {
        "all_lane_reconciliation_count": len(ordered),
        "lane_order": list(CANONICAL_LANES),
        "lane_states": {lane: state.value for lane, state in lane_states.items()},
        "coverage_summary": coverage_summary(lane_states),
        "receipts": [copy.deepcopy(result.receipt) for result in ordered],
        "executed_lanes": [
            result.lane
            for result in ordered
            if result.search_state is not SearchState.UNSEARCHED
        ],
        "unsearched_lanes": [
            result.lane
            for result in ordered
            if result.search_state is SearchState.UNSEARCHED
        ],
        "absence_of_evidence_lanes": [
            result.lane for result in ordered if result.is_absence_of_evidence
        ],
        "sentinel_reasons": {
            result.lane: str(result.diagnostics.get("sentinel_reason"))
            for result in ordered
            if result.search_state is SearchState.UNSEARCHED
        },
        "absence_explanations": {
            result.lane: str(result.diagnostics.get("absence_explanation"))
            for result in ordered
            if result.search_state is SearchState.UNSEARCHED
        },
        "released_channels": released_channels,
        "non_vector_release_origins": non_vector_origins,
        "candidate_count": candidate_count,
        "run_ceiling": run_ceiling,
    }


def assert_lane_coverage(
    reconciliation: Mapping[str, Any],
    *,
    applicable: Sequence[str],
) -> None:
    """Raise `LaneCoverageFailure` when an applicable lane was not covered.

    Delegates to `search_state.require_lane_coverage`, which treats UNSEARCHED
    and failed lanes as gaps rather than as absence.
    """
    require_lane_coverage(reconciliation["lane_states"], applicable=applicable)


def open_index_stats(db_path: Path) -> dict[str, Any]:
    """Read an existing index's stats, or fail closed with a typed error."""
    try:
        return lexical_index.read_index_stats(db_path)
    except (sqlite3.DatabaseError, LexicalIndexError) as error:
        raise LexicalIndexError(str(error)) from error


__all__ = [
    "ABSENT_LANES",
    "ABSENT_LANE_REASONS",
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "ALL_LANE_RECONCILIATION_COUNT",
    "BACKEND_ID",
    "BACKEND_VERSION",
    "CANONICAL_LANES",
    "CHANNEL_ORDER",
    "EXECUTED_LANES",
    "LANE_CHANNEL",
    "NON_VECTOR_RELEASE_ORIGINS",
    "RRF_K",
    "VECTOR_ONLY_RUN_CEILING",
    "LaneContext",
    "LaneContractError",
    "LaneResult",
    "absent_lane_receipt",
    "absent_lane_result",
    "assert_lane_coverage",
    "build_execution_receipt",
    "build_lane_candidates",
    "canonical_json",
    LANE_CITATION,
    "deduplicate_exact",
    "empty_scope_vector",
    LANE_ENTITY_VARIABLE,
    "fuse_lane_documents",
    LANE_LEXICAL,
    "open_index_stats",
    "reconcile_lanes",
    "rrf_fuse",
    "sha256_bytes",
]
