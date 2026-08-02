#!/usr/bin/env python3
"""Run the Z02-0001 SBOM, signing, provenance and deterministic-bundle checks.

Required checks from ``manifests/development_manifest.yaml`` (Z02):
``sbom_test``, ``signature_test`` and ``zip_integrity_test``.  Each maps to one
product pytest module under ``scripts/release`` that composes the deterministic
``scripts/release/z02_release_engine.py`` engine over the in-repo plugin payload
(``plugins/epistemic-foundry``) and the canonical runtime provenance module
``epistemic_foundry.release.provenance``.  The engine spawns no signing service
and fabricates no signature: signing status is *derived* and the reference bundle
is fail-closed ``UNSIGNED`` while remaining hash-re-derivable and describable.

Two additional owned lints (``ruff-check``, ``ruff-format-check``) and the
repository wire-literal invariant (``wire-literal-discipline``) are executed here
too.  The scoped ``full-python-suite`` and five-base ``full-node-suite``
regressions and ``git-diff-check`` are DEFINED here for the integrating session
but are NOT executed by this bounded attempt.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Z02/attempts/0001"
ATTEMPT_ID = "Z02-0001"
ATTEMPT_SCRIPTS = "artifacts/work_packages/Z02/attempts/0001"
PRODUCT = "scripts/release"
SBOM_MODULE = "scripts/release/test_sbom.py"
SIGNATURE_MODULE = "scripts/release/test_signature.py"
ZIP_INTEGRITY_MODULE = "scripts/release/test_zip_integrity.py"
WIRE_LITERAL_MODULE = "tests/test_wire_literal_discipline.py"

# Repository-wide Node inventory count observed when this attempt was written.
# The integrating session owns ``node-full`` and updates this pin; the gate is
# zero Node failures across the five bases, never an exact test count.
EXPECTED_NODE_FILE_COUNT = 140

# Checks this bounded attempt DEFINES but does not run; the integrating session
# owns the repository-wide regression gate.
NOT_EXECUTED_BY_OWNER = ("full-python-suite", "full-node-suite", "git-diff-check")


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


def sbom_test() -> int:
    return _pytest("sbom-test", SBOM_MODULE)


def signature_test() -> int:
    return _pytest("signature-test", SIGNATURE_MODULE)


def zip_integrity_test() -> int:
    return _pytest("zip-integrity-test", ZIP_INTEGRITY_MODULE)


def wire_literal_discipline() -> int:
    return _pytest("wire-literal-discipline", WIRE_LITERAL_MODULE)


def targeted() -> int:
    return _pytest("targeted-z02-release", PRODUCT)


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
        "sbom-test": sbom_test,
        "signature-test": signature_test,
        "zip-integrity-test": zip_integrity_test,
        "wire-literal-discipline": wire_literal_discipline,
        "targeted": targeted,
        # Defined for the integrating session; not executed by this attempt.
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
