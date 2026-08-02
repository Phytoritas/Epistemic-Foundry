#!/usr/bin/env python3
"""Recompute the live 156-package DAG after sealed N04-0001 PASS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N04/attempts/0001"
N03_ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
OUTPUT = ATTEMPT / "post-n04-0001-dag-reconciliation.json"
REVIEW = ATTEMPT / "post-n04-0001-dag-review.md"
EXPECTED_N04_REPORT_HASH = (
    "sha256:8cbe538b5adb087974f83cc181e97172052bc25ff92e6a14da7dad3eb70141f7"
)

sys.path.insert(0, str(N03_ATTEMPT))
import post_n03_0001_dag_reconciliation as previous  # noqa: E402


base = previous.base


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def reconcile() -> dict[str, Any]:
    order, dependencies, definitions = base.load_manifest()
    layers = base.topological_layers(order, dependencies)
    states = {package_id: base.report_state(package_id) for package_id in order}

    n04 = states["N04"]
    if not isinstance(n04.get("report"), str):
        raise SystemExit("N04 report is missing")
    n04_report = base.read_json(ROOT / n04["report"])
    rah = n04_report.get("rah_state")
    if not (
        n04["selected_attempt_id"] == "N04-0001"
        and n04["current_state"] == "PASS"
        and n04["report_sha256"] == EXPECTED_N04_REPORT_HASH
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0076"
        and rah.get("core_generation") == "000076-f98de2cd"
        and rah.get("final_closeout_evidence_id") == "E0077"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("N04-0001 is not the exact sealed PASS")

    completed = {
        package_id for package_id, state in states.items() if state["current_state"] == "PASS"
    }
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    waiting = [
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
            "N04_attempt_id": "N04-0001",
            "N04_core_evidence_id": "E0076",
            "N04_core_generation": "000076-f98de2cd",
            "N04_final_closeout_evidence_id": "E0077",
            "N04_final_generation": "000077-41e5ef8e",
            "N04_final_generation_manifest_sha256": (
                "sha256:b8c59e3010da25e50bb91d80a399843d42c2156787c6f2a88c5b27d043f1d0fa"
            ),
            "N04_report": n04["report"],
            "N04_report_sha256": n04["report_sha256"],
            "status": "PASS",
        },
        "completed_package_count": len(completed),
        "completed_packages_manifest_order": [
            package_id for package_id in order if package_id in completed
        ],
        "completion_ready": False,
        "current_package_evidence": states,
        "current_state_counts": dict(sorted(current_state_counts.items())),
        "external_resume_inspection": {
            "command_surface": "Git for Windows bash + rah.py inspect . --resume --json",
            "completion_ready": False,
            "current_stage": "ralph-active",
            "exit_code": 0,
            "implementation_gate": "fail",
            "observed_evidence_id": "E0077",
            "observed_generation_count": 77,
            "observed_generation_payload_hashes": 462,
            "observed_state_generation": "000077-41e5ef8e",
            "parse_errors": {},
            "ralph_status": "active",
            "six_flat_snapshot_content_matches": 6,
            "six_flat_snapshot_stamps_verified": 6,
            "status": "PASS",
        },
        "manifest": {
            "cycle_count": 0,
            "maximum_layer_width": max(map(len, layers)),
            "path": base.MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": base.sha256_id(base.MANIFEST),
            "topological_layer_count": len(layers),
            "topological_layers": layers,
            "unique_work_package_count": len(order),
            "unknown_dependency_count": 0,
            "work_package_count": len(order),
        },
        "next_package": ready[0] if ready else None,
        "projection": "POST_N04_0001_LIVE_RECOMPUTATION",
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
        "waiting_package_count": len(waiting),
        "waiting_packages": {
            package_id: {
                "current_state": states[package_id]["current_state"],
                "unmet_dependencies": sorted(dependencies[package_id] - completed),
            }
            for package_id in waiting
        },
    }
    if not (
        result["manifest"]["work_package_count"] == 156
        and result["completed_package_count"] == 61
        and result["waiting_package_count"] == 91
        and result["current_state_counts"]
        == {"FAIL": 1, "NOT_STARTED": 93, "PASS": 61, "SPEC_GAP": 1}
        and result["ready_packages_manifest_order"] == ["O01", "T01", "W01", "A06"]
        and result["next_package"] == "O01"
    ):
        raise SystemExit(
            "post-N04 DAG differs from evidence-derived state: "
            f"completed={result['completed_package_count']} "
            f"waiting={result['waiting_package_count']} "
            f"ready={result['ready_packages_manifest_order']}"
        )
    return result


def review_text(result: dict[str, Any]) -> str:
    ready = result["ready_packages_manifest_order"]
    return f"""# Post-N04-0001 live DAG reconciliation

Status: `PASS`

- Manifest packages: {result['manifest']['work_package_count']}
- Completed from current highest-attempt evidence: {result['completed_package_count']}
- Dependency-ready: {result['ready_package_count']}
- Waiting on unmet dependencies: {result['waiting_package_count']}
- Ready set in manifest order: {', '.join(ready) if ready else '(none)'}
- Earliest next package: `{result['next_package']}`
- External resume inspection: `PASS` (`parse_errors={{}}`, active/fail/completion_ready=false)

The READY set is recomputed from the development manifest and current reports;
it is not used as an input. For every package, the highest numeric attempt is
authoritative. A missing report in that attempt is treated as in-progress, so
an older PASS cannot hide a newer non-PASS or incomplete attempt.

N04 is bound to sealed `N04-0001`, core `E0076 / 000076-f98de2cd`, and
final `E0077 / 000077-41e5ef8e`. The final generation manifest hash is
`sha256:b8c59e3010da25e50bb91d80a399843d42c2156787c6f2a88c5b27d043f1d0fa`.
The canonical external resume inspection completed with exit 0 and no parse
errors. The reconciliation selects `O01` as the next bounded package and also
identifies `T01`, `W01`, and `A06` as dependency-ready. It does not claim
overall completion, release readiness, or `completion_ready=true`.
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
                "completed_package_count": result["completed_package_count"],
                "completion_ready": False,
                "next_package": result["next_package"],
                "ready_package_count": result["ready_package_count"],
                "ready_packages_manifest_order": result["ready_packages_manifest_order"],
                "status": "PASS",
                "waiting_package_count": result["waiting_package_count"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
