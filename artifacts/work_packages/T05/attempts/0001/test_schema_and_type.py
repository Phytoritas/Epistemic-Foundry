"""schema_and_type_check — the adapter reads its contracts, never restates them.

The verdict vocabulary comes from `backend-adapter-qualification.schema.json`,
the sandbox classes from S05's threat-model parser, the pipeline stages from the
reconciliation module that owns them, and the projected command set from the
sealed G05 declaration.  Every one of those assumptions is asserted here against
the declaring source, and the adapter modules are scanned for schema enum
literals directly, because holding another contract's vocabulary is exactly what
EF4-I22 forbids.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from epistemic_foundry.adapters.v4_t05 import (
    EVOLUTION_SURFACE_PATH,
    EXECUTION_FIELDS,
    FINDING_CODES,
    QUALIFICATION_ARTIFACT,
    AdapterGateError,
    command_projection,
    qualification_statuses,
)
from epistemic_foundry.adapters.v4_t05 import findings as findings_module
from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
)
from epistemic_foundry.security.v4_s05 import sandbox_classes
from epistemic_foundry.shinka_adapter.backend import (
    REQUIRED_CAPABILITY_TESTS,
    USABLE_QUALIFICATION_STATUSES,
)
from fixtures import binding, execution_qualification, imported_run

ROOT = Path(__file__).resolve().parents[5]
ADAPTER = ROOT / "src/epistemic_foundry/adapters/v4_t05"
ADAPTER_MODULES = (
    ADAPTER / "__init__.py",
    ADAPTER / "backend_adapter.py",
    ADAPTER / "findings.py",
    ADAPTER / "tool_surface.py",
)


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


def schema_enum_values() -> set[str]:
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


def test_the_verdict_vocabulary_comes_from_its_own_schema() -> None:
    document = default_registry().document(QUALIFICATION_ARTIFACT)

    assert qualification_statuses() == tuple(document["properties"]["status"]["enum"])
    assert qualification_statuses() == ("QUALIFIED", "CONDITIONAL", "REJECTED")


def test_the_usable_verdicts_are_the_first_two_positions() -> None:
    # The fixtures select a verdict positionally rather than by name.  That is
    # only sound while the schema declares the vocabulary strongest-first, so
    # the assumption is pinned against the adapter module that owns it.
    declared = qualification_statuses()

    assert set(declared[:2]) == set(USABLE_QUALIFICATION_STATUSES)
    assert declared[2] not in USABLE_QUALIFICATION_STATUSES


def test_the_capability_dimensions_come_from_the_shinka_adapter() -> None:
    document = default_registry().document(QUALIFICATION_ARTIFACT)
    required = document["properties"]["capability_tests"]["required"]

    assert set(REQUIRED_CAPABILITY_TESTS) == set(required)
    assert len(REQUIRED_CAPABILITY_TESTS) == 6


def test_the_pipeline_stages_come_from_the_reconciliation_module() -> None:
    assert STAGES == ("proposed", "generated", "evaluated", "persisted")
    assert TERMINAL_DISPOSITIONS == ("failed", "cancelled")


def test_the_executor_profile_is_a_declared_sandbox_class() -> None:
    record = execution_qualification()

    assert record["sandbox_profile"] in sandbox_classes()
    assert len(sandbox_classes()) == 5


def test_the_execution_fields_exist_on_a_real_s05_qualification() -> None:
    record = execution_qualification()

    assert set(EXECUTION_FIELDS) <= set(record)


def test_the_composed_qualification_validates_against_its_schema() -> None:
    record = binding()

    validate_artifact(QUALIFICATION_ARTIFACT, record["qualification"])


def test_the_imported_run_validates_against_its_schema() -> None:
    envelope = imported_run()

    validate_artifact("imported-run-record", envelope["imported_run"])


def test_the_projection_matches_the_sealed_g05_declaration() -> None:
    document = json.loads((ROOT / EVOLUTION_SURFACE_PATH).read_text(encoding="utf-8"))
    proposed = {
        command
        for skill in document["skills"]
        for command in skill["proposed_commands"]
    }
    available = {
        command
        for skill in document["skills"]
        for command in skill["available_commands"]
    }
    projection = command_projection()

    assert projection["proposed_commands"] == sorted(proposed)
    assert projection["available_commands"] == sorted(available)
    assert projection["surface_id"] == document["surface_id"]


def test_the_g05_finding_is_composed_rather_than_contradicted() -> None:
    # G05 found that the evolution CLI the specification proposes is not
    # projected by the tool surface.  T05 must carry that finding forward
    # exactly, not shrink it.
    projection = command_projection()

    assert len(projection["proposed_commands"]) == 25
    assert (
        projection["proposed_unavailable_commands"] == projection["proposed_commands"]
    )
    assert len(projection["available_commands"]) == 5


def test_the_adapter_holds_no_canonical_schema_vocabulary() -> None:
    vocabulary = schema_enum_values()
    held = {
        path.name: sorted(string_literals(path) & vocabulary)
        for path in ADAPTER_MODULES
        if string_literals(path) & vocabulary
    }

    assert held == {}, held


def test_the_scan_actually_finds_schema_vocabulary() -> None:
    # Guard against a vacuous pass: if the enum extraction returned nothing,
    # the scan above would pass while checking nothing at all.
    assert len(schema_enum_values()) > 100


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 10
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = AdapterGateError("EXECUTOR_UNPROJECTED", "message", {"a": 1})

    assert error.code == "EXECUTOR_UNPROJECTED"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(AdapterGateError) as caught:
        findings_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}
