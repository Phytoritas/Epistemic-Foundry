#!/usr/bin/env python3
"""Generation-committed RALPH state store (R15/R16/R18).

The six authoritative state files used to be written sequentially in place;
a crash mid-sequence could leave goal=done next to loop=active with a
ledger from a third moment (Pro repro class). Here every invocation stages
the complete new state under ``generations/<seq>-<token>/`` with a hash
manifest, fsyncs, and only then flips the tiny ``current.json`` pointer via
``os.replace`` — readers always see one complete generation.

The legacy flat files remain as COMPAT SNAPSHOTS (atomic temp+replace,
stamped with ``state_generation``) written after the pointer commit; they
are views, not authority. ``verify_current`` fails closed on any mixed
state (pointer/manifest/hash/goal-id/snapshot-stamp mismatch) — recovery is
the explicit ``repair_snapshots``, never an automatic fallback to an older
generation (R16). The first commit over a legacy flat layout preserves the
original files under ``generations/pre-store-backup/`` before anything else
(R18); a failed first commit leaves the flat files untouched and
authoritative.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat as stat_module
from pathlib import Path
from typing import Any

GENERATION_FILES = (
    "goal.json",
    "loop_state.json",
    "evidence_ledger.json",
    "plan_graph.json",
    "goal_bridge.json",
    "review_gate.json",
)
CURRENT_POINTER = "current.json"
GENERATIONS_DIR = "generations"
KEEP_GENERATIONS = 3
STORE_SCHEMA = "rah-state-generation/v1"


class StateStoreError(RuntimeError):
    pass


def _refuse_link(path: Path) -> None:
    """Store paths are never links (reviewer finding: only the generation
    dir's final component used to be checked; ancestors, the pointer, the
    manifest, payload files, and flat snapshots followed links silently)."""

    if not path.exists() and not path.is_symlink():
        return
    probe = path.lstat()
    if stat_module.S_ISLNK(probe.st_mode) or (
        os.name == "nt" and getattr(probe, "st_reparse_tag", 0)
    ):
        raise StateStoreError(f"state-store path is a link/reparse point: {path}")


def _generations_root(ralph_root: Path) -> Path:
    return ralph_root / GENERATIONS_DIR


def _pointer_path(ralph_root: Path) -> Path:
    return ralph_root / CURRENT_POINTER


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


GENERATION_ID_RE = re.compile(r"^\d{6}-[0-9a-f]{8}$")


def read_pointer(ralph_root: Path) -> dict[str, Any] | None:
    path = _pointer_path(ralph_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateStoreError(f"unreadable state pointer {path}: {exc}")
    if not isinstance(payload, dict) or not payload.get("generation"):
        raise StateStoreError(f"invalid state pointer shape at {path}")
    # The pointer names a generation; it must never act as a path authority
    # (reviewer-reproduced: an absolute path here made Path-join discard the
    # generations root entirely).
    generation = str(payload.get("generation"))
    if not GENERATION_ID_RE.fullmatch(generation):
        raise StateStoreError(
            f"state pointer carries a non-generation value {generation!r} — refusing to treat it as a path"
        )
    return payload


def _numbered_generations(ralph_root: Path) -> list[str]:
    root = _generations_root(ralph_root)
    if not root.is_dir():
        return []
    return sorted(e.name for e in root.iterdir() if GENERATION_ID_RE.fullmatch(e.name))


def _next_generation_id(ralph_root: Path) -> str:
    root = _generations_root(ralph_root)
    highest = 0
    if root.is_dir():
        for entry in root.iterdir():
            name = entry.name.split("-", 1)[0]
            if name.isdigit():
                highest = max(highest, int(name))
    return f"{highest + 1:06d}-{secrets.token_hex(4)}"


def _preserve_legacy_flat(ralph_root: Path) -> None:
    backup_root = _generations_root(ralph_root) / "pre-store-backup"
    if backup_root.exists():
        return
    flats = [name for name in GENERATION_FILES if (ralph_root / name).is_file()]
    if not flats:
        return
    backup_root.mkdir(parents=True, exist_ok=True)
    for name in flats:
        (backup_root / name).write_bytes((ralph_root / name).read_bytes())


def commit_generation(ralph_root: Path, payloads: dict[str, Any]) -> str:
    """Stage a complete generation, verify it, flip the pointer, snapshot.

    Raises StateStoreError before the pointer flip on any staging problem —
    in that case the previous generation (or legacy flat files) remain the
    untouched authority."""

    missing = [name for name in GENERATION_FILES if name not in payloads]
    if missing:
        raise StateStoreError(f"incomplete generation payloads: missing {missing}")
    # Callers hand back flat snapshots, which carry the *previous* commit's
    # stamp; authoritative generation files must stay stamp-free (only the
    # flat compat views are stamped, by write_snapshots below).
    payloads = {
        name: {k: v for k, v in payload.items() if k != "state_generation"}
        if isinstance(payload, dict)
        else payload
        for name, payload in payloads.items()
    }
    goal_id = str((payloads.get("goal.json") or {}).get("goal_id") or "")
    if not goal_id:
        raise StateStoreError("generation refused: goal.json carries no goal_id")

    def _ledger_high(ledger: Any) -> int:
        if not isinstance(ledger, dict):
            return 0
        highest = 0
        entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
        for entry in entries:
            raw = str((entry or {}).get("id") or "") if isinstance(entry, dict) else ""
            if raw.startswith("E") and raw[1:].isdigit():
                highest = max(highest, int(raw[1:]))
        recorded = ledger.get("issued_id_high_water")
        if isinstance(recorded, int):
            highest = max(highest, recorded)
        return highest

    previous = read_current(ralph_root)
    if previous is not None:
        # Cross-generation monotonicity (reviewer finding: rewinding the
        # high-water mark AND the entries inside one mutable ledger was
        # undetectable from that ledger alone — the previous committed
        # generation is the anchor).
        prev_high = _ledger_high(previous[1].get("evidence_ledger.json"))
        new_high = _ledger_high(payloads.get("evidence_ledger.json"))
        if new_high < prev_high:
            raise StateStoreError(
                f"evidence-ledger high-water rewind refused: previous generation issued up to "
                f"E{prev_high:04d}, candidate tops out at E{new_high:04d}"
            )

    if read_pointer(ralph_root) is None:
        _preserve_legacy_flat(ralph_root)

    generation = _next_generation_id(ralph_root)
    gen_dir = _generations_root(ralph_root) / generation
    gen_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, str] = {}
    try:
        for name in GENERATION_FILES:
            text = _dump(payloads[name])
            _atomic_write_text(gen_dir / name, text)
            manifest[name] = _sha256_text(text)
        _atomic_write_text(
            gen_dir / "generation-manifest.json",
            _dump({"schema": STORE_SCHEMA, "generation": generation, "goal_id": goal_id, "files": manifest}),
        )
        # verify staged bytes from disk before the pointer flip
        for name in GENERATION_FILES:
            staged = (gen_dir / name).read_text(encoding="utf-8")
            if _sha256_text(staged) != manifest[name]:
                raise StateStoreError(f"staged file failed re-read verification: {name}")
    except (OSError, StateStoreError) as exc:
        import shutil

        shutil.rmtree(gen_dir, ignore_errors=True)
        raise StateStoreError(f"generation staging failed; previous state untouched: {exc}")

    _atomic_write_text(
        _pointer_path(ralph_root),
        _dump({"schema": STORE_SCHEMA, "generation": generation, "goal_id": goal_id}),
    )
    try:
        write_snapshots(ralph_root, payloads, generation)
        _prune_generations(ralph_root, keep=KEEP_GENERATIONS)
    except OSError as exc:
        # Unambiguous semantics for the post-pointer window: the generation
        # IS committed and authoritative; only the compat views are behind.
        raise StateStoreError(
            f"generation {generation} committed but snapshot refresh failed ({exc}) — "
            "state is authoritative in the store; heal views with: ralph --repair-state-snapshots"
        )
    return generation


def write_snapshots(ralph_root: Path, payloads: dict[str, Any], generation: str) -> None:
    """Non-authoritative flat compat views, atomically replaced and stamped."""

    for name in GENERATION_FILES:
        payload = payloads[name]
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["state_generation"] = generation
        _atomic_write_text(ralph_root / name, _dump(payload))


def _prune_generations(ralph_root: Path, *, keep: int) -> None:
    root = _generations_root(ralph_root)
    if not root.is_dir():
        return
    numbered = sorted(
        (entry for entry in root.iterdir() if entry.is_dir() and entry.name.split("-", 1)[0].isdigit()),
        key=lambda entry: int(entry.name.split("-", 1)[0]),
    )
    import shutil

    for entry in numbered[:-keep]:
        shutil.rmtree(entry, ignore_errors=True)


def read_current(ralph_root: Path) -> tuple[str, dict[str, Any]] | None:
    """Authoritative read: the complete pointed generation or fail-closed."""

    _refuse_link(_pointer_path(ralph_root))
    pointer = read_pointer(ralph_root)
    if pointer is None:
        # Reviewer-reproduced fail-open: deleting only current.json used to
        # demote an initialized store to trusting legacy flat files. The
        # second downgrade route (deleting/renaming generations/ entirely)
        # is blocked by the stamps the store left on its flat snapshots.
        existing = _numbered_generations(ralph_root)
        if existing:
            raise StateStoreError(
                f"state pointer missing but {len(existing)} committed generation(s) exist — "
                "refusing legacy fallback; restore current.json or recover explicitly"
            )
        for name in GENERATION_FILES:
            flat = ralph_root / name
            if not flat.is_file():
                continue
            try:
                snapshot = json.loads(flat.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(snapshot, dict) and "state_generation" in snapshot:
                raise StateStoreError(
                    f"{name} carries a state_generation stamp but the generation store is gone — "
                    "this repo ran in store mode; refusing legacy downgrade (recover the store "
                    "or deliberately strip the stamps)"
                )
        return None
    generation = str(pointer["generation"])
    generations_root = _generations_root(ralph_root)
    _refuse_link(generations_root)
    gen_dir = generations_root / generation
    _refuse_link(gen_dir)
    manifest_path = gen_dir / "generation-manifest.json"
    _refuse_link(manifest_path)
    if not manifest_path.is_file():
        raise StateStoreError(
            f"state pointer references generation {generation} but its manifest is missing — "
            "explicit recovery required (no automatic fallback to older generations)"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payloads: dict[str, Any] = {}
    for name in GENERATION_FILES:
        path = gen_dir / name
        _refuse_link(path)
        if not path.is_file():
            raise StateStoreError(f"generation {generation} is incomplete: missing {name}")
        text = path.read_text(encoding="utf-8")
        if _sha256_text(text) != (manifest.get("files") or {}).get(name):
            raise StateStoreError(f"generation {generation} failed hash verification: {name}")
        payloads[name] = json.loads(text)
    goal_id = str(manifest.get("goal_id") or "")
    actual_goal = str((payloads.get("goal.json") or {}).get("goal_id") or "")
    if goal_id != actual_goal:
        raise StateStoreError(f"generation {generation} goal_id mismatch")
    return generation, payloads


def verify_current(ralph_root: Path) -> dict[str, Any]:
    """Consumer gate (R16): pointer, generation, and snapshots must agree.

    Legacy layout (no pointer) passes untouched; any mixed state raises with
    the explicit repair hint instead of silently proceeding or falling back."""

    current = read_current(ralph_root)
    if current is None:
        return {"mode": "legacy-flat", "generation": None}
    generation, payloads = current
    stale: list[str] = []
    for name in GENERATION_FILES:
        flat = ralph_root / name
        _refuse_link(flat)
        if not flat.is_file():
            stale.append(f"{name}: snapshot missing")
            continue
        try:
            snapshot = json.loads(flat.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stale.append(f"{name}: snapshot unreadable")
            continue
        stamp = snapshot.get("state_generation") if isinstance(snapshot, dict) else None
        if stamp != generation:
            stale.append(f"{name}: snapshot generation {stamp!r} != current {generation!r}")
            continue
        # Reviewer-reproduced laundering hole: a snapshot edit that keeps the
        # stamp used to pass. The snapshot content (minus stamp) must be the
        # committed generation payload, byte-for-byte in canonical form.
        stripped = (
            {k: v for k, v in snapshot.items() if k != "state_generation"}
            if isinstance(snapshot, dict)
            else snapshot
        )
        authority = payloads.get(name)
        authority_stripped = (
            {k: v for k, v in authority.items() if k != "state_generation"}
            if isinstance(authority, dict)
            else authority
        )
        if _sha256_text(_dump(stripped)) != _sha256_text(_dump(authority_stripped)):
            stale.append(f"{name}: snapshot content diverges from committed generation")
    if stale:
        raise StateStoreError(
            "mixed state generations detected — refusing to proceed on torn state: "
            + "; ".join(stale[:6])
            + " | heal with: ralph --repair-state-snapshots"
        )
    return {"mode": "generation", "generation": generation}


def repair_snapshots(ralph_root: Path) -> dict[str, Any]:
    """Explicit recovery: regenerate flat snapshots from the committed generation."""

    current = read_current(ralph_root)
    if current is None:
        raise StateStoreError("nothing to repair: no committed generation exists")
    generation, payloads = current
    write_snapshots(ralph_root, payloads, generation)
    return {"repaired": True, "generation": generation}
