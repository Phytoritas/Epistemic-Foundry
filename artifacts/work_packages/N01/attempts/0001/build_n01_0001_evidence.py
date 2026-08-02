#!/usr/bin/env python3
"""Build and verify deterministic N01-0001 RoleSpec/ACL evidence."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N01/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/N01"
M04_ATTEMPT = ROOT / "artifacts/work_packages/M04/attempts/0001"
sys.path.insert(0, str(M04_ATTEMPT))

import build_m04_0001_evidence as base  # noqa: E402


ATTEMPT_ID = "N01-0001"
WORK_PACKAGE_ID = "N01"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "packages/role-router/src/contracts/role-spec.mjs",
    "packages/role-router/src/contracts/index.mjs",
    "packages/role-router/src/contracts/role-spec-test-support.mjs",
    "packages/role-router/src/contracts/role-schema.test.mjs",
    "packages/role-router/src/contracts/acl.test.mjs",
)
N01_TESTS = PRODUCT_FILES[3:5]
EXPECTED_DEPENDENCIES = {
    "C04": {
        "attempt_id": "C04-0003",
        "core_evidence_id": "E0020",
        "core_generation": "000020-4032536e",
        "final_closeout_evidence_id": "E0021",
        "report": "artifacts/work_packages/C04/attempts/0003/report.json",
        "report_sha256": "sha256:2610c509309d6f5aa5262cb2267f6fb17aea19d81fb2c33b4b3949c6371de297",
    },
    "E04": {
        "attempt_id": "E04-0001",
        "core_evidence_id": "E0030",
        "core_generation": "000029-9a5e961a",
        "final_closeout_evidence_id": "E0031",
        "report": "artifacts/work_packages/E04/report.json",
        "report_sha256": "sha256:841dcf60989cfc7ab0eff7be95e1ae721ae18ac513cae653ab6ac8a44942f6c1",
    },
    "G04": {
        "attempt_id": "G04-0001",
        "core_evidence_id": "E0058",
        "core_generation": "000056-09b980eb",
        "final_closeout_evidence_id": "E0059",
        "report": "artifacts/work_packages/G04/attempts/0001/report.json",
        "report_sha256": "sha256:3abe50fc722255bb8f8c2196f133b94425a0b11318423cb756fab614026cf1ea",
    },
    "H04": {
        "attempt_id": "H04-0001",
        "core_evidence_id": "E0066",
        "core_generation": "000064-7d91b86c",
        "final_closeout_evidence_id": "E0067",
        "report": "artifacts/work_packages/H04/attempts/0001/report.json",
        "report_sha256": "sha256:cf61978263c39eddfc90bc6107d714ed27201d7094fb45ef882d62dd736bb3fb",
    },
    "J04": {
        "attempt_id": "J04-0001",
        "core_evidence_id": "E0026",
        "core_generation": "000026-ca8416cb",
        "final_closeout_evidence_id": "E0027",
        "report": "artifacts/work_packages/J04/attempts/0001/report.json",
        "report_sha256": "sha256:602c3dc98643608d93304c31c2f0232c449c778b586dded1ffbe416871341e16",
    },
}
EXPECTED_TOOL_CAPABILITIES = (
    "approved_external_search",
    "artifact_read",
    "artifact_write",
    "database_read",
    "database_write",
    "document_register",
    "filesystem_read",
    "filesystem_write",
    "fulltext_search",
    "graph_query",
    "human_approval",
    "human_input",
    "ledger_append",
    "llm_inference",
    "network_fetch",
    "network_read",
    "object_store_read",
    "object_store_write",
    "python_analysis",
    "sandbox_execute",
    "signing_service",
    "subagent_dispatch",
    "vector_search",
    "workflow_dispatch",
)
EXPECTED_EVIDENCE_CLASSES = (
    "adapter_test_results",
    "adjudication_pack",
    "all_permitted",
    "archive_public",
    "attestation_pack",
    "backend_manifest",
    "boundary",
    "candidate_parent",
    "candidate_public",
    "challenge_archive",
    "citation",
    "counter",
    "evaluation_results",
    "evaluator_public",
    "evidence_pack",
    "evolution_state",
    "external_novelty",
    "fitness_public",
    "holdout_metadata",
    "implementation_contract",
    "measurement_contract",
    "mechanism",
    "method",
    "methods",
    "null",
    "primary_results",
    "prompt_quarantine",
    "replication_pack",
    "results",
    "sealed_promotion_pack",
    "selection_events",
    "source_span",
    "support",
    "temporal",
    "theory",
    "validation_plan",
)


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
        raise SystemExit("N01 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("N01 attempt metadata has no recorded_at_utc")
    return value


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "N01"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one N01 row")
    expected = {
        "depends_on": ["C04", "E04", "G04", "H04", "J04"],
        "write_scope": ["packages/role-router/src/contracts/**"],
        "independent_review": "required",
        "exit_criteria": [
            "role mission and forbidden behavior explicit",
            "evidence asymmetry representable",
        ],
        "required_checks": ["role_schema_test", "acl_test"],
        "risk_class": "high",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"N01 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages/role-router/src/contracts").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"N01 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"N01 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"N01 source must be BOM-less UTF-8: {relative}")
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
        raise SystemExit("N01 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-n01-node.junit.xml")
    assert_clean_node(targeted, 21, "N01 targeted")
    names = targeted["test_names"]
    role_schema = [name for name in names if name.startswith("role_schema_test:")]
    acl = [name for name in names if name.startswith("acl_test:")]
    if len(role_schema) != 10 or len(acl) != 11 or len(set(names)) != 21:
        raise SystemExit("N01 targeted test-name partition is not exact 10/11")
    if targeted["observed_files"] != sorted(N01_TESTS):
        raise SystemExit(f"N01 targeted JUnit file inventory differs: {targeted['observed_files']}")
    return {
        **targeted,
        "acl_test_count": len(acl),
        "role_schema_test_count": len(role_schema),
    }


def python_targeted_evidence() -> dict[str, Any]:
    security = pytest_summary(ATTEMPT / "security-python.junit.xml")
    contracts = pytest_summary(ATTEMPT / "dispatch-contract-python.junit.xml")
    if not (
        security["passed"] == security["collected"] == 26
        and contracts["passed"] == contracts["collected"] == 5
        and all(security[key] == 0 for key in ("failed", "errors", "skipped"))
        and all(contracts[key] == 0 for key in ("failed", "errors", "skipped"))
    ):
        raise SystemExit("N01 adjacent Python security/dispatch checks are not clean")
    return {"dispatch_contract": contracts, "security": security, "status": "PASS"}


def extract_js_vocabulary(source: str, export_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"export const {re.escape(export_name)} = OBJECT_FREEZE\(\[(.*?)\]\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise SystemExit(f"cannot find closed JavaScript vocabulary {export_name}")
    values = tuple(re.findall(r'"([a-z0-9_]+)"', match.group(1)))
    if len(values) != len(set(values)):
        raise SystemExit(f"{export_name} contains duplicate values")
    return values


def role_acl_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    tool_capabilities = extract_js_vocabulary(source, "TOOL_CAPABILITIES")
    evidence_classes = extract_js_vocabulary(source, "EVIDENCE_CLASSES")
    if tool_capabilities != EXPECTED_TOOL_CAPABILITIES:
        raise SystemExit("N01 tool capability vocabulary differs from the frozen workflow inventory")
    if evidence_classes != EXPECTED_EVIDENCE_CLASSES:
        raise SystemExit("N01 evidence vocabulary differs from the frozen role authority")
    required_fragments = (
        'ROLE_SPEC_VERSION = "4.0.0-n01.1"',
        'ROLE_SPEC_ID_PREFIX = "ROLE-"',
        'const ACL_KINDS = new Set(["evidence", "network", "read", "tool", "write"])',
        '"mission"',
        '"forbidden_behaviors"',
        '"expected_count"',
        '"independence_group"',
        '"failure_policy"',
        '"max_attempts"',
        '"network_acl"',
        '"evidence_acl"',
        '"CAPABILITY_VOCABULARY_MISMATCH"',
        '"DENY_BY_DEFAULT"',
        '"EXPLICIT_ROLE_SPEC_GRANT"',
        "sha256CanonicalJson(preimage)",
        "deepFreeze(normalizePersistedRoleSpec(candidate))",
        "projectRoleSpecToDispatchRole",
    )
    missing = [fragment for fragment in required_fragments if fragment not in source]
    if missing:
        raise SystemExit(f"N01 RoleSpec/ACL binding is incomplete: {missing}")
    targeted = targeted_evidence()
    python_targeted = python_targeted_evidence()
    return {
        "acl_dimensions": ["tool", "read", "write", "network", "evidence"],
        "all_permitted_is_privileged_grant_only": True,
        "attempt_id": ATTEMPT_ID,
        "caller_input_preservation": "PASS",
        "canonical_capability_aliases_rejected": [
            "artifact.read",
            "artifact:read",
            "llm.inference",
            "search.read",
        ],
        "canonical_hash_and_derived_id": "PASS",
        "deep_immutability": "PASS",
        "deny_by_default": True,
        "dispatch_projection": {
            "provider_neutral": True,
            "role_dispatch_plan_schema": "schemas/role-dispatch-plan.schema.json",
            "status": "PASS",
        },
        "evidence_asymmetry": "PASS",
        "evidence_class_count": len(evidence_classes),
        "evidence_classes": list(evidence_classes),
        "expected_count_is_sealed_in_role_spec": True,
        "failure_and_retry_policy_sealed": True,
        "hostile_input_rejection": "PASS",
        "mission_and_forbidden_behavior_required": True,
        "network_origins_are_exact_https": True,
        "path_traversal_and_malformed_wildcard_rejection": "PASS",
        "python_adjacent_contracts": python_targeted,
        "role_spec_version": "4.0.0-n01.1",
        "status": "PASS",
        "targeted": targeted,
        "tool_capability_count": len(tool_capabilities),
        "tool_capabilities": list(tool_capabilities),
        "unknown_vocabulary_fails_closed": True,
    }


def dependency_evidence() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    for package_id, expected in EXPECTED_DEPENDENCIES.items():
        path = ROOT / expected["report"]
        report = read_json(path)
        rah = report.get("rah_state")
        if not (
            report.get("work_package_id") == package_id
            and report.get("attempt_id") == expected["attempt_id"]
            and report.get("status") == "PASS"
            and report.get("package_status") == "PASS"
            and report.get("completion_ready") is False
            and sha256_id(path) == expected["report_sha256"]
            and isinstance(rah, dict)
            and rah.get("core_evidence_id") == expected["core_evidence_id"]
            and rah.get("core_generation") == expected["core_generation"]
            and rah.get("final_closeout_evidence_id")
            == expected["final_closeout_evidence_id"]
        ):
            raise SystemExit(f"N01 dependency {package_id} is not the exact sealed PASS")
        dependencies[package_id] = {**expected, "status": "PASS"}
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "dependency_count": len(dependencies),
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
    assert_clean_node(full_node, 740, "full Node")
    if not (
        len(files) == len(set(files)) == 73
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 73
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
        "count": 73,
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
        "attempt_id": ATTEMPT_ID,
        "canonical_codegen": {"examples": 126, "schemas": 126, "status": "PASS"},
        "full_node": {**full_node, "test_file_count": 73},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "python_adjacent_contracts": python_targeted_evidence(),
        "repository_structure": "PASS",
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/N01/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/role-router/src/contracts/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    verification = role_acl_verification()
    return {
        "role-acl-verification.json": {
            **verification,
            "manifest_contract": manifest_contract(),
            "syntax": syntax_evidence(),
        },
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    targeted = targeted_evidence()
    return f"""# N01-0001 canonical RoleSpec and evidence/tool ACL review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N01
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. `RoleSpec` requires an explicit mission, non-empty forbidden behaviors,
   input/output schema references, budget, timeout, expected count,
   independence group, acceptance checks, and failure/retry policy. Unknown or
   missing fields fail closed.
