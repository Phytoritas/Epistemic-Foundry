#!/usr/bin/env python3
"""Run the O03-0001 dependency-cluster and Evidence Pack acceptance checks.

Every output is attempt-local.  The runner never modifies product files; it
executes the declared lint, format, targeted, regression, and hygiene gates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/O03/attempts/0001"
ATTEMPT_ID = "O03-0001"
COMPONENT = "python/epistemic_foundry/retrieval/evidence_pack"
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


def ruff_check() -> int:
    command = ["uv", "run", "--locked", "ruff", "check", COMPONENT]
    return run(
        "ruff-check",
        command,
        stdout_path=ATTEMPT / "ruff-check.stdout.log",
        stderr_path=ATTEMPT / "ruff-check.stderr.log",
    )


def ruff_format_check() -> int:
    command = ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT]
    return run(
        "ruff-format-check",
        command,
        stdout_path=ATTEMPT / "ruff-format-check.stdout.log",
        stderr_path=ATTEMPT / "ruff-format-check.stderr.log",
    )


def targeted() -> int:
    command = [
        "uv",
        "run",
        "--locked",
        "python",
        "-B",
        "-m",
        "pytest",
        COMPONENT,
        "-p",
        "no:cacheprovider",
        f"--junitxml={ATTEMPT / 'targeted-evidence-pack.junit.xml'}",
    ]
    return run(
        "targeted-evidence-pack",
        command,
        stdout_path=ATTEMPT / "targeted-evidence-pack.stdout.log",
        stderr_path=ATTEMPT / "targeted-evidence-pack.stderr.log",
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
            "ruff-check",
            "ruff-format-check",
            "targeted",
            "python-full",
            "node-full",
            "diff-check",
        ),
    )
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    checks = {
        "ruff-check": ruff_check,
        "ruff-format-check": ruff_format_check,
        "targeted": targeted,
        "python-full": python_full,
        "node-full": node_full,
        "diff-check": diff_check,
    }
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
