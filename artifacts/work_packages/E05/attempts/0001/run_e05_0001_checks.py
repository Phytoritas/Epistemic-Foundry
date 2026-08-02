#!/usr/bin/env python3
"""Run the E05-0001 candidate effect reconciliation acceptance checks.

Required checks from manifests/development_manifest.yaml (E05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded in ``review.md`` and the
report.  The engine ships under src/epistemic_foundry/effects/v4_e05, so
``wire-literal-discipline`` runs the repository's EF4-I22 gate as its own
check: a new runtime module holding canonical vocabulary must fail here.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/E05/attempts/0001"
ATTEMPT_ID = "E05-0001"
COMPONENT = "artifacts/work_packages/E05/attempts/0001"
# The engine composes the chamber and ledger surfaces, so their own tests
# are the regression that proves the composition still holds. E04's replay
# gate is a Node surface, so it runs through the Node reporter rather than
# pytest, which would collect nothing from it.
DEPENDENCY_TARGETS = {
    "dependency-regression-chamber": (
        "tests/test_evolution_chamber.py",
        "tests/test_product_invariants.py",
    ),
    "dependency-regression-replay": ("tests/replay/effects",),
}
EXPECTED_NODE_FILE_COUNT = 91


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
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT],
    )


def wire_literal_discipline() -> int:
    # EF4-I22 is the invariant a new runtime module is most likely to
    # break, so it runs as a named check rather than only inside the
    # full suite.
    return _pytest("wire-literal-discipline", "tests/test_wire_literal_discipline.py")


def packaging_discovery() -> int:
    # Without the package marker this engine imports from a checkout but
    # is absent from the wheel (HD-EF4-E05-SCOPE-20260802-001).
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
    return _pytest("targeted-e05-effects", COMPONENT)


def dependency_regression_chamber() -> int:
    return _pytest(
        "dependency-regression-chamber",
        *DEPENDENCY_TARGETS["dependency-regression-chamber"],
    )


def dependency_regression_replay() -> int:
    name = "dependency-regression-replay"
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for target in DEPENDENCY_TARGETS[name]
        for path in (ROOT / target).rglob("*.test.mjs")
        if path.is_file()
    )
    if not files:
        write_run_result(name, ["node", "--test", "<no-files>"], 2)
        print("the replay gate declares no Node test file", file=sys.stderr)
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
        "dependency-regression-chamber": dependency_regression_chamber,
        "dependency-regression-replay": dependency_regression_replay,
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
