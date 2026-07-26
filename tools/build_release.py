#!/usr/bin/env python3
"""Build and verify a deterministic Epistemic Foundry v4 spec archive.

The archive contains a specification bundle and a fail-closed reference plugin
blueprint. It does not claim an implemented production plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

EXCLUDED = {"PACKAGE_MANIFEST.json", "MANIFEST.sha256"}
FIXED_ZIP_TIME = (2026, 7, 26, 0, 0, 0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_files(root: Path) -> list[Path]:
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and p.relative_to(root).as_posix() not in EXCLUDED),
        key=lambda p: p.relative_to(root).as_posix(),
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def run_structural_validation(root: Path, output: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(root / "tools/validate_spec_bundle.py"), "--root", str(root), "--json-report", str(output)],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("structural validation failed:\n" + proc.stdout + "\n" + proc.stderr)
    return read_json(output)


def write_manifest(root: Path) -> dict[str, Any]:
    for name in EXCLUDED:
        (root / name).unlink(missing_ok=True)

    spec = read_json(root / "reports/spec_validation_results.json")
    audit = read_json(root / "reports/288_lens_evolution_audit_results.json")
    files = package_files(root)
    entries = [
        {"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        for p in files
    ]
    manifest = {
        "package_name": "Epistemic Foundry v4 Development Specification",
        "package_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "architecture_name": "Epistemic Foundry",
        "scope": "architecture_development_specification_and_fail_closed_reference_blueprint",
        "readiness": {
            "specification_validation": spec.get("summary", {}).get("status", "UNKNOWN"),
            "plugin_blueprint": "REFERENCE_BLUEPRINT_NOT_IMPLEMENTED",
            "architecture_freeze": "CONDITIONAL_PASS",
            "production_implementation": "NOT_CLAIMED",
        },
        "counts": {
            "manifested_files": len(entries),
            "schemas": len(list((root / "schemas").glob("*.schema.json"))),
            "examples_json": len(list((root / "examples").glob("*.json"))),
            "workflows": len(list((root / "workflows").glob("*.workflow.yaml"))),
            "workflow_nodes": spec.get("workflows", {}).get("total_nodes"),
            "prompts": len(list((root / "prompts").rglob("*.md"))),
            "work_packages": spec.get("development", {}).get("work_packages"),
            "invariants": spec.get("development", {}).get("invariants"),
            "plugin_skills": spec.get("plugin_blueprint", {}).get("skills"),
            "plugin_hook_bundles": spec.get("plugin_blueprint", {}).get("hook_bundles"),
            "audit_lenses": audit.get("total"),
        },
        "audit_288": audit.get("summary"),
        "manifest_algorithm": "SHA-256 over final file bytes before manifest creation",
        "excluded_from_recursive_manifest": sorted(EXCLUDED),
        "files": entries,
    }
    manifest_path = root / "PACKAGE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_hash = sha256_file(manifest_path)
    (root / "MANIFEST.sha256").write_text(f"{manifest_hash}  PACKAGE_MANIFEST.json\n", encoding="utf-8")
    return manifest


def create_zip(root: Path, output: Path, prefix: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix())
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{rel}", date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
            archive.writestr(info, path.read_bytes())


def unsafe_zip_name(name: str) -> bool:
    p = PurePosixPath(name)
    return p.is_absolute() or ".." in p.parts or "\\" in name or not name


def verify_manifest(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "PACKAGE_MANIFEST.json"
    manifest = read_json(manifest_path)
    listed: set[str] = set()
    for entry in manifest.get("files", []):
        rel = entry.get("path")
        if not isinstance(rel, str) or rel in listed:
            errors.append(f"invalid or duplicate manifest path: {rel}")
            continue
        listed.add(rel)
        path = root / rel
        if not path.exists():
            errors.append(f"manifested file missing: {rel}")
        elif sha256_file(path) != entry.get("sha256") or path.stat().st_size != entry.get("bytes"):
            errors.append(f"manifest hash/size mismatch: {rel}")
    actual = {p.relative_to(root).as_posix() for p in package_files(root)}
    if listed != actual:
        errors.append(f"manifest inventory mismatch missing={sorted(actual-listed)[:20]} extra={sorted(listed-actual)[:20]}")
    expected = (root / "MANIFEST.sha256").read_text(encoding="utf-8").strip().split()[0]
    if expected != sha256_file(manifest_path):
        errors.append("MANIFEST.sha256 mismatch")
    return errors


def verify_zip(root: Path, output: Path, prefix: str) -> dict[str, Any]:
    manifest_errors = verify_manifest(root)
    with zipfile.ZipFile(output, "r") as archive:
        names = archive.namelist()
        crc_error = archive.testzip()
        duplicates = sorted({n for n in names if names.count(n) > 1})
        unsafe = sorted(n for n in names if unsafe_zip_name(n))
        expected = {
            f"{prefix}/{p.relative_to(root).as_posix()}": sha256_file(p)
            for p in root.rglob("*") if p.is_file()
        }
        actual = set(names)
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        hash_mismatches = [n for n, h in expected.items() if n in actual and hashlib.sha256(archive.read(n)).hexdigest() != h]

    extraction_errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="efoundry-v4-verify-") as temp:
        temp_root = Path(temp)
        with zipfile.ZipFile(output, "r") as archive:
            archive.extractall(temp_root)
        extracted = temp_root / prefix
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            target = extracted / rel
            if not target.exists() or sha256_file(target) != sha256_file(p):
                extraction_errors.append(rel.as_posix())

    failed = any([manifest_errors, crc_error, duplicates, unsafe, missing, extra, hash_mismatches, extraction_errors])
    return {
        "zip_path": str(output),
        "zip_bytes": output.stat().st_size,
        "zip_sha256": sha256_file(output),
        "entries": len(names),
        "manifest_errors": manifest_errors,
        "crc_error_entry": crc_error,
        "duplicate_entries": duplicates,
        "unsafe_entries": unsafe,
        "missing_entries": missing,
        "extra_entries": extra,
        "hash_mismatches": hash_mismatches,
        "clean_extraction_mismatches": extraction_errors,
        "status": "FAIL" if failed else "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", default="epistemic_foundry_v4_spec")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    # Normalize pre-build state so repeated builds do not inherit a previous manifest.
    for name in EXCLUDED:
        (root / name).unlink(missing_ok=True)
    # First validation writes the canonical pre-build report inside the bundle.
    run_structural_validation(root, root / "reports/spec_validation_results.json")
    write_manifest(root)
    # Second validation checks the manifest but writes outside the bundle, avoiding self-mutation.
    with tempfile.TemporaryDirectory(prefix="efoundry-v4-validation-") as temp:
        run_structural_validation(root, Path(temp) / "post_manifest_validation.json")
    create_zip(root, args.output.resolve(), args.prefix)
    result = verify_zip(root, args.output.resolve(), args.prefix)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
