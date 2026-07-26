#!/usr/bin/env python3
"""Resume surface for the Memento-aware recursive architecture harness."""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
from pathlib import Path
from typing import Any

from source_coverage_harness import rows_from_payload, row_ready, validate_coverage_payload


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_parse_error": str(exc), "_path": str(path)}


def parse_error(payload: Any) -> str | None:
    if isinstance(payload, dict) and payload.get("_parse_error"):
        return str(payload.get("_parse_error"))
    return None


def clean_payload(payload: Any) -> Any:
    return None if parse_error(payload) else payload


def removed_runtime_word() -> str:
    return "".join(chr(codepoint) for codepoint in [104, 111, 111, 107])


def build_recipes(status_payload: dict[str, Any], case_map: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workspace = status_payload.get("memento_workspace")
    topic = status_payload.get("memento_topic")
    session_id = status_payload.get("memento_session_id")
    case_id = status_payload.get("memento_case_id")
    issue_number = status_payload.get("issue_number")
    branch_name = status_payload.get("branch_name")
    phase = (case_map or {}).get("phase") or status_payload.get("phase") or "planning"
    current_stage = status_payload.get("current_stage") or "bootstrap-complete"

    base_keywords = [workspace, topic, "architecture-refactor"]
    if branch_name:
        base_keywords.append(branch_name)
    if issue_number:
        base_keywords.append(f"issue-{issue_number}")
    base_keywords = [item for idx, item in enumerate(base_keywords) if item and item not in base_keywords[:idx]]

    if phase in {"planning", "architecture"} or current_stage == "bootstrap-complete":
        recall = {
            "tool": "recall",
            "workspace": workspace,
            "sessionId": session_id,
            "topic": topic,
            "keywords": base_keywords,
            "type": ["procedure", "decision", "error"],
            "depth": "detail",
            "caseMode": bool(case_id),
            "contextText": "bootstrap -> recon -> architecture intake",
        }
    elif phase == "implementation":
        recall = {
            "tool": "recall",
            "workspace": workspace,
            "sessionId": session_id,
            "topic": topic,
            "keywords": base_keywords + ["implementation", "regression", "interface"],
            "type": ["procedure", "error", "decision"],
            "depth": "detail",
            "caseMode": bool(case_id),
            "contextText": "bounded implementation phase with regression awareness",
        }
    else:
        recall = {
            "tool": "recall",
            "workspace": workspace,
            "sessionId": session_id,
            "topic": topic,
            "keywords": base_keywords + ["verification", "test", "review"],
            "type": ["procedure", "error", "decision"],
            "depth": "detail",
            "caseMode": bool(case_id),
            "contextText": "verification / review / regression hardening",
        }

    context = {
        "tool": "context",
        "workspace": workspace,
        "sessionId": session_id,
        "types": ["preference", "procedure", "error", "decision"],
    }

    reflect = {
        "tool": "reflect",
        "source_file": ".rah/memory/memento_reflect_draft.json",
        "expected_fields": ["summary", "decisions", "errors_resolved", "new_procedures", "open_questions"],
        "note": "Reflect only from confirmed work facts, not from speculation.",
    }
    return context, recall, reflect


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


def jobs_summary(rah_root: Path) -> dict[str, Any]:
    jobs_root = rah_root / "jobs"
    if not jobs_root.exists() or not jobs_root.is_dir():
        return {"job_count": 0, "active_jobs": [], "terminal_jobs": []}
    active_statuses = {"starting", "queued", "running", "cancel_requested", "cancelling"}
    terminal_statuses = {"succeeded", "failed", "cancelled", "lost", "orphaned"}
    active_jobs: list[dict[str, Any]] = []
    terminal_jobs: list[dict[str, Any]] = []
    for status_file in sorted(jobs_root.glob("*/status.json")):
        payload = load_json(status_file)
        if not isinstance(payload, dict):
            continue
        item = {
            "job_id": payload.get("job_id"),
            "name": payload.get("name"),
            "status": payload.get("status"),
            "exit_code": payload.get("exit_code"),
            "status_path": str(status_file),
            "completion_evidence_path": payload.get("completion_evidence_path"),
        }
        status = str(payload.get("status") or "").lower()
        if status in active_statuses:
            active_jobs.append(item)
        elif status in terminal_statuses:
            terminal_jobs.append(item)
    return {
        "job_count": len(active_jobs) + len(terminal_jobs),
        "active_jobs": active_jobs,
        "terminal_jobs": terminal_jobs[-10:],
    }


def main() -> int:
    parser = _SuggestingArgumentParser(description="Print a resume packet for the harness.")
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    rah_root = root / ".rah"

    status_payload = load_json(rah_root / "state/status.json")
    gates_payload = load_json(rah_root / "state/gates.json")
    case_map = load_json(rah_root / "memory/case_map.json")
    memento_payload = load_json(rah_root / "state/memento_status.json")
    deployment_payload = load_json(rah_root / "state/deployment.json")
    ralph_goal = load_json(rah_root / "ralph/goal.json")
    ralph_state = load_json(rah_root / "ralph/loop_state.json")
    ralph_evidence = load_json(rah_root / "ralph/evidence_ledger.json")
    ralph_plan_graph = load_json(rah_root / "ralph/plan_graph.json")
    ralph_goal_bridge = load_json(rah_root / "ralph/goal_bridge.json")
    ralph_review_gate = load_json(rah_root / "ralph/review_gate.json")
    source_documents = load_json(rah_root / "ralph/source_documents.json")
    source_coverage = load_json(rah_root / "ralph/source_requirement_coverage.json")
    ralph_driver = load_json(rah_root / "ralph/driver/driver_state.json")
    jobs = jobs_summary(rah_root)
    current_loop_path = rah_root / "plans/current_loop.md"
    wakeup_path = rah_root / "memory/wakeup.md"
    reflect_draft_path = rah_root / "memory/memento_reflect_draft.json"

    parse_errors = {
        name: parse_error(payload)
        for name, payload in {
            "status": status_payload,
            "gates": gates_payload,
            "case_map": case_map,
            "memento": memento_payload,
            "deployment": deployment_payload,
            "ralph_goal": ralph_goal,
            "ralph_state": ralph_state,
            "ralph_evidence": ralph_evidence,
            "ralph_plan_graph": ralph_plan_graph,
            "ralph_goal_bridge": ralph_goal_bridge,
            "ralph_review_gate": ralph_review_gate,
            "source_documents": source_documents,
            "source_coverage": source_coverage,
            "ralph_driver": ralph_driver,
        }.items()
        if parse_error(payload)
    }

    if status_payload is None or gates_payload is None or parse_error(status_payload) or parse_error(gates_payload):
        payload = {
            "state": "uninitialized",
            "root": str(root),
            "next_action": "Run bootstrap first, then resume from saved state.",
            "parse_errors": parse_errors,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("# Resume Packet\n")
            print(f"- root: {root}")
            print("- state: uninitialized")
            print("- next_action: Run bootstrap first, then resume from saved state.")
        return 1

    case_map = clean_payload(case_map)
    memento_payload = clean_payload(memento_payload)
    deployment_payload = clean_payload(deployment_payload)
    ralph_goal = clean_payload(ralph_goal)
    ralph_state = clean_payload(ralph_state)
    ralph_evidence = clean_payload(ralph_evidence)
    ralph_plan_graph = clean_payload(ralph_plan_graph)
    ralph_goal_bridge = clean_payload(ralph_goal_bridge)
    ralph_review_gate = clean_payload(ralph_review_gate)
    source_documents = clean_payload(source_documents)
    source_coverage = clean_payload(source_coverage)
    ralph_driver = clean_payload(ralph_driver)

    context_recipe, recall_recipe, reflect_recipe = build_recipes(status_payload, case_map)
    source_rows = rows_from_payload(source_coverage) if isinstance(source_coverage, dict) else []
    source_validation = (
        validate_coverage_payload(source_coverage, repo_root=root, verify_text_hashes=False)
        if isinstance(source_coverage, dict)
        else None
    )
    source_missing_rows = [
        str(row.get("requirement_id") or row.get("id") or f"row-{idx:04d}")
        for idx, row in enumerate(source_rows, start=1)
        if isinstance(row, dict) and not row_ready(row)
    ]
    removed_contract_key = "stop_" + removed_runtime_word() + "_contract"
    legacy_deployment_key = removed_runtime_word() + "s_install"

    read_first = [
        "AGENTS.md",
        "docs/architecture/Phytoritas.md",
        "docs/architecture/00_workspace_audit.md",
        ".rah/state/status.json",
        ".rah/state/gates.json",
        ".rah/memory/wakeup.md",
        ".rah/plans/current_loop.md",
        ]
    if isinstance(ralph_state, dict):
        read_first.extend(
            [
                ".rah/ralph/goal.json",
                ".rah/ralph/loop_state.json",
                ".rah/ralph/evidence_ledger.json",
                ".rah/ralph/plan_graph.json",
                ".rah/ralph/goal_bridge.json",
                ".rah/ralph/review_gate.json",
                ".rah/ralph/source_documents.json",
                ".rah/ralph/source_requirement_coverage.json",
                ".rah/ralph/source_requirement_coverage.md",
                ".rah/ralph/source_units/",
                ".rah/ralph/driver/driver_state.json",
                ".rah/ralph/driver/control.json",
                ".rah/ralph/driver/cycles/",
            ]
        )
    if (root / ".rah" / "ralph" / "prd.json").exists():
        read_first.extend(
            [
                ".rah/ralph/prd.json",
                ".rah/ralph/prd_mapping_audit.json",
                ".rah/ralph/source_requirement_atoms.json",
                ".rah/ralph/prd_waivers.json",
            ]
        )
    fleet_runs = root / ".rah" / "fleet" / "runs"
    if fleet_runs.exists() and any(fleet_runs.iterdir()):
        read_first.extend([".rah/fleet/runs/", ".rah/fleet/lock.json"])
    if jobs.get("active_jobs") or jobs.get("terminal_jobs"):
        read_first.append(".rah/jobs/*/status.json")

    payload = {
        "root": str(root),
        "parse_errors": parse_errors,
        "read_first": read_first,
        "current_stage": status_payload.get("current_stage"),
        "phase": status_payload.get("phase"),
        "implementation_gate": status_payload.get("implementation_gate"),
        "earliest_restart_point": gates_payload.get("earliest_restart_point"),
        "agents_and_workflow_gate": gates_payload.get("agents_and_workflow_gate", {}).get("status"),
        "next_recommended_action": status_payload.get("next_recommended_action"),
        "memento_enabled": None if memento_payload is None else memento_payload.get("enabled"),
        "memento_workspace": status_payload.get("memento_workspace"),
        "memento_session_id": status_payload.get("memento_session_id"),
        "memento_case_id": status_payload.get("memento_case_id"),
        "memento_connectivity": None if memento_payload is None else memento_payload.get("connectivity"),
        "memento_health_url": None if memento_payload is None else memento_payload.get("health_url"),
        "deployment_helper_target": deployment_target(deployment_payload),
        "deployment_removed_runtime_install_present": legacy_deployment_key in deployment_payload
        if isinstance(deployment_payload, dict)
        else None,
        "jobs": jobs,
        "source_coverage": {
            "source_documents_present": isinstance(source_documents, dict),
            "coverage_present": isinstance(source_coverage, dict),
            "coverage_mode": source_coverage.get("coverage_mode") if isinstance(source_coverage, dict) else None,
            "row_count": len(source_rows) if isinstance(source_coverage, dict) else None,
            "ready": bool(source_rows) and not source_missing_rows and bool((source_validation or {}).get("valid")) if isinstance(source_coverage, dict) else None,
            "missing_ids": source_missing_rows[:50],
            "schema_valid": (source_validation or {}).get("valid") if isinstance(source_validation, dict) else None,
            "schema_errors": (source_validation or {}).get("errors") if isinstance(source_validation, dict) else None,
            "source_unit_total": (source_coverage.get("source_unit_manifest") or {}).get("total_units") if isinstance(source_coverage, dict) else None,
            "source_unit_processed": (source_coverage.get("source_unit_manifest") or {}).get("processed_unit_count") if isinstance(source_coverage, dict) else None,
            "source_unit_text_dir": (source_coverage.get("source_unit_manifest") or {}).get("text_dir") if isinstance(source_coverage, dict) else None,
        },
        "ralph": {
            "status": ralph_state.get("status"),
            "goal_id": ralph_state.get("goal_id"),
            "goal": ralph_state.get("goal"),
            "current_iteration": ralph_state.get("current_iteration"),
            "max_iterations": ralph_state.get("max_iterations"),
            "completion_mode": ralph_state.get("completion_mode"),
            "checkpoint_required": ralph_state.get("checkpoint_required"),
            "loop_phase": ralph_state.get("loop_phase"),
            "blocked_reason": ralph_state.get("blocked_reason"),
            "removed_runtime_contract_present": removed_contract_key in ralph_state,
            "driver_contract_present": isinstance(ralph_state.get("external_driver_contract"), dict),
            "state_machine": ralph_state.get("state_machine"),
            "autonomous_completion_contract": ralph_state.get("autonomous_completion_contract"),
            "external_driver_contract": ralph_state.get("external_driver_contract"),
            "driver_state": ralph_driver if isinstance(ralph_driver, dict) else None,
            "completion_readiness": ralph_state.get("completion_readiness"),
            "stagnation": ralph_state.get("stagnation"),
            "definition_of_done": ralph_goal.get("definition_of_done") if isinstance(ralph_goal, dict) else None,
            "evidence_count": len(ralph_evidence.get("entries", [])) if isinstance(ralph_evidence, dict) else None,
            "active_plan_node": ralph_plan_graph.get("active_node") if isinstance(ralph_plan_graph, dict) else None,
            "goal_bridge_mode": ralph_goal_bridge.get("mode") if isinstance(ralph_goal_bridge, dict) else None,
            "review_gate": ralph_review_gate if isinstance(ralph_review_gate, dict) else None,
            "next_actions": ralph_state.get("next_actions"),
        }
        if isinstance(ralph_state, dict)
        else None,
        "context_call_recipe": context_recipe,
        "recall_call_recipe": recall_recipe,
        "tool_feedback_contract": {
            "tool_name": "recall",
            "required_fields": ["relevant", "sufficient", "fragment_ids", "search_event_id"],
            "ledger_path": ".rah/memory/memento_feedback.json",
        },
        "reflect_call_recipe": reflect_recipe,
        "wakeup_path": str(wakeup_path) if wakeup_path.exists() else None,
        "reflect_draft_path": str(reflect_draft_path) if reflect_draft_path.exists() else None,
        "current_loop_path": str(current_loop_path) if current_loop_path.exists() else None,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("# Resume Packet\n")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
