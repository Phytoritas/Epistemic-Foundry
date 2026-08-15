"""Deterministic I02 InsightCard and ScopeVector compilation.

The upstream framing model may propose text and scope values, but it does not
own canonical admission.  This module snapshots that proposal, normalizes it
to the existing ``InsightCard`` and ``ScopeVector`` contracts, retains unknown
scope values without guessing, and fails closed before an ineligible card can
claim council readiness.

I02 deliberately does not calculate identifiers, timestamps, or
``registration_hash``.  Their canonical generation semantics are not owned by
this package, so callers must supply already-sealed values and this component
only validates and preserves them.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping, Sequence


FRAME_COMPILER_VERSION: Final = "4.0.0-i02.1"

_MISSING: Final = object()
_ID_PATTERN: Final = re.compile(r"^[A-Z][A-Z0-9_-]*-[A-Za-z0-9._:-]+$")
_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER_PATTERN: Final = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$"
)
_RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
    r"[0-9]{2}:[0-9]{2}:(?P<second>[0-9]{2})(?:\.[0-9]+)?"
    r"(?:[Zz]|[+-][0-9]{2}:[0-9]{2})$"
)

_SCOPE_SCALAR_FIELDS: Final = (
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
)
_SCOPE_LIST_FIELDS: Final = ("inclusion_criteria", "exclusion_criteria")
_SCOPE_MAP_FIELDS: Final = ("conditions", "domain_extensions")
_SCOPE_FIELDS: Final = frozenset(
    (*_SCOPE_SCALAR_FIELDS, "intervention_or_exposure", "comparator", *_SCOPE_LIST_FIELDS, *_SCOPE_MAP_FIELDS)
)
_REQUIRED_COUNCIL_SCOPE_FIELDS: Final = (
    "domain",
    "population",
    "unit_of_analysis",
)
_INTERVENTION_FIELDS: Final = (
    "name",
    "category",
    "min_value",
    "max_value",
    "unit",
    "duration",
    "frequency",
    "rate",
    "route_or_delivery",
)
_CARD_FIELDS: Final = frozenset(
    {
        "insight_id",
        "revision",
        "statement",
        "scope",
        "mechanism_path",
        "predictions",
        "falsifiers",
        "alternative_hypotheses",
        "null_model",
        "registration_status",
        "lens_provenance",
        "created_at",
        "registration_hash",
        "risk_class",
        "terms_to_define",
        "decision_context",
        "created_by",
        "schema_version",
    }
)
_LENS_VALUES: Final = frozenset(
    {
        "adapt",
        "borrow",
        "modify",
        "magnify",
        "minify",
        "substitute",
        "rearrange",
        "reverse",
        "combine",
        "human",
    }
)
_REGISTRATION_STATUSES: Final = frozenset({"inbox", "eligible", "withdrawn"})
_RISK_CLASSES: Final = frozenset({"routine", "consequential", "high_stakes"})


class FrameContractError(ValueError):
    """Typed fail-closed error at the I02 component boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise FrameContractError(code, message, details)


class UnknownSource(str, Enum):
    """Why a canonical scope position remains unknown after normalization."""

    ABSENT = "ABSENT"
    EXPLICIT_NULL = "EXPLICIT_NULL"
    BLANK_STRING = "BLANK_STRING"


@dataclass(frozen=True, slots=True)
class ScopeUnknown:
    """Sidecar trace for an unknown that cannot be expressed in list/map slots."""

    path: str
    source: UnknownSource


