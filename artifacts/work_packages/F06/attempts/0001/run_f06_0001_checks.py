#!/usr/bin/env python3
"""Run the F06-0001 FORGE-EVOLVE lifecycle and replay integration gate checks.

Required checks from manifests/development_manifest.yaml (F06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded outside this runner.  The
gate ships under src/epistemic_foundry/evolution/v4_f06; the ``evolution``
package marker already existed before this attempt (created by F05), so the
level that could regress here is the new ``evolution/v4_f06`` marker, and
``packaging-discovery`` proves it actually reaches the wheel rather than only
importing from the checkout.

F06 depends on F05, I05 and R05, whose sealed surfaces the gate composes: the
F05 EVOLVE state machine walks the run's lifecycle and stop certificate, I05
genome intake screens and reconciles the seed population, and the R05 typed
operator registry declares every operator the run applied.  Each dependency's
product tests live in its own sealed attempt directory, so the three dependency
regressions exercise those sealed suites, and a regression in any composed
surface fails here rather than only inside the full suite.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` reproduce the
repository gate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F06/attempts/0001"
ATTEMPT_ID = "F06-0001"
ATTEMPT_DIR = "artifacts/work_packages/F06/attempts/0001"
# F06's write scope is src/epistemic_foundry/evolution/v4_f06/**; the enclosing
# ``evolution`` package marker pre-dates this attempt and is owned by F05, so
# lint/format run only over the F06-owned subtree plus this attempt directory.
EVOLUTION_V4_F06 = "src/epistemic_foundry/evolution/v4_f06"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipt.py",
}
# F05 owns the EVOLVE state machine whose lifecycle and stop-certificate verdict
# the gate composes; I05 owns the genome intake whose seed screening and
# reconciliation the gate composes; R05 owns the typed operator registry every
# applied operator must resolve to.  A change in any of the three must fail here,
# so each runs its own sealed attempt suite as a dependency regression.
DEPENDENCY_TARGETS = {
    "dependency-regression-f05": ("artifacts/work_packages/F05/attempts/0001",),
    "dependency-regression-i05": ("artifacts/work_packages/I05/attempts/0001",),
    "dependency-regression-r05": ("artifacts/work_packages/R05/attempts/0001",),
}
# The Node implementation and its ``*.test.mjs`` suites are untracked
# working-tree content (the repo tracks the blueprint, not the built surface),
# so this inventory guard reflects the current tree rather than a git baseline.
# R05/R06 sealed at 102; five further green suites (role-router routing and
# fallback-provenance, and the aporia/parliament/passport web views) were added
# by parallel work since, so the live surface F06 verifies against is 107.
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
        "ruff-check",
        ["uv", "run", "--locked", "ruff", "check", EVOLUTION_V4_F06, ATTEMPT_DIR],
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        [
            "uv",
            "run",
            "--locked",
            "ruff",
            "format",
            "--check",
            EVOLUTION_V4_F06,
            ATTEMPT_DIR,
        ],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/evolution/v4_f06 is a new package marker, so the
    # wheel claim is proved here rather than assumed.
    return run(
        "packaging-discovery",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            f"{ATTEMPT_DIR}/check_packaging.py",
        ],
    )


def schema_and_type_check() -> int:
    return _pytest("schema-and-type-check", PRODUCT_TESTS["schema-and-type-check"])


def unit_and_contract_tests() -> int:
    return _pytest("unit-and-contract-tests", PRODUCT_TESTS["unit-and-contract-tests"])


def negative_and_adversarial_tests() -> int:
    return _pytest(
        "negative-and-adversarial-tests",
        PRODUCT_TESTS["negative-and-adversarial-tests"],
    )


def provenance_and_receipt_audit() -> int:
    return _pytest(
        "provenance-and-receipt-audit", PRODUCT_TESTS["provenance-and-receipt-audit"]
    )


def targeted() -> int:
    return _pytest("targeted-f06-gate", ATTEMPT_DIR)


def dependency_regression_f05() -> int:
    return _pytest(
        "dependency-regression-f05", *DEPENDENCY_TARGETS["dependency-regression-f05"]
    )


def dependency_regression_i05() -> int:
    return _pytest(
        "dependency-regression-i05", *DEPENDENCY_TARGETS["dependency-regression-i05"]
    )


def dependency_regression_r05() -> int:
    return _pytest(
        "dependency-regression-r05", *DEPENDENCY_TARGETS["dependency-regression-r05"]
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
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "expected": EXPECTED_NODE_FILE_COUNT,
                "files": files,
            },
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
        "packaging-discovery": packaging_discovery,
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "dependency-regression-f05": dependency_regression_f05,
        "dependency-regression-i05": dependency_regression_i05,
        "dependency-regression-r05": dependency_regression_r05,
        "full-python-suite": python_full,
        "full-node-suite": node_full,
        "git-diff-check": diff_check,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
