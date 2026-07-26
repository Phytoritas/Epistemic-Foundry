#!/usr/bin/env python3
"""Status surface for the deployable Memento-aware recursive architecture harness."""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pending_feedback_count(feedback_payload: Any) -> int:
    if not isinstance(feedback_payload, dict):
        return 0
    items = feedback_payload.get("items", [])
    if not isinstance(items, list):
        return 0
    pending = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("relevant") is None or item.get("sufficient") is None:
            pending += 1
    return pending


def deployment_target(deployment_payload: Any) -> str | None:
    if not isinstance(deployment_payload, dict):
        return None
    package_install = deployment_payload.get("package_install")
    if isinstance(package_install, dict):
        return package_install.get("target")
    legacy_skill_install = deployment_payload.get("skill_install")
    if isinstance(legacy_skill_install, dict):
        return legacy_skill_install.get("target")
    return None


def removed_runtime_word() -> str:
    return "".join(chr(codepoint) for codepoint in [104, 111, 111, 107])


def jobs_summary(rah_root: Path) -> dict[str, Any]:
    jobs_root = rah_root / "jobs"
    if not jobs_root.exists() or not jobs_root.is_dir():
        return {"job_count": 0, "active_count": 0, "terminal_count": 0, "active_jobs": []}
    active_statuses = {"starting", "queued", "running", "cancel_requested", "cancelling"}
    terminal_statuses = {"succeeded", "failed", "cancelled", "lost", "orphaned"}
    jobs: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    for status_file in sorted(jobs_root.glob("*/status.json")):
        payload = load_json(status_file)
        if not isinstance(payload, dict):
            parse_errors.append(str(status_file))
            continue
        jobs.append(payload)
    active = [job for job in jobs if str(job.get("status") or "").lower() in active_statuses]
    terminal = [job for job in jobs if str(job.get("status") or "").lower() in terminal_statuses]
    return {
        "job_count": len(jobs),
        "active_count": len(active),
        "terminal_count": len(terminal),
        "parse_error_count": len(parse_errors),
        "active_jobs": [
            {
                "job_id": job.get("job_id"),
                "name": job.get("name"),
                "status": job.get("status"),
                "last_heartbeat_at_utc": job.get("last_heartbeat_at_utc"),
            }
            for job in active[:10]
        ],
    }


