"""negative_and_adversarial_tests — every refusal, one wrong thing at a time.

Each case starts from the committed dataset, changes exactly one thing, and
asserts the code the gate refuses with.  Every entry in both ``FINDING_CODES``
tables is reached by at least one case, and the last test in this module
asserts that coverage rather than trusting the file to stay complete.

The read-side refusals — an unreadable dataset, an unreadable gold corpus, a
stale results artifact — run against a throwaway copy of the committed files,
because exercising them in place would mean damaging the sealed tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import adversarial_harness
import time_sliced_harness
from adversarial_harness import AdversarialEvalError
from fixtures import (
    ROOT,
    adversarial_item,
    attack_class,
    baseline_item,
    mirror_repository,
    sealed_adversarial,
    sealed_time_sliced,
    time_sliced_document,
    time_sliced_item,
    time_sliced_slice,
    unsealed_adversarial,
    unsealed_time_sliced,
)
from time_sliced_harness import TimeSliceError

SEEN_TIME_SLICED: set[str] = set()
SEEN_ADVERSARIAL: set[str] = set()


def refused_time_sliced(payload: Any, code: str) -> TimeSliceError:
    with pytest.raises(TimeSliceError) as caught:
        time_sliced_harness.evaluate(payload, ROOT)
    assert caught.value.code == code, caught.value.code
    SEEN_TIME_SLICED.add(code)
    return caught.value


def refused_adversarial(payload: Any, code: str) -> AdversarialEvalError:
    with pytest.raises(AdversarialEvalError) as caught:
        adversarial_harness.evaluate(payload, ROOT)
    assert caught.value.code == code, caught.value.code
    SEEN_ADVERSARIAL.add(code)
    return caught.value


def refused_call(module, code: str, call) -> Exception:
    """Refusals raised while reading from disk, against a throwaway root."""

    time_sliced = module is time_sliced_harness
    with pytest.raises(TimeSliceError if time_sliced else AdversarialEvalError) as (
        caught
    ):
        call()
    assert caught.value.code == code, caught.value.code
    (SEEN_TIME_SLICED if time_sliced else SEEN_ADVERSARIAL).add(code)
    return caught.value


# --------------------------------------------------------------------------
# Time-sliced gate
# --------------------------------------------------------------------------


def test_a_future_document_in_the_visible_set_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2024-001")["visible_document_ids"].append(
            "DOC-2026-A"
        )

    error = refused_time_sliced(sealed_time_sliced(mutate), "FUTURE_EVIDENCE_LEAK")

    assert error.context["document_id"] == "DOC-2026-A"
    assert error.context["published_at"] == "2026-03-18T00:00:00Z"


def test_a_retrieved_document_outside_the_visible_set_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-002")["retrieved_document_ids"].append(
            "DOC-2023-B"
        )

    error = refused_time_sliced(sealed_time_sliced(mutate), "RETRIEVAL_UNGROUNDED")

    assert error.context["document_ids"] == ["DOC-2023-B"]


def test_a_slice_with_nothing_later_to_withhold_is_refused() -> None:
    # DOC-2026-A is the only document postdating the last slice and no item
    # cites it, so dropping it leaves that slice with nothing to withhold.
    def mutate(payload: dict) -> None:
        payload["documents"] = [
            document
            for document in payload["documents"]
            if document["document_id"] != "DOC-2026-A"
        ]

    error = refused_time_sliced(sealed_time_sliced(mutate), "SLICE_WITHHOLDS_NOTHING")

    assert error.context["slice_id"] == "SLICE-2025"


def test_a_slice_with_no_item_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["slices"].insert(
            2,
            {
                "as_of": "2025-03-31T23:59:59Z",
                "description": "a quarter nothing was ever evaluated at",
                "slice_id": "SLICE-2025Q1",
            },
        )

    error = refused_time_sliced(sealed_time_sliced(mutate), "SLICE_EMPTY")

    assert error.context["slice_id"] == "SLICE-2025Q1"


def test_slices_declared_out_of_order_are_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["slices"][0], payload["slices"][1] = (
            payload["slices"][1],
            payload["slices"][0],
        )

    error = refused_time_sliced(sealed_time_sliced(mutate), "SLICE_ORDER_INVALID")

    assert error.context["slice_id"] == "SLICE-2023"


def test_an_item_filed_under_an_undeclared_slice_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-001")["slice_id"] = "SLICE-2099"

    error = refused_time_sliced(sealed_time_sliced(mutate), "SLICE_UNKNOWN")

    assert error.context["slice_id"] == "SLICE-2099"


def test_an_item_whose_as_of_drifts_from_its_slice_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-001")["as_of"] = "2024-12-31T23:59:59Z"

    error = refused_time_sliced(sealed_time_sliced(mutate), "ITEM_AS_OF_MISMATCH")

    assert error.context["slice_as_of"] == "2023-12-31T23:59:59Z"


def test_an_item_naming_an_undeclared_document_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-001")["visible_document_ids"] = ["DOC-404"]

    error = refused_time_sliced(sealed_time_sliced(mutate), "DOCUMENT_UNKNOWN")

    assert error.context["document_id"] == "DOC-404"


def test_a_document_declared_twice_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["documents"].append(dict(time_sliced_document(payload, "DOC-2023-A")))

    error = refused_time_sliced(sealed_time_sliced(mutate), "DUPLICATE_DOCUMENT")

    assert error.context["document_id"] == "DOC-2023-A"


def test_a_document_repeated_inside_one_item_field_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-002")["visible_document_ids"].append(
            "DOC-2023-A"
        )

    error = refused_time_sliced(sealed_time_sliced(mutate), "DUPLICATE_DOCUMENT")

    assert error.context["field"].endswith("visible_document_ids")


def test_a_duplicated_item_id_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["items"].append(dict(time_sliced_item(payload, "TS-2023-001")))

    error = refused_time_sliced(sealed_time_sliced(mutate), "DUPLICATE_ITEM")

    assert error.context["item_id"] == "TS-2023-001"


def test_a_duplicated_slice_id_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["slices"].append(dict(time_sliced_slice(payload, "SLICE-2025")))

    error = refused_time_sliced(sealed_time_sliced(mutate), "DUPLICATE_SLICE")

    assert error.context["slice_id"] == "SLICE-2025"


def test_an_item_citing_a_case_the_gold_corpus_lacks_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-001")["gold_case_id"] = "GC-invented-001"

    error = refused_time_sliced(sealed_time_sliced(mutate), "GOLD_CASE_UNKNOWN")

    assert error.context["gold_case_id"] == "GC-invented-001"


def test_an_item_relabelled_away_from_the_gold_corpus_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-001")["gold_label"] = "BOUNDARY"

    error = refused_time_sliced(sealed_time_sliced(mutate), "GOLD_LABEL_MISMATCH")

    assert error.context["corpus_label"] == "TRUE_INSIGHT"


def test_a_label_outside_the_gold_vocabulary_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-001")["predicted_label"] = "PROBABLY_TRUE"

    error = refused_time_sliced(sealed_time_sliced(mutate), "LABEL_INVALID")

    assert error.context["value"] == "PROBABLY_TRUE"


def test_a_missing_item_field_is_refused() -> None:
    def mutate(payload: dict) -> None:
        del time_sliced_item(payload, "TS-2023-001")["predicted_label"]

    error = refused_time_sliced(sealed_time_sliced(mutate), "FIELD_SET_INVALID")

    assert error.context["missing"] == ["predicted_label"]


def test_an_unparseable_publication_date_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_document(payload, "DOC-2023-A")["published_at"] = "spring 2023"

    error = refused_time_sliced(sealed_time_sliced(mutate), "TIMESTAMP_INVALID")

    assert error.context["value"] == "spring 2023"


def test_a_naive_publication_date_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_document(payload, "DOC-2023-A")["published_at"] = (
            "2023-02-10T00:00:00"
        )

    refused_time_sliced(sealed_time_sliced(mutate), "TIMESTAMP_INVALID")


def test_a_dataset_edited_after_its_seal_is_refused() -> None:
    def mutate(payload: dict) -> None:
        time_sliced_item(payload, "TS-2023-003")["predicted_label"] = "BOUNDARY"

    error = refused_time_sliced(unsealed_time_sliced(mutate), "DATASET_HASH_MISMATCH")

    assert error.context["declared"] != error.context["recomputed"]


def test_a_dataset_claiming_a_live_system_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["system_under_test"]["synthetic"] = False

    refused_time_sliced(sealed_time_sliced(mutate), "SYSTEM_OVERCLAIM")


def test_a_dataset_citing_some_other_corpus_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["gold_corpus_ref"]["path"] = "evals/gold/private_cases.json"

    refused_time_sliced(sealed_time_sliced(mutate), "GOLD_CORPUS_UNREADABLE")


def test_a_time_sliced_payload_that_is_not_a_mapping_is_refused() -> None:
    refused_time_sliced("not-a-mapping", "INPUT_INVALID")


def test_a_time_sliced_dataset_with_no_document_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["documents"] = []

    refused_time_sliced(sealed_time_sliced(mutate), "INPUT_INVALID")


def test_an_absent_time_sliced_dataset_is_refused(tmp_path: Path) -> None:
    root = mirror_repository(tmp_path)
    (root / time_sliced_harness.BENCHMARK_RELATIVE_PATH).unlink()

    refused_call(
        time_sliced_harness,
        "BENCHMARK_UNREADABLE",
        lambda: time_sliced_harness.evaluate_benchmark(root),
    )


def test_an_absent_gold_corpus_is_refused_by_the_time_sliced_gate(
    tmp_path: Path,
) -> None:
    root = mirror_repository(tmp_path)
    (root / time_sliced_harness.GOLD_CORPUS_RELATIVE_PATH).unlink()

    refused_call(
        time_sliced_harness,
        "GOLD_CORPUS_UNREADABLE",
        lambda: time_sliced_harness.evaluate_benchmark(root),
    )


def test_an_absent_time_sliced_results_artifact_is_refused(tmp_path: Path) -> None:
    root = mirror_repository(tmp_path)
    (root / time_sliced_harness.RESULTS_RELATIVE_PATH).unlink()

    refused_call(
        time_sliced_harness,
        "RESULTS_UNREADABLE",
        lambda: time_sliced_harness.verify_results(root),
    )


def test_a_stale_time_sliced_results_artifact_is_refused(tmp_path: Path) -> None:
    root = mirror_repository(tmp_path)
    path = root / time_sliced_harness.RESULTS_RELATIVE_PATH
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["overall"]["correct"] = 12
    path.write_text(json.dumps(stale), encoding="utf-8")

    refused_call(
        time_sliced_harness,
        "RESULTS_STALE",
        lambda: time_sliced_harness.verify_results(root),
    )


# --------------------------------------------------------------------------
# Adversarial gate
# --------------------------------------------------------------------------


def test_an_adversarial_item_without_its_baseline_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-INJ-001")["baseline_item_id"] = "BASE-404"

    error = refused_adversarial(sealed_adversarial(mutate), "BASELINE_MISSING")

    assert error.context["baseline_item_id"] == "BASE-404"


def test_two_perturbations_of_one_baseline_are_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-NEG-002")["baseline_item_id"] = "BASE-001"

    error = refused_adversarial(sealed_adversarial(mutate), "BASELINE_PAIRED_TWICE")

    assert error.context["item_ids"] == ["ADV-NEG-001", "ADV-NEG-002"]


def test_a_baseline_nothing_perturbs_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["baseline_items"].append(
            {
                "evidence_text": "the falsifying condition is stated in the discussion",
                "gold_case_id": "GC-true-004",
                "gold_label": "TRUE_INSIGHT",
                "item_id": "BASE-009",
                "predicted_label": "TRUE_INSIGHT",
                "statement": (
                    "The paper states a falsifying condition and reports that "
                    "the condition was tested and not met."
                ),
            }
        )

    error = refused_adversarial(sealed_adversarial(mutate), "BASELINE_UNPAIRED")

    assert error.context["baseline_item_ids"] == ["BASE-009"]


def test_a_label_move_without_a_recorded_rationale_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-SWAP-001")["label_change_rationale"] = None

    error = refused_adversarial(sealed_adversarial(mutate), "LABEL_CHANGE_UNJUSTIFIED")

    assert error.context["baseline_label"] == "BOUNDARY"


def test_a_blank_rationale_counts_as_no_rationale() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-SWAP-001")["label_change_rationale"] = "   "

    refused_adversarial(sealed_adversarial(mutate), "LABEL_CHANGE_UNJUSTIFIED")


def test_a_rationale_for_a_label_that_never_moved_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-CITE-001")["label_change_rationale"] = (
            "the citation was swapped but the gold label is unchanged"
        )

    error = refused_adversarial(sealed_adversarial(mutate), "RATIONALE_UNEXPECTED")

    assert error.context["item_id"] == "ADV-CITE-001"


def test_a_declared_attack_class_with_no_item_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["attack_classes"].append(
            {
                "attack_class": "UNIT_RESCALE",
                "description": "the reported unit changes without rescaling the value",
                "evidence_marker": None,
            }
        )

    error = refused_adversarial(sealed_adversarial(mutate), "ATTACK_CLASS_UNPOPULATED")

    assert error.context["attack_classes"] == ["UNIT_RESCALE"]


def test_an_item_naming_an_undeclared_attack_class_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-NEG-001")["attack_class"] = "VIBES_ATTACK"

    error = refused_adversarial(sealed_adversarial(mutate), "ATTACK_CLASS_UNDECLARED")

    assert error.context["attack_class"] == "VIBES_ATTACK"


def test_an_attack_class_declared_twice_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["attack_classes"].append(
            dict(attack_class(payload, "PROMPT_INJECTION"))
        )

    error = refused_adversarial(sealed_adversarial(mutate), "ATTACK_CLASS_DUPLICATED")

    assert error.context["attack_class"] == "PROMPT_INJECTION"


def test_an_injection_item_without_the_injected_text_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-INJ-001")["evidence_text"] = (
            "the pooled average mixes an observational cohort with a randomised "
            "arm, and carries no imperative addressed to the reading system"
        )

    error = refused_adversarial(sealed_adversarial(mutate), "ATTACK_SIGNATURE_ABSENT")

    assert error.context["attack_class"] == "PROMPT_INJECTION"


def test_an_adversarial_item_identical_to_its_baseline_is_refused() -> None:
    def mutate(payload: dict) -> None:
        baseline = baseline_item(payload, "BASE-004")
        item = adversarial_item(payload, "ADV-CITE-001")
        item["statement"] = baseline["statement"]
        item["evidence_text"] = baseline["evidence_text"]

    error = refused_adversarial(sealed_adversarial(mutate), "BASELINE_UNPERTURBED")

    assert error.context["baseline_item_id"] == "BASE-004"


def test_a_benchmark_with_no_known_false_item_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["false_claim_label"] = "TRUE_INSIGHT"

    error = refused_adversarial(
        sealed_adversarial(mutate), "FALSE_CLAIM_COVERAGE_ABSENT"
    )

    assert error.context["false_claim_label"] == "TRUE_INSIGHT"


def test_a_baseline_citing_a_case_the_gold_corpus_lacks_is_refused() -> None:
    def mutate(payload: dict) -> None:
        baseline_item(payload, "BASE-001")["gold_case_id"] = "GC-invented-001"

    error = refused_adversarial(sealed_adversarial(mutate), "BASELINE_UNGROUNDED")

    assert error.context["gold_case_id"] == "GC-invented-001"


def test_a_baseline_relabelled_away_from_the_gold_corpus_is_refused() -> None:
    def mutate(payload: dict) -> None:
        baseline_item(payload, "BASE-001")["gold_label"] = "BOUNDARY"

    error = refused_adversarial(sealed_adversarial(mutate), "GOLD_LABEL_MISMATCH")

    assert error.context["corpus_label"] == "TRUE_INSIGHT"


def test_an_adversarial_label_outside_the_gold_vocabulary_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-NEG-001")["predicted_label"] = "PROBABLY_FALSE"

    error = refused_adversarial(sealed_adversarial(mutate), "LABEL_INVALID")

    assert error.context["value"] == "PROBABLY_FALSE"


def test_a_false_claim_label_outside_the_gold_vocabulary_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["false_claim_label"] = "NOT_A_LABEL"

    error = refused_adversarial(sealed_adversarial(mutate), "LABEL_INVALID")

    assert error.context["value"] == "NOT_A_LABEL"


def test_a_duplicated_adversarial_item_id_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["baseline_items"].append(dict(baseline_item(payload, "BASE-001")))

    error = refused_adversarial(sealed_adversarial(mutate), "DUPLICATE_ITEM")

    assert error.context["item_id"] == "BASE-001"


def test_a_missing_adversarial_field_is_refused() -> None:
    def mutate(payload: dict) -> None:
        del adversarial_item(payload, "ADV-NEG-001")["label_change_rationale"]

    error = refused_adversarial(sealed_adversarial(mutate), "FIELD_SET_INVALID")

    assert error.context["missing"] == ["label_change_rationale"]


def test_an_adversarial_dataset_edited_after_its_seal_is_refused() -> None:
    def mutate(payload: dict) -> None:
        adversarial_item(payload, "ADV-NEG-001")["predicted_label"] = "FALSE_INSIGHT"

    error = refused_adversarial(unsealed_adversarial(mutate), "DATASET_HASH_MISMATCH")

    assert error.context["declared"] != error.context["recomputed"]


def test_an_adversarial_dataset_claiming_a_live_system_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["system_under_test"]["synthetic"] = False

    refused_adversarial(sealed_adversarial(mutate), "SYSTEM_OVERCLAIM")


def test_an_adversarial_dataset_citing_some_other_corpus_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["gold_corpus_ref"]["path"] = "evals/gold/private_cases.json"

    refused_adversarial(sealed_adversarial(mutate), "GOLD_CORPUS_UNREADABLE")


def test_an_adversarial_payload_that_is_not_a_mapping_is_refused() -> None:
    refused_adversarial("not-a-mapping", "INPUT_INVALID")


def test_an_adversarial_dataset_with_no_attack_class_is_refused() -> None:
    def mutate(payload: dict) -> None:
        payload["attack_classes"] = []

    refused_adversarial(sealed_adversarial(mutate), "INPUT_INVALID")


def test_an_absent_adversarial_dataset_is_refused(tmp_path: Path) -> None:
    root = mirror_repository(tmp_path)
    (root / adversarial_harness.BENCHMARK_RELATIVE_PATH).unlink()

    refused_call(
        adversarial_harness,
        "BENCHMARK_UNREADABLE",
        lambda: adversarial_harness.evaluate_benchmark(root),
    )


def test_an_absent_gold_corpus_is_refused_by_the_adversarial_gate(
    tmp_path: Path,
) -> None:
    root = mirror_repository(tmp_path)
    (root / adversarial_harness.GOLD_CORPUS_RELATIVE_PATH).unlink()

    refused_call(
        adversarial_harness,
        "GOLD_CORPUS_UNREADABLE",
        lambda: adversarial_harness.evaluate_benchmark(root),
    )


def test_an_absent_adversarial_results_artifact_is_refused(tmp_path: Path) -> None:
    root = mirror_repository(tmp_path)
    (root / adversarial_harness.RESULTS_RELATIVE_PATH).unlink()

    refused_call(
        adversarial_harness,
        "RESULTS_UNREADABLE",
        lambda: adversarial_harness.verify_results(root),
    )


def test_a_stale_adversarial_results_artifact_is_refused(tmp_path: Path) -> None:
    root = mirror_repository(tmp_path)
    path = root / adversarial_harness.RESULTS_RELATIVE_PATH
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["robustness_delta"] = 0.0
    path.write_text(json.dumps(stale), encoding="utf-8")

    refused_call(
        adversarial_harness,
        "RESULTS_STALE",
        lambda: adversarial_harness.verify_results(root),
    )


# --------------------------------------------------------------------------
# Coverage of the declared refusal vocabulary
# --------------------------------------------------------------------------


def test_zz_every_declared_finding_code_is_exercised_by_this_module() -> None:
    # This module runs its cases before this assertion because pytest executes
    # a file top to bottom; the sets are filled by `refused_*` above.
    assert SEEN_TIME_SLICED == set(time_sliced_harness.FINDING_CODES)
    assert SEEN_ADVERSARIAL == set(adversarial_harness.FINDING_CODES)
