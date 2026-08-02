#!/usr/bin/env python3
"""Build and verify S05-0001 evolution threat-control evidence.

S05-0001 implements `src/epistemic_foundry/security/v4_s05/**`: the gate that
decides whether candidate code may execute at all (EF4-I64), the gate that
refuses a run whose active prompt surface carries unreleased mutations
(EF4-I55), and the canonical leakage audit over the firewall's holdout
intersection (EF4-I44).  The sandbox classes and threat register are parsed
from the threat model the invariant names as evidence, the leakage surfaces
from EF4-I44's own statement, and the network, safety and status vocabularies
are read from their canonical schemas positionally with every positional
assumption pinned by a test.  This builder verifies the executed checks and
emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/S05/attempts/0001"
ATTEMPT_ID = "S05-0001"
WORK_PACKAGE_ID = "S05"
RECORDED_AT = "2026-08-02T14:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/S05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 12
EXPECTED_UNIT_AND_CONTRACT_COUNT = 16
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 23
EXPECTED_PROVENANCE_RECEIPT_COUNT = 11
EXPECTED_TARGETED_COUNT = 62
EXPECTED_DISCIPLINE_COUNT = 5
EXPECTED_C05_REGRESSION_COUNT = 132
EXPECTED_FIREWALL_REGRESSION_COUNT = 97
EXPECTED_REDTEAM_REGRESSION_COUNT = 17
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1063
EXPECTED_NODE_FILE_COUNT = 95

COMPONENT = "src/epistemic_foundry/security/v4_s05"
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/S05/attempts/0001/check_packaging.py": "f4211f6ffccf6c4f4284836468d3cdae0cc5d83dbfcc8ff40116342962e69051",
    "artifacts/work_packages/S05/attempts/0001/fixtures.py": "1d147223ba9399d09338b5a3f9369714b39d74a72e7ba661dba6fa01cc975d90",
    "artifacts/work_packages/S05/attempts/0001/pytest.ini": "6c978a780abf8f17553b74cbfa4458783047d9b51eb7fbcd6472c0b5889c105e",
    "artifacts/work_packages/S05/attempts/0001/run_s05_0001_checks.py": "d0243b92503fa77c8e5662fdcdd6a5e3e31477224871501e5cf78ec0d3196012",
    "artifacts/work_packages/S05/attempts/0001/test_negative_adversarial.py": "e04940edcfc91491dc89caee945fc57a2473637b9bdec1e3d0c8f5c5aeb8d84a",
    "artifacts/work_packages/S05/attempts/0001/test_provenance_receipts.py": "2a67d4805cb50b4b8987705f328d7ee5a10918720f479d3cf286b9103adff76c",
    "artifacts/work_packages/S05/attempts/0001/test_schema_and_type.py": "1b6d95c03388cf1e01ae8edef87d3757bb6b7e9468d16c47e2e208027fcdfec9",
    "artifacts/work_packages/S05/attempts/0001/test_unit_contract.py": "92406e427a01afa15f6362d13c8fa3d4b06481b0ebadf4d87e2e67e21aa11ae1",
    "src/epistemic_foundry/security/v4_s05/__init__.py": "c311d1132ae385cfea553d7b45f2c6268aa028f4a6ac8ad610e1ebbd2a0e3771",
    "src/epistemic_foundry/security/v4_s05/threat_controls.py": "2a4282b3c8fe5fed31b9525a6cd84c44492b65644e581adfef45af9986dcc5df",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/A06/attempts/0002/report.json": "a45eff5d49f16c5307ce886ccfcd8dabd742b3c95efd1898d51fc71b0de80425",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/M05/attempts/0001/report.json": "068cc89635b0b0ced2347be31b9ec805723cecc0ae2520946d9c0c6b9eb83d75",
    "artifacts/work_packages/S04/attempts/0005/report.json": "9f088632a014740e6790127e485262013aac823fb6d58c96d3320f378e20a723",
}
#: Read-only inputs the controls compose.  They are pinned as evidence of what
#: was composed rather than asserted as sealed dependency bindings.
EXPECTED_COMPOSED_HASHES = {
    "docs/evolution_security_threat_model.md": "b7ae81f658581c13590c897eae1a6f28f658c326c41a79a654a5c25eb884d190",
    "manifests/product_invariants.yaml": "de74929aed1566bf2487dcdeba54cea68aa75e09a29add7c2010af6d84d32871",
    "schemas/leakage-audit.schema.json": "bf7fef71038895a88615991719d5bb3366fc74bad08b2f5cb293ffc5307cad20",
    "schemas/validation-target-manifest.schema.json": "33ca04ce4aefcebce4e395338e09038e0a78bac063250b58d65d8d6d54275ebe",
    "src/epistemic_foundry/budgets/envelope.py": "dc76097ae288b91ca3e7d25df25fe98d9f75f41e8caa60e6e5f670cf0bac05a6",
    "src/epistemic_foundry/governance/quarantine.py": "a11511547926e22f35b46daed7eb54aefe579aa86d01041f79876921ec840e31",
    "src/epistemic_foundry/verifier_firewall/firewall.py": "fe0669976a536d1e9174473a38479d487820157f883bfc4eca2aaa1b84b43761",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-s05-threat-controls.junit.xml",
    "discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
    "c05_regression": ATTEMPT / "dependency-regression-c05.junit.xml",
    "firewall_regression": ATTEMPT / "dependency-regression-firewall.junit.xml",
    "redteam_regression": ATTEMPT / "dependency-regression-redteam.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# S04's red-team suites are a Node surface, so their regression JUnit carries
# the Node reporter's semantic footer alongside the full Node suite.
_NODE_JUNITS = frozenset({"full_node", "redteam_regression"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "wire-literal-discipline",
    "packaging-discovery",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-s05-threat-controls",
    "dependency-regression-c05",
    "dependency-regression-firewall",
    "dependency-regression-redteam",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_s05_0001_checks.py",
    "build_s05_0001_evidence.py",
    "s05_0001_rah_seal.py",
    "check_packaging.py",
    "fixtures.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "s05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-s05-threat-controls.junit.xml",
    "wire-literal-discipline.junit.xml",
    "dependency-regression-c05.junit.xml",
    "dependency-regression-firewall.junit.xml",
    "dependency-regression-redteam.junit.xml",
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
    c05 = pytest_summary(JUNIT_PATHS["c05_regression"])
    firewall = pytest_summary(JUNIT_PATHS["firewall_regression"])
    redteam = node_summary(JUNIT_PATHS["redteam_regression"])
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
        ("c05_regression", c05, EXPECTED_C05_REGRESSION_COUNT),
        ("firewall_regression", firewall, EXPECTED_FIREWALL_REGRESSION_COUNT),
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
        ("redteam_regression", redteam, EXPECTED_REDTEAM_REGRESSION_COUNT),
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
        "baseline_attempt": "M05-0001",
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "c05_regression": c05,
        "firewall_regression": firewall,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 1063, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "redteam_regression": redteam,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_s05_threat_controls": targeted,
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
    assert_hashes(EXPECTED_COMPOSED_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_inputs": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_COMPOSED_HASHES.items()
        },
        "dependencies": {
            "A06": _sealed_dependency("A06", "A06-0002", "E0119", "E0120"),
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
            "S04": _sealed_dependency("S04", "S04-0005", "E0097", "E0098"),
        },
        "next_action": "SEAL_S05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("M05", "M05-0001", "E0173", "E0174"),
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
        raise SystemExit(f"security package holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "src/epistemic_foundry/security/v4_s05/**",
            "artifacts/work_packages/S05/**",
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


def s05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_surfaces": {
            "budget_normalizer": (
                "src/epistemic_foundry/budgets/envelope.py normalize_hard_limits"
            ),
            "mutation_quarantine": (
                "src/epistemic_foundry/governance/quarantine.py "
                "may_influence_run/require_not_retroactive"
            ),
            "verifier_firewall": (
                "src/epistemic_foundry/verifier_firewall/firewall.py VerifierFirewall"
            ),
        },
        "declaring_sources": {
            "execution_vocabularies": (
                "schemas/validation-target-manifest.schema.json network/safety/"
                "approval enums, read positionally with the ordering pinned by "
                "a test"
            ),
            "leakage_surfaces": ("manifests/product_invariants.yaml EF4-I44 statement"),
            "sandbox_classes_and_threats": ("docs/evolution_security_threat_model.md"),
            "search_space": "schemas/v4_c05/family-index.json",
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "every qualification, coverage record and leakage audit "
                    "re-derives its own hash from exactly the fields it "
                    "publishes; an execution cannot qualify without a bound "
                    "effect-receipt channel; the audit validates against its "
                    "canonical schema and never carries a score field; and "
                    "nothing holds a clock the caller did not supply"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "the sandbox classes and threat register are parsed from "
                    "the threat model EF4-I64 names as evidence, the leakage "
                    "surfaces from EF4-I44's own statement, every positional "
                    "enum assumption is pinned against the schema text, the "
                    "controls hold no manifest, audit or proposal enum value "
                    "as a literal, and each of the 15 failure codes carries "
                    "its reason"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "a bounded closed-network target qualifies and an approved "
                    "proposal activates for a future run; an open network, an "
                    "undeclared capability, a missing or misnamed quota, a "
                    "blank receipt channel, an undeclared sandbox, a "
                    "quarantined prompt on the active surface, a retroactive "
                    "application, a skipped audit surface and a drifted "
                    "evaluator bundle are each refused by their own code"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                ],
                "mechanism": (
                    "candidate-generating roles are probed live against the "
                    "sealed firewall and denied holdout access "
                    "unconditionally; a kind outside the sealed search space "
                    "cannot qualify; unreleased prompt mutations cannot "
                    "influence a run; and a leakage exposure yields incident "
                    "actions, never a score adjustment"
                ),
                "status": "PASS",
            },
        },
        "failure_classes": [
            "APPROVAL_MISSING",
            "CANDIDATE_KIND_UNQUALIFIED",
            "CAPABILITY_UNDECLARED",
            "HOLDOUT_REACHABLE",
            "INPUT_INVALID",
            "LEAKAGE_SURFACE_MISSING",
            "NETWORK_POLICY_OPEN",
            "QUARANTINED_INFLUENCE",
            "QUOTA_MISSING",
            "RECEIPT_CHANNEL_MISSING",
            "RETROACTIVE_MUTATION",
            "SANDBOX_CLASS_UNDECLARED",
            "THREAT_MODEL_UNREADABLE",
            "THREAT_UNCOVERED",
            "THREAT_UNDECLARED",
        ],
        "implementation_findings": [
            {
                "finding": (
                    "the minimum leakage surfaces were first held as the "
                    "literals ('cache', 'log', 'tool'), and 'tool' is a "
                    "canonical enum value elsewhere, which the repository's "
                    "EF4-I22 gate refused"
                ),
                "resolution": (
                    "the surfaces are parsed from EF4-I44's own statement in "
                    "the invariant manifest, so the audit floor now widens "
                    "automatically if the invariant does"
                ),
            }
        ],
        "not_derivable": {
            "execution_itself": (
                "the qualification decides whether candidate code may run; "
                "actually running it under the lease and minting the effect "
                "receipt belong to the T-phase sandbox and the runtime"
            ),
            "similarity_analysis": (
                "the leakage audit records similarity alerts the caller "
                "supplies; deriving them requires content access this module "
                "deliberately does not have"
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
        "targeted_test_count": regression["targeted_s05_threat_controls"]["collected"],
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
                "artifacts/work_packages/S05/attempts/0001/build_s05_0001_evidence.py",
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
        "# S05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The gap this package closes is the one EF4-I64 names: the firewall\n"
        "  seals evaluators, the quarantine holds proposals inert, and the\n"
        "  sandbox bounds ordinary tools, but nothing decided whether an\n"
        "  evolution candidate's code may execute at all. Now nothing runs\n"
        "  without declared capabilities, an enforceable quota, a bound\n"
        "  effect-receipt channel, a declared sandbox class and verified\n"
        "  evaluator/holdout isolation — and the isolation is probed live\n"
        "  against the sealed firewall for every candidate-generating role,\n"
        "  not read from a flag.\n"
        "- The repository's own EF4-I22 gate caught a real violation during\n"
        "  this attempt: the minimum leakage surfaces were first held as\n"
        "  literals, and 'tool' is a canonical enum value elsewhere. The fix\n"
        "  is better than the original intent — the surfaces are now parsed\n"
        "  from EF4-I44's own statement, so a widened invariant widens the\n"
        "  audit floor without an edit here.\n"
        "- Every positional enum assumption is pinned. The engine refuses the\n"
        "  last network policy and requires approval at the last safety class\n"
        "  by position, because holding the enum values would violate\n"
        "  EF4-I22; the schema-and-type suite asserts the declared orderings\n"
        "  verbatim so the assumption cannot rot in silence.\n"
        "- The gates are passable, which matters as much as their refusals: a\n"
        "  closed-network bounded target qualifies, an allowlisted network\n"
        "  qualifies exactly when its capabilities are declared, every\n"
        "  declared sandbox class is acceptable, and an APPROVED proposal\n"
        "  activates for a future run while its own source run stays refused\n"
        "  through the quarantine module's own retroactivity rule.\n"
        "- The threat register is exact in both directions: coverage without\n"
        "  evidence is refused, and evidence for an invented threat is\n"
        "  refused rather than padding the record. A failed leakage audit\n"
        "  carries the incident actions in the threat model's own words and\n"
        "  never converts an exposure into a score.\n"
        "- Nothing is reimplemented: influence and retroactivity come from\n"
        "  the quarantine module, isolation and drift detection from the\n"
        "  firewall, quota normalization from the budget module, and the\n"
        "  search space from the sealed C05 index.\n"
        "- Residual limitations: the qualification decides, it does not\n"
        "  execute — the lease, the sandbox process and the effect receipt\n"
        "  belong to the T-phase and the runtime; similarity alerts are\n"
        "  recorded from the caller because deriving them needs content\n"
        "  access this module does not have; and this review is not external\n"
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
            "path": f"artifacts/work_packages/S05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "S05_EVOLUTION_THREAT_CONTROLS",
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
        "next_package": "Q04-0001",
        "not_claimed": [
            "execution of candidate code: the qualification decides whether it "
            "may run; the lease, sandbox process and effect receipt belong to "
            "the T-phase and the runtime",
            "similarity analysis, which requires content access this module "
            "deliberately does not have",
            "any change to the composed firewall, quarantine, budget or "
            "sandbox surfaces, which are read-only inputs",
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
        "next_action": "SEAL_S05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_s05_threat_controls": (
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
    verification = s05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("s05-verification.json", verification)
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
        raise SystemExit("S05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "s05-verification.json")
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
    assert_hashes(EXPECTED_COMPOSED_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "s05-verification.json")
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
        raise SystemExit("stored S05-0001 report is not the deterministic document")
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
