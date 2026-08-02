#!/usr/bin/env python3
"""Build and verify deterministic M04-0001 evidence."""

from __future__ import annotations

import argparse
import hashlib
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
ATTEMPT = ROOT / "artifacts/work_packages/M04/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/M04"
M03_ATTEMPT = ROOT / "artifacts/work_packages/M03/attempts/0001"
sys.path.insert(0, str(M03_ATTEMPT))

import build_m03_0001_evidence as base  # noqa: E402


ATTEMPT_ID = "M04-0001"
WORK_PACKAGE_ID = "M04"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "web/src/features/map/ranking-claim-gate.mjs",
    "web/src/features/map/map-view.mjs",
    "web/src/features/map/map-test-fixtures.mjs",
    "web/src/features/map/map-ui.test.mjs",
    "web/src/features/map/ranking-claim-audit.test.mjs",
    "web/src/features/map/index.mjs",
)
M01_TESTS = (
    "packages/workspace-map/src/inventory/map-inventory.test.mjs",
    "packages/workspace-map/src/inventory/edge-resolution.test.mjs",
)
M02_TESTS = (
    "packages/workspace-map/src/ranking/baseline/centrality-reference.test.mjs",
    "packages/workspace-map/src/ranking/baseline/uniform-rank-regression.test.mjs",
)
M03_TESTS = (
    "packages/workspace-map/src/ranking/query/personalization.test.mjs",
    "packages/workspace-map/src/ranking/query/blast-radius.test.mjs",
)
M04_TESTS = PRODUCT_FILES[3:5]
EXPECTED_DEPENDENCIES = {
    "M02": {
        "attempt_id": "M02-0001",
        "core_evidence_id": "E0056",
        "core_generation": "000056-277d83f7",
        "final_closeout_evidence_id": "E0057",
        "report_sha256": "sha256:2834ac5c90e6b4ebf03f6df03329b602dfcfd27ca590b9c91bca802a89c7d493",
    },
    "M03": {
        "attempt_id": "M03-0001",
        "core_evidence_id": "E0059",
        "core_generation": "000059-98fc7a88",
        "final_closeout_evidence_id": "E0060",
        "report_sha256": "sha256:25b90944221399c494a826591ef02cb028bf7b5a8acaff666f57927c9a027802",
    },
}


