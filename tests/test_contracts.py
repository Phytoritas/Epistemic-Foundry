"""Canonical-schema registry and fail-closed validation."""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    repo_root,
    validate_artifact,
)
from epistemic_foundry.contracts.validation import artifact_errors

EXPECTED_SCHEMA_COUNT = 127  # acceptance_matrix.yaml: canonical_schema_count


def test_registry_loads_every_canonical_schema() -> None:
    assert len(default_registry().names()) == EXPECTED_SCHEMA_COUNT


def test_unknown_schema_fails_closed() -> None:
    with pytest.raises(SchemaNotFound):
        default_registry().document("no-such-contract")


def test_shipped_examples_validate_against_their_schemas() -> None:
    """Every `examples/sample_<name>.json` must satisfy `<name>.schema.json`.

    This is the cross-check that keeps the runtime honest: it proves the loader
    resolves local `$ref`s and that the bundle's own examples are conformant,
    rather than asserting a hand-written fixture the code also produced.
    """
    registry = default_registry()
    known = set(registry.names())
    checked = 0
    failures: list[str] = []
    for path in sorted((repo_root() / "examples").glob("sample_*.json")):
        name = path.name[len("sample_") : -len(".json")]
        if name not in known:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        errors = artifact_errors(name, payload)
        checked += 1
        if errors:
            failures.append(f"{name}: {errors[0]}")
    assert checked >= 100, f"expected the example corpus to be scanned, checked={checked}"
    assert not failures, f"{len(failures)} example(s) violate their schema: {failures[:5]}"


def test_validation_reports_every_error_not_just_the_first() -> None:
    payload = {"session_id": "FS-001"}  # many required fields absent
    errors = artifact_errors("forge-session-state", payload)
    assert len(errors) > 1


def test_invalid_enum_is_rejected() -> None:
    sample = json.loads(
        (repo_root() / "examples" / "sample_forge-session-state.json").read_text(encoding="utf-8")
    )
    sample["phase"] = "NOT_A_PHASE"
    with pytest.raises(ContractViolation) as excinfo:
        validate_artifact("forge-session-state", sample)
    assert "phase" in str(excinfo.value)
