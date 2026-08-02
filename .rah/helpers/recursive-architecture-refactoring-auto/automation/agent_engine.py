#!/usr/bin/env python3
"""Shared host-agent CLI layer for RAH drivers and fleet workers.

Single canonical implementation of engine detection, binary resolution, and
`codex exec` / `claude --print` command construction. `ralph_driver.py` (serial
RALPH cycles) and `fleet_harness.py` (parallel implementation workers) both
build their agent invocations here so flag layout never forks.

Verified against codex-cli 0.145.0 (`-c/--config key=value`, `-m`, `-s`,
`-C/--cd`, `--skip-git-repo-check`, `-o/--output-last-message`, `--json`
thread/turn/item event JSONL on stdout; a terminal `turn.completed` event
carries `usage`) and Claude Code 2.1.218 (`--print`, `--output-format`
text|json; the json envelope carries `result`, `session_id`, and `usage`).
Real-engine usage shapes captured 2026-07-24: codex `turn.completed.usage`
= {input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens,
reasoning_output_tokens}; claude `usage` = {input_tokens, cache_read_input_tokens,
cache_creation_input_tokens, output_tokens, ...}.

Structured output is OPT-IN per call site (`json_events` / `output_format`):
fleet workers keep parsing plain final-message stdout, while the RALPH driver
requests event streams to harvest per-cycle token usage. The usage extractors
below are deliberately permissive — any schema mismatch yields all-None usage
(never synthesized zeros) so telemetry can fail open without touching the loop.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

DEFAULT_WORKER_ENGINE = "codex"
DEFAULT_WORKER_MODEL = "gpt-5.6-sol"
DEFAULT_WORKER_EFFORT = "max"

# Feature flags that expose sub-agent delegation to a codex worker.
# Verified against codex-cli 0.145.0 on 2026-07-27: with both disabled a
# worker answers NO-SUBAGENT-TOOLS, while disabling only `multi_agent_v2`
# still leaves `multi_agent_v1__spawn_agent` callable. Fleet workers are
# non-authoritative hands (invariant I5), so recursive fan-out below a
# worker is never wanted: the brain owns decomposition and judgment.
SUBAGENT_FEATURE_FLAGS: tuple[str, ...] = ("multi_agent", "multi_agent_v2")


def subagent_disable_args(flags: Iterable[str] = SUBAGENT_FEATURE_FLAGS) -> list[str]:
    """`codex exec` args that remove every sub-agent tool from a worker."""
    args: list[str] = []
    for flag in flags:
        args.extend(["--disable", str(flag)])
    return args


def worker_model_defaults() -> tuple[str, str]:
    """Fleet codex-worker (model, effort): global config first, constants last.

    Reads `CODEX_HOME/config.toml` `model` / `model_reasoning_effort` so a
    global model switch propagates to fleet workers without editing this
    package (the 2026-07-10 drift class: constants silently pinned workers to
    a retired model for weeks). Any read/parse problem falls back to the
    pinned constants.
    """

    try:
        import tomllib

        home = os.environ.get("CODEX_HOME")
        root = Path(home).expanduser() if home else Path.home() / ".codex"
        # Convention: the effective default lives at top level. Profile-selected
        # models ([profiles.*]) are not resolved here — the top-level `model`
        # (or, absent one, the constants) is returned regardless of any active
        # profile; pass --model explicitly when dispatching under a profile.
        data = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
        model = data.get("model")
        effort = data.get("model_reasoning_effort")
        return (
            model.strip()
            if isinstance(model, str) and model.strip()
            else DEFAULT_WORKER_MODEL,
            effort.strip()
            if isinstance(effort, str) and effort.strip()
            else DEFAULT_WORKER_EFFORT,
        )
    except Exception as exc:
        # Visible fallback: silent reversion to the pinned constant is the
        # exact invisible-drift class this function exists to prevent.
        import sys

        sys.stderr.write(
            f"[agent_engine] config.toml worker defaults unavailable ({type(exc).__name__}); "
            f"falling back to {DEFAULT_WORKER_MODEL}/{DEFAULT_WORKER_EFFORT}\n"
        )
        return DEFAULT_WORKER_MODEL, DEFAULT_WORKER_EFFORT
DRIVER_CYCLE_ENV = "RAH_DRIVER_CYCLE"
CONTINUATION_AUTHORITY_ENV = "RAH_CONTINUATION_AUTHORITY"


def resolve_engine(explicit: str | None) -> str:
    """Decide which host agent CLI to use.

    Order: explicit --engine, then RAH_ENGINE, then runtime env markers
    (Claude Code sets CLAUDECODE/CLAUDE_CODE_ENTRYPOINT; Codex sets CODEX_*),
    then a codex fallback so a bare terminal run keeps the original behavior.
    """
    if explicit and explicit != "auto":
        return explicit
    env_engine = os.environ.get("RAH_ENGINE", "").strip().lower()
    if env_engine in {"codex", "claude"}:
        return env_engine
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if any(key.startswith("CODEX_") for key in os.environ):
        return "codex"
    return "codex"


def resolve_codex_bin(explicit: str | None) -> str:
    if explicit:
        return explicit
    candidates = []
    if os.name == "nt":
        candidates.extend(["codex.cmd", "codex.exe", "codex"])
    else:
        candidates.append("codex")
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("Could not find codex executable. Pass --codex-bin.")


def resolve_claude_bin(explicit: str | None) -> str:
    if explicit:
        return explicit
    candidates = []
    if os.name == "nt":
        candidates.extend(["claude.cmd", "claude.exe", "claude"])
    else:
        candidates.append("claude")
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("Could not find claude executable. Pass --claude-bin.")


def resolve_agent_bin(
    engine: str, codex_bin: str | None, claude_bin: str | None
) -> str:
    return (
        resolve_codex_bin(codex_bin)
        if engine == "codex"
        else resolve_claude_bin(claude_bin)
    )


def build_codex_exec_command(
    codex_bin: str,
    workdir: Path,
    last_message_path: Path,
    *,
    model: str | None = None,
    sandbox: str | None = None,
    bypass_approvals_and_sandbox: bool = False,
    config: Iterable[tuple[str, str]] = (),
    extra_args: Iterable[str] = (),
    json_events: bool = False,
) -> list[str]:
    """`codex exec` invocation; the prompt is fed via stdin (trailing `-`)."""
    cmd = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
    ]
    if json_events:
        cmd.append("--json")
    cmd.extend(
        [
            "-C",
            str(workdir),
            "-o",
            str(last_message_path),
        ]
    )
    if model:
        cmd.extend(["-m", model])
    if sandbox:
        cmd.extend(["-s", sandbox])
    if bypass_approvals_and_sandbox:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    for key, value in config:
        cmd.extend(["-c", f"{key}={value}"])
    for item in extra_args:
        cmd.append(item)
    cmd.append("-")
    return cmd


def build_claude_print_command(
    claude_bin: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    permission_mode: str | None = None,
    dangerously_skip_permissions: bool = False,
    extra_args: Iterable[str] = (),
    output_format: str = "text",
) -> list[str]:
    """Claude Code headless: prompt via stdin, repo is the process cwd (no
    codex-style -C), final message printed to stdout (no -o file)."""
    cmd = [
        claude_bin,
        "--print",
        "--output-format",
        output_format,
    ]
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])
    if permission_mode:
        cmd.extend(["--permission-mode", permission_mode])
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    for item in extra_args:
        cmd.append(item)
    return cmd


_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_creation_input_tokens",
    "output_tokens",
    "total_tokens",
)


def _coerce_usage(raw: Any) -> dict[str, int | None]:
    """Map a provider usage dict onto the ledger schema; unknown -> None.

    Never synthesizes zeros: a missing or non-integer field stays None so a
    schema drift reads as "unknown", not as "free"."""
    usage: dict[str, int | None] = {key: None for key in _USAGE_KEYS}
    if not isinstance(raw, dict):
        return usage
    aliases = {
        "cached_input_tokens": ("cached_input_tokens", "cache_read_input_tokens"),
        # codex 0.145.0 turn.completed uses cache_write_input_tokens; claude
        # uses cache_creation_input_tokens for the same "cache write" concept.
        "cache_creation_input_tokens": ("cache_creation_input_tokens", "cache_write_input_tokens"),
    }
    for key in _USAGE_KEYS:
        for candidate in aliases.get(key, (key,)):
            value = raw.get(candidate)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                usage[key] = value
                break
    return usage


def _empty_usage() -> dict[str, int | None]:
    return {key: None for key in _USAGE_KEYS}


def extract_usage(engine: str, stdout: str) -> tuple[dict[str, int | None], str | None, str | None]:
    """Harvest token usage from structured engine stdout.

    Returns (usage, usage_source, session_id). Permissive by contract: any
    parse problem yields (all-None usage, None, None) — telemetry fails open.
    Codex: JSONL events; accepts both a dict-valued "usage" on any event
    (e.g. turn.completed) and the protocol msg.type == "token_count" shape.
    Claude: a single --output-format json envelope."""
    try:
        if engine == "claude":
            envelope = json.loads(stdout.strip())
            if not isinstance(envelope, dict):
                return _empty_usage(), None, None
            session_id = envelope.get("session_id") if isinstance(envelope.get("session_id"), str) else None
            raw = envelope.get("usage")
            if isinstance(raw, dict):
                return _coerce_usage(raw), "claude-envelope", session_id
            return _empty_usage(), None, session_id

        usage: dict[str, int | None] | None = None
        source: str | None = None
        session_id = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(event, dict):
                continue
            for id_key in ("session_id", "conversation_id", "thread_id"):
                candidate = event.get(id_key)
                if isinstance(candidate, str) and candidate:
                    session_id = candidate
            if isinstance(event.get("usage"), dict):
                usage = _coerce_usage(event["usage"])
                source = f"codex-jsonl:{event.get('type') or 'usage'}"
                continue
            msg = event.get("msg")
            if isinstance(msg, dict) and msg.get("type") == "token_count":
                info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
                raw = info.get("total_token_usage") or info.get("last_token_usage")
                if isinstance(raw, dict):
                    usage = _coerce_usage(raw)
                    source = "codex-jsonl:token_count"
        if usage is not None:
            return usage, source, session_id
        return _empty_usage(), None, session_id
    except Exception:
        return _empty_usage(), None, None


def extract_claude_result_text(stdout: str) -> str | None:
    """`--output-format json` envelope -> final message text, else None."""
    try:
        envelope = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
        return envelope["result"]
    return None


def extract_codex_last_agent_message(stdout: str) -> str | None:
    """Last agent-message text in a codex --json event stream, else None."""
    last: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") in {"agent_message", "assistant_message"}:
            text = item.get("text") or item.get("message") or item.get("content")
            if isinstance(text, str) and text.strip():
                last = text
        msg = event.get("msg")
        if isinstance(msg, dict) and msg.get("type") == "agent_message":
            text = msg.get("message") or msg.get("text")
            if isinstance(text, str) and text.strip():
                last = text
    return last


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Kill the WHOLE worker tree, not only the direct child (R29).

    POSIX workers are started in their own session (see run_once), so the
    process group id equals the child pid and killpg reaches grandchildren —
    the bare process.kill() of the first design left them running (Pro
    repro). TERM first for a graceful window, then KILL; a fallback plain
    kill covers workers spawned without a fresh session."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        # survival check: /F is near-immediate, but never assume — retry once
        for _ in range(20):
            if process.poll() is not None:
                return
            time.sleep(0.1)
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        # Final verdict (reviewer finding): never report silently after the
        # retry — a still-live tree is an operator-visible failure.
        for _ in range(20):
            if process.poll() is not None:
                return
            time.sleep(0.1)
        print(
            json.dumps(
                {"action": "terminate_process_tree_incomplete", "pid": process.pid},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return
    import signal

    group_kill = False
    pgid = None
    try:
        pgid = os.getpgid(process.pid)
        # Only ever killpg a group the worker LEADS (reviewer finding: for a
        # worker spawned without start_new_session, pgid is the CALLER's
        # group and killpg would terminate the caller's own tree).
        group_kill = pgid == process.pid
    except (ProcessLookupError, PermissionError, OSError):
        pgid = None
    if group_kill and pgid is not None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        for _ in range(10):
            if process.poll() is not None:
                break
            time.sleep(0.05)
        # Unconditional KILL sweep (reviewer finding): a leader that exited
        # during the grace window used to leave surviving grandchildren.
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        return
    try:
        process.terminate()
        for _ in range(10):
            if process.poll() is not None:
                return
            time.sleep(0.05)
        process.kill()
    except OSError:
        pass


def single_shot_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return child-only markers for a Fleet or review-finder agent call."""

    environment = dict(os.environ if base is None else base)
    environment[DRIVER_CYCLE_ENV] = "1"
    environment[CONTINUATION_AUTHORITY_ENV] = "external-drive"
    return environment


