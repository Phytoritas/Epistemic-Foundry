#!/usr/bin/env python3
"""Run the Y05-0001 scaling, triage, budget and load-shedding acceptance checks.

Required checks from manifests/development_manifest.yaml (Y05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each under
this attempt directory; the review is a distinct-actor judgement recorded in
``review.md`` outside this runner.  The surface ships under
src/epistemic_foundry/operations/v4_y05 as a new package under the new
``operations`` marker, so ``packaging-discovery`` proves the ``operations`` and
``operations.v4_y05`` markers actually reach the wheel rather than only importing
from the checkout.

Y05 is an integration surface: it composes sealed dependencies (Y01's typed
budgets, Y04's load-shedding measurement, N05's bounded schedule fan-in, Q05's
admissibility gate) and the sealed archive quality-diversity, surrogate and
budget modules.  Those composed surfaces are exercised through
``full-python-suite`` rather than through per-dependency regression runners, so a
regression in any of them still fails here.

Two protective regressions guard the surfaces the new operations module could
disturb without failing its own suite: ``wire-literal-discipline`` re-runs the
wire-literal discipline suite (the surface reads its one triage token positionally
from schema and holds no canonical enum literal), and ``a03-boundary-regression``
re-runs the A03 component import-boundary / cycle-policy check, proving the new
``operations`` top-level package introduces no illegal import edge or cycle.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` reproduce the
repository gate.  The runner never edits any product file and never touches
``.rah/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Y05/attempts/0001"
ATTEMPT_ID = "Y05-0001"
ATTEMPT_DIR = "artifacts/work_packages/Y05/attempts/0001"
SURFACE = "src/epistemic_foundry/operations/v4_y05"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_and_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipts.py",
}
WIRE_LITERAL_TARGET = "tests/test_wire_literal_discipline.py"
A03_BOUNDARY_TARGET = (
    "artifacts/work_packages/A03/attempts/0001/test_boundary_cycle_policy_check.py"
)


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


def packaging_discovery() -> int:
    return run(
        "packaging-discovery",
        ["uv", "run", "--locked", "python", "-B", f"{ATTEMPT_DIR}/check_packaging.py"],
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
    return _pytest("targeted-y05-scaling", ATTEMPT_DIR)


def wire_literal() -> int:
    return _pytest("wire-literal-discipline", WIRE_LITERAL_TARGET)


def a03_boundary_regression() -> int:
    return _pytest("a03-boundary-regression", A03_BOUNDARY_TARGET)


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
        "packaging-discovery": packaging_discovery,
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "wire-literal-discipline": wire_literal,
        "a03-boundary-regression": a03_boundary_regression,
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
            if name == "targeted":
                continue
            code = fn()
            print(f"{name}: exit {code}")
            worst = worst or code
        return worst
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
