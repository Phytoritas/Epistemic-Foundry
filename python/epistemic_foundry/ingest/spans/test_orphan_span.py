from __future__ import annotations

import dataclasses

import pytest

from .emitter import (
    CoordinateSystem,
    ReconciliationStatus,
    SemanticUnit,
    SourceSnapshot,
    SourceSnapshotIndex,
    SourceSpanContractError,
    SpanCandidate,
    SpanKind,
    emit_source_span,
    resolve_source_span,
    verify_source_span,
)


SOURCE_TEXT = "Alpha evidence. Beta evidence. Gamma evidence."


def snapshot(
    *,
    document_id: str = "DOC-K03-ORPHAN",
    paper_version_id: str = "PV-K03-0001",
    provenance_manifest_id: str = "PROV-K03-0001",
    content: str = SOURCE_TEXT,
) -> SourceSnapshot:
    return SourceSnapshot.capture(
        document_id=document_id,
        paper_version_id=paper_version_id,
        provenance_manifest_id=provenance_manifest_id,
        content=content,
    )


def candidate(*, start: int = 0, end: int = 14, page: int = 1) -> SpanCandidate:
    return SpanCandidate(
        kind=SpanKind.TEXT,
        page=page,
        section="Results",
        semantic_unit=SemanticUnit.RESULTS,
        bbox=None,
        char_start=start,
        char_end=end,
        parser_name="grobid",
        parser_version="0.8.2",
        coordinate_system=CoordinateSystem.NOT_AVAILABLE,
        reconciliation_status=ReconciliationStatus.SINGLE_PARSER,
    )


def code(error: pytest.ExceptionInfo[SourceSpanContractError]) -> str:
    return error.value.code


def test_orphan_span_rejects_missing_source_snapshot() -> None:
    source = snapshot()
    span = emit_source_span(source, candidate())

    with pytest.raises(SourceSpanContractError) as captured:
        resolve_source_span(span, ())
    assert code(captured) == "SOURCE_SPAN_ORPHANED"


@pytest.mark.parametrize(
    "wrong_source",
    [
        snapshot(document_id="DOC-OTHER"),
        snapshot(paper_version_id="PV-OTHER"),
    ],
)
def test_orphan_span_rejects_wrong_document_or_version(
    wrong_source: SourceSnapshot,
) -> None:
    span = emit_source_span(snapshot(), candidate())
    with pytest.raises(SourceSpanContractError) as captured:
        verify_source_span(span, wrong_source)
    assert code(captured) == "SOURCE_SPAN_ORPHANED"


def test_orphan_span_rejects_wrong_provenance() -> None:
    source = snapshot()
    span = emit_source_span(source, candidate())
    wrong_provenance = snapshot(provenance_manifest_id="PROV-OTHER")

    with pytest.raises(SourceSpanContractError) as captured:
        SourceSnapshotIndex((wrong_provenance,)).resolve(span)
    assert code(captured) == "SOURCE_SPAN_PROVENANCE_MISMATCH"


def test_orphan_span_rejects_stale_source_text_even_when_slice_is_unchanged() -> None:
    source = snapshot()
    span = emit_source_span(source, candidate())
    changed_outside_slice = snapshot(content=SOURCE_TEXT.replace("Gamma", "Delta"))

    assert changed_outside_slice.source_text[:14] == span.verbatim_text
    with pytest.raises(SourceSpanContractError) as captured:
        verify_source_span(span, changed_outside_slice)
    assert code(captured) == "SOURCE_SPAN_ID_MISMATCH"


def test_orphan_span_rejects_stale_range_content() -> None:
    source = snapshot()
    span = emit_source_span(source, candidate())
    changed_inside_slice = snapshot(content=SOURCE_TEXT.replace("Alpha", "Omega"))

    with pytest.raises(SourceSpanContractError) as captured:
        verify_source_span(span, changed_inside_slice)
    assert code(captured) == "SOURCE_SPAN_TEXT_HASH_MISMATCH"


def test_orphan_span_rejects_source_snapshot_mutation() -> None:
    source = snapshot()
    span = emit_source_span(source, candidate())
    object.__setattr__(source, "source_text", source.source_text + " mutated")

    with pytest.raises(SourceSpanContractError) as captured:
        verify_source_span(span, source)
    assert code(captured) == "SOURCE_SPAN_SOURCE_HASH_MISMATCH"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (0, 0),
        (5, 5),
        (9, 3),
        (-1, 3),
    ],
)
def test_orphan_span_rejects_invalid_ranges(start: int, end: int) -> None:
    with pytest.raises(SourceSpanContractError) as captured:
        candidate(start=start, end=end)
    assert code(captured) in {"SOURCE_SPAN_INPUT_INVALID", "SOURCE_SPAN_RANGE_INVALID"}


def test_orphan_span_rejects_range_beyond_source() -> None:
    with pytest.raises(SourceSpanContractError) as captured:
        emit_source_span(snapshot(), candidate(end=len(SOURCE_TEXT) + 1))
    assert code(captured) == "SOURCE_SPAN_RANGE_INVALID"


def test_orphan_span_rejects_non_positive_page() -> None:
    with pytest.raises(SourceSpanContractError) as captured:
        candidate(page=0)
    assert code(captured) == "SOURCE_SPAN_INPUT_INVALID"


def test_orphan_span_rejects_empty_source() -> None:
    with pytest.raises(SourceSpanContractError) as captured:
        snapshot(content="")
    assert code(captured) == "SOURCE_SPAN_ORPHANED"


def test_orphan_span_rejects_duplicate_snapshot_identity() -> None:
    source = snapshot()
    with pytest.raises(SourceSpanContractError) as captured:
        SourceSnapshotIndex((source, source))
    assert code(captured) == "SOURCE_SPAN_INPUT_INVALID"


def test_orphan_span_values_are_immutable() -> None:
    source = snapshot()
    span = emit_source_span(source, candidate())

    with pytest.raises(dataclasses.FrozenInstanceError):
        span.page = 7  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        source.source_text = "replacement"  # type: ignore[misc]