@dataclass(frozen=True, slots=True)
class FrameCompilation:
    """Immutable result of one deterministic frame compilation."""

    compiler_version: str
    _insight_card_json: bytes
    unknown_scope: tuple[ScopeUnknown, ...]
    council_ready: bool
    council_blockers: tuple[str, ...]

    @property
    def insight_card_json(self) -> bytes:
        """Return the stable canonical JSON snapshot used by this component."""

        return self._insight_card_json

    @property
    def insight_card(self) -> dict[str, object]:
        """Return a fresh mutable projection; the stored result remains immutable."""

        value = json.loads(self._insight_card_json.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("compiled InsightCard snapshot is not an object")
        return value

    @property
    def scope_vector(self) -> dict[str, object]:
        """Return the compiled ScopeVector as a fresh projection."""

        value = self.insight_card["scope"]
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("compiled ScopeVector snapshot is not an object")
        return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:  # defensive boundary
        raise FrameContractError(
            "FRAME_INPUT_INVALID",
            "frame input must be representable as finite canonical JSON",
        ) from error


def _require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _fail("FRAME_INPUT_INVALID", f"{label} must be an object")
    result: dict[str, object] = {}
    for key, entry in value.items():
        if type(key) is not str or not key or "\x00" in key:
            _fail("FRAME_INPUT_INVALID", f"{label} keys must be non-empty NUL-free strings")
        result[key] = entry
    return result


def _require_text(
    value: object,
    label: str,
    *,
    minimum: int = 1,
    code: str = "FRAME_INPUT_INVALID",
) -> str:
    if type(value) is not str or "\x00" in value:
        _fail(code, f"{label} must be a NUL-free string")
    normalized = value.strip()
    if len(normalized) < minimum:
        _fail(code, f"{label} must contain at least {minimum} non-whitespace characters")
    try:
        normalized.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise FrameContractError(code, f"{label} must contain Unicode scalar values") from error
    return normalized


def _require_exact_text(
    value: object,
    label: str,
    *,
    minimum: int = 1,
    code: str = "FRAME_INPUT_INVALID",
) -> str:
    normalized = _require_text(value, label, minimum=minimum, code=code)
    if normalized != value:
        _fail(code, f"{label} must not contain surrounding whitespace")
    return normalized


def _required(payload: Mapping[str, object], field: str) -> object:
    if field not in payload:
        _fail("FRAME_FIELD_REQUIRED", f"{field} is required by the canonical InsightCard")
    return payload[field]


def _require_sequence(
    value: object,
    label: str,
    *,
    minimum: int,
    code: str = "FRAME_INPUT_INVALID",
) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail(code, f"{label} must be an array")
    if len(value) < minimum:
        _fail(code, f"{label} must contain at least {minimum} item(s)")
    return [
        _require_text(entry, f"{label}[{index}]", code=code)
        for index, entry in enumerate(value)
    ]


def _require_enum(value: object, label: str, allowed: frozenset[str]) -> str:
    normalized = _require_text(value, label)
    if normalized not in allowed:
        _fail(
            "FRAME_INPUT_INVALID",
            f"{label} must use the closed canonical vocabulary",
            {"actual": normalized, "allowed": sorted(allowed)},
        )
    return normalized


def _normalize_optional_scope_text(
    raw: object,
    path: str,
    unknowns: list[ScopeUnknown],
) -> str | None:
    if raw is _MISSING:
        unknowns.append(ScopeUnknown(path, UnknownSource.ABSENT))
        return None
    if raw is None:
        unknowns.append(ScopeUnknown(path, UnknownSource.EXPLICIT_NULL))
        return None
    if type(raw) is not str or "\x00" in raw:
        _fail("SCOPE_INPUT_INVALID", f"{path} must be a string or null")
    normalized = raw.strip()
    if not normalized:
        unknowns.append(ScopeUnknown(path, UnknownSource.BLANK_STRING))
        return None
    return normalized


def _normalize_number_or_null(raw: object, path: str) -> int | float | None:
    if raw is _MISSING or raw is None:
        return None
    if type(raw) not in (int, float) or not math.isfinite(raw):
        _fail("SCOPE_INPUT_INVALID", f"{path} must be a finite number or null")
    return raw


def _normalize_rate(raw: object, path: str) -> str | int | float | None:
    if raw is _MISSING or raw is None:
        return None
    if type(raw) in (int, float):
        if not math.isfinite(raw):
            _fail("SCOPE_INPUT_INVALID", f"{path} must be finite")
        return raw
    return _require_text(raw, path)


def _normalize_intervention(
    raw: object,
    unknowns: list[ScopeUnknown],
) -> dict[str, object] | None:
    path = "scope.intervention_or_exposure"
    if raw is _MISSING:
        unknowns.append(ScopeUnknown(path, UnknownSource.ABSENT))
        return None
    if raw is None:
        unknowns.append(ScopeUnknown(path, UnknownSource.EXPLICIT_NULL))
        return None
    value = _require_mapping(raw, path)
    extras = sorted(set(value) - set(_INTERVENTION_FIELDS))
    if extras:
        _fail(
            "SCOPE_FIELD_UNKNOWN",
            "intervention_or_exposure contains fields outside the canonical ScopeVector",
            {"fields": extras},
        )
    if "name" not in value:
        _fail(
            "SCOPE_INTERVENTION_NAME_REQUIRED",
            "a supplied intervention_or_exposure object requires a name",
        )

    result: dict[str, object] = {"name": _require_text(value["name"], f"{path}.name")}
    for field in ("category", "unit", "duration", "frequency", "route_or_delivery"):
        nested_path = f"{path}.{field}"
        result[field] = _normalize_optional_scope_text(
            value.get(field, _MISSING), nested_path, unknowns
        )
    for field in ("min_value", "max_value"):
        nested_path = f"{path}.{field}"
        raw_value = value.get(field, _MISSING)
        if raw_value is _MISSING:
            unknowns.append(ScopeUnknown(nested_path, UnknownSource.ABSENT))
        elif raw_value is None:
            unknowns.append(ScopeUnknown(nested_path, UnknownSource.EXPLICIT_NULL))
        result[field] = _normalize_number_or_null(raw_value, nested_path)
    rate_path = f"{path}.rate"
    raw_rate = value.get("rate", _MISSING)
    if raw_rate is _MISSING:
        unknowns.append(ScopeUnknown(rate_path, UnknownSource.ABSENT))
    elif raw_rate is None:
        unknowns.append(ScopeUnknown(rate_path, UnknownSource.EXPLICIT_NULL))
    result["rate"] = _normalize_rate(raw_rate, rate_path)
    return result


def _normalize_scope_list(
    raw: object,
    path: str,
    unknowns: list[ScopeUnknown],
) -> list[str]:
    if raw is _MISSING:
        unknowns.append(ScopeUnknown(path, UnknownSource.ABSENT))
        return []
    if raw is None:
        unknowns.append(ScopeUnknown(path, UnknownSource.EXPLICIT_NULL))
        return []
    return _require_sequence(raw, path, minimum=0, code="SCOPE_INPUT_INVALID")


def _normalize_json_scalar(value: object, path: str) -> object:
    if value is None or type(value) in (str, bool, int):
        if type(value) is str and "\x00" in value:
            _fail("SCOPE_INPUT_INVALID", f"{path} contains NUL")
        return value
    if type(value) is float and math.isfinite(value):
        return value
    _fail(
        "SCOPE_INPUT_INVALID",
        f"{path} must be a JSON scalar or an array of JSON scalars",
    )


def _normalize_scope_map(
    raw: object,
    path: str,
    unknowns: list[ScopeUnknown],
) -> dict[str, object]:
    if raw is _MISSING:
        unknowns.append(ScopeUnknown(path, UnknownSource.ABSENT))
        return {}
    if raw is None:
        unknowns.append(ScopeUnknown(path, UnknownSource.EXPLICIT_NULL))
        return {}
    value = _require_mapping(raw, path)
    normalized: dict[str, object] = {}
    for key in sorted(value):
        normalized_key = _require_text(key, f"{path} key")
        if normalized_key in normalized:
            _fail("SCOPE_INPUT_INVALID", f"{path} contains duplicate normalized keys")
        entry = value[key]
        if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes, bytearray)):
            normalized[normalized_key] = [
                _normalize_json_scalar(item, f"{path}.{normalized_key}[{index}]")
                for index, item in enumerate(entry)
            ]
        else:
            normalized[normalized_key] = _normalize_json_scalar(
                entry, f"{path}.{normalized_key}"
            )
    return normalized


