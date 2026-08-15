from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator, Mapping
from pathlib import Path

import jsonschema
import pytest

from .emitter import (
    CoordinateSystem,
    ReconciliationStatus,
    SemanticUnit,
    SourceSnapshot,
    SourceSpanContractError,
    SpanCandidate,
    SpanKind,
    emit_source_span,
    emit_source_spans,
    resolve_source_spans,
    source_span_from_mapping,
    verify_source_span,
)


SOURCE_TEXT = (
    "Yield increased under treatment.\n"
    "Table 1: control=4; treatment=7.\n"
    "Figure 1: response curve.\n"
    "Equation: y = ax + b."
)


class DuplicateItemsMapping(Mapping[str, object]):
    def __init__(self, items: list[tuple[str, object]]) -> None:
        self._items = items

    def __getitem__(self, key: str) -> object:
        for candidate, value in reversed(self._items):
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(dict(self._items))

    def __len__(self) -> int:
        return len(dict(self._items))

    def items(self) -> list[tuple[str, object]]:
        return list(self._items)


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def snapshot(content: str | bytes = SOURCE_TEXT) -> SourceSnapshot:
    return SourceSnapshot.capture(
        document_id="DOC-K03-0001",
        paper_version_id="PV-K03-0001",
        provenance_manifest_id="PROV-K03-0001",
        content=content,
    )


def candidate(
    kind: SpanKind,
    unit: SemanticUnit,
    needle: str,
    *,
    page: int,
) -> SpanCandidate:
    start = SOURCE_TEXT.index(needle)
    return SpanCandidate(
        kind=kind,
        page=page,
        section="Results",
        semantic_unit=unit,
        bbox=(0.1, 0.2, 0.9, 0.4),
        char_start=start,
        char_end=start + len(needle),
        parser_name="docling",
        parser_version="2.41.0",
        coordinate_system=CoordinateSystem.NORMALIZED_TOP_LEFT,
        reconciliation_status=ReconciliationStatus.AGREED,
    )


def all_candidates() -> tuple[SpanCandidate, ...]:
    return (
        candidate(SpanKind.TEXT, SemanticUnit.RESULTS, "Yield increased", page=1),
        candidate(SpanKind.TABLE, SemanticUnit.TABLE_CELL, "control=4", page=2),
        candidate(
            SpanKind.FIGURE,
            SemanticUnit.FIGURE_CAPTION,
            "Figure 1: response curve.",
            page=3,
        ),
        candidate(SpanKind.FORMULA, SemanticUnit.EQUATION, "y = ax + b", page=4),
    )


def error_code(error: pytest.ExceptionInfo[SourceSpanContractError]) -> str:
    return error.value.code


def test_source_span_roundtrip_covers_text_table_figure_and_formula() -> None:
    source = snapshot()
    spans = emit_source_spans(source, all_candidates())

    assert [span.semantic_unit for span in spans] == [
        SemanticUnit.RESULTS,
        SemanticUnit.TABLE_CELL,
        SemanticUnit.FIGURE_CAPTION,
        SemanticUnit.EQUATION,
    ]
    assert resolve_source_spans(spans, (source,)) == tuple(
        span.verbatim_text for span in spans
    )
    assert all(span.span_id.startswith("SPAN-") for span in spans)
    assert all(span.text_hash == digest(span.verbatim_text) for span in spans)


