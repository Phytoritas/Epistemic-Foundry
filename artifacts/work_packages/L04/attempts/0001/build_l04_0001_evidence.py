#!/usr/bin/env python3
"""Build and verify deterministic L04-0001 recall gate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/L04/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/L04"
ATTEMPT_ID = "L04-0001"
WORK_PACKAGE_ID = "L04"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "tests/evals/recall/recall-eval-support.mjs",
    "tests/evals/recall/recall-precision.test.mjs",
    "tests/evals/recall/cross-workspace-leak.test.mjs",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(value), encoding="utf-8", newline="\n")


def recorded_at() -> str:
    metadata = read_json(METADATA)
    if metadata.get("attempt_id") != ATTEMPT_ID:
        raise SystemExit("L04 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("L04 attempt metadata has no recorded_at_utc")
    return value


RECORDED_AT = recorded_at()


def node_summary(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    footer = {
        match.group(1).decode("ascii"): int(match.group(2))
        for match in NODE_FOOTER_PATTERN.finditer(raw)
    }
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(footer) != required:
        raise SystemExit(f"Node JUnit footer is incomplete: {path.name}: {footer}")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise SystemExit(f"cannot parse Node JUnit {path}: {error}") from error
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_error_count": len(list(root.iter("error"))),
        "xml_failure_count": len(list(root.iter("failure"))),
        "xml_testcase_count": len(list(root.iter("testcase"))),
    }


def pytest_summary(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise SystemExit(f"cannot parse pytest JUnit {path}: {error}") from error
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise SystemExit(f"pytest JUnit has no top-level suite: {path}")
    tests = sum(int(float(suite.attrib.get("tests", "0"))) for suite in suites)
    failures = sum(int(float(suite.attrib.get("failures", "0"))) for suite in suites)
    errors = sum(int(float(suite.attrib.get("errors", "0"))) for suite in suites)
    skipped = sum(int(float(suite.attrib.get("skipped", "0"))) for suite in suites)
    testcase_count = len(list(root.iter("testcase")))
    if testcase_count != tests:
        raise SystemExit(f"pytest testcase count mismatch: {testcase_count} != {tests}")
    return {
        "collected": tests,
        "errors": errors,
        "failed": failures,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": tests - failures - errors - skipped,
        "skipped": skipped,
        "xml_testcase_count": testcase_count,
    }


def node_test_names(path: Path) -> list[str]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise SystemExit(f"cannot parse Node JUnit {path}: {error}") from error
    return [str(node.attrib.get("name", "")) for node in root.iter("testcase")]


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "L04"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one L04 row")
    expected = {
        "depends_on": ["L02", "L03"],
        "write_scope": ["tests/evals/recall/**", "artifacts/work_packages/L04/**"],
        "independent_review": "required",
        "exit_criteria": [
            "needed prior facts recovered",
            "unrelated private context not returned",
        ],
        "required_checks": ["recall_precision_test", "cross_workspace_leak_test"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"L04 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"L04 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"L04 source must be BOM-less UTF-8: {relative}")
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": sha256_id(path),
                "utf8_bom": False,
            }
        )
    return rows


def assert_clean_node(summary: dict[str, Any], expected: int, label: str) -> None:
    if not (
        summary["passed"] == summary["collected"] == expected
        and all(summary[key] == 0 for key in ("failed", "skipped", "todo", "cancelled"))
        and summary["xml_failure_count"] == summary["xml_error_count"] == 0
    ):
        raise SystemExit(f"{label} gate is not {expected}/{expected}: {summary}")


def recall_verification() -> dict[str, Any]:
    path = ATTEMPT / "targeted-l04-node.junit.xml"
    targeted = node_summary(path)
    assert_clean_node(targeted, 25, "L04 targeted")
    names = node_test_names(path)
    precision_names = [name for name in names if name.startswith("recall_precision_test:")]
    privacy_names = [name for name in names if name.startswith("cross_workspace_leak_test:")]
    if len(precision_names) != 10 or len(privacy_names) != 15:
        raise SystemExit("L04 required-check test-name partition is not 10/15")
    if len(names) != len(set(names)):
        raise SystemExit("L04 targeted test names are not unique")

    support = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    precision = (ROOT / PRODUCT_FILES[1]).read_text(encoding="utf-8")
    privacy = (ROOT / PRODUCT_FILES[2]).read_text(encoding="utf-8")
    required_support = (
        "buildMemoryIndex",
        "executeMemorySearch",
        "redactAndDeduplicateMemory",
        "emitMemoryRetrievalReceipt",
        "validateMemoryRetrievalReceipt",
        "sealMemoryPolicy",
        "sealConsentRecord",
    )
    required_precision = (
        "MEM-L04-NEEDED",
        "MEM-L04-FACT-A",
        "MEM-L04-FACT-B",
        "DUPLICATE_SOURCE_HASH",
        "SEARCHED_NONE",
        "selection_hash",
        "receipt_id",
        "result_hash",
    )
    required_privacy = (
        "MEMORY_SCOPE_DENIED",
        "MEMORY_POLICY_INVALID",
        "crossWorkspaceOptIn: true",
        "consentRecord: null",
        "decision: \"REVOKED\"",
        "MEM-L04-THIRD-FORBIDDEN",
        "prompt injection text in another workspace has no authority",
    )
    for text, fragments, label in (
        (support, required_support, "support"),
        (precision, required_precision, "precision"),
        (privacy, required_privacy, "privacy"),
    ):
        missing = [fragment for fragment in fragments if fragment not in text]
        if missing:
            raise SystemExit(f"L04 {label} contract binding is incomplete: {missing}")

    syntax = read_json(ATTEMPT / "syntax-verification.json")
    if not (
        syntax.get("final_status") == "PASS"
        and len(syntax.get("checks", [])) == 3
        and all(row.get("exit_code") == 0 for row in syntax["checks"])
    ):
        raise SystemExit("L04 syntax verification did not pass")

    return {
        "attempt_id": ATTEMPT_ID,
        "exact_oracle": {
            "expected_memory_id_set_exact_match": True,
            "forbidden_private_or_cross_workspace_id_count": 0,
            "pipeline": ["L01_POLICY", "L02_SCOPED_SEARCH", "L03_REDACTION_DEDUPE", "CANONICAL_RECEIPT"],
            "receipt_hash_and_replay_identity": True,
        },
        "precision": {
            "bounded_top_k_excludes_unrelated_context": True,
            "duplicate_source_amplification": False,
            "expired_memory_excluded_before_ranking": True,
            "needed_fact_exact_id_set_recovered": True,
            "raw_search_text_in_receipt": False,
            "redaction_preserves_identity_without_private_bytes": True,
            "searched_none_distinct_from_unsearched": True,
            "unicode_nfkc_equivalence": True,
        },
        "privacy": {
            "cross_workspace_workspace_store_allowed": False,
            "default_cross_workspace_access": "DENY",
            "explicit_user_opt_in_requires_policy_and_consent": True,
            "forbidden_id_leak_count": 0,
            "malformed_policy_fails_closed": True,
            "prompt_injection_authority": False,
            "raw_forbidden_source_text_returned": False,
            "searched_excluded_class_partition_complete": True,
            "target_workspace_binding_exact": True,
        },
        "status": "PASS",
        "syntax": syntax,
        "targeted": {
            **targeted,
            "cross_workspace_leak_test_count": len(privacy_names),
            "recall_precision_test_count": len(precision_names),
            "test_names": names,
        },
    }


def regression_evidence() -> dict[str, Any]:
    l01 = node_summary(ATTEMPT / "predecessor-l01-node.junit.xml")
    l02 = node_summary(ATTEMPT / "predecessor-l02-node.junit.xml")
    l03 = node_summary(ATTEMPT / "predecessor-l03-node.junit.xml")
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    for summary, count, label in ((l01, 27, "L01"), (l02, 41, "L02"), (l03, 44, "L03"), (full_node, 613, "full Node")):
        assert_clean_node(summary, count, label)
    if not (
        full_python["passed"] == full_python["collected"] == 1064
        and all(full_python[key] == 0 for key in ("failed", "errors", "skipped"))
    ):
        raise SystemExit(f"full Python gate differs: {full_python}")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory.get("count") != 63 or inventory.get("unique") is not True:
        raise SystemExit("full Node inventory is incomplete or ambiguous")
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
        "canonical_codegen": {"example_count": 126, "schema_count": 126, "status": "PASS"},
        "full_node": {**full_node, "test_file_count": inventory["count"]},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "predecessor_l01_node": l01,
        "predecessor_l02_node": l02,
        "predecessor_l03_node": l03,
        "repository_structure": "PASS",
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    expected = {
        "L02": ("L02-0001", "E0045"),
        "L03": ("L03-0001", "E0048"),
    }
    for package_id, (attempt_id, final_id) in expected.items():
        relative = f"artifacts/work_packages/{package_id}/attempts/0001/report.json"
        path = ROOT / relative
        report = read_json(path)
        rah = report.get("rah_state")
        if not (
            report.get("attempt_id") == attempt_id
            and report.get("status") == "PASS"
            and report.get("package_status") == "PASS"
            and isinstance(rah, dict)
            and rah.get("final_closeout_evidence_id") == final_id
        ):
            raise SystemExit(f"L04 dependency {package_id} is not sealed PASS")
        dependencies[package_id] = {
            "attempt_id": attempt_id,
            "final_closeout_evidence_id": final_id,
            "report": relative,
            "report_sha256": sha256_id(path),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "dependency_count": 2,
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    if any(not row["path"].startswith("tests/evals/recall/") for row in inventory):
        raise SystemExit("L04 product file is outside manifest write scope")
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/L04/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "tests/evals/recall/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "recall-quality-privacy-verification.json": recall_verification(),
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    verification = documents["recall-quality-privacy-verification.json"]
    regression = documents["full-regression-impact.json"]
    targeted = verification["targeted"]
    return f"""# L04-0001 recall quality and privacy review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed L04
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The evaluation traverses the actual L01 policy, L02 scoped-search and receipt,
   and L03 redaction/deduplication authorities. It does not replace the product
   path with a scoring-only fixture implementation.
