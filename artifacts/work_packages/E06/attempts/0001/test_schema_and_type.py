"""schema_and_type_check — the gate's declared shapes and borrowed vocabulary.

Two things are checked here that no behavioural test can reach.  First, the
refusal vocabulary: a code that names no reason, a reason too short to explain
anything, or a code raisable without being declared would let a refusal escape
as an unexplained string.  Second, the vocabulary the gate does *not* own: the
effect statuses and their landed projection are imported from the module that
declares them, and this file proves the gate reads that projection rather than
restating it — including the EF4-I22 scan the repository runs over every
shipped module, applied here to the one module this package adds.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from epistemic_foundry.application.mcp_mutating.ports import (
    EFFECT_STATUSES,
    STATUS_PROJECTION,
    UNRESOLVED_STATUS,
)
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.effects import v4_e06
from epistemic_foundry.effects.v4_e06 import gate as gate_module
from epistemic_foundry.effects.v4_e06 import (
    BEGIN,
    COMMIT,
    EFFECT,
    FINDING_CODES,
    LANE_PHASES,
    ConcurrentEffectError,
    normalize_actions,
    settle_interleaving,
)
from fixtures import (
    INITIAL_REVISIONS,
    TARGET_A,
    action,
    disjoint_actions,
    effect_receipt,
    lane,
    serial,
)

GATE_SOURCE = Path(gate_module.__file__)
#: Values too generic to attribute to a wire contract; the repository's own
#: EF4-I22 scan skips these, and skipping a different set here would make this
#: file agree or disagree with the gate for the wrong reason.
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
        body = getattr(node, "body", [])
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
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


def test_the_gate_holds_no_canonical_schema_vocabulary() -> None:
    """EF4-I22, applied to the one runtime module this package adds."""
    held = sorted(_string_literals(GATE_SOURCE) & _schema_enum_values())

    assert held == [], f"the gate restates canonical wire vocabulary: {held}"


def test_the_scan_is_not_vacuous() -> None:
    """A silent failure of either half would make the check above meaningless."""
    assert len(_schema_enum_values()) > 100
    assert "IDEMPOTENCY_KEY_REUSED" in _string_literals(GATE_SOURCE)


def test_every_finding_code_is_upper_snake_case() -> None:
    for code in FINDING_CODES:
        assert re.fullmatch(r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)*", code), code


def test_every_finding_reason_explains_itself() -> None:
    """A reason short enough to be a label is a label, not an explanation."""
    for code, reason in FINDING_CODES.items():
        assert len(reason) > 50, code
        assert reason == reason.strip(), code


def test_finding_reasons_are_distinct() -> None:
    """Two codes sharing a reason means one of them does not exist."""
    reasons = list(FINDING_CODES.values())

    assert len(set(reasons)) == len(reasons)


def test_every_declared_code_has_a_site_that_raises_it() -> None:
    """A code declared and never used is a refusal the gate cannot actually make.

    Counted by occurrence rather than by call graph: the declaration in
    `FINDING_CODES` is one, so a code the gate never names anywhere else stops
    at one and is a promise with nothing behind it.
    """
    source = GATE_SOURCE.read_text(encoding="utf-8")
    unused = sorted(code for code in FINDING_CODES if source.count(f'"{code}"') < 2)

    assert unused == []


def test_an_undeclared_code_cannot_be_raised() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        gate_module._fail("NOT_A_DECLARED_CODE", "boom")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["code"] == "NOT_A_DECLARED_CODE"


def test_an_undeclared_code_cannot_be_recorded_as_a_refusal() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        gate_module._refusal("NOT_A_DECLARED_CODE", ("A", "B"))

    assert caught.value.code == "INPUT_INVALID"


def test_the_error_carries_code_message_and_context() -> None:
    error = ConcurrentEffectError("LOST_UPDATE", "a message", {"target_ref": TARGET_A})

    assert error.code == "LOST_UPDATE"
    assert str(error) == "a message"
    assert error.context == {"target_ref": TARGET_A}


def test_the_error_context_is_a_copy() -> None:
    supplied = {"target_ref": TARGET_A}
    error = ConcurrentEffectError("LOST_UPDATE", "a message", supplied)
    error.context["target_ref"] = "elsewhere"

    assert supplied == {"target_ref": TARGET_A}


def test_the_lane_phases_are_three_ordered_distinct_names() -> None:
    assert LANE_PHASES == (BEGIN, EFFECT, COMMIT)
    assert len(set(LANE_PHASES)) == 3


def test_the_package_exports_exactly_what_it_declares() -> None:
    """A name in `__all__` that does not resolve is an export in name only."""
    assert len(set(v4_e06.__all__)) == len(v4_e06.__all__)
    for name in v4_e06.__all__:
        assert getattr(v4_e06, name) is getattr(gate_module, name), name


def test_the_package_re_exports_nothing_it_did_not_write() -> None:
    """E05's names stay in E05; a second import site would drift from it."""
    assert "reconcile_effect_ledger" not in v4_e06.__all__
    assert "require_effect_reconciliation" not in v4_e06.__all__


