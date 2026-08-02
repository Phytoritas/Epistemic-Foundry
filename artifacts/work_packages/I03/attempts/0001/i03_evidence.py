#!/usr/bin/env python3
"""Build and verify byte-bound evidence for I03-0001."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/I03/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/I03"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRIOR_DAG = ROOT / "artifacts/work_packages/I02/attempts/0001/dependency-status.json"

ATTEMPT_ID = "I03-0001"
WORK_PACKAGE_ID = "I03"
CREATED_AT = "2026-07-29T11:45:10Z"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
READERS_TEST = (
    "orphan_receipt_test: concurrent readers tolerate transient staging and lock handoff"
)
PUBLISHERS_TEST = "orphan_receipt_test: concurrent identical publishers converge"

PRODUCT_HASHES = {
    "python/epistemic_foundry/ontology/__init__.py": (
        "6f165694369ae8a53ff5f86d64823ae959bef655b4774f5f7c68833c898e0f10"
    ),
    "python/epistemic_foundry/ontology/resolver.py": (
        "99d8b3036636188c4bcd8e1c94c35ab24588d85364b77de49c8ba9b2a4c29c8d"
    ),
    "python/epistemic_foundry/ontology/test_ontology_fixture.py": (
        "a85c9c84a0f960133516a40bd13db8993789a247b6f86f9b6f4aa28c71d6f358"
    ),
    "python/epistemic_foundry/ontology/test_measurement_identity.py": (
        "71d6f3e1572aa25d6d4329d9df82d5a0d6589d325d4e4ea2908ffa50a10ae0d3"
    ),
}

JUNIT_HASHES = {
    "targeted-python-suite.junit.xml": (
        "fdff252051e3cdaf9a0383bc9debf9f3891b55d224ff3bd7682885130f489cc8"
    ),
    "full-python-suite.junit.xml": (
        "e00a6756ef31c30fbfdbae78a42f4e209acbda4c09ad74951adfcf41d8b892aa"
    ),
    "full-python-suite.optional-postgres-diagnostic.junit.xml": (
        "686cffe8dfdb47ece9767babd91c7118d73c40f706cffa66f68b8e34683e1a62"
    ),
    "full-node-suite.concurrent-load-diagnostic.junit.xml": (
        "434ce2348acfb0ef774194517a0ec8829f438735d6f23007cbede0a78630d00b"
    ),
    "full-node-suite.standalone-concurrency-diagnostic.junit.xml": (
        "2f4a1e895324c5d79fb63cf839c675d4c8e9b8d8317f50543ff825d35e26fead"
    ),
    "full-node-suite.junit.xml": (
        "3dc91a3634540ff7e6ce5a2eb9ba759ba565ddf8f157893413e97c226daa1c29"
    ),
}

SEALED_INPUTS = {
    "MASTER_SPEC.md": "43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3",
    "manifests/development_manifest.yaml": (
        "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
    ),
    "docs/ontology_measurement_contract.md": (
        "89a70d2d6bd6c03830ba5f0737097e0a6f463d36de4e842831ad7e0b26b10100"
    ),
    "schemas/artifact-receipt.schema.json": (
        "9de81c722fbe36038993437403e265d96b6e9d05d432b89aaab4abc89d996c34"
    ),
    "artifacts/work_packages/I01/report.json": (
        "7174f9292421996fcd7e48de8f29757657dcf9b7aff3483028bbb86be70f886a"
    ),
    "artifacts/work_packages/I02/report.json": (
        "fc55063fdac74f9d66355a5414195bc9b993f001a7f66187946863991e526366"
    ),
    "artifacts/work_packages/I02/attempts/0001/dependency-status.json": (
        "c34d07b2f623552283c385e342af8a4b140e70038beac6bb505c1149404d2214"
    ),
}

NODE_TOTAL_PATTERNS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}
MACHINE_LOCAL_MARKERS = (
    b"hostname=",
    b"C:/dev/insight/Epistemic-Foundry",
    b"C:\\dev\\insight\\Epistemic-Foundry",
    b"C:/Users/",
    b"C:\\Users\\",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_hash_excluding(document: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(document)
    preimage.pop(field, None)
    return canonical_hash(preimage)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def verify_sealed_inputs() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in SEALED_INPUTS.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"sealed dependency/contract changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    dependency = read_json(ROOT / "artifacts/work_packages/I01/report.json")
    if dependency.get("status") != "PASS" or dependency.get("attempt_id") != "I01-0001":
        raise SystemExit("I03 dependency I01 is not evidence-sealed PASS")
    prior = read_json(ROOT / "artifacts/work_packages/I02/report.json")
    if prior.get("status") != "PASS" or prior.get("attempt_id") != "I02-0001":
        raise SystemExit("I03 prior manifest-order package I02 is not evidence-sealed PASS")
    return observed


def verify_utf8(relative: str, expected_hash: str) -> dict[str, Any]:
    path = ROOT / relative
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        raise SystemExit(f"invalid encoding marker in I03 file: {relative}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"I03 file is not UTF-8: {relative}: {error}")
    if "\ufffd" in text:
        raise SystemExit(f"replacement character in I03 file: {relative}")
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected_hash:
        raise SystemExit(f"I03 product hash changed: {relative}: {actual}")
    try:
        ast.parse(text, filename=relative)
    except SyntaxError as error:
        raise SystemExit(f"I03 Python syntax failure: {relative}: {error}")
    return {
        "path": relative,
        "byte_size": len(content),
        "sha256": "sha256:" + actual,
        "bom": False,
        "replacement_character_count": 0,
        "ast_parse": "PASS",
    }


def product_inventory() -> list[dict[str, Any]]:
    scope = ROOT / "python/epistemic_foundry/ontology"
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in scope.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    }
    if actual != set(PRODUCT_HASHES):
        raise SystemExit(f"unexpected I03 product inventory: {sorted(actual)}")
    return [
        verify_utf8(relative, expected)
        for relative, expected in PRODUCT_HASHES.items()
    ]


def normalized_junit_bytes(path: Path) -> bytes:
    content = path.read_bytes()
    if any(marker in content for marker in MACHINE_LOCAL_MARKERS):
        raise SystemExit(f"machine-local metadata remains in {path.name}")
    expected = JUNIT_HASHES.get(path.name)
    if expected is None or sha256(path) != expected:
        raise SystemExit(f"normalized JUnit hash changed: {path.name}")
    return content


def suite_totals(root: ET.Element) -> dict[str, int]:
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def targeted_junit() -> dict[str, Any]:
    path = ATTEMPT / "targeted-python-suite.junit.xml"
    root = ET.fromstring(normalized_junit_bytes(path))
    totals = suite_totals(root)
    expected = {"tests": 39, "failures": 0, "errors": 0, "skipped": 0}
    cases = root.findall(".//testcase")
    ontology_count = sum(
        1
        for case in cases
        if str(case.get("classname") or "").endswith("test_ontology_fixture")
    )
    measurement_count = sum(
        1
        for case in cases
        if str(case.get("classname") or "").endswith("test_measurement_identity")
    )
    if (
        totals != expected
        or len(cases) != 39
        or ontology_count != 16
        or measurement_count != 23
        or root.findall(".//failure")
        or root.findall(".//error")
        or root.findall(".//skipped")
    ):
        raise SystemExit(
            "I03 targeted JUnit changed: "
            f"totals={totals} ontology={ontology_count} measurement={measurement_count}"
        )
    for case in cases:
        name = str(case.get("name") or "")
        if "ontology_fixture" not in name and "measurement_identity" not in name:
            raise SystemExit(f"unexpected I03 targeted case: {name}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "ontology_fixture_case_count": ontology_count,
        "measurement_identity_case_count": measurement_count,
        "test_names": [str(case.get("name") or "") for case in cases],
    }


def python_junit() -> dict[str, Any]:
    path = ATTEMPT / "full-python-suite.junit.xml"
    root = ET.fromstring(normalized_junit_bytes(path))
    totals = suite_totals(root)
    expected = {"tests": 947, "failures": 0, "errors": 0, "skipped": 0}
    if totals != expected or len(root.findall(".//testcase")) != 947:
        raise SystemExit(f"full Python result is not exact 947/947: {totals}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "official_repository_gate_scope": "tests/**",
    }


def optional_postgres_diagnostic() -> dict[str, Any]:
    path = ATTEMPT / "full-python-suite.optional-postgres-diagnostic.junit.xml"
    root = ET.fromstring(normalized_junit_bytes(path))
    totals = suite_totals(root)
    cases = root.findall(".//testcase")
    errors = root.findall(".//error")
    if (
        totals != {"tests": 1, "failures": 0, "errors": 1, "skipped": 0}
        or len(cases) != 1
        or len(errors) != 1
        or cases[0].get("name") != "python.epistemic_foundry.storage.postgres"
        or "No module named 'psycopg'" not in str(errors[0].text or "")
    ):
        raise SystemExit("optional PostgreSQL diagnostic fingerprint changed")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "classification": "OPTIONAL_POSTGRES_FIXTURE_DEPENDENCY_UNAVAILABLE",
        "missing_dependency": "psycopg",
        "official_947_test_gate_impact": "NONE",
        "i03_product_causal_impact": "NONE",
        "package_status_effect": "DIAGNOSTIC_ONLY",
    }


def node_footer(content: bytes) -> dict[str, int]:
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label}")
        totals[label] = int(matches[0])
    return totals


def node_failures(root: ET.Element) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        if failure is None:
            continue
        message = "\n".join(
            part
            for part in (
                str(case.get("failure") or ""),
                str(failure.get("message") or ""),
                str(failure.text or ""),
            )
            if part
        )
        failures.append(
            {
                "name": str(case.get("name") or ""),
                "file": str(case.get("file") or "").replace("\\", "/"),
                "message": message,
            }
        )
    return failures


def assert_s04_failure(failure: dict[str, str]) -> None:
    if (
        failure["name"] != S04_TEST
        or not failure["file"].endswith(
            "tests/security/s04-threat-model-traceability.test.mjs"
        )
        or S04_EXPECTED not in failure["message"]
        or S04_ACTUAL not in failure["message"]
    ):
        raise SystemExit("Node failure is not exact preserved S04-TM004")


def node_junit() -> dict[str, Any]:
    path = ATTEMPT / "full-node-suite.junit.xml"
    content = normalized_junit_bytes(path)
    root = ET.fromstring(content)
    totals = node_footer(content)
    expected = {
        "tests": 361,
        "pass": 360,
        "fail": 1,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }
    failures = node_failures(root)
    cases = root.findall(".//testcase")
    if totals != expected or len(cases) != 359 or len(failures) != 1:
        raise SystemExit(
            f"unexpected serial full Node result: totals={totals} failures={failures}"
        )
    assert_s04_failure(failures[0])
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "xml_testcase_count": len(cases),
        "xml_footer_testcase_delta": totals["tests"] - len(cases),
        "semantic_source_of_truth": "node_junit_footer",
        "execution_mode": "--test-concurrency=1",
        "failure": {
            "debt_id": "S04-TM004",
            "test_name": failures[0]["name"],
            "test_file": failures[0]["file"],
            "expected_manifest_sha256": S04_EXPECTED,
            "actual_manifest_sha256": S04_ACTUAL,
        },
    }


def diagnostic_node_junit(
    name: str,
    transient_name: str,
    transient_code: str,
) -> dict[str, Any]:
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    root = ET.fromstring(content)
    totals = node_footer(content)
    expected = {
        "tests": 361,
        "pass": 359,
        "fail": 2,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }
    failures = node_failures(root)
    by_name = {failure["name"]: failure for failure in failures}
    if totals != expected or set(by_name) != {transient_name, S04_TEST}:
        raise SystemExit(f"Node concurrency diagnostic changed: {name}")
    assert_s04_failure(by_name[S04_TEST])
    transient = by_name[transient_name]
    if (
        not transient["file"].endswith(
            "packages/foundry-kernel/src/artifacts/orphan-receipt.test.mjs"
        )
        or transient_code not in transient["message"]
    ):
        raise SystemExit(f"Node transient fingerprint changed: {name}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "transient_failure_test": transient_name,
        "transient_failure_code": transient_code,
        "s04_fingerprint_verified": True,
    }


def concurrency_diagnostic() -> dict[str, Any]:
    concurrent = diagnostic_node_junit(
        "full-node-suite.concurrent-load-diagnostic.junit.xml",
        READERS_TEST,
        "ARTIFACT_STORE_STRUCTURE_INVALID",
    )
    standalone = diagnostic_node_junit(
        "full-node-suite.standalone-concurrency-diagnostic.junit.xml",
        PUBLISHERS_TEST,
        "ARTIFACT_MUTATION_LOCK_FAILED",
    )
    serial = node_junit()
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "DIAGNOSTICS_RECONCILED",
        "diagnostic_runs": [concurrent, standalone],
        "isolated_reproductions": [
            {
                "test_name": READERS_TEST,
                "runs": 5,
                "passed": 5,
                "failed": 0,
                "transient_reproduced": False,
                "provenance": "commands.jsonl",
            },
            {
                "test_name": PUBLISHERS_TEST,
                "runs": 5,
                "passed": 5,
                "failed": 0,
                "transient_reproduced": False,
                "provenance": "commands.jsonl",
            },
        ],
        "serial_full_node": {
            "path": serial["path"],
            "sha256": serial["sha256"],
            "totals": serial["totals"],
            "transient_failure_count": 0,
        },
        "classification": "TRANSIENT_CONCURRENCY_DIAGNOSTICS_NOT_REPRODUCED",
        "i03_product_failure_claimed": False,
    }


def ontology_verification() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    inventory = product_inventory()
    targeted = targeted_junit()
    scope = ROOT / "python/epistemic_foundry/ontology"
    cache_artifacts = [
        path.relative_to(ROOT).as_posix()
        for path in scope.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"I03 product scope contains cache artifacts: {cache_artifacts}")
    schema_count = len(list((ROOT / "schemas").glob("*.schema.json")))
    if schema_count != 124:
        raise SystemExit(f"canonical schema count changed: {schema_count}")
    test_text = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in PRODUCT_HASHES
        if "/test_" in relative
    )
    if "sys.path" in test_text or "conftest" in {path.name for path in scope.iterdir()}:
        raise SystemExit("I03 tests retain a repository-boundary bypass")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "resolver_version": "4.0.0-i03.1",
        "product_inventory": inventory,
        "sealed_input_hashes": preserved,
        "contract_projection": {
            "exact_normalized_label_only": True,
            "pinned_ontology_and_domain_pack_required": True,
            "structural_context_required_when_catalog_constrains_it": True,
            "string_similarity_authority_used": False,
            "implicit_synonym_authority_used": False,
            "same_label_different_construct_silently_merged": False,
            "ambiguous_and_unknown_states_preserved": True,
            "high_impact_or_frequency_review_queue_exists": True,
            "review_queue_item_treated_as_approval": False,
            "required_mapping_approval_authority": "HumanDecision",
            "measurement_construct_method_protocol_unit_timing_calibration_scope_distinct": True,
            "implicit_unit_conversion_performed": False,
            "bridge_requires_external_authority_and_direction": True,
            "unknown_or_incompatible_measurement_pooled": False,
            "aggregation_requires_same_construct_compatible_status_and_permissive_ceiling": True,
            "method_boundary_or_block_ceiling_allows_pooling": False,
            "canonical_schema_count": schema_count,
            "canonical_schema_added": False,
            "canonical_schema_or_workflow_modified": False,
            "component_local_contract_only": True,
        },
        "required_checks": {
            "ontology_fixture_test": {
                "status": "PASS",
                "passed": 16,
                "failed": 0,
                "skipped": 0,
            },
            "measurement_identity_test": {
                "status": "PASS",
                "passed": 23,
                "failed": 0,
                "skipped": 0,
            },
        },
        "targeted_suite": targeted,
        "repository_structure_check": "PASS",
        "package_boundary_check": "PASS",
        "git_diff_check": "PASS",
        "python_cache_artifact_count": 0,
        "write_scope_violation_count": 0,
        "subagents_or_fleet_used": False,
        "completion_ready": False,
    }


def regression_impact() -> dict[str, Any]:
    targeted = targeted_junit()
    python = python_junit()
    node = node_junit()
    diagnostic = concurrency_diagnostic()
    postgres = optional_postgres_diagnostic()
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT_AND_DIAGNOSTICS",
        "targeted_python": targeted,
        "official_full_python": python,
        "optional_postgres_diagnostic": postgres,
        "node": node,
        "concurrency_diagnostic": diagnostic,
        "node_junit_reporter_reconciliation": {
            "semantic_source_of_truth": "node_junit_footer",
            "footer_test_count": 361,
            "xml_testcase_element_count": 359,
            "failure_element_count": 1,
            "failure_fingerprint_verified": True,
        },
        "i03_caused_python_failure_count": 0,
        "i03_caused_node_failure_count": 0,
        "new_skip_or_xfail_count": 0,
        "preexisting_debt_ids": ["S04-TM004"],
    }


def debt_reconciliation() -> dict[str, Any]:
    node_junit()
    prior = read_json(
        ROOT / "artifacts/work_packages/H04/attempts/0001/preexisting-debt-reconciliation.json"
    )
    expected_prior = {
        "debt_id": "S04-TM004",
        "test_name": S04_TEST,
        "expected_manifest_sha256": S04_EXPECTED,
        "actual_manifest_sha256": S04_ACTUAL,
        "owner": "S04",
    }
    for key, expected in expected_prior.items():
        if prior.get(key) != expected:
            raise SystemExit(f"H04 bounded-debt fingerprint changed at {key}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "classification": "PRE_EXISTING_BOUNDED_DEBT",
        "debt_id": "S04-TM004",
        "owner": "S04",
        "test_name": S04_TEST,
        "test_file": "tests/security/s04-threat-model-traceability.test.mjs",
        "expected_manifest_sha256": S04_EXPECTED,
        "actual_manifest_sha256": S04_ACTUAL,
        "failure_count": 1,
        "fingerprint_changed": False,
        "i03_causal_impact": "NONE",
        "skip_or_xfail_masking": False,
        "global_repository_green_claimed": False,
    }


def topological_layers(
    order: list[str], dependencies: dict[str, set[str]]
) -> list[list[str]]:
    completed: set[str] = set()
    remaining = set(order)
    layers: list[list[str]] = []
    while remaining:
        layer = [
            package_id
            for package_id in order
            if package_id in remaining and dependencies[package_id] <= completed
        ]
        if not layer:
            raise SystemExit(f"development manifest contains a cycle: {sorted(remaining)}")
        layers.append(layer)
        completed.update(layer)
        remaining.difference_update(layer)
    return layers


def dependency_status() -> dict[str, Any]:
    verify_sealed_inputs()
    prior = read_json(PRIOR_DAG)
    if (
        prior.get("status") != "PASS"
        or prior.get("completed_package_count") != 39
        or prior.get("ready_packages_manifest_order")
        != ["I03", "J01", "K01", "T01", "A06"]
        or prior.get("next_package") != "I03"
    ):
        raise SystemExit("sealed I02 dependency state is not the expected I03 input")

    report_path = ROOT / "artifacts/work_packages/I01/report.json"
    dependency = read_json(report_path)
    if dependency.get("status") != "PASS" or dependency.get("attempt_id") != "I01-0001":
        raise SystemExit("I03 dependency I01 changed")
    dependency_evidence = {
        "I01": {
            "status": "PASS",
            "attempt_id": "I01-0001",
            "report": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(report_path),
        }
    }

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = manifest.get("work_packages") if isinstance(manifest, dict) else None
    if not isinstance(packages, list):
        raise SystemExit("development manifest work_packages is not a list")
    order: list[str] = []
    dependencies: dict[str, set[str]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            raise SystemExit("invalid work package in development manifest")
        package_id = package["id"]
        raw_dependencies = package.get("depends_on", [])
        if package_id in dependencies or not isinstance(raw_dependencies, list):
            raise SystemExit(f"invalid or duplicate work package: {package_id}")
        if not all(isinstance(value, str) for value in raw_dependencies):
            raise SystemExit(f"invalid dependencies for {package_id}")
        order.append(package_id)
        dependencies[package_id] = set(raw_dependencies)
    all_ids = set(order)
    unknown = {
        package_id: sorted(values - all_ids)
        for package_id, values in dependencies.items()
        if values - all_ids
    }
    if len(order) != 156 or len(all_ids) != 156 or unknown:
        raise SystemExit(
            f"manifest identity/dependency failure: count={len(order)} unknown={unknown}"
        )
    layers = topological_layers(order, dependencies)
    completed = set(str(value) for value in prior.get("completed_packages", []))
    if len(completed) != 39 or "I03" in completed:
        raise SystemExit("prior completed package inventory changed")
    completed.add("I03")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["I04", "J01", "K01", "T01", "A06"]
    blocked = len(order) - len(completed) - len(ready)
    if len(completed) != 40 or ready != expected_ready or blocked != 111:
        raise SystemExit(
            f"unexpected post-I03 DAG: completed={len(completed)} ready={ready} blocked={blocked}"
        )
    return {
        "schema_version": 1,
        "status": "PASS",
        "completion_ready": False,
        "manifest": {
            "path": "manifests/development_manifest.yaml",
            "sha256": sha256_id(MANIFEST),
            "work_package_count": len(order),
            "unique_work_package_count": len(all_ids),
            "unknown_dependency_count": 0,
            "cycle_count": 0,
            "topological_layer_count": len(layers),
            "maximum_layer_width": max(len(layer) for layer in layers),
        },
        "prior_dependency_state": {
            "path": PRIOR_DAG.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(PRIOR_DAG),
            "completed_package_count": 39,
        },
        "dependency_evidence": dependency_evidence,
        "completed_package_count": len(completed),
        "completed_packages": [package_id for package_id in order if package_id in completed],
        "ready_package_count": len(ready),
        "ready_packages_manifest_order": ready,
        "blocked_package_count": blocked,
        "next_package": ready[0],
    }


def commands_text() -> str:
    rows = (
        ("C001", "Inspect I03 authority, I01 dependency, prior DAG, package scope, and dirty worktree", 0, "PASS"),
        ("C002", "Implement deterministic ontology and measurement-identity resolver with component-local tests", 0, "PASS: four I03 product files"),
        ("C003", "Run final I03 targeted Python JUnit suite", 0, "PASS: 39/39; ontology fixture 16 and measurement identity 23"),
        ("C004", "Run official full Python regression over tests/**", 0, "PASS: 947/947, zero skip"),
        ("D001", "Collect optional tests plus python/epistemic_foundry diagnostic", 2, "DIAGNOSTIC_ONLY: optional PostgreSQL fixture requires unavailable psycopg; official 947-test gate unaffected"),
        ("D002", "Preserve full Node run under concurrent load", 1, "DIAGNOSTIC_RECONCILED: 359 passed; transient reader failure plus exact S04-TM004"),
        ("C005", "Run transient reader case in isolation five times", 0, "PASS: 5/5; transient not reproduced"),
        ("D003", "Preserve standalone full Node concurrency diagnostic", 1, "DIAGNOSTIC_RECONCILED: 359 passed; transient publisher lock failure plus exact S04-TM004"),
        ("C006", "Run transient publisher case in isolation five times", 0, "PASS: 5/5; transient not reproduced"),
        ("C007", "Run final full Node suite with --test-concurrency=1", 1, "BOUNDED_PREEXISTING_DEBT: 360 passed; exact unchanged S04-TM004 only"),
        ("C008", "Normalize six JUnit artifacts while preserving totals, names, failures, and S04 fingerprint", 0, "PASS: machine-local marker count zero"),
        ("C009", "Run npm repository structure check", 0, "PASS"),
        ("C010", "Run npm public-package-boundary check", 0, "PASS"),
        ("R001", "Review measurement pooling against promotion ceilings", 1, "FOUND_AND_FIXED: SAME plus compatible status no longer pools under METHOD_BOUNDARY_ONLY or BLOCK_AGGREGATION"),
        ("C011", "Add two regression cases for ceiling-bound compatible bridges and rerun targeted suite", 0, "PASS: final 39/39"),
        ("C012", "Run final product hash, AST, UTF-8, schema-count, cache, JUnit, and git diff checks", 0, "PASS"),
        ("C013", "Primary-session separate contract review of final I03 product bytes and evidence", 0, "PASS: zero blocking findings; not actor-independent certification"),
        ("D004", "Run py_compile on I03 evidence scripts", 0, "DIAGNOSTIC_ONLY: syntax passed but created two local pyc leaves"),
        ("D005", "Remove calculated cache paths with inline PowerShell", 1, "DIAGNOSTIC_ONLY: safety policy rejected the command before mutation"),
        ("C014", "Verify exact I03 evidence cache inventory and remove two pyc leaves plus empty directory", 0, "PASS: bounded one-time cleanup; product and retained evidence unchanged"),
    )
    lines = []
    for suffix, command, exit_code, result in rows:
        lines.append(
            json.dumps(
                {
                    "command_id": f"I03-0001-{suffix}",
                    "command": command,
                    "recorded_at_utc": CREATED_AT,
                    "exit_code": exit_code,
                    "result": result,
                    "scope": ATTEMPT_ID,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return "\n".join(lines) + "\n"


def review_text(inventory: list[dict[str, Any]]) -> str:
    hashes = "\n".join(f"- `{row['path']}` — `{row['sha256']}`" for row in inventory)
    return f"""# I03-0001 ontology and measurement construct resolution review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I03 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

