"""B04 canonical registry packaging and fail-closed integrity tests."""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest

from epistemic_foundry.contracts.registry import (
    CANONICAL_REGISTRY_DUPLICATE_ID,
    CANONICAL_REGISTRY_HASH_MISMATCH,
    CANONICAL_REGISTRY_MISSING,
    CanonicalRegistryError,
    SchemaRegistry,
    default_registry,
    repo_root,
)
from scripts.build.canonical_registry.materialize import (
    CanonicalMaterializationError,
    PROJECTION_TOOL_IDENTITY,
    PROJECTION_TOOL_VERSION,
    REGISTRY_FORMAT_VERSION,
    REGISTRY_SCHEMA_VERSION,
    SOURCE_CHANGED_DURING_PROJECTION,
    build_registry_document,
    materialize,
    verify_projection,
)
from scripts.build.canonical_registry import materialize as materializer

#: Moved 2026-08-02 by the authorized amendment closing
#: SPEC_GAP-SOURCE-LOCATOR-PAGE, and the node-contract `executor_status`
#: addition that makes an unbuilt workflow executor declarable instead of
#: silent. `source_locator.page` became
#: ["integer", "null"] across the six schemas that declare it, so a page-less
#: text corpus can emit canonical claim-card and evidence-node artifacts without
#: fabricating a page number. The pin moves with the content it attests; the
#: previous values are retained here as history, and B04-0009's sealed
#: attestation of them remains true as of its seal time.
#: Re-pin history, kept so a bundle move stays auditable instead of being erased.
#: [1] pre-amendment:               sha256:2cb8b87793eabf4d6cd209044b6c28bf14f003b15fb85a81cf70db77ce92e2b5
#:     snapshot:                    sha256:9dfd37885743ad02dd680e36882fbf88249a89dcc4ec1b7ac5266a94ca7a2229
#: [2] source_locator nullable page: sha256:7a1b48ec233349d1387ec9d9b16b0cd8454e1cb5a5c9f5d21db14ca2c771fe87
#:     snapshot:                    sha256:b662a542b2afe9d8310f3bd9edd895bd1e0eddb6e39c72e43b650a0cc22a6484
#: [3] document-registration field_sources: sha256:296b248948480b1ff248243cd4265b40b98a12968770a2903c43649f6b3dbe20
#:     snapshot:                    sha256:2e5b0ff2081eba59b3a7b9dd655ca491c1f3660817ccb62079cf93bac46eed57
#: [4] retrieval-candidate identity exclusion_policy — current, below.
EXPECTED_SOURCE_BUNDLE_HASH = (
    "sha256:7cf181912ceed6fdc0df0895b9eb5968f2ce6089577fc0069042229e28d9c7ff"
)
EXPECTED_SNAPSHOT_BUNDLE_HASH = (
    "sha256:a3075d0adab4e0b9cf485728a9064051879d1a5eb6df6ab759a5e24976a87cdd"
)


def _copy_projection(tmp_path: Path) -> Path:
    destination = tmp_path / "canonical"
    materialize(repo_root(), destination)
    return destination


def _copy_authority_root(tmp_path: Path) -> Path:
    root = tmp_path / "authority"
    root.mkdir()
    shutil.copy2(repo_root() / "pyproject.toml", root / "pyproject.toml")
    shutil.copytree(repo_root() / "schemas", root / "schemas")
    shutil.copytree(repo_root() / "openapi", root / "openapi")
    (root / "toolchains").mkdir()
    shutil.copy2(
        repo_root() / "toolchains" / "toolchain-lock.json",
        root / "toolchains" / "toolchain-lock.json",
    )
    return root


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _mutate_schema(root: Path, name: str, revision: str) -> None:
    path = root / "schemas" / name
    document = json.loads(path.read_text(encoding="utf-8"))
    document["x-b04-test-revision"] = revision
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_source_projection_is_current_and_complete() -> None:
    result = verify_projection(repo_root())
    assert result == {
        "destination": str(repo_root() / "src" / "epistemic_foundry" / "_canonical"),
        "expected_file_count": 129,
        "extra": [],
        "mismatches": [],
        "missing": [],
        "status": "PASS",
    }


def test_default_registry_uses_verified_package_resources() -> None:
    registry = default_registry()
    assert len(registry.names()) == 127
    assert registry.manifest["resource_count"] == 128
    assert registry.manifest["schema_count"] == 127
    assert registry.manifest["openapi_document_count"] == 1
    assert registry.openapi_text().startswith("openapi: 3.1.1\n")


