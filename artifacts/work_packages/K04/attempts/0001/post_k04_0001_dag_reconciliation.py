#!/usr/bin/env python3
"""Recompute the live 156-package DAG after sealed K04-0001 PASS."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/K04/attempts/0001"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
OUTPUT = ATTEMPT / "post-k04-0001-dag-reconciliation.json"
REVIEW = ATTEMPT / "post-k04-0001-dag-review.md"
EXPECTED_PACKAGE_COUNT = 156
EXPECTED_K04_REPORT_HASH = (
    "sha256:12d84e70e24fb1f7f9d87619721a27eaf0a77499cfb11b426353bf9c8725c56f"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_manifest() -> tuple[list[str], dict[str, set[str]], dict[str, dict[str, Any]]]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    if not isinstance(packages, list):
        raise SystemExit("development manifest work_packages is not a list")

    order: list[str] = []
    dependencies: dict[str, set[str]] = {}
    definitions: dict[str, dict[str, Any]] = {}
    for row in packages:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise SystemExit("development manifest contains an invalid package row")
        package_id = row["id"]
        if package_id in dependencies:
            raise SystemExit(f"duplicate package ID: {package_id}")
        raw_dependencies = row.get("depends_on", [])
        if not isinstance(raw_dependencies, list) or not all(
            isinstance(value, str) for value in raw_dependencies
        ):
            raise SystemExit(f"invalid dependencies for {package_id}")
        order.append(package_id)
        dependencies[package_id] = set(raw_dependencies)
        definitions[package_id] = row

    if len(order) != EXPECTED_PACKAGE_COUNT or len(set(order)) != EXPECTED_PACKAGE_COUNT:
        raise SystemExit(
            f"expected {EXPECTED_PACKAGE_COUNT} unique packages, found {len(order)}"
        )
    unknown = {
        package_id: sorted(values - set(order))
        for package_id, values in dependencies.items()
        if values - set(order)
    }
    if unknown:
        raise SystemExit(f"unknown package dependencies: {unknown}")
    return order, dependencies, definitions


def topological_layers(order: list[str], dependencies: dict[str, set[str]]) -> list[list[str]]:
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
            raise SystemExit(f"development manifest contains a cycle: {sorted(remaining)}")
        layers.append(layer)
        completed.update(layer)
        remaining.difference_update(layer)
    return layers


def report_state(package_id: str) -> dict[str, Any]:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts_root = package_root / "attempts"
    numeric_attempts: list[tuple[int, Path]] = []
    nonnumeric_attempts: list[str] = []
    if attempts_root.is_dir():
        for path in attempts_root.iterdir():
            if not path.is_dir():
                continue
            if re.fullmatch(r"\d{4,}", path.name):
                numeric_attempts.append((int(path.name), path))
            else:
                nonnumeric_attempts.append(path.name)
    numeric_attempts.sort()
    root_report = package_root / "report.json"
    historical_report_count = int(root_report.is_file()) + sum(
        (path / "report.json").is_file() for _, path in numeric_attempts
    )

    if numeric_attempts:
        attempt_number, latest_directory = numeric_attempts[-1]
        report_path = latest_directory / "report.json"
        selected_attempt = f"{package_id}-{attempt_number:04d}"
        selection = "HIGHEST_NUMERIC_ATTEMPT"
        if not report_path.is_file():
            return {
                "current_state": "IN_PROGRESS_NO_REPORT",
                "historical_report_count": historical_report_count,
                "latest_attempt_directory": latest_directory.relative_to(ROOT).as_posix(),
                "nonnumeric_attempt_directories": sorted(nonnumeric_attempts),
                "package_status": None,
                "report": None,
                "report_sha256": None,
                "selected_attempt_id": selected_attempt,
                "selection_rule": selection,
                "status": None,
            }
    elif root_report.is_file():
        report_path = root_report
        selected_attempt = "historical-root-report"
        selection = "ROOT_REPORT_NO_NUMERIC_ATTEMPTS"
    else:
        return {
            "current_state": "NOT_STARTED",
            "historical_report_count": 0,
            "latest_attempt_directory": None,
            "nonnumeric_attempt_directories": sorted(nonnumeric_attempts),
            "package_status": None,
            "report": None,
            "report_sha256": None,
            "selected_attempt_id": None,
            "selection_rule": "NO_REPORT",
            "status": None,
        }

    report = read_json(report_path)
    reported_attempt = report.get("attempt_id")
    if selection == "HIGHEST_NUMERIC_ATTEMPT" and reported_attempt != selected_attempt:
        raise SystemExit(
            f"attempt identity mismatch for {package_id}: "
            f"{reported_attempt!r} != {selected_attempt!r}"
        )
    status = report.get("status")
    package_status = report.get("package_status")
    is_pass = status == "PASS" and package_status in (None, "PASS")
    return {
        "current_state": "PASS" if is_pass else str(package_status or status or "UNKNOWN"),
        "historical_report_count": historical_report_count,
        "latest_attempt_directory": (
            report_path.parent.relative_to(ROOT).as_posix()
            if selection == "HIGHEST_NUMERIC_ATTEMPT"
            else None
        ),
        "nonnumeric_attempt_directories": sorted(nonnumeric_attempts),
        "package_status": package_status,
        "report": report_path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(report_path),
        "selected_attempt_id": reported_attempt or selected_attempt,
        "selection_rule": selection,
        "status": status,
    }


def reconcile() -> dict[str, Any]:
    order, dependencies, definitions = load_manifest()
    layers = topological_layers(order, dependencies)
    states = {package_id: report_state(package_id) for package_id in order}

    k04 = states["K04"]
    if not isinstance(k04.get("report"), str):
        raise SystemExit("K04 report is missing")
    k04_report = read_json(ROOT / k04["report"])
    rah = k04_report.get("rah_state")
    if not (
        k04["selected_attempt_id"] == "K04-0001"
        and k04["current_state"] == "PASS"
        and k04["report_sha256"] == EXPECTED_K04_REPORT_HASH
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0038"
        and rah.get("core_generation") == "000038-b5335969"
        and rah.get("final_closeout_evidence_id") == "E0039"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("K04-0001 is not the exact sealed PASS")

    completed = {
        package_id for package_id, state in states.items() if state["current_state"] == "PASS"
    }
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
    current_state_counts: dict[str, int] = {}
    for state in states.values():
        name = str(state["current_state"])
        current_state_counts[name] = current_state_counts.get(name, 0) + 1
    result = {
        "attempt_binding": {
            "K04_attempt_id": "K04-0001",
            "K04_core_evidence_id": "E0038",
            "K04_core_generation": "000038-b5335969",
            "K04_final_closeout_evidence_id": "E0039",
            "K04_report": k04["report"],
            "K04_report_sha256": k04["report_sha256"],
            "status": "PASS",
        },
        "blocked_package_count": len(blocked),
        "blocked_packages": {
            package_id: {
                "current_state": states[package_id]["current_state"],
                "unmet_dependencies": sorted(dependencies[package_id] - completed),
            }
            for package_id in blocked
        },
        "completed_package_count": len(completed),
        "completed_packages_manifest_order": [
            package_id for package_id in order if package_id in completed
        ],
        "completion_ready": False,
        "current_package_evidence": states,
        "current_state_counts": dict(sorted(current_state_counts.items())),
        "manifest": {
            "cycle_count": 0,
            "maximum_layer_width": max(map(len, layers)),
            "path": MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(MANIFEST),
            "topological_layer_count": len(layers),
            "topological_layers": layers,
            "unique_work_package_count": len(order),
            "unknown_dependency_count": 0,
            "work_package_count": len(order),
        },
        "next_package": ready[0] if ready else None,
        "projection": "POST_K04_0001_LIVE_RECOMPUTATION",
        "ready_package_count": len(ready),
        "ready_packages": {
            package_id: {
                "dependencies": sorted(dependencies[package_id]),
                "dependencies_pass": True,
                "manifest_index": order.index(package_id),
                "owner_role": definitions[package_id].get("owner_role"),
                "phase": definitions[package_id].get("phase"),
                "risk_class": definitions[package_id].get("risk_class"),
                "status": "READY",
                "title": definitions[package_id].get("title"),
            }
            for package_id in ready
        },
        "ready_packages_manifest_order": ready,
        "schema_version": 2,
        "status": "PASS",
    }
    if not (
        result["completed_package_count"] == 49
        and result["blocked_package_count"] == 102
        and result["ready_packages_manifest_order"]
        == ["L01", "M01", "N01", "T01", "A06"]
        and result["next_package"] == "L01"
    ):
        raise SystemExit(
            "post-K04 DAG differs from the evidence-derived state: "
            f"completed={result['completed_package_count']} "
            f"blocked={result['blocked_package_count']} "
            f"ready={result['ready_packages_manifest_order']}"
        )
    return result


def review_text(result: dict[str, Any]) -> str:
    ready = result["ready_packages_manifest_order"]
    return f"""# Post-K04-0001 live DAG reconciliation

