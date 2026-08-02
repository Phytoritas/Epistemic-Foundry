#!/usr/bin/env python3
"""Recompute the 156-package DAG after the E01 core PASS evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "E01"
MANIFEST = ROOT / "manifests" / "development_manifest.yaml"
RAH_ROOT = ROOT / ".rah" / "ralph"

PASS_REPORTS = {
    "A01": "artifacts/work_packages/A01/report.json",
    "A02": "artifacts/work_packages/A02/report.json",
    "A03": "artifacts/work_packages/A03/report.json",
    "A04": "artifacts/work_packages/A04/report.json",
    "A05": "artifacts/work_packages/A05/attempts/0002/report.json",
    "B01": "artifacts/work_packages/B01/report.json",
    "B02": "artifacts/work_packages/B02/report.json",
    "B03": "artifacts/work_packages/B03/report.json",
    "B04": "artifacts/work_packages/B04/attempts/0002/report.json",
    "C01": "artifacts/work_packages/C01/attempts/0004/report.json",
    "C02": "artifacts/work_packages/C02/report.json",
    "C03": "artifacts/work_packages/C03/report.json",
    "C04": "artifacts/work_packages/C04/report.json",
    "D01": "artifacts/work_packages/D01/report.json",
    "D02": "artifacts/work_packages/D02/report.json",
    "D03": "artifacts/work_packages/D03/report.json",
    "D04": "artifacts/work_packages/D04/report.json",
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

E01_SOURCE_HASHES = {
    "packages/foundry-kernel/src/ledger/noetic-ledger.mjs": (
        "58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed"
    ),
    "packages/foundry-kernel/src/ledger/ledger-test-support.mjs": (
        "4954d4dd7bc985136d744f0689b91316419fb376e842dba2a428c66c9813d6e9"
    ),
    "packages/foundry-kernel/src/ledger/ledger-hash-chain.test.mjs": (
        "e478e71b48d74a139a10023033b3fd2d73fcbdf92660feeb920a6c3953e4eb82"
    ),
    "packages/foundry-kernel/src/ledger/reducer-replay.test.mjs": (
        "a1f9848e08c1231de29ada86236b6a1ffef19d867ce412d16737a8ce44222029"
    ),
    "artifacts/work_packages/E01/review.md": (
        "41c9f3633a3db7e97c80f7e31a6febfd912822232a0d706ca3aa5f517a9d392a"
    ),
    "artifacts/work_packages/E01/e01-verification.json": (
        "404d7c10ddce5dde2925efc0b6b6c2c0f862763ad64661181a32cf96eb6982bf"
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read required JSON evidence {path}: {error}")
    if not isinstance(document, dict):
        raise SystemExit(f"required JSON evidence is not an object: {path}")
    return document


def verified_pass_reports() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for package_id, relative in PASS_REPORTS.items():
        report = read_json(ROOT / relative)
        if report.get("status") != "PASS":
            raise SystemExit(f"{package_id} evidence is not PASS: {relative}")
        result[package_id] = {
            "attempt_id": str(report.get("attempt_id") or "historical-root-pass"),
            "report": relative,
            "report_sha256": sha256(ROOT / relative),
            "status": "PASS",
        }
    return result


def verified_e01_core() -> dict[str, Any]:
    for relative, expected in E01_SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"E01 core source hash changed for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    if "Final verdict: `PASS`" not in review or "blocking findings: 0" not in review:
        raise SystemExit("E01 review is not an unblocked PASS")
    verification = read_json(PACKAGE / "e01-verification.json")
    if verification.get("status") != "PASS":
        raise SystemExit("E01 verification artifact is not PASS")

    current = read_json(RAH_ROOT / "current.json")
    generation = current.get("generation")
    if not isinstance(generation, str) or not re.fullmatch(r"000023-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected E01 core generation: {generation}")
    ledger = read_json(RAH_ROOT / "evidence_ledger.json")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("RAH evidence ledger has no entries")
    latest = entries[-1]
    if not isinstance(latest, dict) or latest.get("id") != "E0024":
        raise SystemExit("E01 DAG reconciliation requires latest evidence E0024")
    summary = str(latest.get("summary", ""))
    if not summary.startswith("E01-0001 PASS core:"):
        raise SystemExit("E0024 is not the E01 core PASS evidence")
    generation_manifest = RAH_ROOT / "generations" / generation / "generation-manifest.json"
    if not generation_manifest.is_file():
        raise SystemExit("E01 core generation manifest is missing")
    return {
        "attempt_id": "E01-0001",
        "core_evidence_id": "E0024",
        "core_generation": generation,
        "core_generation_manifest": generation_manifest.relative_to(ROOT).as_posix(),
        "core_generation_manifest_sha256": sha256(generation_manifest),
        "review": "artifacts/work_packages/E01/review.md",
        "review_sha256": E01_SOURCE_HASHES["artifacts/work_packages/E01/review.md"],
        "verification": "artifacts/work_packages/E01/e01-verification.json",
        "verification_sha256": E01_SOURCE_HASHES[
            "artifacts/work_packages/E01/e01-verification.json"
        ],
        "source_hashes": E01_SOURCE_HASHES,
        "status": "PASS",
    }


def historical_preservation() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, relative in HISTORICAL_NON_PASS.items():
        report = read_json(ROOT / relative)
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
            raise SystemExit(
                f"development manifest contains a dependency cycle: {sorted(remaining)}"
            )
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
    pass_evidence["E01"] = verified_e01_core()
    completed = set(pass_evidence)
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["E02", "E03", "G01", "K01", "A06"]
    if ready != expected_ready:
        raise SystemExit(
            f"post-E01 manifest-order READY set changed: {ready} != {expected_ready}"
        )
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    return {
        "schema_version": 1,
        "status": "PASS",
        "projection": "POST_E01_0001_CORE_PASS",
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
        "ready_packages": {
            package_id: {
                "dependencies": sorted(dependencies[package_id]),
                "dependencies_pass": True,
                "manifest_index": order.index(package_id),
                "status": "READY",
            }
            for package_id in ready
        },
        "next_package": ready[0],
        "blocked_package_count": len(blocked),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PACKAGE / "dependency-status.json")
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
