#!/usr/bin/env python3
"""Advisory inter-process lock for .rah state-writing surfaces (R17).

Parallel state-writing invocations raced on evidence_ledger/loop_state
writes and dropped entries; a repo-level lock file serializes them via the
atomic ``O_CREAT|O_EXCL`` create.

The age-only stale takeover of the first design allowed two proven races
(Pro repro): a LIVE long holder could be dispossessed by mtime alone, and a
late ``release`` from a dispossessed owner could delete the NEW holder's
lock (ABA), letting a third writer in concurrently. This version closes
both:

- the lock file carries a random ``owner_token`` and the holder pid;
- takeover requires BOTH a stale mtime AND a dead holder pid, and runs
  under an OS byte-lock guard with an identity re-check before unlink;
- ``release_state_lock`` unlinks only while the file still carries the
  caller's token.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 120.0
STALE_LOCK_SECONDS = 900.0
POLL_SECONDS = 0.2

if os.name == "nt":
    import msvcrt
else:
    import fcntl


@dataclass(frozen=True)
class StateLockHandle:
    path: Path
    token: str

    def __fspath__(self) -> str:  # pragma: no cover - convenience
        return str(self.path)


def _lock_path(repo_root: Path, name: str) -> Path:
    return repo_root / ".rah" / "state" / f"{name}.lock"


def _guard_path(lock_path: Path) -> Path:
    return lock_path.with_name(lock_path.name + ".guard")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class _ByteLockGuard:
    """1-byte OS lock serializing stale-takeover and release identity checks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> bool:
        try:
            self.handle = open(self.path, "a+b")
            if os.name == "nt":
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            return True
        except OSError:
            if self.handle is not None:
                try:
                    self.handle.close()
                except OSError:
                    pass
                self.handle = None
            return False

    def __exit__(self, *exc_info: object) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self.handle.close()
        except OSError:
            pass


def _read_lock_payload(lock_path: Path) -> dict | None:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _try_stale_takeover(lock_path: Path, stale_seconds: float) -> bool:
    """Remove a dead holder's stale lock; True when the caller may retry."""

    try:
        probe = lock_path.stat()
    except OSError:
        return True  # already gone
    age = time.time() - probe.st_mtime
    if age <= stale_seconds:
        return False
    payload = _read_lock_payload(lock_path)
    holder_pid = int(payload.get("pid") or 0) if payload else 0
    if _pid_alive(holder_pid):
        # A live holder is never dispossessed by age alone; operators see the
        # timeout message instead.
        return False
    holder_token = str(payload.get("owner_token") or "") if payload else ""
    with _ByteLockGuard(_guard_path(lock_path)) as guarded:
        if not guarded:
            return False
        try:
            recheck = lock_path.stat()
        except OSError:
            return True
        current = _read_lock_payload(lock_path)
        current_token = str(current.get("owner_token") or "") if current else ""
        if recheck.st_mtime_ns != probe.st_mtime_ns or current_token != holder_token:
            # someone else replaced the lock between our observation and the
            # guard — never unlink an identity we did not verify
            return False
        try:
            lock_path.unlink()
        except OSError:
            return False
    return True


def acquire_state_lock(
    repo_root: Path,
    name: str = "ralph_state",
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    stale_seconds: float = STALE_LOCK_SECONDS,
) -> StateLockHandle:
    """Acquire the named repo-level state lock, waiting up to timeout_seconds.

    Returns a StateLockHandle (pass it to release_state_lock). Raises
    SystemExit on timeout so CLI surfaces fail closed with a clear message
    instead of silently racing.
    """
    lock_path = _lock_path(repo_root, name)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _try_stale_takeover(lock_path, stale_seconds):
                continue
            if time.monotonic() >= deadline:
                holder = ""
                try:
                    holder = lock_path.read_text(encoding="utf-8", errors="replace")[:200]
                except OSError:
                    pass
                raise SystemExit(
                    f"Timed out after {timeout_seconds:.0f}s waiting for state lock {lock_path} "
                    f"(holder: {holder or 'unknown'}). Run state-writing rah.py commands sequentially; "
                    "the lock clears itself only when the holding process is gone AND the lock is stale."
                )
            time.sleep(POLL_SECONDS)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "owner_token": token,
                    "pid": os.getpid(),
                    "surface": name,
                    "acquired_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                },
                handle,
                ensure_ascii=False,
            )
        return StateLockHandle(path=lock_path, token=token)


def release_state_lock(lock: StateLockHandle | Path | str) -> None:
    """Release only a lock the caller still owns (token identity check).

    A plain path (legacy call shape) releases unconditionally ONLY when the
    lock file carries no owner_token — token-bearing locks require the
    matching handle, so a dispossessed owner can never delete a successor's
    lock."""

    if isinstance(lock, StateLockHandle):
        lock_path, token = lock.path, lock.token
    else:
        lock_path, token = Path(lock), None
    with _ByteLockGuard(_guard_path(lock_path)) as guarded:
        if not guarded:
            # Never run the identity check/unlink unserialized (reviewer
            # finding). Leaving the lock is safe: a dead holder is cleared by
            # the stale-takeover path.
            return
        payload = _read_lock_payload(lock_path)
        current_token = str(payload.get("owner_token") or "") if payload else ""
        if token is not None and current_token != token:
            # Round 2 reviewer finding: an empty/malformed successor lock
            # could be unlinked by a stale handle. A token-bearing handle
            # releases ONLY the exact lock it wrote; anything else is left
            # for stale takeover.
            return
        if token is None and current_token:
            return
        try:
            lock_path.unlink()
        except OSError:
            pass
