#!/usr/bin/env python3
"""Calculate canonical hashes for the S04-0005 authority artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[5]
MANIFEST = ROOT / "manifests/development_manifest.yaml"

FIELDS = {
    "B04": ("exit_criteria", "required_checks"),
    "C01": ("write_scope", "exit_criteria", "required_checks"),
    "C02": ("exit_criteria", "required_checks"),
    "C04": ("exit_criteria", "required_checks"),
    "O02": ("write_scope", "exit_criteria", "required_checks"),
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(relative_path: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {relative_path}")
    return value


def hash_document(relative_path: str, excluded_field: str) -> dict[str, str]:
    document = read_json(relative_path)
    preimage = {
        key: value for key, value in document.items() if key != excluded_field
    }
    return {
        "path": relative_path,
        "excluded_field": excluded_field,
        "canonical_hash": canonical_hash(preimage),
    }


def manifest_fields() -> dict[str, Any]:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = {row["id"]: row for row in manifest["work_packages"]}
    return {
        package_id: {
            field: canonical_hash(packages[package_id][field])
            for field in fields
        }
        for package_id, fields in FIELDS.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    document = subparsers.add_parser("document")
    document.add_argument("path")
    document.add_argument("excluded_field")
    subparsers.add_parser("manifest-fields")
    args = parser.parse_args()

    if args.mode == "document":
        result: Any = hash_document(args.path, args.excluded_field)
    else:
        result = manifest_fields()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
