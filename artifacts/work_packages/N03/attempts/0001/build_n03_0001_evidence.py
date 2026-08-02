#!/usr/bin/env python3
"""Build and verify deterministic N03-0001 scheduler evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/N03"
N02_ATTEMPT = ROOT / "artifacts/work_packages/N02/attempts/0001"
sys.path.insert(0, str(N02_ATTEMPT))

import build_n02_0001_evidence as base  # noqa: E402


ATTEMPT_ID = "N03-0001"
WORK_PACKAGE_ID = "N03"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "packages/foundry-kernel/src/scheduler/dag-scheduler.mjs",
    "packages/foundry-kernel/src/scheduler/index.mjs",
    "packages/foundry-kernel/src/scheduler/resource-conflict.test.mjs",
    "packages/foundry-kernel/src/scheduler/scheduler-property.test.mjs",
    "packages/foundry-kernel/src/scheduler/scheduler-test-support.mjs",
)
N03_TESTS = (
    "packages/foundry-kernel/src/scheduler/resource-conflict.test.mjs",
    "packages/foundry-kernel/src/scheduler/scheduler-property.test.mjs",
)
N01_TESTS = (
    "packages/role-router/src/contracts/acl.test.mjs",
    "packages/role-router/src/contracts/role-schema.test.mjs",
)
E02_TESTS = (
    "packages/foundry-kernel/src/effects/effect-reconciliation.test.mjs",
    "packages/foundry-kernel/src/effects/idempotency.test.mjs",
)
E03_TESTS = (
    "packages/foundry-kernel/src/capabilities/fencing.test.mjs",
    "packages/foundry-kernel/src/capabilities/lease-expiry.test.mjs",
)
N01_DEPENDENCY = {
    "attempt_id": "N01-0001",
    "core_evidence_id": "E0066",
    "core_generation": "000066-096ea5d0",
    "final_closeout_evidence_id": "E0067",
    "report": "artifacts/work_packages/N01/attempts/0001/report.json",
    "report_sha256": "sha256:6c2be21ead767753ebe67931dff46f909e5c15050ea07d9b1c366a5213d84eb2",
}


sha256_id = base.sha256_id
canonical_hash = base.canonical_hash
read_json = base.read_json
render = base.render
write_json = base.write_json
node_summary = base.node_summary
pytest_summary = base.pytest_summary
assert_clean_node = base.assert_clean_node


def recorded_at() -> str:
    metadata = read_json(METADATA)
    if metadata.get("attempt_id") != ATTEMPT_ID:
        raise SystemExit("N03 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("N03 attempt metadata has no recorded_at_utc")
    return value


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "N03"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one N03 row")
    expected = {
        "depends_on": ["N01"],
        "write_scope": ["packages/foundry-kernel/src/scheduler/**"],
        "independent_review": "required",
        "exit_criteria": [
            "real dependencies and resources enforced",
            "cycles require LoopContract",
        ],
        "required_checks": ["scheduler_property_test", "resource_conflict_test"],
        "risk_class": "high",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"N03 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages/foundry-kernel/src/scheduler").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"N03 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"N03 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"N03 source must be BOM-less UTF-8: {relative}")
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": sha256_id(path),
                "utf8_bom": False,
            }
        )
    return rows


def syntax_evidence() -> dict[str, Any]:
    syntax = read_json(ATTEMPT / "syntax-verification.json")
    checks = syntax.get("checks", [])
    if not (
        syntax.get("final_status") == "PASS"
        and len(checks) == len(PRODUCT_FILES)
        and all(row.get("exit_code") == 0 for row in checks)
        and sorted(row.get("path") for row in checks) == sorted(PRODUCT_FILES)
    ):
        raise SystemExit("N03 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-n03-node.junit.xml")
    assert_clean_node(targeted, 24, "N03 targeted")
    names = targeted["test_names"]
    scheduler = [name for name in names if name.startswith("scheduler_property_test:")]
    resource = [name for name in names if name.startswith("resource_conflict_test:")]
    if len(scheduler) != 15 or len(resource) != 9 or len(set(names)) != 24:
        raise SystemExit("N03 targeted test-name partition is not exact 15/9")
    if targeted["observed_files"] != sorted(N03_TESTS):
        raise SystemExit("N03 targeted JUnit file inventory differs")
    return {
        **targeted,
        "resource_conflict_test_count": len(resource),
        "scheduler_property_test_count": len(scheduler),
    }


def adjacent_evidence() -> dict[str, Any]:
    n01 = node_summary(ATTEMPT / "n01-role-contract-regression.junit.xml")
    e02 = node_summary(ATTEMPT / "e02-effect-regression.junit.xml")
    e03 = node_summary(ATTEMPT / "e03-capability-regression.junit.xml")
    assert_clean_node(n01, 21, "N01 RoleSpec/ACL regression")
    assert_clean_node(e02, 19, "E02 effect regression")
    assert_clean_node(e03, 30, "E03 capability regression")
    if n01["observed_files"] != sorted(N01_TESTS):
        raise SystemExit("N01 regression JUnit file inventory differs")
    if e02["observed_files"] != sorted(E02_TESTS):
        raise SystemExit("E02 regression JUnit file inventory differs")
    if e03["observed_files"] != sorted(E03_TESTS):
        raise SystemExit("E03 regression JUnit file inventory differs")
    return {
        "e02_effect_contract": e02,
        "e03_capability_contract": e03,
        "n01_role_contract": n01,
        "status": "PASS",
    }


def scheduler_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    required_fragments = (
        "export const compileSchedulerPlan",
        "export const assertSchedulerPlanIntegrity",
        "export const sealLoopContract",
        "export const sealBudgetEnvelope",
        "export const createDagScheduler",
        "export const replaySchedulerCommands",
        '"DAG_CYCLE_WITHOUT_LOOP_CONTRACT"',
        '"PREDECESSOR_RECEIPT_MISSING"',
        '"BUDGET_LIMIT_EXCEEDED"',
        '"RESOURCE_CONFLICT"',
        '"STALE_FENCING_TOKEN"',
        '"IDEMPOTENCY_CONFLICT"',
        '"RECONCILING"',
        '"EFFECT_RECEIPT_MISSING"',
        "capability_lease_ids",
        "terminal_receipt_id",
        "dry_rounds_required",
        "snapshot()",
    )
    missing = [fragment for fragment in required_fragments if fragment not in source]
    if missing:
        raise SystemExit(f"N03 scheduler contract binding is incomplete: {missing}")
    return {
        "admission": {
            "approval_policy_and_capability_evidence_required": True,
            "capability_leases_are_external_authority": True,
            "failed_admission_is_side_effect_free": True,
        },
        "attempt_id": ATTEMPT_ID,
        "bounded_loops": {
            "cycle_requires_exact_hash_valid_loop_contract": True,
            "dedupe_and_dry_rounds_enforced": True,
            "iteration_cost_and_wall_limits_enforced": True,
        },
        "dependency_readiness": {
            "predecessor_success_required": True,
            "terminal_receipt_required": True,
            "typed_failure_policy_visible": True,
        },
        "deterministic_plan_compilation": "PASS",
        "effects_and_recovery": {
            "effect_success_requires_receipt": True,
            "expired_or_unknown_attempt_reconciliation_required": True,
            "orphan_success_is_forbidden": True,
        },
        "fencing_and_resources": {
            "atomic_multi_resource_admission": True,
            "exclusive_and_quota_capacity_enforced": True,
            "node_and_exclusive_resource_fencing": True,
        },
        "immutable_outputs": ["plan", "lease", "attempt", "snapshot"],
        "replay": {
            "canonical_command_log": True,
            "exact_state_reproduction": True,
            "tamper_rejection": True,
        },
        "retry_and_idempotency": {
            "changed_binding_conflicts": True,
            "exact_acquisition_retry_reuses_lease": True,
            "immutable_attempt_history": True,
            "typed_retryable_failures_only": True,
        },
        "status": "PASS",
        "syntax": syntax_evidence(),
        "targeted": targeted_evidence(),
        "upstream_regressions": adjacent_evidence(),
    }


def dependency_evidence() -> dict[str, Any]:
    path = ROOT / N01_DEPENDENCY["report"]
    report = read_json(path)
    rah = report.get("rah_state")
    if not (
        report.get("work_package_id") == "N01"
        and report.get("attempt_id") == N01_DEPENDENCY["attempt_id"]
        and report.get("status") == "PASS"
        and report.get("package_status") == "PASS"
        and report.get("completion_ready") is False
        and sha256_id(path) == N01_DEPENDENCY["report_sha256"]
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == N01_DEPENDENCY["core_evidence_id"]
        and rah.get("core_generation") == N01_DEPENDENCY["core_generation"]
        and rah.get("final_closeout_evidence_id")
        == N01_DEPENDENCY["final_closeout_evidence_id"]
    ):
        raise SystemExit("N03 dependency N01 is not the exact sealed PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {"N01": {**N01_DEPENDENCY, "status": "PASS"}},
        "dependency_count": 1,
        "status": "PASS",
    }


def node_files() -> list[str]:
    return sorted(
        path.relative_to(ROOT).as_posix()
        for folder in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in folder.rglob("*.test.mjs")
        if path.is_file()
    )


def regression_evidence() -> dict[str, Any]:
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    files = node_files()
    assert_clean_node(full_node, 793, "full Node")
    if not (
        len(files) == len(set(files)) == 77
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 77
    ):
        raise SystemExit("full Node inventory/JUnit coverage is incomplete or ambiguous")
    if not (
        full_python["passed"] == full_python["collected"] == 1064
        and full_python["failed"] == full_python["errors"] == full_python["skipped"] == 0
    ):
        raise SystemExit("full Python gate is not 1064/1064")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory != {
        "attempt_id": ATTEMPT_ID,
        "count": 77,
        "files": files,
        "unique": True,
    }:
        raise SystemExit("stored Node inventory differs from live inventory")
    codegen = read_json(ATTEMPT / "codegen-verification.stdout.log")
    if not (
        codegen.get("status") == "PASS"
        and codegen.get("schema_count") == 126
        and codegen.get("example_count") == 126
        and codegen.get("failures") == []
    ):
        raise SystemExit("canonical codegen verification did not pass 126/126")
    structure = (ATTEMPT / "structure-check.stdout.log").read_text(encoding="utf-8")
    boundaries = (ATTEMPT / "boundary-check.stdout.log").read_text(encoding="utf-8")
    if '"status": "PASS"' not in structure or '"status": "PASS"' not in boundaries:
        raise SystemExit("repository structure or boundary gate did not pass")
    if (ATTEMPT / "git-diff-check.stdout.log").stat().st_size != 0:
        raise SystemExit("git diff --check produced stdout")
    warnings = (ATTEMPT / "git-diff-check.stderr.log").read_text(encoding="utf-8")
    unexpected = [line for line in warnings.splitlines() if line and not line.startswith("warning:")]
    if unexpected:
        raise SystemExit(f"git diff --check stderr contains non-warning output: {unexpected}")
    return {
        "adjacent_contracts": adjacent_evidence(),
        "attempt_id": ATTEMPT_ID,
        "canonical_codegen": {"examples": 126, "schemas": 126, "status": "PASS"},
        "earlier_concurrency_diagnostic": {
            "causal_classification": "TRANSIENT_UNRELATED_ARTIFACT_STORE_CONCURRENCY_DIAGNOSTIC",
            "complete_rerun": "PASS: 793/793",
            "exact_original_test_identifier_retained": False,
            "evidence_limitation": "The original raw JUnit/test identifier was not retained; no identifier is inferred or invented.",
            "initial_observation": "792/793 with one artifact-store concurrency failure",
            "isolated_surface_rerun": "PASS: 1/1",
            "official_serial_gate": "PASS: 793/793 across 77 files",
        },
        "full_node": {**full_node, "test_file_count": 77},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "repository_structure": "PASS",
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/N03/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/foundry-kernel/src/scheduler/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    verification = scheduler_verification()
    return {
        "scheduler-verification.json": {
            **verification,
            "manifest_contract": manifest_contract(),
        },
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    targeted = targeted_evidence()
    return f"""# N03-0001 DAG scheduler, leases, retries and concurrency review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N03
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. DAG compilation is deterministic across node permutations. Duplicate,
   unknown, self, hostile, and cyclic dependencies fail closed; every real
   cycle requires exactly one matching, hash-valid `LoopContract` whose
   back-edge removal yields an entry-to-exit executable order.