2. Precision is an exact fixture oracle: required memory-ID sets must match,
   distractors cannot enter bounded top-k, expired records are excluded before
   ranking, exact-source duplicates do not amplify, and `SEARCHED_NONE` remains
   distinct from an unsearched class.
3. Receipt identity is bound to the post-L03 selected subset. Input permutation
   preserves selection hash, receipt ID, and result hash; selected records retain
   provenance without returning raw search/source text.
4. Privacy is fail-closed. Cross-workspace access is denied by default; the only
   permitted case is an exact USER target with policy permission, explicit opt-in,
   active matching consent, and target-workspace binding. WORKSPACE cross-access,
   missing/revoked consent, malformed policy, other classes, and other workspaces
   are rejected.
5. Prompt-injection-shaped memory text remains untrusted data and acquires no
   authority. Private/cross-workspace forbidden IDs and raw forbidden bytes have
   zero occurrences in selected output and canonical receipts.
6. Required checks pass {targeted['passed']}/{targeted['collected']}: 10
   `recall_precision_test` and 15 `cross_workspace_leak_test` cases, with no
   skipped, todo, cancelled, xfailed, or suppressed case.
7. L01 passes {regression['predecessor_l01_node']['passed']}/27, L02 passes
   {regression['predecessor_l02_node']['passed']}/41, and L03 passes
   {regression['predecessor_l03_node']['passed']}/44. Full Node passes
   {regression['full_node']['passed']}/{regression['full_node']['collected']} across
   {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126 schemas / 126 examples; repository structure, package
   boundaries, and diff checks pass.
8. All three product/evaluation files are BOM-less UTF-8 and remain inside the
   exact `tests/evals/recall/**` scope. Existing dirty-worktree changes, historical
   reports, and RAH generations remain untouched.

## Assurance boundary

This gate establishes deterministic local fixture quality and privacy for the
current L01-L03 memory path. It does not claim production corpus recall metrics,
production persistence/vector infrastructure, actor-independent review, overall
product completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect L04 manifest, dependencies, current recall authorities, dirty worktree, and RAH state", 0, "PASS"),
        ("D001", "Initial L04 targeted execution", 1, "PRESERVED_DIAGNOSTIC: 24/25; malformed-policy test expected only MemoryIndexError while the canonical policy validator directly raised MemoryPolicyError"),
        ("C002", "Accept the canonical MemoryPolicyError boundary in the malformed-policy oracle", 0, "PASS"),
        ("D002", "Second L04 targeted execution", 1, "PRESERVED_DIAGNOSTIC: 24/25; assertion used INVALID_MEMORY_POLICY while the canonical code is MEMORY_POLICY_INVALID"),
        ("C003", "Correct the malformed-policy assertion to exact MemoryPolicyError/MEMORY_POLICY_INVALID", 0, "PASS"),
        ("C004", "node --test --test-concurrency=1 <two L04 tests>", 0, "PASS: 25/25 (precision 10, privacy 15)"),
        ("C005", "Run L01 predecessor memory-policy surfaces", 0, "PASS: 27/27"),
        ("C006", "Run L02 predecessor memory-index/retrieval surfaces", 0, "PASS: 41/41"),
        ("C007", "Run L03 predecessor memory-lifecycle surfaces", 0, "PASS: 44/44"),
        ("C008", "Capture attempt-local syntax verification", 0, "PASS: 3/3"),
        ("C009", "Capture complete sorted repository Node inventory and suite", 0, "PASS: 613/613 across 63 files"),
        ("C010", "Capture full Python suite", 0, "PASS: 1064/1064"),
        ("C011", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C012", "npm run check:structure", 0, "PASS"),
        ("C013", "npm run check:boundaries", 0, "PASS"),
        ("C014", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C015", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C016", "Build and verify deterministic L04 WorkPackageReport evidence", 0, "PASS"),
    ]
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def expected_commands() -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in command_records())


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "L04-0001-RECALL-QUALITY-PRIVACY-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": RECORDED_AT,
        "created_by": {"actor_id": "L04-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-L04-0001-RECALL-QUALITY-PRIVACY-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {"check": "recall_precision_test", "details": "10/10 exact needed-fact, bounded top-k, dedupe, redaction, replay, and receipt cases pass", "status": "PASS"},
            {"check": "cross_workspace_leak_test", "details": "15/15 default-deny, consent, class/workspace isolation, injection, raw-text, and fail-closed cases pass", "status": "PASS"},
            {"check": "memory_pipeline_regression", "details": "L01 27/27, L02 41/41, L03 44/44", "status": "PASS"},
            {"check": "full_regression", "details": "Node 613/613, Python 1064/1064, codegen 126/126, no suppression", "status": "PASS"},
        ],
    }
    receipt["receipt_hash"] = canonical_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid L04 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "recall-quality-privacy-verification.json",
        "recall-quality-privacy-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-l04-node.junit.xml",
        "predecessor-l01-node.junit.xml",
        "predecessor-l02-node.junit.xml",
        "predecessor-l03-node.junit.xml",
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
        "run_l04_0001_checks.py",
        "build_l04_0001_evidence.py",
        "l04_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required L04 evidence artifact is missing: {name}")
        rows.append({"byte_size": path.stat().st_size, "path": path.relative_to(ROOT).as_posix(), "sha256": sha256_id(path)})
    return rows