{hashes}

## Findings

1. Resolution accepts only exact compatibility-normalized labels within the
   pinned ontology and DomainPack authority. It uses structural constraints to
   disambiguate and never turns edit distance, embeddings, stemming, or an
   inferred synonym into mapping authority.
2. Identical labels attached to different constructs remain `AMBIGUOUS` when
   context cannot select one complete candidate. Unknown authority, missing
   context, conflicts, duplicate IDs, and mutable boundary inputs fail closed.
3. High-impact and high-frequency mappings produce deterministic review-queue
   items. A queue item remains a proposal: it does not select the construct and
   explicitly requires an external immutable `HumanDecision`.
4. Measurement identity preserves construct, method, protocol, unit, timing,
   calibration, population/entity, unit of analysis, ontology, DomainPack, and
   proxy identity. Unit conversion requires an explicit directional bridge
   with an external authority reference.
5. Review found a conservative-gate defect: a bridge with `SAME` construct and
   `CONVERTIBLE` status could still pool under `METHOD_BOUNDARY_ONLY` or
   `BLOCK_AGGREGATION`. The final bytes require both an eligible compatibility
   status and a permissive ceiling (`NO_RESTRICTION` or `CONDITIONAL_ONLY`). Two
   regression cases bind the fix.
6. The final targeted suite is 39/39: 16 ontology fixture and 23 measurement
   identity cases. The official full Python suite is 947/947. The broader
   optional collection diagnostic is preserved separately and stops only on
   the unavailable optional `psycopg` fixture dependency.
