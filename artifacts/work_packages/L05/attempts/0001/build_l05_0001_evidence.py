#!/usr/bin/env python3
"""Build and verify L05-0001 evolution memory retention evidence.

L05-0001 implements `src/epistemic_foundry/memory/v4_l05/**`: what survives an
actual forget and what an export may carry out of the workspace.  Negative
knowledge cannot be erased for capacity and is reduced at most to a tombstone
that keeps the class, the reason and the hash; an erasure may not strand the
ancestry of anything that remains, enforced to fixpoint; and an export that
keeps results while dropping the negative knowledge beside them is refused as
survivorship bias.  The entry-class vocabulary and its partition come from the
canonical schema and the archive module, and export scope is delegated to the
memory policy's own enforcement point.  This builder verifies the executed
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
ATTEMPT = ROOT / "artifacts/work_packages/L05/attempts/0001"
ATTEMPT_ID = "L05-0001"
WORK_PACKAGE_ID = "L05"
RECORDED_AT = "2026-08-02T10:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/L05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 11
EXPECTED_UNIT_AND_CONTRACT_COUNT = 20
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 29
EXPECTED_PROVENANCE_RECEIPT_COUNT = 12
EXPECTED_TARGETED_COUNT = 72
EXPECTED_DISCIPLINE_COUNT = 5
EXPECTED_MEMORY_REGRESSION_COUNT = 61
EXPECTED_RECALL_REGRESSION_COUNT = 25
EXPECTED_STORE_REGRESSION_COUNT = 84
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1063
EXPECTED_NODE_FILE_COUNT = 95

COMPONENT = "src/epistemic_foundry/memory/v4_l05"
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/L05/attempts/0001/check_packaging.py": "33237c684c648667beccb5d24f216bb5ab28298b3887b4e9298e59660fdf1a3a",
    "artifacts/work_packages/L05/attempts/0001/fixtures.py": "77348df2e1c056927bfcfce06e35c6bae449f2fdae30672b5be801d66559cf71",
    "artifacts/work_packages/L05/attempts/0001/pytest.ini": "1e14bf4860ea6c7eab0f7c532337c5d994fe881de99995872166d396273b516a",
    "artifacts/work_packages/L05/attempts/0001/run_l05_0001_checks.py": "8f785e6f5602f379ddf29fbb93147a94f646e7ff11b32dad1d46d5cf920c1151",
    "artifacts/work_packages/L05/attempts/0001/test_negative_adversarial.py": "03010aaf2131f2300a6e58d22083ea70ef734c53dd450e37975898f430f646d0",
    "artifacts/work_packages/L05/attempts/0001/test_provenance_receipts.py": "bffc66755c9ed552a5e4ec721d0c4774e1ec63b40dd90e6a5734008f4b5f44f2",
    "artifacts/work_packages/L05/attempts/0001/test_schema_and_type.py": "fd99a7305bd539e85c4f55ecc01c04d180c775a184abc7bf221104effbfa41c0",
    "artifacts/work_packages/L05/attempts/0001/test_unit_contract.py": "81f21888f5a9af568479c75ba187f625813fa976a43b744cf30ca80d3d6a2afb",
    "src/epistemic_foundry/memory/v4_l05/__init__.py": "7ea1ce12b7a31516eae1b260c1702e583eaa42985dbdbf26218153e9e3d57fe6",
    "src/epistemic_foundry/memory/v4_l05/retention.py": "4c75b8eac421c92706238dbbc8b1ecdfffd452f1a3e412edfc57e7610c6e1651",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/D05/attempts/0001/report.json": "326a6215067dfc96910aba0ab3c88787115ded36d00eb462d4f5a92f4b732718",
    "artifacts/work_packages/G05/attempts/0001/report.json": "c854b5ec890ed3783c55665fafc02f965ccf3616c2bd4d8071ea8101f12484d0",
    "artifacts/work_packages/L04/attempts/0001/report.json": "35bb257c90665b2351ab3e9e28a769edd3984aed410c608a2d34ef1713a413d5",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-l05-retention.junit.xml",
    "discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
    "memory_regression": ATTEMPT / "dependency-regression-memory.junit.xml",
    "recall_regression": ATTEMPT / "dependency-regression-recall.junit.xml",
    "store_regression": ATTEMPT / "dependency-regression-store.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# L04's recall evaluations are a Node surface, so their regression JUnit
# carries the Node reporter's semantic footer alongside the full Node suite.
_NODE_JUNITS = frozenset({"full_node", "recall_regression"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "wire-literal-discipline",
    "packaging-discovery",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-l05-retention",
    "dependency-regression-memory",
    "dependency-regression-recall",
    "dependency-regression-store",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_l05_0001_checks.py",
    "build_l05_0001_evidence.py",
    "l05_0001_rah_seal.py",
    "check_packaging.py",
    "fixtures.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "l05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-l05-retention.junit.xml",
    "wire-literal-discipline.junit.xml",
    "dependency-regression-memory.junit.xml",
    "dependency-regression-recall.junit.xml",
    "dependency-regression-store.junit.xml",
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
    discipline = pytest_summary(JUNIT_PATHS["discipline"])
    memory = pytest_summary(JUNIT_PATHS["memory_regression"])
    store = pytest_summary(JUNIT_PATHS["store_regression"])
    recall = node_summary(JUNIT_PATHS["recall_regression"])
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
        ("wire_literal_discipline", discipline, EXPECTED_DISCIPLINE_COUNT),
        ("memory_regression", memory, EXPECTED_MEMORY_REGRESSION_COUNT),
        ("store_regression", store, EXPECTED_STORE_REGRESSION_COUNT),
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
    for label, summary, expected in (
        ("recall_regression", recall, EXPECTED_RECALL_REGRESSION_COUNT),
        ("full_node", node, EXPECTED_NODE_COUNT),
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
    if node_inventory.get("count") != EXPECTED_NODE_FILE_COUNT:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "G05-0001",
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "memory_regression": memory,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 1063, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "recall_regression": recall,
        "schema_and_type_check": schema,
        "status": "PASS",
        "store_regression": store,
        "targeted_l05_retention": targeted,
        "unit_and_contract_tests": unit,
        "wire_literal_discipline": discipline,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str
) -> dict[str, Any]:
    path = (
        ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
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
            "D05": _sealed_dependency("D05", "D05-0001", "E0163", "E0164"),
            "L04": _sealed_dependency("L04", "L04-0001", "E0050", "E0051"),
        },
        "next_action": "SEAL_L05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("G05", "G05-0001", "E0169", "E0170"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    declared = sorted(
        relative
        for relative in EXPECTED_PRODUCT_HASHES
        if relative.startswith(f"{COMPONENT}/")
    )
    if component_files != declared:
        raise SystemExit(f"memory package holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "src/epistemic_foundry/memory/v4_l05/**",
            "artifacts/work_packages/L05/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": None,
        "component_files": component_files,
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def l05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_surfaces": {
            "entry_class_partition": (
                "src/epistemic_foundry/epistemic_species_archive/archive.py "
                "PROTECTED_ENTRY_CLASSES/EVICTABLE_ENTRY_CLASSES"
            ),
            "export_scope_enforcement": (
                "src/epistemic_foundry/memory/policy.py require_recall_permitted"
            ),
            "persistence_store": "migrations/v4_d05/0001_evolution_store.sql",
        },
        "declaring_sources": {
            "entry_classes": "schemas/epistemic-archive-entry.schema.json",
            "forget_grounds": (
                "src/epistemic_foundry/memory/v4_l05/retention.py FORGET_GROUNDS "
                "(this module owns the vocabulary)"
            ),
            "lineage_records": "schemas/candidate-lineage.schema.json",
            "memory_policy": "schemas/memory-policy.schema.json",
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "every plan and manifest re-derives its own hash from "
                    "exactly the fields it publishes, binds the policy it acted "
                    "under by digest, keeps in each tombstone the facts that "
                    "outlive the payload, holds no clock of its own, and an "
                    "export binds into the canonical retrieval receipt"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "entry classes are read from the canonical schema and the "
                    "archive partition is verified against it on every use as "
                    "VOCABULARY_DRIFT; the engine source holds no entry-class, "
                    "memory-class or cross-workspace-mode literal; and each of "
                    "the 10 failure codes carries its reason"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "erasure, tombstoning and refusal are each exercised where "
                    "they are correct; a broken or cyclic lineage, a capacity "
                    "erase of any protected class, an erasure that would strand "
                    "surviving ancestry (to fixpoint), an unauthorized forget, "
                    "a survivorship-biased export and every scope violation are "
                    "refused by their own codes"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_negative_adversarial.py"],
                "mechanism": (
                    "a forget requires a recorded authority with a declared "
                    "ground and approver, capacity pressure can never reach "
                    "protected memory regardless of who asks, and export scope "
                    "is delegated to the memory policy's enforcement point so "
                    "nothing routes around consent, class, retention or "
                    "workspace boundaries"
                ),
                "status": "PASS",
            },
        },
        "failure_classes": [
            "CANDIDATE_UNKNOWN",
            "ENTRY_CLASS_UNKNOWN",
            "EXPORT_SCOPE_DENIED",
            "EXPORT_SURVIVORSHIP_BIASED",
            "FORGET_AUTHORITY_MISSING",
            "INPUT_INVALID",
            "LINEAGE_BROKEN",
            "LINEAGE_ORPHANED",
            "PROTECTED_MEMORY_ERASED",
            "VOCABULARY_DRIFT",
        ],
        "implementation_findings": [
            {
                "finding": (
                    "bound-method identity comparison made the lineage cycle "
                    "check unreachable; a self-ancestry was accepted silently"
                ),
                "resolution": (
                    "the walk takes an explicit refuse_origin flag and a cycle "
                    "is refused at construction, proven by a regression test"
                ),
            },
            {
                "finding": (
                    "erasure eligibility was computed against the requested set, "
                    "so erasing an ancestor could strand the lineage record of a "
                    "descendant that ended up tombstoned or refused"
                ),
                "resolution": (
                    "eligibility iterates to fixpoint over what is actually "
                    "erased; the whole-chain forget now stops at the protected "
                    "tombstone and names the retained descendants"
                ),
            },
        ],
        "not_derivable": {
            "external_sync_semantics": (
                "the policy's class rules carry each class's external-sync "
                "disposition and redaction profile; this module records them in "
                "the manifest rather than interpreting them, because the "
                "disposition vocabulary belongs to the policy owner"
            ),
            "physical_erasure": (
                "the plan decides what may be erased; executing the deletion "
                "against the D05 store and emitting its effect receipt belong "
                "to the runtime that owns the transaction"
            ),
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
        "targeted_test_count": regression["targeted_l05_retention"]["collected"],
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
                "artifacts/work_packages/L05/attempts/0001/build_l05_0001_evidence.py",
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
        "# L05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The gap this package closes is real: the archive decides what may\n"
        "  be evicted for capacity and the memory policy decides what may be\n"
        "  recalled, but nothing decided what survives an actual forget or\n"
        "  what an export may carry out. Erasure obligations exist — consent\n"
        "  withdrawal, regulated erasure, workspace purge — so a module that\n"
        "  could only refuse would be as wrong as one that deletes freely.\n"
        "- Two real defects were found by this review before any test was\n"
        "  written against them, and both fixes are proven by regression\n"
        "  tests. First, the lineage cycle check compared bound-method\n"
        "  identity, which is a fresh object on every access, so it never\n"
        "  fired and a self-ancestry passed silently. Second, erasure\n"
        "  eligibility was computed against the requested set rather than the\n"
        "  erased set, so an ancestor could be erased while its descendant\n"
        "  survived as a tombstone whose lineage record then pointed at\n"
        "  nothing. Eligibility now iterates to fixpoint, and the whole-chain\n"
        "  forget stops at the protected tombstone instead of deleting the\n"
        "  ancestry above it.\n"
        "- Negative knowledge has an asymmetric rule and the tests hold it in\n"
        "  both directions: capacity pressure can never erase any of the five\n"
        "  protected classes, while an external obligation may reduce them to\n"
        "  a tombstone that keeps the class, the reason, the hash, the\n"
        "  lineage id and the generation — the facts that outlive the\n"
        "  payload. An export of only negative knowledge is permitted; an\n"
        "  export that keeps results while dropping any negative class beside\n"
        "  them is refused as survivorship bias.\n"
        "- Nothing is restated. Entry classes come from the canonical schema\n"
        "  with the archive partition verified on every use; export scope is\n"
        "  delegated to require_recall_permitted so consent, class, retention\n"
        "  and workspace checks cannot be partially honoured; and the engine\n"
        "  source holds no canonical enum value as a literal, enforced by the\n"
        "  repository's own EF4-I22 gate running as a named check.\n"
        "- The D05 regression ran against real PostgreSQL via the pinned\n"
        "  container image, 84/84, because mock-only store tests are\n"
        "  forbidden in this repository.\n"
        "- Residual limitations: the plan decides, it does not delete — the\n"
        "  transaction against the D05 store and its effect receipt belong to\n"
        "  the runtime; external-sync dispositions are recorded, not\n"
        "  interpreted, because their vocabulary belongs to the policy owner;\n"
        "  and this review is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/L05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "L05_EVOLUTION_MEMORY_RETENTION",
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
        "next_package": "M05-0001",
        "not_claimed": [
            "physical erasure: the plan decides what may be erased; the "
            "deletion against the D05 store and its effect receipt belong to "
            "the runtime that owns the transaction",
            "interpretation of external-sync dispositions, whose vocabulary "
            "belongs to the memory policy owner",
            "any change to the composed archive, policy or capsule modules, "
            "which are read-only inputs",
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
        "next_action": "SEAL_L05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_l05_retention": (
            f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}"
        ),
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
    verification = l05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("l05-verification.json", verification)
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
        raise SystemExit("L05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "l05-verification.json")
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
    verification = read_json(ATTEMPT / "l05-verification.json")
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
        raise SystemExit("stored L05-0001 report is not the deterministic document")
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
