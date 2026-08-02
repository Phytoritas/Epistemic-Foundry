"""schema_and_type_check — the positional vocabulary matches the schema.

The surface reads the one triage token it reasons about positionally out of the
schema that declares it (EF4-I22).  This suite pins that a given index selects a
given token, proves the surface's refusal codes are internally closed — every
code it raises is a declared ``FINDING_CODES`` entry — and proves no canonical
enum value appears as a bare literal in the shipped module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.operations.v4_y05 import scaling as mod
from fixtures import (
    DEFER,
    EVALUATE_NOW,
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


def test_hard_gate_reject_is_the_only_rejection_the_schema_permits() -> None:
    # The last rung is the only rejection, and it is a deterministic hard-gate
    # result rather than a surrogate judgment.
    assert mod.surrogate_hard_gate_reject_token() == REJECT_ONLY_ON_HARD_GATE
    assert mod._vocab()["triage_reject_on_hard_gate"] == REJECT_ONLY_ON_HARD_GATE


def test_enum_reader_refuses_a_wrong_expected_length() -> None:
    try:
        mod._enum(mod.SURROGATE_KIND, "triage_decision", 3)
    except mod.OperationsScalingError as error:
        assert error.code == "VOCABULARY_DRIFT"
    else:  # pragma: no cover - the reader must refuse
        raise AssertionError("a mis-sized vocabulary was accepted")


def test_all_schema_kinds_resolve_in_the_registry() -> None:
    registry = default_registry()
    for kind in (mod.QD_MAP_KIND, mod.REBALANCE_KIND, mod.SURROGATE_KIND):
        assert registry.document(kind)["title"]


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


def test_finding_codes_are_all_documented() -> None:
    for code, why in mod.FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(why, str) and why.strip()


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
