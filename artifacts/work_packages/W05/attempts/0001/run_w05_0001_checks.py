#!/usr/bin/env python3
"""Run the W05-0001 checkpoint resume, cancel and evaluator-drift reassessment checks.

Required checks from manifests/development_manifest.yaml (W05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is not self-authored and is recorded
by the reviewer outside this runner.  The workflow ships under
src/epistemic_foundry/recovery/v4_w05 behind a new ``recovery`` package marker,
so ``packaging-discovery`` proves the marker actually reaches the wheel rather
than only importing from the checkout.

Four dependency regressions guard the sealed surfaces this package composes.
``dependency-regression-w04`` re-runs W04's replay/drift Node suite (the audit
export and drift verdict this workflow's cancel/resume records lean on);
``dependency-regression-d05`` re-runs the sealed D05 transactional-store attempt
(a real PostgreSQL container it provisions through Docker), which owns the store
a checkpoint is committed to; ``dependency-regression-f05`` re-runs the sealed
F05 EVOLVE state machine, because resume legality *is* that machine's judgment
and this package hands it the resumed run; ``dependency-regression-n05`` re-runs
the sealed N05 bounded lane scheduler, which owns the lane and phase binding a
resumed run re-enters.  W04's surface is Node and the other three are pytest, so
each runs under its own tool; a regression in any of them fails here rather than
only inside the full suite.

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
ATTEMPT = ROOT / "artifacts/work_packages/W05/attempts/0001"
ATTEMPT_ID = "W05-0001"
ATTEMPT_DIR = "artifacts/work_packages/W05/attempts/0001"
#: The recovery component; ``v4_w05`` is the write scope and the marker one level
#: above it is a mandatory wheel-discovery prerequisite (proven by
#: ``check_packaging.py``).  Ruff lints the whole component so the marker is
#: covered too.
COMPONENT = "src/epistemic_foundry/recovery"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_and_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipts.py",
}
# F05 owns the EVOLVE state machine this workflow hands its resumed run to; N05
# owns the lane and phase binding that run re-enters; D05 owns the transactional
# store a checkpoint is committed to.  All three are sealed pytest attempts, so
# re-running them is what proves this package did not disturb them.  D05 drives a
# real PostgreSQL container through Docker.
PYTEST_DEPENDENCY_TARGETS = {
    "dependency-regression-d05": ("artifacts/work_packages/D05/attempts/0001",),
    "dependency-regression-f05": ("artifacts/work_packages/F05/attempts/0001",),
    "dependency-regression-n05": ("artifacts/work_packages/N05/attempts/0001",),
}
# W04's sealed surface is the replay/drift Node suite whose audit export and
# drift verdict this workflow's cancel and resume records depend on.
NODE_DEPENDENCY_TARGETS = {
    "dependency-regression-w04": (
        "packages/foundry-kernel/src/replay/replay-drift.test.mjs",
        "packages/foundry-kernel/src/replay/audit-export.test.mjs",
    ),
}
#: The repository Node gate this DAG level runs (matching the sealed R05
#: baseline): every ``*.test.mjs`` under these bases.
NODE_BASES = ("packages", "tests", "web")
EXPECTED_NODE_FILE_COUNT = 102


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


def _node(name: str, files: tuple[str, ...]) -> int:
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
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, ATTEMPT_DIR]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT, ATTEMPT_DIR],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/recovery is a new package marker for this phase, so
    # the wheel claim is proved here rather than assumed.
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
    return _pytest("targeted-w05-workflow", ATTEMPT_DIR)


def dependency_regression_w04() -> int:
    return _node(
        "dependency-regression-w04",
        NODE_DEPENDENCY_TARGETS["dependency-regression-w04"],
    )


def dependency_regression_d05() -> int:
    return _pytest(
        "dependency-regression-d05",
        *PYTEST_DEPENDENCY_TARGETS["dependency-regression-d05"],
    )


def dependency_regression_f05() -> int:
    return _pytest(
        "dependency-regression-f05",
        *PYTEST_DEPENDENCY_TARGETS["dependency-regression-f05"],
    )


def dependency_regression_n05() -> int:
    return _pytest(
        "dependency-regression-n05",
        *PYTEST_DEPENDENCY_TARGETS["dependency-regression-n05"],
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
        for base in NODE_BASES
        if (ROOT / base).is_dir()
        for path in (ROOT / base).rglob("*.test.mjs")
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
        "dependency-regression-w04": dependency_regression_w04,
        "dependency-regression-d05": dependency_regression_d05,
        "dependency-regression-f05": dependency_regression_f05,
        "dependency-regression-n05": dependency_regression_n05,
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
