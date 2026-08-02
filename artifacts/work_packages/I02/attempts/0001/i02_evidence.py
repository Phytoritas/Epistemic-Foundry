#!/usr/bin/env python3
"""Build and verify byte-bound evidence for I02-0001."""

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
ATTEMPT = ROOT / "artifacts/work_packages/I02/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/I02"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRIOR_DAG = ROOT / "artifacts/work_packages/I01/attempts/0001/dependency-status.json"

ATTEMPT_ID = "I02-0001"
WORK_PACKAGE_ID = "I02"
CREATED_AT = "2026-07-29T08:46:55Z"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
CONCURRENCY_TEST = (
    "orphan_receipt_test: concurrent readers tolerate transient staging and lock handoff"
)

PRODUCT_HASHES = {
    "python/epistemic_foundry/intake/frame/__init__.py": (
        "5401aea2c12d597fc627ed30cab262cc6695d1720a697f73fe603903a93dfc49"
    ),
    "python/epistemic_foundry/intake/frame/compiler.py": (
        "eec74d16d02d7e5ee9ef80bb49ad5e012ade894e8c8406ba99e090eca9fbf4b9"
    ),
    "python/epistemic_foundry/intake/frame/test_falsifier_gate.py": (
        "43721d8510d87492226dda4ee5162e46d891bb0cab2036313962c63482a0238a"
    ),
    "python/epistemic_foundry/intake/frame/test_frame_gold.py": (
        "33c35e6d5e718ddd31863339847dc831fc85773750f970c3a658865f34c4c5d5"
    ),
}
JUNIT_HASHES = {
    "targeted-python-suite.junit.xml": (
        "f391ac24296387d82a213e324c7f6be053fba2f9c1607bc92cc1429cdf4743b2"
    ),
    "full-python-suite.junit.xml": (
        "49326db729ff1c88af6b20cd562e10c2a24f1720b129322c17339b76ab0a5257"
    ),
    "full-node-suite.junit.xml": (
        "8225b5089e1c4dc8497f5801cc3077d32378825e79bc3255f363855ea0a6c172"
    ),
    "full-node-suite.concurrent-load-diagnostic.junit.xml": (
        "54b2135611249688fc708edccf07e7033b7613cd6807550650cc97fdd218950f"
    ),
}
SEALED_INPUTS = {
    "MASTER_SPEC.md": "43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3",
    "manifests/development_manifest.yaml": (
        "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
    ),
    "schemas/artifact-receipt.schema.json": (
        "9de81c722fbe36038993437403e265d96b6e9d05d432b89aaab4abc89d996c34"
    ),
    "schemas/insight-card.schema.json": (
        "08c55d08828e1b883bd1bd426ef2691f2b3be34b6466c2503da62793b1cf3498"
    ),
    "schemas/scope-vector.schema.json": (
        "5f6c99c098a76cee1af133f0e1b47253cc73c49975356bfe78a3ea26260f8a98"
    ),
    "examples/sample_insight.json": (
        "4f03e249457f6ee88ec4a192d2b589c419ca55e3a819ab3b35bb4afeee82737b"
    ),
    "docs/forge_protocol.md": (
        "3273d5efee6f6d9478b86bf05e67f7f01dfda3547ac6371b8cb818e737754ad3"
    ),
    "artifacts/work_packages/I01/report.json": (
        "7174f9292421996fcd7e48de8f29757657dcf9b7aff3483028bbb86be70f886a"
    ),
    "artifacts/work_packages/I01/attempts/0001/dependency-status.json": (
        "a9f6c246dd16fe534df466813eba92b630de8c9e06022ca017cc1198cd75cd06"
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
        raise SystemExit("I02 dependency I01 is not evidence-sealed PASS")
    return observed


def verify_utf8(relative: str, expected_hash: str) -> dict[str, Any]:
    path = ROOT / relative
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        raise SystemExit(f"invalid encoding marker in I02 file: {relative}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"I02 file is not UTF-8: {relative}: {error}")
    if "\ufffd" in text:
        raise SystemExit(f"replacement character in I02 file: {relative}")
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected_hash:
        raise SystemExit(f"I02 product hash changed: {relative}: {actual}")
    try:
        ast.parse(text, filename=relative)
    except SyntaxError as error:
        raise SystemExit(f"I02 Python syntax failure: {relative}: {error}")
    return {
        "path": relative,
        "byte_size": len(content),
        "sha256": "sha256:" + actual,
        "bom": False,
        "replacement_character_count": 0,
        "ast_parse": "PASS",
    }


def product_inventory() -> list[dict[str, Any]]:
    scope = ROOT / "python/epistemic_foundry/intake/frame"
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in scope.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    }
    if actual != set(PRODUCT_HASHES):
        raise SystemExit(f"unexpected I02 product inventory: {sorted(actual)}")
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
    expected = {"tests": 31, "failures": 0, "errors": 0, "skipped": 0}
    cases = root.findall(".//testcase")
    frame_count = sum(
        1 for case in cases if str(case.get("classname") or "").endswith("test_frame_gold")
    )
    falsifier_count = sum(
        1
        for case in cases
        if str(case.get("classname") or "").endswith("test_falsifier_gate")
    )
    if (
        totals != expected
        or len(cases) != 31
        or frame_count != 19
        or falsifier_count != 12
        or root.findall(".//failure")
        or root.findall(".//error")
        or root.findall(".//skipped")
    ):
        raise SystemExit(
            "I02 targeted JUnit changed: "
            f"totals={totals} frame={frame_count} falsifier={falsifier_count}"
        )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "frame_gold_case_count": frame_count,
        "falsifier_gate_case_count": falsifier_count,
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
            f"unexpected full Node result: totals={totals} cases={len(cases)} failures={failures}"
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
        "failure": {
            "debt_id": "S04-TM004",
            "test_name": failures[0]["name"],
            "test_file": failures[0]["file"],
            "expected_manifest_sha256": S04_EXPECTED,
            "actual_manifest_sha256": S04_ACTUAL,
        },
    }


def concurrency_diagnostic() -> dict[str, Any]:
    path = ATTEMPT / "full-node-suite.concurrent-load-diagnostic.junit.xml"
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
    if totals != expected or len(failures) != 2:
        raise SystemExit(f"concurrent-load diagnostic changed: {totals} {failures}")
    by_name = {failure["name"]: failure for failure in failures}
    if set(by_name) != {CONCURRENCY_TEST, S04_TEST}:
        raise SystemExit("concurrent-load diagnostic failure inventory changed")
    assert_s04_failure(by_name[S04_TEST])
    concurrency = by_name[CONCURRENCY_TEST]
    if (
        not concurrency["file"].endswith(
            "packages/foundry-kernel/src/artifacts/orphan-receipt.test.mjs"
        )
        or "ARTIFACT_STORE_STRUCTURE_INVALID" not in concurrency["message"]
    ):
        raise SystemExit("concurrent-load diagnostic fingerprint changed")
    standalone = node_junit()
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "DIAGNOSTIC_RECONCILED",
        "concurrent_run": {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(path),
            "byte_size": path.stat().st_size,
            "totals": totals,
            "transient_failure_test": CONCURRENCY_TEST,
            "transient_failure_code": "ARTIFACT_STORE_STRUCTURE_INVALID",
        },
        "isolated_reproduction": {
            "runs": 5,
            "passed": 5,
            "failed": 0,
            "reproduced": False,
        },
        "standalone_full_node": {
            "sha256": standalone["sha256"],
            "totals": standalone["totals"],
            "transient_failure_present": False,
        },
        "classification": "CONCURRENT_LOAD_DIAGNOSTIC_NOT_REPRODUCED",
        "product_failure_claimed": False,
    }


