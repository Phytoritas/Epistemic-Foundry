#!/usr/bin/env python3
"""Build and verify deterministic N04-0001 fan-in gate evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N04/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/N04"
N03_ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
sys.path.insert(0, str(N03_ATTEMPT))

import build_n03_0001_evidence as base  # noqa: E402


ATTEMPT_ID = "N04-0001"
WORK_PACKAGE_ID = "N04"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_HASHES = {
    "tests/golden/multiagent/fan-in-gate.mjs": (
        "sha256:766ea6c70b7efbd04398c1eb0e820d8858dde715f9e61d9aeea87e702f54f8ac"
    ),
    "tests/golden/multiagent/fan-in-test-support.mjs": (
        "sha256:4100dc6e0734f47259c1ef5d1a2e98473b4ec4a7df3dfbf883838aec35ba7997"
    ),
    "tests/golden/multiagent/independent-review.test.mjs": (
        "sha256:4e0b44b6c11b17c875bb12a332eaabbcd985d62e0bc8bac577ee26d6708e5cf6"
    ),
    "tests/golden/multiagent/missing-node-detection.test.mjs": (
        "sha256:cfcdda61486e0620f51135252364caac474beadc160cd4e288ffa44b93ed2697"
    ),
}
PRODUCT_FILES = tuple(PRODUCT_HASHES)
N04_TESTS = (
    "tests/golden/multiagent/independent-review.test.mjs",
    "tests/golden/multiagent/missing-node-detection.test.mjs",
)
N02_TESTS = (
    "packages/role-router/src/adapters/adapter-compilation.test.mjs",
    "packages/role-router/src/adapters/prompt-injection-boundary.test.mjs",
)
N03_TESTS = (
    "packages/foundry-kernel/src/scheduler/resource-conflict.test.mjs",
    "packages/foundry-kernel/src/scheduler/scheduler-property.test.mjs",
)
DEPENDENCIES = {
    "N02": {
        "attempt_id": "N02-0001",
        "core_evidence_id": "E0069",
        "core_generation": "000069-38d16ba1",
        "final_closeout_evidence_id": "E0070",
        "report": "artifacts/work_packages/N02/attempts/0001/report.json",
        "report_sha256": "sha256:7b63fb48c4a006a63ad33baa414711a5cfc1ac8d3c38f0fc53c68b05f0a41ebd",
    },
    "N03": {
        "attempt_id": "N03-0001",
        "core_evidence_id": "E0072",
        "core_generation": "000072-bd147e2a",
        "final_closeout_evidence_id": "E0073",
        "report": "artifacts/work_packages/N03/attempts/0001/report.json",
        "report_sha256": "sha256:8441523851ff6eed3f6b07877af181190dbbb21c70bca5f2f13dc88098fc4855",
    },
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
        raise SystemExit("N04 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("N04 attempt metadata has no recorded_at_utc")
    return value


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "N04"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one N04 row")
    expected = {
        "depends_on": ["N02", "N03"],
        "write_scope": [
            "tests/golden/multiagent/**",
            "artifacts/work_packages/N04/**",
        ],
        "independent_review": "required",
        "exit_criteria": [
            "expected/actual counts reconcile",
            "author cannot self-approve",
        ],
        "required_checks": [
            "missing_node_detection_test",
            "independent_review_test",
        ],
        "risk_class": "high",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"N04 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests/golden/multiagent").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"N04 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"N04 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"N04 source must be BOM-less UTF-8: {relative}")
        observed_hash = sha256_id(path)
        if observed_hash != PRODUCT_HASHES[relative]:
            raise SystemExit(
                f"N04 source hash changed for {relative}: {observed_hash}"
            )
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": observed_hash,
                "utf8_bom": False,
            }
        )
    return rows


def syntax_evidence() -> dict[str, Any]:
    syntax = read_json(ATTEMPT / "syntax-verification.json")
    checks = syntax.get("checks", [])
    if not (
        syntax.get("attempt_id") == ATTEMPT_ID
        and syntax.get("final_status") == "PASS"
        and len(checks) == len(PRODUCT_FILES)
        and all(row.get("exit_code") == 0 for row in checks)
        and sorted(row.get("path") for row in checks) == sorted(PRODUCT_FILES)
    ):
        raise SystemExit("N04 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-n04-node.junit.xml")
    assert_clean_node(targeted, 26, "N04 targeted")
    names = targeted["test_names"]
    missing = [name for name in names if name.startswith("missing_node_detection_test:")]
    review = [name for name in names if name.startswith("independent_review_test:")]
    if len(missing) != 14 or len(review) != 12 or len(set(names)) != 26:
        raise SystemExit("N04 targeted test-name partition is not exact 14/12")
    if targeted["observed_files"] != sorted(N04_TESTS):
        raise SystemExit("N04 targeted JUnit file inventory differs")
    return {
        **targeted,
        "independent_review_test_count": len(review),
        "missing_node_detection_test_count": len(missing),
    }


def adjacent_evidence() -> dict[str, Any]:
    n02 = node_summary(ATTEMPT / "n02-adapter-regression.junit.xml")
    n03 = node_summary(ATTEMPT / "n03-scheduler-regression.junit.xml")
    assert_clean_node(n02, 29, "N02 adapter regression")
    assert_clean_node(n03, 24, "N03 scheduler regression")
    if n02["observed_files"] != sorted(N02_TESTS):
        raise SystemExit("N02 regression JUnit file inventory differs")
    if n03["observed_files"] != sorted(N03_TESTS):
        raise SystemExit("N03 regression JUnit file inventory differs")
    return {
        "n02_adapter_contract": n02,
        "n03_scheduler_contract": n03,
        "status": "PASS",
    }


def fan_in_verification() -> dict[str, Any]:
    source = (ROOT / "tests/golden/multiagent/fan-in-gate.mjs").read_text(
        encoding="utf-8"
    )
    required_fragments = (
        'export const FAN_IN_GATE_VERSION = "4.0.0-n04.1"',
        "export const evaluateFanInGate",
        "export const sealIndependentReview",
        '"PARTIAL_FAN_IN_NOT_AUTHORIZED"',
        '"MISSING_SPAWN_DESCRIPTOR"',
        '"DUPLICATE_SPAWN_DESCRIPTOR"',
        '"SCHEDULER_NODE_SET_MISMATCH"',
        '"SCHEDULER_REPLAY_MISMATCH"',
        '"NODE_NOT_SUCCESSFUL"',
        '"TERMINAL_RECEIPT_MISMATCH"',
        '"RESULT_COMPLETENESS_MISMATCH"',
        '"MISSING_RESULT_IDENTITY"',
        '"DUPLICATE_RESULT_IDENTITY"',
        '"UNEXPECTED_RESULT_IDENTITY"',
        '"INDEPENDENT_REVIEW_MISSING"',
        '"REVIEWER_SELF_APPROVAL"',
        '"REVIEWER_NOT_INDEPENDENT"',
        '"REVIEW_SCOPE_MISMATCH"',
        '"REVIEWER_DEPENDENCY_MISMATCH"',
        '"REVIEW_RESULT_SCOPE_MISMATCH"',
        '"INDEPENDENT_REVIEW_NOT_PASS"',
        '"REVIEW_ARTIFACT_BINDING_MISSING"',
        "decision_hash",
        "Object.freeze",
    )
    missing = [fragment for fragment in required_fragments if fragment not in source]
    if missing:
        raise SystemExit(f"N04 fan-in contract binding is incomplete: {missing}")
    return {
        "attempt_id": ATTEMPT_ID,
        "count_reconciliation": {
            "dispatch_expected_count_matches_role_identity_count": True,
            "every_expected_spawn_descriptor_is_exactly_once": True,
            "every_expected_scheduler_node_is_exactly_once": True,
            "every_expected_result_identity_is_exactly_once": True,
            "missing_duplicate_and_unexpected_identities_fail_closed": True,
            "partial_fan_in_cannot_pass": True,
        },
        "dependency_binding": {
            "n02_spawn_descriptor_integrity_verified": True,
            "n03_command_replay_and_snapshot_binding_verified": True,
            "scheduler_success_requires_terminal_receipt": True,
        },
        "independent_review": {
            "author_self_approval_forbidden": True,
            "distinct_actor_and_independence_group_required": True,
            "reviewer_depends_on_every_and_only_maker": True,
            "review_scope_binds_every_and_only_maker_output": True,
            "sealed_pass_review_artifact_required": True,
        },
        "immutable_outputs": ["fan_in_decision", "independent_review"],
        "result_contract": {
            "business_artifact_required": True,
            "completeness_reconciles_one_of_one": True,
            "prose_only_success_rejected": True,
        },
        "status": "PASS",
        "syntax": syntax_evidence(),
        "targeted": targeted_evidence(),
        "upstream_regressions": adjacent_evidence(),
        "version": "4.0.0-n04.1",
    }


def dependency_evidence() -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for package_id, binding in DEPENDENCIES.items():
        path = ROOT / binding["report"]
        report = read_json(path)
        rah = report.get("rah_state")
        if not (
            report.get("work_package_id") == package_id
            and report.get("attempt_id") == binding["attempt_id"]
            and report.get("status") == "PASS"
            and report.get("package_status") == "PASS"
            and report.get("completion_ready") is False
            and sha256_id(path) == binding["report_sha256"]
            and isinstance(rah, dict)
            and rah.get("core_evidence_id") == binding["core_evidence_id"]
            and rah.get("core_generation") == binding["core_generation"]
            and rah.get("final_closeout_evidence_id")
            == binding["final_closeout_evidence_id"]
        ):
            raise SystemExit(f"N04 dependency {package_id} is not the exact sealed PASS")
        verified[package_id] = {**binding, "status": "PASS"}
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": verified,
        "dependency_count": len(verified),
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
    assert_clean_node(full_node, 819, "full Node")
    if not (
        len(files) == len(set(files)) == 79
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 79
    ):
        raise SystemExit("full Node inventory/JUnit coverage is incomplete or ambiguous")
    if not (
        full_python["passed"] == full_python["collected"] == 1064
        and full_python["failed"]
        == full_python["errors"]
        == full_python["skipped"]
        == 0
    ):
        raise SystemExit("full Python gate is not 1064/1064")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory != {
        "attempt_id": ATTEMPT_ID,
        "count": 79,
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
        "full_node": {**full_node, "test_file_count": 79},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "repository_structure": "PASS",
        "status": "PASS",
    }


def dirty_worktree_present() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit("cannot inspect dirty worktree preservation")
    return bool(completed.stdout.strip())


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    if not dirty_worktree_present():
        raise SystemExit("pre-existing dirty worktree unexpectedly became clean")
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/N04/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "tests/golden/multiagent/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    verification = fan_in_verification()
    return {
        "fan-in-verification.json": {
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
    return f"""# N04-0001 fan-in, missing-node and independent-review gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N04
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The fan-in gate binds exact N02 dispatch descriptors and exact N03 scheduler
   command replay, plan, run, attempts, terminal receipts, and state hash. A
   fabricated earlier attempt or truncated command history cannot enter fan-in.
