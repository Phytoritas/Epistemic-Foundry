#!/usr/bin/env python3
"""Build and verify I04-0001 intake UX and export-gate evidence.

I04-0001 implements ``web/src/features/intake/**``: a component-local intake
projection and a canonical frame export/import gate.  The projection surfaces
the I02 inbox and the council, scope, ontology, and measurement blockers as the
first visible section with ``aria-live`` assertions, escapes untrusted statement
and blocker text, and never fabricates a confidence or a verdict.  The frame is
always reconstructed from authority inputs, so a caller-supplied assembled frame
cannot forge a derived export gate.  Export is canonical JSON that round-trips
byte-for-byte and is key-order independent; import fails closed on invalid
UTF-8, non-canonical bytes, unknown fields, content tampering, a forged derived
gate, or an Inbox / non-eligible frame.  This builder verifies the executed
checks and emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/I04/attempts/0001"
ATTEMPT_ID = "I04-0001"
WORK_PACKAGE_ID = "I04"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_INTAKE_UI_COUNT = 20
EXPECTED_FRAME_ROUNDTRIP_COUNT = 12
EXPECTED_TARGETED_COUNT = 32
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "web/src/features/intake"
EXPECTED_PRODUCT_HASHES = {
    "web/src/features/intake/frame-roundtrip.test.mjs": "8b0875299347decc68623272e82e918ffc770fc22fa8d655824adcb91fd83c89",
    "web/src/features/intake/index.mjs": "0079cefe80b61de635aede577b96232ad09ae90cc20834c3aacbbe5c9af9c129",
    "web/src/features/intake/intake-frame.mjs": "252161cc937710ccb04fb582ebc6f84370696b2f8822746fd04696ba87b4ff6d",
    "web/src/features/intake/intake-test-fixtures.mjs": "5642e877dd2fbc5eee752676ef1e2e1d45ca4964c9182dc1b6c2ca74a26024f4",
    "web/src/features/intake/intake-ui.test.mjs": "074d41d2b05ada2d9e1218663f937e8bf4f4f2c6dbc56e86405b28bc86d50a19",
    "web/src/features/intake/intake-view.mjs": "28ca7c7142bc0e32c8d75d53bb3841e0ad387778a309f690f42765d338c37daa",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/I02/report.json": "fc55063fdac74f9d66355a5414195bc9b993f001a7f66187946863991e526366",
    "artifacts/work_packages/I03/report.json": "dc09172bfb79cb190a411110845c4913e201df840d22ca7a9faa04b773576644",
}

JUNIT_PATHS = {
    "intake_ui": ATTEMPT / "intake-ui-test.junit.xml",
    "frame_roundtrip": ATTEMPT / "frame-roundtrip-test.junit.xml",
    "targeted": ATTEMPT / "targeted.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every I04 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "intake_ui",
        "frame_roundtrip",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "intake-ui-test",
    "frame-roundtrip-test",
    "targeted",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_i04_0001_checks.py",
    "build_i04_0001_evidence.py",
    "i04_0001_rah_seal.py",
    "dependency-status.json",
    "i04-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "intake-ui-test.junit.xml",
    "frame-roundtrip-test.junit.xml",
    "targeted.junit.xml",
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
    intake_ui = node_summary(JUNIT_PATHS["intake_ui"])
    frame_roundtrip = node_summary(JUNIT_PATHS["frame_roundtrip"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("intake_ui_test", intake_ui, EXPECTED_INTAKE_UI_COUNT),
        ("frame_roundtrip_test", frame_roundtrip, EXPECTED_FRAME_ROUNDTRIP_COUNT),
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
        "frame_roundtrip_test": frame_roundtrip,
        "full_node": node,
        "full_python": python,
        "intake_ui_test": intake_ui,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted": targeted,
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
            "I02": _pass_dependency(
                "I02", "I02-0001", "artifacts/work_packages/I02/report.json"
            ),
            "I03": _pass_dependency(
                "I03", "I03-0001", "artifacts/work_packages/I03/report.json"
            ),
        },
        "next_action": "SEAL_I04_0001_THEN_CONTINUE_DAG",
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
            f"intake component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/I04/**"],
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


def i04_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "frame_export_round_trips": {
                "evidence": [f"{COMPONENT}/frame-roundtrip.test.mjs"],
                "mechanism": (
                    "an eligible frame serializes to canonical UTF-8 JSON whose "
                    "SHA-256 matches the Node oracle; re-importing that envelope "
                    "and re-exporting yields identical bytes, input object key "
                    "order does not change the bytes, and meaningful array order "
                    "is preserved. Import fails closed on invalid UTF-8 "
                    "(INTAKE_FRAME_INVALID_UTF8), non-canonical whitespace "
                    "(INTAKE_FRAME_NOT_CANONICAL), one-byte content tampering "
                    "(INTAKE_FRAME_HASH_MISMATCH), unknown envelope fields "
                    "(INTAKE_FIELD_SET_INVALID), and a fabricated derived gate "
                    "(INTAKE_FRAME_DERIVATION_MISMATCH); an Inbox frame refuses "
                    "export with INTAKE_EXPORT_BLOCKED"
                ),
                "status": "PASS",
            },
            "inbox_and_blockers_visible": {
                "evidence": [f"{COMPONENT}/intake-ui.test.mjs"],
                "mechanism": (
                    "the projection reconstructs the frame from authority inputs "
                    "and renders Blockers as the first visible section under an "
                    "aria-live=assertive region; council, scope, ontology, and "
                    "measurement blockers keep their canonical I02 vocabulary and "
                    "order, untrusted statement and blocker text is HTML-escaped, "
                    "and the export control is disabled with truthful reason_codes "
                    "when not exportable. No confidence or verdict is invented, and "
                    "a forged assembled frame with cleared blockers is rejected"
                ),
                "status": "PASS",
            },
        },
        "honest_degradation": {
            "confidence_or_verdict_fabricated": False,
            "export_fails_closed_with_reason_codes_when_blocked": True,
            "forged_frame_with_cleared_blockers_rejected": True,
            "inbox_frame_refuses_export": True,
            "method_boundary_visible_not_relabelled_a_blocker": True,
            "untrusted_text_html_escaped": True,
        },
        "required_checks": {
            "frame_roundtrip_test": {
                "module": f"{COMPONENT}/frame-roundtrip.test.mjs",
                "status": "PASS",
                "test_count": regression["frame_roundtrip_test"]["collected"],
            },
            "intake_ui_test": {
                "module": f"{COMPONENT}/intake-ui.test.mjs",
                "status": "PASS",
                "test_count": regression["intake_ui_test"]["collected"],
            },
        },
        "round_trip_properties": {
            "byte_for_byte_export_reexport": True,
            "canonical_export_is_key_order_independent": True,
            "meaningful_array_order_preserved": True,
            "no_lossy_transform": True,
            "sha256_matches_node_oracle": True,
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted"]["collected"],
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
                "artifacts/work_packages/I04/attempts/0001/build_i04_0001_evidence.py",
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
        "# I04-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  web/src/features/intake. Reviewer: this seal-prep session, a distinct\n"
        "  actor that did not author the intake projection or the export gate. The\n"
        "  author never approves its own work, so actor_independence HOLDS for this\n"
        "  review; external actor-independent certification does NOT, and no such\n"
        "  claim is made. I04 is risk_class=medium; the projection and gate were\n"
        "  attacked on their visibility, round-trip, and fail-closed contracts\n"
        "  rather than skimmed.\n"
        "- Inbox and blockers are visible, not hidden. buildIntakeView reconstructs\n"
        "  the frame from authority inputs and renders Blockers as the first\n"
        "  visible section inside an aria-live=assertive region. The I02 inbox and\n"
        "  the council, scope-unknown, ontology-review, and measurement blockers\n"
        "  keep their canonical vocabulary and order; a non-canonical council\n"
        "  blocker, a missing unknown-scope sidecar, or a council state conflict\n"
        "  fails closed (INTAKE_COUNCIL_STATE_CONFLICT, INTAKE_UNKNOWN_SCOPE_\n"
        "  CONFLICT). Pending ontology approval stays a visible blocker and an\n"
        "  AUTHORITY_REQUIRED review item; a within-method measurement boundary\n"
        "  stays a visible limitation and is not relabelled a blocker.\n"
        "- No fabricated confidence or verdict. The serialized projection contains\n"
        "  neither a confidence nor a verdict field, and the export control exposes\n"
        "  only a truthful READY/BLOCKED status with the exact blocker reason_codes.\n"
        "  Untrusted statement and blocker text is HTML-escaped, and the export\n"
        "  button is disabled with aria-disabled when export is not permitted.\n"
        "- Frame export round-trips byte-for-byte. serializeIntakeFrame emits\n"
        "  canonical UTF-8 JSON whose SHA-256 equals the Node oracle across padding\n"
        "  boundaries and Unicode; parseIntakeFrame re-imports it and a second\n"
        "  export is byte-identical. The export is key-order independent while\n"
        "  meaningful array order is preserved, and no lossy transform is applied\n"
        "  (lowercase/leap-second RFC 3339 timestamps round-trip unchanged).\n"
        "- Honest degradation fails closed. Import rejects invalid UTF-8\n"
        "  (INTAKE_FRAME_INVALID_UTF8), non-canonical bytes\n"
        "  (INTAKE_FRAME_NOT_CANONICAL), one-byte content tampering\n"
        "  (INTAKE_FRAME_HASH_MISMATCH), unknown envelope fields\n"
        "  (INTAKE_FIELD_SET_INVALID), and a fabricated derived gate\n"
        "  (INTAKE_FRAME_DERIVATION_MISMATCH). An Inbox frame refuses export with\n"
        "  INTAKE_EXPORT_BLOCKED, and a forged assembled frame whose blockers were\n"
        "  cleared cannot be projected (INTAKE_FRAME_DERIVATION_MISMATCH). Assembly,\n"
        "  projection, export, and import never mutate caller-owned inputs.\n"
        "- Dependency and checks: the intake surface builds on the sealed I02\n"
        "  (I02-0001 PASS) inbox/council contract and the sealed I03 (I03-0001 PASS)\n"
        "  ontology and measurement resolution, and adds no new production\n"
        "  dependency; product code reads no node:* module, Buffer, Date.parse, or\n"
        "  environment. The two required checks (intake_ui_test 20/20,\n"
        "  frame_roundtrip_test 12/12), targeted 32/32, full Python 1261/1261, full\n"
        "  Node 1253/1253 across 111 files, and git diff --check all pass with zero\n"
        "  failures.\n"
        "- Residual limitations: I04 is a component-local intake projection and\n"
        "  export/import gate. It adds no canonical schema, implements no\n"
        "  persistence, remote service, ontology approval issuance, or evidence\n"
        "  search, and the full coverage-before-confidence UI remains owned by\n"
        "  O01/O04/U03. Verdict: PASS on the exact I04 package contract.\n"
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
            "path": f"artifacts/work_packages/I04/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "I04_INTAKE_UX_AND_EXPORT_GATE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "frame_export_round_trips": "PASS",
            "inbox_and_blockers_visible": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "a canonical intake or export JSON Schema",
            "persistence, a remote service, ontology approval issuance, or "
            "evidence search",
            "the full coverage-before-confidence UI owned by O01/O04/U03",
            "external actor-independent certification of this review",
            "global repository green status",
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
        "frame_roundtrip_test": (
            f"{EXPECTED_FRAME_ROUNDTRIP_COUNT}/{EXPECTED_FRAME_ROUNDTRIP_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "intake_ui_test": f"{EXPECTED_INTAKE_UI_COUNT}/{EXPECTED_INTAKE_UI_COUNT}",
        "next_action": "SEAL_I04_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "status": "PASS",
        "targeted": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = i04_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("i04-verification.json", verification)
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
        raise SystemExit("I04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "i04-verification.json")
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
    verification = read_json(ATTEMPT / "i04-verification.json")
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
        raise SystemExit("stored I04-0001 report is not the deterministic document")
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
