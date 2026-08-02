from __future__ import annotations

import importlib.util
import json
import sys
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
