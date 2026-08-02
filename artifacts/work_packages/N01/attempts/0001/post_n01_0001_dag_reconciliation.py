#!/usr/bin/env python3
"""Recompute the live 156-package DAG after sealed N01-0001 PASS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N01/attempts/0001"
M04_ATTEMPT = ROOT / "artifacts/work_packages/M04/attempts/0001"
OUTPUT = ATTEMPT / "post-n01-0001-dag-reconciliation.json"
REVIEW = ATTEMPT / "post-n01-0001-dag-review.md"
EXPECTED_N01_REPORT_HASH = (
    "sha256:6c2be21ead767753ebe67931dff46f909e5c15050ea07d9b1c366a5213d84eb2"
)

sys.path.insert(0, str(M04_ATTEMPT))
import post_m04_0001_dag_reconciliation as previous  # noqa: E402


base = previous.base


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def reconcile() -> dict[str, Any]:
    order, dependencies, definitions = base.load_manifest()
    layers = base.topological_layers(order, dependencies)
    states = {package_id: base.report_state(package_id) for package_id in order}

    n01 = states["N01"]
    if not isinstance(n01.get("report"), str):
        raise SystemExit("N01 report is missing")
    n01_report = base.read_json(ROOT / n01["report"])
    rah = n01_report.get("rah_state")
    if not (
        n01["selected_attempt_id"] == "N01-0001"
        and n01["current_state"] == "PASS"
        and n01["report_sha256"] == EXPECTED_N01_REPORT_HASH
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0066"
        and rah.get("core_generation") == "000066-096ea5d0"
        and rah.get("final_closeout_evidence_id") == "E0067"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("N01-0001 is not the exact sealed PASS")

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
            "N01_attempt_id": "N01-0001",
            "N01_core_evidence_id": "E0066",
            "N01_core_generation": "000066-096ea5d0",
            "N01_final_closeout_evidence_id": "E0067",
            "N01_final_generation": "000067-b707c87f",
            "N01_report": n01["report"],
            "N01_report_sha256": n01["report_sha256"],
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
            "observed_state_generation": "000067-b707c87f",
            "parse_errors": {},
            "ralph_status": "active",
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
        "projection": "POST_N01_0001_LIVE_RECOMPUTATION",
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
        result["completed_package_count"] == 58
        and result["waiting_package_count"] == 93
        and result["ready_packages_manifest_order"]
        == ["N02", "N03", "O01", "T01", "A06"]
        and result["next_package"] == "N02"
    ):
        raise SystemExit(
            "post-N01 DAG differs from evidence-derived state: "
            f"completed={result['completed_package_count']} "
            f"waiting={result['waiting_package_count']} "
            f"ready={result['ready_packages_manifest_order']}"
        )
    return result


def review_text(result: dict[str, Any]) -> str:
    ready = result["ready_packages_manifest_order"]
    return f"""# Post-N01-0001 live DAG reconciliation

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

N01 is bound to sealed `N01-0001`, core `E0066 / 000066-096ea5d0`, and
final `E0067 / 000067-b707c87f`. The canonical external resume inspection
completed with exit 0 and no parse errors. The reconciliation selects `N02` as
the next bounded package and also identifies `N03`, `O01`, `T01`, and `A06` as
dependency-ready. It does not claim overall completion, release readiness, or
`completion_ready=true`.
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
                "ready_packages_manifest_order": result[
                    "ready_packages_manifest_order"
                ],
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
