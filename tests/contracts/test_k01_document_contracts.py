from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from epistemic_foundry.contracts import ContractViolation, validate_artifact
from epistemic_foundry.ingest.registry import (
    DocumentRegistryError,
    compute_registration_hash,
    compute_request_hash,
    verify_registration_payload,
    verify_request_payload,
)
from epistemic_foundry.ingest.registry.hash import (
    REGISTRATION_HASH_FIELDS,
    REQUEST_HASH_FIELDS,
)
from packages.contracts.codegen.generate import load_contracts


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "k01"


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_canonical_inventory_has_127_schemas_and_matching_examples() -> None:
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    examples = sorted((ROOT / "examples").glob("sample_*.json"))
    assert len(schemas) == 127
    assert len(examples) == 127
    contracts, schema_bundle_hash, example_bundle_hash = load_contracts(ROOT)
    assert len(contracts) == 127
    assert len({contract.schema_file for contract in contracts}) == 127
    assert len({contract.example_file for contract in contracts}) == 127
    assert schema_bundle_hash.startswith("sha256:")
    assert example_bundle_hash.startswith("sha256:")


@pytest.mark.parametrize(
    ("name", "fixture_name"),
    [
        ("document-registration-request", "document-registration-request.valid.json"),
        ("document-registration", "document-registration.valid.json"),
    ],
)
def test_k01_fixture_equals_canonical_example_and_validates(
    name: str, fixture_name: str
) -> None:
    fixture = load(FIXTURES / fixture_name)
    example = load(ROOT / "examples" / f"sample_{name}.json")
    schema = load(ROOT / "schemas" / f"{name}.schema.json")

    assert fixture == example
    Draft202012Validator.check_schema(schema)
    validate_artifact(name, fixture)


def test_hash_preimage_tables_exactly_match_schema_metadata() -> None:
    request_schema = load(ROOT / "schemas/document-registration-request.schema.json")
    registration_schema = load(ROOT / "schemas/document-registration.schema.json")

    assert tuple(request_schema["x-canonical-hash"]["preimage_fields"]) == REQUEST_HASH_FIELDS
    assert tuple(registration_schema["x-canonical-hash"]["preimage_fields"]) == (
        "schema_id",
        *REGISTRATION_HASH_FIELDS[1:],
    )


def test_volatile_request_and_registration_fields_do_not_change_business_hashes() -> None:
    request = load(FIXTURES / "document-registration-request.valid.json")
    request_mutation = copy.deepcopy(request)
    request_mutation["requested_at"] = "2030-01-01T00:00:00Z"
    request_mutation["request_id"] = "DREQ-" + "0" * 64
    assert compute_request_hash(request_mutation) == request["request_hash"]

    registration = load(FIXTURES / "document-registration.valid.json")
    registration_mutation = copy.deepcopy(registration)
    registration_mutation["registered_at"] = "2030-01-01T00:00:00Z"
    registration_mutation["ledger_event_id"] = "EV-OTHER-K01"
    registration_mutation["source_effect_receipt_id"] = "EFF-OTHER-K01"
    assert compute_registration_hash(registration_mutation) == registration[
        "registration_hash"
    ]


def test_invalid_fixture_is_rejected_by_schema_and_semantic_validator() -> None:
    invalid = load(FIXTURES / "document-registration.invalid.json")
    with pytest.raises(ContractViolation):
        validate_artifact("document-registration", invalid)
    with pytest.raises(DocumentRegistryError) as caught:
        verify_registration_payload(invalid)
    assert caught.value.code == "DOCUMENT_CONTRACT_INVALID"


def test_canonical_examples_pass_hash_and_identity_recomputation() -> None:
    request = load(ROOT / "examples/sample_document-registration-request.json")
    registration = load(ROOT / "examples/sample_document-registration.json")

    assert verify_request_payload(request) == request
    assert verify_registration_payload(registration) == registration
    assert compute_request_hash(request) == request["request_hash"]
    assert compute_registration_hash(registration) == registration["registration_hash"]
