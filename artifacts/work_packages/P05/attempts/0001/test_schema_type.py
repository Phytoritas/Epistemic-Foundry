"""Schema and type discipline for the P05 promotion-Parliament gate.

The gate reads the one canonical vocabulary it needs as a value — the blocking
replication promotion-effect — out of the replication-result schema rather than
restating it (EF4-I22), holds no other canonical enum literal, composes the
sealed owning surfaces, and exposes a stable public surface. These tests pin
those structural facts.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.parliament.v4_p05 import gate

ROOT = Path(__file__).resolve().parents[5]
GATE_SOURCE = ROOT / "src" / "epistemic_foundry" / "parliament" / "v4_p05" / "gate.py"


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
            ):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_the_blocking_replication_effect_is_read_from_the_canonical_schema() -> None:
    schema = default_registry().document("replication-result")
    enum = schema["properties"]["promotion_effect"]["enum"]
    assert gate.replication_blocking_effect() == enum[-1]


def test_the_gate_module_holds_no_canonical_schema_enum_literal() -> None:
    """EF4-I22: the promotion decision surface restates no wire vocabulary.

    This is the module-local statement of the repository-wide wire-literal
    discipline: not one enum value from any canonical schema may appear as a bare
    string constant in the gate, so the tokens it reasons about are read from the
    schemas or imported from the surfaces that own them.
    """
    held = _string_literals(GATE_SOURCE) & _schema_enum_values()
    assert not held, f"gate.py restates canonical schema vocabulary: {sorted(held)}"


def test_the_decision_tokens_are_not_canonical_schema_enum_values() -> None:
    values = _schema_enum_values()
    assert gate.CONVENE not in values
    assert gate.WITHHOLD not in values


def test_every_finding_code_carries_an_explanation() -> None:
    assert gate.FINDING_CODES
    for code, reason in gate.FINDING_CODES.items():
        assert code.isupper() and isinstance(reason, str) and reason.strip()


def test_the_public_surface_is_exactly_the_declared_exports() -> None:
    expected = {
        "CONVENE",
        "FINDING_CODES",
        "GATE_NAME",
        "PromotionParliamentWithheld",
        "SchemaNotFound",
        "WITHHOLD",
        "derive_promotion_parliament",
        "evaluate_promotion_parliament",
        "parliament_grants_promotion",
        "replication_blocking_effect",
    }
    assert set(gate.__all__) == expected
    for name in expected:
        assert hasattr(gate, name)


def test_the_package_reexports_the_gate_surface() -> None:
    from epistemic_foundry.parliament import v4_p05

    assert set(v4_p05.__all__) == set(gate.__all__)
    assert v4_p05.derive_promotion_parliament is gate.derive_promotion_parliament


def test_the_gate_informs_the_promotion_gates_it_composes() -> None:
    """The recorded gate ids come from the promotion authority, not a local copy."""
    from epistemic_foundry.governance.promotion import CANONICAL_GATE_IDS

    assert gate.STATISTICS_GATE in CANONICAL_GATE_IDS
    assert gate.RED_QUEEN_GATE in CANONICAL_GATE_IDS
    assert gate.REPLICATION_GATE in CANONICAL_GATE_IDS
    assert gate.PARLIAMENT_GATE in CANONICAL_GATE_IDS
