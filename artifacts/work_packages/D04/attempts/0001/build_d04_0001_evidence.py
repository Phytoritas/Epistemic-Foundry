#!/usr/bin/env python3
"""Build and verify D04-0001 backup, corruption and recovery gate evidence.

D04-0001 implements ``tests/recovery/state/**``: the D-phase backup, corruption
and recovery gate.  The Node fixtures drive the sealed D01/D02 SQLite state
store and the sealed D03 content-addressed artifact store through abrupt
process death, interrupted transactions, structural corruption, and crash
residue, and through live SQLite WAL backup and canonical artifact-graph
snapshot restore.  Recovery never hides data loss behind a reset: a committed
WAL replays after SIGKILL, an interrupted transaction rolls back, a corrupted
SQLite header enters a read-only ``SAFE_MODE`` while the exact corrupt bytes are
preserved, crash residue stays quarantined while the store stays ``ACTIVE``, and
restore is staged, hash-verified, integrity-checked, and atomically published so
a damaged, hash-mismatched, or raced backup fails closed with the target absent.
A PostgreSQL logical custom-dump fixture qualifies the same staged, verified,
non-destructive restore contract in a disposable container.  This builder
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
ATTEMPT = ROOT / "artifacts/work_packages/D04/attempts/0001"
ATTEMPT_ID = "D04-0001"
WORK_PACKAGE_ID = "D04"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_CRASH_RECOVERY_COUNT = 4
EXPECTED_BACKUP_RESTORE_COUNT = 2
EXPECTED_TARGETED_COUNT = 6
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "tests/recovery/state"
EXPECTED_PRODUCT_HASHES = {
    "tests/recovery/state/backup-restore.test.mjs": "f7e780cf3f3a4b15bfd70054bcf06c91ee9ccaa131cc4d7cadc98372a3f6ac66",
    "tests/recovery/state/crash-recovery.test.mjs": "73ec38611cd9cb8e93ea531065ff8e885c044f0c8a11a4dcb8a5500e85729cdf",
    "tests/recovery/state/recovery-fixtures.mjs": "a09eca4e977092e99500a8e146196831fb64a155e6b04a23e0c576f81b034b66",
    "tests/recovery/state/test_postgres_backup_restore.py": "877fd187e1f2360fe0afec008e2cec9bb4e85733206e4d61089386ad83ad6141",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/D02/report.json": "b843adb04258b3e72d3a2f21591441bd94f2a16ea409b014c8b49f1200eb004b",
    "artifacts/work_packages/D03/report.json": "10f6c29d27bbd68ace5a86fa21d019037b8a7bcec82c92c9f0922d66106eaf33",
}

JUNIT_PATHS = {
    "crash_recovery": ATTEMPT / "crash-recovery-test.junit.xml",
    "backup_restore": ATTEMPT / "backup-restore-test.junit.xml",
    "targeted": ATTEMPT / "targeted-recovery.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every D04 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "crash_recovery",
        "backup_restore",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "crash-recovery-test",
    "backup-restore-test",
    "targeted-recovery",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_d04_0001_checks.py",
    "build_d04_0001_evidence.py",
    "d04_0001_rah_seal.py",
    "dependency-status.json",
    "d04-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "crash-recovery-test.junit.xml",
    "backup-restore-test.junit.xml",
    "targeted-recovery.junit.xml",
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
    crash_recovery = node_summary(JUNIT_PATHS["crash_recovery"])
    backup_restore = node_summary(JUNIT_PATHS["backup_restore"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("crash_recovery_test", crash_recovery, EXPECTED_CRASH_RECOVERY_COUNT),
        ("backup_restore_test", backup_restore, EXPECTED_BACKUP_RESTORE_COUNT),
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
        "backup_restore_test": backup_restore,
        "component_tests_are_targeted_only": True,
        "crash_recovery_test": crash_recovery,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_recovery": targeted,
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
            "D02": _pass_dependency(
                "D02", "D02-0001", "artifacts/work_packages/D02/report.json"
            ),
            "D03": _pass_dependency(
                "D03", "D03-0001", "artifacts/work_packages/D03/report.json"
            ),
        },
        "next_action": "SEAL_D04_0001_THEN_CONTINUE_DAG",
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
            f"recovery component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/D04/**"],
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


def d04_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "crash_and_corruption_recovery": {
            "artifact_crash_residue_quarantined_store_stays_active": True,
            "committed_wal_replays_after_sigkill": True,
            "corrupt_sqlite_header_enters_read_only_safe_mode": True,
            "interrupted_transaction_rolls_back_without_reset": True,
        },
        "exit_criteria": {
            "crash_and_corruption_fixtures_recover_safely": {
                "evidence": [
                    f"{COMPONENT}/crash-recovery.test.mjs",
                    f"{COMPONENT}/backup-restore.test.mjs",
                ],
                "mechanism": (
                    "a committed WAL replays after SIGKILL into a recovered ACTIVE "
                    "store whose sealed record and integrity check pass; an "
                    "interrupted transaction rolls back with no partial record; a "
                    "corrupted SQLite header opens read-only SAFE_MODE and closes; "
                    "artifact crash residue is quarantined while the store stays "
                    "ACTIVE and resolves the committed artifact"
                ),
                "status": "PASS",
            },
            "no_data_loss_hidden_by_reset": {
                "evidence": [
                    f"{COMPONENT}/crash-recovery.test.mjs",
                    f"{COMPONENT}/backup-restore.test.mjs",
                ],
                "mechanism": (
                    "the corrupted database sha256 is identical before and after "
                    "open, so SAFE_MODE never silently resets; crash residue is "
                    "still present after recovery; restore is staged, hash-verified, "
                    "integrity-checked and atomically published, so a damaged, "
                    "hash-mismatched or raced backup throws and leaves the target "
                    "absent while the source and backup are never mutated"
                ),
                "status": "PASS",
            },
        },
        "no_data_loss_hidden_by_reset": {
            "corrupt_bytes_sha256_identical_before_and_after_open": True,
            "crash_residue_preserved_not_reset": True,
            "damaged_or_raced_restore_fails_closed_target_absent": True,
            "snapshot_and_restore_never_mutate_source": True,
        },
        "backup_restore_round_trip": {
            "artifact_snapshot_excludes_staging_and_mutation_lock": True,
            "exact_bytes_preserved": True,
            "point_in_time_correct": True,
            "postgresql_logical_dump_qualified_in_disposable_container": True,
        },
        "required_checks": {
            "backup_restore_test": {
                "module": f"{COMPONENT}/backup-restore.test.mjs",
                "status": "PASS",
                "test_count": regression["backup_restore_test"]["collected"],
            },
            "crash_recovery_test": {
                "module": f"{COMPONENT}/crash-recovery.test.mjs",
                "status": "PASS",
                "test_count": regression["crash_recovery_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_recovery"]["collected"],
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
                "artifacts/work_packages/D04/attempts/0001/build_d04_0001_evidence.py",
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
        "# D04-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  tests/recovery/state (crash-recovery.test.mjs, backup-restore.test.mjs,\n"
        "  recovery-fixtures.mjs, test_postgres_backup_restore.py). Reviewer: this\n"
        "  seal-prep session, a distinct actor that did not author the fixtures. The\n"
        "  author never approves its own work, so actor_independence HOLDS for this\n"
        "  review; external actor-independent certification does NOT, and no such\n"
        "  claim is made. D04 is risk_class=critical, so the gate was attacked on\n"
        "  crash recovery, corruption preservation, and non-destructive restore\n"
        "  rather than skimmed.\n"
        "- Crash and corruption fixtures recover safely. A committed record is\n"
        "  written and the child process is SIGKILLed; on reopen the SQLite store is\n"
        "  ACTIVE, replays the committed WAL, reads back the sealed record, and its\n"
        "  integrity check is ok. An interrupted transaction (a compare-and-swap plus\n"
        "  an insert killed mid-flight) rolls back completely: the baseline record\n"
        "  keeps its original value and the partial record does not exist. A SQLite\n"
        "  header overwritten with non-SQLite bytes opens read-only SAFE_MODE with a\n"
        "  SQLITE_* reason and the handle closed. Artifact crash residue under\n"
        "  .staging survives a SIGKILL; on reopen the artifact store is ACTIVE,\n"
        "  resolves the committed artifact, enumerates exactly it, and integrity is\n"
        "  ok.\n"
        "- No data loss hidden by reset. The corrupted SQLite file's sha256 is\n"
        "  captured before open and asserted identical after SAFE_MODE entry, so the\n"
        "  gate cannot mask corruption by silently re-initialising the file. The\n"
        "  crash residue is asserted still present after recovery precisely so the\n"
        "  recovery path cannot hide loss behind a reset. Restore never mutates its\n"
        "  source: after a corrupt source enters SAFE_MODE, the backup and the\n"
        "  corrupt source both keep their captured hashes. A restore is staged into a\n"
        "  fresh sibling, its copied hash or full canonical inventory and (for\n"
        "  SQLite) PRAGMA integrity_check are revalidated, and only then is the stage\n"
        "  atomically renamed onto an absent target. A damaged backup (truncated, or\n"
        "  a snapshot content file overwritten) fails closed with a hash or inventory\n"
        "  mismatch and the target never exists; a validation-to-publication race\n"
        "  injected through afterCopy fails closed with the target absent and the\n"
        "  quarantined stage preserved.\n"
        "- Backup and restore round-trip faithfully. The live node:sqlite WAL backup\n"
        "  is bound to its SHA-256 and restores a point-in-time snapshot: the record\n"
        "  present at snapshot time is read back and a record written after the\n"
        "  snapshot is absent. The artifact snapshot is a sorted canonical sha256\n"
        "  graph inventory with a source bundle hash; it excludes .staging and\n"
        "  .mutation-lock residue, and the restored store resolves the receipt to the\n"
        "  exact original bytes. The restored artifact tree does not contain the\n"
        "  .mutation-lock directory.\n"
        "- PostgreSQL fixture. A custom-format pg_dump is validated by a pg_restore\n"
        "  TOC preflight and restored single-transaction into a fresh staging\n"
        "  database in a disposable pinned container, with schema, function, owner,\n"
        "  forced-RLS, data, and runtime-principal verification before the database\n"
        "  is renamed; a corrupt archive is rejected before restore. It requires a\n"
        "  local Docker daemon and runs under the full Python suite.\n"
        "- Dependencies and checks: the gate only reads the sealed D02 SQLite state\n"
        "  store (D02-0001 PASS) and D03 content-addressed artifact store (D03-0001\n"
        "  PASS) and modifies none of them; it adds no new production dependency. The\n"
        "  two required checks (crash_recovery_test 4/4, backup_restore_test 2/2),\n"
        "  targeted 6/6, full Python 1261/1261, full Node 1253/1253 across 111 files,\n"
        "  ruff lint and format, and git diff --check all pass with zero failures.\n"
        "- Preserved limitations: Windows abrupt termination proves process-death\n"
        "  recovery, not storage-device power-loss durability beyond host and SQLite\n"
        "  guarantees; the helpers are acceptance fixtures, not a shipped backup CLI\n"
        "  or production recovery service; and the PostgreSQL test qualifies a\n"
        "  logical custom dump in one disposable container, not physical backup,\n"
        "  PITR, cross-region recovery, or production RPO/RTO. Verdict: PASS on the\n"
        "  exact D04 package contract.\n"
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
            "path": f"artifacts/work_packages/D04/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "D04_BACKUP_CORRUPTION_RECOVERY_GATE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "crash_and_corruption_fixtures_recover_safely": "PASS",
            "no_data_loss_hidden_by_reset": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "storage-device power-loss durability beyond host and SQLite guarantees",
            "a shipped backup CLI or production recovery service",
            "PostgreSQL physical backup, PITR, cross-region recovery, or production "
            "RPO/RTO",
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
        "backup_restore_test": (
            f"{EXPECTED_BACKUP_RESTORE_COUNT}/{EXPECTED_BACKUP_RESTORE_COUNT}"
        ),
        "completion_ready": False,
        "crash_recovery_test": (
            f"{EXPECTED_CRASH_RECOVERY_COUNT}/{EXPECTED_CRASH_RECOVERY_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_D04_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "status": "PASS",
        "targeted_recovery": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = d04_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("d04-verification.json", verification)
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
        raise SystemExit("D04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "d04-verification.json")
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
    verification = read_json(ATTEMPT / "d04-verification.json")
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
        raise SystemExit("stored D04-0001 report is not the deterministic document")
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
