"""unit_and_contract_tests — the published numbers are recomputable.

Every metric the two gates publish is recomputed here from the committed items
rather than compared against a copy of itself: per-slice accuracy and withheld
counts from the publication dates, the robustness delta from the paired
baselines, the per-class deltas from their own members.  The determinism
contract is exercised too — the same dataset yields byte-identical reports, and
neither gate mutates the payload it was handed.
"""

from __future__ import annotations

import pytest

import adversarial_harness
import time_sliced_harness
from fixtures import ROOT, adversarial_payload, time_sliced_payload


def time_sliced_report() -> dict:
    return time_sliced_harness.evaluate_benchmark(ROOT).payload


def adversarial_report() -> dict:
    return adversarial_harness.evaluate_benchmark(ROOT).payload


def test_the_committed_time_sliced_benchmark_evaluates() -> None:
    report = time_sliced_report()

    assert report["benchmark_id"] == "Q04-TIME-SLICED"
    assert report["counts"] == {"documents": 7, "items": 12, "slices": 3}
    assert report["overall"]["correct"] == 8
    assert report["overall"]["accuracy"] == pytest.approx(8 / 12)


def test_every_slice_metric_is_recomputable_from_the_items() -> None:
    payload = time_sliced_payload()
    published = {
        document["document_id"]: document["published_at"]
        for document in payload["documents"]
    }

    for entry in time_sliced_report()["slices"]:
        members = [
            item for item in payload["items"] if item["slice_id"] == entry["slice_id"]
        ]
        correct = sum(
            1 for item in members if item["predicted_label"] == item["gold_label"]
        )
        assert entry["item_count"] == len(members)
        assert entry["correct"] == correct
        assert entry["accuracy"] == pytest.approx(correct / len(members))
        assert entry["date_checks"] == sum(
            len(item["visible_document_ids"]) for item in members
        )
        assert entry["withheld_document_ids"] == sorted(
            document_id
            for document_id, date in published.items()
            if date > entry["as_of"]
        )
        assert entry["eligible_document_ids"] == sorted(
            document_id
            for document_id, date in published.items()
            if date <= entry["as_of"]
        )
        assert entry["eligible_document_count"] + entry[
            "withheld_document_count"
        ] == len(published)


def test_the_leakage_evidence_counts_every_visible_document() -> None:
    payload = time_sliced_payload()
    report = time_sliced_report()

    assert report["leakage"]["documents_checked"] == sum(
        len(item["visible_document_ids"]) for item in payload["items"]
    )
    assert report["leakage"]["future_documents_admitted"] == 0
    assert report["leakage"]["withheld_document_total"] == sum(
        entry["withheld_document_count"] for entry in report["slices"]
    )


def test_the_overall_time_sliced_accuracy_is_the_sum_of_its_slices() -> None:
    report = time_sliced_report()

    assert report["overall"]["correct"] == sum(
        entry["correct"] for entry in report["slices"]
    )
    assert report["overall"]["item_count"] == sum(
        entry["item_count"] for entry in report["slices"]
    )


def test_the_committed_adversarial_benchmark_evaluates() -> None:
    report = adversarial_report()

    assert report["benchmark_id"] == "Q04-ADVERSARIAL"
    assert report["counts"] == {
        "adversarial_items": 8,
        "attack_classes": 4,
        "baseline_items": 8,
        "label_changed_items": 4,
    }


def test_the_robustness_delta_is_measured_against_the_paired_baselines() -> None:
    payload = adversarial_payload()
    baselines = {item["item_id"]: item for item in payload["baseline_items"]}
    report = adversarial_report()

    paired = [
        baselines[item["baseline_item_id"]] for item in payload["adversarial_items"]
    ]
    baseline_correct = sum(
        1 for item in paired if item["predicted_label"] == item["gold_label"]
    )
    adversarial_correct = sum(
        1
        for item in payload["adversarial_items"]
        if item["predicted_label"] == item["gold_label"]
    )

    assert report["baseline"]["correct"] == baseline_correct
    assert report["adversarial"]["correct"] == adversarial_correct
    assert report["robustness_delta"] == pytest.approx(
        adversarial_correct / len(paired) - baseline_correct / len(paired)
    )


def test_every_attack_class_delta_is_recomputable_from_its_members() -> None:
    payload = adversarial_payload()
    baselines = {item["item_id"]: item for item in payload["baseline_items"]}

    for entry in adversarial_report()["attack_classes"]:
        members = [
            item
            for item in payload["adversarial_items"]
            if item["attack_class"] == entry["attack_class"]
        ]
        paired = [baselines[item["baseline_item_id"]] for item in members]
        assert entry["item_ids"] == sorted(item["item_id"] for item in members)
        assert entry["adversarial"]["correct"] == sum(
            1 for item in members if item["predicted_label"] == item["gold_label"]
        )
        assert entry["baseline"]["correct"] == sum(
            1 for item in paired if item["predicted_label"] == item["gold_label"]
        )
        assert entry["robustness_delta"] == pytest.approx(
            entry["adversarial"]["accuracy"] - entry["baseline"]["accuracy"]
        )
        assert entry["label_changed_count"] == sum(
            1
            for item, base in zip(members, paired)
            if item["gold_label"] != base["gold_label"]
        )


def test_a_label_move_is_recorded_with_its_rationale_and_nowhere_else() -> None:
    payload = adversarial_payload()
    baselines = {item["item_id"]: item for item in payload["baseline_items"]}

    for item in payload["adversarial_items"]:
        moved = item["gold_label"] != baselines[item["baseline_item_id"]]["gold_label"]
        assert moved == (item["label_change_rationale"] is not None), item["item_id"]


def test_the_declared_attack_signature_is_present_where_it_is_declared() -> None:
    payload = adversarial_payload()
    markers = {
        entry["attack_class"]: entry["evidence_marker"]
        for entry in payload["attack_classes"]
    }

    marked = [name for name, marker in markers.items() if marker is not None]
    assert len(marked) == 1
    for item in payload["adversarial_items"]:
        marker = markers[item["attack_class"]]
        if marker is not None:
            assert marker in item["evidence_text"], item["item_id"]


def test_both_gates_are_deterministic_over_the_same_dataset() -> None:
    assert (
        time_sliced_harness.evaluate_benchmark(ROOT).canonical_bytes
        == time_sliced_harness.evaluate_benchmark(ROOT).canonical_bytes
    )
    assert (
        adversarial_harness.evaluate_benchmark(ROOT).canonical_bytes
        == adversarial_harness.evaluate_benchmark(ROOT).canonical_bytes
    )


def test_neither_gate_mutates_the_payload_it_was_handed() -> None:
    time_sliced = time_sliced_payload()
    adversarial = adversarial_payload()
    before = (
        time_sliced_harness.canonical_json(time_sliced),
        adversarial_harness.canonical_json(adversarial),
    )

    time_sliced_harness.evaluate(time_sliced, ROOT)
    adversarial_harness.evaluate(adversarial, ROOT)

    assert time_sliced_harness.canonical_json(time_sliced) == before[0]
    assert adversarial_harness.canonical_json(adversarial) == before[1]


def test_a_sealed_report_projection_cannot_be_edited_in_place() -> None:
    sealed = time_sliced_harness.evaluate_benchmark(ROOT)
    projection = sealed.payload
    projection["overall"]["correct"] = 0

    assert sealed.payload["overall"]["correct"] == 8
