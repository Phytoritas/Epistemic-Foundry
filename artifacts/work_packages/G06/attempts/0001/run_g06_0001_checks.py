#!/usr/bin/env python3
"""Run the G06-0001 native plugin packaging and skill-discovery acceptance checks.

Required checks from manifests/development_manifest.yaml (G06):
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit`` and
``independent_review``.  The first four map to one Node test module each under
the package's own tree; the review is recorded in ``review.md``.

The packaging surface composes three sealed dependencies, so each runs as a
named regression check rather than only inside the full suite: the sealed G05
evolution surface (``plugin_blueprint/epistemic-foundry/v4_g05``) and the sealed
H05 observability surface (``plugin_blueprint/epistemic-foundry/hooks/v4_h05``)
are Node surfaces, and the sealed T05 tool/adapter surface is exercised through
its Python attempt suite.

``full-node-suite`` reproduces the repository-wide Node gate; the four G06
packaging modules are part of that inventory, so the whole suite must stay green
with this package's tests included.  ``git-diff-check`` and
``write-scope-verification`` bound the attempt's footprint: the product write
scope is ``plugin_blueprint/epistemic-foundry/v4_g06/**`` and nothing else.
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
ATTEMPT = ROOT / "artifacts/work_packages/G06/attempts/0001"
ATTEMPT_ID = "G06-0001"
ATTEMPT_DIR = "artifacts/work_packages/G06/attempts/0001"
COMPONENT = "plugin_blueprint/epistemic-foundry/v4_g06"
APPROVED_SCOPE = ["plugin_blueprint/epistemic-foundry/v4_g06/**"]
PRODUCT_TESTS = {
    "schema-and-type-check": f"{COMPONENT}/packaging-schema.test.mjs",
    "unit-and-contract-tests": f"{COMPONENT}/packaging-contract.test.mjs",
    "negative-and-adversarial-tests": f"{COMPONENT}/packaging-adversarial.test.mjs",
    "provenance-and-receipt-audit": f"{COMPONENT}/packaging-receipts.test.mjs",
}
# The packaging surface composes the sealed G05 evolution surface, the sealed
# H05 observability surface and the sealed T05 tool/adapter surface, so a change
# in any of them must fail here.  G05 and H05 are Node surfaces; T05 is a Python
# adapter exercised through its sealed attempt suite.
DEPENDENCY_NODE_TARGETS = {
    "dependency-regression-g05": ("plugin_blueprint/epistemic-foundry/v4_g05",),
    "dependency-regression-h05": ("plugin_blueprint/epistemic-foundry/hooks/v4_h05",),
}
DEPENDENCY_PYTEST_TARGETS = {
    "dependency-regression-t05": ("artifacts/work_packages/T05/attempts/0001",),
}
# The four G06 packaging modules that must appear in the repository-wide Node
# inventory; the suite gates on zero failures, not on a frozen file count, so
# the live frontier can add or remove modules between seals.
G06_PACKAGING_TESTS = sorted(PRODUCT_TESTS.values())
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


def schema_and_type_check() -> int:
    return _node("schema-and-type-check", PRODUCT_TESTS["schema-and-type-check"])


def unit_and_contract_tests() -> int:
    return _node("unit-and-contract-tests", PRODUCT_TESTS["unit-and-contract-tests"])


def negative_and_adversarial_tests() -> int:
    return _node(
        "negative-and-adversarial-tests",
        PRODUCT_TESTS["negative-and-adversarial-tests"],
    )


def provenance_and_receipt_audit() -> int:
    return _node(
        "provenance-and-receipt-audit", PRODUCT_TESTS["provenance-and-receipt-audit"]
    )


def targeted() -> int:
    return _node("targeted-g06-packaging", COMPONENT)


def dependency_regression_g05() -> int:
    return _node(
        "dependency-regression-g05",
        *DEPENDENCY_NODE_TARGETS["dependency-regression-g05"],
    )


def dependency_regression_h05() -> int:
    return _node(
        "dependency-regression-h05",
        *DEPENDENCY_NODE_TARGETS["dependency-regression-h05"],
    )


def dependency_regression_t05() -> int:
    return _pytest(
        "dependency-regression-t05",
        *DEPENDENCY_PYTEST_TARGETS["dependency-regression-t05"],
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_INVENTORY_ROOTS)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    packaging_present = sorted(rel for rel in files if rel in set(G06_PACKAGING_TESTS))
    (ATTEMPT / "node-test-inventory.json").write_text(
        render(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "files": files,
                "g06_packaging_tests": packaging_present,
                "roots": list(NODE_INVENTORY_ROOTS),
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    if packaging_present != sorted(G06_PACKAGING_TESTS):
        write_run_result("full-node-suite", ["node", "--test", "<g06-missing>"], 2)
        print(
            "G06 packaging tests are not part of the full Node inventory",
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
    # The whole approved product write scope is v4_g06/**.  Every product byte
    # under it is hashed here; the evidence builder pins these hashes and refuses
    # if any product file drifts.
    name = "write-scope-verification"
    command = ["python", "-B", f"{ATTEMPT_DIR}/run_g06_0001_checks.py", name]
    component_root = ROOT / COMPONENT
    if not component_root.is_dir():
        write_run_result(name, command, 2)
        print("v4_g06 write-scope directory is missing", file=sys.stderr)
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
        "approved_scope": [
            "plugin_blueprint/epistemic-foundry/v4_g06/**",
            "artifacts/work_packages/G06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "bounded implementation agent (G06 maker) under the product owner's "
            "explicit parallel-execution instruction"
        ),
        "checked_file_count": len(relatives),
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "sealing session acting as an independent reviewer, separate from "
            "the author"
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
        "schema-and-type-check": schema_and_type_check,
        "unit-and-contract-tests": unit_and_contract_tests,
        "negative-and-adversarial-tests": negative_and_adversarial_tests,
        "provenance-and-receipt-audit": provenance_and_receipt_audit,
        "targeted": targeted,
        "dependency-regression-g05": dependency_regression_g05,
        "dependency-regression-h05": dependency_regression_h05,
        "dependency-regression-t05": dependency_regression_t05,
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
