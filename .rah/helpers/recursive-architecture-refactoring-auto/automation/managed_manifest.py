#!/usr/bin/env python3
"""Closed-set package manifest primitives (R2/R22 foundation).

One authority for "which files make up this package and what bytes are
they". Replaces glob-based partial tracking: every managed file is
enumerated with kind/bytes/sha256/executable, extras are drift, and
symlinks/junctions/reparse points are refused before hashing so a tampered
tree can never route reads or writes outside the package.

The manifest file itself (`package-manifest.json` at the package root) is
excluded from its own entry list; consumers compare it between trees by
direct byte equality.
"""

from __future__ import annotations

# Path-shadowing guard (see rah.py): demote the script dir so a sourceless
# stdlib-named .pyc can never preempt the real stdlib at import time.
import os as _os
import sys as _sys

_here = _os.path.dirname(_os.path.abspath(__file__))
if _sys.path and _os.path.abspath(_sys.path[0] or _os.getcwd()) == _here:
    _sys.path.pop(0)
if _here not in _sys.path:
    _sys.path.append(_here)


import hashlib
import json
import os
import stat as stat_module
from pathlib import Path
from typing import Any

MANIFEST_NAME = "package-manifest.json"
MANIFEST_SCHEMA = "rah-package-manifest/v1"

# Closed managed set: directories enumerated recursively, top-level files
# listed explicitly. Anything on disk outside runtime caches that is not
# matched here is reported as an unmanaged extra (drift), never silently
# ignored.
MANAGED_DIRS = ("automation", "references", "templates", "tests", "agents", "bin")
MANAGED_TOP_FILES = ("SKILL.md", "contract-registry.json")
RUNTIME_CACHE_DIRS = {"__pycache__", ".pytest_cache"}
RUNTIME_CACHE_FILES = {".coverage"}


class ManifestError(RuntimeError):
    pass


def _refuse_special(path: Path, follow_stat: os.stat_result | None = None) -> None:
    probe = path.lstat()
    if stat_module.S_ISLNK(probe.st_mode):
        raise ManifestError(f"symlink refused: {path}")
    if os.name == "nt":
        reparse = getattr(probe, "st_reparse_tag", 0)
        if reparse:
            raise ManifestError(f"reparse point refused: {path}")
    if follow_stat is not None and not stat_module.S_ISREG(follow_stat.st_mode) and path.is_file():
        raise ManifestError(f"not a regular file: {path}")


def stable_file_entry(root: Path, path: Path) -> dict[str, Any]:
    """Hash one managed file, fd-pinned so the hashed bytes and the recorded
    identity come from the same open inode (a path-swap between stats can no
    longer race the hash; the lstat->open window is the documented residue)."""

    _refuse_special(path)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat_module.S_ISREG(before.st_mode):
            raise ManifestError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ManifestError(f"file changed while hashing: {path}")
    return {
        "path": path.relative_to(root).as_posix(),
        "kind": "regular-file",
        "bytes": before.st_size,
        "sha256": digest.hexdigest(),
        "executable": bool(before.st_mode & stat_module.S_IXUSR) if os.name != "nt" else False,
    }