def _normalize_scope(raw: object) -> tuple[dict[str, object], tuple[ScopeUnknown, ...]]:
    if raw is None:
        value: dict[str, object] = {}
        scope_was_null = True
    else:
        value = _require_mapping(raw, "scope")
        scope_was_null = False
    extras = sorted(set(value) - _SCOPE_FIELDS)
    if extras:
        _fail(
            "SCOPE_FIELD_UNKNOWN",
            "scope contains fields outside ScopeVector; domain axes belong in domain_extensions",
            {"fields": extras},
        )

    unknowns: list[ScopeUnknown] = []
    scope: dict[str, object] = {}
    for field in _SCOPE_SCALAR_FIELDS:
        raw_value = value.get(field, _MISSING)
        if scope_was_null:
            raw_value = None
        scope[field] = _normalize_optional_scope_text(
            raw_value, f"scope.{field}", unknowns
        )
    raw_intervention = value.get("intervention_or_exposure", _MISSING)
    if scope_was_null:
        raw_intervention = None
    scope["intervention_or_exposure"] = _normalize_intervention(raw_intervention, unknowns)
    raw_comparator = value.get("comparator", _MISSING)
    if scope_was_null:
        raw_comparator = None
    scope["comparator"] = _normalize_optional_scope_text(
        raw_comparator, "scope.comparator", unknowns
    )
    for field in _SCOPE_LIST_FIELDS:
        raw_value = value.get(field, _MISSING)
        if scope_was_null:
            raw_value = None
        scope[field] = _normalize_scope_list(raw_value, f"scope.{field}", unknowns)
    for field in _SCOPE_MAP_FIELDS:
        raw_value = value.get(field, _MISSING)
        if scope_was_null:
            raw_value = None
        scope[field] = _normalize_scope_map(raw_value, f"scope.{field}", unknowns)
    return scope, tuple(unknowns)


