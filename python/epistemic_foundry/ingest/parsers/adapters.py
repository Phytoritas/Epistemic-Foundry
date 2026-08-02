"""Deterministic adapters for immutable GROBID, Docling, and fallback output.

K02 does not start parser services and does not discover versions from the
current machine.  A caller supplies a fully pinned backend identity and an
immutable output artifact.  This boundary validates that output, emits a
stable observation stream, and keeps parser failures, fallbacks, and
cross-parser disagreements visible.

The module deliberately does not choose one parser as document truth.  It
also does not emit canonical SourceSpan artifacts; K03 owns that projection.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping, Sequence


PARSER_ADAPTER_VERSION: Final = "4.0.0-k02.1"

_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_PARSER_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._/@:-]{0,127}$")
_VERSION_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/@:-]{0,127}$")
_ERROR_CODE_PATTERN: Final = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_FLOATING_VERSIONS: Final = frozenset(
    {"main", "master", "head", "latest", "stable", "nightly", "dev", "trunk"}
)
_RANGE_CHARACTERS: Final = frozenset("*^~<>=|, ")
_GROBID_MEDIA_TYPES: Final = frozenset(
    {"application/tei+xml", "application/xml", "text/xml"}
)
_JSON_MEDIA_TYPES: Final = frozenset(
    {"application/json", "application/vnd.docling+json"}
)
_NORMALIZED_ROOT_FIELDS: Final = frozenset(
    {"parser_version", "profile_hash", "elements"}
)
_NORMALIZED_ELEMENT_FIELDS: Final = frozenset(
    {
        "logical_address",
        "kind",
        "text",
        "page",
        "bbox",
        "char_start",
        "char_end",
        "reading_order",
        "links",
        "row_headers",
        "column_headers",
        "confidence",
    }
)
_ROLE_ORDER: Final = {
    "GROBID_STRUCTURE": 0,
    "DOCLING_LAYOUT": 1,
    "FALLBACK": 2,
}


class ParserRole(str, Enum):
    """Closed role vocabulary; backend product names remain explicit pins."""

    GROBID_STRUCTURE = "GROBID_STRUCTURE"
    DOCLING_LAYOUT = "DOCLING_LAYOUT"
    FALLBACK = "FALLBACK"


class ParserStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


class ElementKind(str, Enum):
    TITLE = "TITLE"
    SECTION_HEADING = "SECTION_HEADING"
    PARAGRAPH = "PARAGRAPH"
    REFERENCE = "REFERENCE"
    TABLE = "TABLE"
    TABLE_CELL = "TABLE_CELL"
    FIGURE = "FIGURE"
    CAPTION = "CAPTION"
    FORMULA = "FORMULA"


class FallbackDisposition(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PRIMARY_FAILED_NO_FALLBACK = "PRIMARY_FAILED_NO_FALLBACK"
    PRIMARY_BLOCKED_NO_FALLBACK = "PRIMARY_BLOCKED_NO_FALLBACK"
    FALLBACK_USED = "FALLBACK_USED"
    FALLBACK_FAILED = "FALLBACK_FAILED"
    FALLBACK_BLOCKED = "FALLBACK_BLOCKED"


class ParserContractError(ValueError):
    """Typed fail-closed K02 contract error."""

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
    raise ParserContractError(code, message, details)


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or "\x00" in value:
        _fail("PARSER_OUTPUT_INVALID", f"{label} must be a NUL-free string")
    if not allow_empty and not value:
        _fail("PARSER_OUTPUT_INVALID", f"{label} must be non-empty")
    if value != value.strip() and not allow_empty:
        _fail("PARSER_OUTPUT_INVALID", f"{label} must not contain edge whitespace")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ParserContractError(
            "PARSER_OUTPUT_INVALID",
            f"{label} must contain Unicode scalar values",
        ) from error
    return value


def _digest(value: object, label: str) -> str:
    candidate = _text(value, label)
    if _SHA256_PATTERN.fullmatch(candidate) is None:
        _fail(
            "PARSER_PIN_INVALID" if "pin" in label else "PARSER_OUTPUT_INVALID",
            f"{label} must be sha256 followed by 64 lowercase hexadecimal digits",
        )
    return candidate


def _exact_version(value: object) -> str:
    if type(value) is not str or "\x00" in value or not value:
        _fail("PARSER_PIN_INVALID", "exact_version must be a non-empty NUL-free string")
    if value != value.strip():
        _fail(
            "PARSER_PIN_FLOATING",
            "exact_version must not contain edge whitespace",
            {"actual": value},
        )
    candidate = value
    lowered = candidate.lower()
    if (
        _VERSION_PATTERN.fullmatch(candidate) is None
        or lowered in _FLOATING_VERSIONS
        or any(character in candidate for character in _RANGE_CHARACTERS)
        or any(token in lowered.split(".") for token in ("x", "latest", "snapshot"))
    ):
        _fail(
            "PARSER_PIN_FLOATING",
            "exact_version must be one immutable version or revision",
            {"actual": candidate},
        )
    return candidate


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
        raise ParserContractError(
            "PARSER_CANONICALIZATION_FAILED",
            "parser record must be finite canonical JSON",
        ) from error


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _sha256(_canonical_json(value))


def _bytes_snapshot(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    _fail("PARSER_ARTIFACT_INVALID", "payload must be bytes-like")


def _enum_value(value: object, enum_type: type[Enum], label: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    _fail(
        "PARSER_OUTPUT_INVALID",
        f"{label} must use the closed {enum_type.__name__} vocabulary",
    )


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("PARSER_OUTPUT_INVALID", f"{label} must be an array")
    values = tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(set(values)) != len(values):
        _fail("PARSER_OUTPUT_INVALID", f"{label} must not contain duplicates")
    return tuple(sorted(values))


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(
            "PARSER_OUTPUT_INVALID",
            f"{label} must be an integer greater than or equal to {minimum}",
        )
    return value


def _nullable_integer(value: object, label: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return _integer(value, label, minimum=minimum)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("PARSER_OUTPUT_INVALID", f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        _fail("PARSER_OUTPUT_INVALID", f"{label} must be a finite number")
    return 0.0 if number == 0 else number


@dataclass(frozen=True, slots=True)
class ParserPin:
    """Exact executable/profile identity supplied before parser execution."""

    parser_id: str
    role: ParserRole
    exact_version: str
    executable_digest: str
    adapter_version: str
    profile_hash: str

    def __post_init__(self) -> None:
        parser_id = _text(self.parser_id, "parser_id")
        if _PARSER_ID_PATTERN.fullmatch(parser_id) is None:
            _fail(
                "PARSER_PIN_INVALID",
                "parser_id must be a lowercase stable backend identifier",
            )
        _enum_value(self.role, ParserRole, "role")
        _exact_version(self.exact_version)
        _digest(self.executable_digest, "pin executable_digest")
        _digest(self.profile_hash, "pin profile_hash")
        if self.adapter_version != PARSER_ADAPTER_VERSION:
            _fail(
                "PARSER_ADAPTER_VERSION_MISMATCH",
                "pin must identify the active K02 adapter version",
                {
                    "expected": PARSER_ADAPTER_VERSION,
                    "actual": self.adapter_version,
                },
            )

    def projection(self) -> dict[str, object]:
        return {
            "adapter_version": self.adapter_version,
            "exact_version": self.exact_version,
            "executable_digest": self.executable_digest,
            "parser_id": self.parser_id,
            "profile_hash": self.profile_hash,
            "role": self.role.value,
        }


@dataclass(frozen=True, slots=True)
class ArtifactEnvelope:
    """Immutable snapshot of one parser output artifact."""

    artifact_id: str
    source_artifact_id: str
    media_type: str
    content_hash: str
    payload: bytes

    def __post_init__(self) -> None:
        _text(self.artifact_id, "artifact_id")
        _text(self.source_artifact_id, "source_artifact_id")
        _text(self.media_type, "media_type")
        _digest(self.content_hash, "content_hash")
        snapshot = _bytes_snapshot(self.payload)
        object.__setattr__(self, "payload", snapshot)
        observed = _sha256(snapshot)
        if observed != self.content_hash:
            _fail(
                "PARSER_ARTIFACT_HASH_MISMATCH",
                "parser output bytes do not match content_hash",
                {"expected": self.content_hash, "observed": observed},
            )

    def projection(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "source_artifact_id": self.source_artifact_id,
        }


@dataclass(frozen=True, slots=True)
class SourceLocator:
    page: int | None
    bbox: tuple[float, float, float, float] | None
    char_start: int | None
    char_end: int | None

    def __post_init__(self) -> None:
        if self.page is not None:
            _integer(self.page, "page", minimum=1)
        if self.bbox is not None:
            if self.page is None:
                _fail("PARSER_OUTPUT_INVALID", "bbox requires a page locator")
            if len(self.bbox) != 4:
                _fail("PARSER_OUTPUT_INVALID", "bbox must contain four coordinates")
            x0, y0, x1, y1 = (
                _finite_number(value, f"bbox[{index}]")
                for index, value in enumerate(self.bbox)
            )
            if x1 < x0 or y1 < y0:
                _fail("PARSER_OUTPUT_INVALID", "bbox must have non-negative extent")
            object.__setattr__(self, "bbox", (x0, y0, x1, y1))
        if (self.char_start is None) != (self.char_end is None):
            _fail(
                "PARSER_OUTPUT_INVALID",
                "char_start and char_end must be supplied together",
            )
        if self.char_start is not None and self.char_end is not None:
            _integer(self.char_start, "char_start")
            _integer(self.char_end, "char_end")
            if self.char_end < self.char_start:
                _fail("PARSER_OUTPUT_INVALID", "char_end must not precede char_start")
        if self.page is None and self.char_start is None:
            _fail(
                "PARSER_PROVENANCE_MISSING",
                "each parsed element needs a page or character-range locator",
            )

    def projection(self) -> dict[str, object]:
        return {
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "char_end": self.char_end,
            "char_start": self.char_start,
            "page": self.page,
        }


@dataclass(frozen=True, slots=True)
class ElementObservation:
    """One parser's immutable observation; never a reconciled truth value."""

    element_id: str
    logical_address: str
    kind: ElementKind
    text: str
    text_hash: str
    locator: SourceLocator
    reading_order: int
    links: tuple[str, ...]
    row_headers: tuple[str, ...]
    column_headers: tuple[str, ...]
    confidence: float | None
    parser_role: ParserRole
    parser_id: str
    parser_artifact_id: str
    source_artifact_id: str

    def __post_init__(self) -> None:
        _text(self.element_id, "element_id")
        _text(self.logical_address, "logical_address")
        _enum_value(self.kind, ElementKind, "kind")
        _text(self.text, "text", allow_empty=True)
        if _sha256(self.text.encode("utf-8")) != self.text_hash:
            _fail(
                "PARSER_ELEMENT_HASH_MISMATCH",
                "element text does not match text_hash",
            )
        if not isinstance(self.locator, SourceLocator):
            _fail("PARSER_OUTPUT_INVALID", "locator must be a SourceLocator")
        _integer(self.reading_order, "reading_order")
        for label, values in (
            ("links", self.links),
            ("row_headers", self.row_headers),
            ("column_headers", self.column_headers),
        ):
            if tuple(sorted(set(values))) != values:
                _fail(
                    "PARSER_OUTPUT_INVALID",
                    f"{label} must be sorted and duplicate-free",
                )
        if self.kind is ElementKind.CAPTION and not self.links:
            _fail("PARSER_LINKAGE_MISSING", "captions must address a figure or table")
        if self.kind is ElementKind.TABLE_CELL and (
            not self.row_headers or not self.column_headers
        ):
            _fail(
                "PARSER_TABLE_ADDRESS_MISSING",
                "table cells must retain row and column header addresses",
            )
        if self.confidence is not None:
            confidence = _finite_number(self.confidence, "confidence")
            if not 0 <= confidence <= 1:
                _fail("PARSER_OUTPUT_INVALID", "confidence must be between 0 and 1")
            object.__setattr__(self, "confidence", confidence)
        _enum_value(self.parser_role, ParserRole, "parser_role")
        _text(self.parser_id, "parser_id")
        _text(self.parser_artifact_id, "parser_artifact_id")
        _text(self.source_artifact_id, "source_artifact_id")

    def projection(self) -> dict[str, object]:
        return {
            "column_headers": list(self.column_headers),
            "confidence": self.confidence,
            "element_id": self.element_id,
            "kind": self.kind.value,
            "links": list(self.links),
            "locator": self.locator.projection(),
            "logical_address": self.logical_address,
            "parser_artifact_id": self.parser_artifact_id,
            "parser_id": self.parser_id,
            "parser_role": self.parser_role.value,
            "reading_order": self.reading_order,
            "row_headers": list(self.row_headers),
            "source_artifact_id": self.source_artifact_id,
            "text": self.text,
            "text_hash": self.text_hash,
        }