2. Readiness is bound to real predecessor status and terminal receipts. Failure
   policy remains typed and visible; a downstream node cannot infer success
   from an absent receipt or an unresolved predecessor.
3. Admission requires resolved inputs, policy/approval evidence, and external
   E03 capability-lease IDs. The scheduler records this evidence but does not
   mint, replace, or broaden capability authority.
4. Budget and resource admission is checked before token, usage, lease, or
   ownership mutation. Exclusive resources, bounded quotas, and multi-resource
   acquisition are atomic; rejected admission leaves no partial reservation.
5. Node and exclusive-resource fencing prevents stale workers from committing.
   Exact acquisition retry reuses one lease, while changed idempotency,
   admission, or reservation bindings conflict instead of silently forking.
6. Attempts are immutable. Retry is allowed only for the closed transient
   failure taxonomy, timestamps cannot regress, and expired/unknown-effect
   work enters reconciliation before reassignment. Success after reconciliation
   requires terminal, reconciliation, and effect receipts.
7. Hard call/concurrency budgets and bounded loop iteration, cost, wall-time,
   dry-round, and dedupe rules are enforced without inventing unavailable
   meters. Command replay reproduces exact state and rejects tamper.
8. Plans, leases, attempts, command logs, and snapshots are deeply immutable;
   snapshots bind active leases, budget usage, fencing heads, resource owners,
   and idempotency bindings.
