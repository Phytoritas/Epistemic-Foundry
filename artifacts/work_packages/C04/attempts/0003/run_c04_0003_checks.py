#!/usr/bin/env python3
"""Run the raw C04-0003 conformance checks without mutating product files."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C04/attempts/0003"


def run(command: list[str], *, stdout_path: Path | None = None) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE if stdout_path else None,
        stderr=subprocess.PIPE if stdout_path else None,
        check=False,
    )
    if stdout_path is not None:
        stdout_path.write_bytes(process.stdout)
        stderr_path = stdout_path.with_suffix(stdout_path.suffix + ".stderr.log")
        stderr_path.write_bytes(process.stderr)
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
        ]
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
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-contract-conformance.junit.xml'}",
        ]
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": "C04-0003",
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != 52:
        print(f"expected 52 Node tests, found {len(files)}", file=sys.stderr)
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
        stdout_path=ATTEMPT / "full-node-suite.junit.xml",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=("python-full", "python-targeted", "node-full"))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return {
        "python-full": python_full,
        "python-targeted": python_targeted,
        "node-full": node_full,
    }[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