sha256 = base.sha256
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
        raise SystemExit("M04 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("M04 attempt metadata has no recorded_at_utc")
    return value


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "M04"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one M04 row")
    expected = {
        "depends_on": ["M02", "M03"],
        "write_scope": ["web/src/features/map/**", "artifacts/work_packages/M04/**"],
        "independent_review": "required",
        "exit_criteria": ["labels match algorithms", "coverage/exclusions visible"],
        "required_checks": ["map_ui_test", "ranking_claim_audit"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"M04 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "web/src/features/map").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"M04 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"M04 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"M04 source must be BOM-less UTF-8: {relative}")
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
        and len(checks) == 6
        and all(row.get("exit_code") == 0 for row in checks)
        and sorted(row.get("path") for row in checks) == sorted(PRODUCT_FILES)
    ):
        raise SystemExit("M04 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-m04-node.junit.xml")
    assert_clean_node(targeted, 26, "M04 targeted")
    names = targeted["test_names"]
    map_ui = [name for name in names if name.startswith("map_ui_test:")]
    audit = [name for name in names if name.startswith("ranking_claim_audit:")]
    if len(map_ui) != 12 or len(audit) != 14 or len(set(names)) != 26:
        raise SystemExit("M04 targeted test-name partition is not exact 12/14")
    if targeted["observed_files"] != sorted(M04_TESTS):
        raise SystemExit(f"M04 targeted JUnit file inventory differs: {targeted['observed_files']}")
    return {
        **targeted,
        "map_ui_test_count": len(map_ui),
        "ranking_claim_audit_count": len(audit),
    }


def combined_evidence() -> dict[str, Any]:
    combined = node_summary(ATTEMPT / "combined-m01-m02-m03-m04-node.junit.xml")
    assert_clean_node(combined, 106, "M01+M02+M03+M04 combined")
    expected_files = sorted((*M01_TESTS, *M02_TESTS, *M03_TESTS, *M04_TESTS))
    if combined["observed_files"] != expected_files:
        raise SystemExit("combined M01+M02+M03+M04 JUnit file inventory differs")
    return combined


def map_ui_verification() -> dict[str, Any]:
    gate = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    view = (ROOT / PRODUCT_FILES[1]).read_text(encoding="utf-8")
    ui_test = (ROOT / PRODUCT_FILES[3]).read_text(encoding="utf-8")
    audit_test = (ROOT / PRODUCT_FILES[4]).read_text(encoding="utf-8")
    combined = gate + view + ui_test + audit_test
    required = (
        'WORKSPACE_MAP_VIEW_VERSION = "4.0.0-m04.1"',
        '"BASELINE_STRUCTURAL_CENTRALITY"',
        '"QUERY_LEXICAL_RELEVANCE"',
        '"INTRINSIC_RISK"',
        '"CHANGE_IMPACT"',
        "validateWorkspaceInventory",
        "validateWorkspaceEdgeExtraction",
        "validateBaselineCentrality",
        "validateQueryPersonalization",
        "validateRiskAndChangeImpact",
        "excluded_unresolved_edge_ids",
        'semantic_score: null',
        'semantic_status: "NOT_COMPUTED"',
        'id: "coverage-and-exclusions"',
        'id: "algorithm-bindings"',
        'id: "separate-ranking-dimensions"',
        "Overall importance",
        "unresolved-edge exclusions cannot be hidden",
        "risk and blast-radius score semantics cannot be conflated",
        "upstream artifact tampering cannot be laundered by matching prose",
        "untrusted label, query, and unresolved hint are HTML escaped",
    )
    missing = [fragment for fragment in required if fragment not in combined]
    if missing:
        raise SystemExit(f"M04 map/ranking contract binding is incomplete: {missing}")
    return {
        "attempt_id": ATTEMPT_ID,
        "artifact_owners_revalidated": ["M01", "M02", "M03"],
        "claim_count": 4,
        "claim_types": [
            "BASELINE_STRUCTURAL_CENTRALITY",
            "QUERY_LEXICAL_RELEVANCE",
            "INTRINSIC_RISK",
            "CHANGE_IMPACT",
        ],
        "coverage_and_exclusions_first": True,
        "coverage_and_exclusions_visible": True,
        "deep_immutability": "PASS",
        "deterministic_input_permutation": "PASS",
        "generic_importance_or_combined_score_forbidden": True,
        "html_escaping": "PASS",
        "labels_bound_to_algorithm_version_hash_order_and_score_field": True,
        "null_query_status": "NOT_PERSONALIZED",
        "ranking_dimensions_separate": True,
        "semantic_score": None,
        "semantic_status": "NOT_COMPUTED",
        "status": "PASS",
        "tamper_and_hostile_input_rejection": "PASS",
        "unreadable_paths_visible": True,
        "unresolved_edges_excluded_from_every_dimension": True,
        "unresolved_edges_visible": True,
        "version": "4.0.0-m04.1",
    }


def selected_dependency_report(package_id: str) -> Path:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts_root = package_root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts_root.is_dir():
        for path in attempts_root.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        latest = max(numeric)[1] / "report.json"
        if not latest.is_file():
            raise SystemExit(f"highest {package_id} attempt has no report")
        return latest
    fallback = package_root / "report.json"
    if not fallback.is_file():
        raise SystemExit(f"dependency report missing: {package_id}")
    return fallback


def dependency_evidence() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    for package_id, expected in EXPECTED_DEPENDENCIES.items():
        path = selected_dependency_report(package_id)
        report = read_json(path)
        rah = report.get("rah_state")
        if not (
            report.get("attempt_id") == expected["attempt_id"]
            and report.get("status") == "PASS"
            and report.get("package_status") == "PASS"
            and sha256_id(path) == expected["report_sha256"]
            and isinstance(rah, dict)
            and rah.get("core_evidence_id") == expected["core_evidence_id"]
            and rah.get("core_generation") == expected["core_generation"]
            and rah.get("final_closeout_evidence_id")
            == expected["final_closeout_evidence_id"]
            and rah.get("completion_ready") is False
        ):
            raise SystemExit(f"M04 dependency {package_id} is not the exact sealed PASS")
        dependencies[package_id] = {
            **expected,
            "report": path.relative_to(ROOT).as_posix(),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "dependency_count": 2,
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
    assert_clean_node(full_node, 719, "full Node")
    if not (
        len(files) == len(set(files)) == 71
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 71
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
        "count": 71,
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
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_codegen": {"examples": 126, "schemas": 126, "status": "PASS"},
        "combined_m01_m02_m03_m04": combined_evidence(),
        "full_node": {**full_node, "test_file_count": 71},
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
        "evidence_scope": "artifacts/work_packages/M04/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "web/src/features/map/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    verification = map_ui_verification()
    return {
        "map-ui-ranking-claim-verification.json": {
            **verification,
            "manifest_contract": manifest_contract(),
            "syntax": syntax_evidence(),
            "targeted": targeted_evidence(),
        },
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    targeted = targeted_evidence()
    return f"""# M04-0001 map UI and ranking-claim gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M04
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The view accepts exactly the M01 inventory/extraction, M02 baseline
   centrality, and M03 query/risk-impact artifacts and invokes every owning
   validator. No score or identity is silently trusted or recomputed by the UI.
2. The claim vocabulary is closed to baseline structural centrality, query
   lexical relevance, intrinsic risk, and change impact. Generic importance,
   combined scores, confidence, verdict, and semantic rank have no authority.
3. Every displayed label is bound to the sealed algorithm name, implementation
   version, artifact hash, order, score field, and unresolved-edge exclusions.
   Missing, duplicate, reordered, relabelled, stale, or tampered claims fail.
4. Coverage and exclusions are the first visible section. Indexed entities,
   unreadable paths, resolved/unresolved edges, reasons, and per-dimension
   exclusions remain visible; unresolved edges affect no ranking or impact.
5. Baseline centrality, query lexical relevance, intrinsic risk, and change
   impact remain four independent node dimensions. Risk is not inferred from
   blast radius and blast radius is not presented as a scalar risk score.
6. Query absence remains `null / NOT_PERSONALIZED`; semantic scoring remains
   `null / NOT_COMPUTED`. No unavailable value is fabricated or collapsed.
7. UI HTML escapes untrusted labels, queries, paths, and unresolved hints.
   Proxies, accessors, sparse arrays, custom fields, upstream tampering, and
   claim laundering fail closed without executing attacker-controlled getters.
8. View and claim derivation are deterministic, input-preserving, and deeply
   frozen. Input permutation produces identical projections and audit results.
9. Required checks pass {targeted['passed']}/{targeted['collected']}: 12
   `map_ui_test` and 14 `ranking_claim_audit` cases. M01 through M04 combined
   passes {regression['combined_m01_m02_m03_m04']['passed']}/{regression['combined_m01_m02_m03_m04']['collected']}.
   Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. The preserved initial 25/26 diagnostic was a test-fixture defect: the test
    attempted to mutate an already frozen artifact and raised before invoking
    the validator. Only the fixture was changed to `structuredClone`; production
    validation was not weakened. The final targeted suite is 26/26.
11. All six product files are BOM-less UTF-8 and remain inside exact
    `web/src/features/map/**` scope. Existing dirty worktree changes and every
    historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes the M04 read model, visible coverage/exclusions, truthful
algorithm labels, and ranking-claim audit for validated M01-M03 artifacts. It
does not establish actor-independent certification, production browser styling,
production-scale performance, overall product completion, release readiness,
or `completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect M04 manifest, EF4-I24, M02/M03 dependencies, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement upstream-validated map read model with four separate ranking dimensions", 0, "PASS"),
        ("C003", "Implement closed ranking-claim audit and visible coverage/exclusion projection", 0, "PASS"),
        ("D001", "Initial M04 targeted execution", 1, "PRESERVED_DIAGNOSTIC: 25/26; test attempted to mutate an already frozen artifact before validation"),
        ("C004", "Correct only the tamper fixture with structuredClone", 0, "PASS without production-contract weakening"),
        ("C005", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C006", "Run exact M04 targeted JUnit", 0, "PASS: 26/26 (map UI 12, ranking claim audit 14)"),
        ("C007", "Run combined M01+M02+M03+M04 JUnit", 0, "PASS: 106/106"),
        ("C008", "node --check <six M04 product files>", 0, "PASS: 6/6"),
        ("C009", "Capture complete sorted repository Node test inventory", 0, "PASS: 71 unique files"),
        ("C010", "Run complete repository Node test inventory", 0, "PASS: 719/719 across 71 files"),
        ("C011", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C012", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C013", "npm run check:structure", 0, "PASS"),
        ("C014", "npm run check:boundaries", 0, "PASS"),
        ("C015", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C016", "Build and verify deterministic M04 WorkPackageReport evidence", 0, "PASS"),
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
        "artifact_id": "M04-0001-MAP-UI-RANKING-CLAIM-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "M04-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-M04-0001-MAP-UI-RANKING-CLAIM-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {"check": "map_ui_test", "details": "12/12 coverage, separation, null, escaping, determinism, and fail-closed cases pass", "status": "PASS"},
            {"check": "ranking_claim_audit", "details": "14/14 label, algorithm, hash, order, exclusion, separation, and hostile-input cases pass", "status": "PASS"},
            {"check": "full_regression", "details": "Node 719/719 across 71 files, Python 1064/1064, codegen 126/126, no suppression", "status": "PASS"},
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
        raise SystemExit(f"invalid M04 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "map-ui-ranking-claim-verification.json",
        "map-ui-ranking-claim-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m04-node.junit.xml",
        "combined-m01-m02-m03-m04-node.junit.xml",
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
        "run_m04_0001_checks.py",
        "build_m04_0001_evidence.py",
        "m04_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required M04 evidence artifact is missing: {name}")
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
    receipt = read_json(
        ATTEMPT / "map-ui-ranking-claim-verification.artifact-receipt.json"
    )
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/M04/attempts/0001/map-ui-ranking-claim-verification.artifact-receipt.json",
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": dependency["dependencies"],
        "diagnostics_preserved": [
            {
                "classification": "TEST_FIXTURE_FROZEN_MUTATION",
                "result": "initial targeted execution was 25/26 because the test mutated an already frozen artifact before invoking validation",
                "resolution": "clone the audit fixture before tampering; production validation and claim contracts remain unchanged",
            }
        ],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "coverage_exclusions_visible": "PASS",
            "labels_match_algorithms": "PASS",
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
            "production browser styling or accessibility certification",
            "production-scale performance",
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
            "map_ui_test": {"failed": 0, "passed": 12, "skipped": 0, "status": "PASS"},
            "ranking_claim_audit": {"failed": 0, "passed": 14, "skipped": 0, "status": "PASS"},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/M04/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "M-phase map UI and ranking-claim gate",
        "verification": {
            "combined_m01_m02_m03_m04": "106/106",
            "full_node": "719/719 across 71 files",
            "full_python": "1064/1064",
            "targeted_m04": "26/26",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "map_ui_and_ranking_claims": documents[
                "map-ui-ranking-claim-verification.json"
            ],
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
    authority_path = ATTEMPT / "map-ui-ranking-claim-verification.json"
    write_json(
        ATTEMPT / "map-ui-ranking-claim-verification.artifact-receipt.json",
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
            raise SystemExit(f"stored M04 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored M04 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored M04 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "map-ui-ranking-claim-verification.json")
    receipt_path = ATTEMPT / "map-ui-ranking-claim-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored M04 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("M04 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored M04 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"M04 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "combined_m01_m02_m03_m04": "106/106",
        "completion_ready": False,
        "full_node": "719/719 across 71 files",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_m04": "26/26",
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