def _validate_timestamp(value: object) -> str:
    timestamp = _require_exact_text(value, "created_at")
    match = _RFC3339_PATTERN.fullmatch(timestamp)
    if match is None:
        _fail("FRAME_INPUT_INVALID", "created_at must be an RFC 3339 date-time")
    candidate = timestamp[:-1] + "+00:00" if timestamp[-1] in "Zz" else timestamp
    # RFC 3339 permits a leap second (``:60``), while ``datetime`` does not.
    # Substitute only for calendar/offset validation; the sealed input remains
    # byte-for-byte unchanged in the compiled card.
    if match.group("second") == "60":
        candidate = candidate[:17] + "59" + candidate[19:]
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise FrameContractError(
            "FRAME_INPUT_INVALID", "created_at must be an RFC 3339 date-time"
        ) from error
    if parsed.tzinfo is None:
        _fail("FRAME_INPUT_INVALID", "created_at must include an explicit timezone")
    return timestamp


def _council_blockers(
    *,
    card: Mapping[str, object],
    scope: Mapping[str, object],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if card["registration_status"] != "eligible":
        blockers.append("COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE")
    for field in _REQUIRED_COUNCIL_SCOPE_FIELDS:
        if scope[field] is None:
            blockers.append(f"COUNCIL_SCOPE_{field.upper()}_UNKNOWN")
    if card["terms_to_define"]:
        blockers.append("COUNCIL_UNDEFINED_CONSTRUCTS")
    return tuple(blockers)


def compile_frame(proposal: Mapping[str, object]) -> FrameCompilation:
    """Compile and gate one proposed frame without inventing missing authority.

    Mapping order is irrelevant.  Array order is retained because canonical
    schemas assign arrays an ordered meaning unless they explicitly say
    otherwise.  Missing or null ScopeVector positions become canonical nulls,
    empty arrays, or empty objects as required by the existing schema, while a
    typed sidecar records why each position remains unknown.
    """

    payload = _require_mapping(proposal, "proposal")
    extras = sorted(set(payload) - _CARD_FIELDS)
    if extras:
        _fail(
            "FRAME_FIELD_UNKNOWN",
            "proposal contains fields outside the canonical InsightCard",
            {"fields": extras},
        )

    # Falsifiability is the load-bearing I02 gate and receives a stable error
    # even if another required field is also absent.
    falsifier_value = payload.get("falsifiers", _MISSING)
    if falsifier_value is _MISSING:
        _fail("FALSIFIER_REQUIRED", "falsifiers are mandatory for every InsightCard")
    falsifiers = _require_sequence(
        falsifier_value,
        "falsifiers",
        minimum=1,
        code="FALSIFIER_REQUIRED",
    )

    scope, unknown_scope = _normalize_scope(_required(payload, "scope"))
    insight_id = _require_exact_text(_required(payload, "insight_id"), "insight_id")
    if _ID_PATTERN.fullmatch(insight_id) is None:
        _fail("FRAME_INPUT_INVALID", "insight_id does not match the canonical ID pattern")
    revision = _required(payload, "revision")
    if type(revision) is not int or revision < 1:
        _fail("FRAME_INPUT_INVALID", "revision must be an integer greater than or equal to 1")
    registration_hash = _require_exact_text(
        _required(payload, "registration_hash"), "registration_hash"
    )
    if _SHA256_PATTERN.fullmatch(registration_hash) is None:
        _fail(
            "FRAME_INPUT_INVALID",
            "registration_hash must be sha256 followed by 64 lowercase hex characters",
        )
    schema_version = _require_exact_text(
        _required(payload, "schema_version"), "schema_version"
    )
    if _SEMVER_PATTERN.fullmatch(schema_version) is None:
        _fail("FRAME_INPUT_INVALID", "schema_version must be a canonical semantic version")

    card: dict[str, object] = {
        "insight_id": insight_id,
        "revision": revision,
        "statement": _require_text(
            _required(payload, "statement"), "statement", minimum=10
        ),
        "scope": scope,
        "mechanism_path": _require_sequence(
            _required(payload, "mechanism_path"), "mechanism_path", minimum=1
        ),
        "predictions": _require_sequence(
            _required(payload, "predictions"), "predictions", minimum=1
        ),
        "falsifiers": falsifiers,
        "alternative_hypotheses": _require_sequence(
            _required(payload, "alternative_hypotheses"),
            "alternative_hypotheses",
            minimum=0,
        ),
        "null_model": _require_text(_required(payload, "null_model"), "null_model"),
        "registration_status": _require_enum(
            _required(payload, "registration_status"),
            "registration_status",
            _REGISTRATION_STATUSES,
        ),
        "lens_provenance": _require_sequence(
            _required(payload, "lens_provenance"), "lens_provenance", minimum=0
        ),
        "created_at": _validate_timestamp(_required(payload, "created_at")),
        "registration_hash": registration_hash,
        "risk_class": _require_enum(
            _required(payload, "risk_class"), "risk_class", _RISK_CLASSES
        ),
        "terms_to_define": _require_sequence(
            _required(payload, "terms_to_define"), "terms_to_define", minimum=0
        ),
        "decision_context": _require_text(
            _required(payload, "decision_context"), "decision_context"
        ),
        "created_by": _require_text(_required(payload, "created_by"), "created_by"),
        "schema_version": schema_version,
    }
    invalid_lenses = sorted(set(card["lens_provenance"]) - _LENS_VALUES)  # type: ignore[arg-type]
    if invalid_lenses:
        _fail(
            "FRAME_INPUT_INVALID",
            "lens_provenance contains a value outside the canonical vocabulary",
            {"values": invalid_lenses},
        )

    blockers = _council_blockers(card=card, scope=scope)
    if card["registration_status"] == "eligible" and blockers:
        _fail(
            "FRAME_ELIGIBILITY_CONFLICT",
            "an eligible InsightCard cannot retain a council admission blocker",
            {"blockers": list(blockers)},
        )

    canonical = _canonical_json(card)
    return FrameCompilation(
        compiler_version=FRAME_COMPILER_VERSION,
        _insight_card_json=canonical,
        unknown_scope=unknown_scope,
        council_ready=not blockers,
        council_blockers=blockers,
    )
