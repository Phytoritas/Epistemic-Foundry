"""schema_and_type_check — the gate reads schema, never restates it.

This gate composes the sealed X05 surfaces and delegates every canonical-token
decision to them or to the bandit module (EF4-I22), so it should hold *no* wire
literal of its own.  This suite pins that: the two schema kinds it names resolve
in the registry, the fixtures' token ladders match the schemas the negative tests
rely on, the finding codes are internally closed — every ``_fail`` code is a
declared ``FINDING_CODES`` entry — and no canonical enum value appears as a bare
literal in the shipped module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evaluation import bandits
from epistemic_foundry.providers.v4_x06 import gate as mod
from fixtures import (
    DELAYED_HOLDOUT,
    FIXED,
    IMMEDIATE_PROXY,
    MANUAL,
    REPLICATION,
    REWARD_NONE,
    SAFE_BANDIT,
    SAFE_UCB,
    THOMPSON,
    UCB,
    VALIDATED_IMPROVEMENT,
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


def test_both_schema_kinds_resolve_in_the_registry() -> None:
    registry = default_registry()
    for kind in (mod.ROUTING_KIND, mod.BANDIT_STATE_KIND):
        assert registry.document(kind)["title"]


def test_routing_policy_ladder_is_the_expected_order() -> None:
    assert _enum(mod.ROUTING_KIND, "policy") == [
        FIXED,
        UCB,
        THOMPSON,
        SAFE_BANDIT,
        MANUAL,
    ]


def test_reward_basis_ladder_leads_with_the_hackable_immediate_proxy() -> None:
    assert _enum(mod.ROUTING_KIND, "reward_basis") == [
        IMMEDIATE_PROXY,
        VALIDATED_IMPROVEMENT,
        DELAYED_HOLDOUT,
        REPLICATION,
        REWARD_NONE,
    ]


def test_bandit_policy_ladder_places_safe_ucb_third() -> None:
    enum = _enum(mod.BANDIT_STATE_KIND, "policy")
    assert len(enum) == 4
    assert enum[2] == SAFE_UCB


def test_bandit_safe_policy_set_agrees_with_the_module() -> None:
    assert bandits.SAFE_POLICIES == frozenset({SAFE_UCB})


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
    """The shipped gate must read every canonical token, never restate one."""
    held = sorted(_string_literals(MODULE_PATH) & _schema_enum_values())
    assert not held, f"canonical enum values appear as literals: {held}"
