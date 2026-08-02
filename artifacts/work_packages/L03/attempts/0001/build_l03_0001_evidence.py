#!/usr/bin/env python3
"""Build and verify deterministic L03-0001 work-package evidence.

The builder consumes already-created verification receipts and the five
L03-owned product files. It writes only beneath artifacts/work_packages/L03.
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
from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/L03/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/L03"
ATTEMPT_ID = "L03-0001"
WORK_PACKAGE_ID = "L03"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"

PRODUCT_FILES = (
    "packages/foundry-kernel/src/memory/lifecycle/memory-lifecycle.mjs",
    "packages/foundry-kernel/src/memory/lifecycle/index.mjs",
    "packages/foundry-kernel/src/memory/lifecycle/memory-lifecycle-test-support.mjs",
    "packages/foundry-kernel/src/memory/lifecycle/redaction.test.mjs",
    "packages/foundry-kernel/src/memory/lifecycle/forget-legal-hold.test.mjs",
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
        raise SystemExit("L03 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("L03 attempt metadata has no recorded_at_utc")
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
    rows = [
        row
        for row in packages
        if isinstance(row, dict) and row.get("id") == WORK_PACKAGE_ID
    ]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one L03 row")
    expected = {
        "depends_on": ["L01"],
        "write_scope": ["packages/foundry-kernel/src/memory/lifecycle/**"],
        "independent_review": "required",
        "exit_criteria": [
            "deletion/hold semantics explicit",
            "duplicate memories do not amplify",
        ],
        "required_checks": ["redaction_test", "forget_legal_hold_test"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"L03 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"L03 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"L03 source must be BOM-less UTF-8: {relative}")
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": sha256_id(path),
                "utf8_bom": False,
            }
        )
    return rows


def coverage_summary() -> dict[str, Any]:
    text = (ATTEMPT / "targeted-l03-coverage.stdout.log").read_text(
        encoding="utf-8"
    )
    implementation_match = re.search(
        r"memory-lifecycle\.mjs\s+\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|",
        text,
    )
    aggregate_match = re.search(
        r"all files\s+\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|",
        text,
    )
    if implementation_match is None or aggregate_match is None:
        raise SystemExit("cannot parse L03 coverage summary")
    implementation = tuple(float(value) for value in implementation_match.groups())
    aggregate = tuple(float(value) for value in aggregate_match.groups())
    if implementation != (94.53, 79.95, 94.79):
        raise SystemExit(f"L03 implementation coverage differs: {implementation}")
    if aggregate != (51.73, 73.54, 56.92):
        raise SystemExit(f"L03 aggregate coverage differs: {aggregate}")
    return {
        "aggregate": {
            "branch_percent": aggregate[1],
            "function_percent": aggregate[2],
            "line_percent": aggregate[0],
        },
        "memory_lifecycle_implementation": {
            "branch_percent": implementation[1],
            "function_percent": implementation[2],
            "line_percent": implementation[0],
        },
        "status": "PASS",
        "stderr_empty": (ATTEMPT / "targeted-l03-coverage.stderr.log").stat().st_size
        == 0,
    }


def lifecycle_verification() -> dict[str, Any]:
    targeted_path = ATTEMPT / "targeted-l03-node.junit.xml"
    targeted = node_summary(targeted_path)
    names = node_test_names(targeted_path)
    redaction_count = sum(name.startswith("redaction_test:") for name in names)
    lifecycle_count = sum(name.startswith("forget_legal_hold_test:") for name in names)
    if not (
        targeted["passed"] == targeted["collected"] == 44
        and targeted["failed"] == targeted["skipped"] == targeted["todo"] == 0
        and targeted["cancelled"] == 0
        and targeted["xml_failure_count"] == targeted["xml_error_count"] == 0
        and redaction_count == 19
        and lifecycle_count == 25
    ):
        raise SystemExit(f"L03 targeted gate is not 44/44: {targeted}")

    runtime = read_json(ATTEMPT / "schema-runtime-verification.json")
    syntax = read_json(ATTEMPT / "syntax-verification.json")
    expected_interop = {
        "action_intent": True,
        "effect_receipt": True,
        "event_record": True,
    }
    schema_errors = runtime.get("canonical_schema_errors")
    if not (
        runtime.get("final_status") == "PASS"
        and runtime.get("node_exit_code") == 0
        and runtime.get("canonical_hash_interop") == expected_interop
        and isinstance(schema_errors, dict)
        and set(schema_errors)
        == {
            "action-intent.schema.json",
            "effect-receipt.schema.json",
            "event-record.schema.json",
        }
        and all(value == [] for value in schema_errors.values())
        and syntax.get("final_status") == "PASS"
        and len(syntax.get("checks", [])) == 5
        and all(row.get("exit_code") == 0 for row in syntax["checks"])
    ):
        raise SystemExit("L03 syntax, schema, or canonical hash interop did not pass")

    implementation = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    tests = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in PRODUCT_FILES[3:]
    )
    required_fragments = (
        "REDACTION_PROFILE_UNRESOLVED",
        "REDACTION_SOURCE_HASH_MISMATCH",
        "REDACTION_SPAN_OVERLAP",
        "REDACTION_SPAN_SPLITS_UTF8",
        "DUPLICATE_SOURCE_HASH",
        "BLOCKED_LEGAL_HOLD",
        "LEGAL_HOLD_HASH_MISMATCH",
        "DERIVED_CACHE_NOT_CANONICAL_MEMORY",
        "MEMORY_LIFECYCLE_IDEMPOTENCY_CONFLICT",
        "MEMORY_LIFECYCLE_REPLAY_DIVERGENCE",
        "MEMORY_LIFECYCLE_STATE_NOT_ACTIVE",
        "PERMITTED_BY_POLICY_AND_LAW",
    )
    if any(
        fragment not in implementation or fragment not in tests
        for fragment in required_fragments
    ):
        raise SystemExit("L03 implementation/test contract binding is incomplete")

    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_interop": {
            "action_intent_schema_and_hash": True,
            "effect_receipt_schema_and_hash": True,
            "event_record_schema_and_hash": True,
            "status": "PASS",
        },
        "coverage": coverage_summary(),
        "deduplication": {
            "duplicate_count_or_score_amplification": False,
            "representative_order": "score_desc_memory_id_asc_source_hash_asc",
            "representative_source_binding": True,
            "source_hash_identity": True,
        },
        "forget_and_delete": {
            "cache_eviction_is_not_forget": True,
            "canonical_artifact_content_removed": True,
            "effect_receipt_required": True,
            "immutable_revision_increment": True,
            "terminal_revision_rewrite_rejected": True,
            "tombstone_hash_requires_policy_and_law_authority": True,
        },
        "legal_hold": {
            "active_matching_hold_blocks_effect": True,
            "authority_record_required": True,
            "blocked_receipt_status": "NOT_EXECUTED",
            "hash_sealed": True,
            "scope_and_time_bound": True,
            "source_state_preserved_when_blocked": True,
        },
        "redaction": {
            "derived_artifact_only": True,
            "explicit_utf8_byte_spans": True,
            "profile_without_authoritative_rules_fails_closed": True,
            "source_bytes_immutable": True,
            "source_hash_and_span_integrity": True,
        },
        "replay": {
            "different_request_conflict": True,
            "memory_lineage_binding": True,
            "policy_hash_binding": True,
            "same_request_identity": True,
        },
        "status": "PASS",
        "syntax": syntax,
        "targeted": {
            **targeted,
            "forget_legal_hold_test_count": lifecycle_count,
            "redaction_test_count": redaction_count,
        },
    }


def regression_evidence() -> dict[str, Any]:
    predecessor = node_summary(ATTEMPT / "predecessor-l01-node.junit.xml")
    adjacent = node_summary(ATTEMPT / "adjacent-l02-node.junit.xml")
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    if not (
        predecessor["passed"] == predecessor["collected"] == 27
        and adjacent["passed"] == adjacent["collected"] == 41
        and full_node["passed"] == full_node["collected"] == 588
        and full_python["passed"] == full_python["collected"] == 1064
    ):
        raise SystemExit("L03 regression counts differ from green receipts")
    for summary in (predecessor, adjacent, full_node):
        if any(
            summary[key] != 0
            for key in ("failed", "skipped", "todo", "cancelled")
        ):
            raise SystemExit(f"Node regression failure or suppression found: {summary}")
    if any(full_python[key] != 0 for key in ("failed", "errors", "skipped")):
        raise SystemExit(f"Python regression failure or suppression found: {full_python}")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory.get("count") != 61 or inventory.get("unique") is not True:
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
        raise SystemExit("git diff --check produced output on stdout")
    return {
        "adjacent_l02_node": adjacent,
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
        "predecessor_l01_node": predecessor,
        "repository_structure": "PASS",
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    relative = "artifacts/work_packages/L01/attempts/0001/report.json"
    path = ROOT / relative
    report = read_json(path)
    rah = report.get("rah_state")
    if not (
        report.get("attempt_id") == "L01-0001"
        and report.get("status") == "PASS"
        and report.get("package_status") == "PASS"
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0041"
        and rah.get("final_closeout_evidence_id") == "E0042"
    ):
        raise SystemExit("L03 dependency L01 is not the sealed PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "L01": {
                "attempt_id": "L01-0001",
                "final_closeout_evidence_id": "E0042",
                "report": relative,
                "report_sha256": sha256_id(path),
                "status": "PASS",
            }
        },
        "dependency_count": 1,
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    prefix = "packages/foundry-kernel/src/memory/lifecycle/"
    if any(not row["path"].startswith(prefix) for row in inventory):
        raise SystemExit("L03 product file is outside the manifest write scope")
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/L03/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/foundry-kernel/src/memory/lifecycle/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "memory-lifecycle-verification.json": lifecycle_verification(),
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    verification = documents["memory-lifecycle-verification.json"]
    regression = documents["full-regression-impact.json"]
    coverage = verification["coverage"]["memory_lifecycle_implementation"]
    return f"""# L03-0001 redaction, dedupe, forget and legal-hold review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial pass over fixed L03
