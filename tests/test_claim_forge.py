"""Source grounding and typed evidence roles."""

from __future__ import annotations

import inspect
import json

import pytest

from epistemic_foundry.claim_forge import (
    GroundingFailure,
    build_evidence_node,
    build_source_span,
    verify_span_text,
)
from epistemic_foundry.claim_forge.evidence import dissenting_evidence, supporting_evidence
from epistemic_foundry.claim_forge.grounding import spans_are_grounded, text_digest
from epistemic_foundry.contracts import repo_root

DOCUMENT = (
    "Introduction text that precedes the finding. "
    "Spaced retrieval practice produced higher delayed-recall scores than rereading. "
    "Discussion follows."
)
FINDING = "Spaced retrieval practice produced higher delayed-recall scores than rereading."
START = DOCUMENT.index(FINDING)


def _span(**overrides) -> dict:
    kwargs = dict(
        document_id="DOC-001",
        paper_version_id="PV-001-01",
        page=8,
        section="Results",
        semantic_unit="results",
        char_start=START,
        char_end=START + len(FINDING),
        verbatim_text=FINDING,
        parser_name="grobid",
        parser_version="0.8.0",
        provenance_manifest_id="PM-001",
    )
    kwargs.update(overrides)
    return build_source_span(**kwargs)


# -- grounding ----------------------------------------------------------


def test_span_anchors_its_text_to_the_document() -> None:
    span = _span()
    verify_span_text(span, DOCUMENT)
    assert span["text_hash"] == text_digest(FINDING)


def test_empty_verbatim_text_is_refused() -> None:
    with pytest.raises(GroundingFailure):
        _span(verbatim_text="   ", char_end=START + 3)


def test_inverted_range_is_refused() -> None:
    with pytest.raises(GroundingFailure):
        _span(char_start=100, char_end=50)


def test_range_width_must_match_the_text_length() -> None:
    """A span whose offsets cannot hold its own text is malformed."""
    with pytest.raises(GroundingFailure) as excinfo:
        _span(char_end=START + len(FINDING) - 5)
    assert "does not match verbatim text length" in str(excinfo.value)


def test_offsets_pointing_at_other_text_fail_verification() -> None:
    """The real check: re-reading the document must reproduce the span."""
    span = _span()
    shifted = dict(span)
    shifted["char_start"] = 0
    shifted["char_end"] = len(FINDING)
    with pytest.raises(GroundingFailure) as excinfo:
        verify_span_text(shifted, DOCUMENT)
    assert "does not match the document" in str(excinfo.value)


def test_edited_text_with_stale_hash_fails_verification() -> None:
    span = _span()
    tampered = dict(span)
    tampered["verbatim_text"] = FINDING.replace("higher", "lower")
    with pytest.raises(GroundingFailure):
        verify_span_text(tampered, DOCUMENT)


def test_span_past_the_end_of_the_document_fails() -> None:
    span = _span()
    with pytest.raises(GroundingFailure):
        verify_span_text(span, DOCUMENT[:20])


def test_spans_are_grounded_is_non_raising() -> None:
    assert spans_are_grounded([_span()], DOCUMENT) is True
    assert spans_are_grounded([_span()], "unrelated document") is False


# -- evidence -----------------------------------------------------------


def _sample_evidence() -> dict:
    return json.loads((repo_root() / "examples" / "sample_evidence.json").read_text(encoding="utf-8"))


def _evidence(**overrides) -> dict:
    sample = _sample_evidence()
    kwargs = dict(
        claim_ids=sample["claim_ids"],
        source_spans=sample["source_spans"],
        experiment_id=sample["experiment_id"],
        role=sample["role"],
        scope=sample["scope"],
        method_ids=sample["method_ids"],
        dataset_family_id=sample["dataset_family_id"],
        quality=sample["quality"],
        provenance_manifest_id=sample["provenance_manifest_id"],
        evidence_class=sample["evidence_class"],
        source_integrity_report_id=sample["source_integrity_report_id"],
    )
    kwargs.update(overrides)
    return build_evidence_node(**kwargs)


def test_evidence_node_matches_the_canonical_schema() -> None:
    node = _evidence()
    assert node["role"] == "support"
    assert node["validity_status"] == "active"


def test_evidence_without_a_claim_is_refused() -> None:
    with pytest.raises(ValueError):
        _evidence(claim_ids=[])


def test_unanchored_evidence_is_refused() -> None:
    """Evidence with no span is unfalsifiable, so it is not storable."""
    with pytest.raises(ValueError) as excinfo:
        _evidence(source_spans=[])
    assert "unanchored evidence is refused" in str(excinfo.value)


def test_role_is_not_defaulted_to_support() -> None:
    """A counter-example must not be filable as agreement by omission."""
    signature = inspect.signature(build_evidence_node)
    assert signature.parameters["role"].default is inspect.Parameter.empty


def test_invalidated_evidence_stops_counting_as_support() -> None:
    active = _evidence()
    invalidated = _evidence(validity_status="invalidated")
    assert supporting_evidence([active, invalidated]) == [active]


def test_dissenting_lanes_stay_visible() -> None:
    counter = _evidence(role="counter")
    null_result = _evidence(role="null")
    boundary = _evidence(role="boundary")
    support = _evidence()
    visible = dissenting_evidence([support, counter, null_result, boundary])
    assert [node["role"] for node in visible] == ["counter", "null", "boundary"]
