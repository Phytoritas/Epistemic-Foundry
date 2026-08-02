#!/usr/bin/env python3
"""Recompute the live 156-package DAG after sealed M01-0001 PASS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M01/attempts/0001"
L04_ATTEMPT = ROOT / "artifacts/work_packages/L04/attempts/0001"
OUTPUT = ATTEMPT / "post-m01-0001-dag-reconciliation.json"
REVIEW = ATTEMPT / "post-m01-0001-dag-review.md"
EXPECTED_M01_REPORT_HASH = (
    "sha256:10430c3495e03ed0aad184ed8e162d5cb87366c4525b46bd4cea8de059e3f26f"
)

sys.path.insert(0, str(L04_ATTEMPT))
import post_l04_0001_dag_reconciliation as base  # noqa: E402


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def reconcile() -> dict[str, Any]:
    order, dependencies, definitions = base.load_manifest()
    layers = base.topological_layers(order, dependencies)
    states = {package_id: base.report_state(package_id) for package_id in order}

    m01 = states["M01"]
    if not isinstance(m01.get("report"), str):
        raise SystemExit("M01 report is missing")
    m01_report = base.read_json(ROOT / m01["report"])
    rah = m01_report.get("rah_state")
    if not (
        m01["selected_attempt_id"] == "M01-0001"
        and m01["current_state"] == "PASS"
        and m01["report_sha256"] == EXPECTED_M01_REPORT_HASH
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0053"
        and rah.get("core_generation") == "000053-7086e787"
        and rah.get("final_closeout_evidence_id") == "E0054"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("M01-0001 is not the exact sealed PASS")

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
            "M01_attempt_id": "M01-0001",
            "M01_core_evidence_id": "E0053",
            "M01_core_generation": "000053-7086e787",
            "M01_final_closeout_evidence_id": "E0054",
            "M01_final_generation": "000054-ada9bb64",
            "M01_report": m01["report"],
            "M01_report_sha256": m01["report_sha256"],
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
            "observed_state_generation": "000054-ada9bb64",
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
        "projection": "POST_M01_0001_LIVE_RECOMPUTATION",
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
        result["completed_package_count"] == 54
        and result["waiting_package_count"] == 97
        and result["ready_packages_manifest_order"]
        == ["M02", "M03", "N01", "T01", "A06"]
        and result["next_package"] == "M02"
    ):
        raise SystemExit(
            "post-M01 DAG differs from evidence-derived state: "
            f"completed={result['completed_package_count']} "
            f"waiting={result['waiting_package_count']} "
            f"ready={result['ready_packages_manifest_order']}"
        )
    return result


def review_text(result: dict[str, Any]) -> str:
    ready = result["ready_packages_manifest_order"]
    return f"""# Post-M01-0001 live DAG reconciliation

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

M01 is bound to sealed `M01-0001`, core `E0053 / 000053-7086e787`, and
final `E0054 / 000054-ada9bb64`. The canonical external resume inspection
completed with exit 0 and no parse errors. The reconciliation selects `M02` as
the next bounded package and also identifies `M03`, `N01`, `T01`, and `A06` as
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
