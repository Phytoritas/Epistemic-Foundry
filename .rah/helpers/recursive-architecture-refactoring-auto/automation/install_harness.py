#!/usr/bin/env python3
"""Install the recursive architecture harness into real Codex and Claude Code discovery locations."""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))

import managed_manifest
import parity_harness
from typing import Any

SKILL_DIR_NAME = "recursive-architecture-refactoring-auto"
BEGIN_MEMENTO_BLOCK = "# >>> RAH MEMENTO MCP >>>"
END_MEMENTO_BLOCK = "# <<< RAH MEMENTO MCP <<<"
DEFAULT_MEMENTO_SERVER_NAME = "memento"
DEFAULT_MEMENTO_URL = "http://localhost:57332/mcp"
DEFAULT_MEMENTO_BEARER_ENV = "MEMENTO_ACCESS_KEY"
CRITICAL_FILE_SPECS: dict[str, dict[str, int]] = {
    "automation/ralph_state_probe.py": {"probe_api_version": 1},
    "automation/agent_engine.py": {},
    "automation/doctor_harness.py": {},
}
TREE_EXCLUDED_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".git",
}
MANAGED_CACHE_DIRS = TREE_EXCLUDED_DIRS - {".git"}


def codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def user_skills_home() -> Path:
    return (codex_home() / "skills").resolve()


