#!/usr/bin/env python3
"""Materialize the canonical source contracts as a package resource snapshot.

The repository-root ``schemas/`` and ``openapi/`` directories remain the
authorities.  This module creates a content-addressed runtime projection under
``src/epistemic_foundry/_canonical`` without changing either authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

EXPECTED_SCHEMA_COUNT = 127
OPENAPI_RELATIVE_PATH = PurePosixPath(
    "openapi/epistemic-foundry-v1.openapi.yaml"
)
REGISTRY_RELATIVE_PATH = PurePosixPath("canonical-registry.json")
SHA256_PREFIX = "sha256:"
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REGISTRY_SCHEMA_VERSION = 2
REGISTRY_FORMAT_VERSION = "2.0.0"
PROJECTION_TOOL_IDENTITY = "epistemic_foundry.canonical_registry.materialize"
PROJECTION_TOOL_VERSION = "2.0.0"
SOURCE_CHANGED_DURING_PROJECTION = "SOURCE_CHANGED_DURING_PROJECTION"


class CanonicalMaterializationError(RuntimeError):
    """Raised when the authoritative bundle cannot be projected safely."""


@dataclass(frozen=True)
class SourceResource:
    relative_path: PurePosixPath
    media_type: str
    document_id: str
    kind: str
    content: bytes

    def manifest_entry(self) -> dict[str, Any]:
        relative_path = self.relative_path.as_posix()
        return {
            "byte_size": len(self.content),
            "document_id": self.document_id,
            "kind": self.kind,
            "media_type": self.media_type,
            "package_path": relative_path,
            "relative_path": relative_path,
            "sha256": SHA256_PREFIX + hashlib.sha256(self.content).hexdigest(),
            "source_path": relative_path,
        }


def _read_bundle_version(root: Path) -> str:
    pyproject_path = root / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        version = pyproject["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise CanonicalMaterializationError(
            f"cannot read project version from {pyproject_path}: {error}"
        ) from error
    if not isinstance(version, str) or not version:
        raise CanonicalMaterializationError("project.version must be a non-empty string")
    return version


def _read_build_epoch(root: Path) -> int:
    lock_path = root / "toolchains" / "toolchain-lock.json"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        locked_epoch = lock["source_date_epoch"]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise CanonicalMaterializationError(
            f"cannot read source_date_epoch from {lock_path}: {error}"
        ) from error
    if not isinstance(locked_epoch, int) or isinstance(locked_epoch, bool):
        raise CanonicalMaterializationError(
            "toolchain-lock source_date_epoch must be an integer"
        )

    environment_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if environment_epoch is not None:
        try:
            parsed_epoch = int(environment_epoch)
        except ValueError as error:
            raise CanonicalMaterializationError(
                "SOURCE_DATE_EPOCH must be an integer"
            ) from error
        if parsed_epoch != locked_epoch:
            raise CanonicalMaterializationError(
                "SOURCE_DATE_EPOCH does not match toolchains/toolchain-lock.json"
            )
    return locked_epoch


def _schema_resources(root: Path) -> list[SourceResource]:
    schema_root = root / "schemas"
    if not schema_root.is_dir():
        raise CanonicalMaterializationError(f"missing canonical schema root: {schema_root}")

    paths = sorted(schema_root.glob("*.schema.json"), key=lambda item: item.name)
    other_files = sorted(
        path.name
        for path in schema_root.iterdir()
        if path.is_file() and not path.name.endswith(".schema.json")
    )
    if other_files:
        raise CanonicalMaterializationError(
            f"unexpected non-schema files under schemas/: {other_files}"
        )
    if len(paths) != EXPECTED_SCHEMA_COUNT:
        raise CanonicalMaterializationError(
            f"expected {EXPECTED_SCHEMA_COUNT} canonical schemas, found {len(paths)}"
        )

    resources: list[SourceResource] = []
    identifiers: dict[str, str] = {}
    for path in paths:
        content = path.read_bytes()
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CanonicalMaterializationError(
                f"canonical schema is not UTF-8 JSON: {path}"
            ) from error
        identifier = document.get("$id") if isinstance(document, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise CanonicalMaterializationError(f"canonical schema has no $id: {path}")
        prior = identifiers.get(identifier)
        if prior is not None:
            raise CanonicalMaterializationError(
                f"duplicate canonical schema $id {identifier!r}: {prior}, {path.name}"
            )
        identifiers[identifier] = path.name
        resources.append(
            SourceResource(
                relative_path=PurePosixPath("schemas", path.name),
                media_type="application/schema+json",
                document_id=identifier,
                kind="json_schema",
                content=content,
            )
        )
    return resources


def _openapi_resource(root: Path) -> SourceResource:
    source_path = root / Path(*OPENAPI_RELATIVE_PATH.parts)
    if not source_path.is_file():
        raise CanonicalMaterializationError(
            f"missing canonical OpenAPI document: {source_path}"
        )
    content = source_path.read_bytes()
    try:
        first_nonempty = next(
            line.strip()
            for line in content.decode("utf-8").splitlines()
            if line.strip()
        )
    except (UnicodeDecodeError, StopIteration) as error:
        raise CanonicalMaterializationError(
            "canonical OpenAPI document must be non-empty UTF-8"
        ) from error
    if first_nonempty != "openapi: 3.1.1":
        raise CanonicalMaterializationError(
            "canonical OpenAPI document must declare OpenAPI 3.1.1"
        )
    return SourceResource(
        relative_path=OPENAPI_RELATIVE_PATH,
        media_type="application/vnd.oai.openapi",
        document_id=OPENAPI_RELATIVE_PATH.as_posix(),
        kind="openapi",
        content=content,
    )


def collect_source_resources(root: Path) -> list[SourceResource]:
    resources = [*_schema_resources(root), _openapi_resource(root)]
    resources.sort(key=lambda resource: resource.relative_path.as_posix())
    return resources


def _canonical_json_bytes(value: Any) -> bytes:
    """Serialize the integer/string-only bundle preimages deterministically."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_identifier(content: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(content).hexdigest()


