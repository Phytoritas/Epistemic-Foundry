#!/usr/bin/env python3
"""Durable external job surface for long-running RAH work.

Long computations must not run inside a single `codex exec` cycle. This helper
launches a detached supervisor process that owns the actual child command,
captures logs, writes heartbeats, and records the terminal exit status under
`.rah/jobs/<job-id>/`.
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
import hashlib
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ACTIVE_STATUSES = {"starting", "queued", "running", "cancel_requested", "cancelling"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "lost", "orphaned"}
DEFAULT_HEARTBEAT_SECONDS = 60
TERMINAL_WRITE_GRACE_SECONDS = 10
WINDOWS_PROCESS_COMMAND_TIMEOUT_SECONDS = 10
CHILD_TERMINATION_GRACE_SECONDS = 10
CHILD_KILL_WAIT_SECONDS = 5
TASKLIST_CSV_PID = re.compile(rb'^\s*(?:\xef\xbb\xbf)?"[^"\r\n]*","([0-9]+)"(?:,|$)')


class ProcessProbeError(RuntimeError):
    """The OS process liveness probe could not produce a trustworthy answer."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug[:48] or "job"


def make_job_id(name: str | None) -> str:
    return f"{safe_stamp()}-{slugify(name or 'job')}"


def jobs_root(repo_root: Path) -> Path:
    return repo_root / ".rah" / "jobs"


def job_root(repo_root: Path, job_id: str) -> Path:
    return jobs_root(repo_root) / job_id


def status_path(root: Path) -> Path:
    return root / "status.json"


def command_path(root: Path) -> Path:
    return root / "command.json"


def control_path(root: Path) -> Path:
    return root / "control.json"


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def append_event(root: Path, event: dict[str, Any]) -> None:
    event_payload = {"at_utc": utc_now(), **event}
    path = root / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event_payload, ensure_ascii=False) + "\n")


