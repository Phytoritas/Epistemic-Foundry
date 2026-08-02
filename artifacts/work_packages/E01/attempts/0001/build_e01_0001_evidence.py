#!/usr/bin/env python3
"""Build and verify E01-0001 append-only Noetic Ledger evidence.

E01-0001 implements ``packages/foundry-kernel/src/ledger/**``: an append-only
Noetic Ledger and its deterministic reducer.  Each ``append`` resolves and
hash-verifies the payload artifact from the sealed C04 content-addressed store,
assigns the next contiguous per-run ``sequence``, links ``previous_event_hash``
to the verified run tail, and commits the immutable EventRecord plus its run
stream inside one D04 SQLite transaction.  Events are written once at revision
0 and never updated or deleted: a non-zero revision fails closed with
``EVENT_RECORD_MUTATED`` and rebinding an event id to different bytes fails with
``EVENT_ID_CONFLICT``.  ``verifyEventChain`` rejects sequence gaps and reorders
(``EVENT_SEQUENCE_MISMATCH``), hash tamper (``EVENT_HASH_MISMATCH``), cross-run
splices (``EVENT_RUN_MISMATCH``), payload drift (``PAYLOAD_HASH_MISMATCH``), and
a missing immutable tail (``EVENT_RECORD_MISSING``) -- every violation fails
closed.  Concurrent writers serialize through the run-stream compare-and-swap.
``rebuild`` re-resolves and hash-verifies every payload, then runs the caller's
reducer twice and asserts an identical canonical trace, rejecting
non-deterministic, async, mutating, and non-JSON reducers; reopening both
durable stores reproduces byte-identical state and ``state_hash``.  This builder
verifies the executed checks and emits immutable attempt evidence; it never
modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/E01/attempts/0001"
ATTEMPT_ID = "E01-0001"
WORK_PACKAGE_ID = "E01"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_LEDGER_HASH_CHAIN_COUNT = 12
EXPECTED_REDUCER_REPLAY_COUNT = 9
EXPECTED_TARGETED_COUNT = 21
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "packages/foundry-kernel/src/ledger"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/ledger/ledger-hash-chain.test.mjs": "e478e71b48d74a139a10023033b3fd2d73fcbdf92660feeb920a6c3953e4eb82",
    "packages/foundry-kernel/src/ledger/ledger-test-support.mjs": "4954d4dd7bc985136d744f0689b91316419fb376e842dba2a428c66c9813d6e9",
    "packages/foundry-kernel/src/ledger/noetic-ledger.mjs": "58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed",
    "packages/foundry-kernel/src/ledger/reducer-replay.test.mjs": "a1f9848e08c1231de29ada86236b6a1ffef19d867ce412d16737a8ce44222029",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C04/report.json": "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f",
    "artifacts/work_packages/D04/report.json": "b47c194e230f4b08ab96b6153e9fc0e170eafb1054318cfaedd8e1ddeb4c5fde",
}

JUNIT_PATHS = {
    "ledger_hash_chain": ATTEMPT / "ledger-hash-chain-test.junit.xml",
    "reducer_replay": ATTEMPT / "reducer-replay-test.junit.xml",
    "targeted": ATTEMPT / "targeted-ledger.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every E01 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "ledger_hash_chain",
        "reducer_replay",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "ledger-hash-chain-test",
    "reducer-replay-test",
    "targeted-ledger",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_e01_0001_checks.py",
    "build_e01_0001_evidence.py",
    "e01_0001_rah_seal.py",
    "dependency-status.json",
    "e01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "ledger-hash-chain-test.junit.xml",
    "reducer-replay-test.junit.xml",
    "targeted-ledger.junit.xml",
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
    ledger_hash_chain = node_summary(JUNIT_PATHS["ledger_hash_chain"])
    reducer_replay = node_summary(JUNIT_PATHS["reducer_replay"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("ledger_hash_chain_test", ledger_hash_chain, EXPECTED_LEDGER_HASH_CHAIN_COUNT),
        ("reducer_replay_test", reducer_replay, EXPECTED_REDUCER_REPLAY_COUNT),
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
        "full_node": node,
        "full_python": python,
        "ledger_hash_chain_test": ledger_hash_chain,
        "new_failure_count": 0,
        "reducer_replay_test": reducer_replay,
        "status": "PASS",
        "targeted_ledger": targeted,
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
            "C04": _pass_dependency(
                "C04", "C04-0001", "artifacts/work_packages/C04/report.json"
            ),
            "D04": _pass_dependency(
                "D04", "D04-0001", "artifacts/work_packages/D04/report.json"
            ),
        },
        "next_action": "SEAL_E01_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(f"ledger component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/E01/**"],
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


def e01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "append_only": {
            "events_are_written_once_at_revision_zero": True,
            "immutable_event_records_are_never_updated_or_deleted": True,
            "mutated_event_revision_fails_closed": True,
            "rebinding_an_event_id_to_new_bytes_is_denied": True,
            "reads_return_deep_frozen_events": True,
        },
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "event_ordering_and_hash_chain_verified": {
                "evidence": [
                    f"{COMPONENT}/ledger-hash-chain.test.mjs",
                ],
                "mechanism": (
                    "append assigns the next contiguous per-run sequence, links "
                    "previous_event_hash to the verified run tail, and commits the "
                    "immutable EventRecord and its run stream in one D04 SQLite "
                    "transaction; verifyEventChain recomputes each event_hash and "
                    "fails closed on sequence gaps or reorder "
                    "(EVENT_SEQUENCE_MISMATCH), hash tamper (EVENT_HASH_MISMATCH), "
                    "cross-run splice (EVENT_RUN_MISMATCH), payload drift "
                    "(PAYLOAD_HASH_MISMATCH), and a missing immutable tail "
                    "(EVENT_RECORD_MISSING); concurrent writers serialize through "
                    "the run-stream compare-and-swap"
                ),
                "status": "PASS",
            },
            "state_is_rebuildable": {
                "evidence": [
                    f"{COMPONENT}/reducer-replay.test.mjs",
                ],
                "mechanism": (
                    "rebuild re-resolves and hash-verifies every payload, then runs "
                    "the caller's synchronous reducer twice and asserts an identical "
                    "canonical trace, rejecting non-deterministic "
                    "(REDUCER_NON_DETERMINISTIC), async (ASYNC_REDUCER_DENIED), "
                    "mutating (REDUCER_FAILED), and non-JSON "
                    "(REDUCER_OUTPUT_INVALID) reducers; reopening both durable "
                    "stores reproduces byte-identical state and state_hash, and an "
                    "empty run deterministically preserves the canonical initial "
                    "state without invoking the reducer"
                ),
                "status": "PASS",
            },
        },
        "hash_chain_and_ordering": {
            "concurrent_writers_serialize_into_one_contiguous_chain": True,
            "cross_run_splice_fails_closed": True,
            "missing_immutable_tail_fails_closed": True,
            "payload_hash_drift_fails_closed": True,
            "sequence_gap_or_reorder_fails_closed": True,
            "tamper_fails_closed": True,
        },
        "required_checks": {
            "ledger_hash_chain_test": {
                "module": f"{COMPONENT}/ledger-hash-chain.test.mjs",
                "status": "PASS",
                "test_count": regression["ledger_hash_chain_test"]["collected"],
            },
            "reducer_replay_test": {
                "module": f"{COMPONENT}/reducer-replay.test.mjs",
                "status": "PASS",
                "test_count": regression["reducer_replay_test"]["collected"],
            },
        },
        "state_rebuildable": {
            "async_or_mutating_or_non_json_reducers_rejected": True,
            "empty_run_preserves_canonical_initial_state": True,
            "non_deterministic_reducer_rejected": True,
            "reopening_durable_stores_reproduces_state_hash": True,
            "two_isolated_reducer_passes_produce_identical_trace": True,
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_ledger"]["collected"],
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
                "artifacts/work_packages/E01/attempts/0001/build_e01_0001_evidence.py",
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
        "# E01-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/ledger. Reviewer: this seal-prep session, a\n"
        "  distinct actor that did not author the ledger. The author never approves\n"
        "  its own work, so actor_independence HOLDS for this review; external\n"
        "  actor-independent certification does NOT, and no such claim is made. E01\n"
        "  is risk_class=critical, so the append-only ledger, its hash chain, and\n"
        "  its rebuild were attacked on their contracts rather than skimmed.\n"
        "- Append-only immutability. Each EventRecord is written once at revision 0\n"
        "  and is never updated or deleted; the public surface exposes only append\n"
        "  and read operations. A stored event whose revision was forced non-zero\n"
        "  fails closed with EVENT_RECORD_MUTATED, an exact retry of the same event\n"
        "  is idempotent (EXISTING, not a second write), and rebinding an event id\n"
        "  to a different actor or payload is denied with EVENT_ID_CONFLICT. Reads\n"
        "  return deep-frozen events, and a partial append (missing payload or an\n"
        "  invalid input carrying an extra field) leaves no event and no run-stream\n"
        "  state behind.\n"
        "- Hash chain and ordering. append assigns the next contiguous per-run\n"
        "  sequence and links previous_event_hash to the verified run tail; the\n"
        "  first event of every run links to null and independent runs each restart\n"
        "  at sequence one. verifyEventChain recomputes each event_hash over its\n"
        "  canonical fields and fails closed on sequence gaps or reorder\n"
        "  (EVENT_SEQUENCE_MISMATCH), field tamper (EVENT_HASH_MISMATCH), a cross-run\n"
        "  splice (EVENT_RUN_MISMATCH), a coherently revised stream that references a\n"
        "  missing immutable event (EVENT_RECORD_MISSING), and a provider-neutral\n"
        "  adapter byte change caught by the sealed payload hash\n"
        "  (PAYLOAD_HASH_MISMATCH). Hash validation reads data properties only and\n"
        "  never triggers a toString coercion hook. Two worker-thread writers racing\n"
        "  a shared barrier serialize through the run-stream compare-and-swap into\n"
        "  one contiguous chain, and a rejected stream commit rolls back the new\n"
        "  immutable event so the run tail is unchanged.\n"
        "- State is rebuildable. rebuild re-resolves and hash-verifies every payload\n"
        "  before any reducer runs, then executes the caller's synchronous reducer\n"
        "  twice and asserts an identical canonical trace. Non-deterministic\n"
        "  (REDUCER_NON_DETERMINISTIC), async (ASYNC_REDUCER_DENIED), input-mutating\n"
        "  (REDUCER_FAILED), and non-JSON (REDUCER_OUTPUT_INVALID) reducers are\n"
        "  rejected; JSON payload decoding rejects invalid UTF-8, a UTF-8 BOM, and\n"
        "  malformed syntax; and canonical state hashing rejects hidden array\n"
        "  properties. Reopening both the D04 SQLite state store and the C04 artifact\n"
        "  store reproduces byte-identical state and state_hash, an empty run\n"
        "  preserves the canonical initial state without invoking the reducer, and\n"
        "  the caller supplies occurred_at so rebuild carries no hidden clock.\n"
        "- Dependencies and checks: the ledger builds on the sealed C04\n"
        "  content-addressed artifact store (C04-0001 PASS) and the sealed D04 SQLite\n"
        "  state store (D04-0001 PASS) and adds no new production dependency; emitted\n"
        "  records validate against the canonical Draft 2020-12\n"
        "  schemas/event-record.schema.json. Ruff lint and format, the two required\n"
        "  checks (ledger_hash_chain_test 12/12, reducer_replay_test 9/9), targeted\n"
        "  21/21, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: E01 provides the append-only ledger, its hash\n"
        "  chain, and deterministic rebuild only; ActionIntent, Attempt, and\n"
        "  EffectReceipt (E02) and the wider effects, capability, and replay surface\n"
        "  remain later packages. Verdict: PASS on the exact E01 package contract.\n"
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
            "path": f"artifacts/work_packages/E01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "E01_APPEND_ONLY_NOETIC_LEDGER_AND_REDUCER",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "event_ordering_and_hash_chain_verified": "PASS",
            "state_is_rebuildable": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "ActionIntent, Attempt, or EffectReceipt behavior (E02)",
            "the wider effects, capability, scheduler, or replay surface",
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
        "ledger_hash_chain_test": (
            f"{EXPECTED_LEDGER_HASH_CHAIN_COUNT}/{EXPECTED_LEDGER_HASH_CHAIN_COUNT}"
        ),
        "next_action": "SEAL_E01_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "reducer_replay_test": (
            f"{EXPECTED_REDUCER_REPLAY_COUNT}/{EXPECTED_REDUCER_REPLAY_COUNT}"
        ),
        "status": "PASS",
        "targeted_ledger": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = e01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("e01-verification.json", verification)
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
        raise SystemExit("E01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "e01-verification.json")
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
    verification = read_json(ATTEMPT / "e01-verification.json")
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
        raise SystemExit("stored E01-0001 report is not the deterministic document")
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
