"""O02 provider-neutral retrieval, integrity, fusion, and release contracts.

All routing, hashing, deduplication, rank fusion, and terminal-state decisions
in this module are deterministic.  Backend payloads are untrusted until their
sealed request, response hash, snapshot, index, adapter, rank, provenance, and
receipt bindings have all been checked.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final


SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
CANDIDATE_ID_PATTERN: Final = re.compile(r"^RC-[0-9a-f]{64}$")


class QueryFamily(str, Enum):
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"
    NULL = "NULL"
    BOUNDARY = "BOUNDARY"
    METHOD = "METHOD"
    NOVELTY = "NOVELTY"


class RetrievalChannel(str, Enum):
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"
    CITATION_GRAPH = "CITATION_GRAPH"
    RELATION_GRAPH = "RELATION_GRAPH"
    EXTERNAL_INDEX = "EXTERNAL_INDEX"


class RelationDirection(str, Enum):
    SAME_DIRECTION = "SAME_DIRECTION"
    REVERSE_DIRECTION = "REVERSE_DIRECTION"
    INVERSE_PREDICATE = "INVERSE_PREDICATE"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    NO_DIRECTION = "NO_DIRECTION"
    UNRESOLVED = "UNRESOLVED"


QUERY_FAMILY_ORDER: Final = tuple(value.value for value in QueryFamily)
CHANNEL_ORDER: Final = tuple(value.value for value in RetrievalChannel)
_FAMILY_RANK: Final = {value: index for index, value in enumerate(QUERY_FAMILY_ORDER)}
_CHANNEL_RANK: Final = {value: index for index, value in enumerate(CHANNEL_ORDER)}

LANE_QUERY_FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "lexical": (QueryFamily.FORWARD.value,),
    "semantic": (QueryFamily.FORWARD.value,),
    "citation": (QueryFamily.FORWARD.value,),
    "entity_variable": (QueryFamily.FORWARD.value,),
    "mechanism": (QueryFamily.FORWARD.value,),
    "counterevidence": (QueryFamily.FORWARD.value, QueryFamily.REVERSE.value),
    "null": (QueryFamily.NULL.value,),
    "boundary": (QueryFamily.BOUNDARY.value,),
    "method": (QueryFamily.METHOD.value,),
    "temporal": (QueryFamily.FORWARD.value,),
    "external_novelty": (QueryFamily.NOVELTY.value,),
}

NON_VECTOR_CHANNELS: Final = frozenset(
    {
        RetrievalChannel.LEXICAL.value,
        RetrievalChannel.CITATION_GRAPH.value,
        RetrievalChannel.RELATION_GRAPH.value,
        RetrievalChannel.EXTERNAL_INDEX.value,
    }
)

PROVIDER_REQUEST_FIELDS: Final = (
    "run_id",
    "query_plan_id",
    "plan_hash",
    "lane",
    "query_families",
    "query_batch",
    "query_hash",
    "scope_filter",
    "corpus_snapshot_hash",
    "index_versions",
    "max_candidates",
    "cutoff_policy_id",
    "deterministic_seed",
    "policy_bundle_hash",
    "capability_lease_id",
    "backend_id",
    "backend_version",
    "adapter_id",
    "adapter_version",
)

BACKEND_RESPONSE_FIELDS: Final = (
    "request_hash",
    "plan_hash",
    "query_hash",
    "corpus_snapshot_hash",
    "index_versions",
    "backend_id",
    "backend_version",
    "adapter_id",
    "adapter_version",
    "backend_receipt_id",
    "executed_query_families",
    "status",
    "complete",
    "interrupted",
    "error_code",
    "hits",
    "response_hash",
)

RAW_HIT_FIELDS: Final = (
    "query_family",
    "retrieval_channel",
    "raw_rank",
    "raw_score",
    "canonical_source_key",
    "source_record_id",
    "source_artifact_id",
    "source_locator",
    "source_version",
    "source_snapshot_hash",
    "source_span_id",
    "ranking_features",
    "matched_terms",
    "matched_edges",
    "relation_direction",
    "scope_estimate",
)

RANKING_FEATURE_FIELDS: Final = (
    "scope_overlap",
    "relation_direction_match",
    "source_directness",
    "method_compatibility",
    "publication_version_status",
    "extraction_grounding_confidence",
)

CANDIDATE_IDENTITY_FIELDS: Final = (
    "plan_hash",
    "lane",
    "query_hash",
    "canonical_source_key",
    "source_version",
    "source_snapshot_hash",
)

CANDIDATE_HASH_FIELDS: Final = (
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

CANDIDATE_FIELDS: Final = ("candidate_id", *CANDIDATE_HASH_FIELDS, "candidate_hash")


class RetrievalContractError(ValueError):
    """Typed fail-closed O02 contract violation."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        terminal_state: str = "FAILED",
        stop_reason: str = "invalid_response",
    ) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.terminal_state = terminal_state
        self.stop_reason = stop_reason


@dataclass(frozen=True)
class SealedBackendRequest:
    """Immutable-by-copy request projection plus its content hash."""

    _payload: dict[str, Any]
    canonical_bytes: bytes
    request_hash: str
    query_text: str

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)


@dataclass(frozen=True)
class TerminalOutcome:
    search_state: str
    stop_reason: str
    error_code: str | None


@dataclass(frozen=True)
class ValidatedBackendResponse:
    _payload: dict[str, Any]
    response_hash: str
    outcome: TerminalOutcome

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)


