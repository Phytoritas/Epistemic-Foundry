"""annotation_agreement_check — adjudication is defined and agreement measured.

Exit criterion under test: "annotator adjudication defined".  Disagreement is
resolved on the record by someone who is neither annotator, with a canonical
resolution and a cited reason; the gold label is the one that survived.
Agreement is a computed coefficient with its inputs exposed, not a claim.
"""

from __future__ import annotations

import copy

import pytest

from validator import (
    KAPPA_FLOOR,
    RESOLUTIONS,
    CaseClass,
    GoldCorpusError,
    Resolution,
    fleiss_kappa,
    validate_corpus,
    validate_repository_corpus,
)
from test_gold_dataset import ROOT, case_of, corpus


def annotated(labels: list[tuple[str, ...]]) -> list[dict]:
    return [
        {
            "annotations": [
                {"annotator_id": f"ann-{index}", "label": label}
                for index, label in enumerate(row)
            ]
        }
        for row in labels
    ]


def test_the_committed_corpus_measures_agreement_above_its_floor() -> None:
    report = validate_repository_corpus(ROOT).payload
    agreement = report["agreement"]

    assert agreement["kappa"] == pytest.approx(0.7486910995)
    assert agreement["kappa"] >= report["kappa_floor"] >= KAPPA_FLOOR
    assert agreement["rater_count"] == 2
    assert agreement["case_count"] == 12


def test_the_coefficient_exposes_the_inputs_it_was_derived_from() -> None:
    agreement = validate_repository_corpus(ROOT).payload["agreement"]

    assert agreement["observed_agreement"] == pytest.approx(0.8333333333)
    assert agreement["expected_agreement"] == pytest.approx(0.3368055556)
    assert sum(agreement["label_proportions"].values()) == pytest.approx(1.0)
    recomputed = (agreement["observed_agreement"] - agreement["expected_agreement"]) / (
        1.0 - agreement["expected_agreement"]
    )
    assert recomputed == pytest.approx(agreement["kappa"])


def test_perfect_agreement_across_several_labels_is_kappa_one() -> None:
    agreement = fleiss_kappa(
        annotated(
            [
                (CaseClass.TRUE_INSIGHT.value, CaseClass.TRUE_INSIGHT.value),
                (CaseClass.FALSE_INSIGHT.value, CaseClass.FALSE_INSIGHT.value),
                (CaseClass.BOUNDARY.value, CaseClass.BOUNDARY.value),
            ]
        )
    )

    assert agreement["kappa"] == pytest.approx(1.0)


def test_a_single_label_corpus_has_no_variance_and_is_undefined() -> None:
    agreement = fleiss_kappa(
        annotated(
            [
                (CaseClass.TRUE_INSIGHT.value, CaseClass.TRUE_INSIGHT.value),
                (CaseClass.TRUE_INSIGHT.value, CaseClass.TRUE_INSIGHT.value),
            ]
        )
    )

    assert agreement["kappa"] is None
    assert (
        agreement["reason"]
        == "every annotation used one label, so there is no variance"
    )


def test_an_undefined_coefficient_fails_the_corpus_rather_than_passing_it() -> None:
    payload = corpus()
    for case in payload["cases"]:
        case["case_class"] = CaseClass.TRUE_INSIGHT.value
        case["gold_label"] = CaseClass.TRUE_INSIGHT.value
        case["boundary_condition"] = None
        case["adjudication"] = None
        for annotation in case["annotations"]:
            annotation["label"] = CaseClass.TRUE_INSIGHT.value

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "CASE_CLASS_MISSING"


def test_total_disagreement_is_at_or_below_zero() -> None:
    agreement = fleiss_kappa(
        annotated(
            [
                (CaseClass.TRUE_INSIGHT.value, CaseClass.FALSE_INSIGHT.value),
                (CaseClass.FALSE_INSIGHT.value, CaseClass.TRUE_INSIGHT.value),
            ]
        )
    )

    assert agreement["kappa"] <= 0.0


def test_an_uneven_rater_count_is_reported_rather_than_averaged() -> None:
    agreement = fleiss_kappa(
        [
            {
                "annotations": [
                    {"annotator_id": "a", "label": CaseClass.TRUE_INSIGHT.value},
                    {"annotator_id": "b", "label": CaseClass.TRUE_INSIGHT.value},
                ]
            },
            {
                "annotations": [
                    {"annotator_id": "a", "label": CaseClass.FALSE_INSIGHT.value},
                    {"annotator_id": "b", "label": CaseClass.FALSE_INSIGHT.value},
                    {"annotator_id": "c", "label": CaseClass.FALSE_INSIGHT.value},
                ]
            },
        ]
    )

    assert agreement["kappa"] is None
    assert "same number of raters" in agreement["reason"]