def frame_verification() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    inventory = product_inventory()
    targeted = targeted_junit()
    scope = ROOT / "python/epistemic_foundry/intake/frame"
    cache_artifacts = [
        path.relative_to(ROOT).as_posix()
        for path in scope.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"I02 product scope contains cache artifacts: {cache_artifacts}")
    schema_count = len(list((ROOT / "schemas").glob("*.schema.json")))
    if schema_count != 124:
        raise SystemExit(f"canonical schema count changed: {schema_count}")
    test_text = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in PRODUCT_HASHES
        if "/test_" in relative
    )
    if "sys.path" in test_text or "conftest" in {path.name for path in scope.iterdir()}:
        raise SystemExit("I02 tests retain a repository-boundary bypass")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "compiler_version": "4.0.0-i02.1",
        "product_inventory": inventory,
        "sealed_input_hashes": preserved,
        "contract_projection": {
            "existing_insight_card_schema_used": True,
            "existing_scope_vector_schema_used": True,
            "canonical_schema_count": schema_count,
            "canonical_schema_added": False,
            "canonical_schema_or_workflow_modified": False,
            "falsifier_required": True,
            "prediction_required": True,
            "mechanism_path_required": True,
            "unknown_scalar_scope_preserved_as_null": True,
            "unknown_collection_scope_preserved_as_empty_canonical_shape": True,
            "unknown_origin_preserved_in_component_local_sidecar": True,
            "unknown_scope_inference_performed": False,
            "eligible_card_with_required_scope_unknown_rejected": True,
            "eligible_card_with_undefined_construct_rejected": True,
            "inbox_and_withdrawn_cards_not_council_ready": True,
            "input_proposal_mutated": False,
            "mapping_order_changes_output": False,
            "identifier_timestamp_or_registration_hash_generated": False,
            "registration_hash_content_recomputed": False,
            "registration_hash_format_validated": True,
            "strict_rfc3339_timestamp_validation": True,
            "rfc3339_leap_second_preserved": True,
        },
        "required_checks": {
            "frame_gold_test": {
                "status": "PASS",
                "passed": 19,
                "failed": 0,
                "skipped": 0,
            },
            "falsifier_gate_test": {
                "status": "PASS",
                "passed": 12,
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
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT",
        "targeted_python": targeted,
        "python": python,
        "node": node,
        "concurrent_load_diagnostic": diagnostic,
        "node_junit_reporter_reconciliation": {
            "semantic_source_of_truth": "node_junit_footer",
            "footer_test_count": 361,
            "xml_testcase_element_count": 359,
            "failure_element_count": 1,
            "failure_fingerprint_verified": True,
        },
        "i02_caused_python_failure_count": 0,
        "i02_caused_node_failure_count": 0,
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
        "i02_causal_impact": "NONE",
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
        or prior.get("completed_package_count") != 38
        or prior.get("ready_packages_manifest_order")
        != ["I02", "I03", "J01", "K01", "T01", "A06"]
        or prior.get("next_package") != "I02"
    ):
        raise SystemExit("sealed I01 dependency state is not the expected I02 input")

    report_path = ROOT / "artifacts/work_packages/I01/report.json"
    dependency = read_json(report_path)
    dependency_evidence = {
        "I01": {
            "status": "PASS",
            "attempt_id": "I01-0001",
            "report": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(report_path),
        }
    }
    if dependency.get("status") != "PASS" or dependency.get("attempt_id") != "I01-0001":
        raise SystemExit("I02 dependency I01 changed")

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
    if len(completed) != 38 or "I02" in completed:
        raise SystemExit("prior completed package inventory changed")
    completed.add("I02")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["I03", "J01", "K01", "T01", "A06"]
    blocked = len(order) - len(completed) - len(ready)
    if len(completed) != 39 or ready != expected_ready or blocked != 112:
        raise SystemExit(
            f"unexpected post-I02 DAG: completed={len(completed)} ready={ready} blocked={blocked}"
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
            "completed_package_count": 38,
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
        ("C001", "Inspect I02 authority, dependency evidence, canonical schemas, and dirty worktree", 0, "PASS"),
        ("D001", "Run initial I02 targeted suite before ScopeUnknown test import was complete", 1, "FOUND_AND_FIXED: ScopeUnknown import added; product contract unchanged"),
        ("C002", "Implement deterministic InsightCard and ScopeVector frame compiler with component-local tests", 0, "PASS: four I02 product files"),
        ("C003", "Run baseline I02 targeted Python suite", 0, "PASS: 24/24, zero skip"),
        ("D002", "Review timestamp boundary after datetime.fromisoformat accepted a space separator", 1, "FOUND_AND_FIXED: strict RFC 3339 extended-form lexical gate added"),
        ("C004", "Run I02 targeted suite after strict separator cases", 0, "PASS: 27/27, zero skip"),
        ("D003", "Review strict timestamp gate for valid RFC 3339 leap-second handling", 1, "FOUND_AND_FIXED: leap second is calendar-validated and original text preserved"),
        ("C005", "Run final I02 targeted Python JUnit suite", 0, "PASS: 31/31, zero skip; frame 19 and falsifier 12"),
        ("C006", "Run full Python regression JUnit suite without concurrent Node load", 0, "PASS: 947/947, zero skip"),
        ("D004", "Preserve earlier full Node run concurrent with full Python load", 1, "DIAGNOSTIC_RECONCILED: 359 passed, transient artifact-store concurrency failure plus exact S04-TM004"),
        ("C007", "Run artifact-store concurrency test in isolation five times", 0, "PASS: 5/5; transient failure not reproduced"),
        ("C008", "Run full Node regression JUnit suite standalone", 1, "BOUNDED_PREEXISTING_DEBT: 360 passed; exact unchanged S04-TM004 only"),
        ("C009", "Normalize four JUnit artifacts while preserving semantic summaries and fingerprints", 0, "PASS: machine-local marker count zero"),
        ("C010", "Run npm repository structure check", 0, "PASS"),
        ("C011", "Run npm public-package-boundary check", 0, "PASS"),
        ("D005", "Search for Node reporter command with an rg pattern beginning with --", 1, "DIAGNOSTIC_ONLY: missing rg option terminator; no product impact"),
        ("D006", "Search Windows artifact paths with a shell wildcard", 1, "DIAGNOSTIC_ONLY: invalid Windows wildcard path; narrowed literal paths used"),
        ("D007", "Read a guessed nested RAH generation layout", 1, "DIAGNOSTIC_ONLY: actual generation files are flat under the generation directory"),
        ("D008", "Remove verified I02 cache with PowerShell recursive command", 1, "DIAGNOSTIC_ONLY: safety hook blocked recursive command; exact Python leaf verification used"),
        ("D009", "Run an UTF-8 source scan over generated pyc cache bytes", 1, "DIAGNOSTIC_ONLY: binary cache was not source; scan narrowed to .py and cache removed"),
        ("C012", "Remove four verified I02 cache leaves and the empty directory with bounded Python path checks", 0, "PASS"),
        ("C013", "Run final product hash, AST, UTF-8, schema-count, JUnit, cache, and git diff checks", 0, "PASS"),
        ("C014", "Primary-session separate contract review of final I02 product bytes and evidence", 0, "PASS: zero blocking findings; not actor-independent certification"),
    )
    lines = []
    for suffix, command, exit_code, result in rows:
        lines.append(
            json.dumps(
                {
                    "command_id": f"I02-0001-{suffix}",
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
    return f"""# I02-0001 InsightCard and ScopeVector contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I02 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

{hashes}

## Findings

1. The compiler projects proposals into the existing strict `InsightCard` and
   `ScopeVector` schemas. It adds no canonical schema, does not modify the
   canonical workflow, and rejects fields outside those contracts.
2. Missing, explicit-null, and blank scalar scope inputs remain `null`; missing
   list/map inputs retain the canonical empty shape. A typed component-local
   `ScopeUnknown` sidecar records why positions are unknown without inventing
   a canonical artifact or inferred scope value.
3. Falsifier, prediction, and mechanism inputs are mandatory. An `eligible`
   card cannot retain required domain/population/unit-of-analysis unknowns or
   undefined constructs; Inbox and withdrawn cards cannot claim council
   readiness. This preserves the `F → O` fail-closed boundary.
4. The compiler preserves supplied identifiers, timestamps, and
   `registration_hash`. It validates their form but neither generates them nor
   recomputes registration-hash content binding, which remains outside I02.
5. Stable JSON output is mapping-order independent and input proposals remain
   unchanged. Strict RFC 3339 parsing rejects loose ISO forms and invalid
   calendar/offset values while preserving a valid RFC 3339 leap-second text.
6. The final targeted suite is 31/31: 19 frame-gold and 12 falsifier-gate
   cases. Full Python is 947/947. Standalone full Node is 360/361 with only
   exact unchanged S04-TM004. The earlier load-concurrent transient failure is
   preserved, failed to reproduce in 5/5 isolated runs, and is absent from the
   standalone full Node result.
7. Product writes are confined to the I02 scope, cache artifacts are absent,
   schema count remains 124, and prior reports, RAH generations, and unrelated
   dirty-worktree content remain preserved.

## Assurance boundary

I02 implements a deterministic component-local compiler and council-readiness
gate. It does not own identifier, timestamp, hash, persistence, ontology,
measurement-identity, UI, or remote-service authority. `ScopeUnknown` is a
component-local sidecar, not a new canonical artifact. The review does not
claim actor-independent certification.

## Decision

Both I02 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
"""


def make_receipt() -> dict[str, Any]:
    artifact = ATTEMPT / "frame-verification.json"
    receipt = {
        "receipt_id": "AR-I02-0001-FRAME-VERIFICATION",
        "artifact_id": "I02-0001-FRAME-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(artifact),
        "byte_size": artifact.stat().st_size,
        "created_by": {
            "actor_id": "SVC-FOUNDRY-KERNEL-I02",
            "actor_type": "service",
        },
        "created_at": CREATED_AT,
        "locator": artifact.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "frame_gold_test",
                "status": "PASS",
                "details": "19/19 canonical projection, unknown preservation, immutability, and timestamp cases passed",
            },
            {
                "check": "falsifier_gate_test",
                "status": "PASS",
                "details": "12/12 falsifier, prediction, mechanism, eligibility, and council-boundary cases passed",
            },
            {
                "check": "full_python_regression",
                "status": "PASS",
                "details": "947/947 passed with zero skipped tests",
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
        raise SystemExit(f"invalid I02 ArtifactReceipt: {errors[0].message}")
    return receipt


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verify_sealed_inputs()
    write_json("frame-verification.json", frame_verification())
    write_json("full-regression-impact.json", regression_impact())
    write_json("concurrency-diagnostic.json", concurrency_diagnostic())
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation())
    write_json("dependency-status.json", dependency_status())
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(product_inventory()), encoding="utf-8", newline="\n"
    )
    write_json("frame-verification.artifact-receipt.json", make_receipt())
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    expected = {
        "frame-verification.json": frame_verification(),
        "full-regression-impact.json": regression_impact(),
        "concurrency-diagnostic.json": concurrency_diagnostic(),
        "preexisting-debt-reconciliation.json": debt_reconciliation(),
        "dependency-status.json": dependency_status(),
        "frame-verification.artifact-receipt.json": make_receipt(),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored I02 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored I02 commands differ from canonical commands")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(
        product_inventory()
    ):
        raise SystemExit("stored I02 review differs from final product inventory")
    for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)
    cache_artifacts = [
        path
        for path in ATTEMPT.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"I02 evidence contains Python cache artifacts: {cache_artifacts}")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "frame_gold_passed": 19,
        "falsifier_gate_passed": 12,
        "targeted_python_passed": 31,
        "full_python_passed": 947,
        "full_node_passed": 360,
        "full_node_preexisting_failures": 1,
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
                key: value for key, value in authority.items() if key != "state_generation"
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
    verification = frame_verification()
    dag = dependency_status()
    artifact_names = [
        "frame-verification.json",
        "full-regression-impact.json",
        "concurrency-diagnostic.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "frame-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "targeted-python-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-node-suite.concurrent-load-diagnostic.junit.xml",
        "normalize_junit.py",
        "i02_evidence.py",
        "i02_rah_seal.py",
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
        "title": "InsightCard, falsifier and ScopeVector compiler",
        "status": "PASS",
        "package_status": "PASS",
        "completion_ready": False,
        "dependencies": dag["dependency_evidence"],
        "write_scope": [
            "python/epistemic_foundry/intake/frame/**",
            "artifacts/work_packages/I02/**",
        ],
        "changed_files": product_inventory(),
        "exit_criteria": {
            "falsifier_mandatory_for_council": "PASS",
            "scope_normalization_preserves_unknowns": "PASS",
        },
        "required_checks": verification["required_checks"],
        "runtime_boundary": {
            "component_local_typed_contract": True,
            "canonical_schema_added": False,
            "canonical_schema_or_workflow_modified": False,
            "canonical_scope_unknown_artifact_claimed": False,
            "identifier_hash_timestamp_authority_claimed": False,
            "registration_hash_content_binding_claimed": False,
            "persistence_or_remote_service_claimed": False,
            "ontology_and_measurement_owner": "I03",
            "intake_ui_and_export_owner": "I04",
        },
        "regression": {
            "targeted_python": {
                "status": "PASS",
                "passed": 31,
                "frame_gold_cases": 19,
                "falsifier_gate_cases": 12,
                "failed": 0,
                "skipped": 0,
            },
            "python": {
                "status": "PASS",
                "passed": 947,
                "failed": 0,
                "skipped": 0,
            },
            "node": {
                "status": "BOUNDED_PREEXISTING_DEBT_S04_TM004",
                "passed": 360,
                "failed": 1,
                "skipped": 0,
                "i02_caused_failure_count": 0,
            },
            "concurrent_load_diagnostic": "PRESERVED_AND_NOT_REPRODUCED_IN_5_ISOLATED_RUNS",
            "repository_structure": "PASS",
            "package_boundaries": "PASS",
            "git_diff_check": "PASS",
            "utf8_ast_schema_count_and_cache_check": "PASS",
        },
        "review": {
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "blocking_findings": 0,
            "subagents_used": False,
            "assurance_limitation": (
                "Procedurally separate primary-session review; not actor-independent certification."
            ),
            "artifact": "artifacts/work_packages/I02/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "preserved_limitations": [
            "I02 validates but does not generate identifiers, timestamps, or registration hashes.",
            "I02 does not recompute registration_hash content binding.",
            "ScopeUnknown is a component-local sidecar, not a canonical artifact.",
            "I02 does not implement ontology or measurement identity, persistence, UI, or remote service boundaries.",
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
            "path": "artifacts/work_packages/I02/attempts/0001/frame-verification.artifact-receipt.json",
            "receipt_id": "AR-I02-0001-FRAME-VERIFICATION",
        },
        "rah_state": {
            "status": "active",
            "core_evidence_id": "E0070",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0071",
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
            "identifier, timestamp, registration-hash content, or persistence authority",
            "canonical ScopeUnknown artifact",
            "ontology, measurement-identity, intake UI, or remote-service implementation",
            "global repository green status, release readiness, or product completion",
        ],
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(68, "E0070")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    integrity = generation_integrity(68, "E0070")
    if read_json(ATTEMPT / "rah-core-integrity.json") != integrity:
        raise SystemExit("stored I02 RAH core integrity differs from live generation")
    if read_json(ATTEMPT / "report.json") != report_document(integrity):
        raise SystemExit("stored I02 report differs from live evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"I02 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": integrity["current_generation"],
        "core_evidence_id": "E0070",
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
