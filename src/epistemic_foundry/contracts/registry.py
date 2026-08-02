"""Load and integrity-check the packaged canonical contract snapshot.

Repository-root ``schemas/`` and ``openapi/`` are source authorities.  Runtime
code reads only the build-time package-resource projection and never falls back
to the checkout, current directory, or an editable-install-only path.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_SUFFIX = ".schema.json"
REGISTRY_FILE = "canonical-registry.json"
OPENAPI_MEDIA_TYPE = "application/vnd.oai.openapi"
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REGISTRY_SCHEMA_VERSION = 2
REGISTRY_FORMAT_VERSION = "2.0.0"
PROJECTION_TOOL_IDENTITY = "epistemic_foundry.canonical_registry.materialize"
PROJECTION_TOOL_VERSION = "2.0.0"
SOURCE_REVISION_KIND = "canonical_source_bundle_sha256"

CANONICAL_REGISTRY_MISSING = "CANONICAL_REGISTRY_MISSING"
CANONICAL_REGISTRY_HASH_MISMATCH = "CANONICAL_REGISTRY_HASH_MISMATCH"
CANONICAL_REGISTRY_DUPLICATE_ID = "CANONICAL_REGISTRY_DUPLICATE_ID"


class CanonicalRegistryError(RuntimeError):
    """A fail-closed canonical package-resource integrity error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class SchemaNotFound(LookupError):
    """Raised when a requested canonical schema does not exist."""


def repo_root() -> Path:
    """Return the source checkout root for development-only corpus tests.

    This compatibility helper is deliberately not used by ``default_registry``
    and is not a runtime resource fallback.
    """
    return Path(__file__).resolve().parents[3]


