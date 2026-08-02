"""schema_and_type_check — the positional vocabulary matches the schema.

The gate reads the one surrogate token it reasons about positionally out of the
schema that declares it and grounds the promotion authority in the canonical
capability the evolution-authority registry declares (EF4-I22).  This suite pins
that a given index selects a given token, proves the gate's refusal codes are
internally closed — every code it raises is a declared ``FINDING_CODES`` entry —
and proves no canonical enum value appears as a bare literal in the shipped module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.governance.evolution_authority.registry import (
    PROMOTION_COMMIT_CAPABILITY,
)
from epistemic_foundry.operations.v4_y06 import qualification as mod
from fixtures import (
    DEFER,
    EVALUATE_NOW,
    PROMOTION_CAPABILITY,
    REJECT_ONLY_ON_HARD_GATE,
    SAMPLE_FOR_CALIBRATION,
)

MODULE_PATH = Path(mod.__file__)

GENERIC_VALUES = frozenset(
    {
        "none",
        "other",
        "all",
        "any",
        "auto",
        "default",
        "unknown",
        "UNKNOWN",
        "read",
        "write",
        "text",
        "json",
        "yaml",
        "high",
        "low",
        "medium",
        "critical",
        "major",
        "minor",
        "safe",
        "active",
        "stale",
        "run",
        "project",
        "workflow",
        "scope",
        "max_generations",
        "method",
    }
)


def _enum(kind: str, field: str) -> list[str]:
    document = default_registry().document(kind)
    return [str(value) for value in document["properties"][field]["enum"]]


def test_triage_decision_ladder_is_the_expected_order() -> None:
    enum = _enum(mod.SURROGATE_KIND, "triage_decision")
    assert enum == [
        EVALUATE_NOW,
        DEFER,
        SAMPLE_FOR_CALIBRATION,
        REJECT_ONLY_ON_HARD_GATE,
    ]


def test_acceptance_token_is_the_first_rung_of_the_ladder() -> None:
    # The acceptance ("evaluate now") rung is index 0, and the gate reads it
    # positionally rather than holding the literal.
    assert mod.surrogate_acceptance_token() == EVALUATE_NOW
    assert mod._accept_decision_token() == EVALUATE_NOW


def test_promotion_capability_is_grounded_in_the_registry_constant() -> None:
    # The authority gate keys off the canonical promotion-commit capability the
    # evolution-authority registry declares, never a literal of its own.
    assert PROMOTION_CAPABILITY == PROMOTION_COMMIT_CAPABILITY


def test_surrogate_schema_kind_resolves_in_the_registry() -> None:
    assert default_registry().document(mod.SURROGATE_KIND)["title"]


def test_every_raised_finding_code_is_declared() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    raised: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_fail"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            raised.add(node.args[0].value)
    assert raised, "the scan found no _fail codes"
    undeclared = sorted(raised - set(mod.FINDING_CODES))
    assert not undeclared, f"undeclared finding codes raised: {undeclared}"


def test_finding_codes_are_all_documented_with_a_reason() -> None:
    for code, why in mod.FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(why, str) and len(why) > 50


def test_fail_refuses_an_undeclared_code() -> None:
    try:
        mod._fail("NOT_A_DECLARED_CODE", "should never surface")
    except mod.OperationsQualificationError as error:
        assert error.code == "INPUT_INVALID"
    else:  # pragma: no cover - the guard must refuse
        raise AssertionError("an undeclared finding code was accepted")


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
    return {value for value in values if value and value not in GENERIC_VALUES}


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


def test_module_holds_no_canonical_enum_literal() -> None:
    """The shipped module must read every canonical token, never restate one."""
    held = sorted(_string_literals(MODULE_PATH) & _schema_enum_values())
    assert not held, f"canonical enum values appear as literals: {held}"
