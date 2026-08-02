#!/usr/bin/env python3
"""Build and verify byte-bound evidence for the F03-0002 correction.

F03-0002 closes the false-green transition-admission boundary discovered while
running F04-0002.  The verifier derives its conclusions from the canonical
GateDecision schema, the final F03/F04 source bytes, JUnit receipts, frozen
history, and the active manifest.  It deliberately preserves the outstanding
J02 and S04 failures instead of presenting either repository suite as green.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F03/attempts/0002"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/F03"
ATTEMPT_ID = "F03-0002"
WORK_PACKAGE_ID = "F03"
DECISION_ID = "HD-EF4-B04-SG002-20260730-001"
RECORDED_AT = "2026-07-30T12:56:49.095Z"

SOURCE_FILES = (
    "packages/foundry-kernel/src/forge/gates/transition-admission-gate.mjs",
    "packages/foundry-kernel/src/forge/gates/index.mjs",
    "packages/foundry-kernel/src/forge/gates/gate-test-support.mjs",
    "packages/foundry-kernel/src/forge/gates/transition-receipt.test.mjs",
    "packages/foundry-kernel/src/forge/gates/override-provenance.test.mjs",
)
F04_INTEGRATION_FILE = "tests/golden/forge/f04-test-support.mjs"
SCHEMA_PATH = "schemas/gate-decision.schema.json"
EXAMPLE_PATH = "examples/sample_gate_decision.json"
MANIFEST_PATH = "manifests/development_manifest.yaml"

FROZEN_HASHES = {
    "artifacts/work_packages/F03/attempts/0001/report.json":
        "99d7796d3f1a750be3e5531f51460846c3780b32b4b76622dfa96536811279c0",
    "artifacts/work_packages/F03/attempts/0001/commands.jsonl":
        "09fe971a28d9165476f39d4d80f1dce2088a4b09af34ebc47f35eb2871aafd78",
    "artifacts/work_packages/F03/attempts/0001/review.md":
        "427ec523544ca81ba3a54a0104d03c1f96478e5b9a7490c07e593dbe3947f879",
    "artifacts/work_packages/C03/attempts/0003/report.json":
        "624ee1ef8fb21ee33670e19b6262d3226e8350aaf291da8d90e94e8c46273a56",
    "artifacts/work_packages/C03/attempts/0003/commands.jsonl":
        "79144c7865dc2532c9f693a7d5f769f923f0f62e86abb29e236788ad5bc08206",
    "artifacts/work_packages/C03/attempts/0003/review.md":
        "0d796594f925740f548ecbc5fd2dae80007d141d092c5959c56b8d5223c4daec",
    "artifacts/authority_decisions/HD-EF4-B04-SG002-20260730-001.human-decision.json":
        "13feb432b4504e11fecabfed4b6fc51c17db315b7a7124106baa82ff1cd63ffe",
    "artifacts/authority_decisions/HD-EF4-B04-SG002-20260730-001.md":
        "c07d5dabf8ad367341c51c14ff9d8c3237d526a79b42c7b73a1a95c69da620d6",
    "artifacts/work_packages/B04/attempts/0006/node-failure-inventory.json":
        "b658c1662b98212018d9fd0259f4e2a9450b47b3f68cb05654b4af9c48622da3",
    "artifacts/work_packages/B04/attempts/0006/report.json":
        "a95d36efd6503bf83724b7da34b10285f1f7e7eae73e8f15e5ef4ff4e67a97ed",
    MANIFEST_PATH:
        "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
}

JUNIT_HASHES = {
    "targeted-node-suite.junit.xml":
        "1f7fb41600e2213ec95b7f80867a1b6b00710f2c2f70e94e82b372fe0b668c4c",
    "combined-f03-f04-node-suite.junit.xml":
        "20828c89de66383209a4e2fa2a9d4d7adea95803bf4f9442f189f532380ed21d",
    "full-node-suite.junit.xml":
        "a1c86ca241da1082eda87e0fbd19f39f8f1075a0c2bf4e4066cd7481b9fb928a",
    "full-python-suite.junit.xml":
        "eba919e71525d0e44fd1fc3de10ba41885502a21035f1d81ff510be9d09bdfbe",
}

GATE_FIELDS = (
    "gate_id",
    "gate_version",
    "run_id",
    "name",
    "status",
    "reasons",
    "evidence_ids",
    "input_artifact_ids",
    "policy_bundle_hash",
    "decision",
    "blocker_ids",
    "waiver_authority",
    "waiver_reason",
    "evaluated_at",
    "created_at",
    "policy_version",
    "non_waivable",
    "evaluator_type",
    "input_hash",
    "decision_hash",
)

NODE_TOTAL_PATTERNS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}

J02_TESTS = {
    "loader verifies all sealed production files and authority pointers":
        "EFREF-BACKEND-SHINKA-V4 authority source has changed",
    "ResolvedSkillContext is identical across 100 repeated sealed loads":
        "EFREF-CORE-CONSTITUTION-V4 authority source has changed",
}
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
J02_PYTHON_NODE = (
    "tests.test_j02_context_budget::"
    "test_repository_dependency_lock_closes_exact_tiktoken_pin"
)
J02_PYTHON_MESSAGE = (
    "TOKENIZER_CONTRACT_UNAVAILABLE: pyproject.toml does not declare exact "
    "tiktoken==0.13.0"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def canonical_hash_excluding(document: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(document)
    preimage.pop(field, None)
    payload = json.dumps(
        preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def assert_frozen_history() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in FROZEN_HASHES.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"frozen history/authority is missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(
                f"frozen history/authority changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    return observed


def source_inventory() -> list[dict[str, Any]]:
    gate_root = ROOT / "packages/foundry-kernel/src/forge/gates"
    actual = tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted(gate_root.iterdir(), key=lambda item: item.name)
        if path.is_file()
    )
    if set(actual) != set(SOURCE_FILES) or len(actual) != len(SOURCE_FILES):
        raise SystemExit(f"unexpected F03 source inventory: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in SOURCE_FILES:
        path = ROOT / relative
        content = path.read_bytes()
        if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
            raise SystemExit(f"invalid source encoding marker: {relative}")
        text = content.decode("utf-8")
        if "\ufffd" in text:
            raise SystemExit(f"replacement character in F03 source: {relative}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    implementation = (ROOT / SOURCE_FILES[0]).read_text(encoding="utf-8")
    if 'TRANSITION_ADMISSION_VERSION = "4.0.0-f03.2"' not in implementation:
        raise SystemExit("transition admission version is not 4.0.0-f03.2")
    for field in GATE_FIELDS:
        if f'"{field}"' not in implementation:
            raise SystemExit(f"runtime GateDecision field is missing: {field}")
    required_runtime_markers = (
        "GATE_DECISION_POLICY_MISMATCH",
        "GATE_INPUT_ARTIFACT_UNRESOLVED",
        "a status-valued GateDecision decision must equal its canonical status",
        "a policy-evidenced NOT_REQUIRED GateDecision must have status PASS",
    )
    for marker in required_runtime_markers:
        if marker not in implementation:
            raise SystemExit(f"runtime GateDecision guard is missing: {marker}")
    return rows


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    packages = raw if isinstance(raw, list) else raw.get("work_packages")
    if not isinstance(packages, list) or len(packages) != 156:
        raise SystemExit("development manifest is not the 156-package DAG")
    by_id = {row["id"]: row for row in packages}
    f03 = by_id["F03"]
    f04 = by_id["F04"]
    if f03.get("depends_on") != ["F01"]:
        raise SystemExit("F03 static dependency contract changed")
    if f03.get("write_scope") != ["packages/foundry-kernel/src/forge/gates/**"]:
        raise SystemExit("F03 write scope changed")
    if f03.get("required_checks") != [
        "transition_receipt_test",
        "override_provenance_test",
    ]:
        raise SystemExit("F03 required checks changed")
    if f04.get("depends_on") != ["F02", "F03"]:
        raise SystemExit("F04 does not remain bound to F02 and F03")
    return {
        "path": MANIFEST_PATH,
        "sha256": sha256_id(ROOT / MANIFEST_PATH),
        "package_count": len(packages),
        "f03_depends_on": f03["depends_on"],
        "f03_write_scope": f03["write_scope"],
        "f03_required_checks": f03["required_checks"],
        "f04_depends_on": f04["depends_on"],
    }


def schema_contract() -> dict[str, Any]:
    schema = read_json(ROOT / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    required = tuple(schema.get("required", []))
    properties = tuple(schema.get("properties", {}).keys())
    if required != GATE_FIELDS or properties != GATE_FIELDS:
        raise SystemExit("canonical GateDecision field inventory is not exact")
    if schema.get("additionalProperties") is not False:
        raise SystemExit("canonical GateDecision schema is not closed")
    validator = Draft202012Validator(schema)
    example = read_json(ROOT / EXAMPLE_PATH)
    errors = list(validator.iter_errors(example))
    if errors:
        raise SystemExit(f"canonical GateDecision example is invalid: {errors[0].message}")
    expected_hash = canonical_hash_excluding(example, "decision_hash")
    stored_hash = example.get("decision_hash")
    hash_recomputes = stored_hash == expected_hash
    not_required = copy.deepcopy(example)
    not_required["status"] = "PASS"
    not_required["decision"] = "NOT_REQUIRED"
    not_required["reasons"] = ["PolicyBundle marks this gate not required for this request."]
    not_required["decision_hash"] = canonical_hash_excluding(not_required, "decision_hash")
    errors = list(validator.iter_errors(not_required))
    if errors:
        raise SystemExit(f"policy-backed PASS/NOT_REQUIRED is schema-invalid: {errors[0].message}")
    return {
        "schema_path": SCHEMA_PATH,
        "schema_sha256": sha256_id(ROOT / SCHEMA_PATH),
        "example_path": EXAMPLE_PATH,
        "example_sha256": sha256_id(ROOT / EXAMPLE_PATH),
        "required_field_count": len(required),
        "property_count": len(properties),
        "additional_properties": False,
        "canonical_example_schema_validation": "PASS",
        "canonical_example_hash_recomputed": hash_recomputes,
        "canonical_example_stored_decision_hash": stored_hash,
        "canonical_example_expected_decision_hash": expected_hash,
        "canonical_example_hash_finding": (
            "NONE"
            if hash_recomputes
            else "PREEXISTING_CANONICAL_EXAMPLE_HASH_DEBT_OUTSIDE_F03_WRITE_SCOPE"
        ),
        "canonical_example_hash_is_f03_acceptance_gate": False,
        "canonical_example_hash_owner": "C01_CANONICAL_CONTRACT",
        "pass_not_required_schema_validation": "PASS",
    }


def node_junit(name: str) -> dict[str, Any]:
    path = ATTEMPT / name
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit(f"JUnit hash changed: {name}")
    content = path.read_bytes()
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SystemExit(f"invalid JUnit XML {name}: {error}") from error
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label}: {name}")
        totals[label] = int(matches[0])
    cases = list(root.iter("testcase"))
    failures: list[dict[str, str]] = []
    for testcase in cases:
        bad = testcase.find("failure")
        message = ""
        body = ""
        if bad is not None:
            message = (bad.get("message") or "").strip()
            body = (bad.text or "").strip()
        elif testcase.get("failure"):
            message = str(testcase.get("failure")).strip()
            body = message
        if message or body:
            failures.append(
                {
                    "name": str(testcase.get("name") or ""),
                    "file": str(testcase.get("file") or "").replace("\\", "/"),
                    "message": message,
                    "body": body,
                }
            )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "tap_totals": totals,
        "leaf_testcase_count": len(cases),
        "leaf_failure_count": len(failures),
        "failures": failures,
    }


def python_junit() -> dict[str, Any]:
    path = ATTEMPT / "full-python-suite.junit.xml"
    if sha256(path) != JUNIT_HASHES[path.name]:
        raise SystemExit("full Python JUnit hash changed")
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if len(suites) != 1:
        raise SystemExit("full Python JUnit does not contain exactly one suite")
    suite = suites[0]
    totals = {
        key: int(suite.get(key, "0"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    failures: list[dict[str, str]] = []
    for testcase in suite.iter("testcase"):
        bad = testcase.find("failure")
        if bad is None:
            bad = testcase.find("error")
        if bad is None:
            continue
        raw = (bad.get("message") or bad.text or "").strip()
        failures.append(
            {
                "node_id": f"{testcase.get('classname', '')}::{testcase.get('name', '')}",
                "message": raw,
                "body": (bad.text or "").strip(),
            }
        )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "failures": failures,
    }


def test_results() -> dict[str, Any]:
    targeted = node_junit("targeted-node-suite.junit.xml")
    combined = node_junit("combined-f03-f04-node-suite.junit.xml")
    full_node = node_junit("full-node-suite.junit.xml")
    full_python = python_junit()
    if targeted["tap_totals"] != {
        "tests": 23,
        "pass": 23,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or targeted["leaf_failure_count"] != 0:
        raise SystemExit("F03 targeted suite is not exact 23/23")
    if combined["tap_totals"] != {
        "tests": 31,
        "pass": 31,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or combined["leaf_failure_count"] != 0:
        raise SystemExit("combined F03/F04 suite is not exact 31/31")
    if full_node["tap_totals"] != {
        "tests": 460,
        "pass": 457,
        "fail": 3,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or full_node["leaf_failure_count"] != 3:
        raise SystemExit("full Node suite is not the expected 457 pass plus 3 failures")
    failures = {row["name"]: row for row in full_node["failures"]}
    if set(failures) != {*J02_TESTS, S04_TEST}:
        raise SystemExit(f"unexpected full Node failure inventory: {sorted(failures)}")
    for name, message in J02_TESTS.items():
        row = failures[name]
        fingerprint = f"{row['message']}\n{row['body']}"
        if (
            not row["file"].endswith("tests/node/j02-skill-context-loader.test.mjs")
            or message not in fingerprint
            or "MASTER_SPEC.md" not in fingerprint
            or "d4854c916594610e0503f9b017c57b0dbac9f52eef78b825b922fdf26b1a0fe3" not in fingerprint
        ):
            raise SystemExit(f"J02 Node failure fingerprint changed: {name}")
    s04 = failures[S04_TEST]
    s04_fingerprint = f"{s04['message']}\n{s04['body']}"
    if (
        not s04["file"].endswith("tests/security/s04-threat-model-traceability.test.mjs")
        or "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12" not in s04_fingerprint
        or "7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319" not in s04_fingerprint
    ):
        raise SystemExit("S04-TM004 failure fingerprint changed")
    if full_python["totals"] != {
        "tests": 987,
        "failures": 1,
        "errors": 0,
        "skipped": 0,
    } or len(full_python["failures"]) != 1:
        raise SystemExit("full Python suite is not the expected 986 pass plus J02 failure")
    python_failure = full_python["failures"][0]
    if (
        python_failure["node_id"] != J02_PYTHON_NODE
        or J02_PYTHON_MESSAGE not in python_failure["message"]
        or J02_PYTHON_MESSAGE not in python_failure["body"]
    ):
        raise SystemExit("J02 Python failure fingerprint changed")
    return {
        "targeted_node": targeted,
        "combined_f03_f04_node": combined,
        "full_node": full_node,
        "full_python": full_python,
    }


def run_repository_checks() -> dict[str, Any]:
    commands = {
        "repository_structure": ["node", "packages/repo-checks/check-structure.mjs"],
        "package_boundaries": ["node", "packages/repo-checks/check-boundaries.mjs"],
    }
    results: dict[str, Any] = {}
    for name, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0 or '"status": "PASS"' not in completed.stdout:
            raise SystemExit(f"{name} failed: {completed.stdout}\n{completed.stderr}")
        results[name] = {"status": "PASS", "exit_code": completed.returncode}
    syntax_files = tuple(path for path in SOURCE_FILES if path.endswith(".mjs"))
    for relative in syntax_files:
        completed = subprocess.run(
            ["node", "--check", relative],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise SystemExit(f"Node syntax check failed: {relative}: {completed.stderr}")
    diff = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            *SOURCE_FILES,
            F04_INTEGRATION_FILE,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if diff.returncode != 0 or diff.stdout.strip():
        raise SystemExit(f"scoped git diff check failed: {diff.stdout}{diff.stderr}")
    results["node_syntax"] = {"status": "PASS", "file_count": len(syntax_files)}
    results["scoped_git_diff_check"] = {"status": "PASS", "exit_code": 0}
    return results


def correction_verification(results: dict[str, Any]) -> dict[str, Any]:
    transition_tests = sum(
        1
        for row in ET.parse(ATTEMPT / "targeted-node-suite.junit.xml").getroot().iter("testcase")
        if str(row.get("file") or "").replace("\\", "/").endswith(
            "/forge/gates/transition-receipt.test.mjs"
        )
    )
    override_tests = sum(
        1
        for row in ET.parse(ATTEMPT / "targeted-node-suite.junit.xml").getroot().iter("testcase")
        if str(row.get("file") or "").replace("\\", "/").endswith(
            "/forge/gates/override-provenance.test.mjs"
        )
    )
    if (transition_tests, override_tests) != (17, 6):
        raise SystemExit(
            f"F03 targeted split is not exact 17+6: {transition_tests}+{override_tests}"
        )
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_id": DECISION_ID,
        "status": "PASS",
        "transition_admission_version": "4.0.0-f03.2",
        "canonical_gate_decision": schema_contract(),
        "source_inventory": source_inventory(),
        "integration_fixture": {
            "path": F04_INTEGRATION_FILE,
            "sha256": sha256_id(ROOT / F04_INTEGRATION_FILE),
            "owner": "F04",
            "used_only_as_integration_evidence": True,
        },
        "manifest_contract": manifest_contract(),
        "required_checks": {
            "transition_receipt_test": {
                "status": "PASS",
                "passed": transition_tests,
                "failed": 0,
                "skipped": 0,
            },
            "override_provenance_test": {
                "status": "PASS",
                "passed": override_tests,
                "failed": 0,
                "skipped": 0,
            },
        },
        "verified_guards": [
            "all 20 canonical GateDecision fields are required and hashed",
            "input_artifact_ids are non-empty, unique, and receipt-resolved",
            "policy_bundle_hash equals the active ForgeSessionState policy_hash",
            "status-valued conclusions equal status",
            "policy-backed NOT_REQUIRED is accepted only with status PASS",
            "FAIL and BLOCK remain transition-rejecting statuses",
            "transition admission version is 4.0.0-f03.2",
        ],
        "targeted_junit": results["targeted_node"],
        "combined_f03_f04_junit": results["combined_f03_f04_node"],
        "completion_ready": False,
    }


def regression_impact(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_DECLARED_J02_AND_S04_DEBT",
        "full_node": {
            **results["full_node"],
            "classification": "EXPECTED_LATER_ATTEMPT_FAILURES",
            "failure_owner_counts": {"J02": 2, "S04": 1},
            "f03_causal_failure_count": 0,
        },
        "full_python": {
            **results["full_python"],
            "classification": "EXPECTED_J02_0003_DEPENDENCY_DEBT",
            "failure_owner": "J02",
            "f03_causal_failure_count": 0,
        },
        "new_f03_failure_count": 0,
        "unexpected_failure_count": 0,
        "unexpected_skip_or_xfail_count": 0,
        "repository_fully_green": False,
        "canonical_example_debt": {
            "path": EXAMPLE_PATH,
            "classification": "PREEXISTING_OUTSIDE_F03_WRITE_SCOPE",
            "stored_decision_hash": schema_contract()[
                "canonical_example_stored_decision_hash"
            ],
            "expected_decision_hash": schema_contract()[
                "canonical_example_expected_decision_hash"
            ],
            "f03_acceptance_effect": "NONE",
            "owner": "C01_CANONICAL_CONTRACT",
            "must_be_reconciled_before_c04_full_conformance": True,
        },
        "next_resolving_attempts": ["F04-0002", "J02-0003", "S04-0003"],
    }


def dependency_status() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "completion_ready": False,
        "static_dag_changed": False,
        "manifest": manifest_contract(),
        "ordered_repair_sequence": [
            "C03-0003",
            "F03-0002",
            "F04-0002",
            "J02-0003",
            "S04-0003",
            "B04-0007",
            "C04-0002",
            "B04-0008",
        ],
        "completed": ["C03-0003", "F03-0002"],
        "next_attempt": "F04-0002",
        "waiting": ["J02-0003", "S04-0003", "B04-0007", "C04-0002", "B04-0008"],
    }


def review_text(verification: dict[str, Any], regression: dict[str, Any]) -> str:
    inventory = "\n".join(
        f"- `{row['path']}` — `{row['sha256']}`"
        for row in verification["source_inventory"]
    )
    return f"""# F03-0002 canonical GateDecision admission review