def test_registry_v2_binds_source_snapshot_paths_and_projection_tool() -> None:
    manifest, resources = build_registry_document(repo_root())
    assert len(resources) == 128
    assert manifest["schema_version"] == REGISTRY_SCHEMA_VERSION == 2
    assert manifest["registry_format_version"] == REGISTRY_FORMAT_VERSION
    assert manifest["source_bundle_hash"] == EXPECTED_SOURCE_BUNDLE_HASH
    assert manifest["projected_snapshot_bundle_hash"] == EXPECTED_SNAPSHOT_BUNDLE_HASH
    assert manifest["build_source_revision"] == EXPECTED_SOURCE_BUNDLE_HASH
    assert manifest["source_revision"] == EXPECTED_SOURCE_BUNDLE_HASH
    assert manifest["projection_tool_identity"] == PROJECTION_TOOL_IDENTITY
    assert manifest["projection_tool_version"] == PROJECTION_TOOL_VERSION
    assert manifest["file_count"] == manifest["resource_count"] == 128
    assert all(
        entry["source_path"] == entry["package_path"] == entry["relative_path"]
        for entry in manifest["resources"]
    )


def test_runtime_accepts_registry_v2_external_projection(tmp_path: Path) -> None:
    projection = _copy_projection(tmp_path)
    registry = SchemaRegistry(projection)
    assert registry.manifest["schema_version"] == 2
    assert registry.manifest["source_bundle_hash"] == EXPECTED_SOURCE_BUNDLE_HASH
    assert (
        registry.manifest["projected_snapshot_bundle_hash"]
        == EXPECTED_SNAPSHOT_BUNDLE_HASH
    )
    assert len(registry.names()) == 127


def test_returned_document_mutation_cannot_change_later_validation() -> None:
    registry = default_registry()
    document = registry.document("action-intent")
    document.clear()
    fresh = registry.document("action-intent")
    assert fresh["$id"].endswith("action-intent.schema.json")
    assert list(registry.validator("action-intent").iter_errors({}))


def test_returned_manifest_nested_mutation_cannot_change_registry_state() -> None:
    registry = default_registry()
    manifest = registry.manifest
    manifest["resources"].clear()
    manifest["openapi_document_count"] = 0
    assert registry.manifest["resource_count"] == 128
    assert registry.manifest["openapi_document_count"] == 1
    assert registry.openapi_text().startswith("openapi: 3.1.1\n")


def test_returned_validator_mutation_cannot_change_later_validation() -> None:
    registry = default_registry()
    validator = registry.validator("action-intent")
    validator.schema.clear()
    assert validator.schema == {}
    assert list(registry.validator("action-intent").iter_errors({}))


def test_materialization_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    materialize(repo_root(), first)
    materialize(repo_root(), second)
    first_files = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_materialize_atomically_replaces_complete_existing_projection(
    tmp_path: Path,
) -> None:
    root = _copy_authority_root(tmp_path)
    destination = tmp_path / "canonical"
    first = materialize(root, destination)
    prior = _tree_bytes(destination)
    _mutate_schema(root, "action-intent.schema.json", "atomic-replacement")

    second = materialize(root, destination)

    assert first["status"] == second["status"] == "PASS"
    assert second["atomic_replacement"] == "PASS"
    assert second["changed_file_count"] == 2
    assert _tree_bytes(destination) != prior
    assert (
        SchemaRegistry(destination).manifest["source_bundle_hash"]
        == second["source_bundle_hash"]
    )