def source_bundle_preimage(resources: Iterable[SourceResource]) -> dict[str, Any]:
    entries = []
    for resource in sorted(
        resources, key=lambda item: item.relative_path.as_posix()
    ):
        path = resource.relative_path.as_posix()
        entries.append(
            {
                "path": path,
                "sha256": _sha256_identifier(resource.content),
                "size": len(resource.content),
                "target_path": path,
            }
        )
    return {"algorithm": "sha256", "entries": entries}


def projected_snapshot_preimage(
    resources: Iterable[SourceResource],
) -> dict[str, Any]:
    entries = []
    for resource in sorted(
        resources, key=lambda item: item.relative_path.as_posix()
    ):
        path = resource.relative_path.as_posix()
        entries.append(
            {
                "byte_size": len(resource.content),
                "path": path,
                "sha256": _sha256_identifier(resource.content),
                "target_path": path,
            }
        )
    return {"algorithm": "sha256", "entries": entries}


def calculate_source_bundle_hash(resources: Iterable[SourceResource]) -> str:
    return _sha256_identifier(_canonical_json_bytes(source_bundle_preimage(resources)))


def calculate_projected_snapshot_bundle_hash(
    resources: Iterable[SourceResource],
) -> str:
    return _sha256_identifier(
        _canonical_json_bytes(projected_snapshot_preimage(resources))
    )


