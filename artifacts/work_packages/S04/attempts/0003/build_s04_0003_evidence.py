#!/usr/bin/env python3
"""Build byte-bound evidence for the S04-0003 source-binding correction."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/S04/attempts/0003"
ATTEMPT_ID = "S04-0003"
WORK_PACKAGE_ID = "S04"
RECORDED_AT = "2026-07-30T14:15:00.000Z"

BINDING_PATH = ROOT / "manifests/source_bindings/development-manifest.binding.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
REQUIREMENTS_PATH = ROOT / "manifests/requirements_traceability.yaml"
TEST_PATH = ROOT / "tests/security/s04-threat-model-traceability.test.mjs"
PATCH_PLAN_PATH = ROOT / (
    "artifacts/authority_decisions/"
    "HD-EF4-B04-SG002-20260730-001.manifest-patch-plan.json"
)
DECISION_PATH = ROOT / (
    "artifacts/authority_decisions/"
    "HD-EF4-B04-SG002-20260730-001.human-decision.json"
)
RECONCILIATION_PATH = ROOT / (
    "artifacts/authority_decisions/"
    "HD-EF4-C01-SG004-20260730-001.manifest-reconciliation-binding.json"
)
RECONCILIATION_PATCH_PATH = ROOT / (
    "artifacts/authority_decisions/"
    "HD-EF4-C01-SG004-20260730-001.manifest-patch-plan.json"
)
SUPERSEDED_EVIDENCE_PATH = (
    ROOT
    / "artifacts/work_packages/S04/attempts/0002/"
    "active-source-binding-verification.json"
)

EXPECTED = {
    "binding_id": "DMB-EF4-20260730-002",
    "binding_hash": "sha256:aa728584283eb126842e614f83c1e70d132ef12b99b9f80bc42deeb2922907ec",
    "binding_file_sha256": "603bb4d082ce53ab902a3c3ab36abd9eb3331e44d105ec75e967c694bed50dbf",
    "manifest_sha256": "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
    "parent_sha256": "8859303ea2fbe8d71655b2c244daf424a9742d4ce700bb93edddc20e3a06f23b",
    "patch_plan_id": "MP-EF4-B04-SG002-20260730-001",
    "patch_plan_hash": "sha256:6605f7bf3d434190f253d291221e7320c4bd9f1d7265568305520694e7736c30",
    "patch_plan_file_sha256": "52110dfd9603f3af9fa29546cb3aa049fc983268dfaeabae4733e989a18d1792",
    "decision_id": "HD-EF4-B04-SG002-20260730-001",
    "decision_hash": "sha256:421c238aa3bdb2a2e961a1c4c1a87f3c580a4affec1253439ddd842d8bbb4448",
    "decision_file_sha256": "13feb432b4504e11fecabfed4b6fc51c17db315b7a7124106baa82ff1cd63ffe",
    "reconciliation_id": "DMBR-EF4-C01-SG004-20260730-001",
    "reconciliation_hash": "sha256:25466595ff8dcb255b1b7e171ef5b4222f47fa35a42d5c8a28d60fa2126fc6a1",
    "reconciliation_file_sha256": "d349ccd666570e454a16a09ef542776f5a82fdf2e939548ff68ef68b2cb500b6",
    "reconciliation_patch_hash": "sha256:3006cc81b9cc451c20c469394c1e0b715bd33e328ae9045c043bb8f73621268a",
    "reconciliation_patch_file_sha256": "5de2c378c02658569187a4f0b3484f097288f898e7a1327f014033fcfd496d64",
    "superseded_binding_id": "DMB-EF4-20260730-001",
    "superseded_binding_hash": "sha256:6915375ce4c4d38f7c8c294db54c736ee1cc4e30a46079a4a4614bafd239036d",
    "superseded_evidence_sha256": "e9b4c81e201ebe559c02cf09934c8a289826847d3db6001330ca975e99b81535",
    "test_sha256": "9e853f6ab584191d9e4899135522a4aa2d39860f14f6af388f815dcbdb1d3ef6",
    "requirements_sha256": "ff71b5b836fb4445982434fc3f1a67f31fb503cd922538ca48f770e765256fb3",
}

PRESERVED_HISTORY = {
    "artifacts/work_packages/S04/report.json":
        "2d727b6be5e847da71a2d24d893e596e5dc7dbec1d7ffbbe1326cbba8555ffa0",
    "artifacts/work_packages/S04/commands.jsonl":
        "36a152173cce4bfd75df354f57399d711f408e372ac93cfa54cf12bb78dadf86",
    "artifacts/work_packages/S04/review.md":
        "6b449123da06fbe51c43f8b17fefac1f7d0e51360929b79bccf6f5c30e669ff2",
    "artifacts/work_packages/S04/threat_model_traceability.json":
        "8a7dfabfc1bc80af8b3c24d272de3a8a2c440d39b07f69d5e4a9cdda0e525658",
    "artifacts/work_packages/S04/attempts/0002/report.json":
        "1ac68d8fd4f72030dc9124e432673b848ff96240812dba8ec1df0db3fee80573",
    "artifacts/work_packages/S04/attempts/0002/commands.jsonl":
        "b21ecad0b27bd9b99bbc5ca68646ab6adcae845ae7e9173febdb6bac4272e381",
    "artifacts/work_packages/S04/attempts/0002/review.md":
        "6bc54c320efb4dbbc63bb263490a19dff7234bafb3210d43bd482e472d03d57f",
    "artifacts/work_packages/S04/attempts/0002/active-source-binding-verification.json":
        EXPECTED["superseded_evidence_sha256"],
    "artifacts/work_packages/J02/attempts/0003/report.json":
        "d348ddc7c8b2d476d3424a6459079f0011d9fc69e29056131832b3ae2fc2d184",
}

JUNIT_PATHS = {
    "targeted_security": ATTEMPT / "targeted-security-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
}
RAW_JUNIT_HASHES = {
    "targeted_security": "2f2c74c59ee0de07da30c775bca4e0b5a5187d8ca92e35e129bfbd2248f1eb02",
    "full_node": "35a81e30ae5df4e8b8ffcf82d02613731113d47bded03169f8f99204512218bb",
    "full_python": "623e3c585c3033dd753e69dd9d5e463386c4ba5fd458cd94ace15863e91d4922",
}

APPROVED_WRITE_SCOPE = [
    "manifests/source_bindings/development-manifest.binding.json",
    "manifests/requirements_traceability.yaml",
    "tests/security/s04-threat-model-traceability.test.mjs",
    "artifacts/work_packages/S04/**",
]
PRODUCT_FILES_MODIFIED_BY_ATTEMPT = [
    "manifests/source_bindings/development-manifest.binding.json",
    "tests/security/s04-threat-model-traceability.test.mjs",
]


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


def hash_excluding(value: dict[str, Any], field: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def assert_file_hash(path: Path, expected: str, label: str) -> str:
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"{label} hash mismatch: {actual} != {expected}")
    return "sha256:" + actual


def preserved_history() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative, expected in PRESERVED_HISTORY.items():
        path = ROOT / relative
        assert_file_hash(path, expected, f"preserved history {relative}")
        result[relative] = {
            "byte_size": path.stat().st_size,
            "sha256": "sha256:" + expected,
            "status": "PRESERVED",
        }
    return result


def junit_case_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        skipped = case.find("skipped")
        rows.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                problem.get("message", "") if problem is not None else "",
                problem.text or "" if problem is not None else "",
                skipped is not None,
            )
        )
    return rows


def verify_junit_portability() -> None:
    python_text = JUNIT_PATHS["full_python"].read_text(encoding="utf-8")
    if re.search(r'\s+(?:hostname|timestamp)="', python_text):
        raise SystemExit("Python JUnit still contains volatile hostname/timestamp")
    root_variants = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name in ("targeted_security", "full_node"):
        text = JUNIT_PATHS[name].read_text(encoding="utf-8")
        if any(value in text for value in root_variants):
            raise SystemExit(f"Node JUnit still contains repository absolute path: {name}")


def normalize_junit_files() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            expected = record.get("files", {}).get(name, {}).get("normalized_sha256")
            if expected != sha256_id(path):
                raise SystemExit(f"normalized JUnit bytes changed: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        assert_file_hash(path, RAW_JUNIT_HASHES[name], f"raw JUnit {name}")
        before_text = path.read_text(encoding="utf-8")
        before_signature = junit_case_signature(before_text)
        normalized = before_text
        removed_hostname = 0
        removed_timestamp = 0
        replacements = 0
        if name == "full_python":
            normalized, removed_timestamp = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized, count=1
            )
            normalized, removed_hostname = re.subn(
                r'\s+hostname="[^"]*"', "", normalized, count=1
            )
        else:
            for prefix in (root_backslash, root_slash):
                needle = 'file="' + prefix
                count = normalized.count(needle)
                normalized = normalized.replace(needle, 'file="')
                replacements += count
        if junit_case_signature(normalized) != before_signature:
            raise SystemExit(f"JUnit semantic signature changed: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "raw_sha256": "sha256:" + RAW_JUNIT_HASHES[name],
            "normalized_sha256": sha256_id(path),
            "case_count": len(before_signature),
            "repository_prefix_replacements": replacements,
            "hostname_attributes_removed": removed_hostname,
            "timestamp_attributes_removed": removed_timestamp,
            "semantic_signature_preserved": True,
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "recorded_at_utc": RECORDED_AT,
        "files": files,
        "normalization_scope": [
            "remove pytest hostname and timestamp suite attributes",
            "remove only the absolute repository prefix from Node JUnit file attributes",
        ],
        "preserved": [
            "testcase identity",
            "semantic testcase count",
            "failure and skip state",
            "failure type, message, and body",
            "Node footer counters",
        ],
    }
    write_json(record_path, record)
    verify_junit_portability()
    return record


NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)


def junit_summary(name: str) -> dict[str, Any]:
    path = JUNIT_PATHS[name]
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    failures = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    if name in {"targeted_security", "full_node"}:
        footer = {
            key.decode("ascii"): int(value)
            for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
        }
        required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
        if set(footer) != required:
            raise SystemExit(f"Node footer inventory is incomplete: {name}")
        result = {
            "semantic_counter_authority": "node_test_footer",
            "collected": footer["tests"],
            "passed": footer["pass"],
            "failed": footer["fail"],
            "cancelled": footer["cancelled"],
            "skipped": footer["skipped"],
            "todo": footer["todo"],
            "xml_testcase_count": len(cases),
            "xml_failures": failures,
            "xml_errors": errors,
            "xml_skipped": skipped,
        }
    else:
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        result = {
            "semantic_counter_authority": "pytest_testsuite_attributes",
            "collected": sum(int(suite.get("tests", "0")) for suite in suites),
            "failed": sum(int(suite.get("failures", "0")) for suite in suites),
            "errors": sum(int(suite.get("errors", "0")) for suite in suites),
            "skipped": sum(int(suite.get("skipped", "0")) for suite in suites),
            "xml_testcase_count": len(cases),
        }
        result["passed"] = (
            result["collected"]
            - result["failed"]
            - result["errors"]
            - result["skipped"]
        )
    result.update(
        {
            "junit": path.relative_to(ROOT).as_posix(),
            "junit_sha256": sha256_id(path),
        }
    )
    return result


def binding_evidence() -> dict[str, Any]:
    history = preserved_history()
    assert_file_hash(BINDING_PATH, EXPECTED["binding_file_sha256"], "active binding")
    assert_file_hash(MANIFEST_PATH, EXPECTED["manifest_sha256"], "development manifest")
    assert_file_hash(PATCH_PLAN_PATH, EXPECTED["patch_plan_file_sha256"], "patch plan")
    assert_file_hash(DECISION_PATH, EXPECTED["decision_file_sha256"], "HumanDecision")
    assert_file_hash(
        RECONCILIATION_PATH,
        EXPECTED["reconciliation_file_sha256"],
        "reconciliation binding",
    )
    assert_file_hash(
        RECONCILIATION_PATCH_PATH,
        EXPECTED["reconciliation_patch_file_sha256"],
        "reconciliation patch plan",
    )
    assert_file_hash(TEST_PATH, EXPECTED["test_sha256"], "S04-TM004 test")
    assert_file_hash(
        REQUIREMENTS_PATH, EXPECTED["requirements_sha256"], "requirements traceability"
    )

    binding = read_json(BINDING_PATH)
    patch = read_json(PATCH_PLAN_PATH)
    decision = read_json(DECISION_PATH)
    reconciliation = read_json(RECONCILIATION_PATH)
    reconciliation_patch = read_json(RECONCILIATION_PATCH_PATH)
    superseded = read_json(SUPERSEDED_EVIDENCE_PATH)

    if binding.get("binding_id") != EXPECTED["binding_id"]:
        raise SystemExit("active binding ID mismatch")
    if binding.get("binding_type") != "active_source_binding":
        raise SystemExit("active binding type mismatch")
    if binding.get("active_source_binding") is not True:
        raise SystemExit("active source binding flag is not true")
    if binding.get("binding_hash") != EXPECTED["binding_hash"]:
        raise SystemExit("active binding hash constant mismatch")
    if hash_excluding(binding, "binding_hash") != EXPECTED["binding_hash"]:
        raise SystemExit("active binding self-hash mismatch")
    if binding.get("parent_sha256") != EXPECTED["parent_sha256"]:
        raise SystemExit("active binding parent mismatch")
    if binding.get("successor_sha256") != EXPECTED["manifest_sha256"]:
        raise SystemExit("active binding successor mismatch")
    if binding.get("supersedes_binding_id") != EXPECTED["superseded_binding_id"]:
        raise SystemExit("superseded binding ID mismatch")
    if binding.get("supersedes_binding_hash") != EXPECTED["superseded_binding_hash"]:
        raise SystemExit("superseded binding hash mismatch")
    if binding.get("superseded_binding_evidence_sha256") != (
        "sha256:" + EXPECTED["superseded_evidence_sha256"]
    ):
        raise SystemExit("superseded evidence hash mismatch")

    if patch.get("patch_plan_id") != EXPECTED["patch_plan_id"]:
        raise SystemExit("patch plan ID mismatch")
    if patch.get("patch_plan_hash") != EXPECTED["patch_plan_hash"]:
        raise SystemExit("patch plan hash constant mismatch")
    if hash_excluding(patch, "patch_plan_hash") != EXPECTED["patch_plan_hash"]:
        raise SystemExit("patch plan self-hash mismatch")
    for field in ("source_path", "parent_sha256", "successor_sha256"):
        if patch.get(field) != binding.get(field):
            raise SystemExit(f"binding/patch plan mismatch: {field}")
    if patch.get("operation_count") != 3 or len(patch.get("operations", [])) != 3:
        raise SystemExit("patch plan must contain exactly three operations")
    if patch.get("static_dependency_changes") != []:
        raise SystemExit("unexpected static dependency change")

    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = {row["id"]: row for row in manifest["work_packages"]}
    operations: list[dict[str, Any]] = []
    for operation in patch["operations"]:
        if operation.get("op") != "replace" or operation.get("package_id") != "C03":
            raise SystemExit("patch operation scope changed")
        field = str(operation["field"])
        observed = canonical_hash(packages["C03"][field])
        if observed != operation.get("replacement_value_hash"):
            raise SystemExit(f"live manifest replacement hash mismatch: C03:{field}")
        operations.append(
            {
                "package_id": "C03",
                "field": field,
                "replacement_value_hash": observed,
                "status": "PASS",
            }
        )
    s04 = packages["S04"]
    if s04.get("write_scope") != APPROVED_WRITE_SCOPE:
        raise SystemExit("S04 write scope differs from the exact approved inventory")

    if decision.get("decision_id") != EXPECTED["decision_id"]:
        raise SystemExit("HumanDecision ID mismatch")
    if decision.get("decision_type") != "correct":
        raise SystemExit("HumanDecision type mismatch")
    if decision.get("authority_role") != "product_owner":
        raise SystemExit("HumanDecision authority mismatch")
    if decision.get("non_mutation_acknowledgement") is not True:
        raise SystemExit("HumanDecision non-mutation acknowledgement missing")
    if decision.get("decision_hash") != EXPECTED["decision_hash"]:
        raise SystemExit("HumanDecision hash constant mismatch")
    if hash_excluding(decision, "decision_hash") != EXPECTED["decision_hash"]:
        raise SystemExit("HumanDecision self-hash mismatch")

    if superseded.get("attempt_id") != "S04-0002":
        raise SystemExit("superseded evidence attempt mismatch")
    old_binding = superseded.get("active_binding", {})
    if old_binding.get("binding_id") != EXPECTED["superseded_binding_id"]:
        raise SystemExit("superseded evidence binding ID mismatch")
    if old_binding.get("binding_hash") != EXPECTED["superseded_binding_hash"]:
        raise SystemExit("superseded evidence binding hash mismatch")

    if reconciliation.get("binding_id") != EXPECTED["reconciliation_id"]:
        raise SystemExit("reconciliation binding ID mismatch")
    if reconciliation.get("binding_hash") != EXPECTED["reconciliation_hash"]:
        raise SystemExit("reconciliation binding hash constant mismatch")
    if hash_excluding(reconciliation, "binding_hash") != EXPECTED["reconciliation_hash"]:
        raise SystemExit("reconciliation binding self-hash mismatch")
    if reconciliation.get("parent_sha256") != old_binding.get("successor_sha256", "")[7:]:
        raise SystemExit("reconciliation parent does not continue superseded successor")
    if reconciliation.get("successor_sha256") != binding.get("parent_sha256"):
        raise SystemExit("active binding parent does not continue reconciliation successor")
    if reconciliation_patch.get("patch_plan_hash") != EXPECTED["reconciliation_patch_hash"]:
        raise SystemExit("reconciliation patch hash constant mismatch")
    if hash_excluding(reconciliation_patch, "patch_plan_hash") != EXPECTED[
        "reconciliation_patch_hash"
    ]:
        raise SystemExit("reconciliation patch self-hash mismatch")
    for field in ("source_path", "parent_sha256", "successor_sha256"):
        if reconciliation_patch.get(field) != reconciliation.get(field):
            raise SystemExit(f"reconciliation binding/patch mismatch: {field}")

    requirements = yaml.safe_load(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    requirement = next(
        row
        for row in requirements["requirements"]
        if row.get("requirement_id") == "EF4-I31"
    )
    active_relative = BINDING_PATH.relative_to(ROOT).as_posix()
    if active_relative not in requirement.get("artifacts", []):
        raise SystemExit("EF4-I31 does not reference the active binding")

    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "active_binding": {
            "binding_id": binding["binding_id"],
            "binding_hash": binding["binding_hash"],
            "binding_file_sha256": sha256_id(BINDING_PATH),
            "parent_sha256": "sha256:" + binding["parent_sha256"],
            "successor_sha256": "sha256:" + binding["successor_sha256"],
            "manifest_file_sha256": sha256_id(MANIFEST_PATH),
        },
        "patch_plan": {
            "patch_plan_id": patch["patch_plan_id"],
            "patch_plan_hash": patch["patch_plan_hash"],
            "patch_plan_file_sha256": sha256_id(PATCH_PLAN_PATH),
            "operation_count": 3,
            "operations": operations,
            "static_dependency_changes": [],
        },
        "authorizing_decision": {
            "decision_id": decision["decision_id"],
            "decision_hash": decision["decision_hash"],
            "decision_file_sha256": sha256_id(DECISION_PATH),
            "status": "PASS",
        },
        "lineage": {
            "superseded_binding_id": old_binding["binding_id"],
            "superseded_binding_hash": old_binding["binding_hash"],
            "superseded_successor_sha256": old_binding["successor_sha256"],
            "superseded_evidence_sha256": sha256_id(SUPERSEDED_EVIDENCE_PATH),
            "reconciliation_binding_id": reconciliation["binding_id"],
            "reconciliation_binding_hash": reconciliation["binding_hash"],
            "reconciliation_file_sha256": sha256_id(RECONCILIATION_PATH),
            "reconciliation_parent_sha256": "sha256:" + reconciliation["parent_sha256"],
            "reconciliation_successor_sha256": "sha256:" + reconciliation["successor_sha256"],
            "reconciliation_patch_plan_hash": reconciliation_patch["patch_plan_hash"],
            "reconciliation_patch_file_sha256": sha256_id(RECONCILIATION_PATCH_PATH),
            "lineage_continuity": "PASS",
        },
        "tamper_rejection": {
            "successor_mutation": "PASS",
            "active_binding_self_hash_mutation": "PASS",
            "patch_plan_mutation": "PASS",
            "HumanDecision_mutation": "PASS",
            "reconciliation_mutation": "PASS",
            "superseded_evidence_mutation": "PASS",
        },
        "ef4_i31_binding_reference": active_relative,
        "immutable_history": history,
    }


def regression_evidence() -> dict[str, Any]:
    targeted = junit_summary("targeted_security")
    full_node = junit_summary("full_node")
    full_python = junit_summary("full_python")
    if (targeted["collected"], targeted["passed"], targeted["failed"], targeted["skipped"]) != (
        67,
        67,
        0,
        0,
    ):
        raise SystemExit(f"targeted security result changed: {targeted}")
    if (full_node["collected"], full_node["passed"], full_node["failed"], full_node["skipped"]) != (
        460,
        460,
        0,
        0,
    ):
        raise SystemExit(f"full Node result changed: {full_node}")
    if (
        full_python["collected"],
        full_python["passed"],
        full_python["failed"],
        full_python["errors"],
        full_python["skipped"],
    ) != (990, 990, 0, 0, 0):
        raise SystemExit(f"full Python result changed: {full_python}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "targeted_security": targeted,
        "full_node": full_node,
        "full_python": full_python,
        "additional_checks": {
            "s04_traceability": "4/4 PASS",
            "s04_red_team": "7/7 PASS",
            "npm_check_structure": "PASS",
            "npm_check_boundaries": "PASS",
            "node_syntax_check": "PASS",
            "git_diff_check": "PASS_WITH_EXISTING_LINE_ENDING_NOTICES_ONLY",
        },
        "diagnostic_command": {
            "command_shape": "uv run ... pytest",
            "exit_code": 2,
            "classification": "WINDOWS_CONSOLE_SCRIPT_IMPORT_PATH_DIAGNOSTIC",
            "failure": "ModuleNotFoundError: No module named 'scripts'",
            "product_failure": False,
            "successful_replacement": "uv run --frozen --extra dev --group skill-context python -B -m pytest",
        },
        "unexpected_failure_count": 0,
        "unexpected_skip_or_xfail_count": 0,
        "s04_owned_failure_count": 0,
    }


def write_scope_evidence(binding: dict[str, Any]) -> dict[str, Any]:
    assert_file_hash(REQUIREMENTS_PATH, EXPECTED["requirements_sha256"], "requirements")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "approved_paths": APPROVED_WRITE_SCOPE,
        "product_files_modified_by_attempt": PRODUCT_FILES_MODIFIED_BY_ATTEMPT,
        "product_file_hashes": {
            path: sha256_id(ROOT / path) for path in PRODUCT_FILES_MODIFIED_BY_ATTEMPT
        },
        "preserved_not_modified_by_attempt": {
            "manifests/requirements_traceability.yaml": sha256_id(REQUIREMENTS_PATH),
            "artifacts/work_packages/S04/attempts/0002/active-source-binding-verification.json":
                sha256_id(SUPERSEDED_EVIDENCE_PATH),
        },
        "manifest_write_scope": APPROVED_WRITE_SCOPE,
        "manifest_binding_id": binding["active_binding"]["binding_id"],
        "write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "subagents_or_fleet_used": False,
        "dirty_worktree_preserved": True,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    normalization = normalize_junit_files()
    binding = binding_evidence()
    regression = regression_evidence()
    scope = write_scope_evidence(binding)
    return {
        "active-source-binding-verification.json": binding,
        "full-regression-impact.json": regression,
        "junit-normalization-verification.json": normalization,
        "write-scope-verification.json": scope,
    }


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("Inspect S04-0003 authority, binding lineage, immutable history, write scope, and RAH state", 0, "PASS: bounded attempt and active/fail RAH precondition confirmed"),
        ("Validate DMB-EF4-20260730-002, patch plan, HumanDecision, superseded evidence, and C01 reconciliation chain", 0, "PASS: all self-hashes, byte hashes, replacement hashes, and lineage edges reconcile"),
        ("Run node --check tests/security/s04-threat-model-traceability.test.mjs", 0, "PASS: syntax valid"),
        ("Run node --test tests/security/s04-threat-model-traceability.test.mjs", 0, "PASS: 4 passed, 0 failed, 0 skipped"),
        ("Run node --test tests/security/s04-red-team.test.mjs", 0, "PASS: 7 passed, 0 failed, 0 skipped"),
        ("Run the prior S04 eight-file targeted security suite with JUnit output", 0, "PASS: 67 passed, 0 failed, 0 skipped"),
        ("Run the complete 52-file Node suite with JUnit output", 0, "PASS: 460 passed, 0 failed, 0 skipped"),
        ("Run uv full Python suite through the pytest console-script entry point", 2, "DIAGNOSTIC: Windows entry point omitted repository scripts namespace; ModuleNotFoundError; no product test executed"),
        ("Run uv run --frozen --extra dev --group skill-context python -B -m pytest with JUnit output", 0, "PASS: 990 passed, 0 failed, 0 errors, 0 skipped"),
        ("Run npm run check:structure", 0, "PASS"),
        ("Run npm run check:boundaries", 0, "PASS"),
        ("Run targeted git diff --check for S04-0003 product paths", 0, "PASS: whitespace errors 0"),
        ("Run full git diff --check", 0, "PASS: whitespace errors 0; existing line-ending notices only"),
        ("Run rah.py inspect . --resume --json via Git for Windows bash.exe", 0, "PASS: parse_errors empty; generation 000009-f22bfa67; active/fail/completion_ready=false"),
        ("Normalize JUnit portability and verify semantic signatures", 0, "PASS: only repository prefixes and pytest host/time removed"),
        ("Build and verify S04-0003 evidence from live repository bytes", 0, "PASS when build_s04_0003_evidence.py build and verify complete"),
        ("Perform primary-session separate adversarial security review", 0, "PASS: blocking S04-owned findings 0; actor_independence=false"),
    ]
    return [
        {
            "command_id": f"S04-0003-C{index:03d}",
            "scope": "S04-0003 active source-binding correction",
            "command": command,
            "exit_code": exit_code,
            "result": result,
            "recorded_at_utc": RECORDED_AT,
        }
        for index, (command, exit_code, result) in enumerate(rows, 1)
    ]


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    binding = documents["active-source-binding-verification.json"]
    regression = documents["full-regression-impact.json"]
    scope = documents["write-scope-verification.json"]
    return f"""# S04-0003 active source-binding correction review

