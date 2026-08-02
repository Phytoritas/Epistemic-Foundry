#!/usr/bin/env python3
"""Run the B04-0010 final post-C04 packaging checks.

Every output is attempt-local.  The runner never materializes or modifies the
canonical source or package snapshot; materialization is checked read-only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0010"
ATTEMPT_ID = "B04-0010"
EXPECTED_NODE_FILE_COUNT = 79


def write_run_result(name: str, command: list[str], exit_code: int) -> None:
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "command": command,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(
    name: str,
    command: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
    junit_from_stdout: Path | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_bytes(process.stdout)
    stderr_path.write_bytes(process.stderr)
    if junit_from_stdout is not None:
        junit_from_stdout.write_bytes(process.stdout)
    write_run_result(name, command, process.returncode)
    return process.returncode


def materialize_check() -> int:
    command = [
        sys.executable,
        "-B",
        "scripts/build/canonical_registry/materialize.py",
        "--root",
        ".",
        "--check",
    ]
    return run(
        "materialize-check",
        command,
        stdout_path=ATTEMPT / "materialize-check.stdout.log",
        stderr_path=ATTEMPT / "materialize-check.stderr.log",
    )


def python_targeted() -> int:
    command = [
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
    return run(
        "targeted-projection",
        command,
        stdout_path=ATTEMPT / "targeted-projection.stdout.log",
        stderr_path=ATTEMPT / "targeted-projection.stderr.log",
    )


def packaging() -> int:
    command = [
        sys.executable,
        "-B",
        "scripts/build/canonical_registry/verify_packaging.py",
        "--root",
        ".",
        "--report",
        str(ATTEMPT / "packaging-verification-run.json"),
        "--dist-dir",
        str(ATTEMPT / "dist"),
    ]
    return run(
        "packaging-verification",
        command,
        stdout_path=ATTEMPT / "packaging-verification.stdout.log",
        stderr_path=ATTEMPT / "packaging-verification.stderr.log",
    )


def python_full() -> int:
    command = [
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
    return run(
        "full-python-suite",
        command,
        stdout_path=ATTEMPT / "full-python-suite.stdout.log",
        stderr_path=ATTEMPT / "full-python-suite.stderr.log",
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": ATTEMPT_ID,
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != EXPECTED_NODE_FILE_COUNT:
        command = ["node", "--test", "<inventory-rejected>"]
        write_run_result("full-node-suite", command, 2)
        print(
            f"expected {EXPECTED_NODE_FILE_COUNT} Node test files, found {len(files)}",
            file=sys.stderr,
        )
        return 2
    node = shutil.which("node")
    if node is None:
        command = ["node", "--test", *files]
        write_run_result("full-node-suite", command, 127)
        print("node executable not found", file=sys.stderr)
        return 127
    command = [
        node,
        "--test",
        "--test-concurrency=1",
        "--test-reporter=junit",
        *files,
    ]
    return run(
        "full-node-suite",
        command,
        stdout_path=ATTEMPT / "full-node-suite.stdout.log",
        stderr_path=ATTEMPT / "full-node-suite.stderr.log",
        junit_from_stdout=ATTEMPT / "full-node-suite.junit.xml",
    )


def diff_check() -> int:
    command = ["git", "diff", "--check"]
    return run(
        "git-diff-check",
        command,
        stdout_path=ATTEMPT / "git-diff-check.stdout.log",
        stderr_path=ATTEMPT / "git-diff-check.stderr.log",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check",
        choices=(
            "materialize-check",
            "python-targeted",
            "packaging",
            "python-full",
            "node-full",
            "diff-check",
        ),
    )
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    checks = {
        "materialize-check": materialize_check,
        "python-targeted": python_targeted,
        "packaging": packaging,
        "python-full": python_full,
        "node-full": node_full,
        "diff-check": diff_check,
    }
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