def run_once(
    cmd: list[str],
    prompt: str,
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    pid_path: Path | None = None,
    stdin_path: Path | None = None,
) -> dict[str, Any]:
    """Single-shot worker invocation: prompt via stdin, bounded by timeout,
    whole process tree killed on expiry. Returns returncode/stdout/stderr/
    timed_out; the caller reads the last-message file (codex) or stdout
    (claude) for the agent's final message. When stdin_path is supplied, a
    regular UTF-8 file provides stdin so detached Windows `.cmd` wrappers and
    their child processes observe deterministic EOF instead of inheriting a
    still-open anonymous-pipe handle."""
    child_env = dict(os.environ)
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        child_env.update(env)
    child_env = single_shot_environment(child_env)
    stdin_handle = None
    try:
        if stdin_path is not None:
            stdin_handle = stdin_path.open(
                "r", encoding="utf-8", errors="replace", newline=""
            )
        process = subprocess.Popen(
            cmd,
            cwd=(str(cwd) if cwd else None),
            stdin=stdin_handle if stdin_handle is not None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
            # POSIX: own session/process group so a timeout kill reaches
            # grandchildren (R29); no-op on Windows where taskkill /T is used.
            start_new_session=(os.name != "nt"),
        )
    except OSError as exc:
        if stdin_handle is not None:
            stdin_handle.close()
        return {
            "returncode": 126,
            "stdout": "",
            "stderr": f"failed to start agent: {exc}",
            "timed_out": False,
        }

    if pid_path is not None:
        try:
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text(str(process.pid), encoding="utf-8")
        except OSError:
            pass

    timed_out = False

    def _kill_on_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        terminate_process_tree(process)

    timer: threading.Timer | None = None
    if timeout_seconds and timeout_seconds > 0:
        timer = threading.Timer(timeout_seconds, _kill_on_timeout)
        timer.daemon = True
        timer.start()
    try:
        stdout, stderr = process.communicate(
            input=None if stdin_handle is not None else prompt
        )
    finally:
        if timer is not None:
            timer.cancel()
        if stdin_handle is not None:
            stdin_handle.close()
    return {
        "returncode": int(process.returncode if process.returncode is not None else 1),
        "stdout": stdout or "",
        "stderr": stderr or "",
        "timed_out": timed_out,
    }
