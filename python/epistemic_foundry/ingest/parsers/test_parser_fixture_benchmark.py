from __future__ import annotations

import hashlib
import itertools
import json

import pytest

from .adapters import (
    PARSER_ADAPTER_VERSION,
    ArtifactEnvelope,
    ElementKind,
    ParserContractError,
    ParserPin,
    ParserRole,
    ParserStatus,
    adapt_docling_artifact,
    adapt_grobid_artifact,
    compare_parser_streams,
)


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def pin(role: ParserRole, **overrides: object) -> ParserPin:
    names = {
        ParserRole.GROBID_STRUCTURE: ("grobid", "0.8.2"),
        ParserRole.DOCLING_LAYOUT: ("docling", "2.41.0"),
        ParserRole.FALLBACK: ("pypdf-fallback", "5.9.0"),
    }
    parser_id, version = names[role]
    values: dict[str, object] = {
        "parser_id": parser_id,
        "role": role,
        "exact_version": version,
        "executable_digest": digest(f"{parser_id}-executable-{version}".encode()),
        "adapter_version": PARSER_ADAPTER_VERSION,
        "profile_hash": digest(f"{parser_id}-profile-v1".encode()),
    }
    values.update(overrides)
    return ParserPin(**values)  # type: ignore[arg-type]


def artifact(
    payload: bytes | bytearray,
    *,
    artifact_id: str,
    media_type: str,
    source_artifact_id: str = "ART-SOURCE-0001",
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        source_artifact_id=source_artifact_id,
        media_type=media_type,
        content_hash=digest(bytes(payload)),
        payload=payload,  # type: ignore[arg-type]
    )


def grobid_payload(parser_pin: ParserPin, *, paragraph: str = "Yield increased by 12%.") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"
     data-parser-version="{parser_pin.exact_version}"
     data-profile-hash="{parser_pin.profile_hash}">
  <teiHeader><fileDesc><titleStmt>
    <title coords="1,10,10,300,20">Pinned parser fixture</title>
  </titleStmt></fileDesc></teiHeader>
  <text><body><div>
    <head coords="1,10,40,120,18">Results</head>
    <p coords="1,10,70,400,40" data-char-start="0" data-char-end="23">
      {paragraph} <ref type="bibr" target="#b0">[1]</ref>
    </p>
  </div></body><back><listBibl>
    <biblStruct coords="2,10,20,400,30">Example et al. 2026.</biblStruct>
  </listBibl></back></text>
