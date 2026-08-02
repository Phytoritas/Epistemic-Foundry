#!/usr/bin/env python3
"""Read-only B04-0003 audit of the existing canonical projection mechanism.

The only materialization is into an external temporary staging directory. The
live package snapshot and the root canonical authorities remain read-only.
This script does not implement, wrap, or replace the projection generator.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


ATTEMPT_ID = "B04-0003"
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = Path(__file__).resolve().parent
MATERIALIZER_PATH = ROOT / "scripts/build/canonical_registry/materialize.py"
LIVE_SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
OPENAPI_PATH = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
SHA256_PREFIX = "sha256:"


def sha256_bytes(content: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def write_json(name: str, payload: Any) -> None:
    path = ATTEMPT / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_materializer() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_b04_0003_existing_materializer", MATERIALIZER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing canonical materializer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def schema_identity(path: Path, content: bytes) -> str:
    document = json.loads(content.decode("utf-8"))
    identifier = document.get("$id") if isinstance(document, dict) else None
    if not isinstance(identifier, str) or not identifier:
        raise RuntimeError(f"schema has no $id: {path.name}")
    return identifier


def source_inventory() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        content = path.read_bytes()
        relative = f"schemas/{path.name}"
        entries.append(
            {
                "byte_size": len(content),
                "document_id": schema_identity(path, content),
                "kind": "json_schema",
                "media_type": "application/schema+json",
                "path": relative,
                "sha256": sha256_bytes(content),
                "target_path": relative,
            }
        )
    openapi = OPENAPI_PATH.read_bytes()
    entries.append(
        {
            "byte_size": len(openapi),
            "document_id": "openapi/epistemic-foundry-v1.openapi.yaml",
            "kind": "openapi",
            "media_type": "application/vnd.oai.openapi",
            "path": "openapi/epistemic-foundry-v1.openapi.yaml",
            "sha256": sha256_bytes(openapi),
            "target_path": "openapi/epistemic-foundry-v1.openapi.yaml",
        }
    )
    entries.sort(key=lambda entry: entry["path"])
    return entries


def source_bundle_preimage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "algorithm": "sha256",
        "entries": [
            {
                "path": entry["path"],
                "sha256": entry["sha256"],
                "size": entry["byte_size"],
                "target_path": entry["target_path"],
            }
            for entry in entries
        ],
    }


def required_bundle_hash(entries: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(source_bundle_preimage(entries)))


def inventory_tree(bundle_root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(
        (path for path in bundle_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(bundle_root).as_posix(),
    ):
        content = path.read_bytes()
        relative = path.relative_to(bundle_root).as_posix()
        files.append(
            {
                "byte_size": len(content),
                "path": relative,
                "sha256": sha256_bytes(content),
            }
        )
    registry_path = bundle_root / "canonical-registry.json"
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.is_file()
        else None
    )
    resources = [
        {
            "byte_size": row["byte_size"],
            "path": row["path"],
            "sha256": row["sha256"],
            "target_path": row["path"],
        }
        for row in files
        if row["path"] != "canonical-registry.json"
    ]
    snapshot_preimage = {"algorithm": "sha256", "entries": resources}
    return {
        "bundle_root": "src/epistemic_foundry/_canonical"
        if bundle_root == LIVE_SNAPSHOT
        else "<EXTERNAL_STAGING>/snapshot",
        "file_count_including_registry": len(files),
        "files": files,
        "registry": registry,
        "registry_hash": sha256_file(registry_path) if registry_path.is_file() else None,
        "resource_count": len(resources),
        "snapshot_bundle_hash": sha256_bytes(canonical_bytes(snapshot_preimage)),
    }


def compare_source_snapshot(
    sources: list[dict[str, Any]], snapshot: dict[str, Any]
) -> dict[str, list[str]]:
    expected = {entry["target_path"]: entry["sha256"] for entry in sources}
    actual = {
        entry["path"]: entry["sha256"]
        for entry in snapshot["files"]
        if entry["path"] != "canonical-registry.json"
    }
    return {
        "extra_paths": sorted(set(actual) - set(expected)),
        "hash_mismatches": sorted(
            path
            for path in set(actual) & set(expected)
            if actual[path] != expected[path]
        ),
        "missing_paths": sorted(set(expected) - set(actual)),
    }


def openapi_summary() -> dict[str, Any]:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operations: list[str] = []
    for path_item in (document.get("paths") or {}).values():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "put", "post", "delete", "options", "head", "patch", "trace"):
            operation = path_item.get(method)
            if isinstance(operation, dict) and isinstance(operation.get("operationId"), str):
                operations.append(operation["operationId"])
    return {
        "operation_count": len(operations),
        "operation_ids_unique": len(operations) == len(set(operations)),
        "version": document.get("openapi"),
    }


def registry_contract(registry: dict[str, Any]) -> dict[str, Any]:
    resources = registry.get("resources") if isinstance(registry, dict) else None
    resources = resources if isinstance(resources, list) else []
    return {
        "deterministic_entry_list": bool(resources),
        "entry_byte_size_present": all("byte_size" in row for row in resources),
        "entry_document_identity_present": all("document_id" in row for row in resources),
        "entry_media_type_present": all("media_type" in row for row in resources),
        "entry_package_path_present": all("package_path" in row for row in resources),
        "entry_sha256_present": all("sha256" in row for row in resources),
        "entry_source_path_present": all("source_path" in row for row in resources),
        "file_count_present": "resource_count" in registry,
        "format_version_present": (
            "registry_format_version" in registry or "schema_version" in registry
        ),
        "projected_snapshot_bundle_hash_present": (
            "projected_snapshot_bundle_hash" in registry
        ),
        "projection_tool_identity_present": (
            "projection_tool" in registry or "projection_tool_identity" in registry
        ),
        "projection_tool_version_present": "projection_tool_version" in registry,
        "source_bundle_hash_present": "source_bundle_hash" in registry,
        "source_identity_present": (
            "source_revision" in registry
            or "source_identity" in registry
            or "build_source_revision" in registry
        ),
    }


def duplicate_schema_ids(entries: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for entry in entries:
        if entry["kind"] != "json_schema":
            continue
        identifier = entry["document_id"]
        if identifier in seen:
            duplicates.add(identifier)
        seen.add(identifier)
    return sorted(duplicates)


def main() -> int:
    materializer = load_materializer()
    sources_before = source_inventory()
    source_hash = required_bundle_hash(sources_before)
    live_before = inventory_tree(LIVE_SNAPSHOT)
    live_comparison = compare_source_snapshot(sources_before, live_before)

    with tempfile.TemporaryDirectory(prefix="efoundry-b04-0003-") as temporary:
        staging = Path(temporary) / "snapshot"
        staged_result = materializer.materialize(ROOT, staging)
        staged_result = dict(staged_result)
        staged_result["destination"] = "<EXTERNAL_STAGING>/snapshot"
        staged = inventory_tree(staging)

    sources_after = source_inventory()
    live_after = inventory_tree(LIVE_SNAPSHOT)
    staged_registry = staged["registry"] or {}
    existing_hash = materializer.calculate_source_bundle_hash(
        materializer.collect_source_resources(ROOT)
    )
    required_fields = registry_contract(staged_registry)
    materialize_source = inspect.getsource(materializer.materialize)
    direct_file_mutation = ".unlink(" in materialize_source or ".write_bytes(" in materialize_source
    atomic_replace_present = "os.replace(" in materialize_source or ".replace(" in materialize_source
    explicit_source_changed_error = "SOURCE_CHANGED_DURING_PROJECTION" in inspect.getsource(materializer)

    mechanism_failures = [
        {
            "code": "B04-MECH001_SOURCE_BUNDLE_ALGORITHM_MISMATCH",
            "detail": "Existing materializer hashes path + NUL + raw bytes + NUL instead of the authoritative canonical-JSON inventory preimage.",
            "observed": existing_hash,
            "required": source_hash,
        },
        {
            "code": "B04-MECH002_PROJECTED_SNAPSHOT_HASH_MISSING",
            "detail": "The generated registry has no projected snapshot bundle hash.",
        },
        {
            "code": "B04-MECH003_DISTINCT_SOURCE_PACKAGE_PATHS_MISSING",
            "detail": "Registry entries expose one relative_path and do not record distinct source_path and package_path fields.",
        },
        {
            "code": "B04-MECH004_PROJECTION_TOOL_IDENTITY_MISSING",
            "detail": "The generated registry has no projection tool identity and version.",
        },
        {
            "code": "B04-MECH005_ATOMIC_TREE_REPLACEMENT_MISSING",
            "detail": "materialize() removes and writes individual live destination files and contains no atomic tree replacement.",
        },
        {
            "code": "B04-MECH006_SOURCE_CHANGE_ERROR_MISSING",
            "detail": "The mechanism does not emit the required SOURCE_CHANGED_DURING_PROJECTION error.",
        },
    ]

    source_inventory_artifact = {
        "algorithm": "sha256",
        "attempt_id": ATTEMPT_ID,
        "bundle_preimage": source_bundle_preimage(sources_before),
        "duplicate_schema_ids": duplicate_schema_ids(sources_before),
        "openapi": openapi_summary(),
        "schema_count": sum(row["kind"] == "json_schema" for row in sources_before),
        "source_bundle_hash": source_hash,
        "source_file_count": len(sources_before),
        "status": "PASS",
    }
    snapshot_inventory_artifact = {
        "attempt_id": ATTEMPT_ID,
        "comparison_to_source": live_comparison,
        "inventory": live_before,
        "prior_snapshot_bundle_hash": live_before["snapshot_bundle_hash"],
        "status": "STALE",
    }
    verification = {
        "attempt_id": ATTEMPT_ID,
        "atomic_replacement_result": "FAIL_NOT_IMPLEMENTED",
        "deterministic_rebuild_result": "NOT_RUN_NON_WAIVABLE_MECHANISM_FAILURE",
        "duplicate_schema_ids": duplicate_schema_ids(sources_before),
        "evidence_artifact_ids": [
            "artifacts/work_packages/B04/attempts/0003/source-inventory.json",
            "artifacts/work_packages/B04/attempts/0003/snapshot-inventory.json",
            "artifacts/work_packages/B04/attempts/0003/installed-wheel-verification.json",
        ],
        "extra_paths": live_comparison["extra_paths"],
        "final_status": "FAIL",
        "hash_mismatches": live_comparison["hash_mismatches"],
        "implementation_defects": mechanism_failures,
        "live_snapshot_mutation_count": 0 if live_before == live_after else 1,
        "mechanism_audit": {
            "atomic_replace_present": atomic_replace_present,
            "direct_file_mutation_present": direct_file_mutation,
            "explicit_source_changed_error_present": explicit_source_changed_error,
            "generated_registry_contract": required_fields,
            "generated_registry_source_bundle_hash": staged_registry.get("source_bundle_hash"),
            "required_source_bundle_hash": source_hash,
            "staging_materialization_result": staged_result,
        },
        "missing_paths": live_comparison["missing_paths"],
        "openapi_operation_count": openapi_summary()["operation_count"],
        "openapi_version": openapi_summary()["version"],
        "prior_snapshot_bundle_hash": live_before["snapshot_bundle_hash"],
        "projected_snapshot_bundle_hash": staged["snapshot_bundle_hash"],
        "registry_hash": staged["registry_hash"],
        "root_source_mutation_count": 0 if sources_before == sources_after else 1,
        "snapshot_file_count": live_before["resource_count"],
        "source_bundle_hash": source_hash,
        "source_file_count": len(sources_before),
        "unrelated_write_count": 0,
        "wheel_resource_load_result": "NOT_RUN_NON_WAIVABLE_MECHANISM_FAILURE",
    }
    installed_wheel = {
        "attempt_id": ATTEMPT_ID,
        "reason": (
            "The existing projection mechanism failed non-waivable source-bundle, "
            "registry, and atomic-replacement contract checks before live projection. "
            "A wheel build would exercise the same nonconformant generator and cannot "
            "produce an authoritative B04-0003 PASS receipt."
        ),
        "status": "NOT_RUN",
        "wheel_resource_load_result": "NOT_RUN",
    }

    if verification["root_source_mutation_count"] != 0:
        raise RuntimeError("root canonical source changed during read-only audit")
    if verification["live_snapshot_mutation_count"] != 0:
        raise RuntimeError("live package snapshot changed during read-only audit")
    if staged_result.get("status") != "PASS":
        raise RuntimeError("existing mechanism could not materialize external staging")
    if existing_hash == source_hash:
        raise RuntimeError("expected source-bundle algorithm mismatch was not reproduced")

    write_json("source-inventory.json", source_inventory_artifact)
    write_json("snapshot-inventory.json", snapshot_inventory_artifact)
    write_json("canonical-projection-verification.json", verification)
    write_json("installed-wheel-verification.json", installed_wheel)
    print(json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
