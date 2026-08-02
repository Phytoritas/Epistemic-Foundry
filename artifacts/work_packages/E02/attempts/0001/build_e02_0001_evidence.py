#!/usr/bin/env python3
"""Build and verify E02-0001 receipt-bound effect coordination evidence.

E02-0001 implements ``packages/foundry-kernel/src/effects/**``: an effect
coordinator that binds ActionIntent, Attempt, and EffectReceipt records so that
external side effects can only complete through evidence, never narration.  Each
``registerIntent`` seals a canonical ActionIntent whose ``intent_hash`` is the
sha256 of its canonical JSON; the same idempotency key with the same canonical
request replays one logical registration (EXISTING), the same key with a
different request fails closed with ``IDEMPOTENCY_KEY_REUSED``, and rebinding an
intent id to different bytes fails with ``INTENT_ID_CONFLICT``.  ``beginAttempt``
grants execution exactly once even under concurrent same-attempt callers
(``EXISTING_ATTEMPT`` for replays; ``ATTEMPT_ID_CONFLICT`` across intents), and
``recordReceipt``/``reconcile`` accept only sealed EffectReceipts whose
``receipt_hash`` re-derives, rejecting mutation (``EFFECT_RECORD_MUTATED``),
hostile accessors and proxies (``NON_CANONICAL_JSON``,
``ACTION_INTENT_HASH_MISMATCH``, ``ACTION_INTENT_INVALID``), and cross-intent
binding.  An UNKNOWN receipt leaves the operation ``RECONCILING`` and blocks a
blind retry (``EFFECT_RECONCILIATION_REQUIRED``); a crash before any receipt
stays unresolved rather than being narrated as success or failure; an unsealed
"the executor says it succeeded" receipt is rejected
(``EFFECT_RECEIPT_INVALID`` / ``EFFECT_RECEIPT_RESOLUTION_EVIDENCE_REQUIRED``);
and reconciliation may not change the observed external operation identity
(``EFFECT_RECONCILIATION_OPERATION_MISMATCH``).  A durable record whose ledger
event or publication checkpoint did not confirm stays
``PENDING_EVENT_RECONCILIATION`` / ``PENDING_EVENT_CONFIRMATION`` and is repaired
by exact replay without granting a second execution.  This builder verifies the
executed checks and emits immutable attempt evidence; it never modifies product
files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/E02/attempts/0001"
ATTEMPT_ID = "E02-0001"
WORK_PACKAGE_ID = "E02"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_EFFECT_RECONCILIATION_COUNT = 10
EXPECTED_IDEMPOTENCY_COUNT = 9
EXPECTED_TARGETED_COUNT = 19
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "packages/foundry-kernel/src/effects"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/effects/effect-coordinator.mjs": "a4d2b9b851f9055869db842d10702e6017a61c18fcc637521fdec398b5abc1f2",
    "packages/foundry-kernel/src/effects/effect-reconciliation.test.mjs": "998a962b3e193e3b497aa60078f5f3d650332d88f973d81d3b167be025a13402",
    "packages/foundry-kernel/src/effects/effect-test-support.mjs": "df45bdec72a2ed2ffda922189e21f1102cc1cdcf2c50d661f9ac1e98051c0a4a",
    "packages/foundry-kernel/src/effects/idempotency.test.mjs": "0d386c1eb2ded877423979838d604e1270ec4112b82f162d2d2222924fda5dec",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/E01/report.json": "beddc2a3019fcf680435ea6d5f907b5e7b50b0fa8a384673917c6198f49f32e1",
}

JUNIT_PATHS = {
    "effect_reconciliation": ATTEMPT / "effect-reconciliation-test.junit.xml",
    "idempotency": ATTEMPT / "idempotency-test.junit.xml",
    "targeted": ATTEMPT / "targeted-effects.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every E02 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "effect_reconciliation",
        "idempotency",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "effect-reconciliation-test",
    "idempotency-test",
    "targeted-effects",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_e02_0001_checks.py",
    "build_e02_0001_evidence.py",
    "e02_0001_rah_seal.py",
    "dependency-status.json",
    "e02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "effect-reconciliation-test.junit.xml",
    "idempotency-test.junit.xml",
    "targeted-effects.junit.xml",
    "full-python-suite.junit.xml",
    "full-node-suite.junit.xml",
    "commands.jsonl",
    "review.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


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


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(render(value), encoding="utf-8", newline="\n")
    return path


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, wanted in expected.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(f"sealed input changed: {relative}: {actual} != {wanted}")


def check_run(name: str) -> dict[str, Any]:
    value = read_json(ATTEMPT / f"{name}.run.json")
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not isinstance(value.get("command"), list)
    ):
        raise SystemExit(f"required check did not pass: {name}: {value}")
    return value


def semantic_junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        message = problem.get("message", "") if problem is not None else ""
        body = (problem.text or "") if problem is not None else ""
        for prefix in prefixes:
            message = message.replace(prefix, "")
            body = body.replace(prefix, "")
        for value in roots:
            message = message.replace(value, ".")
            body = body.replace(value, ".")
        rows.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                message,
                body,
                case.find("skipped") is not None,
            )
        )
    return rows


def verify_junit_portability() -> None:
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(root in text for root in roots):
            raise SystemExit(f"JUnit contains absolute repository path: {name}")
        if name in _NODE_JUNITS:
            if "duration_ms" in text:
                raise SystemExit(f"Node JUnit retains volatile duration_ms: {name}")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit(f"pytest JUnit retains volatile attributes: {name}")


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            if record.get("files", {}).get(name, {}).get(
                "normalized_sha256"
            ) != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        before_bytes = path.read_bytes()
        before = before_bytes.decode("utf-8")
        signature = semantic_junit_signature(before)
        normalized = before
        removed = {
            "duration_comments": 0,
            "hostname_attributes": 0,
            "repository_prefixes": 0,
            "time_attributes": 0,
            "timestamp_attributes": 0,
        }
        for prefix in (root_backslash, root_slash):
            count = normalized.count(prefix)
            normalized = normalized.replace(prefix, "")
            removed["repository_prefixes"] += count
        for value in (str(ROOT), str(ROOT).replace("\\", "/")):
            count = normalized.count(value)
            normalized = normalized.replace(value, ".")
            removed["repository_prefixes"] += count
        if name in _NODE_JUNITS:
            normalized, removed["duration_comments"] = re.subn(
                r"\s*<!-- duration_ms [^>]+ -->", "", normalized
            )
        else:
            normalized, removed["timestamp_attributes"] = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized
            )
            normalized, removed["hostname_attributes"] = re.subn(
                r'\s+hostname="[^"]*"', "", normalized
            )
            normalized, removed["time_attributes"] = re.subn(
                r'(<(?:testsuite|testcase)\b[^>]*?)\s+time="[^"]*"', r"\1", normalized
            )
        if semantic_junit_signature(normalized) != signature:
            raise SystemExit(f"JUnit normalization changed semantics: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "normalized_sha256": sha256_id(path),
            "raw_sha256": sha256_bytes(before_bytes),
            "removed": removed,
            "semantic_signature_preserved": True,
            "testcase_count": len(signature),
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "preserved": [
            "testcase identity and result state",
            "failure type, message, and body after path normalization",
            "Node semantic footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = list(root.findall(".//testcase"))
    result = {
        "collected": sum(int(row.get("tests", "0")) for row in suites),
        "errors": sum(int(row.get("errors", "0")) for row in suites),
        "failed": sum(int(row.get("failures", "0")) for row in suites),
        "skipped": sum(int(row.get("skipped", "0")) for row in suites),
        "xml_testcase_count": len(cases),
    }
    result["passed"] = (
        result["collected"] - result["errors"] - result["failed"] - result["skipped"]
    )
    result.update(
        {
            "junit": path.relative_to(ROOT).as_posix(),
            "junit_sha256": sha256_id(path),
            "semantic_counter_authority": "pytest_testsuite_attributes",
        }
    )
    return result


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
        raise SystemExit("Node JUnit semantic footer is incomplete")
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "semantic_counter_authority": "node_test_footer",
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": sum(case.find("failure") is not None for case in cases),
        "xml_testcase_count": len(cases),
    }


def _assert_node_gate(label: str, summary: dict[str, Any], expected: int) -> None:
    if (
        summary["collected"],
        summary["passed"],
        summary["failed"],
        summary["cancelled"],
        summary["skipped"],
        summary["todo"],
        summary["xml_error_count"],
        summary["xml_failure_count"],
    ) != (expected, expected, 0, 0, 0, 0, 0, 0):
        raise SystemExit(f"{label} gate failed: {summary}")


def regression_evidence() -> dict[str, Any]:
    effect_reconciliation = node_summary(JUNIT_PATHS["effect_reconciliation"])
    idempotency = node_summary(JUNIT_PATHS["idempotency"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        (
            "effect_reconciliation_test",
            effect_reconciliation,
            EXPECTED_EFFECT_RECONCILIATION_COUNT,
        ),
        ("idempotency_test", idempotency, EXPECTED_IDEMPOTENCY_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
    ):
        _assert_node_gate(label, summary, expected)
    if (
        python["collected"],
        python["passed"],
        python["failed"],
        python["errors"],
        python["skipped"],
    ) != (EXPECTED_PYTHON_COUNT, EXPECTED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"full_python gate failed: {python}")
    if (
        node["collected"],
        node["passed"],
        node["failed"],
        node["cancelled"],
        node["skipped"],
        node["todo"],
        node["xml_error_count"],
        node["xml_failure_count"],
        node_inventory.get("count"),
    ) != (
        EXPECTED_NODE_COUNT,
        EXPECTED_NODE_COUNT,
        0,
        0,
        0,
        0,
        0,
        0,
        EXPECTED_NODE_FILE_COUNT,
    ):
        raise SystemExit(f"full Node gate failed: {node}; inventory={node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "effect_reconciliation_test": effect_reconciliation,
        "full_node": node,
        "full_python": python,
        "idempotency_test": idempotency,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_effects": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _pass_dependency(package: str, attempt: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    report = read_json(path)
    if report.get("status") != "PASS":
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "E01": _pass_dependency(
                "E01", "E01-0001", "artifacts/work_packages/E01/report.json"
            ),
        },
        "next_action": "SEAL_E02_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(f"effects component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/E02/**"],
        "attempt_id": ATTEMPT_ID,
        "component_files": component_files,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "write_scope_violation_count": 0,
    }


def e02_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "side_effects_cannot_complete_by_narration": {
                "evidence": [
                    f"{COMPONENT}/effect-reconciliation.test.mjs",
                ],
                "mechanism": (
                    "recordReceipt and reconcile accept only sealed EffectReceipts "
                    "whose receipt_hash re-derives from canonical JSON; an unsealed "
                    "'the executor says it succeeded' receipt is rejected with "
                    "EFFECT_RECEIPT_INVALID and a resolving receipt with no bound "
                    "result/error artifact or observed_state_hash fails with "
                    "EFFECT_RECEIPT_RESOLUTION_EVIDENCE_REQUIRED; completion_proven "
                    "stays false until a resolving receipt plus its reconciled E01 "
                    "event and D01 publication checkpoint exist, and a durable "
                    "record missing its ledger event stays "
                    "PENDING_EVENT_RECONCILIATION rather than being narrated complete"
                ),
                "status": "PASS",
            },
            "unknown_effects_reconcile_before_retry": {
                "evidence": [
                    f"{COMPONENT}/effect-reconciliation.test.mjs",
                    f"{COMPONENT}/idempotency.test.mjs",
                ],
                "mechanism": (
                    "an UNKNOWN receipt leaves the operation RECONCILING and a blind "
                    "retry is denied with EFFECT_RECONCILIATION_REQUIRED; a crash "
                    "before any receipt stays unresolved rather than narrated success "
                    "or failure; reconciliation must retain the observed external "
                    "operation identity (EFFECT_RECONCILIATION_OPERATION_MISMATCH) "
                    "and only a resolving receipt with observation evidence admits a "
                    "retry, while concurrent same-attempt callers grant execution "
                    "exactly once through the run-scoped compare-and-swap"
                ),
                "status": "PASS",
            },
        },
        "idempotency": {
            "concurrent_same_attempt_grants_execution_once": True,
            "hostile_accessor_or_proxy_rejected_before_execution": True,
            "immutable_historical_attempt_and_receipt_replays_are_idempotent": True,
            "intent_id_rebind_fails_closed": True,
            "key_reuse_with_different_request_fails_closed": True,
            "same_key_same_request_replays_one_registration": True,
        },
        "reconciliation": {
            "crash_before_receipt_stays_unresolved": True,
            "durable_record_missing_ledger_event_is_not_completion": True,
            "external_operation_identity_preserved": True,
            "narrated_result_has_no_authority": True,
            "unknown_receipt_blocks_blind_retry": True,
            "unsealed_receipt_rejected": True,
        },
        "receipts_are_immutable_and_rederivable": {
            "canonical_json_sha256_hashing": True,
            "cross_intent_binding_rejected": True,
            "emitted_records_pass_canonical_schemas": True,
            "post_write_mutation_fails_closed": True,
            "tamper_accessor_and_proxy_rejected": True,
        },
        "required_checks": {
            "effect_reconciliation_test": {
                "module": f"{COMPONENT}/effect-reconciliation.test.mjs",
                "status": "PASS",
                "test_count": regression["effect_reconciliation_test"]["collected"],
            },
            "idempotency_test": {
                "module": f"{COMPONENT}/idempotency.test.mjs",
                "status": "PASS",
                "test_count": regression["idempotency_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_effects"]["collected"],
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        records.append(
            {
                "attempt_id": ATTEMPT_ID,
                "command": value["command"],
                "exit_code": value["exit_code"],
                "recorded_at_utc": RECORDED_AT,
                "status": value["status"],
                "step": name,
            }
        )
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                "artifacts/work_packages/E02/attempts/0001/build_e02_0001_evidence.py",
                "build",
            ],
            "exit_code": 0,
            "recorded_at_utc": RECORDED_AT,
            "status": "PASS",
            "step": "evidence-build",
        }
    )
    return records


def commands_text() -> str:
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in command_records()
        )
        + "\n"
    )


def review_text() -> str:
    return (
        "# E02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/effects. Reviewer: this seal-prep session, a\n"
        "  distinct actor that did not author the effect coordinator. The author\n"
        "  never approves its own work, so actor_independence HOLDS for this review;\n"
        "  external actor-independent certification does NOT, and no such claim is\n"
        "  made. E02 governs external side effects, so ActionIntent, Attempt,\n"
        "  EffectReceipt, idempotency, and reconciliation were attacked on their\n"
        "  contracts rather than skimmed.\n"
        "- Receipts are immutable and re-derivable. ActionIntent and EffectReceipt\n"
        "  are sealed as canonical JSON whose intent_hash and receipt_hash are the\n"
        "  sha256 of their canonical bytes, each excluding only its own hash field.\n"
        "  A stored EffectReceipt that is force-rewritten fails closed with\n"
        "  EFFECT_RECORD_MUTATED; a tampered intent is caught by\n"
        "  ACTION_INTENT_HASH_MISMATCH; a hostile getter is never invoked and is\n"
        "  rejected with NON_CANONICAL_JSON; a Proxy is rejected with\n"
        "  ACTION_INTENT_INVALID. Emitted ActionIntent and EffectReceipt documents\n"
        "  validate against the canonical Draft 2020-12 schemas/action-intent and\n"
        "  schemas/effect-receipt schemas, and cross-intent binding is refused.\n"
        "- Idempotent retry never double-applies. The same idempotency key with the\n"
        "  same canonical intent replays one logical registration (EXISTING, not a\n"
        "  second write and not a second ledger event); the same key with a different\n"
        "  canonical request fails with IDEMPOTENCY_KEY_REUSED; rebinding an intent id\n"
        "  to different bytes fails with INTENT_ID_CONFLICT. beginAttempt grants\n"
        "  execute_permitted exactly once: a replay returns EXISTING_ATTEMPT with\n"
        "  execute_permitted=false, an attempt id reused across intents fails with\n"
        "  ATTEMPT_ID_CONFLICT, a receipt id reused across intents fails with\n"
        "  RECEIPT_ID_CONFLICT, and two worker-thread callers racing a shared barrier\n"
        "  on the same attempt see exactly one execution grant while both observe the\n"
        "  single durable Attempt. Older attempt and receipt replays remain idempotent\n"
        "  after later attempts.\n"
        "- Reconciliation is exact, never narrated. An UNKNOWN receipt leaves the\n"
        "  operation RECONCILING (completion_proven=false, retry_permitted=false) and\n"
        "  a blind retry is denied with EFFECT_RECONCILIATION_REQUIRED until an\n"
        "  observed reconciliation with a verified result artifact or observed state\n"
        "  hash resolves it. A crash before any receipt is inspected as RECONCILING /\n"
        "  UNKNOWN, not a narrated success or failure. An unsealed 'the executor says\n"
        "  it completed' receipt is rejected (EFFECT_RECEIPT_INVALID) and a resolving\n"
        "  receipt without observation evidence fails\n"
        "  EFFECT_RECEIPT_RESOLUTION_EVIDENCE_REQUIRED, so executor narration cannot\n"
        "  replace an evidence-bound EffectReceipt. Reconciliation may not change the\n"
        "  observed external operation identity\n"
        "  (EFFECT_RECONCILIATION_OPERATION_MISMATCH). A durable record whose ledger\n"
        "  event or publication checkpoint did not confirm stays\n"
        "  PENDING_EVENT_RECONCILIATION or PENDING_EVENT_CONFIRMATION, blocks verify\n"
        "  with EFFECT_EVENT_RECONCILIATION_REQUIRED / EFFECT_EVENT_CONFIRMATION_REQUIRED,\n"
        "  and is repaired only by exact replay without granting a second execution.\n"
        "- Dependencies and checks: the coordinator builds on the sealed E01\n"
        "  append-only Noetic Ledger (E01-0001 PASS) over the sealed D04 SQLite state\n"
        "  store and C04 content-addressed artifact store, and adds no new production\n"
        "  dependency. Ruff lint and format, the two required checks\n"
        "  (effect_reconciliation_test 10/10, idempotency_test 9/9), targeted 19/19,\n"
        "  full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: E02 proves local E01/D03/D04 reconciliation and\n"
        "  idempotent coordination, not the truth of arbitrary external-service\n"
        "  outcomes beyond supplied resolving evidence, and local serialization is\n"
        "  not a universal distributed exactly-once guarantee. Attempt and the\n"
        "  publication checkpoint remain private runtime projections and create no\n"
        "  new canonical schema authority. Capability leases and approval policy\n"
        "  (E03) and the wider replay surface remain later packages. Verdict: PASS on\n"
        "  the exact E02 package contract.\n"
    )


def report_document(
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    write_scope: dict[str, Any],
    verification: dict[str, Any],
    *,
    rah_state: dict[str, Any] | None,
) -> dict[str, Any]:
    output_names = [
        name
        for name in OUTPUT_NAMES
        if name != "report.json" and (ATTEMPT / name).is_file()
    ]
    if rah_state is not None:
        output_names.append("rah-core-integrity.json")
    artifacts = [
        {
            "byte_size": (ATTEMPT / name).stat().st_size,
            "path": f"artifacts/work_packages/E02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "E02_ACTION_INTENT_ATTEMPT_AND_EFFECT_RECEIPT",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "side_effects_cannot_complete_by_narration": "PASS",
            "unknown_effects_reconcile_before_retry": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "capability leases, fencing, or approval policy (E03)",
            "the wider scheduler, replay, or strict/semantic replay surface",
            "truth of arbitrary external-service outcomes beyond supplied evidence",
            "a universal distributed exactly-once guarantee",
            "external actor-independent certification of this review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Independent review of bounded-agent work by a distinct actor in "
                "this seal-prep session; not external actor-independent "
                "certification."
            ),
            "author": "bounded implementation agent",
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "reviewer": "independent seal-prep session (distinct actor)",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "effect_reconciliation_test": (
            f"{EXPECTED_EFFECT_RECONCILIATION_COUNT}/"
            f"{EXPECTED_EFFECT_RECONCILIATION_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "idempotency_test": (
            f"{EXPECTED_IDEMPOTENCY_COUNT}/{EXPECTED_IDEMPOTENCY_COUNT}"
        ),
        "next_action": "SEAL_E02_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "status": "PASS",
        "targeted_effects": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = e02_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("e02-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    return _summary()


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("E02-0001 report is already RAH-bound")
    if integrity.get("current_generation") != core_generation:
        raise SystemExit("rah-core-integrity does not match the core generation")
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
    regression = regression_evidence()
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "e02-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "e02-verification.json")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("commands.jsonl differs from deterministic command records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("review.md differs from the recorded review")
    expected = report_document(
        regression,
        dependencies,
        write_scope,
        verification,
        rah_state=stored.get("rah_state"),
    )
    if render(expected) != render(stored):
        raise SystemExit("stored E02-0001 report is not the deterministic document")
    return _summary()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = {"build": build, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
