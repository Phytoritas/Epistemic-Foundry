#!/usr/bin/env python3
"""Fleet: brain-hands parallel implementation workers over RAH PRD stories.

Checkpoint-return protocol (docs/rah_fleet_orchestration_v1.md): this harness
never judges. It dispatches implementation-only workers into isolated git
worktrees, machine pre-gates their output, and returns a review packet to the
CALLER — the session model or the drive-cycle host agent — which issues
verdicts. Approved patches are applied to the main tree and their coverage
rows updated here (the single .rah writer); rejected stories are re-dispatched
with the brain's rework feedback. Completion authority stays with source
coverage + RALPH gates.

Exit codes follow the RAH convention:
  0  command succeeded (dispatch/resume additionally wrote the review packet;
     failed/conflict stories are enumerated, never silently dropped)
  2  usage/precondition error (SystemExit -> {"error": ...} JSON)
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import fnmatch
import platform
import shutil
import functools
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_engine
import approval_contract
import source_coverage_harness as coverage_lib

FLEET_SCHEMA_VERSION = 2
DEFAULT_MAX_PARALLEL = max(1, min(4, (os.cpu_count() or 4) - 2))
DEFAULT_TASK_TIMEOUT_SECONDS = 3600
DEFAULT_MAX_AGENTS = 32
SCHEMA_RETRIES = 2
PREGATE_AUTO_REWORK = 2
MAX_QUESTIONS_PER_STORY = 8
MAX_QUESTION_CHARS = 4000
MAX_REPLY_CHARS = 8000
MAX_TRANSCRIPT_CONTENT_CHARS = 16000
DEFAULT_MONITOR_LIMIT = 100
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
QUESTION_ID_RE = re.compile(r"^q-[0-9a-f]{8}-[0-9a-f]{8}-r[1-9][0-9]*-[0-9a-f]{12}$")
RAH_SHORT_SEGMENT_RE = re.compile(r"^\.?rah~[0-9]+$", re.IGNORECASE)

TERMINAL_RUN_STATUSES = {"completed", "cancelled"}
# approved is rejectable too: the brain may retract an approval before resume.
REJECTABLE_STATES = {
    "needs_review", "failed", "conflict", "approved", "waiting_for_brain", "reply_ready"
}

# An implementation approval is a coverage-closing judgment, not a shorthand
# for trusting worker output. Every field below must be authored explicitly by
# the brain that inspected the patch and its validation evidence.
APPROVAL_PROOF_FIELDS = (
    ("evidence", "--evidence"),
    ("validation", "--validation"),
    ("semantic", "--semantic"),
    ("provenance", "--provenance"),
    ("negative_test", "--negative-test"),
)
# Shared with ralph review approvals (approval_contract): one approval
# vocabulary across both gates.
APPROVAL_PLACEHOLDERS = approval_contract.APPROVAL_PLACEHOLDERS

GIT_MAIN_LOCK = threading.Lock()
PACKET_LOCK = threading.Lock()
JSONL_APPEND_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Paths / shared helpers
# ---------------------------------------------------------------------------

def safe_component(value: Any, label: str) -> str:
    component = str(value or "")
    if not SAFE_COMPONENT_RE.fullmatch(component) or component in {".", ".."}:
        raise SystemExit(
            f"{label} must start with a letter or digit, contain only letters, digits, dot, "
            "underscore, or dash, and be at most 128 characters."
        )
    return component


def write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError(f"short write: wrote {offset} of {len(data)} bytes")
        offset += written


@contextmanager
def cross_process_file_lock(path: Path, *, timeout_seconds: float = 10.0):
    """Small dependency-free mutex whose ownership is released by the OS.

    It protects short append/state critical sections across Fleet CLI processes.
    The persistent one-byte sidecar is harmless; only its OS lock is meaningful.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + max(0.1, timeout_seconds)
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Timed out acquiring Fleet file lock: {path}")
                    time.sleep(0.02)
            try:
                if os.fstat(fd).st_size == 0:
                    os.lseek(fd, 0, os.SEEK_SET)
                    write_all(fd, b"0")
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                if os.fstat(fd).st_size == 0:
                    os.lseek(fd, 0, os.SEEK_SET)
                    write_all(fd, b"0")
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)

def fleet_root(repo_root: Path) -> Path:
    return repo_root / ".rah" / "fleet"


def runs_root(repo_root: Path) -> Path:
    return fleet_root(repo_root) / "runs"


def run_dir(repo_root: Path, run_id: str) -> Path:
    return runs_root(repo_root) / safe_component(run_id, "Fleet run id")


def task_dir(repo_root: Path, run_id: str, story_id: str) -> Path:
    return run_dir(repo_root, run_id) / "tasks" / safe_component(story_id, "Fleet story id")


def conversation_path(repo_root: Path, run_id: str) -> Path:
    return run_dir(repo_root, run_id) / "conversation.jsonl"


def supervisor_path(repo_root: Path, run_id: str) -> Path:
    return run_dir(repo_root, run_id) / "supervisor.json"


def mailbox_root(repo_root: Path, run_id: str) -> Path:
    return run_dir(repo_root, run_id) / "mailbox"


def question_path(repo_root: Path, run_id: str, question_id: str) -> Path:
    component = safe_component(question_id, "Fleet question id")
    return mailbox_root(repo_root, run_id) / "questions" / f"{component}.json"


def reply_path(repo_root: Path, run_id: str, question_id: str) -> Path:
    component = safe_component(question_id, "Fleet question id")
    return mailbox_root(repo_root, run_id) / "replies" / f"{component}.json"


def consumed_path(repo_root: Path, run_id: str, question_id: str) -> Path:
    component = safe_component(question_id, "Fleet question id")
    return mailbox_root(repo_root, run_id) / "consumed" / f"{component}.json"


def recovery_path(repo_root: Path, run_id: str, question_id: str) -> Path:
    component = safe_component(question_id, "Fleet question id")
    return mailbox_root(repo_root, run_id) / "recovery" / f"{component}.json"


def recovery_candidates(repo_root: Path, run_id: str, question_id: str) -> list[Path]:
    """Return every immutable recovery record that can close one question.

    Versioned records keep a previously corrupt recovery slot from becoming a
    second poisoned singleton.  The unsuffixed path remains readable for
    compatibility with early observable-Fleet runs.
    """

    component = safe_component(question_id, "Fleet question id")
    root = mailbox_root(repo_root, run_id) / "recovery"
    if not root.exists():
        return []
    return sorted({*root.glob(f"{component}--*.json"), recovery_path(repo_root, run_id, question_id)})


def worktrees_root(repo_root: Path) -> Path:
    return fleet_root(repo_root) / "worktrees"


def lock_path(repo_root: Path) -> Path:
    return fleet_root(repo_root) / "lock.json"


def lifecycle_guard_path(repo_root: Path) -> Path:
    return fleet_root(repo_root) / "lock.guard"


def mutation_lock_path(repo_root: Path, run_id: str) -> Path:
    return run_dir(repo_root, run_id) / "mutation.lock"


def utc_now() -> str:
    return coverage_lib.utc_now()


def read_json_strict(path: Path, label: str) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SystemExit(f"{label} is not parseable JSON: {path} ({exc})")