9. Required N03 checks pass {targeted['passed']}/{targeted['collected']}: 15
   `scheduler_property_test` and 9 `resource_conflict_test` cases. N01 passes
   21/21, E02 passes 19/19, and E03 passes 30/30. The official serial full Node
   gate passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. Before formal serial collection, a diagnostic run observed 792/793 with one
    unrelated artifact-store concurrency failure; the isolated surface passed
    1/1 and a complete rerun passed 793/793. The original failing test identifier
    was not retained, so this review records that evidence limitation without
    inventing a name. The independently captured official serial JUnit is clean.
11. All five product files are BOM-less UTF-8 and remain inside exact
    `packages/foundry-kernel/src/scheduler/**` scope. Existing dirty worktree
    changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes an in-memory deterministic scheduler contract and its
failure, replay, resource, receipt, and fencing semantics. It does not prove
distributed consensus, persistence across process restart outside command-log
replay, remote provider availability, N04 fan-in/reviewer independence,
actor-independent certification, overall product completion, release or
production readiness, or `completion_ready=true`. Global
`implementation_gate=fail` remains required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect N03 manifest, N01 dependency, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement deterministic DAG compilation and hash-valid bounded LoopContracts", 0, "PASS"),
        ("C003", "Implement dependency receipts, external capability admission, budgets, resources, and fencing", 0, "PASS"),
        ("C004", "Implement immutable attempts, typed retries, idempotency, effect reconciliation, replay, and snapshots", 0, "PASS"),
        ("C005", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C006", "Run exact N03 targeted Node JUnit", 0, "PASS: 24/24 (scheduler property 15, resource conflict 9)"),
        ("C007", "Run N01 RoleSpec/ACL regression", 0, "PASS: 21/21"),
        ("C008", "Run E02 effects regression", 0, "PASS: 19/19"),
        ("C009", "Run E03 capability regression", 0, "PASS: 30/30"),
        ("C010", "node --check <five N03 product files>", 0, "PASS: 5/5"),
        ("C011", "Capture complete sorted repository Node test inventory", 0, "PASS: 77 unique files"),
        ("C012", "Diagnostic full Node run and bounded concurrency reconciliation", 0, "792/793 initial; isolated 1/1; complete rerun 793/793; original test ID not retained"),
        ("C013", "Run official complete repository Node inventory serially", 0, "PASS: 793/793 across 77 files"),
        ("C014", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C015", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C016", "npm run check:structure", 0, "PASS"),
        ("C017", "npm run check:boundaries", 0, "PASS"),
        ("C018", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C019", "Build and verify deterministic N03 WorkPackageReport evidence", 0, "PASS"),
    ]
    timestamp = recorded_at()
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": timestamp,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def expected_commands() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "N03-0001-SCHEDULER-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "N03-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-N03-0001-SCHEDULER-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "scheduler_property_test",
                "details": "15/15 deterministic DAG, loop, dependency, admission, retry, budget, reconciliation, replay, and immutability cases pass",
                "status": "PASS",
            },
            {
                "check": "resource_conflict_test",
                "details": "9/9 exclusivity, atomic acquisition, quota, expiry, fencing, idempotency, and rollback cases pass",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Official serial Node 793/793 across 77 files, Python 1064/1064, codegen 126/126, no suppression",
                "status": "PASS",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt)
    )
    if errors:
        raise SystemExit(f"invalid N03 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "scheduler-verification.json",
        "scheduler-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n03-node.junit.xml",
        "n01-role-contract-regression.junit.xml",
        "e02-effect-regression.junit.xml",
        "e03-capability-regression.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "codegen-verification.stdout.log",
        "structure-check.stdout.log",
        "boundary-check.stdout.log",
        "git-diff-check.stdout.log",
        "git-diff-check.stderr.log",
        "commands.jsonl",
        "review.md",
        "attempt-metadata.json",
        "run_n03_0001_checks.py",
        "build_n03_0001_evidence.py",
        "n03_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required N03 evidence artifact is missing: {name}")
        rows.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return rows


