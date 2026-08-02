#!/usr/bin/env python3
"""Run the T04-0001 sandbox and external tool adapter gate acceptance checks.

Required checks from manifests/development_manifest.yaml (T04):
``sandbox_escape_test`` and ``tool_receipt_test``.  Both are component tests
under ``python/epistemic_foundry/tools/sandbox``, which is outside the
repository test path and therefore targeted only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/T04/attempts/0001"
ATTEMPT_ID = "T04-0001"
COMPONENT = "python/epistemic_foundry/tools/sandbox"
# T02's write surface is exercised from tests/node; T03's from beside its own
# sources.  Each entry is the test target for one dependency, not its source
# directory, so a regression is attributed to the package that owns it.
DEPENDENCY_COMPONENTS = (
    "tests/node/t02-mcp-write-surface.test.mjs",
    "packages/plugin-host/src/cli",
)
EXPECTED_NODE_FILE_COUNT = 91


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


def _pytest(name: str, target: str) -> int:
    return run(
        name,
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            target,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
    )


def _node_tests(name: str, component: str) -> int:
    target = ROOT / component
    files = (
        [target.relative_to(ROOT).as_posix()]
        if target.is_file()
        else sorted(
            path.relative_to(ROOT).as_posix()
            for path in target.rglob("*.test.mjs")
            if path.is_file()
        )
    )
    if not files:
        write_run_result(name, ["node", "--test", "<no-files>"], 2)
        print(f"{component} declares no Node test file", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if node is None:
        write_run_result(name, ["node", "--test", *files], 127)
        return 127
    return run(
        name,
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / f"{name}.junit.xml",
    )


def ruff_check() -> int:
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT],
    )


def sandbox_escape_test() -> int:
    return _pytest("sandbox-escape-test", f"{COMPONENT}/test_sandbox_escape.py")


def tool_receipt_test() -> int:
    return _pytest("tool-receipt-test", f"{COMPONENT}/test_tool_receipt.py")


def targeted() -> int:
    return _pytest("targeted-tool-sandbox", COMPONENT)


def dependency_regression_mcp_write() -> int:
    # T04 depends on T02 and T03, whose surfaces are Node rather than Python,
    # so each dependency regression runs that component's own .test.mjs files.
    return _node_tests("dependency-regression-mcp-write", DEPENDENCY_COMPONENTS[0])


def dependency_regression_cli() -> int:
    return _node_tests("dependency-regression-cli", DEPENDENCY_COMPONENTS[1])


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
        "sandbox-escape-test": sandbox_escape_test,
        "tool-receipt-test": tool_receipt_test,
        "targeted": targeted,
        "dependency-regression-mcp-write": dependency_regression_mcp_write,
        "dependency-regression-cli": dependency_regression_cli,
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
