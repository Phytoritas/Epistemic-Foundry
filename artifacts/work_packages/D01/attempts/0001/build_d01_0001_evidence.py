#!/usr/bin/env python3
"""Build and verify D01-0001 SQLite WAL local canonical store evidence.

D01-0001 implements ``packages/foundry-kernel/src/state/sqlite/**``: a local
canonical state store on SQLite in WAL mode using ``node:sqlite``'s
``DatabaseSync`` (no new production dependency).  It commits revisioned records
inside ``BEGIN IMMEDIATE`` transactions, updates state only through a
compare-and-swap on the expected revision so a stale writer becomes a typed
no-op instead of a silent overwrite, and fails closed into a read-only
``SAFE_MODE`` on any integrity violation.  This builder verifies the executed
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
ATTEMPT = ROOT / "artifacts/work_packages/D01/attempts/0001"
ATTEMPT_ID = "D01-0001"
WORK_PACKAGE_ID = "D01"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_SQLITE_WAL_COUNT = 19
EXPECTED_CONCURRENT_REVISION_COUNT = 2
EXPECTED_INTEGRITY_SAFE_MODE_COUNT = 16
EXPECTED_TARGETED_COUNT = 37
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "packages/foundry-kernel/src/state/sqlite"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/state/sqlite/concurrent-revision.test.mjs": "3df6754b227d32fdfad8c6bc4e7352634fc847bad8ffbe3ffceb030441688bbb",
    "packages/foundry-kernel/src/state/sqlite/integrity-safe-mode.test.mjs": "9b6d31b8fb45b17183d3d8a9fe9a3d72d70e047a17f01fd31b2ea516407ac37f",
    "packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs": "6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380",
    "packages/foundry-kernel/src/state/sqlite/sqlite-wal.test.mjs": "e9d17526d229edf4e9369cfffd1834bdb9ff761a264f4aa4605edc3d8f3d2bfc",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/B04/attempts/0002/report.json": "a75e724b453bf58ce2745af174e96d7f08616bd09467e3b047b78f31b8add643",
    "artifacts/work_packages/C04/report.json": "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f",
}

JUNIT_PATHS = {
    "sqlite_wal": ATTEMPT / "sqlite-wal-test.junit.xml",
    "concurrent_revision": ATTEMPT / "concurrent-revision-test.junit.xml",
    "integrity_safe_mode": ATTEMPT / "integrity-safe-mode-test.junit.xml",
    "targeted": ATTEMPT / "targeted-sqlite.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every D01 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "concurrent_revision",
        "full_node",
        "integrity_safe_mode",
        "sqlite_wal",
        "targeted",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "sqlite-wal-test",
    "concurrent-revision-test",
    "integrity-safe-mode-test",
    "targeted-sqlite",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_d01_0001_checks.py",
    "build_d01_0001_evidence.py",
    "d01_0001_rah_seal.py",
    "dependency-status.json",
    "d01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "sqlite-wal-test.junit.xml",
    "concurrent-revision-test.junit.xml",
    "integrity-safe-mode-test.junit.xml",
    "targeted-sqlite.junit.xml",
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
    sqlite_wal = node_summary(JUNIT_PATHS["sqlite_wal"])
    concurrent = node_summary(JUNIT_PATHS["concurrent_revision"])
    integrity = node_summary(JUNIT_PATHS["integrity_safe_mode"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("sqlite_wal_test", sqlite_wal, EXPECTED_SQLITE_WAL_COUNT),
        ("concurrent_revision_test", concurrent, EXPECTED_CONCURRENT_REVISION_COUNT),
        ("integrity_safe_mode_test", integrity, EXPECTED_INTEGRITY_SAFE_MODE_COUNT),
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
        "concurrent_revision_test": concurrent,
        "full_node": node,
        "full_python": python,
        "integrity_safe_mode_test": integrity,
        "new_failure_count": 0,
        "sqlite_wal_test": sqlite_wal,
        "status": "PASS",
        "targeted_sqlite": targeted,
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
            "B04": _pass_dependency(
                "B04",
                "B04-0002",
                "artifacts/work_packages/B04/attempts/0002/report.json",
            ),
            "C04": _pass_dependency(
                "C04", "C04-0001", "artifacts/work_packages/C04/report.json"
            ),
        },
        "next_action": "SEAL_D01_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(f"sqlite component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/D01/**"],
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


def d01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "additional_coverage": {
            "integrity_safe_mode_test": {
                "module": f"{COMPONENT}/integrity-safe-mode.test.mjs",
                "status": "PASS",
                "test_count": regression["integrity_safe_mode_test"]["collected"],
            },
        },
        "attempt_id": ATTEMPT_ID,
        "compare_and_swap": {
            "stale_expected_revision_is_typed_no_op": True,
            "stale_writer_never_overwrites_state": True,
            "revision_exhaustion_refused_without_mutation": True,
        },
        "exit_criteria": {
            "integrity_failure_enters_SAFE_MODE": {
                "evidence": [f"{COMPONENT}/integrity-safe-mode.test.mjs"],
                "mechanism": (
                    "physical corruption, schema drift, invalid persisted JSON, "
                    "and runtime revision or schema-version drift all fail closed "
                    "into a read-only SAFE_MODE that denies every mutation path"
                ),
                "status": "PASS",
            },
            "transactions_and_compare_and_swap_revisions_implemented": {
                "evidence": [
                    f"{COMPONENT}/sqlite-wal.test.mjs",
                    f"{COMPONENT}/concurrent-revision.test.mjs",
                ],
                "mechanism": (
                    "records commit inside BEGIN IMMEDIATE transactions in WAL "
                    "mode and survive reopen; a callback failure rolls back every "
                    "partial write; state advances only through a compare-and-swap "
                    "on the expected revision so a stale writer is a typed no-op"
                ),
                "status": "PASS",
            },
        },
        "integrity_failure_mode": {
            "safe_mode_is_read_only": True,
            "safe_mode_refuses_all_mutation_paths": True,
        },
        "required_checks": {
            "concurrent_revision_test": {
                "module": f"{COMPONENT}/concurrent-revision.test.mjs",
                "status": "PASS",
                "test_count": regression["concurrent_revision_test"]["collected"],
            },
            "sqlite_wal_test": {
                "module": f"{COMPONENT}/sqlite-wal.test.mjs",
                "status": "PASS",
                "test_count": regression["sqlite_wal_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_sqlite"]["collected"],
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
                "artifacts/work_packages/D01/attempts/0001/build_d01_0001_evidence.py",
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
        "# D01-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/state/sqlite. Reviewer: this seal-prep\n"
        "  session, a distinct actor that did not author the store. The author\n"
        "  never approves its own work, so actor_independence HOLDS for this\n"
        "  review; external actor-independent certification does NOT, and no such\n"
        "  claim is made. D01 is risk_class=critical, so the store was attacked\n"
        "  thoroughly rather than skimmed.\n"
        "- WAL durability and transactions. The store opens the database in\n"
        "  SQLite WAL journal mode through node:sqlite DatabaseSync and commits\n"
        "  every revisioned record inside a BEGIN IMMEDIATE transaction.\n"
        "  Committed state survives a close and reopen, and a transaction whose\n"
        "  callback throws rolls back every partial write; when both the\n"
        "  operation and its rollback fail the store refuses to report an\n"
        "  ordinary failure and enters SAFE_MODE with an uncertain-outcome code.\n"
        "- Compare-and-swap revisions. State advances only when the caller's\n"
        "  expected revision matches the persisted revision. Two worker-thread\n"
        "  writers that present the same expected revision produce exactly one\n"
        "  update and one typed stale no-op; the stale writer never overwrites\n"
        "  the record it did not observe. One hundred contention repetitions and\n"
        "  one hundred concurrent first-open repetitions converge deterministically,\n"
        "  and revision exhaustion is refused without changing the record. A\n"
        "  stale compare-and-swap fails as data, not as a silent last-writer-wins\n"
        "  overwrite.\n"
        "- Integrity failure enters SAFE_MODE. Physical corruption, structural\n"
        "  schema drift, invalid persisted JSON, and runtime revision or\n"
        "  schema-version drift each fail closed. Once SAFE_MODE is entered the\n"
        "  store is read-only and every mutation path is denied; hostile\n"
        "  JavaScript values and Promise/thenable transaction callbacks are\n"
        "  rejected without granting execution or leaving partial state. The\n"
        "  failure mode is refusal, never a best-effort write.\n"
        "- No new production dependency: the store uses the runtime's built-in\n"
        "  node:sqlite. Ruff lint and format, the two required checks\n"
        "  (sqlite_wal_test 19/19, concurrent_revision_test 2/2), the extra\n"
        "  integrity-safe-mode coverage 16/16, targeted 37/37, full Python\n"
        "  1261/1261, full Node 1253/1253 across 111 files, and git diff --check\n"
        "  all pass with zero failures.\n"
        "- Residual limitations: WAL busy retry is exercised indirectly by\n"
        "  concurrent opens but has no deterministic retry-count assertion, and\n"
        "  checkIntegrity() has an ordinary linearization point that the next\n"
        "  store operation detects. Broader recovery lifecycle belongs to a later\n"
        "  package. Verdict: PASS on the exact D01 package contract.\n"
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
            "path": f"artifacts/work_packages/D01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "D01_SQLITE_WAL_LOCAL_CANONICAL_STORE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "integrity_failure_enters_SAFE_MODE": "PASS",
            "transactions_and_compare_and_swap_revisions_implemented": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "a deterministic WAL busy-retry count or deadline assertion",
            "recovery lifecycle beyond fail-closed SAFE_MODE entry",
            "the team PostgreSQL store or tenant isolation",
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
        "concurrent_revision_test": (
            f"{EXPECTED_CONCURRENT_REVISION_COUNT}/{EXPECTED_CONCURRENT_REVISION_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "integrity_safe_mode_test": (
            f"{EXPECTED_INTEGRITY_SAFE_MODE_COUNT}/{EXPECTED_INTEGRITY_SAFE_MODE_COUNT}"
        ),
        "next_action": "SEAL_D01_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "sqlite_wal_test": f"{EXPECTED_SQLITE_WAL_COUNT}/{EXPECTED_SQLITE_WAL_COUNT}",
        "status": "PASS",
        "targeted_sqlite": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = d01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("d01-verification.json", verification)
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
        raise SystemExit("D01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "d01-verification.json")
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
    verification = read_json(ATTEMPT / "d01-verification.json")
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
        raise SystemExit("stored D01-0001 report is not the deterministic document")
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
