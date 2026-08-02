"""schema_and_type_check — intake reads its contracts, it never restates them.

The genome contract comes from the canonical schema, the mutable search space
from the sealed C05 family index, and every seed lineage validates against the
canonical lineage schema.  The engine source is scanned for canonical enum
values because EF4-I22 is what stops a second copy of a wire vocabulary from
drifting away from the schema that owns it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.intake.v4_i05 import (
    FINDING_CODES,
    GENOME_KIND,
    SCREEN_CODES,
    SEED_GENERATION,
    SIGNATURE_FIELDS,
    GenomeIntakeError,
    bootstrap_seed_population,
    genome_contract,
    intakeable_genome_kind,
    mutable_genome_kinds,
    screen_genome,
)
from epistemic_foundry.intake.v4_i05 import screening as engine
from fixtures import bootstrap_arguments, genome

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/intake/v4_i05/screening.py"
INDEX = ROOT / "schemas/v4_c05/family-index.json"


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


def schema_enum_values() -> set[str]:
    """Every enum value the canonical schemas declare."""
    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list):
                values.update(item for item in enum if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    registry = default_registry()
    for name in registry.names():
        walk(registry.document(name))
    return {value for value in values if value}


def test_the_search_space_comes_from_the_sealed_c05_index() -> None:
    declared = json.loads(INDEX.read_text(encoding="utf-8"))["mutable_search_space"]
    expected = tuple(
        sorted(
            entry.rsplit("/", 1)[-1].removesuffix(".schema.json") for entry in declared
        )
    )

    assert mutable_genome_kinds() == expected
    assert len(expected) == 4


def test_the_intaken_genome_kind_is_inside_the_sealed_search_space() -> None:
    assert intakeable_genome_kind() == GENOME_KIND
    assert GENOME_KIND in mutable_genome_kinds()


def test_every_screened_field_is_required_by_the_canonical_schema() -> None:
    """The engine reads properties; the schema's own required list is checked here.

    ``required`` is itself a canonical enum value elsewhere, so the engine may
    not hold it as a literal (EF4-I22).  This test is what keeps the weaker
    runtime check honest.
    """
    document = genome_contract()
    required = set(document["required"])

    for field in (
        engine.IDENTITY_FIELD,
        engine.LINEAGE_FIELD,
        engine.FALSIFIER_FIELD,
        engine.MECHANISM_FIELD,
        engine.SCOPE_FIELD,
    ):
        assert field in document["properties"], field
        assert field in required, field


def test_the_falsifier_field_is_a_non_empty_array_in_the_schema() -> None:
    """Falsifiability is the schema's own notion, not one this module invented."""
    declared = genome_contract()["properties"][engine.FALSIFIER_FIELD]

    assert declared["type"] == "array"
    assert declared["minItems"] == 1


def test_the_signature_fields_are_declared_genome_properties() -> None:
    properties = genome_contract()["properties"]

    assert set(SIGNATURE_FIELDS) <= set(properties)
    assert SIGNATURE_FIELDS == (engine.MECHANISM_FIELD, engine.SCOPE_FIELD)


def test_a_seed_lineage_validates_against_the_canonical_lineage_schema() -> None:
    population = bootstrap_seed_population(**bootstrap_arguments())

    assert population["seed_lineages"]
    for lineage in population["seed_lineages"]:
        validate_artifact("candidate-lineage", lineage)
        assert lineage["generation"] == SEED_GENERATION
        assert lineage["parent_ids"] == []
        assert lineage["crossover_parent_ids"] == []


def test_a_screened_genome_is_validated_against_the_canonical_schema() -> None:
    record = screen_genome(genome(), genome_kind=GENOME_KIND)

    assert record["admitted"] is True
    assert record["reason_codes"] == []


def test_the_engine_holds_no_canonical_enum_value_as_a_literal() -> None:
    held = sorted(string_literals(ENGINE) & schema_enum_values())

    assert held == [], held


def test_the_engine_holds_no_genome_status_literal() -> None:
    statuses = set(genome_contract()["properties"]["status"]["enum"])
    held = sorted(string_literals(ENGINE) & statuses)

    assert held == [], held


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 12
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_every_screen_code_is_a_declared_finding() -> None:
    assert set(SCREEN_CODES) <= set(FINDING_CODES)
    assert len(set(SCREEN_CODES)) == len(SCREEN_CODES)


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = GenomeIntakeError("SEED_POPULATION_EMPTY", "message", {"a": 1})

    assert error.code == "SEED_POPULATION_EMPTY"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(GenomeIntakeError) as caught:
        engine._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}
