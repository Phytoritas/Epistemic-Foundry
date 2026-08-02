#!/usr/bin/env python3
"""Run the G05-0001 evolution plugin surface acceptance checks.

Required checks from manifests/development_manifest.yaml (G05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one Node test module each in
the product tree; the review is recorded in ``review.md`` and the report.
The surface is a plugin-side Node module that composes the sealed J01 skill
router and T03 command projection, so ``repo-structure-check`` and
``repo-boundaries-check`` run the repository's own component gates as named
checks: a new tree that reached across a declared boundary must fail here.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/G05/attempts/0001"
ATTEMPT_ID = "G05-0001"
COMPONENT = "plugin_blueprint/epistemic-foundry/v4_g05"
ATTEMPT_DIR = "artifacts/work_packages/G05/attempts/0001"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{COMPONENT}/surface-schema.test.mjs",
    "unit-and-contract-tests": f"{COMPONENT}/surface-contract.test.mjs",
    "negative-and-adversarial-tests": f"{COMPONENT}/surface-adversarial.test.mjs",
    "provenance-and-receipt-audit": f"{COMPONENT}/surface-receipts.test.mjs",
}
# The surface composes J01's routing policy and T03's command projection, and
# G04 is the install gate the plugin payload has to keep passing.  C05 owns the
# sealed mutable search space, and J02 owns the inventory budgets this surface
# enforces.
DEPENDENCY_TARGETS = {
    "dependency-regression-host": (
        "packages/plugin-host/src/skill-router",
        "packages/plugin-host/src/cli",
    ),
    "dependency-regression-install": ("tests/install/local-marketplace",),
    "dependency-regression-c05": ("artifacts/work_packages/C05/attempts/0001",),
    "dependency-regression-plugin": (
        "tests/test_j02_context_budget.py",
        "tests/test_plugin_shell.py",
    ),
}
EXPECTED_NODE_FILE_COUNT = 95


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


def _pytest(name: str, *targets: str) -> int:
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
            *targets,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
    )


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


def _repo_check(name: str, script: str) -> int:
    # The surface is the first product tree outside packages/ that reads the
    # host component source, so the repository's own gates run as named checks
    # rather than only inside the full suite.
    node = shutil.which("node")
    command = ["node", f"packages/repo-checks/{script}"]
    if node is None:
        write_run_result(name, command, 127)
        return 127
    return run(name, [node, command[1]])


def repo_structure_check() -> int:
    return _repo_check("repo-structure-check", "check-structure.mjs")


def repo_boundaries_check() -> int:
    return _repo_check("repo-boundaries-check", "check-boundaries.mjs")


def schema_and_type_check() -> int:
    return _node("schema-and-type-check", PRODUCT_TESTS["schema-and-type-check"])


def unit_and_contract_tests() -> int:
    return _node("unit-and-contract-tests", PRODUCT_TESTS["unit-and-contract-tests"])


def negative_and_adversarial_tests() -> int:
    return _node(
        "negative-and-adversarial-tests",
        PRODUCT_TESTS["negative-and-adversarial-tests"],
    )


def provenance_and_receipt_audit() -> int:
    return _node(
        "provenance-and-receipt-audit", PRODUCT_TESTS["provenance-and-receipt-audit"]
    )


def targeted() -> int:
    return _node("targeted-g05-surface", COMPONENT)


def dependency_regression_host() -> int:
    return _node(
        "dependency-regression-host", *DEPENDENCY_TARGETS["dependency-regression-host"]
    )


def dependency_regression_install() -> int:
    return _node(
        "dependency-regression-install",
        *DEPENDENCY_TARGETS["dependency-regression-install"],
    )


def dependency_regression_c05() -> int:
    return _pytest(
        "dependency-regression-c05", *DEPENDENCY_TARGETS["dependency-regression-c05"]
    )


def dependency_regression_plugin() -> int:
    return _pytest(
        "dependency-regression-plugin",
        *DEPENDENCY_TARGETS["dependency-regression-plugin"],
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
    # The product tree lives outside packages/, so the repository-wide Node
    # inventory has to reach it or G05 would be covered by its own targeted run
    # alone.
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (
            ROOT / "packages",
            ROOT / "plugin_blueprint",
            ROOT / "tests",
            ROOT / "web",
        )
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
        "repo-structure-check": repo_structure_check,
        "repo-boundaries-check": repo_boundaries_check,
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "dependency-regression-host": dependency_regression_host,
        "dependency-regression-install": dependency_regression_install,
        "dependency-regression-c05": dependency_regression_c05,
        "dependency-regression-plugin": dependency_regression_plugin,
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
