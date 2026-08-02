#!/usr/bin/env python3
"""Build and verify byte-bound evidence for I01-0001."""

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
ATTEMPT = ROOT / "artifacts/work_packages/I01/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/I01"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRIOR_DAG = ROOT / "artifacts/work_packages/H04/attempts/0001/dependency-status.json"

ATTEMPT_ID = "I01-0001"
WORK_PACKAGE_ID = "I01"
CREATED_AT = "2026-07-29T07:49:12Z"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"

PRODUCT_HASHES = {
    "python/epistemic_foundry/intake/interview/__init__.py": (
        "533f3441733c40bb38f6182add7eb553d6d6b378503ed8dbfda5e426c96d457c"
    ),
    "python/epistemic_foundry/intake/interview/engine.py": (
        "dded723763a007de1a1d8e51606333b2140d9821e0541ac2bdea6cf40d9db764"
    ),
    "python/epistemic_foundry/intake/interview/test_interview_readiness.py": (
        "d3daa0c5dc6284c1bf3086b64364c6514b3cc84caa392caf2fa8d56713b7d4c7"
    ),
    "python/epistemic_foundry/intake/interview/test_no_repeat_question.py": (
        "b9a14f828e75b1a1ed2854cdb3c784003c517fc23548ef471693fab16fd2a8f4"
    ),
}
JUNIT_HASHES = {
    "targeted-python-suite.junit.xml": (
        "dfdb3ab594953109bfdf3dd6391a22b6e6b8fd889e98118054d49a3b78c1da9b"
    ),
    "full-python-suite.junit.xml": (
        "d56560d5f1543e283893bd19fc56ab4b61b093aa886b67e859e97e4d55974f25"
    ),
    "full-node-suite.junit.xml": (
        "8c0544eaf7fb2299ac1e0e3a51ba31689bd5e34bf027bdc48a75dee32ae4040a"
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
    "artifacts/work_packages/C04/report.json": (
        "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f"
    ),
    "artifacts/work_packages/F04/report.json": (
        "1c7f1a00a684dd84fe08b9bfea83972cf5ed1fd04cb521a7b6c3a4f74f96a12a"
    ),
    "artifacts/work_packages/H04/attempts/0001/dependency-status.json": (
        "defbbb0189969ce8adbb7f6ef967a9404857ea60279e2d69ad262b6e59636696"
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
    return observed


def verify_utf8(relative: str, expected_hash: str) -> dict[str, Any]:
    path = ROOT / relative
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        raise SystemExit(f"invalid encoding marker in I01 file: {relative}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"I01 file is not UTF-8: {relative}: {error}")
    if "\ufffd" in text:
        raise SystemExit(f"replacement character in I01 file: {relative}")
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected_hash:
        raise SystemExit(f"I01 product hash changed: {relative}: {actual}")
    try:
        ast.parse(text, filename=relative)
    except SyntaxError as error:
        raise SystemExit(f"I01 Python syntax failure: {relative}: {error}")
    return {
        "path": relative,
        "byte_size": len(content),
        "sha256": "sha256:" + actual,
        "bom": False,
        "replacement_character_count": 0,
        "ast_parse": "PASS",
    }


def product_inventory() -> list[dict[str, Any]]:
    scope = ROOT / "python/epistemic_foundry/intake/interview"
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in scope.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    }
    if actual != set(PRODUCT_HASHES):
        raise SystemExit(f"unexpected I01 product inventory: {sorted(actual)}")
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
    expected = {"tests": 36, "failures": 0, "errors": 0, "skipped": 0}
    cases = root.findall(".//testcase")
    class_counts: dict[str, int] = {}
    for case in cases:
        class_name = str(case.get("classname") or "")
        name = str(case.get("name") or "")
        class_counts[class_name] = class_counts.get(class_name, 0) + 1
        if class_name.endswith("test_interview_readiness"):
            if not name.startswith("test_interview_readiness_test_"):
                raise SystemExit(f"unexpected I01 readiness case: {name}")
        elif class_name.endswith("test_no_repeat_question"):
            if not name.startswith("test_no_repeat_question_test_"):
                raise SystemExit(f"unexpected I01 no-repeat case: {name}")
        else:
            raise SystemExit(f"unexpected I01 targeted test class: {class_name}")
    readiness_count = sum(
        count for name, count in class_counts.items() if name.endswith("test_interview_readiness")
    )
    no_repeat_count = sum(
        count for name, count in class_counts.items() if name.endswith("test_no_repeat_question")
    )
    if (
        totals != expected
        or len(cases) != 36
        or readiness_count != 19
        or no_repeat_count != 17
        or root.findall(".//failure")
        or root.findall(".//error")
        or root.findall(".//skipped")
    ):
        raise SystemExit(
            "I01 targeted JUnit changed: "
            f"totals={totals} readiness={readiness_count} no_repeat={no_repeat_count}"
        )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "interview_readiness_case_count": readiness_count,
        "no_repeat_question_case_count": no_repeat_count,
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
    if totals != expected:
        raise SystemExit(f"full Node result differs from bounded debt: {totals}")
    cases = root.findall(".//testcase")
    failures: list[dict[str, str]] = []
    for case in cases:
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
    if len(cases) != 359 or len(failures) != 1:
        raise SystemExit(
            f"unexpected full Node reporter inventory: cases={len(cases)} failures={failures}"
        )
    failure = failures[0]
    if (
        failure["name"] != S04_TEST
        or not failure["file"].endswith(
            "tests/security/s04-threat-model-traceability.test.mjs"
        )
        or S04_EXPECTED not in failure["message"]
        or S04_ACTUAL not in failure["message"]
    ):
        raise SystemExit("full Node failure is not exact preserved S04-TM004")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "xml_testcase_count": len(cases),
        "xml_footer_testcase_delta": totals["tests"] - len(cases),
        "xml_failure_count": 1,
        "semantic_source_of_truth": "node_junit_footer",
        "failure": {
            "debt_id": "S04-TM004",
            "test_name": failure["name"],
            "test_file": failure["file"],
            "expected_manifest_sha256": S04_EXPECTED,
            "actual_manifest_sha256": S04_ACTUAL,
        },
    }


def interview_verification() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    inventory = product_inventory()
    targeted = targeted_junit()
    scope = ROOT / "python/epistemic_foundry/intake/interview"
    cache_artifacts = [
        path.relative_to(ROOT).as_posix()
        for path in scope.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"I01 product scope contains cache artifacts: {cache_artifacts}")
    test_text = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in PRODUCT_HASHES
        if "/test_" in relative
    )
    if "sys.path" in test_text or "conftest" in {path.name for path in scope.iterdir()}:
        raise SystemExit("I01 tests retain a repository-boundary bypass")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "engine_version": "4.0.0-i01.1",
        "product_inventory": inventory,
        "sealed_input_hashes": preserved,
        "contract_projection": {
            "closed_interview_rule_count": 9,
            "closed_interview_dimension_count": 11,
            "immutable_component_contracts": True,
            "only_decision_critical_questions_emitted": True,
            "noncritical_needs_deferred_explicitly": True,
            "one_question_per_missing_dimension": True,
            "known_or_answered_dimension_reasked": False,
            "same_revision_question_ids_deterministic": True,
            "same_revision_prior_questions_reemitted": False,
            "previously_asked_questions_remain_pending": True,
            "critical_contradictions_recorded": True,
            "unresolved_critical_contradictions_routed": True,
            "accepted_blockers_sticky": True,
            "invalid_vocabulary_and_mutable_inputs_fail_closed": True,
            "duplicate_or_forged_identifiers_fail_closed": True,
            "rule_dimension_mismatch_fails_closed": True,
            "new_canonical_schema_invented": False,
            "canonical_workflow_modified": False,
        },
        "required_checks": {
            "interview_readiness_test": {
                "status": "PASS",
                "passed": 19,
                "failed": 0,
                "skipped": 0,
            },
            "no_repeat_question_test": {
                "status": "PASS",
                "passed": 17,
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
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT",
        "targeted_python": targeted,
        "python": python,
        "node": node,
        "node_junit_reporter_reconciliation": {
            "semantic_source_of_truth": "node_junit_footer",
            "footer_test_count": 361,
            "xml_testcase_element_count": 359,
            "failure_element_count": 1,
            "failure_fingerprint_verified": True,
        },
        "i01_caused_python_failure_count": 0,
        "i01_caused_node_failure_count": 0,
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
        "i01_causal_impact": "NONE",
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
        or prior.get("completed_package_count") != 37
        or prior.get("ready_packages_manifest_order")
        != ["I01", "J01", "K01", "T01", "A06"]
        or prior.get("next_package") != "I01"
    ):
        raise SystemExit("sealed H04 dependency state is not the expected I01 input")

    dependency_evidence: dict[str, Any] = {}
    for package_id in ("C04", "F04"):
        report_path = ROOT / f"artifacts/work_packages/{package_id}/report.json"
        report = read_json(report_path)
        if report.get("status") != "PASS" or report.get("attempt_id") != f"{package_id}-0001":
            raise SystemExit(f"I01 dependency {package_id} is not evidence-sealed PASS")
        dependency_evidence[package_id] = {
            "status": "PASS",
            "attempt_id": f"{package_id}-0001",
            "report": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(report_path),
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
    if len(completed) != 37 or "I01" in completed:
        raise SystemExit("prior completed package inventory changed")
    completed.add("I01")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["I02", "I03", "J01", "K01", "T01", "A06"]
    blocked = len(order) - len(completed) - len(ready)
    if len(completed) != 38 or ready != expected_ready or blocked != 112:
        raise SystemExit(
            f"unexpected post-I01 DAG: completed={len(completed)} ready={ready} blocked={blocked}"
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
            "completed_package_count": 37,
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
        ("C001", "Inspect I01 authority, dependency evidence, manifest scope, and dirty worktree", 0, "PASS"),
        ("C002", "Implement deterministic bounded Interview planner and component-local tests", 0, "PASS: four I01 product files"),
        ("C003", "Run initial I01 targeted Python suite", 0, "PASS: 36/36, zero skip"),
        ("D001", "Run package-boundary check with a test-only sys.path bridge", 1, "FOUND_AND_FIXED: repository-boundary bypass rejected; bridge removed and relative imports used"),
        ("C004", "Remove test import bridge and conftest; preserve package-relative imports", 0, "PASS"),
        ("C005", "Run final I01 targeted Python JUnit suite", 0, "PASS: 36/36, zero skip"),
        ("C006", "Run full Python regression JUnit suite", 0, "PASS: 947/947, zero skip"),
        ("C007", "Run full Node regression JUnit suite", 1, "BOUNDED_PREEXISTING_DEBT: 360 passed; exact unchanged S04-TM004 only"),
        ("C008", "Normalize three JUnit receipts while preserving semantic summaries and S04 fingerprint", 0, "PASS: machine-local marker count zero"),
        ("C009", "Run npm repository structure check", 0, "PASS"),
        ("C010", "Run npm public-package-boundary check", 0, "PASS"),
        ("C011", "Run final Python AST, UTF-8, product hash, cache, and git diff checks", 0, "PASS"),
        ("D002", "Attempt a PowerShell ConvertFrom-Yaml DAG diagnostic", 1, "DIAGNOSTIC_ONLY: cmdlet unavailable; evidence builder uses repository PyYAML"),
        ("C012", "Primary-session separate contract review of final I01 product bytes and evidence", 0, "PASS: zero blocking findings; not actor-independent certification"),
    )
    lines = []
    for suffix, command, exit_code, result in rows:
        lines.append(
            json.dumps(
                {
                    "command_id": f"I01-0001-{suffix}",
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
    return f"""# I01-0001 bounded Interview contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I01 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

{hashes}

## Findings

1. The component accepts only the closed I01-I09 rule vocabulary and typed
   dimensions. Raw enum aliases, mutable input collections, duplicate IDs,
   invalid dispositions, and rule/dimension mismatches fail closed.
2. Only decision-critical missing dimensions produce questions. Multiple needs
   for one dimension merge into one canonically ordered question; known and
   answered dimensions are not re-asked; noncritical needs remain explicit.
3. Question identity binds engine version, immutable request ID and revision,
   target type, and target ID. Same-revision retries are deterministic. A prior
   open question remains pending instead of being emitted again, and forged or
   missing-target history is rejected.
4. Every supplied contradiction is retained. Critical unresolved contradictions
   are routed to a question, resolved contradictions bind an artifact, and
   accepted blockers remain sticky. An unrecorded critical conflict cannot pass.
5. The final targeted suite is 36/36: 19 readiness cases and 17 no-repeat cases.
   Full Python is 947/947. Full Node is 360/361 with only exact unchanged
   S04-TM004, whose footer/XML testcase delta is explicitly reconciled.
6. The rejected test-only import bridge was removed. Product writes are confined
   to the I01 scope, cache artifacts are absent, and prior reports, RAH
   generations, and unrelated dirty-worktree content remain preserved.

## Assurance boundary

I01 emits a deterministic component-local Interview plan and readiness verdict.
It does not invent a new canonical schema, persist a canonical ResearchBrief,
implement a user interface or remote interview service, decide downstream
scientific claims, or claim actor-independent certification. I02 and I03 retain
framing and ontology/measurement responsibilities.

## Decision

Both I01 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
"""


def make_receipt() -> dict[str, Any]:
    artifact = ATTEMPT / "interview-verification.json"
    receipt = {
        "receipt_id": "AR-I01-0001-INTERVIEW-VERIFICATION",
        "artifact_id": "I01-0001-INTERVIEW-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(artifact),
        "byte_size": artifact.stat().st_size,
        "created_by": {
            "actor_id": "SVC-FOUNDRY-KERNEL-I01",
            "actor_type": "service",
        },
        "created_at": CREATED_AT,
        "locator": artifact.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "interview_readiness_test",
                "status": "PASS",
                "details": "19/19 decision-critical question, readiness, contradiction, ordering, and fail-closed cases passed",
            },
            {
                "check": "no_repeat_question_test",
                "status": "PASS",
                "details": "17/17 stable identity, pending, replay, blocker, and forged-history cases passed",
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
        raise SystemExit(f"invalid I01 ArtifactReceipt: {errors[0].message}")
    return receipt


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verify_sealed_inputs()
    write_json("interview-verification.json", interview_verification())
    write_json("full-regression-impact.json", regression_impact())
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation())
    write_json("dependency-status.json", dependency_status())
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(product_inventory()), encoding="utf-8", newline="\n"
    )
    write_json("interview-verification.artifact-receipt.json", make_receipt())
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    expected = {
        "interview-verification.json": interview_verification(),
        "full-regression-impact.json": regression_impact(),
        "preexisting-debt-reconciliation.json": debt_reconciliation(),
        "dependency-status.json": dependency_status(),
        "interview-verification.artifact-receipt.json": make_receipt(),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored I01 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored I01 commands differ from canonical commands")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(
        product_inventory()
    ):
        raise SystemExit("stored I01 review differs from final product inventory")
    for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)
    cache_artifacts = [
        path
        for path in ATTEMPT.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"I01 evidence contains Python cache artifacts: {cache_artifacts}")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "interview_readiness_passed": 19,
        "no_repeat_question_passed": 17,
        "targeted_python_passed": 36,
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
    verification = interview_verification()
    dag = dependency_status()
    artifact_names = [
        "interview-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "interview-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "targeted-python-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "normalize_junit.py",
        "i01_evidence.py",
        "i01_rah_seal.py",
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
        "title": "Bounded Interview and contradiction scan",
        "status": "PASS",
        "package_status": "PASS",
        "completion_ready": False,
        "dependencies": dag["dependency_evidence"],
        "write_scope": [
            "python/epistemic_foundry/intake/interview/**",
            "artifacts/work_packages/I01/**",
        ],
        "changed_files": product_inventory(),
        "exit_criteria": {
            "only_decision_critical_questions_asked": "PASS",
            "critical_contradictions_recorded": "PASS",
        },
        "required_checks": verification["required_checks"],
        "runtime_boundary": {
            "component_local_typed_contract": True,
            "canonical_schema_added": False,
            "canonical_workflow_modified": False,
            "canonical_research_brief_claimed": False,
            "persistence_or_remote_service_claimed": False,
            "framing_owner": "I02",
            "ontology_and_measurement_owner": "I03",
        },
        "regression": {
            "targeted_python": {
                "status": "PASS",
                "passed": 36,
                "interview_readiness_cases": 19,
                "no_repeat_question_cases": 17,
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
                "i01_caused_failure_count": 0,
            },
            "repository_structure": "PASS",
            "package_boundaries": "PASS",
            "git_diff_check": "PASS",
            "utf8_ast_and_cache_check": "PASS",
        },
        "review": {
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "blocking_findings": 0,
            "subagents_used": False,
            "assurance_limitation": (
                "Procedurally separate primary-session review; not actor-independent certification."
            ),
            "artifact": "artifacts/work_packages/I01/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "preserved_limitations": [
            "I01 emits a component-local Interview plan and does not invent a canonical ResearchBrief schema.",
            "I01 does not implement a user interface, remote interview service, or downstream scientific decision.",
            "I02 and I03 retain framing and ontology/measurement responsibilities.",
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
            "path": "artifacts/work_packages/I01/attempts/0001/interview-verification.artifact-receipt.json",
            "receipt_id": "AR-I01-0001-INTERVIEW-VERIFICATION",
        },
        "rah_state": {
            "status": "active",
            "core_evidence_id": "E0068",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0069",
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
            "canonical ResearchBrief schema or persistence",
            "interactive UI or remote interview service",
            "downstream scientific claim, framing, or ontology resolution",
            "global repository green status, release readiness, or product completion",
        ],
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(66, "E0068")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    integrity = generation_integrity(66, "E0068")
    if read_json(ATTEMPT / "rah-core-integrity.json") != integrity:
        raise SystemExit("stored I01 RAH core integrity differs from live generation")
    if read_json(ATTEMPT / "report.json") != report_document(integrity):
        raise SystemExit("stored I01 report differs from live evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"I01 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": integrity["current_generation"],
        "core_evidence_id": "E0068",
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