def test_a_corpus_below_its_declared_floor_is_refused() -> None:
    payload = corpus()
    for case in payload["cases"]:
        if case["case_class"] == CaseClass.TRUE_INSIGHT.value:
            case["annotations"][1]["label"] = CaseClass.FALSE_INSIGHT.value
            case["adjudication"] = {
                "adjudicator_id": "ann-c",
                "decided_at": "2026-08-01T19:00:00Z",
                "reason": "the source measures the construct the claim is about",
                "resolution": Resolution.ANNOTATOR_A_CORRECT.value,
            }

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "AGREEMENT_BELOW_FLOOR"
    assert caught.value.context["kappa"] < caught.value.context["floor"]


def test_a_floor_weaker_than_the_contract_floor_is_refused() -> None:
    payload = corpus()
    payload["kappa_floor"] = 0.1

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "KAPPA_FLOOR_TOO_LOW"
    assert caught.value.context["contract_floor"] == KAPPA_FLOOR


def test_every_disagreement_in_the_corpus_is_adjudicated() -> None:
    report = validate_repository_corpus(ROOT).payload

    assert report["adjudicated_case_ids"] == ["GC-boundary-004", "GC-false-004"]
    for case in report["cases"]:
        labels = {entry["label"] for entry in case["annotations"]}
        if len(labels) > 1:
            assert case["adjudication"] is not None, case["case_id"]
        else:
            assert case["adjudication"] is None, case["case_id"]


def test_an_unadjudicated_disagreement_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-false-004")["adjudication"] = None

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "DISAGREEMENT_UNADJUDICATED"
    assert caught.value.context["case_id"] == "GC-false-004"


def test_an_annotator_may_not_adjudicate_its_own_disagreement() -> None:
    payload = corpus()
    case_of(payload, "GC-false-004")["adjudication"]["adjudicator_id"] = "ann-a"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "ADJUDICATOR_NOT_INDEPENDENT"


def test_a_unanimous_case_may_not_carry_an_adjudication() -> None:
    payload = corpus()
    case_of(payload, "GC-true-001")["adjudication"] = copy.deepcopy(
        case_of(payload, "GC-false-004")["adjudication"]
    )

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "ADJUDICATION_UNEXPECTED"


def test_a_non_canonical_resolution_is_refused() -> None:
    payload = corpus()
    case_of(payload, "GC-false-004")["adjudication"]["resolution"] = (
        "SPLIT_THE_DIFFERENCE"
    )

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "RESOLUTION_INVALID"


def test_the_resolution_vocabulary_admits_ambiguous_guidance() -> None:
    assert sorted(RESOLUTIONS) == [
        "ANNOTATOR_A_CORRECT",
        "ANNOTATOR_B_CORRECT",
        "GUIDANCE_AMBIGUOUS",
        "NEITHER_CORRECT",
    ]


def test_an_adjudication_must_cite_a_reason() -> None:
    payload = corpus()
    case_of(payload, "GC-false-004")["adjudication"]["reason"] = "  "

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "INPUT_INVALID"


def test_an_adjudication_must_be_dated() -> None:
    payload = corpus()
    case_of(payload, "GC-false-004")["adjudication"]["decided_at"] = "yesterday"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "INPUT_INVALID"


def test_the_gold_label_of_a_unanimous_case_is_the_one_both_gave() -> None:
    report = validate_repository_corpus(ROOT).payload

    for case in report["cases"]:
        labels = {entry["label"] for entry in case["annotations"]}
        if len(labels) == 1:
            assert case["gold_label"] == labels.pop(), case["case_id"]


def test_a_unanimous_case_cannot_take_a_third_label() -> None:
    payload = corpus()
    case = case_of(payload, "GC-true-001")
    case["case_class"] = CaseClass.BOUNDARY.value
    case["gold_label"] = CaseClass.BOUNDARY.value
    case["boundary_condition"] = "invented"

    with pytest.raises(GoldCorpusError) as caught:
        validate_corpus(payload)

    assert caught.value.code == "GOLD_LABEL_UNSUPPORTED"


def test_the_adjudicated_cases_follow_the_standing_scope_rule() -> None:
    report = validate_repository_corpus(ROOT).payload

    scope_jump = next(
        case for case in report["cases"] if case["case_id"] == "GC-false-004"
    )
    named_condition = next(
        case for case in report["cases"] if case["case_id"] == "GC-boundary-004"
    )

    assert scope_jump["gold_label"] == CaseClass.FALSE_INSIGHT.value
    assert scope_jump["boundary_condition"] is None
    assert named_condition["gold_label"] == CaseClass.BOUNDARY.value
    assert named_condition["boundary_condition"]
