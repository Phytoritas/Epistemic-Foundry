#!/usr/bin/env python3
"""Canonical/mirror package parity by exact manifest (R22/R23).

Glob-based partial tracking is gone: both trees are judged against the
canonical package's checked-in ``package-manifest.json`` (closed set —
agents/, bin/, templates, nested test fixtures included; extras are drift;
symlinks/junctions refuse before hashing). The canonical tree drifting from
its OWN manifest is itself a reported failure, never silently re-blessed.

``--sync`` heals the mirror FROM canonical only, as a staging transaction:
build a complete staging tree, verify it against the manifest, swap the
current mirror aside as a timestamped backup (extras preserved inside it),
activate staging, re-verify, and swap back on any failure — the active
mirror path only ever holds a complete old tree or a complete new tree.

Exit codes: 0 parity (or verified sync), 1 drift reported, 2 structural
error (missing/stale manifest, same or nested roots, sync failure).
"""

from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import managed_manifest

SKILL_DIR_NAME = "recursive-architecture-refactoring-auto"


def default_codex_root() -> Path:
    return Path.home() / ".codex" / "skills" / SKILL_DIR_NAME


def default_claude_root() -> Path:
    return Path.home() / ".claude" / "skills" / SKILL_DIR_NAME


def _roots_sane(codex_root: Path, claude_root: Path) -> str | None:
    codex_resolved = codex_root.resolve()
    claude_resolved = claude_root.resolve()
    if codex_resolved == claude_resolved:
        return "canonical and mirror roots are the same directory"
    for parent, child in ((codex_resolved, claude_resolved), (claude_resolved, codex_resolved)):
        try:
            child.relative_to(parent)
            return "canonical and mirror roots are nested"
        except ValueError:
            continue
    return None


def compare_packages(codex_root: Path, claude_root: Path) -> dict[str, object]:
    manifest = managed_manifest.load_manifest(codex_root)
    if not manifest.get("files"):
        raise managed_manifest.ManifestError("canonical manifest is empty — refusing vacuous parity")
    canonical = managed_manifest.verify_tree(codex_root, manifest)
    mirror = managed_manifest.verify_tree(claude_root, manifest)
    mirror_manifest = claude_root / managed_manifest.MANIFEST_NAME
    manifest_equal = (
        mirror_manifest.is_file()
        and (codex_root / managed_manifest.MANIFEST_NAME).read_bytes() == mirror_manifest.read_bytes()
    )
    in_parity = canonical["in_contract"] and mirror["in_contract"] and manifest_equal
    return {
        "codex_root": str(codex_root),
        "claude_root": str(claude_root),
        "manifest_file_count": len(manifest.get("files", [])),
        "manifest_root_digest": managed_manifest.manifest_root_digest(manifest),
        "canonical_in_contract": canonical["in_contract"],
        "canonical_findings": canonical["findings"],
        "mirror_in_contract": mirror["in_contract"],
        "mirror_findings": mirror["findings"],
        "manifest_files_equal": manifest_equal,
        "in_parity": in_parity,
    }


