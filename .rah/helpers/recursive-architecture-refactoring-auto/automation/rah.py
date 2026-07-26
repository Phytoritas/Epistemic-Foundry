#!/usr/bin/env python3
"""Unified CLI wrapper for the recursive architecture harness helpers."""
from __future__ import annotations

import os
import sys

# FIRST executable lines, before any shadowable stdlib import: demote the
# script dir from sys.path[0] to the END. Reviewer round 2: a sourceless
# `automation/json.pyc` would otherwise load INSTEAD of the stdlib the
# moment this script says `import json` — before any gate can run
# (SourcelessFileLoader ignores pycache_prefix). With the dir at the end,
# stdlib wins; sibling imports still resolve. Residual boundary: a sibling
# whose .py was deleted AND replaced by a .pyc is verifier-compromise
# territory — the manifest flags both (missing + sourceless-bytecode
# findings) for every OTHER process.
_here = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0] or os.getcwd()) == _here:
    sys.path.pop(0)
if _here not in sys.path:
    sys.path.append(_here)

import tempfile

# Bytecode caches inside the package are outside the manifest, so this
# process (and every child via the env var) must never READ or write an
# in-tree __pycache__ (defense-in-depth alongside the path demotion above).
if not sys.pycache_prefix:
    sys.pycache_prefix = os.path.join(tempfile.gettempdir(), "rah-pyc")
    os.environ.setdefault("PYTHONPYCACHEPREFIX", sys.pycache_prefix)

import argparse
import errno
import hashlib
import json
import shutil
import stat
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SKILL_DIR_NAME = "recursive-architecture-refactoring-auto"
# One command authority (R31): every surface, alias, and policy bit lives in
# COMMAND_REGISTRY; SCRIPT_MAP / REPO_AWARE_COMMANDS / AUTO_BOOTSTRAP_COMMANDS
# are derived views so the three can never disagree.
#
# Public surface (R30) is exactly four verbs — run / inspect / verify / admin.
# Legacy names keep byte-identical dispatch behavior but live only in
# --help-all, and print a one-line stderr notice pointing at the verb path.

PUBLIC_VERBS = ("run", "inspect", "verify", "admin")

COMMAND_REGISTRY: dict[str, dict] = {
    # public verbs
    "run": {"target": "autopilot_harness.py", "repo_aware": True, "bootstrap": True, "public": True,
            "summary": "start or resume a goal (source intake + coverage + RALPH + drive)"},
    "inspect": {"target": "harness_status.py", "repo_aware": True, "bootstrap": True, "public": True,
                "summary": "read-only state: status by default, --doctor / --resume variants"},
    "verify": {"target": "verify_harness.py", "repo_aware": False, "bootstrap": False, "public": True,
               "summary": "self-contained package verification with a replayable evidence bundle"},
    "admin": {"target": None, "repo_aware": False, "bootstrap": False, "public": True,
              "summary": "install / parity / setup / gitignore / cleanup-legacy maintenance"},
    # expert / legacy surfaces (hidden from the default help)
    "autopilot": {"target": "autopilot_harness.py", "repo_aware": True, "bootstrap": True, "verb_hint": "run"},
    "install": {"target": "install_harness.py", "verb_hint": "admin install"},
    "parity": {"target": "parity_harness.py", "verb_hint": "admin parity"},
    "setup": {"target": "bootstrap_scaffold.py", "repo_aware": True, "verb_hint": "admin setup"},
    "doctor": {"target": "doctor_harness.py", "repo_aware": True, "bootstrap": True, "verb_hint": "inspect --doctor"},
    "status": {"target": "harness_status.py", "repo_aware": True, "bootstrap": True, "verb_hint": "inspect"},
    "resume": {"target": "resume_harness.py", "repo_aware": True, "bootstrap": True, "verb_hint": "inspect --resume"},
    "ralph": {"target": "ralph_harness.py", "repo_aware": True, "bootstrap": True},
    "drive": {"target": "ralph_driver.py", "repo_aware": True, "bootstrap": True},
    "job": {"target": "long_job_harness.py", "repo_aware": True, "bootstrap": True},
    "jobs": {"target": "long_job_harness.py", "repo_aware": True, "bootstrap": True},
    "source": {"target": "source_coverage_harness.py", "repo_aware": True, "bootstrap": True},
    "coverage": {"target": "source_coverage_harness.py", "repo_aware": True, "bootstrap": True},
    "ops": {"target": "ralph_ops.py", "repo_aware": True},
    "prd": {"target": "prd_projection_harness.py", "repo_aware": True, "bootstrap": True},
    "fleet": {"target": "fleet_harness.py", "repo_aware": True, "bootstrap": True},
    "gitignore": {"target": "gitignore_contract.py", "repo_aware": True, "verb_hint": "admin gitignore"},
    "migrate": {"target": "cleanup_legacy.py", "verb_hint": "admin cleanup-legacy", "repo_aware": True},
    "cleanup-legacy": {"target": "cleanup_legacy.py", "verb_hint": "admin cleanup-legacy", "repo_aware": True},
    "manifest": {"target": "managed_manifest.py", "verb_hint": "admin manifest"},
}