def test_source_span_roundtrip_projection_validates_against_canonical_schema() -> None:
    root = Path(__file__).resolve().parents[4]
    schema = json.loads((root / "schemas" / "source-span.schema.json").read_text("utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    for span in emit_source_spans(snapshot(), all_candidates()):
        validator.validate(span.projection())
        assert set(span.projection()) == set(schema["required"])


def test_source_span_roundtrip_identity_is_deterministic_and_source_bound() -> None:
    first = emit_source_spans(snapshot(), all_candidates())
    second = emit_source_spans(snapshot(SOURCE_TEXT.encode("utf-8")), all_candidates())

    assert [span.span_id for span in first] == [span.span_id for span in second]
    assert [span.projection() for span in first] == [span.projection() for span in second]

    changed = SOURCE_TEXT.replace("treatment=7", "treatment=8")
    changed_span = emit_source_span(snapshot(changed), all_candidates()[0])
    assert changed_span.verbatim_text == first[0].verbatim_text
    assert changed_span.span_id != first[0].span_id


def test_source_span_roundtrip_detaches_bytes_subclass_before_hashing() -> None:
    class HostileBytes(bytes):
        def decode(self, *args: object, **kwargs: object) -> str:
            return "caller-defined decode projection"

    source = snapshot(HostileBytes(SOURCE_TEXT.encode("utf-8")))

    assert type(source.source_text) is str
    assert source.source_text == SOURCE_TEXT
    assert source.source_text_hash == digest(SOURCE_TEXT)


def test_source_span_roundtrip_derives_text_and_rejects_duplicate_candidates() -> None:
    source = snapshot()
    one = all_candidates()[0]
    span = emit_source_span(source, one)
    assert span.verbatim_text == source.source_text[one.char_start : one.char_end]

    with pytest.raises(SourceSpanContractError) as captured:
        emit_source_spans(source, (one, one))
    assert error_code(captured) == "SOURCE_SPAN_ID_MISMATCH"


@pytest.mark.parametrize("floating", ["main", "latest", "^2.0", "2.x", "2.0 - 3.0"])
def test_source_span_roundtrip_rejects_floating_parser_versions(floating: str) -> None:
    values = all_candidates()[0]
    with pytest.raises(SourceSpanContractError) as captured:
        SpanCandidate(
            kind=values.kind,
            page=values.page,
            section=values.section,
            semantic_unit=values.semantic_unit,
            bbox=values.bbox,
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=floating,
            coordinate_system=values.coordinate_system,
            reconciliation_status=values.reconciliation_status,
        )
    assert error_code(captured) == "SOURCE_SPAN_INPUT_INVALID"


@pytest.mark.parametrize(
    ("kind", "unit"),
    [
        (SpanKind.TEXT, SemanticUnit.EQUATION),
        (SpanKind.TABLE, SemanticUnit.RESULTS),
        (SpanKind.FIGURE, SemanticUnit.TABLE_CELL),
        (SpanKind.FORMULA, SemanticUnit.FIGURE_CAPTION),
    ],
)
def test_source_span_roundtrip_rejects_kind_semantic_mismatch(
    kind: SpanKind,
    unit: SemanticUnit,
) -> None:
    with pytest.raises(SourceSpanContractError) as captured:
        candidate(kind, unit, "Yield", page=1)
    assert error_code(captured) == "SOURCE_SPAN_INPUT_INVALID"


@pytest.mark.parametrize(
    ("bbox", "coordinate_system"),
    [
        (None, CoordinateSystem.NORMALIZED_TOP_LEFT),
        ((0.0, 0.0, 1.0, 1.0), CoordinateSystem.NOT_AVAILABLE),
        ((0.0, 0.0, 1.1, 1.0), CoordinateSystem.NORMALIZED_TOP_LEFT),
        ((0.8, 0.2, 0.1, 0.4), CoordinateSystem.NORMALIZED_TOP_LEFT),
    ],
)
def test_source_span_roundtrip_accepts_schema_defined_bbox_coordinate_pairs(
    bbox: tuple[float, float, float, float] | None,
    coordinate_system: CoordinateSystem,
) -> None:
    values = all_candidates()[0]
    span = emit_source_span(
        snapshot(),
        SpanCandidate(
            kind=values.kind,
            page=values.page,
            section=values.section,
            semantic_unit=values.semantic_unit,
            bbox=bbox,
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=coordinate_system,
            reconciliation_status=values.reconciliation_status,
        ),
    )

    assert span.bbox == bbox
    assert span.coordinate_system is coordinate_system


def test_source_span_roundtrip_preserves_large_integer_bbox_value() -> None:
    values = all_candidates()[0]
    span = emit_source_span(
        snapshot(),
        SpanCandidate(
            kind=values.kind,
            page=values.page,
            section=values.section,
            semantic_unit=values.semantic_unit,
            bbox=(0, 0, 10**400, 1),
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=CoordinateSystem.PDF_POINTS_TOP_LEFT,
            reconciliation_status=values.reconciliation_status,
        ),
    )

    assert span.bbox == (0, 0, 10**400, 1)
    assert span.bbox is not None
    assert type(span.bbox[2]) is int


@pytest.mark.parametrize(
    "bbox",
    [
        (0, 0, 1),
        (0, 0, True, 1),
        (0, 0, float("nan"), 1),
        (0, 0, "one", 1),
    ],
)
def test_source_span_roundtrip_rejects_non_schema_bbox_values(
    bbox: object,
) -> None:
    values = all_candidates()[0]
    with pytest.raises(SourceSpanContractError) as captured:
        SpanCandidate(
            kind=values.kind,
            page=values.page,
            section=values.section,
            semantic_unit=values.semantic_unit,
            bbox=bbox,  # type: ignore[arg-type]
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=CoordinateSystem.PDF_POINTS_TOP_LEFT,
            reconciliation_status=values.reconciliation_status,
        )

    assert error_code(captured) == "SOURCE_SPAN_INPUT_INVALID"


def test_source_span_roundtrip_accepts_typed_null_bbox() -> None:
    values = all_candidates()[0]
    span = emit_source_span(
        snapshot(),
        SpanCandidate(
            kind=values.kind,
            page=values.page,
            section=None,
            semantic_unit=values.semantic_unit,
            bbox=None,
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=CoordinateSystem.NOT_AVAILABLE,
            reconciliation_status=ReconciliationStatus.SINGLE_PARSER,
        ),
    )
    assert span.bbox is None
    assert span.coordinate_system is CoordinateSystem.NOT_AVAILABLE


def test_source_span_roundtrip_accepts_schema_defined_null_page() -> None:
    values = all_candidates()[0]
    span = emit_source_span(
        snapshot(),
        SpanCandidate(
            kind=values.kind,
            page=None,
            section=None,
            semantic_unit=values.semantic_unit,
            bbox=None,
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=CoordinateSystem.NOT_AVAILABLE,
            reconciliation_status=ReconciliationStatus.SINGLE_PARSER,
        ),
    )

    restored = source_span_from_mapping(span.projection())

    assert restored.page is None
    assert restored.bbox is None
    assert restored.coordinate_system is CoordinateSystem.NOT_AVAILABLE
    assert verify_source_span(restored, snapshot()) == restored.verbatim_text


def test_source_span_roundtrip_preserves_schema_defined_empty_section() -> None:
    values = all_candidates()[0]
    span = emit_source_span(
        snapshot(),
        SpanCandidate(
            kind=values.kind,
            page=values.page,
            section="",
            semantic_unit=values.semantic_unit,
            bbox=values.bbox,
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=values.coordinate_system,
            reconciliation_status=values.reconciliation_status,
        ),
    )

    assert source_span_from_mapping(span.projection()).section == ""


def test_source_span_roundtrip_null_page_requires_absent_geometry() -> None:
    values = all_candidates()[0]
    with pytest.raises(SourceSpanContractError) as captured:
        SpanCandidate(
            kind=values.kind,
            page=None,
            section=values.section,
            semantic_unit=values.semantic_unit,
            bbox=values.bbox,
            char_start=values.char_start,
            char_end=values.char_end,
            parser_name=values.parser_name,
            parser_version=values.parser_version,
            coordinate_system=values.coordinate_system,
            reconciliation_status=values.reconciliation_status,
        )

    assert error_code(captured) == "SOURCE_SPAN_INPUT_INVALID"


def test_source_span_roundtrip_rejects_tampered_text_hash_and_id() -> None:
    source = snapshot()
    projection = emit_source_span(source, all_candidates()[0]).projection()

    bad_text = copy.deepcopy(projection)
    bad_text["verbatim_text"] = "Yield decreased"
    with pytest.raises(SourceSpanContractError) as captured:
        source_span_from_mapping(bad_text)
    assert error_code(captured) == "SOURCE_SPAN_TEXT_HASH_MISMATCH"

    bad_id = copy.deepcopy(projection)
    bad_id["span_id"] = "SPAN-" + ("f" * 64)
    with pytest.raises(SourceSpanContractError) as captured:
        verify_source_span(bad_id, source)
    assert error_code(captured) == "SOURCE_SPAN_ID_MISMATCH"


def test_source_span_roundtrip_rejects_unknown_persisted_fields() -> None:
    projection = emit_source_span(snapshot(), all_candidates()[0]).projection()
    projection["caller_claimed_truth"] = True
    with pytest.raises(SourceSpanContractError) as captured:
        source_span_from_mapping(projection)
    assert error_code(captured) == "SOURCE_SPAN_INPUT_INVALID"


def test_source_span_roundtrip_rejects_duplicate_projected_mapping_keys() -> None:
    projection = emit_source_span(snapshot(), all_candidates()[0]).projection()
    duplicate = DuplicateItemsMapping(
        [("span_id", "SPAN-" + ("f" * 64)), *projection.items()]
    )

    with pytest.raises(SourceSpanContractError) as captured:
        source_span_from_mapping(duplicate)

    assert error_code(captured) == "SOURCE_SPAN_INPUT_INVALID"
