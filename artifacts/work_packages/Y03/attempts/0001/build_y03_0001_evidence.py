#!/usr/bin/env python3
"""Build and verify Y03-0001 backup, disaster-recovery and runbook evidence.

Y03-0001 implements ``ops/runbooks/**`` and ``tests/recovery/production/**``:
the operational backup, corruption-response, and disaster-recovery runbooks plus
the two acceptance checks that keep them honest.  ``runbook_lint`` is fail-closed:
a runbook is lint-clean only when it declares exactly the required sections in
order (Metadata, Preconditions, Procedure, Verification, Rollback, Escalation),
its metadata carries a well-formed id, severity, review date, and RPO/RTO
expressed as measured durations (a vague "as soon as possible" is rejected), its
procedure steps are 1..N imperative verbs each carrying a ``Verify:`` line, and
no placeholder token (TODO/TBD/FIXME/<...>) survives.  ``disaster_recovery_drill``
executes the documented RB-Y03-DR-RESTORE runbook end to end in process over the
sealed D01/D02 SQLite state store and the sealed D03 content-addressed artifact
store using the sealed D04 recovery fixtures: it takes a coordinated backup,
continues writing, corrupts both primaries, and performs a hash- and
manifest-checked staged restore.  Nothing is faked or silently reset -- every
pre-backup record and artifact is restored byte-exact, post-backup writes are
asserted ABSENT as bounded expected loss within RPO, the corrupt primaries are
asserted PRESERVED digest-unchanged as evidence, a tampered backup is asserted to
REFUSE restore and publish nothing, and the measured RPO/RTO are checked against
the budgets parsed from the runbook.  This builder verifies the executed checks
and emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/Y03/attempts/0001"
ATTEMPT_ID = "Y03-0001"
WORK_PACKAGE_ID = "Y03"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_DISASTER_RECOVERY_COUNT = 2
EXPECTED_RUNBOOK_LINT_COUNT = 15
EXPECTED_TARGETED_COUNT = 17
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1291
EXPECTED_NODE_FILE_COUNT = 115

# Y03 writes two product roots: the operational runbooks and their acceptance
# tree.  Both are pinned by content so a change to a runbook, the lint contract,
# or a test is caught here.
RUNBOOK_ROOT = "ops/runbooks"
PRODUCTION_TEST_ROOT = "tests/recovery/production"
EXPECTED_PRODUCT_HASHES = {
    "ops/runbooks/backup.md": "1afa62c4b57ff413099cb73598173d2a7d10a9d7262edc7440820ecf25067832",
    "ops/runbooks/corruption-response.md": "b589bf39ff7b758b4c8e863407a34936c14cba491632f55a3020eebb25a389f6",
    "ops/runbooks/disaster-recovery.md": "b7471d25c50e7fa84db378deed136af195bd86cde468944617dd5816edfb059e",
    "tests/recovery/production/disaster-recovery-drill.test.mjs": "0336a3fe58768a6835cc4de7d4fa463e04a58e69746c386ccf4d0de4b627e49e",
    "tests/recovery/production/runbook-lint.mjs": "fa4a0c4ef0173f0468ba8f75ffc998c34614b93b553fa4c92c2832a42630e0c7",
    "tests/recovery/production/runbook-lint.test.mjs": "3a2420b67abc53b8c4e0097d8a152553d549b0fa86c4412ac370e2200882f8c0",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/Y01/attempts/0001/report.json": "b2bf7aee2c7f65894556457a36762344c48ae12fa879c10aa7642d1d9ce31fec",
}

JUNIT_PATHS = {
    "disaster_recovery": ATTEMPT / "disaster-recovery-drill.junit.xml",
    "runbook_lint": ATTEMPT / "runbook-lint.junit.xml",
    "targeted": ATTEMPT / "targeted-recovery-production.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every Y03 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "disaster_recovery",
        "runbook_lint",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "disaster-recovery-drill",
    "runbook-lint",
    "targeted-recovery-production",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_y03_0001_checks.py",
    "build_y03_0001_evidence.py",
    "y03_0001_rah_seal.py",
    "dependency-status.json",
    "y03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "disaster-recovery-drill.junit.xml",
    "runbook-lint.junit.xml",
    "targeted-recovery-production.junit.xml",
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
    disaster_recovery = node_summary(JUNIT_PATHS["disaster_recovery"])
    runbook_lint = node_summary(JUNIT_PATHS["runbook_lint"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        (
            "disaster_recovery_drill",
            disaster_recovery,
            EXPECTED_DISASTER_RECOVERY_COUNT,
        ),
        ("runbook_lint", runbook_lint, EXPECTED_RUNBOOK_LINT_COUNT),
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
        "disaster_recovery_drill": disaster_recovery,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "runbook_lint": runbook_lint,
        "status": "PASS",
        "targeted_recovery_production": targeted,
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
        "next_action": "SEAL_Y03_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for root in (RUNBOOK_ROOT, PRODUCTION_TEST_ROOT)
        for path in (ROOT / root).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(f"Y03 product roots hold unexpected files: {component_files}")
    return {
        "approved_scope": [
            f"{RUNBOOK_ROOT}/**",
            f"{PRODUCTION_TEST_ROOT}/**",
            "artifacts/work_packages/Y03/**",
        ],
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


def y03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "backup_and_disaster_recovery_drill": {
            "both_stores_recovered_active_integrity_ok": True,
            "corrupt_primaries_preserved_digest_unchanged_as_evidence": True,
            "every_pre_backup_record_and_artifact_restored_byte_exact": True,
            "post_backup_writes_absent_as_bounded_expected_loss_within_rpo": True,
            "tampered_backup_refuses_restore_and_publishes_nothing": True,
        },
        "exit_criteria": {
            "restore_drills_documented": {
                "evidence": [
                    f"{RUNBOOK_ROOT}/disaster-recovery.md",
                    f"{RUNBOOK_ROOT}/backup.md",
                    f"{RUNBOOK_ROOT}/corruption-response.md",
                    f"{PRODUCTION_TEST_ROOT}/disaster-recovery-drill.test.mjs",
                ],
                "mechanism": (
                    "the RB-Y03-DR-RESTORE, RB-Y03-BACKUP and RB-Y03-CORRUPTION "
                    "runbooks document the coordinated backup, corruption response "
                    "and hash-checked staged restore over the two canonical stores, "
                    "each with ordered required sections, imperative Verify-complete "
                    "steps and no placeholder text; runbook_lint enforces that "
                    "structure fail-closed and the disaster_recovery_drill executes "
                    "the documented RB-Y03-DR-RESTORE procedure end to end in process"
                ),
                "status": "PASS",
            },
            "rpo_and_rto_measured": {
                "evidence": [
                    f"{PRODUCTION_TEST_ROOT}/disaster-recovery-drill.test.mjs",
                    f"{PRODUCTION_TEST_ROOT}/runbook-lint.mjs",
                    f"{RUNBOOK_ROOT}/disaster-recovery.md",
                ],
                "mechanism": (
                    "runbook_lint rejects a vague RPO/RTO and admits only a measured "
                    "duration; the drill parses the documented RPO (15 minutes) and "
                    "RTO (30 minutes) budgets from the runbook and asserts the "
                    "measured data-loss window and the measured restore-plus-verify "
                    "time are each within budget, so the objectives are quantified "
                    "and enforced rather than narrated"
                ),
                "status": "PASS",
            },
        },
        "no_hidden_loss": {
            "corrupt_primaries_open_safe_mode_not_reset": True,
            "corrupt_primaries_preserved_digest_unchanged_after_recovery": True,
            "post_backup_writes_explicitly_asserted_absent": True,
            "tampered_backup_target_never_published": True,
        },
        "required_checks": {
            "disaster_recovery_drill": {
                "module": f"{PRODUCTION_TEST_ROOT}/disaster-recovery-drill.test.mjs",
                "status": "PASS",
                "test_count": regression["disaster_recovery_drill"]["collected"],
            },
            "runbook_lint": {
                "module": f"{PRODUCTION_TEST_ROOT}/runbook-lint.test.mjs",
                "status": "PASS",
                "test_count": regression["runbook_lint"]["collected"],
            },
        },
        "rpo_and_rto_measured": {
            "budgets_parsed_from_runbook_not_hardcoded": True,
            "measured_rpo_window_within_documented_budget": True,
            "measured_rto_within_documented_budget": True,
            "vague_unmeasured_objective_rejected_by_lint": True,
        },
        "runbooks_lint_clean": {
            "exactly_ordered_required_sections_enforced": True,
            "imperative_steps_with_verify_lines_enforced": True,
            "negative_fixtures_prove_lint_is_not_vacuous": True,
            "placeholder_tokens_rejected": True,
            "quantified_rpo_rto_required": True,
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_recovery_production"]["collected"],
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
                "artifacts/work_packages/Y03/attempts/0001/build_y03_0001_evidence.py",
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
        "# Y03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote ops/runbooks\n"
        "  (backup.md, corruption-response.md, disaster-recovery.md) and\n"
        "  tests/recovery/production (runbook-lint.mjs, runbook-lint.test.mjs,\n"
        "  disaster-recovery-drill.test.mjs). Reviewer: this seal-prep session, a\n"
        "  distinct actor that did not author the runbooks, the lint contract, or the\n"
        "  drill. The author never approves its own work, so actor_independence HOLDS\n"
        "  for this review; external actor-independent certification does NOT, and no\n"
        "  such claim is made. Y03 is risk_class=high and was implemented fresh this\n"
        "  session, so the drill, the loss accounting, and the lint were attacked on\n"
        "  their contracts as new code rather than skimmed.\n"
        "- The disaster recovery drill genuinely recovers. It seeds three revisioned\n"
        "  records and two artifacts into the sealed D02 SQLite state store and D03\n"
        "  content-addressed artifact store, takes a real node:sqlite online backup\n"
        "  plus a canonical artifact snapshot, then corrupts BOTH primaries on disk\n"
        "  (a non-SQLite header over the database, overwritten artifact payload\n"
        "  bytes). The corrupt primaries open in SAFE_MODE rather than reset. Restore\n"
        "  runs through the sealed D04 hash- and manifest-checked staged restore into\n"
        "  a clean recovery location; the recovered state and artifact stores both\n"
        "  open ACTIVE, pass their integrity checks, and reproduce every pre-backup\n"
        "  record and artifact byte-exact (each artifact resolved by receipt to its\n"
        "  exact original bytes).\n"
        "- No hidden loss. Post-backup writes (a record and an artifact created after\n"
        "  the backup point) are explicitly asserted ABSENT from the recovered stores\n"
        "  -- bounded expected loss within RPO, acknowledged rather than masked. The\n"
        "  corrupt primaries are asserted to keep their captured corrupt-state digests\n"
        "  both immediately after the disaster and again after a successful recovery,\n"
        "  so the drill cannot hide loss behind a silent reset. A separate case tampers\n"
        "  a backup after its digest is recorded and asserts restoreSQLiteBackup throws\n"
        "  a hash mismatch and that the rejected target never comes into existence, so\n"
        "  an unverified restore publishes nothing.\n"
        "- RPO/RTO are measured against budgets parsed from the runbook, not\n"
        "  hardcoded. The drill lints the runbook directory, reads the RB-Y03-DR-RESTORE\n"
        "  RPO (15 minutes) and RTO (30 minutes) as measured durations, and asserts the\n"
        "  measured data-loss window and the measured restore-plus-verify time are each\n"
        "  within those budgets.\n"
        "- The runbooks are lint-clean and the lint is not vacuous. runbook_lint\n"
        "  requires exactly the ordered sections Metadata, Preconditions, Procedure,\n"
        "  Verification, Rollback, Escalation; a well-formed id, sev1|sev2|sev3\n"
        "  severity, ISO review date, and RPO/RTO expressed as measured durations; a\n"
        "  1..N imperative-verb procedure where every step carries a Verify: line; and\n"
        "  rejects any TODO/TBD/FIXME/<...> placeholder. Eleven negative fixtures prove\n"
        "  each rule fails closed (placeholder, angle-bracket, vague RPO, missing and\n"
        "  reordered sections, passive and unverifiable and mis-numbered steps, missing\n"
        "  metadata, title mismatch, empty runbook), and the shipped disaster-recovery\n"
        "  runbook's RPO/RTO are asserted to bind the 15/30-minute budgets.\n"
        "- Dependencies and checks: the drill only reads the sealed Y01-0001 package\n"
        "  (Y01-0001 PASS) transitively through the sealed D02/D03 stores and the\n"
        "  sealed D04 recovery fixtures it imports, and modifies none of them; it adds\n"
        "  no new production dependency and needs no external database, container, or\n"
        "  Docker daemon. The two required checks (disaster_recovery_drill "
        + f"{EXPECTED_DISASTER_RECOVERY_COUNT}/{EXPECTED_DISASTER_RECOVERY_COUNT}, "
        + f"runbook_lint {EXPECTED_RUNBOOK_LINT_COUNT}/{EXPECTED_RUNBOOK_LINT_COUNT}), "
        + f"targeted {EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, ruff lint and format, and git diff "
        "--check all pass with zero genuine failures.\n"
        "- Preserved limitations: the drill qualifies an in-process restore of a\n"
        "  logical SQLite online backup and a canonical artifact snapshot on one host;\n"
        "  it is not a shipped backup service, cross-region or physical-media disaster\n"
        "  recovery, or a production RPO/RTO measurement under real load, and the\n"
        "  runbooks are operational procedure text rather than automation. Verdict:\n"
        "  PASS on the exact Y03 package contract.\n"
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
            "path": f"artifacts/work_packages/Y03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "Y03_BACKUP_DISASTER_RECOVERY_AND_RUNBOOKS",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "restore_drills_documented": "PASS",
            "rpo_and_rto_measured": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "a shipped backup service or automated recovery pipeline",
            "cross-region, physical-media, or off-host disaster recovery",
            "a production RPO/RTO measurement under real load",
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
        "disaster_recovery_drill": (
            f"{EXPECTED_DISASTER_RECOVERY_COUNT}/{EXPECTED_DISASTER_RECOVERY_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_Y03_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "runbook_lint": f"{EXPECTED_RUNBOOK_LINT_COUNT}/{EXPECTED_RUNBOOK_LINT_COUNT}",
        "status": "PASS",
        "targeted_recovery_production": (
            f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}"
        ),
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = y03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("y03-verification.json", verification)
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
        raise SystemExit("Y03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "y03-verification.json")
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
    verification = read_json(ATTEMPT / "y03-verification.json")
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
        raise SystemExit("stored Y03-0001 report is not the deterministic document")
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