@dataclass(frozen=True)
class CandidateSetResult:
    candidates: tuple[dict[str, Any], ...]
    outcome: TerminalOutcome
    raw_hit_count: int
    duplicate_count: int
    cutoff_count: int
    excluded_count: int
    run_ceiling: str

    def candidate_payloads(self) -> list[dict[str, Any]]:
        return copy.deepcopy(list(self.candidates))


@dataclass(frozen=True)
class ReleaseGuardResult:
    allowed: bool
    run_ceiling: str
    reason: str
    vector_only_candidate_ids: tuple[str, ...]
    metadata_only_candidate_ids: tuple[str, ...]
    direct_evidence_candidate_ids: tuple[str, ...]
    silent_fallback_count: int


def canonical_json(value: Any) -> bytes:
    """Return the repository's RFC-8785-equivalent deterministic UTF-8 form."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RetrievalContractError("CANONICAL_JSON_INVALID", str(exc)) from exc


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_object(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RetrievalContractError("TYPE_MISMATCH", f"{label} must be an object")
    return copy.deepcopy(dict(value))


def _exact_fields(value: Mapping[str, Any], fields: Sequence[str], label: str) -> None:
    expected = set(fields)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RetrievalContractError(
            "FIELD_SET_MISMATCH",
            f"{label} missing={missing} extra={extra}",
        )


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RetrievalContractError("FIELD_INVALID", f"{field} must be a non-empty string")
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise RetrievalContractError("HASH_FORMAT_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return value


def _string_map(value: Any, field: str) -> dict[str, str]:
    result = _mapping(value, field)
    if not result:
        raise RetrievalContractError("FIELD_INVALID", f"{field} must not be empty")
    for key, item in result.items():
        _nonempty_string(key, f"{field} key")
        _nonempty_string(item, f"{field}.{key}")
    return dict(sorted(result.items()))


def _ordered_unique_strings(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RetrievalContractError("FIELD_INVALID", f"{field} must be an array")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        text = _nonempty_string(item, f"{field}[{index}]")
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    if not allow_empty and not result:
        raise RetrievalContractError("FIELD_INVALID", f"{field} must not be empty")
    return result


def _validate_query_batch(
    batch_value: Any,
    lane: str,
    query_families: Sequence[str],
) -> dict[str, Any]:
    batch = _mapping(batch_value, "query_batch")
    _exact_fields(batch, ("lane", "families"), "query_batch")
    if batch["lane"] != lane:
        raise RetrievalContractError(
            "INVALID_QUERY_FAMILY_BINDING", "query_batch lane does not match request lane"
        )
    families_value = batch["families"]
    if isinstance(families_value, (str, bytes)) or not isinstance(families_value, Sequence):
        raise RetrievalContractError("INVALID_QUERY_FAMILY_BINDING", "query_batch.families must be an array")
    normalized: list[dict[str, Any]] = []
    for index, row_value in enumerate(families_value):
        row = _mapping(row_value, f"query_batch.families[{index}]")
        _exact_fields(row, ("family", "queries"), f"query_batch.families[{index}]")
        family = _nonempty_string(row["family"], f"query_batch.families[{index}].family")
        if family not in QUERY_FAMILY_ORDER:
            raise RetrievalContractError("QUERY_FAMILY_UNKNOWN", family)
        normalized.append(
            {
                "family": family,
                "queries": _ordered_unique_strings(
                    row["queries"], f"query_batch.families[{index}].queries", allow_empty=False
                ),
            }
        )
    normalized.sort(key=lambda row: _FAMILY_RANK[row["family"]])
    observed = [row["family"] for row in normalized]
    if len(observed) != len(set(observed)) or observed != list(query_families):
        raise RetrievalContractError(
            "INVALID_QUERY_FAMILY_BINDING",
            f"query_batch families {observed!r} do not match sealed families {list(query_families)!r}",
        )
    return {"families": normalized, "lane": lane}


def _validate_lane_specific_scope(lane: str, scope_filter: Mapping[str, Any]) -> None:
    extensions_value = scope_filter.get("domain_extensions")
    extensions = dict(extensions_value) if isinstance(extensions_value, Mapping) else {}
    if lane == "temporal":
        time_period = scope_filter.get("time_period")
        version = extensions.get("date_filter_version")
        correction_filter = extensions.get("correction_filter")
        if not isinstance(time_period, str) or not time_period.strip() or not isinstance(version, str) or not version.strip():
            raise RetrievalContractError(
                "TEMPORAL_FILTER_REQUIRED",
                "temporal requests require time_period and domain_extensions.date_filter_version",
            )
        if correction_filter in (None, ""):
            raise RetrievalContractError(
                "TEMPORAL_FILTER_REQUIRED",
                "temporal requests require domain_extensions.correction_filter",
            )
    if lane == "external_novelty":
        if not isinstance(extensions.get("external_scope"), str) or not extensions["external_scope"].strip():
            raise RetrievalContractError(
                "EXTERNAL_NOVELTY_SCOPE_REQUIRED",
                "external_novelty requires domain_extensions.external_scope",
            )
        if not isinstance(extensions.get("stop_rule"), str) or not extensions["stop_rule"].strip():
            raise RetrievalContractError(
                "EXTERNAL_NOVELTY_STOP_RULE_REQUIRED",
                "external_novelty requires domain_extensions.stop_rule",
            )


def seal_backend_request(value: Mapping[str, Any]) -> SealedBackendRequest:
    """Validate and seal the exact provider-neutral O02 backend request."""

    payload = _mapping(value, "backend request")
    _exact_fields(payload, PROVIDER_REQUEST_FIELDS, "backend request")
    for field in (
        "run_id",
        "query_plan_id",
        "cutoff_policy_id",
        "capability_lease_id",
        "backend_id",
        "backend_version",
        "adapter_id",
        "adapter_version",
    ):
        _nonempty_string(payload[field], field)
    for field in ("plan_hash", "query_hash", "corpus_snapshot_hash", "policy_bundle_hash"):
        _sha256(payload[field], field)
    lane = _nonempty_string(payload["lane"], "lane")
    if lane not in LANE_QUERY_FAMILIES:
        raise RetrievalContractError("LANE_UNKNOWN", lane)
    families = _ordered_unique_strings(payload["query_families"], "query_families", allow_empty=False)
    for family in families:
        if family not in QUERY_FAMILY_ORDER:
            raise RetrievalContractError("QUERY_FAMILY_UNKNOWN", family)
    families.sort(key=_FAMILY_RANK.__getitem__)
    required = list(LANE_QUERY_FAMILIES[lane])
    if families != required:
        raise RetrievalContractError(
            "INVALID_QUERY_FAMILY_BINDING",
            f"lane {lane!r} requires {required!r}, received {families!r}",
        )
    payload["query_families"] = families
    payload["query_batch"] = _validate_query_batch(payload["query_batch"], lane, families)
    query_text = canonical_json(payload["query_batch"]).decode("utf-8")
    expected_query_hash = sha256_bytes(query_text.encode("utf-8"))
    if payload["query_hash"] != expected_query_hash:
        raise RetrievalContractError("QUERY_HASH_MISMATCH", "query_hash does not bind canonical query_batch")
    scope_filter = _mapping(payload["scope_filter"], "scope_filter")
    _validate_lane_specific_scope(lane, scope_filter)
    payload["scope_filter"] = scope_filter
    payload["index_versions"] = _string_map(payload["index_versions"], "index_versions")
    if not isinstance(payload["max_candidates"], int) or isinstance(payload["max_candidates"], bool) or payload["max_candidates"] < 1:
        raise RetrievalContractError("FIELD_INVALID", "max_candidates must be a positive integer")
    if not isinstance(payload["deterministic_seed"], int) or isinstance(payload["deterministic_seed"], bool):
        raise RetrievalContractError("FIELD_INVALID", "deterministic_seed must be an integer")
    canonical_bytes = canonical_json(payload)
    return SealedBackendRequest(
        _payload=payload,
        canonical_bytes=canonical_bytes,
        request_hash=sha256_bytes(canonical_bytes),
        query_text=query_text,
    )


def _response_preimage(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "response_hash"}


def seal_backend_response(
    request: SealedBackendRequest,
    response_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind adapter observations to a sealed request and add the response hash.

    This is the adapter-side sealing step.  Callers must still pass its output
    through :func:`validate_backend_response` before using any hit.
    """

    values = _mapping(response_values, "backend response values")
    expected_values = {
        "backend_receipt_id",
        "executed_query_families",
        "status",
        "complete",
        "interrupted",
        "error_code",
        "hits",
    }
    if set(values) != expected_values:
        raise RetrievalContractError(
            "FIELD_SET_MISMATCH",
            f"backend response values missing={sorted(expected_values - set(values))} extra={sorted(set(values) - expected_values)}",
        )
    request_payload = request.payload
    payload = {
        "request_hash": request.request_hash,
        "plan_hash": request_payload["plan_hash"],
        "query_hash": request_payload["query_hash"],
        "corpus_snapshot_hash": request_payload["corpus_snapshot_hash"],
        "index_versions": request_payload["index_versions"],
        "backend_id": request_payload["backend_id"],
        "backend_version": request_payload["backend_version"],
        "adapter_id": request_payload["adapter_id"],
        "adapter_version": request_payload["adapter_version"],
        **values,
    }
    payload["response_hash"] = _sha256_object(_response_preimage(payload))
    return payload


