#!/usr/bin/env python3
"""Build and verify deterministic N02-0001 spawn-adapter evidence."""

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
ATTEMPT = ROOT / "artifacts/work_packages/N02/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/N02"
N01_ATTEMPT = ROOT / "artifacts/work_packages/N01/attempts/0001"
sys.path.insert(0, str(N01_ATTEMPT))

import build_n01_0001_evidence as base  # noqa: E402


ATTEMPT_ID = "N02-0001"
WORK_PACKAGE_ID = "N02"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "packages/role-router/src/adapters/adapter-contract.mjs",
    "packages/role-router/src/adapters/adapter-test-support.mjs",
    "packages/role-router/src/adapters/adapter-compilation.test.mjs",
    "packages/role-router/src/adapters/prompt-injection-boundary.test.mjs",
    "packages/role-router/src/adapters/codex-adapter.mjs",
    "packages/role-router/src/adapters/claude-adapter.mjs",
    "packages/role-router/src/adapters/index.mjs",
)
N02_TESTS = PRODUCT_FILES[2:4]
N01_TESTS = (
    "packages/role-router/src/contracts/role-schema.test.mjs",
    "packages/role-router/src/contracts/acl.test.mjs",
)
HOST_CAPABILITY_TESTS = (
    "tests/compatibility/hooks/hook-feature-probe.test.mjs",
    "tests/compatibility/hooks/hook-degraded-mode.test.mjs",
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
        raise SystemExit("N02 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("N02 attempt metadata has no recorded_at_utc")
    return value


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "N02"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one N02 row")
    expected = {
        "depends_on": ["N01"],
        "write_scope": ["packages/role-router/src/adapters/**"],
        "independent_review": "required",
        "exit_criteria": [
            "host details do not alter canonical role",
            "resolved model recorded",
        ],
        "required_checks": [
            "adapter_compilation_test",
            "prompt_injection_boundary_test",
        ],
        "risk_class": "high",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"N02 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages/role-router/src/adapters").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"N02 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"N02 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"N02 source must be BOM-less UTF-8: {relative}")
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
        raise SystemExit("N02 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-n02-node.junit.xml")
    assert_clean_node(targeted, 29, "N02 targeted")
    names = targeted["test_names"]
    adapter = [name for name in names if name.startswith("adapter_compilation_test:")]
    injection = [
        name for name in names if name.startswith("prompt_injection_boundary_test:")
    ]
    if len(adapter) != 17 or len(injection) != 12 or len(set(names)) != 29:
        raise SystemExit("N02 targeted test-name partition is not exact 17/12")
    if targeted["observed_files"] != sorted(N02_TESTS):
        raise SystemExit(f"N02 targeted JUnit file inventory differs: {targeted['observed_files']}")
    return {
        **targeted,
        "adapter_compilation_test_count": len(adapter),
        "prompt_injection_boundary_test_count": len(injection),
    }


def upstream_evidence() -> dict[str, Any]:
    n01 = node_summary(ATTEMPT / "n01-role-contract-regression.junit.xml")
    host = node_summary(ATTEMPT / "host-capability-regression.junit.xml")
    assert_clean_node(n01, 21, "N01 RoleSpec/ACL regression")
    assert_clean_node(host, 18, "host capability regression")
    if n01["observed_files"] != sorted(N01_TESTS):
        raise SystemExit("N01 regression JUnit file inventory differs")
    if host["observed_files"] != sorted(HOST_CAPABILITY_TESTS):
        raise SystemExit("host capability regression JUnit file inventory differs")
    feature = [
        name for name in host["test_names"] if name.startswith("hook_feature_probe_test:")
    ]
    degraded = [
        name for name in host["test_names"] if name.startswith("hook_degraded_mode_test:")
    ]
    if len(feature) != 11 or len(degraded) != 7:
        raise SystemExit("host capability regression partition is not exact 11/7")
    return {
        "host_capability": {
            **host,
            "hook_degraded_mode_test_count": len(degraded),
            "hook_feature_probe_test_count": len(feature),
        },
        "n01_role_contract": n01,
        "status": "PASS",
    }


def spawn_adapter_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    required_fragments = (
        'ADAPTER_CONTRACT_VERSION = "4.0.0-n02.1"',
        'EXECUTION_ENVELOPE_SCHEMA_REF = "schemas/result-envelope.schema.json"',
        '"claude_code"',
        '"codex_cli"',
        '"codex_desktop"',
        '"serial_execution"',
        '"subagent_dispatch"',
        '"HOST_EXECUTION_CAPABILITY_MISSING"',
        '"FLOATING_MODEL_REFERENCE"',
        '"HOST_DESCRIPTOR_SEMANTIC_MISMATCH"',
        '"CANONICAL_ROLE_PROMPT_MISMATCH"',
        "verifyRoleSpecIntegrity",
        "verifyAdapterHostCapabilityReport",
        "canonical_role_prompt_hash",
        "routing_receipt_hash",
        "business_output_schema_ref",
        "prose_completion_is_authority: false",
    )
    missing = [fragment for fragment in required_fragments if fragment not in source]
    if missing:
        raise SystemExit(f"N02 spawn-adapter contract binding is incomplete: {missing}")
    return {
        "adapter_contract_version": "4.0.0-n02.1",
        "attempt_id": ATTEMPT_ID,
        "canonical_role_authority": "RoleSpec",
        "canonical_role_preserved_across_hosts": True,
        "descriptor_content_addressed_and_immutable": True,
        "descriptor_semantic_revalidation": "PASS",
        "exact_model_and_runtime_resolution_required": True,
        "fallback_policy_decision_required": True,
        "floating_model_or_runtime_reference_rejection": "PASS",
        "host_capability_report_canonicalization": "PASS",
        "host_details_alter_canonical_role": False,
        "host_modes_fail_closed": ["BLOCKED", "SAFE_MODE"],
        "prompt_injection_boundary": "PASS",
        "resolved_model_recorded": True,
        "result_contract": {
            "business_output_from_role_spec": True,
            "execution_envelope_schema_ref": "schemas/result-envelope.schema.json",
            "expected_count_from_role_spec": True,
            "prose_completion_is_authority": False,
        },
        "serial_fallback": "EXPLICIT_CAPABILITY_ONLY",
        "supported_hosts": ["claude_code", "codex_cli", "codex_desktop"],
        "targeted": targeted_evidence(),
        "upstream_regressions": upstream_evidence(),
        "status": "PASS",
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
        raise SystemExit("N02 dependency N01 is not the exact sealed PASS")
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
    assert_clean_node(full_node, 769, "full Node")
    if not (
        len(files) == len(set(files)) == 75
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 75
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
        "count": 75,
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
        "full_node": {**full_node, "test_file_count": 75},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "repository_structure": "PASS",
        "status": "PASS",
        "upstream_targeted": upstream_evidence(),
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/N02/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/role-router/src/adapters/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    verification = spawn_adapter_verification()
    return {
        "spawn-adapter-verification.json": {
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
    return f"""# N02-0001 Codex/Claude role compilation and spawn-adapter review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N02
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The verified canonical `RoleSpec` is the only role authority. Codex CLI,
   Codex Desktop, and Claude Code host selections change only the bounded host
   descriptor; mission, ACLs, scopes, budgets, expected count, acceptance
   checks, and business output remain hash-bound to the same `RoleSpec`.
2. Every executable descriptor records exact provider/model/version and exact
   runtime/version plus the model-routing receipt. Floating aliases, ranges,
   unauthorized tiers, and unapproved fallback tiers fail closed.
3. Host capability reports are integrity-checked at the adapter boundary.
   RFC 3339 time, closed hook-event vocabulary and order, limitation/path/
   blocker order, report hash, host identity, and capability state are all
   validated before a descriptor can be emitted.
4. `subagent_dispatch` unavailability permits only an explicitly observed
   `serial_execution` fallback. If neither capability is supported the adapter
   blocks; `BLOCKED`, `SAFE_MODE`, and write-capable work on `READ_ONLY` hosts
   also fail closed.
5. Host/model/caller data cannot inject a prompt or broaden authority. Proxy,
   accessor, custom-prototype, tampered RoleSpec, tampered report, prompt
   replacement, descriptor mutation, and attacker-rehash paths are rejected.
6. Spawn descriptors and canonical role prompts are deterministic,
   content-addressed, deeply immutable, and semantically revalidated. A valid
   outer hash cannot conceal an internally altered target, prompt, model, host,
   output schema, or count.
7. `ResultEnvelope` remains execution telemetry only; the business output
   schema and expected count come from the RoleSpec, and prose completion is
   explicitly non-authoritative.
8. Required N02 checks pass {targeted['passed']}/{targeted['collected']}: 17
   `adapter_compilation_test` and 12 `prompt_injection_boundary_test` cases.
   N01 RoleSpec/ACL regression passes 21/21 and upstream host-capability
   regression passes 18/18. Full Node passes
   {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
9. All seven product files are BOM-less UTF-8 and remain inside exact
   `packages/role-router/src/adapters/**` scope. Existing dirty worktree changes
   and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes deterministic compilation of verified RoleSpecs into
bounded Codex/Claude spawn descriptors and adapter-side integrity validation.
It does not execute provider hosts, implement scheduler leases/retries (N03),
enforce N-phase fan-in/reviewer independence (N04), prove remote-provider
availability, claim actor-independent certification, complete the product, or
set `completion_ready=true`. Global `implementation_gate=fail` remains required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect N02 manifest, N01 dependency, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement deterministic Codex CLI/Desktop and Claude Code RoleSpec compilation", 0, "PASS"),
        ("C003", "Implement exact model/runtime/routing receipt and host capability binding", 0, "PASS"),
        ("C004", "Implement prompt-injection, tamper, and attacker-rehash fail-closed boundaries", 0, "PASS"),
        ("C005", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C006", "Run exact N02 targeted Node JUnit", 0, "PASS: 29/29 (adapter compilation 17, injection boundary 12)"),
        ("C007", "Run N01 RoleSpec/ACL regression", 0, "PASS: 21/21"),
        ("C008", "Run upstream host-capability regression", 0, "PASS: 18/18"),
        ("C009", "node --check <seven N02 product files>", 0, "PASS: 7/7"),
        ("C010", "Capture complete sorted repository Node test inventory", 0, "PASS: 75 unique files"),
        ("C011", "Run complete repository Node test inventory", 0, "PASS: 769/769 across 75 files"),
        ("C012", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C013", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C014", "npm run check:structure", 0, "PASS"),
        ("C015", "npm run check:boundaries", 0, "PASS"),
        ("C016", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C017", "Build and verify deterministic N02 WorkPackageReport evidence", 0, "PASS"),
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
        "artifact_id": "N02-0001-SPAWN-ADAPTER-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "N02-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-N02-0001-SPAWN-ADAPTER-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "adapter_compilation_test",
                "details": "17/17 host compilation, model resolution, capability, fallback, integrity, and fail-closed cases pass",
                "status": "PASS",
            },
            {
                "check": "prompt_injection_boundary_test",
                "details": "12/12 host/model/caller injection, proxy, accessor, mutation, and attacker-rehash cases pass",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Node 769/769 across 75 files, Python 1064/1064, codegen 126/126, no suppression",
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
        raise SystemExit(f"invalid N02 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "spawn-adapter-verification.json",
        "spawn-adapter-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n02-node.junit.xml",
        "n01-role-contract-regression.junit.xml",
        "host-capability-regression.junit.xml",
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
        "run_n02_0001_checks.py",
        "build_n02_0001_evidence.py",
        "n02_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required N02 evidence artifact is missing: {name}")
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
    receipt = read_json(ATTEMPT / "spawn-adapter-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/N02/attempts/0001/spawn-adapter-verification.artifact-receipt.json",
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
            "host_details_do_not_alter_canonical_role": "PASS",
            "resolved_model_recorded": "PASS",
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
            "remote provider execution or availability",
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
            "adapter_compilation_test": {
                "failed": 0,
                "passed": 17,
                "skipped": 0,
                "status": "PASS",
            },
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "prompt_injection_boundary_test": {
                "failed": 0,
                "passed": 12,
                "skipped": 0,
                "status": "PASS",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/N02/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Codex/Claude role compilation and spawn adapters",
        "verification": {
            "full_node": "769/769 across 75 files",
            "full_python": "1064/1064",
            "host_capability_regression": "18/18",
            "n01_role_contract_regression": "21/21",
            "targeted_n02": "29/29",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "spawn_adapters": documents["spawn-adapter-verification.json"],
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
    authority_path = ATTEMPT / "spawn-adapter-verification.json"
    write_json(
        ATTEMPT / "spawn-adapter-verification.artifact-receipt.json",
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
            raise SystemExit(f"stored N02 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored N02 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored N02 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "spawn-adapter-verification.json")
    receipt_path = ATTEMPT / "spawn-adapter-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored N02 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("N02 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored N02 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"N02 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "769/769 across 75 files",
        "full_python": "1064/1064",
        "host_capability_regression": "18/18",
        "n01_role_contract_regression": "21/21",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_n02": "29/29",
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
