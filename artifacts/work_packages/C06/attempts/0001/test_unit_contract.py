"""unit_and_contract_tests — the four receipts agree and the fixtures conform.

The reconciliation is re-derived here from the live repository rather than read
back from the emitted index: the C05 family index, the three C02 contract
manifests, the canonical schema files and the canonical examples must all agree
on every one of the 42 members.  The fixture audit is re-run and its result must
equal what the index recorded, and the compatibility binding must accept a
canonical migration record assembled from real examples.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from c06_integration_gate import (
    ASSEMBLED_COMPOSITES,
    BINDING_NAME,
    C05_BUNDLE_DIR,
    CANDIDATE_COMPOSITE,
    CANDIDATE_FAMILY,
    COMPATIBILITY_MEMBERS,
    FAMILY_COMPOSITES,
    INDEX_NAME,
    PROJECTION_MANIFESTS,
    _all_members,
    _registry,
    audit_fixtures,
    build_binding,
    build_index,
    emit,
    family_members,
    mutable_search_space,
    reconcile_projections,
    render,
    verify,
)
from test_schema_and_type import BUNDLE, ROOT, load

MEMBERS = _all_members(family_members(ROOT))


def example(name: str) -> dict:
    return json.loads(
        (ROOT / f"examples/sample_{name}.json").read_text(encoding="utf-8")
    )


def composite_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        json.loads((ROOT / C05_BUNDLE_DIR / name).read_text(encoding="utf-8")),
        registry=_registry(ROOT),
    )


def test_the_committed_bundle_verifies() -> None:
    report = verify(ROOT)

    assert report["status"] == "PASS"
    assert report["member_count"] == 42
    assert report["projections_reconciled"] == len(PROJECTION_MANIFESTS)
    assert report["sources_verified"] == 4
    assert report["fixtures_validated"] == 84


def test_all_four_receipts_agree_on_every_member() -> None:
    parity = reconcile_projections(ROOT)
    c05 = json.loads(
        (ROOT / "schemas/v4_c05/family-index.json").read_text(encoding="utf-8")
    )
    c05_hashes = {
        entry["canonical"]: entry["sha256"]
        for record in c05["families"].values()
        for entry in record["members"]
    }
    manifests = {
        language: {
            row["schema_file"]: row
            for row in json.loads((ROOT / relative).read_text(encoding="utf-8"))[
                "contracts"
            ]
        }
        for language, relative in PROJECTION_MANIFESTS.items()
    }

    for name in MEMBERS:
        key = f"schemas/{name}.schema.json"
        live = "sha256:" + hashlib.sha256((ROOT / key).read_bytes()).hexdigest()
        assert parity["members"][name]["canonical_sha256"] == live, name
        assert c05_hashes[key] == live, name
        for language in manifests:
            assert manifests[language][key]["source_sha256"] == live, (name, language)


def test_every_member_carries_a_canonical_fixture_whose_hash_agrees() -> None:
    parity = reconcile_projections(ROOT)

    for name in MEMBERS:
        path = ROOT / f"examples/sample_{name}.json"
        assert path.is_file(), name
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert parity["members"][name]["example_sha256"] == digest, name


@pytest.mark.parametrize("name", MEMBERS)
def test_every_canonical_fixture_satisfies_its_own_schema(name: str) -> None:
    schema = json.loads(
        (ROOT / f"schemas/{name}.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, registry=_registry(ROOT)).validate(example(name))


@pytest.mark.parametrize("name", sorted(mutable_search_space(ROOT)))
def test_every_canonical_genome_fixture_is_admitted_as_a_candidate(
    name: str,
) -> None:
    composite_validator(CANDIDATE_COMPOSITE).validate(example(name))


@pytest.mark.parametrize("family", sorted(FAMILY_COMPOSITES))
def test_every_family_fixture_satisfies_its_composite(family: str) -> None:
    validator = composite_validator(FAMILY_COMPOSITES[family])

    for name in family_members(ROOT)[family]:
        validator.validate(example(name))


@pytest.mark.parametrize("composite", sorted(ASSEMBLED_COMPOSITES))
def test_the_assembled_canonical_fixtures_satisfy_their_composite(
    composite: str,
) -> None:
    assembled = {
        field: example(name) for name, field in ASSEMBLED_COMPOSITES[composite].items()
    }

    composite_validator(composite).validate(assembled)


def test_the_compatibility_binding_accepts_a_canonical_migration() -> None:
    record = {field: example(name) for field, name in COMPATIBILITY_MEMBERS.items()}

    Draft202012Validator(load(BINDING_NAME), registry=_registry(ROOT)).validate(record)


def test_the_binding_accepts_the_minimum_required_record() -> None:
    record = {
        "compatibility_matrix": example("compatibility-matrix"),
        "migration": example("schema-migration"),
    }

    Draft202012Validator(load(BINDING_NAME), registry=_registry(ROOT)).validate(record)


def test_the_index_records_the_audit_that_re_running_produces() -> None:
    assert load(INDEX_NAME)["fixtures"] == audit_fixtures(ROOT)


def test_regeneration_is_byte_identical() -> None:
    parity = reconcile_projections(ROOT)
    binding = build_binding(ROOT)
    fixtures = audit_fixtures(ROOT)

    assert (BUNDLE / BINDING_NAME).read_bytes() == render(binding)
    assert (BUNDLE / "generated-projection-parity.json").read_bytes() == render(parity)
    assert (BUNDLE / INDEX_NAME).read_bytes() == render(
        build_index(ROOT, parity, fixtures, binding)
    )


def test_re_emitting_in_place_changes_nothing() -> None:
    before = {path.name: path.read_bytes() for path in sorted(BUNDLE.iterdir())}
    emit(ROOT)

    assert {path.name: path.read_bytes() for path in sorted(BUNDLE.iterdir())} == (
        before
    )
    assert verify(ROOT)["status"] == "PASS"


def test_the_candidate_family_splits_into_bound_and_schema_only() -> None:
    membership = family_members(ROOT)
    fixtures = audit_fixtures(ROOT)
    candidates = set(mutable_search_space(ROOT))
    genome = set(membership[CANDIDATE_FAMILY])

    assert candidates < genome
    assert candidates <= set(fixtures["composite_bound"])
    assert genome - candidates == set(fixtures["schema_only"])


def test_the_bundle_holds_exactly_the_three_receipted_files() -> None:
    names = sorted(path.name for path in BUNDLE.iterdir())

    assert names == sorted(
        [BINDING_NAME, "generated-projection-parity.json", INDEX_NAME]
    )


def test_the_index_is_canonical_json_on_disk() -> None:
    raw = (BUNDLE / INDEX_NAME).read_text(encoding="utf-8")

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )
