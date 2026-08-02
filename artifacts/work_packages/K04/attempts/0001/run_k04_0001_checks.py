#!/usr/bin/env python3
"""Run K04-0001 checks into attempt-local evidence files.

The runner writes only beneath ``artifacts/work_packages/K04/attempts/0001``.
Product runtime and canonical contracts remain read-only during this integration
gate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/K04/attempts/0001"

K04_PYTHON_TESTS = (
    "tests/security/corpus/test_ingest_quality_gate.py",
    "tests/security/corpus/test_corpus_ingest_workflow.py",
)
K04_NODE_TESTS = ("tests/security/corpus/corpus-injection.test.mjs",)
S01_NODE_REGRESSION = (
    "packages/foundry-kernel/src/security/trust/prompt-injection.test.mjs",
    "packages/foundry-kernel/src/security/trust/authority-escalation.test.mjs",
)
ROOT_INGEST_REGRESSION = (
    "tests/test_release.py",
    "tests/ingest",
    "tests/contracts/test_k01_document_contracts.py",
    "tests/integration/test_k01_register_document_node.py",
)
COMPONENT_INGEST_REGRESSION = (
    "python/epistemic_foundry/ingest/parsers",
    "python/epistemic_foundry/ingest/spans",
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


def pytest_check(paths: tuple[str, ...], output_name: str) -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            *paths,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / output_name}",
        ],
        stdout_path=ATTEMPT / f"{output_name}.stdout.log",
        stderr_path=ATTEMPT / f"{output_name}.stderr.log",
    )


def node_check(paths: tuple[str, ...], output_name: str) -> int:
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *paths],
        stdout_path=ATTEMPT / output_name,
        stderr_path=ATTEMPT / f"{output_name}.stderr.log",
    )


def k04_python() -> int:
    return pytest_check(K04_PYTHON_TESTS, "targeted-k04-python.junit.xml")


def k04_node() -> int:
    return node_check(K04_NODE_TESTS, "targeted-k04-node.junit.xml")


def predecessor_python_root() -> int:
    return pytest_check(ROOT_INGEST_REGRESSION, "predecessor-root-python.junit.xml")


def predecessor_python_components() -> int:
    return pytest_check(
        COMPONENT_INGEST_REGRESSION,
        "predecessor-k02-k03-python.junit.xml",
    )


def predecessor_node() -> int:
    return node_check(S01_NODE_REGRESSION, "predecessor-s01-node.junit.xml")


def full_python() -> int:
    return pytest_check(("tests",), "full-python-suite.junit.xml")


def full_node() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    inventory = {
        "attempt_id": "K04-0001",
        "count": len(files),
        "files": files,
    }
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != 55:
        print(f"expected 55 Node test files, found {len(files)}", file=sys.stderr)
        return 2
    return node_check(tuple(files), "full-node-suite.junit.xml")


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


def structure() -> int:
    return run(
        ["npm", "run", "check:structure"],
        stdout_path=ATTEMPT / "structure-check.stdout.log",
        stderr_path=ATTEMPT / "structure-check.stderr.log",
    )


def boundaries() -> int:
    return run(
        ["npm", "run", "check:boundaries"],
        stdout_path=ATTEMPT / "boundary-check.stdout.log",
        stderr_path=ATTEMPT / "boundary-check.stderr.log",
    )


def ruff() -> int:
    return run(
        ["uv", "run", "--locked", "ruff", "check", "tests/security/corpus"],
        stdout_path=ATTEMPT / "ruff-check.stdout.log",
        stderr_path=ATTEMPT / "ruff-check.stderr.log",
    )


def diff_check() -> int:
    return run(
        ["git", "diff", "--check"],
        stdout_path=ATTEMPT / "git-diff-check.stdout.log",
        stderr_path=ATTEMPT / "git-diff-check.stderr.log",
    )


CHECKS = {
    "k04-python": k04_python,
    "k04-node": k04_node,
    "predecessor-python-root": predecessor_python_root,
    "predecessor-python-components": predecessor_python_components,
    "predecessor-node": predecessor_node,
    "full-python": full_python,
    "full-node": full_node,
    "codegen": codegen,
    "structure": structure,
    "boundaries": boundaries,
    "ruff": ruff,
    "diff-check": diff_check,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=tuple(CHECKS))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return CHECKS[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
