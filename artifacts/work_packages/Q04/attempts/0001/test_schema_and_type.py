"""schema_and_type_check — the gates read their vocabulary, never restate it.

The label vocabulary belongs to the sealed Q01 gold corpus and the attack
vocabulary belongs to the adversarial dataset; both are asserted here against
those declaring files, and the harness sources are scanned so neither
vocabulary — nor any dataset identifier — can be held as a literal and drift
in silence.  The scan is scoped to the vocabularies these gates actually
consume rather than to every enum in the canonical registry, because a
registry-wide scan matches ordinary English field words such as ``correct`` or
``title`` that pin nothing about the wire format; EF4-I22's own gate runs over
``src`` as its own named check.

The field contracts are checked against the committed datasets in both
directions, so a dataset field the harness does not know about, and a harness
field the dataset never carries, are both visible failures.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import adversarial_harness
import time_sliced_harness
from adversarial_harness import AdversarialEvalError
from fixtures import ROOT, adversarial_payload, time_sliced_payload
from time_sliced_harness import TimeSliceError

TIME_SLICED_SOURCE = ROOT / "evals/time_sliced/time_sliced_harness.py"
ADVERSARIAL_SOURCE = ROOT / "evals/adversarial/adversarial_harness.py"
HARNESSES = (time_sliced_harness, adversarial_harness)
SOURCES = (TIME_SLICED_SOURCE, ADVERSARIAL_SOURCE)


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def gold_corpus() -> dict:
    return json.loads(
        (ROOT / "evals/gold/insight_gold_cases.json").read_text(encoding="utf-8")
    )


def test_the_label_vocabulary_comes_from_the_sealed_gold_corpus() -> None:
    declared = tuple(sorted({case["gold_label"] for case in gold_corpus()["cases"]}))

    assert time_sliced_harness.gold_labels(ROOT) == declared
    assert adversarial_harness.gold_labels(ROOT) == declared
    assert len(declared) == 3


def test_every_sealed_gold_case_is_addressable_by_both_harnesses() -> None:
    expected = {case["case_id"]: case["gold_label"] for case in gold_corpus()["cases"]}

    assert time_sliced_harness.gold_case_labels(ROOT) == expected
    assert adversarial_harness.gold_case_labels(ROOT) == expected
    assert len(expected) == 12


def test_neither_harness_holds_a_gold_label_literal() -> None:
    vocabulary = set(time_sliced_harness.gold_labels(ROOT))

    for source in SOURCES:
        assert string_literals(source) & vocabulary == set(), source.name


def test_the_adversarial_harness_holds_no_attack_class_literal() -> None:
    declared = {
        entry["attack_class"] for entry in adversarial_payload()["attack_classes"]
    }

    assert string_literals(ADVERSARIAL_SOURCE) & declared == set()
    assert len(declared) == 4


def test_neither_harness_holds_a_dataset_identifier_literal() -> None:
    time_sliced = time_sliced_payload()
    adversarial = adversarial_payload()
    identifiers = (
        {item["item_id"] for item in time_sliced["items"]}
        | {entry["slice_id"] for entry in time_sliced["slices"]}
        | {entry["document_id"] for entry in time_sliced["documents"]}
        | {item["item_id"] for item in adversarial["baseline_items"]}
        | {item["item_id"] for item in adversarial["adversarial_items"]}
    )

    for source in SOURCES:
        assert string_literals(source) & identifiers == set(), source.name


def test_the_time_sliced_field_contracts_match_the_committed_dataset() -> None:
    payload = time_sliced_payload()

    assert set(payload) == set(time_sliced_harness._BENCHMARK_FIELDS)
    for record in payload["documents"]:
        assert set(record) == set(time_sliced_harness._DOCUMENT_FIELDS)
    for record in payload["slices"]:
        assert set(record) == set(time_sliced_harness._SLICE_FIELDS)
    for record in payload["items"]:
        assert set(record) == set(time_sliced_harness._ITEM_FIELDS)


def test_the_adversarial_field_contracts_match_the_committed_dataset() -> None:
    payload = adversarial_payload()

    assert set(payload) == set(adversarial_harness._BENCHMARK_FIELDS)
    for record in payload["attack_classes"]:
        assert set(record) == set(adversarial_harness._ATTACK_CLASS_FIELDS)
    for record in payload["baseline_items"]:
        assert set(record) == set(adversarial_harness._BASELINE_FIELDS)
    for record in payload["adversarial_items"]:
        assert set(record) == set(adversarial_harness._ADVERSARIAL_FIELDS)


def test_the_false_claim_label_is_a_label_the_gold_corpus_declares() -> None:
    payload = adversarial_payload()

    assert payload["false_claim_label"] in adversarial_harness.gold_labels(ROOT)


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(time_sliced_harness.FINDING_CODES) == 23
    assert len(adversarial_harness.FINDING_CODES) == 23
    for module in HARNESSES:
        for code, reason in module.FINDING_CODES.items():
            assert code == code.upper()
            assert code.replace("_", "").isalpha(), code
            assert len(reason) > 50, code


def test_the_refusals_carry_their_code_message_and_context() -> None:
    time_sliced = TimeSliceError("FUTURE_EVIDENCE_LEAK", "message", {"a": 1})
    adversarial = AdversarialEvalError("BASELINE_MISSING", "message", {"a": 1})

    assert time_sliced.code == "FUTURE_EVIDENCE_LEAK"
    assert adversarial.code == "BASELINE_MISSING"
    for error in (time_sliced, adversarial):
        assert str(error) == "message"
        assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised_by_either_harness() -> None:
    with pytest.raises(TimeSliceError) as time_sliced:
        time_sliced_harness._fail("INVENTED_CODE", "message")
    with pytest.raises(AdversarialEvalError) as adversarial:
        adversarial_harness._fail("INVENTED_CODE", "message")

    for caught in (time_sliced, adversarial):
        assert caught.value.code == "INPUT_INVALID"
        assert caught.value.context == {"code": "INVENTED_CODE"}


def test_the_committed_datasets_cite_the_sealed_gold_corpus_by_path() -> None:
    for payload, module in (
        (time_sliced_payload(), time_sliced_harness),
        (adversarial_payload(), adversarial_harness),
    ):
        assert payload["gold_corpus_ref"]["path"] == module.GOLD_CORPUS_RELATIVE_PATH
        assert payload["gold_corpus_ref"]["corpus_id"] == gold_corpus()["corpus_id"]
        assert (
            payload["gold_corpus_ref"]["corpus_version"]
            == gold_corpus()["corpus_version"]
        )
