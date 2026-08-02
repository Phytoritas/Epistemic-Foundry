"""schema_and_type_check — the emitted documents keep their declared contracts.

The profile is a build artifact, but its shape is still a contract: exact field
sets, recomputable content hashes, and a readiness map that must cover the
canonical ShinkaBackendManifest schema exactly — every required field is either
pinnable now from the public observation or blocked with the reason it cannot
be pinned yet, and the pinnable constants must equal the schema's own consts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from b05_profile import (
    BACKEND_SCHEMA_PATH,
    EXPECTED_OPENAPI_COUNT,
    EXPECTED_RESOURCE_COUNT,
    EXPECTED_SCHEMA_COUNT,
    FEATURE_NAME,
    INPUT_PATHS,
    MANIFEST_NAME,
    OUTPUT_DIR,
    PROFILE_NAME,
    REGISTRY_PATH,
    _FEATURE_FIELDS,
    _MANIFEST_FIELDS,
    _PROFILE_FIELDS,
    _hash_excluding,
)

ROOT = Path(__file__).resolve().parents[5]
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def load(name: str) -> dict:
    return json.loads((ROOT / OUTPUT_DIR / name).read_text(encoding="utf-8"))


def test_the_profile_keeps_its_exact_field_set() -> None:
    assert set(load(PROFILE_NAME)) == set(_PROFILE_FIELDS)


def test_the_feature_document_keeps_its_exact_field_set() -> None:
    assert set(load(FEATURE_NAME)) == set(_FEATURE_FIELDS)


def test_the_manifest_keeps_its_exact_field_set() -> None:
    assert set(load(MANIFEST_NAME)) == set(_MANIFEST_FIELDS)


def test_every_document_hash_is_recomputable() -> None:
    for name, field in (
        (PROFILE_NAME, "profile_hash"),
        (FEATURE_NAME, "feature_hash"),
        (MANIFEST_NAME, "manifest_hash"),
    ):
        document = load(name)
        assert SHA256.fullmatch(document[field]), name
        assert _hash_excluding(document, field) == document[field], name


def test_the_readiness_map_covers_the_canonical_schema_exactly() -> None:
    schema = json.loads((ROOT / BACKEND_SCHEMA_PATH).read_text(encoding="utf-8"))
    readiness = load(FEATURE_NAME)["canonical_manifest_readiness"]
    pinnable = set(readiness["pinnable_fields"])
    blocked = set(readiness["blocked_fields"])

    assert pinnable | blocked == set(schema["required"])
    assert not pinnable & blocked
    for reason in readiness["blocked_fields"].values():
        assert reason.strip()


def test_the_pinnable_constants_equal_the_schema_consts() -> None:
    schema = json.loads((ROOT / BACKEND_SCHEMA_PATH).read_text(encoding="utf-8"))
    pinnable = load(FEATURE_NAME)["canonical_manifest_readiness"]["pinnable_fields"]

    assert pinnable["backend_name"] == schema["properties"]["backend_name"]["const"]
    assert pinnable["license"] == schema["properties"]["license"]["const"]


def test_the_canonical_resource_counts_match_the_live_registry() -> None:
    registry = json.loads((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
    resources = load(PROFILE_NAME)["canonical_resources"]

    assert (
        resources["schema_count"] == registry["schema_count"] == (EXPECTED_SCHEMA_COUNT)
    )
    assert resources["openapi_document_count"] == EXPECTED_OPENAPI_COUNT
    assert (
        resources["resource_count"]
        == registry["resource_count"]
        == (EXPECTED_RESOURCE_COUNT)
    )
    assert SHA256.fullmatch(resources["registry_sha256"])


def test_the_profile_inputs_are_exactly_the_declared_inputs() -> None:
    profile = load(PROFILE_NAME)

    assert tuple(sorted(profile["inputs"])) == tuple(sorted(INPUT_PATHS))
    for digest in profile["inputs"].values():
        assert SHA256.fullmatch(digest)


def test_locked_packages_are_sorted_typed_and_hashed() -> None:
    packages = load(PROFILE_NAME)["locked_packages"]

    assert packages == sorted(packages, key=lambda entry: entry["name"])
    for entry in packages:
        assert set(entry) == {
            "artifact_hash_digest",
            "name",
            "sdist_sha256",
            "version",
            "wheel_count",
        }
        assert entry["version"]
        assert isinstance(entry["wheel_count"], int)
        assert SHA256.fullmatch(entry["artifact_hash_digest"])
        assert entry["sdist_sha256"] is None or SHA256.fullmatch(entry["sdist_sha256"])
        assert entry["sdist_sha256"] is not None or entry["wheel_count"] > 0


def test_every_direct_dependency_resolves_to_a_locked_package() -> None:
    profile = load(PROFILE_NAME)
    locked = {entry["name"]: entry["version"] for entry in profile["locked_packages"]}

    assert profile["direct_dependencies"]
    for group in (
        profile["direct_dependencies"],
        *profile["dependency_groups"].values(),
    ):
        for dependency in group:
            assert locked[dependency["name"]] == dependency["locked_version"]


def test_the_dependency_groups_are_the_declared_ones() -> None:
    groups = load(PROFILE_NAME)["dependency_groups"]

    assert sorted(groups) == ["dev", "skill-context"]
    assert [entry["name"] for entry in groups["skill-context"]] == ["tiktoken"]
    assert groups["skill-context"][0]["specifier"].startswith("tiktoken==")


def test_the_build_system_is_pinned_exactly() -> None:
    build_system = load(PROFILE_NAME)["build_system"]

    assert build_system["exact_pin"] is True
    assert build_system["backend"] == "setuptools.build_meta"
    for requirement in build_system["requires"]:
        assert "==" in requirement


def test_the_project_identity_matches_pyproject() -> None:
    project = load(PROFILE_NAME)["project"]

    assert project["name"] == "epistemic-foundry"
    assert project["version"] == "4.0.0"
    assert project["requires_python"] == ">=3.12"


def test_the_observation_names_its_source_and_admits_its_limits() -> None:
    observation = load(FEATURE_NAME)["observation"]

    assert observation["source"] in INPUT_PATHS
    assert observation["full_revision_verified"] is False
    assert observation["verification_state"] == "PUBLIC_SOURCE_OBSERVATION_ONLY"
