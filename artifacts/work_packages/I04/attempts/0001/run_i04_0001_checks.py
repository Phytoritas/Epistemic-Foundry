#!/usr/bin/env python3
"""Run the I04-0001 intake UX and export-gate acceptance checks.

Required checks from ``manifests/development_manifest.yaml`` (I04):
``intake_ui_test`` and ``frame_roundtrip_test``.  I04 is a Node/Web package
under ``web/src/features/intake`` — the manifest lists exactly these two checks
(not the standard five), so there is no Ruff gate on product code here.  Each
required check maps onto a single whole Node test module run with
``node --test --test-concurrency=1 --test-reporter=junit`` from the repository
root; the intake fixtures resolve the repository root from ``import.meta.url``
so the working directory does not matter.

``intake_ui_test``
    ``web/src/features/intake/intake-ui.test.mjs`` — the intake projection and
    export control: inbox and council/measurement/ontology blockers are the
    first visible section, confidence and verdict are never invented, untrusted
    text is escaped, and a forged assembled frame cannot hide a derived blocker.

``frame_roundtrip_test``
    ``web/src/features/intake/frame-roundtrip.test.mjs`` — canonical export
    parses and re-exports byte-for-byte, key order does not change the bytes,
    SHA-256 matches the Node oracle, and an Inbox / fabricated / non-canonical /
    tampered frame fails closed on import or export.

Both intake modules also join the whole-repository Node inventory under
``packages/``, ``tests/`` and ``web/``; that full suite is the regression that
matters and is captured by ``node-full``.  A scoped ``python-full`` run under
``tests/`` guards the Python surface, and ``diff-check`` completes the gate.
The whole-repository Node file count is pinned so an inventory drift is caught,
but the gate is zero Node failures, never an exact test count.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/I04/attempts/0001"
ATTEMPT_ID = "I04-0001"
COMPONENT = "web/src/features/intake"
# The repository-wide Node inventory count observed when this attempt was
# written.  The integrating session owns ``node-full`` and updates this pin
# when other trees add or remove test modules; the gate is zero Node failures,
# never an exact test count.
EXPECTED_NODE_FILE_COUNT = 111


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
    for relative in files:
        if not (ROOT / relative).is_file():
            write_run_result(name, ["node", "--test", relative, "<missing>"], 2)
            print(f"{name}: missing Node test file {relative}", file=sys.stderr)
            return 2
    node = shutil.which("node")
    if node is None:
        write_run_result(name, ["node", "--test", *files], 127)
        return 127
    return run(
        name,
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / f"{name}.junit.xml",
    )


def intake_ui_test() -> int:
    return _node("intake-ui-test", [f"{COMPONENT}/intake-ui.test.mjs"])


def frame_roundtrip_test() -> int:
    return _node("frame-roundtrip-test", [f"{COMPONENT}/frame-roundtrip.test.mjs"])


def targeted() -> int:
    return _node(
        "targeted",
        [
            f"{COMPONENT}/intake-ui.test.mjs",
            f"{COMPONENT}/frame-roundtrip.test.mjs",
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
    # The two I04 intake modules must be present in the inventory.
    required = {
        f"{COMPONENT}/intake-ui.test.mjs",
        f"{COMPONENT}/frame-roundtrip.test.mjs",
    }
    if not required.issubset(files):
        write_run_result("full-node-suite", ["node", "--test", "<i04-missing>"], 2)
        print("full-node-suite: I04 intake modules absent from inventory", file=sys.stderr)
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
        "intake-ui-test": intake_ui_test,
        "frame-roundtrip-test": frame_roundtrip_test,
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