def _terminal_outcome(payload: Mapping[str, Any]) -> TerminalOutcome:
    status = payload["status"]
    hits = payload["hits"]
    complete = payload["complete"]
    interrupted = payload["interrupted"]
    error_code = payload["error_code"]
    if status == "OK":
        if complete is not True or interrupted is not False or error_code is not None:
            raise RetrievalContractError("RESPONSE_STATE_INVALID", "OK must be complete, uninterrupted, and error-free")
        return TerminalOutcome("SEARCHED_WITH_RESULTS" if hits else "SEARCHED_NONE", "complete", None)
    if status == "PARTIAL":
        if complete is not False or interrupted is not True:
            raise RetrievalContractError("RESPONSE_STATE_INVALID", "PARTIAL must be incomplete and interrupted")
        return TerminalOutcome("PARTIAL", "bounded_interruption", _nonempty_string(error_code, "error_code"))
    blocked = {
        "POLICY_DENIED": "policy_blocked",
        "CREDENTIAL_UNAVAILABLE": "credential_unavailable",
        "BACKEND_UNAVAILABLE": "backend_unavailable",
    }
    if status in blocked:
        if complete is not False or interrupted is not False or hits:
            raise RetrievalContractError("RESPONSE_STATE_INVALID", f"{status} cannot carry results")
        return TerminalOutcome("BLOCKED", blocked[status], _nonempty_string(error_code, "error_code"))
    if status == "PROVIDER_ERROR":
        if complete is not False or interrupted is not False or hits:
            raise RetrievalContractError("RESPONSE_STATE_INVALID", "PROVIDER_ERROR cannot carry results")
        return TerminalOutcome("FAILED", "provider_failure", _nonempty_string(error_code, "error_code"))
    raise RetrievalContractError("BACKEND_STATUS_UNKNOWN", str(status))


