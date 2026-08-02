#!/usr/bin/env python3
"""Run the X01-0001 Codex plugin, hook and subagent adapter acceptance checks.

Required checks from manifests/development_manifest.yaml (X01):
``codex_adapter_test`` and ``codex_hook_coverage_test``, plus the
``independent_review`` this package declares.  The adapter tree carries four
Node test modules, and each required check maps onto two of them: the adapter
test is covered by ``codex-schema-check`` (the vocabulary the adapter reads
rather than restates) and ``codex-adapter-test`` (what it does with the payload
that ships); the hook coverage test is covered by ``codex-adversarial-tests``
(one broken input at a time) and ``codex-hook-coverage-test`` (the receipt that
publishes the coverage of every canonical event type, including the ones this
payload registers for none).  The review is recorded in ``review.md``.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` are defined
here so the attempt names its whole gate, but this attempt does not run them:
the repository-wide suites belong to the integrating session.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/X01/attempts/0001"
ATTEMPT_ID = "X01-0001"
COMPONENT = "adapters/codex"
ATTEMPT_DIR = "artifacts/work_packages/X01/attempts/0001"
PRODUCT_TESTS = {
    "codex-schema-check": f"{COMPONENT}/codex-schema.test.mjs",
    "codex-adapter-test": f"{COMPONENT}/codex-contract.test.mjs",
    "codex-adversarial-tests": f"{COMPONENT}/codex-adversarial.test.mjs",
    "codex-hook-coverage-test": f"{COMPONENT}/codex-receipts.test.mjs",
}
# The adapter composes H01's hook gateway (event types, hosts, coverage classes,
# envelope validation and canonical hashing) and validates the payload G04's
# local-marketplace install gate has to keep accepting.
DEPENDENCY_TARGETS = {
    "dependency-regression-gateway": ("packages/plugin-host/src/hooks/gateway",),
    "dependency-regression-install": ("tests/install/local-marketplace",),
}
# The repository-wide Node inventory has to reach adapters/, or the adapter
# would be covered by its own targeted run alone.  The count is the inventory
# observed when this attempt was written; the integrating session owns
# ``node-full`` and updates it when other trees add or remove test modules.
EXPECTED_NODE_FILE_COUNT = 107
NODE_INVENTORY_ROOTS = ("adapters", "packages", "plugin_blueprint", "tests", "web")


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


def _node(name: str, *targets: str) -> int:
    files: list[str] = []
    for target in targets:
        path = ROOT / target
        if path.is_file():
            files.append(target)
            continue
        files.extend(
            candidate.relative_to(ROOT).as_posix()
            for candidate in path.rglob("*.test.mjs")
            if candidate.is_file()
        )
    files = sorted(set(files))
    if not files:
        write_run_result(name, ["node", "--test", "<no-files>"], 2)
        print(f"{name} declares no Node test file", file=sys.stderr)
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
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", ATTEMPT_DIR])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", ATTEMPT_DIR],
    )


def codex_schema_check() -> int:
    return _node("codex-schema-check", PRODUCT_TESTS["codex-schema-check"])


def codex_adapter_test() -> int:
    return _node("codex-adapter-test", PRODUCT_TESTS["codex-adapter-test"])


def codex_adversarial_tests() -> int:
    return _node("codex-adversarial-tests", PRODUCT_TESTS["codex-adversarial-tests"])


def codex_hook_coverage_test() -> int:
    return _node("codex-hook-coverage-test", PRODUCT_TESTS["codex-hook-coverage-test"])


def targeted() -> int:
    return _node("targeted-x01-codex", COMPONENT)


def dependency_regression_gateway() -> int:
    return _node(
        "dependency-regression-gateway",
        *DEPENDENCY_TARGETS["dependency-regression-gateway"],
    )


def dependency_regression_install() -> int:
    return _node(
        "dependency-regression-install",
        *DEPENDENCY_TARGETS["dependency-regression-install"],
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
        for base in (ROOT / name for name in NODE_INVENTORY_ROOTS)
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
        "codex-schema-check": codex_schema_check,
        "codex-adapter-test": codex_adapter_test,
        "codex-adversarial-tests": codex_adversarial_tests,
        "codex-hook-coverage-test": codex_hook_coverage_test,
        "targeted": targeted,
        "dependency-regression-gateway": dependency_regression_gateway,
        "dependency-regression-install": dependency_regression_install,
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