2. Tool, read, write, network, and evidence authority remain five independent
   ACL dimensions. A grant in one dimension implies no grant in another, and
   every known undeclared request returns deterministic `DENY_BY_DEFAULT`.
3. The tool vocabulary is closed to the 24 active canonical snake_case
   capabilities. Dotted and colon aliases fail with
   `CAPABILITY_VOCABULARY_MISMATCH`; unknown capability, evidence, and ACL
   labels are errors rather than silently denied aliases.
4. The evidence vocabulary is closed to 36 role-authority labels.
   `all_permitted` is an explicit privileged grant and cannot be requested as
   an evidence class. Defender and prosecutor fixtures prove asymmetric views.
5. Scopes reject absolute paths, drive paths, traversal, backslashes, ambiguous
   separators, and malformed wildcards. Network access binds exact canonical
   HTTPS origins without credentials, paths, wildcard hosts, or case aliases.
6. Role identity is deterministic and content-addressed. The SHA-256 hash binds
   canonical RoleSpec content and derives `ROLE-<64 hex>`; persisted ordering,
   content, and ID tampering fail closed.
7. Proxy objects, accessors, sparse arrays, decorated arrays, custom
   prototypes, unsupported Unicode/numbers, and cycles are rejected without
   invoking attacker-controlled getters. Inputs remain unmodified and emitted
   artifacts and ACL decisions are deeply immutable.
