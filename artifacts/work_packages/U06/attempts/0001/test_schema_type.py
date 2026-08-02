"""Schema-and-type checks for the U06 operator usability gate.

These pin the gate's contract surface: the finding-code catalogue, the honest-UI
states it reads from the module that owns them rather than naming, the surfaces
it composes (exactly the sealed U05 surfaces), the principal-count keys it reads
from a U05 view, and the invariant that the shipped module holds no canonical
enum literal of its own (EF4-I22).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import fixtures
from epistemic_foundry.console import v4_u06
from epistemic_foundry.console.v4_u05 import projection as u05
from epistemic_foundry.console.v4_u06 import usability_gate as gate
from epistemic_foundry.contracts import repo_root
from epistemic_foundry.observability.result_state import ResultState

EXPECTED_CODES = {
    "INPUT_INVALID",
    "SURFACE_UNDECLARED",
    "PROMOTION_AUTHORITY_REFUSED",
    "RECEIPT_DRIFT",
    "DASHBOARD_SUBPANEL_TAMPERED",
    "DISHONEST_STATE_REFUSED",
    "COMPLETENESS_OVERSTATED",
}


def test_finding_codes_are_documented_strings() -> None:
    assert set(gate.FINDING_CODES) == EXPECTED_CODES
    for code, reason in gate.FINDING_CODES.items():
        assert isinstance(code, str) and code
        assert isinstance(reason, str) and reason.strip()


def test_panel_surfaces_are_exactly_the_sealed_console_surfaces() -> None:
    """The gate composes the sealed U05 console; it invents no surface of its own."""
    assert gate.declared_panel_surfaces() == u05.declared_surfaces()
    assert set(gate._PRINCIPAL_COUNT) == set(u05.declared_surfaces())


def test_principal_count_keys_exist_in_the_u05_views() -> None:
    """Emptiness is read from a real key in each surface's ``counts`` map."""
    views = {
        u05.SURFACE_PARETO_FRONT: u05.project_pareto_front(fixtures.pareto_snapshot()),
        u05.SURFACE_NICHE_MAP: u05.project_niche_map(fixtures.two_niches()),
        u05.SURFACE_LINEAGES: u05.project_lineages(fixtures.two_lineages()),
        u05.SURFACE_CHALLENGE_BOARD: u05.project_challenge_board(
            [fixtures.challenge_genome()], [fixtures.challenge_result()]
        ),
    }
    for surface, key in gate._PRINCIPAL_COUNT.items():
        assert key in views[surface]["counts"], (surface, key)


def test_states_are_the_four_honest_ui_states_from_the_owner() -> None:
    """The gate reads the honest-UI vocabulary from its owner (EF4-I23/EF4-I22)."""
    assert gate.ResultState is ResultState
    assert {str(state) for state in ResultState} == {
        "POPULATED",
        "EMPTY_CONFIRMED",
        "DEGRADED",
        "UNAVAILABLE",
    }


def test_public_api_is_exported() -> None:
    for name in v4_u06.__all__:
        assert hasattr(v4_u06, name), name
    assert v4_u06.build_operator_panel is gate.build_operator_panel
    assert v4_u06.compose_operator_dashboard is gate.compose_operator_dashboard


def _schema_enum_values() -> set[str]:
    from epistemic_foundry.contracts import default_registry

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


def test_shipped_gate_holds_no_canonical_enum_literal() -> None:
    """The gate must read every canonical value, never name one (EF4-I22).

    The honest-UI states in particular are referenced through ``ResultState`` and
    never written as bare strings, so a schema change reshapes the gate instead
    of drifting from it.
    """
    enum_values = _schema_enum_values()
    module = repo_root() / "src" / "epistemic_foundry" / "console" / "v4_u06"
    for path in sorted(module.rglob("*.py")):
        held = sorted(_string_literals(path) & enum_values)
        assert not held, f"{path} holds canonical enum literal(s): {held}"


def test_fixtures_are_canonically_valid() -> None:
    """A vacuous suite would pass over fixtures the schema secretly rejects."""
    json.dumps(fixtures.pareto_snapshot())
    assert fixtures.niche()["niche_hash"].startswith("sha256:")
    assert fixtures.challenge_result()["result_hash"].startswith("sha256:")
