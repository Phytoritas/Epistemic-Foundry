"""Schema and type discipline for the O06 integration gate.

These tests pin the *positions* the gate reads canonical tokens by against the
schema text itself, so a schema edit that reorders or empties a ladder fails
here rather than being silently mis-read at runtime.  Test modules may name the
canonical tokens as literals; the gate under test may not, and the wire-literal
discipline suite in the main tree enforces that separately.
"""

from __future__ import annotations

import fixtures as f
import pytest
from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.retrieval.v4_o05 import (
    CERTIFICATE_SCHEMA,
    receipt_state_vocabulary,
)
from epistemic_foundry.retrieval.v4_o06 import gate as engine
from epistemic_foundry.retrieval.v4_o06 import (
    ABSENCE_CORPUS_CONDITIONAL_POSITION,
    ABSENCE_EXTERNAL_CONDITIONAL_POSITION,
    ABSENCE_NONE_POSITION,
    COMPLETION_BLOCKED_POSITION,
    COMPLETION_FAIL_POSITION,
    COMPLETION_NOT_REQUIRED_POSITION,
    COMPLETION_PARTIAL_POSITION,
    COMPLETION_PASS_POSITION,
    EXEMPT_WORK_CLASS_POSITION,
    FINDING_CODES,
    NOVELTY_CORPUS_NOVEL_ONLY_POSITION,
    NOVELTY_NOT_ASSESSED_POSITION,
    NOVELTY_SEARCH_CONDITIONAL_POSITION,
    RECEIPT_BLOCKED_POSITION,
    RECEIPT_FAILED_POSITION,
    RECEIPT_PARTIAL_POSITION,
    absence_ceiling_vocabulary,
    completion_state_vocabulary,
    novelty_ceiling_vocabulary,
    work_class_vocabulary,
)


def _certificate_schema() -> dict:
    return default_registry().document(CERTIFICATE_SCHEMA)


def test_completion_state_positions_match_the_schema_order() -> None:
    """The five completion states are read positionally; pin every position."""
    enum = _certificate_schema()["properties"]["completion_state"]["enum"]
    assert tuple(completion_state_vocabulary()) == tuple(enum)
    assert enum[COMPLETION_NOT_REQUIRED_POSITION] == "NOT_REQUIRED"
    assert enum[COMPLETION_PASS_POSITION] == "PASS"
    assert enum[COMPLETION_PARTIAL_POSITION] == "PARTIAL"
    assert enum[COMPLETION_BLOCKED_POSITION] == "BLOCKED"
    assert enum[COMPLETION_FAIL_POSITION] == "FAIL"


def test_absence_ceiling_positions_match_the_schema_order() -> None:
    enum = _certificate_schema()["properties"]["absence_claim_ceiling"]["enum"]
    assert tuple(absence_ceiling_vocabulary()) == tuple(enum)
    assert enum[ABSENCE_NONE_POSITION] == "NONE"
    assert enum[ABSENCE_CORPUS_CONDITIONAL_POSITION] == "CORPUS_CONDITIONAL"
    assert enum[ABSENCE_EXTERNAL_CONDITIONAL_POSITION] == "EXTERNAL_CONDITIONAL"


def test_novelty_ceiling_positions_match_the_schema_order() -> None:
    enum = _certificate_schema()["properties"]["novelty_claim_ceiling"]["enum"]
    assert tuple(novelty_ceiling_vocabulary()) == tuple(enum)
    assert enum[NOVELTY_NOT_ASSESSED_POSITION] == "NOT_ASSESSED"
    assert enum[NOVELTY_CORPUS_NOVEL_ONLY_POSITION] == "CORPUS_NOVEL_ONLY"
    assert enum[NOVELTY_SEARCH_CONDITIONAL_POSITION] == "SEARCH_CONDITIONAL"


def test_exempt_work_class_is_the_schemas_first_class() -> None:
    enum = _certificate_schema()["properties"]["work_class"]["enum"]
    assert tuple(work_class_vocabulary()) == tuple(enum)
    assert enum[EXEMPT_WORK_CLASS_POSITION] == "E0"


def test_receipt_state_positions_match_the_o05_vocabulary() -> None:
    """The degraded receipt states are read positionally from O05's vocabulary."""
    vocabulary = receipt_state_vocabulary()
    assert vocabulary[RECEIPT_PARTIAL_POSITION] == "PARTIAL"
    assert vocabulary[RECEIPT_BLOCKED_POSITION] == "BLOCKED"
    assert vocabulary[RECEIPT_FAILED_POSITION] == "FAILED"


def test_the_gate_holds_no_canonical_completion_or_ceiling_literal() -> None:
    """The gate reads its tokens; it must not restate them as source literals.

    This mirrors the main-tree wire-literal discipline at the package boundary:
    the reconciliation and decision must derive every canonical enum token, so a
    bare occurrence of one in the module body is a drift risk.
    """
    import ast
    from pathlib import Path

    source = Path(engine.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }
    forbidden = (
        set(completion_state_vocabulary())
        | set(absence_ceiling_vocabulary())
        | set(novelty_ceiling_vocabulary())
        | set(work_class_vocabulary())
        | set(receipt_state_vocabulary())
    )
    assert not (literals & forbidden), literals & forbidden


def test_built_certificate_satisfies_the_canonical_schema() -> None:
    validate_artifact(CERTIFICATE_SCHEMA, f.certificate())


def test_exempt_class_certificate_satisfies_the_schema() -> None:
    from epistemic_foundry.retrieval.v4_o05 import canonical_lane_order

    pinned = f.snapshot()
    order = canonical_lane_order()
    e0_plan = f.plan(pinned, lane_dispositions={lane: f._sentinel() for lane in order})
    certificate = engine.build_search_completeness_certificate(
        plan=e0_plan,
        receipts=f.receipts(e0_plan, pinned),
        work_class="E0",
        required_lanes=[],
        subject_ref=f.SUBJECT_REF,
        generated_at=f.GENERATED_AT,
    )
    validate_artifact(CERTIFICATE_SCHEMA, certificate)
    assert certificate["completion_state"] == "NOT_REQUIRED"
    assert len(certificate["unsearched_lanes"]) == len(order)


def test_gate_receipt_carries_every_declared_field() -> None:
    receipt = engine.derive_search_integrity_admissibility(**f.gate_arguments())
    for field in (
        "gate",
        "decision",
        "admissible_for_promotion_review",
        "finding_code",
        "candidate_id",
        "subject_ref",
        "certificate_id",
        "certificate_hash",
        "completion_state",
        "novelty_claim_ceiling",
        "absence_claim_ceiling",
        "novelty_status",
        "gate_id",
        "receipt_hash",
    ):
        assert field in receipt, field
    assert receipt["gate"] == engine.GATE_NAME


def test_finding_codes_are_documented_and_nonempty() -> None:
    assert FINDING_CODES
    assert all(isinstance(v, str) and v for v in FINDING_CODES.values())


def test_required_typed_inputs_are_rejected() -> None:
    with pytest.raises(engine.SearchIntegrityRefused) as excinfo:
        engine.derive_search_integrity_admissibility(**f.gate_arguments(created_at=""))
    assert excinfo.value.code == "INPUT_INVALID"
