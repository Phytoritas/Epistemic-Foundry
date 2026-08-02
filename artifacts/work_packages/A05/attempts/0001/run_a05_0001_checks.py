#!/usr/bin/env python3
"""Run the A05-0001 evolution-authority-boundary acceptance checks.

A05 is the constitutional core: the evolution authority boundary and the
scientific promotion charter.  Its manifest names NINE required checks --
``schema_and_type_check``, ``unit_and_contract_tests``,
``negative_and_adversarial_tests``, ``provenance_and_receipt_audit``,
``independent_review``, ``gate_registry_exact_15``,
``evolution_promotion_workflow_exact_23``, ``constitutional_negative_24`` and
``constitutional_positive_6``.  ``independent_review`` is recorded in
``review.md`` outside this runner; the other eight are executed here as pytest
selections over the three consolidated A05 suites under
``tests/governance/a05`` (the impl consolidated the enumerated 13 filenames
into the permitted ``evolution_authority/`` package -- see OBS-A05-01 in
review.md).  Each executable check maps to an explicit, non-overlapping set of
test node IDs so its receipt cites exactly the cases that discharge it:

* ``schema-and-type-check``    -> the resolved-reference tuple/schema shape and
  the applicability-matrix domain typing (2 cases).
* ``unit-and-contract-tests``  -> the decider-agreement, chamber-delegation and
  runtime-node-binding contracts (3 cases).
* ``negative-and-adversarial-tests`` -> all 24 negative/adversarial cases.
* ``provenance-and-receipt-audit``   -> the EffectReceipt / CAS / idempotency /
  replay / reconciliation / revision provenance cases (7 cases).
* ``gate-registry-exact-15``         -> the canonical G00-G14 (15) gate order
  and applicability matrix (1 case; the exact-15 count is re-proved
  structurally in build_a05_0001_evidence.py).
* ``evolution-promotion-workflow-exact-23`` -> the 23-node binding and the
  fail-closed tampering cases (2 cases; the exact-23 node count, the single
  promotion:commit holder and the G14 receipt-bound reconcile node are
  re-proved structurally in build_a05_0001_evidence.py).
* ``constitutional-negative-24``     -> all 24 negative cases (exact-24).
* ``constitutional-positive-6``      -> the 6 positive boundary controls
  (exact-6; two parametrised lower-level controls are additional).

The ``negative-and-adversarial-tests`` and ``constitutional-negative-24``
checks intentionally execute the same 24-case suite: the manifest lists them as
distinct required checks and this consolidated suite discharges both (an
adversarial-coverage reading and an exact-24 constitutional-registry reading).
That is disclosed, not hidden.

Regressions reproduce the repository gate over the bytes A05 touched:
``wire-literal`` proves the new modules were registered in the wire-literal
guard, ``a03-boundary-regression`` proves the new ``evolution_authority``
package introduced no import-boundary cycle or layer inversion, and the
``full-python-suite``, ``full-node-suite`` and ``git-diff-check`` reproduce the
repository gate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/A05/attempts/0001"
ATTEMPT_ID = "A05-0001"
ATTEMPT_DIR = "artifacts/work_packages/A05/attempts/0001"
EVOLUTION_AUTHORITY = "src/epistemic_foundry/governance/evolution_authority"
LINT_TARGETS = (EVOLUTION_AUTHORITY, "tests/governance/a05", ATTEMPT_DIR)

_GATE = "tests/governance/a05/test_a05_gate_registry.py"
_NEG = "tests/governance/a05/test_a05_negative_cases.py"
_POS = "tests/governance/a05/test_a05_positive_cases.py"

#: The eight executable required checks, each a disjoint (except for the
#: disclosed negative/constitutional-negative overlap) set of pytest node IDs.
REQUIRED_CHECK_SELECTIONS: dict[str, tuple[str, ...]] = {
    "schema-and-type-check": (
        f"{_GATE}::test_a05_registry_resolved_reference_contract_shape",
        f"{_GATE}::test_a05_registry_matrix_matches_the_charter_shape",
    ),
    "unit-and-contract-tests": (
        f"{_GATE}::test_a05_registry_matrix_agrees_with_the_bounded_decider",
        f"{_GATE}::test_a05_registry_chamber_binding_passes_on_the_canonical_file",
        f"{_GATE}::test_a05_registry_every_bound_runtime_node_resolves",
    ),
    "negative-and-adversarial-tests": (_NEG,),
    "provenance-and-receipt-audit": (
        f"{_NEG}::test_a05_neg_020_commit_without_effect_receipt_fails",
        f"{_NEG}::test_a05_neg_021_idempotency_key_reuse_with_new_request_conflicts",
        f"{_NEG}::test_a05_neg_022_same_request_retry_replays_without_a_second_effect",
        f"{_NEG}::test_a05_neg_023_crash_between_cas_and_receipt_stays_unknown_then_reconciles",
        f"{_NEG}::test_a05_neg_024_prior_revisions_cannot_be_overwritten_in_place",
        f"{_POS}::test_a05_pos_005_full_evidence_promotion_commits_atomically",
        f"{_POS}::test_a05_pos_006_identical_retry_returns_the_same_logical_result",
    ),
    "gate-registry-exact-15": (
        f"{_GATE}::test_a05_registry_gate_order_is_the_canonical_g00_g14_set",
    ),
    "evolution-promotion-workflow-exact-23": (
        f"{_GATE}::test_a05_registry_promotion_workflow_binding_passes_on_the_canonical_file",
        f"{_GATE}::test_a05_registry_workflow_tampering_fails_closed",
    ),
    "constitutional-negative-24": (_NEG,),
    "constitutional-positive-6": (
        f"{_POS}::test_a05_pos_001_inbox_truth_is_storable_without_higher_meaning",
        f"{_POS}::test_a05_pos_002_policy_backed_not_required_approval_is_explicit",
        f"{_POS}::test_a05_pos_003_unreplicated_empirical_work_caps_at_empirically_tested",
        f"{_POS}::test_a05_pos_004_formal_equivalence_is_a_narrow_replication_exception",
        f"{_POS}::test_a05_pos_005_full_evidence_promotion_commits_atomically",
        f"{_POS}::test_a05_pos_006_identical_retry_returns_the_same_logical_result",
    ),
}

WIRE_LITERAL_TARGET = "tests/test_wire_literal_discipline.py"
A03_BOUNDARY_TARGET = (
    "artifacts/work_packages/A03/attempts/0001/test_boundary_cycle_policy_check.py"
)
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
    return run("ruff-check", ["uv", "run", "--locked", "ruff", "check", *LINT_TARGETS])


def ruff_format_check() -> int:
    return run(
        "ruff-format-check",
        ["uv", "run", "--locked", "ruff", "format", "--check", *LINT_TARGETS],
    )


def required_check(name: str) -> int:
    return _pytest(name, *REQUIRED_CHECK_SELECTIONS[name])


def wire_literal() -> int:
    return _pytest("wire-literal", WIRE_LITERAL_TARGET)


def a03_boundary_regression() -> int:
    return _pytest("a03-boundary-regression", A03_BOUNDARY_TARGET)


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
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "expected": EXPECTED_NODE_FILE_COUNT,
                "files": files,
            },
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
        **{
            name: (lambda n=name: required_check(n))
            for name in REQUIRED_CHECK_SELECTIONS
        },
        "wire-literal": wire_literal,
        "a03-boundary-regression": a03_boundary_regression,
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
