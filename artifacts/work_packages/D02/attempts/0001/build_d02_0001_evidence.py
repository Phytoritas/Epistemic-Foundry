#!/usr/bin/env python3
"""Build and verify D02-0001 evidence: PostgreSQL team store and tenant isolation.

This attempt was implemented by a bounded implementation agent under the product
owner's explicit instruction, with a disjoint write scope
(python/epistemic_foundry/storage/postgres/** and migrations/postgres/**), and
was reviewed by the sealing agent (actor-independent from the author) before
sealing.  The builder verifies every executed check receipt, gates every JUnit
against its measured count, pins product, migration, and dependency bytes, and
emits the deterministic attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/D02/attempts/0001"
ATTEMPT_ID = "D02-0001"
WORK_PACKAGE_ID = "D02"
RECORDED_AT = "2026-08-02T09:45:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/D02/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/D02/attempts/0001/check_packaging.py": "2db517b0ec5fc7d831ed81e5550140f44e96c695baec2b57797cf9211df66df6",
    "artifacts/work_packages/D02/attempts/0001/run_d02_0001_checks.py": "01fc79b637747b7a3fe9b709acac14136ef4c2092218df215c61bd01fd595f78",
    "migrations/postgres/0001_team_store.sql": "21f349f098a03b8e7e2f4a82cef69f5df0fe2e73d88224ab197191260e316682",
    "migrations/postgres/README.md": "5ecaffa635dd57485cfd2396818293e3a55febfcb544dc055f6f2fc5dcf83824",
    "python/epistemic_foundry/storage/postgres/__init__.py": "31c6f062cb222577dcc7075214b846d9f8a3675cfec2a130381d66d87eac9b35",
    "python/epistemic_foundry/storage/postgres/conftest.py": "c0dc0003e1046a8323919bacdaccd798a321dd6c79c81e6bb700f9280c001d45",
    "python/epistemic_foundry/storage/postgres/pytest.ini": "66c104fc7cf9ee25275c59ce534e0ba856e4dc09e1720c6ad8f9d39ff1685af3",
    "python/epistemic_foundry/storage/postgres/store.py": "ce99d637676c7044e8279d0778de94870e6f78946ed4884dbff2a19c2b8b875e",
    "python/epistemic_foundry/storage/postgres/test_postgres_contract.py": "d4dab6fc3bf06c8a82367d1862896e605e82376342e6e867fae9c952e47f875c",
    "python/epistemic_foundry/storage/postgres/test_tenant_isolation.py": "013f69760a94fadf74eb6c0910f6d307de5dbb0bb36fddae39f227febca85882",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/D01/report.json": "00d44672b4c9680589ecd85c39f617c29bdfe79afd288a2769cafb1ba59a9a91",
}

JUNIT_PATHS = {
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "postgres_contract_test": ATTEMPT / "postgres-contract-test.junit.xml",
    "tenant_isolation_test": ATTEMPT / "tenant-isolation-test.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "packaging-discovery",
    "postgres-contract-test",
    "ruff-check",
    "tenant-isolation-test",
    "wire-literal-discipline",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_d02_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "d02-verification.json",
    "d02_0001_rah_seal.py",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "postgres-contract-test.junit.xml",
    "review.md",
    "run_d02_0001_checks.py",
    "tenant-isolation-test.junit.xml",
    "wire-literal-discipline.junit.xml",
    "write-scope-verification.json",
)

# Measured gate counts (observed at seal-prep time on the live tree against the
# ephemeral postgres:16 server).
POSTGRES_CONTRACT_COUNT = 30
TENANT_ISOLATION_COUNT = 13
WIRE_LITERAL_COUNT = 5
FULL_PYTHON_COUNT = 1261
FULL_NODE_COUNT = 1702
NODE_INVENTORY_COUNT = 136


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
    commanded = isinstance(value.get("command"), list) or isinstance(
        value.get("commands"), list
    )
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not commanded
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
    summaries: dict[str, dict[str, Any]] = {}
    for label, summary, expected in (
        (
            "postgres_contract_test",
            pytest_summary(JUNIT_PATHS["postgres_contract_test"]),
            POSTGRES_CONTRACT_COUNT,
        ),
        (
            "tenant_isolation_test",
            pytest_summary(JUNIT_PATHS["tenant_isolation_test"]),
            TENANT_ISOLATION_COUNT,
        ),
        (
            "wire_literal_discipline",
            pytest_summary(JUNIT_PATHS["wire_literal_discipline"]),
            WIRE_LITERAL_COUNT,
        ),
        (
            "full_python_suite",
            pytest_summary(JUNIT_PATHS["full_python_suite"]),
            FULL_PYTHON_COUNT,
        ),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
        summaries[label] = summary
    for label, summary, expected in (
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), FULL_NODE_COUNT),
    ):
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
        summaries[label] = summary

    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if node_inventory.get("count") != NODE_INVENTORY_COUNT:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "new_failure_count": 0,
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(package: str, core: str, final: str) -> dict[str, Any]:
    path = ROOT / f"artifacts/work_packages/{package}/report.json"
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{package} is not the sealed PASS dependency")
    return {
        "attempt_id": str(report.get("attempt_id")),
        "core_evidence_id": core,
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    status: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "D01": _sealed_dependency("D01", "E0016", "E0017"),
        },
        "next_action": "SEAL_D02_0001_THEN_RECOMPUTE_DAG",
        "status": "PASS",
    }
    if AUTHORITY_DECISION is not None:
        decision_path = (
            f"artifacts/authority_decisions/{AUTHORITY_DECISION}.human-decision.json"
        )
        status["authority_decision"] = {
            "decision_id": AUTHORITY_DECISION,
            "path": decision_path,
            "sha256": sha256_id(ROOT / decision_path),
        }
    return status


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    return {
        "approved_scope": [
            "python/epistemic_foundry/storage/postgres/**",
            "migrations/postgres/**",
            "artifacts/work_packages/D02/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
        "authored_by": (
            "bounded implementation agent under the product owner's explicit "
            "instruction"
        ),
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": "sealing agent (actor-independent from the author)",
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    required = {
        "postgres_contract_test": suites["postgres_contract_test"]["collected"],
        "tenant_isolation_test": suites["tenant_isolation_test"]["collected"],
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "contract_metadata": (
                "epistemic_foundry.store_metadata seeds contract_id "
                "'epistemic-foundry-postgres-team-store/v1', schema_version 1, "
                "revision_genesis 0, revision_ceiling 9007199254740991, "
                "identifier_encoding 'utf16be-lowerhex-v1', and the "
                "principal+tenant+workspace+transaction-local isolation policy in "
                "migrations/postgres/0001_team_store.sql, each mirrored by the "
                "adapter constants in "
                "python/epistemic_foundry/storage/postgres/store.py"
            ),
            "finding_codes": (
                "RECORD_NOT_FOUND, RECORD_ALREADY_EXISTS, STALE_REVISION, "
                "REVISION_EXHAUSTED, INVALID_INPUT, INVALID_REVISION, "
                "INVALID_RECORD_VALUE, SCOPE_NOT_AUTHORIZED, "
                "PRIVILEGED_PRINCIPAL_DENIED, POSTGRES_PRINCIPAL_INVALID, "
                "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH, "
                "POSTGRES_PRINCIPAL_ROLE_MEMBERSHIP_DENIED, ROLE_SWITCH_DENIED, "
                "TENANT_CONTEXT_BINDING_FAILED, BOUND_SCOPE_CONTEXT_CHANGED, "
                "ASYNC_TRANSACTION_DENIED, NESTED_TRANSACTION_DENIED, "
                "CONCURRENT_TRANSACTION_ACCESS_DENIED, POSTGRES_WRITER_LOCK_FAILED, "
                "POSTGRES_TRANSACTION_OUTCOME_UNCERTAIN, POSTGRES_INTEGRITY_FAILED, "
                "POSTGRES_RLS_CONFIGURATION_MISMATCH, POSTGRES_RLS_FUNCTION_MISMATCH, "
                "POSTGRES_RLS_POLICY_MISMATCH, POSTGRES_SCHEMA_RELATION_MISMATCH, "
                "POSTGRES_SCHEMA_COLUMN_MISMATCH, POSTGRES_SCHEMA_CONSTRAINT_MISMATCH, "
                "POSTGRES_SCHEMA_INDEX_MISMATCH, POSTGRES_SCHEMA_TRIGGER_MISMATCH, "
                "POSTGRES_SCHEMA_ACL_MISMATCH, POSTGRES_PERSISTED_IDENTIFIER_INVALID, "
                "POSTGRES_PERSISTED_IDENTITY_DUPLICATE, POSTGRES_PERSISTED_JSON_INVALID, "
                "POSTGRES_PERSISTED_REVISION_INVALID, STORE_SAFE_MODE, STORE_CLOSED"
            ),
        },
        "exit_criteria": {
            "team_store_matches_local_semantics": {
                "mechanism": (
                    "the store reuses the D01 logical identity (tenant_id, "
                    "workspace_id, record_type, record_id) with revision genesis "
                    "zero, one atomic compare-and-swap that increments by exactly "
                    "one, stale/duplicate/missing refusals (STALE_REVISION, "
                    "RECORD_ALREADY_EXISTS, RECORD_NOT_FOUND), REVISION_EXHAUSTED "
                    "at the 9007199254740991 ceiling, unbounded JavaScript-string "
                    "identity via the reversible utf16be-lowerhex-v1 projection, "
                    "and PostgreSQL json (not jsonb) with fail-closed integrity "
                    "validation so member order, control characters, and lone "
                    "UTF-16 surrogates round-trip while non-finite numbers such as "
                    "1e400 are rejected"
                ),
                "status": "PASS",
            },
            "tenant_workspace_isolation_enforced": {
                "mechanism": (
                    "revisioned_records carries ENABLE plus FORCE ROW LEVEL "
                    "SECURITY so even the non-superuser table owner is bound; "
                    "access requires the runtime role's administrative "
                    "principal_scopes binding on session_user, the "
                    "transaction-local epistemic_foundry.tenant_id/workspace_id "
                    "GUCs, and scope_is_authorized, so a missing context is "
                    "default-deny and a GUC set for an unauthorized scope raises "
                    "42501/InsufficientPrivilege; the four fixed SECURITY DEFINER "
                    "functions pin search_path=pg_catalog with PUBLIC EXECUTE "
                    "revoked, and superuser/BYPASSRLS principals or privilege, "
                    "column, policy, role-membership and catalog drift enter "
                    "fail-closed SAFE_MODE"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded implementation agent; reviewer: "
                    "the sealing agent, a distinct actor; actor_independence "
                    "between author and reviewer holds, external certification "
                    "does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in required.items()
            },
        },
        "status": "PASS",
        "suite_counts": {name: row["collected"] for name, row in suites.items()},
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        record = {
            "attempt_id": ATTEMPT_ID,
            "exit_code": value["exit_code"],
            "recorded_at_utc": RECORDED_AT,
            "status": value["status"],
            "step": name,
        }
        if "command" in value:
            record["command"] = value["command"]
        else:
            record["commands"] = value["commands"]
        records.append(record)
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                f"{ATTEMPT_DIR}/build_d02_0001_evidence.py",
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
        "# D02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (disjoint write scope over\n"
        "  python/epistemic_foundry/storage/postgres/** and migrations/postgres/**,\n"
        "  frozen contracts) under the product owner's explicit instruction.\n"
        "  Reviewer: the sealing agent, which did not author this attempt;\n"
        "  author/reviewer separation holds with actor_independence=true, while\n"
        "  external actor-independent certification does not.\n"
        "- Team store matches D01 local semantics: the logical identity is\n"
        "  (tenant_id, workspace_id, record_type, record_id); a created record has\n"
        "  revision genesis zero; compare_and_swap_revision increments by exactly\n"
        "  one under the expected-revision guard; a stale expected revision is\n"
        "  refused STALE_REVISION, a duplicate create returns the existing record\n"
        "  (RECORD_ALREADY_EXISTS on the create contract), a missing record is\n"
        "  refused RECORD_NOT_FOUND, and the 9007199254740991 ceiling refuses\n"
        "  REVISION_EXHAUSTED.\n"
        "- JSON and identifier edge values round-trip: PostgreSQL json (not jsonb)\n"
        "  plus adapter integrity validation preserves JSON member order, control\n"
        "  characters, and escaped lone UTF-16 surrogates as values while\n"
        "  fail-closing on semantic non-finite numbers such as 1e400; record_type\n"
        "  and record_id use the reversible utf16be-lowerhex-v1 (u16be:) projection\n"
        "  so NUL, astral characters, lone surrogates, and long strings keep exact\n"
        "  full-text identity under deterministic pg_catalog.\"C\" collation rather\n"
        "  than a length-limited key.\n"
        "- Tenant/workspace isolation is genuinely enforced against real roles:\n"
        "  records are partitioned by tenant_id + workspace_id; access requires the\n"
        "  runtime role's administrative principal_scopes binding on session_user,\n"
        "  the transaction-local epistemic_foundry.tenant_id/workspace_id GUCs, and\n"
        "  scope_is_authorized. Unauthorized scope is denied at open\n"
        "  (SCOPE_NOT_AUTHORIZED); a GUC set for a scope the principal lacks cannot\n"
        "  bypass the binding and raises 42501/InsufficientPrivilege; a missing\n"
        "  context is default-deny; ENABLE plus FORCE ROW LEVEL SECURITY binds even\n"
        "  the non-superuser table owner; superuser/BYPASSRLS principals are\n"
        "  rejected by the adapter; and privilege, column, policy, role-membership,\n"
        "  and catalog drift enter fail-closed SAFE_MODE rather than a permissive\n"
        "  fallback.\n"
        "- Fixed security-definer boundary: four SECURITY DEFINER functions\n"
        "  (scope_is_authorized, acquire_writer_lock, create_revisioned_record,\n"
        "  compare_and_swap_revision) pin search_path=pg_catalog with PUBLIC EXECUTE\n"
        "  revoked; the runtime role has no direct INSERT/UPDATE/DELETE/TRUNCATE on\n"
        "  revisioned_records, so create and update cross the boundary only through\n"
        "  the two fixed functions under forced RLS, mirroring D01's writer\n"
        "  serialization.\n"
        "- Real-server execution, not mocks: conftest.py provisions an ephemeral\n"
        "  database and dedicated NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT\n"
        "  NOBYPASSRLS runtime roles from an administrator DSN read from the\n"
        "  environment, and the fixture refuses a mock-only run. The two required\n"
        "  suites are green against postgres:16 (postgres_contract_test 30/30,\n"
        "  tenant_isolation_test 13/13, 43 targeted). No assertion was weakened or\n"
        "  skipped.\n"
        "- Boundary: the adapter imports the standard library alone and injects no\n"
        "  driver; a caller supplies the PostgreSQL connection factory. D01 is a\n"
        "  manifest-order dependency, not composed code. The component ships under\n"
        "  python/ and stays out of the wheel.\n"
        "- Integration gates at review time: ruff check clean, git diff --check\n"
        "  clean, the two required suites green at 30/30 and 13/13, the EF4-I22\n"
        "  wire-literal gate 5/5, packaging discovery PASS, full Python 1261/1261\n"
        "  and full Node 1702/1702 across the 136-file inventory. Zero blocking\n"
        "  findings.\n"
        "- Preserved observation (non-blocking, outside D02 scope): on the first\n"
        "  full-Node sweep one test in\n"
        "  packages/foundry-kernel/src/artifacts/orphan-receipt.test.mjs\n"
        "  (\"concurrent readers tolerate transient staging and lock handoff\")\n"
        "  flaked once with a Windows EPERM under ARTIFACT_STORE_STRUCTURE_INVALID.\n"
        "  It passed 4/4 in isolation and the full sweep re-ran clean at 1702/1702.\n"
        "  The file is D03 (artifact-store) territory, outside D02's write scope,\n"
        "  and D02 changed no Node-relevant file; the flake is a pre-existing\n"
        "  Windows-concurrency artifact, not a D02 regression, and is recorded here\n"
        "  rather than hidden.\n"
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
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "D02_POSTGRES_TEAM_STORE_AND_TENANT_ISOLATION",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {key: "PASS" for key in verification["exit_criteria"]},
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": True,
        },
        "implementation_status": "PASS",
        "next_package": "RECOMPUTE_DAG",
        "not_claimed": [
            "content-addressed artifact store or receipts: D03 territory; this package provides the PostgreSQL TEAM-profile revisioned-record store and tenant isolation only",
            "scoring, ranking, selection, promotion or evaluation of any candidate",
            "any composed code dependency on D01: it is a manifest-order dependency and the adapter imports the standard library alone with an injected connection factory",
            "external actor-independent certification of this review",
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
                "Author/reviewer separation holds with actor_independence=true "
                "(a bounded implementation agent authored, the sealing agent "
                "reviewed); external actor-independent certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
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
        "next_action": "SEAL_D02_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("d02-verification.json", verification)
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
        raise SystemExit("D02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "d02-verification.json")
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
    verification = read_json(ATTEMPT / "d02-verification.json")
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
        raise SystemExit("stored D02-0001 report is not the deterministic document")
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