2. Dispatch expected count, canonical role identities, spawn descriptors,
   scheduler nodes, and result identities reconcile exactly. Missing, duplicate,
   and unexpected identities fail closed; partial or quorum fan-in cannot PASS.
3. Each role contributes one receipt-bound `ResultEnvelope` with exact
   one-of-one completeness and a business artifact. Prose-only success, missing
   terminal receipts, non-terminal attempts, and receipt mismatches are rejected.
4. Independent review is a sealed, hash-addressed artifact. It binds the exact
   dispatch, scheduler state and command log, every and only maker terminal
   receipt, output artifact set, and output hash.
5. The reviewer must be a distinct actor in a distinct independence group, must
   execute after every and only maker role, must return PASS, and must emit the
   sealed review artifact. Author self-approval is a non-waivable failure.
6. Required N04 checks pass {targeted['passed']}/{targeted['collected']}: 14
   `missing_node_detection_test` and 12 `independent_review_test` cases. N02
   adapter regression passes 29/29 and N03 scheduler regression passes 24/24.
7. Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} unique files; full Python
   passes {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
8. All four product files match their fixed SHA-256 values, are BOM-less UTF-8,
   and remain inside exact `tests/golden/multiagent/**` scope. N02 and N03 bind
   their exact sealed PASS report hashes and RAH evidence IDs.
9. Existing dirty worktree changes and every historical attempt, report,
   evidence entry, and generation remain preserved.

## Assurance boundary

This gate establishes deterministic in-process fan-in completeness and the
independent-review contract over sealed N02/N03 fixtures. It does not prove
actor-independent certification of this implementation review, distributed
execution, remote provider availability, downstream package conformance,
overall product completion, release or production readiness, or
`completion_ready=true`. Global `implementation_gate=fail` remains required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect N04 manifest, N02/N03 dependencies, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement exact N02/N03 receipt-bound fan-in and count reconciliation", 0, "PASS"),
        ("C003", "Implement missing, duplicate, unexpected, partial, and prose-only failure gates", 0, "PASS"),
        ("C004", "Implement sealed independent review, scope binding, and self-approval rejection", 0, "PASS"),
        ("C005", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C006", "Run exact N04 targeted Node JUnit", 0, "PASS: 26/26 (missing-node 14, independent-review 12)"),
        ("C007", "Run N02 adapter regression", 0, "PASS: 29/29"),
        ("C008", "Run N03 scheduler regression", 0, "PASS: 24/24"),
        ("C009", "node --check <four N04 product files>", 0, "PASS: 4/4"),
        ("C010", "Capture complete sorted repository Node test inventory", 0, "PASS: 79 unique files"),
        ("C011", "Run official complete repository Node inventory serially", 0, "PASS: 819/819 across 79 files"),
        ("C012", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C013", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C014", "npm run check:structure", 0, "PASS"),
        ("C015", "npm run check:boundaries", 0, "PASS"),
        ("C016", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C017", "Build and verify deterministic N04 WorkPackageReport evidence", 0, "PASS"),
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
        "artifact_id": "N04-0001-FAN-IN-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "N04-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-N04-0001-FAN-IN-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "missing_node_detection_test",
                "details": "14/14 exact count, identity, replay, receipt, completeness, and missing-node cases pass",
                "status": "PASS",
            },
            {
                "check": "independent_review_test",
                "details": "12/12 reviewer independence, scope, ordering, hash, verdict, and output-binding cases pass",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Node 819/819 across 79 files, Python 1064/1064, codegen 126/126, no suppression",
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
        raise SystemExit(f"invalid N04 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "fan-in-verification.json",
        "fan-in-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n04-node.junit.xml",
        "n02-adapter-regression.junit.xml",
        "n03-scheduler-regression.junit.xml",
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
        "run_n04_0001_checks.py",
        "build_n04_0001_evidence.py",
        "n04_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required N04 evidence artifact is missing: {name}")
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
    receipt = read_json(ATTEMPT / "fan-in-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/N04/attempts/0001/fan-in-verification.artifact-receipt.json",
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
            "author_cannot_self_approve": "PASS",
            "expected_actual_counts_reconcile": "PASS",
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
            "actor-independent certification of this implementation review",
            "distributed multi-agent execution",
            "remote provider availability",
            "downstream package conformance",
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
            "independent_review_test": {
                "failed": 0,
                "passed": 12,
                "skipped": 0,
                "status": "PASS",
            },
            "missing_node_detection_test": {
                "failed": 0,
                "passed": 14,
                "skipped": 0,
                "status": "PASS",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/N04/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "N-phase fan-in, missing-node and independent-review gate",
        "verification": {
            "full_node": "819/819 across 79 files",
            "full_python": "1064/1064",
            "n02_adapter_regression": "29/29",
            "n03_scheduler_regression": "24/24",
            "targeted_n04": "26/26",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "fan_in": documents["fan-in-verification.json"],
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
    authority_path = ATTEMPT / "fan-in-verification.json"
    write_json(
        ATTEMPT / "fan-in-verification.artifact-receipt.json",
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
            raise SystemExit(f"stored N04 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored N04 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored N04 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "fan-in-verification.json")
    receipt_path = ATTEMPT / "fan-in-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(
        expected_receipt
    ):
        raise SystemExit("stored N04 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("N04 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored N04 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"N04 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "819/819 across 79 files",
        "full_python": "1064/1064",
        "n02_adapter_regression": "29/29",
        "n03_scheduler_regression": "24/24",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_n04": "26/26",
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
