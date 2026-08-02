#!/usr/bin/env python3
"""Run authoritative K01-0002 checks into attempt-local evidence files.

The runner writes only beneath ``artifacts/work_packages/K01/attempts/0002``.
It deliberately invokes pytest through ``python -m`` so the repository source
layout is resolved exactly as in the accepted full-suite command shape.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/K01/attempts/0002"

K01_PATHS = (
    "src/epistemic_foundry/ingest/registry",
    "tests/ingest",
    "tests/contracts/test_k01_document_contracts.py",
    "tests/integration/test_k01_register_document_node.py",
)


def run(
    command: list[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> int:
    executable = command
    if sys.platform == "win32" and command[0] == "npm":
        executable = ["cmd.exe", "/d", "/c", "npm.cmd", *command[1:]]
    completed = subprocess.run(
        executable,
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


def targeted() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/ingest",
            "tests/contracts/test_k01_document_contracts.py",
            "tests/integration/test_k01_register_document_node.py",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-k01-suite.junit.xml'}",
        ]
    )


def full_python() -> int:
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


def full_node() -> int:
    junit_path = ATTEMPT / "full-node-suite.junit.xml"
    stderr_path = ATTEMPT / "full-node-suite.junit.xml.stderr.log"
    if junit_path.exists() and b"<!-- fail 1 -->" in junit_path.read_bytes():
        initial_failure = ATTEMPT / "full-node-suite.initial-failure.junit.xml"
        if not initial_failure.exists():
            shutil.copy2(junit_path, initial_failure)
        initial_stderr = ATTEMPT / "full-node-suite.initial-failure.stderr.log"
        if stderr_path.exists() and not initial_stderr.exists():
            shutil.copy2(stderr_path, initial_stderr)
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": "K01-0002",
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != 54:
        print(f"expected 54 Node test files, found {len(files)}", file=sys.stderr)
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
        stdout_path=junit_path,
        stderr_path=stderr_path,
    )


def codegen() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "packages/contracts/codegen/verify.py",
            "--repo-root",
            ".",
        ],
        stdout_path=ATTEMPT / "codegen-verification.stdout.log",
        stderr_path=ATTEMPT / "codegen-verification.stderr.log",
    )


def structure() -> int:
    return run(
        ["npm", "run", "check:structure"],
        stdout_path=ATTEMPT / "structure-check.stdout.log",
        stderr_path=ATTEMPT / "structure-check.stderr.log",
    )


def boundaries() -> int:
    return run(
        ["npm", "run", "check:boundaries"],
        stdout_path=ATTEMPT / "boundary-check.stdout.log",
        stderr_path=ATTEMPT / "boundary-check.stderr.log",
    )


def ruff() -> int:
    return run(
        ["uv", "run", "--locked", "ruff", "check", *K01_PATHS],
        stdout_path=ATTEMPT / "ruff-check.stdout.log",
        stderr_path=ATTEMPT / "ruff-check.stderr.log",
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
            "targeted",
            "full-python",
            "full-node",
            "codegen",
            "structure",
            "boundaries",
            "ruff",
            "diff-check",
        ),
    )
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return {
        "targeted": targeted,
        "full-python": full_python,
        "full-node": full_node,
        "codegen": codegen,
        "structure": structure,
        "boundaries": boundaries,
        "ruff": ruff,
        "diff-check": diff_check,
    }[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