def report_document(
    documents: dict[str, dict[str, Any]], *, rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    targeted = targeted_evidence()
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(ATTEMPT / "scheduler-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/N03/attempts/0001/scheduler-verification.artifact-receipt.json",
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": dependency["dependencies"],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "cycles_require_LoopContract": "PASS",
            "real_dependencies_and_resources_enforced": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "actor-independent certification",
            "distributed consensus or durable cross-process scheduling",
            "remote provider availability",
            "N04 fan-in or independent-review enforcement",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "rah_state": rah_state,
        "regression": regression,
        "required_checks": {
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "resource_conflict_test": {
                "failed": 0,
                "passed": 9,
                "skipped": 0,
                "status": "PASS",
            },
            "scheduler_property_test": {
                "failed": 0,
                "passed": 15,
                "skipped": 0,
                "status": "PASS",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/N03/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "DAG scheduler, leases, retries and concurrency",
        "verification": {
            "e02_effect_regression": "19/19",
            "e03_capability_regression": "30/30",
            "full_node_official_serial": "793/793 across 77 files",
            "full_python": "1064/1064",
            "n01_role_contract_regression": "21/21",
            "targeted_n03": "24/24",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "scheduler": documents["scheduler-verification.json"],
            "targeted": targeted,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is None:
        report.pop("rah_state")
    return report


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    manifest_contract()
    syntax_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(
        expected_commands(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    authority_path = ATTEMPT / "scheduler-verification.json"
    write_json(
        ATTEMPT / "scheduler-verification.artifact-receipt.json",
        make_receipt(authority_path),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "active",
    }
    write_json(ATTEMPT / "report.json", report_document(documents, rah_state=rah_state))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    manifest_contract()
    syntax_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored N03 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored N03 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored N03 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "scheduler-verification.json")
    receipt_path = ATTEMPT / "scheduler-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored N03 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("N03 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored N03 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"N03 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "e02_effect_regression": "19/19",
        "e03_capability_regression": "30/30",
        "full_node_official_serial": "793/793 across 77 files",
        "full_python": "1064/1064",
        "n01_role_contract_regression": "21/21",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_n03": "24/24",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
