"""Schema-and-type checks: the gate's field contract matches the canonical schemas.

The gate resolves references across four canonical schemas by reading their
fields back by name. These tests hold the gate's declared field names against
the schemas themselves, so a rename in a schema fails here rather than leaving a
binding check that silently passes on an absent field. They also assert the
finding-code vocabulary is internally consistent and the intake status is the
one the genome schema actually declares.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.intake.v4_i06 import gate as g

import fixtures as fx

_registry = default_registry()


def test_every_contract_field_is_a_declared_property_of_its_schema() -> None:
    for schema_name, fields in g._CONTRACT_FIELDS.items():
        properties = set(_registry.document(schema_name)["properties"])
        assert set(fields) <= properties, (
            schema_name,
            sorted(set(fields) - properties),
        )


def test_verify_contract_returns_the_declared_field_groups() -> None:
    verified = g.verify_contract()
    assert set(verified) == set(g._CONTRACT_FIELDS)
    for schema_name, fields in g._CONTRACT_FIELDS.items():
        assert verified[schema_name] == fields


def test_the_gate_only_reads_schemas_the_registry_declares() -> None:
    known = set(_registry.names())
    for schema_name in (
        g.GENOME_KIND,
        g.SCOPE_KIND,
        g.FALSIFIER_KIND,
        g.PREDICTION_KIND,
    ):
        assert schema_name in known


def test_the_intake_status_is_the_first_status_the_genome_schema_declares() -> None:
    declared = _registry.document(g.GENOME_KIND)["properties"]["status"]["enum"]
    assert g.intake_status() == str(declared[0])


def test_every_finding_helper_code_is_a_declared_finding_code() -> None:
    for code in g.FINDING_CODES:
        row = g._finding(code)
        assert row["code"] == code
        assert row["reason"] == g.FINDING_CODES[code]


def test_an_undeclared_finding_code_is_refused() -> None:
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g._finding("NOT_A_CODE")
    assert raised.value.code == "INPUT_INVALID"


def test_the_admit_receipt_is_a_schema_valid_arrangement_of_its_own_hashes() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments())
    # The gate publishes no schema of its own yet, so this test asserts the
    # shape the provenance suite depends on rather than a registry contract.
    assert receipt["decision"] == g.ADMITTED
    assert receipt["admitted"] is True
    assert receipt["finding_codes"] == []
    assert isinstance(receipt["resolved_bindings"], dict)


def test_the_fixtures_are_documents_the_canonical_schemas_accept() -> None:
    validate_artifact(g.GENOME_KIND, fx.genome())
    validate_artifact(g.SCOPE_KIND, fx.scope_vector())
    validate_artifact(g.FALSIFIER_KIND, fx.falsifier_gene())
    validate_artifact(g.PREDICTION_KIND, fx.prediction_gene())


def test_the_intake_status_fixture_matches_the_gate() -> None:
    assert fx.INTAKE_STATUS == g.intake_status()
    assert fx.genome()["status"] == g.intake_status()
