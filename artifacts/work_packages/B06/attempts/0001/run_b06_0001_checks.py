#!/usr/bin/env python3
"""Run the B06-0001 reproducible build and backend-pin gate acceptance checks.

Required checks from manifests/development_manifest.yaml (B06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded in ``review.md`` and the
report.

Two checks execute the gate itself rather than a test double.
``reproducible-build`` stages one source snapshot, builds the wheel and the
sdist twice from it, and compares every distribution byte for byte; that is the
real ``uv build`` pair, and it is why the unit suite exercises the comparator
against staged archive trees instead.  ``backend-pin-ledger`` builds the pin
ledger from the sealed declaring sources and re-validates it from its own
bytes.  Both write their receipts under ``build/v4_b06``.

``wire-literal-discipline`` runs the repository's EF4-I22 gate: this package
ships no module under ``src``, so the check is here to prove that claim rather
than to assume it.  ``dependency-regression-b05`` runs the sealed B05 attempt's
own suite, which is the deterministic build profile this gate builds on.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` are defined
here so the primary session can run them; this attempt does not run them.  The
Node inventory is written rather than compared against a hardcoded count,
because the file set moves with packages this attempt neither owns nor gates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B06/attempts/0001"
ATTEMPT_ID = "B06-0001"
COMPONENT = "artifacts/work_packages/B06/attempts/0001"
GATE = f"{COMPONENT}/b06_gate.py"
# B05 sealed the deterministic build profile and the dependency pinning this
# gate builds on; its attempt directory holds the suite that proves it.
DEPENDENCY_TARGETS = {
    "dependency-regression-b05": ("artifacts/work_packages/B05/attempts/0001",),
}


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
    return _pytest("targeted-b06-build-gate", COMPONENT)


def reproducible_build() -> int:
    # The real double build: two uv builds of one staged snapshot, compared
    # byte for byte.  Nothing about this check is simulated.
    return run(
        "reproducible-build",
        ["uv", "run", "--locked", "python", "-B", GATE, "reproducible-build"],
    )


def backend_pin_ledger() -> int:
    return run(
        "backend-pin-ledger",
        ["uv", "run", "--locked", "python", "-B", GATE, "pin-ledger"],
    )


def wire_literal_discipline() -> int:
    return _pytest("wire-literal-discipline", "tests/test_wire_literal_discipline.py")


def dependency_regression_b05() -> int:
    return _pytest(
        "dependency-regression-b05", *DEPENDENCY_TARGETS["dependency-regression-b05"]
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
    if not files:
        write_run_result("full-node-suite", ["node", "--test", "<inventory-empty>"], 2)
        print("the Node inventory is empty", file=sys.stderr)
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
        "reproducible-build": reproducible_build,
        "backend-pin-ledger": backend_pin_ledger,
        "wire-literal-discipline": wire_literal_discipline,
        "dependency-regression-b05": dependency_regression_b05,
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