ADMIN_SUBCOMMANDS = {
    "install": "install_harness.py",
    "manifest": "managed_manifest.py",
    "parity": "parity_harness.py",
    "setup": "bootstrap_scaffold.py",
    "gitignore": "gitignore_contract.py",
    "cleanup-legacy": "cleanup_legacy.py",
}

SCRIPT_MAP = {
    name: spec["target"] for name, spec in COMMAND_REGISTRY.items() if spec.get("target")
}
REPO_AWARE_COMMANDS = {
    name for name, spec in COMMAND_REGISTRY.items() if spec.get("repo_aware")
}
AUTO_BOOTSTRAP_COMMANDS = {
    name for name, spec in COMMAND_REGISTRY.items() if spec.get("bootstrap")
}


def _resolve_dispatch(command: str, rest: list[str]) -> tuple[str, str, list[str], list[str]]:
    """Pure dispatch resolution: (effective_command, target_script, args, notices).

    The equivalence contract (R30) lives here: a legacy name resolves to the
    same target and forwarded argv as its verb form, plus a stderr notice."""

    notices: list[str] = []
    if command == "admin":
        if not rest or rest[0] in ("-h", "--help"):
            return "admin", "", [], []
        sub = rest[0]
        if sub == "setup" and len(rest) >= 2:
            return "setup", ADMIN_SUBCOMMANDS["setup"], rest[1:], []
        if sub in ADMIN_SUBCOMMANDS:
            return (sub if sub != "install" else "install"), ADMIN_SUBCOMMANDS[sub], rest[1:], []
        raise SystemExit(f"unknown admin subcommand {sub!r}; choose from {sorted(ADMIN_SUBCOMMANDS)}")
    if command == "inspect":
        forwarded = list(rest)
        scannable = _scannable_tokens(forwarded)
        target = "harness_status.py"
        effective = "status"
        if "--doctor" in scannable and "--resume" in scannable:
            raise SystemExit("inspect accepts at most one of --doctor / --resume")
        if "--doctor" in scannable:
            forwarded.remove("--doctor")
            target, effective = "doctor_harness.py", "doctor"
        elif "--resume" in scannable:
            forwarded.remove("--resume")
            target, effective = "resume_harness.py", "resume"
        return effective, target, forwarded, []
    spec = COMMAND_REGISTRY.get(command)
    if spec is None:
        import difflib

        close = difflib.get_close_matches(command, list(COMMAND_REGISTRY), n=2, cutoff=0.5)
        hint = f" — did you mean {' or '.join(close)}?" if close else ""
        raise SystemExit(f"unknown command {command!r}{hint} (rah --help for the standard verbs, --help-all for everything)")
    if not spec.get("public"):
        hint = spec.get("verb_hint")
        if hint:
            notices.append(f"[rah] '{command}' is a legacy alias; standard path: rah {hint} (see --help-all)")
        else:
            notices.append(f"[rah] '{command}' is an expert surface; standard verbs are {', '.join(PUBLIC_VERBS)} (see --help-all)")
    return command, spec["target"], list(rest), notices


