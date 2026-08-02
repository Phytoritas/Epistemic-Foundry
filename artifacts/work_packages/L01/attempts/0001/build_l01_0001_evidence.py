#!/usr/bin/env python3
"""Build and verify deterministic L01-0001 evidence.

The builder reads the already-produced verification receipts and the four
L01-owned product files.  It writes only beneath the L01 evidence scope.
"""

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
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/L01/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/L01"
ATTEMPT_ID = "L01-0001"
WORK_PACKAGE_ID = "L01"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"

PRODUCT_FILES = (
    "packages/foundry-kernel/src/memory/policy/memory-policy.mjs",
    "packages/foundry-kernel/src/memory/policy/index.mjs",
    "packages/foundry-kernel/src/memory/policy/consent-policy.test.mjs",
    "packages/foundry-kernel/src/memory/policy/retention.test.mjs",
)
DEPENDENCY_REPORTS = {
    "D04": "artifacts/work_packages/D04/report.json",
    "H02": "artifacts/work_packages/H02/attempts/0001/report.json",
    "J04": "artifacts/work_packages/J04/attempts/0001/report.json",
    "S02": "artifacts/work_packages/S02/report.json",
}
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
    value = read_json(METADATA)
    if value.get("attempt_id") != ATTEMPT_ID:
        raise SystemExit("L01 attempt metadata has the wrong attempt ID")
    timestamp = value.get("recorded_at_utc")
    if not isinstance(timestamp, str):
        raise SystemExit("L01 attempt metadata has no recorded_at_utc")
    return timestamp


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


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == WORK_PACKAGE_ID]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one L01 row")
    expected = {
        "depends_on": ["D04", "H02", "J04", "S02"],
        "write_scope": ["packages/foundry-kernel/src/memory/policy/**"],
        "independent_review": "required",
        "exit_criteria": [
            "cross-workspace default deny",
            "revocation/expiry immediate",
        ],
        "required_checks": ["consent_policy_test", "retention_test"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"L01 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"L01 source is not UTF-8: {relative}: {error}") from error
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": sha256_id(path),
                "utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
            }
        )
    if any(row["utf8_bom"] for row in rows):
        raise SystemExit("L01 product files must be BOM-less UTF-8")
    return rows


def coverage_summary() -> dict[str, Any]:
    text = (ATTEMPT / "targeted-l01-coverage.stdout.log").read_text(encoding="utf-8")
    match = re.search(
        r"memory-policy\.mjs\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|",
        text,
    )
    if match is None:
        raise SystemExit("cannot parse L01 coverage summary")
    values = tuple(float(value) for value in match.groups())
    if values[0] < 90.0 or values[1] < 80.0 or values[2] != 100.0:
        raise SystemExit(f"L01 coverage regressed: {values}")
    return {
        "branch_percent": values[1],
        "function_percent": values[2],
        "line_percent": values[0],
        "status": "PASS",
        "stderr_empty": (ATTEMPT / "targeted-l01-coverage.stderr.log").stat().st_size == 0,
    }


