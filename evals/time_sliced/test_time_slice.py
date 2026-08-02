"""time_slice_test — future material is withheld, and the gate proves it.

Exit criterion under test: "future papers withheld correctly".  The committed
dataset is evaluated as it stands, the per-slice withheld lists are recomputed
from the publication dates rather than read back from the report, and a single
future-dated document injected into one item's visible set is refused.  A slice
that has nothing later than its own as-of time is refused too, because such a
slice reports a clean withholding record it never earned.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from time_sliced_harness import (
    TimeSliceError,
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


def refused(payload: dict, code: str) -> TimeSliceError:
    with pytest.raises(TimeSliceError) as caught:
        evaluate(payload, ROOT)
    assert caught.value.code == code, caught.value.code
    return caught.value


def item_of(payload: dict, item_id: str) -> dict:
    for item in payload["items"]:
        if item["item_id"] == item_id:
            return item
    raise AssertionError(item_id)


def test_the_committed_benchmark_evaluates() -> None:
    report = evaluate_benchmark(ROOT).payload

    assert report["benchmark_id"] == "Q04-TIME-SLICED"
    assert report["counts"] == {"documents": 7, "items": 12, "slices": 3}
    assert report["overall"] == {
        "accuracy": 8 / 12,
        "correct": 8,
        "item_count": 12,
    }


def test_every_slice_withholds_the_documents_published_after_it() -> None:
    payload = benchmark()
    published = {
        document["document_id"]: document["published_at"]
        for document in payload["documents"]
    }
    report = evaluate_benchmark(ROOT).payload

    for entry in report["slices"]:
        expected = sorted(
            document_id
            for document_id, date in published.items()
            if date > entry["as_of"]
        )
        assert entry["withheld_document_ids"] == expected
        assert entry["withheld_document_count"] == len(expected)
        assert expected, entry["slice_id"]


def test_no_item_ever_saw_material_dated_after_its_as_of_time() -> None:
    payload = benchmark()
    published = {
        document["document_id"]: document["published_at"]
        for document in payload["documents"]
    }
    checked = 0

    for item in payload["items"]:
        for document_id in item["visible_document_ids"]:
            checked += 1
            assert published[document_id] <= item["as_of"], item["item_id"]

    report = evaluate_benchmark(ROOT).payload
    assert report["leakage"]["documents_checked"] == checked
    assert report["leakage"]["future_documents_admitted"] == 0


def test_the_visible_corpus_grows_monotonically_across_slices() -> None:
    eligible = [
        set(entry["eligible_document_ids"])
        for entry in evaluate_benchmark(ROOT).payload["slices"]
    ]

    for earlier, later in zip(eligible, eligible[1:]):
        assert earlier < later


def test_every_item_is_bound_to_a_sealed_gold_case() -> None:
    labels = gold_case_labels(ROOT)

    for item in benchmark()["items"]:
        assert item["gold_label"] == labels[item["gold_case_id"]]


def test_a_future_document_in_the_visible_set_is_refused() -> None:
    payload = benchmark()
    item_of(payload, "TS-2023-001")["visible_document_ids"].append("DOC-2026-A")

    error = refused(resealed(payload), "FUTURE_EVIDENCE_LEAK")

    assert error.context["document_id"] == "DOC-2026-A"
    assert error.context["item_id"] == "TS-2023-001"


def test_a_slice_with_nothing_later_to_withhold_is_refused() -> None:
    payload = benchmark()
    payload["slices"].append(
        {
            "as_of": "2026-12-31T23:59:59Z",
            "description": "a slice that postdates every declared document",
            "slice_id": "SLICE-2026",
        }
    )
    payload["items"].append(
        {
            "as_of": "2026-12-31T23:59:59Z",
            "gold_case_id": "GC-true-001",
            "gold_label": "TRUE_INSIGHT",
            "item_id": "TS-2026-001",
            "predicted_label": "TRUE_INSIGHT",
            "retrieved_document_ids": ["DOC-2026-A"],
            "slice_id": "SLICE-2026",
            "visible_document_ids": ["DOC-2026-A"],
        }
    )

    error = refused(resealed(payload), "SLICE_WITHHOLDS_NOTHING")

    assert error.context["slice_id"] == "SLICE-2026"


def test_the_committed_results_artifact_is_the_report_the_dataset_produces() -> None:
    derived = verify_results(ROOT)

    assert derived["report_hash"] == hash_excluding(derived, "report_hash")
