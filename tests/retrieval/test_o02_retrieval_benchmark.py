from __future__ import annotations

import importlib.util
import inspect
import json
import math
import re
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "retrieval" / "o02"
CONTRACTS_PATH = ROOT / "python" / "epistemic_foundry" / "retrieval" / "lanes" / "contracts.py"


def load_contracts():
    name = "ef_o02_benchmark_contracts"
    spec = importlib.util.spec_from_file_location(name, CONTRACTS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTRACTS = load_contracts()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_corpus() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (FIXTURES / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def benchmark_report() -> dict[str, object]:
    corpus = load_corpus()
    query_fixture = load_json(FIXTURES / "queries.json")
    labels = load_json(FIXTURES / "relevance-labels.json")
    rankings = CONTRACTS.rank_fixture_corpus(corpus, query_fixture["queries"])
    return CONTRACTS.evaluate_retrieval_benchmark(
        rankings,
        query_fixture["queries"],
        labels["relevance"],
        must_find_query_ids=labels["critical_must_find_query_ids"],
    )


def test_retrieval_benchmark_all_required_lanes_meet_exact_thresholds() -> None:
    report = benchmark_report()

    CONTRACTS.assert_benchmark_thresholds(report)
    assert set(report["per_lane"]) == set(CONTRACTS.LANE_QUERY_FAMILIES)
    assert all(row["recall_at_20"] >= 0.90 for row in report["per_lane"].values())
    assert all(row["ndcg_at_20"] >= 0.85 for row in report["per_lane"].values())
    assert report["fused_recall_at_20"] >= 0.95
    assert all(report["critical_must_find"].values())
    assert report["live_network_calls"] == 0
    assert report["live_llm_calls"] == 0


def test_retrieval_benchmark_is_deterministic_under_input_reordering() -> None:
    corpus = load_corpus()
    query_fixture = load_json(FIXTURES / "queries.json")

    first = CONTRACTS.rank_fixture_corpus(corpus, query_fixture["queries"])
    second = CONTRACTS.rank_fixture_corpus(list(reversed(corpus)), list(reversed(query_fixture["queries"])))

    assert first == second


@pytest.mark.parametrize(
    ("metric", "value", "expected_code"),
    [
        ("recall_at_20", 0.899999, "BENCHMARK_RECALL_BELOW_THRESHOLD"),
        ("ndcg_at_20", 0.849999, "BENCHMARK_NDCG_BELOW_THRESHOLD"),
    ],
)
def test_retrieval_benchmark_does_not_average_away_a_failing_lane(
    metric: str,
    value: float,
    expected_code: str,
) -> None:
    report = benchmark_report()
    report["per_lane"]["method"][metric] = value

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.assert_benchmark_thresholds(report)

    assert raised.value.code == expected_code


def test_retrieval_benchmark_critical_must_find_requires_every_case() -> None:
    report = benchmark_report()
    report["critical_must_find"]["Q-COUNTER"] = False

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.assert_benchmark_thresholds(report)

    assert raised.value.code == "BENCHMARK_CRITICAL_MUST_FIND_FAILED"


# ---------------------------------------------------------------------------
# Whether the fixture is a valid test of anything
#
# The checks above prove the benchmark enforces its thresholds. They cannot
# prove the fixture measures retrieval rather than string overlap. Every query
# here currently shares 100% of its terms with its one relevant document, so a
# purely lexical backend scores perfectly on the semantic and mechanism lanes
# too. That is the exact confusion the eleven-lane contract exists to prevent,
# and it is recorded here rather than left as an unstated limit of the score.
# ---------------------------------------------------------------------------


def query_terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 2}


def corpus_by_id() -> dict[str, str]:
    return {str(row["document_id"]): str(row["text"]) for row in load_corpus()}


def test_benchmark_fixture_lane_coverage_is_declared_not_assumed() -> None:
    """Every canonical lane has a query, a labelled target, and a distractor."""
    queries = load_json(FIXTURES / "queries.json")["queries"]
    labels = load_json(FIXTURES / "relevance-labels.json")
    documents = corpus_by_id()

    lanes_with_queries = {str(query["lane"]) for query in queries}
    assert lanes_with_queries == set(CONTRACTS.LANE_QUERY_FAMILIES)

    for query in queries:
        targets = labels["relevance"][str(query["query_id"])]
        assert targets, f"{query['query_id']} has no labelled target"
        for target in targets:
            assert target in documents, f"{target} is labelled but absent from the corpus"

    # A corpus with no distractor cannot distinguish retrieval from enumeration.
    unlabelled = set(documents) - {
        target for targets in labels["relevance"].values() for target in targets
    }
    assert unlabelled, "the fixture needs at least one distractor document"


def test_benchmark_fixture_query_family_matches_the_canonical_lane_binding() -> None:
    """A lane's fixture query must use the family that lane actually accepts."""
    for query in load_json(FIXTURES / "queries.json")["queries"]:
        lane = str(query["lane"])
        assert str(query["query_family"]) in CONTRACTS.LANE_QUERY_FAMILIES[lane], (
            f"{query['query_id']} uses a family {lane} does not accept"
        )


def lexical_substitution_rankings() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Rank every fixture query through the one real lexical backend.

    Returns the rankings the benchmark would score, plus the retrieval channel
    each query's candidates actually came from. This is the counterfactual the
    benchmark never runs: one index, eleven lane labels.
    """
    from epistemic_foundry.retrieval import lanes as shipped_lanes
    from epistemic_foundry.retrieval import lexical_index

    queries = load_json(FIXTURES / "queries.json")["queries"]

    with tempfile.TemporaryDirectory() as tmp:
        corpus_dir = Path(tmp) / "corpus"
        corpus_dir.mkdir()
        for row in load_corpus():
            (corpus_dir / f"{row['document_id']}.md").write_text(
                str(row["text"]), encoding="utf-8"
            )
        db = Path(tmp) / "index.db"
        stats = lexical_index.build_index(corpus_dir, db)
        context = shipped_lanes.LaneContext.from_index_stats(
            stats,
            run_id="RUN-O02-SUBSTITUTION",
            query_plan_id="QP-O02-SUBSTITUTION",
            plan_hash="sha256:" + "1" * 64,
            policy_bundle_hash="sha256:" + "2" * 64,
            capability_lease_id="TEST-LEASE",
            cutoff_policy_id="TEST-CUTOFF",
            lane_decision_evidence_ids=("EV-SUBSTITUTION",),
            started_at="2026-08-14T00:00:00Z",
            finished_at="2026-08-14T00:00:01Z",
        )

        rankings: dict[str, list[str]] = {}
        channels: dict[str, list[str]] = {}
        for query in queries:
            query_id = str(query["query_id"])
            terms = [
                word
                for word in str(query["text"]).split()
                if word.isalpha() and word.lower() not in {"or", "and", "not", "near"}
            ][:6]
            result = shipped_lanes.lexical(db, context, expression=" OR ".join(terms))
            rankings[query_id] = [
                str(row["source_record_id"]) for row in result.candidates
            ]
            channels[query_id] = sorted(
                {
                    channel
                    for row in result.candidates
                    for channel in row["retrieval_channels"]
                }
            )
        return rankings, channels


def test_retrieval_benchmark_rejects_lexical_channel_substitution() -> None:
    """The benchmark gate itself must refuse lexical-only eleven-lane credit.

    The eleven-lane contract exists so that no single retrieval channel can
    stand in for the rest. This feeds the gate the real counterfactual: every
    fixture query ranked by the shipped SQLite FTS5 backend, where every
    candidate carries `LEXICAL` provenance. If the gate passes that ranking, it
    cannot tell eleven retrieval capabilities from one.

    The assertion is on the gate, not on the scores. Scoring the rankings here
    and asserting the arithmetic would only restate what the backend did; the
    question is what the acceptance oracle does with it.

    This check is expected to fail against the current benchmark. That failure
    is the finding.
    """
    rankings, channels = lexical_substitution_rankings()
    queries = load_json(FIXTURES / "queries.json")["queries"]
    labels = load_json(FIXTURES / "relevance-labels.json")

    # Precondition: this is genuinely a single-channel run, so a gate that
    # accepts it is accepting one channel for all eleven lanes.
    non_lexical = {
        str(query["query_id"]): channels[str(query["query_id"])]
        for query in queries
        if str(query["lane"]) != "lexical"
    }
    assert all(value == ["LEXICAL"] for value in non_lexical.values()), (
        f"substitution run was not lexical-only: {non_lexical}"
    )

    report = CONTRACTS.evaluate_retrieval_benchmark(
        rankings,
        queries,
        labels["relevance"],
        must_find_query_ids=labels["critical_must_find_query_ids"],
    )

    with pytest.raises(CONTRACTS.RetrievalContractError):
        CONTRACTS.assert_benchmark_thresholds(report)


def test_benchmark_external_dependency_check_observes_the_run() -> None:
    """`BENCHMARK_EXTERNAL_DEPENDENCY` must be able to fire.

    `assert_benchmark_thresholds` refuses a report whose `live_network_calls` or
    `live_llm_calls` are non-zero. But `evaluate_retrieval_benchmark` writes
    both as literal zeros into the report it returns; neither is an argument or
    a measurement. The gate therefore reads back a constant it supplied itself,
    and a benchmark that did call the network would report zero and pass.

    This asserts that the values come from the run rather than from the
    reporter. It is expected to fail against the current implementation.
    """
    queries = load_json(FIXTURES / "queries.json")["queries"]
    labels = load_json(FIXTURES / "relevance-labels.json")
    rankings = CONTRACTS.rank_fixture_corpus(load_corpus(), queries)

    signature = inspect.signature(CONTRACTS.evaluate_retrieval_benchmark)
    observable = {"live_network_calls", "live_llm_calls"} & set(signature.parameters)

    report = CONTRACTS.evaluate_retrieval_benchmark(
        rankings,
        queries,
        labels["relevance"],
        must_find_query_ids=labels["critical_must_find_query_ids"],
    )
    assert report["live_network_calls"] == 0
    assert report["live_llm_calls"] == 0

    assert observable, (
        "O02_BENCHMARK_EXTERNAL_DEPENDENCY_CHECK_IS_VACUOUS: "
        "evaluate_retrieval_benchmark hard-codes live_network_calls and "
        "live_llm_calls, so assert_benchmark_thresholds validates its own "
        "constants and BENCHMARK_EXTERNAL_DEPENDENCY can never fire"
    )
