#!/usr/bin/env python3
"""Run the T01-0002 MCP read/planning acceptance checks.

Every output is attempt-local.  The runner never modifies product files; it
executes the declared lint, format, targeted Python, targeted Node, full
regression, and hygiene gates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/T01/attempts/0002"
ATTEMPT_ID = "T01-0002"
LINT_TARGETS = ("src/epistemic_foundry/application", "tests/mcp")
TARGETED_NODE_FILES = (
    "tests/node/t01-tool-catalog.test.mjs",
    "tests/node/t01-schema-resolution.test.mjs",
    "tests/node/t01-transport-framing.test.mjs",
)
EXPECTED_NODE_FILE_COUNT = 82


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
    command = ["uv", "run", "--locked", "ruff", "check", *LINT_TARGETS]
    return run(
        "ruff-check",
        command,
        stdout_path=ATTEMPT / "ruff-check.stdout.log",
        stderr_path=ATTEMPT / "ruff-check.stderr.log",
    )


def ruff_format_check() -> int:
    command = ["uv", "run", "--locked", "ruff", "format", "--check", *LINT_TARGETS]
    return run(
        "ruff-format-check",
        command,
        stdout_path=ATTEMPT / "ruff-format-check.stdout.log",
        stderr_path=ATTEMPT / "ruff-format-check.stderr.log",
    )


def targeted_python() -> int:
    command = [
        "uv",
        "run",
        "--locked",
        "python",
        "-B",
        "-m",
        "pytest",
        "tests/mcp",
        "-p",
        "no:cacheprovider",
        f"--junitxml={ATTEMPT / 'targeted-mcp-python.junit.xml'}",
    ]
    return run(
        "targeted-mcp-python",
        command,
        stdout_path=ATTEMPT / "targeted-mcp-python.stdout.log",
        stderr_path=ATTEMPT / "targeted-mcp-python.stderr.log",
    )


def targeted_node() -> int:
    node = shutil.which("node")
    if node is None:
        write_run_result("targeted-mcp-node", ["node", "--test"], 127)
        print("node executable not found", file=sys.stderr)
        return 127
    command = [
        node,
        "--test",
        "--test-concurrency=1",
        "--test-reporter=junit",
        *TARGETED_NODE_FILES,
    ]
    return run(
        "targeted-mcp-node",
        command,
        stdout_path=ATTEMPT / "targeted-mcp-node.stdout.log",
        stderr_path=ATTEMPT / "targeted-mcp-node.stderr.log",
        junit_from_stdout=ATTEMPT / "targeted-mcp-node.junit.xml",
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
            "targeted-python",
            "targeted-node",
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
        "targeted-python": targeted_python,
        "targeted-node": targeted_node,
        "python-full": python_full,
        "node-full": node_full,
        "diff-check": diff_check,
    }
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
