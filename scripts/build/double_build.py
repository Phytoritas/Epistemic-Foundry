#!/usr/bin/env python3
"""Build B02 artifacts twice from fresh source copies and compare bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SOURCE_FILES = (
    "README.md",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "uv.lock",
)
SOURCE_DIRECTORIES = ("packages", "src", "toolchains")
IGNORED_NAMES = {
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
ARTIFACT_SUFFIXES = (".tgz", ".whl")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORED_NAMES or name.endswith((".egg-info", ".pyc", ".pyo"))
    }


def stage_source(root: Path, destination: Path) -> str:
    destination.mkdir(parents=True, exist_ok=False)
    for relative in SOURCE_FILES:
        shutil.copy2(root / relative, destination / relative)
    for relative in SOURCE_DIRECTORIES:
        shutil.copytree(root / relative, destination / relative, ignore=ignored)

    digest = hashlib.sha256()
    for path in sorted((path for path in destination.rglob("*") if path.is_file()), key=lambda item: item.relative_to(destination).as_posix()):
        relative = path.relative_to(destination).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    display_command: list[str] | None = None,
) -> dict[str, Any]:
    executable = shutil.which(command[0], path=environment.get("PATH"))
    if executable is None:
        raise RuntimeError(f"required executable is not on PATH: {command[0]}")
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(command)} failed ({completed.returncode}):\n{detail}")
    return {
        "command": display_command or command,
        "exit_code": completed.returncode,
    }


def build_once(source: Path, output: Path, epoch: int) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "SOURCE_DATE_EPOCH": str(epoch),
            "PYTHONHASHSEED": "0",
            "TZ": "UTC",
            "NO_COLOR": "1",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "npm_config_ignore_scripts": "true",
        }
    )
    commands = [
        run(
            [
                "npm",
                "pack",
                "--workspaces",
                "--ignore-scripts",
                "--pack-destination",
                str(output),
                "--json",
            ],
            source,
            environment,
            [
                "npm",
                "pack",
                "--workspaces",
                "--ignore-scripts",
                "--pack-destination",
                "<BUILD_OUTPUT>",
                "--json",
            ],
        ),
        run(
            [
                "uv",
                "build",
                "--wheel",
                "--build-constraints",
                "toolchains/python-build-constraints.txt",
                "--require-hashes",
                "--no-python-downloads",
                "--no-build-logs",
                "--out-dir",
                str(output),
                ".",
            ],
            source,
            environment,
            [
                "uv",
                "build",
                "--wheel",
                "--build-constraints",
                "toolchains/python-build-constraints.txt",
                "--require-hashes",
                "--no-python-downloads",
                "--no-build-logs",
                "--out-dir",
                "<BUILD_OUTPUT>",
                ".",
            ],
        ),
    ]
    artifacts = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(output.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.suffix in ARTIFACT_SUFFIXES
    }
    workspace_count = len(list((source / "packages").glob("*/package.json")))
    node_count = sum(name.endswith(".tgz") for name in artifacts)
    python_count = sum(name.endswith(".whl") for name in artifacts)
    if node_count != workspace_count:
        raise RuntimeError(f"expected {workspace_count} Node tarballs, built {node_count}")
    if python_count != 1:
        raise RuntimeError(f"expected one Python wheel, built {python_count}")
    return {"commands": commands, "artifacts": artifacts}


def compare(root: Path) -> dict[str, Any]:
    lock = json.loads((root / "toolchains" / "toolchain-lock.json").read_text(encoding="utf-8"))
    epoch = lock.get("source_date_epoch")
    if not isinstance(epoch, int):
        raise RuntimeError("toolchain-lock source_date_epoch must be an integer")

    lock_check = subprocess.run(
        [sys.executable, str(root / "scripts" / "build" / "check_locks.py"), "--root", str(root)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if lock_check.returncode != 0:
        raise RuntimeError("lockfile_check failed before build:\n" + (lock_check.stdout or lock_check.stderr))

    with tempfile.TemporaryDirectory(prefix="efoundry-b02-double-build-") as temporary:
        temporary_root = Path(temporary)
        source_one = temporary_root / "source-one"
        source_two = temporary_root / "source-two"
        source_hash_one = stage_source(root, source_one)
        source_hash_two = stage_source(root, source_two)
        first = build_once(source_one, temporary_root / "output-one", epoch)
        second = build_once(source_two, temporary_root / "output-two", epoch)

    inventory_equal = set(first["artifacts"]) == set(second["artifacts"])
    mismatches = sorted(
        name
        for name in set(first["artifacts"]) | set(second["artifacts"])
        if first["artifacts"].get(name) != second["artifacts"].get(name)
    )
    source_equal = source_hash_one == source_hash_two
    status = "PASS" if source_equal and inventory_equal and not mismatches else "FAIL"
    return {
        "check": "double_build_comparison",
        "status": status,
        "source_date_epoch": epoch,
        "source_snapshot_sha256": source_hash_one,
        "source_snapshots_equal": source_equal,
        "artifact_inventory_equal": inventory_equal,
        "artifact_count": len(first["artifacts"]),
        "artifacts": first["artifacts"],
        "mismatches": mismatches,
        "builds": [
            {"commands": first["commands"]},
            {"commands": second["commands"]},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.root.resolve())
    except Exception as error:
        result = {
            "check": "double_build_comparison",
            "status": "FAIL",
            "error": str(error),
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
