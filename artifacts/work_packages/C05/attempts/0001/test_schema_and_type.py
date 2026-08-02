"""schema_and_type_check — the bundle is valid, resolvable and literal-free.

Every composite must be a valid Draft 2020-12 schema whose references resolve
to the canonical files by exact ``$id``; none may declare an enum, const,
pattern or format of its own, because the canonical sources stay the single
declaring site (EF4-I22); and the family index must keep exactly the five
families the package title names, with a recomputable hash.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from c05_schema_bundle import (
    EXCLUDED_WITH_REASONS,
    FAMILIES,
    FORBIDDEN_COMPOSITE_KEYWORDS,
    INDEX_NAME,
    MUTABLE_SEARCH_SPACE,
    OUTPUT_DIR,
    _hash_excluding,
    build_composites,
    members,
)

ROOT = Path(__file__).resolve().parents[5]
BUNDLE = ROOT / OUTPUT_DIR
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMPOSITE_NAMES = sorted(build_composites(ROOT))


def load(name: str) -> dict:
    return json.loads((BUNDLE / name).read_text(encoding="utf-8"))


def registry() -> Registry:
    resources = []
    for path in (ROOT / "schemas").glob("*.schema.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        resources.append((document["$id"], Resource.from_contents(document)))
    for name in COMPOSITE_NAMES:
        document = load(name)
        resources.append((document["$id"], Resource.from_contents(document)))
    return Registry().with_resources(resources)


@pytest.mark.parametrize("name", COMPOSITE_NAMES)
def test_every_composite_is_a_valid_draft_2020_12_schema(name: str) -> None:
    Draft202012Validator.check_schema(load(name))


@pytest.mark.parametrize("name", COMPOSITE_NAMES)
def test_every_reference_resolves_to_a_canonical_id(name: str) -> None:
    resolver = registry().resolver()
    document = load(name)
    refs = re.findall(r'"\$ref": "([^"]+)"', json.dumps(document, indent=0))

    assert refs
    for ref in refs:
        assert resolver.lookup(ref).contents["$id"] == ref


@pytest.mark.parametrize("name", COMPOSITE_NAMES)
def test_no_composite_declares_local_vocabulary(name: str) -> None:
    text = json.dumps(load(name))

    for keyword in FORBIDDEN_COMPOSITE_KEYWORDS:
        assert f'"{keyword}":' not in text, keyword


def test_the_composite_ids_are_unique_and_namespaced() -> None:
    ids = [load(name)["$id"] for name in COMPOSITE_NAMES]

    assert len(set(ids)) == len(ids)
    for value in ids:
        assert value.startswith("https://epistemic-foundry.local/schemas/v4_c05/")


def test_the_index_names_exactly_the_five_titled_families() -> None:
    index = load(INDEX_NAME)

    assert sorted(index["families"]) == [
        "adapter",
        "archive",
        "evaluator",
        "genome",
        "statistics",
    ]
    assert index["member_count"] == 42


def test_the_family_membership_is_exhaustive_and_disjoint() -> None:
    listed = [name for family in FAMILIES.values() for name in family["members"]]

    assert len(listed) == len(set(listed)) == 42
    assert sorted(listed) == list(members())


def test_every_family_cites_at_least_one_invariant() -> None:
    for family_name, family in FAMILIES.items():
        assert family["invariants"], family_name
        for invariant in family["invariants"]:
            assert re.fullmatch(r"EF4-I[0-9]{2}", invariant), family_name


def test_the_mutable_search_space_is_the_four_genome_kinds() -> None:
    index = load(INDEX_NAME)

    assert index["mutable_search_space"] == [
        f"schemas/{name}.schema.json" for name in MUTABLE_SEARCH_SPACE
    ]
    assert set(MUTABLE_SEARCH_SPACE) <= set(FAMILIES["genome"]["members"])
    assert [name for name in MUTABLE_SEARCH_SPACE if name.endswith("-genome")] == (
        list(MUTABLE_SEARCH_SPACE)
    )


def test_every_exclusion_names_its_owner() -> None:
    index = load(INDEX_NAME)

    assert len(index["excluded"]) == len(EXCLUDED_WITH_REASONS) == 4
    for entry in index["excluded"]:
        assert (ROOT / entry["canonical"]).is_file()
        assert entry["reason"].strip()


def test_the_index_hash_is_recomputable() -> None:
    index = load(INDEX_NAME)

    assert _hash_excluding(index, "index_hash") == index["index_hash"]


def test_every_member_hash_matches_the_pattern() -> None:
    index = load(INDEX_NAME)

    for family in index["families"].values():
        for entry in family["members"]:
            assert SHA256.fullmatch(entry["sha256"]), entry["canonical"]


def test_the_candidate_composite_admits_exactly_the_mutable_space() -> None:
    candidate = load("evolution-candidate.schema.json")
    refs = sorted(entry["$ref"] for entry in candidate["oneOf"])

    assert refs == sorted(
        f"https://epistemic-foundry.local/schemas/{name}.schema.json"
        for name in MUTABLE_SEARCH_SPACE
    )


def test_the_statistics_composite_requires_the_correction_triple() -> None:
    statistics = load("adaptive-search-statistics.schema.json")

    assert statistics["required"] == [
        "multiple_testing_adjustment",
        "selective_inference_report",
        "sequential_testing_ledger",
    ]
    assert statistics["additionalProperties"] is False


def test_the_backend_composite_requires_the_qualification_triple() -> None:
    binding = load("external-backend-binding.schema.json")

    assert binding["required"] == [
        "backend_manifest",
        "imported_run",
        "qualification",
    ]
    assert binding["additionalProperties"] is False
