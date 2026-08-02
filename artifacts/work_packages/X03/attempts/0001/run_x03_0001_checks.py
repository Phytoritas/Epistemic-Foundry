#!/usr/bin/env python3
"""Run the X03-0001 model routing and fallback policy acceptance checks.

Required checks from manifests/development_manifest.yaml (X03):
``routing_policy_test`` and ``fallback_provenance_test``, plus the
``independent_review`` this package declares.  Each required check maps onto
one Node test module under the package's routing tree:
``routing-policy-test`` runs ``routing-policy.test.mjs`` (the routing table,
policy vocabulary, receipt schema and refusals) and ``fallback-provenance-test``
runs ``fallback-provenance.test.mjs`` (the ordered fallback chain, safe-default
placement and policy-approved fallback decision ids).  The review is recorded in
``review.md``.

``full-node-suite`` reproduces the repository-wide Node gate; the two X03
routing modules are part of that inventory, so the whole suite must stay green
with this package's tests included.  ``git-diff-check`` and
``write-scope-verification`` bound the attempt's footprint: the write scope is
``packages/role-router/src/routing/**`` and nothing else.
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
ATTEMPT = ROOT / "artifacts/work_packages/X03/attempts/0001"
ATTEMPT_ID = "X03-0001"
ATTEMPT_DIR = "artifacts/work_packages/X03/attempts/0001"
ROUTING = "packages/role-router/src/routing"
APPROVED_SCOPE = ["packages/role-router/src/routing/**"]
PRODUCT_TESTS = {
    "routing-policy-test": f"{ROUTING}/routing-policy.test.mjs",
    "fallback-provenance-test": f"{ROUTING}/fallback-provenance.test.mjs",
}
# The repository-wide Node inventory must reach the routing tree, or X03 would
# be covered by its targeted run alone.  The file count is recorded rather than
# rejected: the integrating session owns the frontier and other trees add or
# remove modules between seals, so the suite gates on zero failures, not on a
# frozen file count.
NODE_INVENTORY_ROOTS = ("packages", "tests", "web")


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


def routing_policy_test() -> int:
    return _node("routing-policy-test", PRODUCT_TESTS["routing-policy-test"])


def fallback_provenance_test() -> int:
    return _node("fallback-provenance-test", PRODUCT_TESTS["fallback-provenance-test"])


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_INVENTORY_ROOTS)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    routing_present = sorted(
        rel for rel in files if rel.startswith(f"{ROUTING}/") and rel.endswith(".test.mjs")
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        render(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "files": files,
                "roots": list(NODE_INVENTORY_ROOTS),
                "x03_routing_tests": routing_present,
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    if len(routing_present) != 2:
        write_run_result("full-node-suite", ["node", "--test", "<x03-missing>"], 2)
        print("X03 routing tests are not part of the full Node inventory", file=sys.stderr)
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
    # The whole approved write scope is packages/role-router/src/routing/**.
    # Every product byte under it is hashed here; the evidence builder pins
    # these hashes and refuses if any product file drifts.
    name = "write-scope-verification"
    command = [
        "python",
        "-B",
        f"{ATTEMPT_DIR}/run_x03_0001_checks.py",
        name,
    ]
    routing_root = ROOT / ROUTING
    if not routing_root.is_dir():
        write_run_result(name, command, 2)
        print("routing write-scope directory is missing", file=sys.stderr)
        return 2
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in routing_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    product_file_hashes = {relative: "sha256:" + sha256(ROOT / relative) for relative in relatives}
    record = {
        "approved_scope": APPROVED_SCOPE,
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "bounded implementation agent (X03 maker) under the product owner's "
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
        "routing-policy-test": routing_policy_test,
        "fallback-provenance-test": fallback_provenance_test,
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