def claude_home() -> Path:
    raw = os.environ.get("CLAUDE_CONFIG_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".claude").resolve()


def claude_skills_home() -> Path:
    return (claude_home() / "skills").resolve()


def repo_helper_home(repo_root: Path) -> Path:
    return (repo_root / ".rah" / "helpers" / SKILL_DIR_NAME).resolve()


def detect_default_link_mode() -> str:
    return "copy" if os.name == "nt" else "symlink"


def skill_source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_api_version(path: Path) -> int | None:
    match = re.search(
        r"(?m)^PROBE_API_VERSION\s*=\s*(\d+)\s*$",
        path.read_text(encoding="utf-8"),
    )
    return int(match.group(1)) if match else None


def verify_critical_files(source: Path, target: Path) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for relative, expected in CRITICAL_FILE_SPECS.items():
        source_file = source / relative
        target_file = target / relative
        if not source_file.is_file() or source_file.is_symlink():
            raise FileNotFoundError(
                f"Missing or link-backed critical source file: {relative}"
            )
        if not target_file.is_file() or target_file.is_symlink():
            raise FileNotFoundError(f"Missing or link-backed critical target file: {relative}")
        source_digest = sha256_file(source_file)
        target_digest = sha256_file(target_file)
        if source_digest != target_digest:
            raise OSError(f"Critical file verification failed: {relative}")
        record: dict[str, Any] = {
            "sha256": source_digest,
            "verified": True,
        }
        if "probe_api_version" in expected:
            api_version = probe_api_version(target_file)
            if api_version != expected["probe_api_version"]:
                raise ValueError(f"Unexpected lifecycle probe API: {api_version}")
            record["probe_api_version"] = api_version
        verified[relative] = record
    return verified


def finalize_install_report(
    report: dict[str, Any], source: Path, target: Path
) -> dict[str, Any]:
    report["critical_files"] = verify_critical_files(source, target)
    return report


def remove_path(path: Path) -> None:
    is_junction = bool(hasattr(path, "is_junction") and path.is_junction())
    if not path.exists() and not path.is_symlink() and not is_junction:
        return
    if is_junction:
        path.rmdir()
    elif path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def path_is_junction(path: Path) -> bool:
    return bool(hasattr(path, "is_junction") and path.is_junction())


def preflight_tree_without_links(
    root: Path, *, excluded_names: set[str] | None = None
) -> None:
    if not root.exists():
        return
    if not root.is_dir() or root.is_symlink() or path_is_junction(root):
        raise OSError("Managed tree root is not a plain directory")
    excluded = excluded_names or set()
    root_absolute = Path(os.path.abspath(root))
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                target = Path(entry.path)
                if os.path.commonpath(
                    (root_absolute, Path(os.path.abspath(target)))
                ) != str(root_absolute):
                    raise OSError("Managed tree entry escaped its root")
                if entry.name in excluded:
                    continue
                if target.is_symlink() or path_is_junction(target):
                    raise OSError("Managed tree contains a link or junction")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(target)


def validate_repo_helper_target(repo_root: Path, target_root: Path) -> None:
    root = Path(os.path.abspath(repo_root))
    target = Path(os.path.abspath(target_root))
    if os.path.commonpath((root, target)) != str(root):
        raise OSError("Repo helper target escaped the repository root")
    cursor = target
    while True:
        if (cursor.exists() or cursor.is_symlink() or path_is_junction(cursor)) and (
            cursor.is_symlink() or path_is_junction(cursor)
        ):
            raise OSError("Repo helper path contains a link or junction")
        if cursor == root:
            break
        if cursor.parent == cursor:
            raise OSError("Repo helper ancestry did not reach the repository root")
        cursor = cursor.parent


def copytree_filtered(src: Path, dst: Path) -> None:
    preflight_tree_without_links(src, excluded_names=TREE_EXCLUDED_DIRS)

    def _ignore(_dir: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        for name in names:
            if (
                name in TREE_EXCLUDED_DIRS
                or name.endswith(".pyc")
                or name.endswith(".pyo")
            ):
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=_ignore)


def remove_managed_cache_dirs(root: Path) -> list[str]:
    removed: list[str] = []
    if (
        not root.is_dir()
        or root.is_symlink()
        or (hasattr(root, "is_junction") and root.is_junction())
    ):
        return removed
    root_absolute = Path(os.path.abspath(root))

    def visit(current: Path) -> None:
        with os.scandir(current) as entries:
            for entry in entries:
                target = Path(entry.path)
                if os.path.commonpath(
                    (root_absolute, Path(os.path.abspath(target)))
                ) != str(root_absolute):
                    raise OSError("Managed cache candidate escaped install root")
                if entry.name in MANAGED_CACHE_DIRS:
                    remove_path(target)
                    removed.append(target.relative_to(root).as_posix())
                    continue
                if target.is_symlink() or (
                    hasattr(target, "is_junction") and target.is_junction()
                ):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    visit(target)

    visit(root)
    return sorted(removed)


def sync_python_scripts_only(src: Path, dst: Path) -> None:
    preflight_tree_without_links(src, excluded_names=TREE_EXCLUDED_DIRS)
    preflight_tree_without_links(dst)
    ensure_dir(dst)
    source_names = {path.name for path in src.iterdir() if path.is_file() and path.suffix == ".py"}

    for source_path in src.iterdir():
        if not source_path.is_file() or source_path.suffix != ".py":
            continue
        target_path = dst / source_path.name
        shutil.copy2(source_path, target_path)

    for target_path in list(dst.iterdir()):
        if target_path.name == "__pycache__" or target_path.name.endswith(".pyc") or target_path.name.endswith(".pyo"):
            remove_path(target_path)
            continue
        if target_path.is_dir():
            remove_path(target_path)
            continue
        if target_path.name not in source_names:
            remove_path(target_path)


def sync_tree_filtered(src: Path, dst: Path) -> list[str]:
    preflight_tree_without_links(src, excluded_names=TREE_EXCLUDED_DIRS)
    preflight_tree_without_links(dst)
    ensure_dir(dst)
    removed_caches = remove_managed_cache_dirs(dst)
    for source_path in src.rglob("*"):
        rel_path = source_path.relative_to(src)
        if any(part in TREE_EXCLUDED_DIRS for part in rel_path.parts):
            continue
        if source_path.name.endswith(".pyc") or source_path.name.endswith(".pyo"):
            continue

        target_path = dst / rel_path
        if source_path.is_dir():
            ensure_dir(target_path)
            continue

        ensure_dir(target_path.parent)
        shutil.copy2(source_path, target_path)
    return removed_caches


def install_repo_helpers(
    source_root: Path,
    target_root: Path,
    force: bool,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    automation_source = source_root / "automation"
    if not automation_source.exists():
        raise FileNotFoundError(f"Missing automation source: {automation_source}")

    report: dict[str, Any] = {
        "source": str(source_root),
        "target": str(target_root),
        "mode": "copy",
        "action": None,
        "note": None,
    }
    cleanup_failures: list[str] = []

    if repo_root is not None:
        validate_repo_helper_target(repo_root, target_root)

    if (target_root.exists() or target_root.is_symlink()) and not force:
        raise FileExistsError(f"Target already exists: {target_root}")
    if target_root.is_symlink() or target_root.is_file():
        remove_path(target_root)

    ensure_dir(target_root)
    sync_python_scripts_only(automation_source, target_root / "automation")

    for child in list(target_root.iterdir()):
        if child.name != "automation":
            try:
                remove_path(child)
            except OSError as exc:
                cleanup_failures.append(f"{child.name}: {exc}")

    report["action"] = "updated" if force and any(target_root.iterdir()) else "copied"
    report["note"] = "Repo helper bundle refreshed with automation scripts only."
    if cleanup_failures:
        report["note"] += " Cleanup skipped for: " + "; ".join(cleanup_failures)
    return finalize_install_report(report, source_root, target_root)


def _staged_user_install(
    source_root: Path,
    targets: list[tuple[str, Path]],
) -> list[dict]:
    """Dual-host install as one transaction (R23).

    Each target is installed via the staged whole-tree swap (verify staging,
    backup old tree, activate, re-verify). If a LATER target fails, every
    earlier target is restored from its backup so both hosts end on the same
    generation — the sequential split-brain of the first design (Pro repro)
    cannot occur. Requires the source package to carry its manifest; a
    manifest-less source falls back to the legacy copy path explicitly."""

    import shutil as _shutil

    # Pin the source generation across both targets (reviewer finding: an
    # unpinned source could install different generations per host).
    source_manifest = managed_manifest.load_manifest(source_root)
    source_digest = managed_manifest.manifest_root_digest(source_manifest)

    completed: list[tuple[str, Path, str | None]] = []
    installs: list[dict] = []
    try:
        for runtime, target in targets:
            live_state = managed_manifest.verify_tree(source_root)
            live_digest = live_state.get("root_digest")
            if not live_state["in_contract"] or live_digest != source_digest:
                raise managed_manifest.ManifestError(
                    "source package changed or broke its manifest mid-install "
                    f"(pinned {source_digest[:12]}, now {str(live_digest)[:12]}, "
                    f"in_contract={live_state['in_contract']})"
                )
            if source_root.resolve() == target.resolve():
                installs.append(
                    {"runtime": runtime, "target": str(target), "mode": "already-canonical"}
                )
                continue
            backup_parent = target.parent.parent / "backups" / "rah-install"
            actions = parity_harness.sync_mirror_transaction(source_root, target, backup_parent)
            completed.append((runtime, target, actions.get("backup_path")))
            # Round 2 reviewer finding: the pinned-digest check ran only
            # BEFORE the copy; re-verify the installed bytes against the pin
            # so a mid-copy source swap cannot land silently.
            installed_state = managed_manifest.verify_tree(target)
            if not installed_state["in_contract"] or installed_state.get("root_digest") != source_digest:
                raise managed_manifest.ManifestError(
                    f"installed tree at {target} does not match the pinned source generation "
                    f"(pinned {source_digest[:12]}, got {str(installed_state.get('root_digest'))[:12]})"
                )
            installs.append(
                {
                    "runtime": runtime,
                    "target": str(target),
                    "mode": "staged-transaction",
                    **actions,
                }
            )
    except Exception as exc:  # noqa: BLE001 — ANY failure after a completed target must roll back (Pro round 2)
        # Reviewer findings: only ManifestError used to trigger rollback (an
        # OSError escaped with targets split), and rollback success was
        # claimed without verification.
        rollback_reports: list[dict] = []
        for runtime, target, backup in reversed(completed):
            report = {"runtime": runtime, "target": str(target), "restored": False, "verified": False}
            try:
                if target.exists():
                    _shutil.rmtree(target)
                if backup and Path(backup).exists():
                    Path(backup).rename(target)
                    report["restored"] = True
                    restored_state = managed_manifest.verify_tree(target)
                    report["verified"] = bool(restored_state["in_contract"])
            except Exception as rollback_exc:  # noqa: BLE001 — one target's restore failure must not abort the rest
                # Round 2 reviewer finding: a ManifestError from verify_tree
                # inside this loop used to abort the REMAINING restores.
                report["error"] = str(rollback_exc)
            rollback_reports.append(report)
        failed_rollbacks = [r for r in rollback_reports if not r.get("verified")]
        if failed_rollbacks:
            raise OSError(
                "dual-host install failed AND rollback could not be verified on "
                f"{[r['target'] for r in failed_rollbacks]} — hosts may be split; "
                f"restore from backups under <target>/../../backups/rah-install. Cause: {exc}"
            )
        raise OSError(
            f"dual-host install failed on a later target; earlier targets were rolled back and re-verified: {exc}"
        )
    return installs


def install_skill_tree(source: Path, target: Path, mode: str, force: bool) -> dict[str, Any]:
    report: dict[str, Any] = {
        "source": str(source),
        "target": str(target),
        "mode": mode,
        "action": None,
        "note": None,
    }

    if target.exists() or target.is_symlink():
        target_is_junction = bool(
            hasattr(target, "is_junction") and target.is_junction()
        )
        if mode == "copy" and target_is_junction:
            raise OSError("Refusing in-place copy refresh through a junction target")
        same_target = False
        try:
            if target.is_symlink():
                same_target = target.resolve() == source.resolve()
            elif target.is_dir():
                same_target = target.resolve() == source.resolve()
        except OSError:
            same_target = False
        if same_target:
            report["action"] = "noop"
            report["note"] = "Target already points to this package."
            return finalize_install_report(report, source, target)
        if not force:
            raise FileExistsError(f"Target already exists: {target}")
        if mode == "copy" and target.is_dir() and not target.is_symlink():
            removed_caches = sync_tree_filtered(source, target)
            report["action"] = "updated"
            report["note"] = "Existing copy-mode install refreshed in place."
            report["removed_cache_dirs"] = removed_caches
            return finalize_install_report(report, source, target)
        remove_path(target)

    ensure_dir(target.parent)

    if mode == "symlink":
        try:
            target.symlink_to(source, target_is_directory=True)
            report["action"] = "symlinked"
            return finalize_install_report(report, source, target)
        except OSError as exc:
            report["mode"] = "copy"
            report["note"] = f"Symlink failed ({exc}); fell back to copy."
            mode = "copy"

    copytree_filtered(source, target)
    report["action"] = "copied"
    return finalize_install_report(report, source, target)


def render_memento_block(
    server_name: str,
    url: str,
    bearer_env: str | None,
    required: bool,
    startup_timeout_sec: float,
    tool_timeout_sec: float,
) -> str:
    lines = [
        BEGIN_MEMENTO_BLOCK,
        f"[mcp_servers.{server_name}]",
        "enabled = true",
        f"required = {'true' if required else 'false'}",
        f'url = "{url}"',
    ]
    if bearer_env:
        lines.append(f'bearer_token_env_var = "{bearer_env}"')
    lines.append(f"startup_timeout_sec = {startup_timeout_sec:.1f}")
    lines.append(f"tool_timeout_sec = {tool_timeout_sec:.1f}")
    lines.append(END_MEMENTO_BLOCK)
    return "\n".join(lines) + "\n"


def _memento_table_regex(server_name: str) -> re.Pattern[str]:
    return re.compile(rf"^\[mcp_servers\.{re.escape(server_name)}\]\s*$", re.MULTILINE)


def update_managed_memento_block(
    config_path: Path,
    server_name: str,
    url: str,
    bearer_env: str | None,
    required: bool,
    startup_timeout_sec: float,
    tool_timeout_sec: float,
    force_config: bool,
) -> dict[str, Any]:
    ensure_dir(config_path.parent)
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    block = render_memento_block(server_name, url, bearer_env, required, startup_timeout_sec, tool_timeout_sec)

    unmanaged_exists = _memento_table_regex(server_name).search(existing) and BEGIN_MEMENTO_BLOCK not in existing
    if unmanaged_exists and not force_config:
        return {
            "config_path": str(config_path),
            "action": "skipped",
            "note": f"Unmanaged [mcp_servers.{server_name}] already exists; not overwriting without --force-config.",
        }

    if BEGIN_MEMENTO_BLOCK in existing and END_MEMENTO_BLOCK in existing:
        pattern = re.compile(
            re.escape(BEGIN_MEMENTO_BLOCK) + r".*?" + re.escape(END_MEMENTO_BLOCK) + r"\n?",
            re.DOTALL,
        )
        new_text = pattern.sub(block, existing)
        action = "updated"
    else:
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        new_text = prefix + block
        action = "created" if not existing else "appended"

    config_path.write_text(new_text, encoding="utf-8")
    return {"config_path": str(config_path), "action": action, "note": None}


def maybe_write_deployment_state(repo_root: Path, deployment: dict[str, Any]) -> str | None:
    rah_state = repo_root / ".rah" / "state"
    if not rah_state.exists():
        return None
    target = rah_state / "deployment.json"
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        if isinstance(existing, dict):
            for key in ("memento_config", "commit_safety"):
                if deployment.get(key) is None and existing.get(key) is not None:
                    deployment[key] = existing[key]
    target.write_text(json.dumps(deployment, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(target)


def run_setup_if_requested(source_root: Path, repo_root: Path, bootstrap: bool, project_name: str | None) -> dict[str, Any] | None:
    if not bootstrap:
        return None
    cmd = [sys.executable, "-B", str(source_root / "automation" / "rah.py"), "setup", str(repo_root)]
    if project_name:
        cmd += ["--project-name", project_name]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = _SuggestingArgumentParser(description="Install the recursive architecture harness into Codex and Claude Code discovery/config paths.")
    parser.add_argument("--scope", choices=["user", "repo"], default="user", help="Install the package into user skill discovery or repo-local helper paths.")
    parser.add_argument("--targets", choices=["both", "codex", "claude"], default="both", help="User-scope skill homes to install into: Codex (~/.codex/skills), Claude Code (~/.claude/skills), or both.")
    parser.add_argument("--repo-root", default=None, help="Required for --scope repo, project-scoped config, or bootstrap.")
    parser.add_argument("--package-root", default=None, help="Override source package root; defaults to the current extracted package.")
    parser.add_argument("--mode", choices=["symlink", "copy"], default=None, help="Install skill via symlink or copy.")
    parser.add_argument("--force", action="store_true", help="Replace an existing installed skill target.")
    parser.add_argument("--force-config", action="store_true", help="Replace an unmanaged existing [mcp_servers.<name>] block.")
    parser.add_argument("--skills-home", default=None, help="Override the Codex user skill discovery directory.")
    parser.add_argument("--codex-home", default=None, help="Override Codex home (default: CODEX_HOME or ~/.codex).")
    parser.add_argument("--claude-home", default=None, help="Override Claude Code home (default: CLAUDE_CONFIG_DIR or ~/.claude).")
    parser.add_argument("--claude-skills-home", default=None, help="Override the Claude Code user skill discovery directory.")
    parser.add_argument("--configure-memento", action="store_true", help="Write a managed Memento MCP block into config.toml.")
    parser.add_argument("--mcp-scope", choices=["user", "project"], default="user", help="Where to write the Memento MCP config.")
    parser.add_argument("--memento-server-name", default=DEFAULT_MEMENTO_SERVER_NAME)
    parser.add_argument("--memento-url", default=DEFAULT_MEMENTO_URL)
    parser.add_argument("--memento-bearer-env", default=DEFAULT_MEMENTO_BEARER_ENV)
    parser.add_argument("--memento-required", action="store_true", help="Mark the Memento MCP server as required.")
    parser.add_argument("--startup-timeout-sec", type=float, default=10.0)
    parser.add_argument("--tool-timeout-sec", type=float, default=60.0)
    parser.add_argument("--bootstrap", action="store_true", help="Run rah setup after installation when --repo-root is provided.")
    parser.add_argument("--project-name", default=None, help="Optional project name forwarded to setup when --bootstrap is used.")
    args = parser.parse_args()

    source_root = Path(args.package_root).expanduser().resolve() if args.package_root else skill_source_root()
    if not (source_root / "SKILL.md").exists():
        print(json.dumps({"error": f"Invalid package root: {source_root}"}, ensure_ascii=False))
        return 2

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else None
    if args.scope == "repo" and repo_root is None:
        print(json.dumps({"error": "--repo-root is required when --scope repo"}, ensure_ascii=False))
        return 2
    if args.mcp_scope == "project" and repo_root is None:
        print(json.dumps({"error": "--repo-root is required when --mcp-scope project"}, ensure_ascii=False))
        return 2
    if args.bootstrap and repo_root is None:
        print(json.dumps({"error": "--repo-root is required with --bootstrap"}, ensure_ascii=False))
        return 2

    mode = args.mode or detect_default_link_mode()
    codex_root = Path(args.codex_home).expanduser().resolve() if args.codex_home else codex_home()
    skills_home = Path(args.skills_home).expanduser().resolve() if args.skills_home else user_skills_home()
    claude_root = Path(args.claude_home).expanduser().resolve() if args.claude_home else claude_home()
    claude_skills = (
        Path(args.claude_skills_home).expanduser().resolve() if args.claude_skills_home else (claude_root / "skills").resolve()
    )

    report: dict[str, Any] = {
        "package_install": None,
        "package_installs": None,
        "memento_config": None,
        "bootstrap": None,
        "deployment_state_path": None,
    }

    try:
        if args.scope == "repo":
            repo_report = install_repo_helpers(
                source_root,
                repo_helper_home(repo_root),
                args.force,
                repo_root,
            )
            repo_report["runtime"] = "repo"
            report["package_install"] = repo_report
            report["package_installs"] = [repo_report]
        else:
            user_targets: list[tuple[str, Path]] = []
            if args.targets in ("both", "codex"):
                user_targets.append(("codex", skills_home / SKILL_DIR_NAME))
            if args.targets in ("both", "claude"):
                user_targets.append(("claude", claude_skills / SKILL_DIR_NAME))
            installs: list[dict[str, Any]] = []
            if (source_root / managed_manifest.MANIFEST_NAME).is_file():
                installs = _staged_user_install(source_root, user_targets)
            else:
                # manifest-less source: legacy per-target copy, explicitly
                # labeled non-transactional
                for runtime, target in user_targets:
                    rep = install_skill_tree(source_root, target, mode, args.force)
                    rep["runtime"] = runtime
                    rep["mode"] = rep.get("mode") or "legacy-non-transactional"
                    installs.append(rep)
            report["package_installs"] = installs
            report["package_install"] = installs[0] if installs else None
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    if args.configure_memento:
        config_path = (repo_root / ".codex" / "config.toml") if args.mcp_scope == "project" else (codex_root / "config.toml")
        report["memento_config"] = update_managed_memento_block(
            config_path=config_path,
            server_name=args.memento_server_name,
            url=args.memento_url,
            bearer_env=args.memento_bearer_env,
            required=args.memento_required,
            startup_timeout_sec=args.startup_timeout_sec,
            tool_timeout_sec=args.tool_timeout_sec,
            force_config=args.force_config,
        )

    report["bootstrap"] = run_setup_if_requested(source_root, repo_root, args.bootstrap, args.project_name) if repo_root else None

    deployment_state = {
        "installed_at_source": str(source_root),
        "package_install": report["package_install"],
        "package_installs": report["package_installs"],
        "memento_config": report["memento_config"],
        "bootstrap": report["bootstrap"],
        "codex_home": str(codex_root),
        "skills_home": str(skills_home),
        "claude_home": str(claude_root),
        "claude_skills_home": str(claude_skills),
        "targets": args.targets if args.scope == "user" else None,
        "scope": args.scope,
    }
    if repo_root:
        report["deployment_state_path"] = maybe_write_deployment_state(repo_root, deployment_state)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["bootstrap"] and report["bootstrap"]["returncode"] not in (0, None):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
