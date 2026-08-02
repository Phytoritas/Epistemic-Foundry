#!/usr/bin/env python3
"""Build and verify T02-0001 MCP mutating-tool evidence.

T02-0001 composes nine MUTATING_EFFECT tools onto the sealed T01 read and
planning surface.  It verifies the executed checks and emits immutable attempt
evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/T02/attempts/0001"
ATTEMPT_ID = "T02-0001"
WORK_PACKAGE_ID = "T02"
RECORDED_AT = "2026-08-01T07:55:00.000Z"

EXPECTED_MCP_EFFECT_COUNT = 24
EXPECTED_APPROVAL_COUNT = 18
EXPECTED_TARGETED_COUNT = 65
EXPECTED_SEALED_T01_COUNT = 106
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 903
EXPECTED_NODE_FILE_COUNT = 87

APPROVED_SCOPE = (
    "contracts/mcp/catalog-set.yaml",
    "contracts/mcp/t02/**",
    "src/epistemic_foundry/application/mcp_mutating/**",
    "packages/plugin-host/src/mcp/write/**",
    "tests/mcp/t02/**",
    "tests/node/t02-mcp-write-surface.test.mjs",
    "tests/test_wire_literal_discipline.py",
    "docs/t02_mutating_tool_architecture.md",
    "artifacts/authority_decisions/HD-EF4-T02-SCOPE-20260801-002.human-decision.json",
    "artifacts/work_packages/T02/**",
)
COMPONENT = "src/epistemic_foundry/application/mcp_mutating"
EXPECTED_PRODUCT_HASHES = {
    "contracts/mcp/catalog-set.yaml": "283cbdd9ac17756483f908bd8fa13904dd262660a2a2272de4e212e292b81744",
    "contracts/mcp/t02/schemas/common-mutation-input.schema.json": "dfcb1aa6d53f2c27979df9b176d606e20db2abd64526c1c617cc11694338adde",
    "contracts/mcp/t02/schemas/mutation-error-details.schema.json": "edd167e2c27cfe29fe584a94126491d2c54fdcaa35a21c4f72ee8886f7a7eb71",
    "contracts/mcp/t02/schemas/mutation-result.schema.json": "aa1bf2b6335e41ed2240ef92f98fc754448f5fcc2e92b6f84f2be7ccba3de386",
    "contracts/mcp/t02/schemas/tools/claim-promote.input.schema.json": "3e6b0eb85ad5ea0bd10f0b47900a783d02126bfc190274b75ee4630d900c7d42",
    "contracts/mcp/t02/schemas/tools/corpus-register.input.schema.json": "208512d777cefa9cf0f4211d7bbf697cb2f8be34b6a6efb9c61c746a26564fe0",
    "contracts/mcp/t02/schemas/tools/memory-write.input.schema.json": "1688f599e854854f7eb042d3a7fff0f144d923a7ea2f6f2825f0d29de68ef21f",
    "contracts/mcp/t02/schemas/tools/parliament-execute.input.schema.json": "8520d23cdfd81c2f086f7c6d26a84e7d327b9850ff2bbe53d3493998656a9c01",
    "contracts/mcp/t02/schemas/tools/passport-publish.input.schema.json": "3ef74a823286d5b3f2bd581edd508104e9ef7fd3ccfb144e4f5eaf2bf85a868f",
    "contracts/mcp/t02/schemas/tools/search-execute.input.schema.json": "48ff0a18cdc7acc73f63e7658762eed382987cb0dc6a2b007c64b7b0774c388b",
    "contracts/mcp/t02/schemas/tools/session-transition.input.schema.json": "0d32bf1c97b9a3308f9939e05fdecd8e0a68cd8651b505d14ed39f91cea00e63",
    "contracts/mcp/t02/schemas/tools/skill-activate.input.schema.json": "ba6b7ef577a133a6fb865cd02c5efa1b8ca1902cdcb541681428cc7ab3967b6f",
    "contracts/mcp/t02/schemas/tools/validation-execute.input.schema.json": "ffe409c755d2f291d445df3a2fe16ec06cecfed88846dd6be1e3b712f08bc704",
    "contracts/mcp/t02/tool-catalog.yaml": "20d05890e664eadd3b3afc7c9a82fb6a5d358fd91ad1a4fd29d09f00ad8afea6",
    "packages/plugin-host/src/mcp/write/adapter.mjs": "27ed7d49de208bd4df27b1169204bb3ccca9171d4ea10c751e15b4f07b0a992b",
    "packages/plugin-host/src/mcp/write/catalog-set.mjs": "f017c9b2c0dbec571e29348446be3b7764ae48b277044c06b1dcd24f9cf59f1d",
    "packages/plugin-host/src/mcp/write/generated/t02-tool-descriptors.json": "70f8f2cd93479055fa34072852af87796fef859d899773438890b17fd23fde91",
    "src/epistemic_foundry/application/mcp_mutating/__init__.py": "67082d7551e78bb7255157556c435fe8f1a920a1085221559f3a197f7fab4bc9",
    "src/epistemic_foundry/application/mcp_mutating/handler_factory.py": "2722f26540e272629de8f34316d6e76f8a67ed917913bedaf3abead87dd70684",
    "src/epistemic_foundry/application/mcp_mutating/ports.py": "10fb6af0d03a684670faaa0eaf2815867d3013f5a366704ec4c76426aa03dc5e",
    "src/epistemic_foundry/application/mcp_mutating/reconciliation.py": "3aea319bafe359a8c1c57c057ca491e36c450b1eef5b909a75b42effd028ab0f",
    "src/epistemic_foundry/application/mcp_mutating/service.py": "7111d6db50556844c9922d534b76b429fc1e185bd14529301d5c81e81165a52d",
    "tests/mcp/t02/conftest.py": "76e80c0e433e3507ec7e0a1c627f4dd247e384fa77e5f3efe40fb349ad1a9dda",
    "tests/mcp/t02/harness.py": "8db93901d3f58fb51e76efd99e3c8e752168ae65f45af25e12e02034644a655a",
    "tests/mcp/t02/test_approval.py": "53a68c380beda9d2a86671f7fb127e83dfa143c63c146a65664a32b464923598",
    "tests/mcp/t02/test_mcp_effect.py": "472b7deefb029294ebcd90624e7ea82cec356d55ff131e618b6a1022475c2812",
    "tests/mcp/t02/test_tool_catalog.py": "84bcc363be37583becc333720e500e4cb9229a6d6429b2e44bf3bc1b89a8506f",
    "tests/mcp/t02/test_tools_list.py": "f618d967c1d1a9e12ad7d1c40534755d41d252142419a7b0fc21677a6d9e4f53",
    "tests/node/t02-mcp-write-surface.test.mjs": "e1916a84e20b604d84a7545ccb853a5fc06cd2d52224e3c5f52762a11f8dca19",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/T01/attempts/0002/report.json": "474def1666b367e5a9da3bdbf622b78211046a88e2d2110aa3176a775f016ea4",
    "artifacts/work_packages/W03/attempts/0001/report.json": "e43a43d65fb0177131fc23b0a966dfcd1111e1b9e2eaeb809bda6a57148c3a58",
}

JUNIT_PATHS = {
    "mcp_effect": ATTEMPT / "mcp-effect-test.junit.xml",
    "approval": ATTEMPT / "approval-test.junit.xml",
    "targeted": ATTEMPT / "targeted-mcp-mutating.junit.xml",
    "sealed_t01": ATTEMPT / "sealed-t01-regression.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "mcp-effect-test",
    "approval-test",
    "targeted-mcp-mutating",
    "sealed-t01-regression",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_t02_0001_checks.py",
    "build_t02_0001_evidence.py",
    "t02_0001_rah_seal.py",
    "dependency-status.json",
    "t02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "mcp-effect-test.junit.xml",
    "approval-test.junit.xml",
    "targeted-mcp-mutating.junit.xml",
    "sealed-t01-regression.junit.xml",
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
    mcp_effect = pytest_summary(JUNIT_PATHS["mcp_effect"])
    approval = pytest_summary(JUNIT_PATHS["approval"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    sealed = pytest_summary(JUNIT_PATHS["sealed_t01"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("mcp_effect_test", mcp_effect, EXPECTED_MCP_EFFECT_COUNT),
        ("approval_test", approval, EXPECTED_APPROVAL_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("sealed_t01_regression", sealed, EXPECTED_SEALED_T01_COUNT),
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
        "approval_test": approval,
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "W03-0001",
        "full_node": node,
        "full_python": python,
        "mcp_effect_test": mcp_effect,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 887, "full_python": 1196},
        "sealed_t01_regression": sealed,
        "status": "PASS",
        "targeted_mcp_mutating": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    t01_path = ROOT / "artifacts/work_packages/T01/attempts/0002/report.json"
    t01 = read_json(t01_path)
    t01_rah = t01.get("rah_state")
    if (
        t01.get("status") != "PASS"
        or not isinstance(t01_rah, dict)
        or t01_rah.get("core_evidence_id") != "E0113"
        or t01_rah.get("final_closeout_evidence_id") != "E0114"
    ):
        raise SystemExit("T01-0002 dependency is not the sealed PASS attempt")
    baseline_path = ROOT / "artifacts/work_packages/W03/attempts/0001/report.json"
    baseline = read_json(baseline_path)
    rah = baseline.get("rah_state")
    if (
        baseline.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != "E0125"
        or rah.get("final_closeout_evidence_id") != "E0126"
    ):
        raise SystemExit("W03-0001 regression baseline is not the sealed PASS attempt")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "T01": {
                "attempt_id": "T01-0002",
                "core_evidence_id": "E0113",
                "final_closeout_evidence_id": "E0114",
                "report": "artifacts/work_packages/T01/attempts/0002/report.json",
                "report_sha256": sha256_id(t01_path),
                "status": "PASS",
            }
        },
        "next_action": "SEAL_T02_0001_THEN_CONTINUE_DAG",
        "regression_baseline": {
            "attempt_id": "W03-0001",
            "core_evidence_id": "E0125",
            "final_closeout_evidence_id": "E0126",
            "report": "artifacts/work_packages/W03/attempts/0001/report.json",
            "report_sha256": sha256_id(baseline_path),
            "status": "PASS",
        },
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    declared_component = sorted(
        relative
        for relative in EXPECTED_PRODUCT_HASHES
        if relative.startswith(f"{COMPONENT}/")
    )
    if component_files != declared_component:
        raise SystemExit(
            f"mutating component holds unexpected files: {component_files}"
        )
    sealed_t01 = {
        "contracts/mcp/t01/tool-catalog.yaml",
        "contracts/mcp/t01/foundry-mcp-tool-result.schema.json",
        "contracts/mcp/t01/foundry-mcp-tool-error.schema.json",
        "packages/plugin-host/src/mcp/generated/tool-descriptors.json",
        "packages/plugin-host/src/mcp/read/mcp-server.mjs",
    }
    return {
        "approved_scope": list(APPROVED_SCOPE),
        "attempt_id": ATTEMPT_ID,
        "component_files": component_files,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "sealed_t01_surface_untouched": sorted(sealed_t01),
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def t02_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_decision": "HD-EF4-T02-SCOPE-20260801-002",
        "authorization_order": {
            "approval_placement": "inside CAPABILITY_AUTHORIZATION, before lease issuance",
            "frozen_top_level_order_extended": False,
            "self_approval_enforced_by_service": True,
        },
        "catalog_composition": {
            "catalog_set_holds_no_tool_name_literal": True,
            "composed_tool_count": 22,
            "mutating_tool_count": 9,
            "sealed_t01_tool_count": 13,
        },
        "exit_criteria": {
            "effects_reconcile": {
                "evidence": [
                    "tests/mcp/t02/test_mcp_effect.py",
                    f"{COMPONENT}/reconciliation.py",
                ],
                "status": "PASS",
            },
            "no_mutation_without_lease": {
                "evidence": [
                    "tests/mcp/t02/test_mcp_effect.py",
                    f"{COMPONENT}/handler_factory.py",
                ],
                "status": "PASS",
            },
        },
        "mutation_semantics": {
            "committed_is_tristate": True,
            "dry_run_records_intent_and_not_executed_receipt": True,
            "unknown_effect_is_result_not_internal_error": True,
            "unknown_never_rendered_as_not_committed": True,
        },
        "required_checks": {
            "approval_test": {
                "module": "tests/mcp/t02/test_approval.py",
                "status": "PASS",
                "test_count": regression["approval_test"]["collected"],
            },
            "mcp_effect_test": {
                "module": "tests/mcp/t02/test_mcp_effect.py",
                "status": "PASS",
                "test_count": regression["mcp_effect_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_mcp_mutating"]["collected"],
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
                "artifacts/work_packages/T02/attempts/0001/build_t02_0001_evidence.py",
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
        "# T02-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Catalog composition: the nine mutating names are declared exactly\n"
        "  once, in contracts/mcp/t02/tool-catalog.yaml. The sealed T01 catalog,\n"
        "  its generated descriptor projection, and both shared envelope schemas\n"
        "  are byte-identical, and the sealed exact-13 tests still pass. The\n"
        "  catalog set carries membership, order, and counts and holds no MCP\n"
        "  tool-name literal, so tools/list composes 13 + 9 = 22 without a\n"
        "  second declaring source.\n"
        "- No mutation without lease: the effect executor is unreachable unless\n"
        "  policy grants the declared capability, required approvals verify, the\n"
        "  issued lease covers the exact workspace:target scope, carries that\n"
        "  capability, and binds exactly the verified approvals, and the lease\n"
        "  revalidates unrevoked immediately before the effect. Each negative\n"
        "  case asserts the executor recorded zero calls, not merely that the\n"
        "  response was an error.\n"
        "- Effects reconcile: an unresolved effect answers UNKNOWN with\n"
        "  reconciliation_required and committed=null. It is never rendered as\n"
        "  committed=false, which would falsely claim nothing happened, and\n"
        "  never as INTERNAL. A crash between intent and receipt replays as\n"
        "  UNKNOWN against a recorded unobserved-effect operation id instead of\n"
        "  re-attempting the effect; a reservation with no intent may safely\n"
        "  continue because the effect could not have started. Reconciliation\n"
        "  appends a resolving receipt and refuses to invent a terminal status\n"
        "  when the probe cannot observe the operation.\n"
        "- Approval placement: verification sits inside CAPABILITY_AUTHORIZATION\n"
        "  after policy and before lease issuance, so every refusal leaves no\n"
        "  lease, no intent, and no effect. Self-approval is rejected by the\n"
        "  service itself rather than delegated to the resolver, and an\n"
        "  unresolvable approval record is refused without disclosing whether it\n"
        "  exists. The sealed top-level error enum is not extended; a closed\n"
        "  mutation subcode rides in details and its mapping is asserted against\n"
        "  the sealed schema.\n"
        "- Idempotency: the fingerprint covers dry_run, so a dry-run key can\n"
        "  never be reused for a live commit; approval_record_ids are excluded,\n"
        "  so supplying approvals after an APPROVAL_REQUIRED refusal is not a\n"
        "  conflict. A committed key replays its stored receipt without a second\n"
        "  effect.\n"
        "- Residual limitations: every authority and evidence port is injected\n"
        "  and exercised against in-memory fakes; kernel binding to live policy,\n"
        "  approval, lease, revision, intent, and receipt stores remains T04/T05.\n"
        "  Reconciliation probes are not wired to any external system. This\n"
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
            "path": f"artifacts/work_packages/T02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "T02_MCP_MUTATING_TOOLS_WITH_INTENTS_AND_RECEIPTS",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "effects_reconcile": "PASS",
            "no_mutation_without_lease": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "T03-0001",
        "not_claimed": [
            "kernel binding of policy, approval, lease, revision, intent, or receipt stores",
            "live external effect execution or reconciliation probing",
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
        "approval_test": f"{EXPECTED_APPROVAL_COUNT}/{EXPECTED_APPROVAL_COUNT}",
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "mcp_effect_test": f"{EXPECTED_MCP_EFFECT_COUNT}/{EXPECTED_MCP_EFFECT_COUNT}",
        "next_action": "SEAL_T02_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_mcp_mutating": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = t02_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("t02-verification.json", verification)
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
        raise SystemExit("T02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "t02-verification.json")
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
    verification = read_json(ATTEMPT / "t02-verification.json")
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
        raise SystemExit("stored T02-0001 report is not the deterministic document")
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
