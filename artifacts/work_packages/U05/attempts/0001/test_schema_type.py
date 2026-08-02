"""Schema-and-type checks for the U05 Evolution Chamber console.

These pin the console's contract surface: the finding-code catalogue, the
vocabularies it reads from the canonical schemas rather than naming, the schema
position it depends on, the declared surfaces, and the invariant that the shipped
module holds no canonical enum literal of its own (EF4-I22).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import fixtures
from epistemic_foundry.console import v4_u05
from epistemic_foundry.console.v4_u05 import projection as engine
from epistemic_foundry.contracts import default_registry, repo_root

EXPECTED_CODES = {
    "INPUT_INVALID",
    "SURFACE_UNDECLARED",
    "PROMOTION_AUTHORITY_REFUSED",
    "SNAPSHOT_REFUSED",
    "SNAPSHOT_DRIFT",
    "FRONT_PAIRING_INCOMPLETE",
    "FRONT_REFERENCE_MISALIGNED",
    "NICHE_REFUSED",
    "LINEAGE_REFUSED",
    "CHALLENGE_GENOME_REFUSED",
    "CHALLENGE_RESULT_REFUSED",
    "RESULT_DRIFT",
    "CHALLENGE_TARGET_MISSING",
}


def test_finding_codes_are_documented_strings() -> None:
    assert set(engine.FINDING_CODES) == EXPECTED_CODES
    for code, reason in engine.FINDING_CODES.items():
        assert isinstance(code, str) and code
        assert isinstance(reason, str) and reason.strip()


def test_declared_surfaces_are_the_four_console_surfaces() -> None:
    assert engine.declared_surfaces() == (
        engine.SURFACE_PARETO_FRONT,
        engine.SURFACE_NICHE_MAP,
        engine.SURFACE_LINEAGES,
        engine.SURFACE_CHALLENGE_BOARD,
    )
    assert len(set(engine.declared_surfaces())) == 4


def test_outcome_field_position_names_the_outcome_property() -> None:
    """The position the module reads instead of naming must be the outcome field."""
    properties = list(
        default_registry().document(engine.CHALLENGE_RESULT_SCHEMA)["properties"]
    )
    assert properties[engine.CHALLENGE_OUTCOME_FIELD_POSITION] == "outcome"


def test_vocabularies_are_read_from_the_canonical_schema() -> None:
    assert list(engine.challenge_outcome_vocabulary()) == fixtures.enum_of(
        engine.CHALLENGE_RESULT_SCHEMA, "outcome"
    )
    assert list(engine.challenge_severity_vocabulary()) == fixtures.enum_of(
        engine.CHALLENGE_RESULT_SCHEMA, "severity"
    )


def test_public_api_is_exported() -> None:
    for name in v4_u05.__all__:
        assert hasattr(v4_u05, name), name
    assert v4_u05.build_console_projection is engine.build_console_projection


def _schema_enum_values() -> set[str]:
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
    return values


def _string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_shipped_module_holds_no_canonical_enum_literal() -> None:
    """The console must read every canonical value, never name one (EF4-I22)."""
    enum_values = _schema_enum_values()
    src = repo_root() / "src" / "epistemic_foundry" / "console"
    for path in sorted(src.rglob("*.py")):
        held = sorted(_string_literals(path) & enum_values)
        assert not held, f"{path} holds canonical enum literal(s): {held}"


def test_fixtures_are_canonically_valid() -> None:
    """A vacuous suite would pass over fixtures the schema secretly rejects."""
    json.dumps(fixtures.pareto_snapshot())
    assert fixtures.niche()["niche_hash"].startswith("sha256:")
    assert fixtures.challenge_result()["result_hash"].startswith("sha256:")