def _validate_feature_map(value: Any) -> dict[str, float | None]:
    result = _mapping(value, "ranking_features")
    _exact_fields(result, RANKING_FEATURE_FIELDS, "ranking_features")
    for field, item in result.items():
        if item is None:
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise RetrievalContractError("RANKING_FEATURE_INVALID", field)
        if not 0 <= float(item) <= 1:
            raise RetrievalContractError("RANKING_FEATURE_INVALID", field)
        result[field] = float(item)
    return result


def _validate_hit(value: Any, request: SealedBackendRequest) -> dict[str, Any]:
    hit = _mapping(value, "backend hit")
    _exact_fields(hit, RAW_HIT_FIELDS, "backend hit")
    family = _nonempty_string(hit["query_family"], "query_family")
    if family not in request.payload["query_families"]:
        raise RetrievalContractError("INVALID_QUERY_FAMILY_BINDING", f"hit family {family!r} was not requested")
    channel = _nonempty_string(hit["retrieval_channel"], "retrieval_channel")
    if channel not in CHANNEL_ORDER:
        raise RetrievalContractError("RETRIEVAL_CHANNEL_UNKNOWN", channel)
    rank = hit["raw_rank"]
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
        raise RetrievalContractError("RAW_RANK_INVALID", repr(rank))
    score = hit["raw_score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
        raise RetrievalContractError("RAW_SCORE_INVALID", repr(score))
    hit["raw_score"] = float(score)
    for field in ("canonical_source_key", "source_record_id", "source_locator", "source_version"):
        _nonempty_string(hit[field], field)
    if hit["source_artifact_id"] is not None:
        _nonempty_string(hit["source_artifact_id"], "source_artifact_id")
    if hit["source_span_id"] is not None:
        _nonempty_string(hit["source_span_id"], "source_span_id")
    _sha256(hit["source_snapshot_hash"], "source_snapshot_hash")
    hit["ranking_features"] = _validate_feature_map(hit["ranking_features"])
    hit["matched_terms"] = sorted(_ordered_unique_strings(hit["matched_terms"], "matched_terms"))
    hit["matched_edges"] = sorted(_ordered_unique_strings(hit["matched_edges"], "matched_edges"))
    direction = _nonempty_string(hit["relation_direction"], "relation_direction")
    if direction not in {item.value for item in RelationDirection}:
        raise RetrievalContractError("RELATION_DIRECTION_UNKNOWN", direction)
    if hit["scope_estimate"] is not None:
        hit["scope_estimate"] = _mapping(hit["scope_estimate"], "scope_estimate")
    return hit


def _integrity_failure(code: str, detail: str) -> RetrievalContractError:
    return RetrievalContractError(code, detail, terminal_state="FAILED", stop_reason="integrity_failure")


def validate_backend_response(
    request: SealedBackendRequest,
    response_value: Mapping[str, Any],
) -> ValidatedBackendResponse:
    """Validate all bindings of an untrusted backend response."""

    payload = _mapping(response_value, "backend response")
    _exact_fields(payload, BACKEND_RESPONSE_FIELDS, "backend response")
    expected_hash = _sha256_object(_response_preimage(payload))
    if payload["response_hash"] != expected_hash:
        raise _integrity_failure("BACKEND_RESPONSE_HASH_MISMATCH", "response content changed after sealing")
    request_payload = request.payload
    bindings = {
        "request_hash": request.request_hash,
        "plan_hash": request_payload["plan_hash"],
        "query_hash": request_payload["query_hash"],
        "corpus_snapshot_hash": request_payload["corpus_snapshot_hash"],
        "index_versions": request_payload["index_versions"],
        "backend_id": request_payload["backend_id"],
        "backend_version": request_payload["backend_version"],
        "adapter_id": request_payload["adapter_id"],
        "adapter_version": request_payload["adapter_version"],
    }
    for field, expected in bindings.items():
        if payload[field] != expected:
            code = "STALE_RETRIEVAL_SNAPSHOT" if field in {"corpus_snapshot_hash", "index_versions"} else "RESPONSE_BINDING_MISMATCH"
            raise _integrity_failure(code, f"{field} does not match sealed request")
    _sha256(payload["response_hash"], "response_hash")
    _nonempty_string(payload["backend_receipt_id"], "backend_receipt_id")
    executed_families = _ordered_unique_strings(
        payload["executed_query_families"],
        "executed_query_families",
        allow_empty=True,
    )
    for family in executed_families:
        if family not in QUERY_FAMILY_ORDER:
            raise RetrievalContractError("QUERY_FAMILY_UNKNOWN", family)
    executed_families.sort(key=_FAMILY_RANK.__getitem__)
    payload["executed_query_families"] = executed_families
    if payload["status"] in {"OK", "PARTIAL"}:
        requested_families = request_payload["query_families"]
        if payload["status"] == "OK" and executed_families != requested_families:
            raise RetrievalContractError(
                "INCOMPLETE_QUERY_FAMILY_EXECUTION",
                f"complete response executed {executed_families!r}, expected {requested_families!r}",
            )
        if any(family not in requested_families for family in executed_families):
            raise RetrievalContractError(
                "UNPLANNED_QUERY_FAMILY_EXECUTION",
                repr(executed_families),
            )
    elif executed_families:
        raise RetrievalContractError(
            "UNPLANNED_QUERY_FAMILY_EXECUTION",
            "blocked or failed response cannot claim an executed family",
        )
    if not isinstance(payload["complete"], bool) or not isinstance(payload["interrupted"], bool):
        raise RetrievalContractError("RESPONSE_STATE_INVALID", "complete and interrupted must be booleans")
    if not isinstance(payload["hits"], list):
        raise RetrievalContractError("INVALID_RESPONSE", "hits must be an array")
    payload["hits"] = [_validate_hit(hit, request) for hit in payload["hits"]]
    outcome = _terminal_outcome(payload)
    return ValidatedBackendResponse(_payload=payload, response_hash=expected_hash, outcome=outcome)


def compute_candidate_id(candidate: Mapping[str, Any]) -> str:
    preimage = {field: copy.deepcopy(candidate[field]) for field in CANDIDATE_IDENTITY_FIELDS}
    return "RC-" + hashlib.sha256(canonical_json(preimage)).hexdigest()


def compute_candidate_hash(candidate: Mapping[str, Any]) -> str:
    preimage = {field: copy.deepcopy(candidate[field]) for field in CANDIDATE_HASH_FIELDS}
    return _sha256_object(preimage)


def _observed_channel_maps(
    observations: Sequence[dict[str, Any]],
) -> tuple[list[str], dict[str, float | None], dict[str, int | None]]:
    by_channel: dict[str, dict[str, Any]] = {}
    for observation in observations:
        channel = observation["retrieval_channel"]
        current = by_channel.get(channel)
        key = (observation["raw_rank"], observation["canonical_source_key"])
        if current is None or key < (current["raw_rank"], current["canonical_source_key"]):
            by_channel[channel] = observation
    channels = sorted(by_channel, key=_CHANNEL_RANK.__getitem__)
    scores: dict[str, float | None] = {channel: None for channel in CHANNEL_ORDER}
    ranks: dict[str, int | None] = {channel: None for channel in CHANNEL_ORDER}
    for channel in channels:
        scores[channel] = by_channel[channel]["raw_score"]
        ranks[channel] = by_channel[channel]["stable_channel_rank"]
    return channels, scores, ranks


def _validate_group_provenance(observations: Sequence[dict[str, Any]]) -> None:
    fields = (
        "source_record_id",
        "source_artifact_id",
        "source_locator",
        "source_version",
        "source_snapshot_hash",
        "source_span_id",
    )
    for field in fields:
        if len({json.dumps(item[field], sort_keys=True) for item in observations}) != 1:
            raise _integrity_failure(
                "DUPLICATE_PROVENANCE_CONFLICT", f"duplicate observations disagree on {field}"
            )


def _candidate_from_observations(
    request: SealedBackendRequest,
    response: ValidatedBackendResponse,
    observations: Sequence[dict[str, Any]],
    duplicate_count: int,
) -> dict[str, Any]:
    _validate_group_provenance(observations)
    request_payload = request.payload
    response_payload = response.payload
    primary = min(
        observations,
        key=lambda item: (
            _FAMILY_RANK[item["query_family"]],
            item["raw_rank"],
            _CHANNEL_RANK[item["retrieval_channel"]],
        ),
    )
    channels, raw_scores, channel_ranks = _observed_channel_maps(observations)
    fusion_score = None
    fusion_method = "SINGLE_CHANNEL"
    if len(channels) > 1:
        fusion_method = "RRF_K60"
        fusion_score = sum(1.0 / (60 + int(channel_ranks[channel])) for channel in channels)
    candidate: dict[str, Any] = {
        "run_id": request_payload["run_id"],
        "query_plan_id": request_payload["query_plan_id"],
        "plan_hash": request_payload["plan_hash"],
        "lane": request_payload["lane"],
        "query_family": primary["query_family"],
        "query_text": request.query_text,
        "query_hash": request_payload["query_hash"],
        "scope_filter": request_payload["scope_filter"],
        "corpus_snapshot_hash": request_payload["corpus_snapshot_hash"],
        "index_versions": request_payload["index_versions"],
        "backend_id": request_payload["backend_id"],
        "backend_version": request_payload["backend_version"],
        "backend_adapter_id": request_payload["adapter_id"],
        "backend_adapter_version": request_payload["adapter_version"],
        "backend_request_hash": request.request_hash,
        "backend_response_hash": response.response_hash,
        "backend_receipt_id": response_payload["backend_receipt_id"],
        "canonical_source_key": primary["canonical_source_key"],
        "source_record_id": primary["source_record_id"],
        "source_artifact_id": primary["source_artifact_id"],
        "source_locator": primary["source_locator"],
        "source_version": primary["source_version"],
        "source_snapshot_hash": primary["source_snapshot_hash"],
        "source_span_id": primary["source_span_id"],
        "raw_rank": min(int(item["raw_rank"]) for item in observations),
        "raw_scores": raw_scores,
        "channel_ranks": channel_ranks,
        "retrieval_channels": channels,
        "fusion_method": fusion_method,
        "fusion_score": fusion_score,
        "ranking_features": copy.deepcopy(primary["ranking_features"]),
        "matched_terms": sorted({term for item in observations for term in item["matched_terms"]}),
        "matched_edges": sorted({edge for item in observations for edge in item["matched_edges"]}),
        "relation_direction": primary["relation_direction"],
        "scope_estimate": copy.deepcopy(primary["scope_estimate"]),
        "duplicate_candidate_ids": [],
        "multi_channel_verified": len(channels) > 1,
        "retrieval_explanation": (
            f"Validated {len(observations)} observation(s) from {', '.join(channels)}; "
            "ranking is retrieval priority and not scientific evidence strength."
        ),
    }
    candidate["candidate_id"] = compute_candidate_id(candidate)
    if duplicate_count:
        # Identity-equal duplicates necessarily have the same canonical ID.  A
        # single self-ID preserves that duplicate lineage without fabrication.
        candidate["duplicate_candidate_ids"] = [candidate["candidate_id"]]
    candidate["candidate_hash"] = compute_candidate_hash(candidate)
    validate_retrieval_candidate(candidate)
    return candidate


def validate_retrieval_candidate(candidate_value: Mapping[str, Any]) -> None:
    candidate = _mapping(candidate_value, "RetrievalCandidate")
    _exact_fields(candidate, CANDIDATE_FIELDS, "RetrievalCandidate")
    if not CANDIDATE_ID_PATTERN.fullmatch(str(candidate["candidate_id"])):
        raise RetrievalContractError("CANDIDATE_ID_FORMAT_INVALID", str(candidate["candidate_id"]))
    if candidate["candidate_id"] != compute_candidate_id(candidate):
        raise _integrity_failure("CANDIDATE_ID_MISMATCH", "candidate identity preimage does not match ID")
    _sha256(candidate["candidate_hash"], "candidate_hash")
    if candidate["candidate_hash"] != compute_candidate_hash(candidate):
        raise _integrity_failure("CANDIDATE_HASH_MISMATCH", "candidate content changed after sealing")
    if sha256_bytes(str(candidate["query_text"]).encode("utf-8")) != candidate["query_hash"]:
        raise _integrity_failure("QUERY_HASH_MISMATCH", "candidate query_text is not query_hash-bound")
    lane = candidate["lane"]
    family = candidate["query_family"]
    if lane not in LANE_QUERY_FAMILIES or family not in LANE_QUERY_FAMILIES[lane]:
        raise RetrievalContractError("INVALID_QUERY_FAMILY_BINDING", f"{lane}/{family}")
    channels = candidate["retrieval_channels"]
    if not isinstance(channels, list) or not channels or channels != sorted(set(channels), key=_CHANNEL_RANK.__getitem__):
        raise RetrievalContractError("CHANNEL_ORDER_INVALID", repr(channels))
    for channel in CHANNEL_ORDER:
        observed = channel in channels
        score = candidate["raw_scores"].get(channel)
        rank = candidate["channel_ranks"].get(channel)
        if observed != (score is not None and rank is not None):
            raise RetrievalContractError("CHANNEL_OBSERVATION_MISMATCH", channel)
    if len(channels) == 1:
        if candidate["fusion_method"] != "SINGLE_CHANNEL" or candidate["fusion_score"] is not None or candidate["multi_channel_verified"] is not False:
            raise RetrievalContractError("FUSION_CONTRACT_VIOLATION", "single-channel candidate has fused fields")
    else:
        expected = sum(1.0 / (60 + candidate["channel_ranks"][channel]) for channel in channels)
        if candidate["fusion_method"] != "RRF_K60" or candidate["multi_channel_verified"] is not True:
            raise RetrievalContractError("FUSION_CONTRACT_VIOLATION", "multi-channel candidate is not RRF_K60")
        score = candidate["fusion_score"]
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isclose(float(score), expected, rel_tol=0, abs_tol=1e-15):
            raise RetrievalContractError("RRF_SCORE_MISMATCH", repr(score))
    _validate_feature_map(candidate["ranking_features"])
    if candidate["relation_direction"] not in {value.value for value in RelationDirection}:
        raise RetrievalContractError("RELATION_DIRECTION_UNKNOWN", str(candidate["relation_direction"]))
    duplicate_ids = candidate["duplicate_candidate_ids"]
    if not isinstance(duplicate_ids, list) or len(duplicate_ids) != len(set(duplicate_ids)):
        raise RetrievalContractError("DUPLICATE_LINEAGE_INVALID", repr(duplicate_ids))
    for duplicate_id in duplicate_ids:
        if not CANDIDATE_ID_PATTERN.fullmatch(str(duplicate_id)):
            raise RetrievalContractError("DUPLICATE_LINEAGE_INVALID", str(duplicate_id))


def _deduplicate_and_rank_hits(
    hits: Sequence[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    int,
    dict[tuple[str, str, str, str], int],
]:
    by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        by_channel[hit["retrieval_channel"]].append(copy.deepcopy(hit))
    collapsed: list[dict[str, Any]] = []
    duplicate_count = 0
    duplicates_by_identity: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for channel in sorted(by_channel, key=_CHANNEL_RANK.__getitem__):
        ordered = sorted(
            by_channel[channel],
            key=lambda hit: (hit["raw_rank"], hit["canonical_source_key"]),
        )
        seen: set[tuple[str, str, str, str]] = set()
        channel_unique: list[dict[str, Any]] = []
        for hit in ordered:
            identity = (
                hit["canonical_source_key"],
                hit["source_version"],
                hit["source_snapshot_hash"],
                hit["source_locator"],
            )
            if identity in seen:
                duplicate_count += 1
                duplicates_by_identity[identity] += 1
                continue
            seen.add(identity)
            channel_unique.append(hit)
        for stable_rank, hit in enumerate(channel_unique, start=1):
            hit["stable_channel_rank"] = stable_rank
            collapsed.append(hit)
    return collapsed, duplicate_count, dict(duplicates_by_identity)


def build_candidate_set(
    request: SealedBackendRequest,
    response_value: Mapping[str, Any],
) -> CandidateSetResult:
    """Validate, deduplicate, fuse, cut off, and seal one lane candidate set."""

    response = validate_backend_response(request, response_value)
    if response.outcome.search_state in {"BLOCKED", "FAILED"}:
        return CandidateSetResult((), response.outcome, 0, 0, 0, 0, "PARTIAL")
    hits = response.payload["hits"]
    if not hits:
        ceiling = "PASS" if response.outcome.search_state == "SEARCHED_NONE" else "PARTIAL"
        return CandidateSetResult((), response.outcome, 0, 0, 0, 0, ceiling)
    collapsed, duplicate_count, duplicates_by_identity = _deduplicate_and_rank_hits(hits)
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for hit in collapsed:
        identity = (
            hit["canonical_source_key"],
            hit["source_version"],
            hit["source_snapshot_hash"],
            hit["source_locator"],
        )
        grouped[identity].append(hit)
    candidates: list[dict[str, Any]] = []
    for identity in sorted(grouped):
        observations = grouped[identity]
        candidates.append(
            _candidate_from_observations(
                request,
                response,
                observations,
                duplicate_count=duplicates_by_identity.get(identity, 0),
            )
        )

    def ranking_score(candidate: Mapping[str, Any]) -> float:
        if candidate["fusion_score"] is not None:
            return float(candidate["fusion_score"])
        channel = candidate["retrieval_channels"][0]
        return 1.0 / (60 + int(candidate["channel_ranks"][channel]))

    candidates.sort(key=lambda item: (-ranking_score(item), item["candidate_id"]))
    max_candidates = request.payload["max_candidates"]
    cutoff_count = max(0, len(candidates) - max_candidates)
    candidates = candidates[:max_candidates]
    non_vector_present = any(
        set(candidate["retrieval_channels"]) & NON_VECTOR_CHANNELS for candidate in candidates
    )
    run_ceiling = (
        "PASS"
        if non_vector_present and response.outcome.search_state == "SEARCHED_WITH_RESULTS"
        else "PARTIAL"
    )
    return CandidateSetResult(
        candidates=tuple(copy.deepcopy(candidates)),
        outcome=response.outcome,
        raw_hit_count=len(hits),
        duplicate_count=duplicate_count,
        cutoff_count=cutoff_count,
        excluded_count=duplicate_count + cutoff_count,
        run_ceiling=run_ceiling,
    )


def classify_relation_direction(
    canonical_relation: Sequence[str],
    observed_relations: Sequence[Sequence[str]],
    *,
    inverse_predicates: Mapping[str, str] | None = None,
    ontology_version: str | None = None,
    symmetric_predicates: Iterable[str] = (),
    trusted_grounding: bool = True,
) -> RelationDirection:
    """Classify relation orientation using only versioned, explicit mappings."""

    if not trusted_grounding:
        return RelationDirection.UNRESOLVED
    if len(canonical_relation) != 3:
        raise RetrievalContractError("RELATION_SHAPE_INVALID", "canonical relation must be [subject,predicate,object]")
    subject, predicate, object_ = (_nonempty_string(item, "relation item") for item in canonical_relation)
    symmetric = set(symmetric_predicates)
    if predicate in symmetric:
        return RelationDirection.NO_DIRECTION
    observed: set[tuple[str, str, str]] = set()
    for relation in observed_relations:
        if len(relation) != 3:
            raise RetrievalContractError("RELATION_SHAPE_INVALID", "observed relation must be [subject,predicate,object]")
        observed.add(tuple(_nonempty_string(item, "relation item") for item in relation))
    same = (subject, predicate, object_) in observed
    reverse = (object_, predicate, subject) in observed
    if same and reverse:
        return RelationDirection.BIDIRECTIONAL
    if same:
        return RelationDirection.SAME_DIRECTION
    if reverse:
        return RelationDirection.REVERSE_DIRECTION
    inverse_map = dict(inverse_predicates or {})
    if inverse_map:
        if not isinstance(ontology_version, str) or not ontology_version.strip():
            raise RetrievalContractError("ONTOLOGY_VERSION_REQUIRED", "inverse predicates require a versioned ontology")
        inverse = inverse_map.get(predicate)
        if inverse and (object_, inverse, subject) in observed:
            return RelationDirection.INVERSE_PREDICATE
    return RelationDirection.UNRESOLVED


def evaluate_non_vector_release(
    candidates: Sequence[Mapping[str, Any]],
    *,
    required_lane_states: Mapping[str, str],
    work_class: str = "E1",
    silent_fallback_count: int = 0,
) -> ReleaseGuardResult:
    """Enforce non-vector release and metadata-only evidence boundaries."""

    if silent_fallback_count < 0:
        raise RetrievalContractError("FIELD_INVALID", "silent_fallback_count cannot be negative")
    payloads = [copy.deepcopy(dict(candidate)) for candidate in candidates]
    for candidate in payloads:
        validate_retrieval_candidate(candidate)
    vector_only = tuple(
        sorted(
            candidate["candidate_id"]
            for candidate in payloads
            if not (set(candidate["retrieval_channels"]) & NON_VECTOR_CHANNELS)
        )
    )
    metadata_only = tuple(
        sorted(candidate["candidate_id"] for candidate in payloads if candidate["source_span_id"] is None)
    )
    direct = tuple(
        sorted(candidate["candidate_id"] for candidate in payloads if candidate["source_span_id"] is not None)
    )
    if silent_fallback_count:
        return ReleaseGuardResult(False, "FAIL", "silent_fallback_detected", vector_only, metadata_only, direct, silent_fallback_count)
    required_e1 = ("lexical", "semantic", "citation", "temporal")
    if work_class != "E0":
        missing = [
            lane
            for lane in required_e1
            if required_lane_states.get(lane) not in {"SEARCHED_NONE", "SEARCHED_WITH_RESULTS"}
        ]
        if missing:
            return ReleaseGuardResult(False, "PARTIAL", "required_lane_incomplete", vector_only, metadata_only, direct, 0)
    if not payloads:
        all_complete_none = bool(required_lane_states) and all(
            state == "SEARCHED_NONE" for state in required_lane_states.values()
        )
        return ReleaseGuardResult(
            all_complete_none,
            "PASS" if all_complete_none else "PARTIAL",
            "complete_zero_results" if all_complete_none else "incomplete_empty_release",
            vector_only,
            metadata_only,
            direct,
            0,
        )
    has_non_vector = any(set(candidate["retrieval_channels"]) & NON_VECTOR_CHANNELS for candidate in payloads)
    return ReleaseGuardResult(
        has_non_vector,
        "PASS" if has_non_vector else "PARTIAL",
        "non_vector_origin_present" if has_non_vector else "vector_only_release",
        vector_only,
        metadata_only,
        direct,
        0,
    )


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int = 20) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def ndcg_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int = 20) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    dcg = sum(
        1.0 / math.log2(index + 2)
        for index, document_id in enumerate(ranked_ids[:k])
        if document_id in relevant
    )
    ideal_count = min(k, len(relevant))
    ideal = sum(1.0 / math.log2(index + 2) for index in range(ideal_count))
    return dcg / ideal


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.lower()) if len(token) > 1}


