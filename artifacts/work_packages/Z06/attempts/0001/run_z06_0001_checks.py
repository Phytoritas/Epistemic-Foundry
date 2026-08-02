#!/usr/bin/env python3
"""Run the Z06-0001 terminal release composition checks.

Required checks from manifests/development_manifest.yaml (Z06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each under
this attempt directory; the review is a distinct-actor judgement recorded in
``review.md`` outside this runner.  The surface ships under ``release/v4_z06`` —
outside the ``src`` package tree, so it is not part of the wheel and is not
collected by ``pytest tests``; its product tests run solely through this runner.

Z06 is the terminal composition gate: it composes the sealed Z05 zero-trust
release (read from its frozen sealed report, not re-run — exactly as Z05 composed
Z04) and the thirteen sealed ``*06`` integration gates into one terminal verdict
that proves a declared bundle clean-extracts and refuses zip-slip/tampered/surplus
members, that every source states the maturity honestly at the acceptance-matrix
floor, and that every composed package is sealed PASS with completion never
claimed.  Two protective dependency regressions run composed dependency attempt
suites directly, so a break in a composed surface fails here rather than only in
its own package: ``dependency-regression-release`` runs the sealed Z05 attempt
suite (the engine this gate composes) and ``dependency-regression-operations``
runs the sealed Y06 attempt suite (one of the thirteen ``*06`` gates).
``wire-literal-discipline`` re-runs the repository wire-literal discipline suite;
the terminal module reads its status token and maturity floor through the composed
Z05 surface and derives the signing status through the sealed provenance surface,
holding no canonical enum literal of its own.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` reproduce the
repository gate.  They are DEFINED here but are NOT executed by this owner; the
integrating session runs them.  The runner never edits any product file and never
touches ``.rah/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Z06/attempts/0001"
ATTEMPT_ID = "Z06-0001"
ATTEMPT_DIR = "artifacts/work_packages/Z06/attempts/0001"
SURFACE = "release/v4_z06"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_and_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipts.py",
}
WIRE_LITERAL_TARGET = "tests/test_wire_literal_discipline.py"
Z05_ATTEMPT_DIR = "artifacts/work_packages/Z05/attempts/0001"
Y06_ATTEMPT_DIR = "artifacts/work_packages/Y06/attempts/0001"

#: Checks defined for reproducing the repository gate but never executed by this
#: owner; the integrating session runs them.
NOT_EXECUTED_BY_OWNER = ("full-python-suite", "full-node-suite", "git-diff-check")


def resolve_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    fallback = Path(r"C:\Program Files\nodejs\node.EXE")
    return str(fallback) if fallback.is_file() else None


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
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", SURFACE, ATTEMPT_DIR]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", SURFACE, ATTEMPT_DIR],
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
    return _pytest("targeted-z06-release", ATTEMPT_DIR)


def wire_literal() -> int:
    return _pytest("wire-literal-discipline", WIRE_LITERAL_TARGET)


def dependency_regression_release() -> int:
    return _pytest("dependency-regression-release", Z05_ATTEMPT_DIR)


def dependency_regression_operations() -> int:
    return _pytest("dependency-regression-operations", Y06_ATTEMPT_DIR)


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
    node = resolve_node()
    if node is None:
        write_run_result("full-node-suite", ["node", "--test", *files], 127)
        print("node executable not found", file=sys.stderr)
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
        "wire-literal-discipline": wire_literal,
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "dependency-regression-release": dependency_regression_release,
        "dependency-regression-operations": dependency_regression_operations,
        "full-python-suite": python_full,
        "full-node-suite": node_full,
        "git-diff-check": diff_check,
    }
    parser.add_argument("check", choices=(*tuple(checks), "all"))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    if args.check == "all":
        worst = 0
        for name, fn in checks.items():
            # The three repository-gate checks are defined but left for the
            # integrating session; this owner does not execute them.
            if name in NOT_EXECUTED_BY_OWNER:
                continue
            code = fn()
            print(f"{name}: exit {code}")
            worst = worst or code
        return worst
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
