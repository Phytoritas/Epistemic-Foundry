"""scale_qualification — the system stays correct and within budget at 50/200/2000.

Required check: ``scale_qualification``.  The synthetic, deterministic corpus is
qualified at all three tier sizes the release ladder names.  A tier passes only
when every document is processed correctly (honest ``OK`` state), every measured
budget dimension stays at or under the tier's ``hard_limits`` (mirroring the
``PRODUCTION_2000`` gate ``hard_budget_overrun_rate: 0``), the p95 latency stays
within budget, and the expected/processed/persisted counts reconcile exactly
(no silent partial completion, EF4-I26).

The refusal cases prove the qualification is fail-closed rather than vacuous: an
inflated per-document cost is caught as a budget overrun, a mislabelled document
drops the honest state out of ``OK``, and a dataset that claims a licensed
corpus or a certified release gate is refused as a ``SCALE_OVERCLAIM``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scale_harness import (
    ROOT,
    ScaleError,
    content_hash,
    evaluate_scale,
    load_budget_vocabulary,
    load_dataset,
    qualify_tier,
)

DATASET = load_dataset()
GEN = DATASET["generator"]
VOCAB = load_budget_vocabulary()
TIERS = {tier["name"]: tier for tier in DATASET["tiers"]}
EXPECTED_TIERS = ["EVOLUTION_MVP_50", "PILOT_200", "PRODUCTION_2000"]
EXPECTED_SIZES = {"EVOLUTION_MVP_50": 50, "PILOT_200": 200, "PRODUCTION_2000": 2000}


def test_the_corpus_covers_exactly_the_three_named_tier_sizes() -> None:
    assert [tier["name"] for tier in DATASET["tiers"]] == EXPECTED_TIERS
    assert {name: TIERS[name]["size"] for name in EXPECTED_TIERS} == EXPECTED_SIZES


def test_every_tier_qualifies_correct_and_within_budget() -> None:
    report = evaluate_scale()

    assert report["status"] == "PASS"
    assert report["synthetic"] is True
    assert report["licensed_corpus"] is False
    assert report["release_gate_certified"] is False
    assert [t["tier"] for t in report["tiers"]] == EXPECTED_TIERS
    for tier in report["tiers"]:
        assert tier["qualified"] is True, tier["tier"]
        assert tier["quality_state"]["state"] == "OK", tier["tier"]
        assert tier["within_budget"] is True, tier["tier"]
        assert tier["budget_overruns"] == {}, tier["tier"]
        assert tier["latency_ok"] is True, tier["tier"]
        assert tier["breach_applied"] is None, tier["tier"]


def test_each_tier_reconciles_expected_processed_persisted() -> None:
    report = evaluate_scale()
    for tier in report["tiers"]:
        rec = tier["reconciliation"]
        assert rec["reconciled"] is True, tier["tier"]
        assert rec["expected"] == rec["processed"] == rec["persisted"] == tier["size"]


def test_the_measured_budget_stays_under_every_hard_limit() -> None:
    report = evaluate_scale()
    for tier in report["tiers"]:
        for dim, limit in tier["hard_limits"].items():
            assert tier["measured"][dim] <= limit, (tier["tier"], dim)


def test_the_report_is_deterministic_and_self_hashing() -> None:
    first = evaluate_scale()
    second = evaluate_scale()
    assert first["report_hash"] == second["report_hash"]
    assert first["report_hash"] == content_hash(first, drop_key="report_hash")


# --- Fail-closed refusals: the qualification is not vacuous. ---------------- #
def test_an_inflated_per_document_cost_is_caught_as_a_budget_overrun() -> None:
    tier = TIERS["PRODUCTION_2000"]
    report = qualify_tier(GEN, tier, VOCAB, cost_inflation=100)

    assert report["within_budget"] is False
    assert "tokens" in report["budget_overruns"]
    assert report["qualified"] is False
    # An overrun is surfaced with the tier's breach policy, never absorbed.
    assert report["breach_applied"] == tier["budget"]["breach_policy"]


def test_a_mislabelled_document_drops_the_state_out_of_ok() -> None:
    tier = TIERS["EVOLUTION_MVP_50"]
    report = qualify_tier(GEN, tier, VOCAB, corrupt_indices=frozenset({3}))

    assert report["quality_state"]["state"] == "DEGRADED"
    assert report["quality_state"]["good_count"] == tier["size"] - 1
    assert report["qualified"] is False


def test_a_dataset_that_claims_a_licensed_corpus_is_refused(tmp_path: Path) -> None:
    tampered = json.loads((ROOT / "evals/scale/scale_corpus.json").read_text("utf-8"))
    tampered["licensed_corpus"] = True
    tampered.pop("dataset_hash", None)
    root = tmp_path
    (root / "evals" / "scale").mkdir(parents=True)
    (root / "schemas").mkdir()
    (root / "evals" / "scale" / "scale_corpus.json").write_text(
        json.dumps(tampered), "utf-8"
    )
    (root / "schemas" / "budget-envelope.schema.json").write_text(
        (ROOT / "schemas" / "budget-envelope.schema.json").read_text("utf-8"), "utf-8"
    )
    with pytest.raises(ScaleError) as caught:
        load_dataset(root)
    assert caught.value.code == "SCALE_OVERCLAIM"


def test_a_dataset_that_claims_a_certified_release_gate_is_refused(
    tmp_path: Path,
) -> None:
    tampered = json.loads((ROOT / "evals/scale/scale_corpus.json").read_text("utf-8"))
    tampered["release_gate_certified"] = True
    tampered.pop("dataset_hash", None)
    (tmp_path / "evals" / "scale").mkdir(parents=True)
    (tmp_path / "evals" / "scale" / "scale_corpus.json").write_text(
        json.dumps(tampered), "utf-8"
    )
    with pytest.raises(ScaleError) as caught:
        load_dataset(tmp_path)
    assert caught.value.code == "SCALE_OVERCLAIM"
