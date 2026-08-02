"""Schema and type discipline for the Q05 admissibility gate.

The gate reads its one canonical vocabulary — the passing hard-gate token — out
of the fitness-vector schema rather than restating it (EF4-I22), composes the
sealed owning surfaces rather than re-deriving their contracts, and exposes a
stable public surface. These tests pin those structural facts.
"""

from __future__ import annotations

from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evaluation.v4_q05 import gate

ROOT = Path(__file__).resolve().parents[5]


def test_the_passing_hard_gate_token_is_read_from_the_canonical_schema() -> None:
    schema = default_registry().document("fitness-vector")
    enum = schema["properties"]["hard_gate_status"]["enum"]
    assert gate.hard_gate_pass_token() == enum[0]


def test_the_gate_module_holds_no_canonical_hard_gate_status_literal() -> None:
    """The gate must not restate the fitness status vocabulary as a literal."""
    source = (
        ROOT / "src" / "epistemic_foundry" / "evaluation" / "v4_q05" / "gate.py"
    ).read_text(encoding="utf-8")
    schema = default_registry().document("fitness-vector")
    for token in schema["properties"]["hard_gate_status"]["enum"]:
        assert f'"{token}"' not in source and f"'{token}'" not in source


def test_the_decision_tokens_are_not_canonical_schema_enum_values() -> None:
    """ADMIT/REFUSE are the gate's own vocabulary, not wire-pinned values."""
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
    assert gate.ADMIT not in values
    assert gate.REFUSE not in values


def test_every_finding_code_carries_an_explanation() -> None:
    assert gate.FINDING_CODES
    for code, reason in gate.FINDING_CODES.items():
        assert code.isupper() and isinstance(reason, str) and reason.strip()


def test_the_public_surface_is_exactly_the_documented_exports() -> None:
    assert set(gate.__all__) == {
        "ADMIT",
        "FINDING_CODES",
        "GATE_NAME",
        "REFUSE",
        "SchemaNotFound",
        "SelectiveAdmissibilityRefused",
        "derive_selective_admissibility",
        "evaluate_selective_admissibility",
        "hard_gate_pass_token",
    }


def test_the_package_re_exports_the_gate_surface() -> None:
    from epistemic_foundry.evaluation import v4_q05

    for name in (
        "derive_selective_admissibility",
        "evaluate_selective_admissibility",
        "SelectiveAdmissibilityRefused",
        "FINDING_CODES",
    ):
        assert hasattr(v4_q05, name)


def test_the_gate_never_writes_a_canonical_schema_enum_value() -> None:
    """The whole gate module holds zero canonical enum literal (EF4-I22).

    This mirrors the repository-wide wire-literal discipline suite for the one
    module Q05 owns, so a drift is caught in the package's own targeted run.
    """
    import ast

    source_path = (
        ROOT / "src" / "epistemic_foundry" / "evaluation" / "v4_q05" / "gate.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            if isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }

    generic = {
        "none",
        "other",
        "all",
        "any",
        "auto",
        "default",
        "unknown",
        "read",
        "write",
    }
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
    enum_values = {value for value in values if value and value not in generic}
    assert not (literals & enum_values), literals & enum_values
