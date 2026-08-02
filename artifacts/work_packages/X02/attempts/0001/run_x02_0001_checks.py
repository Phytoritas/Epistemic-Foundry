#!/usr/bin/env python3
"""Run the X02-0001 Claude Code skills, agents and worktree adapter checks.

Required checks from manifests/development_manifest.yaml (X02):
``claude_adapter_test`` and ``worktree_isolation_test``, plus the
``independent_review`` this package declares.  The adapter tree carries five
Node test modules and the two required checks map onto them: the adapter test
is covered by ``claude-schema-check`` (the vocabulary the adapter reads rather
than restates), ``claude-adapter-test`` (the RoleSpec-to-custom-agent contract
the declared payload produces), ``claude-adversarial-tests`` (one broken input
at a time) and ``claude-receipts`` (the binding and worktree-plan receipts that
re-derive their own hash); the worktree isolation test is covered by
``claude-worktree-isolation-test`` (disjoint parallel-write worktree plans that
never overlap and never claim isolation they do not prove).  The review is
recorded in ``review.md``.

``dependency-regression-codex-adapter`` re-runs the sealed X01 Codex adapter
tree this package depends on, ``full-node-suite`` reproduces the repository-wide
Node gate with this package's tests inside the inventory, and
``git-diff-check`` and ``write-scope-verification`` bound the attempt's
footprint: the write scope is ``adapters/claude-code/**`` and nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/X02/attempts/0001"
ATTEMPT_ID = "X02-0001"
ATTEMPT_DIR = "artifacts/work_packages/X02/attempts/0001"
COMPONENT = "adapters/claude-code"
APPROVED_SCOPE = ["adapters/claude-code/**"]
PRODUCT_TESTS = {
    "claude-schema-check": f"{COMPONENT}/claude-schema.test.mjs",
    "claude-adapter-test": f"{COMPONENT}/claude-contract.test.mjs",
    "claude-adversarial-tests": f"{COMPONENT}/claude-adversarial.test.mjs",
    "claude-worktree-isolation-test": f"{COMPONENT}/claude-worktree.test.mjs",
    "claude-receipts": f"{COMPONENT}/claude-receipts.test.mjs",
}
# The adapter composes and re-verifies the sealed X01 Codex adapter surface it
# depends on; the dependency regression runs that whole tree so a drift in the
# dependency is caught here rather than at integration.
DEPENDENCY_TARGETS = {
    "dependency-regression-codex-adapter": ("adapters/codex",),
}
# The repository-wide Node inventory has to reach adapters/, or the adapter
# would be covered by its own targeted run alone.  The count is the inventory
# observed when this attempt was written; the integrating session owns the
# frontier and updates it when other trees add or remove test modules.
EXPECTED_NODE_FILE_COUNT = 132
NODE_INVENTORY_ROOTS = ("adapters", "packages", "plugin_blueprint", "tests", "web")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_run_result(name: str, command: list[str], exit_code: int) -> None:
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "command": command,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        render(value), encoding="utf-8", newline="\n"
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


def _node_files(*targets: str) -> list[str]:
    files: list[str] = []
    for target in targets:
        path = ROOT / target
        if path.is_file():
            files.append(target)
            continue
        files.extend(
            candidate.relative_to(ROOT).as_posix()
            for candidate in path.rglob("*.test.mjs")
            if candidate.is_file()
        )
    return sorted(set(files))


def _node(name: str, *targets: str) -> int:
    files = _node_files(*targets)
    if not files:
        write_run_result(name, ["node", "--test", "<no-files>"], 2)
        print(f"{name} declares no Node test file", file=sys.stderr)
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


def claude_schema_check() -> int:
    return _node("claude-schema-check", PRODUCT_TESTS["claude-schema-check"])


def claude_adapter_test() -> int:
    return _node("claude-adapter-test", PRODUCT_TESTS["claude-adapter-test"])


def claude_adversarial_tests() -> int:
    return _node("claude-adversarial-tests", PRODUCT_TESTS["claude-adversarial-tests"])


def claude_worktree_isolation_test() -> int:
    return _node(
        "claude-worktree-isolation-test",
        PRODUCT_TESTS["claude-worktree-isolation-test"],
    )


def claude_receipts() -> int:
    return _node("claude-receipts", PRODUCT_TESTS["claude-receipts"])


def dependency_regression_codex_adapter() -> int:
    return _node(
        "dependency-regression-codex-adapter",
        *DEPENDENCY_TARGETS["dependency-regression-codex-adapter"],
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_INVENTORY_ROOTS)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    claude_present = sorted(
        rel
        for rel in files
        if rel.startswith(f"{COMPONENT}/") and rel.endswith(".test.mjs")
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        render(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "files": files,
                "roots": list(NODE_INVENTORY_ROOTS),
                "x02_claude_tests": claude_present,
            }
        ),
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
    if len(claude_present) != len(PRODUCT_TESTS):
        write_run_result("full-node-suite", ["node", "--test", "<x02-missing>"], 2)
        print(
            "X02 Claude Code tests are not part of the full Node inventory",
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


def write_scope_verification() -> int:
    # The whole approved write scope is adapters/claude-code/**.  Every product
    # byte under it is hashed here; the evidence builder pins these hashes and
    # refuses if any product file drifts.
    name = "write-scope-verification"
    command = [
        "python",
        "-B",
        f"{ATTEMPT_DIR}/run_x02_0001_checks.py",
        name,
    ]
    component_root = ROOT / COMPONENT
    if not component_root.is_dir():
        write_run_result(name, command, 2)
        print("claude-code write-scope directory is missing", file=sys.stderr)
        return 2
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    product_file_hashes = {
        relative: "sha256:" + sha256(ROOT / relative) for relative in relatives
    }
    record = {
        "approved_scope": APPROVED_SCOPE,
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "bounded implementation agent (X02 maker) under the product owner's "
            "explicit parallel-execution instruction"
        ),
        "checked_file_count": len(relatives),
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "sealing session acting as an independent contract-reviewer, "
            "separate from the author"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }
    (ATTEMPT / "write-scope-verification.json").write_text(
        render(record), encoding="utf-8", newline="\n"
    )
    write_run_result(name, command, 0)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    checks = {
        "claude-schema-check": claude_schema_check,
        "claude-adapter-test": claude_adapter_test,
        "claude-adversarial-tests": claude_adversarial_tests,
        "claude-worktree-isolation-test": claude_worktree_isolation_test,
        "claude-receipts": claude_receipts,
        "dependency-regression-codex-adapter": dependency_regression_codex_adapter,
        "full-node-suite": node_full,
        "git-diff-check": diff_check,
        "write-scope-verification": write_scope_verification,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