def rank_fixture_corpus(
    corpus: Sequence[Mapping[str, Any]],
    queries: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Network-free deterministic lexical oracle used only by O02 fixtures."""

    rankings: dict[str, list[str]] = {}
    for query in queries:
        query_id = _nonempty_string(query.get("query_id"), "query_id")
        lane = _nonempty_string(query.get("lane"), "lane")
        terms = _tokens(_nonempty_string(query.get("text"), "query text"))
        scored: list[tuple[int, str]] = []
        for document in corpus:
            document_id = _nonempty_string(document.get("document_id"), "document_id")
            lanes = document.get("lanes")
            if not isinstance(lanes, list) or lane not in lanes:
                continue
            overlap = len(terms & _tokens(_nonempty_string(document.get("text"), "document text")))
            if overlap:
                scored.append((overlap, document_id))
        rankings[query_id] = [document_id for _, document_id in sorted(scored, key=lambda row: (-row[0], row[1]))]
    return rankings


def evaluate_retrieval_benchmark(
    rankings: Mapping[str, Sequence[str]],
    queries: Sequence[Mapping[str, Any]],
    relevance: Mapping[str, Sequence[str]],
    *,
    must_find_query_ids: Iterable[str],
    k: int = 20,
) -> dict[str, Any]:
    per_lane_values: dict[str, list[tuple[float, float]]] = defaultdict(list)
    fused_scores: dict[str, float] = defaultdict(float)
    must_find = set(must_find_query_ids)
    critical_found: dict[str, bool] = {}
    for query in queries:
        query_id = _nonempty_string(query.get("query_id"), "query_id")
        lane = _nonempty_string(query.get("lane"), "lane")
        ranked = list(rankings.get(query_id, ()))
        relevant = list(relevance.get(query_id, ()))
        per_lane_values[lane].append((recall_at_k(ranked, relevant, k), ndcg_at_k(ranked, relevant, k)))
        if query_id in must_find:
            critical_found[query_id] = set(relevant).issubset(set(ranked[:k]))
        for rank, document_id in enumerate(ranked[:k], start=1):
            fused_scores[document_id] += 1.0 / (60 + rank)
    per_lane = {
        lane: {
            "recall_at_20": sum(value[0] for value in values) / len(values),
            "ndcg_at_20": sum(value[1] for value in values) / len(values),
        }
        for lane, values in sorted(per_lane_values.items())
    }
    all_relevant = {document_id for values in relevance.values() for document_id in values}
    fused_order = [
        document_id
        for document_id, _ in sorted(
            fused_scores.items(),
            key=lambda row: (-row[1], row[0]),
        )
    ]
    return {
        "per_lane": per_lane,
        "fused_recall_at_20": recall_at_k(fused_order, all_relevant, k),
        "critical_must_find": dict(sorted(critical_found.items())),
        "query_count": len(queries),
        "live_network_calls": 0,
        "live_llm_calls": 0,
    }


def assert_benchmark_thresholds(report: Mapping[str, Any]) -> None:
    for lane, metrics in report["per_lane"].items():
        if metrics["recall_at_20"] < 0.90:
            raise RetrievalContractError("BENCHMARK_RECALL_BELOW_THRESHOLD", lane)
        if metrics["ndcg_at_20"] < 0.85:
            raise RetrievalContractError("BENCHMARK_NDCG_BELOW_THRESHOLD", lane)
    if report["fused_recall_at_20"] < 0.95:
        raise RetrievalContractError("BENCHMARK_FUSED_RECALL_BELOW_THRESHOLD", "fused")
    if not all(report["critical_must_find"].values()):
        raise RetrievalContractError("BENCHMARK_CRITICAL_MUST_FIND_FAILED", "critical query")
    if report.get("live_network_calls") != 0 or report.get("live_llm_calls") != 0:
        raise RetrievalContractError("BENCHMARK_EXTERNAL_DEPENDENCY", "benchmark must be local and deterministic")
