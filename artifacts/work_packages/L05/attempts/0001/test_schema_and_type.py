"""schema_and_type_check — the engine reads its vocabulary, never restates it.

The entry classes come from the canonical archive schema, the protected and
evictable partition from the archive module that owns it, and export scope
from the memory policy's own enforcement point.  The engine's source is
scanned for canonical enum values because EF4-I22 is what stops a second copy
of a wire vocabulary from drifting.  A schema or partition change must break
this suite rather than leave an engine describing memory that no longer
exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.epistemic_species_archive.archive import (
    EVICTABLE_ENTRY_CLASSES,
    PROTECTED_ENTRY_CLASSES,
)
from epistemic_foundry.memory.v4_l05 import (
    CAPACITY_GROUND,
    EvolutionMemoryError,
    FINDING_CODES,
    FORGET_GROUNDS,
    FORGET_OUTCOMES,
    entry_class_vocabulary,
)
from epistemic_foundry.memory.v4_l05 import retention as retention_module

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/memory/v4_l05/retention.py"


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


def test_the_vocabulary_comes_from_the_declaring_schema() -> None:
    document = default_registry().document("epistemic-archive-entry")

    assert entry_class_vocabulary() == tuple(
        document["properties"]["entry_class"]["enum"]
    )
    assert len(entry_class_vocabulary()) == 8


def test_the_partition_comes_from_the_archive_module() -> None:
    vocabulary = set(entry_class_vocabulary())

    assert PROTECTED_ENTRY_CLASSES | EVICTABLE_ENTRY_CLASSES == vocabulary
    assert not PROTECTED_ENTRY_CLASSES & EVICTABLE_ENTRY_CLASSES


def test_the_engine_holds_no_entry_class_literal() -> None:
    held = string_literals(ENGINE) & set(entry_class_vocabulary())

    assert held == set(), held


def test_the_engine_holds_no_memory_class_literal() -> None:
    document = default_registry().document("memory-policy")
    memory_classes = set(document["properties"]["allowed_classes"]["items"]["enum"])
    held = string_literals(ENGINE) & memory_classes

    assert held == set(), held


def test_the_engine_holds_no_cross_workspace_mode_literal() -> None:
    document = default_registry().document("memory-policy")
    modes = set(document["properties"]["cross_workspace_retrieval"]["enum"])
    held = string_literals(ENGINE) & modes

    assert held == set(), held


def test_a_dropped_protected_class_is_vocabulary_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weakened = PROTECTED_ENTRY_CLASSES - {sorted(PROTECTED_ENTRY_CLASSES)[0]}
    monkeypatch.setattr(retention_module, "PROTECTED_ENTRY_CLASSES", weakened)

    with pytest.raises(EvolutionMemoryError) as caught:
        entry_class_vocabulary()
    assert caught.value.code == "VOCABULARY_DRIFT"
    assert caught.value.context["declared"]


def test_an_overlapping_partition_is_vocabulary_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlapping = EVICTABLE_ENTRY_CLASSES | {sorted(PROTECTED_ENTRY_CLASSES)[0]}
    monkeypatch.setattr(retention_module, "EVICTABLE_ENTRY_CLASSES", overlapping)

    with pytest.raises(EvolutionMemoryError) as caught:
        entry_class_vocabulary()
    assert caught.value.code == "VOCABULARY_DRIFT"
    assert caught.value.context["overlap"]


def test_the_forget_grounds_are_this_modules_own_vocabulary() -> None:
    assert FORGET_GROUNDS == (
        "capacity_pressure",
        "consent_withdrawal",
        "regulated_erasure",
        "workspace_purge",
    )
    assert CAPACITY_GROUND == FORGET_GROUNDS[0]
    assert FORGET_OUTCOMES == ("erased", "refused", "tombstoned")


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 10
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = EvolutionMemoryError("LINEAGE_BROKEN", "message", {"a": 1})

    assert error.code == "LINEAGE_BROKEN"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(EvolutionMemoryError) as caught:
        retention_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}