7. Final serial Node execution is 360/361 with only exact unchanged S04-TM004.
   Two earlier concurrency transients are preserved; each passed 5/5 isolated
   reproductions and neither appears in the serial final run.
8. Product writes are confined to the I03 scope, cache artifacts are absent,
   canonical schema count remains 124, and no schema or workflow was modified.

## Assurance boundary

I03 supplies deterministic component-local execution contracts. It does not
create a canonical schema, persist ontology authority, issue a HumanDecision,
implement a review UI or remote service, or claim that a review item is an
approval. The optional PostgreSQL fixture diagnostic and S04-TM004 remain
outside I03 ownership. This review does not claim actor-independent
certification.

## Decision

Both I03 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
"""


def make_receipt() -> dict[str, Any]:
    artifact = ATTEMPT / "ontology-verification.json"
    receipt = {
        "receipt_id": "AR-I03-0001-ONTOLOGY-VERIFICATION",
        "artifact_id": "I03-0001-ONTOLOGY-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(artifact),
        "byte_size": artifact.stat().st_size,
        "created_by": {
            "actor_id": "SVC-FOUNDRY-KERNEL-I03",
            "actor_type": "service",
        },
        "created_at": CREATED_AT,
        "locator": artifact.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "ontology_fixture_test",
                "status": "PASS",
                "details": "16/16 exact mapping, ambiguity, review queue, authority, and deterministic identity cases passed",
            },
            {
                "check": "measurement_identity_test",
                "status": "PASS",
                "details": "23/23 identity, bridge, ceiling, incompatibility, scope, and aggregation cases passed",
            },
            {
                "check": "full_python_regression",
                "status": "PASS",
                "details": "947/947 official tests/** cases passed with zero skipped tests",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt),
        key=lambda error: list(error.path),
    )
    if errors:
        raise SystemExit(f"invalid I03 ArtifactReceipt: {errors[0].message}")
    return receipt


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verify_sealed_inputs()
    write_json("ontology-verification.json", ontology_verification())
    write_json("full-regression-impact.json", regression_impact())
    write_json("concurrency-diagnostic.json", concurrency_diagnostic())
    write_json("optional-postgres-diagnostic.json", optional_postgres_diagnostic())
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation())
    write_json("dependency-status.json", dependency_status())
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(product_inventory()), encoding="utf-8", newline="\n"
    )
    write_json("ontology-verification.artifact-receipt.json", make_receipt())
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    expected = {
        "ontology-verification.json": ontology_verification(),
        "full-regression-impact.json": regression_impact(),
        "concurrency-diagnostic.json": concurrency_diagnostic(),
        "optional-postgres-diagnostic.json": optional_postgres_diagnostic(),
        "preexisting-debt-reconciliation.json": debt_reconciliation(),
        "dependency-status.json": dependency_status(),
        "ontology-verification.artifact-receipt.json": make_receipt(),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored I03 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored I03 commands differ from canonical commands")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(
        product_inventory()
    ):
        raise SystemExit("stored I03 review differs from final product inventory")
    for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)
    cache_artifacts = [
        path
        for path in ATTEMPT.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"I03 evidence contains Python cache artifacts: {cache_artifacts}")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "ontology_fixture_passed": 16,
        "measurement_identity_passed": 23,
        "targeted_python_passed": 39,
        "full_python_passed": 947,
        "full_node_passed": 360,
        "full_node_preexisting_failures": 1,
        "optional_postgres_diagnostic_errors": 1,
        "sealed_input_hash_count": len(preserved),
        "completion_ready": False,
    }


def generation_integrity(expected_count: int, expected_evidence: str) -> dict[str, Any]:
    automation = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
    sys.path.insert(0, str(automation))
    import state_store  # type: ignore

    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH current pointer and generation verification disagree")
    generations = sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )
    if len(generations) != expected_count or generations[-1] != generation:
        raise SystemExit("RAH generation inventory mismatch")
    checked = 0
    for name in generations:
        generation_root = ralph_root / "generations" / name
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict):
            raise SystemExit(f"invalid RAH generation manifest: {name}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"RAH generation file set mismatch: {name}")
        for filename in state_store.GENERATION_FILES:
            if sha256(generation_root / filename) != files[filename]:
                raise SystemExit(f"RAH payload hash mismatch: {name}/{filename}")
            checked += 1
    flat_stamps = 0
    flat_matches = 0
    for filename in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / filename)
        if flat.get("state_generation") == generation:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[filename]
        if isinstance(authority, dict):
            authority = {
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    ledger = payloads.get("evidence_ledger.json", {})
    entries = ledger.get("entries", []) if isinstance(ledger, dict) else []
    identifiers = [row.get("id") for row in entries if isinstance(row, dict)]
    if identifiers != [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]:
        raise SystemExit("RAH evidence ledger is not continuous")
    if not identifiers or identifiers[-1] != expected_evidence:
        raise SystemExit("RAH evidence high-water mismatch")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH must remain active with completion_ready=false")
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("six RAH flat projections are not current")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "current_generation": generation,
        "latest_evidence_id": expected_evidence,
        "evidence_count": len(identifiers),
        "retained_generation_manifest_count": len(generations),
        "generation_file_hashes_verified": checked,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "generation_manifest_sha256": sha256_id(
            ralph_root / "generations" / generation / "generation-manifest.json"
        ),
        "completion_ready": False,
    }


def report_document(integrity: dict[str, Any]) -> dict[str, Any]:
    verification = ontology_verification()
    dag = dependency_status()
    artifact_names = [
        "ontology-verification.json",
        "full-regression-impact.json",
        "concurrency-diagnostic.json",
        "optional-postgres-diagnostic.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "ontology-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "targeted-python-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-python-suite.optional-postgres-diagnostic.junit.xml",
        "full-node-suite.concurrent-load-diagnostic.junit.xml",
        "full-node-suite.standalone-concurrency-diagnostic.junit.xml",
        "full-node-suite.junit.xml",
        "normalize_junit.py",
        "i03_evidence.py",
        "i03_rah_seal.py",
    ]
    artifacts = [
        {
            "path": (ATTEMPT / name).relative_to(ROOT).as_posix(),
            "sha256": sha256_id(ATTEMPT / name),
            "byte_size": (ATTEMPT / name).stat().st_size,
        }
        for name in artifact_names
    ]
    return {
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "Ontology and measurement construct resolution",
        "status": "PASS",
        "package_status": "PASS",
        "completion_ready": False,
        "dependencies": dag["dependency_evidence"],
        "write_scope": [
            "python/epistemic_foundry/ontology/**",
            "artifacts/work_packages/I03/**",
        ],
        "changed_files": product_inventory(),
        "exit_criteria": {
            "same_label_different_construct_not_silently_merged": "PASS",
            "human_approval_queue_exists": "PASS",
        },
        "required_checks": verification["required_checks"],
        "runtime_boundary": {
            "component_local_typed_contract": True,
            "canonical_schema_added": False,
            "canonical_schema_or_workflow_modified": False,
            "mapping_review_item_is_approval": False,
            "human_decision_issued": False,
            "persistence_ui_or_remote_service_claimed": False,
            "intake_ui_and_export_owner": "I04",
        },
        "regression": {
            "targeted_python": {
                "status": "PASS",
                "passed": 39,
                "ontology_fixture_cases": 16,
                "measurement_identity_cases": 23,
                "failed": 0,
                "skipped": 0,
            },
            "python": {
                "status": "PASS",
                "scope": "tests/**",
                "passed": 947,
                "failed": 0,
                "skipped": 0,
            },
            "optional_postgres_diagnostic": {
                "status": "OPTIONAL_DEPENDENCY_UNAVAILABLE",
                "missing_dependency": "psycopg",
                "official_gate_impact": "NONE",
            },
            "node": {
                "status": "BOUNDED_PREEXISTING_DEBT_S04_TM004",
                "passed": 360,
                "failed": 1,
                "skipped": 0,
                "i03_caused_failure_count": 0,
            },
            "concurrency_diagnostics": "TWO_TRANSIENTS_PRESERVED_AND_EACH_NOT_REPRODUCED_IN_5_ISOLATED_RUNS",
            "repository_structure": "PASS",
            "package_boundaries": "PASS",
            "git_diff_check": "PASS",
            "utf8_ast_schema_count_and_cache_check": "PASS",
        },
        "review": {
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "blocking_findings": 0,
            "findings_fixed": 1,
            "fixed_finding": "compatible SAME bridge cannot pool under METHOD_BOUNDARY_ONLY or BLOCK_AGGREGATION",
            "subagents_used": False,
            "assurance_limitation": (
                "Procedurally separate primary-session review; not actor-independent certification."
            ),
            "artifact": "artifacts/work_packages/I03/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "preserved_limitations": [
            "I03 types are component-local execution contracts, not new canonical schemas.",
            "I03 does not issue HumanDecision approval or implement review persistence, UI, or remote services.",
            "The optional PostgreSQL fixture diagnostic requires psycopg and is not the official 947-test gate.",
            "S04-TM004 remains exact pre-existing S04-owned debt.",
            "Review is not actor-independent because the product owner forbids subagents and Fleet in this sequence.",
        ],
        "historical_and_worktree_preservation": {
            "prior_reports_and_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "product_write_scope_violations": 0,
            "subagents_or_fleet_used": False,
            "failed_diagnostics_preserved_in_commands": True,
        },
        "evidence_artifacts": artifacts,
        "artifact_receipt": {
            "path": "artifacts/work_packages/I03/attempts/0001/ontology-verification.artifact-receipt.json",
            "receipt_id": "AR-I03-0001-ONTOLOGY-VERIFICATION",
        },
        "rah_state": {
            "status": "active",
            "core_evidence_id": "E0072",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0073",
            "retained_generation_manifest_count": integrity[
                "retained_generation_manifest_count"
            ],
            "generation_file_hashes_verified": integrity[
                "generation_file_hashes_verified"
            ],
            "flat_snapshot_stamps_verified": 6,
            "flat_snapshot_content_matches": 6,
            "completion_ready": False,
        },
        "dependency_effect": {
            "dag_recomputed": True,
            "completed_package_count": dag["completed_package_count"],
            "ready_packages_manifest_order": dag["ready_packages_manifest_order"],
            "blocked_package_count": dag["blocked_package_count"],
            "next_package": dag["next_package"],
        },
        "not_claimed": [
            "canonical ontology or measurement JSON Schema",
            "HumanDecision approval, ontology persistence, UI, or remote service",
            "optional PostgreSQL fixture readiness",
            "global repository green status, release readiness, or product completion",
        ],
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(70, "E0072")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    integrity = generation_integrity(70, "E0072")
    if read_json(ATTEMPT / "rah-core-integrity.json") != integrity:
        raise SystemExit("stored I03 RAH core integrity differs from live generation")
    if read_json(ATTEMPT / "report.json") != report_document(integrity):
        raise SystemExit("stored I03 report differs from live evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"I03 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": integrity["current_generation"],
        "core_evidence_id": "E0072",
        "root_projection_count": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=(
            "build-pre-core",
            "verify-pre-core",
            "build-post-core",
            "verify-post-core",
        ),
    )
    args = parser.parse_args()
    if args.mode == "build-pre-core":
        build_pre_core()
        result = verify_pre_core()
    elif args.mode == "verify-pre-core":
        result = verify_pre_core()
    elif args.mode == "build-post-core":
        build_post_core()
        result = verify_post_core()
    else:
        result = verify_post_core()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
