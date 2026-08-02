#!/usr/bin/env python3
"""Run the T03-0001 stable CLI JSON/error and PATH-less acceptance checks.

Required checks from manifests/development_manifest.yaml (T03):
``cli_contract_test`` and ``pathless_cli_test``.  Both are Node test files
under ``packages/plugin-host/src/cli``, so they also join the full Node
inventory rather than being targeted only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/T03/attempts/0001"
ATTEMPT_ID = "T03-0001"
COMPONENT = "packages/plugin-host/src/cli"
ATTEMPT_SCRIPTS = "artifacts/work_packages/T03/attempts/0001"
EXPECTED_NODE_FILE_COUNT = 89


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


def _node(name: str, files: list[str]) -> int:
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
    # The T03 surface is Node; ruff still guards this attempt's own scripts.
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", ATTEMPT_SCRIPTS]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", ATTEMPT_SCRIPTS],
    )


def cli_contract_test() -> int:
    return _node("cli-contract-test", [f"{COMPONENT}/cli-contract.test.mjs"])


def pathless_cli_test() -> int:
    return _node("pathless-cli-test", [f"{COMPONENT}/pathless-cli.test.mjs"])


def targeted() -> int:
    return _node(
        "targeted-cli",
        [
            f"{COMPONENT}/cli-contract.test.mjs",
            f"{COMPONENT}/pathless-cli.test.mjs",
        ],
    )


def dependency_regression_mcp() -> int:
    # T03 derives its command table from the sealed T01/T02 catalogs, so their
    # Node surface is the regression that matters here.
    return _node(
        "dependency-regression-mcp",
        [
            "tests/node/t01-tool-catalog.test.mjs",
            "tests/node/t01-transport-framing.test.mjs",
            "tests/node/t02-mcp-write-surface.test.mjs",
        ],
    )


def dependency_regression_dispatch() -> int:
    return _node(
        "dependency-regression-dispatch",
        [
            "packages/plugin-host/src/cli-dispatch/dispatcher-boundary.test.mjs",
            "packages/plugin-host/src/cli-dispatch/payload-cli-smoke.test.mjs",
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
        "cli-contract-test": cli_contract_test,
        "pathless-cli-test": pathless_cli_test,
        "targeted": targeted,
        "dependency-regression-mcp": dependency_regression_mcp,
        "dependency-regression-dispatch": dependency_regression_dispatch,
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
