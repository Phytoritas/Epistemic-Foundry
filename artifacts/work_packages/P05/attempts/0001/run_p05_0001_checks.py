#!/usr/bin/env python3
"""Run the P05-0001 evolution-promotion Parliament gate acceptance checks.

Required checks from manifests/development_manifest.yaml (P05):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one product test module each
under this attempt directory; the review is recorded outside this runner.

The gate ships under src/epistemic_foundry/parliament/v4_p05 behind a NEW
``parliament`` package marker: ``src/epistemic_foundry/parliament`` did not
exist before this package (the sealed P04 Parliament adjudication tree lives
under ``python/epistemic_foundry/parliament``, a separate root), so P05 created
the ``src`` marker as the minimum needed to reach ``v4_p05``.  Both markers are
P05-owned, so lint/format and ``packaging-discovery`` run over the whole
``src/epistemic_foundry/parliament`` subtree, proving the markers actually reach
the wheel rather than only importing from the checkout.

The dependency regressions cover the sealed surfaces this integration gate
composes: P04's evidence-Parliament adjudication (whose canonical adjudication
and its binding-recommendation flag the docket is validated against), O05's
evolution evidence-retrieval surface (whose declared adversarial evidence lanes
must all have been searched), Q05's selective-admissibility gate (whose ADMIT
receipt is the required statistical dimension), and R05's typed-operator surface
(whose candidate lineage kind an intact lineage is validated against).  Each is
exercised through the dependency's own sealed test surface, so a regression in
any of them fails here rather than only inside the full suite.

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
ATTEMPT = ROOT / "artifacts/work_packages/P05/attempts/0001"
ATTEMPT_ID = "P05-0001"
ATTEMPT_DIR = "artifacts/work_packages/P05/attempts/0001"
# P05's write scope is src/epistemic_foundry/parliament/v4_p05/**; the enclosing
# ``parliament`` marker is also P05-owned (P05 created it as a wheel-discovery
# prerequisite), so lint/format run over the whole P05-owned subtree plus this
# attempt directory.
PARLIAMENT = "src/epistemic_foundry/parliament"
PRODUCT_TESTS = {
    "schema-and-type-check": f"{ATTEMPT_DIR}/test_schema_type.py",
    "unit-and-contract-tests": f"{ATTEMPT_DIR}/test_unit_contract.py",
    "negative-and-adversarial-tests": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
    "provenance-and-receipt-audit": f"{ATTEMPT_DIR}/test_provenance_receipt.py",
}
# P05 depends on P04, O05, Q05 and R05.  Each dependency's own sealed test
# surface is the real regression surface: P04 owns the evidence-Parliament
# adjudication whose canonical adjudication the docket is validated against; O05
# owns the retrieval surface whose adversarial lanes must all be searched; Q05
# owns the selective-admissibility gate whose ADMIT receipt is required; R05 owns
# the typed-operator surface whose candidate lineage kind is enforced.  A change
# in any of the four must fail here, so each runs its own sealed suite.
DEPENDENCY_TARGETS = {
    "dependency-regression-p04": ("python/epistemic_foundry/parliament/adjudication",),
    "dependency-regression-o05": ("artifacts/work_packages/O05/attempts/0001",),
    "dependency-regression-q05": ("artifacts/work_packages/Q05/attempts/0001",),
    "dependency-regression-r05": ("artifacts/work_packages/R05/attempts/0001",),
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
        ["uv", "run", "--locked", "ruff", "check", PARLIAMENT, ATTEMPT_DIR],
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", PARLIAMENT, ATTEMPT_DIR],
    )


def packaging_discovery() -> int:
    # src/epistemic_foundry/parliament and .../parliament/v4_p05 are new package
    # markers, so the wheel claim is proved here rather than assumed.
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
    return _pytest("targeted-p05-parliament", ATTEMPT_DIR)


def dependency_regression_p04() -> int:
    return _pytest(
        "dependency-regression-p04", *DEPENDENCY_TARGETS["dependency-regression-p04"]
    )


def dependency_regression_o05() -> int:
    return _pytest(
        "dependency-regression-o05", *DEPENDENCY_TARGETS["dependency-regression-o05"]
    )


def dependency_regression_q05() -> int:
    return _pytest(
        "dependency-regression-q05", *DEPENDENCY_TARGETS["dependency-regression-q05"]
    )


def dependency_regression_r05() -> int:
    return _pytest(
        "dependency-regression-r05", *DEPENDENCY_TARGETS["dependency-regression-r05"]
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
        "dependency-regression-p04": dependency_regression_p04,
        "dependency-regression-o05": dependency_regression_o05,
        "dependency-regression-q05": dependency_regression_q05,
        "dependency-regression-r05": dependency_regression_r05,
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
