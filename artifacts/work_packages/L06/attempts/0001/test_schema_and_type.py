"""schema_and_type_check — the gate reads its vocabularies, never restates them.

Memory classes come from the memory policy, protected entry classes from the
archive module, forget grounds and every plan-level decision from L05.  The
gate's source is scanned for canonical enum values because EF4-I22 is what
stops a second copy of a wire vocabulary from drifting, and a gate that
restated the class list would keep refusing against a partition the rest of the
runtime had already moved past.

The typed refusal surface is checked here too: a code that carries no reason,
or a reason too short to say why the refusal exists, is a finding nobody can
act on.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.epistemic_species_archive.archive import (
    EVICTABLE_ENTRY_CLASSES,
    PROTECTED_ENTRY_CLASSES,
)
from epistemic_foundry.memory.policy import MEMORY_CLASSES
from epistemic_foundry.memory.v4_l05 import (
    FORGET_GROUNDS,
    EvolutionMemoryError,
    entry_class_vocabulary,
)
from epistemic_foundry.memory.v4_l06 import (
    FINDING_CODES,
    HOLD_AUTHORITY_FIELDS,
    HOLD_PLACEMENT_FIELDS,
    TOMBSTONE_FACT_FIELDS,
    MemoryGateError,
)
from epistemic_foundry.memory.v4_l06 import gate as gate_module
from fixtures import REGULATED_ERASURE

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = ROOT / "src/epistemic_foundry/memory/v4_l06"
ENGINE = PACKAGE / "gate.py"


def wire_literal_gate() -> object:
    """The repository's own EF4-I22 scanner, loaded rather than restated.

    Re-implementing the enum walk here would give this package a second
    definition of the invariant it is supposed to satisfy, which is the exact
    drift EF4-I22 exists to prevent.
    """
    path = ROOT / "tests" / "test_wire_literal_discipline.py"
    spec = importlib.util.spec_from_file_location("ef4_i22_scanner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_this_package_alone_satisfies_the_repository_wire_literal_gate() -> None:
    """EF4-I22, narrowed to the two modules this package owns.

    The repository gate scans every shipped module at once, so a failure there
    can originate anywhere; this proves the L06 package is not the source.
    """
    scanner = wire_literal_gate()
    enum_values = scanner._schema_enum_values()  # type: ignore[attr-defined]
    held = {
        path.name: sorted(
            scanner._string_literals(path) & enum_values  # type: ignore[attr-defined]
        )
        for path in sorted(PACKAGE.glob("*.py"))
    }

    assert held == {"__init__.py": [], "gate.py": []}, held


def test_the_gate_holds_no_entry_class_literal() -> None:
    held = string_literals(ENGINE) & set(entry_class_vocabulary())

    assert held == set(), held


def test_the_gate_holds_no_memory_class_literal() -> None:
    document = default_registry().document("memory-policy")
    memory_classes = set(document["properties"]["allowed_classes"]["items"]["enum"])
    held = string_literals(ENGINE) & memory_classes

    assert held == set(), held


def test_the_gate_holds_no_external_sync_or_cross_workspace_literal() -> None:
    document = default_registry().document("memory-policy")
    rule = document["properties"]["class_rules"]["items"]["properties"]
    modes = set(document["properties"]["cross_workspace_retrieval"]["enum"])
    modes |= set(rule["external_sync"]["enum"])
    held = string_literals(ENGINE) & modes

    assert held == set(), held


def test_the_gate_holds_no_forget_ground_literal() -> None:
    held = string_literals(ENGINE) & set(FORGET_GROUNDS)

    assert held == set(), held


def test_the_memory_class_vocabulary_is_the_policys_own() -> None:
    document = default_registry().document("memory-policy")

    assert set(MEMORY_CLASSES) == set(
        document["properties"]["allowed_classes"]["items"]["enum"]
    )
    assert gate_module.MEMORY_CLASSES is MEMORY_CLASSES


def test_the_protected_partition_is_the_archives_own() -> None:
    assert gate_module.PROTECTED_ENTRY_CLASSES is PROTECTED_ENTRY_CLASSES
    assert PROTECTED_ENTRY_CLASSES | EVICTABLE_ENTRY_CLASSES == set(
        entry_class_vocabulary()
    )


def test_the_regulated_ground_this_gate_outranks_is_a_declared_ground() -> None:
    # The hold must outrank a regulated erasure specifically, so the fixture
    # naming that ground is pinned to L05's vocabulary rather than to a string
    # this package invented.
    assert REGULATED_ERASURE in FORGET_GROUNDS


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 17
    for code, reason in FINDING_CODES.items():
        assert code == code.upper(), code
        assert len(reason) > 50, code


def test_the_finding_codes_are_declared_once_and_sorted() -> None:
    assert list(FINDING_CODES) == sorted(FINDING_CODES)


def test_every_declared_code_is_actually_raised_somewhere() -> None:
    """A code nobody can reach is a refusal the gate claims but never makes.

    Each code appears once where it is declared, so a second occurrence is what
    proves some path actually raises or records it.
    """
    source = ENGINE.read_text(encoding="utf-8")
    unreachable = sorted(
        code for code in FINDING_CODES if source.count(f'"{code}"') < 2
    )

    assert unreachable == [], unreachable


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = MemoryGateError("LEGAL_HOLD_ACTIVE", "message", {"a": 1})

    assert error.code == "LEGAL_HOLD_ACTIVE"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(MemoryGateError) as caught:
        gate_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}


def test_the_gate_refusal_is_its_own_type_not_the_engines() -> None:
    # A gate finding is not an L05 finding: conflating them would let a caller
    # handling retention failures silently absorb a legal-hold refusal.
    assert not issubclass(MemoryGateError, EvolutionMemoryError)
    assert not issubclass(EvolutionMemoryError, MemoryGateError)
    assert issubclass(MemoryGateError, ValueError)


def test_the_hold_authority_shape_is_declared_once() -> None:
    # One list, used by both the placement and the release path, is what makes
    # "the same recorded authority shape" a property rather than a convention.
    assert HOLD_AUTHORITY_FIELDS == (
        "approved_by",
        "hold_authority_id",
        "legal_matter_id",
    )
    assert list(HOLD_AUTHORITY_FIELDS) == sorted(HOLD_AUTHORITY_FIELDS)


def test_the_placement_digest_covers_every_scope_field() -> None:
    assert HOLD_PLACEMENT_FIELDS == (
        "held_candidate_ids",
        "held_memory_classes",
        "hold_authority",
        "hold_id",
        "placed_at",
    )
    assert "hold_hash" not in HOLD_PLACEMENT_FIELDS


def test_the_tombstone_facts_are_the_ones_the_engine_keeps() -> None:
    # Every field L05 puts in a tombstone except its own finding code and
    # reason, which describe why the tombstone was made rather than what it
    # preserves about the entry.
    assert TOMBSTONE_FACT_FIELDS == (
        "archive_entry_id",
        "artifact_hash",
        "candidate_id",
        "entry_class",
        "generation",
        "lineage_id",
        "retention_reason",
    )
    assert list(TOMBSTONE_FACT_FIELDS) == sorted(TOMBSTONE_FACT_FIELDS)


def test_the_public_surface_is_exactly_what_the_package_exports() -> None:
    from epistemic_foundry.memory import v4_l06

    assert sorted(v4_l06.__all__) == list(v4_l06.__all__)
    for name in v4_l06.__all__:
        assert hasattr(v4_l06, name), name
