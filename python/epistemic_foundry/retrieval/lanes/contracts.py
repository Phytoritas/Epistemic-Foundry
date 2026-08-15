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
from types import MappingProxyType
from typing import Any, Final

from ..planning import contracts as planning


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

LANE_QUERY_FAMILIES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
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
)

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
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.message = detail
        self.details = (
            MappingProxyType(dict(details)) if details is not None else None
        )
        self.terminal_state = terminal_state
        self.stop_reason = stop_reason


@dataclass(frozen=True, slots=True)
class SealedBackendRequest:
    """Canonical request bytes plus independently re-derivable bindings."""

    _canonical_bytes: bytes
    request_hash: str
    query_text: str

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, Any]:
        value = _load_request_payload(self._canonical_bytes)
        if type(value) is not dict:  # pragma: no cover - validated construction invariant
            raise AssertionError("sealed backend request is not an object")
        return value


@dataclass(frozen=True)
class TerminalOutcome:
    search_state: str
    stop_reason: str
    error_code: str | None


@dataclass(frozen=True, slots=True)
class ValidatedBackendResponse:
    _canonical_bytes: bytes
    response_hash: str
    outcome: TerminalOutcome

    @property
    def payload(self) -> dict[str, Any]:
        value = _load_canonical_json(self._canonical_bytes)
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("validated backend response is not an object")
        return value


@dataclass(frozen=True, slots=True, init=False)
class CandidateSetResult:
    _candidate_bytes: tuple[bytes, ...]
    outcome: TerminalOutcome
    raw_hit_count: int
    duplicate_count: int
    cutoff_count: int
    excluded_count: int
    run_ceiling: str

    def __init__(
        self,
        candidates: Sequence[Mapping[str, Any]],
        outcome: TerminalOutcome,
        raw_hit_count: int,
        duplicate_count: int,
        cutoff_count: int,
        excluded_count: int,
        run_ceiling: str,
    ) -> None:
        if (
            isinstance(candidates, (str, bytes, bytearray, memoryview, Mapping))
            or not isinstance(candidates, Sequence)
        ):
            raise RetrievalContractError("TYPE_MISMATCH", "candidates must be an array")
        detached = _json_snapshot(candidates, "candidate set", {}, set())
        if type(detached) is not list:  # pragma: no cover - root check above
            raise AssertionError("candidate set snapshot root is not an array")
        candidate_bytes: list[bytes] = []
        for index, candidate in enumerate(detached):
            if type(candidate) is not dict:
                raise RetrievalContractError(
                    "TYPE_MISMATCH", f"candidates[{index}] must be an object"
                )
            candidate_bytes.append(canonical_json(candidate))
        object.__setattr__(self, "_candidate_bytes", tuple(candidate_bytes))
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "raw_hit_count", raw_hit_count)
        object.__setattr__(self, "duplicate_count", duplicate_count)
        object.__setattr__(self, "cutoff_count", cutoff_count)
        object.__setattr__(self, "excluded_count", excluded_count)
        object.__setattr__(self, "run_ceiling", run_ceiling)

    @property
    def candidates(self) -> tuple[dict[str, Any], ...]:
        payloads: list[dict[str, Any]] = []
        for value in self._candidate_bytes:
            candidate = _load_canonical_json(value)
            if type(candidate) is not dict:  # pragma: no cover - construction invariant
                raise AssertionError("candidate set item is not an object")
            for field in ("raw_rank", "channel_ranks"):
                if field not in candidate:
                    raise RetrievalContractError(
                        "FIELD_SET_MISMATCH", f"RetrievalCandidate missing {field}"
                    )
            candidate["raw_rank"] = _integer(candidate["raw_rank"], "raw_rank")
            channel_ranks = _mapping(candidate["channel_ranks"], "channel_ranks")
            for channel, rank in channel_ranks.items():
                if rank is not None:
                    channel_ranks[channel] = _integer(rank, f"channel_ranks.{channel}")
            candidate["channel_ranks"] = channel_ranks
            payloads.append(candidate)
        return tuple(payloads)

    def candidate_payloads(self) -> list[dict[str, Any]]:
        return list(self.candidates)


