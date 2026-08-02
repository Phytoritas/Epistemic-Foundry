#!/usr/bin/env python3
"""Capture byte-bound B04-0006 root and package projection inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0006"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
sys.path.insert(0, str(ROOT))

from scripts.build.canonical_registry.materialize import (  # noqa: E402
    _registry_bytes,
    build_registry_document,
)


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(name: str, value: dict[str, object]) -> None:
    (ATTEMPT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def capture(stage: str) -> dict[str, object]:
    registry, resources = build_registry_document(ROOT)
    source_entries: list[dict[str, object]] = []
    snapshot_entries: list[dict[str, object]] = []
    missing: list[str] = []
    mismatches: list[str] = []
    expected_paths: set[str] = set()
    document_ids: set[str] = set()
    duplicates: list[str] = []

    for resource in resources:
        entry = resource.manifest_entry()
        relative = resource.relative_path.as_posix()
        expected_paths.add(relative)
        document_id = str(entry["document_id"])
        if document_id in document_ids:
            duplicates.append(document_id)
        document_ids.add(document_id)
        source_entries.append(
            {
                "byte_size": entry["byte_size"],
                "document_id": document_id,
                "media_type": entry["media_type"],
                "path": relative,
                "projection_target_path": entry["package_path"],
                "sha256": entry["sha256"],
            }
        )
        target = SNAPSHOT / Path(*resource.relative_path.parts)
        if not target.is_file():
            missing.append(relative)
            continue
        observed_hash = sha256_file(target)
        snapshot_entries.append(
            {
                "byte_size": target.stat().st_size,
                "document_id": document_id,
                "package_path": relative,
                "sha256": observed_hash,
                "source_path": entry["source_path"],
            }
        )
        if observed_hash != entry["sha256"] or target.read_bytes() != resource.content:
            mismatches.append(relative)

    actual_paths = {
        path.relative_to(SNAPSHOT).as_posix()
        for path in SNAPSHOT.rglob("*")
        if path.is_file() and path.name != "canonical-registry.json"
    }
    extra = sorted(actual_paths - expected_paths)
    missing = sorted(set(missing) | (expected_paths - actual_paths))
    registry_path = SNAPSHOT / "canonical-registry.json"
    registry_current = registry_path.is_file() and (
        registry_path.read_bytes() == _registry_bytes(registry)
    )
    common = {
        "attempt_id": "B04-0006",
        "captured_stage": stage,
        "duplicate_schema_ids": sorted(duplicates),
        "expected_registry_sha256": sha256_bytes(_registry_bytes(registry)),
        "openapi_resource_count": registry["openapi_document_count"],
        "projected_snapshot_bundle_hash": registry[
            "projected_snapshot_bundle_hash"
        ],
        "schema_count": registry["schema_count"],
        "source_bundle_hash": registry["source_bundle_hash"],
        "source_resource_count": len(source_entries),
    }
    source = {
        **common,
        "entries": source_entries,
        "status": "PASS" if not duplicates else "FAIL",
    }
    snapshot = {
        **common,
        "comparison_to_source": {
            "extra_paths": extra,
            "hash_mismatches": sorted(mismatches),
            "missing_paths": missing,
            "status": (
                "PASS"
                if not missing and not extra and not mismatches and registry_current
                else "STALE"
            ),
        },
        "entries": snapshot_entries,
        "observed_registry_sha256": (
            sha256_file(registry_path) if registry_path.is_file() else None
        ),
        "projection_file_count_including_registry": sum(
            path.is_file() for path in SNAPSHOT.rglob("*")
        ),
        "registry_matches_expected": registry_current,
        "snapshot_resource_count": len(snapshot_entries),
    }
    write_json(f"source-inventory-{stage}.json", source)
    write_json(f"snapshot-inventory-{stage}.json", snapshot)
    return {
        "source": common,
        "snapshot_status": snapshot["comparison_to_source"],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("preprojection", "postprojection"))
    args = parser.parse_args()
    result = capture(args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
