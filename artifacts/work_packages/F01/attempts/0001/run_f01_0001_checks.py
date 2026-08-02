#!/usr/bin/env python3
"""Run the F01-0001 E0-E5 epistemic-work-classifier acceptance checks.

F01 is a MAJOR FORGE package whose deterministic classifier is the
classification-truth boundary of the forge.  The manifest declares eleven
required checks (``manifests/development_manifest.yaml`` -> F01):

``classifier_gold_test``, ``underprocessing_guard``,
``classifier_adversarial_test``, ``classifier_hash_vector_test``,
``classifier_retry_replay_test``, ``classifier_immutable_override_test``,
``classifier_workflow_contract_test``, ``canonical_schema_example_validation``,
``canonical_projection_freshness``, ``full_repository_regression`` and
``independent_implementation_review``.

Ten of the eleven are objective and executed here; the eleventh
(``independent_implementation_review``) is a distinct-actor judgement recorded
in ``review.md`` outside this runner.  Six objective checks are Node test
suites under the classifier write scope, four are pytest modules, and
``full_repository_regression`` reproduces the whole Node and Python gate.

Two protective regressions guard the surfaces the new classifier module could
disturb without failing its own suite: ``regression-wire-literal`` re-runs the
wire-literal discipline suite, and ``regression-a03-boundary`` re-runs the A03
component import-boundary / cycle-policy check, proving the new
``packages/foundry-kernel/src/forge/classifier`` module introduces no illegal
import edge or cycle.

The runner is deliberately deterministic plumbing: each step captures its own
``<name>.run.json`` receipt plus stdout/stderr (and JUnit for test suites) so
``build_f01_0001_evidence.py`` can gate on the receipts rather than a live
process.  It never edits any product file and never touches ``.rah/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F01/attempts/0001"
ATTEMPT_ID = "F01-0001"
ATTEMPT_DIR = "artifacts/work_packages/F01/attempts/0001"

CLASSIFIER_DIR = "packages/foundry-kernel/src/forge/classifier"

#: Six Node classifier suites, one per objective check.  ``<name>`` is the
#: receipt/JUnit stem; the value is the classifier ``*.test.mjs`` file.
NODE_SUITES = {
    "classifier-gold-test": f"{CLASSIFIER_DIR}/classifier-gold.test.mjs",
    "underprocessing-guard-node": f"{CLASSIFIER_DIR}/underprocessing-guard.test.mjs",
    "classifier-adversarial-test": f"{CLASSIFIER_DIR}/classifier-adversarial.test.mjs",
    "classifier-hash-vector-test": f"{CLASSIFIER_DIR}/classifier-hash-vector.test.mjs",
    "classifier-retry-replay-test": f"{CLASSIFIER_DIR}/classification-committer.test.mjs",
    "classifier-immutable-override-test": f"{CLASSIFIER_DIR}/classifier-override.test.mjs",
}

#: Pytest modules: the Python half of the underprocessing guard, the workflow
#: contract, the canonical schema/example validation, the canonical projection
#: freshness gate, and the two protective regressions.
PYTEST_TARGETS = {
    "underprocessing-guard-python": ("tests/test_f01_underprocessing_guard.py",),
    "classifier-workflow-contract-test": ("tests/test_f01_workflow_contract.py",),
    "canonical-schema-example-validation": (
        "tests/test_f01_epistemic_work_classifier.py",
    ),
    "canonical-projection-freshness": ("tests/packaging/test_canonical_registry.py",),
    "regression-wire-literal": ("tests/test_wire_literal_discipline.py",),
    "regression-a03-boundary": (
        "artifacts/work_packages/A03/attempts/0001/test_boundary_cycle_policy_check.py",
    ),
}


def resolve_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    fallback = Path(r"C:\Program Files\nodejs\node.EXE")
    return str(fallback) if fallback.is_file() else None


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
            sys.executable,
            "-B",
            "-m",
            "pytest",
            *targets,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
    )


def _node_suite(name: str, relative: str) -> int:
    node = resolve_node()
    if node is None:
        write_run_result(name, ["node", "--test", relative], 127)
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        name,
        [
            node,
            "--test",
            "--test-concurrency=1",
            "--test-reporter=junit",
            relative,
        ],
        junit_from_stdout=ATTEMPT / f"{name}.junit.xml",
    )


def full_python() -> int:
    return run(
        "full-python-suite",
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "tests",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'full-python-suite.junit.xml'}",
        ],
    )


def full_node() -> int:
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
    node = resolve_node()
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
    checks: dict[str, object] = {}
    for name, relative in NODE_SUITES.items():
        checks[name] = (lambda n=name, r=relative: _node_suite(n, r))
    for name, targets in PYTEST_TARGETS.items():
        checks[name] = (lambda n=name, t=targets: _pytest(n, *t))
    checks["full-python-suite"] = full_python
    checks["full-node-suite"] = full_node
    checks["git-diff-check"] = diff_check

    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=(*tuple(checks), "all"))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    if args.check == "all":
        worst = 0
        for name, fn in checks.items():
            code = fn()  # type: ignore[operator]
            print(f"{name}: exit {code}")
            worst = worst or code
        return worst
    return checks[args.check]()  # type: ignore[operator]


if __name__ == "__main__":
    raise SystemExit(main())
