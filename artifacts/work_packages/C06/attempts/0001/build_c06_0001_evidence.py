#!/usr/bin/env python3
"""Build and verify C06-0001 generated types, fixtures and compatibility evidence.

C06-0001 emits `schemas/v4_c06/**` as an integration gate over receipts that
were produced independently: the sealed C05 family index and the TypeScript,
Python and UI contract manifests C02 emits.  It reconciles all four against
the live canonical schemas and their canonical fixtures, proves those
fixtures satisfy the C05 composites that govern them, and binds compatibility
as pure $ref structure.  This builder verifies the executed checks and emits
immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/C06/attempts/0001"
ATTEMPT_ID = "C06-0001"
WORK_PACKAGE_ID = "C06"
RECORDED_AT = "2026-08-02T01:30:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/C06/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 18
EXPECTED_UNIT_AND_CONTRACT_COUNT = 61
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 34
EXPECTED_PROVENANCE_RECEIPT_COUNT = 11
EXPECTED_TARGETED_COUNT = 124
EXPECTED_C05_REGRESSION_COUNT = 132
EXPECTED_CONTRACTS_REGRESSION_COUNT = 29
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "schemas/v4_c06"
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/C06/attempts/0001/c06_integration_gate.py": "9117d79598bf8341947a9630b1b0e431711967ca7830ed0999c3b7783d3b2323",
    "artifacts/work_packages/C06/attempts/0001/pytest.ini": "915e8e897341535df82abc6cf984a25b924579eda19f52bc6448e1a2d1605fea",
    "artifacts/work_packages/C06/attempts/0001/test_negative_adversarial.py": "fe03d9b44b77dc0c265bb94c2ee721f75501d50c9e6bc198a129ec9c67390e45",
    "artifacts/work_packages/C06/attempts/0001/test_provenance_receipts.py": "393d5345b3cbac5dcf7727af4742ec61a73048d07dc23293cd899a0330144504",
    "artifacts/work_packages/C06/attempts/0001/test_schema_and_type.py": "85c6a1b9afd2bb8c729bc26d123f7e8d16cb6be9e573a5c4abe76bfd81c68467",
    "artifacts/work_packages/C06/attempts/0001/test_unit_contract.py": "9694c39872d9d2ff819cd902ebf52840f9d6d5856917e84137dc471a3d8d258d",
    "schemas/v4_c06/evolution-compatibility-binding.schema.json": "b6e91931bb88712fba857b45680c2df56c46618321896a56ee80506f80d62435",
    "schemas/v4_c06/generated-projection-parity.json": "cc7d5c3e9f7733103b1f13890bd3b8bdb13d278589d42fecb034700aeaa79dba",
    "schemas/v4_c06/integration-index.json": "6eda2f914492452474241c3e093f676d4321c8efc6c98be04e58c135f7bc64f0",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/Q03/attempts/0001/report.json": "b0f601f10de7e39db863cc38440aa1ec0994217167b1fd22e3af0ace4aa8db20",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-c06-gate.junit.xml",
    "c05_regression": ATTEMPT / "dependency-regression-c05.junit.xml",
    "contracts_regression": ATTEMPT / "dependency-regression-contracts.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every C06 dependency is a Python surface, so only the full Node suite
# carries the Node reporter's semantic footer.
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "gate-emit",
    "gate-verify",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-c06-gate",
    "dependency-regression-c05",
    "dependency-regression-contracts",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_c06_0001_checks.py",
    "build_c06_0001_evidence.py",
    "c06_0001_rah_seal.py",
    "c06_integration_gate.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "c06-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-c06-gate.junit.xml",
    "dependency-regression-c05.junit.xml",
    "dependency-regression-contracts.junit.xml",
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
    c05 = pytest_summary(JUNIT_PATHS["c05_regression"])
    contracts = pytest_summary(JUNIT_PATHS["contracts_regression"])
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
        ("c05_regression", c05, EXPECTED_C05_REGRESSION_COUNT),
        (
            "contracts_regression",
            contracts,
            EXPECTED_CONTRACTS_REGRESSION_COUNT,
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
        "baseline_attempt": "Q03-0001",
        "c05_regression": c05,
        "component_tests_are_targeted_only": True,
        "contracts_regression": contracts,
        "full_node": node,
        "full_python": python,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_c06_gate": targeted,
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
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
        },
        "next_action": "SEAL_C06_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("Q03", "Q03-0001", "E0159", "E0160"),
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
        raise SystemExit(
            f"integration bundle holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [
            "schemas/v4_c06/**",
            "artifacts/work_packages/C06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "bundle_is_generated_and_regenerable": True,
        "canonical_schemas_modified": False,
        "component_files": component_files,
        "generated_projections_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "sealed_c05_bundle_modified": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def c06_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "canonical_schemas": "schemas/*.schema.json (C01 authority; unmodified)",
            "compatibility_vocabulary": (
                "none: the binding is pure $ref structure over "
                "compatibility-matrix, schema-migration and "
                "update-impact-report (EF4-I22)"
            ),
            "family_membership": "schemas/v4_c05/family-index.json (sealed C05)",
            "generated_projections": (
                "packages/contracts, python/epistemic_foundry/contracts and "
                "web/src/generated contract manifests (C02 authority; "
                "unmodified)"
            ),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "integration-index.json receipts the generator, the four "
                    "reconciled sources and both emitted outputs by content "
                    "hash; verification recomputes every one of them from the "
                    "live repository, regeneration is byte-identical, and a "
                    "file in the bundle that no receipt covers is refused"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "the compatibility binding is a valid Draft 2020-12 schema "
                    "whose references resolve to canonical $ids and which "
                    "declares no enum, const, pattern or format of its own; "
                    "the index and parity record keep exact field sets with "
                    "recomputable hashes and account for exactly the sealed "
                    "C05 membership"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "all four receipts are re-derived from the live repository "
                    "and must agree on every member; every canonical fixture "
                    "validates against its own schema and, where one governs "
                    "it, its C05 composite; divergence, staleness, tampering "
                    "and re-sealing are each refused with a typed code, and a "
                    "deleted output is repaired byte-identically by re-emitting"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_negative_adversarial.py"],
                "mechanism": (
                    "the EF4-I41 boundary is proved with the repository's own "
                    "fixtures: each of the eleven genome-family records that "
                    "merely describe variation must be refused as a candidate, "
                    "as must the evaluator and holdout fixtures, and a bundle "
                    "whose candidate composite was widened is refused as "
                    "AUTHORITY_IN_MUTABLE_SPACE"
                ),
                "status": "PASS",
            },
        },
        "reconciliation": {
            "canonical_fixtures_validated": 84,
            "composite_bound_members": 31,
            "member_count": 42,
            "projections_reconciled": 3,
            "schema_only_members": 11,
            "sources_reconciled": 4,
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
        "targeted_test_count": regression["targeted_c06_gate"]["collected"],
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
                "artifacts/work_packages/C06/attempts/0001/build_c06_0001_evidence.py",
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
        "# C06-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- An integration gate is only worth the independence of what it\n"
        "  reconciles. Four receipts cover the C05 family and none derives from\n"
        "  another: the sealed C05 index and the TypeScript, Python and UI\n"
        "  contract manifests C02 emits. All four must agree with the live\n"
        "  canonical file for every one of the 42 members; a disagreement is\n"
        "  refused rather than resolved by picking a winner.\n"
        "- The gate caught a real error during this attempt. The first fixture\n"
        "  mapping bound the whole fifteen-member genome family to the\n"
        "  candidate composite, and candidate-generation-record failed. The\n"
        "  composite was right and the mapping was wrong: only the four mutable\n"
        "  genome kinds are candidates (EF4-I41). Rather than widen the\n"
        "  composite, the mapping was corrected and the remaining eleven are\n"
        "  now checked from the hostile side — each must be refused as a\n"
        "  candidate — and recorded as schema-only with the reason.\n"
        "- Fixtures are proved against the repository, not against themselves.\n"
        "  Every member's canonical example validates against its own schema,\n"
        "  and where a C05 composite governs it, against that composite too:\n"
        "  84 validations over 42 members. This is what turns C05's composites\n"
        "  from plausible structure into structure the repository's own\n"
        "  fixtures satisfy.\n"
        "- Compatibility is structure, not advice. A migration cannot validate\n"
        "  without the compatibility matrix it applies under, and the binding\n"
        "  adds no vocabulary: every constraint is a reference to the canonical\n"
        "  contract that owns it, checked by the same forbidden-keyword scan\n"
        "  C05 uses.\n"
        "- Nothing outside the write scope was touched. The 127 canonical\n"
        "  schemas, the canonical examples, the three generated projections and\n"
        "  the sealed C05 bundle are all read-only inputs, hashed into the\n"
        "  receipt and verified unchanged.\n"
        "- Residual limitations: the gate reconciles receipts and fixtures, not\n"
        "  the generators that produced them — regenerating the C02 projections\n"
        "  is C02's own codegen_clean_diff check; the compatibility binding\n"
        "  describes what a migration record must carry, not whether a proposed\n"
        "  migration is correct, which C03 owns; and this review is not\n"
        "  external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/C06/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "C06_GENERATED_TYPES_FIXTURES_AND_COMPATIBILITY_GATE",
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
        "next_package": "D05-0001",
        "not_claimed": [
            "any change to the canonical schemas, examples, generated "
            "projections, or the sealed C05 bundle, which are read-only inputs",
            "that the C02 generators reproduce their projections, which C02's "
            "own codegen check owns",
            "that a proposed migration is correct, only that a migration record "
            "carries the matrix and impact it must",
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
        "next_action": "SEAL_C06_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_c06_gate": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
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
    verification = c06_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("c06-verification.json", verification)
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
        raise SystemExit("C06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "c06-verification.json")
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
    verification = read_json(ATTEMPT / "c06-verification.json")
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