RUN_CURATED_HELP = """usage: rah run <repo-root> [--goal "<objective>"] [options]

Start a new goal or resume the active one. The harness infers source intake,
coverage, RALPH setup, review contract, and drive.

common options (full list: rah run --help-all):
  --goal TEXT            objective to pursue until done or blocked
  --source PATH          source document driving coverage (md/txt/pdf)
  --source-mode MODE     implementation|analysis|paper|summary|synthesis|writing
  --resume-current-goal  continue the retained goal instead of starting new
  --no-drive             set up everything but skip the external driver
  --dry-run              plan only; change nothing
  --json                 machine-readable output
"""

INSPECT_CURATED_HELP = """usage: rah inspect <repo-root> [--doctor | --resume] [--json]

Read-only state. Default: stage/gates/blockers status. --doctor runs the
health verification; --resume emits the shortest trustworthy restart packet.
"""

ADMIN_CURATED_HELP = """usage: rah admin <subcommand> ...

subcommands:
  install         deploy/update the skill package (dual-host transaction)
  parity          canonical/mirror manifest parity; --sync to heal
  setup <repo>    initialize the .rah scaffold explicitly
  gitignore ...   managed .gitignore contract
  cleanup-legacy  quarantine-report legacy layouts (explicit purge only)
  manifest        regenerate package-manifest.json after intentional edits
"""


def _top_help(show_all: bool) -> str:
    lines = ["usage: rah <command> [args]", "", "standard verbs:"]
    for verb in PUBLIC_VERBS:
        lines.append(f"  {verb:<10} {COMMAND_REGISTRY[verb]['summary']}")
    lines.append("")
    lines.append("rah <verb> --help shows the curated path; rah --help-all lists every surface.")
    if show_all:
        lines.append("")
        lines.append("expert / legacy surfaces (byte-identical dispatch, hidden by default):")
        for name in sorted(COMMAND_REGISTRY):
            spec = COMMAND_REGISTRY[name]
            if spec.get("public"):
                continue
            hint = spec.get("verb_hint")
            lines.append(f"  {name:<16} -> {spec['target']}" + (f"  (standard: rah {hint})" if hint else ""))
    return "\n".join(lines) + "\n"


REPO_HELPER_SYNC_LOCK_TIMEOUT_SECONDS = 10.0
REPO_HELPER_SYNC_LOCK_POLL_SECONDS = 0.05


def _repo_root_from_args(args: list[str]) -> Path | None:
    if not args:
        return None
    first = args[0]
    if first == "--" or first.startswith("-"):
        return None
    return Path(first).expanduser().resolve()


def _scannable_tokens(args: list[str]) -> list[str]:
    """Tokens the facade may interpret: everything before a literal `--`.

    Anything after `--` is downstream payload byte-for-byte (reviewer
    finding: help/doctor scans used to consume literals past `--`)."""

    if "--" in args:
        return args[: args.index("--")]
    return args


def _is_help_request(args: list[str]) -> bool:
    return any(token in {"-h", "--help"} for token in _scannable_tokens(args))


def _repo_local_rah(repo_root: Path) -> Path:
    return repo_root / ".rah" / "helpers" / SKILL_DIR_NAME / "automation" / "rah.py"


def _legacy_repo_skill_root(repo_root: Path) -> Path:
    return repo_root / ".agents" / "skills" / SKILL_DIR_NAME


def _legacy_repo_runtime_helper_root(repo_root: Path) -> Path:
    return repo_root / ".rah" / "runtime" / SKILL_DIR_NAME


