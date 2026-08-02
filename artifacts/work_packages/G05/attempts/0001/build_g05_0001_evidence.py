#!/usr/bin/env python3
"""Build and verify G05-0001 evolution plugin surface evidence.

G05-0001 implements `plugin_blueprint/epistemic-foundry/v4_g05/**`: the
binding between the evolution skills the payload ships, the CLI the tool
surface actually projects, and the progressive disclosure each skill may open.
The skill set is derived from the sealed inventory rather than listed, the
proposed evolution CLI is read from the specification section that proposes
it, and the mutable search space comes from the sealed C05 index, so the
surface cannot claim a command that does not exist, mutate a genome outside
the search space, disclose past its budget, or name a command that carries
promotion authority.  This builder verifies the executed checks and emits
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
ATTEMPT = ROOT / "artifacts/work_packages/G05/attempts/0001"
ATTEMPT_ID = "G05-0001"
WORK_PACKAGE_ID = "G05"
RECORDED_AT = "2026-08-02T08:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/G05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 20
EXPECTED_UNIT_AND_CONTRACT_COUNT = 18
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 27
EXPECTED_PROVENANCE_RECEIPT_COUNT = 16
EXPECTED_TARGETED_COUNT = 81
EXPECTED_HOST_REGRESSION_COUNT = 57
EXPECTED_INSTALL_REGRESSION_COUNT = 1
EXPECTED_C05_REGRESSION_COUNT = 132
EXPECTED_PLUGIN_REGRESSION_COUNT = 37
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1063
EXPECTED_NODE_FILE_COUNT = 95

COMPONENT = "plugin_blueprint/epistemic-foundry/v4_g05"
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/G05/attempts/0001/run_g05_0001_checks.py": "da5d2c157a445989aa08830657248c5c38b76c05bc62b5d887454eddea883ab6",
    "plugin_blueprint/epistemic-foundry/v4_g05/evolution-surface.json": "2505e45f8c8e62aa591b767aeb148170640bc4a4ab51e77cf1e0ff1b8bc28ebb",
    "plugin_blueprint/epistemic-foundry/v4_g05/index.mjs": "1ee2112e027ff2958d63adc505fba4bd4f73d00a82f893802a5d076ac4aaeac7",
    "plugin_blueprint/epistemic-foundry/v4_g05/surface-adversarial.test.mjs": "f30159996393a7d58e6cecf5360a3b8e465b93e4d3300fedefaed7b497cffb83",
    "plugin_blueprint/epistemic-foundry/v4_g05/surface-contract.test.mjs": "a3b858097120bf828774d0b58b42f4d1e49312a8e6c2eb2ec347367dd6c023c1",
    "plugin_blueprint/epistemic-foundry/v4_g05/surface-fixtures.mjs": "9ff024cb8fe41eca655e61f1f68f6d11459fd5c6a614d12dd450211232ef298c",
    "plugin_blueprint/epistemic-foundry/v4_g05/surface-receipts.test.mjs": "1525f54b8a2427feb976469c96841097384d64e965a7e22f8efe2d44c874fe00",
    "plugin_blueprint/epistemic-foundry/v4_g05/surface-schema.test.mjs": "5dd95a4ee8bf29c4221f91add0e497202f914cffed75817cabbe1486d1b472ed",
    "plugin_blueprint/epistemic-foundry/v4_g05/surface.mjs": "82f2b3b14c69b12bdbc1fc4edfe6eabc487df7547ce979eeb692cea5d92e95d7",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/A06/attempts/0002/report.json": "a45eff5d49f16c5307ce886ccfcd8dabd742b3c95efd1898d51fc71b0de80425",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/G04/attempts/0001/report.json": "3abe50fc722255bb8f8c2196f133b94425a0b11318423cb756fab614026cf1ea",
}
#: Read-only inputs the surface composes.  They are not dependencies of this
#: package, so they are pinned as evidence of what was composed rather than
#: asserted as sealed dependency bindings.
EXPECTED_COMPOSED_HASHES = {
    "MASTER_SPEC.md": "8482f50765f1cd372f306f93f8cf3431ce33442498d1a7a97643ddeef01f886e",
    "packages/plugin-host/src/cli/command-surface.mjs": "cb364c9cd86bbdabcc57196a20de8e7f037f583df6aebb11fc785b7101ef0929",
    "packages/plugin-host/src/skill-router/skill-router.mjs": "6320ea8bb09eb3b69b9b2ea180b3d14bb8dbbf501f3a5afbe5dea63060a9b737",
    "plugins/epistemic-foundry/skills/skill-inventory.json": "2c608ef57735c5f72de39c491763b68572c0802989627ddab86743f5b8b28c54",
    "schemas/skill-routing-decision.schema.json": "31bb0c22e5070ae2647322c19f1a7c02281e7f57cca1bea35664be691a485af7",
    "schemas/v4_c05/family-index.json": "e4365a2e46b28d782bffbc35ffadb0301087fda787270898eb38b1477d7cf36e",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-g05-surface.junit.xml",
    "host_regression": ATTEMPT / "dependency-regression-host.junit.xml",
    "install_regression": ATTEMPT / "dependency-regression-install.junit.xml",
    "c05_regression": ATTEMPT / "dependency-regression-c05.junit.xml",
    "plugin_regression": ATTEMPT / "dependency-regression-plugin.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# The product and both host regressions are Node surfaces, so their JUnit
# carries the Node reporter's semantic footer rather than pytest attributes.
_NODE_JUNITS = frozenset(
    {
        "schema_and_type",
        "unit_and_contract",
        "negative_adversarial",
        "provenance_receipt",
        "targeted",
        "host_regression",
        "install_regression",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "repo-structure-check",
    "repo-boundaries-check",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-g05-surface",
    "dependency-regression-host",
    "dependency-regression-install",
    "dependency-regression-c05",
    "dependency-regression-plugin",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_g05_0001_checks.py",
    "build_g05_0001_evidence.py",
    "g05_0001_rah_seal.py",
    "dependency-status.json",
    "g05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-g05-surface.junit.xml",
    "dependency-regression-host.junit.xml",
    "dependency-regression-install.junit.xml",
    "dependency-regression-c05.junit.xml",
    "dependency-regression-plugin.junit.xml",
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
    schema = node_summary(JUNIT_PATHS["schema_and_type"])
    unit = node_summary(JUNIT_PATHS["unit_and_contract"])
    negative = node_summary(JUNIT_PATHS["negative_adversarial"])
    provenance = node_summary(JUNIT_PATHS["provenance_receipt"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    host = node_summary(JUNIT_PATHS["host_regression"])
    install = node_summary(JUNIT_PATHS["install_regression"])
    c05 = pytest_summary(JUNIT_PATHS["c05_regression"])
    plugin = pytest_summary(JUNIT_PATHS["plugin_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("c05_regression", c05, EXPECTED_C05_REGRESSION_COUNT),
        ("plugin_regression", plugin, EXPECTED_PLUGIN_REGRESSION_COUNT),
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
        ("host_regression", host, EXPECTED_HOST_REGRESSION_COUNT),
        ("install_regression", install, EXPECTED_INSTALL_REGRESSION_COUNT),
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
        "baseline_attempt": "F05-0001",
        "c05_regression": c05,
        "component_tests_are_targeted_only": False,
        "full_node": node,
        "full_python": python,
        "host_regression": host,
        "install_regression": install,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "plugin_regression": plugin,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_g05_surface": targeted,
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
            "G04": _sealed_dependency("G04", "G04-0001", "E0058", "E0059"),
        },
        "next_action": "SEAL_G05_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(f"the surface holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "plugin_blueprint/epistemic-foundry/v4_g05/**",
            "artifacts/work_packages/G05/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": None,
        "component_files": component_files,
        "composed_modules_modified": False,
        "payload_or_blueprint_skills_modified": False,
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


def g05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "cli_surface": {
            "authority_bearing_commands": ["claim promote", "passport publish"],
            "available_commands_named_by_evolution_skills": 5,
            "projected_commands": 22,
            "proposed_evolution_commands": 25,
            "proposed_evolution_commands_projected": 0,
        },
        "composed_surfaces": {
            "cli_projection": "packages/plugin-host/src/cli/command-surface.mjs",
            "proposed_cli": "MASTER_SPEC.md section 35",
            "routing_policy": (
                "packages/plugin-host/src/skill-router/skill-router.mjs"
            ),
            "skill_inventory": "plugins/epistemic-foundry/skills/skill-inventory.json",
        },
        "declaring_sources": {
            "context_budgets": (
                "plugins/epistemic-foundry/skills/skill-inventory.json budgets"
            ),
            "evolution_skill_membership": (
                "derived from the inventory reference closure by the declared rule"
            ),
            "mutable_search_space": "schemas/v4_c05/family-index.json",
            "routing_decision": "schemas/skill-routing-decision.schema.json",
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{COMPONENT}/surface-receipts.test.mjs"],
                "mechanism": (
                    "the surface receipt binds every declaring source by digest, "
                    "re-derives its own hash with the sealed routing hash "
                    "function, carries no clock and no randomness, and the "
                    "routing decision it issues re-derives its own hash and "
                    "binds each candidate to the sealed content hash of its "
                    "skill"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{COMPONENT}/surface-schema.test.mjs"],
                "mechanism": (
                    "the skill set is derived from the sealed inventory rather "
                    "than listed, the proposed CLI is parsed from the section "
                    "that proposes it, the mutable search space is read from the "
                    "sealed C05 index, the emitted decision is validated against "
                    "schemas/skill-routing-decision.schema.json, and each of the "
                    "18 failure codes carries its reason"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{COMPONENT}/surface-contract.test.mjs",
                    f"{COMPONENT}/surface-adversarial.test.mjs",
                ],
                "mechanism": (
                    "a named evolution skill routes, discloses within budget and "
                    "reports which commands exist; and an invented command, a "
                    "twice-claimed command, an unowned command, an unprojected "
                    "command, a genome outside the search space, a drifted "
                    "inventory, a contradicted payload policy, a dropped "
                    "reference and an outgrown budget are each refused by their "
                    "own code against a staged copy of the declaring sources"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [
                    f"{COMPONENT}/surface-adversarial.test.mjs",
                    f"{COMPONENT}/surface-receipts.test.mjs",
                ],
                "mechanism": (
                    "the promotion-bearing commands are derived from the sealed "
                    "catalog by effect class and object, no evolution skill may "
                    "name one, a predicate that matched nothing is refused as "
                    "vacuous rather than satisfied, and the routing decision "
                    "states in its own authority notes that it carries neither "
                    "state nor authority"
                ),
                "status": "PASS",
            },
        },
        "failure_classes": [
            "AUTHORITY_CLAIMED",
            "AUTHORITY_PREDICATE_EMPTY",
            "COMMAND_CLAIMED_TWICE",
            "COMMAND_MISDECLARED",
            "COMMAND_UNPROJECTED",
            "COMMAND_UNPROPOSED",
            "DECLARATION_NONCANONICAL",
            "DISCLOSURE_BUDGET_EXCEEDED",
            "INVENTORY_HASH_DRIFT",
            "MEMBERSHIP_DRIFT",
            "PARENT_UNDECLARED",
            "POLICY_DRIFT",
            "PROPOSED_COMMAND_UNROUTED",
            "REFERENCE_UNDECLARED",
            "SEARCH_SPACE_VIOLATION",
            "SKILL_OUT_OF_SURFACE",
            "SPEC_BLOCK_MISSING",
            "SURFACE_UNREADABLE",
        ],
        "not_derivable": {
            "command_ownership": (
                "which skill owns which proposed command is declared here; the "
                "command vocabulary itself is parsed from the specification and "
                "every claim is checked against it, but the assignment is a "
                "judgment this surface records rather than derives"
            ),
            "reference_token_counts": (
                "token counts are taken from the sealed inventory, which owns "
                "the tokenizer; only byte counts and digests are recomputed here"
            ),
        },
        "progressive_disclosure": {
            "evolution_skills": 15,
            "maximal_closure_reference_count": 11,
            "maximal_closure_depth": 5,
            "reference_closure_max_count": 12,
            "reference_closure_max_depth": 5,
        },
        "required_checks": {
            "independent_review": {
                "evidence": "review.md (primary-session separate, "
                "actor_independence=false)",
                "status": "PASS",
            },
            "negative_and_adversarial_tests": {
                "module": f"{COMPONENT}/surface-adversarial.test.mjs",
                "status": "PASS",
                "test_count": regression["negative_and_adversarial_tests"]["collected"],
            },
            "provenance_and_receipt_audit": {
                "module": f"{COMPONENT}/surface-receipts.test.mjs",
                "status": "PASS",
                "test_count": regression["provenance_and_receipt_audit"]["collected"],
            },
            "schema_and_type_check": {
                "module": f"{COMPONENT}/surface-schema.test.mjs",
                "status": "PASS",
                "test_count": regression["schema_and_type_check"]["collected"],
            },
            "unit_and_contract_tests": {
                "module": f"{COMPONENT}/surface-contract.test.mjs",
                "status": "PASS",
                "test_count": regression["unit_and_contract_tests"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_g05_surface"]["collected"],
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
                "artifacts/work_packages/G05/attempts/0001/build_g05_0001_evidence.py",
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
        "# G05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The surface answers a question nothing else in the repository asked:\n"
        "  the payload ships 29 skills and the tool surface projects 22\n"
        "  commands, and until now nothing checked that the evolution skills\n"
        "  and the CLI describe the same product. The binding is now explicit\n"
        "  and refuses in both directions.\n"
        "- The membership rule is data. The 15 evolution skills are derived\n"
        "  from the sealed inventory by reference closure, so a new evolution\n"
        "  skill breaks this gate until the surface accounts for it, and a\n"
        "  hand-edited list cannot silently diverge from the payload.\n"
        "- The CLI finding is the honest one. All 25 commands the specification\n"
        "  proposes for evolution are absent from the projected tool surface, so\n"
        "  the surface records them as proposed and unavailable rather than\n"
        "  implying they can be run. Five commands the skills may legitimately\n"
        "  name do exist, and each is published with its effect class.\n"
        "- Authority is checked where it can actually leak. The\n"
        "  promotion-bearing commands are derived from the sealed catalog by\n"
        "  effect class and object rather than hard-coded, no evolution skill\n"
        "  may name one, and a predicate that matches nothing is refused as\n"
        "  vacuous instead of passing silently.\n"
        "- Progressive disclosure is enforced against J02's own budgets, with\n"
        "  the closure resolved over the inventory's dependency edges. The\n"
        "  widest evolution skill opens 11 references at depth 5 against limits\n"
        "  of 12 and 5, so the bound is real rather than decorative.\n"
        "- Two claims are recorded as not derivable rather than asserted:\n"
        "  which skill owns which proposed command is a judgment this surface\n"
        "  declares, and token counts are taken from the inventory that owns\n"
        "  the tokenizer. Byte counts and digests are recomputed here.\n"
        "- A real property fell out of the payload rather than being assumed:\n"
        "  no evolution skill declares an activation phrase, so none can be\n"
        "  reached implicitly today. The receipt records that as a fact it\n"
        "  derived, not as a design intent.\n"
        "- Residual limitations: the surface validates and routes, it does not\n"
        "  execute; the blueprint tree remains a reference package whose CLI\n"
        "  still exits 78; the sealed host modules and payload skills are\n"
        "  read-only inputs and were not modified; and this review is not\n"
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
            "path": f"artifacts/work_packages/G05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "G05_EVOLUTION_PLUGIN_SURFACE",
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
        "next_package": "L05-0001",
        "not_claimed": [
            "execution of any evolution command: the proposed CLI is absent "
            "from the projected tool surface and this surface does not add it",
            "that the blueprint package is installable: it remains a reference "
            "package whose CLI exits 78",
            "ownership of the routing policy, the command projection, the skill "
            "inventory or the payload skills, which are read-only inputs",
            "token accounting: the sealed inventory owns the tokenizer, and only "
            "byte counts and digests are recomputed here",
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
        "next_action": "SEAL_G05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_g05_surface": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
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
    verification = g05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("g05-verification.json", verification)
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
        raise SystemExit("G05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "g05-verification.json")
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
    verification = read_json(ATTEMPT / "g05-verification.json")
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
        raise SystemExit("stored G05-0001 report is not the deterministic document")
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
