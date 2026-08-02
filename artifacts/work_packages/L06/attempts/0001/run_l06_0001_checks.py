#!/usr/bin/env python3
"""Run the L06-0001 memory retention and legal-hold gate acceptance checks.

Required checks from manifests/development_manifest.yaml (L06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is not self-authored and is recorded
by the reviewer.

The gate ships under src/epistemic_foundry/memory/v4_l06, so
``wire-literal-discipline`` runs the repository's EF4-I22 gate as its own
check: a new runtime module holding canonical vocabulary must fail here.

Two dependency regressions guard what this package composes.
``dependency-regression-retention`` re-runs the sealed L05 attempt, because
this gate calls L05's plan, lineage and refusal surfaces directly;
``dependency-regression-memory`` re-runs the composed policy, capsule and
archive suites.  Both assert an exact test count: a regression that silently
loses cases is indistinguishable from one that passes.

The D05 store regression is *not* run here.  It drives a real PostgreSQL
container and the primary session owns that resource; this attempt references
D05 as the owner of the physical delete rather than exercising it.
``python-full``, ``node-full`` and ``diff-check`` are defined for the primary
session and are deliberately not executed by this attempt.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/L06/attempts/0001"
ATTEMPT_ID = "L06-0001"
COMPONENT = "artifacts/work_packages/L06/attempts/0001"
ENGINE = "src/epistemic_foundry/memory/v4_l06"
# L05 is the retention engine this gate composes; the Python memory regression
# covers the policy, capsule and archive modules both packages read from.
DEPENDENCY_TARGETS = {
    "dependency-regression-retention": ("artifacts/work_packages/L05/attempts/0001",),
    "dependency-regression-memory": (
        "tests/test_memory_and_observability.py",
        "tests/test_context_capsule.py",
        "tests/test_epistemic_species_archive.py",
    ),
}
#: A dependency regression that quietly stops collecting cases still reports
#: PASS, so the count is pinned rather than inferred from a green exit code.
EXPECTED_DEPENDENCY_TESTS = {
    "dependency-regression-retention": 72,
    "dependency-regression-memory": 61,
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


def _junit_test_count(name: str) -> int:
    report = ATTEMPT / f"{name}.junit.xml"
    if not report.is_file():
        return -1
    root = ElementTree.parse(report).getroot()
    suites = root.findall("testsuite") or ([root] if root.tag == "testsuite" else [])
    return sum(int(suite.get("tests", "0")) for suite in suites)


def _dependency_regression(name: str) -> int:
    exit_code = _pytest(name, *DEPENDENCY_TARGETS[name])
    if exit_code != 0:
        return exit_code
    expected = EXPECTED_DEPENDENCY_TESTS[name]
    collected = _junit_test_count(name)
    if collected != expected:
        write_run_result(name, ["<collection-rejected>", name], 2)
        print(
            f"expected {expected} tests in {name}, collected {collected}",
            file=sys.stderr,
        )
        return 2
    return 0


def ruff_check() -> int:
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, ENGINE]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT, ENGINE],
    )


def wire_literal_discipline() -> int:
    # EF4-I22 is the invariant a new runtime module is most likely to break, so
    # it runs as a named check rather than only inside the full suite.  The
    # package-local narrowing of the same scan lives in the schema-and-type
    # suite, which is what isolates a failure here to this package or away
    # from it.
    return _pytest("wire-literal-discipline", "tests/test_wire_literal_discipline.py")


def packaging_discovery() -> int:
    # src/epistemic_foundry/memory already ships, so no new marker and no scope
    # decision exist; this check proves that claim instead of assuming it.
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
    return _pytest("targeted-l06-gate", COMPONENT)


def dependency_regression_retention() -> int:
    return _dependency_regression("dependency-regression-retention")


def dependency_regression_memory() -> int:
    return _dependency_regression("dependency-regression-memory")


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
        "dependency-regression-retention": dependency_regression_retention,
        "dependency-regression-memory": dependency_regression_memory,
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
