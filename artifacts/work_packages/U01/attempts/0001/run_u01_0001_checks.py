#!/usr/bin/env python3
"""Run the U01-0001 OpenAPI server and generated-client acceptance checks.

Required checks from ``manifests/development_manifest.yaml`` (U01) are
``openapi_conformance`` and ``generated_client_test``.  Both are defined here
as named checks over the product Node suites, and each of the four suites is
also runnable on its own so a failure names the surface it came from.

The surface is an adapter-layer component that derives its whole route table
from ``openapi/epistemic-foundry-v1.openapi.yaml``, and the generated client
under ``web/src/generated/ui-client`` is written by ``generate_client.py`` in
this attempt directory.  ``client-generation-parity`` therefore runs the
generator in ``--check`` mode: a hand-edited generated file fails here rather
than drifting silently away from the declaring document.

``repo-structure-check`` and ``repo-boundaries-check`` run the repository's own
component gates as named checks, because this package is the first ui-api tree
with source in it.

``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` are defined
here but are owned by the primary session; this attempt does not execute them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/U01/attempts/0001"
ATTEMPT_ID = "U01-0001"
ATTEMPT_DIR = "artifacts/work_packages/U01/attempts/0001"
COMPONENT = "packages/ui-api/src/openapi"
GENERATED_TREE = "web/src/generated/ui-client"
GENERATOR = f"{ATTEMPT_DIR}/generate_client.py"

PRODUCT_TESTS = {
    "openapi-schema": f"{COMPONENT}/openapi-schema.test.mjs",
    "openapi-contract": f"{COMPONENT}/openapi-contract.test.mjs",
    "openapi-adversarial": f"{COMPONENT}/openapi-adversarial.test.mjs",
    "openapi-receipts": f"{COMPONENT}/openapi-receipts.test.mjs",
}
# `openapi_conformance` is the document-side claim: the projection matches the
# declaring document and every structural refusal is reachable.
OPENAPI_CONFORMANCE_TESTS = (
    PRODUCT_TESTS["openapi-schema"],
    PRODUCT_TESTS["openapi-contract"],
    PRODUCT_TESTS["openapi-adversarial"],
)
# `generated_client_test` is the client-side claim: the committed generated
# tree is a faithful, re-derivable projection of the same document.
GENERATED_CLIENT_TESTS = (
    PRODUCT_TESTS["openapi-contract"],
    PRODUCT_TESTS["openapi-receipts"],
)
# C04 sealed the canonical contract registry this surface binds to, so the
# contract tests are the dependency this package must not regress.
DEPENDENCY_TARGETS = {
    "dependency-regression-contracts": ("tests/test_contracts.py",),
}
EXPECTED_NODE_FILE_COUNT = 107


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


def _node(name: str, *targets: str) -> int:
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
    files = sorted(set(files))
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


def ruff_check() -> int:
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", ATTEMPT_DIR])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", ATTEMPT_DIR],
    )


def _repo_check(name: str, script: str) -> int:
    node = shutil.which("node")
    command = ["node", f"packages/repo-checks/{script}"]
    if node is None:
        write_run_result(name, command, 127)
        return 127
    return run(name, [node, command[1]])


def repo_structure_check() -> int:
    return _repo_check("repo-structure-check", "check-structure.mjs")


def repo_boundaries_check() -> int:
    return _repo_check("repo-boundaries-check", "check-boundaries.mjs")


def openapi_schema() -> int:
    return _node("openapi-schema", PRODUCT_TESTS["openapi-schema"])


def openapi_contract() -> int:
    return _node("openapi-contract", PRODUCT_TESTS["openapi-contract"])


def openapi_adversarial() -> int:
    return _node("openapi-adversarial", PRODUCT_TESTS["openapi-adversarial"])


def openapi_receipts() -> int:
    return _node("openapi-receipts", PRODUCT_TESTS["openapi-receipts"])


def openapi_conformance() -> int:
    return _node("openapi-conformance", *OPENAPI_CONFORMANCE_TESTS)


def generated_client_test() -> int:
    return _node("generated-client-test", *GENERATED_CLIENT_TESTS)


def targeted() -> int:
    return _node("targeted-u01-surface", "packages/ui-api")


def client_generation_parity() -> int:
    # Regenerate from the declaring document and refuse on any byte-level
    # difference from the committed tree.  A generated file that was edited by
    # hand is a silent fork of the contract, so it fails as a check rather than
    # being reconciled by rewriting the file.
    return run(
        "client-generation-parity",
        ["uv", "run", "--locked", "python", "-B", GENERATOR, "--check"],
    )


def dependency_regression_contracts() -> int:
    return _pytest(
        "dependency-regression-contracts",
        *DEPENDENCY_TARGETS["dependency-regression-contracts"],
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
        "repo-structure-check": repo_structure_check,
        "repo-boundaries-check": repo_boundaries_check,
        "openapi-schema": openapi_schema,
        "openapi-contract": openapi_contract,
        "openapi-adversarial": openapi_adversarial,
        "openapi-receipts": openapi_receipts,
        "openapi-conformance": openapi_conformance,
        "generated-client-test": generated_client_test,
        "targeted": targeted,
        "client-generation-parity": client_generation_parity,
        "dependency-regression-contracts": dependency_regression_contracts,
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
