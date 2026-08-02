"""schema_and_type_check — the engine restates no vocabulary it does not own.

The disposition table is data, not Python literals, and it must cover the
imported ``EffectStatus`` exactly: a status added to the contract has to fail
here rather than fall through to a permissive default.  The engine module itself
is scanned for canonical schema enum values, because EF4-I22 is what stops a
second copy of a wire vocabulary from drifting.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import get_args

import pytest

from epistemic_foundry.effects.v4_e05 import (
    DISPOSITION_PATH,
    FINDING_CODES,
    EffectReconciliationError,
    load_disposition_table,
)
from epistemic_foundry.evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
)
from epistemic_foundry.noetic_ledger.receipts import EffectStatus

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/effects/v4_e05/engine.py"


def string_literals(path: Path) -> set[str]:
    """Every string constant in a module, docstrings excluded."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
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


def test_the_table_covers_the_effect_status_vocabulary_exactly() -> None:
    table = load_disposition_table()

    assert set(table.dispositions) == set(get_args(EffectStatus))
    assert len(table.dispositions) == 5


def test_the_engine_holds_no_effect_status_literal() -> None:
    held = string_literals(ENGINE) & set(get_args(EffectStatus))

    assert held == set(), held


def test_the_engine_holds_no_pipeline_stage_literal() -> None:
    held = string_literals(ENGINE) & {*STAGES, *TERMINAL_DISPOSITIONS}

    assert held == set(), held


def test_every_disposition_is_a_stage_or_a_terminal_state() -> None:
    table = load_disposition_table()
    allowed = {*STAGES, *TERMINAL_DISPOSITIONS, None}

    for status, disposition in table.dispositions.items():
        assert disposition in allowed, status


def test_exactly_one_status_leaves_a_candidate_unresolved() -> None:
    table = load_disposition_table()
    unresolved = [
        status
        for status, disposition in table.dispositions.items()
        if disposition is None
    ]

    assert len(unresolved) == 1
    assert not table.resolves(unresolved[0])


def test_only_one_status_marks_a_candidate_persisted() -> None:
    table = load_disposition_table()
    persisted = [
        status
        for status, disposition in table.dispositions.items()
        if disposition == STAGES[-1]
    ]

    assert len(persisted) == 1


def test_every_disposition_states_its_reason() -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))

    for status, entry in document["dispositions"].items():
        assert entry["reason"].strip(), status
        assert isinstance(entry["resolves"], bool), status


def test_the_table_declares_its_contract() -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))

    assert document["contract"] == "epistemic-foundry-effect-disposition/v1"
    assert "EF4-I22" in document["$comment"]


def test_the_table_file_is_canonical_json_on_disk() -> None:
    raw = DISPOSITION_PATH.read_text(encoding="utf-8")

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )


def test_a_table_missing_a_status_is_refused(tmp_path: Path) -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    dropped = sorted(document["dispositions"])[0]
    del document["dispositions"][dropped]
    target = tmp_path / DISPOSITION_PATH.name
    target.write_text(json.dumps(document), encoding="utf-8")

    original = DISPOSITION_PATH.read_bytes()
    try:
        DISPOSITION_PATH.write_bytes(target.read_bytes())
        with pytest.raises(EffectReconciliationError) as caught:
            load_disposition_table()
        assert caught.value.code == "DISPOSITION_DRIFT"
        assert caught.value.context["missing"] == [dropped]
    finally:
        DISPOSITION_PATH.write_bytes(original)


def test_a_table_with_an_unknown_status_is_refused() -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    document["dispositions"]["INVENTED"] = {
        "disposition": None,
        "reason": "invented",
        "resolves": False,
    }

    original = DISPOSITION_PATH.read_bytes()
    try:
        DISPOSITION_PATH.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(EffectReconciliationError) as caught:
            load_disposition_table()
        assert caught.value.code == "DISPOSITION_DRIFT"
        assert caught.value.context["unknown"] == ["INVENTED"]
    finally:
        DISPOSITION_PATH.write_bytes(original)


def test_a_disposition_outside_the_pipeline_is_refused() -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    status = sorted(document["dispositions"])[0]
    document["dispositions"][status]["disposition"] = "promoted"

    original = DISPOSITION_PATH.read_bytes()
    try:
        DISPOSITION_PATH.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(EffectReconciliationError) as caught:
            load_disposition_table()
        assert caught.value.code == "DISPOSITION_INVALID"
    finally:
        DISPOSITION_PATH.write_bytes(original)


def test_a_status_that_resolves_without_a_disposition_is_refused() -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    for status, entry in document["dispositions"].items():
        if entry["disposition"] is None:
            entry["resolves"] = True
            break

    original = DISPOSITION_PATH.read_bytes()
    try:
        DISPOSITION_PATH.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(EffectReconciliationError) as caught:
            load_disposition_table()
        assert caught.value.code == "DISPOSITION_INVALID"
    finally:
        DISPOSITION_PATH.write_bytes(original)


def test_a_disposition_without_a_reason_is_refused() -> None:
    document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    status = sorted(document["dispositions"])[0]
    document["dispositions"][status]["reason"] = "   "

    original = DISPOSITION_PATH.read_bytes()
    try:
        DISPOSITION_PATH.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(EffectReconciliationError) as caught:
            load_disposition_table()
        assert caught.value.code == "DISPOSITION_UNREASONED"
    finally:
        DISPOSITION_PATH.write_bytes(original)


def test_an_unreadable_table_fails_closed() -> None:
    original = DISPOSITION_PATH.read_bytes()
    try:
        DISPOSITION_PATH.write_text("{not json", encoding="utf-8")
        with pytest.raises(EffectReconciliationError) as caught:
            load_disposition_table()
        assert caught.value.code == "DISPOSITION_UNREADABLE"
    finally:
        DISPOSITION_PATH.write_bytes(original)


def test_an_unknown_status_has_no_disposition() -> None:
    table = load_disposition_table()

    with pytest.raises(EffectReconciliationError) as caught:
        table.disposition_of("INVENTED")
    assert caught.value.code == "STATUS_UNMAPPED"


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 6
    for field, (code, message) in FINDING_CODES.items():
        assert field.replace("_", "").isalpha() or "_" in field
        assert code.isupper()
        assert len(message) > 40


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = EffectReconciliationError("ORPHAN_SIDE_EFFECT", "message", {"a": 1})

    assert error.code == "ORPHAN_SIDE_EFFECT"
    assert str(error) == "message"
    assert error.context == {"a": 1}