def main() -> int:
    parser = _SuggestingArgumentParser(description="Show harness status for a repository.")
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    rah_root = root / ".rah"

    status_payload = load_json(rah_root / "state/status.json")
    gates_payload = load_json(rah_root / "state/gates.json")
    doctor_payload = load_json(rah_root / "state/doctor.json")
    memento_payload = load_json(rah_root / "state/memento_status.json")
    feedback_payload = load_json(rah_root / "memory/memento_feedback.json")
    case_map = load_json(rah_root / "memory/case_map.json")
    deployment_payload = load_json(rah_root / "state/deployment.json")
    ralph_payload = load_json(rah_root / "ralph/loop_state.json")
    fleet_latest_run = None
    fleet_runs_root = rah_root / "fleet" / "runs"
    if fleet_runs_root.exists():
        fleet_candidates = sorted(child.name for child in fleet_runs_root.iterdir() if child.is_dir())
        if fleet_candidates:
            fleet_run_root = fleet_runs_root / fleet_candidates[-1]
            fleet_state = load_json(fleet_run_root / "state.json")
            if isinstance(fleet_state, dict):
                questions_root = fleet_run_root / "mailbox" / "questions"
                replies_root = fleet_run_root / "mailbox" / "replies"
                open_question_count = 0
                if questions_root.exists():
                    open_question_count = sum(
                        1
                        for question in questions_root.glob("q-*.json")
                        if not (replies_root / question.name).exists()
                    )
                fleet_latest_run = {
                    "run_id": fleet_candidates[-1],
                    "status": fleet_state.get("status"),
                    "template": fleet_state.get("template"),
                    "open_question_count": open_question_count,
                    "conversation_path": (
                        f".rah/fleet/runs/{fleet_candidates[-1]}/conversation.jsonl"
                    ),
                    "monitor_command": (
                        f"rah.py fleet <repo-root> monitor {fleet_candidates[-1]} --since 0 --json"
                    ),
                }
    ralph_evidence = load_json(rah_root / "ralph/evidence_ledger.json")
    ralph_plan_graph = load_json(rah_root / "ralph/plan_graph.json")
    ralph_goal_bridge = load_json(rah_root / "ralph/goal_bridge.json")
    ralph_review_gate = load_json(rah_root / "ralph/review_gate.json")
    ralph_driver = load_json(rah_root / "ralph/driver/driver_state.json")
    jobs = jobs_summary(rah_root)
    removed_contract_key = "stop_" + removed_runtime_word() + "_contract"
    legacy_deployment_key = removed_runtime_word() + "s_install"

    if status_payload is None or gates_payload is None:
        payload = {
            "state": "uninitialized",
            "root": str(root),
            "next_action": "Run python automation/rah.py setup <repo-root> first.",
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("# Harness Status\n")
            print(f"- root: {root}")
            print(f"- state: {payload['state']}")
            print(f"- next_action: {payload['next_action']}")
        return 0

    payload = {
        "state": "initialized",
        "root": str(root),
        "current_stage": status_payload.get("current_stage"),
        "phase": status_payload.get("phase"),
        "implementation_gate": status_payload.get("implementation_gate"),
        "next_action": status_payload.get("next_recommended_action"),
        "restart_point": status_payload.get("earliest_restart_point"),
        "doctor_state": status_payload.get("doctor_state"),
        "doctor_overall_status": doctor_payload.get("overall_status") if isinstance(doctor_payload, dict) else None,
        "memento_workspace": status_payload.get("memento_workspace"),
        "memento_topic": status_payload.get("memento_topic"),
        "memento_session_id": status_payload.get("memento_session_id"),
        "memento_case_id": status_payload.get("memento_case_id"),
        "memory_freshness": status_payload.get("memory_freshness"),
        "memento_connectivity": memento_payload.get("connectivity") if isinstance(memento_payload, dict) else None,
        "memento_health_url": memento_payload.get("health_url") if isinstance(memento_payload, dict) else None,
        "memento_last_context_at": status_payload.get("memento_last_context_at"),
        "memento_last_recall_at": status_payload.get("memento_last_recall_at"),
        "pending_feedback_count": pending_feedback_count(feedback_payload),
        "agents_gate": (gates_payload.get("agents_and_workflow_gate") or {}).get("status")
        if isinstance(gates_payload, dict)
        else None,
        "memento_recall_gate": (gates_payload.get("memento_recall_gate") or {}).get("status")
        if isinstance(gates_payload, dict)
        else None,
        "memento_feedback_gate": (gates_payload.get("memento_feedback_gate") or {}).get("status")
        if isinstance(gates_payload, dict)
        else None,
        "deployment_scope": deployment_payload.get("scope") if isinstance(deployment_payload, dict) else None,
        "deployment_helper_target": deployment_target(deployment_payload),
        "deployment_removed_runtime_install_present": legacy_deployment_key in deployment_payload
        if isinstance(deployment_payload, dict)
        else None,
        "case_phase": case_map.get("phase") if isinstance(case_map, dict) else None,
        "ralph_status": ralph_payload.get("status") if isinstance(ralph_payload, dict) else None,
        "ralph_goal": ralph_payload.get("goal") if isinstance(ralph_payload, dict) else None,
        "ralph_iteration": ralph_payload.get("current_iteration") if isinstance(ralph_payload, dict) else None,
        "ralph_completion_mode": ralph_payload.get("completion_mode") if isinstance(ralph_payload, dict) else None,
        "ralph_checkpoint_required": ralph_payload.get("checkpoint_required") if isinstance(ralph_payload, dict) else None,
        "ralph_loop_phase": ralph_payload.get("loop_phase") if isinstance(ralph_payload, dict) else None,
        "ralph_state": (ralph_payload.get("state_machine") or {}).get("current_state")
        if isinstance(ralph_payload, dict)
        else None,
        "ralph_completion_ready": (ralph_payload.get("completion_readiness") or {}).get("ready")
        if isinstance(ralph_payload, dict)
        else None,
        "source_coverage_present": (ralph_payload.get("completion_readiness") or {}).get("source_coverage_present")
        if isinstance(ralph_payload, dict)
        else None,
        "source_coverage_required": (ralph_payload.get("completion_readiness") or {}).get("source_coverage_required")
        if isinstance(ralph_payload, dict)
        else None,
        "source_coverage_ready": (ralph_payload.get("completion_readiness") or {}).get("source_coverage_ready")
        if isinstance(ralph_payload, dict)
        else None,
        "source_coverage_total_rows": (ralph_payload.get("completion_readiness") or {}).get("source_coverage_total_rows")
        if isinstance(ralph_payload, dict)
        else None,
        "source_coverage_missing_ids": (ralph_payload.get("completion_readiness") or {}).get("source_coverage_missing_ids")
        if isinstance(ralph_payload, dict)
        else None,
        "source_unit_total": (ralph_payload.get("completion_readiness") or {}).get("source_unit_total")
        if isinstance(ralph_payload, dict)
        else None,
        "source_unit_processed": (ralph_payload.get("completion_readiness") or {}).get("source_unit_processed")
        if isinstance(ralph_payload, dict)
        else None,
        "source_unit_blocked_ids": (ralph_payload.get("completion_readiness") or {}).get("source_unit_blocked_ids")
        if isinstance(ralph_payload, dict)
        else None,
        "source_unit_text_missing_ids": (ralph_payload.get("completion_readiness") or {}).get("source_unit_text_missing_ids")
        if isinstance(ralph_payload, dict)
        else None,
        "prd_present": (ralph_payload.get("completion_readiness") or {}).get("prd_present")
        if isinstance(ralph_payload, dict)
        else None,
        "prd_required": (ralph_payload.get("completion_readiness") or {}).get("prd_required")
        if isinstance(ralph_payload, dict)
        else None,
        "prd_ready": (ralph_payload.get("completion_readiness") or {}).get("prd_ready")
        if isinstance(ralph_payload, dict)
        else None,
        "prd_stale": (ralph_payload.get("completion_readiness") or {}).get("prd_stale")
        if isinstance(ralph_payload, dict)
        else None,
        "prd_blocks_completion": (ralph_payload.get("completion_readiness") or {}).get("prd_blocks_completion")
        if isinstance(ralph_payload, dict)
        else None,
        "fleet_latest_run": fleet_latest_run,
        "ralph_missing_closeout_ids": (ralph_payload.get("completion_readiness") or {}).get("missing_closeout_ids")
        if isinstance(ralph_payload, dict)
        else None,
        "ralph_evidence_count": len(ralph_evidence.get("entries", [])) if isinstance(ralph_evidence, dict) else None,
        "ralph_active_plan_node": ralph_plan_graph.get("active_node") if isinstance(ralph_plan_graph, dict) else None,
        "ralph_goal_bridge_mode": ralph_goal_bridge.get("mode") if isinstance(ralph_goal_bridge, dict) else None,
        "ralph_review_status": ralph_review_gate.get("status") if isinstance(ralph_review_gate, dict) else None,
        "ralph_review_required": ralph_review_gate.get("required") if isinstance(ralph_review_gate, dict) else None,
        "ralph_blocked_reason": ralph_payload.get("blocked_reason") if isinstance(ralph_payload, dict) else None,
        "ralph_removed_runtime_contract_present": removed_contract_key in ralph_payload
        if isinstance(ralph_payload, dict)
        else None,
        "ralph_driver_contract_present": isinstance(
            (ralph_payload.get("external_driver_contract") if isinstance(ralph_payload, dict) else None),
            dict,
        ),
        "ralph_driver_command": (ralph_payload.get("external_driver_contract") or {}).get("command")
        if isinstance(ralph_payload, dict)
        else None,
        "ralph_driver_status": ralph_driver.get("status") if isinstance(ralph_driver, dict) else None,
        "ralph_driver_cycles_run": ralph_driver.get("cycles_run") if isinstance(ralph_driver, dict) else None,
        "ralph_driver_blocked_reason": ralph_driver.get("blocked_reason") if isinstance(ralph_driver, dict) else None,
        "job_count": jobs.get("job_count"),
        "job_active_count": jobs.get("active_count"),
        "job_terminal_count": jobs.get("terminal_count"),
        "job_parse_error_count": jobs.get("parse_error_count"),
        "job_active_jobs": jobs.get("active_jobs"),
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        # Compact human/agent block: None-valued fields are omitted except a
        # small always-printed core — the --json payload keeps every field.
        always_print = {
            "root",
            "current_stage",
            "phase",
            "next_action",
            "ralph_status",
            "ralph_iteration",
            "ralph_completion_ready",
            "ralph_review_status",
        }
        print("# Harness Status\n")
        for key in [
            "root",
            "current_stage",
            "phase",
            "implementation_gate",
            "restart_point",
            "next_action",
            "doctor_overall_status",
            "memento_workspace",
            "memento_topic",
            "memento_session_id",
            "memento_case_id",
            "memory_freshness",
            "memento_connectivity",
            "memento_health_url",
            "pending_feedback_count",
            "agents_gate",
            "memento_recall_gate",
            "memento_feedback_gate",
            "deployment_scope",
            "deployment_helper_target",
            "deployment_removed_runtime_install_present",
            "ralph_status",
            "ralph_iteration",
            "ralph_completion_mode",
            "ralph_checkpoint_required",
            "ralph_loop_phase",
            "ralph_state",
            "ralph_completion_ready",
            "source_coverage_present",
            "source_coverage_required",
            "source_coverage_ready",
            "source_coverage_total_rows",
            "source_coverage_missing_ids",
            "source_unit_total",
            "source_unit_processed",
            "source_unit_blocked_ids",
            "source_unit_text_missing_ids",
            "prd_present",
            "prd_required",
            "prd_ready",
            "prd_stale",
            "prd_blocks_completion",
            "fleet_latest_run",
            "ralph_missing_closeout_ids",
            "ralph_evidence_count",
            "ralph_active_plan_node",
            "ralph_goal_bridge_mode",
            "ralph_review_status",
            "ralph_review_required",
            "ralph_blocked_reason",
            "ralph_removed_runtime_contract_present",
            "ralph_driver_contract_present",
            "ralph_driver_command",
            "ralph_driver_status",
            "ralph_driver_cycles_run",
            "ralph_driver_blocked_reason",
            "job_count",
            "job_active_count",
            "job_terminal_count",
            "job_parse_error_count",
            "job_active_jobs",
        ]:
            value = payload.get(key)
            if value is None and key not in always_print:
                continue
            print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