@dataclass(frozen=True)
class NonVectorAssessmentResult:
    """Non-authoritative projection; never a release authorization."""

    satisfies_non_vector_policy: bool
    assessed_ceiling: str
    reason: str
    vector_only_candidate_ids: tuple[str, ...]
    metadata_only_candidate_ids: tuple[str, ...]
    direct_evidence_candidate_ids: tuple[str, ...]
    silent_fallback_count: int


def _binary64(value: int | float, label: str) -> float:
    if type(value) is int:
        try:
            number = float(value)
        except OverflowError as exc:
            raise RetrievalContractError(
                "CANONICAL_JSON_INVALID", f"{label} is outside finite binary64"
            ) from exc
        if not math.isfinite(number) or int(number) != value:
            raise RetrievalContractError(
                "CANONICAL_JSON_INVALID",
                f"{label} is not losslessly representable as binary64",
            )
        return number
    if type(value) is float:
        if not math.isfinite(value):
            raise RetrievalContractError(
                "CANONICAL_JSON_INVALID", f"{label} contains a non-finite number"
            )
        return value
    raise RetrievalContractError(
        "CANONICAL_JSON_INVALID", f"{label} contains a numeric subclass"
    )


def _ecmascript_number(value: int | float, label: str) -> str:
    """Serialize one finite binary64 value using ECMAScript/JCS notation."""

    number = _binary64(value, label)
    if number == 0:
        return "0"
    negative = number < 0
    token = repr(-number if negative else number).lower()
    mantissa, separator, exponent_text = token.partition("e")
    exponent = int(exponent_text) if separator else 0
    integer_part, point, fractional_part = mantissa.partition(".")
    digits = integer_part + (fractional_part if point else "")
    decimal_position = len(integer_part) + exponent
    while len(digits) > 1 and digits.startswith("0"):
        digits = digits[1:]
        decimal_position -= 1
    while len(digits) > 1 and digits.endswith("0"):
        digits = digits[:-1]

    if 1e-6 <= abs(number) < 1e21:
        if decimal_position <= 0:
            rendered = "0." + ("0" * -decimal_position) + digits
        elif decimal_position >= len(digits):
            rendered = digits + ("0" * (decimal_position - len(digits)))
        else:
            rendered = digits[:decimal_position] + "." + digits[decimal_position:]
    else:
        coefficient = digits[0]
        if len(digits) > 1:
            coefficient += "." + digits[1:]
        scientific_exponent = decimal_position - 1
        exponent_sign = "+" if scientific_exponent >= 0 else "-"
        rendered = f"{coefficient}e{exponent_sign}{abs(scientific_exponent)}"
    return ("-" if negative else "") + rendered


def _ijson_string(value: str, label: str) -> str:
    for character in value:
        codepoint = ord(character)
        if (
            0xD800 <= codepoint <= 0xDFFF
            or 0xFDD0 <= codepoint <= 0xFDEF
            or (codepoint & 0xFFFF) in {0xFFFE, 0xFFFF}
        ):
            raise RetrievalContractError(
                "CANONICAL_JSON_INVALID",
                f"{label} contains an I-JSON-forbidden code point",
            )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", f"{label} contains invalid Unicode"
        ) from exc
    return value


def _jcs_string(value: str, label: str) -> str:
    return json.dumps(_ijson_string(value, label), ensure_ascii=False)


def _utf16_sort_key(value: str) -> bytes:
    try:
        return _ijson_string(value, "object key").encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", "object key contains invalid Unicode"
        ) from exc


