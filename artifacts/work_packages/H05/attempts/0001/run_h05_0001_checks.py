#!/usr/bin/env python3
"""Run the H05-0001 evolution/holdout observability acceptance checks.

Required checks from manifests/development_manifest.yaml (H05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one Node test module each in the
product tree; the review is recorded outside this runner.

The observability surface composes the sealed H01 hook gateway and reads the
G05 evolution vocabulary's declaring sources, so both dependencies run as named
regression checks rather than only inside the full suite.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` are defined
here so the repository gate is reproducible, but this attempt does not execute
them: the full suites are owned by the primary session.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/H05/attempts/0001"
ATTEMPT_ID = "H05-0001"
COMPONENT = "plugin_blueprint/epistemic-foundry/hooks/v4_h05"
ATTEMPT_DIR = "artifacts/work_packages/H05/attempts/0001"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{COMPONENT}/observability-schema.test.mjs",
    "unit-and-contract-tests": f"{COMPONENT}/observability-contract.test.mjs",
    "negative-and-adversarial-tests": f"{COMPONENT}/observability-adversarial.test.mjs",
    "provenance-and-receipt-audit": f"{COMPONENT}/observability-receipts.test.mjs",
}
# H01 owns the hook gateway whose host, event-type, decision and coverage
# vocabularies this surface imports; G05 owns the evolution surface whose
# declaring sources it sits beside.  A change in either must fail here.
DEPENDENCY_TARGETS = {
    "dependency-regression-gateway": ("packages/plugin-host/src/hooks/gateway",),
    "dependency-regression-g05": ("plugin_blueprint/epistemic-foundry/v4_g05",),
}
EXPECTED_NODE_FILE_COUNT = 107


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
    return _node("targeted-h05-observability", COMPONENT)


def dependency_regression_gateway() -> int:
    return _node(
        "dependency-regression-gateway",
        *DEPENDENCY_TARGETS["dependency-regression-gateway"],
    )


def dependency_regression_g05() -> int:
    return _node(
        "dependency-regression-g05", *DEPENDENCY_TARGETS["dependency-regression-g05"]
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
    # inventory has to reach it or H05 would be covered by its own targeted run
    # alone.
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (
            ROOT / "adapters",
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
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "dependency-regression-gateway": dependency_regression_gateway,
        "dependency-regression-g05": dependency_regression_g05,
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
