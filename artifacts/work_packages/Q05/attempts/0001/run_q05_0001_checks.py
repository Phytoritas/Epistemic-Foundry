#!/usr/bin/env python3
"""Run the Q05-0001 multi-objective / hidden-evaluation / selective-inference gate checks.

Required checks from manifests/development_manifest.yaml (Q05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded outside this runner.  The
gate ships under src/epistemic_foundry/evaluation/v4_q05; the ``evaluation``
package marker already existed before this attempt, so the level that could
regress here is the new ``evaluation/v4_q05`` marker, and ``packaging-discovery``
proves it actually reaches the wheel rather than only importing from the
checkout.

Q05 depends on Q04, O05 and C05, and each dependency runs as a regression so a
change in a composed dependency surface fails here rather than only inside the
full suite:

* ``dependency-regression-c05`` exercises the sealed C05 evolution schema-family
  bundle suite.  Q05 reads the canonical ``fitness-vector`` vocabulary and
  validates every artifact against schemas that bundle owns, so a schema-family
  regression must surface at this gate.
* ``dependency-regression-o05`` exercises the sealed O05 evolution evidence
  retrieval / novelty-coverage suite that Q05 composes downstream.
* ``dependency-regression-q04`` exercises the sealed Q04 time-sliced adversarial
  benchmark suite.  Q04 ships its harnesses under ``evals/time_sliced`` and
  ``evals/adversarial`` and exports no importable ``epistemic_foundry`` module,
  so there is no src surface to target; its sealed pytest suite in the Q04
  attempt directory is the real regression surface and is used here.

Each dependency regression targets the dependency's own sealed attempt directory
(its committed pytest.ini puts the right roots on the path), mirroring the gold
template's dependency-regression convention.

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
ATTEMPT = ROOT / "artifacts/work_packages/Q05/attempts/0001"
ATTEMPT_ID = "Q05-0001"
ATTEMPT_DIR = "artifacts/work_packages/Q05/attempts/0001"
# Q05's write scope is src/epistemic_foundry/evaluation/v4_q05/**; the enclosing
# ``evaluation`` package marker pre-dates this attempt and is owned by an earlier
# package, so lint/format run only over the Q05-owned subtree plus this attempt
# directory.
EVALUATION_V4_Q05 = "src/epistemic_foundry/evaluation/v4_q05"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipt.py",
}
# Q05 depends on Q04, O05 and C05.  Each dependency's own sealed attempt suite is
# the real regression surface: Q04 ships evals/ harnesses with no importable
# module, so its sealed pytest suite stands in for a src surface it does not
# have; C05 owns the evolution schema-family bundle Q05 validates against; O05
# owns the retrieval/novelty surface Q05 composes downstream.
DEPENDENCY_TARGETS = {
    "dependency-regression-q04": ("artifacts/work_packages/Q04/attempts/0001",),
    "dependency-regression-o05": ("artifacts/work_packages/O05/attempts/0001",),
    "dependency-regression-c05": ("artifacts/work_packages/C05/attempts/0001",),
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
        "ruff-check",
        ["uv", "run", "--locked", "ruff", "check", EVALUATION_V4_Q05, ATTEMPT_DIR],
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
            EVALUATION_V4_Q05,
            ATTEMPT_DIR,
        ],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/evaluation/v4_q05 is a new package marker, so the
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
    return _pytest("targeted-q05-gate", ATTEMPT_DIR)


def dependency_regression_q04() -> int:
    return _pytest(
        "dependency-regression-q04", *DEPENDENCY_TARGETS["dependency-regression-q04"]
    )


def dependency_regression_o05() -> int:
    return _pytest(
        "dependency-regression-o05", *DEPENDENCY_TARGETS["dependency-regression-o05"]
    )


def dependency_regression_c05() -> int:
    return _pytest(
        "dependency-regression-c05", *DEPENDENCY_TARGETS["dependency-regression-c05"]
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
        "dependency-regression-q04": dependency_regression_q04,
        "dependency-regression-o05": dependency_regression_o05,
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