def read_json_lenient(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError, OSError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def write_text(path: Path, content: str) -> None:
    coverage_lib.write_text(path, content)


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append one UTF-8 JSON line under an OS-backed process mutex.

    Fleet worker threads and the calling brain may append concurrently. Windows
    CRT O_APPEND alone is not a cross-process atomicity guarantee, so a sidecar
    byte-range lock serializes the single-write append on every platform.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with JSONL_APPEND_LOCK:
        with cross_process_file_lock(path.with_name(path.name + ".append.lock")):
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                write_all(fd, data)
            finally:
                os.close(fd)


def journal_append(repo_root: Path, run_id: str, event: dict[str, Any]) -> None:
    path = run_dir(repo_root, run_id) / "journal.jsonl"
    append_jsonl(path, {"at": utc_now(), **event})


def message_preview(value: str, limit: int = 240) -> str:
    compact = " ".join(str(value or "").split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def conversation_append(
    repo_root: Path,
    run_id: str,
    *,
    actor: str,
    kind: str,
    story_id: str | None = None,
    content: str | None = None,
    **fields: Any,
) -> None:
    """Record explicit coordination messages, never model chain-of-thought."""
    event: dict[str, Any] = {
        "at": utc_now(),
        "run_id": run_id,
        "actor": actor,
        "kind": kind,
    }
    if story_id:
        event["story_id"] = story_id
    if content is not None:
        content = str(content)
        event["summary"] = message_preview(content)
        event["content"] = content[:MAX_TRANSCRIPT_CONTENT_CHARS]
        if len(content) > MAX_TRANSCRIPT_CONTENT_CHARS:
            event["content_truncated"] = True
    event.update(fields)
    append_jsonl(conversation_path(repo_root, run_id), event)


# ---------------------------------------------------------------------------
# Git plumbing
# ---------------------------------------------------------------------------

def run_git(cwd: Path, *args: str) -> "subprocess.CompletedProcess[str]":
    import subprocess

    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def require_git_repo(repo_root: Path) -> None:
    probe = run_git(repo_root, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise SystemExit(
            f"Fleet write templates require a git repository: {repo_root}. "
            "Non-git directories only support read-only fleet work."
        )


def git_head(repo_root: Path) -> str:
    probe = run_git(repo_root, "rev-parse", "HEAD")
    if probe.returncode != 0:
        raise SystemExit(f"Cannot resolve HEAD in {repo_root}: {probe.stderr.strip()}")
    return probe.stdout.strip()


def git_apply_with_fallback(
    repo_root: Path, patch_file: Path, *, check_only: bool
) -> "tuple[subprocess.CompletedProcess[str], str | None]":
    """Apply (or --check) a patch, retrying with --ignore-whitespace.

    CRLF/LF-mixed mainlines fail plain `git apply` on line-ending context alone
    even when the patch content is valid; the fallback keeps such stories out of
    the conflict lane. Returns (result, mode): mode is "plain",
    "ignore-whitespace", or None when both attempts fail — the returned result
    is then the plain attempt, whose error is the primary contract.
    """
    base_args = ["apply", *(["--check"] if check_only else [])]
    plain = run_git(repo_root, *base_args, str(patch_file))
    if plain.returncode == 0:
        return plain, "plain"
    fallback = run_git(repo_root, *base_args, "--ignore-whitespace", str(patch_file))
    if fallback.returncode == 0:
        return fallback, "ignore-whitespace"
    return plain, None


def parse_git_status_porcelain_z(stdout: str) -> list[dict[str, str]]:
    tokens = stdout.split("\0")
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        record = tokens[index]
        index += 1
        if not record:
            continue
        status = record[:2]
        path = record[3:] if len(record) >= 3 and record[2] == " " else record[2:]
        entry = {"status": status, "path": path}
        if ("R" in status or "C" in status) and index < len(tokens):
            entry["original_path"] = tokens[index]
            index += 1
        entries.append(entry)
    return entries


def working_tree_dirty_paths(repo_root: Path) -> list[str]:
    """Dirty paths excluding .rah/ — fleet's own runtime artifacts must not
    block its dispatch/apply preflights."""
    probe = run_git(
        repo_root,
        "-c",
        "core.quotepath=false",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if probe.returncode != 0:
        raise SystemExit(f"git status failed during fleet clean-tree check: {probe.stderr.strip()}")
    dirty: list[str] = []
    for entry in parse_git_status_porcelain_z(probe.stdout):
        paths = [entry.get("path", "")]
        if entry.get("original_path"):
            paths.append(entry["original_path"])
        normalized_paths = [normalize_repo_path(path) for path in paths]
        if normalized_paths and all(is_reserved_rah_path(path) for path in normalized_paths):
            continue
        display = f"{entry.get('status', '')} {entry.get('path', '')}"
        if entry.get("original_path"):
            display += f" <- {entry['original_path']}"
        dirty.append(display)
    return dirty


def require_clean_tree(repo_root: Path, *, action: str) -> None:
    dirty = working_tree_dirty_paths(repo_root)
    if dirty:
        raise SystemExit(
            f"Fleet {action} requires a clean working tree so main-session edits are never clobbered; "
            f"dirty paths: {', '.join(dirty[:8])}{' ...' if len(dirty) > 8 else ''}"
        )


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

def state_path(repo_root: Path, run_id: str) -> Path:
    return run_dir(repo_root, run_id) / "state.json"


def load_state(repo_root: Path, run_id: str) -> dict[str, Any]:
    payload = read_json_strict(state_path(repo_root, run_id), "fleet state.json")
    if not isinstance(payload, dict):
        raise SystemExit(f"Unknown fleet run: {run_id} (missing {state_path(repo_root, run_id)})")
    return payload


def save_state(repo_root: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = utc_now()
    write_json(state_path(repo_root, str(state.get("run_id"))), state)


def latest_run_id(repo_root: Path) -> str | None:
    root = runs_root(repo_root)
    if not root.exists():
        return None
    candidates: list[tuple[str, str]] = []
    for child in root.iterdir():
        if not child.is_dir() or not SAFE_COMPONENT_RE.fullmatch(child.name):
            continue
        state = read_json_lenient(child / "state.json")
        created = str((state or {}).get("created_at_utc") or "") if isinstance(state, dict) else ""
        if not created:
            created = f"{child.stat().st_mtime_ns:020d}"
        candidates.append((created, child.name))
    return max(candidates)[1] if candidates else None


def resolve_run_id(repo_root: Path, explicit: str | None) -> str:
    run_id = explicit or latest_run_id(repo_root)
    if not run_id:
        raise SystemExit("No fleet runs exist yet. Run `fleet <repo> dispatch` first.")
    return safe_component(run_id, "Fleet run id")


def nonterminal_run(repo_root: Path) -> str | None:
    root = runs_root(repo_root)
    if not root.exists():
        return None
    for child in sorted((c for c in root.iterdir() if c.is_dir()), reverse=True):
        if not SAFE_COMPONENT_RE.fullmatch(child.name):
            continue
        payload = read_json_lenient(child / "state.json")
        if isinstance(payload, dict) and payload.get("status") not in TERMINAL_RUN_STATUSES:
            return child.name
    return None


def load_task(repo_root: Path, run_id: str, story_id: str) -> dict[str, Any]:
    payload = read_json_lenient(task_dir(repo_root, run_id, story_id) / "task.json")
    return payload if isinstance(payload, dict) else {}


def save_task(repo_root: Path, run_id: str, task: dict[str, Any]) -> None:
    task["updated_at_utc"] = utc_now()
    write_json(task_dir(repo_root, run_id, str(task.get("story_id"))) / "task.json", task)


def approval_verdict_contract_errors(verdict: Any) -> list[str]:
    """Return strict approval-contract violations for persisted verdict data."""
    if not isinstance(verdict, dict):
        return ["decision=approve", *(flag for _, flag in APPROVAL_PROOF_FIELDS)]
    errors: list[str] = []
    if verdict.get("decision") != "approve":
        errors.append("decision=approve")
    for field, flag in APPROVAL_PROOF_FIELDS:
        value = str(verdict.get(field) or "").strip()
        if not value:
            errors.append(flag)
        else:
            normalized = " ".join(value.casefold().split())
            alnum_key = "".join(character for character in normalized if character.isalnum())
            if not alnum_key or alnum_key in APPROVAL_PLACEHOLDERS:
                errors.append(f"{flag} (placeholder)")
    return errors


def all_tasks(repo_root: Path, run_id: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    return [load_task(repo_root, run_id, story_id) for story_id in state.get("story_ids", [])]


# ---------------------------------------------------------------------------
# PRD story loading
# ---------------------------------------------------------------------------

def ralph_dir(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph"


def load_prd_stories(repo_root: Path, selected: list[str] | None) -> list[dict[str, Any]]:
    prd = read_json_strict(ralph_dir(repo_root) / "prd.json", "prd.json")
    if not isinstance(prd, dict) or not isinstance(prd.get("stories"), list):
        raise SystemExit(
            "Fleet implement needs a PRD projection (.rah/ralph/prd.json). "
            "Run `rah.py prd <repo-root> emit` (or autopilot with PRD wording) first."
        )
    stories = [story for story in prd["stories"] if isinstance(story, dict)]
    if selected:
        wanted = {item.strip() for item in selected if item.strip()}
        stories = [story for story in stories if str(story.get("id")) in wanted]
        missing = wanted - {str(story.get("id")) for story in stories}
        if missing:
            raise SystemExit(f"Unknown PRD story id(s): {', '.join(sorted(missing))}")
    if not stories:
        raise SystemExit("No PRD stories matched; nothing to dispatch.")
    return stories


def load_atoms_by_id(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = read_json_lenient(ralph_dir(repo_root) / "source_requirement_atoms.json")
    atoms = payload.get("atoms") if isinstance(payload, dict) else None
    return {
        str(atom.get("atom_id")): atom
        for atom in (atoms or [])
        if isinstance(atom, dict) and atom.get("atom_id")
    }


def coverage_rows_by_id(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = read_json_lenient(ralph_dir(repo_root) / "source_requirement_coverage.json")
    rows = coverage_lib.rows_from_payload(payload) if isinstance(payload, dict) else []
    return {
        str(row.get("requirement_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("requirement_id")
    }


def story_already_ready(story: dict[str, Any], rows_by_id: dict[str, dict[str, Any]]) -> bool:
    linked = [rows_by_id.get(str(row_id)) for row_id in (story.get("linked_source_row_ids") or [])]
    linked_rows = [row for row in linked if isinstance(row, dict)]
    return bool(linked_rows) and all(coverage_lib.row_ready(row) for row in linked_rows)


# ---------------------------------------------------------------------------
# Worker brief + result contract
# ---------------------------------------------------------------------------

RESULT_SCHEMA_TEXT = (
    '{"story_id": "<the story id you were given>", "status": "completed" | "blocked" | "needs_input", '
    '"files_changed": ["relative/path", ...], "commands_run": ["...", ...], '
    '"tests_added": ["test_name_or_path", ...], "evidence": "<concrete proof of what you built and verified>", '
    '"notes": "<optional>", "question": {"text": "<required for needs_input>", '
    '"choices": ["<optional bounded choice>", ...], "blocking_reason": "<why guessing is unsafe>"} | null}'
)


def worker_contract_text(
    story_id: str,
    ownership: list[str] | None,
    test_cmd: str | None,
    additional_contract: str | None = None,
) -> str:
    lines = [
        "## Worker contract (hands: implementation only)",
        "",
        "- You are an implementation-only worker inside YOUR OWN git worktree (the current directory).",
        "- Start by inspecting the repository (README/AGENTS.md, src/tests layout, existing conventions) and match the surrounding style.",
        "- Implement the story below and write/extend tests for its acceptance atoms.",
        f"- Run the project's targeted tests before finishing{f' (at minimum: `{test_cmd}`)' if test_cmd else ''}.",
        "- You have NO judgment authority: do not declare the story complete, do not review other work.",
        "- You have NO delegation authority: sub-agent tools are disabled for you (`--disable multi_agent --disable multi_agent_v2`). Do not spawn, message, or simulate sub-agents, and do not shell out to another agent CLI (`codex`, `claude`, `rah.py fleet`) to do your work. Implement the story yourself in this worktree.",
        "- NEVER touch `.rah/` and never invoke `rah.py ralph|source|prd|fleet` — state is orchestrator-owned.",
        "- Work only inside this worktree. Do not modify files outside it.",
        "- If one concrete brain decision is required and guessing would be unsafe, return status `needs_input` with one bounded question. The harness may answer it in a later worker round; this process is not interactive.",
    ]
    if ownership:
        lines.append(f"- File ownership (exclusive globs — stay inside): {', '.join(ownership)}")
    if additional_contract and additional_contract.strip():
        lines.extend(
            [
                "",
                "## Additional brain-authored contract",
                "",
                additional_contract.strip(),
            ]
        )
    lines.extend(
        [
            "",
            "## Output contract",
            "",
            "Your FINAL message must be ONLY one JSON object (no prose, no markdown fences):",
            "",
            RESULT_SCHEMA_TEXT,
            "",
            f'"story_id" must be exactly "{story_id}". "evidence" must cite concrete files/tests/commands.',
        ]
    )
    return "\n".join(lines)


def build_brief(
    story: dict[str, Any],
    atoms_by_id: dict[str, dict[str, Any]],
    *,
    ownership: list[str] | None,
    test_cmd: str | None,
    additional_contract: str | None = None,
) -> str:
    story_id = str(story.get("id"))
    lines = [
        f"# Fleet story brief: {story_id} — {story.get('title')}",
        "",
        str(story.get("description") or ""),
        "",
        "## Acceptance atoms (implement + verify each)",
        "",
    ]
    for atom_id in story.get("linked_source_atom_ids") or []:
        atom = atoms_by_id.get(str(atom_id))
        if not atom:
            continue
        constraints = atom.get("constraints") or {}
        extras = []
        if atom.get("polarity") == "negative":
            extras.append("NEGATIVE — needs a negative test")
        if constraints.get("numeric"):
            extras.append(f"numeric: {'; '.join(constraints['numeric'])}")
        if constraints.get("interface"):
            extras.append(f"interface: {'; '.join(constraints['interface'])}")
        suffix = f" [{' | '.join(extras)}]" if extras else ""
        lines.append(f"- {atom_id} ({atom.get('modality')}): {atom.get('requirement')}{suffix}")
    for criterion in story.get("acceptance_criteria") or []:
        if isinstance(criterion, dict):
            verification = criterion.get("verification") or {}
            lines.append(
                f"- criterion {criterion.get('id')}: {criterion.get('criterion')} "
                f"(verify: {verification.get('type')} -> {verification.get('target')})"
            )
    lines.extend(["", worker_contract_text(story_id, ownership, test_cmd, additional_contract)])
    return "\n".join(lines) + "\n"


def extract_json_object(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    starts = [index for index, char in enumerate(stripped) if char == "{"]
    for start in reversed(starts):
        depth = 0
        for index in range(start, len(stripped)):
            char = stripped[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[start:index + 1])
                    except json.JSONDecodeError:
                        break
    return None


def validate_result(payload: Any, story_id: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["reply is not a JSON object"]
    if str(payload.get("story_id") or "") != story_id:
        errors.append(f'story_id must be "{story_id}"')
    if payload.get("status") not in {"completed", "blocked", "needs_input"}:
        errors.append('status must be "completed", "blocked", or "needs_input"')
    for key in ("files_changed", "commands_run", "tests_added"):
        value = payload.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{key} must be a list of strings")
    if not str(payload.get("evidence") or "").strip():
        errors.append("evidence must be a non-empty string")
    if payload.get("status") == "needs_input":
        question = payload.get("question")
        if not isinstance(question, dict):
            errors.append("needs_input requires question object")
        else:
            text = str(question.get("text") or "").strip()
            if not text:
                errors.append("question.text must be non-empty")
            elif len(text) > MAX_QUESTION_CHARS:
                errors.append(f"question.text exceeds {MAX_QUESTION_CHARS} characters")
            choices = question.get("choices", [])
            if not isinstance(choices, list) or not all(isinstance(item, str) for item in choices):
                errors.append("question.choices must be a list of strings")
            if len(choices) > 12:
                errors.append("question.choices may contain at most 12 items")
            if any(len(item) > 500 for item in choices if isinstance(item, str)):
                errors.append("each question choice may contain at most 500 characters")
            blocking_reason = str(question.get("blocking_reason") or "").strip()
            if not blocking_reason:
                errors.append("question.blocking_reason must be non-empty")
            elif len(blocking_reason) > 2000:
                errors.append("question.blocking_reason exceeds 2000 characters")
    return errors


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(4)}.tmp"
    )
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit(f"Could not allocate immutable Fleet mailbox temp artifact: {temporary}")
    try:
        write_all(fd, data)
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    try:
        try:
            # A hard link publishes a fully written same-filesystem inode and
            # fails atomically if another immutable writer already won.
            os.link(temporary, path)
        except FileExistsError:
            raise SystemExit(f"Immutable Fleet mailbox artifact already exists: {path}")
        except OSError:
            # Filesystems without hard-link support still get atomic publish.
            # The sidecar OS lock preserves no-overwrite semantics for every
            # harness writer while os.replace prevents a partial target.
            with cross_process_file_lock(path.with_name(path.name + ".publish.lock")):
                if path.exists():
                    raise SystemExit(f"Immutable Fleet mailbox artifact already exists: {path}")
                os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def question_record_id(run_id: str, story_id: str, round_number: int, question_sha: str) -> str:
    return f"q-{short_hash(run_id)}-{short_hash(story_id)}-r{round_number}-{question_sha[:12]}"


def validate_question_record(
    payload: Any,
    *,
    expected_run_id: str | None = None,
    expected_story_id: str | None = None,
    expected_question_id: str | None = None,
    expected_round: int | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise SystemExit("Invalid immutable Fleet question: payload is not an object.")
    if payload.get("schema_version") != FLEET_SCHEMA_VERSION:
        errors.append("schema_version is not the current immutable mailbox schema")
    run_id = str(payload.get("run_id") or "")
    story_id = str(payload.get("story_id") or "")
    question_id = str(payload.get("question_id") or "")
    try:
        safe_component(run_id, "Fleet question run id")
        safe_component(story_id, "Fleet question story id")
        safe_component(question_id, "Fleet question id")
    except SystemExit as exc:
        errors.append(str(exc))
    if not QUESTION_ID_RE.fullmatch(question_id):
        errors.append("question_id does not match the generated Fleet question format")
    round_value = payload.get("round")
    if isinstance(round_value, bool) or not isinstance(round_value, int) or round_value < 1:
        errors.append("round must be a positive integer")
        round_number = 0
    else:
        round_number = round_value
    question = payload.get("question")
    if not isinstance(question, dict):
        errors.append("question must be an object")
        normalized: dict[str, Any] = {}
    else:
        text = question.get("text")
        choices = question.get("choices")
        blocking_reason = question.get("blocking_reason")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_QUESTION_CHARS:
            errors.append("question.text is invalid")
        if not isinstance(choices, list) or not all(isinstance(item, str) for item in choices):
            errors.append("question.choices is invalid")
            choices = []
        elif len(choices) > 12 or any(len(item) > 500 for item in choices):
            errors.append("question.choices exceeds the bounded count or item length")
        if not isinstance(blocking_reason, str) or not blocking_reason.strip() or len(blocking_reason) > 2000:
            errors.append("question.blocking_reason is invalid")
        normalized = {
            "text": text.strip() if isinstance(text, str) else "",
            "choices": list(choices) if isinstance(choices, list) else [],
            "blocking_reason": blocking_reason.strip() if isinstance(blocking_reason, str) else "",
        }
        if question != normalized:
            errors.append("question content is not in canonical normalized form")
    computed_sha = canonical_sha256(normalized)
    if payload.get("question_sha256") != computed_sha:
        errors.append("question_sha256 does not match the current question content")
    if round_number:
        computed_id = question_record_id(run_id, story_id, round_number, computed_sha)
        if question_id != computed_id:
            errors.append("question_id does not match run/story/round/content provenance")
    expected = {
        "run_id": expected_run_id,
        "story_id": expected_story_id,
        "question_id": expected_question_id,
        "round": expected_round,
    }
    actual = {
        "run_id": run_id,
        "story_id": story_id,
        "question_id": question_id,
        "round": round_number,
    }
    for key, value in expected.items():
        if value is not None and actual[key] != value:
            errors.append(f"{key} does not match the active task/run")
    if errors:
        raise SystemExit("Invalid immutable Fleet question: " + "; ".join(errors))
    return payload


def validate_reply_record(
    payload: Any,
    question: dict[str, Any],
    *,
    expected_run_id: str,
    expected_story_id: str,
    expected_question_id: str,
    expected_round: int,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SystemExit("Invalid immutable Fleet reply: payload is not an object.")
    errors: list[str] = []
    if payload.get("schema_version") != FLEET_SCHEMA_VERSION:
        errors.append("schema_version is not the current immutable mailbox schema")
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_REPLY_CHARS:
        errors.append("message is invalid")
        canonical_message = ""
    else:
        canonical_message = message.strip()
        if message != canonical_message:
            errors.append("message is not in canonical normalized form")
    computed_message_sha = hashlib.sha256(canonical_message.encode("utf-8")).hexdigest()
    if payload.get("message_sha256") != computed_message_sha:
        errors.append("message_sha256 does not match the current message content")
    expected_fields = {
        "run_id": expected_run_id,
        "story_id": expected_story_id,
        "question_id": expected_question_id,
        "round": expected_round,
        "question_sha256": question.get("question_sha256"),
    }
    for key, value in expected_fields.items():
        if payload.get(key) != value:
            errors.append(f"{key} does not match the active question/task provenance")
    if errors:
        raise SystemExit("Invalid immutable Fleet reply: " + "; ".join(errors))
    return payload


def mailbox_diagnostic(
    repo_root: Path,
    path: Path,
    *,
    kind: str,
    error: BaseException | str,
) -> dict[str, Any]:
    relative_path = coverage_lib.relative(path, repo_root)
    try:
        raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raw_sha = None
    reason = str(error).replace(str(path), relative_path)
    return {
        "kind": kind,
        "path": relative_path,
        "raw_sha256": raw_sha,
        "reason": reason[:500],
        "trusted": False,
    }


def validate_close_record(
    payload: Any,
    question: dict[str, Any],
    *,
    expected_path_kind: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid immutable Fleet {expected_path_kind}: payload is not an object.")
    expected = {
        "question_id": question.get("question_id"),
        "question_sha256": question.get("question_sha256"),
        "run_id": question.get("run_id"),
        "story_id": question.get("story_id"),
        "round": question.get("round"),
    }
    errors = [key for key, value in expected.items() if payload.get(key) != value]
    if payload.get("schema_version") != FLEET_SCHEMA_VERSION:
        errors.append("schema_version")
    if errors:
        raise SystemExit(
            f"Invalid immutable Fleet {expected_path_kind}: provenance mismatch in "
            + ", ".join(errors)
        )
    return payload


def write_forensic_recovery(
    repo_root: Path,
    run_id: str,
    *,
    story_id: str,
    question_id: str,
    round_number: int,
    question_sha256: str | None,
    reply_sha256: str | None,
    disposition: str,
    corrupt_artifact: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    """Close a poisoned immutable slot without modifying or trusting it.

    The recovery filename is content-addressed and versionable.  If an older
    recovery file with the same identity is itself corrupt, a numeric suffix
    provides another in-band recovery path.  New records are published through
    ``write_json_exclusive``, so their visible target is always complete JSON.
    """

    identity = {
        "question_id": question_id,
        "question_sha256": question_sha256,
        "reply_sha256": reply_sha256,
        "run_id": run_id,
        "story_id": story_id,
        "round": round_number,
        "disposition": disposition,
        "corrupt_kind": corrupt_artifact.get("kind"),
        "corrupt_path": corrupt_artifact.get("path"),
        "corrupt_raw_sha256": corrupt_artifact.get("raw_sha256"),
    }
    recovery_key = canonical_sha256(identity)[:16]
    component = safe_component(question_id, "Fleet question id")
    root = mailbox_root(repo_root, run_id) / "recovery"
    payload = {
        "schema_version": FLEET_SCHEMA_VERSION,
        **identity,
        "corrupt_artifact": corrupt_artifact,
        "recovered_at_utc": utc_now(),
    }
    expected = {
        "schema_version": FLEET_SCHEMA_VERSION,
        **identity,
    }
    for index in range(0, 100):
        if index == 0:
            target = recovery_path(repo_root, run_id, question_id)
        else:
            suffix = "" if index == 1 else f"-{index}"
            target = root / f"{component}--{recovery_key}{suffix}.json"
        if target.exists():
            try:
                existing = read_json_strict(target, "Fleet recovery record")
            except (SystemExit, OSError):
                continue
            if isinstance(existing, dict) and all(existing.get(key) == value for key, value in expected.items()):
                return existing, target
            continue
        write_json_exclusive(target, payload)
        return payload, target
    raise SystemExit(
        f"Fleet recovery namespace exhausted for question {question_id}; cancel the run and inspect mailbox diagnostics."
    )


def create_worker_question(
    repo_root: Path,
    run_id: str,
    story_id: str,
    round_number: int,
    question: dict[str, Any],
) -> dict[str, Any]:
    questions_dir = mailbox_root(repo_root, run_id) / "questions"
    existing_for_story = 0
    if questions_dir.exists():
        for path in questions_dir.glob("q-*.json"):
            payload = read_json_lenient(path)
            if isinstance(payload, dict) and payload.get("story_id") == story_id:
                existing_for_story += 1
    if existing_for_story >= MAX_QUESTIONS_PER_STORY:
        raise SystemExit(
            f"Story {story_id} exceeded the {MAX_QUESTIONS_PER_STORY}-question safety limit. "
            "The brain must narrow the story or reject it with a bounded rework plan."
        )
    normalized = {
        "text": str(question.get("text") or "").strip(),
        "choices": [str(item) for item in (question.get("choices") or [])],
        "blocking_reason": str(question.get("blocking_reason") or "").strip(),
    }
    question_sha = canonical_sha256(normalized)
    question_id = question_record_id(run_id, story_id, round_number, question_sha)
    payload = {
        "schema_version": FLEET_SCHEMA_VERSION,
        "question_id": question_id,
        "run_id": run_id,
        "story_id": story_id,
        "round": round_number,
        "question": normalized,
        "question_sha256": question_sha,
        "created_at_utc": utc_now(),
    }
    target = question_path(repo_root, run_id, question_id)
    if target.exists():
        existing = read_json_strict(target, "Fleet question")
        return validate_question_record(
            existing,
            expected_run_id=run_id,
            expected_story_id=story_id,
            expected_question_id=question_id,
            expected_round=round_number,
        )
    write_json_exclusive(target, payload)
    return payload


def load_open_questions(
    repo_root: Path,
    run_id: str,
    story_id: str | None = None,
    *,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    root = mailbox_root(repo_root, run_id) / "questions"
    if not root.exists():
        return []
    questions: list[dict[str, Any]] = []
    for path in sorted(root.glob("q-*.json")):
        try:
            payload = read_json_strict(path, "Fleet question")
            payload = validate_question_record(
                payload,
                expected_run_id=run_id,
                expected_question_id=path.stem,
            )
        except (SystemExit, OSError) as exc:
            if diagnostics is not None:
                diagnostics.append(
                    mailbox_diagnostic(
                        repo_root,
                        path,
                        kind="corrupt_question",
                        error=exc,
                    )
                )
            continue
        if story_id and payload.get("story_id") != story_id:
            continue
        question_id = str(payload.get("question_id") or "")
        if not question_id:
            continue
        closed = False
        close_candidates = [
            ("consumed", consumed_path(repo_root, run_id, question_id)),
            *[
                ("recovery", candidate)
                for candidate in recovery_candidates(repo_root, run_id, question_id)
            ],
        ]
        for kind, candidate in close_candidates:
            if not candidate.exists():
                continue
            try:
                validate_close_record(
                    read_json_strict(candidate, f"Fleet {kind}"),
                    payload,
                    expected_path_kind=kind,
                )
                closed = True
            except (SystemExit, OSError) as exc:
                if diagnostics is not None:
                    diagnostics.append(
                        mailbox_diagnostic(
                            repo_root,
                            candidate,
                            kind=f"corrupt_{kind}",
                            error=exc,
                        )
                    )
        reply_candidate = reply_path(repo_root, run_id, question_id)
        if reply_candidate.exists():
            try:
                validate_reply_record(
                    read_json_strict(reply_candidate, "Fleet reply"),
                    payload,
                    expected_run_id=run_id,
                    expected_story_id=str(payload.get("story_id")),
                    expected_question_id=question_id,
                    expected_round=int(payload.get("round") or 0),
                )
            except (SystemExit, OSError) as exc:
                if diagnostics is not None:
                    diagnostics.append(
                        mailbox_diagnostic(
                            repo_root,
                            reply_candidate,
                            kind="corrupt_reply",
                            error=exc,
                        )
                    )
            closed = True
        if closed:
            continue
        questions.append(payload)
    return questions


def validate_review_finding_result(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["reply is not a JSON object"]
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return ["findings must be a list"]
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"findings[{index}] is not an object")
            continue
        for key in ("title", "file", "severity", "evidence", "suggestion"):
            if not str(finding.get(key) or "").strip():
                errors.append(f"findings[{index}].{key} missing")
    return errors


# ---------------------------------------------------------------------------
# Worker invocation
# ---------------------------------------------------------------------------

def control_cancel_requested(repo_root: Path, run_id: str) -> bool:
    payload = read_json_lenient(run_dir(repo_root, run_id) / "control.json")
    return bool(isinstance(payload, dict) and payload.get("cancel"))


def cancellation_requested(ctx: dict[str, Any]) -> bool:
    requested = bool(
        ctx["control"].is_set()
        or control_cancel_requested(ctx["repo_root"], ctx["run_id"])
    )
    if requested:
        ctx["control"].set()
    return requested

def build_worker_command(
    params: dict[str, Any],
    workdir: Path,
    last_message_path: Path,
) -> tuple[list[str], Path | None]:
    """Returns (command, cwd). codex sets the workdir via -C (cwd stays None);
    claude has no -C, so the worktree becomes the process cwd."""
    engine = params["engine"]
    if engine == "codex":
        config: list[tuple[str, str]] = []
        if params.get("effort"):
            config.append(("model_reasoning_effort", str(params["effort"])))
        cmd = agent_engine.build_codex_exec_command(
            params["agent_bin"],
            workdir,
            last_message_path,
            model=params.get("model"),
            sandbox=params.get("sandbox"),
            bypass_approvals_and_sandbox=bool(params.get("bypass")),
            config=config,
            # Invariant I5: a worker is a non-authoritative hand. Strip every
            # sub-agent tool so a worker cannot fan out its own delegates and
            # launder unreviewed judgment back into the review packet.
            extra_args=agent_engine.subagent_disable_args(),
        )
        return cmd, None
    cmd = agent_engine.build_claude_print_command(
        params["agent_bin"],
        model=params.get("model"),
        effort=params.get("effort"),
        permission_mode=params.get("permission_mode"),
        dangerously_skip_permissions=bool(params.get("skip_permissions")),
        extra_args=params.get("claude_args") or (),
    )
    return cmd, workdir


def invoke_worker_once(
    repo_root: Path,
    run_id: str,
    story_id: str,
    params: dict[str, Any],
    workdir: Path,
    prompt: str,
    attempt: int,
) -> tuple[str, dict[str, Any]]:
    tdir = task_dir(repo_root, run_id, story_id)
    last_message_path = tdir / f"last_message_{attempt}.txt"
    prompt_path = tdir / f"prompt_{attempt}.md"
    try:
        last_message_path.unlink()
    except OSError:
        pass
    write_text(prompt_path, prompt)
    pid_path = tdir / "worker.pid"
    cmd, cwd = build_worker_command(params, workdir, last_message_path)
    try:
        outcome = agent_engine.run_once(
            cmd,
            prompt,
            timeout_seconds=int(params.get("task_timeout") or DEFAULT_TASK_TIMEOUT_SECONDS),
            cwd=cwd,
            pid_path=pid_path,
            stdin_path=prompt_path,
        )
    finally:
        try:
            pid_path.unlink()
        except OSError:
            pass
    write_text(tdir / f"stdout_{attempt}.log", outcome["stdout"])
    write_text(tdir / f"stderr_{attempt}.log", outcome["stderr"])
    fresh_last_message = bool(
        params["engine"] != "codex"
        or (outcome.get("returncode") == 0 and last_message_path.is_file())
    )
    if params["engine"] == "codex" and fresh_last_message:
        message = last_message_path.read_text(encoding="utf-8", errors="replace")
    elif params["engine"] != "codex":
        message = outcome["stdout"]
    else:
        message = ""
    outcome["fresh_last_message"] = fresh_last_message
    outcome["last_message_path"] = coverage_lib.relative(last_message_path, repo_root)
    outcome["stdout_path"] = coverage_lib.relative(tdir / f"stdout_{attempt}.log", repo_root)
    outcome["stderr_path"] = coverage_lib.relative(tdir / f"stderr_{attempt}.log", repo_root)
    outcome["prompt_path"] = coverage_lib.relative(prompt_path, repo_root)
    return message, outcome


def run_worker_with_schema_retry(
    ctx: dict[str, Any],
    story_id: str,
    workdir: Path,
    prompt: str,
    *,
    validator,
    attempt_offset: int = 0,
) -> tuple[dict[str, Any] | None, int, str | None]:
    repo_root, run_id, params = ctx["repo_root"], ctx["run_id"], ctx["params"]
    attempts = 0
    current_prompt = prompt
    last_error: str | None = None
    while attempts <= SCHEMA_RETRIES:
        if cancellation_requested(ctx):
            return None, attempts, "cancelled"
        if not ctx["budget"].spend():
            return None, attempts, "budget_exhausted: max_agents reached"
        attempts += 1
        persisted_task = load_task(repo_root, run_id, story_id)
        persisted_attempts = int(persisted_task.get("attempts") or 0)
        invocation_id = max(attempt_offset + attempts, persisted_attempts + 1)
        # Reserve the invocation before journal/prompt/process creation. A hard
        # driver crash must not reuse its artifact id or refund the agent budget.
        persisted_task["attempts"] = invocation_id
        save_task(repo_root, run_id, persisted_task)
        journal_append(
            repo_root,
            run_id,
            {"event": "worker_invoked", "story_id": story_id, "attempt": invocation_id},
        )
        conversation_append(
            repo_root,
            run_id,
            actor="harness",
            kind="worker_started",
            story_id=story_id,
            content=f"Worker attempt {invocation_id} started.",
            attempt=invocation_id,
        )
        message, outcome = invoke_worker_once(
            repo_root,
            run_id,
            story_id,
            params,
            workdir,
            current_prompt,
            invocation_id,
        )
        conversation_append(
            repo_root,
            run_id,
            actor="harness",
            kind="worker_exited",
            story_id=story_id,
            content=(
                f"Worker attempt {invocation_id} exited with returncode={outcome.get('returncode')}"
                f"{' after timeout' if outcome.get('timed_out') else ''}."
            ),
            attempt=invocation_id,
            returncode=outcome.get("returncode"),
            timed_out=bool(outcome.get("timed_out")),
            stdout_path=outcome.get("stdout_path"),
            stderr_path=outcome.get("stderr_path"),
            last_message_path=outcome.get("last_message_path"),
        )
        if cancellation_requested(ctx):
            return None, attempts, "cancelled"
        if outcome["timed_out"]:
            last_error = f"worker timed out after {params.get('task_timeout')}s"
            journal_append(
                repo_root,
                run_id,
                {"event": "worker_timeout", "story_id": story_id, "attempt": invocation_id},
            )
            continue
        if int(outcome.get("returncode") or 0) != 0:
            last_error = f"worker exited nonzero: {outcome.get('returncode')}"
            journal_append(
                repo_root,
                run_id,
                {
                    "event": "worker_nonzero",
                    "story_id": story_id,
                    "attempt": invocation_id,
                    "returncode": outcome.get("returncode"),
                },
            )
            continue
        if params["engine"] == "codex" and not outcome.get("fresh_last_message"):
            last_error = "codex worker exited without a fresh last-message artifact"
            journal_append(
                repo_root,
                run_id,
                {"event": "worker_output_missing", "story_id": story_id, "attempt": invocation_id},
            )
            continue
        payload = extract_json_object(message)
        errors = validator(payload)
        if not errors:
            return payload, attempts, None
        last_error = "result schema invalid: " + "; ".join(errors)
        journal_append(
            repo_root, run_id,
            {
                "event": "worker_schema_invalid",
                "story_id": story_id,
                "attempt": invocation_id,
                "errors": errors,
            },
        )
        current_prompt = (
            prompt
            + "\n\n## VALIDATION FAILURE\n\nYour previous reply failed validation: "
            + "; ".join(errors)
            + "\nReply again with ONLY the JSON object, matching the output contract exactly."
        )
    return None, attempts, last_error


class AgentBudget:
    """Hard ceiling on worker invocations for a run — over-budget stories are
    enumerated as failed(budget_exhausted), never silently dropped."""

    def __init__(self, limit: int, *, already_spent: int = 0) -> None:
        self._limit = max(1, int(limit))
        self._spent = max(0, int(already_spent))
        self._lock = threading.Lock()

    def spend(self) -> bool:
        with self._lock:
            if self._spent >= self._limit:
                return False
            self._spent += 1
            return True

    @property
    def spent(self) -> int:
        return self._spent


# ---------------------------------------------------------------------------
# Worktrees / patches / pre-gates
# ---------------------------------------------------------------------------

def worktree_path(repo_root: Path, run_id: str, story_id: str) -> Path:
    return worktrees_root(repo_root) / f"{short_hash(run_id)}-{story_id}"


def branch_name(run_id: str, story_id: str) -> str:
    return f"fleet/{run_id}/{story_id}"


def ensure_worktree(repo_root: Path, run_id: str, story_id: str, base_commit: str) -> Path:
    path = worktree_path(repo_root, run_id, story_id)
    if path.exists():
        return path
    with GIT_MAIN_LOCK:
        result = run_git(repo_root, "worktree", "add", "-b", branch_name(run_id, story_id), str(path), base_commit)
    if result.returncode != 0:
        raise SystemExit(f"git worktree add failed for {story_id}: {result.stderr.strip()}")
    return path


def remove_worktree(repo_root: Path, run_id: str, story_id: str) -> None:
    path = worktree_path(repo_root, run_id, story_id)
    with GIT_MAIN_LOCK:
        if path.exists():
            run_git(repo_root, "worktree", "remove", "--force", str(path))
        run_git(repo_root, "branch", "-D", branch_name(run_id, story_id))


def collect_patch(repo_root: Path, run_id: str, story_id: str, base_commit: str) -> tuple[str, list[str], str]:
    """Returns (patch_text, changed_files, diffstat) from the story worktree."""
    wt = worktree_path(repo_root, run_id, story_id)
    run_git(wt, "add", "-A")
    # NUL-delimited names are never C-quoted by Git, so non-ASCII, spaces,
    # quotes, and backslashes cannot hide an orchestrator-owned path from the
    # ownership or .rah namespace gates. --no-renames exposes both the source
    # deletion and destination addition, blocking moves into or out of .rah.
    files_probe = run_git(
        wt,
        "-c",
        "core.quotepath=false",
        "diff",
        "--cached",
        "--no-renames",
        "--name-only",
        "-z",
        base_commit,
    )
    if files_probe.returncode != 0:
        raise SystemExit(f"git diff --name-only failed for {story_id}: {files_probe.stderr.strip()}")
    changed = [path for path in files_probe.stdout.split("\0") if path]
    patch_probe = run_git(wt, "diff", "--cached", "--binary", base_commit)
    stat_probe = run_git(wt, "diff", "--cached", "--stat", base_commit)
    diffstat = stat_probe.stdout.strip().splitlines()[-1].strip() if stat_probe.stdout.strip() else ""
    return patch_probe.stdout, changed, diffstat


def ownership_violations(changed: list[str], globs: list[str] | None) -> list[str]:
    if not globs:
        return []
    return [
        path
        for path in changed
        if not any(
            fnmatch.fnmatch(normalize_repo_path(path), normalize_repo_path(pattern))
            for pattern in globs
        )
    ]


def normalize_repo_path(raw_path: str) -> str:
    normalized = str(raw_path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_reserved_rah_path(raw_path: str) -> bool:
    normalized = normalize_repo_path(raw_path)
    first_segment = normalized.split("/", 1)[0].casefold()
    return first_segment == ".rah" or bool(RAH_SHORT_SEGMENT_RE.fullmatch(first_segment))


def worker_state_violations(changed: list[str]) -> list[str]:
    return [raw_path for raw_path in changed if is_reserved_rah_path(raw_path)]


def run_pregate(
    ctx: dict[str, Any],
    story: dict[str, Any],
    task: dict[str, Any],
    patch_text: str,
    changed: list[str],
) -> tuple[dict[str, Any], bool]:
    repo_root, run_id = ctx["repo_root"], ctx["run_id"]
    story_id = str(story.get("id"))
    checks: dict[str, Any] = {"schema_valid": True}
    checks["patch_nonempty"] = bool(patch_text.strip())
    violations = ownership_violations(changed, ctx["ownership"].get(story_id))
    checks["ownership_ok"] = not violations
    if violations:
        checks["ownership_violations"] = violations
    state_violations = worker_state_violations(changed)
    checks["worker_state_ok"] = not state_violations
    if state_violations:
        checks["worker_state_violations"] = state_violations
    patch_file = task_dir(repo_root, run_id, story_id) / "patch.diff"
    write_text(patch_file, patch_text)
    if checks["patch_nonempty"]:
        with GIT_MAIN_LOCK:
            apply_probe, apply_mode = git_apply_with_fallback(repo_root, patch_file, check_only=True)
        checks["patch_applies"] = apply_mode is not None
        if apply_mode is not None:
            checks["patch_apply_mode"] = apply_mode
        else:
            checks["patch_applies_error"] = apply_probe.stderr.strip()[-400:]
    else:
        checks["patch_applies"] = False
    test_cmd = ctx["params"].get("test_cmd")
    if test_cmd:
        import shlex
        import subprocess

        wt = worktree_path(repo_root, run_id, story_id)
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        test_run = subprocess.run(
            shlex.split(test_cmd, posix=(os.name != "nt")),
            cwd=str(wt),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        checks["tests_pass"] = test_run.returncode == 0
        write_text(task_dir(repo_root, run_id, story_id) / "test_output.log", test_run.stdout + test_run.stderr)
    else:
        checks["tests_pass"] = None
    echoes: dict[str, bool] = {}
    for atom_id in story.get("linked_source_atom_ids") or []:
        atom = ctx["atoms_by_id"].get(str(atom_id))
        if not atom:
            continue
        constraints = atom.get("constraints") or {}
        needles = list(constraints.get("numeric") or []) + list(constraints.get("interface") or [])
        if not needles:
            continue
        echoes[str(atom_id)] = any(needle in patch_text for needle in needles)
    checks["atom_echoes"] = echoes
    hard_fail = (
        not checks["patch_nonempty"]
        or checks["tests_pass"] is False
        or not checks["ownership_ok"]
        or not checks["worker_state_ok"]
    )
    return checks, hard_fail


# ---------------------------------------------------------------------------
# Story processing (one dispatch round)
# ---------------------------------------------------------------------------

def refresh_packet(ctx: dict[str, Any]) -> None:
    """Rolling checkpoint: rebuild the review packet as each story lands so the
    brain can start verdicting early finishers while the rest still run."""
    repo_root, run_id = ctx["repo_root"], ctx["run_id"]
    with PACKET_LOCK:
        state = read_json_lenient(state_path(repo_root, run_id))
        if isinstance(state, dict):
            build_review_packet(repo_root, run_id, state, ctx["atoms_by_id"])
            journal_append(repo_root, run_id, {"event": "packet_updated"})


def process_story(ctx: dict[str, Any], story: dict[str, Any]) -> None:
    repo_root, run_id = ctx["repo_root"], ctx["run_id"]
    story_id = str(story.get("id"))
    task = load_task(repo_root, run_id, story_id)
    if cancellation_requested(ctx):
        task["state"] = "cancelled"
        save_task(repo_root, run_id, task)
        return
    deadline = ctx.get("deadline")
    if deadline and time.monotonic() > deadline:
        task["state"] = "failed"
        task["error"] = "run wall-clock budget exceeded before dispatch"
        save_task(repo_root, run_id, task)
        journal_append(repo_root, run_id, {"event": "story_failed", "story_id": story_id, "reason": task["error"]})
        return
    tdir = task_dir(repo_root, run_id, story_id)
    brief_path = tdir / "brief.md"
    brief = brief_path.read_text(encoding="utf-8")
    previous_question_id = str(task.get("open_question_id") or "")
    if previous_question_id:
        task["last_question_id"] = previous_question_id
    task.pop("open_question_id", None)
    task.pop("brain_reply_id", None)
    task.pop("brain_reply_at_utc", None)
    task["state"] = "dispatched"
    task["round"] = int(task.get("round") or 0) + 1
    task["brief_sha"] = short_hash(brief)
    if not task.get("base_commit"):
        task["base_commit"] = ctx["base_commit"]
    save_task(repo_root, run_id, task)
    journal_append(repo_root, run_id, {"event": "story_dispatched", "story_id": story_id, "round": task["round"]})
    conversation_append(
        repo_root,
        run_id,
        actor="brain",
        kind="brief_sent",
        story_id=story_id,
        content=f"Dispatched {story_id} round {task['round']} with its current brief and worker contract.",
        round=task["round"],
        message_path=coverage_lib.relative(brief_path, repo_root),
    )

    workdir = ensure_worktree(repo_root, run_id, story_id, str(task["base_commit"]))
    rework_left = PREGATE_AUTO_REWORK
    prompt = brief
    while True:
        result, attempts, error = run_worker_with_schema_retry(
            ctx,
            story_id,
            workdir,
            prompt,
            validator=lambda payload: validate_result(payload, story_id),
            attempt_offset=int(task.get("attempts") or 0),
        )
        task["attempts"] = max(
            int(task.get("attempts") or 0) + attempts,
            int(load_task(repo_root, run_id, story_id).get("attempts") or 0),
        )
        if result is None:
            cancelled = error == "cancelled" or cancellation_requested(ctx)
            task["state"] = "cancelled" if cancelled else "failed"
            task["error"] = None if cancelled else (error or "worker produced no valid result")
            save_task(repo_root, run_id, task)
            journal_append(
                repo_root,
                run_id,
                {
                    "event": "story_cancelled" if cancelled else "story_failed",
                    "story_id": story_id,
                    "reason": task["error"],
                },
            )
            refresh_packet(ctx)
            return
        if cancellation_requested(ctx):
            task["state"] = "cancelled"
            task["error"] = None
            save_task(repo_root, run_id, task)
            refresh_packet(ctx)
            return
        write_json(tdir / "result.json", result)
        task["result"] = result
        if str(result.get("status")) == "needs_input":
            # The worker process is single-shot. Preserve any partial work, but
            # enforce ownership/.rah boundaries before exposing its question.
            patch_text, changed, diffstat = collect_patch(
                repo_root, run_id, story_id, str(task["base_commit"])
            )
            ownership_errors = ownership_violations(
                changed, ctx["ownership"].get(story_id)
            )
            state_errors = worker_state_violations(changed)
            if ownership_errors or state_errors:
                task["state"] = "failed"
                reasons = []
                if ownership_errors:
                    reasons.append(f"ownership violation: {', '.join(ownership_errors[:5])}")
                if state_errors:
                    reasons.append(f"worker state path violation: {', '.join(state_errors[:5])}")
                task["error"] = "; ".join(reasons)
                save_task(repo_root, run_id, task)
                journal_append(
                    repo_root,
                    run_id,
                    {"event": "story_failed", "story_id": story_id, "reason": task["error"]},
                )
                refresh_packet(ctx)
                return
            partial_patch_path = tdir / f"patch_question_round{task['round']}.diff"
            write_text(partial_patch_path, patch_text)
            task["diffstat"] = diffstat
            task["files_changed"] = changed
            task["partial_patch_path"] = coverage_lib.relative(partial_patch_path, repo_root)
            question_record = create_worker_question(
                repo_root,
                run_id,
                story_id,
                int(task["round"]),
                dict(result.get("question") or {}),
            )
            task["state"] = "waiting_for_brain"
            task["open_question_id"] = question_record["question_id"]
            task["error"] = None
            save_task(repo_root, run_id, task)
            journal_append(
                repo_root,
                run_id,
                {
                    "event": "worker_question",
                    "story_id": story_id,
                    "question_id": question_record["question_id"],
                    "round": task["round"],
                },
            )
            conversation_append(
                repo_root,
                run_id,
                actor="worker",
                kind="question",
                story_id=story_id,
                content=str(question_record["question"]["text"]),
                question_id=question_record["question_id"],
                choices=question_record["question"].get("choices", []),
                blocking_reason=question_record["question"].get("blocking_reason"),
                round=task["round"],
            )
            refresh_packet(ctx)
            return
        if str(result.get("status")) == "blocked":
            # A legitimate worker outcome, not a mechanical failure: surface the
            # blocker to the brain instead of misclassifying it as an empty patch.
            task["state"] = "failed"
            task["error"] = "worker reported blocked: " + str(result.get("notes") or result.get("evidence") or "")[:300]
            save_task(repo_root, run_id, task)
            journal_append(repo_root, run_id, {"event": "story_blocked", "story_id": story_id})
            conversation_append(
                repo_root,
                run_id,
                actor="worker",
                kind="blocker",
                story_id=story_id,
                content=str(result.get("notes") or result.get("evidence") or "Worker reported blocked."),
                round=task["round"],
            )
            refresh_packet(ctx)
            return
        conversation_append(
            repo_root,
            run_id,
            actor="worker",
            kind="result",
            story_id=story_id,
            content=str(result.get("evidence") or result.get("notes") or "Worker returned a result."),
            round=task["round"],
            commands_run=result.get("commands_run", []),
            tests_added=result.get("tests_added", []),
        )
        patch_text, changed, diffstat = collect_patch(repo_root, run_id, story_id, str(task["base_commit"]))
        task["diffstat"] = diffstat
        task["files_changed"] = changed
        checks, hard_fail = run_pregate(ctx, story, task, patch_text, changed)
        write_json(tdir / "pregate.json", checks)
        task["pregate"] = checks
        if hard_fail and rework_left > 0:
            rework_left -= 1
            failure_notes = json.dumps(
                {key: value for key, value in checks.items() if key != "atom_echoes"}, ensure_ascii=False
            )
            prompt = (
                brief
                + "\n\n## MECHANICAL PRE-GATE FAILURE (auto-rework)\n\n"
                + f"Your previous attempt failed machine checks: {failure_notes}\n"
                + "Fix the failures in this same worktree and reply again with ONLY the result JSON."
            )
            journal_append(
                repo_root, run_id,
                {"event": "story_auto_rework", "story_id": story_id, "checks": failure_notes},
            )
            continue
        if hard_fail:
            task["state"] = "failed"
            task["error"] = "pre-gate hard failure after auto-rework"
            save_task(repo_root, run_id, task)
            journal_append(repo_root, run_id, {"event": "story_failed", "story_id": story_id, "reason": task["error"]})
            refresh_packet(ctx)
            return
        task["state"] = "needs_review"
        task["error"] = None
        # A successful round owns the canonical exported patch. Any partial
        # question-round patch remains immutable forensic history, but it must
        # never shadow patch.diff in the brain's review packet.
        task.pop("partial_patch_path", None)
        save_task(repo_root, run_id, task)
        journal_append(repo_root, run_id, {"event": "story_needs_review", "story_id": story_id, "round": task["round"]})
        refresh_packet(ctx)
        return


def process_review_finder(ctx: dict[str, Any], story: dict[str, Any]) -> None:
    """Review template: read-only finder workers; findings are data for the brain."""
    repo_root, run_id = ctx["repo_root"], ctx["run_id"]
    story_id = str(story.get("id"))
    task = load_task(repo_root, run_id, story_id)
    tdir = task_dir(repo_root, run_id, story_id)
    prompt = (tdir / "brief.md").read_text(encoding="utf-8")
    task["state"] = "dispatched"
    task["round"] = int(task.get("round") or 0) + 1
    save_task(repo_root, run_id, task)
    result, attempts, error = run_worker_with_schema_retry(
        ctx,
        story_id,
        repo_root,
        prompt,
        validator=validate_review_finding_result,
        attempt_offset=int(task.get("attempts") or 0),
    )
    task["attempts"] = max(
        int(task.get("attempts") or 0) + attempts,
        int(load_task(repo_root, run_id, story_id).get("attempts") or 0),
    )
    if result is None:
        task["state"] = "cancelled" if error == "cancelled" else "failed"
        task["error"] = None if error == "cancelled" else error
    else:
        write_json(tdir / "result.json", result)
        task["result"] = result
        task["state"] = "needs_review"
    save_task(repo_root, run_id, task)
    refresh_packet(ctx)


REVIEW_DIMENSIONS = [
    ("correctness", "logic errors, broken edge cases, wrong behavior vs the documented intent"),
    ("tests", "missing/weak tests, untested failure paths, assertions that cannot fail"),
    ("robustness", "error handling, encoding, portability (Windows paths), resource leaks"),
]


def build_review_brief(dimension: str, focus: str) -> str:
    return (
        f"# Fleet review finder: {dimension}\n\n"
        f"You are a READ-ONLY finder. Search this repository for {focus}.\n"
        "Do not modify any file. You have no judgment authority over completion; the calling\n"
        "session (the brain) adjudicates your findings.\n\n"
        "Your FINAL message must be ONLY one JSON object:\n"
        '{"findings": [{"title": "...", "file": "relative/path", "line": 0, '
        '"severity": "high|medium|low", "evidence": "...", "suggestion": "..."}]}\n'
        "Return at most 8 findings; an empty list is a valid answer.\n"
    )


# ---------------------------------------------------------------------------
# Review packet
# ---------------------------------------------------------------------------

def review_focus_hints(story: dict[str, Any], task: dict[str, Any], atoms_by_id: dict[str, dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    if task.get("state") == "waiting_for_brain":
        hints.append(
            "worker returned one bounded question; answer it with fleet reply, then run fleet resume. "
            "The reply is next-round input, not approval evidence"
        )
    if task.get("state") == "conflict":
        hints.append(
            "patch no longer applies to the moved main tree; worktrees are pinned to the old base — "
            "cancel this run and re-dispatch the story at the fresh base"
        )
    result = task.get("result") or {}
    tests_added = " ".join(result.get("tests_added") or [])
    for atom_id in story.get("linked_source_atom_ids") or []:
        atom = atoms_by_id.get(str(atom_id))
        if not atom:
            continue
        if atom.get("polarity") == "negative" and atom_id not in tests_added:
            hints.append(f"negative atom {atom_id} — confirm a real negative test exists")
    for atom_id, echoed in (task.get("pregate") or {}).get("atom_echoes", {}).items():
        if not echoed:
            hints.append(f"atom {atom_id} constraints not visible in the patch — verify manually")
    return hints


def build_review_packet(repo_root: Path, run_id: str, state: dict[str, Any], atoms_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stories_meta = {str(story.get("id")): story for story in state.get("stories_snapshot", [])}
    entries: list[dict[str, Any]] = []
    for story_id in state.get("story_ids", []):
        task = load_task(repo_root, run_id, story_id)
        if task.get("state") == "applied":
            continue
        story = stories_meta.get(story_id, {"id": story_id})
        task_state = str(task.get("state") or "")
        canonical_patch_path = coverage_lib.relative(
            task_dir(repo_root, run_id, story_id) / "patch.diff", repo_root
        )
        packet_patch_path = (
            task.get("partial_patch_path")
            if task_state in {"waiting_for_brain", "reply_ready"}
            else canonical_patch_path
        )
        entry = {
            "story_id": story_id,
            "state": task.get("state"),
            "round": task.get("round"),
            "patch_path": packet_patch_path or canonical_patch_path,
            "diffstat": task.get("diffstat"),
            "files_changed": task.get("files_changed", []),
            "worker_result": task.get("result"),
            "pre_gates": task.get("pregate"),
            "error": task.get("error"),
            "linked_atoms": story.get("linked_source_atom_ids", []),
            "review_focus": review_focus_hints(story, task, atoms_by_id),
            "open_question": None,
        }
        question_id = str(task.get("open_question_id") or "")
        if task.get("state") == "waiting_for_brain" and question_id:
            question_file = question_path(repo_root, run_id, question_id)
            try:
                entry["open_question"] = validate_question_record(
                    read_json_strict(question_file, "Fleet question"),
                    expected_run_id=run_id,
                    expected_story_id=story_id,
                    expected_question_id=question_id,
                    expected_round=int(task.get("round") or 0),
                )
            except (SystemExit, OSError) as exc:
                entry["mailbox_error"] = mailbox_diagnostic(
                    repo_root,
                    question_file,
                    kind="corrupt_question",
                    error=exc,
                )
                entry["review_focus"].append(
                    "question artifact is corrupt; do not trust/delete it — reject with explicit rework or cancel"
                )
        entries.append(entry)
    packet = {
        "schema_version": FLEET_SCHEMA_VERSION,
        "run_id": run_id,
        "template": state.get("template"),
        "round": max([int(load_task(repo_root, run_id, sid).get("round") or 1) for sid in state.get("story_ids", [])] or [1]),
        "created_at_utc": utc_now(),
        "stories": entries,
        "brain_contract": (
            "You are the brain. Review each patch yourself (read the diff), then record verdicts. "
            "Do not approve on the worker's word alone. Approval requires your own explicit, non-empty "
            "--evidence, --validation, --semantic, --provenance, and --negative-test; worker claims "
            "cannot populate these coverage proofs. Resume fails closed before applying any patch if an "
            "approved task lacks this strict verdict contract. A worker question is explicit next-round "
            "input only: answer it with fleet reply, then resume; it never grants approval or completion authority."
        ),
        "verdict_command": (
            f"python <automation>/rah.py fleet <repo-root> verdict {run_id} "
            "--story <id> --approve --evidence \"<brain diff finding>\" "
            "--validation \"<brain command/result>\" --semantic \"<brain semantic proof>\" "
            "--provenance \"<brain source/data-path proof>\" "
            "--negative-test \"<brain fails-if-superficial proof>\" | --reject --rework \"...\""
        ),
        "resume_command": f"python <automation>/rah.py fleet <repo-root> resume {run_id}",
        "monitor_command": f"python <automation>/rah.py fleet <repo-root> monitor {run_id} --since <cursor> --json",
        "reply_command": (
            f"python <automation>/rah.py fleet <repo-root> reply {run_id} "
            "--question <question-id> --message-file <path>"
        ),
    }
    write_json(run_dir(repo_root, run_id) / "review_packet.json", packet)
    write_text(run_dir(repo_root, run_id) / "review_packet.md", render_packet_md(packet))
    return packet


def render_packet_md(packet: dict[str, Any]) -> str:
    lines = [f"# Fleet review packet — {packet.get('run_id')} (round {packet.get('round')})", ""]
    lines.append(packet.get("brain_contract", ""))
    lines.append("")
    for entry in packet.get("stories", []):
        lines.append(f"## {entry.get('story_id')} — {entry.get('state')}")
        lines.append(f"- diffstat: {entry.get('diffstat')}")
        files = entry.get("files_changed") or []
        lines.append(f"- files: {', '.join(files[:20])}{' ...' if len(files) > 20 else ''}")
        lines.append(f"- patch: {entry.get('patch_path')}")
        if entry.get("error"):
            lines.append(f"- error: {entry['error']}")
        question = entry.get("open_question")
        if isinstance(question, dict):
            question_payload = question.get("question") or {}
            lines.append(f"- question_id: {question.get('question_id')}")
            lines.append(f"- worker question: {question_payload.get('text')}")
        for hint in entry.get("review_focus") or []:
            lines.append(f"- focus: {hint}")
        lines.append("")
    lines.append(f"verdict: {packet.get('verdict_command')}")
    lines.append(f"reply:   {packet.get('reply_command')}")
    lines.append(f"monitor: {packet.get('monitor_command')}")
    lines.append(f"resume:  {packet.get('resume_command')}")
    return "\n".join(lines) + "\n"


def write_summary(repo_root: Path, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
    tasks = all_tasks(repo_root, run_id, state)
    mailbox_diagnostics: list[dict[str, Any]] = []
    open_questions = load_open_questions(
        repo_root,
        run_id,
        diagnostics=mailbox_diagnostics,
    )
    counts: dict[str, int] = {}
    for task in tasks:
        counts[str(task.get("state"))] = counts.get(str(task.get("state")), 0) + 1
    summary = {
        "run_id": run_id,
        "template": state.get("template"),
        "status": state.get("status"),
        "counts": counts,
        "stories": [
            {
                "story_id": task.get("story_id"),
                "state": task.get("state"),
                "round": task.get("round"),
                "error": task.get("error"),
                "verdict": (task.get("verdict") or {}).get("decision"),
            }
            for task in tasks
        ],
        "agents_spawned": state.get("agents_spawned"),
        "open_questions": [
            {
                "question_id": question.get("question_id"),
                "story_id": question.get("story_id"),
                "round": question.get("round"),
                "summary": message_preview(str((question.get("question") or {}).get("text") or "")),
            }
            for question in open_questions
        ],
        "mailbox_diagnostics": mailbox_diagnostics,
        "warnings": [
            *list(state.get("warnings") or []),
            *[
                f"untrusted Fleet mailbox artifact preserved: {item.get('kind')} "
                f"{item.get('path')} sha256={item.get('raw_sha256') or 'unavailable'}"
                for item in mailbox_diagnostics
            ],
        ],
        "updated_at_utc": utc_now(),
    }
    write_json(run_dir(repo_root, run_id) / "summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------

def process_is_alive(pid: Any) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name == "nt":
        # On Windows, os.kill(pid, 0) calls TerminateProcess rather than acting
        # as the POSIX liveness probe. Query the process handle without mutation.
        ctypes, wintypes, kernel32 = _windows_process_api()
        still_active = 259
        handle = kernel32.OpenProcess(0x1000, False, value)
        if not handle:
            # Access denied proves that a process owns the PID even though this
            # caller cannot inspect it. Other failures mean it is not live.
            return ctypes.get_last_error() == 5
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return ctypes.get_last_error() == 5
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(value, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@functools.lru_cache(maxsize=1)
def _windows_process_api():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return ctypes, wintypes, kernel32


def _try_create_lock(path: Path, payload: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    try:
        write_all(fd, data)
    except Exception:
        os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    return True


def _remove_observed_stale_lock(path: Path, observed: dict[str, Any]) -> bool:
    current = read_json_lenient(path)
    identity = (observed.get("run_id"), observed.get("pid"), observed.get("owner_token"))
    if not isinstance(current, dict):
        return False
    if (current.get("run_id"), current.get("pid"), current.get("owner_token")) != identity:
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def acquire_lock(repo_root: Path, run_id: str, *, force: bool) -> str:
    run_id = safe_component(run_id, "Fleet run id")
    path = lock_path(repo_root)
    owner_token = secrets.token_hex(16)
    payload = {
        "schema_version": FLEET_SCHEMA_VERSION,
        "run_id": run_id,
        "pid": os.getpid(),
        "owner_token": owner_token,
        "heartbeat_utc": utc_now(),
    }
    with cross_process_file_lock(lifecycle_guard_path(repo_root), timeout_seconds=10.0):
        deadline = time.monotonic() + 2.0
        while True:
            if _try_create_lock(path, payload):
                return owner_token
            existing = read_json_lenient(path)
            if not isinstance(existing, dict):
                if time.monotonic() >= deadline:
                    raise SystemExit(
                        "Fleet lock exists but is not parseable; refuse to steal an unknown owner lock."
                    )
                time.sleep(0.02)
                continue
            other = str(existing.get("run_id") or "")
            owner_pid = existing.get("pid")
            if process_is_alive(owner_pid):
                relation = "this run" if other == run_id else f"run {other}"
                raise SystemExit(
                    f"Fleet lock is still owned by live pid {owner_pid} for {relation}; "
                    "wait for its checkpoint or request cancellation."
                )
            if other and other != run_id and not force:
                other_state = read_json_lenient(state_path(repo_root, other))
                if isinstance(other_state, dict) and other_state.get("status") not in TERMINAL_RUN_STATUSES:
                    raise SystemExit(
                        f"Another fleet run is non-terminal with a stale owner: {other} "
                        f"(status {other_state.get('status')}). Cancel it or pass --force-new."
                    )
            if not _remove_observed_stale_lock(path, existing):
                if time.monotonic() >= deadline:
                    raise SystemExit("Fleet lock changed while acquiring it; retry after the current mutation.")
                time.sleep(0.02)


def release_lock(repo_root: Path, run_id: str, owner_token: str) -> bool:
    with cross_process_file_lock(lifecycle_guard_path(repo_root), timeout_seconds=10.0):
        existing = read_json_lenient(lock_path(repo_root))
        if (
            isinstance(existing, dict)
            and existing.get("run_id") == run_id
            and existing.get("owner_token") == owner_token
            and str(existing.get("pid") or "") == str(os.getpid())
        ):
            try:
                lock_path(repo_root).unlink()
                return True
            except OSError:
                pass
    return False


def live_run_lock(repo_root: Path, run_id: str) -> dict[str, Any] | None:
    payload = read_json_lenient(lock_path(repo_root))
    if (
        isinstance(payload, dict)
        and payload.get("run_id") == run_id
        and process_is_alive(payload.get("pid"))
    ):
        return payload
    return None


@contextmanager
def mutation_lock(repo_root: Path, run_id: str):
    with cross_process_file_lock(mutation_lock_path(repo_root, run_id), timeout_seconds=10.0):
        yield


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def build_run_context(repo_root: Path, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
    params = dict(state.get("params") or {})
    params["engine"] = state.get("engine")
    params["model"] = state.get("model")
    params["effort"] = state.get("effort")
    params["sandbox"] = state.get("sandbox")
    params["agent_bin"] = state.get("agent_bin")
    claude_args = state.get("claude_args") or []
    if not isinstance(claude_args, list) or any(
        not isinstance(item, str) for item in claude_args
    ):
        raise SystemExit("Fleet run state claude_args must be a list of strings.")
    params["claude_args"] = list(claude_args)
    params["permission_mode"] = state.get("permission_mode")
    params["skip_permissions"] = state.get("skip_permissions")
    params["bypass"] = state.get("bypass")
    control = threading.Event()
    control_payload = read_json_lenient(run_dir(repo_root, run_id) / "control.json")
    if isinstance(control_payload, dict) and control_payload.get("cancel"):
        control.set()
    run_timeout = int(params.get("run_timeout") or 0)
    persisted_attempts = sum(
        int(load_task(repo_root, run_id, story_id).get("attempts") or 0)
        for story_id in state.get("story_ids", [])
    )
    return {
        "deadline": (time.monotonic() + run_timeout) if run_timeout > 0 else None,
        "repo_root": repo_root,
        "run_id": run_id,
        "params": params,
        "base_commit": state.get("base_commit"),
        "ownership": state.get("ownership") or {},
        "atoms_by_id": load_atoms_by_id(repo_root),
        "budget": AgentBudget(
            int(params.get("max_agents") or DEFAULT_MAX_AGENTS),
            already_spent=max(int(state.get("agents_spawned") or 0), persisted_attempts),
        ),
        "control": control,
    }


def run_pool(ctx: dict[str, Any], stories: list[dict[str, Any]], worker_fn) -> None:
    max_parallel = int(ctx["params"].get("max_parallel") or DEFAULT_MAX_PARALLEL)
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(worker_fn, ctx, story): str(story.get("id")) for story in stories}
        for future in as_completed(futures):
            story_id = futures[future]
            try:
                future.result()
            except SystemExit as exc:
                task = load_task(ctx["repo_root"], ctx["run_id"], story_id)
                cancelled = cancellation_requested(ctx) or task.get("state") == "cancelled"
                task["state"] = "cancelled" if cancelled else "failed"
                task["error"] = None if cancelled else str(exc)
                save_task(ctx["repo_root"], ctx["run_id"], task)
                conversation_append(
                    ctx["repo_root"], ctx["run_id"], actor="harness", kind="worker_error",
                    story_id=story_id, content=str(exc),
                )
            except Exception as exc:  # a worker crash must be enumerated, not raised
                task = load_task(ctx["repo_root"], ctx["run_id"], story_id)
                cancelled = cancellation_requested(ctx) or task.get("state") == "cancelled"
                task["state"] = "cancelled" if cancelled else "failed"
                task["error"] = None if cancelled else f"{type(exc).__name__}: {exc}"
                save_task(ctx["repo_root"], ctx["run_id"], task)
                conversation_append(
                    ctx["repo_root"], ctx["run_id"], actor="harness", kind="worker_error",
                    story_id=story_id, content=task["error"],
                )


def finalize_round(repo_root: Path, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
    with mutation_lock(repo_root, run_id):
        current = read_json_lenient(state_path(repo_root, run_id))
        if isinstance(current, dict):
            state = current
        tasks = all_tasks(repo_root, run_id, state)
        cancelled = control_cancel_requested(repo_root, run_id)
        if cancelled:
            for task in tasks:
                if task.get("state") != "applied":
                    task["state"] = "cancelled"
                    task["error"] = None
                    save_task(repo_root, run_id, task)
                    remove_worktree(repo_root, run_id, str(task.get("story_id")))
            tasks = all_tasks(repo_root, run_id, state)
        state["agents_spawned"] = sum(int(task.get("attempts") or 0) for task in tasks)
        open_states = {str(task.get("state")) for task in tasks} - {"applied", "cancelled"}
        if state.get("template") == "review":
            # review runs end at the packet: findings are data for the brain,
            # there is no verdict/apply stage.
            open_states -= {"needs_review", "failed"}
        if cancelled:
            state["status"] = "cancelled"
        elif not open_states:
            state["status"] = "completed"
        elif "waiting_for_brain" in open_states:
            state["status"] = "awaiting_brain"
        else:
            state["status"] = "awaiting_verdicts"
        save_state(repo_root, state)
        atoms_by_id = load_atoms_by_id(repo_root)
        packet = build_review_packet(repo_root, run_id, state, atoms_by_id)
        summary = write_summary(repo_root, run_id, state)
    return {"packet": packet, "summary": summary}


WINDOWS_SANDBOX_PROBE_STATE = "windows_sandbox_probe.json"
WINDOWS_SANDBOX_PROBE_TTL_SECONDS = 14 * 24 * 3600
WINDOWS_SANDBOX_PROBE_FAILURE_TTL_SECONDS = 6 * 3600
WINDOWS_SANDBOX_PROBE_SCHEMA = 2
CODEX_VERSION_TIMEOUT_SECONDS = 10


def _codex_version_fingerprint(codex_bin: str) -> dict[str, Any] | None:
    """Bounded `codex --version` + binary identity for the probe cache key.

    Returns None when the version cannot be established — in that state a
    cached POSITIVE result must not be reused (R27): a swapped or upgraded
    binary would otherwise inherit up to 14 days of stale capability."""

    try:
        completed = subprocess.run(
            [str(codex_bin), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CODEX_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version_text = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0 or not version_text:
        return None
    # Resolve a bare PATH name to the executable that actually ran (reviewer
    # finding: Path("codex").stat() probes the CWD, not the PATH hit, so a
    # swapped binary reporting the same version inherited the cache).
    resolved = codex_bin
    if not Path(codex_bin).is_absolute():
        which_hit = shutil.which(codex_bin)
        if which_hit:
            resolved = which_hit
    try:
        probe_stat = Path(resolved).stat()
    except OSError:
        # No binary identity means no trustworthy fingerprint: never let a
        # positive capability survive a binary we cannot pin.
        return None
    return {
        "codex_version": version_text.splitlines()[0][:120],
        "binary_path": str(resolved),
        "binary_size": probe_stat.st_size,
        "binary_mtime_ns": probe_stat.st_mtime_ns,
        "os_build": platform.version() if os.name == "nt" else sys.platform,
        "probe_schema": WINDOWS_SANDBOX_PROBE_SCHEMA,
    }


def windows_sandbox_probe(
    repo_root: Path,
    codex_bin: str,
    sandbox: str,
    *,
    force: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Bounded viability probe for the Windows codex sandbox.

    On this platform a broken sandbox does not error — worker shell calls
    spawn a `codex-windows-sandbox-setup.exe` that never returns, hanging the
    whole fleet. The probe runs one tiny `codex exec` in a temp dir under the
    requested sandbox mode and requires the worker to read a random nonce
    file through an actual shell call (so a completed-but-shell-broken run
    still fails). The process tree is killed at `timeout_seconds`. Results
    are cached in `.rah/state/windows_sandbox_probe.json` for
    `WINDOWS_SANDBOX_PROBE_TTL_SECONDS` keyed by codex binary + sandbox mode
    (one probe is one real, deliberately cheap model call).
    """

    state_dir = repo_root / ".rah" / "state"
    cache_path = state_dir / WINDOWS_SANDBOX_PROBE_STATE
    key = {"codex_bin": str(codex_bin), "sandbox": str(sandbox)}
    fingerprint = _codex_version_fingerprint(codex_bin)
    now_epoch = time.time()
    # R27: cache is valid only for the same binary/version/OS/probe-schema
    # fingerprint, only within 0<=age<=TTL (a future timestamp is invalid,
    # not eternally fresh), and failures expire on a much shorter TTL so a
    # repaired sandbox is retried within hours, not two weeks. With no
    # verifiable fingerprint a positive cache is never trusted.
    if not force and fingerprint is not None:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            age = now_epoch - float(cached.get("probed_at_epoch"))
            ttl = (
                WINDOWS_SANDBOX_PROBE_TTL_SECONDS
                if cached.get("ok")
                else WINDOWS_SANDBOX_PROBE_FAILURE_TTL_SECONDS
            )
            if (
                isinstance(cached, dict)
                and cached.get("codex_bin") == key["codex_bin"]
                and cached.get("sandbox") == key["sandbox"]
                and cached.get("fingerprint") == fingerprint
                and 0 <= age <= ttl
            ):
                return dict(cached, cached=True)
        except (OSError, ValueError, TypeError):
            pass

    import tempfile

    nonce = secrets.token_hex(8)
    with tempfile.TemporaryDirectory(prefix="rah-sandbox-probe-", ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "probe_nonce.txt").write_text(nonce, encoding="utf-8")
        last_message = tmp_path / "last_message.txt"
        cmd = agent_engine.build_codex_exec_command(
            codex_bin,
            tmp_path,
            last_message,
            sandbox=sandbox,
            config=[("model_reasoning_effort", "low")],
            # Keep the probe shaped like a real worker: same no-subagent
            # surface, so viability is measured on the dispatch config.
            extra_args=agent_engine.subagent_disable_args(),
        )
        prompt = (
            "Sandbox probe. Run the shell command `cat probe_nonce.txt` in the current "
            "working directory and reply with exactly the file content, nothing else. "
            "If the shell call fails, reply with exactly SHELL-FAILED."
        )
        result = agent_engine.run_once(cmd, prompt, timeout_seconds=timeout_seconds, cwd=tmp_path)
        answer = ""
        try:
            answer = last_message.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    ok = (not result["timed_out"]) and int(result["returncode"]) == 0 and nonce in answer
    payload: dict[str, Any] = {
        **key,
        "fingerprint": fingerprint,
        "ok": ok,
        "timed_out": bool(result["timed_out"]),
        "returncode": int(result["returncode"]),
        "nonce_echoed": nonce in answer,
        "probed_at_epoch": now_epoch,
        "probed_at_utc": utc_now(),
        "cached": False,
    }
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        write_json(cache_path, payload)
    except OSError:
        pass
    return payload


def dispatch_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists():
        raise SystemExit(f"Missing repo root: {repo_root}")
    template = args.template
    if template == "implement":
        require_git_repo(repo_root)
        require_clean_tree(repo_root, action="dispatch")
    active = nonterminal_run(repo_root)
    if active and not args.force_new:
        raise SystemExit(
            f"Fleet run {active} is still awaiting verdicts. Resume/cancel it first, or pass --force-new."
        )
    engine = agent_engine.resolve_engine(args.engine)
    if args.claude_arg and engine != "claude":
        raise SystemExit("--claude-arg requires --engine claude.")
    agent_bin = agent_engine.resolve_agent_bin(engine, args.codex_bin, args.claude_bin)
    base_commit = git_head(repo_root) if template == "implement" else None
    seed = json.dumps([template, args.stories, base_commit], ensure_ascii=False)
    if args.run_id:
        run_id = safe_component(args.run_id, "Fleet run id")
        if run_dir(repo_root, run_id).exists():
            raise SystemExit(f"Fleet run already exists: {run_id}")
    else:
        base_run_id = f"run-{utc_now().replace(':', '').replace('-', '')[:15]}-{short_hash(seed)[:4]}"
        run_id = base_run_id
        suffix = 2
        while run_dir(repo_root, run_id).exists():
            run_id = f"{base_run_id}-{suffix}"
            suffix += 1

    if template == "implement":
        stories = load_prd_stories(repo_root, args.stories.split(",") if args.stories else None)
        rows_by_id = coverage_rows_by_id(repo_root)
        skipped = [str(s.get("id")) for s in stories if story_already_ready(s, rows_by_id)]
        stories = [s for s in stories if str(s.get("id")) not in set(skipped)]
        if not stories:
            # Benign no-op, not an error: an autopilot re-run over finished
            # stories must fall through to drive instead of aborting.
            return {
                "operation": "dispatch",
                "run_id": None,
                "template": template,
                "dispatched": 0,
                "skipped_ready_story_ids": skipped,
                "note": "all selected stories already have ready coverage rows; nothing to dispatch",
            }
    else:
        stories = [
            {"id": f"finder-{key}", "title": f"review finder: {key}", "dimension": key, "focus": focus}
            for key, focus in REVIEW_DIMENSIONS
        ]
        skipped = []
    for story in stories:
        safe_component(story.get("id"), "Fleet story id")

    ownership: dict[str, list[str]] = {}
    if args.ownership_file:
        payload = read_json_strict(Path(args.ownership_file).expanduser().resolve(), "ownership file")
        if not isinstance(payload, dict):
            raise SystemExit("ownership file must map story ids to glob lists")
        ownership = {str(key): [str(g) for g in value] for key, value in payload.items() if isinstance(value, list)}
        claimed: dict[str, str] = {}
        for story_id, globs in ownership.items():
            for pattern in globs:
                if pattern in claimed and claimed[pattern] != story_id:
                    raise SystemExit(f"ownership overlap: glob {pattern!r} claimed by {claimed[pattern]} and {story_id}")
                claimed[pattern] = story_id

    default_sandbox = args.sandbox or ("workspace-write" if template == "implement" else "read-only")
    if (
        engine == "codex"
        and os.name == "nt"
        and default_sandbox
        and not args.dangerously_bypass_approvals_and_sandbox
    ):
        probe = windows_sandbox_probe(
            repo_root,
            agent_bin,
            default_sandbox,
            force=bool(getattr(args, "reprobe_sandbox", False)),
            timeout_seconds=int(getattr(args, "sandbox_probe_timeout_seconds", 120)),
        )
        if not probe.get("ok"):
            failure = "timeout" if probe.get("timed_out") else (
                f"rc={probe.get('returncode')}" if probe.get("returncode") else "shell call did not run"
            )
            raise SystemExit(
                f"Windows codex sandbox probe failed for mode {default_sandbox!r} ({failure}; "
                f"cached={probe.get('cached', False)}, probed_at={probe.get('probed_at_utc')}). "
                "Workers would hang on codex-windows-sandbox-setup.exe, so nothing was dispatched. "
                "Options: fix codex sandbox support and rerun with --reprobe-sandbox; or use "
                "--sandbox read-only when workers only read; or pass "
                "--dangerously-bypass-approvals-and-sandbox for a trusted repo."
            )

    # Lock only after every precondition has passed so a rejected dispatch
    # never leaves a stale lock behind.
    owner_token = acquire_lock(repo_root, run_id, force=args.force_new)
    try:
        # Close the preflight→lock TOCTOU: another dispatch may have completed
        # its worker phase and released the lifecycle lock after our first
        # nonterminal/run-dir checks but before this process acquired it.
        if run_dir(repo_root, run_id).exists():
            raise SystemExit(f"Fleet run already exists: {run_id}")
        active_after_lock = nonterminal_run(repo_root)
        if active_after_lock and not args.force_new:
            raise SystemExit(
                f"Fleet run {active_after_lock} became non-terminal while dispatch was acquiring "
                "the lifecycle lock; finish or cancel it before starting another run."
            )
    except BaseException:
        release_lock(repo_root, run_id, owner_token)
        raise
    if engine == "codex":
        default_worker_model, default_worker_effort = agent_engine.worker_model_defaults()
    else:
        default_worker_model = default_worker_effort = None
    state = {
        "schema_version": FLEET_SCHEMA_VERSION,
        "run_id": run_id,
        "template": template,
        "status": "dispatching",
        "engine": engine,
        "agent_bin": agent_bin,
        "model": args.model or default_worker_model if engine == "codex" else args.model,
        "effort": (
            args.effort if args.effort is not None else default_worker_effort
        )
        if engine == "codex"
        else args.effort,
        "sandbox": default_sandbox if engine == "codex" else None,
        "claude_args": list(args.claude_arg) if engine == "claude" else [],
        "permission_mode": args.permission_mode,
        "skip_permissions": args.dangerously_skip_permissions,
        "bypass": args.dangerously_bypass_approvals_and_sandbox,
        "base_commit": base_commit,
        "story_ids": [str(story.get("id")) for story in stories],
        "stories_snapshot": stories,
        "skipped_ready_story_ids": skipped,
        "ownership": ownership,
        "params": {
            "max_parallel": args.max_parallel,
            "task_timeout": args.task_timeout_seconds,
            "max_agents": args.max_agents,
            "run_timeout": args.run_timeout_seconds,
            "test_cmd": args.test_cmd,
            "worker_contract": args.worker_contract,
        },
        "created_at_utc": utc_now(),
    }
    save_state(repo_root, state)
    supervisor_job_id = str(os.environ.get("RAH_JOB_ID") or "").strip()
    if supervisor_job_id and os.environ.get("RAH_JOB_KIND") == "fleet-dispatch":
        write_json(
            supervisor_path(repo_root, run_id),
            {
                "schema_version": 1,
                "job_id": supervisor_job_id,
                "fleet_run_id": run_id,
                "kind": "fleet-dispatch",
                "linked_at_utc": utc_now(),
                "linked_by": "fleet-dispatch",
            },
        )
    journal_append(repo_root, run_id, {"event": "run_created", "template": template, "stories": state["story_ids"]})
    conversation_append(
        repo_root,
        run_id,
        actor="harness",
        kind="run_created",
        content=f"Fleet {template} run created for {len(state['story_ids'])} story task(s).",
        stories=state["story_ids"],
    )

    atoms_by_id = load_atoms_by_id(repo_root)
    for story in stories:
        story_id = str(story.get("id"))
        tdir = task_dir(repo_root, run_id, story_id)
        if template == "implement":
            override = Path(args.brief_dir) / f"{story_id}.md" if args.brief_dir else None
            if override and override.exists():
                brief = override.read_text(encoding="utf-8")
                brief += "\n\n" + worker_contract_text(
                    story_id,
                    ownership.get(story_id),
                    args.test_cmd,
                    args.worker_contract,
                )
            else:
                brief = build_brief(
                    story,
                    atoms_by_id,
                    ownership=ownership.get(story_id),
                    test_cmd=args.test_cmd,
                    additional_contract=args.worker_contract,
                )
        else:
            brief = build_review_brief(str(story.get("dimension")), str(story.get("focus")))
        write_text(tdir / "brief.md", brief)
        save_task(repo_root, run_id, {"story_id": story_id, "state": "pending", "round": 0, "attempts": 0})

    ctx = build_run_context(repo_root, run_id, state)
    try:
        run_pool(ctx, stories, process_story if template == "implement" else process_review_finder)
        outcome = finalize_round(repo_root, run_id, load_state(repo_root, run_id))
    finally:
        release_lock(repo_root, run_id, owner_token)
    return {
        "operation": "dispatch",
        "run_id": run_id,
        "template": template,
        "skipped_ready_story_ids": skipped,
        "summary": outcome["summary"],
        "review_packet_path": coverage_lib.relative(run_dir(repo_root, run_id) / "review_packet.md", repo_root),
        "packet": outcome["packet"],
    }


def packet_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = resolve_run_id(repo_root, args.run_id)
    if getattr(args, "refresh", False):
        with PACKET_LOCK:
            state = load_state(repo_root, run_id)
            packet = build_review_packet(
                repo_root, run_id, state, load_atoms_by_id(repo_root)
            )
        journal_append(repo_root, run_id, {"event": "packet_refreshed_by_operator"})
    else:
        packet = read_json_strict(
            run_dir(repo_root, run_id) / "review_packet.json", "review packet"
        )
    if not isinstance(packet, dict):
        raise SystemExit(f"No review packet for run {run_id}; dispatch first.")
    return {"operation": "packet", "run_id": run_id, "packet": packet}


def reply_message_from_args(args: argparse.Namespace) -> str:
    selected = int(bool(args.message)) + int(bool(args.message_file)) + int(bool(args.stdin))
    if selected != 1:
        raise SystemExit("Pass exactly one of --message, --message-file, or --stdin.")
    if args.message_file:
        path = Path(args.message_file).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise SystemExit(f"Reply message file does not exist: {path}")
        message = path.read_text(encoding="utf-8", errors="replace")
    elif args.stdin:
        message = sys.stdin.read()
    else:
        message = str(args.message or "")
    message = message.strip()
    if not message:
        raise SystemExit("Brain reply must be non-empty.")
    if len(message) > MAX_REPLY_CHARS:
        raise SystemExit(f"Brain reply exceeds {MAX_REPLY_CHARS} characters; use a smaller bounded answer.")
    return message


def resolve_question_record(
    repo_root: Path,
    run_id: str,
    *,
    question_id: str | None,
    story_id: str | None,
) -> dict[str, Any]:
    if question_id:
        safe_component(question_id, "Fleet question id")
        payload = read_json_strict(question_path(repo_root, run_id, question_id), "Fleet question")
        if payload is None:
            raise SystemExit(f"Unknown Fleet question: {question_id}")
        payload = validate_question_record(
            payload,
            expected_run_id=run_id,
            expected_story_id=story_id,
            expected_question_id=question_id,
        )
        if story_id and payload.get("story_id") != story_id:
            raise SystemExit(
                f"Question {question_id} belongs to {payload.get('story_id')}, not {story_id}."
            )
        return payload
    questions = load_open_questions(repo_root, run_id, story_id=story_id)
    if not questions:
        scope = f" for story {story_id}" if story_id else ""
        raise SystemExit(f"No open Fleet question exists{scope}.")
    if len(questions) != 1:
        raise SystemExit(
            "More than one open Fleet question matches; pass --question with one of: "
            + ", ".join(str(question.get("question_id")) for question in questions)
        )
    return questions[0]


def reply_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = resolve_run_id(repo_root, args.run_id)
    message = reply_message_from_args(args)
    with mutation_lock(repo_root, run_id):
        return _reply_command_locked(args, repo_root, run_id, message)


def _reply_command_locked(
    args: argparse.Namespace,
    repo_root: Path,
    run_id: str,
    message: str,
) -> dict[str, Any]:
    state = load_state(repo_root, run_id)
    if state.get("template") != "implement":
        raise SystemExit("reply applies only to implement Fleet runs.")
    if state.get("status") == "resuming":
        raise SystemExit("Fleet resume/apply mutation is active; wait for its next dispatch checkpoint.")
    question = resolve_question_record(
        repo_root,
        run_id,
        question_id=args.question,
        story_id=args.story,
    )
    question_id = str(question.get("question_id"))
    story_id = str(question.get("story_id"))
    message_sha = hashlib.sha256(message.encode("utf-8")).hexdigest()
    target = reply_path(repo_root, run_id, question_id)
    if target.exists():
        existing = read_json_strict(target, "Fleet reply")
        task = load_task(repo_root, run_id, story_id)
        existing = validate_reply_record(
            existing,
            question,
            expected_run_id=run_id,
            expected_story_id=story_id,
            expected_question_id=question_id,
            expected_round=int(question.get("round") or 0),
        )
        if existing.get("message_sha256") == message_sha:
            if (
                task.get("state") not in {"waiting_for_brain", "reply_ready"}
                or str(task.get("open_question_id") or "") != question_id
                or int(task.get("round") or 0) != int(question.get("round") or 0)
            ):
                raise SystemExit(
                    f"Question {question_id} is no longer the active question for story {story_id}."
                )
            if (
                task.get("state") == "waiting_for_brain"
                and str(task.get("open_question_id") or "") == question_id
            ):
                task["state"] = "reply_ready"
                task["brain_reply_id"] = question_id
                task["brain_reply_at_utc"] = existing.get("created_at_utc")
                save_task(repo_root, run_id, task)
            fresh_state = load_state(repo_root, run_id)
            if fresh_state.get("status") != "dispatching":
                remaining_waiters = any(
                    load_task(repo_root, run_id, candidate).get("state") == "waiting_for_brain"
                    for candidate in fresh_state.get("story_ids", [])
                )
                fresh_state["status"] = "awaiting_brain" if remaining_waiters else "reply_ready"
                save_state(repo_root, fresh_state)
            return {
                "operation": "reply",
                "run_id": run_id,
                "story_id": story_id,
                "question_id": question_id,
                "state": load_task(repo_root, run_id, story_id).get("state"),
                "idempotent": True,
                "next_action": f"fleet resume {run_id}",
            }
        raise SystemExit(
            f"Question {question_id} already has a different immutable reply; use verdict --reject "
            "with explicit rework instructions to supersede this Q/A round."
        )
    task = load_task(repo_root, run_id, story_id)
    if task.get("state") != "waiting_for_brain":
        raise SystemExit(
            f"Reply requires state waiting_for_brain (story {story_id} is {task.get('state')})."
        )
    if str(task.get("open_question_id") or "") != question_id:
        raise SystemExit(
            f"Question {question_id} is stale for story {story_id}; current question is {task.get('open_question_id')}."
        )
    validate_question_record(
        question,
        expected_run_id=run_id,
        expected_story_id=story_id,
        expected_question_id=question_id,
        expected_round=int(task.get("round") or 0),
    )
    reply = {
        "schema_version": FLEET_SCHEMA_VERSION,
        "question_id": question_id,
        "question_sha256": question.get("question_sha256"),
        "run_id": run_id,
        "story_id": story_id,
        "round": question.get("round"),
        "message": message,
        "message_sha256": message_sha,
        "created_at_utc": utc_now(),
    }
    reply_created = True
    try:
        write_json_exclusive(target, reply)
    except SystemExit:
        raced = read_json_lenient(target)
        raced = validate_reply_record(
            raced,
            question,
            expected_run_id=run_id,
            expected_story_id=story_id,
            expected_question_id=question_id,
            expected_round=int(question.get("round") or 0),
        )
        if raced.get("message_sha256") != message_sha:
            raise
        reply_created = False
    task["state"] = "reply_ready"
    task["brain_reply_id"] = question_id
    task["brain_reply_at_utc"] = reply["created_at_utc"]
    save_task(repo_root, run_id, task)
    fresh_state = load_state(repo_root, run_id)
    remaining_waiters = any(
        load_task(repo_root, run_id, candidate).get("state") == "waiting_for_brain"
        for candidate in fresh_state.get("story_ids", [])
    )
    if fresh_state.get("status") != "dispatching":
        fresh_state["status"] = "awaiting_brain" if remaining_waiters else "reply_ready"
        save_state(repo_root, fresh_state)
    if reply_created:
        journal_append(
            repo_root,
            run_id,
            {"event": "brain_reply", "story_id": story_id, "question_id": question_id},
        )
        conversation_append(
            repo_root,
            run_id,
            actor="brain",
            kind="reply",
            story_id=story_id,
            content=message,
            question_id=question_id,
            round=question.get("round"),
        )
    return {
        "operation": "reply",
        "run_id": run_id,
        "story_id": story_id,
        "question_id": question_id,
        "state": "reply_ready",
        "idempotent": not reply_created,
        "next_action": f"fleet resume {run_id}",
    }


def read_conversation_page(
    repo_root: Path,
    run_id: str,
    *,
    since: int,
    limit: int,
    story_id: str | None,
    include_content: bool,
) -> tuple[list[dict[str, Any]], int, list[int]]:
    path = conversation_path(repo_root, run_id)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    cursor = min(max(0, since), len(lines))
    events: list[dict[str, Any]] = []
    parse_error_lines: list[int] = []
    index = cursor
    while index < len(lines) and len(events) < limit:
        raw = lines[index]
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            parse_error_lines.append(index + 1)
            # A concurrently-written final line may be incomplete. Do not
            # advance the cursor so a later monitor call can retry it.
            if index == len(lines) - 1:
                break
            index += 1
            continue
        index += 1
        if not isinstance(event, dict):
            continue
        if story_id and event.get("story_id") != story_id:
            continue
        event = dict(event)
        event["cursor"] = index
        if not include_content:
            event.pop("content", None)
        events.append(event)
    return events, index, parse_error_lines


def log_metadata(path: Path, repo_root: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": coverage_lib.relative(path, repo_root), "exists": False, "size": 0}
    stat = path.stat()
    return {
        "path": coverage_lib.relative(path, repo_root),
        "exists": True,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def monitor_task_snapshot(repo_root: Path, run_id: str, story_id: str) -> dict[str, Any]:
    task = load_task(repo_root, run_id, story_id)
    tdir = task_dir(repo_root, run_id, story_id)
    pid_path = tdir / "worker.pid"
    pid: int | None = None
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = None
    attempt = max(1, int(task.get("attempts") or 0) + (1 if task.get("state") == "dispatched" else 0))
    stdout_candidates = sorted(tdir.glob("stdout_*.log"))
    stderr_candidates = sorted(tdir.glob("stderr_*.log"))
    return {
        "story_id": story_id,
        "state": task.get("state"),
        "round": task.get("round"),
        "attempts": task.get("attempts"),
        "error": task.get("error"),
        "open_question_id": task.get("open_question_id") if task.get("state") in {"waiting_for_brain", "reply_ready"} else None,
        "worker_pid": pid,
        "worker_running": process_is_alive(pid),
        "stdout": log_metadata(stdout_candidates[-1] if stdout_candidates else tdir / f"stdout_{attempt}.log", repo_root),
        "stderr": log_metadata(stderr_candidates[-1] if stderr_candidates else tdir / f"stderr_{attempt}.log", repo_root),
    }


def monitor_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = args.run_id or latest_run_id(repo_root)
    if not run_id:
        return {"operation": "monitor", "runs": [], "cursor": 0, "events": []}
    deadline = time.monotonic() + max(0.0, float(args.wait_seconds))
    events: list[dict[str, Any]] = []
    cursor = max(0, int(args.since))
    parse_errors: list[int] = []
    state = load_state(repo_root, run_id)
    while True:
        events, cursor, parse_errors = read_conversation_page(
            repo_root,
            run_id,
            since=int(args.since),
            limit=max(1, int(args.limit)),
            story_id=args.story,
            include_content=bool(args.include_content),
        )
        state = load_state(repo_root, run_id)
        if events or time.monotonic() >= deadline or state.get("status") != "dispatching":
            break
        time.sleep(max(0.05, float(args.poll_seconds)))
    tasks = [
        monitor_task_snapshot(repo_root, run_id, story_id)
        for story_id in state.get("story_ids", [])
        if not args.story or story_id == args.story
    ]
    mailbox_diagnostics: list[dict[str, Any]] = []
    open_questions = [
        {
            "question_id": question.get("question_id"),
            "story_id": question.get("story_id"),
            "round": question.get("round"),
            "summary": message_preview(str((question.get("question") or {}).get("text") or "")),
        }
        for question in load_open_questions(
            repo_root,
            run_id,
            story_id=args.story,
            diagnostics=mailbox_diagnostics,
        )
    ]
    needs_brain = any(
        task.get("state")
        in {
            "waiting_for_brain",
            "reply_ready",
            "needs_review",
            "approved",
            "rejected",
            "failed",
            "conflict",
        }
        for task in tasks
    )
    reply_ready = any(task.get("state") == "reply_ready" for task in tasks)
    return {
        "operation": "monitor",
        "run_id": run_id,
        "status": state.get("status"),
        "cursor": cursor,
        "events": events,
        "parse_error_lines": parse_errors,
        "tasks": tasks,
        "open_questions": open_questions,
        "mailbox_diagnostics": mailbox_diagnostics,
        "needs_brain": needs_brain,
        "conversation_path": coverage_lib.relative(conversation_path(repo_root, run_id), repo_root),
        "supervisor": read_json_lenient(supervisor_path(repo_root, run_id)),
        "next_actions": [
            (
                f"Reply: fleet reply {run_id} --question <id> --message-file <path>; "
                f"then fleet resume {run_id}"
                if open_questions
                else (
                    "Reject/cancel the task with the preserved corrupt mailbox artifact"
                    if mailbox_diagnostics
                    else (
                    f"Resume answered/reviewed tasks: fleet resume {run_id}"
                    if reply_ready
                    else f"Continue monitoring with --since {cursor}"
                    )
                )
            ),
            f"Review packet: fleet packet {run_id}",
        ],
    }


def verdict_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = resolve_run_id(repo_root, args.run_id)
    with mutation_lock(repo_root, run_id):
        return _verdict_command_locked(args, repo_root, run_id)


def _verdict_command_locked(
    args: argparse.Namespace,
    repo_root: Path,
    run_id: str,
) -> dict[str, Any]:
    state = load_state(repo_root, run_id)
    if state.get("template") != "implement":
        raise SystemExit("verdict/resume apply to the implement template; review runs end at the packet.")
    if state.get("status") == "resuming":
        raise SystemExit("Fleet resume/apply mutation is active; wait for its next dispatch checkpoint.")
    task = load_task(repo_root, run_id, args.story)
    if not task:
        raise SystemExit(f"Unknown story in run {run_id}: {args.story}")
    if args.approve == args.reject:
        raise SystemExit("Pass exactly one of --approve or --reject.")
    current = str(task.get("state"))
    if args.approve:
        if current != "needs_review":
            raise SystemExit(f"--approve requires state needs_review (story {args.story} is {current}).")
        proof = {
            "evidence": str(args.evidence or "").strip(),
            "validation": str(args.validation or "").strip(),
            "semantic": str(args.semantic or "").strip(),
            "provenance": str(args.provenance or "").strip(),
            "negative_test": str(args.negative_test or "").strip(),
        }
        proof_errors = approval_verdict_contract_errors({"decision": "approve", **proof})
        if proof_errors:
            raise SystemExit(
                "--approve requires explicit substantive brain proof for every coverage field; "
                f"invalid: {', '.join(proof_errors)}. Blank/known-placeholder values and worker claims "
                "cannot satisfy this contract."
            )
        task["state"] = "approved"
        task["verdict"] = {
            "decision": "approve",
            **proof,
            "at": utc_now(),
        }
    else:
        if current not in REJECTABLE_STATES:
            raise SystemExit(f"--reject requires state in {sorted(REJECTABLE_STATES)} (story {args.story} is {current}).")
        if not str(args.rework or "").strip():
            raise SystemExit("--reject requires non-empty --rework instructions for the worker.")
        question_id = str(task.get("open_question_id") or "")
        if current in {"waiting_for_brain", "reply_ready"} and question_id:
            task_round = int(task.get("round") or 0)
            question_file = question_path(repo_root, run_id, question_id)
            try:
                question = validate_question_record(
                    read_json_strict(question_file, "Fleet question"),
                    expected_run_id=run_id,
                    expected_story_id=args.story,
                    expected_question_id=question_id,
                    expected_round=task_round,
                )
            except (SystemExit, OSError) as exc:
                diagnostic = mailbox_diagnostic(
                    repo_root,
                    question_file,
                    kind="corrupt_question",
                    error=exc,
                )
                _recovery, recovery_file = write_forensic_recovery(
                    repo_root,
                    run_id,
                    story_id=args.story,
                    question_id=question_id,
                    round_number=task_round,
                    question_sha256=None,
                    reply_sha256=None,
                    disposition="rejected_corrupt_question",
                    corrupt_artifact=diagnostic,
                )
                task.setdefault("mailbox_diagnostics", []).append(diagnostic)
                task["mailbox_recovery_path"] = coverage_lib.relative(recovery_file, repo_root)
            else:
                reply_file = reply_path(repo_root, run_id, question_id)
                reply_sha: str | None = None
                corrupt_reply_sha: str | None = None
                corrupt_reply_reason: str | None = None
                if reply_file.exists():
                    try:
                        reply = validate_reply_record(
                            read_json_strict(reply_file, "Fleet reply"),
                            question,
                            expected_run_id=run_id,
                            expected_story_id=args.story,
                            expected_question_id=question_id,
                            expected_round=task_round,
                        )
                        reply_sha = str(reply.get("message_sha256") or "")
                    except (SystemExit, OSError) as exc:
                        # Explicit brain rejection is the recovery path for a
                        # corrupt immutable reply. Preserve its raw digest as
                        # forensic evidence; never trust, edit, or delete it.
                        diagnostic = mailbox_diagnostic(
                            repo_root,
                            reply_file,
                            kind="corrupt_reply",
                            error=exc,
                        )
                        task.setdefault("mailbox_diagnostics", []).append(diagnostic)
                        corrupt_reply_sha = diagnostic.get("raw_sha256")
                        corrupt_reply_reason = diagnostic.get("reason")
                closed = consumed_path(repo_root, run_id, question_id)
                expected_closed = {
                    "schema_version": FLEET_SCHEMA_VERSION,
                    "question_id": question_id,
                    "question_sha256": question.get("question_sha256"),
                    "reply_sha256": reply_sha,
                    "run_id": run_id,
                    "story_id": args.story,
                    "round": task_round,
                }
                if not closed.exists():
                    write_json_exclusive(
                        closed,
                        {
                            **expected_closed,
                            "disposition": (
                                "rejected_corrupt_reply"
                                if corrupt_reply_sha
                                else "rejected_for_rework"
                            ),
                            "corrupt_reply_sha256": corrupt_reply_sha,
                            "corrupt_reply_reason": corrupt_reply_reason,
                            "consumed_at_utc": utc_now(),
                        },
                    )
                else:
                    try:
                        closed_payload = read_json_strict(closed, "Fleet consumed reply")
                        if not isinstance(closed_payload, dict) or any(
                            closed_payload.get(key) != value
                            for key, value in expected_closed.items()
                        ):
                            raise SystemExit(
                                f"Consumed reply provenance mismatch for story {args.story}."
                            )
                    except (SystemExit, OSError) as exc:
                        diagnostic = mailbox_diagnostic(
                            repo_root,
                            closed,
                            kind="corrupt_consumed",
                            error=exc,
                        )
                        _recovery, recovery_file = write_forensic_recovery(
                            repo_root,
                            run_id,
                            story_id=args.story,
                            question_id=question_id,
                            round_number=task_round,
                            question_sha256=str(question.get("question_sha256") or ""),
                            reply_sha256=reply_sha,
                            disposition="rejected_corrupt_consumed",
                            corrupt_artifact=diagnostic,
                        )
                        task.setdefault("mailbox_diagnostics", []).append(diagnostic)
                        task["mailbox_recovery_path"] = coverage_lib.relative(recovery_file, repo_root)
            task["closed_question_id"] = question_id
            task.pop("open_question_id", None)
            task.pop("brain_reply_id", None)
            task.pop("brain_reply_at_utc", None)
        task["state"] = "rejected"
        task["verdict"] = {"decision": "reject", "rework": args.rework, "at": utc_now()}
    save_task(repo_root, run_id, task)
    journal_append(repo_root, run_id, {"event": "verdict", "story_id": args.story, "decision": task["verdict"]["decision"]})
    if args.approve:
        conversation_append(
            repo_root,
            run_id,
            actor="brain",
            kind="approval",
            story_id=args.story,
            content=str(task["verdict"]["evidence"]),
        )
    else:
        conversation_append(
            repo_root,
            run_id,
            actor="brain",
            kind="rework",
            story_id=args.story,
            content=str(args.rework),
        )
    fresh_state = load_state(repo_root, run_id)
    if fresh_state.get("status") != "dispatching":
        waiters = any(
            load_task(repo_root, run_id, candidate).get("state") == "waiting_for_brain"
            for candidate in fresh_state.get("story_ids", [])
        )
        fresh_state["status"] = "awaiting_brain" if waiters else "awaiting_verdicts"
        save_state(repo_root, fresh_state)
    return {"operation": "verdict", "run_id": run_id, "story_id": args.story, "state": task["state"]}


def apply_coverage_updates(repo_root: Path, run_id: str, story: dict[str, Any], task: dict[str, Any]) -> list[str]:
    import subprocess

    warnings: list[str] = []
    verdict = task.get("verdict") or {}
    contract_errors = approval_verdict_contract_errors(verdict)
    if contract_errors:
        raise SystemExit(
            f"Refusing coverage update for {task.get('story_id')}: strict brain verdict contract "
            f"missing {', '.join(contract_errors)}."
        )
    evidence = str(verdict["evidence"]).strip()
    validation = str(verdict["validation"]).strip()
    semantic = str(verdict["semantic"]).strip()
    provenance = str(verdict["provenance"]).strip()
    negative = str(verdict["negative_test"]).strip()
    script = Path(__file__).resolve().parent / "source_coverage_harness.py"
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    for row_id in story.get("linked_source_row_ids") or []:
        cmd = [
            sys.executable, "-B", str(script), str(repo_root), "update", str(row_id),
            "--status", "implemented",
            "--evidence", evidence,
            "--validation", validation,
            "--semantic-validation", semantic,
            "--negative-test", negative,
            "--provenance", provenance,
            "--json",
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        if proc.returncode != 0:
            warnings.append(f"coverage update failed for row {row_id}: {proc.stdout[-200:] or proc.stderr[-200:]}")
    return warnings


def resume_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = resolve_run_id(repo_root, args.run_id)
    state = load_state(repo_root, run_id)
    if state.get("template") != "implement":
        raise SystemExit("resume applies to the implement template.")
    if state.get("status") == "cancelled":
        raise SystemExit(f"Run {run_id} is cancelled.")
    if state.get("status") == "dispatching":
        owner = live_run_lock(repo_root, run_id)
        if owner:
            raise SystemExit(
                f"Run {run_id} is still dispatching under live pid {owner.get('pid')}. "
                "Monitor it until the checkpoint before resume."
            )
        live_workers: list[str] = []
        for story_id in state.get("story_ids", []):
            pid_file = task_dir(repo_root, run_id, story_id) / "worker.pid"
            try:
                worker_pid = int(pid_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            if process_is_alive(worker_pid):
                live_workers.append(f"{story_id}:{worker_pid}")
        if live_workers:
            raise SystemExit(
                f"Run {run_id} lost its driver but still has live worker(s): {', '.join(live_workers)}. "
                "Request fleet cancel before recovery."
            )
    owner_token = acquire_lock(repo_root, run_id, force=False)
    warnings: list[str] = []
    budget_extension: dict[str, Any] | None = None
    resume_state_entered = False
    try:
        state = load_state(repo_root, run_id)
        if state.get("status") == "dispatching":
            with mutation_lock(repo_root, run_id):
                for story_id in state.get("story_ids", []):
                    interrupted = load_task(repo_root, run_id, story_id)
                    if interrupted.get("state") in {"pending", "dispatched"}:
                        interrupted["state"] = "failed"
                        interrupted["error"] = (
                            "Fleet driver exited before a checkpoint; reject with rework to redispatch."
                        )
                        save_task(repo_root, run_id, interrupted)
                state["status"] = "awaiting_verdicts"
                save_state(repo_root, state)
                journal_append(
                    repo_root,
                    run_id,
                    {"event": "stale_dispatch_recovered", "reason": "driver lock not live"},
                )
        with mutation_lock(repo_root, run_id):
            state = load_state(repo_root, run_id)
            requested_max_agents = getattr(args, "max_agents", None)
            if requested_max_agents is not None:
                requested_max_agents = int(requested_max_agents)
                if requested_max_agents < 1:
                    raise SystemExit("--max-agents must be at least 1.")
                params = dict(state.get("params") or {})
                configured_max_agents = int(
                    params.get("max_agents") or DEFAULT_MAX_AGENTS
                )
                persisted_attempts = sum(
                    int(load_task(repo_root, run_id, story_id).get("attempts") or 0)
                    for story_id in state.get("story_ids", [])
                )
                already_spent = max(
                    int(state.get("agents_spawned") or 0), persisted_attempts
                )
                if requested_max_agents < configured_max_agents:
                    raise SystemExit(
                        "--max-agents may only extend the cumulative worker budget "
                        f"(configured={configured_max_agents}, requested={requested_max_agents})."
                    )
                if requested_max_agents < already_spent:
                    raise SystemExit(
                        "--max-agents cannot be lower than the persisted worker attempts "
                        f"(spent={already_spent}, requested={requested_max_agents})."
                    )
                if requested_max_agents > configured_max_agents:
                    budget_extension = {
                        "event": "worker_budget_extended",
                        "at_utc": utc_now(),
                        "old_max_agents": configured_max_agents,
                        "new_max_agents": requested_max_agents,
                        "agents_already_spent": already_spent,
                        "actor": "operator",
                    }
                    params["max_agents"] = requested_max_agents
                    state["params"] = params
                    state.setdefault("worker_budget_history", []).append(
                        dict(budget_extension)
                    )
            state["status"] = "resuming"
            save_state(repo_root, state)
            resume_state_entered = True
        if budget_extension is not None:
            journal_append(repo_root, run_id, dict(budget_extension))
            conversation_append(
                repo_root,
                run_id,
                actor="harness",
                kind="worker_budget_extended",
                content=(
                    "Operator extended the cumulative Fleet worker budget from "
                    f"{budget_extension['old_max_agents']} to "
                    f"{budget_extension['new_max_agents']} after "
                    f"{budget_extension['agents_already_spent']} persisted attempts."
                ),
            )
        stories_meta = {str(story.get("id")): story for story in state.get("stories_snapshot", [])}
        applied: list[str] = []
        approved_tasks: list[tuple[str, dict[str, Any]]] = []
        for story_id in state.get("story_ids", []):
            task = load_task(repo_root, run_id, story_id)
            if task.get("state") == "approved":
                approved_tasks.append((story_id, task))
        invalid_approvals: list[tuple[str, list[str]]] = []
        for story_id, task in approved_tasks:
            contract_errors = approval_verdict_contract_errors(task.get("verdict"))
            if contract_errors:
                invalid_approvals.append((story_id, contract_errors))
        if invalid_approvals:
            details = "; ".join(
                f"{story_id}: {', '.join(errors)}"
                for story_id, errors in invalid_approvals
            )
            raise SystemExit(
                "Resume refused before applying any patch: approved task(s) lack the strict brain "
                f"verdict contract ({details}). Re-review and record a new verdict."
            )
        if approved_tasks:
            # Checked once: each applied patch legitimately dirties the tree for
            # the next one; cross-story conflicts surface as apply failures below.
            require_clean_tree(repo_root, action="apply")
        for story_id in state.get("story_ids", []):
            if control_cancel_requested(repo_root, run_id):
                break
            task = load_task(repo_root, run_id, story_id)
            if task.get("state") != "approved":
                continue
            patch_file = task_dir(repo_root, run_id, story_id) / "patch.diff"
            violations = ownership_violations(task.get("files_changed", []), (state.get("ownership") or {}).get(story_id))
            if violations:
                task["state"] = "conflict"
                task["error"] = f"ownership violation at apply: {', '.join(violations[:5])}"
                save_task(repo_root, run_id, task)
                continue
            state_violations = worker_state_violations(task.get("files_changed", []))
            if state_violations:
                task["state"] = "conflict"
                task["error"] = f"worker state path violation at apply: {', '.join(state_violations[:5])}"
                save_task(repo_root, run_id, task)
                continue
            with GIT_MAIN_LOCK:
                apply_run, apply_mode = git_apply_with_fallback(repo_root, patch_file, check_only=False)
            if apply_mode is None:
                task["state"] = "conflict"
                task["error"] = f"patch apply failed: {apply_run.stderr.strip()[-300:]}"
                save_task(repo_root, run_id, task)
                journal_append(repo_root, run_id, {"event": "story_conflict", "story_id": story_id})
                continue
            task["apply_mode"] = apply_mode
            task["base_commit"] = state.get("base_commit")
            row_warnings = apply_coverage_updates(repo_root, run_id, stories_meta.get(story_id, {}), task)
            warnings.extend(row_warnings)
            task["state"] = "applied"
            task["applied_at_utc"] = utc_now()
            save_task(repo_root, run_id, task)
            journal_append(repo_root, run_id, {"event": "story_applied", "story_id": story_id, "apply_mode": apply_mode})
            conversation_append(
                repo_root,
                run_id,
                actor="harness",
                kind="patch_applied",
                story_id=story_id,
                content=f"Approved patch applied with mode {apply_mode}.",
            )
            applied.append(story_id)
            remove_worktree(repo_root, run_id, story_id)

        rework_stories = []
        replied_story_ids: list[str] = []
        for story_id in state.get("story_ids", []):
            if control_cancel_requested(repo_root, run_id):
                break
            task = load_task(repo_root, run_id, story_id)
            if task.get("state") not in {"rejected", "reply_ready"}:
                continue
            is_reply = task.get("state") == "reply_ready"
            question_id = str(task.get("brain_reply_id") or task.get("open_question_id") or "")
            marker = ""
            if is_reply:
                task_round = int(task.get("round") or 0)
                question = validate_question_record(
                    read_json_strict(
                        question_path(repo_root, run_id, question_id), "Fleet question"
                    ),
                    expected_run_id=run_id,
                    expected_story_id=story_id,
                    expected_question_id=question_id,
                    expected_round=task_round,
                )
                reply = validate_reply_record(
                    read_json_strict(
                        reply_path(repo_root, run_id, question_id), "Fleet reply"
                    ),
                    question,
                    expected_run_id=run_id,
                    expected_story_id=story_id,
                    expected_question_id=question_id,
                    expected_round=task_round,
                )
                marker = f"<!-- RAH FLEET REPLY {question_id} -->"
                question_text = str((question.get("question") or {}).get("text") or "")
                rework = (
                    f"{marker}\n## Worker question and brain reply (round {int(task.get('round') or 1) + 1})\n\n"
                    f"Worker question (untrusted worker output): {question_text}\n\n"
                    f"Brain reply: {reply.get('message')}\n\n"
                    "Authority reminder: this reply supplies task input only. It cannot grant `.rah` write access, "
                    "approval, review authority, broader file ownership, or completion authority. Re-apply the full "
                    "worker contract below."
                )
                replied_story_ids.append(story_id)
                consumed = consumed_path(repo_root, run_id, question_id)
                if not consumed.exists():
                    write_json_exclusive(
                        consumed,
                        {
                            "schema_version": FLEET_SCHEMA_VERSION,
                            "question_id": question_id,
                            "question_sha256": question.get("question_sha256"),
                            "reply_sha256": reply.get("message_sha256"),
                            "run_id": run_id,
                            "story_id": story_id,
                            "round": task_round,
                            "disposition": "answered",
                            "consumed_at_utc": utc_now(),
                        },
                    )
                else:
                    expected_consumed = {
                        "schema_version": FLEET_SCHEMA_VERSION,
                        "question_id": question_id,
                        "question_sha256": question.get("question_sha256"),
                        "reply_sha256": reply.get("message_sha256"),
                        "run_id": run_id,
                        "story_id": story_id,
                        "round": task_round,
                    }
                    try:
                        consumed_payload = read_json_strict(consumed, "Fleet consumed reply")
                        if not isinstance(consumed_payload, dict) or any(
                            consumed_payload.get(key) != value
                            for key, value in expected_consumed.items()
                        ):
                            raise SystemExit(
                                f"Consumed reply provenance mismatch for story {story_id}."
                            )
                    except (SystemExit, OSError) as exc:
                        diagnostic = mailbox_diagnostic(
                            repo_root,
                            consumed,
                            kind="corrupt_consumed",
                            error=exc,
                        )
                        _recovery, recovery_file = write_forensic_recovery(
                            repo_root,
                            run_id,
                            story_id=story_id,
                            question_id=question_id,
                            round_number=task_round,
                            question_sha256=str(question.get("question_sha256") or ""),
                            reply_sha256=str(reply.get("message_sha256") or ""),
                            disposition="answered_corrupt_consumed",
                            corrupt_artifact=diagnostic,
                        )
                        task.setdefault("mailbox_diagnostics", []).append(diagnostic)
                        task["mailbox_recovery_path"] = coverage_lib.relative(recovery_file, repo_root)
                        save_task(repo_root, run_id, task)
            else:
                rework = str((task.get("verdict") or {}).get("rework") or "")
            brief_path = task_dir(repo_root, run_id, story_id) / "brief.md"
            brief_text = brief_path.read_text(encoding="utf-8")
            if not marker or marker not in brief_text:
                heading = (
                    ""
                    if is_reply
                    else f"## Rework feedback from the brain (round {int(task.get('round') or 1) + 1})\n\n"
                )
                contract_repeat = (
                    "\n\n## Worker contract reminder\n\n"
                    "You remain implementation-only: never write `.rah/`, never approve or declare completion, "
                    "stay inside this worktree and assigned ownership, and finish with the required result JSON.\n"
                )
                brief_path.write_text(
                    brief_text + f"\n\n{heading}{rework}\n" + contract_repeat,
                    encoding="utf-8",
                )
            current_head = git_head(repo_root)
            if str(task.get("base_commit") or state.get("base_commit")) != current_head:
                # Stale-base recovery: the main tree advanced (other applies or a
                # conflicting commit), so a rework in the old worktree would just
                # conflict again. Recreate the worktree at the fresh HEAD and keep
                # the previous attempt as a reference patch.
                tdir = task_dir(repo_root, run_id, story_id)
                prev_patch = tdir / "patch.diff"
                if not prev_patch.exists() and task.get("partial_patch_path"):
                    prev_patch = repo_root / str(task.get("partial_patch_path"))
                prev_copy = tdir / f"patch_round{int(task.get('round') or 1)}.diff"
                if prev_patch.exists():
                    prev_copy.write_bytes(prev_patch.read_bytes())
                remove_worktree(repo_root, run_id, story_id)
                task["base_commit"] = current_head
                save_task(repo_root, run_id, task)
                brief_path.write_text(
                    brief_path.read_text(encoding="utf-8")
                    + (
                        f"\n\nNOTE: the main tree advanced; your worktree was recreated at base {current_head[:8]}. "
                        f"Re-implement against the current file state. Previous attempt patch (read-only reference): {prev_copy}\n"
                    ),
                    encoding="utf-8",
                )
                journal_append(
                    repo_root, run_id,
                    {"event": "story_rebased", "story_id": story_id, "base": current_head[:8]},
                )
            rework_stories.append(stories_meta.get(story_id, {"id": story_id}))
        if rework_stories:
            with mutation_lock(repo_root, run_id):
                dispatch_state = load_state(repo_root, run_id)
                dispatch_state["status"] = "dispatching"
                save_state(repo_root, dispatch_state)
            ctx = build_run_context(repo_root, run_id, state)
            run_pool(ctx, rework_stories, process_story)
        if warnings:
            fresh = load_state(repo_root, run_id)
            fresh.setdefault("warnings", []).extend(warnings)
            save_state(repo_root, fresh)
        outcome = finalize_round(repo_root, run_id, load_state(repo_root, run_id))
    except BaseException:
        # A failed apply/rework must not leave a stale `resuming` state that
        # blocks the brain from correcting its verdict. Preserve the original
        # exception after restoring only the checkpoint status.
        if resume_state_entered:
            try:
                with mutation_lock(repo_root, run_id):
                    failed_state = load_state(repo_root, run_id)
                    tasks = all_tasks(repo_root, run_id, failed_state)
                    task_states = {str(task.get("state")) for task in tasks}
                    if control_cancel_requested(repo_root, run_id):
                        failed_state["status"] = "cancelled"
                    elif task_states and task_states <= {"applied", "cancelled"}:
                        failed_state["status"] = "completed"
                    elif "waiting_for_brain" in task_states:
                        failed_state["status"] = "awaiting_brain"
                    else:
                        failed_state["status"] = "awaiting_verdicts"
                    save_state(repo_root, failed_state)
            except BaseException:
                pass
        raise
    finally:
        release_lock(repo_root, run_id, owner_token)
    payload = {
        "operation": "resume",
        "run_id": run_id,
        "applied_story_ids": applied,
        "redispatched_story_ids": [str(story.get("id")) for story in rework_stories],
        "replied_story_ids": replied_story_ids,
        "worker_budget_extension": budget_extension,
        "warnings": warnings,
        "summary": outcome["summary"],
        "packet": outcome["packet"],
    }
    return payload


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = args.run_id or latest_run_id(repo_root)
    if not run_id:
        return {"operation": "status", "runs": []}
    state = load_state(repo_root, run_id)
    tasks = [
        monitor_task_snapshot(repo_root, run_id, story_id)
        for story_id in state.get("story_ids", [])
    ]
    mailbox_diagnostics: list[dict[str, Any]] = []
    open_questions = load_open_questions(
        repo_root,
        run_id,
        diagnostics=mailbox_diagnostics,
    )
    return {
        "operation": "status",
        "run_id": run_id,
        "status": state.get("status"),
        "template": state.get("template"),
        "engine": state.get("engine"),
        "model": state.get("model"),
        "tasks": tasks,
        "open_questions": [
            {
                "question_id": question.get("question_id"),
                "story_id": question.get("story_id"),
                "round": question.get("round"),
                "summary": message_preview(str((question.get("question") or {}).get("text") or "")),
            }
            for question in open_questions
        ],
        "mailbox_diagnostics": mailbox_diagnostics,
        "conversation_path": coverage_lib.relative(conversation_path(repo_root, run_id), repo_root),
        "supervisor": read_json_lenient(supervisor_path(repo_root, run_id)),
    }


def kill_worker_processes(repo_root: Path, run_id: str, state: dict[str, Any]) -> list[str]:
    """Best-effort: terminate still-running worker processes recorded via
    worker.pid files. PID reuse makes this a convenience, not a guarantee."""
    import subprocess

    killed: list[str] = []
    for story_id in state.get("story_ids", []):
        pid_file = task_dir(repo_root, run_id, story_id) / "worker.pid"
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if not process_is_alive(pid):
            continue
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False, capture_output=True, text=True,
                )
            else:
                os.kill(pid, 9)
            killed.append(f"{story_id}:{pid}")
        except OSError:
            continue
    return killed


def cancel_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_id = resolve_run_id(repo_root, args.run_id)
    state = load_state(repo_root, run_id)
    if state.get("status") in TERMINAL_RUN_STATUSES:
        return {
            "operation": "cancel",
            "run_id": run_id,
            "status": state.get("status"),
            "idempotent": True,
            "note": "terminal Fleet history is immutable; cancel made no changes",
        }
    write_json(run_dir(repo_root, run_id) / "control.json", {"cancel": True, "at": utc_now()})
    killed = kill_worker_processes(repo_root, run_id, state)
    with cross_process_file_lock(lifecycle_guard_path(repo_root), timeout_seconds=10.0):
        existing_lock = read_json_lenient(lock_path(repo_root))
    live_owner = bool(
        isinstance(existing_lock, dict)
        and existing_lock.get("run_id") == run_id
        and process_is_alive(existing_lock.get("pid"))
    )
    if live_owner:
        conversation_append(
            repo_root,
            run_id,
            actor="harness",
            kind="cancel_requested",
            content=(
                "Fleet cancellation requested. The live driver retains its owner lock and will "
                "terminalize the run after workers stop."
            ),
            owner_pid=existing_lock.get("pid"),
        )
        return {
            "operation": "cancel",
            "run_id": run_id,
            "status": "cancel_requested",
            "owner_pid": existing_lock.get("pid"),
            "killed_workers": killed,
        }
    owner_token = acquire_lock(repo_root, run_id, force=True)
    try:
        outcome = finalize_round(repo_root, run_id, load_state(repo_root, run_id))
    finally:
        release_lock(repo_root, run_id, owner_token)
    conversation_append(
        repo_root,
        run_id,
        actor="harness",
        kind="run_cancelled",
        content=f"Fleet run cancelled; killed worker records: {', '.join(killed) if killed else 'none'}.",
    )
    return {
        "operation": "cancel",
        "run_id": run_id,
        "status": "cancelled",
        "killed_workers": killed,
        "summary": outcome["summary"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _bounded_probe_timeout(value: str) -> int:
    # R28: 0/negative silently disables the kill timer in run_once — refuse
    # before any subprocess can start.
    number = int(value)
    if not 1 <= number <= 600:
        raise argparse.ArgumentTypeError("sandbox probe timeout must be within 1..600 seconds")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = _SuggestingArgumentParser(
        description=(
            "Fleet: parallel implementation-only workers with a checkpoint-return protocol. "
            "The harness never judges; the calling session (the brain) reviews the packet and issues verdicts."
        )
    )
    parser.add_argument("repo_root", help="Path to the repository root.")
    sub = parser.add_subparsers(dest="command", required=True)

    dispatch = sub.add_parser("dispatch", help="Fan out workers, pre-gate results, emit a review packet, then stop.")
    dispatch.add_argument("--from-prd", action="store_true", default=True, help=argparse.SUPPRESS)
    dispatch.add_argument("--run-id", default=None, help="Optional caller-provided safe run id (useful for monitored background dispatch).")
    dispatch.add_argument("--template", choices=["implement", "review"], default="implement")
    dispatch.add_argument("--stories", default=None, help="Comma-separated PRD story ids (default: all unready).")
    # Workers default to codex (gpt-5.6-sol max) regardless of the host runtime;
    # claude is opt-in only (design contract R3). "auto" keeps runtime detection
    # available for operators who explicitly want it.
    dispatch.add_argument("--engine", choices=["codex", "claude", "auto"], default="codex")
    dispatch.add_argument("--model", default=None, help="Worker model (codex default from config.toml, else gpt-5.6-sol).")
    dispatch.add_argument(
        "--effort",
        default=None,
        help=(
            "Worker effort: codex model_reasoning_effort (default from config.toml, "
            "else max) or claude --effort; empty skips the flag."
        ),
    )
    dispatch.add_argument("--sandbox", default=None, help="codex sandbox (default workspace-write / read-only for review).")
    dispatch.add_argument(
        "--reprobe-sandbox",
        action="store_true",
        help="Ignore the cached Windows sandbox probe result and probe again before dispatch.",
    )
    dispatch.add_argument(
        "--sandbox-probe-timeout-seconds",
        type=_bounded_probe_timeout,
        default=120,
        help="Kill-and-fail deadline (1..600s) for the Windows codex sandbox viability probe (one tiny model call; success cached 14 days, failure 6 hours).",
    )
    dispatch.add_argument("--codex-bin", default=None)
    dispatch.add_argument("--claude-bin", default=None)
    dispatch.add_argument(
        "--claude-arg",
        action="append",
        default=[],
        metavar="ARG",
        help=(
            "Repeatable raw Claude CLI argument appended in order; use "
            "--claude-arg=VALUE when VALUE begins with '-' or is empty. "
            "Requires --engine claude."
        ),
    )
    dispatch.add_argument("--permission-mode", default=None, help="claude --permission-mode. (engine=claude)")
    dispatch.add_argument("--dangerously-skip-permissions", action="store_true")
    dispatch.add_argument("--dangerously-bypass-approvals-and-sandbox", action="store_true")
    dispatch.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL)
    dispatch.add_argument("--task-timeout-seconds", type=int, default=DEFAULT_TASK_TIMEOUT_SECONDS)
    dispatch.add_argument("--max-agents", type=int, default=DEFAULT_MAX_AGENTS)
    dispatch.add_argument("--run-timeout-seconds", type=int, default=0, help="Wall-clock budget for the whole run (0 = off).")
    dispatch.add_argument("--test-cmd", default=None, help="Command run inside each worktree as a pre-gate.")
    dispatch.add_argument("--worker-contract", default=None, help="Additional brain-authored contract appended to every implementation brief.")
    dispatch.add_argument("--ownership-file", default=None, help="JSON mapping story id -> exclusive glob list.")
    dispatch.add_argument("--brief-dir", default=None, help="Brain-authored brief overrides (<story>.md).")
    dispatch.add_argument("--force-new", action="store_true")
    dispatch.add_argument("--json", action="store_true")

    packet = sub.add_parser("packet", help="Reprint the review packet (brain inbox).")
    packet.add_argument("run_id", nargs="?", default=None)
    packet.add_argument(
        "--refresh",
        action="store_true",
        help="Deterministically rebuild the packet from current task checkpoints before reading it.",
    )
    packet.add_argument("--json", action="store_true")

    monitor = sub.add_parser(
        "monitor",
        help="Read the explicit worker/brain conversation stream with a stable cursor.",
    )
    monitor.add_argument("run_id", nargs="?", default=None)
    monitor.add_argument("--since", type=int, default=0, help="Return events after this cursor.")
    monitor.add_argument("--limit", type=int, default=DEFAULT_MONITOR_LIMIT)
    monitor.add_argument("--story", default=None, help="Filter display to one story while advancing the run cursor.")
    monitor.add_argument("--wait-seconds", type=float, default=0.0, help="Long-poll for new events for at most this many seconds.")
    monitor.add_argument("--poll-seconds", type=float, default=0.25)
    monitor.add_argument(
        "--include-content",
        action="store_true",
        help="Include full explicit brief/question/reply/result content. Hidden reasoning is never recorded.",
    )
    monitor.add_argument("--json", action="store_true")

    reply = sub.add_parser(
        "reply",
        help="Answer one immutable worker question for the next re-dispatch round.",
    )
    reply.add_argument("run_id", nargs="?", default=None)
    reply.add_argument("--question", default=None, help="Question id; may be omitted when exactly one is open.")
    reply.add_argument("--story", default=None, help="Optional story scope or provenance check.")
    reply.add_argument("--message", default=None, help="Short answer (prefer --message-file/--stdin for sensitive text).")
    reply.add_argument("--message-file", default=None, help="UTF-8 file containing the brain answer.")
    reply.add_argument("--stdin", action="store_true", help="Read the brain answer from stdin.")
    reply.add_argument("--json", action="store_true")

    verdict = sub.add_parser("verdict", help="Record the brain's judgment for one story.")
    verdict.add_argument("run_id", nargs="?", default=None)
    verdict.add_argument("--story", required=True)
    verdict.add_argument("--approve", action="store_true")
    verdict.add_argument("--reject", action="store_true")
    verdict.add_argument("--evidence", default=None, help="Required with --approve: the brain's own diff finding.")
    verdict.add_argument("--rework", default=None, help="Required with --reject: instructions for the worker.")
    verdict.add_argument("--validation", default=None, help="Required with --approve: brain-verified command/result.")
    verdict.add_argument("--semantic", default=None, help="Required with --approve: brain-verified semantic proof.")
    verdict.add_argument("--negative-test", default=None, help="Required with --approve: brain-verified fails-if-superficial proof.")
    verdict.add_argument("--provenance", default=None, help="Required with --approve: brain-verified source/data-path proof.")
    verdict.add_argument("--json", action="store_true")

    resume = sub.add_parser("resume", help="Apply approved patches (+coverage rows) and re-dispatch rejected stories.")
    resume.add_argument("run_id", nargs="?", default=None)
    resume.add_argument(
        "--max-agents",
        type=int,
        default=None,
        help=(
            "Increase this run's cumulative worker-attempt ceiling before re-dispatch. "
            "The value may not lower the configured or already-spent budget."
        ),
    )
    resume.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Show run/task states (read-only).")
    status.add_argument("run_id", nargs="?", default=None)
    status.add_argument("--json", action="store_true")

    cancel = sub.add_parser("cancel", help="Cancel a run and clean its worktrees.")
    cancel.add_argument("run_id", nargs="?", default=None)
    cancel.add_argument("--json", action="store_true")
    return parser


COMMANDS = {
    "dispatch": dispatch_command,
    "packet": packet_command,
    "monitor": monitor_command,
    "reply": reply_command,
    "verdict": verdict_command,
    "resume": resume_command,
    "status": status_command,
    "cancel": cancel_command,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = COMMANDS[args.command](args)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    coverage_lib.print_payload(payload, getattr(args, "json", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
