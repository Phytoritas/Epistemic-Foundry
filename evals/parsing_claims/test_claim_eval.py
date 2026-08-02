"""claim_eval — precision, recall and unsupported promotion are measured.

Exit criterion under test: "precision/recall and unsupported promotion
measured".  The metrics are recomputed from the counts the report exposes, the
match key is stated rather than implied, and promotion is counted separately
from precision so a system that invents evidence strength cannot hide behind a
good F1.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evaluator import (
    MATCH_FIELDS,
    UNSUPPORTED_LAYER,
    ClaimEvalError,
    evaluate,
    evaluate_corpus,
    evidence_layers,
    load_corpus,
    match_key,
)

ROOT = Path(__file__).resolve().parents[2]


def corpus() -> dict:
    return copy.deepcopy(load_corpus(ROOT))


def claim_of(payload: dict, claim_id: str) -> dict:
    for key in ("gold_claims", "predicted_claims"):
        for claim in payload[key]:
            if claim["claim_id"] == claim_id:
                return claim
    raise AssertionError(claim_id)


def refused(payload: dict) -> ClaimEvalError:
    with pytest.raises(ClaimEvalError) as caught:
        evaluate(payload, ROOT)
    return caught.value


def test_the_committed_corpus_evaluates() -> None:
    report = evaluate_corpus(ROOT).payload

    assert report["corpus_id"] == "Q02-PARSING-CLAIMS"
    assert report["counts"] == {
        "documents": 2,
        "gold_claims": 8,
        "predicted_claims": 8,
    }


def test_precision_and_recall_are_recomputable_from_the_reported_counts() -> None:
    metrics = evaluate_corpus(ROOT).payload["metrics"]
    true_positive = metrics["true_positive"]

    assert metrics["precision"] == pytest.approx(
        true_positive / (true_positive + metrics["false_positive"])
    )
    assert metrics["recall"] == pytest.approx(
        true_positive / (true_positive + metrics["false_negative"])
    )
    assert metrics["f1"] == pytest.approx(
        2
        * metrics["precision"]
        * metrics["recall"]
        / (metrics["precision"] + metrics["recall"])
    )


def test_the_measured_values_are_the_ones_v1_actually_scores() -> None:
    metrics = evaluate_corpus(ROOT).payload["metrics"]

    assert metrics["true_positive"] == 6
    assert metrics["false_positive"] == 2
    assert metrics["false_negative"] == 2
    assert metrics["precision"] == pytest.approx(0.75)
    assert metrics["recall"] == pytest.approx(0.75)


def test_the_match_key_is_stated_rather_than_implied() -> None:
    report = evaluate_corpus(ROOT).payload

    assert report["match_fields"] == list(MATCH_FIELDS)
    assert MATCH_FIELDS == ("subject", "relation", "object", "direction")


def test_the_match_key_ignores_case_and_padding_but_not_direction() -> None:
    payload = corpus()
    gold = claim_of(payload, "GC-001")
    predicted = claim_of(payload, "PC-001")

    assert match_key(gold) == match_key(predicted)
    flipped = dict(predicted)
    flipped["direction"] = "positive"
    assert match_key(flipped) != match_key(gold)


def test_an_inverted_direction_scores_as_a_miss_not_a_hit() -> None:
    payload = corpus()
    claim_of(payload, "PC-001")["direction"] = "positive"
    metrics = evaluate(payload, ROOT).payload["metrics"]

    assert metrics["true_positive"] == 5
    assert metrics["false_positive"] == 3
    assert metrics["false_negative"] == 3


def test_a_perfect_prediction_set_scores_one() -> None:
    payload = corpus()
    payload["predicted_claims"] = [
        {**claim, "claim_id": claim["claim_id"].replace("GC-", "PX-")}
        for claim in payload["gold_claims"]
    ]
    report = evaluate(payload, ROOT).payload

    assert report["metrics"]["precision"] == pytest.approx(1.0)
    assert report["metrics"]["recall"] == pytest.approx(1.0)
    assert report["metrics"]["f1"] == pytest.approx(1.0)
    assert report["unsupported_promotion"]["count"] == 0


def test_unsupported_promotion_names_the_claims_that_promoted() -> None:
    promotion = evaluate_corpus(ROOT).payload["unsupported_promotion"]

    assert promotion["claim_ids"] == ["PC-003", "PC-004"]
    assert promotion["count"] == 2
    assert promotion["denominator"] == 6
    assert promotion["rate"] == pytest.approx(2 / 6)


def test_promotion_is_counted_separately_from_precision() -> None:
    payload = corpus()
    for claim_id in ("PC-003", "PC-004"):
        claim_of(payload, claim_id)["evidence_layer"] = UNSUPPORTED_LAYER
    report = evaluate(payload, ROOT).payload

    assert report["metrics"]["precision"] == pytest.approx(0.75)
    assert report["unsupported_promotion"]["count"] == 0


def test_promotion_is_undefined_rather_than_zero_without_a_matched_pair() -> None:
    payload = corpus()
    for claim in payload["predicted_claims"]:
        claim["subject"] = f"unmatched {claim['claim_id']}"
    report = evaluate(payload, ROOT).payload

    assert report["metrics"]["true_positive"] == 0
    assert report["unsupported_promotion"]["rate"] is None
    assert "undefined" in report["unsupported_promotion"]["reason"]


def test_demoting_a_supported_claim_is_not_counted_as_promotion() -> None:
    payload = corpus()
    claim_of(payload, "PC-001")["evidence_layer"] = UNSUPPORTED_LAYER
    report = evaluate(payload, ROOT).payload

    assert "PC-001" not in report["unsupported_promotion"]["claim_ids"]


def test_the_claim_vocabularies_come_from_the_canonical_schema() -> None:
    layers = evidence_layers(ROOT)
    schema = json.loads(
        (ROOT / "schemas/claim-card.schema.json").read_text(encoding="utf-8")
    )

    assert list(layers) == schema["properties"]["evidence_layer"]["enum"]
    assert UNSUPPORTED_LAYER in layers


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("claim_type", "vibes"),
        ("author_stance", "confident"),
        ("direction", "up"),
        ("evidence_layer", "trust_me"),
    ],
)
def test_a_non_canonical_claim_value_is_refused(field: str, value: str) -> None:
    payload = corpus()
    claim_of(payload, "GC-001")[field] = value

    error = refused(payload)
    assert error.code == "VOCABULARY_INVALID"
    assert error.context["field"] == field


def test_two_gold_claims_with_one_identity_are_refused() -> None:
    payload = corpus()
    duplicate = copy.deepcopy(claim_of(payload, "GC-001"))
    duplicate["claim_id"] = "GC-901"
    payload["gold_claims"].append(duplicate)

    assert refused(payload).code == "DUPLICATE_MATCH_KEY"


def test_a_duplicate_claim_id_is_refused() -> None:
    payload = corpus()
    duplicate = copy.deepcopy(claim_of(payload, "GC-001"))
    duplicate["subject"] = "something else"
    payload["predicted_claims"].append(duplicate)

    assert refused(payload).code == "DUPLICATE_CLAIM"


def test_an_empty_prediction_set_is_refused_rather_than_scored_zero() -> None:
    payload = corpus()
    payload["predicted_claims"] = []

    assert refused(payload).code == "INPUT_INVALID"


def test_a_corpus_claiming_a_real_extractor_is_refused() -> None:
    payload = corpus()
    payload["extractor_under_test"]["synthetic"] = False

    assert refused(payload).code == "EXTRACTOR_OVERCLAIM"


def test_an_unknown_corpus_field_is_refused() -> None:
    payload = corpus()
    payload["notes"] = "extra"

    assert refused(payload).code == "FIELD_SET_INVALID"


def test_the_report_is_deterministic_and_content_addressed() -> None:
    first = evaluate_corpus(ROOT)
    second = evaluate_corpus(ROOT)

    assert first.canonical_bytes == second.canonical_bytes
    assert first.payload["report_hash"].startswith("sha256:")


def test_the_corpus_file_is_canonical_json_on_disk() -> None:
    raw = (ROOT / "evals/parsing_claims/parsing_claims_cases.json").read_text(
        encoding="utf-8"
    )

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )
