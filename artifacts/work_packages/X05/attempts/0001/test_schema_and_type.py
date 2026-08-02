"""schema_and_type_check — the positional vocabularies match the schemas.

The surface reads every canonical token it reasons about positionally out of the
schema that declares it (EF4-I22), and it discovers the ``policy`` field name
rather than writing it as a literal because that token is itself a canonical
enum value elsewhere.  This suite pins both assumptions: that a given index
selects a given token, and that the field discovery lands on the right property.
It also proves the surface's refusal codes are internally closed — every code it
raises is a declared ``FINDING_CODES`` entry — and that no canonical enum value
appears as a bare literal in the shipped module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evaluation import bandits
from epistemic_foundry.providers.v4_x05 import routing as mod
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


def test_routing_policy_ladder_is_the_expected_order() -> None:
    enum = _enum(mod.ROUTING_KIND, "policy")
    assert enum == [FIXED, UCB, THOMPSON, SAFE_BANDIT, MANUAL]


def test_reward_basis_ladder_leads_with_the_hackable_immediate_proxy() -> None:
    enum = _enum(mod.ROUTING_KIND, "reward_basis")
    assert enum == [
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


def test_field_discovery_lands_on_the_right_properties() -> None:
    fields = mod._fields()
    assert fields["routing_policy"] == "policy"
    assert fields["routing_reward"] == "reward_basis"
    assert fields["bandit_policy"] == "policy"


def test_vocab_selects_the_expected_tokens() -> None:
    vocab = mod._vocab()
    assert vocab["routing_learning_safe"] == SAFE_BANDIT
    assert vocab["routing_learning_unsafe"] == frozenset({UCB, THOMPSON})
    assert vocab["routing_non_learning"] == frozenset({FIXED, MANUAL})
    assert vocab["reward_immediate_proxy"] == IMMEDIATE_PROXY
    assert vocab["reward_none"] == REWARD_NONE
    assert vocab["reward_validated"] == frozenset(
        {VALIDATED_IMPROVEMENT, DELAYED_HOLDOUT, REPLICATION}
    )
    assert vocab["bandit_policy_safe"] == SAFE_UCB


def test_vocab_safe_token_agrees_with_the_bandit_module() -> None:
    assert bandits.SAFE_POLICIES == frozenset({mod._vocab()["bandit_policy_safe"]})


def test_enum_reader_refuses_a_wrong_expected_length() -> None:
    try:
        mod._enum(mod.ROUTING_KIND, "policy", 4)
    except mod.MutationRoutingError as error:
        assert error.code == "VOCABULARY_DRIFT"
    else:  # pragma: no cover - the reader must refuse
        raise AssertionError("a mis-sized vocabulary was accepted")


def test_all_schema_kinds_resolve_in_the_registry() -> None:
    registry = default_registry()
    for kind in (mod.ROUTING_KIND, mod.BANDIT_STATE_KIND):
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