def scan_tree(root: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    """Closed-set walk: managed files plus every closure violation.

    Reviewer-reproduced holes closed here: a stray top-level file/dir used to
    be invisible (only managed names were enumerated), and a symlinked
    subdirectory inside a managed dir was silently skipped by os.walk. Both
    are now explicit findings instead of silent gaps."""

    files: list[Path] = []
    findings: list[dict[str, Any]] = []
    allowed_top = (
        {MANIFEST_NAME}
        | set(MANAGED_TOP_FILES)
        | set(MANAGED_DIRS)
        | RUNTIME_CACHE_DIRS
        | RUNTIME_CACHE_FILES
    )
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name not in allowed_top:
            findings.append(
                {
                    "path": entry.name,
                    "error": "top-level entry outside the closed managed set",
                }
            )
            continue
        if entry.name in RUNTIME_CACHE_DIRS or entry.name in RUNTIME_CACHE_FILES:
            # Cache NAMES are allowed but a link wearing a cache name is not
            # (reviewer finding: cache entries skipped specialness checks).
            try:
                _refuse_special(entry)
            except ManifestError as exc:
                findings.append({"path": entry.name, "error": str(exc)})
    for name in MANAGED_TOP_FILES:
        candidate = root / name
        if candidate.exists():
            files.append(candidate)
    for dir_name in MANAGED_DIRS:
        base = root / dir_name
        if not base.exists():
            continue
        try:
            _refuse_special(base)
        except ManifestError as exc:
            findings.append({"path": dir_name, "error": str(exc)})
            continue
        for current, dirs, names in os.walk(base):
            kept: list[str] = []
            for d in sorted(dirs):
                try:
                    _refuse_special(Path(current) / d)
                except ManifestError as exc:
                    findings.append(
                        {
                            "path": (Path(current) / d).relative_to(root).as_posix(),
                            "error": str(exc),
                        }
                    )
                    continue
                if d in RUNTIME_CACHE_DIRS:
                    continue
                kept.append(d)
            dirs[:] = kept
            for entry in sorted(names):
                if entry in RUNTIME_CACHE_FILES:
                    continue
                if entry.endswith(".pyc"):
                    # Reviewer finding: a bare .pyc OUTSIDE __pycache__ is a
                    # sourceless-loadable module (SourcelessFileLoader) that
                    # pycache redirection cannot neutralize — it is drift,
                    # never a cache artifact.
                    findings.append(
                        {
                            "path": (Path(current) / entry).relative_to(root).as_posix(),
                            "error": "sourceless bytecode outside __pycache__ refused",
                        }
                    )
                    continue
                files.append(Path(current) / entry)
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    return files, findings


def iter_managed_files(root: Path) -> list[Path]:
    files, findings = scan_tree(root)
    if findings:
        first = findings[0]
        raise ManifestError(
            f"tree closure violation ({len(findings)}): {first['path']}: {first['error']}"
        )
    return files


def build_manifest(root: Path) -> dict[str, Any]:
    entries = [stable_file_entry(root, path) for path in iter_managed_files(root)]
    return {
        "schema": MANIFEST_SCHEMA,
        "managed_dirs": list(MANAGED_DIRS),
        "managed_top_files": list(MANAGED_TOP_FILES),
        "file_count": len(entries),
        "files": entries,
    }


def manifest_root_digest(manifest: dict[str, Any]) -> str:
    # kind/executable included (reviewer finding: two generations differing
    # only in POSIX mode used to share a digest).
    ordered = [
        (f["path"], f["bytes"], f["sha256"], f.get("kind"), bool(f.get("executable")))
        for f in manifest.get("files", [])
    ]
    canonical = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise ManifestError(f"missing {MANIFEST_NAME} at {root}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Reviewer finding: a malformed manifest escaped as a raw
        # JSONDecodeError that transaction rollback handlers did not catch.
        raise ManifestError(f"unreadable manifest at {path}: {exc}")
    if not isinstance(payload, dict) or payload.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError(f"invalid manifest schema at {path}")
    return payload


def write_manifest(root: Path) -> dict[str, Any]:
    manifest = build_manifest(root)
    path = root / MANIFEST_NAME
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)
    return manifest


def resolve_contained_file(
    repo_root: Path,
    value: str,
    *,
    allowed_subdir: str,
    must_exist: bool = True,
) -> Path:
    """Containment gate for operator-ledger paths (R21).

    Ledger JSON is data, not authority: a tampered `text_path` must not be
    able to route reads outside the repo (absolute, drive-relative, UNC,
    `..`) or through links. Returns the resolved path only when it is a
    plain regular file inside `repo_root/allowed_subdir`."""

    raw = str(value or "").strip()
    if not raw:
        raise ManifestError("empty managed path")
    if raw.startswith(("\\\\", "//")):
        raise ManifestError(f"UNC path refused: {raw}")
    if len(raw) >= 2 and raw[1] == ":":
        raise ManifestError(f"drive path refused: {raw}")
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ManifestError(f"absolute path refused: {raw}")
    if ".." in candidate.parts:
        raise ManifestError(f"parent traversal refused: {raw}")
    # Reviewer-reproduced escape: if the allowed subdir (or any ancestor on
    # the way to the target) is itself a link, resolve() legitimizes the
    # outside tree as the "allowed root". Refuse links on every component
    # below repo_root before trusting resolve().
    for chain in (Path(allowed_subdir).parts, candidate.parts):
        probe = repo_root
        for part in chain:
            probe = probe / part
            if probe.exists() or probe.is_symlink():
                try:
                    _refuse_special(probe)
                except OSError as exc:
                    raise ManifestError(f"unreadable path component: {probe}: {exc}")
    allowed_root = (repo_root / allowed_subdir).resolve()
    repo_resolved = str(repo_root.resolve())
    allowed_text_probe = str(allowed_root)
    if os.name == "nt":
        repo_resolved = repo_resolved.casefold()
        allowed_text_probe = allowed_text_probe.casefold()
    if allowed_text_probe != repo_resolved and not allowed_text_probe.startswith(
        repo_resolved + os.sep
    ):
        raise ManifestError(f"allowed root escapes the repo: {allowed_subdir}")
    target = repo_root / candidate
    resolved = target.resolve()
    resolved_text = str(resolved)
    allowed_text = str(allowed_root)
    if os.name == "nt":
        resolved_text = resolved_text.casefold()
        allowed_text = allowed_text.casefold()
    if resolved_text != allowed_text and not resolved_text.startswith(allowed_text + os.sep):
        raise ManifestError(f"path escapes managed root: {raw}")
    if target.exists():
        _refuse_special(target)
    if not must_exist and not resolved.exists():
        return resolved
    if not resolved.is_file():
        raise ManifestError(f"missing managed file: {raw}")
    _refuse_special(resolved)
    return resolved


def verify_tree(root: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare the on-disk tree against the manifest (closed-set semantics)."""

    manifest = manifest if manifest is not None else load_manifest(root)
    expected = {f["path"]: f for f in manifest.get("files", []) if isinstance(f, dict)}
    findings: dict[str, list[dict[str, Any]]] = {
        "missing": [],
        "hash_mismatch": [],
        "unmanaged_extra": [],
        "special_file": [],
    }
    scanned, closure_findings = scan_tree(root)
    for finding in closure_findings:
        target = "special_file" if "refused" in finding["error"] else "unmanaged_extra"
        findings[target].append(finding)
    actual: dict[str, dict[str, Any]] = {}
    for path in scanned:
        rel = path.relative_to(root).as_posix()
        try:
            actual[rel] = stable_file_entry(root, path)
        except ManifestError as exc:
            findings["special_file"].append({"path": rel, "error": str(exc)})
    for rel, spec in expected.items():
        entry = actual.get(rel)
        if entry is None:
            findings["missing"].append({"path": rel, "expected_sha256": spec.get("sha256")})
        elif (
            entry["sha256"] != spec.get("sha256")
            or entry["bytes"] != spec.get("bytes")
            or entry["kind"] != spec.get("kind")
            or bool(entry["executable"]) != bool(spec.get("executable"))
        ):
            findings["hash_mismatch"].append(
                {
                    "path": rel,
                    "expected_sha256": spec.get("sha256"),
                    "actual_sha256": entry["sha256"],
                    "expected_bytes": spec.get("bytes"),
                    "actual_bytes": entry["bytes"],
                    "expected_executable": bool(spec.get("executable")),
                    "actual_executable": bool(entry["executable"]),
                }
            )
    for rel in actual:
        if rel not in expected:
            findings["unmanaged_extra"].append({"path": rel})
    in_contract = not any(findings.values())
    return {
        "root": str(root),
        "schema": MANIFEST_SCHEMA,
        "expected_count": len(expected),
        "actual_count": len(actual),
        "in_contract": in_contract,
        "findings": findings,
        "root_digest": manifest_root_digest(manifest),
    }


def main() -> int:
    import argparse
    import sys
    import tempfile

    # Bytecode caches inside the package are outside the manifest; redirect
    # this process's pycache so a poisoned in-tree .pyc is never loaded.
    if not sys.pycache_prefix:
        sys.pycache_prefix = os.path.join(tempfile.gettempdir(), "rah-pyc")
        os.environ.setdefault("PYTHONPYCACHEPREFIX", sys.pycache_prefix)

    parser = argparse.ArgumentParser(description="Regenerate or verify the closed package manifest.")
    parser.add_argument("--verify-only", action="store_true", help="Verify the tree against the existing manifest without rewriting it.")
    parser.add_argument("--root", default=None, help="Package root (default: this package).")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve() if args.root else Path(__file__).resolve().parent.parent
    if args.verify_only:
        report = verify_tree(root)
        print(json.dumps({k: v for k, v in report.items() if k != "root_digest"} | {"root_digest": report["root_digest"]}, ensure_ascii=False, indent=1))
        return 0 if report["in_contract"] else 1
    manifest = write_manifest(root)
    print(json.dumps({"operation": "regenerate", "file_count": manifest["file_count"], "root_digest": manifest_root_digest(manifest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
