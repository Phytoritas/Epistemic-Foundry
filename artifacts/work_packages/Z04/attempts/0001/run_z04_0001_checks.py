#!/usr/bin/env python3
"""Run the Z04-0001 final release-gate, attestation and manifest-hash checks.

Required checks from ``manifests/development_manifest.yaml`` (Z04):
``final_release_gate``, ``independent_attestation`` and ``manifest_hash_check``.
Each maps to one pytest module under ``reports/release`` that composes the
deterministic ``reports/release/z04_release_gate.py`` engine against the declaring
sources ``manifests/development_manifest.yaml``, ``.rah/ralph/evidence_ledger.json``,
the canonical manifests, ``PACKAGE_MANIFEST.json`` and the plugin manifest.  The
engine reconciles the 156-package A-Z set (153 sealed-PASS + {Z04, Z05, Z06}
named/owned remaining), attests the UNVERIFIED reference-maturity release label,
and reconciles the canonical manifest hashes and PACKAGE_MANIFEST byte pins.  It
seals nothing and mutates no canonical file: these are declared, fail-closed
reconciliations, not a production release.

Owned checks executed by this bounded attempt: ``ruff-check``,
``ruff-format-check``, ``final-release-gate``, ``independent-attestation``,
``manifest-hash-check`` and ``wire-literal-discipline``.  The repository-gate
checks ``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` are
DEFINED here for the integrating session but are NOT executed by this attempt.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Z04/attempts/0001"
ATTEMPT_ID = "Z04-0001"
ATTEMPT_SCRIPTS = "artifacts/work_packages/Z04/attempts/0001"
RELEASE_DIR = "reports/release"
FINAL_RELEASE_GATE_MODULE = "reports/release/test_final_release_gate.py"
INDEPENDENT_ATTESTATION_MODULE = "reports/release/test_independent_attestation.py"
MANIFEST_HASH_CHECK_MODULE = "reports/release/test_manifest_hash_check.py"
WIRE_LITERAL_MODULE = "tests/test_wire_literal_discipline.py"

#: Deterministic, caller-supplied timestamp so every emitted reconciliation
#: record is byte-identical on re-run.  Overridable via ``--generated-at``.
DEFAULT_GENERATED_AT = "1970-01-01T00:00:00Z"

#: Repository-gate checks the integrating session owns; defined but never run by
#: this bounded attempt.
NOT_EXECUTED_BY_OWNER = ("full-python-suite", "full-node-suite", "git-diff-check")

# Repository-wide Node inventory count observed when this attempt was written.
# The integrating session owns ``full-node-suite`` and updates this pin; the gate
# is zero Node failures across the five bases, never an exact test count.
EXPECTED_NODE_FILE_COUNT = 140

_GENERATED_AT = DEFAULT_GENERATED_AT


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


def emit_reconciliation_records() -> None:
    """Emit the three content-addressed reconciliation records under reports/."""

    sys.path.insert(0, str(ROOT / "reports" / "release"))
    import z04_release_gate as engine

    engine.write_records(generated_at=_GENERATED_AT)


def ruff_check() -> int:
    return run(
        "ruff-check",
        ["uv", "run", "--locked", "ruff", "check", ATTEMPT_SCRIPTS, RELEASE_DIR],
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
            RELEASE_DIR,
        ],
    )


def final_release_gate() -> int:
    emit_reconciliation_records()
    return _pytest("final-release-gate", FINAL_RELEASE_GATE_MODULE)


def independent_attestation() -> int:
    emit_reconciliation_records()
    return _pytest("independent-attestation", INDEPENDENT_ATTESTATION_MODULE)


def manifest_hash_check() -> int:
    emit_reconciliation_records()
    return _pytest("manifest-hash-check", MANIFEST_HASH_CHECK_MODULE)


def wire_literal_discipline() -> int:
    return _pytest("wire-literal-discipline", WIRE_LITERAL_MODULE)


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


OWNED_CHECKS = {
    "ruff-check": ruff_check,
    "ruff-format-check": ruff_format_check,
    "final-release-gate": final_release_gate,
    "independent-attestation": independent_attestation,
    "manifest-hash-check": manifest_hash_check,
    "wire-literal-discipline": wire_literal_discipline,
}

GATE_CHECKS = {
    "full-python-suite": python_full,
    "full-node-suite": node_full,
    "git-diff-check": diff_check,
}


def main() -> int:
    global _GENERATED_AT
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check",
        nargs="?",
        default="all",
        choices=("all", *OWNED_CHECKS, *GATE_CHECKS),
    )
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    args = parser.parse_args()
    _GENERATED_AT = args.generated_at
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    if args.check == "all":
        # The three NOT_EXECUTED_BY_OWNER gates are intentionally skipped here.
        worst = 0
        for name, fn in OWNED_CHECKS.items():
            code = fn()
            print(f"{name}: exit {code}")
            worst = worst or code
        return worst
    if args.check in GATE_CHECKS:
        return GATE_CHECKS[args.check]()
    return OWNED_CHECKS[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
