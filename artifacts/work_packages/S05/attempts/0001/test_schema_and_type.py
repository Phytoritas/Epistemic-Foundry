"""schema_and_type_check — the controls read their vocabulary, never restate it.

The sandbox classes and the threat register come from the threat model that
EF4-I64 names as its evidence, the leakage surfaces from EF4-I44's own
statement, and the network, safety, approval and status vocabularies from
their canonical schemas — positionally, because holding those enum values as
literals is exactly what EF4-I22 forbids.  Every positional assumption is
asserted here against the declaring text, so the assumption cannot rot in
silence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.security.v4_s05 import (
    FINDING_CODES,
    INCIDENT_ACTIONS,
    INVARIANTS_PATH,
    LEAKAGE_INVARIANT_ID,
    THREAT_MODEL_PATH,
    ThreatControlError,
    qualify_candidate_execution,
    required_leakage_surfaces,
    sandbox_classes,
    threat_register,
)
from epistemic_foundry.security.v4_s05 import threat_controls as controls_module
from fixtures import qualification_arguments

ROOT = Path(__file__).resolve().parents[5]
CONTROLS = ROOT / "src/epistemic_foundry/security/v4_s05/threat_controls.py"


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_the_sandbox_classes_come_from_the_threat_model() -> None:
    text = (ROOT / THREAT_MODEL_PATH).read_text(encoding="utf-8")

    assert sandbox_classes() == tuple(
        re.findall(
            r"^- `([a-z_]+)`:", text.split("## Sandbox classes")[1], re.MULTILINE
        )
    )
    assert len(sandbox_classes()) == 5


def test_the_threat_register_holds_every_table_row() -> None:
    register = threat_register()

    assert len(register) == 12
    assert "candidate reads holdout" in register
    assert "prompt genome authority drift" in register
    for control in register.values():
        assert control


def test_the_leakage_surfaces_come_from_the_invariant_statement() -> None:
    document = yaml.safe_load((ROOT / INVARIANTS_PATH).read_text(encoding="utf-8"))
    statement = next(
        row["statement"]
        for row in document["invariants"]
        if row["id"] == LEAKAGE_INVARIANT_ID
    )
    enumerated = re.search(r"([\w]+(?:/[\w]+)+) leakage", statement).group(1)

    assert required_leakage_surfaces() == tuple(sorted(enumerated.split("/")))
    assert len(required_leakage_surfaces()) == 3


def test_the_network_vocabulary_is_declared_in_escalating_order() -> None:
    # The engine refuses the last network policy and requires capabilities
    # for the second; that positional rule is only sound while the schema
    # declares the vocabulary closed-to-open.  This test pins the assumption.
    document = default_registry().document("validation-target-manifest")

    assert document["properties"]["network_policy"]["enum"] == [
        "disabled",
        "allowlist",
        "unrestricted_with_approval",
    ]
    assert document["properties"]["safety_class"]["enum"] == [
        "read_only",
        "bounded_compute",
        "controlled_effect",
        "high_risk",
    ]
    assert document["properties"]["approval_policy"]["enum"] == [
        "none",
        "high_risk_only",
        "all_effects",
    ]


def test_the_audit_status_vocabulary_is_declared_pass_first() -> None:
    document = default_registry().document("leakage-audit")

    assert document["properties"]["status"]["enum"][:2] == ["PASS", "FAIL"]


def test_the_incident_actions_appear_in_the_threat_models_own_words() -> None:
    text = (ROOT / THREAT_MODEL_PATH).read_text(encoding="utf-8").lower()
    incident = text.split("## incident handling")[1]

    for action in INCIDENT_ACTIONS:
        for word in action.split():
            assert word in incident, (action, word)


def test_the_controls_hold_no_manifest_enum_literal() -> None:
    document = default_registry().document("validation-target-manifest")
    vocabulary = set()
    for field in ("network_policy", "safety_class", "approval_policy", "target_type"):
        vocabulary.update(document["properties"][field]["enum"])
    held = string_literals(CONTROLS) & vocabulary

    assert held == set(), held


def test_the_controls_hold_no_audit_status_or_proposal_status_literal() -> None:
    audit = default_registry().document("leakage-audit")
    proposal = default_registry().document("prompt-mutation-proposal")
    vocabulary = set(audit["properties"]["status"]["enum"]) | set(
        proposal["properties"]["status"]["enum"]
    )
    held = string_literals(CONTROLS) & vocabulary

    assert held == set(), held


def test_a_qualification_names_only_registered_threats() -> None:
    record = qualify_candidate_execution(**qualification_arguments())

    assert set(record["threats_controlled"]) <= set(threat_register())
    assert len(record["threats_controlled"]) == 4


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 15
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = ThreatControlError("HOLDOUT_REACHABLE", "message", {"a": 1})

    assert error.code == "HOLDOUT_REACHABLE"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(ThreatControlError) as caught:
        controls_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}
