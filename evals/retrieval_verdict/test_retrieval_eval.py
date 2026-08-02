"""retrieval_eval — counter and null recall are measured on their own.

Exit criterion under test: "counter/null recall measured".  A retriever
optimised for agreement returns every supporting document and misses the ones
that would refute the claim, and undifferentiated recall hides exactly that.
So recall is reported per evidence polarity with its numerator, denominator and
the ids it missed, and a corpus carrying no counter or null evidence is refused
rather than scored a perfect one.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evaluator import (
    ADVERSARIAL_POLARITIES,
    EVIDENCE_POLARITIES,
    VERDICTS,
    RetrievalEvalError,
    evaluate,
    evaluate_corpus,
    load_corpus,
)

ROOT = Path(__file__).resolve().parents[2]


def corpus() -> dict:
    return copy.deepcopy(load_corpus(ROOT))


def query_of(payload: dict, query_id: str) -> dict:
    return next(q for q in payload["queries"] if q["query_id"] == query_id)


def refused(payload: dict) -> RetrievalEvalError:
    with pytest.raises(RetrievalEvalError) as caught:
        evaluate(payload, ROOT)
    return caught.value


def test_the_committed_corpus_evaluates() -> None:
    report = evaluate_corpus(ROOT).payload

    assert report["corpus_id"] == "Q03-RETRIEVAL-VERDICT"
    assert report["counts"] == {
        "queries": 4,
        "relevant_documents": 13,
        "verdict_cases": 12,
    }


def test_recall_is_reported_for_every_polarity() -> None:
    recall = evaluate_corpus(ROOT).payload["recall_by_polarity"]

    assert sorted(recall) == sorted(EVIDENCE_POLARITIES)
    assert ADVERSARIAL_POLARITIES == ("counter", "null")


def test_every_recall_is_recomputable_from_its_own_counts() -> None:
    recall = evaluate_corpus(ROOT).payload["recall_by_polarity"]

    for polarity, entry in recall.items():
        assert entry["recall"] == pytest.approx(entry["found"] / entry["relevant"]), (
            polarity
        )
        assert entry["found"] + len(entry["missed_ids"]) == entry["relevant"]


def test_the_measured_counter_recall_is_the_one_v1_actually_scores() -> None:
    recall = evaluate_corpus(ROOT).payload["recall_by_polarity"]

    assert recall["counter"]["relevant"] == 4
    assert recall["counter"]["found"] == 2
    assert recall["counter"]["recall"] == pytest.approx(0.5)
    assert recall["null"]["recall"] == pytest.approx(1.0)
    assert recall["supporting"]["recall"] == pytest.approx(1.0)


def test_the_missed_counter_evidence_is_named() -> None:
    recall = evaluate_corpus(ROOT).payload["recall_by_polarity"]

    assert recall["counter"]["missed_ids"] == ["Q-001/DOC-A4", "Q-002/DOC-B2"]
    assert recall["supporting"]["missed_ids"] == []


def test_high_supporting_recall_does_not_lift_counter_recall() -> None:
    report = evaluate_corpus(ROOT).payload

    assert report["recall_by_polarity"]["supporting"]["recall"] == pytest.approx(1.0)
    assert report["recall_by_polarity"]["counter"]["recall"] < 1.0


def test_retrieving_the_missed_counter_document_raises_only_counter_recall() -> None:
    payload = corpus()
    query_of(payload, "Q-001")["retrieved"].append("DOC-A4")
    recall = evaluate(payload, ROOT).payload["recall_by_polarity"]

    assert recall["counter"]["found"] == 3
    assert recall["counter"]["recall"] == pytest.approx(0.75)
    assert recall["supporting"]["recall"] == pytest.approx(1.0)


def test_a_corpus_without_counter_evidence_is_refused() -> None:
    payload = corpus()
    for query in payload["queries"]:
        query["relevant"] = [
            entry for entry in query["relevant"] if entry["polarity"] != "counter"
        ]

    error = refused(payload)
    assert error.code == "POLARITY_UNMEASURED"
    assert error.context["polarities"] == ["counter"]


def test_a_corpus_without_null_results_is_refused() -> None:
    payload = corpus()
    for query in payload["queries"]:
        query["relevant"] = [
            entry for entry in query["relevant"] if entry["polarity"] != "null"
        ]

    error = refused(payload)
    assert error.code == "POLARITY_UNMEASURED"
    assert error.context["polarities"] == ["null"]


def test_a_retriever_that_returns_nothing_scores_zero_not_undefined() -> None:
    payload = corpus()
    for query in payload["queries"]:
        query["retrieved"] = []
    recall = evaluate(payload, ROOT).payload["recall_by_polarity"]

    for polarity in EVIDENCE_POLARITIES:
        assert recall[polarity]["recall"] == pytest.approx(0.0)
        assert recall[polarity]["found"] == 0


def test_an_unknown_polarity_is_refused() -> None:
    payload = corpus()
    query_of(payload, "Q-001")["relevant"][0]["polarity"] = "mostly_supporting"

    assert refused(payload).code == "POLARITY_INVALID"


def test_a_query_with_no_relevant_document_is_refused() -> None:
    payload = corpus()
    query_of(payload, "Q-003")["relevant"] = []

    error = refused(payload)
    assert error.code == "QUERY_UNGRADED"
    assert error.context["query_id"] == "Q-003"


def test_a_duplicate_relevant_document_is_refused() -> None:
    payload = corpus()
    query = query_of(payload, "Q-003")
    query["relevant"].append(copy.deepcopy(query["relevant"][0]))

    assert refused(payload).code == "DUPLICATE_RELEVANT"


def test_a_repeated_retrieval_result_is_refused() -> None:
    payload = corpus()
    query = query_of(payload, "Q-003")
    query["retrieved"].append(query["retrieved"][0])

    assert refused(payload).code == "DUPLICATE_RETRIEVED"


def test_a_duplicate_query_id_is_refused() -> None:
    payload = corpus()
    payload["queries"].append(copy.deepcopy(query_of(payload, "Q-001")))

    assert refused(payload).code == "DUPLICATE_QUERY"


def test_a_verdict_case_without_its_query_is_refused() -> None:
    payload = corpus()
    payload["verdict_cases"][0]["query_id"] = "Q-999"

    error = refused(payload)
    assert error.code == "CASE_UNGROUNDED"
    assert error.context["query_id"] == "Q-999"


def test_the_verdict_vocabulary_admits_undetermined() -> None:
    assert sorted(VERDICTS) == ["REFUTED", "SUPPORTED", "UNDETERMINED"]


def test_a_non_canonical_verdict_is_refused() -> None:
    payload = corpus()
    payload["verdict_cases"][0]["gold_verdict"] = "PROBABLY"

    assert refused(payload).code == "VERDICT_INVALID"


def test_verdict_accuracy_is_recomputable() -> None:
    report = evaluate_corpus(ROOT).payload
    accuracy = report["verdict_accuracy"]

    assert accuracy["total"] == report["counts"]["verdict_cases"]
    assert accuracy["rate"] == pytest.approx(accuracy["correct"] / accuracy["total"])
    assert accuracy["correct"] == 9


def test_a_corpus_claiming_a_real_retriever_is_refused() -> None:
    payload = corpus()
    payload["retriever_under_test"]["synthetic"] = False

    assert refused(payload).code == "RETRIEVER_OVERCLAIM"


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
    raw = (ROOT / "evals/retrieval_verdict/retrieval_verdict_cases.json").read_text(
        encoding="utf-8"
    )

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )


def test_an_unreadable_corpus_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RetrievalEvalError) as caught:
        load_corpus(tmp_path)

    assert caught.value.code == "CORPUS_UNREADABLE"
