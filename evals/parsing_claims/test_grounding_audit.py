"""grounding_audit — every claim traces to a span, including tables and figures.

Exit criterion under test: "table/figure spans included".  A parser benchmark
built from running prose alone would excuse exactly the spans parsers get
wrong, so the corpus must ground gold claims in table cells and figure
captions, every span must satisfy the canonical SourceSpan schema with its
hash recomputed from the verbatim bytes, and a claim whose text does not
actually appear in a cited span is refused rather than scored.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from evaluator import (
    REQUIRED_GROUNDING_UNITS,
    SPAN_SCHEMA_PATH,
    ClaimEvalError,
    audit_grounding,
    evaluate,
    load_corpus,
    semantic_units,
)
from test_claim_eval import ROOT, claim_of, corpus, refused


def span_of(payload: dict, span_id: str) -> dict:
    for document in payload["documents"]:
        for span in document["spans"]:
            if span["span_id"] == span_id:
                return span
    raise AssertionError(span_id)


def test_the_committed_corpus_grounds_every_claim() -> None:
    grounding = audit_grounding(ROOT)

    assert grounding["status"] == "PASS"
    assert grounding["spans_total"] == 10
    assert grounding["claims_audited"] == 16


def test_both_required_span_units_carry_gold_claims() -> None:
    grounding = audit_grounding(ROOT)

    assert REQUIRED_GROUNDING_UNITS == ("figure_caption", "table_cell")
    for unit in REQUIRED_GROUNDING_UNITS:
        assert grounding["gold_claims_grounded_in_required_units"][unit] >= 1
        assert grounding["spans_by_semantic_unit"][unit] >= 1


def test_the_span_units_come_from_the_canonical_schema() -> None:
    units = semantic_units(ROOT)
    schema = json.loads((ROOT / SPAN_SCHEMA_PATH).read_text(encoding="utf-8"))

    assert list(units) == schema["properties"]["semantic_unit"]["enum"]
    assert set(REQUIRED_GROUNDING_UNITS) <= set(units)


def test_a_corpus_without_a_table_cell_claim_is_refused() -> None:
    payload = corpus()
    payload["gold_claims"] = [
        claim
        for claim in payload["gold_claims"]
        if claim["claim_id"] not in {"GC-002", "GC-007"}
    ]
    payload["predicted_claims"] = [
        claim for claim in payload["predicted_claims"] if claim["claim_id"] != "PC-002"
    ]

    error = refused(payload)
    assert error.code == "REQUIRED_UNIT_UNGROUNDED"
    assert error.context["units"] == ["table_cell"]


def test_a_corpus_with_no_figure_span_at_all_is_refused() -> None:
    payload = corpus()
    for document in payload["documents"]:
        document["spans"] = [
            span
            for span in document["spans"]
            if span["semantic_unit"] != "figure_caption"
        ]
    payload["gold_claims"] = [
        claim
        for claim in payload["gold_claims"]
        if claim["claim_id"] not in {"GC-003", "GC-006"}
    ]
    payload["predicted_claims"] = [
        claim
        for claim in payload["predicted_claims"]
        if claim["claim_id"] not in {"PC-005", "PC-008"}
    ]

    error = refused(payload)
    assert error.code in {"REQUIRED_UNIT_MISSING", "CLAIM_UNGROUNDED"}


def test_every_span_satisfies_the_canonical_schema() -> None:
    payload = load_corpus(ROOT)
    schema = json.loads((ROOT / SPAN_SCHEMA_PATH).read_text(encoding="utf-8"))
    validator = __import__("jsonschema").Draft202012Validator(schema)

    for document in payload["documents"]:
        for span in document["spans"]:
            validator.validate(span)


def test_a_span_missing_a_canonical_field_is_refused() -> None:
    payload = corpus()
    del span_of(payload, "SP-002")["coordinate_system"]

    assert refused(payload).code == "SPAN_SCHEMA_INVALID"


def test_a_span_with_an_unknown_field_is_refused() -> None:
    payload = corpus()
    span_of(payload, "SP-002")["confidence"] = 0.9

    assert refused(payload).code == "SPAN_SCHEMA_INVALID"


def test_every_span_hash_is_the_hash_of_its_verbatim_text() -> None:
    payload = load_corpus(ROOT)

    for document in payload["documents"]:
        for span in document["spans"]:
            expected = (
                "sha256:"
                + hashlib.sha256(span["verbatim_text"].encode("utf-8")).hexdigest()
            )
            assert span["text_hash"] == expected, span["span_id"]


def test_a_span_whose_hash_does_not_match_its_text_is_refused() -> None:
    payload = corpus()
    span_of(payload, "SP-003")["verbatim_text"] = "28 C / 42% fruit set / n=48"

    error = refused(payload)
    assert error.code == "SPAN_HASH_MISMATCH"
    assert error.context["span_id"] == "SP-003"


def test_a_span_whose_range_is_inverted_is_refused() -> None:
    payload = corpus()
    span = span_of(payload, "SP-002")
    span["char_end"] = span["char_start"]

    assert refused(payload).code in {"SPAN_SCHEMA_INVALID", "SPAN_RANGE_INVALID"}


def test_a_span_filed_under_the_wrong_document_is_refused() -> None:
    payload = corpus()
    span_of(payload, "SP-101")["document_id"] = "DOC-Q02-001"

    assert refused(payload).code == "SPAN_DOCUMENT_MISMATCH"


def test_a_duplicate_span_id_is_refused() -> None:
    payload = corpus()
    payload["documents"][1]["spans"].append(copy.deepcopy(span_of(payload, "SP-101")))

    assert refused(payload).code == "DUPLICATE_SPAN"


def test_a_claim_citing_an_absent_span_is_refused() -> None:
    payload = corpus()
    claim_of(payload, "GC-001")["source_span_ids"] = ["SP-999"]

    error = refused(payload)
    assert error.code == "CLAIM_UNGROUNDED"
    assert error.context["span_id"] == "SP-999"


def test_a_claim_citing_no_span_is_refused() -> None:
    payload = corpus()
    claim_of(payload, "GC-001")["source_span_ids"] = []

    assert refused(payload).code == "GROUNDING_MISSING"


def test_a_claim_whose_text_is_not_in_its_span_is_refused() -> None:
    payload = corpus()
    claim_of(payload, "GC-001")["verbatim_text"] = "Fruit set rose sharply."

    error = refused(payload)
    assert error.code == "VERBATIM_UNGROUNDED"
    assert error.context["claim_id"] == "GC-001"


def test_a_claim_citing_the_same_span_twice_is_refused() -> None:
    payload = corpus()
    claim_of(payload, "GC-001")["source_span_ids"] = ["SP-002", "SP-002"]

    assert refused(payload).code == "DUPLICATE_SPAN_REFERENCE"


def test_a_multi_span_claim_needs_only_one_containing_span() -> None:
    payload = corpus()
    claim = claim_of(payload, "GC-006")

    assert claim["source_span_ids"] == ["SP-101", "SP-103"]
    assert evaluate(payload, ROOT).payload["status"] == "PASS"


def test_a_bboxless_span_is_accepted_when_its_coordinate_system_says_so() -> None:
    payload = load_corpus(ROOT)
    span = None
    for document in payload["documents"]:
        for entry in document["spans"]:
            if entry["bbox"] is None:
                span = entry
                break

    assert span is not None
    assert span["coordinate_system"] == "not_available"


def test_the_corpus_records_a_parser_disagreement_rather_than_hiding_it() -> None:
    payload = load_corpus(ROOT)
    statuses = {
        span["reconciliation_status"]
        for document in payload["documents"]
        for span in document["spans"]
    }

    assert "conflict_recorded" in statuses
    assert "human_resolved" in statuses


def test_every_span_pins_the_parser_that_produced_it() -> None:
    payload = load_corpus(ROOT)
    parsers = set()

    for document in payload["documents"]:
        for span in document["spans"]:
            assert span["parser_name"] and span["parser_version"]
            parsers.add((span["parser_name"], span["parser_version"]))
    assert len(parsers) > 1


def test_the_grounding_audit_is_the_report_slice() -> None:
    from evaluator import evaluate_corpus

    assert audit_grounding(ROOT) == evaluate_corpus(ROOT).payload["grounding"]


def test_an_unreadable_corpus_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ClaimEvalError) as caught:
        load_corpus(tmp_path)

    assert caught.value.code == "CORPUS_UNREADABLE"