def sync_mirror_transaction(
    codex_root: Path,
    claude_root: Path,
    backup_parent: Path,
) -> dict[str, object]:
    """Staged one-way heal (codex -> claude). Never leaves a mixed tree."""

    manifest = managed_manifest.load_manifest(codex_root)
    canonical_state = managed_manifest.verify_tree(codex_root, manifest)
    if not canonical_state["in_contract"]:
        raise managed_manifest.ManifestError(
            "canonical tree is out of contract with its own manifest — regenerate the manifest first; "
            f"findings: {json.dumps(canonical_state['findings'])[:400]}"
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    staging = claude_root.parent / f".{claude_root.name}.staging-{stamp}"
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = backup_parent / f"{claude_root.name}.backup-{stamp}"
    if staging.exists():
        shutil.rmtree(staging)

    for spec in manifest["files"]:
        src = codex_root / str(spec["path"])
        dst = staging / str(spec["path"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copy2(codex_root / managed_manifest.MANIFEST_NAME, staging / managed_manifest.MANIFEST_NAME)

    staged_state = managed_manifest.verify_tree(staging, manifest)
    if not staged_state["in_contract"]:
        shutil.rmtree(staging, ignore_errors=True)
        raise managed_manifest.ManifestError("staging tree failed manifest verification — sync aborted, mirror untouched")

    mirror_existed = claude_root.exists()
    activated = False
    try:
        if mirror_existed:
            claude_root.rename(backup)
        staging.rename(claude_root)
        activated = True
        post = managed_manifest.verify_tree(claude_root, manifest)
        if not post["in_contract"]:
            raise managed_manifest.ManifestError("post-activation verification failed")
    except (OSError, managed_manifest.ManifestError) as exc:
        # restore: whatever state we are in, put the old tree back whole
        try:
            if activated and claude_root.exists():
                shutil.rmtree(claude_root, ignore_errors=True)
            if mirror_existed and backup.exists():
                backup.rename(claude_root)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        raise managed_manifest.ManifestError(f"sync transaction failed and was rolled back: {exc}")

    return {
        "backup_path": str(backup) if mirror_existed else None,
        "activated": True,
        "extras_preserved_in_backup": mirror_existed,
    }


def main() -> int:
    parser = _SuggestingArgumentParser(
        description="Compare (and optionally one-way sync) the canonical and mirror RAH skill packages by exact manifest."
    )
    parser.add_argument("--codex-root", default=None, help="Canonical package root (default ~/.codex/skills/...).")
    parser.add_argument("--claude-root", default=None, help="Mirror package root (default ~/.claude/skills/...).")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Heal the mirror from canonical (codex -> claude only) via a staged whole-tree transaction; the previous mirror (extras included) becomes a timestamped backup.",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Backup parent directory for --sync (default <claude-root parent>/../backups/rah-parity).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    codex_root = Path(args.codex_root).expanduser() if args.codex_root else default_codex_root()
    claude_root = Path(args.claude_root).expanduser() if args.claude_root else default_claude_root()
    if not codex_root.is_dir():
        print(json.dumps({"error": "canonical package root not found", "path": str(codex_root)}, ensure_ascii=False))
        return 2
    # Always checked (reviewer finding): a NOT-YET-EXISTING mirror path could
    # be pointed inside the canonical tree and pass. resolve() on Windows
    # handles missing paths, so existence is irrelevant to sanity.
    sanity = _roots_sane(codex_root, claude_root)
    if sanity:
        print(json.dumps({"error": sanity}, ensure_ascii=False))
        return 2

    try:
        if args.sync:
            report = compare_packages(codex_root, claude_root) if claude_root.is_dir() else {"in_parity": False}
            if report.get("in_parity"):
                print(json.dumps({**report, "sync": "not-needed"}, ensure_ascii=False, indent=1))
                return 0
            backup_parent = (
                Path(args.backup_dir).expanduser()
                if args.backup_dir
                else claude_root.parent.parent / "backups" / "rah-parity"
            )
            actions = sync_mirror_transaction(codex_root, claude_root, backup_parent)
            post = compare_packages(codex_root, claude_root)
            payload = {**post, "sync_actions": actions, "post_sync_in_parity": post["in_parity"]}
            print(json.dumps(payload, ensure_ascii=False, indent=1))
            return 0 if post["in_parity"] else 2
        if not claude_root.is_dir():
            print(json.dumps({"error": "mirror package root not found", "path": str(claude_root)}, ensure_ascii=False))
            return 2
        report = compare_packages(codex_root, claude_root)
    except managed_manifest.ManifestError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=1))
    if report["in_parity"]:
        return 0
    print(
        "drift detected; heal with: python <active-skill-root>/automation/rah.py parity --sync",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