def update_status(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(status_path(root))
    if not isinstance(payload, dict):
        payload = {"schema_version": SCHEMA_VERSION}
    payload.update(updates)
    payload["updated_at_utc"] = utc_now()
    write_json(status_path(root), payload)
    return payload


def parse_env(items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--env requires KEY=VALUE, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--env requires a non-empty key, got: {item}")
        parsed[key] = value
    return parsed


def normalize_command(tokens: list[str]) -> list[str]:
    command = list(tokens)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Missing command. Use: rah.py job <repo-root> launch -- <command> [args...]")
    return command


def command_hash(command: list[str], cwd: Path) -> str:
    payload = json.dumps({"command": command, "cwd": str(cwd)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tasklist_reports_pid(stdout: bytes, pid: int) -> bool:
    """Parse tasklist CSV bytes without depending on the active Windows code page."""

    for line in stdout.splitlines():
        match = TASKLIST_CSV_PID.match(line)
        if match is not None and int(match.group(1)) == pid:
            return True
    return False


def windows_pid_exists(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=WINDOWS_PROCESS_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProcessProbeError(f"tasklist timed out while probing PID {pid}") from exc
    except OSError as exc:
        raise ProcessProbeError(f"tasklist failed while probing PID {pid}: {exc}") from exc
    except subprocess.SubprocessError as exc:
        raise ProcessProbeError(f"tasklist probe failed for PID {pid}: {exc}") from exc
    if completed.returncode != 0:
        raise ProcessProbeError(
            f"tasklist returned {completed.returncode} while probing PID {pid}"
        )
    if not isinstance(completed.stdout, (bytes, bytearray)):
        raise ProcessProbeError(f"tasklist returned non-binary stdout for PID {pid}")
    return tasklist_reports_pid(bytes(completed.stdout), pid)


def pid_exists(pid: Any) -> bool:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    if os.name == "nt":
        return windows_pid_exists(pid_int)
    try:
        os.kill(pid_int, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def terminate_process_tree(pid: Any) -> bool:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid_int), "/T", "/F"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=WINDOWS_PROCESS_COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0
    try:
        os.killpg(pid_int, signal.SIGTERM)
        return True
    except OSError:
        try:
            os.kill(pid_int, signal.SIGTERM)
            return True
        except OSError:
            return False


def wait_for_cancelled_child(
    child: subprocess.Popen[Any],
) -> tuple[int | None, bool, str | None]:
    """Bound cancellation waits and escalate only through the owned Popen handle."""

    try:
        return int(child.wait(timeout=CHILD_TERMINATION_GRACE_SECONDS)), False, None
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except OSError as exc:
            return None, True, f"exact child kill failed after tree termination timeout: {exc}"
        try:
            return int(child.wait(timeout=CHILD_KILL_WAIT_SECONDS)), True, None
        except subprocess.TimeoutExpired:
            return (
                None,
                True,
                "exact child remained alive after bounded tree termination and child kill waits",
            )


def build_completion_evidence(root: Path, status: dict[str, Any]) -> Path:
    evidence = root / "completion_evidence.md"
    lines = [
        "# RAH Long Job Completion Evidence",
        "",
        f"- job_id: `{status.get('job_id')}`",
        f"- name: {status.get('name')}",
        f"- status: `{status.get('status')}`",
        f"- exit_code: `{status.get('exit_code')}`",
        f"- started_at_utc: `{status.get('started_at_utc')}`",
        f"- finished_at_utc: `{status.get('finished_at_utc')}`",
        f"- cwd: `{status.get('cwd')}`",
        f"- stdout: `{status.get('stdout_path')}`",
        f"- stderr: `{status.get('stderr_path')}`",
        f"- result_dir: `{status.get('result_dir')}`",
        f"- checkpoint_dir: `{status.get('checkpoint_dir')}`",
        "",
        "## Command",
        "",
        "```text",
        " ".join(str(token) for token in status.get("command", [])),
        "```",
        "",
    ]
    atomic_write_text(evidence, "\n".join(lines))
    return evidence


def launch(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise SystemExit(f"Missing repo root: {repo_root}")

    command = normalize_command(args.command)
    job_id = args.job_id or make_job_id(args.name or Path(command[0]).name)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", job_id):
        raise SystemExit("job id may contain only letters, digits, dot, underscore, and dash")

    root = job_root(repo_root, job_id)
    if root.exists():
        raise SystemExit(f"Job already exists: {job_id}")

    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else repo_root
    if not cwd.exists() or not cwd.is_dir():
        raise SystemExit(f"Missing job cwd: {cwd}")

    checkpoint_dir = root / "checkpoints"
    result_dir = root / "result"
    for directory in [root, checkpoint_dir, result_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    now = utc_now()
    env_overrides = parse_env(args.env or [])
    command_payload = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "name": args.name or job_id,
        "kind": args.kind,
        "repo_root": str(repo_root),
        "cwd": str(cwd),
        "command": command,
        "command_hash": command_hash(command, cwd),
        "env": env_overrides,
        "heartbeat_seconds": max(1, int(args.heartbeat_seconds)),
        "created_at_utc": now,
    }
    write_json(command_path(root), command_payload)
    write_json(control_path(root), {"schema_version": SCHEMA_VERSION, "status": "run", "updated_at_utc": now})

    status = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "name": command_payload["name"],
        "kind": args.kind,
        "status": "queued",
        "repo_root": str(repo_root),
        "cwd": str(cwd),
        "command": command,
        "created_at_utc": now,
        "updated_at_utc": now,
        "started_at_utc": None,
        "finished_at_utc": None,
        "runner_pid": None,
        "child_pid": None,
        "exit_code": None,
        "stdout_path": relative(root / "stdout.log", repo_root),
        "stderr_path": relative(root / "stderr.log", repo_root),
        "wrapper_stdout_path": relative(root / "wrapper_stdout.log", repo_root),
        "wrapper_stderr_path": relative(root / "wrapper_stderr.log", repo_root),
        "events_path": relative(root / "events.jsonl", repo_root),
        "status_path": relative(status_path(root), repo_root),
        "control_path": relative(control_path(root), repo_root),
        "checkpoint_dir": relative(checkpoint_dir, repo_root),
        "result_dir": relative(result_dir, repo_root),
        "completion_evidence_path": relative(root / "completion_evidence.md", repo_root),
        "command_hash": command_payload["command_hash"],
    }
    write_json(status_path(root), status)
    append_event(root, {"event": "job_created", "job_id": job_id, "command_hash": command_payload["command_hash"]})

    wrapper_cmd = [sys.executable, "-B", str(Path(__file__).resolve()), "_run", str(repo_root), job_id]
    wrapper_stdout = (root / "wrapper_stdout.log").open("ab")
    wrapper_stderr = (root / "wrapper_stderr.log").open("ab")
    try:
        kwargs: dict[str, Any] = {
            "cwd": str(repo_root),
            "stdout": wrapper_stdout,
            "stderr": wrapper_stderr,
            "stdin": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(wrapper_cmd, **kwargs)
    finally:
        wrapper_stdout.close()
        wrapper_stderr.close()

    status = update_status(
        root,
        {
            "status": "starting",
            "runner_pid": process.pid,
            "launched_at_utc": utc_now(),
        },
    )
    append_event(root, {"event": "supervisor_launched", "job_id": job_id, "runner_pid": process.pid})
    return {"operation": "launch", "status": "starting", "job": status}


def run_supervisor(repo_root: Path, job_id: str) -> int:
    root = job_root(repo_root, job_id)
    command_payload = read_json(command_path(root))
    if not isinstance(command_payload, dict):
        update_status(root, {"status": "failed", "exit_code": 126, "failure_reason": "missing command.json"})
        return 126

    command = command_payload.get("command")
    if not isinstance(command, list) or not command:
        update_status(root, {"status": "failed", "exit_code": 126, "failure_reason": "invalid command"})
        return 126

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in (command_payload.get("env") or {}).items()})
    env["RAH_JOB_ID"] = job_id
    env["RAH_JOB_KIND"] = str(command_payload.get("kind") or "external")
    cwd = Path(command_payload.get("cwd") or repo_root).expanduser().resolve()
    heartbeat_seconds = max(1, int(command_payload.get("heartbeat_seconds") or DEFAULT_HEARTBEAT_SECONDS))

    started = utc_now()
    update_status(
        root,
        {
            "status": "running",
            "runner_pid": os.getpid(),
            "started_at_utc": started,
            "last_heartbeat_at_utc": started,
        },
    )
    append_event(root, {"event": "supervisor_started", "job_id": job_id, "runner_pid": os.getpid()})

    stdout_path = root / "stdout.log"
    stderr_path = root / "stderr.log"
    child: subprocess.Popen[Any] | None = None
    terminal_status = "failed"
    returncode = 126
    cancellation_tree_succeeded: bool | None = None
    cancellation_escalated = False
    cancellation_failure: str | None = None
    try:
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            kwargs: dict[str, Any] = {
                "cwd": str(cwd),
                "env": env,
                "stdout": stdout,
                "stderr": stderr,
                "stdin": subprocess.DEVNULL,
                "close_fds": True,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            child = subprocess.Popen([str(token) for token in command], **kwargs)
            update_status(root, {"status": "running", "child_pid": child.pid})
            append_event(root, {"event": "child_started", "job_id": job_id, "child_pid": child.pid})

            next_heartbeat = time.monotonic()
            cancelled = False
            while child.poll() is None:
                control = read_json(control_path(root))
                if isinstance(control, dict) and str(control.get("status") or "").lower() in {"cancel", "cancel_requested", "cancelled"}:
                    cancelled = True
                    update_status(root, {"status": "cancelling", "cancel_requested_at_utc": control.get("updated_at_utc") or utc_now()})
                    append_event(root, {"event": "child_cancel_requested", "job_id": job_id, "child_pid": child.pid})
                    cancellation_tree_succeeded = terminate_process_tree(child.pid)
                    append_event(
                        root,
                        {
                            "event": "child_tree_termination_finished",
                            "job_id": job_id,
                            "child_pid": child.pid,
                            "succeeded": cancellation_tree_succeeded,
                        },
                    )
                    break
                now_mono = time.monotonic()
                if now_mono >= next_heartbeat:
                    update_status(root, {"status": "running", "last_heartbeat_at_utc": utc_now()})
                    next_heartbeat = now_mono + heartbeat_seconds
                time.sleep(min(5, heartbeat_seconds))

            if cancelled:
                cancelled_returncode, cancellation_escalated, cancellation_failure = (
                    wait_for_cancelled_child(child)
                )
                if cancelled_returncode is None:
                    returncode = 126
                    terminal_status = "failed"
                else:
                    returncode = cancelled_returncode
                    terminal_status = "cancelled"
            else:
                returncode = int(child.wait())
                terminal_status = "succeeded" if returncode == 0 else "failed"
    except FileNotFoundError as exc:
        returncode = 127
        update_status(root, {"status": "failed", "exit_code": returncode, "failure_reason": str(exc)})
        append_event(root, {"event": "job_failed_to_start", "job_id": job_id, "exit_code": returncode, "reason": str(exc)})
        return returncode
    except Exception as exc:
        returncode = 126
        update_status(root, {"status": "failed", "exit_code": returncode, "failure_reason": str(exc)})
        append_event(root, {"event": "job_supervisor_error", "job_id": job_id, "exit_code": returncode, "reason": str(exc)})
        return returncode

    finished = utc_now()
    terminal_updates: dict[str, Any] = {
        "status": terminal_status,
        "exit_code": returncode,
        "finished_at_utc": finished,
        "last_heartbeat_at_utc": finished,
    }
    if cancellation_tree_succeeded is not None:
        terminal_updates["cancellation_tree_succeeded"] = cancellation_tree_succeeded
    if cancellation_escalated:
        terminal_updates["cancellation_escalated"] = True
    if cancellation_failure:
        terminal_updates["failure_reason"] = cancellation_failure
    status = update_status(root, terminal_updates)
    evidence_path = build_completion_evidence(root, status)
    update_status(root, {"completion_evidence_path": relative(evidence_path, repo_root)})
    append_event(root, {"event": "job_finished", "job_id": job_id, "status": terminal_status, "exit_code": returncode})
    return 0 if terminal_status == "succeeded" else returncode


def refresh_status(repo_root: Path, job_id: str) -> dict[str, Any]:
    root = job_root(repo_root, job_id)
    payload = read_json(status_path(root))
    if not isinstance(payload, dict):
        raise SystemExit(f"Missing job status: {job_id}")
    status = str(payload.get("status") or "").lower()
    if status in ACTIVE_STATUSES:
        try:
            runner_alive = pid_exists(payload.get("runner_pid"))
            child_pid = payload.get("child_pid")
            child_alive = pid_exists(child_pid)
        except ProcessProbeError as exc:
            raise RuntimeError(
                f"job {job_id} process liveness probe failed: {exc}"
            ) from exc
        updated_at = payload.get("updated_at_utc")
        try:
            updated = datetime.fromisoformat(str(updated_at))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            update_age = (datetime.now(timezone.utc) - updated).total_seconds()
        except (TypeError, ValueError):
            update_age = TERMINAL_WRITE_GRACE_SECONDS
        if child_pid and child_alive and not runner_alive:
            payload = update_status(root, {"status": "orphaned", "orphaned_at_utc": utc_now()})
        elif child_pid and not child_alive and not runner_alive and update_age >= TERMINAL_WRITE_GRACE_SECONDS:
            payload = update_status(root, {"status": "lost", "lost_at_utc": utc_now(), "failure_reason": "runner and child are no longer alive without terminal status"})
        elif not child_pid and not runner_alive and update_age >= TERMINAL_WRITE_GRACE_SECONDS:
            payload = update_status(root, {"status": "lost", "lost_at_utc": utc_now(), "failure_reason": "runner is no longer alive before child pid was recorded"})
    return payload


def iter_job_ids(repo_root: Path) -> list[str]:
    root = jobs_root(repo_root)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def summarize_jobs_for_driver(repo_root: Path) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    failures: list[str] = []
    for job_id in iter_job_ids(repo_root):
        try:
            payload = refresh_status(repo_root, job_id)
        except SystemExit as exc:
            failures.append(f"{job_id}: {exc}")
            continue
        status = str(payload.get("status") or "").lower()
        if status not in ACTIVE_STATUSES | TERMINAL_STATUSES:
            failures.append(f"{job_id}: unknown job status {status!r}")
            continue
        jobs.append(
            {
                "job_id": payload.get("job_id"),
                "name": payload.get("name"),
                "status": payload.get("status"),
                "exit_code": payload.get("exit_code"),
                "updated_at_utc": payload.get("updated_at_utc"),
                "last_heartbeat_at_utc": payload.get("last_heartbeat_at_utc"),
                "completion_evidence_path": payload.get("completion_evidence_path"),
            }
        )
    if failures:
        raise RuntimeError("invalid long job state: " + "; ".join(failures))
    active = [job for job in jobs if str(job.get("status") or "").lower() in ACTIVE_STATUSES]
    terminal = [job for job in jobs if str(job.get("status") or "").lower() in TERMINAL_STATUSES]
    return {
        "job_count": len(jobs),
        "active_count": len(active),
        "terminal_count": len(terminal),
        "active_jobs": active,
        "terminal_jobs": terminal,
        "latest_updated_at_utc": max((str(job.get("updated_at_utc") or "") for job in jobs), default=None),
    }


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    payload = refresh_status(repo_root, args.job_id)
    return {"operation": "status", "job": payload}


def list_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    jobs = [refresh_status(repo_root, job_id) for job_id in iter_job_ids(repo_root)]
    if not args.all:
        jobs = [job for job in jobs if str(job.get("status") or "").lower() in ACTIVE_STATUSES]
    return {"operation": "list", "jobs": jobs, "summary": summarize_jobs_for_driver(repo_root)}


def cancel_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    root = job_root(repo_root, args.job_id)
    payload = refresh_status(repo_root, args.job_id)
    if str(payload.get("status") or "").lower() in TERMINAL_STATUSES:
        return {"operation": "cancel", "status": "noop", "reason": "job is already terminal", "job": payload}
    now = utc_now()
    write_json(
        control_path(root),
        {
            "schema_version": SCHEMA_VERSION,
            "status": "cancel_requested",
            "reason": args.reason or "operator requested cancellation",
            "updated_at_utc": now,
        },
    )
    if args.force:
        terminate_process_tree(payload.get("child_pid") or payload.get("runner_pid"))
        append_event(root, {"event": "force_terminate_requested", "job_id": args.job_id, "reason": args.reason})
    payload = update_status(root, {"status": "cancel_requested", "cancel_requested_at_utc": now, "cancel_reason": args.reason})
    append_event(root, {"event": "cancel_requested", "job_id": args.job_id, "reason": args.reason, "force": bool(args.force)})
    return {"operation": "cancel", "job": payload}


def tail_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    root = job_root(repo_root, args.job_id)
    filename = {
        "stdout": "stdout.log",
        "stderr": "stderr.log",
        "wrapper-stdout": "wrapper_stdout.log",
        "wrapper-stderr": "wrapper_stderr.log",
        "evidence": "completion_evidence.md",
    }[args.stream]
    target = root / filename
    content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    return {"operation": "tail", "job_id": args.job_id, "path": relative(target, repo_root), "content": content[-args.chars :]}


def evidence_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    payload = refresh_status(repo_root, args.job_id)
    note = (
        f"Long job {payload.get('job_id')} finished with status={payload.get('status')} "
        f"exit_code={payload.get('exit_code')}; evidence={payload.get('completion_evidence_path')}; "
        f"stdout={payload.get('stdout_path')}; stderr={payload.get('stderr_path')}; result_dir={payload.get('result_dir')}."
    )
    return {
        "operation": "evidence",
        "job": payload,
        "evidence_note": note,
        "ralph_record_recipe": f"python <active-skill-root>/automation/rah.py ralph {repo_root} --record-evidence \"{note}\"",
    }


def print_payload(payload: dict[str, Any], json_only: bool) -> None:
    if json_only:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"# RAH Job: {payload.get('operation')}\n")
    for key, value in payload.items():
        if key == "content":
            print("\n## Content\n")
            print(value)
        elif isinstance(value, (dict, list)):
            print(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            print(f"- {key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = _SuggestingArgumentParser(description="Launch and inspect durable external jobs for long-running RAH work.")
    parser.add_argument("repo_root", help="Path to the repository root")
    sub = parser.add_subparsers(dest="operation", required=True)

    launch_parser = sub.add_parser("launch", help="Launch a detached supervised job.")
    launch_parser.add_argument("--job-id", default=None, help="Stable job id. Defaults to timestamp + name.")
    launch_parser.add_argument("--name", default=None, help="Human-readable job name.")
    launch_parser.add_argument("--kind", default="generic", help="Job kind label, such as python-compute or validation.")
    launch_parser.add_argument("--cwd", default=None, help="Working directory for the child command. Defaults to repo root.")
    launch_parser.add_argument("--env", action="append", default=[], help="Environment override KEY=VALUE. Can repeat.")
    launch_parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS, help="Supervisor heartbeat interval.")
    launch_parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    launch_parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --.")

    status_parser = sub.add_parser("status", help="Show one job status.")
    status_parser.add_argument("job_id")
    status_parser.add_argument("--json", action="store_true")

    list_parser = sub.add_parser("list", help="List jobs.")
    list_parser.add_argument("--all", action="store_true", help="Include terminal jobs.")
    list_parser.add_argument("--json", action="store_true")

    cancel_parser = sub.add_parser("cancel", help="Cancel one job.")
    cancel_parser.add_argument("job_id")
    cancel_parser.add_argument("--reason", default=None)
    cancel_parser.add_argument("--force", action="store_true", help="Also issue OS-level tree termination for the recorded PID.")
    cancel_parser.add_argument("--json", action="store_true")

    tail_parser = sub.add_parser("tail", help="Tail one job log.")
    tail_parser.add_argument("job_id")
    tail_parser.add_argument("--stream", choices=["stdout", "stderr", "wrapper-stdout", "wrapper-stderr", "evidence"], default="stdout")
    tail_parser.add_argument("--chars", type=int, default=4000)
    tail_parser.add_argument("--json", action="store_true")

    evidence_parser = sub.add_parser("evidence", help="Emit a RALPH evidence note for one job.")
    evidence_parser.add_argument("job_id")
    evidence_parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "_run":
        return run_supervisor(Path(sys.argv[2]).expanduser().resolve(), sys.argv[3])

    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.operation == "launch":
            payload = launch(args)
        elif args.operation == "status":
            payload = status_command(args)
        elif args.operation == "list":
            payload = list_command(args)
        elif args.operation == "cancel":
            payload = cancel_command(args)
        elif args.operation == "tail":
            payload = tail_command(args)
        else:
            payload = evidence_command(args)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print_payload(payload, getattr(args, "json", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