Status: `PASS`

- Manifest packages: {result['manifest']['work_package_count']}
- Completed from current highest-attempt evidence: {result['completed_package_count']}
- Dependency-ready: {result['ready_package_count']}
- Blocked by unmet dependencies: {result['blocked_package_count']}
- Ready set in manifest order: {', '.join(ready) if ready else '(none)'}
- Earliest next package: `{result['next_package']}`

The READY set is recomputed from the development manifest and current reports;
it is not used as an input. For every package, the highest numeric attempt is
authoritative. A missing report in that attempt is treated as in-progress, so
an older PASS cannot hide a newer non-PASS or incomplete attempt.

K04 is bound to sealed `K04-0001`, core `E0038 / 000038-b5335969`, and
final `E0039`. The reconciliation selects `L01` as the next bounded package and
also identifies `M01`, `N01`, `T01`, and `A06` as dependency-ready. It does not
claim overall completion, release readiness, or `completion_ready=true`.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--review", type=Path, default=REVIEW)
    args = parser.parse_args()
    result = reconcile()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    review = args.review if args.review.is_absolute() else ROOT / args.review
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(result), encoding="utf-8", newline="\n")
    review.write_text(review_text(result), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "blocked_package_count": result["blocked_package_count"],
                "completed_package_count": result["completed_package_count"],
                "completion_ready": False,
                "next_package": result["next_package"],
                "ready_package_count": result["ready_package_count"],
                "ready_packages_manifest_order": result[
                    "ready_packages_manifest_order"
                ],
                "status": "PASS",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