def build_registry_document(
    root: Path, resources: Iterable[SourceResource] | None = None
) -> tuple[dict[str, Any], list[SourceResource]]:
    resources = sorted(
        collect_source_resources(root) if resources is None else list(resources),
        key=lambda resource: resource.relative_path.as_posix(),
    )
    source_bundle_hash = calculate_source_bundle_hash(resources)
    projected_snapshot_bundle_hash = calculate_projected_snapshot_bundle_hash(
        resources
    )
    epoch = _read_build_epoch(root)
    generated_at = datetime.fromtimestamp(epoch, tz=UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    entries = [resource.manifest_entry() for resource in resources]
    registry = {
        "build_epoch": epoch,
        "build_source_revision": source_bundle_hash,
        "build_source_revision_kind": "canonical_source_bundle_sha256",
        "bundle_version": _read_bundle_version(root),
        "file_count": len(entries),
        "generated_at": generated_at,
        "openapi_document_count": sum(
            entry["kind"] == "openapi" for entry in entries
        ),
        "projected_snapshot_bundle_hash": projected_snapshot_bundle_hash,
        "projection_tool_identity": PROJECTION_TOOL_IDENTITY,
        "projection_tool_version": PROJECTION_TOOL_VERSION,
        "registry_format_version": REGISTRY_FORMAT_VERSION,
        "resource_count": len(entries),
        "resources": entries,
        "schema_count": sum(entry["kind"] == "json_schema" for entry in entries),
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "source_revision": source_bundle_hash,
        "source_revision_kind": "canonical_source_bundle_sha256",
        "source_bundle_hash": source_bundle_hash,
    }
    return registry, resources


def _registry_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _expected_files(
    root: Path, resources: Iterable[SourceResource] | None = None
) -> tuple[
    dict[PurePosixPath, bytes], int, dict[str, Any], list[SourceResource]
]:
    registry, collected = build_registry_document(root, resources)
    expected = {
        resource.relative_path: resource.content for resource in collected
    }
    expected[REGISTRY_RELATIVE_PATH] = _registry_bytes(registry)
    return expected, registry["build_epoch"], registry, collected


def _inventory(destination: Path) -> dict[PurePosixPath, Path]:
    if _is_link_like(destination):
        raise CanonicalMaterializationError(
            f"canonical projection root must not be a symlink: {destination}"
        )
    if not destination.exists():
        return {}
    inventory: dict[PurePosixPath, Path] = {}
    for path in destination.rglob("*"):
        if _is_link_like(path):
            raise CanonicalMaterializationError(
                f"canonical projection must not contain symlinks: {path}"
            )
        if path.is_file():
            relative = PurePosixPath(path.relative_to(destination).as_posix())
            inventory[relative] = path
    return inventory


def _is_link_like(path: Path) -> bool:
    """Recognize symlinks and Windows junctions without resolving them."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _destination_path(root: Path, destination: Path | None) -> Path:
    """Select a destination while preserving link identity for rejection."""
    selected = (
        destination
        if destination is not None
        else root / "src" / "epistemic_foundry" / "_canonical"
    )
    selected = selected.absolute()
    for candidate in (selected, *selected.parents):
        if _is_link_like(candidate):
            raise CanonicalMaterializationError(
                f"canonical projection path must not traverse a link: {candidate}"
            )
    return selected


def _assert_projection_owned(
    destination: Path,
    actual: dict[PurePosixPath, Path],
    expected: dict[PurePosixPath, bytes],
) -> set[PurePosixPath]:
    """Fail closed unless a non-empty destination is a known projection.

    The registry document is the ownership marker.  Existing files that are
    not registered by that marker, or that are outside the new projection,
    are never deleted or overwritten.
    """
    if not actual:
        return set()
    marker = actual.get(REGISTRY_RELATIVE_PATH)
    if marker is None:
        raise CanonicalMaterializationError(
            "non-empty canonical projection destination has no registry ownership marker"
        )
    try:
        manifest = json.loads(marker.read_text(encoding="utf-8"))
        resources = manifest["resources"]
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalMaterializationError(
            "canonical projection ownership marker is unreadable or malformed"
        ) from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in (
        1,
        REGISTRY_SCHEMA_VERSION,
    ):
        raise CanonicalMaterializationError(
            "canonical projection ownership marker has an unsupported schema"
        )
    if not isinstance(resources, list):
        raise CanonicalMaterializationError(
            "canonical projection ownership marker has no resource list"
        )
    schema_version = manifest.get("schema_version")
    if schema_version == REGISTRY_SCHEMA_VERSION:
        required_fields = {
            "build_source_revision",
            "build_source_revision_kind",
            "file_count",
            "projected_snapshot_bundle_hash",
            "projection_tool_identity",
            "projection_tool_version",
            "registry_format_version",
            "resource_count",
            "source_bundle_hash",
            "source_revision",
            "source_revision_kind",
        }
        missing_fields = sorted(required_fields - set(manifest))
        if missing_fields:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker is missing v2 fields: "
                f"{missing_fields}"
            )
        if (
            manifest.get("registry_format_version") != REGISTRY_FORMAT_VERSION
            or manifest.get("projection_tool_identity")
            != PROJECTION_TOOL_IDENTITY
            or manifest.get("projection_tool_version") != PROJECTION_TOOL_VERSION
            or manifest.get("build_source_revision_kind")
            != "canonical_source_bundle_sha256"
            or manifest.get("source_revision_kind")
            != "canonical_source_bundle_sha256"
            or manifest.get("build_source_revision")
            != manifest.get("source_bundle_hash")
            or manifest.get("source_revision")
            != manifest.get("source_bundle_hash")
        ):
            raise CanonicalMaterializationError(
                "canonical projection ownership marker has invalid v2 bindings"
            )
    registered: set[PurePosixPath] = set()
    verified_resources: list[tuple[dict[str, Any], bytes]] = []
    for entry in resources:
        value = entry.get("relative_path") if isinstance(entry, dict) else None
        if not isinstance(value, str) or not value or "\\" in value:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker contains an unsafe path"
            )
        relative = PurePosixPath(value)
        if relative.is_absolute() or "." in relative.parts or ".." in relative.parts:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker contains an unsafe path"
            )
        if relative in registered:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker contains duplicate paths"
            )
        registered.add(relative)
        resource_path = actual.get(relative)
        if resource_path is None:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker references a missing file"
            )
        content = resource_path.read_bytes()
        expected_hash = entry.get("sha256")
        if (
            not isinstance(expected_hash, str)
            or not SHA256_PATTERN.fullmatch(expected_hash)
            or expected_hash != SHA256_PREFIX + hashlib.sha256(content).hexdigest()
            or entry.get("byte_size") != len(content)
        ):
            raise CanonicalMaterializationError(
                "canonical projection ownership marker does not match its resources"
            )
        if schema_version == REGISTRY_SCHEMA_VERSION:
            source_value = entry.get("source_path")
            package_value = entry.get("package_path")
            if (
                not isinstance(source_value, str)
                or not isinstance(package_value, str)
                or source_value != relative.as_posix()
                or package_value != relative.as_posix()
            ):
                raise CanonicalMaterializationError(
                    "canonical projection ownership marker has inconsistent source/package paths"
                )
        verified_resources.append((entry, content))
    unregistered = sorted(
        path.as_posix()
        for path in set(actual) - {REGISTRY_RELATIVE_PATH} - registered
    )
    if unregistered:
        raise CanonicalMaterializationError(
            "canonical projection destination contains unregistered files; "
            f"refusing to modify it: {unregistered}"
        )
    if manifest.get("resource_count") != len(registered) or (
        schema_version == REGISTRY_SCHEMA_VERSION
        and manifest.get("file_count") != len(registered)
    ):
        raise CanonicalMaterializationError(
            "canonical projection ownership marker has an invalid resource count"
        )
    if schema_version == 1:
        digest = hashlib.sha256()
        for entry, content in sorted(
            verified_resources, key=lambda item: item[0]["relative_path"]
        ):
            digest.update(entry["relative_path"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
            digest.update(b"\0")
        if manifest.get("source_bundle_hash") != SHA256_PREFIX + digest.hexdigest():
            raise CanonicalMaterializationError(
                "canonical projection ownership marker has an invalid legacy bundle hash"
            )
    else:
        source_entries = []
        snapshot_entries = []
        for entry, content in sorted(
            verified_resources, key=lambda item: str(item[0].get("package_path"))
        ):
            source_path = entry.get("source_path")
            package_path = entry.get("package_path")
            if not isinstance(source_path, str) or not isinstance(
                package_path, str
            ):
                raise CanonicalMaterializationError(
                    "canonical projection ownership marker has malformed source/package paths"
                )
            content_hash = _sha256_identifier(content)
            source_entries.append(
                {
                    "path": source_path,
                    "sha256": content_hash,
                    "size": len(content),
                    "target_path": package_path,
                }
            )
            snapshot_entries.append(
                {
                    "byte_size": len(content),
                    "path": package_path,
                    "sha256": content_hash,
                    "target_path": package_path,
                }
            )
        source_hash = _sha256_identifier(
            _canonical_json_bytes({"algorithm": "sha256", "entries": source_entries})
        )
        snapshot_hash = _sha256_identifier(
            _canonical_json_bytes(
                {"algorithm": "sha256", "entries": snapshot_entries}
            )
        )
        if manifest.get("source_bundle_hash") != source_hash:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker has an invalid source bundle hash"
            )
        if manifest.get("projected_snapshot_bundle_hash") != snapshot_hash:
            raise CanonicalMaterializationError(
                "canonical projection ownership marker has an invalid snapshot bundle hash"
            )
    return registered - set(expected)


def _verify_expected_files(
    destination: Path, expected: dict[PurePosixPath, bytes]
) -> dict[str, Any]:
    actual = _inventory(destination)
    missing = sorted(path.as_posix() for path in set(expected) - set(actual))
    extra = sorted(path.as_posix() for path in set(actual) - set(expected))
    mismatches = sorted(
        path.as_posix()
        for path in set(expected) & set(actual)
        if actual[path].read_bytes() != expected[path]
    )
    return {
        "destination": str(destination),
        "expected_file_count": len(expected),
        "extra": extra,
        "mismatches": mismatches,
        "missing": missing,
        "status": "PASS" if not missing and not extra and not mismatches else "FAIL",
    }


def _source_hash(root: Path) -> str:
    return calculate_source_bundle_hash(collect_source_resources(root))


def _assert_source_unchanged(root: Path, sealed_hash: str) -> None:
    try:
        current_hash = _source_hash(root)
    except (CanonicalMaterializationError, OSError):
        raise CanonicalMaterializationError(
            SOURCE_CHANGED_DURING_PROJECTION
        ) from None
    if current_hash != sealed_hash:
        raise CanonicalMaterializationError(SOURCE_CHANGED_DURING_PROJECTION)


def _empty_directories(destination: Path) -> list[PurePosixPath]:
    """Return only empty user directories so atomic replacement preserves them."""
    if not destination.is_dir():
        return []
    directories: list[PurePosixPath] = []
    for path in sorted(destination.rglob("*"), key=lambda item: len(item.parts)):
        if path.is_dir() and not any(path.iterdir()):
            directories.append(PurePosixPath(path.relative_to(destination).as_posix()))
    return directories


def _write_staged_tree(
    staging: Path,
    expected: dict[PurePosixPath, bytes],
    epoch: int,
    preserved_empty_directories: Iterable[PurePosixPath],
) -> None:
    for relative, content in sorted(
        expected.items(), key=lambda item: item[0].as_posix()
    ):
        path = staging / Path(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        os.utime(path, (epoch, epoch))
    for relative in preserved_empty_directories:
        (staging / Path(*relative.parts)).mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    if _is_link_like(path) or not path.is_dir():
        raise CanonicalMaterializationError(
            f"refusing to remove non-directory projection staging path: {path}"
        )
    shutil.rmtree(path)


def _reserve_absent_sibling(destination: Path, label: str) -> Path:
    reserved = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.{label}-", dir=str(destination.parent)
        )
    )
    reserved.rmdir()
    return reserved


def _rollback_after_swap(
    destination: Path, backup: Path | None, failed_tree: Path
) -> None:
    rollback_error: BaseException | None = None
    try:
        if destination.exists():
            os.replace(destination, failed_tree)
        if backup is not None and backup.exists():
            os.replace(backup, destination)
    except BaseException as error:
        rollback_error = error
    finally:
        if failed_tree.exists():
            _remove_tree(failed_tree)
    if rollback_error is not None:
        raise CanonicalMaterializationError(
            "canonical projection rollback failed"
        ) from rollback_error


def verify_projection(root: Path, destination: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    destination = _destination_path(root, destination)
    expected, _epoch, _registry, _resources = _expected_files(root)
    return _verify_expected_files(destination, expected)


def materialize(root: Path, destination: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    destination = _destination_path(root, destination)
    resources = collect_source_resources(root)
    sealed_source_hash = calculate_source_bundle_hash(resources)
    expected, epoch, registry, resources = _expected_files(root, resources)
    actual = _inventory(destination)
    _assert_projection_owned(destination, actual, expected)
    changed = sum(
        1
        for relative, content in expected.items()
        if relative not in actual or actual[relative].read_bytes() != content
    ) + len(set(actual) - set(expected))
    if changed == 0:
        _assert_source_unchanged(root, sealed_source_hash)
        verification = _verify_expected_files(destination, expected)
        _assert_source_unchanged(root, sealed_source_hash)
        verification.update(
            {
                "atomic_replacement": "NOT_REQUIRED_ALREADY_CURRENT",
                "changed_file_count": 0,
                "projected_snapshot_bundle_hash": registry[
                    "projected_snapshot_bundle_hash"
                ],
                "source_bundle_hash": sealed_source_hash,
                "source_resource_count": len(resources),
            }
        )
        return verification

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-", dir=str(destination.parent)
        )
    )
    backup: Path | None = None
    swapped = False
    try:
        _write_staged_tree(
            staging, expected, epoch, _empty_directories(destination)
        )
        staged_verification = _verify_expected_files(staging, expected)
        if staged_verification["status"] != "PASS":
            raise CanonicalMaterializationError(
                f"canonical projection staging verification failed: {staged_verification}"
            )
        _assert_source_unchanged(root, sealed_source_hash)

        if destination.exists():
            backup = _reserve_absent_sibling(destination, "backup")
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
            swapped = True
        except BaseException:
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise

        try:
            verification = _verify_expected_files(destination, expected)
            if verification["status"] != "PASS":
                raise CanonicalMaterializationError(
                    f"canonical projection verification failed: {verification}"
                )
            _assert_source_unchanged(root, sealed_source_hash)
        except BaseException:
            failed_tree = _reserve_absent_sibling(destination, "failed")
            _rollback_after_swap(destination, backup, failed_tree)
            backup = None
            swapped = False
            raise
        if backup is not None:
            _remove_tree(backup)
            backup = None
    finally:
        if staging.exists():
            _remove_tree(staging)
        # A remaining backup means replacement or rollback did not finish.
        # Never delete it in generic cleanup: it is the only recovery copy of
        # the previously verified projection.

    verification.update(
        {
            "atomic_replacement": "PASS",
            "changed_file_count": changed,
            "projected_snapshot_bundle_hash": registry[
                "projected_snapshot_bundle_hash"
            ],
            "source_bundle_hash": sealed_source_hash,
            "source_resource_count": len(resources),
        }
    )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            verify_projection(args.root, args.destination)
            if args.check
            else materialize(args.root, args.destination)
        )
    except CanonicalMaterializationError as error:
        result = {"error": str(error), "status": "FAIL"}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
