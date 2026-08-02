#!/usr/bin/env python3
"""Run the O06-0001 search-completeness / novelty-failure / prior-art gate checks.

Required checks from manifests/development_manifest.yaml (O06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded outside this runner.  The
gate ships under src/epistemic_foundry/retrieval/v4_o06; the ``retrieval``
package marker already existed before this attempt (it carries O05's surface),
so the level that could regress here is the new ``retrieval/v4_o06`` marker, and
``packaging-discovery`` proves it actually reaches the wheel rather than only
importing from the checkout.

O06 depends on O05 and Q05, and each dependency runs as a regression so a change
in a composed dependency surface fails here rather than only inside the full
suite:

* ``dependency-regression-o05`` exercises the sealed O05 evolution retrieval,
  layered-novelty and coverage-debt suite.  O06 reconciles O05's eleven
  canonical lane receipts into the search-completeness certificate and reads its
  lane-state, disposition and lane-order vocabularies from O05, so a regression
  in that surface must surface at this gate.
* ``dependency-regression-q05`` exercises the sealed Q05 multi-objective /
  hidden-evaluation / selective-inference admissibility suite.  O06 composes the
  Q05 admissibility receipt (its ADMIT decision and its own re-derived hash) so a
  candidate reaches review only when a real fitness vector cleared the
  statistical gate; a regression in Q05 must surface here too.

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
ATTEMPT = ROOT / "artifacts/work_packages/O06/attempts/0001"
ATTEMPT_ID = "O06-0001"
ATTEMPT_DIR = "artifacts/work_packages/O06/attempts/0001"
# O06's write scope is src/epistemic_foundry/retrieval/v4_o06/**; the enclosing
# ``retrieval`` package marker pre-dates this attempt and is owned by an earlier
# package, so lint/format run only over the O06-owned subtree plus this attempt
# directory.
RETRIEVAL_V4_O06 = "src/epistemic_foundry/retrieval/v4_o06"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipt.py",
}
# O06 depends on O05 and Q05.  Each dependency's own sealed attempt suite is the
# real regression surface: O05 owns the retrieval, layered-novelty and coverage
# surface whose eleven lane receipts O06 reconciles into the certificate, and Q05
# owns the selective-inference admissibility gate whose sealed receipt O06
# composes.
DEPENDENCY_TARGETS = {
    "dependency-regression-o05": ("artifacts/work_packages/O05/attempts/0001",),
    "dependency-regression-q05": ("artifacts/work_packages/Q05/attempts/0001",),
}
EXPECTED_NODE_FILE_COUNT = 109


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
        ["uv", "run", "--locked", "ruff", "check", RETRIEVAL_V4_O06, ATTEMPT_DIR],
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
            RETRIEVAL_V4_O06,
            ATTEMPT_DIR,
        ],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/retrieval/v4_o06 is a new package marker, so the
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
    return _pytest("targeted-o06-gate", ATTEMPT_DIR)


def dependency_regression_o05() -> int:
    return _pytest(
        "dependency-regression-o05", *DEPENDENCY_TARGETS["dependency-regression-o05"]
    )


def dependency_regression_q05() -> int:
    return _pytest(
        "dependency-regression-q05", *DEPENDENCY_TARGETS["dependency-regression-q05"]
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
        "dependency-regression-o05": dependency_regression_o05,
        "dependency-regression-q05": dependency_regression_q05,
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
