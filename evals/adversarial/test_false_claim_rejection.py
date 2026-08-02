"""false_claim_rejection_test — known false claims are rejected, and counted.

Exit criterion under test: "known false claims rejected".  The rejection rate
is recomputed here from the items rather than read back from the report, it is
reported separately for the unperturbed baselines and for the perturbations,
and the items the system admitted are named.  The three refusals that keep the
number honest are exercised: an adversarial item with no baseline, a
perturbation that moved the gold label without recording why, and an attack
class the report would otherwise claim coverage of with zero items.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from adversarial_harness import (
    AdversarialEvalError,
    evaluate,
    evaluate_benchmark,
    gold_case_labels,
    hash_excluding,
    load_benchmark,
    verify_results,
)

ROOT = Path(__file__).resolve().parents[2]


def benchmark() -> dict:
    return copy.deepcopy(load_benchmark(ROOT))


def resealed(payload: dict) -> dict:
    payload["dataset_hash"] = hash_excluding(payload, "dataset_hash")
    return payload


def refused(payload: dict, code: str) -> AdversarialEvalError:
    with pytest.raises(AdversarialEvalError) as caught:
        evaluate(payload, ROOT)
    assert caught.value.code == code, caught.value.code
    return caught.value


def adversarial_item(payload: dict, item_id: str) -> dict:
    for item in payload["adversarial_items"]:
        if item["item_id"] == item_id:
            return item
    raise AssertionError(item_id)


def test_the_committed_benchmark_evaluates() -> None:
    report = evaluate_benchmark(ROOT).payload

    assert report["benchmark_id"] == "Q04-ADVERSARIAL"
    assert report["counts"] == {
        "adversarial_items": 8,
        "attack_classes": 4,
        "baseline_items": 8,
        "label_changed_items": 4,
    }


def test_the_rejection_rate_is_recomputable_from_the_items() -> None:
    payload = benchmark()
    report = evaluate_benchmark(ROOT).payload
    false_label = payload["false_claim_label"]

    known_false = [
        item
        for item in payload["adversarial_items"]
        if item["gold_label"] == false_label
    ]
    rejected = [item for item in known_false if item["predicted_label"] == false_label]

    measured = report["false_claim_rejection"]["adversarial"]
    assert measured["known_false_count"] == len(known_false)
    assert measured["rejected_count"] == len(rejected)
    assert measured["rate"] == pytest.approx(len(rejected) / len(known_false))
    assert measured["admitted_item_ids"] == sorted(
        item["item_id"] for item in known_false if item not in rejected
    )


def test_the_perturbations_are_harder_than_the_baselines_they_came_from() -> None:
    report = evaluate_benchmark(ROOT).payload

    assert report["robustness_delta"] == pytest.approx(
        report["adversarial"]["accuracy"] - report["baseline"]["accuracy"]
    )
    assert report["robustness_delta"] < 0
    assert (
        report["false_claim_rejection"]["baseline"]["rate"]
        > (report["false_claim_rejection"]["adversarial"]["rate"])
    )


def test_every_declared_attack_class_carries_measured_items() -> None:
    report = evaluate_benchmark(ROOT).payload

    assert [entry["attack_class"] for entry in report["attack_classes"]] == sorted(
        entry["attack_class"] for entry in benchmark()["attack_classes"]
    )
    for entry in report["attack_classes"]:
        assert entry["adversarial"]["item_count"] > 0, entry["attack_class"]
        assert entry["robustness_delta"] == pytest.approx(
            entry["adversarial"]["accuracy"] - entry["baseline"]["accuracy"]
        )


def test_every_baseline_item_is_a_sealed_gold_case() -> None:
    labels = gold_case_labels(ROOT)

    for item in benchmark()["baseline_items"]:
        assert item["gold_label"] == labels[item["gold_case_id"]]


def test_an_adversarial_item_without_its_baseline_is_refused() -> None:
    payload = benchmark()
    adversarial_item(payload, "ADV-NEG-001")["baseline_item_id"] = "BASE-404"

    error = refused(resealed(payload), "BASELINE_MISSING")

    assert error.context["baseline_item_id"] == "BASE-404"


def test_a_label_move_without_a_recorded_rationale_is_refused() -> None:
    payload = benchmark()
    adversarial_item(payload, "ADV-NEG-001")["label_change_rationale"] = None

    error = refused(resealed(payload), "LABEL_CHANGE_UNJUSTIFIED")

    assert error.context["item_id"] == "ADV-NEG-001"


def test_an_attack_class_with_no_item_is_refused() -> None:
    payload = benchmark()
    payload["attack_classes"].append(
        {
            "attack_class": "UNIT_RESCALE",
            "description": "the reported unit is changed without rescaling the value",
            "evidence_marker": None,
        }
    )

    error = refused(resealed(payload), "ATTACK_CLASS_UNPOPULATED")

    assert error.context["attack_classes"] == ["UNIT_RESCALE"]


def test_the_committed_results_artifact_is_the_report_the_dataset_produces() -> None:
    derived = verify_results(ROOT)

    assert derived["report_hash"] == hash_excluding(derived, "report_hash")