Status: `PASS_WITH_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires this correction sequence to run in the primary
session without Fleet or subagents. This review is procedurally separate from
the edit pass, but it is not actor-independent certification.

## Reviewed boundary

{inventory}

- `{F04_INTEGRATION_FILE}` — `{verification['integration_fixture']['sha256']}`
- `{SCHEMA_PATH}` — `{verification['canonical_gate_decision']['schema_sha256']}`
- `{EXAMPLE_PATH}` — `{verification['canonical_gate_decision']['example_sha256']}`

## Findings

1. F03 now consumes the canonical 20-field `GateDecision` shape instead of the
   earlier 14-field runtime projection. Unknown, missing, or forged fields fail
   before admission.
2. `input_artifact_ids` must be explicit and receipt-resolved, and
   `policy_bundle_hash` must equal the active session policy. This closes the
   false-green path that F04 exposed.
3. A conclusion equal to a gate status must match `status`. The separately
   canonical, policy-evidenced `NOT_REQUIRED` conclusion remains valid only
   with `status=PASS`; `FAIL/NOT_REQUIRED` is rejected.
4. The decision hash covers every semantic field except itself, including the
   version, inputs, policy, conclusion, waiver data, evaluator, and timestamps.
5. F03 targeted execution is 23/23 and the combined repaired F03/F04 path is
   31/31. No test is skipped or xfailed.
6. The repository is not globally green. Node retains exactly two J02 failures
   and one S04-TM004 failure; Python retains exactly the J02 `tiktoken==0.13.0`
   declaration failure. Their fingerprints match the authorized later repair
   attempts, and F03 causal failure count is zero.
7. The canonical GateDecision example is structurally valid, but its stored
   `decision_hash` does not recompute after the earlier 14-field to 20-field
   canonical expansion. Both official Python hash implementations produce
   `{verification['canonical_gate_decision']['canonical_example_expected_decision_hash']}`
   rather than the stored
   `{verification['canonical_gate_decision']['canonical_example_stored_decision_hash']}`.
   F03 neither modifies nor certifies that C01-owned example: its declared
   acceptance gates are `transition_receipt_test` and
   `override_provenance_test`. The mismatch remains explicit debt that must be
   reconciled before C04 full conformance.

## Assurance boundary

This review establishes the in-process transition-admission contract and its
current F04 integration. It does not declare J02, S04, full repository
conformance, final packaging, release readiness, or product completion.
`actor_independence=false`, `implementation_gate=fail`, and
`completion_ready=false` remain explicit.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect F03/F04 source, GateDecision authority, current RAH, and prior immutable evidence", 0, "PASS"),
        ("C002", "Run pre-repair F04 targeted suite", 1, "PRESERVED_REPRODUCTION: 0/8; runtime rejected gate_version"),
        ("C003", "Run pre-repair F03 targeted suite", 0, "PRESERVED_FALSE_GREEN: 21/21 against legacy runtime projection"),
        ("C004", "Implement canonical 20-field GateDecision admission and update bounded F03 fixtures/tests", 0, "PASS"),
        ("C005", "Run JavaScript syntax checks for F03 correction files", 0, "PASS: 4/4"),
        ("C006", "Run final F03 targeted Node suite with JUnit", 0, "PASS: 23/23"),
        ("C007", "Run final combined F03/F04 Node suite with JUnit", 0, "PASS: TAP 31/31"),
        ("C008", "Run full Python suite with JUnit", 1, "EXPECTED_LATER_DEBT: 986 passed; exact J02 tiktoken failure only"),
        ("C009", "Run full Node suite serially with JUnit", 1, "EXPECTED_LATER_DEBT: 457 passed; exact J02 x2 and S04 x1"),
        ("C010", "Run npm check:repo-structure and check:package-boundaries", 1, "PRESERVED_COMMAND_ERROR: script names do not exist; no state changed"),
        ("C011", "Run npm check:structure", 0, "PASS"),
        ("C012", "Run npm check:boundaries", 0, "PASS"),
        ("C013", "Run F03 evidence builder with initial Node JUnit failure parser", 1, "PRESERVED_BUILDER_FAILURE: short failure message omitted the detailed J02 fingerprint body; no evidence or RAH state committed"),
        ("C014", "Correct F03 evidence parser to inspect both JUnit failure message and body", 0, "PASS"),
        ("C015", "Run F03 evidence builder with canonical example hash assertion", 1, "PRESERVED_BUILDER_FAILURE: C01-owned sample_gate_decision.json stored hash does not recompute; no evidence or RAH state committed"),
        ("C016", "Compare sample GateDecision hash with domain hash_excluding and OpenAPI canonical_hash oracle", 0, "PASS: both official paths compute sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851; stored sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1 is stale"),
        ("C017", "Bound F03 evidence to its declared required checks and record the out-of-scope canonical example debt", 0, "PASS: mismatch remains visible and must be reconciled before C04"),
        ("C018", "Run scoped git diff check", 0, "PASS"),
        ("C019", "Primary-session separate review of final F03 bytes", 0, "PASS: actor_independence=false; zero F03-blocking findings"),
    ]
    return [
        {
            "command_id": f"{ATTEMPT_ID}-{suffix}",
            "command": command,
            "recorded_at_utc": RECORDED_AT,
            "exit_code": exit_code,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for suffix, command, exit_code, result in rows
    ]


def report_document(
    verification: dict[str, Any],
    regression: dict[str, Any],
    dependency: dict[str, Any],
    repository_checks: dict[str, Any],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_names = [
        "gate-decision-correction-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "targeted-node-suite.junit.xml",
        "combined-f03-f04-node-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "commands.jsonl",
        "review.md",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        evidence_names.append("rah-core-integrity.json")
    artifacts = [
        {
            "path": (ATTEMPT / name).relative_to(ROOT).as_posix(),
            "byte_size": (ATTEMPT / name).stat().st_size,
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in evidence_names
    ]
    result: dict[str, Any] = {
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "Canonical GateDecision transition-admission correction",
        "status": "PASS",
        "package_status": "PASS",
        "contract_status": "CONFORMANT",
        "completion_ready": False,
        "authority_decision_id": DECISION_ID,
        "supersedes_runtime_revision": "4.0.0-f03.1",
        "transition_admission_version": "4.0.0-f03.2",
        "write_scope": ["packages/foundry-kernel/src/forge/gates/**"],
        "changed_files": verification["source_inventory"],
        "integration_evidence": verification["integration_fixture"],
        "exit_criteria": {
            "no_prose_only_transition": "PASS",
            "human_override_remains_explicit": "PASS",
            "canonical_gate_decision_runtime_parity": "PASS",
        },
        "required_checks": verification["required_checks"],
        "targeted_results": {
            "f03": verification["targeted_junit"],
            "combined_f03_f04": verification["combined_f03_f04_junit"],
        },
        "regression": regression,
        "repository_checks": repository_checks,
        "review": {
            "status": "PASS_WITH_PRIMARY_SESSION_SEPARATE_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "actor_independence": False,
            "blocking_findings": 0,
            "subagents_used": False,
            "artifact": "artifacts/work_packages/F03/attempts/0002/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "history_and_worktree": {
            "prior_f03_attempt_preserved": True,
            "prior_c03_attempt_preserved": True,
            "prior_rah_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "write_scope_violation_count": 0,
        },
        "preserved_limitations": [
            "The C01-owned sample GateDecision stored decision_hash is stale and is not represented as passing.",
            "That canonical example debt must be reconciled by its owner before C04 full conformance.",
        ],
        "dependency_effect": dependency,
        "evidence_artifacts": artifacts,
        "global_status": {
            "implementation_gate": "fail",
            "completion_ready": False,
            "repository_fully_green": False,
            "next_attempt": "F04-0002",
        },
    }
    if rah_state is not None:
        result["rah_state"] = rah_state
    return result


def verification() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    assert_frozen_history()
    results = test_results()
    checks = run_repository_checks()
    verified = correction_verification(results)
    regression = regression_impact(results)
    dependency = dependency_status()
    return verified, regression, dependency, checks


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verified, regression, dependency, checks = verification()
    write_json(ATTEMPT / "gate-decision-correction-verification.json", verified)
    write_json(ATTEMPT / "full-regression-impact.json", regression)
    write_json(ATTEMPT / "dependency-status.json", dependency)
    (ATTEMPT / "review.md").write_text(
        review_text(verified, regression), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_records()
        ),
        encoding="utf-8",
        newline="\n",
    )
    write_json(
        ATTEMPT / "report.json",
        report_document(verified, regression, dependency, checks),
    )
    return verify()


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> dict[str, Any]:
    verified, regression, dependency, checks = verification()
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
    write_json(
        ATTEMPT / "report.json",
        report_document(
            verified,
            regression,
            dependency,
            checks,
            rah_state=rah_state,
        ),
    )
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    verified, regression, dependency, checks = verification()
    stored_report = read_json(ATTEMPT / "report.json")
    rah_state = stored_report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict):
            raise SystemExit("F03-0002 RAH binding is not an object")
        if not re.fullmatch(r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))):
            raise SystemExit("F03-0002 core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if not re.fullmatch(r"E\d{4,}", str(rah_state.get(key))):
                raise SystemExit(f"F03-0002 {key} binding is malformed")
    expected_json = {
        "gate-decision-correction-verification.json": verified,
        "full-regression-impact.json": regression,
        "dependency-status.json": dependency,
        "report.json": report_document(
            verified,
            regression,
            dependency,
            checks,
            rah_state=rah_state,
        ),
    }
    for name, value in expected_json.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(value):
            raise SystemExit(f"stored F03-0002 evidence differs from live inputs: {name}")
    expected_review = review_text(verified, regression)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != expected_review:
        raise SystemExit("stored F03-0002 review differs from final bytes")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored F03-0002 commands differ from deterministic record")
    for line in expected_commands.splitlines():
        json.loads(line)
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"F03 root projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "targeted_f03": "23/23",
        "combined_f03_f04": "31/31",
        "full_node": "457 passed, 3 expected later-attempt failures",
        "full_python": "986 passed, 1 expected J02 failure",
        "new_f03_failure_count": 0,
        "completion_ready": False,
        "rah_bound": rah_state is not None,
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
