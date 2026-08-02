#!/usr/bin/env python3
"""Build and verify D05-0001 evolution transactional store evidence.

D05-0001 implements `migrations/v4_d05/**`: the PostgreSQL store behind
candidate lineage, the quality-diversity archive, islands and atomic
checkpoints.  Its two governing invariants are enforced by the database
rather than by its callers — a checkpoint carries all seven bindings or is
not written (EF4-I61), and a protected archive entry cannot be evicted for
low fitness through any path the runtime holds (EF4-I49).  Every check runs
against a real server in the image the sealed D04 gate qualified; mock-only
PostgreSQL tests are forbidden.  This builder verifies the executed checks
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
ATTEMPT = ROOT / "artifacts/work_packages/D05/attempts/0001"
ATTEMPT_ID = "D05-0001"
WORK_PACKAGE_ID = "D05"
RECORDED_AT = "2026-08-02T02:30:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/D05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 21
EXPECTED_UNIT_AND_CONTRACT_COUNT = 13
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 39
EXPECTED_PROVENANCE_RECEIPT_COUNT = 11
EXPECTED_TARGETED_COUNT = 84
EXPECTED_MIGRATION_APPLY_COUNT = 21
EXPECTED_C05_REGRESSION_COUNT = 132
EXPECTED_RECOVERY_REGRESSION_COUNT = 1
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "migrations/v4_d05"
#: The pinned server image; a PASS recorded against anything else would not
#: be a PASS for this store.
POSTGRES_IMAGE = (
    "pgvector/pgvector@sha256:"
    "7d400e340efb42f4d8c9c12c6427adb253f726881a9985d2a471bf0eed824dff"
)
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/D05/attempts/0001/conftest.py": "b037a80c51b29c40096790a878de95cb5632065d1f6c5d81db8209bc2bf6c3c0",
    "artifacts/work_packages/D05/attempts/0001/pg_harness.py": "08de73b327ca9b8d4e468d8366e5c9571a79d97e808f13d994bcaeba9c1fd9c5",
    "artifacts/work_packages/D05/attempts/0001/pytest.ini": "d5acf2299b7e7eb1fab4f35f316a0cd4184a988a7a008501d178a5a279ea610e",
    "artifacts/work_packages/D05/attempts/0001/test_negative_adversarial.py": "4d9e4553d2404ea945f13b515bd8be0e0f0dc47cea444c2fc1e0486f3cd3db7d",
    "artifacts/work_packages/D05/attempts/0001/test_provenance_receipts.py": "b24e6a68e27e270ce8fa034e6bbe20fae5b9e8d1cc625ba4d062b91d3315ae29",
    "artifacts/work_packages/D05/attempts/0001/test_schema_and_type.py": "d69d199a8afcb38c675db08e7f31411e60e5ad220d9a78a943e225fd9ce0ab84",
    "artifacts/work_packages/D05/attempts/0001/test_unit_contract.py": "70eb99450e3ae7299254c4ea13e64346db6fe59e7e59065d662eadfe99d75c50",
    "migrations/v4_d05/0001_evolution_store.sql": "775d593b1818129f1bf929de89c8006a79af0458b798bc7f411ca75844d50f63",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/A06/attempts/0002/report.json": "a45eff5d49f16c5307ce886ccfcd8dabd742b3c95efd1898d51fc71b0de80425",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/C06/attempts/0001/report.json": "cc5a900acf1a266d85387fc63c7f065fa8a547e7b613e89d3d45883c31aa1661",
    "artifacts/work_packages/D04/report.json": "b47c194e230f4b08ab96b6153e9fc0e170eafb1054318cfaedd8e1ddeb4c5fde",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-d05-store.junit.xml",
    "migration_apply": ATTEMPT / "migration-apply.junit.xml",
    "c05_regression": ATTEMPT / "dependency-regression-c05.junit.xml",
    "recovery_regression": ATTEMPT / "dependency-regression-recovery.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every D05 dependency check is a Python surface, so only the full Node
# suite carries the Node reporter's semantic footer.
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "store-preflight",
    "migration-apply",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-d05-store",
    "dependency-regression-c05",
    "dependency-regression-recovery",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_d05_0001_checks.py",
    "build_d05_0001_evidence.py",
    "d05_0001_rah_seal.py",
    "pg_harness.py",
    "conftest.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "d05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-d05-store.junit.xml",
    "migration-apply.junit.xml",
    "dependency-regression-c05.junit.xml",
    "dependency-regression-recovery.junit.xml",
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


def regression_evidence() -> dict[str, Any]:
    schema = pytest_summary(JUNIT_PATHS["schema_and_type"])
    unit = pytest_summary(JUNIT_PATHS["unit_and_contract"])
    negative = pytest_summary(JUNIT_PATHS["negative_adversarial"])
    provenance = pytest_summary(JUNIT_PATHS["provenance_receipt"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    migration = pytest_summary(JUNIT_PATHS["migration_apply"])
    c05 = pytest_summary(JUNIT_PATHS["c05_regression"])
    recovery = pytest_summary(JUNIT_PATHS["recovery_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("schema_and_type_check", schema, EXPECTED_SCHEMA_AND_TYPE_COUNT),
        ("unit_and_contract_tests", unit, EXPECTED_UNIT_AND_CONTRACT_COUNT),
        (
            "negative_and_adversarial_tests",
            negative,
            EXPECTED_NEGATIVE_ADVERSARIAL_COUNT,
        ),
        (
            "provenance_and_receipt_audit",
            provenance,
            EXPECTED_PROVENANCE_RECEIPT_COUNT,
        ),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("migration_apply", migration, EXPECTED_MIGRATION_APPLY_COUNT),
        ("c05_regression", c05, EXPECTED_C05_REGRESSION_COUNT),
        (
            "recovery_regression",
            recovery,
            EXPECTED_RECOVERY_REGRESSION_COUNT,
        ),
        ("full_python", python, EXPECTED_PYTHON_COUNT),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
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
        "baseline_attempt": "C06-0001",
        "c05_regression": c05,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "migration_apply": migration,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "postgres_image": POSTGRES_IMAGE,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "recovery_regression": recovery,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_d05_store": targeted,
        "unit_and_contract_tests": unit,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str, *, flat: bool = False
) -> dict[str, Any]:
    path = ROOT / (
        f"artifacts/work_packages/{package}/report.json"
        if flat
        else f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
    )
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "core_evidence_id": core,
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "A06": _sealed_dependency("A06", "A06-0002", "E0119", "E0120"),
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
            # D04 predates the attempts/ layout and keeps its report at the
            # package root; citing the wrong path would silently unbind it.
            "D04": _sealed_dependency("D04", "D04-0001", "E0022", "E0023", flat=True),
        },
        "next_action": "SEAL_D05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("C06", "C06-0001", "E0161", "E0162"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file()
    )
    declared = sorted(
        relative
        for relative in EXPECTED_PRODUCT_HASHES
        if relative.startswith(f"{COMPONENT}/")
    )
    if component_files != declared:
        raise SystemExit(f"migration holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "migrations/v4_d05/**",
            "artifacts/work_packages/D05/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "component_files": component_files,
        "existing_migrations_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def d05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "checkpoint_bindings": "EF4-I61 (MASTER_SPEC)",
            "postgres_image": POSTGRES_IMAGE,
            "protection_reasons": "EF4-I49 (MASTER_SPEC)",
        },
        "enforcement": {
            "append_only_tables": [
                "archive_entries",
                "candidate_lineage",
                "evolution_checkpoints",
                "evolution_runs",
            ],
            "checkpoint_bindings": 7,
            "mock_postgres_used": False,
            "protection_reasons": 5,
            "runtime_delete_privilege": False,
            "runtime_privileges": ["INSERT", "SELECT"],
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "every hash column is a checked sha256 domain rather than "
                    "free text, an eviction records when and why, a rolled-back "
                    "or failed seal leaves nothing behind, and an evicted "
                    "archive row stays in place as evidence rather than being "
                    "deleted"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "the assertions are PostgreSQL's own catalog answers after "
                    "the migration ran: the nine tables, the seven NOT NULL "
                    "checkpoint bindings, the sha256 and identifier domains "
                    "under deterministic C collation, the five append-only and "
                    "evaluator guards, and the two SECURITY DEFINER entry "
                    "points"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "lineage resolves to its root, islands specialise, the "
                    "archive keeps whole niches, and a checkpoint seals in one "
                    "statement; every attack is executed as the runtime "
                    "principal against the real server, including a rolled-back "
                    "seal that must leave no resume point at all"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_negative_adversarial.py"],
                "mechanism": (
                    "a checkpoint may bind only the evaluator its run was "
                    "opened with, so a resume point cannot swap the evaluator "
                    "(EF4-I43); a run row cannot be rewritten; and a protected "
                    "archive entry cannot be evicted for low fitness through "
                    "the function, a direct UPDATE, or a DELETE the runtime "
                    "does not hold (EF4-I49)"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": "review.md (primary-session separate, "
                "actor_independence=false)",
                "status": "PASS",
            },
            "negative_and_adversarial_tests": {
                "module": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                "status": "PASS",
                "test_count": regression["negative_and_adversarial_tests"]["collected"],
            },
            "provenance_and_receipt_audit": {
                "module": f"{ATTEMPT_DIR}/test_provenance_receipts.py",
                "status": "PASS",
                "test_count": regression["provenance_and_receipt_audit"]["collected"],
            },
            "schema_and_type_check": {
                "module": f"{ATTEMPT_DIR}/test_schema_and_type.py",
                "status": "PASS",
                "test_count": regression["schema_and_type_check"]["collected"],
            },
            "unit_and_contract_tests": {
                "module": f"{ATTEMPT_DIR}/test_unit_contract.py",
                "status": "PASS",
                "test_count": regression["unit_and_contract_tests"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_d05_store"]["collected"],
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
                "artifacts/work_packages/D05/attempts/0001/build_d05_0001_evidence.py",
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
        "# D05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Nothing here is mocked. The repository already forbids mock-only\n"
        "  PostgreSQL tests, so the suite applies the migration to a real\n"
        "  server in the image the sealed D04 gate qualified, and the\n"
        "  store-preflight check fails closed when the daemon or that image is\n"
        "  unavailable rather than passing against a substitute.\n"
        "- The two invariants are enforced by the database, not by its callers.\n"
        "  A checkpoint carries all seven bindings NOT NULL, so a partially\n"
        "  bound resume point cannot be written; the parametrised test omits\n"
        "  each binding in turn and the server refuses every one. A protected\n"
        "  archive entry cannot be evicted for low fitness through the eviction\n"
        "  function, through a direct UPDATE, or through a DELETE, because the\n"
        "  runtime holds only SELECT and INSERT and the append-only guard stops\n"
        "  even a superuser DELETE.\n"
        "- The tests found a real defect in the migration. The first draft used\n"
        "  the IEEE self-comparison idiom to reject NaN scores, but PostgreSQL\n"
        "  defines NaN = NaN as true and sorts NaN above every finite value, so\n"
        "  a NaN combined score was accepted. The constraint now uses the\n"
        "  inequality, which is false for NaN, and the test that caught it\n"
        "  stays. A migration reviewed only by reading would have shipped this.\n"
        "- The adversarial suite runs as the runtime principal, not as a\n"
        "  superuser, so a refusal is the refusal the deployment would actually\n"
        "  get. Where a superuser could still act, that is tested separately\n"
        "  and the trigger catches it.\n"
        "- Crash safety is proved by rolling back mid-transaction: a sealed but\n"
        "  uncommitted checkpoint leaves no resume point, and a committed one\n"
        "  reads back with every binding intact.\n"
        "- A combined score may be recorded but may not decide protection\n"
        "  (EF4-I45): protection is a stored property with its own reason\n"
        "  vocabulary, and stripping it to enable an eviction is refused as an\n"
        "  immutability violation.\n"
        "- Residual limitations: this is the schema and its guarantees, not a\n"
        "  deployed database — provisioning, connection management and the\n"
        "  runtime adapter belong elsewhere; row-level security is not applied\n"
        "  here because the store is single-tenant per deployment, unlike the\n"
        "  D02 team store; performance under load is unmeasured; and this\n"
        "  review is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/D05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "D05_EVOLUTION_TRANSACTIONAL_STORE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": (
                "PASS"
            ),
            "governing_schemas_authority_boundaries_failure_states_exact": "PASS",
            "happy_negative_crash_resume_adversarial_coverage": "PASS",
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": ("PASS"),
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "E05-0001",
        "not_claimed": [
            "a deployed database: provisioning, connection management and the "
            "runtime adapter are outside this migration",
            "row-level security, which the single-tenant evolution store does "
            "not apply and the D02 team store owns for multi-tenant data",
            "performance or capacity under load, which is unmeasured here",
            "any change to the existing migrations, which are untouched",
            "actor-independent certification of this implementation review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": False,
            "assurance_limitation": (
                "Primary-session separate review; not external actor-independent "
                "certification."
            ),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
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
        "negative_and_adversarial_tests": (
            f"{EXPECTED_NEGATIVE_ADVERSARIAL_COUNT}/"
            f"{EXPECTED_NEGATIVE_ADVERSARIAL_COUNT}"
        ),
        "next_action": "SEAL_D05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_d05_store": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
        "unit_and_contract_tests": (
            f"{EXPECTED_UNIT_AND_CONTRACT_COUNT}/{EXPECTED_UNIT_AND_CONTRACT_COUNT}"
        ),
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = d05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("d05-verification.json", verification)
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
        raise SystemExit("D05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "d05-verification.json")
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
    verification = read_json(ATTEMPT / "d05-verification.json")
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
        raise SystemExit("stored Q01-0001 report is not the deterministic document")
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