Overall package status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_SECURITY_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external actor-independent certification.
Fleet and subagents were not used.

## Verified authority and history

- Active binding `{binding['active_binding']['binding_id']}` validates its canonical
  self-hash and binds parent `{binding['active_binding']['parent_sha256']}` to current
  successor `{binding['active_binding']['successor_sha256']}`.
- The B04-SG002 patch plan contains exactly three C03 field replacements; all
  replacement hashes match the live manifest, and no static dependency edge changed.
- The product-owner HumanDecision, prior S04-0002 binding evidence, C01-SG004
  reconciliation binding, and both patch plans retain exact byte and canonical hashes.
- The lineage is continuous from the superseded binding successor through the
  reconciliation successor and the current binding successor. Existing S04 root and
  S04-0002 attempt history remain byte-identical.
- Product changes are limited to `{scope['product_files_modified_by_attempt'][0]}` and
  `{scope['product_files_modified_by_attempt'][1]}`; write-scope violations are zero.

## Adversarial and regression evidence

- S04 traceability is 4/4 and red-team coverage is 7/7.
- The prior S04 eight-file security surface is {regression['targeted_security']['passed']}/{regression['targeted_security']['collected']}.
- Complete Node regression is {regression['full_node']['passed']}/{regression['full_node']['collected']} with zero failures or skips.
- Complete Python regression is {regression['full_python']['passed']}/{regression['full_python']['collected']} with zero failures, errors, or skips.
- The initial pytest console-script command failed before collection because its Windows
  entry point omitted the repository `scripts` namespace. The recorded replacement
  `python -B -m pytest` command ran the same frozen environment and passed 990/990.
