"""schema_and_type_check — the workflow reads its vocabularies, never restates them.

Checkpoint components and the stop-reason classification come from
``evolution_chamber.checkpoint``, run legality from F05, drift from the verifier
firewall, and the retroactivity rule from ``governance.quarantine``.  The
workflow's source is scanned for canonical enum values because EF4-I22 is what
stops a second copy of a wire vocabulary from drifting: a workflow that restated
the stop list would keep certifying against a vocabulary the schema had already
moved past.

The typed refusal surface is checked here too, along with the one thing this
package does own — the reassessment markers.  No canonical schema declares a
reassessment status, so those two strings are package-local by necessity, and
the test that matters is that they are deliberately *not* schema enum values: a
comparison the evaluator never re-ran is not in the schema's invalidated state.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evolution.v4_f05 import (
    EvolveStateError,
    load_graph,
    stop_reasons,
)
from epistemic_foundry.evolution_chamber.checkpoint import (
    ADVERSE_STOPS,
    CHECKPOINT_COMPONENTS,
    ORDERLY_STOPS,
)
from epistemic_foundry.governance.quarantine import (
    DEFECT_CLASSES,
    QuarantineViolation,
)
from epistemic_foundry.recovery.v4_w05 import (
    COMPARISON_BINDING_FIELDS,
    COMPARISON_POTENTIALLY_INVALID,
    COMPARISON_UNAFFECTED,
    FINDING_CODES,
    RecoveryWorkflowError,
)
from epistemic_foundry.recovery.v4_w05 import workflow as workflow_module
from epistemic_foundry.verifier_firewall.firewall import EvaluatorDrift
from fixtures import LOOP_ENTRY, LOOP_EXIT, ROOT

PACKAGE = ROOT / "src/epistemic_foundry/recovery/v4_w05"
ENGINE = PACKAGE / "workflow.py"


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
    can originate anywhere; this proves the W05 package is not the source.
    """
    scanner = wire_literal_gate()
    enum_values = scanner._schema_enum_values()  # type: ignore[attr-defined]
    held = {
        path.name: sorted(
            scanner._string_literals(path) & enum_values  # type: ignore[attr-defined]
        )
        for path in sorted(PACKAGE.glob("*.py"))
    }

    assert held == {"__init__.py": [], "workflow.py": []}, held


def test_the_workflow_holds_no_stop_reason_literal() -> None:
    held = string_literals(ENGINE) & (ORDERLY_STOPS | ADVERSE_STOPS)

    assert held == set(), held


def test_the_workflow_holds_no_checkpoint_component_literal() -> None:
    # Component names are the checkpoint module's declaration; a second copy
    # here would keep accepting a resume point after the seven changed.
    held = string_literals(ENGINE) & set(CHECKPOINT_COMPONENTS)

    assert held == set(), held


def test_the_workflow_holds_no_defect_class_or_proposal_status_literal() -> None:
    document = default_registry().document("evaluator-mutation-proposal")
    statuses = set(document["properties"]["status"]["enum"])
    held = string_literals(ENGINE) & (set(DEFECT_CLASSES) | statuses)

    assert held == set(), held


def test_the_stop_vocabulary_is_the_checkpoint_modules_own() -> None:
    # F05 reads the classification from the checkpoint module; the workflow
    # reads it from F05. One declaration, two hops, no restatement.
    assert set(stop_reasons()) == set(ORDERLY_STOPS | ADVERSE_STOPS)
    document = default_registry().document("evolution-stop-certificate")
    assert set(stop_reasons()) == set(document["properties"]["stop_reason"]["enum"])


def test_the_seven_components_are_the_ones_the_checkpoint_module_declares() -> None:
    document = default_registry().document("evolution-checkpoint")
    required = set(document["required"])

    assert len(CHECKPOINT_COMPONENTS) == 7
    assert set(CHECKPOINT_COMPONENTS) <= required


def test_the_loop_endpoints_the_fixtures_name_are_declared_workflow_nodes() -> None:
    # The resume edge is expressed between the loop contract's endpoints, so a
    # fixture naming a node the workflow dropped would test a graph that no
    # longer exists.
    graph = load_graph(ROOT)

    assert LOOP_EXIT in graph.dependencies
    assert LOOP_ENTRY in graph.dependencies


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 12
    for code, reason in FINDING_CODES.items():
        assert code == code.upper(), code
        assert len(reason) > 50, code


def test_the_finding_codes_are_declared_once_and_sorted() -> None:
    assert list(FINDING_CODES) == sorted(FINDING_CODES)


def test_every_declared_code_is_actually_raised_somewhere() -> None:
    """A code nobody can reach is a refusal the workflow claims but never makes.

    Each code appears once where it is declared, so a second occurrence is what
    proves some path actually raises it.
    """
    source = ENGINE.read_text(encoding="utf-8")
    unreachable = sorted(
        code for code in FINDING_CODES if source.count(f'"{code}"') < 2
    )

    assert unreachable == [], unreachable


def test_no_composed_modules_finding_code_is_restated_here() -> None:
    """Upstream refusals travel out unwrapped, so their codes must not be copied.

    A W05 paraphrase of ``CHECKPOINT_INCOMPLETE`` would tell a caller that this
    module decided resume legality, which is exactly the judgment it delegates.
    """
    from epistemic_foundry.evolution.v4_f05 import FINDING_CODES as MACHINE_CODES

    machine = {code for code, _ in MACHINE_CODES.values()}

    assert machine & set(FINDING_CODES) == set()
    assert string_literals(ENGINE) & machine == set()


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = RecoveryWorkflowError("DRIFT_ABSENT", "message", {"a": 1})

    assert error.code == "DRIFT_ABSENT"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        workflow_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}


def test_the_workflow_refusal_is_its_own_type_not_a_composed_one() -> None:
    # Conflating them would let a caller handling resume-legality failures
    # silently absorb a drift refusal, or the reverse.
    assert not issubclass(RecoveryWorkflowError, EvolveStateError)
    assert not issubclass(RecoveryWorkflowError, QuarantineViolation)
    assert not issubclass(RecoveryWorkflowError, EvaluatorDrift)
    assert issubclass(RecoveryWorkflowError, ValueError)


def test_the_reassessment_markers_are_not_canonical_schema_vocabulary() -> None:
    """The mark is package-local on purpose.

    No schema declares a reassessment status, and borrowing the invalidated
    state from an unrelated enum would claim an evaluator verdict this workflow
    never obtained.
    """
    scanner = wire_literal_gate()
    enum_values = scanner._schema_enum_values()  # type: ignore[attr-defined]

    assert COMPARISON_POTENTIALLY_INVALID not in enum_values
    assert COMPARISON_UNAFFECTED not in enum_values
    assert COMPARISON_POTENTIALLY_INVALID != COMPARISON_UNAFFECTED


def test_the_comparison_binding_fields_are_declared_once_and_sorted() -> None:
    assert COMPARISON_BINDING_FIELDS == ("comparison_id", "evaluator_bundle_id")
    assert list(COMPARISON_BINDING_FIELDS) == sorted(COMPARISON_BINDING_FIELDS)


def test_the_public_surface_is_exactly_what_the_package_exports() -> None:
    from epistemic_foundry.recovery import v4_w05

    assert sorted(v4_w05.__all__) == list(v4_w05.__all__)
    for name in v4_w05.__all__:
        assert hasattr(v4_w05, name), name
