"""schema_and_type_check — the positional vocabularies match the schemas.

The gate reads every canonical token it reasons about positionally out of the
schema that declares it (EF4-I22), so the assumption that a given index selects a
given token is a contract this suite pins.  If a schema reorders its enum, these
tests fail here rather than the gate silently selecting the wrong token.  The
suite also proves the gate's refusal codes are internally closed: every code it
raises is a declared ``FINDING_CODES`` entry.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.security.v4_s06 import governance_gate as gate
from fixtures import (
    APPROVED_FOR_FUTURE,
    FAIL,
    IMMEDIATE_PROXY,
    PASS,
    QUALIFIED,
    QUARANTINED,
    REJECTED,
)

MODULE_PATH = Path(gate.__file__)


def _enum(kind: str, field: str) -> list[str]:
    document = default_registry().document(kind)
    return [str(value) for value in document["properties"][field]["enum"]]


def test_evaluator_proposal_status_ladder_is_the_expected_order() -> None:
    enum = _enum(gate.EVALUATOR_PROPOSAL_KIND, "status")
    assert len(enum) == 4
    assert enum[0] == QUARANTINED
    assert enum[2] == APPROVED_FOR_FUTURE
    assert enum[3] == REJECTED


def test_qualification_status_ladder_puts_qualified_first() -> None:
    enum = _enum(gate.EVALUATOR_QUALIFICATION_KIND, "qualification_status")
    assert len(enum) == 4
    assert enum[0] == QUALIFIED


def test_hard_gate_ladder_is_pass_then_fail() -> None:
    enum = _enum(gate.FITNESS_KIND, "hard_gate_status")
    assert len(enum) == 4
    assert enum[0] == PASS
    assert enum[1] == FAIL


def test_reward_basis_ladder_leads_with_the_hackable_immediate_proxy() -> None:
    enum = _enum(gate.ROUTING_KIND, "reward_basis")
    assert len(enum) == 5
    assert enum[0] == IMMEDIATE_PROXY


def test_vocab_selects_the_expected_tokens() -> None:
    vocab = gate._vocab()
    assert vocab == {
        "proposal_approved": APPROVED_FOR_FUTURE,
        "future_qualified": QUALIFIED,
        "hard_gate_failed": FAIL,
        "reward_immediate_proxy": IMMEDIATE_PROXY,
    }


def test_enum_reader_refuses_a_wrong_expected_length() -> None:
    try:
        gate._enum(gate.FITNESS_KIND, "hard_gate_status", 3)
    except gate.GovernanceGateError as error:
        assert error.code == "VOCABULARY_DRIFT"
    else:  # pragma: no cover - the reader must refuse
        raise AssertionError("a mis-sized vocabulary was accepted")


def test_all_schema_kinds_resolve_in_the_registry() -> None:
    registry = default_registry()
    for kind in (
        gate.EVALUATOR_PROPOSAL_KIND,
        gate.EVALUATOR_QUALIFICATION_KIND,
        gate.FITNESS_KIND,
        gate.ROUTING_KIND,
    ):
        assert registry.document(kind)["title"]


def test_every_raised_finding_code_is_declared() -> None:
    """Each ``_fail`` in the shipped gate names a declared finding code."""
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
    undeclared = sorted(raised - set(gate.FINDING_CODES))
    assert not undeclared, f"undeclared finding codes raised: {undeclared}"


def test_finding_codes_are_all_documented() -> None:
    for code, why in gate.FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(why, str) and why.strip()
