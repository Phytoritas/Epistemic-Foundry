"""Schema and type checks for the R06 crossover safety gate.

The gate binds to the canonical schemas rather than to a private copy of their
vocabularies, so these tests assert that every vocabulary the gate reads —
genome reference fields, the identification ladder, the scope scalar fields and
the four crossover axes — is the one the canonical schema declares, and that the
gate refuses when a schema drops a field it depends on.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.reasoning.v4_r06 import gate
from epistemic_foundry.reasoning.v4_r06.gate import (
    COMPATIBILITY_AXES,
    FINDING_CODES,
    CrossoverSafetyRefused,
)
from fixtures import gate_arguments

_registry = default_registry()


def test_every_schema_the_gate_reads_is_a_registered_canonical_contract() -> None:
    names = set(_registry.names())
    for kind in (
        gate.MECHANISM_KIND,
        gate.SCOPE_KIND,
        gate.MEASUREMENT_REPORT_KIND,
        gate.CROSSOVER_REPORT_KIND,
    ):
        assert kind in names


def test_the_genome_reference_fields_are_properties_of_the_genome_schema() -> None:
    properties = gate.engine.genome_properties(gate.GENOME_KIND)
    for field in gate.genome_reference_fields():
        assert field in properties


def test_the_identification_vocabulary_is_the_mechanism_schemas_own() -> None:
    enum = _registry.document(gate.MECHANISM_KIND)["properties"][
        "identification_status"
    ]["enum"]
    assert gate.identification_statuses() == tuple(str(value) for value in enum)
    assert gate.IDENTIFIED in gate.identification_statuses()
    assert gate.NOT_ASSESSED in gate.identification_statuses()


def test_the_scope_scalar_fields_are_the_scope_schemas_string_null_fields() -> None:
    properties = _registry.document(gate.SCOPE_KIND)["properties"]
    expected = tuple(
        sorted(
            field
            for field, spec in properties.items()
            if spec.get("type") == ["string", "null"]
        )
    )
    assert gate.scope_scalar_fields() == expected


def test_the_four_axes_are_the_crossover_reports_own_axis_properties() -> None:
    properties = _registry.document(gate.CROSSOVER_REPORT_KIND)["properties"]
    for axis in COMPATIBILITY_AXES:
        assert axis in properties
        assert gate.COMPATIBLE_TOKEN in properties[axis]["enum"]


def test_the_finding_codes_are_documented_and_nonempty() -> None:
    assert FINDING_CODES
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(reason, str) and reason.strip()


def test_a_compatible_crossover_yields_a_typed_allow_receipt() -> None:
    receipt = gate.evaluate_crossover_safety(**gate_arguments())
    assert receipt["decision"] == "ALLOW"
    assert receipt["finding_code"] is None
    assert receipt["gate"] == "crossover-safety"
    assert set(receipt["derived_axes"]) == set(COMPATIBILITY_AXES)
    assert receipt["gate_id"].startswith("XSG-")
    assert receipt["receipt_hash"].startswith("sha256:")


def test_the_gate_refuses_when_the_genome_schema_drops_a_reference_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate.engine, "genome_properties", lambda kind: {})
    with pytest.raises(CrossoverSafetyRefused) as caught:
        gate.derive_crossover_safety(**gate_arguments())
    assert caught.value.code == "GENOME_FIELD_UNDECLARED_BY_SCHEMA"
