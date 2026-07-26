#!/usr/bin/env python3
"""Operational controls for RAH RALPH state.

This is intentionally separate from `ralph_harness.py`: the harness records
goal progress, while ops manages operator controls such as cancel, clear,
pause, resume, and driver log inspection.
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"done", "blocked", "cancelled", "canceled", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_stamp() -> str:
    return utc_now().replace(":", "").replace("+", "Z")


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Invalid JSON at {path}. Run `rah.py doctor` and recover the state before operating on it: {exc}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def ralph_root(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph"


def loop_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "loop_state.json"


def driver_root(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "driver"


def driver_state_path(repo_root: Path) -> Path:
    return driver_root(repo_root) / "driver_state.json"


def driver_control_path(repo_root: Path) -> Path:
    return driver_root(repo_root) / "control.json"


def update_loop_status(repo_root: Path, *, status: str, reason: str | None, now: str) -> dict[str, Any]:
    loop = load_json(loop_path(repo_root))
    if not isinstance(loop, dict):
        loop = {}
    loop["status"] = status
    loop["done"] = status == "done"
    loop["updated_at_utc"] = now
    if reason:
        loop["blocked_reason"] = reason
        loop["operator_reason"] = reason
    write_json(loop_path(repo_root), loop)
    return loop


def update_goal_status(repo_root: Path, *, status: str, now: str) -> None:
    path = ralph_root(repo_root) / "goal.json"
    goal = load_json(path)
    if not isinstance(goal, dict):
        return
    goal["status"] = status
    goal["updated_at_utc"] = now
    write_json(path, goal)


def update_driver_state(repo_root: Path, *, status: str, reason: str | None, now: str) -> dict[str, Any]:
    state = load_json(driver_state_path(repo_root))
    if not isinstance(state, dict):
        state = {"schema_version": 1, "repo_root": str(repo_root)}
    state["status"] = status
    state["updated_at_utc"] = now
    if reason:
        state["blocked_reason"] = reason
        state["operator_reason"] = reason
    write_json(driver_state_path(repo_root), state)
    return state


def write_control(repo_root: Path, *, status: str, reason: str | None, now: str) -> dict[str, Any]:
    control = {
        "schema_version": 1,
        "status": status,
        "reason": reason,
        "updated_at_utc": now,
    }
    write_json(driver_control_path(repo_root), control)
    return control


def cancel(repo_root: Path, reason: str | None) -> dict[str, Any]:
    now = utc_now()
    reason = reason or "operator cancelled RALPH"
    loop = update_loop_status(repo_root, status="cancelled", reason=reason, now=now)
    update_goal_status(repo_root, status="cancelled", now=now)
    state = update_driver_state(repo_root, status="cancelled", reason=reason, now=now)
    control = write_control(repo_root, status="cancelled", reason=reason, now=now)
    report_path = ralph_root(repo_root) / "cancelled.md"
    write_text(
        report_path,
        "\n".join(
            [
                "# RALPH Cancelled",
                "",
                f"- cancelled_at_utc: `{now}`",
                f"- reason: {reason}",
                "",
            ]
        ),
    )
    return {
        "operation": "cancel",
        "status": "cancelled",
        "loop_state": loop,
        "driver_state": state,
        "driver_control": control,
        "report_path": relative(report_path, repo_root),
    }


def pause(repo_root: Path, reason: str | None) -> dict[str, Any]:
    now = utc_now()
    reason = reason or "operator paused RALPH driver"
    state = update_driver_state(repo_root, status="paused", reason=reason, now=now)
    control = write_control(repo_root, status="paused", reason=reason, now=now)
    return {"operation": "pause", "status": "paused", "driver_state": state, "driver_control": control}


def resume(repo_root: Path, reason: str | None) -> dict[str, Any]:
    now = utc_now()
    reason = reason or "operator requested RALPH driver resume"
    state = update_driver_state(repo_root, status="resume_requested", reason=reason, now=now)
    control = write_control(repo_root, status="resume_requested", reason=reason, now=now)
    return {
        "operation": "resume",
        "status": "resume_requested",
        "driver_state": state,
        "driver_control": control,
        "next_action": "Restart the external driver with `python <active-skill-root>/automation/rah.py drive <repo-root>`.",
    }


def clear(repo_root: Path, *, delete: bool) -> dict[str, Any]:
    root = ralph_root(repo_root)
    if not root.exists():
        return {"operation": "clear", "status": "noop", "reason": "No .rah/ralph state exists."}
    git_preview = git_state_preview(repo_root)
    if delete:
        assert_safe_delete_target(repo_root, root)
        shutil.rmtree(root)
        return {"operation": "clear", "status": "deleted", "target": relative(root, repo_root), "git_preview": git_preview}

    archive_root = repo_root / ".rah" / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"ralph-{safe_stamp()}"
    counter = 2
    while target.exists():
        target = archive_root / f"ralph-{safe_stamp()}-{counter}"
        counter += 1
    shutil.move(str(root), str(target))
    return {
        "operation": "clear",
        "status": "archived",
        "archive_path": relative(target, repo_root),
        "git_preview": git_preview,
        "ignore_hint": "Keep .rah/archive/ ignored unless repo policy explicitly tracks archived runtime state.",
    }


def assert_safe_delete_target(repo_root: Path, target: Path) -> None:
    resolved_repo = repo_root.resolve()
    resolved_target = target.resolve()
    expected_literal = repo_root / ".rah" / "ralph"
    if target != expected_literal:
        raise SystemExit(f"Refusing to delete unexpected RALPH target: {target}")
    try:
        resolved_target.relative_to(resolved_repo)
    except ValueError as exc:
        raise SystemExit(f"Refusing to delete RALPH target outside repo root: {resolved_target}") from exc
    if resolved_target == resolved_repo:
        raise SystemExit("Refusing to delete repo root.")


def git_state_preview(repo_root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", ".rah/ralph", ".rah/archive"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        "returncode": completed.returncode,
        "tracked_or_untracked_runtime_paths": lines[:200],
        "line_count": len(lines),
        "note": "Preview captured before clear/archive to explain dirty-worktree impact.",
    }


def driver_status(repo_root: Path) -> dict[str, Any]:
    return {
        "operation": "driver-status",
        "loop_state": load_json(loop_path(repo_root)),
        "driver_state": load_json(driver_state_path(repo_root)),
        "driver_control": load_json(driver_control_path(repo_root)),
        "review_gate": load_json(ralph_root(repo_root) / "review_gate.json"),
    }


def latest_cycle(repo_root: Path) -> Path | None:
    cycles_root = driver_root(repo_root) / "cycles"
    if not cycles_root.exists():
        return None
    cycles = sorted(path for path in cycles_root.iterdir() if path.is_dir())
    return cycles[-1] if cycles else None


def tail(repo_root: Path, stream: str) -> dict[str, Any]:
    cycle = latest_cycle(repo_root)
    if cycle is None:
        return {"operation": "tail", "status": "missing", "reason": "No driver cycle logs found."}
    filename = {
        "stdout": "stdout.log",
        "stderr": "stderr.log",
        "last": "last_message.md",
        "prompt": "prompt.md",
    }[stream]
    target = cycle / filename
    content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    return {
        "operation": "tail",
        "status": "ok",
        "cycle": cycle.name,
        "path": relative(target, repo_root),
        "content": content[-4000:],
    }


def main() -> int:
    parser = _SuggestingArgumentParser(description="Operate RAH RALPH state and driver controls.")
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument(
        "operation",
        choices=["cancel", "clear", "pause", "resume", "driver-status", "tail"],
        help="Operation to perform.",
    )
    parser.add_argument("--reason", default=None, help="Reason for cancel/pause/resume.")
    parser.add_argument("--delete", action="store_true", help="For clear: delete instead of archiving .rah/ralph.")
    parser.add_argument("--stream", choices=["stdout", "stderr", "last", "prompt"], default="last", help="For tail.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(json.dumps({"error": f"Missing repo root: {repo_root}"}, ensure_ascii=False))
        return 2

    try:
        if args.operation == "cancel":
            payload = cancel(repo_root, args.reason)
        elif args.operation == "pause":
            payload = pause(repo_root, args.reason)
        elif args.operation == "resume":
            payload = resume(repo_root, args.reason)
        elif args.operation == "clear":
            payload = clear(repo_root, delete=args.delete)
        elif args.operation == "tail":
            payload = tail(repo_root, args.stream)
        else:
            payload = driver_status(repo_root)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"# RALPH Ops: {payload.get('operation')}\n")
        for key, value in payload.items():
            if key == "content":
                print("\n## Content\n")
                print(value)
            elif isinstance(value, (dict, list)):
                print(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            else:
                print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
