#!/usr/bin/env python3
"""External RALPH driver for repeat-until-terminal RALPH loops.

The driver wraps the host coding agent (`codex exec` under Codex, `claude -p`
under Claude Code) outside the model turn. It auto-detects which runtime
launched it and keeps invoking the matching agent with a compact RALPH
continuation prompt until `.rah/ralph/loop_state.json` reaches a terminal state
(`done`, `blocked`, `cancelled`, or `failed`). This is the Windows-native
hard-continuation driver.
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_engine

SKILL_NAME = "recursive-architecture-refactoring-auto"
SCHEMA_VERSION = 1
TERMINAL_STATUSES = {"done", "blocked", "cancelled", "canceled", "failed"}
SUCCESS_STATUSES = {"done"}
ACTIVE_STATUSES = {"active", "verify", "review", "decide"}
DEFAULT_CYCLE_TIMEOUT_SECONDS = 86400
DEFAULT_MAX_IDLE_CYCLES = 0
DEFAULT_JOB_POLL_SECONDS = 60
MAX_CONSECUTIVE_JOB_SNAPSHOT_ERRORS = 3
DRIVER_CYCLE_ENV = "RAH_DRIVER_CYCLE"
CONTINUATION_AUTHORITY_ENV = "RAH_CONTINUATION_AUTHORITY"

try:
    from long_job_harness import summarize_jobs_for_driver
except Exception:  # pragma: no cover - fallback for partial helper installs
    summarize_jobs_for_driver = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def record_driver_blocker(repo_root: Path, reason: str) -> None:
    now = utc_now()
    write_text(
        repo_root / ".rah" / "ralph" / "driver" / "blockers.md",
        "\n".join(
            [
                "# RALPH Driver Blocker",
                "",
                f"- generated_at_utc: `{now}`",
                f"- driver_blocked_reason: `{reason}`",
                "- ralph_status_preserved: `true`",
                "",
            ]
        ),
    )


def mark_driver_blocked(
    repo_root: Path,
    state: dict[str, Any],
    reason: str,
    *,
    operator_limit_reached: bool = False,
) -> None:
    state["status"] = "driver_blocked"
    state["blocked_reason"] = reason
    state["driver_blocked"] = True
    state["operator_limit_reached"] = operator_limit_reached
    record_driver_blocker(repo_root, reason)


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def is_terminal(loop_state: Any) -> bool:
    if not isinstance(loop_state, dict):
        return False
    return normalize_status(loop_state.get("status")) in TERMINAL_STATUSES


def evidence_count(repo_root: Path) -> int:
    ledger = load_json(repo_root / ".rah" / "ralph" / "evidence_ledger.json")
    if not isinstance(ledger, dict):
        return 0
    entries = ledger.get("entries")
    return len(entries) if isinstance(entries, list) else 0


def review_gate(repo_root: Path) -> dict[str, Any]:
    payload = load_json(repo_root / ".rah" / "ralph" / "review_gate.json")
    return payload if isinstance(payload, dict) else {"status": "missing", "required": True}


def active_plan_node(repo_root: Path) -> dict[str, Any] | None:
    graph = load_json(repo_root / ".rah" / "ralph" / "plan_graph.json")
    if not isinstance(graph, dict):
        return None
    active_id = graph.get("active_node") or graph.get("active_node_id")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == active_id:
            return node
    for node in nodes:
        if isinstance(node, dict) and normalize_status(node.get("status")) in {"active", "in_progress"}:
            return node
    return None


def readiness(loop_state: dict[str, Any]) -> dict[str, Any]:
    value = loop_state.get("completion_readiness")
    return value if isinstance(value, dict) else {}


def compact_list(values: Any, *, limit: int = 12) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    rendered = [str(value) for value in values[:limit]]
    if len(values) > limit:
        rendered.append(f"... {len(values) - limit} more")
    return ", ".join(rendered)


def unavailable_jobs_snapshot(error: str) -> dict[str, Any]:
    return {
        "job_count": None,
        "active_count": 1,
        "terminal_count": None,
        "active_jobs": [
            {
                "job_id": None,
                "name": "job snapshot unavailable",
                "status": "unknown",
            }
        ],
        "terminal_jobs": [],
        "snapshot_status": "unavailable",
        "error": error,
    }


def jobs_snapshot(repo_root: Path) -> dict[str, Any]:
    if summarize_jobs_for_driver is None:
        return unavailable_jobs_snapshot("long_job_harness is unavailable")
    try:
        snapshot = summarize_jobs_for_driver(repo_root)
        if not isinstance(snapshot, dict):
            raise TypeError("long job summary is not an object")
        active_jobs = snapshot.get("active_jobs")
        active_count = snapshot.get("active_count")
        if not isinstance(active_jobs, list):
            raise TypeError("long job summary active_jobs is not a list")
        if isinstance(active_count, bool) or not isinstance(active_count, int):
            raise TypeError("long job summary active_count is not an integer")
        if active_count != len(active_jobs):
            raise ValueError("long job summary active_count does not match active_jobs")
        return snapshot
    except Exception as exc:
        return unavailable_jobs_snapshot(f"{type(exc).__name__}: {exc}")


def job_snapshot_error(snapshot: Any) -> str | None:
    if not isinstance(snapshot, dict):
        return "invalid job snapshot object"
    if snapshot.get("error"):
        return str(snapshot["error"])
    active_jobs = snapshot.get("active_jobs")
    active_count = snapshot.get("active_count")
    if not isinstance(active_jobs, list):
        return "job snapshot active_jobs is not a list"
    if isinstance(active_count, bool) or not isinstance(active_count, int):
        return "job snapshot active_count is not an integer"
    if active_count != len(active_jobs):
        return "job snapshot active_count does not match active_jobs"
    return None


def job_snapshot_ready_for_agent(snapshot: Any) -> bool:
    return job_snapshot_error(snapshot) is None and snapshot.get("active_count") == 0


def state_signature(
    repo_root: Path,
    loop_state: Any,
    *,
    job_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    jobs = job_state if job_state is not None else jobs_snapshot(repo_root)
    if not isinstance(loop_state, dict):
        return {"status": None, "evidence_count": evidence_count(repo_root), "jobs": jobs}
    ready = readiness(loop_state)
    node = active_plan_node(repo_root)
    return {
        "status": normalize_status(loop_state.get("status")),
        "iteration": loop_state.get("current_iteration"),
        "completion_ready": ready.get("ready"),
        "missing_acceptance_ids": ready.get("missing_acceptance_ids"),
        "missing_validation_ids": ready.get("missing_validation_ids"),
        "missing_closeout_ids": ready.get("missing_closeout_ids"),
        "source_coverage_required": ready.get("source_coverage_required"),
        "source_coverage_missing_ids": ready.get("source_coverage_missing_ids"),
        "source_coverage_missing_evidence_ids": ready.get("source_coverage_missing_evidence_ids"),
        "source_coverage_missing_validation_ids": ready.get("source_coverage_missing_validation_ids"),
        "source_unit_total": ready.get("source_unit_total"),
        "source_unit_processed": ready.get("source_unit_processed"),
        "source_unit_blocked_ids": ready.get("source_unit_blocked_ids"),
        "source_unit_text_missing_ids": ready.get("source_unit_text_missing_ids"),
        "evidence_count": evidence_count(repo_root),
        "review_status": review_gate(repo_root).get("status"),
        "active_node": node.get("id") if isinstance(node, dict) else None,
        "jobs": {
            "active_count": jobs.get("active_count"),
            "terminal_count": jobs.get("terminal_count"),
            "latest_updated_at_utc": jobs.get("latest_updated_at_utc"),
            "snapshot_status": jobs.get("snapshot_status"),
            "error": jobs.get("error"),
        },
    }


# Canonical engine detection/binary resolution lives in agent_engine so the
# serial driver and the parallel fleet build identical invocations.
resolve_engine = agent_engine.resolve_engine
resolve_codex_bin = agent_engine.resolve_codex_bin
resolve_claude_bin = agent_engine.resolve_claude_bin
resolve_agent_bin = agent_engine.resolve_agent_bin


def command_token(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def run_helper(script_dir: Path, script_name: str, args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-B", str(script_dir / script_name), *args]
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        cmd,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )


def bootstrap_if_missing(repo_root: Path, script_dir: Path, project_name: str | None) -> None:
    required = [
        repo_root / ".rah" / "state" / "status.json",
        repo_root / ".rah" / "state" / "gates.json",
        repo_root / "docs" / "architecture" / "Phytoritas.md",
    ]
    if all(path.exists() for path in required):
        return
    result = run_helper(
        script_dir,
        "bootstrap_scaffold.py",
        [str(repo_root), "--project-name", project_name or repo_root.name],
        capture=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            json.dumps(
                {
                    "error": "driver bootstrap failed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                ensure_ascii=False,
            )
        )


def initialize_ralph(args: argparse.Namespace, script_dir: Path, repo_root: Path) -> None:
    loop_path = repo_root / ".rah" / "ralph" / "loop_state.json"
    goal_path = repo_root / ".rah" / "ralph" / "goal.json"
    if args.reset and not args.goal:
        raise SystemExit("--reset requires --goal so the archived state is replaced by an explicit new objective.")
    if loop_path.exists() and not args.reset:
        existing_goal = load_json(goal_path)
        existing_loop = load_json(loop_path)
        if args.goal:
            current_goal = ""
            if isinstance(existing_goal, dict) and existing_goal.get("goal"):
                current_goal = str(existing_goal.get("goal") or "")
            elif isinstance(existing_loop, dict):
                current_goal = str(existing_loop.get("goal") or existing_loop.get("objective") or "")
            if current_goal != args.goal:
                existing_status = str(
                    (existing_loop.get("status") if isinstance(existing_loop, dict) else None)
                    or (existing_goal.get("status") if isinstance(existing_goal, dict) else None)
                    or ""
                ).lower()
                if existing_status in TERMINAL_STATUSES and (args.replace_terminal_goal or existing_status != "blocked"):
                    ralph_args = [str(repo_root), "--goal", args.goal, "--completion-mode", args.completion_mode, "--replace-terminal-goal"]
                    if args.max_iterations:
                        ralph_args.extend(["--max-iterations", str(args.max_iterations)])
                    for item in args.acceptance:
                        ralph_args.extend(["--acceptance", item])
                    for item in args.validation:
                        ralph_args.extend(["--validation", item])
                    result = run_helper(script_dir, "ralph_harness.py", ralph_args, capture=True)
                    if result.returncode != 0:
                        raise SystemExit(
                            json.dumps(
                                {
                                    "error": "driver RALPH terminal-goal replacement failed",
                                    "returncode": result.returncode,
                                    "stdout": result.stdout,
                                    "stderr": result.stderr,
                                },
                                ensure_ascii=False,
                            )
                        )
                    return
                raise SystemExit(
                    "Existing RALPH state has a different active/blocked goal. Use --reset, --replace-terminal-goal for blocked terminal state, or omit --goal to resume."
                )
        return
    if not args.goal and not loop_path.exists():
        raise SystemExit("--goal is required when no active RALPH state exists.")

    ralph_args = [str(repo_root), "--goal", args.goal, "--completion-mode", args.completion_mode]
    if args.max_iterations:
        ralph_args.extend(["--max-iterations", str(args.max_iterations)])
    if args.reset:
        ralph_args.append("--reset")
    if args.replace_terminal_goal:
        ralph_args.append("--replace-terminal-goal")
    for item in args.acceptance:
        ralph_args.extend(["--acceptance", item])
    for item in args.validation:
        ralph_args.extend(["--validation", item])

    result = run_helper(script_dir, "ralph_harness.py", ralph_args, capture=True)
    if result.returncode != 0:
        raise SystemExit(
            json.dumps(
                {
                    "error": "driver RALPH initialization failed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                ensure_ascii=False,
            )
        )


def fleet_snapshot(repo_root: Path) -> str:
    runs = repo_root / ".rah" / "fleet" / "runs"
    if not runs.exists():
        return "none"
    candidates = sorted(child.name for child in runs.iterdir() if child.is_dir())
    if not candidates:
        return "none"
    latest = runs / candidates[-1]
    state = load_json(latest / "state.json") or {}
    questions_root = latest / "mailbox" / "questions"
    replies_root = latest / "mailbox" / "replies"
    open_questions = 0
    if questions_root.exists():
        open_questions = sum(
            1 for question in questions_root.glob("q-*.json")
            if not (replies_root / question.name).exists()
        )
    return (
        f"{candidates[-1]} status={state.get('status')} template={state.get('template')} "
        f"open_questions={open_questions}"
    )


def build_prompt(
    repo_root: Path,
    loop_state: dict[str, Any],
    *,
    cycle: int,
    idle_cycles: int,
    extra: str | None,
    engine: str,
    job_state: dict[str, Any] | None = None,
) -> str:
    goal = load_json(repo_root / ".rah" / "ralph" / "goal.json")
    ready = readiness(loop_state)
    review = review_gate(repo_root)
    node = active_plan_node(repo_root)
    jobs = job_state if job_state is not None else jobs_snapshot(repo_root)
    objective = goal.get("goal") or goal.get("objective") if isinstance(goal, dict) else loop_state.get("goal")
    node_line = "none"
    if isinstance(node, dict):
        node_line = f"{node.get('id')} / {node.get('status')} / {node.get('title') or node.get('label') or node.get('summary')}"

    if engine == "claude":
        skill_line = f"Use the /{SKILL_NAME} skill."
        invoke_line = "This Claude Code (`claude -p`) invocation is one bounded continuation cycle. The external driver will re-run Claude Code if RALPH remains active."
        cycle_term = "`claude -p` cycle"
        agent_name = "Claude Code"
    else:
        skill_line = f"Use the ${SKILL_NAME} skill."
        invoke_line = "This Codex exec invocation is one bounded continuation cycle. The external driver will re-run Codex if RALPH remains active."
        cycle_term = "`codex exec`"
        agent_name = "Codex"

    fleet_line = fleet_snapshot(repo_root)
    review_status = str(review.get("status") or "missing").lower()
    review_duty_relevant = review.get("required") is not False and (
        review_status not in {"not_requested", "missing", "approved"} or bool(ready.get("ready"))
    )

    # Section order is a provider prompt-cache contract: everything up to and
    # including "Required sequence:" is byte-identical across cycles of a run,
    # so a fresh child process still lands prefix-cache hits. Volatile state
    # and phase-gated duties live at the tail — never above the static block.
    lines = [
        skill_line,
        "",
        "You are running under the RAH external RALPH driver.",
        invoke_line,
        "",
        "Hard contract:",
        "- External driver mode overrides the in-turn no-yield rule: do exactly one bounded continuation cycle, then return control to the driver unless the goal is terminal.",
        "- Do not claim the objective is complete unless `.rah/ralph/loop_state.json` has status `done`.",
        "- If source coverage exists or is required, source coverage must be complete before the goal can be done.",
        "- If the objective is not complete, perform the next bounded phase and leave RALPH state active for the driver to continue.",
        "- If no meaningful progress is possible, record a durable blocker with `rah.py ralph <repo-root> --block \"<reason>\"`.",
        "- Record concrete evidence before marking acceptance or validation rows.",
        f"- For long computations, launch a supervised external job with `rah.py job <repo-root> launch -- <command>` and return control; do not wait inside {cycle_term}.",
        f"- Do not keep working indefinitely inside this single {cycle_term}; the parent driver owns repetition across cycles.",
        "",
        "Required sequence:",
        "1. Read the nearest `AGENTS.md` and the RALPH files under `.rah/ralph/`.",
        "2. If `.rah/ralph/source_requirement_coverage.json` exists, read it and continue uncovered rows before broad closeout. If `.rah/ralph/prd.json` exists, treat it only as a planning view — completion authority stays with source coverage — and when prd_required is true run `rah.py prd <repo-root> validate` before review or mark-done.",
        "3. Read `docs/architecture/Phytoritas.md` and `.rah/plans/current_loop.md` if they exist.",
        "4. Execute the smallest phase that advances the active plan node or next uncovered source coverage row.",
        "5. Run targeted validation and inspect failures.",
        f"6. If the next step is a 30+ minute computation, launch it as an external job and leave RALPH active; the driver will poll `.rah/jobs` instead of invoking {agent_name} while the job runs.",
        "7. When an external job completes, inspect `rah.py job <repo-root> status <job-id>` and record its evidence note before marking rows.",
        "8. Update source coverage, RALPH evidence, and row statuses, for example:",
        f"   `python {command_token(str(repo_root / '.rah' / 'helpers' / SKILL_NAME / 'automation' / 'rah.py'))} ralph {command_token(repo_root)} --record-evidence \"<observed proof>\" --acceptance-met A1 --validation-passed V1`",
        "9. Run `rah.py ralph <repo-root> --closeout-check` before review; mark C-rows with `--closeout-met C1` or `--closeout-documented C1` only with evidence.",
        "10. When source coverage, acceptance, validation, closeout, and evidence are ready, request reviewer verification with `--request-review`; follow the reviewer duties below when they apply.",
        "11. Only after readiness is true and review is approved, run the same helper with `--mark-done`.",
        "12. Before final response, re-read `.rah/ralph/loop_state.json`; if status is still active, summarize only the cycle progress, leave state active, and return control to the driver.",
    ]
    if extra:
        lines.extend(["", "Additional user/driver instruction:", extra])

    duty_lines: list[str] = []
    if fleet_line != "none":
        duty_lines.extend(
            [
                "- If a fleet run is awaiting verdicts, YOU are the brain for this cycle: read `.rah/fleet/runs/<run-id>/review_packet.md`, review each patch diff yourself, record `rah.py fleet <repo-root> verdict <run-id> --story <id> --approve --evidence ... --validation ... --semantic ... --provenance ... --negative-test ...` or `--reject --rework ...`, then `rah.py fleet <repo-root> resume <run-id>`. All five approval proof fields must be brain-authored; fleet workers are implementation-only and their claims cannot satisfy coverage.",
                "- If a fleet run is awaiting_brain, inspect `rah.py fleet <repo-root> monitor <run-id> --include-content --json`; answer each bounded worker question with `fleet reply --question <id> --message-file <path>`, then `fleet resume`. A reply is next-round input, never approval evidence.",
            ]
        )
    if review_duty_relevant:
        duty_lines.extend(
            [
                "- If reviewer verification is pending and a reviewer agent/thread exists, call `wait_agent` with the maximum practical timeout (default policy: 3600000 ms). Keep waiting/retrying until reviewer approval or rejection arrives; no-response, pending status, or wait timeout is not completion, blocker, or fallback evidence.",
                "- Use `--review-fallback` only for an explicit tool/runtime failure to spawn or access the reviewer path, never for ordinary reviewer latency or no response.",
            ]
        )
    if duty_lines:
        lines.extend(["", "Phase duties (this cycle):", *duty_lines])

    state_lines = [
        "",
        "Current RALPH state:",
        f"- repo_root: {repo_root}",
        f"- cycle: {cycle}",
        f"- idle_cycles_seen_by_driver: {idle_cycles}",
        f"- goal_id: {loop_state.get('goal_id')}",
        f"- objective: {objective}",
        f"- status: {loop_state.get('status')}",
        f"- iteration: {loop_state.get('current_iteration')} / {loop_state.get('max_iterations')}",
        f"- completion_mode: {loop_state.get('completion_mode')}",
        f"- completion_ready: {ready.get('ready')}",
        f"- review_required: {review.get('required')}",
        f"- review_status: {review.get('status')}",
        f"- source_coverage_required: {ready.get('source_coverage_required')}",
        f"- source_coverage_ready: {ready.get('source_coverage_ready')}",
        f"- fleet_run: {fleet_line}",
        f"- evidence_entries: {evidence_count(repo_root)}",
        f"- active_plan_node: {node_line}",
        f"- external_jobs_active: {jobs.get('active_count')}",
    ]
    if jobs.get("error"):
        state_lines.append(f"- external_jobs_snapshot_error: {jobs.get('error')}")
    if loop_state.get("checkpoint_required"):
        state_lines.append(f"- checkpoint_required: {loop_state.get('checkpoint_required')}")
    if jobs.get("terminal_count"):
        state_lines.append(f"- external_jobs_terminal: {jobs.get('terminal_count')}")
    if ready.get("source_coverage_present"):
        state_lines.extend(
            [
                f"- source_coverage_present: {ready.get('source_coverage_present')}",
                f"- source_coverage_total_rows: {ready.get('source_coverage_total_rows')}",
                f"- source_unit_total: {ready.get('source_unit_total')}",
                f"- source_unit_processed: {ready.get('source_unit_processed')}",
            ]
        )
    for label, key in (
        ("missing_acceptance_ids", "missing_acceptance_ids"),
        ("missing_validation_ids", "missing_validation_ids"),
        ("missing_closeout_ids", "missing_closeout_ids"),
        ("source_unit_blocked_ids", "source_unit_blocked_ids"),
        ("source_unit_text_missing_ids", "source_unit_text_missing_ids"),
        ("source_coverage_missing_ids", "source_coverage_missing_ids"),
        ("source_coverage_missing_evidence_ids", "source_coverage_missing_evidence_ids"),
        ("source_coverage_missing_validation_ids", "source_coverage_missing_validation_ids"),
        ("source_coverage_invalid_row_ids", "source_coverage_invalid_row_ids"),
    ):
        if ready.get(key):
            state_lines.append(f"- {label}: {compact_list(ready.get(key))}")
    if ready.get("prd_present") or ready.get("prd_required"):
        state_lines.extend(
            [
                f"- prd_present: {ready.get('prd_present')}",
                f"- prd_required: {ready.get('prd_required')}",
                f"- prd_ready: {ready.get('prd_ready')}",
                f"- prd_stale: {ready.get('prd_stale')}",
            ]
        )
    lines.extend(state_lines)

    if idle_cycles:
        lines.extend(
            [
                "",
                "Driver warning:",
                f"- The previous {idle_cycles} cycle(s) did not change the RALPH progress signature.",
                "- This cycle must update evidence/acceptance/validation/closeout/review state or record a concrete blocker.",
            ]
        )
    return "\n".join(lines)


def usage_ledger_path(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph" / "driver" / "usage.jsonl"


def append_usage_record(repo_root: Path, record: dict[str, Any]) -> None:
    """Append one per-cycle usage line. Strictly fail-open telemetry: any
    failure here must never affect the drive loop. Lives under
    .rah/ralph/driver/, outside the six generation-bound state files."""
    try:
        append_text(usage_ledger_path(repo_root), json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def driver_state_path(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph" / "driver" / "driver_state.json"


def driver_control_path(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph" / "driver" / "control.json"


def driver_control(repo_root: Path) -> dict[str, Any]:
    payload = load_json(driver_control_path(repo_root))
    return payload if isinstance(payload, dict) else {"status": "running"}


def cycle_dir(repo_root: Path, cycle: int) -> Path:
    return repo_root / ".rah" / "ralph" / "driver" / "cycles" / f"{cycle:04d}"


_CYCLE_DIR_RE = re.compile(r"^\d{4}$")


def prune_cycle_dirs(repo_root: Path, keep: int, current_cycle: int) -> None:
    """Bound the per-cycle artifact directories to the newest ``keep`` (plus
    the current cycle). ``keep <= 0`` keeps everything. Fail-open: a locked or
    unreadable directory simply survives to the next prune."""
    if keep <= 0:
        return
    cycles_root = repo_root / ".rah" / "ralph" / "driver" / "cycles"
    try:
        names = sorted(child.name for child in cycles_root.iterdir() if child.is_dir() and _CYCLE_DIR_RE.match(child.name))
    except OSError:
        return
    if len(names) <= keep:
        return
    current_name = f"{current_cycle:04d}"
    survivors = set(names[-keep:])
    survivors.add(current_name)
    for name in names:
        if name in survivors:
            continue
        shutil.rmtree(cycles_root / name, ignore_errors=True)


def update_driver_state(repo_root: Path, payload: dict[str, Any]) -> None:
    payload["updated_at_utc"] = utc_now()
    write_json(driver_state_path(repo_root), payload)


def append_driver_event(state: dict[str, Any], event: dict[str, Any]) -> None:
    state.setdefault("events", []).append(event)
    if len(state["events"]) > 200:
        state["events"] = state["events"][-200:]


def wait_for_external_jobs(repo_root: Path, args: argparse.Namespace, state: dict[str, Any]) -> tuple[str, str | None]:
    waited = 0
    announced_signature: Any = None
    consecutive_snapshot_errors = 0
    while True:
        snapshot = jobs_snapshot(repo_root)
        active_jobs = snapshot.get("active_jobs") if isinstance(snapshot, dict) else []
        snapshot_error = job_snapshot_error(snapshot)
        if job_snapshot_ready_for_agent(snapshot):
            state["job_snapshot"] = snapshot
            update_driver_state(repo_root, state)
            return "ready", None
        if snapshot_error:
            consecutive_snapshot_errors += 1
        else:
            consecutive_snapshot_errors = 0

        control = driver_control(repo_root)
        control_status = normalize_status(control.get("status"))
        if control_status == "paused":
            return "paused", control.get("reason") or "driver paused by operator while waiting for external jobs"
        if control_status in {"cancelled", "canceled"}:
            return "cancelled", control.get("reason") or "driver cancelled by operator while waiting for external jobs"

        signature = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
        if signature != announced_signature:
            append_driver_event(
                state,
                {
                    "at_utc": utc_now(),
                    "event": "external_jobs_wait",
                    "active_count": snapshot.get("active_count"),
                    "active_jobs": active_jobs,
                    "snapshot_error": snapshot_error,
                    "consecutive_snapshot_errors": consecutive_snapshot_errors,
                    "waited_seconds": waited,
                },
            )
            announced_signature = signature

        state["status"] = "waiting_for_external_jobs"
        state["job_snapshot"] = snapshot
        update_driver_state(repo_root, state)

        if consecutive_snapshot_errors >= MAX_CONSECUTIVE_JOB_SNAPSHOT_ERRORS:
            return (
                "error",
                "External job snapshot remained unavailable for "
                f"{consecutive_snapshot_errors} consecutive polls: {snapshot_error}",
            )
        if args.job_max_wait_seconds and waited >= args.job_max_wait_seconds:
            return "timeout", f"External job wait limit reached ({args.job_max_wait_seconds}s) while jobs remained active."

        sleep_seconds = max(1, int(args.job_poll_seconds))
        time.sleep(sleep_seconds)
        waited += sleep_seconds


def structured_output_enabled() -> bool:
    """Env escape hatch: RAH_DRIVER_PLAIN_OUTPUT=1 restores plain engine
    stdout (no --json / json envelope) and disables usage harvesting."""
    return os.environ.get("RAH_DRIVER_PLAIN_OUTPUT", "").strip() != "1"


def build_codex_command(args: argparse.Namespace, codex_bin: str, repo_root: Path, prompt: str, last_message_path: Path) -> list[str]:
    del prompt  # fed via stdin by run_agent_cycle; kept in the signature for call-site clarity
    return agent_engine.build_codex_exec_command(
        codex_bin,
        repo_root,
        last_message_path,
        model=args.model,
        sandbox=args.sandbox,
        bypass_approvals_and_sandbox=args.dangerously_bypass_approvals_and_sandbox,
        extra_args=args.codex_arg,
        json_events=structured_output_enabled(),
    )


def build_claude_command(args: argparse.Namespace, claude_bin: str) -> list[str]:
    return agent_engine.build_claude_print_command(
        claude_bin,
        model=args.model,
        permission_mode=args.permission_mode,
        dangerously_skip_permissions=args.dangerously_skip_permissions,
        extra_args=args.claude_arg,
        output_format="json" if structured_output_enabled() else "text",
    )


terminate_process_tree = agent_engine.terminate_process_tree


def append_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(content)
        handle.flush()


def pump_pipe_to_file(pipe: Any, target: Path, chunks: list[str]) -> None:
    try:
        with target.open("a", encoding="utf-8", newline="") as handle:
            for chunk in iter(pipe.readline, ""):
                chunks.append(chunk)
                handle.write(chunk)
                handle.flush()
    except Exception as exc:
        note = f"\n[RAH driver] failed to stream {target.name}: {exc}\n"
        chunks.append(note)
        try:
            append_text(target, note)
        except OSError:
            pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def agent_cycle_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return child-only markers for one externally driven agent cycle."""

    environment = dict(os.environ if base is None else base)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    environment[DRIVER_CYCLE_ENV] = "1"
    environment[CONTINUATION_AUTHORITY_ENV] = "external-drive"
    return environment


