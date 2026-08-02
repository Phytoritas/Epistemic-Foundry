#!/usr/bin/env python3
"""Run the C04-0004 evidence-only conformance checks.

The runner writes only below the C04 attempt directory.  Product files are
never changed, and a failing command is returned verbatim so no downstream
builder or RAH sealer can turn a failed gate into narrative PASS evidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C04/attempts/0004"
ATTEMPT_ID = "C04-0004"
EXPECTED_NODE_FILE_COUNT = 79

TARGETED_PATHS = (
    "tests/contracts/openapi",
    "tests/test_contracts.py",
    "tests/packaging/test_canonical_registry.py",
    "tests/test_cli.py",
    "tests/test_product_invariants.py",
    "tests/test_foundry_kernel.py",
    "tests/test_verifier_firewall.py",
    "tests/test_evidence_parliament.py",
    "tests/test_wire_literal_discipline.py",
    "tests/test_evolution_chamber.py",
    "tests/test_governance.py",
    "tests/test_integration_forge_cycle.py",
    "tests/retrieval",
)


def run(
    command: list[str],
    *,
    stdout_log: Path,
    stderr_log: Path,
    junit_from_stdout: Path | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_log.write_bytes(process.stdout)
    stderr_log.write_bytes(process.stderr)
    if junit_from_stdout is not None:
        junit_from_stdout.write_bytes(process.stdout)
    return process.returncode


def python_full() -> int:
    return run(
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
        stdout_log=ATTEMPT / "full-python-suite.stdout.log",
        stderr_log=ATTEMPT / "full-python-suite.stderr.log",
    )


def python_targeted() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            *TARGETED_PATHS,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-contract-conformance.junit.xml'}",
        ],
        stdout_log=ATTEMPT / "targeted-contract-conformance.stdout.log",
        stderr_log=ATTEMPT / "targeted-contract-conformance.stderr.log",
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": ATTEMPT_ID,
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != EXPECTED_NODE_FILE_COUNT:
        print(
            f"expected {EXPECTED_NODE_FILE_COUNT} Node test files, found {len(files)}",
            file=sys.stderr,
        )
        return 2
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        [
            node,
            "--test",
            "--test-concurrency=1",
            "--test-reporter=junit",
            *files,
        ],
        stdout_log=ATTEMPT / "full-node-suite.stdout.log",
        stderr_log=ATTEMPT / "full-node-suite.stderr.log",
        junit_from_stdout=ATTEMPT / "full-node-suite.junit.xml",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check", choices=("python-full", "python-targeted", "node-full")
    )
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return {
        "python-full": python_full,
        "python-targeted": python_targeted,
        "node-full": node_full,
    }[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
