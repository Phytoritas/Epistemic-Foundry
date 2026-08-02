#!/usr/bin/env python3
"""Run the Y03-0001 backup, disaster-recovery and operational-runbook checks.

Required checks from manifests/development_manifest.yaml (Y03):
``disaster_recovery_drill`` and ``runbook_lint``.  Both are Node test files
under ``tests/recovery/production``.  ``runbook_lint`` fail-closed-lints the
shipped operational runbooks under ``ops/runbooks`` (exact ordered sections,
quantified RPO/RTO, imperative + Verify-complete steps, placeholder rejection),
and ``disaster_recovery_drill`` runs an honest end-to-end restore drill in
process over the sealed D01/D02 SQLite state store and the sealed D03
content-addressed artifact store using the sealed D04 recovery fixtures: real
backup, post-backup writes, corruption of both primaries, hash/manifest-checked
restore, and RPO/RTO measured against the budgets parsed from the runbook.
Because the drill exercises the wider kernel and recovery surface, both files
also enter the full Node inventory rather than being targeted only; the whole
upstream Node tree is the regression that matters, so it is covered by the full
Node suite rather than a bespoke dependency-regression run.  The drill runs
fully in process on the kernel SQLite and artifact stores and needs no external
database, container, or Docker daemon.  Ruff still guards this attempt's own
Python scripts, so the Python toolchain must be resolvable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Y03/attempts/0001"
ATTEMPT_ID = "Y03-0001"
COMPONENT = "tests/recovery/production"
ATTEMPT_SCRIPTS = "artifacts/work_packages/Y03/attempts/0001"
# The repository-wide Node inventory count observed when this attempt was
# written.  The integrating session owns ``node-full`` and updates this pin
# when other trees add or remove test modules; the gate is zero Node failures,
# never an exact test count.
EXPECTED_NODE_FILE_COUNT = 115


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


def _node(name: str, files: list[str]) -> int:
    node = shutil.which("node")
    if node is None:
        write_run_result(name, ["node", "--test", *files], 127)
        return 127
    return run(
        name,
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / f"{name}.junit.xml",
    )


def ruff_check() -> int:
    # The Y03 surface is Node runbooks and fixtures; ruff still guards this
    # attempt's own scripts.
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", ATTEMPT_SCRIPTS]
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", ATTEMPT_SCRIPTS],
    )


def disaster_recovery_drill() -> int:
    return _node(
        "disaster-recovery-drill", [f"{COMPONENT}/disaster-recovery-drill.test.mjs"]
    )


def runbook_lint() -> int:
    return _node("runbook-lint", [f"{COMPONENT}/runbook-lint.test.mjs"])


def targeted() -> int:
    # Equivalent to `node --test tests/recovery/production/*.test.mjs`, expanded
    # to explicit sorted files so the run is deterministic and shell-independent.
    return _node(
        "targeted-recovery-production",
        [
            f"{COMPONENT}/disaster-recovery-drill.test.mjs",
            f"{COMPONENT}/runbook-lint.test.mjs",
        ],
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
        "disaster-recovery-drill": disaster_recovery_drill,
        "runbook-lint": runbook_lint,
        "targeted": targeted,
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
