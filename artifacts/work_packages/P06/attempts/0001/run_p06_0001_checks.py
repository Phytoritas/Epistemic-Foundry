#!/usr/bin/env python3
"""Run the P06-0001 no-majority promotion referral gate acceptance checks.

Required checks from manifests/development_manifest.yaml (P06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded outside this runner.

The gate ships under src/epistemic_foundry/parliament/v4_p06.  P06's write scope
is that package only; the enclosing ``parliament`` namespace marker already
exists (the sealed P05 gate created and owns it), so lint/format run over the
P06-owned ``v4_p06`` package plus this attempt directory, and
``packaging-discovery`` proves ``v4_p06`` actually reaches the wheel rather than
only importing from the checkout.  The gate holds no canonical schema enum
literal, so the repository-wide wire-literal discipline test runs inside the full
Python suite.

The dependency regressions cover the two sealed decision organs this integration
gate composes: P05's evolution-promotion Parliament (whose CONVENE receipt, gate
name, preserved dissent and replication-bounded ceiling the referral reads and
whose ``grants_promotion=false`` boundary it enforces) and V05's validation
cascade (whose ADVANCE receipt is verified as opaque integrity-checked data
against a pinned boundary gate name, so no ``parliament``<->``validation``
component cycle is formed).  Each is exercised through the dependency's own sealed
test surface, so a regression in either fails here rather than only inside the
full suite.

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
ATTEMPT = ROOT / "artifacts/work_packages/P06/attempts/0001"
ATTEMPT_ID = "P06-0001"
ATTEMPT_DIR = "artifacts/work_packages/P06/attempts/0001"
# P06's write scope is src/epistemic_foundry/parliament/v4_p06/**.  The enclosing
# ``parliament`` marker predates P06 (P05 created and owns it), so lint/format run
# over the P06-owned ``v4_p06`` package plus this attempt directory only, leaving
# the sealed P05 files untouched.
V4_P06 = "src/epistemic_foundry/parliament/v4_p06"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipt.py",
}
# P06 depends on P05 and V05.  Each dependency's own sealed test surface is the
# real regression surface: P05 owns the evolution-promotion Parliament whose
# CONVENE receipt, preserved dissent, replication-bounded ceiling and
# ``grants_promotion=false`` boundary the referral composes; V05 owns the
# validation cascade whose ADVANCE receipt the referral verifies as opaque
# integrity-checked data against a pinned gate name.  A change in either must fail
# here, so each runs its own sealed suite.
DEPENDENCY_TARGETS = {
    "dependency-regression-p05": ("artifacts/work_packages/P05/attempts/0001",),
    "dependency-regression-v05": ("artifacts/work_packages/V05/attempts/0001",),
}
EXPECTED_NODE_FILE_COUNT = 111


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
        ["uv", "run", "--locked", "ruff", "check", V4_P06, ATTEMPT_DIR],
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", V4_P06, ATTEMPT_DIR],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/parliament/v4_p06 is a new package under the P06 write
    # scope, so the wheel claim is proved here rather than assumed.
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
    return _pytest("targeted-p06-referral", ATTEMPT_DIR)


def dependency_regression_p05() -> int:
    return _pytest(
        "dependency-regression-p05", *DEPENDENCY_TARGETS["dependency-regression-p05"]
    )


def dependency_regression_v05() -> int:
    return _pytest(
        "dependency-regression-v05", *DEPENDENCY_TARGETS["dependency-regression-v05"]
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
        "dependency-regression-p05": dependency_regression_p05,
        "dependency-regression-v05": dependency_regression_v05,
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
