#!/usr/bin/env python3
"""Run the Z01-0001 fresh-install, compatibility and uninstall matrix checks.

Required checks from ``manifests/development_manifest.yaml`` (Z01):
``install_matrix_test`` and ``uninstall_data_test``.  Each maps to one product
pytest module under ``tests/install`` that composes the deterministic
``tests/install/z01_matrix_harness.py`` engine against the declaring source
``manifests/compatibility_matrix.yaml``.  A third owned check,
``compatibility-matrix-lint``, proves the matrix parses and that every host row
cites sealed evidence.  The harness spawns no host and installs nothing: these
are declared-matrix lifecycle proofs, not real multi-OS installs -- the one real
single-host marketplace lifecycle is composed from the sealed ``G04-0001`` gate.

The scoped ``full-python-suite`` and five-base ``full-node-suite`` regressions
and ``git-diff-check`` are DEFINED here for the integrating session but are NOT
executed by this bounded attempt.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Z01/attempts/0001"
ATTEMPT_ID = "Z01-0001"
ATTEMPT_SCRIPTS = "artifacts/work_packages/Z01/attempts/0001"
PRODUCT = "tests/install"
INSTALL_MATRIX_MODULE = "tests/install/test_install_matrix.py"
UNINSTALL_DATA_MODULE = "tests/install/test_uninstall_data.py"
# Repository-wide Node inventory count observed when this attempt was written.
# The integrating session owns ``node-full`` and updates this pin; the gate is
# zero Node failures across the five bases, never an exact test count.
EXPECTED_NODE_FILE_COUNT = 140


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
        ["uv", "run", "--locked", "ruff", "check", ATTEMPT_SCRIPTS, PRODUCT],
    )


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        [
            "uv",
            "run",
            "--locked",
            "ruff",
            "format",
            "--check",
            ATTEMPT_SCRIPTS,
            PRODUCT,
        ],
    )


def install_matrix_test() -> int:
    return _pytest("install-matrix-test", INSTALL_MATRIX_MODULE)


def uninstall_data_test() -> int:
    return _pytest("uninstall-data-test", UNINSTALL_DATA_MODULE)


def compatibility_matrix_lint() -> int:
    return run(
        "compatibility-matrix-lint",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            f"{ATTEMPT_SCRIPTS}/check_matrix_lint.py",
        ],
    )


def targeted() -> int:
    return _pytest("targeted-z01-install", PRODUCT)


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
        "install-matrix-test": install_matrix_test,
        "uninstall-data-test": uninstall_data_test,
        "compatibility-matrix-lint": compatibility_matrix_lint,
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
