#!/usr/bin/env python3
"""Run the T05-0001 evolution backend adapter acceptance checks.

Required checks from manifests/development_manifest.yaml (T05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded in ``review.md`` and the
report.  The adapter ships under src/epistemic_foundry/adapters/v4_t05, so
``wire-literal-discipline`` runs the repository's EF4-I22 gate as its own
check: a new runtime module holding canonical vocabulary must fail here.
``packaging-discovery`` exists because this package introduced a new
``epistemic_foundry.adapters`` marker, which a wheel would otherwise omit.

The dependency regressions cover what T05 composes rather than reimplements:
S05's sealed threat controls supply the execution qualification this adapter
binds to, and the shinka adapter supplies the manifest builder, the
qualification builder, the advisory-signal classification and the EF4-I63
authority-routing refusal.  ``tests/test_shinka_adapter.py`` is run alongside
``tests/test_backend_isolation_and_provenance.py`` because the first covers
``backend.py`` and the second ``isolation.py``, and this package composes both.

``python-full``, ``node-full`` and ``diff-check`` are defined here so the
attempt declares its full gate, but the primary session owns their execution;
this attempt does not run them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/T05/attempts/0001"
ATTEMPT_ID = "T05-0001"
COMPONENT = "artifacts/work_packages/T05/attempts/0001"
ADAPTER = "src/epistemic_foundry/adapters/v4_t05"
DEPENDENCY_TARGETS = {
    "dependency-regression-s05": ("artifacts/work_packages/S05/attempts/0001",),
    "dependency-regression-shinka": (
        "tests/test_backend_isolation_and_provenance.py",
        "tests/test_shinka_adapter.py",
    ),
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
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, ADAPTER]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT, ADAPTER],
    )


def wire_literal_discipline() -> int:
    # EF4-I22 is the invariant a new runtime module is most likely to break,
    # so it runs as a named check rather than only inside the full suite.
    return _pytest("wire-literal-discipline", "tests/test_wire_literal_discipline.py")


def packaging_discovery() -> int:
    # src/epistemic_foundry/adapters is new in this package, so the wheel would
    # omit it without a marker at both levels; this check proves the marker.
    return run(
        "packaging-discovery",
        ["uv", "run", "--locked", "python", "-B", f"{COMPONENT}/check_packaging.py"],
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
    return _pytest("targeted-t05-adapter", COMPONENT)


def dependency_regression_s05() -> int:
    return _pytest(
        "dependency-regression-s05", *DEPENDENCY_TARGETS["dependency-regression-s05"]
    )


def dependency_regression_shinka() -> int:
    name = "dependency-regression-shinka"
    targets = [
        target for target in DEPENDENCY_TARGETS[name] if (ROOT / target).exists()
    ]
    if not targets:
        write_run_result(name, ["pytest", "<no-shinka-suite>"], 2)
        print("no shinka/backend regression suite was found", file=sys.stderr)
        return 2
    return _pytest(name, *targets)


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
        "dependency-regression-s05": dependency_regression_s05,
        "dependency-regression-shinka": dependency_regression_shinka,
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