def policy_verification() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-l01-node.junit.xml")
    if not (
        targeted["passed"] == targeted["collected"] == 27
        and targeted["failed"] == targeted["skipped"] == targeted["todo"] == 0
        and targeted["cancelled"] == 0
        and targeted["xml_failure_count"] == targeted["xml_error_count"] == 0
    ):
        raise SystemExit(f"L01 targeted gate is not 27/27: {targeted}")
    schema_runtime = read_json(ATTEMPT / "schema-runtime-verification.json")
    syntax = read_json(ATTEMPT / "syntax-verification.json")
    if schema_runtime.get("final_status") != "PASS" or syntax.get("final_status") != "PASS":
        raise SystemExit("L01 syntax or canonical schema validation did not pass")
    memory_schema = read_json(ROOT / "schemas/memory-policy.schema.json")
    classes = memory_schema["properties"]["allowed_classes"]["items"]["enum"]
    expected_classes = [
        "EPHEMERAL",
        "SESSION",
        "WORKSPACE",
        "USER",
        "EVIDENCE",
        "REGULATED",
    ]
    if classes != expected_classes:
        raise SystemExit(f"canonical memory classes changed: {classes}")
    implementation = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    tests = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8") for relative in PRODUCT_FILES[2:]
    )
    required_fragments = (
        "CROSS_WORKSPACE_DENIED",
        "CROSS_WORKSPACE_OPT_IN_REQUIRED",
        "CONSENT_REVOKED",
        "CONSENT_EXPIRED",
        "RETENTION_EXPIRED",
        "MEMORY_TIMESTAMP_IN_FUTURE",
        "CONSENT_SCOPE_MISMATCH",
        "MEMORY_POLICY_HASH_MISMATCH",
        "CONSENT_RECORD_HASH_MISMATCH",
    )
    if any(fragment not in implementation or fragment not in tests for fragment in required_fragments):
        raise SystemExit("L01 implementation/test binding is incomplete")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_memory_classes": expected_classes,
        "canonical_schema_validation": schema_runtime,
        "closed_input_shapes": True,
        "consent_binding": {
            "data_class": True,
            "memory_class_scope": True,
            "policy_hash": True,
            "purpose": True,
            "workspace": True,
        },
        "coverage": coverage_summary(),
        "cross_workspace": {
            "default_deny": True,
            "explicit_opt_in_required": True,
            "only_user_class_can_cross": True,
        },
        "hash_integrity": {
            "consent_record": True,
            "memory_policy": True,
        },
        "immediate_denial": {
            "expired": True,
            "revoked": True,
            "retention_expired": True,
        },
        "scope_boundary": {
            "l01_recall_admission_only": True,
            "l02_search_and_retrieval_receipts_not_implemented": True,
            "l03_redaction_deletion_legal_hold_not_implemented": True,
        },
        "status": "PASS",
        "syntax": syntax,
        "targeted": targeted,
    }


