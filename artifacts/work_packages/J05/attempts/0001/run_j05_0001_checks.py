#!/usr/bin/env python3
"""Run the J05-0001 typed mutation-operator registry acceptance checks.

Required checks from manifests/development_manifest.yaml (J05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded outside this runner.  The
registry ships under src/epistemic_foundry/operators/v4_j05 behind a new
``operators`` package marker (authorized HD-EF4-J05-SCOPE-20260802-001), so
``packaging-discovery`` proves the marker actually reaches the wheel rather than
only importing from the checkout.

The dependency regressions cover the sealed surfaces this package composes:
I05's intake surface, whose sealed mutable-genome kinds an operator's declared
kinds and the prompt-genome kind are validated against; C05's evolution family,
whose evolution-candidate/genome schemas and the ``evolution_chamber.mutation``
authority check J05 reads through (``apply_mutation`` /
``AuthorityMutationRefused``); and J04's post-compaction recovery gate, which
ships only Node golden tests under ``tests/golden/compaction`` (there is no
``operators.v4_j04`` Python surface to import), exercised through those very
tests so a regression in the recovery oracle fails here.  I05 and the C05
evolution family run their own pytest suites; J04 runs its Node golden tests.

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
ATTEMPT = ROOT / "artifacts/work_packages/J05/attempts/0001"
ATTEMPT_ID = "J05-0001"
ATTEMPT_DIR = "artifacts/work_packages/J05/attempts/0001"
COMPONENT = "src/epistemic_foundry/operators"
V4_J05 = "src/epistemic_foundry/operators/v4_j05"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_and_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipt.py",
}
# I05 owns the intake surface whose sealed mutable-genome kinds the operators and
# the prompt-genome kind are validated against; C05's evolution family owns the
# evolution-candidate/genome schemas and the evolution_chamber.mutation authority
# check J05 reads through.  A change in either must fail here, so each runs its
# own sealed pytest suite.  J04 ships only Node golden compaction tests.
DEPENDENCY_PYTEST_TARGETS = {
    "dependency-regression-i05": ("artifacts/work_packages/I05/attempts/0001",),
    "dependency-regression-c05": (
        "tests/test_evolution_chamber.py",
        "tests/test_genome_and_refutation.py",
        "tests/test_crossover_and_quarantine.py",
    ),
}
# J04 is the post-compaction recovery gate; its product is Node golden tests
# under tests/golden/compaction, so its dependency regression is a Node run.
DEPENDENCY_NODE_TARGETS = {
    "dependency-regression-j04": (
        "tests/golden/compaction/compaction-resume.test.mjs",
        "tests/golden/compaction/context-poisoning.test.mjs",
    ),
}
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


def _node(name: str, *files: str) -> int:
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
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", V4_J05, ATTEMPT_DIR]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", V4_J05, ATTEMPT_DIR],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/operators is a new package marker authorized under
    # HD-EF4-J05-SCOPE-20260802-001, so the wheel claim is proved here rather
    # than assumed.
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
    return _pytest("targeted-j05-operators", ATTEMPT_DIR)


def dependency_regression_i05() -> int:
    return _pytest(
        "dependency-regression-i05",
        *DEPENDENCY_PYTEST_TARGETS["dependency-regression-i05"],
    )


def dependency_regression_c05() -> int:
    return _pytest(
        "dependency-regression-c05",
        *DEPENDENCY_PYTEST_TARGETS["dependency-regression-c05"],
    )


def dependency_regression_j04() -> int:
    return _node(
        "dependency-regression-j04",
        *DEPENDENCY_NODE_TARGETS["dependency-regression-j04"],
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
        "dependency-regression-i05": dependency_regression_i05,
        "dependency-regression-j04": dependency_regression_j04,
        "dependency-regression-c05": dependency_regression_c05,
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
