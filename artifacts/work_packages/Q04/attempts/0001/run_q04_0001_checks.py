#!/usr/bin/env python3
"""Run the Q04-0001 time-sliced and adversarial benchmark acceptance checks.

Required checks from manifests/development_manifest.yaml (Q04):
``time_slice_test`` and ``false_claim_rejection_test``.  Each maps to one test
module beside the gate it exercises — ``evals/time_sliced/test_time_slice.py``
and ``evals/adversarial/test_false_claim_rejection.py`` — because both eval
components sit outside the repository test path and carry their own
``pytest.ini``.  The four attempt-directory suites (schema and type, unit and
contract, negative and adversarial, provenance and receipts) sit beside this
runner and are targeted only.

``wire-literal-discipline`` runs the repository's EF4-I22 gate as its own named
check.  Nothing new ships under ``src`` in this package, so that check proves
the invariant is untouched rather than newly satisfied.

Every dependency component is run in its own pytest process: ``evals/gold``,
``evals/parsing_claims`` and ``evals/retrieval_verdict`` each declare a module
named ``evaluator`` or ``validator`` at their own root, so a shared invocation
resolves pytest's rootdir above all three and the second component's module
shadows the first.  ``dependency-regression-evals`` therefore drives three
subprocesses and records the worst exit code beside their individual receipts.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` are defined
here so the repository gate can invoke them, but this package does not run
them: the primary session owns the repository-wide gates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Q04/attempts/0001"
ATTEMPT_ID = "Q04-0001"
COMPONENT = "artifacts/work_packages/Q04/attempts/0001"
#: The two benchmark gates this package ships.
ENGINES = ("evals/time_sliced", "evals/adversarial")
#: The sealed Q-phase components Q04 depends on, each with its own pytest root.
DEPENDENCY_COMPONENTS = (
    ("gold", "evals/gold"),
    ("claims", "evals/parsing_claims"),
    ("verdict", "evals/retrieval_verdict"),
)
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
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, *ENGINES]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", COMPONENT, *ENGINES],
    )


def wire_literal_discipline() -> int:
    # EF4-I22 scans src only, and this package adds nothing there; the check
    # runs anyway so "no runtime vocabulary moved" is evidence, not an
    # assumption.
    return _pytest("wire-literal-discipline", "tests/test_wire_literal_discipline.py")


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


def time_slice_test() -> int:
    return _pytest("time-slice-test", f"{ENGINES[0]}/test_time_slice.py")


def false_claim_rejection_test() -> int:
    return _pytest(
        "false-claim-rejection-test", f"{ENGINES[1]}/test_false_claim_rejection.py"
    )


def targeted() -> int:
    return _pytest("targeted-q04-benchmark-gate", COMPONENT)


def dependency_regression_evals() -> int:
    name = "dependency-regression-evals"
    commands: list[list[str]] = []
    worst = 0
    for suffix, component in DEPENDENCY_COMPONENTS:
        child = f"{name}-{suffix}"
        exit_code = _pytest(child, component)
        worst = max(worst, exit_code)
        commands.append(
            json.loads((ATTEMPT / f"{child}.run.json").read_text("utf-8"))["command"]
        )
    (ATTEMPT / f"{name}.stdout.log").write_text(
        "".join(
            (ATTEMPT / f"{name}-{suffix}.stdout.log").read_text(
                encoding="utf-8", errors="replace"
            )
            for suffix, _ in DEPENDENCY_COMPONENTS
        ),
        encoding="utf-8",
        newline="\n",
    )
    (ATTEMPT / f"{name}.stderr.log").write_text("", encoding="utf-8", newline="\n")
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "commands": commands,
        "components": [component for _, component in DEPENDENCY_COMPONENTS],
        "exit_code": worst,
        "status": "PASS" if worst == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return worst


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
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "time-slice-test": time_slice_test,
        "false-claim-rejection-test": false_claim_rejection_test,
        "targeted": targeted,
        "dependency-regression-evals": dependency_regression_evals,
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
