"""Source-span construction and verbatim verification.

Contract source: `schemas/source-span.schema.json`.

A span is the anchor that makes a claim checkable. Two rules are enforced:

* `text_hash` is computed from the span's own verbatim text, so a later edit to
  either the text or the hash is detectable by recomputation.
* `verify_span_text` re-reads the document at the recorded offsets and compares
  the result to the span. A span whose offsets no longer select its text is a
  grounding failure, not a stale detail: citing it would attribute words to a
  document that does not contain them at that location.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import sha256_hex
from ..domain.ids import new_id


class GroundingFailure(ValueError):
    """A span does not faithfully anchor its text to the source document."""


def text_digest(text: str) -> str:
    """Digest of the exact verbatim bytes, UTF-8 encoded."""
    return sha256_hex(text.encode("utf-8"))


def build_source_span(
    *,
    document_id: str,
    paper_version_id: str,
    page: int,
    section: str | None,
    semantic_unit: str,
    char_start: int,
    char_end: int,
    verbatim_text: str,
    parser_name: str,
    parser_version: str,
    provenance_manifest_id: str,
    bbox: Sequence[float] | None = None,
    coordinate_system: str = "not_available",
    reconciliation_status: str = "single_parser",
    span_id: str | None = None,
) -> dict[str, Any]:
    """Build a verified source span.

    Offsets are validated against the text length up front: a span claiming a
    range that cannot hold its own text is malformed regardless of what the
    document says.
    """
    if not verbatim_text.strip():
        raise GroundingFailure("a source span must carry non-empty verbatim text")
    if char_end <= char_start:
        raise GroundingFailure(
            f"invalid span range: char_end {char_end} must exceed char_start {char_start}"
        )
    if (char_end - char_start) != len(verbatim_text):
        raise GroundingFailure(
            f"span range width {char_end - char_start} does not match verbatim text length "
            f"{len(verbatim_text)}"
        )
    span: dict[str, Any] = {
        "span_id": span_id or new_id("SPAN"),
        "document_id": document_id,
        "paper_version_id": paper_version_id,
        "page": page,
        "section": section,
        "semantic_unit": semantic_unit,
        "bbox": list(bbox) if bbox is not None else None,
        "char_start": char_start,
        "char_end": char_end,
        "verbatim_text": verbatim_text,
        "text_hash": text_digest(verbatim_text),
        "parser_name": parser_name,
        "parser_version": parser_version,
        "coordinate_system": coordinate_system,
        "reconciliation_status": reconciliation_status,
        "provenance_manifest_id": provenance_manifest_id,
    }
    validate_artifact("source-span", span)
    return span


def verify_span_text(span: dict[str, Any], document_text: str) -> None:
    """Re-read the document at the span offsets; raise on any mismatch.

    This is the check that makes source grounding real rather than declarative.
    """
    start = int(span["char_start"])
    end = int(span["char_end"])
    if end > len(document_text):
        raise GroundingFailure(
            f"span {span['span_id']} ends at {end} but the document is {len(document_text)} chars"
        )
    actual = document_text[start:end]
    if actual != span["verbatim_text"]:
        raise GroundingFailure(
            f"span {span['span_id']} does not match the document at [{start}:{end}]: "
            f"recorded {span['verbatim_text']!r} != actual {actual!r}"
        )
    recomputed = text_digest(span["verbatim_text"])
    if recomputed != span["text_hash"]:
        raise GroundingFailure(
            f"span {span['span_id']} text_hash {span['text_hash']} != recomputed {recomputed}"
        )


def spans_are_grounded(spans: Sequence[dict[str, Any]], document_text: str) -> bool:
    """Non-raising variant for reporting surfaces."""
    try:
        for span in spans:
            verify_span_text(span, document_text)
    except GroundingFailure:
        return False
    return True
