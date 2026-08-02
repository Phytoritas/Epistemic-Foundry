#!/usr/bin/env python3
"""Recompute the 156-package DAG after the E04 core PASS evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "E04"
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
    "E01": "artifacts/work_packages/E01/report.json",
    "E02": "artifacts/work_packages/E02/report.json",
    "E03": "artifacts/work_packages/E03/report.json",
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

E04_SOURCE_HASHES = {
    "tests/replay/effects/replay-test-support.mjs": (
        "da299cd4d9fd44a30d4851be3c4f7ac5104aadb94de57fe525cb2b1c8a98ca4b"
    ),
    "tests/replay/effects/strict-replay.test.mjs": (
        "b4d930073c16169139ae480a9fca549f6216a538adce5dec5c7da11f3f35adc1"
    ),
    "tests/replay/effects/semantic-replay.test.mjs": (
        "bfb99786cdc201c486fb710ffa973d2c0a241af4e53fb6be2cbb6a0587b036ed"
    ),
    "artifacts/work_packages/E04/review.md": (
        "18cda4135b66486a91151f3c15b68ed90bbcef44d00663b6433dc9341162ef78"
    ),
    "artifacts/work_packages/E04/e04-verification.json": (
        "37e9a9367a6c1bfaf75c2c0e3d93498631e2ff47a9beaebec18d1050738b13dd"
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


def verified_e04_core() -> dict[str, Any]:
    for relative, expected in E04_SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"E04 core source hash changed for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    if "Final verdict: `PASS`" not in review or "blocking findings: 0" not in review:
        raise SystemExit("E04 review is not an unblocked PASS")
    verification = read_json(PACKAGE / "e04-verification.json")
    if verification.get("status") != "PASS":
        raise SystemExit("E04 verification artifact is not PASS")

    current = read_json(RAH_ROOT / "current.json")
    generation = current.get("generation")
    if not isinstance(generation, str) or not re.fullmatch(r"000029-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected E04 core generation: {generation}")
    ledger = read_json(RAH_ROOT / "evidence_ledger.json")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("RAH evidence ledger has no entries")
    latest = entries[-1]
    if not isinstance(latest, dict) or latest.get("id") != "E0030":
        raise SystemExit("E04 DAG reconciliation requires latest evidence E0030")
    summary = str(latest.get("summary", ""))
    if not summary.startswith("E04-0001 PASS core:"):
        raise SystemExit("E0030 is not the E04 core PASS evidence")
    generation_manifest = RAH_ROOT / "generations" / generation / "generation-manifest.json"
    if not generation_manifest.is_file():
        raise SystemExit("E04 core generation manifest is missing")
    return {
        "attempt_id": "E04-0001",
        "core_evidence_id": "E0030",
        "core_generation": generation,
        "core_generation_manifest": generation_manifest.relative_to(ROOT).as_posix(),
        "core_generation_manifest_sha256": sha256(generation_manifest),
        "review": "artifacts/work_packages/E04/review.md",
        "review_sha256": E04_SOURCE_HASHES["artifacts/work_packages/E04/review.md"],
        "verification": "artifacts/work_packages/E04/e04-verification.json",
        "verification_sha256": E04_SOURCE_HASHES[
            "artifacts/work_packages/E04/e04-verification.json"
        ],
        "source_hashes": E04_SOURCE_HASHES,
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
    pass_evidence["E04"] = verified_e04_core()
    completed = set(pass_evidence)
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["F01", "G01", "K01", "A06"]
    if ready != expected_ready:
        raise SystemExit(
            f"post-E04 manifest-order READY set changed: {ready} != {expected_ready}"
        )
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    return {
        "schema_version": 1,
        "status": "PASS",
        "projection": "POST_E04_0001_CORE_PASS",
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
