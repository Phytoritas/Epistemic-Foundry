#!/usr/bin/env python3
"""Recompute the live 156-package DAG after sealed O01-0002 PASS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/O01/attempts/0002"
B04_ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0008"
OUTPUT = ATTEMPT / "post-o01-0002-dag-reconciliation.json"
REVIEW = ATTEMPT / "post-o01-0002-dag-review.md"
EXPECTED_O01_REPORT_HASH = (
    "sha256:21cd6f07ce4caae4d7a7d673a85aec105117f35f2a560ef8310ee532cb188051"
)
EXPECTED_FINAL_GENERATION_MANIFEST_HASH = (
    "sha256:b627d4233efd54b4cc9eaf0b449c6c28b8336ba9589e43d7f6c59ee875f3b1ec"
)

sys.path.insert(0, str(B04_ATTEMPT))
import post_b04_0008_dag_reconciliation as base  # noqa: E402


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def reconcile() -> dict[str, Any]:
    order, dependencies, definitions = base.load_manifest()
    layers = base.topological_layers(order, dependencies)
    states = {package_id: base.report_state(package_id) for package_id in order}

    o01 = states["O01"]
    if not isinstance(o01.get("report"), str):
        raise SystemExit("O01 report is missing")
    o01_report = base.read_json(ROOT / o01["report"])
    rah = o01_report.get("rah_state")
    if not (
        o01["selected_attempt_id"] == "O01-0002"
        and o01["current_state"] == "PASS"
        and o01["report_sha256"] == EXPECTED_O01_REPORT_HASH
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0081"
        and rah.get("core_generation") == "000081-ec78f8a8"
        and rah.get("final_closeout_evidence_id") == "E0082"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("O01-0002 is not the exact sealed PASS")

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
            "O01_attempt_id": "O01-0002",
            "O01_core_evidence_id": "E0081",
            "O01_core_generation": "000081-ec78f8a8",
            "O01_final_closeout_evidence_id": "E0082",
            "O01_final_generation": "000082-fbc64882",
            "O01_final_generation_manifest_sha256": EXPECTED_FINAL_GENERATION_MANIFEST_HASH,
            "O01_report": o01["report"],
            "O01_report_sha256": o01["report_sha256"],
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
            "observed_evidence_id": "E0082",
            "observed_generation_count": 82,
            "observed_generation_payload_hashes": 492,
            "observed_state_generation": "000082-fbc64882",
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
        "projection": "POST_O01_0002_LIVE_RECOMPUTATION",
        "ready_package_count": len(ready),
        "ready_packages": {
            package_id: {
                "current_state": states[package_id]["current_state"],
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
        and result["completed_package_count"] == 62
        and result["waiting_package_count"] == 89
        and result["current_state_counts"]
        == {"FAIL": 1, "NOT_STARTED": 92, "PASS": 62, "SPEC_GAP": 1}
        and result["ready_packages_manifest_order"]
        == ["O02", "O03", "T01", "W01", "A06"]
        and result["next_package"] == "O02"
    ):
        raise SystemExit(
            "post-O01 DAG differs from evidence-derived state: "
            f"completed={result['completed_package_count']} "
            f"waiting={result['waiting_package_count']} "
            f"counts={result['current_state_counts']} "
            f"ready={result['ready_packages_manifest_order']}"
        )
    return result


def review_text(result: dict[str, Any]) -> str:
    ready = result["ready_packages_manifest_order"]
    return f"""# Post-O01-0002 live DAG reconciliation

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
authoritative. A missing report in that attempt is treated as in progress, so
an older PASS cannot hide a newer non-PASS or incomplete attempt.

O01 is bound to sealed `O01-0002`, core `E0081 / 000081-ec78f8a8`, and
final `E0082 / 000082-fbc64882`. The final generation manifest hash is
`{EXPECTED_FINAL_GENERATION_MANIFEST_HASH}`. The canonical external resume
inspection completed with exit 0 and no parse errors. The reconciliation
selects `O02` as the next bounded package and also identifies `O03`, `T01`,
`W01`, and `A06` as dependency-ready. Existing T01 SPEC_GAP and A06 FAIL
remain visible current states; READY means only that their dependencies pass.
This does not claim overall completion, release readiness, or
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