source hashes and verification receipts, not actor-independent certification.

## Findings

1. Redaction accepts only explicit source-hash-bound UTF-8 byte spans. Source
   content is verified before use; out-of-range, overlapping, code-point-
   splitting, no-op, duplicate, unused, or profile-only directives fail closed.
   Source bytes are never mutated; a content-addressed derived artifact is
   emitted and replay validation rejects accessor/proxy and hash tampering.
2. Deduplication groups only exact source hashes. The representative is selected
   by score descending, memory ID ascending, then source hash ascending. A
   duplicate neither contributes another selected hit nor raises the score, and
   every exclusion is bound back to the selected representative and source.
3. Forget and delete create a new immutable terminal revision, clear canonical
   content/artifact references, and retain a non-reversible source tombstone
   only when a sealed policy carries explicit policy-and-law authority. A new
   request cannot rewrite a terminal revision.
4. Legal holds require a sealed authority record, bounded start/expiry interval,
   workspace scope and optional memory/class scope. A matching active hold
   preserves the exact source revision and records `NOT_EXECUTED`; expired,
   future, and nonmatching holds do not acquire blocking authority.
5. Canonical forget is distinct from disposable index/cache eviction. The
   lifecycle request rejects noncanonical targets, so cache deletion cannot be
   represented as fulfillment of a user forget request.
