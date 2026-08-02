#!/usr/bin/env python3
"""Run M02-0001 checks into attempt-local evidence files only."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M02/attempts/0001"
ATTEMPT_ID = "M02-0001"
M01_TESTS = (
    "packages/workspace-map/src/inventory/map-inventory.test.mjs",
    "packages/workspace-map/src/inventory/edge-resolution.test.mjs",
)
M02_TESTS = (
    "packages/workspace-map/src/ranking/baseline/centrality-reference.test.mjs",
    "packages/workspace-map/src/ranking/baseline/uniform-rank-regression.test.mjs",
)
PRODUCT_FILES = (
    "packages/workspace-map/src/ranking/baseline/baseline-centrality.mjs",
    "packages/workspace-map/src/ranking/baseline/index.mjs",
    *M02_TESTS,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def ensure_metadata() -> None:
    path = ATTEMPT / "attempt-metadata.json"
    if path.is_file():
        return
    write_json(
        path,
        {
            "attempt_id": ATTEMPT_ID,
            "recorded_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "work_package_id": "M02",
        },
    )


def run(
    command: list[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> int:
    executable = command
    if sys.platform == "win32" and command[0] == "npm":
        executable = ["cmd.exe", "/d", "/c", "npm.cmd", *command[1:]]
    completed = subprocess.run(
        executable,
        cwd=ROOT,
        stdout=subprocess.PIPE if stdout_path is not None else None,
        stderr=subprocess.PIPE if stderr_path is not None else None,
        check=False,
    )
    if stdout_path is not None:
        stdout_path.write_bytes(completed.stdout)
    if stderr_path is not None:
        stderr_path.write_bytes(completed.stderr)
    return completed.returncode


def node_test(paths: tuple[str, ...], name: str) -> int:
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *paths],
        stdout_path=ATTEMPT / f"{name}.junit.xml",
        stderr_path=ATTEMPT / f"{name}.junit.xml.stderr.log",
    )


def syntax() -> int:
    node = shutil.which("node")
    if node is None:
        return 127
    rows: list[dict[str, object]] = []
    final = 0
    for relative in PRODUCT_FILES:
        completed = subprocess.run(
            [node, "--check", relative],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        rows.append(
            {
                "exit_code": completed.returncode,
                "path": relative,
                "stderr": completed.stderr,
                "stdout": completed.stdout,
            }
        )
        final = max(final, completed.returncode)
    write_json(
        ATTEMPT / "syntax-verification.json",
        {
            "attempt_id": ATTEMPT_ID,
            "checks": rows,
            "final_status": "PASS" if final == 0 else "FAIL",
        },
    )
    return final


def node_files() -> list[str]:
    return sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )


def node_inventory() -> int:
    files = node_files()
    write_json(
        ATTEMPT / "node-test-inventory.json",
        {
            "attempt_id": ATTEMPT_ID,
            "count": len(files),
            "files": files,
            "unique": len(files) == len(set(files)),
        },
    )
    return 0 if len(files) == len(set(files)) else 2


def full_node() -> int:
    result = node_inventory()
    if result != 0:
        return result
    return node_test(tuple(node_files()), "full-node-suite")


def full_python() -> int:
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
        stdout_path=ATTEMPT / "full-python-suite.junit.xml.stdout.log",
        stderr_path=ATTEMPT / "full-python-suite.junit.xml.stderr.log",
    )


def codegen() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "packages/contracts/codegen/verify.py",
            "--repo-root",
            ".",
        ],
        stdout_path=ATTEMPT / "codegen-verification.stdout.log",
        stderr_path=ATTEMPT / "codegen-verification.stderr.log",
    )


def npm_check(script: str, prefix: str) -> int:
    return run(
        ["npm", "run", script],
        stdout_path=ATTEMPT / f"{prefix}.stdout.log",
        stderr_path=ATTEMPT / f"{prefix}.stderr.log",
    )


def diff_check() -> int:
    return run(
        ["git", "diff", "--check"],
        stdout_path=ATTEMPT / "git-diff-check.stdout.log",
        stderr_path=ATTEMPT / "git-diff-check.stderr.log",
    )


CHECKS = {
    "syntax": syntax,
    "targeted": lambda: node_test(M02_TESTS, "targeted-m02-node"),
    "combined": lambda: node_test((*M01_TESTS, *M02_TESTS), "combined-m01-m02-node"),
    "node-inventory": node_inventory,
    "full-node": full_node,
    "full-python": full_python,
    "codegen": codegen,
    "structure": lambda: npm_check("check:structure", "structure-check"),
    "boundaries": lambda: npm_check("check:boundaries", "boundary-check"),
    "diff-check": diff_check,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=tuple(CHECKS))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    ensure_metadata()
    return CHECKS[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