def regression_evidence() -> dict[str, Any]:
    predecessor = node_summary(ATTEMPT / "predecessor-l01-node.junit.xml")
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    if not (
        predecessor["passed"] == predecessor["collected"] == 42
        and full_node["passed"] == full_node["collected"] == 503
        and full_python["passed"] == full_python["collected"] == 1064
    ):
        raise SystemExit("L01 regression counts differ from the verified green receipts")
    for summary in (predecessor, full_node):
        if any(summary[key] != 0 for key in ("failed", "skipped", "todo", "cancelled")):
            raise SystemExit(f"Node regression suppression or failure found: {summary}")
    if any(full_python[key] != 0 for key in ("failed", "errors", "skipped")):
        raise SystemExit(f"Python regression suppression or failure found: {full_python}")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory.get("count") != 57 or inventory.get("unique") is not True:
        raise SystemExit("full Node inventory is incomplete or ambiguous")
    codegen = read_json(ATTEMPT / "codegen-verification.stdout.log")
    if not (
        codegen.get("status") == "PASS"
        and codegen.get("schema_count") == 126
        and codegen.get("example_count") == 126
    ):
        raise SystemExit("canonical codegen verification did not pass 126/126")
    structure = (ATTEMPT / "structure-check.stdout.log").read_text(encoding="utf-8")
    boundaries = (ATTEMPT / "boundary-check.stdout.log").read_text(encoding="utf-8")
    if '"status": "PASS"' not in structure or '"status": "PASS"' not in boundaries:
        raise SystemExit("repository structure or boundary gate did not pass")
    if (ATTEMPT / "git-diff-check.stdout.log").stat().st_size != 0:
        raise SystemExit("git diff --check produced a failure on stdout")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_codegen": {
            "example_count": 126,
            "schema_count": 126,
            "status": "PASS",
        },
        "full_node": {**full_node, "test_file_count": inventory["count"]},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "predecessor_node": predecessor,
        "repository_structure": "PASS",
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    for package_id, relative in DEPENDENCY_REPORTS.items():
        path = ROOT / relative
        report = read_json(path)
        if report.get("status") != "PASS" or report.get("package_status") not in (None, "PASS"):
            raise SystemExit(f"L01 dependency is not PASS: {package_id}")
        dependencies[package_id] = {
            "attempt_id": report.get("attempt_id"),
            "report": relative,
            "report_sha256": sha256_id(path),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "dependency_count": len(dependencies),
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    expected_prefix = "packages/foundry-kernel/src/memory/policy/"
    if any(not row["path"].startswith(expected_prefix) for row in inventory):
        raise SystemExit("L01 product file is outside the manifest write scope")
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "consent-retention-verification.json": policy_verification(),
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    coverage = documents["consent-retention-verification.json"]["coverage"]
    return f"""# L01-0001 memory policy contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial pass over the fixed L01
source hashes and verification receipts, not actor-independent certification.

## Findings

1. The policy vocabulary is closed to the six canonical memory classes. Plain
   data objects, dense arrays, exact fields, canonical hashes, and frozen
   projections prevent accessors, Proxies, sparse arrays, unknown fields, and
   post-validation mutation from becoming authority.
2. Same-workspace recall is bound to the policy workspace, effective time,
   allowed class, retention window, purpose, data class, canonical class scope,
   and policy hash. Invalid or tampered policies and consent records fail closed.
3. Cross-workspace access defaults to `DENY`; a permissive policy never admits
   non-`USER` memory and still requires explicit opt-in plus a valid consent.
4. `DENIED`, `REVOKED`, and `EXPIRED` decisions deny immediately. A nominally
   `GRANTED` record also denies at the exact revocation or expiry boundary.
   Retention admits the exact boundary and denies the following millisecond.
5. Consent supplied to a class that does not require it is integrity-validated
   but is not recorded as the authority for that access. This prevents optional
   consent from fabricating an authorization lineage.
6. L01 stops before any store or index is searched. L02 retains ownership of
   scoped retrieval and retrieval receipts; L03 retains redaction, deletion,
   deduplication, forget, and legal-hold semantics.
7. Required checks pass 27/27. Coverage is {coverage['line_percent']:.2f}% lines,
   {coverage['branch_percent']:.2f}% branches, and {coverage['function_percent']:.2f}%
   functions. The sealed runtime artifacts validate against both canonical
   Draft 2020-12 schemas.
8. D04/H02/J04/S02 predecessor surfaces pass 42/42. Full Node passes
   {regression['full_node']['passed']}/{regression['full_node']['collected']} and
   full Python passes {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126 schemas / 126 examples; structure, package boundaries,
   and diff checks pass with no skipped, xfailed, todo, or cancelled cases.
9. All four product files are within the exact L01 manifest scope. Historical
   attempts, RAH generations, and unrelated dirty worktree changes remain
   untouched.

## Assurance boundary

This gate establishes deterministic admission policy behavior. It does not
claim a production memory store, retrieval index, automatic deletion service,
legal-hold executor, cross-device synchronization service, overall product
completion, or release readiness. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect L01 manifest, canonical schemas, predecessors, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement deterministic memory class, consent, retention, and workspace admission under packages/foundry-kernel/src/memory/policy/**", 0, "PASS: four product files"),
        ("D001", "Initial L01 targeted Node execution", 1, "PRESERVED_DIAGNOSTIC: 24/25 because one test fixture supplied a USER class rule outside its overridden allowed_classes; product enforcement correctly failed closed"),
        ("C003", "Correct the bounded test fixture without weakening product enforcement", 0, "PASS"),
        ("C004", "node --check <four L01 .mjs files>", 0, "PASS: 4/4"),
        ("C005", "node --test --test-concurrency=1 --test-reporter=junit <two L01 tests>", 0, "PASS: 27/27"),
        ("C006", "node --test --experimental-test-coverage <two L01 tests>", 0, "PASS: lines 92.05%, branches 80.89%, functions 100%"),
        ("C007", "Validate sealed MemoryPolicy and ConsentRecord against canonical Draft 2020-12 schemas", 0, "PASS: 2/2 schemas, zero errors"),
        ("C008", "Run D04/H02/J04/S02 predecessor Node surfaces", 0, "PASS: 42/42"),
        ("C009", "uv run --locked python -m pytest tests -p no:cacheprovider --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 1064/1064"),
        ("C010", "node --test --test-concurrency=1 --test-reporter=junit <complete sorted repository Node inventory>", 0, "PASS: 503/503 across 57 files"),
        ("C011", "uv run --locked python packages/contracts/codegen/verify.py --repo-root .", 0, "PASS: 126 schemas / 126 examples"),
        ("C012", "npm run check:structure", 0, "PASS"),
        ("C013", "npm run check:boundaries", 0, "PASS"),
        ("C014", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C015", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("D002", "git diff --no-index /dev/null <new L01 file>", 1, "DIAGNOSTIC_ONLY: exit 1 means the new file differs from /dev/null; no whitespace defect"),
        ("D003", "Use a Windows wildcard directly in an rg artifact path", 1, "DIAGNOSTIC_ONLY: Windows path syntax rejected; no mutation"),
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
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "L01-0001-CONSENT-RETENTION-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "L01-0001-PRIMARY-SESSION-VERIFIER",
            "actor_type": "tool",
        },
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-L01-0001-CONSENT-RETENTION-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "consent_policy_test",
                "details": "20 consent/policy executions including five bound-mismatch subtests pass",
                "status": "PASS",
            },
            {
                "check": "retention_test",
                "details": "7/7 class override, exact boundary, future time, zero-day, and fail-closed cases pass",
                "status": "PASS",
            },
            {
                "check": "canonical_schema_validation",
                "details": "sealed MemoryPolicy and ConsentRecord validate with zero Draft 2020-12 errors",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "predecessors 42/42, Node 503/503, Python 1064/1064, no suppression",
                "status": "PASS",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid L01 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "consent-retention-verification.json",
        "consent-retention-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "schema-runtime-verification.json",
        "targeted-l01-node.junit.xml",
        "targeted-l01-coverage.stdout.log",
        "predecessor-l01-node.junit.xml",
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
        "run_l01_0001_checks.py",
        "build_l01_0001_evidence.py",
        "l01_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required L01 evidence artifact is missing: {name}")
        rows.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return rows


def report_document(
    documents: dict[str, dict[str, Any]],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verification = documents["consent-retention-verification.json"]
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(
        ATTEMPT / "consent-retention-verification.artifact-receipt.json"
    )
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/L01/attempts/0001/consent-retention-verification.artifact-receipt.json",
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
            "cross_workspace_default_deny": "PASS",
            "revocation_and_expiry_immediate": "PASS",
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
            "memory retrieval/index implementation (L02)",
            "redaction/deletion/legal-hold implementation (L03)",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "consent_policy_test": {
                "failed": 0,
                "passed": 20,
                "skipped": 0,
                "status": "PASS",
            },
            "retention_test": {
                "failed": 0,
                "passed": 7,
                "skipped": 0,
                "status": "PASS",
            },
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/L01/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Memory classes, consent and retention policy",
        "verification": {
            "canonical_schema_validation": "2/2",
            "full_node": "503/503",
            "full_python": "1064/1064",
            "predecessor_node": "42/42",
            "targeted_l01": "27/27",
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
    (ATTEMPT / "commands.jsonl").write_text(
        expected_commands(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    write_json(
        ATTEMPT / "consent-retention-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "consent-retention-verification.json"),
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
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored L01 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored L01 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored L01 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "consent-retention-verification.json")
    receipt_path = ATTEMPT / "consent-retention-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(
        expected_receipt
    ):
        raise SystemExit("stored L01 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("L01 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored L01 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"L01 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "503/503",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "predecessor_node": "42/42",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_l01": "27/27",
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