class SchemaRegistry:
    """Verified canonical resources plus validators, keyed by schema name."""

    def __init__(self, bundle_root: Traversable | Path) -> None:
        self._bundle_root = bundle_root
        self._schema_dir = bundle_root.joinpath("schemas")
        self._resource_bytes: dict[str, bytes] = {}
        self._manifest = self._load_and_verify()

    @property
    def schema_dir(self) -> Traversable:
        return self._schema_dir

    @property
    def bundle_root(self) -> Traversable:
        return self._bundle_root

    @property
    def manifest(self) -> dict[str, Any]:
        """Return a defensive copy of the verified registry manifest."""
        return deepcopy(self._manifest)

    def names(self) -> list[str]:
        """Sorted canonical schema names (file stem without `.schema`)."""
        return sorted(
            PurePosixPath(entry["relative_path"]).name[: -len(SCHEMA_SUFFIX)]
            for entry in self._manifest["resources"]
            if entry["kind"] == "json_schema"
        )

    @staticmethod
    def _safe_relative_path(value: object) -> PurePosixPath:
        if not isinstance(value, str) or not value or "\\" in value:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                f"invalid canonical resource path: {value!r}",
            )
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                f"unsafe canonical resource path: {value!r}",
            )
        return path

    def _node(self, relative_path: PurePosixPath) -> Traversable:
        node = self._bundle_root
        for part in relative_path.parts:
            node = node.joinpath(part)
        return node

    def _read_required(self, relative_path: PurePosixPath) -> bytes:
        node = self._node(relative_path)
        try:
            if not node.is_file():
                raise FileNotFoundError(relative_path.as_posix())
            return node.read_bytes()
        except (FileNotFoundError, OSError) as error:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_MISSING,
                f"canonical package resource is missing: {relative_path.as_posix()}",
            ) from error

    def _package_inventory(self) -> set[str]:
        inventory: set[str] = set()

        def walk(node: Traversable, prefix: PurePosixPath) -> None:
            try:
                children = list(node.iterdir())
            except (FileNotFoundError, OSError) as error:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_MISSING,
                    f"canonical package-resource root is missing: {self._bundle_root}",
                ) from error
            for child in children:
                relative = prefix / child.name
                if child.is_dir():
                    walk(child, relative)
                elif child.is_file():
                    inventory.add(relative.as_posix())

        try:
            if not self._bundle_root.is_dir():
                raise FileNotFoundError(str(self._bundle_root))
        except (FileNotFoundError, OSError) as error:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_MISSING,
                "canonical package-resource root is missing",
            ) from error
        walk(self._bundle_root, PurePosixPath())
        return inventory

    @staticmethod
    def _canonical_json_hash(value: object) -> str:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(canonical).hexdigest()

    @classmethod
    def _source_bundle_hash(
        cls, resources: list[tuple[str, str, bytes]]
    ) -> str:
        entries = [
            {
                "path": source_path,
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "target_path": package_path,
            }
            for source_path, package_path, content in sorted(
                resources, key=lambda item: item[0]
            )
        ]
        return cls._canonical_json_hash(
            {"algorithm": "sha256", "entries": entries}
        )

    @classmethod
    def _projected_snapshot_bundle_hash(
        cls, resources: list[tuple[str, bytes]]
    ) -> str:
        entries = [
            {
                "byte_size": len(content),
                "path": package_path,
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "target_path": package_path,
            }
            for package_path, content in sorted(resources)
        ]
        return cls._canonical_json_hash(
            {"algorithm": "sha256", "entries": entries}
        )

    def _load_and_verify(self) -> dict[str, Any]:
        manifest_bytes = self._read_required(PurePosixPath(REGISTRY_FILE))
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical-registry.json is not valid UTF-8 JSON",
            ) from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != REGISTRY_SCHEMA_VERSION
        ):
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "unsupported or malformed canonical registry document",
            )
        resources = manifest.get("resources")
        if not isinstance(resources, list) or not resources:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_MISSING,
                "canonical registry has no resources",
            )
        required_top_level = {
            "build_epoch",
            "build_source_revision",
            "build_source_revision_kind",
            "bundle_version",
            "file_count",
            "generated_at",
            "openapi_document_count",
            "projected_snapshot_bundle_hash",
            "projection_tool_identity",
            "projection_tool_version",
            "registry_format_version",
            "resource_count",
            "schema_count",
            "source_revision",
            "source_revision_kind",
            "source_bundle_hash",
        }
        missing_top_level = sorted(required_top_level - set(manifest))
        if missing_top_level:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_MISSING,
                f"canonical registry fields are missing: {missing_top_level}",
            )
        if (
            manifest["resource_count"] != len(resources)
            or manifest["file_count"] != len(resources)
        ):
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical registry file/resource count does not match resources",
            )
        epoch = manifest["build_epoch"]
        if not isinstance(epoch, int) or isinstance(epoch, bool):
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical registry build_epoch is not an integer",
            )
        expected_generated_at = datetime.fromtimestamp(epoch, tz=UTC).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        if manifest["generated_at"] != expected_generated_at:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical registry generated_at does not match build_epoch",
            )
        if not isinstance(manifest["bundle_version"], str) or not manifest[
            "bundle_version"
        ]:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical registry bundle_version is invalid",
            )
        for field in (
            "source_bundle_hash",
            "projected_snapshot_bundle_hash",
            "source_revision",
            "build_source_revision",
        ):
            if not isinstance(manifest[field], str) or not SHA256_PATTERN.fullmatch(
                manifest[field]
            ):
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    f"canonical registry {field} is not a SHA-256 identifier",
                )
        if (
            manifest["registry_format_version"] != REGISTRY_FORMAT_VERSION
            or manifest["projection_tool_identity"] != PROJECTION_TOOL_IDENTITY
            or manifest["projection_tool_version"] != PROJECTION_TOOL_VERSION
        ):
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical registry format or projection tool identity is unsupported",
            )
        if (
            manifest["build_source_revision_kind"] != SOURCE_REVISION_KIND
            or manifest["source_revision_kind"] != SOURCE_REVISION_KIND
            or manifest["build_source_revision"] != manifest["source_bundle_hash"]
            or manifest["source_revision"] != manifest["source_bundle_hash"]
        ):
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "source revisions are not bound to the canonical source bundle",
            )

        seen_package_paths: set[str] = set()
        seen_source_paths: set[str] = set()
        seen_ids: dict[str, str] = {}
        verified_source_resources: list[tuple[str, str, bytes]] = []
        verified_snapshot_resources: list[tuple[str, bytes]] = []
        schema_count = 0
        openapi_count = 0
        for entry in resources:
            if not isinstance(entry, dict):
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    "canonical resource entry is not an object",
                )
            required_entry = {
                "byte_size",
                "document_id",
                "kind",
                "media_type",
                "package_path",
                "relative_path",
                "sha256",
                "source_path",
            }
            missing_entry = sorted(required_entry - set(entry))
            if missing_entry:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_MISSING,
                    f"canonical resource fields are missing: {missing_entry}",
                )
            relative = self._safe_relative_path(entry["relative_path"])
            source = self._safe_relative_path(entry["source_path"])
            package = self._safe_relative_path(entry["package_path"])
            relative_path = relative.as_posix()
            source_path = source.as_posix()
            package_path = package.as_posix()
            if relative_path != package_path:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    "canonical resource relative_path is not its package_path",
                )
            if package_path in seen_package_paths:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    f"duplicate canonical package path: {package_path}",
                )
            if source_path in seen_source_paths:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    f"duplicate canonical source path: {source_path}",
                )
            seen_package_paths.add(package_path)
            seen_source_paths.add(source_path)
            document_id = entry["document_id"]
            if not isinstance(document_id, str) or not document_id:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    f"canonical resource has invalid document_id: {relative_path}",
                )
            if document_id in seen_ids:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_DUPLICATE_ID,
                    f"duplicate document ID {document_id!r}: "
                    f"{seen_ids[document_id]}, {relative_path}",
                )
            seen_ids[document_id] = relative_path
            content = self._read_required(package)
            expected_hash = entry["sha256"]
            actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
            if (
                not isinstance(expected_hash, str)
                or not SHA256_PATTERN.fullmatch(expected_hash)
                or expected_hash != actual_hash
                or entry["byte_size"] != len(content)
            ):
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    f"canonical resource integrity mismatch: {relative_path}",
                )
            kind = entry["kind"]
            if kind == "json_schema":
                schema_count += 1
                if entry["media_type"] != "application/schema+json" or not (
                    relative_path.startswith("schemas/")
                    and relative_path.endswith(SCHEMA_SUFFIX)
                ):
                    raise CanonicalRegistryError(
                        CANONICAL_REGISTRY_HASH_MISMATCH,
                        f"invalid JSON Schema resource metadata: {relative_path}",
                    )
                try:
                    document = json.loads(content.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise CanonicalRegistryError(
                        CANONICAL_REGISTRY_HASH_MISMATCH,
                        f"canonical schema is not UTF-8 JSON: {relative_path}",
                    ) from error
                if not isinstance(document, dict) or document.get("$id") != document_id:
                    raise CanonicalRegistryError(
                        CANONICAL_REGISTRY_HASH_MISMATCH,
                        f"canonical schema $id mismatch: {relative_path}",
                    )
            elif kind == "openapi":
                openapi_count += 1
                if entry["media_type"] != OPENAPI_MEDIA_TYPE or not relative_path.startswith(
                    "openapi/"
                ):
                    raise CanonicalRegistryError(
                        CANONICAL_REGISTRY_HASH_MISMATCH,
                        f"invalid OpenAPI resource metadata: {relative_path}",
                    )
            else:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_HASH_MISMATCH,
                    f"unknown canonical resource kind {kind!r}",
                )
            self._resource_bytes[relative_path] = content
            verified_source_resources.append(
                (source_path, package_path, content)
            )
            verified_snapshot_resources.append((package_path, content))

        if manifest["schema_count"] != schema_count or manifest[
            "openapi_document_count"
        ] != openapi_count:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical registry kind counts do not match resources",
            )
        if openapi_count != 1:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_MISSING,
                f"expected one canonical OpenAPI document, found {openapi_count}",
            )
        actual_source_hash = self._source_bundle_hash(verified_source_resources)
        if actual_source_hash != manifest["source_bundle_hash"]:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "canonical source bundle hash does not match packaged resources",
            )
        actual_snapshot_hash = self._projected_snapshot_bundle_hash(
            verified_snapshot_resources
        )
        if actual_snapshot_hash != manifest["projected_snapshot_bundle_hash"]:
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                "projected snapshot bundle hash does not match packaged resources",
            )
        expected_inventory = seen_package_paths | {REGISTRY_FILE}
        actual_inventory = self._package_inventory()
        if actual_inventory != expected_inventory:
            missing = sorted(expected_inventory - actual_inventory)
            extra = sorted(actual_inventory - expected_inventory)
            if missing:
                raise CanonicalRegistryError(
                    CANONICAL_REGISTRY_MISSING,
                    f"canonical package resources are missing: {missing}",
                )
            raise CanonicalRegistryError(
                CANONICAL_REGISTRY_HASH_MISMATCH,
                f"unregistered canonical package resources are present: {extra}",
            )
        return manifest

    def document(self, name: str) -> dict[str, Any]:
        """Return a fresh schema document that cannot mutate registry state."""
        relative_path = f"schemas/{name}{SCHEMA_SUFFIX}"
        content = self._resource_bytes.get(relative_path)
        if content is None:
            raise SchemaNotFound(f"no canonical schema named {name!r}")
        document = json.loads(content.decode("utf-8"))
        if not isinstance(document, dict):
            raise SchemaNotFound(f"schema {name!r} is not a JSON object")
        return document

    def resource_bytes(self, relative_path: str) -> bytes:
        """Return one verified resource by its bundle-relative path."""
        content = self._resource_bytes.get(relative_path)
        if content is None:
            raise SchemaNotFound(f"no canonical resource named {relative_path!r}")
        return content

    def openapi_text(self) -> str:
        """Return the single verified canonical OpenAPI document as UTF-8."""
        paths = [
            entry["relative_path"]
            for entry in self._manifest["resources"]
            if entry["kind"] == "openapi"
        ]
        return self.resource_bytes(paths[0]).decode("utf-8")

    def registry(self) -> Registry:
        """Return a fresh `$ref` registry with caller-isolated resources."""
        resources = []
        for name in self.names():
            document = self.document(name)
            # `$schema` is present in every canonical file, but pass the draft
            # explicitly so a schema missing it still registers as 2020-12
            # instead of raising "unknown specification".
            resource = Resource.from_contents(document, default_specification=DRAFT202012)
            filename = f"{name}{SCHEMA_SUFFIX}"
            identifier = document.get("$id") or filename
            resources.append((str(identifier), resource))
            # Also expose the bare filename so a relative `$ref` resolves.
            resources.append((filename, resource))
        return Registry().with_resources(resources)

    def validator(self, name: str) -> Draft202012Validator:
        """Return a fresh validator isolated from prior caller mutations."""
        return Draft202012Validator(self.document(name), registry=self.registry())


@lru_cache(maxsize=1)
def default_registry() -> SchemaRegistry:
    """Load the integrity-checked package-resource canonical snapshot."""
    return SchemaRegistry(files("epistemic_foundry").joinpath("_canonical"))
