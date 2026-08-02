#!/usr/bin/env python3
"""Run the raw B04-0008 final packaging checks.

This runner only writes attempt-local evidence and distribution artifacts.  It
does not modify canonical source, the derived package snapshot, or product
tests.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0008"


def run(
    command: list[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> int:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE if stdout_path is not None else None,
        stderr=subprocess.PIPE if stderr_path is not None else None,
        check=False,
    )
    if stdout_path is not None:
        stdout_path.write_bytes(completed.stdout)
    if stderr_path is not None:
        stderr_path.write_bytes(completed.stderr)
    return completed.returncode


def python_targeted() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/packaging/test_canonical_registry.py",
            "tests/test_contracts.py",
            "tests/test_cli.py",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-projection.junit.xml'}",
        ]
    )


def python_full() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'full-python-suite.junit.xml'}",
        ]
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": "B04-0008",
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != 52:
        print(f"expected 52 Node test files, found {len(files)}", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        [
            node,
            "--test",
            "--test-concurrency=1",
            "--test-reporter=junit",
            *files,
        ],
        stdout_path=ATTEMPT / "full-node-suite.junit.xml",
        stderr_path=ATTEMPT / "full-node-suite.junit.xml.stderr.log",
    )


def packaging() -> int:
    return run(
        [
            sys.executable,
            "-B",
            "scripts/build/canonical_registry/verify_packaging.py",
            "--root",
            ".",
            "--report",
            str(ATTEMPT / "packaging-verification-run.json"),
            "--dist-dir",
            str(ATTEMPT / "dist"),
        ],
        stdout_path=ATTEMPT / "packaging-verification.stdout.log",
        stderr_path=ATTEMPT / "packaging-verification.stderr.log",
    )


def materialize_check() -> int:
    return run(
        [
            sys.executable,
            "-B",
            "scripts/build/canonical_registry/materialize.py",
            "--root",
            ".",
            "--check",
        ],
        stdout_path=ATTEMPT / "materialize-check.stdout.log",
        stderr_path=ATTEMPT / "materialize-check.stderr.log",
    )


def diff_check() -> int:
    return run(
        ["git", "diff", "--check"],
        stdout_path=ATTEMPT / "git-diff-check.stdout.log",
        stderr_path=ATTEMPT / "git-diff-check.stderr.log",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check",
        choices=(
            "python-targeted",
            "python-full",
            "node-full",
            "packaging",
            "materialize-check",
            "diff-check",
        ),
    )
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return {
        "python-targeted": python_targeted,
        "python-full": python_full,
        "node-full": node_full,
        "packaging": packaging,
        "materialize-check": materialize_check,
        "diff-check": diff_check,
    }[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
