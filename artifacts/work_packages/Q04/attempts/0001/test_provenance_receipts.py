"""provenance_and_receipt_audit — every artifact proves itself.

The two datasets and the two reports each re-derive their own hash from
exactly the fields they publish, and each digest is checked against
``epistemic_foundry.domain.hashing`` rather than only against the harness that
produced it — a local canonicalisation that agreed only with itself would be
reproducible and still wrong.  The committed results artifacts are re-derived
from the committed datasets, so a metric cannot be edited into the tree
without the gate noticing.  Neither harness holds a clock or a random source:
``evaluated_at`` and ``report_id`` are dataset inputs, which is what makes the
report hash stable across runs.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import adversarial_harness
import time_sliced_harness
from epistemic_foundry.domain.hashing import canonical_json, hash_excluding
from fixtures import ROOT, adversarial_payload, time_sliced_payload

TIME_SLICED_SOURCE = ROOT / "evals/time_sliced/time_sliced_harness.py"
ADVERSARIAL_SOURCE = ROOT / "evals/adversarial/adversarial_harness.py"
SOURCES = (TIME_SLICED_SOURCE, ADVERSARIAL_SOURCE)


def committed(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_each_dataset_re_derives_its_own_hash() -> None:
    for payload in (time_sliced_payload(), adversarial_payload()):
        assert payload["dataset_hash"] == hash_excluding(payload, "dataset_hash")


def test_each_report_re_derives_its_own_hash() -> None:
    for module in (time_sliced_harness, adversarial_harness):
        report = module.evaluate_benchmark(ROOT).payload
        assert report["report_hash"] == hash_excluding(report, "report_hash")


def test_the_local_canonicalisation_agrees_with_the_canonical_module() -> None:
    for module in (time_sliced_harness, adversarial_harness):
        report = module.evaluate_benchmark(ROOT).payload
        assert module.canonical_json(report) == canonical_json(report)
        assert module.hash_excluding(report, "report_hash") == hash_excluding(
            report, "report_hash"
        )


def test_each_report_binds_the_dataset_it_was_computed_from() -> None:
    for module, payload in (
        (time_sliced_harness, time_sliced_payload()),
        (adversarial_harness, adversarial_payload()),
    ):
        report = module.evaluate_benchmark(ROOT).payload
        assert report["dataset_hash"] == payload["dataset_hash"]


def test_each_report_binds_the_sealed_gold_corpus_it_drew_from() -> None:
    corpus = committed("evals/gold/insight_gold_cases.json")

    for module in (time_sliced_harness, adversarial_harness):
        reference = module.evaluate_benchmark(ROOT).payload["gold_corpus_ref"]
        assert reference["corpus_id"] == corpus["corpus_id"]
        assert reference["corpus_version"] == corpus["corpus_version"]
        assert reference["path"] == module.GOLD_CORPUS_RELATIVE_PATH


def test_the_committed_results_artifacts_are_the_reports_they_claim_to_be() -> None:
    time_sliced = time_sliced_harness.verify_results(ROOT)
    adversarial = adversarial_harness.verify_results(ROOT)

    assert time_sliced == committed(time_sliced_harness.RESULTS_RELATIVE_PATH)
    assert adversarial == committed(adversarial_harness.RESULTS_RELATIVE_PATH)


def test_the_committed_results_hashes_are_re_derivable_from_the_files() -> None:
    for module in (time_sliced_harness, adversarial_harness):
        artifact = committed(module.RESULTS_RELATIVE_PATH)
        assert artifact["report_hash"] == hash_excluding(artifact, "report_hash")


def test_a_report_id_and_an_evaluated_at_are_supplied_by_the_caller() -> None:
    for module, payload in (
        (time_sliced_harness, time_sliced_payload()),
        (adversarial_harness, adversarial_payload()),
    ):
        report = module.evaluate_benchmark(ROOT).payload
        assert report["report_id"] == payload["report_id"]
        assert report["evaluated_at"] == payload["evaluated_at"]


def test_the_reports_are_byte_identical_across_runs() -> None:
    for module in (time_sliced_harness, adversarial_harness):
        assert (
            module.evaluate_benchmark(ROOT).canonical_bytes
            == module.evaluate_benchmark(ROOT).canonical_bytes
        )


def test_neither_harness_holds_a_clock_or_a_random_source() -> None:
    for source in SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        called = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "utc_now_iso" not in called, source.name
        assert not any(name.startswith("random") for name in called), source.name
        assert "random" not in imported, source.name
        assert "datetime.now" not in called, source.name
        assert "datetime.utcnow" not in called, source.name


def test_a_leaked_document_would_change_the_receipt_rather_than_the_score() -> None:
    # The gate refuses on leakage, so there is no leaked-run report to compare
    # against; what is asserted here is the shape that makes that possible —
    # the report publishes the check count and an explicit zero admission, and
    # carries no field a leak could be discounted into.
    report = time_sliced_harness.evaluate_benchmark(ROOT).payload

    assert report["leakage"]["future_documents_admitted"] == 0
    assert report["leakage"]["documents_checked"] > 0
    for key in report:
        assert "penalty" not in key
        assert "adjust" not in key


def test_the_datasets_on_disk_are_the_datasets_the_gates_read() -> None:
    for module, payload in (
        (time_sliced_harness, time_sliced_payload()),
        (adversarial_harness, adversarial_payload()),
    ):
        on_disk = committed(module.BENCHMARK_RELATIVE_PATH)
        assert canonical_json(on_disk) == canonical_json(payload)
        assert Path(ROOT / module.BENCHMARK_RELATIVE_PATH).is_file()