</TEI>""".encode()


def docling_value(parser_pin: ParserPin) -> dict[str, object]:
    def element(
        address: str,
        kind: str,
        text: str,
        page: int,
        bbox: list[float],
        order: int,
        *,
        links: list[str] | None = None,
        rows: list[str] | None = None,
        columns: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "logical_address": address,
            "kind": kind,
            "text": text,
            "page": page,
            "bbox": bbox,
            "char_start": None,
            "char_end": None,
            "reading_order": order,
            "links": links or [],
            "row_headers": rows or [],
            "column_headers": columns or [],
            "confidence": 0.98,
        }

    return {
        "parser_version": parser_pin.exact_version,
        "profile_hash": parser_pin.profile_hash,
        "elements": [
            element("header/title", "TITLE", "Pinned parser fixture", 1, [10, 10, 310, 30], 0),
            element(
                "body/section[0]/heading",
                "SECTION_HEADING",
                "Results",
                1,
                [10, 40, 130, 58],
                1,
            ),
            element(
                "body/section[0]/paragraph[0]",
                "PARAGRAPH",
                "Yield increased by twelve percent [1]",
                1,
                [10, 70, 410, 110],
                3,
                links=["#b0"],
            ),
            element("table[0]", "TABLE", "Treatment results", 1, [20, 140, 500, 300], 4),
            element(
                "table[0]/cell[1,1]",
                "TABLE_CELL",
                "12%",
                1,
                [100, 180, 180, 210],
                5,
                rows=["Yield"],
                columns=["Treatment A"],
            ),
            element(
                "caption[0]",
                "CAPTION",
                "Table 1. Treatment results.",
                1,
                [20, 305, 500, 330],
                6,
                links=["table[0]"],
            ),
            element("formula[0]", "FORMULA", "y = ax + b", 2, [30, 50, 180, 80], 7),
        ],
    }


def docling_payload(parser_pin: ParserPin) -> bytes:
    return json.dumps(
        docling_value(parser_pin),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def successful_streams():
    grobid_pin = pin(ParserRole.GROBID_STRUCTURE)
    docling_pin = pin(ParserRole.DOCLING_LAYOUT)
    grobid = adapt_grobid_artifact(
        grobid_pin,
        artifact(
            grobid_payload(grobid_pin),
            artifact_id="ART-GROBID-0001",
            media_type="application/tei+xml",
        ),
    )
    docling = adapt_docling_artifact(
        docling_pin,
        artifact(
            docling_payload(docling_pin),
            artifact_id="ART-DOCLING-0001",
            media_type="application/vnd.docling+json",
        ),
    )
    assert grobid.stream is not None
    assert docling.stream is not None
    return grobid.stream, docling.stream


def test_parser_fixture_benchmark_exact_grobid_projection() -> None:
    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    attempt = adapt_grobid_artifact(
        parser_pin,
        artifact(
            grobid_payload(parser_pin),
            artifact_id="ART-GROBID-0001",
            media_type="application/tei+xml",
        ),
    )

    assert attempt.status is ParserStatus.PASS
    assert attempt.stream is not None
    assert [item.kind for item in attempt.stream.elements] == [
        ElementKind.TITLE,
        ElementKind.SECTION_HEADING,
        ElementKind.PARAGRAPH,
        ElementKind.REFERENCE,
    ]
    paragraph = attempt.stream.elements[2]
    assert paragraph.links == ("#b0",)
    assert paragraph.locator.page == 1
    assert paragraph.locator.bbox == (10.0, 70.0, 410.0, 110.0)
    assert paragraph.locator.char_start == 0
    assert paragraph.locator.char_end == 23
    assert attempt.stream.artifact.payload == grobid_payload(parser_pin)


def test_parser_fixture_benchmark_exact_docling_projection() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(
            docling_payload(parser_pin),
            artifact_id="ART-DOCLING-0001",
            media_type="application/vnd.docling+json",
        ),
    )

    assert attempt.status is ParserStatus.PASS
    assert attempt.stream is not None
    assert len(attempt.stream.elements) == 7
    table_cell = next(
        item for item in attempt.stream.elements if item.kind is ElementKind.TABLE_CELL
    )
    caption = next(item for item in attempt.stream.elements if item.kind is ElementKind.CAPTION)
    assert table_cell.row_headers == ("Yield",)
    assert table_cell.column_headers == ("Treatment A",)
    assert caption.links == ("table[0]",)
    assert all(item.locator.page is not None for item in attempt.stream.elements)
    assert all(item.locator.bbox is not None for item in attempt.stream.elements)


def test_parser_fixture_benchmark_hashes_are_repeatable() -> None:
    first = successful_streams()
    second = successful_streams()

    assert [stream.stream_hash for stream in first] == [
        stream.stream_hash for stream in second
    ]
    assert [item.element_id for item in first[0].elements] == [
        item.element_id for item in second[0].elements
    ]


def test_parser_fixture_benchmark_disagreement_retains_both_observations() -> None:
    grobid, docling = successful_streams()
    comparison = compare_parser_streams((grobid, docling))

    paragraph = next(
        item
        for item in comparison.disagreements
        if item.logical_address == "body/section[0]/paragraph[0]"
    )
    assert paragraph.status == "UNRESOLVED"
    assert set(paragraph.differing_fields) >= {"text_hash", "reading_order"}
    assert [item.text for item in paragraph.observations] == [
        "Yield increased by 12%. [1]",
        "Yield increased by twelve percent [1]",
    ]
    assert {item.parser_role for item in paragraph.observations} == {
        ParserRole.GROBID_STRUCTURE,
        ParserRole.DOCLING_LAYOUT,
    }
    assert not hasattr(comparison, "selected_text")


def test_parser_fixture_benchmark_confidence_disagreement_remains_visible() -> None:
    grobid, docling = successful_streams()
    comparison = compare_parser_streams((grobid, docling))

    title = next(
        item
        for item in comparison.disagreements
        if item.logical_address == "header/title"
    )
    assert title.differing_fields == ("confidence",)
    assert [item.confidence for item in title.observations] == [None, 0.98]


def test_parser_fixture_benchmark_missing_observations_remain_visible() -> None:
    grobid, docling = successful_streams()
    comparison = compare_parser_streams((grobid, docling))

    table = next(
        item for item in comparison.disagreements if item.logical_address == "table[0]"
    )
    assert "missing_observation" in table.differing_fields
    assert len(table.observations) == 1
    assert table.observations[0].parser_role is ParserRole.DOCLING_LAYOUT


def test_parser_fixture_benchmark_stream_order_does_not_change_comparison() -> None:
    streams = successful_streams()
    results = [compare_parser_streams(order) for order in itertools.permutations(streams)]

    assert {item.comparison_hash for item in results} == {results[0].comparison_hash}
    assert {item.stream_hashes for item in results} == {results[0].stream_hashes}


@pytest.mark.parametrize(
    "value",
    ["main", "latest", "1.x", ">=1.0", "1.0 || 2.0", "1.0,2.0", " snapshot "],
)
def test_parser_fixture_benchmark_floating_version_is_rejected(value: str) -> None:
    with pytest.raises(ParserContractError) as raised:
        pin(ParserRole.GROBID_STRUCTURE, exact_version=value)

    assert raised.value.code == "PARSER_PIN_FLOATING"


def test_parser_fixture_benchmark_bad_executable_digest_is_rejected() -> None:
    with pytest.raises(ParserContractError) as raised:
        pin(ParserRole.GROBID_STRUCTURE, executable_digest="sha256:abc")

    assert raised.value.code == "PARSER_PIN_INVALID"


def test_parser_fixture_benchmark_wrong_adapter_version_is_rejected() -> None:
    with pytest.raises(ParserContractError) as raised:
        pin(ParserRole.GROBID_STRUCTURE, adapter_version="4.0.0-k02.other")

    assert raised.value.code == "PARSER_ADAPTER_VERSION_MISMATCH"


def test_parser_fixture_benchmark_output_version_mismatch_is_typed_failure() -> None:
    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    payload = grobid_payload(parser_pin).replace(b'0.8.2', b'0.8.3')
    attempt = adapt_grobid_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-G", media_type="application/tei+xml"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_PIN_OUTPUT_MISMATCH"
    assert attempt.stream is None


def test_parser_fixture_benchmark_profile_mismatch_is_typed_failure() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["profile_hash"] = digest(b"other-profile")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_PIN_OUTPUT_MISMATCH"


def test_parser_fixture_benchmark_malformed_tei_is_typed_failure() -> None:
    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    payload = b"<TEI><broken></TEI>"
    attempt = adapt_grobid_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-G", media_type="application/tei+xml"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "GROBID_OUTPUT_MALFORMED"


def test_parser_fixture_benchmark_dtd_is_rejected_before_xml_parse() -> None:
    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    payload = b'<!DOCTYPE TEI [<!ENTITY x "bad">]><TEI>&x;</TEI>'
    attempt = adapt_grobid_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-G", media_type="application/tei+xml"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "GROBID_UNSAFE_XML"


def test_parser_fixture_benchmark_utf16_dtd_cannot_bypass_declaration_scan() -> None:
    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    payload = '<!DOCTYPE TEI [<!ENTITY x "bad">]><TEI>&x;</TEI>'.encode("utf-16")
    attempt = adapt_grobid_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-G", media_type="application/tei+xml"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "GROBID_UNSAFE_XML"


def test_parser_fixture_benchmark_mutable_payload_is_snapshotted() -> None:
    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    mutable = bytearray(grobid_payload(parser_pin))
    envelope = artifact(
        mutable,
        artifact_id="ART-GROBID-0001",
        media_type="application/tei+xml",
    )
    before = envelope.payload
    mutable[0] = ord("X")

    attempt = adapt_grobid_artifact(parser_pin, envelope)

    assert envelope.payload == before
    assert attempt.status is ParserStatus.PASS


def test_parser_fixture_benchmark_bytes_subclass_is_detached_before_validation() -> None:
    class HostileBytes(bytes):
        def lower(self) -> bytes:
            return b"caller-defined lower projection"

        def decode(self, *args: object, **kwargs: object) -> str:
            return "caller-defined decode projection"

    parser_pin = pin(ParserRole.GROBID_STRUCTURE)
    source = grobid_payload(parser_pin)
    envelope = artifact(
        HostileBytes(source),
        artifact_id="ART-GROBID-0001",
        media_type="application/tei+xml",
    )

    attempt = adapt_grobid_artifact(parser_pin, envelope)

    assert type(envelope.payload) is bytes
    assert envelope.payload == source
    assert attempt.status is ParserStatus.PASS


def test_parser_fixture_benchmark_artifact_hash_mismatch_is_rejected() -> None:
    with pytest.raises(ParserContractError) as raised:
        ArtifactEnvelope(
            artifact_id="ART-BAD",
            source_artifact_id="ART-SOURCE",
            media_type="application/json",
            content_hash=digest(b"different"),
            payload=b"{}",
        )

    assert raised.value.code == "PARSER_ARTIFACT_HASH_MISMATCH"


def test_parser_fixture_benchmark_unknown_docling_field_is_typed_failure() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["provider_comment"] = "not part of the normalized contract"
    payload = json.dumps(value, sort_keys=True).encode()
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_OUTPUT_MALFORMED"


def test_parser_fixture_benchmark_duplicate_json_keys_are_not_collapsed() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    valid = docling_payload(parser_pin)
    payload = b'{"parser_version":"shadow",' + valid[1:]
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_OUTPUT_MALFORMED"


def test_parser_fixture_benchmark_docling_bbox_is_required() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["elements"][0]["bbox"] = None  # type: ignore[index]
    payload = json.dumps(value, sort_keys=True).encode()
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_PROVENANCE_MISSING"


def test_parser_fixture_benchmark_oversized_number_is_a_typed_failure() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["elements"][0]["confidence"] = 10**400  # type: ignore[index]
    payload = json.dumps(value, sort_keys=True).encode()
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_OUTPUT_INVALID"


def test_parser_fixture_benchmark_caption_link_is_required() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["elements"][5]["links"] = []  # type: ignore[index]
    payload = json.dumps(value, sort_keys=True).encode()
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_LINKAGE_MISSING"


def test_parser_fixture_benchmark_table_cell_headers_are_required() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["elements"][4]["column_headers"] = []  # type: ignore[index]
    payload = json.dumps(value, sort_keys=True).encode()
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_TABLE_ADDRESS_MISSING"


def test_parser_fixture_benchmark_duplicate_reading_order_is_rejected() -> None:
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    value = docling_value(parser_pin)
    value["elements"][1]["reading_order"] = 0  # type: ignore[index]
    payload = json.dumps(value, sort_keys=True).encode()
    attempt = adapt_docling_artifact(
        parser_pin,
        artifact(payload, artifact_id="ART-D", media_type="application/json"),
    )

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_READING_ORDER_CONFLICT"


def test_parser_fixture_benchmark_source_mismatch_cannot_be_compared() -> None:
    grobid, _ = successful_streams()
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    docling = adapt_docling_artifact(
        parser_pin,
        artifact(
            docling_payload(parser_pin),
            artifact_id="ART-D",
            media_type="application/json",
            source_artifact_id="ART-OTHER-SOURCE",
        ),
    )
    assert docling.stream is not None

    with pytest.raises(ParserContractError) as raised:
        compare_parser_streams((grobid, docling.stream))

    assert raised.value.code == "PARSER_SOURCE_MISMATCH"