def _is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError:
        return False
    file_attrs = getattr(path_stat, "st_file_attributes", 0)
    return bool(file_attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _stat_is_reparse(path_stat: os.stat_result) -> bool:
    file_attrs = getattr(path_stat, "st_file_attributes", 0)
    return bool(file_attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _plain_file_stat(path: Path) -> os.stat_result | None:
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISREG(path_stat.st_mode) or _stat_is_reparse(path_stat):
        return None
    return path_stat


def _is_plain_directory(path: Path) -> bool:
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(path_stat.st_mode) and not _stat_is_reparse(path_stat)


def _same_open_file(path_stat: os.stat_result, open_stat: os.stat_result) -> bool:
    return (
        stat.S_ISREG(open_stat.st_mode)
        and not _stat_is_reparse(open_stat)
        and path_stat.st_dev == open_stat.st_dev
        and path_stat.st_ino == open_stat.st_ino
    )


def _sha256_plain_file(path: Path) -> str | None:
    before = _plain_file_stat(path)
    if before is None:
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            opened_before = os.fstat(stream.fileno())
            if not _same_open_file(before, opened_before):
                return None
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            opened_after = os.fstat(stream.fileno())
        after = _plain_file_stat(path)
    except OSError:
        return None
    if after is None or not _same_open_file(after, opened_after):
        return None
    # Windows path stat and descriptor fstat expose different st_ctime meanings,
    # so identity + size + nanosecond mtime is the portable stability check.
    before_signature = (before.st_size, before.st_mtime_ns)
    opened_after_signature = (opened_after.st_size, opened_after.st_mtime_ns)
    after_signature = (after.st_size, after.st_mtime_ns)
    if before_signature != opened_after_signature or before_signature != after_signature:
        return None
    return digest.hexdigest()


def _repo_helper_tree_matches(script_dir: Path, target_automation: Path) -> bool:
    """Return true only for an exact, flat, plain-file Python helper copy."""
    if not _is_plain_directory(script_dir) or not _is_plain_directory(target_automation):
        return False
    try:
        source_files: dict[str, Path] = {}
        with os.scandir(script_dir) as entries:
            for entry in entries:
                if not entry.name.endswith(".py"):
                    continue
                path = Path(entry.path)
                if _plain_file_stat(path) is None:
                    return False
                source_files[entry.name] = path

        target_files: dict[str, Path] = {}
        with os.scandir(target_automation) as entries:
            for entry in entries:
                path = Path(entry.path)
                if not entry.name.endswith(".py") or _plain_file_stat(path) is None:
                    return False
                target_files[entry.name] = path
    except OSError:
        return False

    if not source_files or source_files.keys() != target_files.keys():
        return False
    for name, source_path in source_files.items():
        source_hash = _sha256_plain_file(source_path)
        target_hash = _sha256_plain_file(target_files[name])
        if source_hash is None or target_hash is None or source_hash != target_hash:
            return False
    return True


def _repo_helper_lock_path(repo_root: Path) -> Path:
    helper_root = repo_root / ".rah" / "helpers"
    for directory in (repo_root / ".rah", helper_root):
        try:
            directory.mkdir(exist_ok=True)
        except FileExistsError:
            pass
        if not _is_plain_directory(directory):
            raise OSError(f"Repo helper lock ancestry is not a plain directory: {directory}")
    return helper_root / f".{SKILL_DIR_NAME}.sync.lock"


def _acquire_os_byte_lock(file_descriptor: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.lseek(file_descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for repo helper sync lock") from exc
            time.sleep(REPO_HELPER_SYNC_LOCK_POLL_SECONDS)


def _release_os_byte_lock(file_descriptor: int) -> None:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file_descriptor, fcntl.LOCK_UN)


@contextmanager
def _repo_helper_sync_lock(repo_root: Path) -> Iterator[None]:
    lock_path = _repo_helper_lock_path(repo_root)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_descriptor = os.open(lock_path, flags, 0o600)
    acquired = False
    try:
        path_stat = _plain_file_stat(lock_path)
        open_stat = os.fstat(file_descriptor)
        if path_stat is None or not _same_open_file(path_stat, open_stat):
            raise OSError(f"Repo helper sync lock is not a plain file: {lock_path}")
        _acquire_os_byte_lock(file_descriptor, REPO_HELPER_SYNC_LOCK_TIMEOUT_SECONDS)
        acquired = True
        # Keep the sentinel stable and empty: no truncate/write/unlink occurs before or
        # after acquisition, so contenders always lock the same persistent inode.
        yield
    finally:
        if acquired:
            try:
                _release_os_byte_lock(file_descriptor)
            finally:
                os.close(file_descriptor)
        else:
            os.close(file_descriptor)


def _project_name_from_args(args: list[str], repo_root: Path) -> str:
    for idx, token in enumerate(args):
        if token == "--project-name" and idx + 1 < len(args):
            return args[idx + 1]
        if token.startswith("--project-name="):
            return token.split("=", 1)[1]
    return repo_root.name


def _needs_bootstrap(repo_root: Path) -> bool:
    required = [
        repo_root / ".rah" / "state" / "status.json",
        repo_root / ".rah" / "state" / "gates.json",
        repo_root / "docs" / "architecture" / "Phytoritas.md",
    ]
    return any(not path.exists() for path in required)


def _auto_bootstrap_if_missing(command: str, args: list[str], repo_root: Path, automation_dir: Path) -> None:
    if command not in AUTO_BOOTSTRAP_COMMANDS:
        return
    if not _needs_bootstrap(repo_root):
        return

    bootstrap_script = automation_dir / SCRIPT_MAP["setup"]
    bootstrap_cmd = [
        sys.executable,
        "-B",
        str(bootstrap_script),
        str(repo_root),
        "--project-name",
        _project_name_from_args(args, repo_root),
    ]
    print(
        json.dumps(
            {
                "action": "auto_bootstrap_missing_harness",
                "repo_root": str(repo_root),
                "command": command,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    completed = subprocess.run(
        bootstrap_cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        error_payload = {
            "error": "Auto bootstrap failed",
            "repo_root": str(repo_root),
            "command": command,
            "returncode": int(completed.returncode),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        print(json.dumps(error_payload, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(int(completed.returncode))


def _quarantine_tree(repo_root: Path, target: Path, reason: str) -> Path | None:
    """Move a legacy tree into .rah/archive/legacy instead of deleting it (R25).

    Automatic cleanup paths must never destroy data they do not own: the
    marker heuristic proves the tree LOOKS like ours, not that every file in
    it is. The whole tree is renamed into a timestamped quarantine with a
    per-file inventory (path/bytes/sha256) so anything can be restored;
    permanent purge stays a deliberate operator action (cleanup-legacy)."""

    import hashlib as _hashlib
    import secrets as _secrets
    from datetime import datetime as _datetime, timezone as _timezone

    stamp = _datetime.now(_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine_root = repo_root / ".rah" / "archive" / "legacy" / f"{stamp}-{_secrets.token_hex(4)}"
    dest = quarantine_root / target.name
    inventory = []
    try:
        for path in sorted(target.rglob("*")):
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                inventory.append(
                    {
                        "path": path.relative_to(target).as_posix(),
                        "bytes": len(data),
                        "sha256": _hashlib.sha256(data).hexdigest(),
                    }
                )
        quarantine_root.mkdir(parents=True, exist_ok=True)
        try:
            target.rename(dest)
        except OSError:
            # Copy fallback verifies every byte against the pre-collected
            # inventory BEFORE the original is deleted (reviewer finding: an
            # unverified copytree+rmtree could destroy the only copy).
            shutil.copytree(target, dest, symlinks=True)
            for item in inventory:
                copied = dest / item["path"]
                data = copied.read_bytes()
                if len(data) != item["bytes"] or _hashlib.sha256(data).hexdigest() != item["sha256"]:
                    shutil.rmtree(dest, ignore_errors=True)
                    raise OSError(
                        errno.EIO, f"quarantine copy verification failed at {item['path']}; original left in place"
                    )
            shutil.rmtree(target)
        (quarantine_root / "inventory.json").write_text(
            json.dumps(
                {
                    "schema": "rah-legacy-quarantine/v1",
                    "original_path": str(target),
                    "reason": reason,
                    "quarantined_at_utc": stamp,
                    "file_count": len(inventory),
                    "files": inventory,
                    "restore": f"move {dest} back to {target}",
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        return dest
    except OSError as exc:
        print(
            json.dumps(
                {"action": "legacy_quarantine_failed", "target": str(target), "error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return None


def _report_legacy_trees(repo_root: Path) -> None:
    """Read-only legacy detection: name the heal command, touch nothing."""

    detected = []
    legacy_helper = _legacy_repo_runtime_helper_root(repo_root)
    if legacy_helper.exists():
        detected.append(str(legacy_helper))
    legacy_skill = _legacy_repo_skill_root(repo_root)
    if legacy_skill.exists():
        detected.append(str(legacy_skill))
    if detected:
        print(
            json.dumps(
                {
                    "action": "legacy_trees_detected",
                    "targets": detected,
                    "heal": "run a state-mutating surface (e.g. `rah.py cleanup-legacy <repo-root>`) to quarantine them",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )


def _cleanup_legacy_repo_runtime_helper(repo_root: Path) -> None:
    legacy_root = _legacy_repo_runtime_helper_root(repo_root)
    if not legacy_root.exists():
        return
    if legacy_root.is_symlink() or _is_reparse_point(legacy_root) or not legacy_root.is_dir():
        print(
            json.dumps(
                {
                    "action": "legacy_runtime_helper_cleanup_skipped",
                    "reason": "not-a-plain-directory",
                    "target": str(legacy_root),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return

    try:
        quarantined = _quarantine_tree(repo_root, legacy_root, "legacy runtime helper layout")
        print(
            json.dumps(
                {
                    "action": "legacy_runtime_helper_quarantined",
                    "target": str(legacy_root),
                    "quarantine": str(quarantined) if quarantined else None,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return
    except OSError as exc:
        print(
            json.dumps(
                {
                    "action": "legacy_runtime_helper_remove_failed",
                    "target": str(legacy_root),
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    removed_files: list[str] = []
    removed_dirs: list[str] = []
    failed_paths: list[str] = []
    for path in sorted(legacy_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            path.unlink()
            removed_files.append(str(path))
        except OSError as exc:
            failed_paths.append(f"{path}: {exc}")

    for path in sorted(
        (candidate for candidate in legacy_root.rglob("*") if candidate.is_dir()),
        key=lambda candidate: len(candidate.relative_to(legacy_root).parts),
        reverse=True,
    ):
        if not path.is_dir():
            continue
        try:
            path.rmdir()
            removed_dirs.append(str(path))
        except OSError:
            continue

    try:
        legacy_root.rmdir()
        removed_dirs.append(str(legacy_root))
    except OSError:
        pass

    payload = {
        "action": "legacy_runtime_helper_pruned",
        "target": str(legacy_root),
        "removed_file_count": len(removed_files),
        "removed_dir_count": len(removed_dirs),
        "failed_path_count": len(failed_paths),
    }
    if failed_paths:
        payload["failed_paths"] = failed_paths[:10]
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def _cleanup_legacy_repo_skill(repo_root: Path) -> None:
    legacy_root = _legacy_repo_skill_root(repo_root)
    if not legacy_root.exists():
        return
    if legacy_root.is_symlink() or _is_reparse_point(legacy_root) or not legacy_root.is_dir():
        print(
            json.dumps(
                {
                    "action": "legacy_repo_skill_cleanup_skipped",
                    "reason": "not-a-plain-directory",
                    "target": str(legacy_root),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return
    marker_files = [legacy_root / "SKILL.md", legacy_root / "automation" / "rah.py"]
    if not all(path.exists() for path in marker_files):
        print(
            json.dumps(
                {
                    "action": "legacy_repo_skill_cleanup_skipped",
                    "reason": "missing-expected-markers",
                    "target": str(legacy_root),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return
    skill_md = legacy_root / "SKILL.md"
    disabled_skill_md = legacy_root / "SKILL.disabled.md"
    if skill_md.exists() and not disabled_skill_md.exists():
        try:
            skill_md.replace(disabled_skill_md)
            print(
                json.dumps(
                    {
                        "action": "legacy_repo_skill_disabled",
                        "target": str(skill_md),
                        "replacement": str(disabled_skill_md),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
        except OSError as exc:
            print(
                json.dumps(
                    {
                        "action": "legacy_repo_skill_disable_failed",
                        "target": str(skill_md),
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )

    try:
        quarantined = _quarantine_tree(repo_root, legacy_root, "legacy nested skill copy")
        print(
            json.dumps(
                {
                    "action": "legacy_repo_skill_quarantined",
                    "target": str(legacy_root),
                    "quarantine": str(quarantined) if quarantined else None,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    except OSError as exc:
        print(
            json.dumps(
                {
                    "action": "legacy_repo_skill_remove_failed",
                    "target": str(legacy_root),
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )


def _ensure_repo_local_sync(command: str, args: list[str], script_dir: Path) -> Path | None:
    if command not in REPO_AWARE_COMMANDS:
        return None

    repo_root = _repo_root_from_args(args)
    if repo_root is None:
        return None

    repo_local_rah = _repo_local_rah(repo_root)
    current_script = Path(__file__).resolve()
    if repo_local_rah.exists() and repo_local_rah.resolve() == current_script:
        return repo_local_rah

    install_script = script_dir / SCRIPT_MAP["install"]
    install_cmd = [
        sys.executable,
        "-B",
        str(install_script),
        "--scope",
        "repo",
        "--repo-root",
        str(repo_root),
        "--force",
    ]
    try:
        with _repo_helper_sync_lock(repo_root):
            target_automation = repo_local_rah.parent
            if _repo_helper_tree_matches(script_dir, target_automation):
                return repo_local_rah

            print(
                json.dumps(
                    {
                        "action": "ensure_repo_local_sync",
                        "repo_root": str(repo_root),
                        "target": str(repo_local_rah),
                        "mode": "force-refresh",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            completed = subprocess.run(
                install_cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                print(
                    json.dumps(
                        {
                            "error": "Repo-local helper sync failed",
                            "repo_root": str(repo_root),
                            "target": str(repo_local_rah),
                            "returncode": int(completed.returncode),
                            "stdout": completed.stdout,
                            "stderr": completed.stderr,
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                raise SystemExit(int(completed.returncode))
            if not _repo_helper_tree_matches(script_dir, target_automation):
                print(
                    json.dumps(
                        {
                            "error": "Repo-local helper tree still mismatched after install",
                            "repo_root": str(repo_root),
                            "target": str(target_automation),
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                raise SystemExit(2)
    except (OSError, TimeoutError) as exc:
        print(
            json.dumps(
                {
                    "error": "Repo-local helper sync lock failed",
                    "repo_root": str(repo_root),
                    "target": str(repo_local_rah),
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    return repo_local_rah


# "manifest" is the designated heal path and must stay reachable from a
# drifted package (bootstrap exemption alongside the read-only surfaces).
PACKAGE_CONTRACT_READONLY_COMMANDS = {"status", "resume", "doctor", "parity", "verify", "install", "manifest"}


def _package_contract_gate(command: str, script_dir: Path) -> None:
    """Refuse MUTATING dispatch from a package that drifted from its manifest (R24).

    Applies only where a checked-in package-manifest.json exists (installed
    skill packages); repo-local helper trees carry no manifest and are
    already exact-hash verified by _repo_helper_tree_matches on every call.

    Every mutating dispatch pays a full tree hash (~tens of ms for the 53
    managed files). The earlier persistent TTL cache is gone: reviewers
    reproduced both a post-check tamper admitted for the cache lifetime and
    a cache forged from scratch — a positive cache the gate cannot
    authenticate is not a cache, it is a bypass."""

    if command in PACKAGE_CONTRACT_READONLY_COMMANDS:
        return
    package_root = script_dir.parent
    manifest_path = package_root / "package-manifest.json"
    if not manifest_path.is_file():
        # Fail closed (reviewer finding): an installed package whose manifest
        # was deleted is maximal drift, not a pass. Repo-local helper trees
        # (.rah/helpers/<skill>/automation, exact-hash verified per call and
        # manifest-less by design) stay exempt.
        if package_root.parent.name == "helpers" and package_root.parent.parent.name == ".rah":
            return
        print(
            json.dumps(
                {
                    "error": "package-manifest.json missing from the active package; refusing state-mutating dispatch",
                    "package_root": str(package_root),
                    "heal": "run `rah.py admin manifest` from a trusted checkout or reinstall the package",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
    # Pro round-2 kill-test: a forged sourceless managed_manifest.pyc with
    # the real .py deleted imports SUCCESSFULLY (no ImportError) and would
    # self-report a clean tree. Refuse BEFORE importing anything: the source
    # verifier must exist as a plain file and no stray bytecode may sit
    # beside the automation sources.
    verifier_py = script_dir / "managed_manifest.py"
    stray_bytecode = sorted(p.name for p in script_dir.glob("*.pyc"))
    if not verifier_py.is_file() or verifier_py.is_symlink() or stray_bytecode:
        print(
            json.dumps(
                {
                    "error": "verifier integrity refused before import; refusing state-mutating dispatch",
                    "package_root": str(package_root),
                    "managed_manifest_py_present": verifier_py.is_file() and not verifier_py.is_symlink(),
                    "stray_bytecode": stray_bytecode,
                    "heal": "restore automation/managed_manifest.py from a trusted checkout and delete stray .pyc files",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        import managed_manifest as _managed_manifest
    except ImportError as exc:
        # Fail closed (reviewer finding): deleting the verifier module is
        # itself drift and must not disable the gate.
        print(
            json.dumps(
                {
                    "error": "managed_manifest verifier unavailable; refusing state-mutating dispatch",
                    "package_root": str(package_root),
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        report = _managed_manifest.verify_tree(package_root)
    except _managed_manifest.ManifestError as exc:
        print(
            json.dumps(
                {
                    "error": "active package failed its manifest contract",
                    "package_root": str(package_root),
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not report["in_contract"]:
        print(
            json.dumps(
                {
                    "error": "active package drifted from package-manifest.json; refusing state-mutating dispatch",
                    "package_root": str(package_root),
                    "findings": report["findings"],
                    "heal": "regenerate the manifest after intentional edits, or run parity --sync for a drifted mirror",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(_top_help(show_all=False))
        return 0
    if argv[0] == "--help-all":
        print(_top_help(show_all=True))
        return 0
    try:
        effective, target_script, forwarded, notices = _resolve_dispatch(argv[0], argv[1:])
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for notice in notices:
        print(notice, file=sys.stderr)
    if argv[0] == "admin" and not target_script:
        print(ADMIN_CURATED_HELP)
        return 0
    scannable = _scannable_tokens(forwarded)
    if argv[0] == "run" and any(flag in scannable for flag in ("-h", "--help")) and "--help-all" not in scannable:
        print(RUN_CURATED_HELP)
        return 0
    if argv[0] == "inspect" and any(flag in scannable for flag in ("-h", "--help")):
        print(INSPECT_CURATED_HELP)
        return 0
    if "--help-all" in scannable:
        # In-place substitution before the literal `--` only: token order and
        # `--` semantics are preserved for the downstream parser.
        boundary = forwarded.index("--") if "--" in forwarded else len(forwarded)
        forwarded = [
            ("--help" if index < boundary and token == "--help-all" else token)
            for index, token in enumerate(forwarded)
        ]

    class _NS:
        pass

    ns = _NS()
    ns.command = effective
    ns.args = forwarded

    script_dir = Path(__file__).resolve().parent
    if _is_help_request(ns.args):
        target = script_dir / SCRIPT_MAP[ns.command]
        cmd = [sys.executable, "-B", str(target), *ns.args]
        completed = subprocess.run(cmd, check=False)
        return int(completed.returncode)

    _package_contract_gate(ns.command, script_dir)
    repo_local_rah = _ensure_repo_local_sync(ns.command, ns.args, script_dir)
    if repo_local_rah is not None:
        repo_root = _repo_root_from_args(ns.args) or Path.cwd()
        _auto_bootstrap_if_missing(ns.command, ns.args, repo_root, repo_local_rah.parent)
        if ns.command in PACKAGE_CONTRACT_READONLY_COMMANDS:
            # Read-only surfaces report legacy trees; they never move them
            # (reviewer finding: `status` used to quarantine — a mutation —
            # while being package-gate exempt as "read-only").
            _report_legacy_trees(repo_root)
        else:
            _cleanup_legacy_repo_runtime_helper(repo_root)
            _cleanup_legacy_repo_skill(repo_root)
        target = repo_local_rah.parent / SCRIPT_MAP[ns.command]
        cmd = [sys.executable, "-B", str(target), *ns.args]
        completed = subprocess.run(cmd, check=False)
        return int(completed.returncode)

    target = script_dir / SCRIPT_MAP[ns.command]
    cmd = [sys.executable, "-B", str(target), *ns.args]
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
