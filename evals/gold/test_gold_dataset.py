"""gold_dataset_validation — false, true, and boundary cases are represented.

Exit criterion under test: "false/true/boundary cases represented".  A corpus
of clear positives measures nothing, so all three classes must be present in
usable numbers, every case must be grounded in a source span, and a boundary
case must state the condition that makes it a boundary rather than merely hard.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from validator import (
    CASE_CLASSES,
    MANUAL_RELATIVE_PATH,
    MINIMUM_ANNOTATORS,
    MINIMUM_CASES_PER_CLASS,
    CaseClass,
    GoldCorpusError,
    load_corpus,
    validate_corpus,
    validate_repository_corpus,
)

ROOT = Path(__file__).resolve().parents[2]


def corpus() -> dict:
    return copy.deepcopy(load_corpus(ROOT))


def case_of(payload: dict, case_id: str) -> dict:
    return next(case for case in payload["cases"] if case["case_id"] == case_id)


def test_the_committed_corpus_validates() -> None:
    report = validate_repository_corpus(ROOT).payload

    assert report["case_count"] == 12
    assert report["corpus_hash"].startswith("sha256:")


def test_all_three_classes_are_represented_in_usable_numbers() -> None:
    report = validate_repository_corpus(ROOT).payload

    assert sorted(report["coverage"]) == sorted(CASE_CLASSES)
    for label, count in report["coverage"].items():
        assert count >= MINIMUM_CASES_PER_CLASS, label


def test_a_corpus_missing_a_class_is_refused() -> None:
    payload = corpus()
    payload["cases"] = [
        case
        for case in payload["cases"]
        if case["case_class"] != CaseClass.BOUNDARY.value
    ]

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "CASE_CLASS_MISSING"
    assert "BOUNDARY" in caught.value.context["classes"]


def test_a_corpus_thin_in_one_class_is_refused() -> None:
    payload = corpus()
    keep = [
        case
        for case in payload["cases"]
        if case["case_class"] != CaseClass.FALSE_INSIGHT.value
    ]
    thin = [
        case
        for case in payload["cases"]
        if case["case_class"] == CaseClass.FALSE_INSIGHT.value
    ][:2]
    payload["cases"] = keep + thin

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "CASE_CLASS_MISSING"
    assert caught.value.context["minimum"] == MINIMUM_CASES_PER_CLASS


def test_every_boundary_case_states_its_condition() -> None:
    payload = corpus()

    for case in payload["cases"]:
        if case["case_class"] == CaseClass.BOUNDARY.value:
            assert case["boundary_condition"], case["case_id"]
        else:
            assert case["boundary_condition"] is None, case["case_id"]


def test_a_boundary_case_without_a_condition_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-boundary-001")["boundary_condition"] = None

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "INPUT_INVALID"


def test_a_non_boundary_case_may_not_carry_a_condition() -> None:
    payload = corpus()
    case_of(payload, "GC-true-001")["boundary_condition"] = "sometimes"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "BOUNDARY_CONDITION_UNEXPECTED"


def test_every_case_is_grounded_in_a_source_span() -> None:
    payload = corpus()

    for case in payload["cases"]:
        assert case["source_spans"], case["case_id"]


def test_a_case_with_no_source_span_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-true-002")["source_spans"] = []

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "CASE_UNGROUNDED"


def test_every_case_carries_at_least_two_annotations() -> None:
    payload = corpus()

    assert MINIMUM_ANNOTATORS == 2
    for case in payload["cases"]:
        assert len(case["annotations"]) >= MINIMUM_ANNOTATORS, case["case_id"]


def test_a_single_annotator_case_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-true-003")["annotations"] = case_of(payload, "GC-true-003")[
        "annotations"
    ][:1]

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "INSUFFICIENT_ANNOTATORS"


def test_one_annotator_may_not_label_a_case_twice() -> None:
    payload = corpus()
    case = case_of(payload, "GC-true-004")
    case["annotations"].append(dict(case["annotations"][0]))

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "ANNOTATOR_DUPLICATED"


def test_a_non_canonical_class_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-true-001")["case_class"] = "PROBABLY_TRUE"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "CASE_CLASS_INVALID"


def test_a_non_canonical_annotation_label_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-true-001")["annotations"][0]["label"] = "MAYBE"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "LABEL_INVALID"


def test_the_gold_label_must_match_the_class_the_case_is_filed_under() -> None:
    payload = corpus()
    case_of(payload, "GC-true-001")["gold_label"] = CaseClass.FALSE_INSIGHT.value

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "GOLD_LABEL_INCONSISTENT"


def test_a_duplicate_case_id_is_refused() -> None:
    payload = corpus()
    payload["cases"].append(copy.deepcopy(payload["cases"][0]))

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "DUPLICATE_CASE"


def test_the_corpus_must_cite_the_manual_it_was_labelled_under() -> None:
    payload = corpus()
    payload["annotation_manual"] = "docs/some_other_guide.md"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "MANUAL_UNBOUND"


def test_the_cited_manual_exists_and_binds_this_corpus() -> None:
    payload = corpus()
    manual = (ROOT / MANUAL_RELATIVE_PATH).read_text(encoding="utf-8")

    assert payload["annotation_manual"] == MANUAL_RELATIVE_PATH
    assert "evals/gold/insight_gold_cases.json" in manual
    assert "GC-false-004" in manual
    assert "GC-boundary-004" in manual


def test_an_unknown_corpus_field_is_refused() -> None:
    payload = corpus()
    payload["notes"] = "extra"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "FIELD_SET_INVALID"


def test_the_corpus_file_is_canonical_json_on_disk() -> None:
    raw = (ROOT / "evals" / "gold" / "insight_gold_cases.json").read_text(
        encoding="utf-8"
    )

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )


def test_the_report_is_deterministic_and_content_addressed() -> None:
    first = validate_repository_corpus(ROOT)
    second = validate_repository_corpus(ROOT)

    assert first.canonical_bytes == second.canonical_bytes