def report_document(documents: dict[str, dict[str, Any]], *, rah_state: dict[str, Any] | None = None) -> dict[str, Any]:
    verification = documents["recall-quality-privacy-verification.json"]
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(ATTEMPT / "recall-quality-privacy-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/L04/attempts/0001/recall-quality-privacy-verification.artifact-receipt.json",
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
                "classification": "TEST_ORACLE_TYPE_BOUNDARY",
                "result": "initial targeted execution 24/25 because the malformed-policy oracle accepted only MemoryIndexError",
                "resolution": "recognized the direct canonical MemoryPolicyError boundary without changing production code",
            },
            {
                "classification": "TEST_ORACLE_CODE_MISMATCH",
                "result": "second targeted execution 24/25 because the assertion used INVALID_MEMORY_POLICY",
                "resolution": "bound the assertion to canonical MEMORY_POLICY_INVALID; final targeted execution is 25/25",
            },
        ],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "needed_prior_facts_recovered": "PASS",
            "unrelated_private_context_not_returned": "PASS",
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
            "production corpus recall performance",
            "production persistence or vector backend",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "cross_workspace_leak_test": {"failed": 0, "passed": 15, "skipped": 0, "status": "PASS"},
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "recall_precision_test": {"failed": 0, "passed": 10, "skipped": 0, "status": "PASS"},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/L04/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "L-phase recall quality/privacy gate",
        "verification": {
            "full_node": "613/613",
            "full_python": "1064/1064",
            "predecessor_l01_node": "27/27",
            "predecessor_l02_node": "41/41",
            "predecessor_l03_node": "44/44",
            "targeted_l04": "25/25",
            "write_scope_violation_count": 0,
        },
        "verification_details": verification,
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    manifest_contract()
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(expected_commands(), encoding="utf-8", newline="\n")
    (ATTEMPT / "review.md").write_text(review_text(documents), encoding="utf-8", newline="\n")
    write_json(
        ATTEMPT / "recall-quality-privacy-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "recall-quality-privacy-verification.json"),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(*, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str) -> dict[str, Any]:
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
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored L04 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored L04 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored L04 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "recall-quality-privacy-verification.json")
    receipt_path = ATTEMPT / "recall-quality-privacy-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored L04 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("L04 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored L04 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"L04 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "613/613",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_l04": "25/25",
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
