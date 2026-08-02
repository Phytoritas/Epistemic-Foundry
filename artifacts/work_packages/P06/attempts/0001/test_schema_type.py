"""Schema and type discipline for the P06 no-majority promotion referral gate.

The gate reads the one canonical vocabulary it needs as a value — the passing
attestation status — out of the attestation schema rather than restating it
(EF4-I22), holds no other canonical enum literal, composes the sealed owning
surfaces, pins the one V05 gate name it cannot import to the real one, and
exposes a stable public surface. These tests pin those structural facts.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.parliament.v4_p06 import gate

ROOT = Path(__file__).resolve().parents[5]
GATE_SOURCE = ROOT / "src" / "epistemic_foundry" / "parliament" / "v4_p06" / "gate.py"


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


def test_the_passing_attestation_status_is_read_from_the_canonical_schema() -> None:
    schema = default_registry().document("attestation")
    enum = schema["properties"]["overall_status"]["enum"]
    assert gate.attestation_pass_status() == enum[0]


def test_the_gate_module_holds_no_canonical_schema_enum_literal() -> None:
    """EF4-I22: the referral surface restates no wire vocabulary.

    Not one enum value from any canonical schema may appear as a bare string
    constant in the gate, so the tokens it reasons about are read from the schemas
    or imported from the surfaces that own them.
    """
    held = _string_literals(GATE_SOURCE) & _schema_enum_values()
    assert not held, f"gate.py restates canonical schema vocabulary: {sorted(held)}"


def test_the_decision_tokens_are_not_canonical_schema_enum_values() -> None:
    values = _schema_enum_values()
    assert gate.REFER not in values
    assert gate.WITHHOLD not in values


def test_the_pinned_validation_gate_name_matches_the_real_v05_gate() -> None:
    """The pinned boundary constant is the actual V05 gate name, not a guess.

    The runtime module cannot import ``validation.v4_v05`` without closing a
    forbidden ``parliament``↔``validation`` component cycle, so it pins the gate
    name it verifies against.  This test — which lives outside the component graph
    and may import V05 freely — proves the pin equals the real name, so a rename
    of the V05 gate fails here loudly instead of drifting silently.
    """
    from epistemic_foundry.validation.v4_v05 import GATE_NAME as VALIDATION_GATE_NAME

    assert gate.COMPOSED_VALIDATION_GATE_NAME == VALIDATION_GATE_NAME


def test_the_parliament_gate_name_is_imported_from_the_owning_gate() -> None:
    from epistemic_foundry.parliament.v4_p05 import GATE_NAME as PARLIAMENT_GATE_NAME

    assert gate.PARLIAMENT_GATE_NAME == PARLIAMENT_GATE_NAME


def test_the_referral_informs_the_constitutional_attestation_gate() -> None:
    from epistemic_foundry.governance.promotion import CANONICAL_GATE_IDS

    assert gate.ATTESTATION_GATE in CANONICAL_GATE_IDS
    assert gate.ATTESTATION_GATE == CANONICAL_GATE_IDS[12]


def test_every_finding_code_carries_an_explanation() -> None:
    assert gate.FINDING_CODES
    for code, reason in gate.FINDING_CODES.items():
        assert code.isupper() and isinstance(reason, str) and reason.strip()


def test_the_public_surface_is_exactly_the_declared_exports() -> None:
    expected = {
        "FINDING_CODES",
        "GATE_NAME",
        "NoMajorityPromotionWithheld",
        "REFER",
        "SchemaNotFound",
        "WITHHOLD",
        "attestation_pass_status",
        "derive_promotion_referral",
        "evaluate_promotion_referral",
        "gate_grants_promotion",
    }
    assert set(gate.__all__) == expected
    for name in expected:
        assert hasattr(gate, name)


def test_the_package_reexports_the_gate_surface() -> None:
    from epistemic_foundry.parliament import v4_p06

    assert set(v4_p06.__all__) == set(gate.__all__)
    assert v4_p06.derive_promotion_referral is gate.derive_promotion_referral
