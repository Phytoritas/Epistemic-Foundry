"""Deterministic SourceSpan emission and source-bound round-trip verification.

K03 owns the ingest boundary that projects a normalized immutable source text
into canonical ``SourceSpan`` records.  The caller may propose locators and
typed metadata, but it cannot supply the emitted verbatim text, text hash, or
span identifier.  Those values are derived from the sealed source snapshot.

This module does not redefine ``schemas/source-span.schema.json`` and does not
choose between parser observations.  Parser reconciliation is an upstream
concern; K03 preserves the supplied reconciliation status and fails closed
when a span cannot be resolved to the exact document version and provenance.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping, Sequence


SOURCE_SPAN_EMITTER_VERSION: Final = "4.0.0-k03.1"

_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_SPAN_ID_PATTERN: Final = re.compile(r"^SPAN-[0-9a-f]{64}$")
_VERSION_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/@:-]{0,127}$")
_FLOATING_VERSIONS: Final = frozenset(
    {"main", "master", "head", "latest", "stable", "nightly", "dev", "trunk"}
)
_RANGE_CHARACTERS: Final = frozenset("*^~<>=|, ")
_SOURCE_SPAN_FIELDS: Final = frozenset(
    {
        "span_id",
        "document_id",
        "paper_version_id",
        "page",
        "section",
        "semantic_unit",
        "bbox",
        "char_start",
        "char_end",
        "verbatim_text",
        "text_hash",
        "parser_name",
        "parser_version",
        "coordinate_system",
        "reconciliation_status",
        "provenance_manifest_id",
    }
)


class SpanKind(str, Enum):
    """Closed K03 input vocabulary for the four required emission classes."""

    TEXT = "TEXT"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    FORMULA = "FORMULA"


class SemanticUnit(str, Enum):
    """Vocabulary owned by the canonical SourceSpan schema."""

    TITLE = "title"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    FIGURE_CAPTION = "figure_caption"
    TABLE_CAPTION = "table_caption"
    TABLE_CELL = "table_cell"
    EQUATION = "equation"
    FOOTNOTE = "footnote"
    REFERENCE = "reference"
    OTHER = "other"


class CoordinateSystem(str, Enum):
    PDF_POINTS_BOTTOM_LEFT = "pdf_points_bottom_left"
    PDF_POINTS_TOP_LEFT = "pdf_points_top_left"
    NORMALIZED_TOP_LEFT = "normalized_top_left"
    NOT_AVAILABLE = "not_available"


class ReconciliationStatus(str, Enum):
    SINGLE_PARSER = "single_parser"
    AGREED = "agreed"
    CONFLICT_RECORDED = "conflict_recorded"
    HUMAN_RESOLVED = "human_resolved"


_KIND_UNITS: Final = {
    SpanKind.TEXT: frozenset(
        {
            SemanticUnit.TITLE,
            SemanticUnit.ABSTRACT,
            SemanticUnit.INTRODUCTION,
            SemanticUnit.METHODS,
            SemanticUnit.RESULTS,
            SemanticUnit.DISCUSSION,
            SemanticUnit.CONCLUSION,
            SemanticUnit.FOOTNOTE,
            SemanticUnit.REFERENCE,
            SemanticUnit.OTHER,
        }
    ),
    SpanKind.TABLE: frozenset(
        {SemanticUnit.TABLE_CAPTION, SemanticUnit.TABLE_CELL}
    ),
    SpanKind.FIGURE: frozenset({SemanticUnit.FIGURE_CAPTION}),
    SpanKind.FORMULA: frozenset({SemanticUnit.EQUATION}),
}


class SourceSpanContractError(ValueError):
    """Typed fail-closed error at the K03 SourceSpan boundary."""

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
    raise SourceSpanContractError(code, message, details)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SourceSpanContractError(
            "SOURCE_SPAN_CANONICALIZATION_FAILED",
            "SourceSpan identity preimage must be finite canonical JSON",
        ) from error


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or "\x00" in value:
        _fail("SOURCE_SPAN_INPUT_INVALID", f"{label} must be a NUL-free string")
    if not allow_empty and not value:
        _fail("SOURCE_SPAN_INPUT_INVALID", f"{label} must be non-empty")
    if not allow_empty and value != value.strip():
        _fail("SOURCE_SPAN_INPUT_INVALID", f"{label} must not have edge whitespace")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise SourceSpanContractError(
            "SOURCE_SPAN_INPUT_INVALID",
            f"{label} must contain Unicode scalar values",
        ) from error
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            f"{label} must be an integer greater than or equal to {minimum}",
        )
    return value


def _digest(value: object, label: str) -> str:
    candidate = _text(value, label)
    if _SHA256_PATTERN.fullmatch(candidate) is None:
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            f"{label} must be sha256 followed by 64 lowercase hexadecimal digits",
        )
    return candidate


def _exact_version(value: object) -> str:
    candidate = _text(value, "parser_version")
    lowered = candidate.lower()
    if (
        _VERSION_PATTERN.fullmatch(candidate) is None
        or lowered in _FLOATING_VERSIONS
        or any(character in candidate for character in _RANGE_CHARACTERS)
        or any(token in lowered.split(".") for token in ("x", "latest", "snapshot"))
    ):
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            "parser_version must identify one exact version or revision",
            {"actual": candidate},
        )
    return candidate


def _enum(value: object, enum_type: type[Enum], label: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    _fail(
        "SOURCE_SPAN_INPUT_INVALID",
        f"{label} must use the closed {enum_type.__name__} vocabulary",
    )


def _parse_enum(value: object, enum_type: type[Enum], label: str) -> Enum:
    if type(value) is not str:
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            f"persisted {label} must be a canonical string",
        )
    try:
        return enum_type(value)
    except ValueError as error:
        raise SourceSpanContractError(
            "SOURCE_SPAN_INPUT_INVALID",
            f"persisted {label} uses an unknown value",
            {"actual": value},
        ) from error


def _bbox(
    value: object,
    coordinate_system: CoordinateSystem,
) -> tuple[float, float, float, float] | None:
    if value is None:
        if coordinate_system is not CoordinateSystem.NOT_AVAILABLE:
            _fail(
                "SOURCE_SPAN_INPUT_INVALID",
                "bbox=null requires coordinate_system=not_available",
            )
        return None
    if coordinate_system is CoordinateSystem.NOT_AVAILABLE:
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            "a bbox requires an explicit coordinate system",
        )
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("SOURCE_SPAN_INPUT_INVALID", "bbox must be null or four numbers")
    if len(value) != 4:
        _fail("SOURCE_SPAN_INPUT_INVALID", "bbox must contain exactly four numbers")
    values: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            _fail("SOURCE_SPAN_INPUT_INVALID", f"bbox[{index}] must be numeric")
        number = float(item)
        if not math.isfinite(number):
            _fail("SOURCE_SPAN_INPUT_INVALID", f"bbox[{index}] must be finite")
        values.append(0.0 if number == 0 else number)
    x0, y0, x1, y1 = values
    if min(values) < 0 or x1 <= x0 or y1 <= y0:
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            "bbox must have non-negative coordinates and positive extent",
        )
    if coordinate_system is CoordinateSystem.NORMALIZED_TOP_LEFT and any(
        number > 1 for number in values
    ):
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            "normalized_top_left bbox values must be between zero and one",
        )
    return x0, y0, x1, y1


def _validate_range(char_start: object, char_end: object) -> tuple[int, int]:
    start = _integer(char_start, "char_start")
    end = _integer(char_end, "char_end", minimum=1)
    if end <= start:
        _fail(
            "SOURCE_SPAN_RANGE_INVALID",
            "char_end must be greater than char_start",
            {"char_start": start, "char_end": end},
        )
    return start, end


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Immutable normalized text and its exact version/provenance identity."""

    document_id: str
    paper_version_id: str
    provenance_manifest_id: str
    source_text: str
    source_text_hash: str

    def __post_init__(self) -> None:
        _text(self.document_id, "document_id")
        _text(self.paper_version_id, "paper_version_id")
        _text(self.provenance_manifest_id, "provenance_manifest_id")
        source_text = _text(self.source_text, "source_text", allow_empty=True)
        if not source_text:
            _fail(
                "SOURCE_SPAN_ORPHANED",
                "a source snapshot must contain normalized text",
            )
        _digest(self.source_text_hash, "source_text_hash")
        observed = _sha256(source_text.encode("utf-8"))
        if observed != self.source_text_hash:
            _fail(
                "SOURCE_SPAN_SOURCE_HASH_MISMATCH",
                "source text bytes do not match source_text_hash",
                {"expected": self.source_text_hash, "observed": observed},
            )

    @classmethod
    def capture(
        cls,
        *,
        document_id: str,
        paper_version_id: str,
        provenance_manifest_id: str,
        content: str | bytes | bytearray | memoryview,
        expected_hash: str | None = None,
    ) -> SourceSnapshot:
        """Copy UTF-8 source content and seal its digest before span emission."""

        if isinstance(content, str):
            source_text = content[:]
        elif isinstance(content, (bytes, bytearray, memoryview)):
            try:
                source_text = bytes(content).decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise SourceSpanContractError(
                    "SOURCE_SPAN_INPUT_INVALID",
                    "source bytes must be valid UTF-8",
                ) from error
        else:
            _fail(
                "SOURCE_SPAN_INPUT_INVALID",
                "source content must be text or immutable UTF-8 bytes",
            )
        observed = _sha256(source_text.encode("utf-8"))
        if expected_hash is not None and _digest(expected_hash, "expected_hash") != observed:
            _fail(
                "SOURCE_SPAN_SOURCE_HASH_MISMATCH",
                "captured source text does not match expected_hash",
                {"expected": expected_hash, "observed": observed},
            )
        return cls(
            document_id=document_id,
            paper_version_id=paper_version_id,
            provenance_manifest_id=provenance_manifest_id,
            source_text=source_text,
            source_text_hash=observed,
        )

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.document_id, self.paper_version_id, self.provenance_manifest_id