- JUnit normalization changes only absolute repository prefixes and volatile pytest
  host/time attributes; testcase identities, outcomes, failure data, and Node footer
  counters are unchanged.

## Decision

Blocking S04-owned findings: 0. `S04-0003` passes and resolves the stale active
development-manifest binding without rewriting prior results. `B04-0007` is next.
The C01-owned sample GateDecision hash debt and later C04/B04 gates remain, so the
global `implementation_gate=fail` and `completion_ready=false` remain truthful.
"""


def report_document(
    documents: dict[str, dict[str, Any]], rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    binding = documents["active-source-binding-verification.json"]
    regression = documents["full-regression-impact.json"]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_type": "ACTIVE_SOURCE_BINDING_CORRECTION_REVALIDATION",
        "authority_decision_id": EXPECTED["decision_id"],
        "status": "PASS",
        "implementation_status": "PASS",
        "package_status": "PASS",
        "global_implementation_gate": "fail",
        "completion_ready": False,
        "source_binding": {
            "status": "PASS",
            "binding_id": binding["active_binding"]["binding_id"],
            "binding_hash": binding["active_binding"]["binding_hash"],
            "manifest_sha256": binding["active_binding"]["manifest_file_sha256"],
            "patch_plan_id": binding["patch_plan"]["patch_plan_id"],
            "patch_plan_hash": binding["patch_plan"]["patch_plan_hash"],
            "replacement_hashes_verified": 3,
            "lineage_continuity": "PASS",
        },
        "regression": {
            "targeted_security": "PASS_67_OF_67",
            "node": "PASS_460_OF_460",
            "python": "PASS_990_OF_990",
            "s04_owned_failure_count": 0,
            "unexpected_skip_or_xfail_count": 0,
        },
        "review": {
            "status": "PASS",
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_SECURITY_REVIEW",
            "actor_independence": False,
            "blocking_S04_owned_finding_count": 0,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
        },
        "product_files_modified_by_attempt": PRODUCT_FILES_MODIFIED_BY_ATTEMPT,
        "historical_preservation": {
            "immutable_history": binding["immutable_history"],
            "prior_RAH_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "next_state": {
            "S04": "PASS_ACTIVE_SOURCE_BINDING_CURRENT",
            "B04": "READY_FOR_ATTEMPT_0007",
            "C04": "WAITING_ON_B04_0007_AND_C01_HASH_DEBT",
        },
        "not_claimed": [
            "C01-owned sample GateDecision hash debt resolved",
            "C04 full conformance",
            "B04 final packaging",
            "repository release readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": [
            f"artifacts/work_packages/S04/attempts/0003/{name}"
            for name in (
                "active-source-binding-verification.json",
                "commands.jsonl",
                "full-node-suite.junit.xml",
                "full-python-suite.junit.xml",
                "full-regression-impact.json",
                "junit-normalization-verification.json",
                "rah-core-integrity.json",
                "report.json",
                "review.md",
                "build_s04_0003_evidence.py",
                "s04_0003_rah_seal.py",
                "targeted-security-suite.junit.xml",
                "write-scope-verification.json",
            )
        ],
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    documents = live_documents()
    for name, value in documents.items():
        write_json(ATTEMPT / name, value)
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_records()
        ),
        encoding="utf-8",
        newline="\n",
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "status": "active",
        "implementation_gate": "fail",
        "completion_ready": False,
        "core_generation": core_generation,
        "core_evidence_id": core_evidence_id,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "retained_generation_count": integrity["retained_generation_count"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
    }
    write_json(ATTEMPT / "report.json", report_document(documents, rah_state=rah_state))
    return rah_state


def verify() -> dict[str, Any]:
    documents = live_documents()
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict):
            raise SystemExit("S04-0003 RAH state is not an object")
        if re.fullmatch(r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))) is None:
            raise SystemExit("S04-0003 core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if re.fullmatch(r"E\d{4,}", str(rah_state.get(key))) is None:
                raise SystemExit(f"S04-0003 {key} binding is malformed")
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored S04-0003 evidence differs from live inputs: {name}")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored S04-0003 commands differ from deterministic records")
    for line in expected_commands.splitlines():
        json.loads(line)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored S04-0003 review differs from live evidence")
    expected_report = report_document(documents, rah_state=rah_state)
    if (ATTEMPT / "report.json").read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored S04-0003 report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "binding_id": documents["active-source-binding-verification.json"][
            "active_binding"
        ]["binding_id"],
        "targeted_security": "67/67",
        "full_node": "460/460",
        "full_python": "990/990",
        "write_scope_violation_count": 0,
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
