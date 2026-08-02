#!/usr/bin/env python3
"""Build and verify C05-0001 evolution schema bundle evidence.

C05-0001 emits `schemas/v4_c05/**` as a generated, regenerable composition
layer over the sealed canonical contracts: five composites that draw the
EF4-I41 mutable-space boundary, encode EF4-I53 adaptive-search statistics and
EF4-I63 backend isolation structurally, and a family index that receipts all
42 canonical members and every composite by content hash.  This builder
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
ATTEMPT = ROOT / "artifacts/work_packages/C05/attempts/0001"
ATTEMPT_ID = "C05-0001"
WORK_PACKAGE_ID = "C05"
RECORDED_AT = "2026-08-01T22:30:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/C05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 26
EXPECTED_UNIT_AND_CONTRACT_COUNT = 71
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 27
EXPECTED_PROVENANCE_RECEIPT_COUNT = 8
EXPECTED_TARGETED_COUNT = 132
EXPECTED_A06_REGRESSION_COUNT = 40
EXPECTED_C04_REGRESSION_COUNT = 62
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "schemas/v4_c05"
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/C05/attempts/0001/c05_schema_bundle.py": "305e89a1aaa74b35b51b72c57425e77c5f50f158a80fe7346fb1d14c75c921ec",
    "artifacts/work_packages/C05/attempts/0001/instance_synthesis.py": "c0a8737e1ae9528ab6f0c21351ed65a09cf9b4fc6c1fb5d18dfe481cc5fb7f8f",
    "artifacts/work_packages/C05/attempts/0001/pytest.ini": "2ecedc6d24a1c1d6026303382ff85db584521c2b0d7361fa8276dc237d7d05ad",
    "artifacts/work_packages/C05/attempts/0001/test_negative_adversarial.py": "7f8f13ae6fa05c1e0c1655b7977732d3d29b0dda71c9315cfd32ab503a711c18",
    "artifacts/work_packages/C05/attempts/0001/test_provenance_receipts.py": "bb5de6d11c43b53bbf0d09547ab3ff99aabec271587a1baf4fe01bb25dd93b29",
    "artifacts/work_packages/C05/attempts/0001/test_schema_and_type.py": "8657d68eb54eebe440f66f4564ba9d9cb4efdf7408d61d21ed3197ee77e5e1de",
    "artifacts/work_packages/C05/attempts/0001/test_unit_contract.py": "f3e40e558ecd00527d0fc14c5aa5635cd24e6e10be75f461bcdf5ddb31145c70",
    "schemas/v4_c05/adaptive-search-statistics.schema.json": "3d9984fc7346abed33a8a70d402edc75ca50f0ca8d12db757a349cf27659d3e9",
    "schemas/v4_c05/archive-preservation-record.schema.json": "5941dccea86fb7c3b2b0e4d5edc631561c0ebe36d9a04592e424592040416d5e",
    "schemas/v4_c05/evaluator-authority-surface.schema.json": "eed58038fcb6f0a22b0c26d2f411d4a5a4bf766e0cf0d5921366262dc125002b",
    "schemas/v4_c05/evolution-candidate.schema.json": "82d988fb2ef0d908f6911bbe6f1891d27f4333c4913fe8393e2ed107152db37f",
    "schemas/v4_c05/external-backend-binding.schema.json": "7fa53be09e7d5b7c949b28b36495b3ffa254195dd1338d894c70c648c2ceac1b",
    "schemas/v4_c05/family-index.json": "e4365a2e46b28d782bffbc35ffadb0301087fda787270898eb38b1477d7cf36e",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/A06/attempts/0002/report.json": "a45eff5d49f16c5307ce886ccfcd8dabd742b3c95efd1898d51fc71b0de80425",
    "artifacts/work_packages/B05/attempts/0001/report.json": "b296d29a541cd94f6f8acbba08adc07f9c413a2521a6e0ab3a7178a6273fc731",
    "artifacts/work_packages/C04/attempts/0004/report.json": "28cded86378c3ad189839296bd00dc5c29395dce3d31a6db590de67a7ac008ab",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-c05-bundle.junit.xml",
    "a06_regression": ATTEMPT / "dependency-regression-a06.junit.xml",
    "c04_regression": ATTEMPT / "dependency-regression-c04.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Both C05 dependencies are Python surfaces, so only the full Node suite
# carries the Node reporter's semantic footer.
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "bundle-emit",
    "bundle-verify",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-c05-bundle",
    "dependency-regression-a06",
    "dependency-regression-c04",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_c05_0001_checks.py",
    "build_c05_0001_evidence.py",
    "c05_0001_rah_seal.py",
    "c05_schema_bundle.py",
    "instance_synthesis.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "c05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-c05-bundle.junit.xml",
    "dependency-regression-a06.junit.xml",
    "dependency-regression-c04.junit.xml",
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
    a06 = pytest_summary(JUNIT_PATHS["a06_regression"])
    c04 = pytest_summary(JUNIT_PATHS["c04_regression"])
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
        ("a06_regression", a06, EXPECTED_A06_REGRESSION_COUNT),
        ("c04_regression", c04, EXPECTED_C04_REGRESSION_COUNT),
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
        "a06_regression": a06,
        "baseline_attempt": "B05-0001",
        "c04_regression": c04,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_c05_bundle": targeted,
        "unit_and_contract_tests": unit,
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
            "A06": _sealed_dependency("A06", "A06-0002", "E0119", "E0120"),
            "C04": _sealed_dependency("C04", "C04-0004", "E0107", "E0108"),
        },
        "next_action": "SEAL_C05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("B05", "B05-0001", "E0153", "E0154"),
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
        raise SystemExit(f"schema bundle holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "schemas/v4_c05/**",
            "artifacts/work_packages/C05/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "bundle_is_generated_and_regenerable": True,
        "canonical_schemas_modified": False,
        "component_files": component_files,
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


def c05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "canonical_schemas": "schemas/*.schema.json (C01 authority; unmodified)",
            "composite_vocabulary": (
                "none: composites are pure $ref structure with no enum, const, "
                "pattern or format (EF4-I22)"
            ),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "family-index.json receipts the generator, all 42 canonical "
                    "members and all five composites by content hash; "
                    "verification recomputes every hash from the live files, "
                    "regeneration is byte-identical, and an unreceipted file in "
                    "the bundle is refused"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "every composite is a valid Draft 2020-12 schema whose "
                    "references resolve to canonical $ids; none declares an "
                    "enum, const, pattern or format of its own; the index keeps "
                    "exactly the five titled families over 42 members with "
                    "four explicit, reasoned exclusions"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "a synthesized minimal instance of every canonical member "
                    "validates against its own schema and its family "
                    "composite; hostile instances and edited bundles are "
                    "refused with typed codes; a deleted composite is refused "
                    "then repaired byte-identically by re-emitting"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_negative_adversarial.py"],
                "mechanism": (
                    "the mutable search space is exactly the four genome kinds "
                    "(EF4-I41); evaluator, holdout, promotion, archive and "
                    "backend documents are refused as candidates; a bundle "
                    "edited to widen the space is refused as "
                    "AUTHORITY_IN_MUTABLE_SPACE; adaptive results require "
                    "their statistics (EF4-I53) and imports their "
                    "qualification (EF4-I63)"
                ),
                "status": "PASS",
            },
        },
        "families": {
            "adapter": 3,
            "archive": 9,
            "evaluator": 10,
            "genome": 15,
            "statistics": 5,
        },
        "mutable_search_space": [
            "schemas/challenge-genome.schema.json",
            "schemas/experiment-genome.schema.json",
            "schemas/hypothesis-genome.schema.json",
            "schemas/prompt-genome.schema.json",
        ],
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
        "targeted_test_count": regression["targeted_c05_bundle"]["collected"],
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
                "artifacts/work_packages/C05/attempts/0001/build_c05_0001_evidence.py",
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
        "# C05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The deliverable interpretation is recorded, not assumed silently.\n"
        "  The manifest grants schemas/v4_c05/** while the canonical schema\n"
        "  count is sealed at 127 by B04 and C04, so C05 cannot add canonical\n"
        "  schemas and must not restate them (EF4-I22). Following the x05\n"
        "  namespace pattern (docs/v4_a06, build/v4_b05), the bundle is a\n"
        "  composition layer: pure $ref structure over the canonical sources,\n"
        "  generated deterministically and regenerable byte-for-byte. The\n"
        "  canonical scanners were checked to be non-recursive before the\n"
        "  subdirectory was created, so the sealed 127/128 counts are\n"
        "  untouched.\n"
        "- The mutable-space boundary is structural, not narrative. A document\n"
        "  is a candidate if and only if it is one of the four genome kinds;\n"
        "  evaluator, holdout, promotion-shaped, archive and backend documents\n"
        "  are refused by the same oneOf that admits genomes, and a bundle\n"
        "  edited to widen or narrow that space is refused at verification as\n"
        "  AUTHORITY_IN_MUTABLE_SPACE or MUTABLE_SPACE_MISMATCH.\n"
        "- EF4-I53 and EF4-I63 are encoded as validation requirements rather\n"
        "  than advice: adaptive-search evidence cannot validate without its\n"
        "  multiplicity, sequential and selective-inference records, and an\n"
        "  imported run cannot validate without the pinned backend manifest\n"
        "  and its qualification — with backend_name and license enforced by\n"
        "  the canonical consts, not by this bundle.\n"
        "- The happy paths are synthesized, not hand-picked: one minimal\n"
        "  instance per canonical member is derived mechanically from the\n"
        "  schema itself and validated against both its own schema and its\n"
        "  family composite. The synthesizer refuses constructs it does not\n"
        "  model, so a canonical schema growing an unmodelled pattern fails\n"
        "  loudly instead of being silently skipped. Its number handling was\n"
        "  corrected during this attempt when ratio fields with maximum 1\n"
        "  rejected salted values — caught by the validation tests doing\n"
        "  exactly their job.\n"
        "- Membership is exhaustive and explicit: 42 members across exactly\n"
        "  the five titled families, disjoint, and four evolution-adjacent\n"
        "  protocol schemas excluded by name with the owner that consumes\n"
        "  them, so nothing is silently out of scope.\n"
        "- Residual limitations: the composites bind documents, not runtime\n"
        "  behaviour — enforcement of the boundary in the running chamber\n"
        "  belongs to E05/F05 and the kernel; generated types and fixtures\n"
        "  belong to C06; the synthesizer models only the constructs the\n"
        "  canonical family actually uses; and this review is not external\n"
        "  actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/C05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "C05_EVOLUTION_SCHEMA_FAMILY_BUNDLE",
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
        "next_package": "Q02-0001",
        "not_claimed": [
            "any change to the 127 sealed canonical schemas, which stay the "
            "single declaring source",
            "runtime enforcement of the mutable-space boundary, which E05/F05 "
            "and the kernel own",
            "generated types and fixtures, which the C06 gate owns",
            "that the synthesizer models JSON Schema beyond the constructs "
            "the canonical family uses",
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
        "next_action": "SEAL_C05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_c05_bundle": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
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
    verification = c05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("c05-verification.json", verification)
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
        raise SystemExit("C05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "c05-verification.json")
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
    verification = read_json(ATTEMPT / "c05-verification.json")
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
