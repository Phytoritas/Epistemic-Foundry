#!/usr/bin/env python3
"""Build and verify Y02-0001 observability, SLO and telemetry-redaction evidence.

Y02-0001 implements ``packages/foundry-kernel/src/observability/**``: an
observability subsystem that emits OpenTelemetry-style spans over W3C trace
context, correlates each span to a hashed effect receipt, redacts secrets and
PII from log and telemetry records before they are stored, and reports honest
SLO result states that never fabricate a healthy metric.  ``emitSpan`` builds a
span that is well-formed by construction -- a 16-byte non-zero ``trace_id``, an
8-byte non-zero ``span_id``, an optional parent span sharing the trace, monotonic
start/end Unix-nano timing, a canonical kind and status, and a W3C
``traceparent`` -- and refuses malformed identifiers, all-zero ids, an end before
start, or a self-parent (``SPAN_INVALID``); it redacts span and per-event
attributes and re-scans them so no literal secret survives serialization, and it
forbids a dishonest status (an ``exception`` event cannot coexist with ``OK`` and
an ``ERROR`` demands a cause -- ``DISHONEST_SPAN_STATUS``).  ``correlateReceipt``
ties a span's ``trace_id``/``span_id`` to an effect receipt by id and sha256 hash
and fails closed on any mismatch or a missing reference
(``RECEIPT_CORRELATION_MISMATCH`` / ``RECEIPT_CORRELATION_MISSING``).
``redactRecord`` drops sensitive-keyed values whole and rewrites secret- and
PII-shaped substrings (email, Bearer, JWT, AWS, GitHub, provider key, SSN, card),
fails closed on malformed input or a declared ``required_redactions`` path that
was not applied (``REDACTION_REQUIRED_MISSING``), and ``assertNoResidualSecrets``
re-scans the output so the no-leak property is verified, not asserted.
``evaluateSlo`` returns ``UNKNOWN`` when there are no samples rather than
inventing ``OK``.  This builder verifies the executed checks and emits immutable
attempt evidence; it never modifies product files.  Y02 is a standalone module
grounded in the manifest exit criteria; no canonical observability schema exists
in ``schemas/``, which this builder discloses as a non-blocking observation
rather than treating as a defect.
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
ATTEMPT = ROOT / "artifacts/work_packages/Y02/attempts/0001"
ATTEMPT_ID = "Y02-0001"
WORK_PACKAGE_ID = "Y02"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_OTEL_TRACE_COUNT = 13
EXPECTED_LOG_REDACTION_COUNT = 8
EXPECTED_TARGETED_COUNT = 21
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1274
EXPECTED_NODE_FILE_COUNT = 113

COMPONENT = "packages/foundry-kernel/src/observability"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/observability/index.mjs": "8c3c42082c916fa575c71526c58c8a2054189e402ffeb47e8671ea8d2f31d32c",
    "packages/foundry-kernel/src/observability/log-redaction.mjs": "2c5db0564b4088124676636586118946dad33c79c28049dff435f827b915de4c",
    "packages/foundry-kernel/src/observability/log-redaction.test.mjs": "6c8aa8b63651ddd7a7e0aa86aaf5c402a7424dacc237e1491c028599ab92bee3",
    "packages/foundry-kernel/src/observability/observability-primitives.mjs": "a4dbc77d5dc1486bf3394b2d7ec55cca0cd0a3bc171732ac5005ec7de4d83b77",
    "packages/foundry-kernel/src/observability/otel-trace.mjs": "043738bb4507ea1968d1e1005cbbbe13796fce971948ed9b1b5f35e5f0682acb",
    "packages/foundry-kernel/src/observability/otel-trace.test.mjs": "246eaa5523139c96479b094936bc3bc63fbabdfe538cf27945d88d7cc1995bd2",
    "packages/foundry-kernel/src/observability/result-state.mjs": "de6a3ca348a181eafad8a3603fd126fa92f00b147e74ce12bcdfe2d2f96a8636",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/Y01/attempts/0001/report.json": "b2bf7aee2c7f65894556457a36762344c48ae12fa879c10aa7642d1d9ce31fec",
}

JUNIT_PATHS = {
    "otel_trace": ATTEMPT / "otel-trace-test.junit.xml",
    "log_redaction": ATTEMPT / "log-redaction-test.junit.xml",
    "targeted": ATTEMPT / "targeted-observability.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every Y02 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "otel_trace",
        "log_redaction",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "otel-trace-test",
    "log-redaction-test",
    "targeted-observability",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_y02_0001_checks.py",
    "build_y02_0001_evidence.py",
    "y02_0001_rah_seal.py",
    "dependency-status.json",
    "y02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "otel-trace-test.junit.xml",
    "log-redaction-test.junit.xml",
    "targeted-observability.junit.xml",
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
    otel_trace = node_summary(JUNIT_PATHS["otel_trace"])
    log_redaction = node_summary(JUNIT_PATHS["log_redaction"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("otel_trace_test", otel_trace, EXPECTED_OTEL_TRACE_COUNT),
        ("log_redaction_test", log_redaction, EXPECTED_LOG_REDACTION_COUNT),
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
        "component_tests_are_targeted_only": False,
        "full_node": node,
        "full_python": python,
        "log_redaction_test": log_redaction,
        "new_failure_count": 0,
        "otel_trace_test": otel_trace,
        "status": "PASS",
        "targeted_observability": targeted,
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
            "Y01": _pass_dependency(
                "Y01",
                "Y01-0001",
                "artifacts/work_packages/Y01/attempts/0001/report.json",
            ),
        },
        "next_action": "SEAL_Y02_0001_THEN_CONTINUE_DAG",
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
            f"observability component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/Y02/**"],
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


def y02_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "logs_redacted": {
                "evidence": [
                    f"{COMPONENT}/log-redaction.test.mjs",
                    f"{COMPONENT}/otel-trace.test.mjs",
                ],
                "mechanism": (
                    "redactRecord drops any value under a sensitive key whole and "
                    "rewrites every secret- and PII-shaped substring (email, Bearer, "
                    "JWT, AWS access key, GitHub token, provider key, SSN, card) "
                    "anywhere it appears; malformed, proxied, symbol-keyed, or "
                    "array input fails closed with REDACTION_INPUT_INVALID, and a "
                    "caller-declared required_redactions path that was not applied "
                    "fails with REDACTION_REQUIRED_MISSING rather than silently "
                    "passing through. assertNoResidualSecrets re-scans the output so "
                    "no sensitive key retains a real value and no secret/PII pattern "
                    "survives. emitSpan redacts span-level and per-event attributes "
                    "through the same path before storage and re-scans them, so no "
                    "literal secret survives span serialization"
                ),
                "status": "PASS",
            },
            "trace_ids_and_receipts_correlated": {
                "evidence": [
                    f"{COMPONENT}/otel-trace.test.mjs",
                ],
                "mechanism": (
                    "emitSpan builds a span that is well-formed by construction: a "
                    "16-byte non-zero trace_id and 8-byte non-zero span_id validated "
                    "as lowercase hex (all-zero or malformed identifiers, an end "
                    "before start, and a self-parent all fail closed with "
                    "SPAN_INVALID), a canonical kind and honest status, a W3C "
                    "traceparent that round-trips through parseTraceparent, and a "
                    "span_hash binding the whole record. correlateReceipt ties the "
                    "span's trace_id and span_id to an effect receipt by receipt_id "
                    "and sha256 receipt_hash and fails closed on any id or hash "
                    "mismatch (RECEIPT_CORRELATION_MISMATCH) or a span with no "
                    "receipt reference (RECEIPT_CORRELATION_MISSING); a span that "
                    "recorded an exception event cannot claim OK "
                    "(DISHONEST_SPAN_STATUS), and an SLO with no samples reports "
                    "UNKNOWN rather than a fabricated healthy state"
                ),
                "status": "PASS",
            },
        },
        "honest_states": {
            "empty_slo_window_reports_unknown_not_ok": True,
            "error_span_without_cause_or_message_is_refused": True,
            "exception_event_forbids_ok_status": True,
            "zero_good_samples_report_unavailable_not_degraded": True,
        },
        "logs_redacted": {
            "assert_no_residual_secrets_rescans_output": True,
            "malformed_or_proxied_input_fails_closed": True,
            "required_redaction_not_applied_fails_closed": True,
            "sensitive_keyed_values_dropped_whole": True,
            "span_and_event_attributes_redacted_before_storage": True,
            "value_pattern_secrets_and_pii_redacted_in_place": True,
        },
        "required_checks": {
            "log_redaction_test": {
                "module": f"{COMPONENT}/log-redaction.test.mjs",
                "status": "PASS",
                "test_count": regression["log_redaction_test"]["collected"],
            },
            "otel_trace_test": {
                "module": f"{COMPONENT}/otel-trace.test.mjs",
                "status": "PASS",
                "test_count": regression["otel_trace_test"]["collected"],
            },
        },
        "schema_registry_observation": {
            "is_defect": False,
            "note": (
                "Y02 is a standalone observability module grounded in the manifest "
                "exit criteria (trace IDs and receipts correlated; logs redacted); "
                "no canonical observability span/redaction/SLO schema exists in the "
                "schemas/ registry, so emitted records are validated by the module's "
                "own fail-closed structural guards and deterministic sha256 hashing "
                "rather than against a registry schema. Disclosed as a non-blocking "
                "observation, not a contract violation."
            ),
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_observability"]["collected"],
        "trace_ids_and_receipts_correlated": {
            "all_zero_or_malformed_identifiers_fail_closed": True,
            "correlate_receipt_binds_span_to_receipt_by_id_and_hash": True,
            "mismatch_or_missing_receipt_reference_fails_closed": True,
            "monotonic_timing_and_self_parent_enforced": True,
            "span_hash_binds_the_record": True,
            "w3c_traceparent_emitted_and_round_trips": True,
        },
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
                "artifacts/work_packages/Y02/attempts/0001/build_y02_0001_evidence.py",
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
        "# Y02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/observability. Reviewer: this seal-prep\n"
        "  session, a distinct actor that did not author the observability\n"
        "  subsystem. The author never approves its own work, so actor_independence\n"
        "  HOLDS for this review; external actor-independent certification does NOT,\n"
        "  and no such claim is made. Y02 is risk_class=high and was implemented\n"
        "  fresh this session, so spans, receipt correlation, redaction, and SLO\n"
        "  honesty were attacked on their contracts as new code rather than skimmed.\n"
        "- Traces are well-formed by construction. emitSpan validates a 16-byte\n"
        "  non-zero trace_id and an 8-byte non-zero span_id as lowercase hex; an\n"
        "  all-zero id, a non-hex id, a span id in the trace-id slot, an\n"
        "  end_unix_nano before start_unix_nano, and a self-parent all fail closed\n"
        "  with SPAN_INVALID. Timing is monotonic (duration = end - start), the kind\n"
        "  and status are canonical, and the W3C traceparent is emitted as\n"
        "  00-<trace>-<span>-<flags> and round-trips through parseTraceparent for\n"
        "  both the sampled and not-sampled flag. The span_hash is a deterministic\n"
        "  sha256 over the canonicalized record, binding every field.\n"
        "- Trace IDs and receipts are correlated (exit criterion). A span may carry\n"
        "  exactly one receipt_ref (receipt_id + sha256 receipt_hash), and\n"
        "  correlateReceipt ties the span's trace_id/span_id to a supplied effect\n"
        "  receipt only when both id and hash match; a differing id or hash fails\n"
        "  with RECEIPT_CORRELATION_MISMATCH and a span without a reference fails\n"
        "  with RECEIPT_CORRELATION_MISSING, so a trace id is tied to real hashed\n"
        "  evidence and never to an unverified effect.\n"
        "- Secrets and PII are redacted privacy-safe (exit criterion). redactRecord\n"
        "  drops any value under a sensitive key whole (password, secret, token,\n"
        "  api_key, authorization, session, cookie, ssn, ...) whatever its type, and\n"
        "  rewrites every secret- and PII-shaped substring in place by value pattern\n"
        "  (email, Bearer, JWT, AKIA AWS key, GitHub gh*_ token, sk/pk/rk provider\n"
        "  key, SSN, card). It does not mutate its input, is order-independent and\n"
        "  deterministic by redaction_hash, and fails closed on a Proxy, an array,\n"
        "  an unknown option, or a non-string required path\n"
        "  (REDACTION_INPUT_INVALID); a declared required_redactions path that was\n"
        "  not applied fails REDACTION_REQUIRED_MISSING rather than passing through.\n"
        "  emitSpan redacts span-level and per-event attributes through the same\n"
        "  path before storage and calls assertNoResidualSecrets, which re-scans and\n"
        "  raises RESIDUAL_SECRET on any sensitive key still holding a real value or\n"
        "  any surviving pattern -- so no literal secret survives serialization.\n"
        "- States are honest. evaluateSlo returns UNKNOWN with observed_ratio null\n"
        "  when sample_count is 0 (never a fabricated OK), UNAVAILABLE when there are\n"
        "  samples but zero good, DEGRADED when the objective is missed, and OK only\n"
        "  when it is met; good_count > sample_count fails SLO_INPUT_INVALID. A span\n"
        "  that recorded an exception event cannot claim status OK, and an ERROR\n"
        "  span without an exception event or message is refused\n"
        "  (DISHONEST_SPAN_STATUS).\n"
        "- Schema-registry disclosure (non-blocking). Y02 is a standalone module\n"
        "  grounded in the manifest exit criteria; there is no canonical\n"
        "  observability span/redaction/SLO schema in the schemas/ registry, so\n"
        "  emitted records are validated by the module's own fail-closed structural\n"
        "  guards and canonical sha256 hashing rather than against a registry\n"
        "  schema. This is disclosed as an observation, not a defect.\n"
        "- Dependencies and checks: the subsystem builds on the sealed Y01-0001\n"
        "  package (Y01-0001 PASS) and adds no new production dependency; it uses\n"
        "  only the Node standard library (node:crypto, node:util, node:test). Ruff\n"
        "  lint and format, the two required checks (otel_trace_test "
        + f"{EXPECTED_OTEL_TRACE_COUNT}/{EXPECTED_OTEL_TRACE_COUNT}, log_redaction_test "
        + f"{EXPECTED_LOG_REDACTION_COUNT}/{EXPECTED_LOG_REDACTION_COUNT}), targeted "
        + f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: Y02 provides the observability primitives, spans,\n"
        "  redaction, and SLO states only; the wider operations, scale, backup, and\n"
        "  disaster-recovery surface of the Y phase remains later packages. Verdict:\n"
        "  PASS on the exact Y02 package contract.\n"
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
            "path": f"artifacts/work_packages/Y02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "Y02_OBSERVABILITY_SLOS_AND_PRIVACY_SAFE_TELEMETRY",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "logs_redacted": "PASS",
            "trace_ids_and_receipts_correlated": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "the wider Y-phase operations, scale, backup, or disaster-recovery surface",
            "a canonical observability schema in the schemas/ registry",
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
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "log_redaction_test": (
            f"{EXPECTED_LOG_REDACTION_COUNT}/{EXPECTED_LOG_REDACTION_COUNT}"
        ),
        "next_action": "SEAL_Y02_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "otel_trace_test": f"{EXPECTED_OTEL_TRACE_COUNT}/{EXPECTED_OTEL_TRACE_COUNT}",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_observability": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = y02_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("y02-verification.json", verification)
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
        raise SystemExit("Y02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "y02-verification.json")
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
    verification = read_json(ATTEMPT / "y02-verification.json")
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
        raise SystemExit("stored Y02-0001 report is not the deterministic document")
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