def run_agent_cycle(cmd: list[str], prompt: str, timeout_seconds: int, stdout_path: Path, stderr_path: Path, cwd: Path | None, label: str) -> tuple[int, str, str, bool]:
    write_text(stdout_path, "")
    write_text(stderr_path, "")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=(str(cwd) if cwd else None),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=agent_cycle_environment(),
        )
    except OSError as exc:
        return 126, "", f"[RAH driver] failed to start {label}: {exc}\n", False

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_thread = threading.Thread(target=pump_pipe_to_file, args=(process.stdout, stdout_path, stdout_chunks), daemon=True)
    stderr_thread = threading.Thread(target=pump_pipe_to_file, args=(process.stderr, stderr_path, stderr_chunks), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    if process.stdin is not None:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            note = f"[RAH driver] {label} stdin closed before prompt write completed: {exc}\n"
            stderr_chunks.append(note)
            append_text(stderr_path, note)

    try:
        process.wait(timeout=timeout_seconds if timeout_seconds > 0 else None)
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        return int(process.returncode or 0), "".join(stdout_chunks), "".join(stderr_chunks), False
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        stdout_text = "".join(stdout_chunks)
        stderr_text = "".join(stderr_chunks)
        timeout_note = f"\n[RAH driver] {label} exceeded cycle timeout ({timeout_seconds}s) and was terminated.\n"
        append_text(stderr_path, timeout_note)
        return int(process.returncode or 124), stdout_text, stderr_text + timeout_note, True


AGENT_FAILURE_BACKOFF_BASE_SECONDS = 60
AGENT_FAILURE_BACKOFF_CAP_SECONDS = 3600


def agent_failure_backoff_seconds(streak: int) -> int:
    """Exponential backoff for consecutive non-zero agent exits (60s -> 1h cap).

    Usage-limit exits recover on their own once the provider window resets; a
    capped backoff keeps the driver alive without hammering the nested CLI.
    """
    if streak <= 0:
        return 0
    return min(AGENT_FAILURE_BACKOFF_CAP_SECONDS, AGENT_FAILURE_BACKOFF_BASE_SECONDS * (2 ** (streak - 1)))


def main() -> int:
    parser = _SuggestingArgumentParser(description="Drive a RALPH loop by repeatedly invoking codex exec until terminal state.")
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument("--goal", default=None, help="Goal to initialize before driving. Required if no RALPH state exists.")
    parser.add_argument("--acceptance", action="append", default=[], help="Acceptance criterion to pass into initial RALPH state.")
    parser.add_argument("--validation", action="append", default=[], help="Validation check to pass into initial RALPH state.")
    parser.add_argument("--completion-mode", choices=["bounded", "exhaustive"], default="exhaustive")
    parser.add_argument("--max-iterations", type=int, default=None, help="Initial RALPH iteration checkpoint/limit.")
    parser.add_argument("--reset", action="store_true", help="Reset RALPH state before driving.")
    parser.add_argument("--replace-terminal-goal", action="store_true", help="Archive terminal stale RALPH state if --goal differs before driving.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Driver cycle limit. 0 means unlimited until terminal RALPH status.")
    parser.add_argument(
        "--keep-cycle-dirs",
        type=int,
        default=20,
        help="Retain only the newest N per-cycle artifact directories under .rah/ralph/driver/cycles/. 0 keeps all (unbounded growth).",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        default=DEFAULT_MAX_IDLE_CYCLES,
        help="Optional idle-cycle blocker. Default is 0, meaning no automatic stop for no-progress/no-response cycles.",
    )
    parser.add_argument(
        "--max-agent-failure-streak",
        type=int,
        default=0,
        help=(
            "Optional guard for consecutive non-zero agent exits (usage limits, transient CLI failures). "
            "Default is 0: the driver backs off (60s doubling to a 1h cap) and retries instead of blocking."
        ),
    )
    parser.add_argument(
        "--cycle-timeout-seconds",
        type=int,
        default=DEFAULT_CYCLE_TIMEOUT_SECONDS,
        help="Maximum seconds for one codex exec cycle. Default is 86400 (24 hours); 0 disables the per-cycle timeout.",
    )
    parser.add_argument(
        "--job-poll-seconds",
        type=int,
        default=DEFAULT_JOB_POLL_SECONDS,
        help="Seconds between external job polls while .rah/jobs has active supervised jobs.",
    )
    parser.add_argument(
        "--job-max-wait-seconds",
        type=int,
        default=0,
        help="Maximum external job wait before blocking the driver. 0 means wait until jobs are terminal.",
    )
    parser.add_argument("--project-name", default=None, help="Project name for bootstrap if needed.")
    parser.add_argument(
        "--engine",
        choices=["auto", "codex", "claude"],
        default="auto",
        help="Host agent that runs each RALPH cycle. 'auto' detects the runtime (Claude Code -> claude, Codex -> codex) and falls back to codex.",
    )
    parser.add_argument("--model", default=None, help="Optional model override (codex exec -m / claude --model).")
    # Codex engine options
    parser.add_argument("--codex-bin", default=None, help="Path to codex/codex.cmd. Defaults to PATH lookup. (engine=codex)")
    parser.add_argument("--sandbox", default=None, help="Optional codex exec sandbox override. (engine=codex)")
    parser.add_argument("--codex-arg", action="append", default=[], help="Extra raw argument passed to codex exec. Repeat for each token. (engine=codex)")
    parser.add_argument(
        "--dangerously-bypass-approvals-and-sandbox",
        action="store_true",
        help="Forward Codex's approval/sandbox bypass to nested codex exec for fully unattended driver runs. (engine=codex)",
    )
    # Claude Code engine options
    parser.add_argument("--claude-bin", default=None, help="Path to claude/claude.cmd. Defaults to PATH lookup. (engine=claude)")
    parser.add_argument("--permission-mode", default=None, help="Optional claude --permission-mode for the nested cycle. (engine=claude)")
    parser.add_argument("--claude-arg", action="append", default=[], help="Extra raw argument passed to claude -p. Repeat for each token. (engine=claude)")
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Forward claude --dangerously-skip-permissions to nested claude -p for fully unattended driver runs. (engine=claude)",
    )
    parser.add_argument("--extra-prompt", default=None, help="Additional instruction appended to every continuation prompt.")
    parser.add_argument("--extra-prompt-file", default=None, help="Path to additional instruction text for long driver prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Write the next prompt and driver state without invoking the host agent.")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary only.")
    args = parser.parse_args()

    if args.max_cycles < 0:
        print(json.dumps({"error": "--max-cycles must be >= 0"}, ensure_ascii=False))
        return 2
    if args.keep_cycle_dirs < 0:
        print(json.dumps({"error": "--keep-cycle-dirs must be >= 0"}, ensure_ascii=False))
        return 2
    if args.max_idle_cycles < 0:
        print(json.dumps({"error": "--max-idle-cycles must be >= 0"}, ensure_ascii=False))
        return 2
    if args.max_agent_failure_streak < 0:
        print(json.dumps({"error": "--max-agent-failure-streak must be >= 0"}, ensure_ascii=False))
        return 2
    if args.cycle_timeout_seconds < 0:
        print(json.dumps({"error": "--cycle-timeout-seconds must be >= 0"}, ensure_ascii=False))
        return 2
    if args.job_poll_seconds < 1:
        print(json.dumps({"error": "--job-poll-seconds must be >= 1"}, ensure_ascii=False))
        return 2
    if args.job_max_wait_seconds < 0:
        print(json.dumps({"error": "--job-max-wait-seconds must be >= 0"}, ensure_ascii=False))
        return 2
    extra_prompt = args.extra_prompt
    if args.extra_prompt_file:
        extra_path = Path(args.extra_prompt_file).expanduser().resolve()
        if not extra_path.exists() or not extra_path.is_file():
            print(json.dumps({"error": f"Missing --extra-prompt-file: {extra_path}"}, ensure_ascii=False))
            return 2
        file_extra = extra_path.read_text(encoding="utf-8")
        extra_prompt = "\n\n".join(item for item in [extra_prompt, file_extra] if item)

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(json.dumps({"error": f"Missing repo root: {repo_root}"}, ensure_ascii=False))
        return 2

    script_dir = Path(__file__).resolve().parent
    try:
        bootstrap_if_missing(repo_root, script_dir, args.project_name)
        initialize_ralph(args, script_dir, repo_root)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    engine = resolve_engine(args.engine)
    agent_bin = resolve_agent_bin(engine, args.codex_bin, args.claude_bin)
    agent_label = "codex exec" if engine == "codex" else "claude -p"
    agent_cwd = None if engine == "codex" else repo_root
    started_at = utc_now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "started_at_utc": started_at,
        "updated_at_utc": started_at,
        "repo_root": str(repo_root),
        "engine": engine,
        "agent_bin": agent_bin,
        "status": "running",
        "cycles_run": 0,
        "max_cycles": args.max_cycles,
        "keep_cycle_dirs": args.keep_cycle_dirs,
        "max_idle_cycles": args.max_idle_cycles,
        "max_agent_failure_streak": args.max_agent_failure_streak,
        "cycle_timeout_seconds": args.cycle_timeout_seconds,
        "job_poll_seconds": args.job_poll_seconds,
        "job_max_wait_seconds": args.job_max_wait_seconds,
        "events": [],
    }

    idle_cycles = 0
    agent_failure_streak = 0
    prelaunch_job_guard_failures = 0
    cycle = 0

    while True:
        control = driver_control(repo_root)
        control_status = normalize_status(control.get("status"))
        if control_status == "paused":
            state["status"] = "paused"
            state["blocked_reason"] = control.get("reason") or "driver paused by operator"
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 5
        if control_status in {"cancelled", "canceled"}:
            state["status"] = "cancelled"
            state["blocked_reason"] = control.get("reason") or "driver cancelled by operator"
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 3

        loop_state = load_json(repo_root / ".rah" / "ralph" / "loop_state.json")
        if not isinstance(loop_state, dict):
            mark_driver_blocked(repo_root, state, "Missing or invalid .rah/ralph/loop_state.json")
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 4

        status = normalize_status(loop_state.get("status"))
        if status in TERMINAL_STATUSES:
            state["status"] = status
            state["terminal_status"] = status
            state["cycles_run"] = cycle
            append_driver_event(state, {"at_utc": utc_now(), "event": "terminal_state_detected", "status": status})
            update_driver_state(repo_root, state)
            if not args.json:
                print(f"RAH driver terminal state: {status}")
            else:
                print(json.dumps(state, indent=2, ensure_ascii=False))
            return 0 if status in SUCCESS_STATUSES else 3

        if status not in ACTIVE_STATUSES:
            reason = f"Unknown RALPH status: {status}"
            mark_driver_blocked(repo_root, state, reason)
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 4

        wait_status, wait_reason = wait_for_external_jobs(repo_root, args, state)
        if wait_status == "paused":
            state["status"] = "paused"
            state["blocked_reason"] = wait_reason
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 5
        if wait_status == "cancelled":
            state["status"] = "cancelled"
            state["blocked_reason"] = wait_reason
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 3
        if wait_status == "timeout":
            reason = wait_reason or "External job wait limit reached."
            mark_driver_blocked(repo_root, state, reason, operator_limit_reached=True)
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 4
        if wait_status == "error":
            reason = wait_reason or "External job snapshot remained unavailable."
            mark_driver_blocked(repo_root, state, reason)
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 4

        if args.max_cycles and cycle >= args.max_cycles:
            reason = f"Driver max cycles reached ({args.max_cycles}) while RALPH remained active."
            mark_driver_blocked(repo_root, state, reason, operator_limit_reached=True)
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 4

        prelaunch_job_state = jobs_snapshot(repo_root)
        if not job_snapshot_ready_for_agent(prelaunch_job_state):
            prelaunch_job_guard_failures += 1
            append_driver_event(
                state,
                {
                    "at_utc": utc_now(),
                    "event": "prelaunch_job_guard_wait",
                    "job_snapshot": prelaunch_job_state,
                    "consecutive_failures": prelaunch_job_guard_failures,
                },
            )
            state["status"] = "waiting_for_external_jobs"
            state["job_snapshot"] = prelaunch_job_state
            state["prelaunch_job_guard_failures"] = prelaunch_job_guard_failures
            if prelaunch_job_guard_failures >= MAX_CONSECUTIVE_JOB_SNAPSHOT_ERRORS:
                reason = (
                    "Prelaunch job guard remained unsafe for "
                    f"{prelaunch_job_guard_failures} checks: "
                    f"{job_snapshot_error(prelaunch_job_state) or 'external jobs became active'}"
                )
                mark_driver_blocked(repo_root, state, reason)
                update_driver_state(repo_root, state)
                print(json.dumps(state, indent=2, ensure_ascii=False))
                return 4
            update_driver_state(repo_root, state)
            continue

        cycle += 1
        prompt = build_prompt(
            repo_root,
            loop_state,
            cycle=cycle,
            idle_cycles=idle_cycles,
            extra=extra_prompt,
            engine=engine,
            job_state=prelaunch_job_state,
        )
        cdir = cycle_dir(repo_root, cycle)
        prompt_path = cdir / "prompt.md"
        stdout_path = cdir / "stdout.log"
        stderr_path = cdir / "stderr.log"
        last_message_path = cdir / "last_message.md"
        write_text(prompt_path, prompt)
        write_text(stdout_path, "")
        write_text(stderr_path, "")
        write_text(last_message_path, "")

        signature_before = state_signature(
            repo_root,
            loop_state,
            job_state=prelaunch_job_state,
        )
        if args.dry_run:
            state["status"] = "dry_run"
            state["cycles_run"] = 0
            state["next_prompt_path"] = str(prompt_path)
            state["signature_before"] = signature_before
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 0

        if engine == "codex":
            cmd = build_codex_command(args, agent_bin, repo_root, prompt, last_message_path)
        else:
            cmd = build_claude_command(args, agent_bin)

        final_launch_job_state = jobs_snapshot(repo_root)
        if not job_snapshot_ready_for_agent(final_launch_job_state):
            prelaunch_job_guard_failures += 1
            append_driver_event(
                state,
                {
                    "at_utc": utc_now(),
                    "event": "agent_launch_suppressed_by_job_guard",
                    "cycle": cycle,
                    "job_snapshot": final_launch_job_state,
                    "consecutive_failures": prelaunch_job_guard_failures,
                },
            )
            state["status"] = "waiting_for_external_jobs"
            state["job_snapshot"] = final_launch_job_state
            state["prelaunch_job_guard_failures"] = prelaunch_job_guard_failures
            cycle -= 1
            if prelaunch_job_guard_failures >= MAX_CONSECUTIVE_JOB_SNAPSHOT_ERRORS:
                reason = (
                    "Agent launch job guard remained unsafe for "
                    f"{prelaunch_job_guard_failures} checks: "
                    f"{job_snapshot_error(final_launch_job_state) or 'external jobs became active'}"
                )
                mark_driver_blocked(repo_root, state, reason)
                update_driver_state(repo_root, state)
                print(json.dumps(state, indent=2, ensure_ascii=False))
                return 4
            update_driver_state(repo_root, state)
            continue

        prelaunch_job_guard_failures = 0
        state["prelaunch_job_guard_failures"] = 0
        append_driver_event(
            state,
            {
                "at_utc": utc_now(),
                "event": "cycle_start",
                "cycle": cycle,
                "prompt_path": str(prompt_path),
                "signature_before": signature_before,
            },
        )
        update_driver_state(repo_root, state)

        cycle_started_monotonic = time.monotonic()
        returncode, stdout, stderr, timed_out = run_agent_cycle(cmd, prompt, args.cycle_timeout_seconds, stdout_path, stderr_path, agent_cwd, agent_label)
        cycle_duration_seconds = time.monotonic() - cycle_started_monotonic
        write_text(stdout_path, stdout)
        write_text(stderr_path, stderr)
        if engine == "claude":
            # claude -p prints its final message to stdout (no codex-style -o
            # file); under --output-format json the message is the envelope's
            # `result` field, with raw stdout as the parse-failure fallback.
            result_text = agent_engine.extract_claude_result_text(stdout) if structured_output_enabled() else None
            write_text(last_message_path, result_text if result_text is not None else stdout)
        elif structured_output_enabled():
            # -o stays the primary channel; the --json event stream is only a
            # fallback when the file came back empty.
            try:
                if not last_message_path.exists() or last_message_path.stat().st_size == 0:
                    fallback_message = agent_engine.extract_codex_last_agent_message(stdout)
                    if fallback_message:
                        write_text(last_message_path, fallback_message)
            except OSError:
                pass

        try:
            harvest_source = stdout if structured_output_enabled() else ""
            cycle_usage, usage_source, session_id = agent_engine.extract_usage(engine, harvest_source)
            try:
                last_message_bytes: int | None = last_message_path.stat().st_size
            except OSError:
                last_message_bytes = None
            append_usage_record(
                repo_root,
                {
                    "schema": "rah-driver-usage/v1",
                    "at_utc": utc_now(),
                    "cycle": cycle,
                    "engine": engine,
                    "model": args.model,
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "duration_seconds": round(cycle_duration_seconds, 3),
                    "prompt_bytes": len(prompt.encode("utf-8")),
                    "stdout_bytes": len(stdout.encode("utf-8")),
                    "last_message_bytes": last_message_bytes,
                    "usage": cycle_usage,
                    "usage_source": usage_source,
                    "session_id": session_id,
                },
            )
        except Exception:
            pass  # telemetry only — never let usage accounting touch the loop

        next_loop_state = load_json(repo_root / ".rah" / "ralph" / "loop_state.json")
        signature_after = state_signature(repo_root, next_loop_state)
        idle_cycles = idle_cycles + 1 if signature_after == signature_before else 0

        append_driver_event(
            state,
            {
                "at_utc": utc_now(),
                "event": "cycle_end",
                "cycle": cycle,
                "returncode": returncode,
                "timed_out": timed_out,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "last_message_path": str(last_message_path),
                "signature_after": signature_after,
                "idle_cycles": idle_cycles,
            },
        )
        state["cycles_run"] = cycle
        state["last_returncode"] = returncode
        state["last_timed_out"] = timed_out
        state["last_stdout_path"] = str(stdout_path)
        state["last_stderr_path"] = str(stderr_path)
        update_driver_state(repo_root, state)

        prune_cycle_dirs(repo_root, args.keep_cycle_dirs, cycle)

        status_after_cycle = normalize_status(next_loop_state.get("status")) if isinstance(next_loop_state, dict) else None
        if status_after_cycle in TERMINAL_STATUSES:
            continue

        if timed_out:
            append_driver_event(
                state,
                {
                    "at_utc": utc_now(),
                    "event": "cycle_timeout_retry",
                    "cycle": cycle,
                    "signature_changed": signature_after != signature_before,
                    "signature_after": signature_after,
                    "note": "Timeout/no-response is not a terminal state; the driver will retry until RALPH itself is terminal or an explicit operator limit is reached.",
                },
            )
            state["status"] = "running_after_timeout"
            update_driver_state(repo_root, state)
            continue

        if returncode != 0:
            agent_failure_streak += 1
            state["agent_failure_streak"] = agent_failure_streak
            if args.max_agent_failure_streak and agent_failure_streak >= args.max_agent_failure_streak:
                reason = (
                    f"{agent_label} returned non-zero exit code {returncode} for "
                    f"{agent_failure_streak} consecutive cycle(s) (--max-agent-failure-streak reached)."
                )
                mark_driver_blocked(repo_root, state, reason, operator_limit_reached=True)
                update_driver_state(repo_root, state)
                print(json.dumps(state, indent=2, ensure_ascii=False))
                return 4
            backoff_seconds = agent_failure_backoff_seconds(agent_failure_streak)
            append_driver_event(
                state,
                {
                    "at_utc": utc_now(),
                    "event": "cycle_agent_failure_retry",
                    "cycle": cycle,
                    "returncode": returncode,
                    "agent_failure_streak": agent_failure_streak,
                    "backoff_seconds": backoff_seconds,
                    "note": (
                        "A non-zero agent exit (usage limit, transient API/CLI failure) is not a terminal state; "
                        "the driver backs off and retries until RALPH is terminal or an explicit operator limit is reached."
                    ),
                },
            )
            state["status"] = "running_after_agent_failure"
            update_driver_state(repo_root, state)
            time.sleep(backoff_seconds)
            continue

        if agent_failure_streak:
            agent_failure_streak = 0
            state["agent_failure_streak"] = 0

        if args.max_idle_cycles and idle_cycles >= args.max_idle_cycles:
            reason = f"Driver observed {idle_cycles} consecutive cycle(s) without RALPH progress signature changes."
            mark_driver_blocked(repo_root, state, reason, operator_limit_reached=True)
            update_driver_state(repo_root, state)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 4


if __name__ == "__main__":
    raise SystemExit(main())