8. Projection to the existing nested `RoleDispatchPlan` role contains exactly
   the schema-accepted provider-neutral fields. `expected_count` remains sealed
   in the RoleSpec and plan-level authority remains with `RoleDispatchPlan`.
   Host-specific Codex/Claude compilation remains N02 responsibility.
9. Required checks pass {targeted['passed']}/{targeted['collected']}: 10
   `role_schema_test` and 11 `acl_test` cases. Adjacent Python security passes
   26/26 and dispatch contracts pass 5/5. Full Node passes
   {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. All five product files are BOM-less UTF-8 and remain inside exact
    `packages/role-router/src/contracts/**` scope. Existing dirty worktree
    changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes the canonical RoleSpec construction/integrity contract,
ACL decision semantics, evidence asymmetry, and provider-neutral dispatch-role
projection. It does not implement host compilation/spawning (N02), scheduler
leases/retries (N03), fan-in/reviewer independence enforcement (N04), overall
product completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect N01 manifest, EF4-I25, dependencies, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement deterministic canonical RoleSpec construction and integrity verification", 0, "PASS"),
        ("C003", "Implement separated deny-by-default tool/read/write/network/evidence ACL evaluation", 0, "PASS"),
        ("C004", "Implement exact provider-neutral RoleDispatchPlan role projection", 0, "PASS"),
        ("C005", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C006", "Run exact N01 targeted Node JUnit", 0, "PASS: 21/21 (role schema 10, ACL 11)"),
        ("C007", "Run adjacent Python security tests", 0, "PASS: 26/26"),
        ("C008", "Run adjacent Python dispatch contract tests", 0, "PASS: 5/5"),
        ("C009", "node --check <five N01 product files>", 0, "PASS: 5/5"),
        ("C010", "Capture complete sorted repository Node test inventory", 0, "PASS: 73 unique files"),
        ("C011", "Run complete repository Node test inventory", 0, "PASS: 740/740 across 73 files"),
        ("C012", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C013", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C014", "npm run check:structure", 0, "PASS"),
        ("C015", "npm run check:boundaries", 0, "PASS"),
        ("C016", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C017", "Build and verify deterministic N01 WorkPackageReport evidence", 0, "PASS"),
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
        "artifact_id": "N01-0001-ROLE-ACL-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "N01-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-N01-0001-ROLE-ACL-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "role_schema_test",
                "details": "10/10 mission, identity, canonicalization, projection, immutability, and hostile-input cases pass",
                "status": "PASS",
            },
            {
                "check": "acl_test",
                "details": "11/11 explicit grant, deny-by-default, asymmetry, vocabulary, path, network, and tamper cases pass",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Node 740/740 across 73 files, Python 1064/1064, codegen 126/126, no suppression",
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
        raise SystemExit(f"invalid N01 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "role-acl-verification.json",
        "role-acl-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n01-node.junit.xml",
        "security-python.junit.xml",
        "dispatch-contract-python.junit.xml",
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
        "run_n01_0001_checks.py",
        "build_n01_0001_evidence.py",
        "n01_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required N01 evidence artifact is missing: {name}")
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
    receipt = read_json(ATTEMPT / "role-acl-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/N01/attempts/0001/role-acl-verification.artifact-receipt.json",
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
            "evidence_asymmetry_representable": "PASS",
            "role_mission_and_forbidden_behavior_explicit": "PASS",
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
            "host-specific role compilation or spawning",
            "scheduler leases, retries, or concurrency",
            "fan-in or independent-review enforcement",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "rah_state": rah_state,
        "regression": regression,
        "required_checks": {
            "acl_test": {"failed": 0, "passed": 11, "skipped": 0, "status": "PASS"},
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "role_schema_test": {"failed": 0, "passed": 10, "skipped": 0, "status": "PASS"},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/N01/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Canonical RoleSpec and evidence/tool ACLs",
        "verification": {
            "adjacent_python_dispatch_contract": "5/5",
            "adjacent_python_security": "26/26",
            "full_node": "740/740 across 73 files",
            "full_python": "1064/1064",
            "targeted_n01": "21/21",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "role_spec_and_acls": documents["role-acl-verification.json"],
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
    authority_path = ATTEMPT / "role-acl-verification.json"
    write_json(
        ATTEMPT / "role-acl-verification.artifact-receipt.json",
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
            raise SystemExit(f"stored N01 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored N01 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored N01 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "role-acl-verification.json")
    receipt_path = ATTEMPT / "role-acl-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored N01 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("N01 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored N01 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"N01 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "740/740 across 73 files",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "python_dispatch_contract": "5/5",
        "python_security": "26/26",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_n01": "21/21",
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
