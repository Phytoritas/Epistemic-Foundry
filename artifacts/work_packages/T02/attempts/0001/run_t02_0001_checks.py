#!/usr/bin/env python3
"""Run the T02-0001 MCP mutating-tool acceptance checks.

Required checks from manifests/development_manifest.yaml (T02):
``mcp_effect_test`` and ``approval_test``.  Both are Python test modules under
``tests/mcp/t02``; the composed Node surface is covered by the Node inventory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/T02/attempts/0001"
ATTEMPT_ID = "T02-0001"
COMPONENTS = (
    "src/epistemic_foundry/application/mcp_mutating",
    "tests/mcp/t02",
)
EXPECTED_NODE_FILE_COUNT = 87


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


def ruff_check() -> int:
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", *COMPONENTS])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", *COMPONENTS],
    )


def mcp_effect_test() -> int:
    return run(
        "mcp-effect-test",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/mcp/t02/test_mcp_effect.py",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'mcp-effect-test.junit.xml'}",
        ],
    )


def approval_test() -> int:
    return run(
        "approval-test",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/mcp/t02/test_approval.py",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'approval-test.junit.xml'}",
        ],
    )


def targeted() -> int:
    return run(
        "targeted-mcp-mutating",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/mcp/t02",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-mcp-mutating.junit.xml'}",
        ],
    )


def sealed_t01_regression() -> int:
    return run(
        "sealed-t01-regression",
        [
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
            f"--junitxml={ATTEMPT / 'sealed-t01-regression.junit.xml'}",
        ],
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
        if base.is_dir()
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
        write_run_result(
            "full-node-suite", ["node", "--test", "<inventory-rejected>"], 2
        )
        print(
            f"expected {EXPECTED_NODE_FILE_COUNT} Node test files, found {len(files)}",
            file=sys.stderr,
        )
        return 2
    node = shutil.which("node")
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
    checks = {
        "ruff-check": ruff_check,
        "ruff-format-check": ruff_format_check,
        "mcp-effect-test": mcp_effect_test,
        "approval-test": approval_test,
        "targeted": targeted,
        "sealed-t01-regression": sealed_t01_regression,
        "python-full": python_full,
        "node-full": node_full,
        "diff-check": diff_check,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
