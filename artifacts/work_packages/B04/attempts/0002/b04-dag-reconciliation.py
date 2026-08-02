#!/usr/bin/env python3
"""Recompute the 156-package DAG after the resolving B04 attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts" / "work_packages" / "B04" / "attempts" / "0002"
MANIFEST = ROOT / "manifests" / "development_manifest.yaml"

PASS_REPORTS = {
    "A01": "artifacts/work_packages/A01/report.json",
    "A02": "artifacts/work_packages/A02/report.json",
    "A03": "artifacts/work_packages/A03/report.json",
    "A04": "artifacts/work_packages/A04/report.json",
    "A05": "artifacts/work_packages/A05/attempts/0002/report.json",
    "B01": "artifacts/work_packages/B01/report.json",
    "B02": "artifacts/work_packages/B02/report.json",
    "B03": "artifacts/work_packages/B03/report.json",
    "C01": "artifacts/work_packages/C01/attempts/0004/report.json",
    "C02": "artifacts/work_packages/C02/report.json",
    "C03": "artifacts/work_packages/C03/report.json",
    "C04": "artifacts/work_packages/C04/report.json",
    "S01": "artifacts/work_packages/S01/report.json",
    "S02": "artifacts/work_packages/S02/report.json",
    "S03": "artifacts/work_packages/S03/report.json",
    "S04": "artifacts/work_packages/S04/report.json",
}

HISTORICAL_NON_PASS = {
    "A05-legacy-root": "artifacts/work_packages/A05/report.json",
    "B04-legacy-root": "artifacts/work_packages/B04/report.json",
    "C01-legacy-root": "artifacts/work_packages/C01/report.json",
    "C01-0002": "artifacts/work_packages/C01/attempts/0002/report.json",
    "C01-0003": "artifacts/work_packages/C01/attempts/0003/report.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read required JSON evidence {relative}: {error}")
    if not isinstance(document, dict):
        raise SystemExit(f"required JSON evidence is not an object: {relative}")
    return document


def verified_pass_reports() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for package_id, relative in PASS_REPORTS.items():
        report = read_json(relative)
        if report.get("status") != "PASS":
            raise SystemExit(f"{package_id} evidence is not PASS: {relative}")
        result[package_id] = {
            "attempt_id": str(report.get("attempt_id") or "historical-root-pass"),
            "report": relative,
            "report_sha256": sha256(ROOT / relative),
            "status": "PASS",
        }
    return result


def verified_b04_pass() -> dict[str, Any]:
    verification_path = ATTEMPT / "b04-packaging-verification.json"
    verification = read_json(verification_path.relative_to(ROOT).as_posix())
    if verification.get("status") != "PASS":
        raise SystemExit("B04 packaging verification is not PASS")
    review_path = ATTEMPT / "review.md"
    try:
        review = review_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SystemExit("B04 resolving review is unavailable") from error
    if "Status: `PASS`" not in review or "blocking findings: 0" not in review.lower():
        raise SystemExit("B04 resolving review is not an unblocked PASS")
    receipts = {}
    for kind in ("wheel", "sdist"):
        path = ATTEMPT / f"{kind}.artifact-receipt.json"
        receipt = read_json(path.relative_to(ROOT).as_posix())
        if not str(receipt.get("content_hash", "")).startswith("sha256:"):
            raise SystemExit(f"B04 {kind} receipt does not bind artifact bytes")
        receipts[kind] = {
            "path": path.relative_to(ROOT).as_posix(),
            "receipt_hash": receipt.get("receipt_hash"),
            "sha256": sha256(path),
        }
    return {
        "attempt_id": "B04-0002",
        "packaging_verification": verification_path.relative_to(ROOT).as_posix(),
        "packaging_verification_sha256": sha256(verification_path),
        "receipts": receipts,
        "review": review_path.relative_to(ROOT).as_posix(),
        "review_sha256": sha256(review_path),
        "status": "PASS",
    }


def historical_preservation() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, relative in HISTORICAL_NON_PASS.items():
        report = read_json(relative)
        if report.get("status") == "PASS":
            raise SystemExit(f"historical non-PASS report was overwritten: {relative}")
        result[label] = {
            "path": relative,
            "sha256": sha256(ROOT / relative),
            "status": report.get("status"),
        }
    return result


def topological_layers(
    order: list[str], dependencies: dict[str, set[str]]
) -> list[list[str]]:
    remaining = set(order)
    completed: set[str] = set()
    layers: list[list[str]] = []
    while remaining:
        layer = [
            package_id
            for package_id in order
            if package_id in remaining and dependencies[package_id] <= completed
        ]
        if not layer:
            cycle = sorted(remaining)
            raise SystemExit(f"development manifest contains a dependency cycle: {cycle}")
        layers.append(layer)
        completed.update(layer)
        remaining.difference_update(layer)
    return layers


def reconcile() -> dict[str, Any]:
    try:
        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = manifest["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}")
    if not isinstance(packages, list):
        raise SystemExit("development manifest work_packages is not a list")
    order: list[str] = []
    dependencies: dict[str, set[str]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            raise SystemExit("development manifest contains an invalid work package")
        package_id = package["id"]
        if package_id in dependencies:
            raise SystemExit(f"duplicate work-package ID: {package_id}")
        raw_dependencies = package.get("depends_on", [])
        if not isinstance(raw_dependencies, list) or not all(
            isinstance(value, str) for value in raw_dependencies
        ):
            raise SystemExit(f"invalid dependencies for {package_id}")
        order.append(package_id)
        dependencies[package_id] = set(raw_dependencies)
    all_ids = set(order)
    unknown = {
        package_id: sorted(values - all_ids)
        for package_id, values in dependencies.items()
        if values - all_ids
    }
    if unknown:
        raise SystemExit(f"unknown work-package dependencies: {unknown}")
    if len(order) != 156:
        raise SystemExit(f"expected 156 work packages, found {len(order)}")
    layers = topological_layers(order, dependencies)

    pass_evidence = verified_pass_reports()
    pass_evidence["B04"] = verified_b04_pass()
    completed = set(pass_evidence)
    if not completed <= all_ids:
        raise SystemExit("PASS evidence includes a package absent from the manifest")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    ready_details = {
        package_id: {
            "dependencies": sorted(dependencies[package_id]),
            "dependencies_pass": True,
            "manifest_index": order.index(package_id),
            "status": "READY",
        }
        for package_id in ready
    }
    expected_ready = ["D01", "G01", "A06"]
    if ready != expected_ready:
        raise SystemExit(
            f"post-B04 manifest-order READY set changed: {ready} != {expected_ready}"
        )
    return {
        "schema_version": 1,
        "status": "PASS",
        "projection": "POST_B04_0002_PASS",
        "manifest": {
            "path": MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": sha256(MANIFEST),
            "work_package_count": len(order),
            "unique_work_package_count": len(all_ids),
            "unknown_dependency_count": 0,
            "cycle_count": 0,
            "topological_layer_count": len(layers),
            "maximum_layer_width": max(map(len, layers)),
            "topological_layers": layers,
        },
        "completed_package_count": len(completed),
        "completed_packages": [package_id for package_id in order if package_id in completed],
        "pass_evidence": pass_evidence,
        "historical_non_pass_reports_preserved": historical_preservation(),
        "ready_package_count": len(ready),
        "ready_packages_manifest_order": ready,
        "ready_packages": ready_details,
        "next_package": ready[0],
        "blocked_package_count": len(blocked),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ATTEMPT / "dependency-status.json")
    args = parser.parse_args()
    result = reconcile()
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
