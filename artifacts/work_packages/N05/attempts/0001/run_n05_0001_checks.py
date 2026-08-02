#!/usr/bin/env python3
"""Run the N05-0001 bounded lane scheduler acceptance checks.

Required checks from manifests/development_manifest.yaml (N05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded in ``review.md`` and the
report.  The scheduler ships under src/epistemic_foundry/scheduler/v4_n05, so
``wire-literal-discipline`` runs the repository's EF4-I22 gate as its own
check: a new runtime module holding canonical vocabulary must fail here.

The scheduler composes rather than reimplements two sealed surfaces, so both
carry a named dependency regression: E05 owns the count reconciliation the lane
ledgers feed, and F05 owns the EVOLVE node graph the lane phases are bound
against.  A change to either that this package silently absorbed would show up
there before it showed up in a lane test.

``python-full``, ``node-full`` and ``diff-check`` are defined here for the
primary session, which owns the repository-wide gates; this attempt does not
run them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N05/attempts/0001"
ATTEMPT_ID = "N05-0001"
COMPONENT = "artifacts/work_packages/N05/attempts/0001"
ENGINE = "src/epistemic_foundry/scheduler/v4_n05"
# The scheduler composes E05's reconciliation engine and F05's EVOLVE graph
# loader, so both sealed attempt suites run unchanged as the regression that
# proves this package consumed them rather than forked them.
DEPENDENCY_TARGETS = {
    "dependency-regression-machine": ("artifacts/work_packages/F05/attempts/0001",),
    "dependency-regression-effects": ("artifacts/work_packages/E05/attempts/0001",),
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


def ruff_check() -> int:
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, ENGINE]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT, ENGINE],
    )


def wire_literal_discipline() -> int:
    # EF4-I22 is the invariant a new runtime module is most likely to
    # break, so it runs as a named check rather than only inside the
    # full suite.
    return _pytest("wire-literal-discipline", "tests/test_wire_literal_discipline.py")


def packaging_discovery() -> int:
    # src/epistemic_foundry/scheduler carries a package marker authorized under
    # HD-EF4-N05-SCOPE-20260802-001, and the lane phase binding is package data
    # the scheduler reads at runtime; this check proves both ship.
    return run(
        "packaging-discovery",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            f"{COMPONENT}/check_packaging.py",
        ],
    )


def schema_and_type_check() -> int:
    return _pytest("schema-and-type-check", f"{COMPONENT}/test_schema_and_type.py")


def unit_and_contract_tests() -> int:
    return _pytest("unit-and-contract-tests", f"{COMPONENT}/test_unit_contract.py")


def negative_and_adversarial_tests() -> int:
    return _pytest(
        "negative-and-adversarial-tests", f"{COMPONENT}/test_negative_adversarial.py"
    )


def provenance_and_receipt_audit() -> int:
    return _pytest(
        "provenance-and-receipt-audit", f"{COMPONENT}/test_provenance_receipts.py"
    )


def targeted() -> int:
    return _pytest("targeted-n05-lanes", COMPONENT)


def dependency_regression_machine() -> int:
    return _pytest(
        "dependency-regression-machine",
        *DEPENDENCY_TARGETS["dependency-regression-machine"],
    )


def dependency_regression_effects() -> int:
    return _pytest(
        "dependency-regression-effects",
        *DEPENDENCY_TARGETS["dependency-regression-effects"],
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
        "wire-literal-discipline": wire_literal_discipline,
        "packaging-discovery": packaging_discovery,
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "dependency-regression-machine": dependency_regression_machine,
        "dependency-regression-effects": dependency_regression_effects,
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
