"""schema_and_type_check — the gate reads its vocabularies, never restates them.

Candidate dispositions come from ``evolution_chamber.reconciliation``, the replay
equivalence vocabulary is reached only through ``release.replay``'s predicates,
the resume and its checkpoint checks from W05, the schedule verdict from N06 and
the retroactivity rule from ``governance.quarantine``.  The gate's source is
scanned for canonical enum values because EF4-I22 is what stops a second copy of a
wire vocabulary from drifting: an integration gate that restated a disposition or
an equivalence token would keep judging against a vocabulary the schema had moved
past.

The typed refusal surface and the composed-module code discipline are checked
here too — an upstream refusal must travel out under its own code, never a W06
paraphrase.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from epistemic_foundry.evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
)
from epistemic_foundry.recovery.v4_w06 import (
    FINDING_CODES,
    RecoveryGateError,
)
from epistemic_foundry.recovery.v4_w06 import gate as gate_module
from fixtures import ROOT

PACKAGE = ROOT / "src/epistemic_foundry/recovery/v4_w06"
ENGINE = PACKAGE / "gate.py"


def wire_literal_gate() -> object:
    """The repository's own EF4-I22 scanner, loaded rather than restated."""
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
    """EF4-I22, narrowed to the one module this package owns."""
    scanner = wire_literal_gate()
    enum_values = scanner._schema_enum_values()  # type: ignore[attr-defined]
    held = {
        path.name: sorted(
            scanner._string_literals(path) & enum_values  # type: ignore[attr-defined]
        )
        for path in sorted(PACKAGE.glob("*.py"))
    }

    assert held == {"__init__.py": [], "gate.py": []}, held


def test_the_gate_holds_no_disposition_literal() -> None:
    # ``proposed``, ``failed`` and ``cancelled`` are canonical enum values; the
    # gate composes them through the reconciliation owner and never restates one.
    held = string_literals(ENGINE) & (set(STAGES) | set(TERMINAL_DISPOSITIONS))

    assert held == set(), held


def test_the_gate_names_no_replay_equivalence_token() -> None:
    # The equivalence vocabulary lives in ``release.replay``; the gate reaches it
    # only through ``replay_reproduced`` and ``require_comparable``, so none of
    # its tokens appear as literals here.
    from epistemic_foundry.contracts import default_registry

    document = default_registry().document("replay-report")
    equivalence = set(document["properties"]["event_equivalence"]["enum"])
    modes = set(document["properties"]["mode"]["enum"])
    held = string_literals(ENGINE) & (equivalence | modes)

    assert held == set(), held


def test_the_final_states_are_the_reconciliation_modules_own() -> None:
    # persisted is the last pipeline stage; failed and cancelled are the terminal
    # dispositions. All three are read from the declaring module.
    assert gate_module._FINAL_STATES == (STAGES[-1], *TERMINAL_DISPOSITIONS)
    assert len(gate_module._FINAL_STATES) == 3


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 5
    for code, reason in FINDING_CODES.items():
        assert code == code.upper(), code
        assert len(reason) > 50, code


def test_the_finding_codes_are_declared_once_and_sorted() -> None:
    assert list(FINDING_CODES) == sorted(FINDING_CODES)


def test_every_declared_code_is_actually_raised_somewhere() -> None:
    """A code nobody can reach is a refusal the gate claims but never makes."""
    source = ENGINE.read_text(encoding="utf-8")
    unreachable = sorted(
        code for code in FINDING_CODES if source.count(f'"{code}"') < 2
    )

    assert unreachable == [], unreachable


def test_no_composed_modules_finding_code_is_restated_here() -> None:
    """Upstream refusals travel out unwrapped, so their codes must not be copied."""
    from epistemic_foundry.evolution.v4_f05 import FINDING_CODES as MACHINE_CODES
    from epistemic_foundry.recovery.v4_w05 import FINDING_CODES as W05_CODES
    from epistemic_foundry.scheduler.v4_n06 import FINDING_CODES as N06_CODES

    machine = {code for code, _ in MACHINE_CODES.values()}
    n06 = {code for code, _ in N06_CODES.values()}
    composed = machine | n06 | set(W05_CODES)

    # W06 reuses only the neutral INPUT_INVALID shape guard; every other code is
    # its own and no composed code is restated as a literal.
    assert (set(FINDING_CODES) & composed) <= {"INPUT_INVALID"}
    assert string_literals(ENGINE) & (composed - {"INPUT_INVALID"}) == set()


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = RecoveryGateError("RECOVERY_CANDIDATE_LOST", "message", {"a": 1})

    assert error.code == "RECOVERY_CANDIDATE_LOST"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(RecoveryGateError) as caught:
        gate_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}


def test_the_gate_refusal_is_its_own_type_not_a_composed_one() -> None:
    from epistemic_foundry.evolution_chamber.reconciliation import ReconciliationFailed
    from epistemic_foundry.governance.quarantine import QuarantineViolation
    from epistemic_foundry.release.replay import ReplayVerificationFailed
    from epistemic_foundry.scheduler.v4_n06 import IntegrationError

    assert issubclass(RecoveryGateError, ValueError)
    assert not issubclass(RecoveryGateError, ReconciliationFailed)
    assert not issubclass(RecoveryGateError, ReplayVerificationFailed)
    assert not issubclass(RecoveryGateError, QuarantineViolation)
    assert not issubclass(RecoveryGateError, IntegrationError)


def test_the_public_surface_is_exactly_what_the_package_exports() -> None:
    from epistemic_foundry.recovery import v4_w06

    assert sorted(v4_w06.__all__) == list(v4_w06.__all__)
    for name in v4_w06.__all__:
        assert hasattr(v4_w06, name), name
