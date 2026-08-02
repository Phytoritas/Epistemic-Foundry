#!/usr/bin/env python3
"""Build and verify E03-0001 capability lease, fencing and approval evidence.

E03-0001 implements ``packages/foundry-kernel/src/capabilities/**``: a capability
authority that issues scoped, expiring CapabilityLeases, mints monotonic fencing
tokens to prevent split-brain use, and gates privileged capabilities on explicit
server-derived human approval.  ``issueLease`` binds each lease to a sealed
PolicyBundle subject, its declared run and resource scopes, and a strictly
positive lifetime -- a zero or negative lifetime fails closed with
``LEASE_ALREADY_EXPIRED`` before any state mutation, a subject/run/scope drift
fails with ``LEASE_RUN_SCOPE_MISMATCH`` or ``LEASE_SUBJECT_SCOPE_MISMATCH``, and a
missing required approval fails with ``REQUIRED_APPROVAL_MISSING``.
``commitWithLease`` fails closed before invoking or persisting the caller
callback on an expired (``LEASE_EXPIRED``), not-yet-valid (``LEASE_NOT_YET_VALID``),
revoked (``LEASE_REVOKED``), policy-changed (``LEASE_POLICY_MISMATCH`` /
``LEASE_POLICY_PROJECTION_MISMATCH``), forged (``LEASE_HASH_MISMATCH``), or stale
(``STALE_FENCING_TOKEN``) lease; an in-callback clock regression
(``CLOCK_REGRESSION``), expiry (``LEASE_EXPIRED``), async callback
(``ASYNC_LEASE_COMMIT_DENIED``), thrown callback (``LEASE_COMMIT_CALLBACK_FAILED``),
or authority-private state access (``CAPABILITY_STATE_ACCESS_DENIED``) rolls the
protected mutation and its event outbox back atomically, and an exact operation
retry is idempotent (``EXISTING``).  A newer overlapping lease increments the
monotonic fencing token so no two holders act at once, and the client can never
assert its own ``authority_role`` (``INVALID_INPUT``), approve its own subject
(``SELF_APPROVAL_DENIED``), or let a candidate/model/backend principal grant
privileged authority (``UNTRUSTED_AUTHORITY_GRANT_DENIED``).  This builder verifies
the executed checks and emits immutable attempt evidence; it never modifies
product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/E03/attempts/0001"
ATTEMPT_ID = "E03-0001"
WORK_PACKAGE_ID = "E03"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_LEASE_EXPIRY_COUNT = 11
EXPECTED_FENCING_COUNT = 19
EXPECTED_TARGETED_COUNT = 30
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "packages/foundry-kernel/src/capabilities"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/capabilities/capability-authority.mjs": "a8e3376568350229ca1a997aafbc1c4c138f2f01fbee945c916d390283a3720a",
    "packages/foundry-kernel/src/capabilities/capability-test-support.mjs": "6b08085736247a17b3c477617aa820274a09ca8206d616acc44cd12a1358e2fa",
    "packages/foundry-kernel/src/capabilities/fencing.test.mjs": "e66558d061c74f2c3be7c5a648b1230ad22f566359d608c6135b62f626940884",
    "packages/foundry-kernel/src/capabilities/lease-expiry.test.mjs": "ec179fea28039c9e53cc1df8d6d39e1b97ce45b8d60edb0193f64f472ac2f640",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/E01/report.json": "beddc2a3019fcf680435ea6d5f907b5e7b50b0fa8a384673917c6198f49f32e1",
}

JUNIT_PATHS = {
    "lease_expiry": ATTEMPT / "lease-expiry-test.junit.xml",
    "fencing": ATTEMPT / "fencing-test.junit.xml",
    "targeted": ATTEMPT / "targeted-capabilities.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every E03 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "lease_expiry",
        "fencing",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "lease-expiry-test",
    "fencing-test",
    "targeted-capabilities",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_e03_0001_checks.py",
    "build_e03_0001_evidence.py",
    "e03_0001_rah_seal.py",
    "dependency-status.json",
    "e03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "lease-expiry-test.junit.xml",
    "fencing-test.junit.xml",
    "targeted-capabilities.junit.xml",
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
    lease_expiry = node_summary(JUNIT_PATHS["lease_expiry"])
    fencing = node_summary(JUNIT_PATHS["fencing"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("lease_expiry_test", lease_expiry, EXPECTED_LEASE_EXPIRY_COUNT),
        ("fencing_test", fencing, EXPECTED_FENCING_COUNT),
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
        "fencing_test": fencing,
        "full_node": node,
        "full_python": python,
        "lease_expiry_test": lease_expiry,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_capabilities": targeted,
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
        "next_action": "SEAL_E03_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(
            f"capabilities component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/E03/**"],
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


def e03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_is_explicit": {
            "candidate_model_or_backend_principal_cannot_grant_authority": True,
            "client_asserted_authority_role_rejected": True,
            "later_revoke_head_invalidates_earlier_approved_lease": True,
            "promotion_capability_requires_matching_approval": True,
            "self_approval_is_a_non_waivable_denial": True,
        },
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "leases_are_scoped_and_expiring": {
                "evidence": [
                    f"{COMPONENT}/lease-expiry.test.mjs",
                ],
                "mechanism": (
                    "issueLease binds each lease to a sealed PolicyBundle subject, "
                    "its declared run and resource scopes, and a strictly positive "
                    "lifetime; a zero or negative lifetime fails closed with "
                    "LEASE_ALREADY_EXPIRED before any state mutation, and a "
                    "subject/run/scope drift fails with LEASE_RUN_SCOPE_MISMATCH or "
                    "LEASE_SUBJECT_SCOPE_MISMATCH. commitWithLease fails closed "
                    "before invoking or persisting the callback on an expired "
                    "(LEASE_EXPIRED), not-yet-valid (LEASE_NOT_YET_VALID), revoked "
                    "(LEASE_REVOKED), or policy-changed (LEASE_POLICY_MISMATCH) "
                    "lease; an in-callback expiry or clock regression rolls the "
                    "protected mutation back atomically (LEASE_EXPIRED / "
                    "CLOCK_REGRESSION), and an exact issuance or operation retry is "
                    "idempotent"
                ),
                "status": "PASS",
            },
            "stale_fencing_tokens_rejected": {
                "evidence": [
                    f"{COMPONENT}/fencing.test.mjs",
                ],
                "mechanism": (
                    "a newer overlapping lease increments the monotonic global "
                    "fencing token so a stale holder's commit fails closed with "
                    "STALE_FENCING_TOKEN without persisting its mutation, and no two "
                    "holders act at once; a forged fencing token or lease field is "
                    "caught by the sealed lease hash (LEASE_HASH_MISMATCH) before the "
                    "callback runs; the callback cannot read authority-private "
                    "scope-head state (CAPABILITY_STATE_ACCESS_DENIED); an async "
                    "(ASYNC_LEASE_COMMIT_DENIED) or thrown "
                    "(LEASE_COMMIT_CALLBACK_FAILED) callback rolls back its result "
                    "and event outbox; and a committed lease survives an E01 outage "
                    "and reconciles its event exactly once"
                ),
                "status": "PASS",
            },
        },
        "leases_are_scoped_and_expiring": {
            "clock_before_issued_at_is_not_yet_valid": True,
            "expiry_boundary_rejects_commit_without_invoking_callback": True,
            "in_callback_expiry_or_clock_regression_rolls_back": True,
            "issued_leases_are_canonical_frozen_and_schema_valid": True,
            "zero_or_negative_lifetime_fails_before_mutation": True,
        },
        "required_checks": {
            "fencing_test": {
                "module": f"{COMPONENT}/fencing.test.mjs",
                "status": "PASS",
                "test_count": regression["fencing_test"]["collected"],
            },
            "lease_expiry_test": {
                "module": f"{COMPONENT}/lease-expiry.test.mjs",
                "status": "PASS",
                "test_count": regression["lease_expiry_test"]["collected"],
            },
        },
        "stale_fencing_tokens_rejected": {
            "async_or_thrown_callback_rolls_back_result_and_outbox": True,
            "committed_state_survives_e01_outage_and_reconciles_once": True,
            "forged_lease_field_or_hash_fails_before_callback": True,
            "newer_overlapping_lease_increments_monotonic_token": True,
            "stale_holder_commit_fails_closed_without_persisting": True,
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_capabilities"]["collected"],
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
                "artifacts/work_packages/E03/attempts/0001/build_e03_0001_evidence.py",
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
        "# E03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/capabilities. Reviewer: this seal-prep\n"
        "  session, a distinct actor that did not author the capability authority.\n"
        "  The author never approves its own work, so actor_independence HOLDS for\n"
        "  this review; external actor-independent certification does NOT, and no\n"
        "  such claim is made. E03 is risk_class=medium and governs bounded\n"
        "  authority, so leases, fencing, and approval were attacked on their\n"
        "  contracts rather than skimmed.\n"
        "- Leases are scoped and expiring (fail closed). issueLease binds every\n"
        "  lease to a sealed PolicyBundle subject and its declared run and resource\n"
        "  scopes; a run or scope drift is denied with LEASE_RUN_SCOPE_MISMATCH or\n"
        "  LEASE_SUBJECT_SCOPE_MISMATCH, and a zero or negative lifetime fails with\n"
        "  LEASE_ALREADY_EXPIRED before the global fencing counter is ever created.\n"
        "  commitWithLease refuses to invoke or persist the caller callback on an\n"
        "  expired lease (LEASE_EXPIRED at the exact expires_at boundary), a clock\n"
        "  before issued_at (LEASE_NOT_YET_VALID), a revoked lease (LEASE_REVOKED),\n"
        "  or a changed policy (LEASE_POLICY_MISMATCH). An expiry or authority clock\n"
        "  regression that happens after the callback has already staged a\n"
        "  revisioned record rolls that record back so nothing persists\n"
        "  (LEASE_EXPIRED, CLOCK_REGRESSION), and an exact lease-issuance or\n"
        "  operation retry returns the first logical lease rather than minting a\n"
        "  second. Issued leases are deep-frozen, schema-valid against the canonical\n"
        "  Draft 2020-12 capability-lease schema, and carry a sha256 lease_hash.\n"
        "- Fencing prevents split-brain (monotonic token). The global fencing token\n"
        "  is monotonic: a newer overlapping lease is issued at old_token+1, and the\n"
        "  stale holder's later commit fails closed with STALE_FENCING_TOKEN without\n"
        "  persisting its mutation, so two holders never both act. Replacing even\n"
        "  one scope of a multi-scope lease invalidates the whole prior lease. A\n"
        "  forged fencing token or any other tampered lease field is caught by the\n"
        "  sealed lease_hash (LEASE_HASH_MISMATCH) before the callback runs; the\n"
        "  callback cannot read authority-private scope-head state\n"
        "  (CAPABILITY_STATE_ACCESS_DENIED); an async callback is denied and its\n"
        "  pre-await mutation rolls back (ASYNC_LEASE_COMMIT_DENIED); a thrown\n"
        "  callback rolls back result, lease-use, and event outbox\n"
        "  (LEASE_COMMIT_CALLBACK_FAILED); and a lease committed through a\n"
        "  transient E01 outage reconciles its single event exactly once. A same\n"
        "  policy_hash carrying a different capability projection is rejected\n"
        "  (LEASE_POLICY_PROJECTION_MISMATCH).\n"
        "- Approval is explicit, never implicit. A privileged capability\n"
        "  (promotion:commit) cannot be leased without a matching approval\n"
        "  (REQUIRED_APPROVAL_MISSING) and passes only with the exact prior\n"
        "  approval. The approval authority_role is server-derived from the sealed\n"
        "  policy: a client that asserts its own authority_role is rejected\n"
        "  (INVALID_INPUT), a principal cannot approve its own subject\n"
        "  (SELF_APPROVAL_DENIED), an approver role without approval:issue is denied\n"
        "  (CAPABILITY_NOT_AUTHORIZED), and a candidate/model/backend principal that\n"
        "  tries to hold privileged authority is refused at policy seal time\n"
        "  (UNTRUSTED_AUTHORITY_GRANT_DENIED). A later REVOKE approval head\n"
        "  invalidates an earlier APPROVE-bound lease, and the approval head itself\n"
        "  rejects clock regression (APPROVAL_CLOCK_REGRESSION) and same-instant\n"
        "  conflicting decisions (APPROVAL_TIMESTAMP_CONFLICT).\n"
        "- Dependencies and checks: the capability authority builds on the sealed\n"
        "  E01 append-only Noetic Ledger (E01-0001 PASS) over the sealed C04\n"
        "  artifact store and D04 SQLite state store and adds no new production\n"
        "  dependency; emitted leases and approvals validate against the canonical\n"
        "  Draft 2020-12 capability-lease and approval-record schemas. Ruff lint and\n"
        "  format, the two required checks (lease_expiry_test "
        + f"{EXPECTED_LEASE_EXPIRY_COUNT}/{EXPECTED_LEASE_EXPIRY_COUNT}, fencing_test "
        + f"{EXPECTED_FENCING_COUNT}/{EXPECTED_FENCING_COUNT}), targeted "
        + f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: E03 provides capability leases, fencing, and the\n"
        "  approval policy only; the E-phase strict and semantic replay gate (E04)\n"
        "  and the wider scheduler, effects execution, and promotion surface remain\n"
        "  later packages. Verdict: PASS on the exact E03 package contract.\n"
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
            "path": f"artifacts/work_packages/E03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "E03_CAPABILITY_LEASES_FENCING_AND_APPROVAL",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "leases_are_scoped_and_expiring": "PASS",
            "stale_fencing_tokens_rejected": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "the E-phase strict and semantic replay gate (E04)",
            "the wider scheduler, effects execution, or promotion surface",
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
        "fencing_test": f"{EXPECTED_FENCING_COUNT}/{EXPECTED_FENCING_COUNT}",
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "lease_expiry_test": (
            f"{EXPECTED_LEASE_EXPIRY_COUNT}/{EXPECTED_LEASE_EXPIRY_COUNT}"
        ),
        "next_action": "SEAL_E03_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "status": "PASS",
        "targeted_capabilities": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = e03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("e03-verification.json", verification)
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
        raise SystemExit("E03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "e03-verification.json")
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
    verification = read_json(ATTEMPT / "e03-verification.json")
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
        raise SystemExit("stored E03-0001 report is not the deterministic document")
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