def test_second_rename_failure_restores_old_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_authority_root(tmp_path)
    destination = tmp_path / "canonical"
    materialize(root, destination)
    prior = _tree_bytes(destination)
    _mutate_schema(root, "action-intent.schema.json", "rename-failure")
    real_replace = materializer.os.replace
    call_count = 0

    def fail_second_replace(source: object, target: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("injected second rename failure")
        real_replace(source, target)

    monkeypatch.setattr(materializer.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="injected second rename failure"):
        materialize(root, destination)

    assert call_count == 3
    assert _tree_bytes(destination) == prior
    assert SchemaRegistry(destination).manifest["schema_version"] == 2


def test_source_mutation_before_swap_fails_without_live_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_authority_root(tmp_path)
    destination = tmp_path / "canonical"
    materialize(root, destination)
    prior = _tree_bytes(destination)
    _mutate_schema(root, "action-intent.schema.json", "planned-update")
    real_write = materializer._write_staged_tree

    def mutate_after_staging(*args: object, **kwargs: object) -> None:
        real_write(*args, **kwargs)
        _mutate_schema(root, "approval-record.schema.json", "concurrent-change")

    monkeypatch.setattr(materializer, "_write_staged_tree", mutate_after_staging)
    with pytest.raises(
        CanonicalMaterializationError,
        match=f"^{SOURCE_CHANGED_DURING_PROJECTION}$",
    ):
        materialize(root, destination)

    assert _tree_bytes(destination) == prior
    assert SchemaRegistry(destination).manifest["schema_version"] == 2


def test_source_mutation_after_swap_rolls_back_old_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_authority_root(tmp_path)
    destination = tmp_path / "canonical"
    materialize(root, destination)
    prior = _tree_bytes(destination)
    _mutate_schema(root, "action-intent.schema.json", "planned-update")
    real_replace = materializer.os.replace
    call_count = 0

    def mutate_after_live_swap(source: object, target: object) -> None:
        nonlocal call_count
        call_count += 1
        real_replace(source, target)
        if call_count == 2:
            _mutate_schema(root, "approval-record.schema.json", "post-swap-change")

    monkeypatch.setattr(materializer.os, "replace", mutate_after_live_swap)
    with pytest.raises(
        CanonicalMaterializationError,
        match=f"^{SOURCE_CHANGED_DURING_PROJECTION}$",
    ):
        materialize(root, destination)

    assert call_count == 4
    assert _tree_bytes(destination) == prior
    assert SchemaRegistry(destination).manifest["schema_version"] == 2


def test_materialize_rejects_unrelated_destination_without_deleting_it(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "unrelated"
    destination.mkdir()
    sentinel = destination / "keep-me.txt"
    sentinel.write_text("user data\n", encoding="utf-8", newline="\n")
    with pytest.raises(CanonicalMaterializationError):
        materialize(repo_root(), destination)
    assert sentinel.read_text(encoding="utf-8") == "user data\n"
    assert list(destination.iterdir()) == [sentinel]


def test_materialize_preserves_unrelated_empty_directory(tmp_path: Path) -> None:
    destination = tmp_path / "projection-with-user-directory"
    preserved = destination / "user-owned-empty-directory"
    preserved.mkdir(parents=True)
    result = materialize(repo_root(), destination)
    assert result["status"] == "PASS"
    assert preserved.is_dir()
    assert list(preserved.iterdir()) == []


def test_materialize_rejects_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    destination = tmp_path / "linked-projection"
    destination.symlink_to(target, target_is_directory=True)
    with pytest.raises(CanonicalMaterializationError, match="link"):
        materialize(repo_root(), destination)
    assert not list(target.iterdir())


def test_build_backend_is_exactly_pinned() -> None:
    pyproject = tomllib.loads(
        (repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["build-system"] == {
        "requires": ["setuptools==82.0.1"],
        "build-backend": "setuptools.build_meta",
    }
    constraints = (repo_root() / "toolchains/python-build-constraints.txt").read_text(
        encoding="utf-8"
    )
    assert "setuptools==82.0.1 \\\n" in constraints


def test_missing_packaged_resource_fails_closed(tmp_path: Path) -> None:
    projection = _copy_projection(tmp_path)
    (projection / "schemas" / "action-intent.schema.json").unlink()
    with pytest.raises(CanonicalRegistryError) as caught:
        SchemaRegistry(projection)
    assert caught.value.code == CANONICAL_REGISTRY_MISSING


def test_one_byte_tamper_fails_closed(tmp_path: Path) -> None:
    projection = _copy_projection(tmp_path)
    target = projection / "schemas" / "action-intent.schema.json"
    content = bytearray(target.read_bytes())
    content[-2] = ord(" ") if content[-2] != ord(" ") else ord("\t")
    target.write_bytes(content)
    with pytest.raises(CanonicalRegistryError) as caught:
        SchemaRegistry(projection)
    assert caught.value.code == CANONICAL_REGISTRY_HASH_MISMATCH


def test_duplicate_document_id_fails_closed(tmp_path: Path) -> None:
    projection = _copy_projection(tmp_path)
    registry_path = projection / "canonical-registry.json"
    manifest = json.loads(registry_path.read_text(encoding="utf-8"))
    manifest["resources"][1]["document_id"] = manifest["resources"][0]["document_id"]
    registry_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CanonicalRegistryError) as caught:
        SchemaRegistry(projection)
    assert caught.value.code == CANONICAL_REGISTRY_DUPLICATE_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("projected_snapshot_bundle_hash", "sha256:" + "0" * 64),
        ("projection_tool_identity", "unapproved.projector"),
        ("projection_tool_version", "999.0.0"),
        ("source_revision", "sha256:" + "0" * 64),
    ],
)
def test_registry_v2_binding_tamper_fails_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    projection = _copy_projection(tmp_path)
    registry_path = projection / "canonical-registry.json"
    manifest = json.loads(registry_path.read_text(encoding="utf-8"))
    manifest[field] = value
    registry_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CanonicalRegistryError) as caught:
        SchemaRegistry(projection)
    assert caught.value.code == CANONICAL_REGISTRY_HASH_MISMATCH


def test_unregistered_extra_resource_fails_closed(tmp_path: Path) -> None:
    projection = _copy_projection(tmp_path)
    (projection / "schemas" / "unregistered.schema.json").write_text(
        "{}\n", encoding="utf-8"
    )
    with pytest.raises(CanonicalRegistryError) as caught:
        SchemaRegistry(projection)
    assert caught.value.code == CANONICAL_REGISTRY_HASH_MISMATCH
