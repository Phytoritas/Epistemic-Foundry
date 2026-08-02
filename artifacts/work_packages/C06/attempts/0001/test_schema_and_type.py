"""schema_and_type_check — the bundle is valid, resolvable and literal-free.

The compatibility binding must be a valid Draft 2020-12 schema whose references
resolve to canonical ``$id``s, and it must declare no enum, const, pattern or
format of its own — the canonical contracts stay the single declaring source
(EF4-I22).  The integration index and parity record keep exact field sets with
recomputable hashes, and the parity record must account for exactly the C05
membership as the sealed index recorded it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from c06_integration_gate import (
    BINDING_NAME,
    C05_INDEX_PATH,
    COMPATIBILITY_MEMBERS,
    COMPATIBILITY_REQUIRED,
    FORBIDDEN_COMPOSITE_KEYWORDS,
    INDEX_NAME,
    OUTPUT_DIR,
    PARITY_NAME,
    PROJECTION_MANIFESTS,
    _all_members,
    _hash_excluding,
    _INDEX_FIELDS,
    _PARITY_FIELDS,
    _registry,
    family_members,
    mutable_search_space,
)

ROOT = Path(__file__).resolve().parents[5]
BUNDLE = ROOT / OUTPUT_DIR
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def load(name: str) -> dict:
    return json.loads((BUNDLE / name).read_text(encoding="utf-8"))


def test_the_binding_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(load(BINDING_NAME))


def test_every_binding_reference_resolves_to_a_canonical_id() -> None:
    resolver = _registry(ROOT).resolver()
    refs = re.findall(r'"\$ref": "([^"]+)"', json.dumps(load(BINDING_NAME)))

    assert len(refs) == len(COMPATIBILITY_MEMBERS)
    for ref in refs:
        assert resolver.lookup(ref).contents["$id"] == ref


def test_the_binding_declares_no_local_vocabulary() -> None:
    text = json.dumps(load(BINDING_NAME))

    for keyword in FORBIDDEN_COMPOSITE_KEYWORDS:
        assert f'"{keyword}":' not in text, keyword


def test_a_migration_cannot_be_recorded_without_its_matrix() -> None:
    binding = load(BINDING_NAME)

    assert binding["required"] == sorted(COMPATIBILITY_REQUIRED)
    assert "migration" in binding["required"]
    assert "compatibility_matrix" in binding["required"]
    assert binding["additionalProperties"] is False


def test_the_binding_id_is_namespaced_to_this_package() -> None:
    assert load(BINDING_NAME)["$id"] == (
        f"https://epistemic-foundry.local/schemas/v4_c06/{BINDING_NAME}"
    )


def test_the_index_keeps_its_exact_field_set() -> None:
    assert set(load(INDEX_NAME)) == set(_INDEX_FIELDS)


def test_the_parity_record_keeps_its_exact_field_set() -> None:
    assert set(load(PARITY_NAME)) == set(_PARITY_FIELDS)


def test_both_hashes_are_recomputable() -> None:
    for name, field in ((INDEX_NAME, "index_hash"), (PARITY_NAME, "parity_hash")):
        document = load(name)
        assert SHA256.fullmatch(document[field]), name
        assert _hash_excluding(document, field) == document[field], name


def test_the_parity_record_covers_exactly_the_c05_membership() -> None:
    parity = load(PARITY_NAME)
    membership = _all_members(family_members(ROOT))

    assert sorted(parity["members"]) == membership
    assert parity["agreed_member_count"] == len(membership) == 42


def test_every_parity_member_carries_typed_provenance() -> None:
    for name, entry in load(PARITY_NAME)["members"].items():
        assert set(entry) == {
            "canonical",
            "canonical_sha256",
            "example",
            "example_sha256",
            "title",
        }, name
        assert SHA256.fullmatch(entry["canonical_sha256"]), name
        assert SHA256.fullmatch(entry["example_sha256"]), name
        assert entry["canonical"] == f"schemas/{name}.schema.json"
        assert entry["example"] == f"examples/sample_{name}.json"
        assert entry["title"]


def test_the_index_names_all_three_generated_projections() -> None:
    projections = load(INDEX_NAME)["projections"]

    assert sorted(projections) == sorted(PROJECTION_MANIFESTS)
    for language, entry in projections.items():
        assert entry["manifest"] == PROJECTION_MANIFESTS[language]
        assert entry["contract_count"] == 127
        assert SHA256.fullmatch(entry["manifest_sha256"])
        assert SHA256.fullmatch(entry["schema_bundle_sha256"])


def test_the_index_binds_every_source_it_reconciled() -> None:
    sources = load(INDEX_NAME)["sources"]

    assert sorted(sources) == sorted([C05_INDEX_PATH, *PROJECTION_MANIFESTS.values()])
    for digest in sources.values():
        assert SHA256.fullmatch(digest)


def test_the_mutable_space_is_read_from_the_sealed_c05_index() -> None:
    index = json.loads((ROOT / C05_INDEX_PATH).read_text(encoding="utf-8"))

    assert mutable_search_space(ROOT) == tuple(
        sorted(
            entry.removeprefix("schemas/").removesuffix(".schema.json")
            for entry in index["mutable_search_space"]
        )
    )
    assert len(mutable_search_space(ROOT)) == 4


def test_the_fixture_audit_accounts_for_every_member() -> None:
    fixtures = load(INDEX_NAME)["fixtures"]
    accounted = set(fixtures["composite_bound"]) | set(fixtures["schema_only"])

    assert accounted == set(_all_members(family_members(ROOT)))
    assert fixtures["member_count"] == 42
    assert not set(fixtures["composite_bound"]) & set(fixtures["schema_only"])


def test_every_schema_only_member_states_why_it_carries_no_composite() -> None:
    schema_only = load(INDEX_NAME)["fixtures"]["schema_only"]

    assert len(schema_only) == 11
    for reason in schema_only.values():
        assert "EF4-I41" in reason


@pytest.mark.parametrize("field", sorted(COMPATIBILITY_MEMBERS))
def test_every_compatibility_field_names_a_canonical_contract(field: str) -> None:
    name = COMPATIBILITY_MEMBERS[field]

    assert (ROOT / "schemas" / f"{name}.schema.json").is_file()
    assert load(BINDING_NAME)["properties"][field]["$ref"].endswith(
        f"{name}.schema.json"
    )
