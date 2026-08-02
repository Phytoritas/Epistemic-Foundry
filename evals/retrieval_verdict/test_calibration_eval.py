"""calibration_eval — Brier and ECE are computed with their inputs exposed.

Exit criterion under test: "Brier/ECE reported".  Both statistics derive from
the same confidence/outcome pairs and are reported alongside the reliability
bins they came from, so the tests re-add the bins and recover the ECE rather
than trusting it.  The emitted document is validated against the canonical
CalibrationReport schema, and a sample too small to say anything is
INSUFFICIENT_DATA with both statistics null rather than a flattering number.
"""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest

from evaluator import (
    CALIBRATION_SCHEMA_PATH,
    MINIMUM_CALIBRATION_SAMPLE,
    RELIABILITY_BIN_COUNT,
    audit_calibration,
    brier_score,
    calibration_statuses,
    calibration_targets,
    evaluate,
    evaluate_corpus,
    expected_calibration_error,
    reliability_bins,
)
from test_retrieval_eval import ROOT, corpus, refused


def test_the_committed_corpus_reports_both_statistics() -> None:
    calibration = audit_calibration(ROOT)

    assert calibration["sample_count"] == 12
    assert calibration["brier_score"] == pytest.approx(0.1655333333, abs=1e-9)
    assert calibration["expected_calibration_error"] == pytest.approx(0.305)


def test_the_emitted_report_satisfies_the_canonical_schema() -> None:
    schema = json.loads((ROOT / CALIBRATION_SCHEMA_PATH).read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(audit_calibration(ROOT))


def test_the_target_and_status_come_from_the_canonical_schema() -> None:
    calibration = audit_calibration(ROOT)

    assert calibration["target"] in calibration_targets(ROOT)
    assert calibration["calibration_status"] in calibration_statuses(ROOT)
    assert calibration["target"] == "verdict"


def test_the_brier_score_is_recomputable_from_the_pairs() -> None:
    payload = evaluate_corpus(ROOT).payload
    cases = copy.deepcopy(corpus()["verdict_cases"])
    pairs = [
        (case["confidence"], case["predicted_verdict"] == case["gold_verdict"])
        for case in cases
    ]

    assert payload["calibration"]["brier_score"] == pytest.approx(brier_score(pairs))


def test_the_ece_is_recomputable_by_re_adding_the_reported_bins() -> None:
    calibration = audit_calibration(ROOT)
    total = calibration["sample_count"]
    recomputed = sum(
        (entry["count"] / total)
        * abs(entry["empirical_accuracy"] - entry["mean_confidence"])
        for entry in calibration["reliability_bins"]
        if entry["count"] > 0
    )

    assert recomputed == pytest.approx(calibration["expected_calibration_error"])


def test_the_bins_partition_the_unit_interval_and_hold_every_case() -> None:
    calibration = audit_calibration(ROOT)
    bins = calibration["reliability_bins"]

    assert len(bins) == RELIABILITY_BIN_COUNT
    assert bins[0]["lower"] == 0.0
    assert bins[-1]["upper"] == 1.0
    for lower, upper in zip(bins, bins[1:]):
        assert lower["upper"] == pytest.approx(upper["lower"])
    assert sum(entry["count"] for entry in bins) == calibration["sample_count"]


def test_an_empty_bin_reports_null_rather_than_zero() -> None:
    empty = [
        entry
        for entry in audit_calibration(ROOT)["reliability_bins"]
        if not entry["count"]
    ]

    assert empty
    for entry in empty:
        assert entry["mean_confidence"] is None
        assert entry["empirical_accuracy"] is None


def test_a_perfectly_calibrated_set_scores_zero_error() -> None:
    pairs = [(1.0, True)] * 6 + [(0.0, False)] * 6
    bins = reliability_bins(pairs)

    assert brier_score(pairs) == pytest.approx(0.0)
    assert expected_calibration_error(pairs, bins) == pytest.approx(0.0)


def test_a_confidently_wrong_set_scores_the_worst_brier() -> None:
    pairs = [(1.0, False)] * 5

    assert brier_score(pairs) == pytest.approx(1.0)


def test_a_confidence_of_one_lands_in_the_top_bin() -> None:
    bins = reliability_bins([(1.0, True)])

    assert bins[-1]["count"] == 1
    assert sum(entry["count"] for entry in bins) == 1


def test_a_confidence_of_zero_lands_in_the_bottom_bin() -> None:
    bins = reliability_bins([(0.0, False)])

    assert bins[0]["count"] == 1


def test_an_empty_pair_set_has_no_statistics() -> None:
    assert brier_score([]) is None
    assert expected_calibration_error([], reliability_bins([])) is None


def test_a_sample_below_the_floor_is_insufficient_rather_than_scored() -> None:
    payload = corpus()
    payload["verdict_cases"] = payload["verdict_cases"][
        : MINIMUM_CALIBRATION_SAMPLE - 1
    ]
    calibration = evaluate(payload, ROOT).payload["calibration"]

    assert calibration["calibration_status"] == "INSUFFICIENT_DATA"
    assert calibration["brier_score"] is None
    assert calibration["expected_calibration_error"] is None
    assert calibration["sample_count"] == MINIMUM_CALIBRATION_SAMPLE - 1


def test_a_well_calibrated_corpus_reaches_pass() -> None:
    payload = corpus()
    for index, case in enumerate(payload["verdict_cases"]):
        case["predicted_verdict"] = case["gold_verdict"]
        case["confidence"] = 0.95 if index % 2 == 0 else 0.92
    calibration = evaluate(payload, ROOT).payload["calibration"]

    assert calibration["calibration_status"] == "PASS"
    assert calibration["expected_calibration_error"] < 0.10


def test_the_committed_corpus_warns_rather_than_passing() -> None:
    calibration = audit_calibration(ROOT)

    assert calibration["calibration_status"] == "WARN"
    assert calibration["expected_calibration_error"] > 0.10


def test_the_calibration_hash_is_recomputable() -> None:
    from evaluator import _hash_excluding

    calibration = audit_calibration(ROOT)

    assert _hash_excluding(calibration, "report_hash") == calibration["report_hash"]


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_a_confidence_outside_the_unit_interval_is_refused(
    confidence: float,
) -> None:
    payload = corpus()
    payload["verdict_cases"][0]["confidence"] = confidence

    assert refused(payload).code == "CONFIDENCE_OUT_OF_RANGE"


def test_a_non_numeric_confidence_is_refused() -> None:
    payload = corpus()
    payload["verdict_cases"][0]["confidence"] = "high"

    assert refused(payload).code == "INPUT_INVALID"


def test_a_boolean_confidence_is_refused() -> None:
    payload = corpus()
    payload["verdict_cases"][0]["confidence"] = True

    assert refused(payload).code == "INPUT_INVALID"


def test_a_duplicate_case_id_is_refused() -> None:
    payload = corpus()
    payload["verdict_cases"].append(copy.deepcopy(payload["verdict_cases"][0]))

    assert refused(payload).code == "DUPLICATE_CASE"


def test_an_empty_verdict_set_is_refused() -> None:
    payload = corpus()
    payload["verdict_cases"] = []

    assert refused(payload).code == "INPUT_INVALID"


def test_the_calibration_audit_is_the_report_slice() -> None:
    assert audit_calibration(ROOT) == evaluate_corpus(ROOT).payload["calibration"]