def test_the_gate_accepts_every_declared_effect_status() -> None:
    """A status the contract declares must be projectable, not merely tolerated."""
    for index, status in enumerate(EFFECT_STATUSES):
        receipt = effect_receipt(f"INT-{index}", f"IDEM-{index}", status)
        normalized = normalize_actions(
            [
                action(
                    f"ACT-{index}",
                    candidate_id=f"CAND-{index}",
                    idempotency_key=f"IDEM-{index}",
                    receipt=receipt,
                )
            ]
        )

        landed, _ = STATUS_PROJECTION[status]
        assert normalized[f"ACT-{index}"]["landed"] is landed


def test_the_unobserved_status_is_the_only_tri_state_one() -> None:
    """`landed` is None exactly when the runtime could not observe the outcome."""
    unobserved = [
        status for status in EFFECT_STATUSES if STATUS_PROJECTION[status][0] is None
    ]

    assert unobserved == [UNRESOLVED_STATUS]


def test_an_undeclared_status_is_refused_rather_than_projected() -> None:
    receipt = dict(effect_receipt("INT-1", "IDEM-1"))
    receipt["status"] = "PROBABLY_FINE"

    with pytest.raises(ConcurrentEffectError) as caught:
        normalize_actions(
            [
                action(
                    "ACT-1",
                    candidate_id="CAND-1",
                    idempotency_key="IDEM-1",
                    receipt=receipt,
                )
            ]
        )

    assert caught.value.code == "STATUS_UNDECLARED"
    assert caught.value.context["declared"] == list(EFFECT_STATUSES)


def test_a_normalized_action_carries_the_fields_the_replay_reads() -> None:
    normalized = normalize_actions(disjoint_actions())

    assert sorted(normalized["ACT-1"]) == [
        "action_id",
        "base_revision",
        "candidate_id",
        "effect_receipt",
        "effect_receipt_id",
        "idempotency_key",
        "landed",
        "new_revision",
        "payload_fingerprint",
        "status",
        "target_ref",
    ]


def test_a_settlement_carries_the_shape_the_agreement_check_reads() -> None:
    settlement = settle_interleaving(
        actions=disjoint_actions(),
        events=serial("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
        interleaving_id="IL-1",
    )

    assert sorted(settlement) == [
        "admitted",
        "interleaving_id",
        "ledger",
        "ledger_hash",
        "notices",
        "refusals",
        "settlement_hash",
    ]


def test_a_settled_ledger_is_keyed_by_idempotency_key() -> None:
    """The ledger records effects, and an effect is what a key deduplicated."""
    settlement = settle_interleaving(
        actions=disjoint_actions(),
        events=serial("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
        interleaving_id="IL-1",
    )

    assert sorted(settlement["ledger"]) == [
        "bindings",
        "committed_keys",
        "revisions",
        "unlanded_keys",
        "unobserved_keys",
    ]
    assert sorted(settlement["ledger"]["bindings"]) == ["IDEM-1", "IDEM-2"]


def test_every_bound_key_falls_in_exactly_one_disposition() -> None:
    receipt = effect_receipt("INT-1", "IDEM-1", UNRESOLVED_STATUS)
    settlement = settle_interleaving(
        actions=[
            action(
                "ACT-1",
                candidate_id="CAND-1",
                idempotency_key="IDEM-1",
                receipt=receipt,
            )
        ],
        events=lane("L1", "ACT-1"),
        initial_revisions=INITIAL_REVISIONS,
        interleaving_id="IL-1",
    )
    ledger = settlement["ledger"]
    dispositions = (
        set(ledger["committed_keys"])
        | set(ledger["unlanded_keys"])
        | set(ledger["unobserved_keys"])
    )

    assert dispositions == set(ledger["bindings"])
    assert ledger["unobserved_keys"] == ["IDEM-1"]
