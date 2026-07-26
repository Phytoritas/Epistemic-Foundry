#!/usr/bin/env python3
"""Cleanup/migration report surface for legacy repo-local harness artifacts."""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
from pathlib import Path
from typing import Any

SKILL_DIR_NAME = "recursive-architecture-refactoring-auto"


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_relative_entries(root: Path) -> tuple[list[str], list[str]]:
    if not root.exists() or not root.is_dir():
        return [], []

    files: list[str] = []
    dirs: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            dirs.append(rel)
        elif path.is_file():
            files.append(rel)
    return files, dirs


def deployment_target(deployment_payload: Any) -> str | None:
    if not isinstance(deployment_payload, dict):
        return None
    package_install = deployment_payload.get("package_install")
    if isinstance(package_install, dict):
        return package_install.get("target")
    legacy_skill_install = deployment_payload.get("skill_install")
    if isinstance(legacy_skill_install, dict):
        return legacy_skill_install.get("target")
    return None


def build_payload(root: Path) -> dict[str, Any]:
    helper_root = root / ".rah" / "helpers" / SKILL_DIR_NAME
    legacy_runtime_root = root / ".rah" / "runtime" / SKILL_DIR_NAME
    legacy_skill_root = root / ".agents" / "skills" / SKILL_DIR_NAME
    deployment_payload = load_json(root / ".rah" / "state" / "deployment.json")

    helper_files, helper_dirs = list_relative_entries(helper_root)
    legacy_runtime_files, legacy_runtime_dirs = list_relative_entries(legacy_runtime_root)
    legacy_skill_files, legacy_skill_dirs = list_relative_entries(legacy_skill_root)

    payload = {
        "root": str(root),
        "deployment_helper_target": deployment_target(deployment_payload),
        "helper_root": str(helper_root),
        "helper_exists": helper_root.exists(),
        "helper_files": helper_files,
        "helper_dirs": helper_dirs,
        "legacy_runtime_root": str(legacy_runtime_root),
        "legacy_runtime_exists": legacy_runtime_root.exists(),
        "legacy_runtime_file_count": len(legacy_runtime_files),
        "legacy_runtime_dir_count": len(legacy_runtime_dirs),
        "legacy_runtime_files": legacy_runtime_files,
        "legacy_runtime_dirs": legacy_runtime_dirs,
        "legacy_skill_root": str(legacy_skill_root),
        "legacy_skill_exists": legacy_skill_root.exists(),
        "legacy_skill_active": (legacy_skill_root / "SKILL.md").exists(),
        "legacy_skill_disabled": (legacy_skill_root / "SKILL.disabled.md").exists(),
        "legacy_skill_file_count": len(legacy_skill_files),
        "legacy_skill_dir_count": len(legacy_skill_dirs),
        "legacy_skill_files": legacy_skill_files,
        "legacy_skill_dirs": legacy_skill_dirs,
    }
    return payload


def print_markdown(payload: dict[str, Any]) -> None:
    print("# Legacy Cleanup Report\n")
    for key in [
        "root",
        "deployment_helper_target",
        "helper_root",
        "helper_exists",
        "legacy_runtime_root",
        "legacy_runtime_exists",
        "legacy_runtime_file_count",
        "legacy_runtime_dir_count",
        "legacy_skill_root",
        "legacy_skill_exists",
        "legacy_skill_active",
        "legacy_skill_disabled",
        "legacy_skill_file_count",
        "legacy_skill_dir_count",
    ]:
        print(f"- {key}: {payload.get(key)}")

    if payload["helper_files"]:
        print("- helper_files:")
        for rel in payload["helper_files"]:
            print(f"  - {rel}")

    if payload["legacy_runtime_files"] or payload["legacy_runtime_dirs"]:
        print("- legacy_runtime_remaining:")
        for rel in payload["legacy_runtime_files"]:
            print(f"  - file: {rel}")
        for rel in payload["legacy_runtime_dirs"]:
            print(f"  - dir: {rel}")

    if payload["legacy_skill_files"] or payload["legacy_skill_dirs"]:
        print("- legacy_skill_remaining:")
        for rel in payload["legacy_skill_files"]:
            print(f"  - file: {rel}")
        for rel in payload["legacy_skill_dirs"]:
            print(f"  - dir: {rel}")


def main() -> int:
    parser = _SuggestingArgumentParser(
        description=(
            "Report helper-only migration state after rah.py has refreshed repo-local helpers "
            "and pruned recognized legacy artifacts."
        )
    )
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    payload = build_payload(root)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_markdown(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