@dataclass(frozen=True, slots=True)
class ParserStream:
    pin: ParserPin
    artifact: ArtifactEnvelope
    status: ParserStatus
    elements: tuple[ElementObservation, ...]
    warnings: tuple[str, ...]
    stream_hash: str

    def __post_init__(self) -> None:
        if self.status not in (ParserStatus.PASS, ParserStatus.PARTIAL):
            _fail("PARSER_STREAM_INVALID", "successful streams must be PASS or PARTIAL")
        if not self.elements:
            _fail("PARSER_STREAM_EMPTY", "successful parser output must emit elements")
        if len({item.element_id for item in self.elements}) != len(self.elements):
            _fail("PARSER_ELEMENT_ID_CONFLICT", "element_id values must be unique")
        if len({item.logical_address for item in self.elements}) != len(self.elements):
            _fail(
                "PARSER_LOGICAL_ADDRESS_CONFLICT",
                "logical addresses must be unique within one stream",
            )
        if len({item.reading_order for item in self.elements}) != len(self.elements):
            _fail("PARSER_READING_ORDER_CONFLICT", "reading order must be unique")
        if tuple(sorted(set(self.warnings))) != self.warnings:
            _fail("PARSER_STREAM_INVALID", "warnings must be sorted and duplicate-free")
        expected = _stream_hash(
            self.pin,
            self.artifact,
            self.status,
            self.elements,
            self.warnings,
        )
        if expected != self.stream_hash:
            _fail("PARSER_STREAM_HASH_MISMATCH", "stream hash is not canonical")

    def projection(self) -> dict[str, object]:
        return {
            "artifact": self.artifact.projection(),
            "elements": [element.projection() for element in self.elements],
            "pin": self.pin.projection(),
            "status": self.status.value,
            "stream_hash": self.stream_hash,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ParserAttempt:
    pin: ParserPin
    status: ParserStatus
    stream: ParserStream | None
    error_code: str | None
    error_message: str | None

    def __post_init__(self) -> None:
        successful = self.status in (ParserStatus.PASS, ParserStatus.PARTIAL)
        if successful:
            if self.stream is None or self.error_code is not None or self.error_message is not None:
                _fail(
                    "PARSER_ATTEMPT_INVALID",
                    "successful attempts require one stream and no error",
                )
            if self.stream.pin != self.pin or self.stream.status is not self.status:
                _fail("PARSER_ATTEMPT_INVALID", "attempt and stream identity must match")
        else:
            if self.stream is not None or self.error_code is None or self.error_message is None:
                _fail(
                    "PARSER_ATTEMPT_INVALID",
                    "failed or blocked attempts require an error and no stream",
                )
            if _ERROR_CODE_PATTERN.fullmatch(self.error_code) is None:
                _fail("PARSER_ATTEMPT_INVALID", "error_code must be a stable code")
            _text(self.error_message, "error_message")

    def projection(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "pin": self.pin.projection(),
            "status": self.status.value,
            "stream_hash": self.stream.stream_hash if self.stream is not None else None,
        }


@dataclass(frozen=True, slots=True)
class FallbackResolution:
    disposition: FallbackDisposition
    terminal_status: ParserStatus
    primary: ParserAttempt
    fallback: ParserAttempt | None
    selected_stream: ParserStream | None
    resolution_hash: str

    def __post_init__(self) -> None:
        expected = _fallback_hash(
            self.disposition,
            self.terminal_status,
            self.primary,
            self.fallback,
            self.selected_stream,
        )
        if expected != self.resolution_hash:
            _fail("FALLBACK_HASH_MISMATCH", "fallback resolution hash is not canonical")

    def projection(self) -> dict[str, object]:
        return {
            "disposition": self.disposition.value,
            "fallback": self.fallback.projection() if self.fallback else None,
            "primary": self.primary.projection(),
            "resolution_hash": self.resolution_hash,
            "selected_stream_hash": (
                self.selected_stream.stream_hash if self.selected_stream else None
            ),
            "terminal_status": self.terminal_status.value,
        }


@dataclass(frozen=True, slots=True)
class ParserDisagreement:
    disagreement_id: str
    logical_address: str
    differing_fields: tuple[str, ...]
    observations: tuple[ElementObservation, ...]
    status: str

    def __post_init__(self) -> None:
        if self.status != "UNRESOLVED":
            _fail(
                "PARSER_DISAGREEMENT_INVALID",
                "new disagreements must remain explicitly UNRESOLVED",
            )
        if not self.differing_fields:
            _fail(
                "PARSER_DISAGREEMENT_INVALID",
                "disagreement requires at least one differing field",
            )

    def projection(self) -> dict[str, object]:
        return {
            "differing_fields": list(self.differing_fields),
            "disagreement_id": self.disagreement_id,
            "logical_address": self.logical_address,
            "observations": [item.projection() for item in self.observations],
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationComparison:
    source_artifact_id: str
    stream_hashes: tuple[str, ...]
    agreement_addresses: tuple[str, ...]
    disagreements: tuple[ParserDisagreement, ...]
    comparison_hash: str

    def __post_init__(self) -> None:
        expected = _hash_json(
            {
                "agreement_addresses": list(self.agreement_addresses),
                "disagreements": [item.projection() for item in self.disagreements],
                "source_artifact_id": self.source_artifact_id,
                "stream_hashes": list(self.stream_hashes),
            }
        )
        if expected != self.comparison_hash:
            _fail(
                "PARSER_COMPARISON_HASH_MISMATCH",
                "comparison hash is not canonical",
            )

    def projection(self) -> dict[str, object]:
        return {
            "agreement_addresses": list(self.agreement_addresses),
            "comparison_hash": self.comparison_hash,
            "disagreements": [item.projection() for item in self.disagreements],
            "source_artifact_id": self.source_artifact_id,
            "stream_hashes": list(self.stream_hashes),
        }


def _stream_hash(
    pin: ParserPin,
    artifact: ArtifactEnvelope,
    status: ParserStatus,
    elements: tuple[ElementObservation, ...],
    warnings: tuple[str, ...],
) -> str:
    return _hash_json(
        {
            "adapter_contract": PARSER_ADAPTER_VERSION,
            "artifact": artifact.projection(),
            "elements": [element.projection() for element in elements],
            "pin": pin.projection(),
            "status": status.value,
            "warnings": list(warnings),
        }
    )


def _make_stream(
    pin: ParserPin,
    artifact: ArtifactEnvelope,
    elements: Sequence[ElementObservation],
    warnings: Sequence[str] = (),
) -> ParserStream:
    ordered = tuple(sorted(elements, key=lambda item: (item.reading_order, item.element_id)))
    normalized_warnings = tuple(sorted(set(warnings)))
    status = ParserStatus.PARTIAL if normalized_warnings else ParserStatus.PASS
    digest = _stream_hash(pin, artifact, status, ordered, normalized_warnings)
    return ParserStream(pin, artifact, status, ordered, normalized_warnings, digest)


def _success(stream: ParserStream) -> ParserAttempt:
    return ParserAttempt(stream.pin, stream.status, stream, None, None)


def _failure(pin: ParserPin, error: ParserContractError) -> ParserAttempt:
    return ParserAttempt(pin, ParserStatus.FAIL, None, error.code, str(error))


def blocked_attempt(pin: ParserPin, code: str, message: str) -> ParserAttempt:
    """Record an unavailable credential/service/backend without faking output."""

    if _ERROR_CODE_PATTERN.fullmatch(code) is None:
        _fail("PARSER_ATTEMPT_INVALID", "blocked error code must be stable uppercase")
    _text(message, "message")
    return ParserAttempt(pin, ParserStatus.BLOCKED, None, code, message)


def _element_id(
    pin: ParserPin,
    artifact: ArtifactEnvelope,
    logical_address: str,
    kind: ElementKind,
) -> str:
    digest = _hash_json(
        {
            "artifact_hash": artifact.content_hash,
            "kind": kind.value,
            "logical_address": logical_address,
            "parser_id": pin.parser_id,
            "role": pin.role.value,
        }
    )
    return "PE-" + digest.removeprefix("sha256:")


def _observation(
    *,
    pin: ParserPin,
    artifact: ArtifactEnvelope,
    logical_address: str,
    kind: ElementKind,
    text: str,
    locator: SourceLocator,
    reading_order: int,
    links: Sequence[str] = (),
    row_headers: Sequence[str] = (),
    column_headers: Sequence[str] = (),
    confidence: float | None = None,
) -> ElementObservation:
    normalized_text = _text(text, "text", allow_empty=True)
    normalized_links = tuple(sorted(set(links)))
    normalized_rows = tuple(sorted(set(row_headers)))
    normalized_columns = tuple(sorted(set(column_headers)))
    return ElementObservation(
        element_id=_element_id(pin, artifact, logical_address, kind),
        logical_address=_text(logical_address, "logical_address"),
        kind=kind,
        text=normalized_text,
        text_hash=_sha256(normalized_text.encode("utf-8")),
        locator=locator,
        reading_order=reading_order,
        links=normalized_links,
        row_headers=normalized_rows,
        column_headers=normalized_columns,
        confidence=confidence,
        parser_role=pin.role,
        parser_id=pin.parser_id,
        parser_artifact_id=artifact.artifact_id,
        source_artifact_id=artifact.source_artifact_id,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _collapsed_text(node: ET.Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _tei_locator(node: ET.Element) -> SourceLocator:
    coords = node.attrib.get("coords")
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    if coords is not None:
        first = coords.split(";", 1)[0].split(",")
        if len(first) != 5:
            _fail("GROBID_OUTPUT_MALFORMED", "coords must use page,x,y,width,height")
        try:
            page = int(first[0])
            x, y, width, height = (float(value) for value in first[1:])
        except ValueError as error:
            raise ParserContractError(
                "GROBID_OUTPUT_MALFORMED",
                "coords must contain numeric values",
            ) from error
        if width < 0 or height < 0:
            _fail("GROBID_OUTPUT_MALFORMED", "coords extent must not be negative")
        bbox = (x, y, x + width, y + height)
    elif "data-page" in node.attrib:
        try:
            page = int(node.attrib["data-page"])
        except ValueError as error:
            raise ParserContractError(
                "GROBID_OUTPUT_MALFORMED",
                "data-page must be an integer",
            ) from error

    start_value = node.attrib.get("data-char-start")
    end_value = node.attrib.get("data-char-end")
    try:
        char_start = int(start_value) if start_value is not None else None
        char_end = int(end_value) if end_value is not None else None
    except ValueError as error:
        raise ParserContractError(
            "GROBID_OUTPUT_MALFORMED",
            "character locators must be integers",
        ) from error
    return SourceLocator(page, bbox, char_start, char_end)


def _tei_links(node: ET.Element) -> tuple[str, ...]:
    links: set[str] = set()
    for descendant in node.iter():
        target = descendant.attrib.get("target")
        if target:
            links.add(target)
    return tuple(sorted(links))


def _require_role(pin: ParserPin, role: ParserRole) -> None:
    if pin.role is not role:
        _fail(
            "PARSER_ROLE_MISMATCH",
            "parser pin role does not match the selected adapter",
            {"expected": role.value, "actual": pin.role.value},
        )


def adapt_grobid_artifact(
    pin: ParserPin,
    artifact: ArtifactEnvelope,
) -> ParserAttempt:
    """Validate retained TEI and project addressable scholarly observations."""

    try:
        _require_role(pin, ParserRole.GROBID_STRUCTURE)
        if artifact.media_type not in _GROBID_MEDIA_TYPES:
            _fail("GROBID_OUTPUT_MALFORMED", "GROBID output must be retained TEI XML")
        lowered = artifact.payload.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            _fail("GROBID_UNSAFE_XML", "DTD and entity declarations are forbidden")
        try:
            root = ET.fromstring(artifact.payload)
        except ET.ParseError as error:
            raise ParserContractError(
                "GROBID_OUTPUT_MALFORMED",
                "GROBID TEI is not well-formed XML",
            ) from error
        if _local_name(root.tag) != "TEI":
            _fail("GROBID_OUTPUT_MALFORMED", "GROBID root must be TEI")
        if root.attrib.get("data-parser-version") != pin.exact_version:
            _fail(
                "PARSER_PIN_OUTPUT_MISMATCH",
                "TEI parser version does not match the sealed pin",
            )
        if root.attrib.get("data-profile-hash") != pin.profile_hash:
            _fail(
                "PARSER_PIN_OUTPUT_MISMATCH",
                "TEI profile hash does not match the sealed pin",
            )

        elements: list[ElementObservation] = []
        reading_order = 0

        title_nodes = [node for node in root.iter() if _local_name(node.tag) == "title"]
        if title_nodes:
            title = title_nodes[0]
            text = _collapsed_text(title)
            if text:
                elements.append(
                    _observation(
                        pin=pin,
                        artifact=artifact,
                        logical_address="header/title",
                        kind=ElementKind.TITLE,
                        text=text,
                        locator=_tei_locator(title),
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

        body_nodes = [node for node in root.iter() if _local_name(node.tag) == "body"]
        if not body_nodes:
            _fail("GROBID_OUTPUT_MALFORMED", "TEI must contain a body")
        section_index = 0
        for div in (node for node in body_nodes[0].iter() if _local_name(node.tag) == "div"):
            direct_children = list(div)
            heads = [node for node in direct_children if _local_name(node.tag) == "head"]
            if heads and _collapsed_text(heads[0]):
                head = heads[0]
                elements.append(
                    _observation(
                        pin=pin,
                        artifact=artifact,
                        logical_address=f"body/section[{section_index}]/heading",
                        kind=ElementKind.SECTION_HEADING,
                        text=_collapsed_text(head),
                        locator=_tei_locator(head),
                        reading_order=reading_order,
                    )
                )
                reading_order += 1
            paragraph_index = 0
            for paragraph in (
                node for node in direct_children if _local_name(node.tag) == "p"
            ):
                text = _collapsed_text(paragraph)
                if not text:
                    continue
                elements.append(
                    _observation(
                        pin=pin,
                        artifact=artifact,
                        logical_address=(
                            f"body/section[{section_index}]/paragraph[{paragraph_index}]"
                        ),
                        kind=ElementKind.PARAGRAPH,
                        text=text,
                        locator=_tei_locator(paragraph),
                        reading_order=reading_order,
                        links=_tei_links(paragraph),
                    )
                )
                paragraph_index += 1
                reading_order += 1
            section_index += 1

        reference_index = 0
        for node in root.iter():
            if _local_name(node.tag) != "biblStruct":
                continue
            text = _collapsed_text(node)
            if not text:
                continue
            elements.append(
                _observation(
                    pin=pin,
                    artifact=artifact,
                    logical_address=f"references/reference[{reference_index}]",
                    kind=ElementKind.REFERENCE,
                    text=text,
                    locator=_tei_locator(node),
                    reading_order=reading_order,
                )
            )
            reference_index += 1
            reading_order += 1

        stream = _make_stream(pin, artifact, elements)
        return _success(stream)
    except ParserContractError as error:
        return _failure(pin, error)


def _json_object(payload: bytes) -> dict[str, object]:
    try:
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ParserContractError(
            "PARSER_OUTPUT_MALFORMED",
            "parser JSON output must be strict UTF-8 JSON",
        ) from error
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        _fail("PARSER_OUTPUT_MALFORMED", "parser JSON root must be an object")
    return value


def _bbox(value: object, *, required: bool) -> tuple[float, float, float, float] | None:
    if value is None:
        if required:
            _fail("PARSER_PROVENANCE_MISSING", "Docling elements require bbox")
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("PARSER_OUTPUT_INVALID", "bbox must be an array")
    if len(value) != 4:
        _fail("PARSER_OUTPUT_INVALID", "bbox must contain four coordinates")
    return tuple(_finite_number(item, f"bbox[{index}]") for index, item in enumerate(value))  # type: ignore[return-value]


def _confidence(value: object) -> float | None:
    if value is None:
        return None
    result = _finite_number(value, "confidence")
    if not 0 <= result <= 1:
        _fail("PARSER_OUTPUT_INVALID", "confidence must be between 0 and 1")
    return result


def _normalized_elements(
    *,
    pin: ParserPin,
    artifact: ArtifactEnvelope,
    root: Mapping[str, object],
    require_bbox: bool,
) -> tuple[ElementObservation, ...]:
    actual_root_fields = frozenset(root)
    if actual_root_fields != _NORMALIZED_ROOT_FIELDS:
        _fail(
            "PARSER_OUTPUT_MALFORMED",
            "normalized parser output must contain exactly the adapter fields",
            {
                "missing": sorted(_NORMALIZED_ROOT_FIELDS - actual_root_fields),
                "unexpected": sorted(actual_root_fields - _NORMALIZED_ROOT_FIELDS),
            },
        )
    if root["parser_version"] != pin.exact_version:
        _fail(
            "PARSER_PIN_OUTPUT_MISMATCH",
            "parser output version does not match the sealed pin",
        )
    if root["profile_hash"] != pin.profile_hash:
        _fail(
            "PARSER_PIN_OUTPUT_MISMATCH",
            "parser output profile does not match the sealed pin",
        )
    raw_elements = root["elements"]
    if not isinstance(raw_elements, list):
        _fail("PARSER_OUTPUT_MALFORMED", "elements must be an array")

    observations: list[ElementObservation] = []
    for index, raw_element in enumerate(raw_elements):
        if not isinstance(raw_element, dict) or any(
            type(key) is not str for key in raw_element
        ):
            _fail("PARSER_OUTPUT_MALFORMED", f"elements[{index}] must be an object")
        actual_fields = frozenset(raw_element)
        if actual_fields != _NORMALIZED_ELEMENT_FIELDS:
            _fail(
                "PARSER_OUTPUT_MALFORMED",
                f"elements[{index}] must contain exactly the normalized fields",
                {
                    "missing": sorted(_NORMALIZED_ELEMENT_FIELDS - actual_fields),
                    "unexpected": sorted(actual_fields - _NORMALIZED_ELEMENT_FIELDS),
                },
            )
        try:
            kind = ElementKind(raw_element["kind"])
        except (TypeError, ValueError) as error:
            raise ParserContractError(
                "PARSER_OUTPUT_INVALID",
                f"elements[{index}].kind uses an unknown value",
            ) from error
        page = _nullable_integer(raw_element["page"], "page", minimum=1)
        locator = SourceLocator(
            page=page,
            bbox=_bbox(raw_element["bbox"], required=require_bbox),
            char_start=_nullable_integer(raw_element["char_start"], "char_start"),
            char_end=_nullable_integer(raw_element["char_end"], "char_end"),
        )
        if require_bbox and page is None:
            _fail("PARSER_PROVENANCE_MISSING", "Docling elements require page")
        observations.append(
            _observation(
                pin=pin,
                artifact=artifact,
                logical_address=_text(
                    raw_element["logical_address"],
                    f"elements[{index}].logical_address",
                ),
                kind=kind,
                text=_text(raw_element["text"], f"elements[{index}].text", allow_empty=True),
                locator=locator,
                reading_order=_integer(
                    raw_element["reading_order"],
                    f"elements[{index}].reading_order",
                ),
                links=_string_tuple(raw_element["links"], f"elements[{index}].links"),
                row_headers=_string_tuple(
                    raw_element["row_headers"],
                    f"elements[{index}].row_headers",
                ),
                column_headers=_string_tuple(
                    raw_element["column_headers"],
                    f"elements[{index}].column_headers",
                ),
                confidence=_confidence(raw_element["confidence"]),
            )
        )
    return tuple(observations)


def adapt_docling_artifact(
    pin: ParserPin,
    artifact: ArtifactEnvelope,
) -> ParserAttempt:
    """Validate a pinned normalized Docling JSON artifact with layout locators."""

    try:
        _require_role(pin, ParserRole.DOCLING_LAYOUT)
        if artifact.media_type not in _JSON_MEDIA_TYPES:
            _fail("DOCLING_OUTPUT_MALFORMED", "Docling output must be JSON")
        root = _json_object(artifact.payload)
        stream = _make_stream(
            pin,
            artifact,
            _normalized_elements(
                pin=pin,
                artifact=artifact,
                root=root,
                require_bbox=True,
            ),
        )
        return _success(stream)
    except ParserContractError as error:
        return _failure(pin, error)


def adapt_fallback_artifact(
    pin: ParserPin,
    artifact: ArtifactEnvelope,
) -> ParserAttempt:
    """Validate a pinned fallback JSON artifact without upgrading its authority."""

    try:
        _require_role(pin, ParserRole.FALLBACK)
        if artifact.media_type not in _JSON_MEDIA_TYPES:
            _fail("FALLBACK_OUTPUT_MALFORMED", "fallback output must be JSON")
        root = _json_object(artifact.payload)
        stream = _make_stream(
            pin,
            artifact,
            _normalized_elements(
                pin=pin,
                artifact=artifact,
                root=root,
                require_bbox=False,
            ),
        )
        return _success(stream)
    except ParserContractError as error:
        return _failure(pin, error)


def _fallback_hash(
    disposition: FallbackDisposition,
    terminal_status: ParserStatus,
    primary: ParserAttempt,
    fallback: ParserAttempt | None,
    selected_stream: ParserStream | None,
) -> str:
    return _hash_json(
        {
            "disposition": disposition.value,
            "fallback": fallback.projection() if fallback else None,
            "primary": primary.projection(),
            "selected_stream_hash": selected_stream.stream_hash if selected_stream else None,
            "terminal_status": terminal_status.value,
        }
    )


def _fallback_resolution(
    disposition: FallbackDisposition,
    terminal_status: ParserStatus,
    primary: ParserAttempt,
    fallback: ParserAttempt | None,
    selected_stream: ParserStream | None,
) -> FallbackResolution:
    digest = _fallback_hash(
        disposition,
        terminal_status,
        primary,
        fallback,
        selected_stream,
    )
    return FallbackResolution(
        disposition,
        terminal_status,
        primary,
        fallback,
        selected_stream,
        digest,
    )


def resolve_fallback(
    primary: ParserAttempt,
    fallback: ParserAttempt | None = None,
) -> FallbackResolution:
    """Apply a fallback without erasing the primary attempt or its typed failure."""

    if primary.pin.role is ParserRole.FALLBACK:
        _fail("FALLBACK_PRIMARY_INVALID", "primary attempt cannot use the fallback role")
    if fallback is not None and fallback.pin.role is not ParserRole.FALLBACK:
        _fail("FALLBACK_ROLE_MISMATCH", "fallback attempt must use the fallback role")

    if primary.status in (ParserStatus.PASS, ParserStatus.PARTIAL):
        if fallback is not None:
            _fail(
                "FALLBACK_NOT_ALLOWED",
                "fallback output cannot replace a successful primary parser",
            )
        return _fallback_resolution(
            FallbackDisposition.NOT_REQUIRED,
            primary.status,
            primary,
            None,
            primary.stream,
        )

    if fallback is None:
        disposition = (
            FallbackDisposition.PRIMARY_BLOCKED_NO_FALLBACK
            if primary.status is ParserStatus.BLOCKED
            else FallbackDisposition.PRIMARY_FAILED_NO_FALLBACK
        )
        return _fallback_resolution(
            disposition,
            primary.status,
            primary,
            None,
            None,
        )

    if fallback.status in (ParserStatus.PASS, ParserStatus.PARTIAL):
        return _fallback_resolution(
            FallbackDisposition.FALLBACK_USED,
            ParserStatus.PARTIAL,
            primary,
            fallback,
            fallback.stream,
        )
    if fallback.status is ParserStatus.BLOCKED:
        return _fallback_resolution(
            FallbackDisposition.FALLBACK_BLOCKED,
            ParserStatus.BLOCKED,
            primary,
            fallback,
            None,
        )
    return _fallback_resolution(
        FallbackDisposition.FALLBACK_FAILED,
        ParserStatus.FAIL,
        primary,
        fallback,
        None,
    )


def _stream_sort_key(stream: ParserStream) -> tuple[int, str, str]:
    return (
        _ROLE_ORDER[stream.pin.role.value],
        stream.pin.parser_id,
        stream.stream_hash,
    )


def _observation_sort_key(
    observation: ElementObservation,
) -> tuple[int, str, str]:
    return (
        _ROLE_ORDER[observation.parser_role.value],
        observation.parser_id,
        observation.element_id,
    )


def _differing_fields(
    observations: tuple[ElementObservation, ...],
    expected_count: int,
) -> tuple[str, ...]:
    fields: list[str] = []
    if len(observations) != expected_count:
        fields.append("missing_observation")
    projections: tuple[tuple[str, tuple[object, ...]], ...] = (
        ("kind", tuple(item.kind.value for item in observations)),
        ("text_hash", tuple(item.text_hash for item in observations)),
        ("locator", tuple(_canonical_json(item.locator.projection()) for item in observations)),
        ("reading_order", tuple(item.reading_order for item in observations)),
        ("links", tuple(item.links for item in observations)),
        ("row_headers", tuple(item.row_headers for item in observations)),
        ("column_headers", tuple(item.column_headers for item in observations)),
    )
    for name, values in projections:
        if len(set(values)) > 1:
            fields.append(name)
    return tuple(sorted(fields))


def compare_parser_streams(
    streams: Sequence[ParserStream],
) -> ReconciliationComparison:
    """Compare parser observations without selecting or inventing merged text."""

    if len(streams) < 2:
        _fail("PARSER_COMPARISON_INVALID", "at least two parser streams are required")
    if any(not isinstance(stream, ParserStream) for stream in streams):
        _fail("PARSER_COMPARISON_INVALID", "all inputs must be ParserStream values")
    ordered_streams = tuple(sorted(streams, key=_stream_sort_key))
    identities = tuple((stream.pin.role.value, stream.pin.parser_id) for stream in ordered_streams)
    if len(set(identities)) != len(identities):
        _fail("PARSER_COMPARISON_INVALID", "parser stream identities must be unique")
    source_ids = {stream.artifact.source_artifact_id for stream in ordered_streams}
    if len(source_ids) != 1:
        _fail(
            "PARSER_SOURCE_MISMATCH",
            "parser streams must describe the same immutable source artifact",
        )

    by_address: dict[str, list[ElementObservation]] = {}
    for stream in ordered_streams:
        for observation in stream.elements:
            by_address.setdefault(observation.logical_address, []).append(observation)

    agreements: list[str] = []
    disagreements: list[ParserDisagreement] = []
    for address in sorted(by_address):
        observations = tuple(sorted(by_address[address], key=_observation_sort_key))
        fields = _differing_fields(observations, len(ordered_streams))
        if not fields:
            agreements.append(address)
            continue
        preimage = {
            "differing_fields": list(fields),
            "logical_address": address,
            "observations": [item.projection() for item in observations],
            "status": "UNRESOLVED",
        }
        disagreement_id = "PD-" + _hash_json(preimage).removeprefix("sha256:")
        disagreements.append(
            ParserDisagreement(
                disagreement_id,
                address,
                fields,
                observations,
                "UNRESOLVED",
            )
        )

    source_artifact_id = next(iter(source_ids))
    stream_hashes = tuple(stream.stream_hash for stream in ordered_streams)
    comparison_preimage = {
        "agreement_addresses": agreements,
        "disagreements": [item.projection() for item in disagreements],
        "source_artifact_id": source_artifact_id,
        "stream_hashes": list(stream_hashes),
    }
    return ReconciliationComparison(
        source_artifact_id=source_artifact_id,
        stream_hashes=stream_hashes,
        agreement_addresses=tuple(agreements),
        disagreements=tuple(disagreements),
        comparison_hash=_hash_json(comparison_preimage),
    )
