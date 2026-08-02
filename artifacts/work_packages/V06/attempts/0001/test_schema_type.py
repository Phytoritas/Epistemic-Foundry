"""schema_and_type_check — the composed receipt shapes and vocabulary hold.

V06 validates no canonical schema of its own: it composes the sealed Q05, V05 and
P05 gate *receipts*.  So the contract this suite pins is the type/shape assumption
the gate makes about those receipts — every field it reads must be present, and of
the type it reads it as, on a genuine sealed sub-receipt — together with the
gate's own vocabulary discipline: its ``gate`` name and decision tokens are its
own, not canonical schema enum values (EF4-I22), the sub-gate names it binds
against are the sealed gates' own exported ``GATE_NAME`` constants rather than
restated literals, and its refusal codes are internally closed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evaluation.v4_q05 import ADMIT as STATISTICAL_ADMIT
from epistemic_foundry.evaluation.v4_q05 import GATE_NAME as STATISTICAL_GATE_NAME
from epistemic_foundry.parliament.v4_p05 import CONVENE as PARLIAMENT_CONVENE
from epistemic_foundry.parliament.v4_p05 import GATE_NAME as PARLIAMENT_GATE_NAME
from epistemic_foundry.validation.v4_v05 import ADVANCE as VALIDATION_ADVANCE
from epistemic_foundry.validation.v4_v05 import GATE_NAME as VALIDATION_GATE_NAME
from epistemic_foundry.validation.v4_v06 import gate
from fixtures import q05_receipt, v05_receipt, p05_receipt

MODULE_PATH = Path(gate.__file__)


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


# -- the gate's own vocabulary is not canonical wire vocabulary -------------


def test_module_holds_no_canonical_schema_enum_literal() -> None:
    """EF4-I22: the gate restates no canonical enum value as a bare literal.

    Because it composes gate receipts rather than schema artifacts, the gate has
    no legitimate reason to hold a canonical enum at all; this proves it does not.
    """
    held = sorted(_string_literals(MODULE_PATH) & _schema_enum_values())
    assert not held, f"module holds canonical schema enum literals: {held}"


def test_decision_tokens_are_the_gates_own_not_schema_enum_values() -> None:
    enums = _schema_enum_values()
    assert gate.INTEGRATE not in enums
    assert gate.REFUSE not in enums
    assert gate.GATE_NAME not in enums


def test_bound_sub_gate_names_are_the_sealed_gates_exported_constants() -> None:
    """The gate binds against imported ``GATE_NAME`` constants, never restatements."""
    assert STATISTICAL_GATE_NAME and VALIDATION_GATE_NAME and PARLIAMENT_GATE_NAME
    # Three distinct sealed gates, so a receipt of one can never satisfy another.
    assert len({STATISTICAL_GATE_NAME, VALIDATION_GATE_NAME, PARLIAMENT_GATE_NAME}) == 3


# -- the sub-receipt shape assumptions hold on genuine sealed outputs -------


def test_statistical_receipt_carries_the_fields_the_gate_reads() -> None:
    receipt = q05_receipt()
    assert receipt["gate"] == STATISTICAL_GATE_NAME
    assert receipt["decision"] == STATISTICAL_ADMIT
    assert isinstance(receipt["admissible_for_promotion_review"], bool)
    assert isinstance(receipt["candidate_id"], str)
    assert isinstance(receipt["receipt_hash"], str)
    assert isinstance(receipt["gate_id"], str)


def test_validation_receipt_carries_the_fields_the_gate_reads() -> None:
    receipt = v05_receipt()
    assert receipt["gate"] == VALIDATION_GATE_NAME
    assert receipt["decision"] == VALIDATION_ADVANCE
    assert isinstance(receipt["advanced"], bool)
    # The reference V06 cross-checks against the handed statistical clearance.
    assert isinstance(receipt["statistical_admissibility_receipt_hash"], str)
    assert isinstance(receipt["candidate_id"], str)


def test_parliament_receipt_carries_the_fields_the_gate_reads() -> None:
    receipt = p05_receipt()
    assert receipt["gate"] == PARLIAMENT_GATE_NAME
    assert receipt["decision"] == PARLIAMENT_CONVENE
    assert isinstance(receipt["convened_for_promotion_authority"], bool)
    # The authority boundary the gate re-verifies, and the reference it binds.
    assert receipt["grants_promotion"] is False
    assert isinstance(receipt["statistical_receipt_hash"], str)


def test_the_one_clearance_is_referenced_by_both_downstream_receipts() -> None:
    """A genuine end-to-end path threads one Q05 hash through V05 and P05."""
    clearance = q05_receipt()
    validation = v05_receipt(admissibility_receipt=clearance)
    parliament = p05_receipt(selective_admissibility=clearance)
    assert (
        validation["statistical_admissibility_receipt_hash"]
        == clearance["receipt_hash"]
    )
    assert parliament["statistical_receipt_hash"] == clearance["receipt_hash"]


# -- the gate's refusal vocabulary is internally closed ---------------------


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
    undeclared = sorted(raised - set(gate.FINDING_CODES))
    assert not undeclared, f"undeclared finding codes raised: {undeclared}"


def test_finding_codes_are_all_documented() -> None:
    for code, why in gate.FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(why, str) and why.strip()
