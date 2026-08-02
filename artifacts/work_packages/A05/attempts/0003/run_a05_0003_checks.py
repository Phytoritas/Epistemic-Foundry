#!/usr/bin/env python3
"""Run the A05-0003 constitutional-correction acceptance checks."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/A05/attempts/0003"
ATTEMPT_ID = "A05-0003"
LINT_TARGETS = (
    "src/epistemic_foundry/governance/evolution_authority",
    "tests/governance",
)
TARGETED_NODE_FILES = (
    "tests/node/j02-reference-reachability.test.mjs",
    "tests/node/j02-skill-context-loader.test.mjs",
)
EXPECTED_NODE_FILE_COUNT = 84


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
    junit_from_stdout: Path | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (ATTEMPT / f"{name}.stdout.log").write_bytes(process.stdout)
    (ATTEMPT / f"{name}.stderr.log").write_bytes(process.stderr)
    if junit_from_stdout is not None:
        junit_from_stdout.write_bytes(process.stdout)
    write_run_result(name, command, process.returncode)
    return process.returncode


def node_binary() -> str | None:
    return shutil.which("node")


def ruff_check() -> int:
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", *LINT_TARGETS])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", *LINT_TARGETS],
    )


def targeted_python() -> int:
    return run(
        "targeted-a05-python",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/governance/a05",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-a05-python.junit.xml'}",
        ],
    )


def targeted_node() -> int:
    node = node_binary()
    if node is None:
        write_run_result("targeted-j02-node", ["node", "--test"], 127)
        return 127
    return run(
        "targeted-j02-node",
        [
            node,
            "--test",
            "--test-concurrency=1",
            "--test-reporter=junit",
            *TARGETED_NODE_FILES,
        ],
        junit_from_stdout=ATTEMPT / "targeted-j02-node.junit.xml",
    )


def python_full() -> int:
    return run(
        "full-python-suite",
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
        ],
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(
            {"attempt_id": ATTEMPT_ID, "count": len(files), "files": files},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != EXPECTED_NODE_FILE_COUNT:
        write_run_result("full-node-suite", ["node", "--test", "<inventory-rejected>"], 2)
        print(
            f"expected {EXPECTED_NODE_FILE_COUNT} Node test files, found {len(files)}",
            file=sys.stderr,
        )
        return 2
    node = node_binary()
    if node is None:
        write_run_result("full-node-suite", ["node", "--test", *files], 127)
        return 127
    return run(
        "full-node-suite",
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / "full-node-suite.junit.xml",
    )


def diff_check() -> int:
    return run("git-diff-check", ["git", "diff", "--check"])


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