def _jcs_text(value: object, label: str) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is str:
        return _jcs_string(value, label)
    if type(value) in {int, float}:
        return _ecmascript_number(value, label)
    if type(value) is list:
        return "[" + ",".join(
            _jcs_text(item, f"{label}[{index}]")
            for index, item in enumerate(value)
        ) + "]"
    if type(value) is dict:
        parts: list[str] = []
        for key in sorted(value, key=_utf16_sort_key):
            parts.append(
                _jcs_string(key, f"{label} key")
                + ":"
                + _jcs_text(value[key], f"{label}.{key}")
            )
        return "{" + ",".join(parts) + "}"
    raise AssertionError("JSON snapshot contains a non-JSON value")


def canonical_json(value: Any) -> bytes:
    """Return strict RFC 8785 JCS UTF-8 bytes for one JSON value."""

    try:
        detached = _json_snapshot(value, "canonical JSON value", {}, set())
        return _jcs_text(detached, "canonical JSON value").encode("utf-8")
    except RetrievalContractError:
        raise
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise RetrievalContractError("CANONICAL_JSON_INVALID", str(exc)) from exc


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_object(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def _json_snapshot(
    value: object,
    label: str,
    memo: dict[int, object],
    active: set[int],
) -> object:
    """Detach one caller-owned composite through base JSON primitives."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _ijson_string(str.__str__(value), label)
    if isinstance(value, int):
        if type(value) is not int:
            raise RetrievalContractError(
                "CANONICAL_JSON_INVALID", f"{label} contains a numeric subclass"
            )
        _binary64(value, label)
        return value
    if isinstance(value, float):
        if type(value) is not float:
            raise RetrievalContractError(
                "CANONICAL_JSON_INVALID", f"{label} contains a numeric subclass"
            )
        _binary64(value, label)
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", f"{label} contains a byte-like value"
        )

    identity = id(value)
    if identity in active:
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", f"{label} contains a cycle"
        )
    if identity in memo:
        return memo[identity]

    if isinstance(value, Mapping):
        detached_mapping: dict[str, object] = {}
        memo[identity] = detached_mapping
        active.add(identity)
        try:
            try:
                entries = value.items()
                for key, entry in entries:
                    if not isinstance(key, str):
                        raise RetrievalContractError(
                            "CANONICAL_JSON_INVALID", f"{label} keys must be strings"
                        )
                    plain_key = str.__str__(key)
                    _ijson_string(plain_key, f"{label} key")
                    if plain_key in detached_mapping:
                        raise RetrievalContractError(
                            "CANONICAL_JSON_INVALID", f"{label} keys must be unique"
                        )
                    detached_mapping[plain_key] = _json_snapshot(
                        entry,
                        f"{label}.{plain_key}",
                        memo,
                        active,
                    )
            except RetrievalContractError:
                raise
            except Exception as exc:
                raise RetrievalContractError(
                    "CANONICAL_JSON_INVALID", f"{label} could not be read as an object"
                ) from exc
        finally:
            active.remove(identity)
        return detached_mapping

    if isinstance(value, Sequence):
        detached_sequence: list[object] = []
        memo[identity] = detached_sequence
        active.add(identity)
        try:
            try:
                for index, entry in enumerate(value):
                    detached_sequence.append(
                        _json_snapshot(entry, f"{label}[{index}]", memo, active)
                    )
            except RetrievalContractError:
                raise
            except Exception as exc:
                raise RetrievalContractError(
                    "CANONICAL_JSON_INVALID", f"{label} could not be read as an array"
                ) from exc
        finally:
            active.remove(identity)
        return detached_sequence

    raise RetrievalContractError(
        "CANONICAL_JSON_INVALID", f"{label} contains a non-JSON value"
    )


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RetrievalContractError("TYPE_MISMATCH", f"{label} must be an object")
    detached = _json_snapshot(value, label, {}, set())
    if type(detached) is not dict:  # pragma: no cover - root check above
        raise AssertionError("mapping snapshot root is not an object")
    return detached


def _decode_binary64(token: str) -> float:
    try:
        value = float(token)
    except (OverflowError, ValueError) as exc:
        raise ValueError("JSON number is not binary64") from exc
    if not math.isfinite(value):
        raise ValueError("JSON number is not finite binary64")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"JSON constant {token!r} is not permitted")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains duplicate keys")
        result[key] = value
    return result


def _load_canonical_json(value: bytes) -> object:
    if type(value) is not bytes:
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", "canonical JSON input must be bytes"
        )
    try:
        parsed = json.loads(
            value.decode("utf-8"),
            parse_int=_decode_binary64,
            parse_float=_decode_binary64,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_object,
        )
        return _json_snapshot(parsed, "decoded canonical JSON", {}, set())
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", "bytes are not finite I-JSON"
        ) from exc


def _integer(value: object, field: str) -> int:
    if type(value) is int:
        _binary64(value, field)
        return value
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return int(value)
    raise RetrievalContractError("FIELD_INVALID", f"{field} must be an integer")


def _load_request_payload(value: bytes) -> dict[str, Any]:
    payload = _load_canonical_json(value)
    if type(payload) is not dict:
        raise RetrievalContractError(
            "CANONICAL_JSON_INVALID", "sealed backend request must be an object"
        )
    for field in ("max_candidates", "deterministic_seed"):
        if field in payload:
            payload[field] = _integer(payload[field], field)
    return payload


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
    if not isinstance(value, str) or not str.strip(value):
        raise RetrievalContractError("FIELD_INVALID", f"{field} must be a non-empty string")
    return str.__str__(value)


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
    extensions = (
        {}
        if extensions_value is None
        else _mapping(extensions_value, "scope_filter.domain_extensions")
    )
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


def _project_bound_lane_query(
    query_plan: Mapping[str, object] | planning.SealedArtifact,
    lane: object,
) -> planning.LaneQueryProjection:
    """Translate an O01 plan/lane refusal without weakening its semantics."""

    if isinstance(query_plan, planning.SealedArtifact):
        if (
            type(query_plan) is not planning.SealedArtifact
            or type(query_plan.artifact_type) is not str
            or query_plan.artifact_type != "QueryPlan"
            or type(query_plan.canonical_bytes) is not bytes
        ):
            raise RetrievalContractError(
                "REQUEST_INTEGRITY_INVALID",
                "query_plan is not a valid canonical QueryPlan artifact",
                terminal_state="FAILED",
                stop_reason="integrity_failure",
            )
    try:
        return planning.project_lane_query(query_plan, lane)  # type: ignore[arg-type]
    except planning.PlanningContractError as exc:
        raise RetrievalContractError(
            exc.code,
            str(exc),
            terminal_state="FAILED",
            stop_reason="invalid_response",
            details=exc.details,
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "query_plan is not a valid canonical QueryPlan artifact",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        ) from exc
    except AssertionError as exc:
        if type(query_plan) is not planning.SealedArtifact:
            raise
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "query_plan is not a valid canonical QueryPlan artifact",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        ) from exc


def seal_backend_request(
    value: Mapping[str, Any],
    *,
    query_plan: Mapping[str, object] | planning.SealedArtifact,
) -> SealedBackendRequest:
    """Validate and seal the exact provider-neutral O02 backend request."""

    payload = _mapping(value, "backend request")
    _exact_fields(payload, PROVIDER_REQUEST_FIELDS, "backend request")
    projection = _project_bound_lane_query(query_plan, payload["lane"])
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
    if payload["query_plan_id"] != projection.query_plan_id:
        raise RetrievalContractError(
            "PLAN_HASH_MISMATCH",
            "query_plan_id does not match the projected QueryPlan",
        )
    if payload["plan_hash"] != projection.plan_hash:
        raise RetrievalContractError(
            "PLAN_HASH_MISMATCH",
            "plan_hash does not match the projected QueryPlan",
        )
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
    normalized_query_batch = _validate_query_batch(
        payload["query_batch"], lane, families
    )
    projected_query_batch = projection.query_batch
    if normalized_query_batch != projected_query_batch:
        raise RetrievalContractError(
            "INVALID_QUERY_FAMILY_BINDING",
            "query_batch does not match the projected QueryPlan lane query",
        )
    payload["query_batch"] = normalized_query_batch
    query_text = canonical_json(payload["query_batch"]).decode("utf-8")
    batch_query_hash = sha256_bytes(query_text.encode("utf-8"))
    projected_query_hash = sha256_bytes(projection.query_batch_bytes)
    if payload["query_hash"] != batch_query_hash:
        raise RetrievalContractError("QUERY_HASH_MISMATCH", "query_hash does not bind canonical query_batch")
    if payload["query_hash"] != projected_query_hash:
        raise RetrievalContractError(
            "QUERY_HASH_MISMATCH",
            "query_hash does not bind the projected QueryPlan lane query",
        )
    scope_filter = _mapping(payload["scope_filter"], "scope_filter")
    _validate_lane_specific_scope(lane, scope_filter)
    payload["scope_filter"] = scope_filter
    payload["index_versions"] = _string_map(payload["index_versions"], "index_versions")
    payload["max_candidates"] = _integer(payload["max_candidates"], "max_candidates")
    if payload["max_candidates"] < 1:
        raise RetrievalContractError("FIELD_INVALID", "max_candidates must be a positive integer")
    payload["deterministic_seed"] = _integer(
        payload["deterministic_seed"], "deterministic_seed"
    )
    canonical_bytes = canonical_json(payload)
    return SealedBackendRequest(
        _canonical_bytes=canonical_bytes,
        request_hash=sha256_bytes(canonical_bytes),
        query_text=query_text,
    )


def validate_sealed_backend_request(
    value: object,
    *,
    query_plan: Mapping[str, object] | planning.SealedArtifact,
) -> SealedBackendRequest:
    """Re-derive a sealed request from canonical bytes before authority use."""

    if type(value) is not SealedBackendRequest:
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "request must be an exact SealedBackendRequest",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        )
    if (
        type(value.canonical_bytes) is not bytes
        or type(value.request_hash) is not str
        or type(value.query_text) is not str
    ):
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "sealed request fields must use canonical primitive types",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        )
    try:
        payload = _load_request_payload(value.canonical_bytes)
    except RetrievalContractError as exc:
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "sealed request bytes are not canonical UTF-8 JSON",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        ) from exc
    try:
        rebuilt = seal_backend_request(payload, query_plan=query_plan)
    except RetrievalContractError as exc:
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "sealed request bytes do not satisfy the request contract",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        ) from exc
    if (
        rebuilt.canonical_bytes != value.canonical_bytes
        or rebuilt.request_hash != value.request_hash
        or rebuilt.query_text != value.query_text
    ):
        raise RetrievalContractError(
            "REQUEST_INTEGRITY_INVALID",
            "sealed request bytes, hash, and query text do not agree",
            terminal_state="FAILED",
            stop_reason="integrity_failure",
        )
    return rebuilt


def _response_preimage(payload: Mapping[str, Any]) -> dict[str, Any]:
    detached = _mapping(payload, "backend response")
    return {key: value for key, value in detached.items() if key != "response_hash"}


def seal_backend_response(
    request: SealedBackendRequest,
    response_values: Mapping[str, Any],
    *,
    query_plan: Mapping[str, object] | planning.SealedArtifact,
) -> dict[str, Any]:
    """Bind adapter observations to a sealed request and add the response hash.

    This is the adapter-side sealing step.  Callers must still pass its output
    through :func:`validate_backend_response` before using any hit.
    """

    request = validate_sealed_backend_request(request, query_plan=query_plan)
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
    try:
        rank = _integer(hit["raw_rank"], "raw_rank")
    except RetrievalContractError as exc:
        raise RetrievalContractError("RAW_RANK_INVALID", repr(hit["raw_rank"])) from exc
    if rank < 1:
        raise RetrievalContractError("RAW_RANK_INVALID", repr(rank))
    hit["raw_rank"] = rank
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
    *,
    query_plan: Mapping[str, object] | planning.SealedArtifact,
) -> ValidatedBackendResponse:
    """Validate all bindings of an untrusted backend response."""

    request = validate_sealed_backend_request(request, query_plan=query_plan)
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
    for hit in payload["hits"]:
        if hit["query_family"] not in executed_families:
            raise _integrity_failure(
                "RESPONSE_BINDING_MISMATCH",
                f"hit query_family {hit['query_family']!r} was not executed",
            )
    outcome = _terminal_outcome(payload)
    return ValidatedBackendResponse(
        _canonical_bytes=canonical_json(payload),
        response_hash=expected_hash,
        outcome=outcome,
    )


def compute_candidate_id(candidate: Mapping[str, Any]) -> str:
    payload = _mapping(candidate, "RetrievalCandidate identity input")
    missing = [field for field in CANDIDATE_IDENTITY_FIELDS if field not in payload]
    if missing:
        raise RetrievalContractError(
            "FIELD_SET_MISMATCH",
            f"RetrievalCandidate identity input missing={missing}",
        )
    preimage = {field: payload[field] for field in CANDIDATE_IDENTITY_FIELDS}
    return "RC-" + hashlib.sha256(canonical_json(preimage)).hexdigest()


def compute_candidate_hash(candidate: Mapping[str, Any]) -> str:
    payload = _mapping(candidate, "RetrievalCandidate hash input")
    missing = [field for field in CANDIDATE_HASH_FIELDS if field not in payload]
    if missing:
        raise RetrievalContractError(
            "FIELD_SET_MISMATCH",
            f"RetrievalCandidate hash input missing={missing}",
        )
    preimage = {field: payload[field] for field in CANDIDATE_HASH_FIELDS}
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
        if len({canonical_json(item[field]) for item in observations}) != 1:
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
    for field in (
        "plan_hash",
        "corpus_snapshot_hash",
        "backend_request_hash",
        "backend_response_hash",
        "source_snapshot_hash",
    ):
        _sha256(candidate[field], field)
    if type(candidate["raw_rank"]) is not int or candidate["raw_rank"] < 1:
        raise RetrievalContractError("RAW_RANK_INVALID", repr(candidate["raw_rank"]))
    if candidate["source_span_id"] is not None:
        _nonempty_string(candidate["source_span_id"], "source_span_id")
    lane = candidate["lane"]
    family = candidate["query_family"]
    if lane not in LANE_QUERY_FAMILIES or family not in LANE_QUERY_FAMILIES[lane]:
        raise RetrievalContractError("INVALID_QUERY_FAMILY_BINDING", f"{lane}/{family}")
    channels = candidate["retrieval_channels"]
    if not isinstance(channels, list) or not channels:
        raise RetrievalContractError("CHANNEL_ORDER_INVALID", repr(channels))
    for channel in channels:
        if channel not in CHANNEL_ORDER:
            raise RetrievalContractError("RETRIEVAL_CHANNEL_UNKNOWN", repr(channel))
    if channels != sorted(set(channels), key=_CHANNEL_RANK.__getitem__):
        raise RetrievalContractError("CHANNEL_ORDER_INVALID", repr(channels))
    raw_scores = _mapping(candidate["raw_scores"], "raw_scores")
    channel_ranks = _mapping(candidate["channel_ranks"], "channel_ranks")
    _exact_fields(raw_scores, CHANNEL_ORDER, "raw_scores")
    _exact_fields(channel_ranks, CHANNEL_ORDER, "channel_ranks")
    for channel in CHANNEL_ORDER:
        observed = channel in channels
        score = raw_scores[channel]
        rank = channel_ranks[channel]
        if score is not None and type(score) not in {int, float}:
            raise RetrievalContractError("RAW_SCORE_INVALID", repr(score))
        if rank is not None and (type(rank) is not int or rank < 1):
            raise RetrievalContractError("RAW_RANK_INVALID", repr(rank))
        if observed != (score is not None) or observed != (rank is not None):
            raise RetrievalContractError("CHANNEL_OBSERVATION_MISMATCH", channel)
    if len(channels) == 1:
        if candidate["fusion_method"] != "SINGLE_CHANNEL" or candidate["fusion_score"] is not None or candidate["multi_channel_verified"] is not False:
            raise RetrievalContractError("FUSION_CONTRACT_VIOLATION", "single-channel candidate has fused fields")
    else:
        expected = sum(1.0 / (60 + channel_ranks[channel]) for channel in channels)
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
    *,
    query_plan: Mapping[str, object] | planning.SealedArtifact,
) -> CandidateSetResult:
    """Validate, deduplicate, fuse, cut off, and seal one lane candidate set."""

    request = validate_sealed_backend_request(request, query_plan=query_plan)
    response = validate_backend_response(
        request,
        response_value,
        query_plan=query_plan,
    )
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
        candidates=tuple(candidates),
        outcome=response.outcome,
        raw_hit_count=len(hits),
        duplicate_count=duplicate_count,
        cutoff_count=cutoff_count,
        excluded_count=duplicate_count + cutoff_count,
        run_ceiling=run_ceiling,
    )


def _relation_triplet(value: object, label: str) -> tuple[str, str, str]:
    if (
        isinstance(value, (str, bytes, bytearray, memoryview, Mapping))
        or not isinstance(value, Sequence)
    ):
        raise RetrievalContractError(
            "RELATION_SHAPE_INVALID", f"{label} must be [subject,predicate,object]"
        )
    detached = _json_snapshot(value, label, {}, set())
    if type(detached) is not list or len(detached) != 3:
        raise RetrievalContractError(
            "RELATION_SHAPE_INVALID", f"{label} must be [subject,predicate,object]"
        )
    subject, predicate, object_ = (
        _nonempty_string(item, f"{label} item") for item in detached
    )
    return subject, predicate, object_


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

    if type(trusted_grounding) is not bool:
        raise RetrievalContractError(
            "FIELD_INVALID", "trusted_grounding must be a boolean"
        )
    if not trusted_grounding:
        return RelationDirection.UNRESOLVED

    subject, predicate, object_ = _relation_triplet(
        canonical_relation, "canonical relation"
    )
    if (
        isinstance(symmetric_predicates, (str, bytes, bytearray, memoryview, Mapping))
        or not isinstance(symmetric_predicates, Iterable)
    ):
        raise RetrievalContractError(
            "FIELD_INVALID", "symmetric_predicates must be an iterable of strings"
        )
    symmetric: set[str] = set()
    try:
        for index, item in enumerate(symmetric_predicates):
            symmetric.add(_nonempty_string(item, f"symmetric_predicates[{index}]"))
    except RetrievalContractError:
        raise
    except Exception as exc:
        raise RetrievalContractError(
            "FIELD_INVALID", "symmetric_predicates could not be read"
        ) from exc
    if predicate in symmetric:
        return RelationDirection.NO_DIRECTION

    if (
        isinstance(observed_relations, (str, bytes, bytearray, memoryview, Mapping))
        or not isinstance(observed_relations, Sequence)
    ):
        raise RetrievalContractError(
            "RELATION_SHAPE_INVALID", "observed relations must be an array"
        )
    detached_observed = _json_snapshot(
        observed_relations, "observed relations", {}, set()
    )
    if type(detached_observed) is not list:  # pragma: no cover - root check above
        raise AssertionError("observed relation snapshot root is not an array")
    observed: set[tuple[str, str, str]] = set()
    for index, relation in enumerate(detached_observed):
        observed.add(_relation_triplet(relation, f"observed relation[{index}]"))
    same = (subject, predicate, object_) in observed
    reverse = (object_, predicate, subject) in observed
    if same and reverse:
        return RelationDirection.BIDIRECTIONAL
    if same:
        return RelationDirection.SAME_DIRECTION
    if reverse:
        return RelationDirection.REVERSE_DIRECTION
    inverse_map = (
        {}
        if inverse_predicates is None
        else _mapping(inverse_predicates, "inverse_predicates")
    )
    if inverse_map:
        if not isinstance(ontology_version, str) or not ontology_version.strip():
            raise RetrievalContractError("ONTOLOGY_VERSION_REQUIRED", "inverse predicates require a versioned ontology")
        normalized_inverse_map = {
            _nonempty_string(key, "inverse_predicates key"): _nonempty_string(
                value, f"inverse_predicates.{key}"
            )
            for key, value in inverse_map.items()
        }
        inverse = normalized_inverse_map.get(predicate)
        if inverse and (object_, inverse, subject) in observed:
            return RelationDirection.INVERSE_PREDICATE
    return RelationDirection.UNRESOLVED


def assess_non_vector_origin(
    candidates: Sequence[Mapping[str, Any]],
    *,
    required_lane_states: Mapping[str, str],
    work_class: str = "E1",
    silent_fallback_count: int = 0,
) -> NonVectorAssessmentResult:
    """Assess non-vector and metadata boundaries without authorizing release.

    Candidate self-hashes and caller-supplied lane states cannot resolve the
    missing O01 SearchLaneReceipt-to-RetrievalCandidate result binding.
    """

    if type(silent_fallback_count) is not int or silent_fallback_count < 0:
        raise RetrievalContractError(
            "FIELD_INVALID", "silent_fallback_count must be a non-negative integer"
        )
    _nonempty_string(work_class, "work_class")
    if (
        isinstance(candidates, (str, bytes, bytearray, memoryview, Mapping))
        or not isinstance(candidates, Sequence)
    ):
        raise RetrievalContractError("TYPE_MISMATCH", "candidates must be an array")
    detached_candidates = _json_snapshot(candidates, "candidates", {}, set())
    if type(detached_candidates) is not list:  # pragma: no cover - root check above
        raise AssertionError("candidate snapshot root is not an array")
    payloads = [
        _mapping(candidate, f"candidates[{index}]")
        for index, candidate in enumerate(detached_candidates)
    ]
    for candidate in payloads:
        validate_retrieval_candidate(candidate)
    lane_states = _mapping(required_lane_states, "required_lane_states")
    for lane, state in lane_states.items():
        _nonempty_string(lane, "required_lane_states key")
        _nonempty_string(state, f"required_lane_states.{lane}")
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
        return NonVectorAssessmentResult(False, "FAIL", "silent_fallback_detected", vector_only, metadata_only, direct, silent_fallback_count)
    required_e1 = ("lexical", "semantic", "citation", "temporal")
    if work_class != "E0":
        missing = [
            lane
            for lane in required_e1
            if lane_states.get(lane) not in {"SEARCHED_NONE", "SEARCHED_WITH_RESULTS"}
        ]
        if missing:
            return NonVectorAssessmentResult(False, "PARTIAL", "required_lane_incomplete", vector_only, metadata_only, direct, 0)
    if not payloads:
        all_complete_none = bool(lane_states) and all(
            state == "SEARCHED_NONE" for state in lane_states.values()
        )
        return NonVectorAssessmentResult(
            all_complete_none,
            "PASS" if all_complete_none else "PARTIAL",
            "complete_zero_results" if all_complete_none else "incomplete_empty_release",
            vector_only,
            metadata_only,
            direct,
            0,
        )
    has_non_vector = any(set(candidate["retrieval_channels"]) & NON_VECTOR_CHANNELS for candidate in payloads)
    return NonVectorAssessmentResult(
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
