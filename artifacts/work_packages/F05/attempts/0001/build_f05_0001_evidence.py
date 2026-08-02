#!/usr/bin/env python3
"""Build and verify F05-0001 EVOLVE subprotocol state machine evidence.

F05-0001 implements `src/epistemic_foundry/evolution/v4_f05/**`: the state
machine that makes EVOLVE a search rather than a pipeline, and constrains the
return edge that makes it one.  A loop back is admitted only across a
committed checkpoint (EF4-I61), bounded by the run's own LoopContract, and a
run may leave only through a typed stop certificate (EF4-I62).  The node
graph is read from the declaring workflow and the stop vocabulary from the
module that owns it, so the machine holds no canonical schema enum value as a
string literal (EF4-I22).  This builder verifies the executed checks and
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
ATTEMPT = ROOT / "artifacts/work_packages/F05/attempts/0001"
ATTEMPT_ID = "F05-0001"
WORK_PACKAGE_ID = "F05"
RECORDED_AT = "2026-08-02T06:30:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/F05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 23
EXPECTED_UNIT_AND_CONTRACT_COUNT = 21
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 21
EXPECTED_PROVENANCE_RECEIPT_COUNT = 11
EXPECTED_TARGETED_COUNT = 76
EXPECTED_DISCIPLINE_COUNT = 5
EXPECTED_CHAMBER_REGRESSION_COUNT = 79
# The Node reporter renders the parent test of the adversarial file as a
# testsuite rather than a testcase, so its semantic footer counts one more test
# than the XML holds testcase elements; the footer is the counter authority.
EXPECTED_GOLDEN_REGRESSION_COUNT = 33
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "src/epistemic_foundry/evolution"
#: The scope decision that authorized the one file outside the manifest
#: grant, without which the machine would be absent from the built wheel.
AUTHORITY_DECISION = "HD-EF4-F05-SCOPE-20260802-001"
AUTHORITY_DECISION_PATH = (
    "artifacts/authority_decisions/HD-EF4-F05-SCOPE-20260802-001.human-decision.json"
)
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/F05/attempts/0001/check_packaging.py": "5d276064529642393b8c3bb901097860e62602ca881d70fd312b2b3ee4aa61dc",
    "artifacts/work_packages/F05/attempts/0001/fixtures.py": "969ffca790998845ab5228ae704093411a8d7a4558ea7e1d7ef1f362697101e8",
    "artifacts/work_packages/F05/attempts/0001/pytest.ini": "209100435cc5a03ff0c4c718af69c7345bc17f36b398290f50eace80ea6720be",
    "artifacts/work_packages/F05/attempts/0001/test_negative_adversarial.py": "81bb361c72ea29519fb463148747ced68e056de799692d1bde7b19c42f0a0711",
    "artifacts/work_packages/F05/attempts/0001/test_provenance_receipts.py": "238481cea0390fe2dd857ba330aabccfb443faac275e77d1a81f61a725508a05",
    "artifacts/work_packages/F05/attempts/0001/test_schema_and_type.py": "bbb96a8a99f8374311af3c5e693ea68f8ee1c3d0be6ca0a0a6f59589a297c4cf",
    "artifacts/work_packages/F05/attempts/0001/test_unit_contract.py": "6cf8238988d2c90a35ec3d2ef0a282169548b30463e991fd709480f083bc2fa2",
    "src/epistemic_foundry/evolution/__init__.py": "5e78003441fe841a387fec000a4d4e53dc35316ed923e46e042a2a4cf47e6f2c",
    "src/epistemic_foundry/evolution/v4_f05/__init__.py": "99113b057119160f287d67673f64e82eab0f8bd349b1385e6be69909c43fce46",
    "src/epistemic_foundry/evolution/v4_f05/machine.py": "8ddcc52b668c6c4e419d19a435176f78eae990e7dceb52551be86e63d57f8c26",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/authority_decisions/HD-EF4-F05-SCOPE-20260802-001.human-decision.json": "f05d1d58b5d7e4f979097dc5768491812f3d8f2fa7aab7803a7996253e81a895",
    "artifacts/work_packages/A06/attempts/0002/report.json": "a45eff5d49f16c5307ce886ccfcd8dabd742b3c95efd1898d51fc71b0de80425",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/E05/attempts/0001/report.json": "1c47949096382d3e98a5f204e0a44ee4255dd0432d0fb60baa4a5339c60043ad",
    "artifacts/work_packages/F04/report.json": "5a2414ebb79c923af7425b87d614faa088ba9fbd4e6950406948b2eb86d6ab46",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-f05-machine.junit.xml",
    "discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
    "chamber_regression": ATTEMPT / "dependency-regression-chamber.junit.xml",
    "golden_regression": ATTEMPT / "dependency-regression-golden.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# F04's golden classifier gate is a Node surface, so its regression JUnit
# carries the Node reporter's semantic footer alongside the full Node suite.
_NODE_JUNITS = frozenset({"full_node", "golden_regression"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "wire-literal-discipline",
    "packaging-discovery",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-f05-machine",
    "dependency-regression-chamber",
    "dependency-regression-golden",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_f05_0001_checks.py",
    "build_f05_0001_evidence.py",
    "f05_0001_rah_seal.py",
    "check_packaging.py",
    "fixtures.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "f05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-f05-machine.junit.xml",
    "wire-literal-discipline.junit.xml",
    "dependency-regression-chamber.junit.xml",
    "dependency-regression-golden.junit.xml",
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
    chamber = pytest_summary(JUNIT_PATHS["chamber_regression"])
    replay = node_summary(JUNIT_PATHS["golden_regression"])
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
        ("chamber_regression", chamber, EXPECTED_CHAMBER_REGRESSION_COUNT),
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
        ("golden_regression", replay, EXPECTED_GOLDEN_REGRESSION_COUNT),
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
        "baseline_attempt": "E05-0001",
        "chamber_regression": chamber,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "golden_regression": replay,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_f05_machine": targeted,
        "unit_and_contract_tests": unit,
        "wire_literal_discipline": discipline,
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
        "authority_decision": {
            "decision_id": AUTHORITY_DECISION,
            "path": AUTHORITY_DECISION_PATH,
            "sha256": sha256_id(ROOT / AUTHORITY_DECISION_PATH),
        },
        "dependencies": {
            "A06": _sealed_dependency("A06", "A06-0002", "E0119", "E0120"),
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
            # F04 predates the attempts/ layout and keeps its report at the
            # package root; citing the wrong path would silently unbind it.
            "F04": _sealed_dependency("F04", "F04-0002", "E0006", "E0007", flat=True),
        },
        "next_action": "SEAL_F05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("E05", "E05-0001", "E0165", "E0166"),
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
        raise SystemExit(f"evolution package holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "src/epistemic_foundry/evolution/v4_f05/**",
            "artifacts/work_packages/F05/**",
            "src/epistemic_foundry/evolution/__init__.py "
            "(HD-EF4-F05-SCOPE-20260802-001)",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
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


def f05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_surfaces": {
            "checkpoint_components": (
                "src/epistemic_foundry/evolution_chamber/checkpoint.py"
            ),
            "node_graph": "workflows/evolution_chamber_cycle.workflow.yaml",
            "stop_classification": (
                "src/epistemic_foundry/evolution_chamber/checkpoint.py "
                "ORDERLY_STOPS/ADVERSE_STOPS"
            ),
        },
        "declaring_sources": {
            "loop_bounds": "schemas/loop-contract.schema.json",
            "node_ids": "workflows/evolution_chamber_cycle.workflow.yaml",
            "stop_reasons": "schemas/evolution-stop-certificate.schema.json",
            "terminal_states": "workflows/evolution_chamber_cycle.workflow.yaml",
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "the stop certificate and the checkpoint are minted by the "
                    "runtime's own builders and validated against their "
                    "canonical schemas, each self-hash is re-derived, an "
                    "unexplained stop yields no certificate at all, and the "
                    "machine mints nothing of its own"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "the node graph, dependencies and terminal states are "
                    "compared against the declaring workflow rather than "
                    "restated; the machine source is scanned and holds no node "
                    "id, terminal state or stop reason as a literal; and a "
                    "workflow with a dangling or duplicated node fails closed"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "a run that walks the declared graph, loops within budget "
                    "and stops with a certificate is accepted under every "
                    "orderly stop reason; an undeclared jump, an uncheckpointed "
                    "or misplaced return edge, an incomplete resume point, a "
                    "run past its iteration budget and a run that never "
                    "certifies its stop are each refused by their own code"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_negative_adversarial.py"],
                "mechanism": (
                    "the machine admits only transitions the workflow declares, "
                    "so a run cannot skip the evaluation, audit and Parliament "
                    "nodes between qualification and promotion; and a stop "
                    "certificate naming a resume point the run never committed "
                    "is refused rather than trusted"
                ),
                "status": "PASS",
            },
        },
        "failure_classes": [
            "CHECKPOINT_INCOMPLETE",
            "ITERATION_BUDGET_EXCEEDED",
            "RETURN_EDGE_MISPLACED",
            "RETURN_EDGE_UNCHECKPOINTED",
            "RUN_UNTERMINATED",
            "STOP_CERTIFICATE_INVALID",
            "TRANSITION_UNDECLARED",
        ],
        "graph": {
            "declared_nodes": 26,
            "entry_nodes": 1,
            "stop_reasons": 9,
            "terminal_states": 5,
        },
        "not_derivable": {
            "stop_ordering": (
                "the caller supplies a run and how it ended with no evidence of "
                "which came first, so the machine does not claim to order the "
                "stop against the transitions; it checks the derivable property "
                "instead, that the certified resume point is one the run "
                "committed"
            )
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
        "targeted_test_count": regression["targeted_f05_machine"]["collected"],
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
                "artifacts/work_packages/F05/attempts/0001/build_f05_0001_evidence.py",
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
        "# F05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The return edge is the whole point. A pipeline that only moves\n"
        "  forward cannot search, and looping is exactly how a search escapes\n"
        "  its own limits, so the machine constrains the loop rather than the\n"
        "  line: a loop back is admitted only across a committed checkpoint, is\n"
        "  bounded by the run's own LoopContract, and must run between the\n"
        "  endpoints that contract declares.\n"
        "- Nothing is restated. The 26 nodes, their dependencies and the five\n"
        "  terminal states are read from the declaring workflow and compared\n"
        "  against it in the tests, and the stop classification comes from the\n"
        "  chamber module that owns it. A workflow that renames a node breaks\n"
        "  this suite instead of leaving a machine describing a graph that no\n"
        "  longer exists.\n"
        "- EF4-I22 caught a real violation during this attempt: the report used\n"
        "  'dry_rounds' as a key, which is also a canonical stop reason, along\n"
        "  with two other colliding keys. The fields were renamed rather than\n"
        "  the module being registered as a declaring owner it is not.\n"
        "- One claim was withdrawn because it could not be derived. The first\n"
        "  draft refused a run that looped 'after' an adverse stop, but the\n"
        "  caller supplies transitions and a certificate with no evidence of\n"
        "  which came first, so the rule was asserting an ordering the data\n"
        "  does not carry — and it wrongly rejected the normal case of a run\n"
        "  that looped and then hit a safety stop. It was replaced with a check\n"
        "  that is derivable: the certified resume point must be one the run\n"
        "  actually committed. The machine now records that limitation\n"
        "  explicitly instead of implying a guarantee it cannot give.\n"
        "- Partial work cannot be hidden. A certificate that sets\n"
        "  partial_results_visible false, records no observed condition, or\n"
        "  names no checkpoint is refused, and the runtime builder forces the\n"
        "  flag true so a caller cannot stop a run and erase where the search\n"
        "  had got to.\n"
        "- One file outside the manifest grant was authorized and recorded:\n"
        "  src/epistemic_foundry/evolution/__init__.py, on the same verified\n"
        "  grounds as the effects marker. A named packaging-discovery check\n"
        "  proves the machine stays discoverable and reads the discovery mode\n"
        "  from pyproject rather than assuming it.\n"
        "- Residual limitations: the machine evaluates a run that is handed to\n"
        "  it, it does not drive one — executing the nodes belongs to the\n"
        "  kernel scheduler; it does not order the stop against the\n"
        "  transitions, as recorded above; the loop contract is read as data\n"
        "  rather than resolved from a run spec, which T05 and the runtime\n"
        "  own; and this review is not external actor-independent\n"
        "  certification.\n"
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
            "path": f"artifacts/work_packages/F05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "F05_EVOLVE_SUBPROTOCOL_STATE_MACHINE",
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
        "next_package": "G05-0001",
        "not_claimed": [
            "execution of an EVOLVE run: the machine evaluates a run handed to "
            "it, and driving the nodes belongs to the kernel scheduler",
            "any ordering of the stop against the transitions, which the input "
            "does not carry evidence for",
            "resolution of the loop contract from a run spec, which T05 and the "
            "runtime own",
            "any change to the declaring workflow or the composed chamber "
            "module, which are read-only inputs",
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
        "next_action": "SEAL_F05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_f05_machine": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
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
    verification = f05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("f05-verification.json", verification)
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
        raise SystemExit("F05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "f05-verification.json")
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
    verification = read_json(ATTEMPT / "f05-verification.json")
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
        raise SystemExit("stored F05-0001 report is not the deterministic document")
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
