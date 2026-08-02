#!/usr/bin/env python3
"""Run O02-0002 acceptance and regression checks without mutating product files."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/O02/attempts/0002"


def run(command: list[str], *, stem: str) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (ATTEMPT / f"{stem}.stdout.log").write_bytes(process.stdout)
    (ATTEMPT / f"{stem}.stderr.log").write_bytes(process.stderr)
    return process.returncode


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
            "tests/retrieval/test_o02_retrieval_benchmark.py",
            "tests/retrieval/test_o02_relation_direction.py",
            "tests/retrieval/test_o02_integrity_and_fallback.py",
            "tests/retrieval/test_o02_non_vector_guard.py",
            "python/epistemic_foundry/retrieval/planning/test_query_plan.py",
            "python/epistemic_foundry/retrieval/planning/test_receipt_completeness.py",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-o02-o01-python.junit.xml'}",
        ],
        stem="targeted-o02-o01-python",
    )


def python_o02_only() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/retrieval/test_o02_retrieval_benchmark.py",
            "tests/retrieval/test_o02_relation_direction.py",
            "tests/retrieval/test_o02_integrity_and_fallback.py",
            "tests/retrieval/test_o02_non_vector_guard.py",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'targeted-o02-python.junit.xml'}",
        ],
        stem="targeted-o02-python",
    )


def python_d04_reproduction() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests/recovery/state/test_postgres_backup_restore.py::test_backup_restore_test_postgres_staging_restore_preserves_corrupt_source",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'd04-postgres-race-reproduction.junit.xml'}",
        ],
        stem="d04-postgres-race-reproduction",
    )


def python_full(*, recheck: bool = False) -> int:
    suffix = "-recheck" if recheck else ""
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
            f"--junitxml={ATTEMPT / f'full-python-suite{suffix}.junit.xml'}",
        ],
        stem=f"full-python-suite{suffix}",
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": "O02-0002",
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != 79:
        print(f"expected preserved 79-file Node inventory, found {len(files)}", file=sys.stderr)
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
        stem="full-node-suite",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check",
        choices=(
            "python-o02-only",
            "python-targeted",
            "python-d04-reproduction",
            "python-full",
            "python-full-recheck",
            "node-full",
        ),
    )
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return {
        "python-o02-only": python_o02_only,
        "python-targeted": python_targeted,
        "python-d04-reproduction": python_d04_reproduction,
        "python-full": python_full,
        "python-full-recheck": lambda: python_full(recheck=True),
        "node-full": node_full,
    }[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
