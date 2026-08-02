#!/usr/bin/env python3
"""Recompute the live 156-package DAG after sealed N03-0001 PASS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
N02_ATTEMPT = ROOT / "artifacts/work_packages/N02/attempts/0001"
OUTPUT = ATTEMPT / "post-n03-0001-dag-reconciliation.json"
REVIEW = ATTEMPT / "post-n03-0001-dag-review.md"
EXPECTED_N03_REPORT_HASH = (
    "sha256:8441523851ff6eed3f6b07877af181190dbbb21c70bca5f2f13dc88098fc4855"
)

sys.path.insert(0, str(N02_ATTEMPT))
import post_n02_0001_dag_reconciliation as previous  # noqa: E402


base = previous.base


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def reconcile() -> dict[str, Any]:
    order, dependencies, definitions = base.load_manifest()
    layers = base.topological_layers(order, dependencies)
    states = {package_id: base.report_state(package_id) for package_id in order}

    n03 = states["N03"]
    if not isinstance(n03.get("report"), str):
        raise SystemExit("N03 report is missing")
    n03_report = base.read_json(ROOT / n03["report"])
    rah = n03_report.get("rah_state")
    if not (
        n03["selected_attempt_id"] == "N03-0001"
        and n03["current_state"] == "PASS"
        and n03["report_sha256"] == EXPECTED_N03_REPORT_HASH
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0072"
        and rah.get("core_generation") == "000072-bd147e2a"
        and rah.get("final_closeout_evidence_id") == "E0073"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("N03-0001 is not the exact sealed PASS")

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
            "N03_attempt_id": "N03-0001",
            "N03_core_evidence_id": "E0072",
            "N03_core_generation": "000072-bd147e2a",
            "N03_final_closeout_evidence_id": "E0073",
            "N03_final_generation": "000073-6df5ddba",
            "N03_final_generation_manifest_sha256": (
                "sha256:549b8882c534f2053a2f01588d17ab283499ae81cec7621faad97f7e59ff053f"
            ),
            "N03_report": n03["report"],
            "N03_report_sha256": n03["report_sha256"],
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
            "observed_evidence_id": "E0073",
            "observed_generation_count": 73,
            "observed_generation_payload_hashes": 438,
            "observed_state_generation": "000073-6df5ddba",
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
        "projection": "POST_N03_0001_LIVE_RECOMPUTATION",
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
        result["completed_package_count"] == 60
        and result["waiting_package_count"] == 92
        and result["ready_packages_manifest_order"] == ["N04", "O01", "T01", "A06"]
        and result["next_package"] == "N04"
    ):
        raise SystemExit(
            "post-N03 DAG differs from evidence-derived state: "
            f"completed={result['completed_package_count']} "
            f"waiting={result['waiting_package_count']} "
            f"ready={result['ready_packages_manifest_order']}"
        )
    return result


def review_text(result: dict[str, Any]) -> str:
    ready = result["ready_packages_manifest_order"]
    return f"""# Post-N03-0001 live DAG reconciliation

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

N03 is bound to sealed `N03-0001`, core `E0072 / 000072-bd147e2a`, and
final `E0073 / 000073-6df5ddba`. The final generation manifest hash is
`sha256:549b8882c534f2053a2f01588d17ab283499ae81cec7621faad97f7e59ff053f`.
The canonical external resume inspection completed with exit 0 and no parse
errors. The reconciliation selects `N04` as the next bounded package and also
identifies `O01`, `T01`, and `A06` as dependency-ready. It does not claim
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