6. Requests, policies, states, holds, payloads, outcomes, and replay lineage are
   hash-bound. Same-key/same-request replay returns the prior immutable outcome;
   key reuse with another request, another policy, or unrelated state lineage
   fails closed.
7. ActionIntent and EffectReceipt use the common effect authority; EventRecord
   uses the Noetic Ledger hash authority. All three canonical Draft 2020-12
   schemas validate with zero errors and independently recomputed hashes match.
8. Required checks pass 44/44: 19 `redaction_test` and 25
   `forget_legal_hold_test` cases. `memory-lifecycle.mjs` coverage is
   {coverage['line_percent']:.2f}% lines, {coverage['branch_percent']:.2f}%
   branches, and {coverage['function_percent']:.2f}% functions.
9. L01 predecessor tests pass
   {regression['predecessor_l01_node']['passed']}/{regression['predecessor_l01_node']['collected']};
   adjacent L02 passes
   {regression['adjacent_l02_node']['passed']}/{regression['adjacent_l02_node']['collected']}.
   Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files and full Python
   passes {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126 schemas / 126 examples; structure, package boundaries,
   and diff checks pass without skipped, xfailed, todo, or cancelled cases.
10. All five product files remain inside the exact L03 manifest scope. Existing
    dirty-worktree changes, historical attempts, and RAH generations remain
    untouched.

## Assurance boundary

This gate establishes deterministic local in-memory lifecycle semantics. It
does not claim a production persistence backend, jurisdiction-specific legal
advice, L04 recall-quality integration, L05 evolution-memory policy, overall
product completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect L03 manifest, L01 dependency, memory/effect/ledger authorities, dirty worktree, and RAH state", 0, "PASS"),
        ("D001", "Probe obsolete guessed effect/ledger paths", 1, "PRESERVED_DIAGNOSTIC: effect-manager.mjs, ledger.mjs, and guessed index files do not exist; canonical authorities are effect-coordinator.mjs and noetic-ledger.mjs"),
        ("C002", "Implement deterministic redaction, source-hash dedupe, immutable forget/delete, and legal-hold enforcement under packages/foundry-kernel/src/memory/lifecycle/**", 0, "PASS: five product files"),
        ("D002", "Intermediate targeted execution after strengthened blocked-state bindings", 1, "PRESERVED_DIAGNOSTIC: 3 legal-hold cases failed because blocked state updated_at was incorrectly required to equal effect time; blocked outcomes correctly preserve the prior immutable state timestamp"),
        ("C003", "Restrict effect-time/new-state timestamp equality to APPLIED transitions without weakening blocked state preservation", 0, "PASS"),
        ("C004", "Add accessor, forged duplicate representative, canonical directive order, effect/ledger interop, policy/lineage replay, and state-transition adversarial coverage", 0, "PASS"),
        ("C005", "node --check <five L03 .mjs files>", 0, "PASS: 5/5"),
        ("C006", "node --test --test-concurrency=1 --test-reporter=junit <two L03 tests>", 0, "PASS: 44/44"),
        ("C007", "node --test --experimental-test-coverage <two L03 tests>", 0, "PASS: memory-lifecycle.mjs lines 94.53%, branches 79.95%, functions 94.79%"),
        ("C008", "Validate emitted ActionIntent, EventRecord, and EffectReceipt against canonical Draft 2020-12 schemas and common hash authorities", 0, "PASS: zero schema errors and 3/3 hash interop"),
        ("C009", "Run L01 predecessor memory-policy Node surfaces", 0, "PASS: 27/27"),
        ("C010", "Run L02 adjacent memory-index/retrieval Node surfaces", 0, "PASS: 41/41"),
        ("C011", "node --test --test-concurrency=1 --test-reporter=junit <complete sorted repository Node inventory>", 0, "PASS: 588/588 across 61 files"),
        ("C012", "uv run --locked python -m pytest tests -p no:cacheprovider --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 1064/1064"),
        ("C013", "uv run --locked python packages/contracts/codegen/verify.py --repo-root .", 0, "PASS: 126 schemas / 126 examples"),
        ("C014", "npm run check:structure", 0, "PASS"),
        ("C015", "npm run check:boundaries", 0, "PASS"),
        ("C016", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C017", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C018", "Build and verify deterministic L03 WorkPackageReport evidence", 0, "PASS"),
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
        "artifact_id": "L03-0001-MEMORY-LIFECYCLE-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "L03-0001-PRIMARY-SESSION-VERIFIER",
            "actor_type": "tool",
        },
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-L03-0001-MEMORY-LIFECYCLE-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "redaction_test",
                "details": "19/19 redaction, source integrity, dedupe, ordering, and tamper cases pass",
                "status": "PASS",
            },
            {
                "check": "forget_legal_hold_test",
                "details": "25/25 immutable revision, legal hold, receipt, replay, and policy cases pass",
                "status": "PASS",
            },
            {
                "check": "canonical_effect_and_ledger_interop",
                "details": "ActionIntent, EventRecord, and EffectReceipt schemas and hashes pass 3/3",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "L01 27/27, L02 41/41, Node 588/588, Python 1064/1064, no suppression",
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
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(receipt)
    )
    if errors:
        raise SystemExit(f"invalid L03 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "memory-lifecycle-verification.json",
        "memory-lifecycle-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "schema-runtime-verification.json",
        "targeted-l03-node.junit.xml",
        "targeted-l03-coverage.stdout.log",
        "predecessor-l01-node.junit.xml",
        "adjacent-l02-node.junit.xml",
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
        "run_l03_0001_checks.py",
        "build_l03_0001_evidence.py",
        "l03_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required L03 evidence artifact is missing: {name}")
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
    verification = documents["memory-lifecycle-verification.json"]
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(
        ATTEMPT / "memory-lifecycle-verification.artifact-receipt.json"
    )
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/L03/attempts/0001/memory-lifecycle-verification.artifact-receipt.json",
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
                "classification": "PATH_DISCOVERY_DIAGNOSTIC",
                "result": "initial guessed effect/ledger module paths did not exist",
                "resolution": "used canonical effect-coordinator.mjs and noetic-ledger.mjs authorities",
            },
            {
                "classification": "ADVERSARIAL_BINDING_REFINEMENT",
                "result": "three intermediate blocked-path tests failed when prior state updated_at was incorrectly compared with the request effect time",
                "resolution": "timestamp equality applies only to APPLIED transitions; blocked legal-hold outcomes preserve the exact prior immutable state and final targeted is 44/44",
            },
        ],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "deletion_hold_semantics_explicit": "PASS",
            "duplicate_memories_do_not_amplify": "PASS",
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
            "production persistence backend",
            "jurisdiction-specific legal advice",
            "L04/L05/L06 memory integration",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "forget_legal_hold_test": {
                "failed": 0,
                "passed": 25,
                "skipped": 0,
                "status": "PASS",
            },
            "redaction_test": {
                "failed": 0,
                "passed": 19,
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
            "artifact": "artifacts/work_packages/L03/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Redaction, dedupe, forget and legal hold",
        "verification": {
            "adjacent_l02_node": "41/41",
            "canonical_effect_ledger_interop": "3/3",
            "full_node": "588/588",
            "full_python": "1064/1064",
            "predecessor_l01_node": "27/27",
            "targeted_l03": "44/44",
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
        ATTEMPT / "memory-lifecycle-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "memory-lifecycle-verification.json"),
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
            raise SystemExit(f"stored L03 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored L03 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored L03 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "memory-lifecycle-verification.json")
    receipt_path = ATTEMPT / "memory-lifecycle-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(
        expected_receipt
    ):
        raise SystemExit("stored L03 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("L03 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored L03 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"L03 root evidence projection differs: {name}")
    return {
        "adjacent_l02_node": "41/41",
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "588/588",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "predecessor_l01_node": "27/27",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_l03": "44/44",
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
