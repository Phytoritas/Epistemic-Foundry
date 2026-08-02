"""Schema and type discipline for the Q06 governance-integration gate.

The gate reads its one canonical vocabulary — the passing calibration status —
out of the calibration-report schema rather than restating it (EF4-I22),
composes the sealed Q05 and V05 verdicts, and reduces a bundle of composed
artifacts to one immutable receipt.  It composes V05 *without* importing the
``validation`` component, so no new top-level ``evaluation``↔``validation`` cycle
is closed.  These tests pin the vocabulary read, the receipt's shape and
identifier formats, the cycle-avoiding import discipline, and the non-canonical
decision tokens, so a schema reshape, a receipt-field drift, or an accidental
cross-component import fails here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import fixtures as fx
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evaluation.v4_q06 import gate as engine

ROOT = Path(__file__).resolve().parents[5]
GATE_SOURCE = (
    ROOT / "src" / "epistemic_foundry" / "evaluation" / "v4_q06" / "gate.py"
).read_text(encoding="utf-8")


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
    return {value for value in values if value}


def test_passing_calibration_status_is_read_from_the_schema() -> None:
    document = default_registry().document("calibration-report")
    statuses = document["properties"]["calibration_status"]["enum"]
    assert engine.calibration_pass_status() == statuses[0]
    assert engine.calibration_pass_status() in statuses


def test_gate_source_holds_no_calibration_status_literal() -> None:
    """The gate must not restate the calibration status vocabulary as a literal."""
    document = default_registry().document("calibration-report")
    for token in document["properties"]["calibration_status"]["enum"]:
        assert f'"{token}"' not in GATE_SOURCE and f"'{token}'" not in GATE_SOURCE


def test_decision_tokens_are_not_canonical_schema_enum_values() -> None:
    """GOVERN/REFUSE are the gate's own vocabulary, not wire-pinned values."""
    enum_values = _schema_enum_values()
    assert engine.GOVERN not in enum_values
    assert engine.REFUSE not in enum_values


def test_gate_does_not_import_the_validation_component() -> None:
    """Composing V05 must not close a new evaluation<->validation import cycle.

    The advancement receipt is verified structurally and bound to the Q05
    clearance by hash, so no import from ``validation`` (or ``validation_bay``)
    is needed.  An import of either would be the edge that closes the forbidden
    top-level cycle, so the gate's own import table is asserted to hold none.
    """
    tree = ast.parse(GATE_SOURCE)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert not any("validation" in module for module in imported), imported


def test_every_finding_code_carries_a_reason() -> None:
    assert engine.FINDING_CODES
    for code, reason in engine.FINDING_CODES.items():
        assert code.isupper()
        assert isinstance(reason, str) and reason.strip()


def test_govern_receipt_has_the_expected_shape_and_types() -> None:
    receipt = engine.derive_governance_integration(**fx.gate_arguments())
    assert receipt["gate"] == engine.GATE_NAME
    assert receipt["decision"] == engine.GOVERN
    assert receipt["cleared_for_promotion_review"] is True
    assert receipt["finding_code"] is None
    assert receipt["candidate_id"] == fx.CANDIDATE_ID
    assert receipt["evaluation_id"] == fx.EVALUATION_ID
    assert receipt["statistical_admitted"] is True
    assert receipt["validation_advanced"] is True
    assert receipt["calibration_passed"] is True
    assert receipt["calibration_status"] == engine.calibration_pass_status()
    assert receipt["winner_curse_controlled"] is True
    assert receipt["concerns_gated"] == sorted(
        (
            engine.CONCERN_STATISTICAL_ADMISSIBILITY,
            engine.CONCERN_VALIDATION_ADVANCEMENT,
            engine.CONCERN_CALIBRATION,
            engine.CONCERN_WINNER_CURSE,
        )
    )


def test_receipt_identifiers_have_stable_formats() -> None:
    receipt = engine.derive_governance_integration(**fx.gate_arguments())
    assert receipt["gate_id"].startswith(engine.GATE_ID_PREFIX)
    assert receipt["receipt_hash"].startswith("sha256:")
    assert len(receipt["receipt_hash"]) == len("sha256:") + 64


def test_receipt_binds_both_sealed_verdicts_by_hash() -> None:
    args = fx.gate_arguments()
    receipt = engine.derive_governance_integration(**args)
    assert (
        receipt["statistical_admissibility_receipt_hash"]
        == args["admissibility_receipt"]["receipt_hash"]
    )
    assert (
        receipt["validation_advancement_receipt_hash"]
        == args["advancement_receipt"]["receipt_hash"]
    )
    assert (
        receipt["selective_report_hash"]
        == args["admissibility_receipt"]["selective_report_hash"]
    )


def test_public_surface_is_stable() -> None:
    for name in (
        "FINDING_CODES",
        "GATE_NAME",
        "GATE_ID_PREFIX",
        "GOVERN",
        "REFUSE",
        "SchemaNotFound",
        "GovernanceIntegrationRefused",
        "calibration_pass_status",
        "derive_governance_integration",
        "evaluate_governance_integration",
        "governance_hash_matches",
    ):
        assert hasattr(engine, name)
