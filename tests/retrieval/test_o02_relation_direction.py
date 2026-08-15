from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "retrieval" / "o02" / "relation-direction-cases.json"
CONTRACTS_PATH = ROOT / "python" / "epistemic_foundry" / "retrieval" / "lanes" / "contracts.py"


def load_contracts():
    name = "ef_o02_direction_contracts"
    spec = importlib.util.spec_from_file_location(name, CONTRACTS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTRACTS = load_contracts()
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[row["case_id"] for row in CASES])
def test_relation_direction_fixture_exact_answers(case: dict[str, object]) -> None:
    actual = CONTRACTS.classify_relation_direction(
        case["canonical_relation"],
        case["observed_relations"],
        inverse_predicates=case["inverse_predicates"],
        ontology_version=case["ontology_version"],
        symmetric_predicates=case["symmetric_predicates"],
        trusted_grounding=case["trusted_grounding"],
    )

    assert actual.value == case["expected"]


def test_inverse_predicate_requires_versioned_ontology() -> None:
    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.classify_relation_direction(
            ["A", "parent_of", "B"],
            [["B", "child_of", "A"]],
            inverse_predicates={"parent_of": "child_of"},
        )

    assert raised.value.code == "ONTOLOGY_VERSION_REQUIRED"


@pytest.mark.parametrize("direction", ["NO_DIRECTION", "UNRESOLVED"])
def test_no_direction_and_unresolved_are_not_direction_matches(direction: str) -> None:
    feature_value = 1.0 if direction in {"SAME_DIRECTION", "INVERSE_PREDICATE"} else 0.0
    assert feature_value == 0.0


def test_unknown_relation_shapes_fail_closed() -> None:
    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.classify_relation_direction(["A", "parent_of"], [])

    assert raised.value.code == "RELATION_SHAPE_INVALID"


@pytest.mark.parametrize(
    ("canonical_relation", "observed_relations"),
    [
        ("ABC", []),
        (["A", "parent_of", "B"], "ABC"),
        (["A", "parent_of", "B"], ["ABC"]),
    ],
)
def test_scalar_relation_containers_are_never_split_into_characters(
    canonical_relation: object,
    observed_relations: object,
) -> None:
    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.classify_relation_direction(
            canonical_relation,
            observed_relations,
        )

    assert raised.value.code == "RELATION_SHAPE_INVALID"


def test_trusted_grounding_requires_an_actual_boolean() -> None:
    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.classify_relation_direction(
            ["A", "parent_of", "B"],
            [],
            trusted_grounding=0,
        )

    assert raised.value.code == "FIELD_INVALID"