@dataclass(frozen=True, slots=True)
class SpanCandidate:
    """Typed locator proposal; source-derived fields are intentionally absent."""

    kind: SpanKind
    page: int
    section: str | None
    semantic_unit: SemanticUnit
    bbox: tuple[float, float, float, float] | None
    char_start: int
    char_end: int
    parser_name: str
    parser_version: str
    coordinate_system: CoordinateSystem
    reconciliation_status: ReconciliationStatus

    def __post_init__(self) -> None:
        kind = _enum(self.kind, SpanKind, "kind")
        _integer(self.page, "page", minimum=1)
        if self.section is not None:
            _text(self.section, "section")
        unit = _enum(self.semantic_unit, SemanticUnit, "semantic_unit")
        coordinate_system = _enum(
            self.coordinate_system,
            CoordinateSystem,
            "coordinate_system",
        )
        normalized_bbox = _bbox(self.bbox, coordinate_system)  # type: ignore[arg-type]
        object.__setattr__(self, "bbox", normalized_bbox)
        _validate_range(self.char_start, self.char_end)
        _text(self.parser_name, "parser_name")
        _exact_version(self.parser_version)
        _enum(
            self.reconciliation_status,
            ReconciliationStatus,
            "reconciliation_status",
        )
        if unit not in _KIND_UNITS[kind]:  # type: ignore[index]
            _fail(
                "SOURCE_SPAN_INPUT_INVALID",
                "semantic_unit is incompatible with the candidate kind",
                {"kind": kind.value, "semantic_unit": unit.value},
            )


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Canonical SourceSpan value with exactly the schema-defined properties."""

    span_id: str
    document_id: str
    paper_version_id: str
    page: int
    section: str | None
    semantic_unit: SemanticUnit
    bbox: tuple[float, float, float, float] | None
    char_start: int
    char_end: int
    verbatim_text: str
    text_hash: str
    parser_name: str
    parser_version: str
    coordinate_system: CoordinateSystem
    reconciliation_status: ReconciliationStatus
    provenance_manifest_id: str

    def __post_init__(self) -> None:
        if type(self.span_id) is not str or _SPAN_ID_PATTERN.fullmatch(self.span_id) is None:
            _fail(
                "SOURCE_SPAN_ID_MISMATCH",
                "span_id must be a K03 content-addressed identifier",
            )
        _text(self.document_id, "document_id")
        _text(self.paper_version_id, "paper_version_id")
        _integer(self.page, "page", minimum=1)
        if self.section is not None:
            _text(self.section, "section")
        _enum(self.semantic_unit, SemanticUnit, "semantic_unit")
        coordinate_system = _enum(
            self.coordinate_system,
            CoordinateSystem,
            "coordinate_system",
        )
        normalized_bbox = _bbox(self.bbox, coordinate_system)  # type: ignore[arg-type]
        object.__setattr__(self, "bbox", normalized_bbox)
        start, end = _validate_range(self.char_start, self.char_end)
        verbatim_text = _text(self.verbatim_text, "verbatim_text")
        if end - start != len(verbatim_text):
            _fail(
                "SOURCE_SPAN_RANGE_INVALID",
                "character range width must equal verbatim_text length",
            )
        _digest(self.text_hash, "text_hash")
        observed = _sha256(verbatim_text.encode("utf-8"))
        if observed != self.text_hash:
            _fail(
                "SOURCE_SPAN_TEXT_HASH_MISMATCH",
                "verbatim_text does not match text_hash",
                {"expected": self.text_hash, "observed": observed},
            )
        _text(self.parser_name, "parser_name")
        _exact_version(self.parser_version)
        _enum(
            self.reconciliation_status,
            ReconciliationStatus,
            "reconciliation_status",
        )
        _text(self.provenance_manifest_id, "provenance_manifest_id")

    def projection(self) -> dict[str, object]:
        """Return the canonical JSON-schema projection without extra authority."""

        return {
            "span_id": self.span_id,
            "document_id": self.document_id,
            "paper_version_id": self.paper_version_id,
            "page": self.page,
            "section": self.section,
            "semantic_unit": self.semantic_unit.value,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "verbatim_text": self.verbatim_text,
            "text_hash": self.text_hash,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "coordinate_system": self.coordinate_system.value,
            "reconciliation_status": self.reconciliation_status.value,
            "provenance_manifest_id": self.provenance_manifest_id,
        }


def _verify_snapshot_integrity(snapshot: SourceSnapshot) -> None:
    if not isinstance(snapshot, SourceSnapshot):
        _fail("SOURCE_SPAN_INPUT_INVALID", "source must be a SourceSnapshot")
    observed = _sha256(snapshot.source_text.encode("utf-8"))
    if observed != snapshot.source_text_hash:
        _fail(
            "SOURCE_SPAN_SOURCE_HASH_MISMATCH",
            "source snapshot changed after it was sealed",
            {"expected": snapshot.source_text_hash, "observed": observed},
        )


def _span_identifier(snapshot: SourceSnapshot, projection: Mapping[str, object]) -> str:
    semantic_fields = {key: projection[key] for key in sorted(projection) if key != "span_id"}
    preimage = {
        "emitter_version": SOURCE_SPAN_EMITTER_VERSION,
        "source_text_hash": snapshot.source_text_hash,
        "span": semantic_fields,
    }
    return "SPAN-" + hashlib.sha256(_canonical_json(preimage)).hexdigest()


def emit_source_span(snapshot: SourceSnapshot, candidate: SpanCandidate) -> SourceSpan:
    """Derive one immutable SourceSpan exclusively from a sealed source slice."""

    _verify_snapshot_integrity(snapshot)
    if not isinstance(candidate, SpanCandidate):
        _fail("SOURCE_SPAN_INPUT_INVALID", "candidate must be a SpanCandidate")
    if candidate.char_end > len(snapshot.source_text):
        _fail(
            "SOURCE_SPAN_RANGE_INVALID",
            "candidate range extends beyond the sealed source text",
            {"char_end": candidate.char_end, "source_length": len(snapshot.source_text)},
        )
    verbatim_text = snapshot.source_text[candidate.char_start : candidate.char_end]
    if not verbatim_text:
        _fail("SOURCE_SPAN_RANGE_INVALID", "candidate range resolves to empty text")
    values: dict[str, object] = {
        "span_id": "SPAN-" + ("0" * 64),
        "document_id": snapshot.document_id,
        "paper_version_id": snapshot.paper_version_id,
        "page": candidate.page,
        "section": candidate.section,
        "semantic_unit": candidate.semantic_unit.value,
        "bbox": list(candidate.bbox) if candidate.bbox is not None else None,
        "char_start": candidate.char_start,
        "char_end": candidate.char_end,
        "verbatim_text": verbatim_text,
        "text_hash": _sha256(verbatim_text.encode("utf-8")),
        "parser_name": candidate.parser_name,
        "parser_version": candidate.parser_version,
        "coordinate_system": candidate.coordinate_system.value,
        "reconciliation_status": candidate.reconciliation_status.value,
        "provenance_manifest_id": snapshot.provenance_manifest_id,
    }
    values["span_id"] = _span_identifier(snapshot, values)
    return source_span_from_mapping(values)


def emit_source_spans(
    snapshot: SourceSnapshot,
    candidates: Sequence[SpanCandidate],
) -> tuple[SourceSpan, ...]:
    """Emit an ordered batch and reject duplicate content-addressed spans."""

    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes, bytearray)):
        _fail("SOURCE_SPAN_INPUT_INVALID", "candidates must be a sequence")
    emitted = tuple(emit_source_span(snapshot, candidate) for candidate in candidates)
    identifiers = tuple(span.span_id for span in emitted)
    if len(set(identifiers)) != len(identifiers):
        _fail(
            "SOURCE_SPAN_ID_MISMATCH",
            "one emission batch must not contain duplicate spans",
        )
    return emitted


def emit(
    snapshot: SourceSnapshot,
    candidates: Sequence[SpanCandidate],
) -> tuple[SourceSpan, ...]:
    """Workflow entry point for ``epistemic_foundry.ingest.spans:emit``."""

    return emit_source_spans(snapshot, candidates)


def source_span_from_mapping(value: Mapping[str, object]) -> SourceSpan:
    """Parse a persisted canonical record without tolerating unknown fields."""

    if not isinstance(value, Mapping):
        _fail("SOURCE_SPAN_INPUT_INVALID", "persisted SourceSpan must be an object")
    actual_fields = frozenset(value)
    if actual_fields != _SOURCE_SPAN_FIELDS:
        _fail(
            "SOURCE_SPAN_INPUT_INVALID",
            "persisted SourceSpan fields must exactly match the canonical schema",
            {
                "missing": sorted(_SOURCE_SPAN_FIELDS - actual_fields),
                "extra": sorted(actual_fields - _SOURCE_SPAN_FIELDS),
            },
        )
    section = value["section"]
    if section is not None:
        section = _text(section, "section")
    coordinate_system = _parse_enum(
        value["coordinate_system"],
        CoordinateSystem,
        "coordinate_system",
    )
    bbox = _bbox(value["bbox"], coordinate_system)  # type: ignore[arg-type]
    return SourceSpan(
        span_id=_text(value["span_id"], "span_id"),
        document_id=_text(value["document_id"], "document_id"),
        paper_version_id=_text(value["paper_version_id"], "paper_version_id"),
        page=_integer(value["page"], "page", minimum=1),
        section=section,
        semantic_unit=_parse_enum(
            value["semantic_unit"],
            SemanticUnit,
            "semantic_unit",
        ),  # type: ignore[arg-type]
        bbox=bbox,
        char_start=_integer(value["char_start"], "char_start"),
        char_end=_integer(value["char_end"], "char_end", minimum=1),
        verbatim_text=_text(value["verbatim_text"], "verbatim_text"),
        text_hash=_digest(value["text_hash"], "text_hash"),
        parser_name=_text(value["parser_name"], "parser_name"),
        parser_version=_exact_version(value["parser_version"]),
        coordinate_system=coordinate_system,  # type: ignore[arg-type]
        reconciliation_status=_parse_enum(
            value["reconciliation_status"],
            ReconciliationStatus,
            "reconciliation_status",
        ),  # type: ignore[arg-type]
        provenance_manifest_id=_text(
            value["provenance_manifest_id"],
            "provenance_manifest_id",
        ),
    )


def verify_source_span(
    span: SourceSpan | Mapping[str, object],
    snapshot: SourceSnapshot,
) -> str:
    """Resolve a span to the exact source text or raise a typed integrity error."""

    record = span if isinstance(span, SourceSpan) else source_span_from_mapping(span)
    _verify_snapshot_integrity(snapshot)
    if (record.document_id, record.paper_version_id) != (
        snapshot.document_id,
        snapshot.paper_version_id,
    ):
        _fail(
            "SOURCE_SPAN_ORPHANED",
            "span document/version identity does not match the source snapshot",
        )
    if record.provenance_manifest_id != snapshot.provenance_manifest_id:
        _fail(
            "SOURCE_SPAN_PROVENANCE_MISMATCH",
            "span provenance does not match the source snapshot",
        )
    if record.char_end > len(snapshot.source_text):
        _fail(
            "SOURCE_SPAN_RANGE_INVALID",
            "persisted span range extends beyond the source snapshot",
        )
    actual = snapshot.source_text[record.char_start : record.char_end]
    if actual != record.verbatim_text:
        _fail(
            "SOURCE_SPAN_TEXT_HASH_MISMATCH",
            "persisted verbatim text does not resolve at the recorded source range",
            {
                "expected_hash": record.text_hash,
                "observed_hash": _sha256(actual.encode("utf-8")),
            },
        )
    if _sha256(actual.encode("utf-8")) != record.text_hash:
        _fail(
            "SOURCE_SPAN_TEXT_HASH_MISMATCH",
            "resolved source slice does not match text_hash",
        )
    expected_id = _span_identifier(snapshot, record.projection())
    if expected_id != record.span_id:
        _fail(
            "SOURCE_SPAN_ID_MISMATCH",
            "span identifier is not bound to this exact source snapshot and locator",
            {"expected": expected_id, "observed": record.span_id},
        )
    return actual


class SourceSnapshotIndex:
    """Exact identity index used to detect orphaned and provenance-stale spans."""

    __slots__ = ("_snapshots", "_document_versions")

    def __init__(self, snapshots: Sequence[SourceSnapshot]) -> None:
        if not isinstance(snapshots, Sequence) or isinstance(
            snapshots, (str, bytes, bytearray)
        ):
            _fail("SOURCE_SPAN_INPUT_INVALID", "snapshots must be a sequence")
        by_identity: dict[tuple[str, str, str], SourceSnapshot] = {}
        document_versions: set[tuple[str, str]] = set()
        for snapshot in snapshots:
            _verify_snapshot_integrity(snapshot)
            if snapshot.identity in by_identity:
                _fail(
                    "SOURCE_SPAN_INPUT_INVALID",
                    "snapshot identity values must be unique",
                )
            by_identity[snapshot.identity] = snapshot
            document_versions.add((snapshot.document_id, snapshot.paper_version_id))
        self._snapshots = MappingProxyType(by_identity)
        self._document_versions = frozenset(document_versions)

    def resolve(self, span: SourceSpan | Mapping[str, object]) -> str:
        record = span if isinstance(span, SourceSpan) else source_span_from_mapping(span)
        key = (
            record.document_id,
            record.paper_version_id,
            record.provenance_manifest_id,
        )
        snapshot = self._snapshots.get(key)
        if snapshot is None:
            if (record.document_id, record.paper_version_id) in self._document_versions:
                _fail(
                    "SOURCE_SPAN_PROVENANCE_MISMATCH",
                    "document version exists but the span provenance is unknown",
                )
            _fail(
                "SOURCE_SPAN_ORPHANED",
                "no immutable source snapshot resolves the span document version",
            )
        return verify_source_span(record, snapshot)


def resolve_source_span(
    span: SourceSpan | Mapping[str, object],
    snapshots: Sequence[SourceSnapshot],
) -> str:
    """Resolve one span through an exact source identity index."""

    return SourceSnapshotIndex(snapshots).resolve(span)


def resolve_source_spans(
    spans: Sequence[SourceSpan | Mapping[str, object]],
    snapshots: Sequence[SourceSnapshot],
) -> tuple[str, ...]:
    """Resolve every span; one orphan or integrity failure rejects the batch."""

    if not isinstance(spans, Sequence) or isinstance(spans, (str, bytes, bytearray)):
        _fail("SOURCE_SPAN_INPUT_INVALID", "spans must be a sequence")
    index = SourceSnapshotIndex(snapshots)
    return tuple(index.resolve(span) for span in spans)
