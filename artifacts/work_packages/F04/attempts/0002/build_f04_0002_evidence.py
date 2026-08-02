#!/usr/bin/env python3
"""Build and verify byte-bound evidence for the F04-0002 revalidation.

F04-0002 re-runs the end-to-end FORGE golden flows after F03 corrected the
runtime GateDecision boundary.  This verifier refuses the earlier partial
Node receipt (which omitted two web test files), binds the complete 52-file
Node inventory, preserves both pre-repair reproduction receipts, and keeps
the outstanding J02, S04, and C01-owned canonical example debts explicit.
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
ATTEMPT = ROOT / "artifacts/work_packages/F04/attempts/0002"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/F04"
ATTEMPT_ID = "F04-0002"
WORK_PACKAGE_ID = "F04"
RECORDED_AT = "2026-07-30T14:02:00.000Z"

MANIFEST_PATH = "manifests/development_manifest.yaml"
SCHEMA_PATH = "schemas/gate-decision.schema.json"
EXAMPLE_PATH = "examples/sample_gate_decision.json"
RECEIPT_SCHEMA_PATH = "schemas/artifact-receipt.schema.json"

IMPLEMENTATION_FILES = (
    "tests/golden/forge/f04_forge_golden_flows.json",
    "tests/golden/forge/f04-test-support.mjs",
    "tests/golden/forge/f04_forge_golden_flows.test.mjs",
    "tests/golden/forge/f04_phase_artifact_reconciliation.test.mjs",
)

PRESERVED_HASHES = {
    "artifacts/work_packages/F02/attempts/0001/report.json":
        "4d6dae9525ac559cba26e59ff1ab93f7e94918e21076030c50c55f7022b3b152",
    "artifacts/work_packages/F03/attempts/0002/report.json":
        "bb70fa7718bac42169c4b529e52861733dac2d6c129482b9155f97154d9c44b9",
    "artifacts/work_packages/F04/attempts/0001/report.json":
        "1c7f1a00a684dd84fe08b9bfea83972cf5ed1fd04cb521a7b6c3a4f74f96a12a",
    "artifacts/work_packages/F04/attempts/0001/commands.jsonl":
        "faa801056fd6b9d3a5b5c1f2a0d10d78d281d4a3ae3682ff873d2ca103cddad9",
    "artifacts/work_packages/F04/attempts/0001/review.md":
        "607527730921afa7dc80c85bd7f43a7a47b11462f82ef49b6e41825da9855c8e",
    MANIFEST_PATH:
        "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
    SCHEMA_PATH:
        "ee341a7adab98d1814906c2f37b36cdbb03842b77ea8b52e94a164d061b7379c",
    EXAMPLE_PATH:
        "3680818e3376ab2592e6df0876ab6dcb67843bf73d3dbbb4c3ada366ba93b035",
}

JUNIT_HASHES = {
    "targeted-node-suite.junit.xml":
        "fa6d90191b59de1e5c589d559ee3e4b4abaab9c47a7d418ecb33422d581f8a54",
    "f03-targeted-node-suite.junit.xml":
        "70805812cc2a64dbc647d8609b31bf279f9a56e881a4b302ccea5be755636aad",
    "final-targeted-node-suite.junit.xml":
        "9338e4d98e7b9f13c3ab3f9a74be02c63be20eb37160d0bb9a7b168194a14cc4",
    "final-full-python-suite.junit.xml":
        "c99e3c2c0f5be7dea1dabe5e18c4168995cecb0b3488a8e223d95edc0fa54ab6",
    "final-full-node-suite.junit.xml":
        "ee85dbb6a9ede475007f3ec39423de4bfe9051b11fd99919655b206559c4e220",
    "final-full-node-suite-complete.raw.junit.xml":
        "39f0a53307c63fc8b529d0c02c6799415527cfa04134a1e3a1683b23961eebe1",
    "final-full-node-suite-complete.junit.xml":
        "d64dc7e1995c599352502fef06f1306bd9c7191e1439bf6dedf94cd2c92ce0b7",
}

RAW_BEFORE_NORMALIZATION = {
    "final-targeted-node-suite.junit.xml":
        "78403f9a5372260691f3b43b377a3de18ec606a670996bba5755219aa8561676",
    "final-full-python-suite.junit.xml":
        "5cfa72279422603aa9bfbcfac32f5e8cd30f4ac120305d85b5c8638679299fde",
    "final-full-node-suite.junit.xml":
        "3c2f8d7d22e932f44e695aa6946d83bc4487304290353fda1e41dc9a4c4b978f",
}

NODE_TOTAL_PATTERNS = {
    label: re.compile(rb"<!-- " + label.encode("ascii") + rb" ([0-9]+) -->")
    for label in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}

EXPECTED_CASES = [
    {
        "case_id": "E1_LOOKUP_MINIMUM",
        "path_kind": "MINIMUM",
        "signal": "LOOKUP",
        "missing_contract_flags": [],
        "expected_work_class": "E1",
        "expected_required_phases": ["F", "O", "E"],
    },
    {
        "case_id": "E3_MECHANISM_FULL",
        "path_kind": "FULL",
        "signal": "MECHANISM",
        "missing_contract_flags": [],
        "expected_work_class": "E3",
        "expected_required_phases": ["F", "O", "R", "G", "E"],
    },
    {
        "case_id": "E5_AMBIGUOUS_INTERVIEW_FULL",
        "path_kind": "FULL_WITH_INTERVIEW",
        "signal": "AMBIGUOUS",
        "missing_contract_flags": ["I01_AMBIGUOUS_SIGNAL"],
        "expected_work_class": "E5",
        "expected_required_phases": ["I", "F", "O", "R", "G", "E"],
    },
]

J02_NODE_TESTS = {
    "loader verifies all sealed production files and authority pointers":
        "EFREF-BACKEND-SHINKA-V4 authority source has changed",
    "ResolvedSkillContext is identical across 100 repeated sealed loads":
        "EFREF-CORE-CONSTITUTION-V4 authority source has changed",
}
S04_NODE_TEST = (
    "S04-TM004 traceability source bindings fail on undocumented contract drift"
)
J02_PYTHON_NODE = (
    "tests.test_j02_context_budget::"
    "test_repository_dependency_lock_closes_exact_tiktoken_pin"
)
J02_PYTHON_MESSAGE = (
    "TOKENIZER_CONTRACT_UNAVAILABLE: pyproject.toml does not declare exact "
    "tiktoken==0.13.0"
)
MASTER_SPEC_ACTIVE_HASH = (
    "d4854c916594610e0503f9b017c57b0dbac9f52eef78b825b922fdf26b1a0fe3"
)
S04_ACTUAL_HASH = (
    "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"
)
S04_EXPECTED_HASH = (
    "7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319"
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


def assert_frozen_inputs() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in PRESERVED_HASHES.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"preserved input/history is missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(
                f"preserved input/history changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    for name, expected in JUNIT_HASHES.items():
        path = ATTEMPT / name
        if not path.is_file() or sha256(path) != expected:
            actual = sha256(path) if path.is_file() else "MISSING"
            raise SystemExit(f"F04 JUnit changed: {name}: {actual} != {expected}")
    return observed


def source_inventory() -> list[dict[str, Any]]:
    actual = tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted(
            (ROOT / "tests/golden/forge").glob("f04*"), key=lambda item: item.name
        )
        if path.is_file()
    )
    if set(actual) != set(IMPLEMENTATION_FILES) or len(actual) != len(
        IMPLEMENTATION_FILES
    ):
        raise SystemExit(f"unexpected F04 source inventory: {actual}")
    fixture = read_json(ROOT / IMPLEMENTATION_FILES[0])
    if fixture != {"schema_version": "1.0.0", "cases": EXPECTED_CASES}:
        raise SystemExit("F04 golden fixture differs from the exact three-case contract")
    support = (ROOT / IMPLEMENTATION_FILES[1]).read_text(encoding="utf-8")
    for marker in (
        "Draft202012Validator",
        "compileForgePlan",
        "admitForgeTransition",
        "reduceForgeTransition",
        "replayForgeTransitionEvents",
        "persistTransitionRecord",
        "UNDERDETERMINED",
        "classification_identity_context",
        "reconcileGoldenFlows",
    ):
        if marker not in support:
            raise SystemExit(f"F04 support is missing required marker: {marker}")
    golden = (ROOT / IMPLEMENTATION_FILES[2]).read_text(encoding="utf-8")
    reconciliation = (ROOT / IMPLEMENTATION_FILES[3]).read_text(encoding="utf-8")
    for marker in (
        "UNDERDETERMINED is a receipt-bound truthful terminal outcome",
        "admission cannot bypass F02 classification identity context",
        "CLASSIFICATION_INTEGRITY_FAILED",
    ):
        if marker not in golden:
            raise SystemExit(f"F04 golden-flow test is missing {marker!r}")
    for marker in (
        "every expected F04 transition and phase set resolves exactly once",
        "a missing persisted transition fails closed",
    ):
        if marker not in reconciliation:
            raise SystemExit(f"F04 reconciliation test is missing {marker!r}")
    rows: list[dict[str, Any]] = []
    for relative in IMPLEMENTATION_FILES:
        path = ROOT / relative
        content = path.read_bytes()
        if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
            raise SystemExit(f"invalid F04 source encoding marker: {relative}")
        text = content.decode("utf-8")
        if "\ufffd" in text:
            raise SystemExit(f"replacement character in F04 source: {relative}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    return rows


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    packages = raw if isinstance(raw, list) else raw.get("work_packages")
    if not isinstance(packages, list) or len(packages) != 156:
        raise SystemExit("development manifest is not the 156-package DAG")
    identifiers = [row.get("id") for row in packages if isinstance(row, dict)]
    if len(set(identifiers)) != 156:
        raise SystemExit("development manifest package IDs are not unique")
    by_id = {row["id"]: row for row in packages}
    f04 = by_id["F04"]
    expected = {
        "depends_on": ["F02", "F03"],
        "write_scope": ["tests/golden/forge/**", "artifacts/work_packages/F04/**"],
        "required_checks": ["forge_golden_flows", "phase_artifact_reconciliation"],
        "exit_criteria": [
            "minimum paths and full paths pass",
            "UNDERDETERMINED is accepted outcome",
        ],
    }
    for key, value in expected.items():
        if f04.get(key) != value:
            raise SystemExit(f"F04 manifest {key} changed: {f04.get(key)!r}")
    return {
        "path": MANIFEST_PATH,
        "sha256": sha256_id(ROOT / MANIFEST_PATH),
        "package_count": 156,
        **expected,
    }


def normalized_file(value: str) -> str:
    result = value.replace("\\", "/")
    for marker in ("C:/dev/insight/Epistemic-Foundry/", "/workspace/"):
        if result.startswith(marker):
            result = result[len(marker):]
    return result


def assert_normalized_receipt(path: Path) -> None:
    content = path.read_bytes()
    forbidden = (
        b"hostname=",
        b"timestamp=",
        b" time=\"",
        b"C:/dev/insight/Epistemic-Foundry",
        b"C:\\dev\\insight\\Epistemic-Foundry",
    )
    if any(marker in content for marker in forbidden):
        raise SystemExit(f"volatile machine metadata remains: {path.name}")


def node_junit(name: str, *, normalized: bool) -> dict[str, Any]:
    path = ATTEMPT / name
    if normalized:
        assert_normalized_receipt(path)
    content = path.read_bytes()
    root = ET.fromstring(content)
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label}: {name}")
        totals[label] = int(matches[0])
    failures: list[dict[str, str]] = []
    tests: list[dict[str, str]] = []
    for case in root.findall(".//testcase"):
        row = {
            "name": str(case.get("name") or ""),
            "file": normalized_file(str(case.get("file") or "")),
        }
        tests.append(row)
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if bad is not None:
            failures.append(
                {
                    **row,
                    "message": (bad.get("message") or "").strip(),
                    "body": (bad.text or "").strip(),
                }
            )
    suites = [
        {
            "name": suite.get("name"),
            "tests": int(suite.get("tests", "0")),
            "failures": int(suite.get("failures", "0")),
            "skipped": int(suite.get("skipped", "0")),
        }
        for suite in root.findall(".//testsuite")
    ]
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "tap_totals": totals,
        "leaf_testcase_count": len(tests),
        "leaf_failure_count": len(failures),
        "test_file_count": len({row["file"] for row in tests}),
        "failures": failures,
        "tests": tests,
        "nested_suites": suites,
    }


def python_junit() -> dict[str, Any]:
    path = ATTEMPT / "final-full-python-suite.junit.xml"
    assert_normalized_receipt(path)
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
    for case in suite.iter("testcase"):
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if bad is None:
            continue
        failures.append(
            {
                "node_id": f"{case.get('classname', '')}::{case.get('name', '')}",
                "message": (bad.get("message") or "").strip(),
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


def expected_node_files() -> list[str]:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for top in ("packages", "tests", "web")
        for path in (ROOT / top).rglob("*.test.mjs")
        if path.is_file()
    )
    if len(files) != 52 or len(set(files)) != 52:
        raise SystemExit(f"live Node test inventory is not exact 52: {len(files)}")
    return files


def normalized_complete_bytes(raw: bytes) -> bytes:
    value = re.sub(rb'\s+(?:time|timestamp|hostname)="[^"]*"', b"", raw)
    value = value.replace(
        b"file:///C:/dev/insight/Epistemic-Foundry/", b"file:///workspace/"
    )
    value = value.replace(b"C:/dev/insight/Epistemic-Foundry/", b"")
    value = value.replace(b"C:\\dev\\insight\\Epistemic-Foundry\\", b"")
    return value


def test_results() -> dict[str, Any]:
    reproduction = node_junit("targeted-node-suite.junit.xml", normalized=False)
    false_green = node_junit("f03-targeted-node-suite.junit.xml", normalized=False)
    targeted = node_junit("final-targeted-node-suite.junit.xml", normalized=True)
    incomplete = node_junit("final-full-node-suite.junit.xml", normalized=True)
    raw_complete = node_junit(
        "final-full-node-suite-complete.raw.junit.xml", normalized=False
    )
    complete = node_junit("final-full-node-suite-complete.junit.xml", normalized=True)
    python = python_junit()

    if reproduction["tap_totals"] != {
        "tests": 8,
        "pass": 0,
        "fail": 8,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or reproduction["leaf_failure_count"] != 7:
        raise SystemExit("pre-repair F04 reproduction is not exact 0/8")
    reproduction_blob = "\n".join(
        row["message"] + "\n" + row["body"] for row in reproduction["failures"]
    )
    if "GateDecision.gate_version is not allowed" not in reproduction_blob:
        raise SystemExit("pre-repair F04 failure fingerprint changed")
    if false_green["tap_totals"] != {
        "tests": 21,
        "pass": 21,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }:
        raise SystemExit("preserved pre-repair F03 false-green receipt changed")
    if targeted["tap_totals"] != {
        "tests": 8,
        "pass": 8,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or targeted["leaf_failure_count"] != 0:
        raise SystemExit("final F04 targeted suite is not exact 8/8")
    golden_rows = [
        row
        for row in targeted["tests"]
        if row["file"].endswith("tests/golden/forge/f04_forge_golden_flows.test.mjs")
    ]
    reconcile_rows = [
        row
        for row in targeted["tests"]
        if row["file"].endswith(
            "tests/golden/forge/f04_phase_artifact_reconciliation.test.mjs"
        )
    ]
    parent_suites = [
        row
        for row in targeted["nested_suites"]
        if str(row.get("name") or "").startswith("forge_golden_flows:")
    ]
    if (len(golden_rows), len(parent_suites), len(reconcile_rows)) != (5, 1, 2):
        raise SystemExit("final F04 targeted split is not exact 5+1 and 2")

    expected_files = expected_node_files()
    incomplete_files = sorted({row["file"] for row in incomplete["tests"]})
    complete_files = sorted({row["file"] for row in complete["tests"]})
    missing = sorted(set(expected_files) - set(incomplete_files))
    if incomplete["tap_totals"] != {
        "tests": 428,
        "pass": 425,
        "fail": 3,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or missing != [
        "web/src/features/intake/frame-roundtrip.test.mjs",
        "web/src/features/intake/intake-ui.test.mjs",
    ]:
        raise SystemExit("partial Node diagnostic no longer proves the two-file omission")
    if complete_files != expected_files:
        raise SystemExit("complete Node JUnit does not cover the live 52-file inventory")
    if complete["tap_totals"] != {
        "tests": 460,
        "pass": 457,
        "fail": 3,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or complete["leaf_failure_count"] != 3:
        raise SystemExit("complete Node suite is not exact 457 pass plus 3 failures")
    raw_bytes = (ATTEMPT / "final-full-node-suite-complete.raw.junit.xml").read_bytes()
    normalized_bytes = (ATTEMPT / "final-full-node-suite-complete.junit.xml").read_bytes()
    if normalized_complete_bytes(raw_bytes) != normalized_bytes:
        raise SystemExit("normalized complete Node receipt does not derive from raw bytes")
    if raw_complete["tap_totals"] != complete["tap_totals"]:
        raise SystemExit("raw and normalized complete Node totals differ")

    failures = {row["name"]: row for row in complete["failures"]}
    if set(failures) != {*J02_NODE_TESTS, S04_NODE_TEST}:
        raise SystemExit(f"unexpected complete Node failures: {sorted(failures)}")
    for name, message in J02_NODE_TESTS.items():
        row = failures[name]
        blob = row["message"] + "\n" + row["body"]
        if (
            row["file"] != "tests/node/j02-skill-context-loader.test.mjs"
            or message not in blob
            or "MASTER_SPEC.md" not in blob
            or MASTER_SPEC_ACTIVE_HASH not in blob
        ):
            raise SystemExit(f"J02 Node fingerprint changed: {name}")
    s04 = failures[S04_NODE_TEST]
    s04_blob = s04["message"] + "\n" + s04["body"]
    if (
        s04["file"] != "tests/security/s04-threat-model-traceability.test.mjs"
        or S04_ACTUAL_HASH not in s04_blob
        or S04_EXPECTED_HASH not in s04_blob
    ):
        raise SystemExit("S04-TM004 Node fingerprint changed")

    if python["totals"] != {
        "tests": 987,
        "failures": 1,
        "errors": 0,
        "skipped": 0,
    } or len(python["failures"]) != 1:
        raise SystemExit("full Python suite is not exact 986 pass plus J02 failure")
    py_failure = python["failures"][0]
    if (
        py_failure["node_id"] != J02_PYTHON_NODE
        or J02_PYTHON_MESSAGE not in py_failure["message"]
        or J02_PYTHON_MESSAGE not in py_failure["body"]
    ):
        raise SystemExit("J02 Python failure fingerprint changed")

    for row in (reproduction, false_green, targeted, incomplete, raw_complete, complete):
        row.pop("tests", None)
        row.pop("nested_suites", None)
    return {
        "pre_repair_f04": reproduction,
        "pre_repair_f03_false_green": false_green,
        "final_targeted": targeted,
        "partial_node_diagnostic": {
            **incomplete,
            "accepted_as_full_suite": False,
            "missing_test_files": missing,
            "missing_leaf_tests": 32,
        },
        "complete_node_raw": raw_complete,
        "complete_node": complete,
        "full_python": python,
        "complete_node_test_files": expected_files,
    }


def flow_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in EXPECTED_CASES:
        phases = list(case["expected_required_phases"])
        rows.append(
            {
                "case_id": case["case_id"],
                "path_kind": case["path_kind"],
                "signal": case["signal"],
                "work_class": case["expected_work_class"],
                "required_phases": phases,
                "transition_count": len(phases) + 1,
                "phase_artifact_set_count": len(phases),
                "terminal_phase": "IDLE",
                "terminal_status": "COMPLETED",
                "scientific_outcome": "UNDERDETERMINED",
            }
        )
    return rows


def flow_verification(results: dict[str, Any]) -> dict[str, Any]:
    rows = flow_rows()
    return {
        "attempt_id": ATTEMPT_ID,
        "work_package_id": WORK_PACKAGE_ID,
        "status": "PASS",
        "required_check": "forge_golden_flows",
        "targeted_passed": 6,
        "targeted_failed": 0,
        "targeted_skipped": 0,
        "flow_count": 3,
        "flows": rows,
        "transition_count": 17,
        "phase_artifact_set_count": 14,
        "underdetermined_truthful_outcome_count": 3,
        "verified_contracts": [
            "E1 executes F-O-E and returns to IDLE",
            "E3 executes F-O-R-G-E and returns to IDLE",
            "E5 AMBIGUOUS executes I-F-O-R-G-E and returns to IDLE",
            "all 17 transitions pass corrected canonical F03 admission",
            "direct reduction, persistence, and strict replay are identical",
            "all 14 PhaseArtifactSets reconcile exactly once",
            "UNDERDETERMINED remains a successful truthful scientific outcome",
            "classification identity-context mutation fails closed",
        ],
        "source_inventory": source_inventory(),
        "targeted_junit": results["final_targeted"],
        "completion_ready": False,
    }


def phase_reconciliation() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "required_check": "phase_artifact_reconciliation",
        "targeted_passed": 2,
        "targeted_failed": 0,
        "targeted_skipped": 0,
        "flow_count": 3,
        "expected_transition_count": 17,
        "generated_transition_count": 17,
        "admitted_transition_count": 17,
        "reduced_transition_count": 17,
        "replayed_transition_count": 17,
        "persisted_transition_count": 17,
        "expected_phase_artifact_set_count": 14,
        "generated_phase_artifact_set_count": 14,
        "admitted_phase_artifact_set_count": 14,
        "underdetermined_terminal_outcome_count": 3,
        "failed_count": 0,
        "cancelled_count": 0,
        "missing_transition_ids": [],
        "duplicate_transition_ids": [],
        "missing_phase_artifact_set_ids": [],
        "negative_missing_persisted_transition_test": "PASS_FAIL_CLOSED",
    }


def canonical_debt() -> dict[str, Any]:
    schema = read_json(ROOT / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    example = read_json(ROOT / EXAMPLE_PATH)
    errors = list(Draft202012Validator(schema).iter_errors(example))
    if errors:
        raise SystemExit(f"canonical GateDecision example is invalid: {errors[0].message}")
    expected = canonical_hash_excluding(example, "decision_hash")
    stored = str(example.get("decision_hash"))
    if stored != (
        "sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1"
    ) or expected != (
        "sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851"
    ):
        raise SystemExit("canonical GateDecision example debt fingerprint changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PREEXISTING_CANONICAL_EXAMPLE_HASH_DEBT",
        "path": EXAMPLE_PATH,
        "owner": "C01_CANONICAL_CONTRACT",
        "schema_validation": "PASS",
        "stored_decision_hash": stored,
        "expected_decision_hash": expected,
        "f04_acceptance_effect": "NONE",
        "must_be_reconciled_before_c04_full_conformance": True,
        "hidden_or_repaired_by_f04": False,
    }


def normalization_verification(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "normalization_rule": (
            "remove hostname/timestamp/duration and workspace-root prefixes only; "
            "preserve test names, totals, messages, and authority hashes"
        ),
        "raw_before_normalization_sha256": {
            name: "sha256:" + value for name, value in RAW_BEFORE_NORMALIZATION.items()
        },
        "normalized_sha256": {
            name: "sha256:" + JUNIT_HASHES[name]
            for name in (
                "final-targeted-node-suite.junit.xml",
                "final-full-python-suite.junit.xml",
                "final-full-node-suite.junit.xml",
                "final-full-node-suite-complete.junit.xml",
            )
        },
        "complete_raw_sha256": (
            "sha256:" + JUNIT_HASHES[
                "final-full-node-suite-complete.raw.junit.xml"
            ]
        ),
        "complete_raw_preserved": True,
        "complete_raw_to_normalized_exact_transform": "PASS",
        "pre_repair_receipts_preserved": {
            "targeted-node-suite.junit.xml": results["pre_repair_f04"]["sha256"],
            "f03-targeted-node-suite.junit.xml": results[
                "pre_repair_f03_false_green"
            ]["sha256"],
        },
        "partial_node_receipt_rejected_as_full_suite": True,
        "partial_node_missing_test_files": results["partial_node_diagnostic"][
            "missing_test_files"
        ],
        "semantic_totals_and_failure_fingerprints_preserved": True,
    }


def regression_impact(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_DECLARED_J02_AND_S04_DEBT",
        "full_node": {
            **results["complete_node"],
            "classification": "EXPECTED_LATER_ATTEMPT_FAILURES",
            "failure_owner_counts": {"J02": 2, "S04": 1},
            "f04_causal_failure_count": 0,
            "complete_test_file_count": 52,
        },
        "full_python": {
            **results["full_python"],
            "classification": "EXPECTED_J02_0003_DEPENDENCY_DEBT",
            "failure_owner": "J02",
            "f04_causal_failure_count": 0,
        },
        "partial_node_diagnostic": results["partial_node_diagnostic"],
        "new_f04_failure_count": 0,
        "unexpected_failure_count": 0,
        "unexpected_skip_or_xfail_count": 0,
        "repository_fully_green": False,
        "canonical_example_debt": canonical_debt(),
        "next_resolving_attempts": ["J02-0003", "S04-0003"],
    }


def dependency_status() -> dict[str, Any]:
    f02 = read_json(ROOT / "artifacts/work_packages/F02/attempts/0001/report.json")
    f03 = read_json(ROOT / "artifacts/work_packages/F03/attempts/0002/report.json")
    if f02.get("status") != "PASS" or f02.get("attempt_id") != "F02-0001":
        raise SystemExit("F02 dependency is not the sealed PASS input")
    if (
        f03.get("status") != "PASS"
        or f03.get("attempt_id") != "F03-0002"
        or f03.get("contract_status") != "CONFORMANT"
    ):
        raise SystemExit("F03 corrected dependency is not sealed PASS/CONFORMANT")
    return {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "completion_ready": False,
        "static_dag_changed": False,
        "manifest": manifest_contract(),
        "dependencies": {
            "F02": {
                "attempt_id": "F02-0001",
                "status": "PASS",
                "report": "artifacts/work_packages/F02/attempts/0001/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/F02/attempts/0001/report.json"
                ),
            },
            "F03": {
                "attempt_id": "F03-0002",
                "status": "PASS",
                "contract_status": "CONFORMANT",
                "report": "artifacts/work_packages/F03/attempts/0002/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/F03/attempts/0002/report.json"
                ),
            },
        },
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
        "completed": ["C03-0003", "F03-0002", "F04-0002"],
        "next_attempt": "J02-0003",
        "waiting": ["S04-0003", "B04-0007", "C04-0002", "B04-0008"],
    }


def run_repository_checks() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, command in {
        "repository_structure": ["node", "packages/repo-checks/check-structure.mjs"],
        "package_boundaries": ["node", "packages/repo-checks/check-boundaries.mjs"],
    }.items():
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
        results[name] = {"status": "PASS", "exit_code": 0}
    for relative in IMPLEMENTATION_FILES[1:]:
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
        ["git", "diff", "--check", "--", "tests/golden/forge"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if diff.returncode != 0 or diff.stdout.strip():
        raise SystemExit(f"F04 scoped git diff check failed: {diff.stdout}{diff.stderr}")
    results["node_syntax"] = {"status": "PASS", "file_count": 3}
    results["scoped_git_diff_check"] = {"status": "PASS", "exit_code": 0}
    return results


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect F04 dependencies, frozen history, RAH state, and canonical GateDecision boundary", 0, "PASS"),
        ("C002", "Preserve and parse pre-repair F04 targeted reproduction", 1, "PRESERVED_REPRODUCTION: 0/8; runtime rejected gate_version"),
        ("C003", "Preserve and parse pre-repair F03 targeted receipt", 0, "PRESERVED_FALSE_GREEN: 21/21 against the legacy projection"),
        ("C004", "Bind F04 to sealed F03-0002 canonical GateDecision correction", 0, "PASS: dependency report is PASS/CONFORMANT"),
        ("C005", "Run JavaScript syntax checks for all F04 modules", 0, "PASS: 3/3"),
        ("C006", "Run final F04 targeted Node suite", 0, "PASS: 8/8"),
        ("C007", "Run full Python suite", 1, "EXPECTED_LATER_DEBT: 986 passed; exact J02 tiktoken failure only"),
        ("C008", "Run initial Node regression selection", 1, "DIAGNOSTIC_INCOMPLETE: 425 passed; J02 x2 and S04 x1; omitted exactly two web test files and 32 tests"),
        ("C009", "Compare initial Node receipt with live test-file inventory", 0, "PASS: incomplete receipt rejected as full-suite evidence"),
        ("C010", "Run all 52 Node test files serially", 1, "EXPECTED_LATER_DEBT: 457 passed; exact J02 x2 and S04 x1"),
        ("C011", "Normalize final JUnit receipts without changing semantic totals or failure fingerprints", 0, "PASS"),
        ("C012", "Run repository structure and package-boundary checks", 0, "PASS"),
        ("C013", "Run scoped git diff check", 0, "PASS"),
        ("C014", "Primary-session separate integration review of final F04 bytes", 0, "PASS: actor_independence=false; zero F04-blocking findings"),
        ("D001", "Attempt strict JUnit normalization comparison before path canonicalization", 1, "DIAGNOSTIC_ONLY: absolute stack paths changed the byte-level signature; no complete Node receipt was overwritten"),
        ("D002", "Normalize targeted and Python receipts before discovering partial Node inventory", 0, "PRESERVED_DIAGNOSTIC: semantic totals and messages retained"),
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


def review_text(
    flow: dict[str, Any], regression: dict[str, Any], normalization: dict[str, Any]
) -> str:
    inventory = "\n".join(
        f"- `{row['path']}` — `{row['sha256']}`" for row in flow["source_inventory"]
    )
    debt = regression["canonical_example_debt"]
    return f"""# F04-0002 F-phase end-to-end revalidation review

Status: `PASS_WITH_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking F04 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Actor independence: `false`

The product owner requires this repair sequence to run in the primary session
without Fleet or subagents. This is a procedurally separate review of the final
F04 bytes; it is not actor-independent certification.

## Reviewed boundary

{inventory}

- F02 sealed report — `{dependency_status()['dependencies']['F02']['report_sha256']}`
- F03-0002 sealed report — `{dependency_status()['dependencies']['F03']['report_sha256']}`
- complete normalized Node receipt — `{regression['full_node']['sha256']}`
- normalized Python receipt — `{regression['full_python']['sha256']}`

## Findings

1. F04 now consumes the corrected 20-field GateDecision runtime boundary sealed
   by F03-0002. The original 0/8 failure and the earlier 21/21 false-green F03
   receipt remain immutable reproduction evidence.
2. The exact E1, E3, and ambiguous E5 projections execute F-O-E, F-O-R-G-E,
   and I-F-O-R-G-E. Every path returns to IDLE with orchestration status
   COMPLETED and a truthful `UNDERDETERMINED` scientific outcome.
3. All 17 transition requests are admitted, reduced, replayed, and persisted.
   All 14 PhaseArtifactSets reconcile exactly once; removing a persisted
   transition fails closed.
4. The final F04 targeted suite is 8/8 with no skip or xfail.
5. The first Node regression receipt contained only 50 of 52 test files and
   omitted 32 intake UI tests. It is explicitly classified as a diagnostic and
   cannot satisfy the full-suite gate. The replacement receipt covers all 52
   files and reports 457 passes with exactly two J02 and one S04 failures.
6. Full Python reports 986 passes with only the exact J02 `tiktoken==0.13.0`
   declaration failure. No residual failure is caused by F04.
7. JUnit normalization removes only machine-local paths, timestamps, hostnames,
   and durations. The complete raw Node receipt is preserved at
   `{normalization['complete_raw_sha256']}` and derives byte-for-byte into the
   normalized receipt under the declared transform.
8. The C01-owned GateDecision example remains structurally valid but its stored
   hash `{debt['stored_decision_hash']}` does not equal the canonical
   recomputation `{debt['expected_decision_hash']}`. F04 does not hide or repair
   this debt; it remains mandatory before C04 full conformance.

## Assurance boundary

This evidence establishes deterministic in-process F-phase composition. It
does not certify distributed delivery, production external effects, J02, S04,
C04 conformance, final packaging, release readiness, or product completion.
`implementation_gate=fail` and `completion_ready=false` remain explicit.
"""


def make_receipt(flow_path: Path) -> dict[str, Any]:
    receipt = {
        "receipt_id": "AR-F04-0002-FORGE-GOLDEN-FLOW-VERIFICATION",
        "artifact_id": "F04-0002-FORGE-GOLDEN-FLOW-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(flow_path),
        "byte_size": flow_path.stat().st_size,
        "created_by": {"actor_id": "SVC-FOUNDRY-KERNEL-F04", "actor_type": "service"},
        "created_at": RECORDED_AT,
        "locator": flow_path.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {"check": "forge_golden_flows", "status": "PASS", "details": "6/6"},
            {"check": "phase_artifact_reconciliation", "status": "PASS", "details": "2/2"},
            {"check": "f04_targeted_gate", "status": "PASS", "details": "8/8"},
            {
                "check": "regression_fingerprint_reconciliation",
                "status": "PASS",
                "details": "F04 causal failures 0; exact J02 x3 and S04 x1 remain",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(ROOT / RECEIPT_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid F04 ArtifactReceipt: {errors[0].message}")
    return receipt


def report_document(
    flow: dict[str, Any],
    phase: dict[str, Any],
    regression: dict[str, Any],
    normalization: dict[str, Any],
    dependency: dict[str, Any],
    checks: dict[str, Any],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_names = [
        "forge-golden-flow-verification.json",
        "phase-artifact-reconciliation.json",
        "full-regression-impact.json",
        "canonical-debt-reconciliation.json",
        "junit-normalization-verification.json",
        "dependency-status.json",
        "forge-golden-flow-verification.artifact-receipt.json",
        "targeted-node-suite.junit.xml",
        "f03-targeted-node-suite.junit.xml",
        "final-targeted-node-suite.junit.xml",
        "final-full-python-suite.junit.xml",
        "final-full-node-suite.junit.xml",
        "final-full-node-suite-complete.raw.junit.xml",
        "final-full-node-suite-complete.junit.xml",
        "commands.jsonl",
        "review.md",
        "build_f04_0002_evidence.py",
        "f04_0002_rah_seal.py",
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
        "title": "F-phase end-to-end E1/E3/E5 flows after canonical GateDecision correction",
        "status": "PASS",
        "package_status": "PASS",
        "contract_status": "CONFORMANT",
        "completion_ready": False,
        "write_scope": ["tests/golden/forge/**", "artifacts/work_packages/F04/**"],
        "changed_files": flow["source_inventory"],
        "dependencies": dependency["dependencies"],
        "exit_criteria": {
            "minimum_and_full_paths_pass": "PASS",
            "underdetermined_is_accepted_outcome": "PASS",
        },
        "required_checks": {
            "forge_golden_flows": {"status": "PASS", "passed": 6, "failed": 0},
            "phase_artifact_reconciliation": {
                "status": "PASS",
                "passed": 2,
                "failed": 0,
            },
            "f04_targeted_gate": {
                "status": "PASS",
                "passed": 8,
                "failed": 0,
                "skipped": 0,
            },
        },
        "flow_reconciliation": {
            "flow_count": phase["flow_count"],
            "transition_count": phase["expected_transition_count"],
            "phase_artifact_set_count": phase["expected_phase_artifact_set_count"],
            "missing_count": 0,
            "duplicate_count": 0,
            "failed_count": 0,
            "cancelled_count": 0,
            "underdetermined_outcome_count": 3,
        },
        "regression": {
            "python": {
                "status": "EXPECTED_J02_0003_DEPENDENCY_DEBT",
                "passed": 986,
                "failed": 1,
                "skipped": 0,
                "f04_causal_failure_count": 0,
            },
            "node": {
                "status": "EXPECTED_J02_AND_S04_LATER_ATTEMPT_DEBT",
                "passed": 457,
                "failed": 3,
                "skipped": 0,
                "test_file_count": 52,
                "f04_causal_failure_count": 0,
            },
            "partial_node_receipt_accepted": False,
            "repository_fully_green": False,
        },
        "canonical_example_debt": regression["canonical_example_debt"],
        "normalization": normalization,
        "repository_checks": checks,
        "review": {
            "status": "PASS_WITH_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW",
            "actor_independence": False,
            "blocking_findings": 0,
            "subagents_used": False,
            "artifact": "artifacts/work_packages/F04/attempts/0002/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "history_and_worktree": {
            "prior_f04_attempt_preserved": True,
            "f03_correction_evidence_preserved": True,
            "prior_rah_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "write_scope_violation_count": 0,
        },
        "preserved_limitations": [
            "F04 proves deterministic in-process composition, not distributed exactly-once execution.",
            "Review is primary-session separate and not actor-independent certification.",
            "J02 and S04 residual failures remain explicit and are owned by their next authorized attempts.",
            "The C01-owned sample GateDecision decision_hash remains stale and must be reconciled before C04.",
        ],
        "dependency_effect": dependency,
        "evidence_artifacts": artifacts,
        "artifact_receipt": {
            "path": (
                "artifacts/work_packages/F04/attempts/0002/"
                "forge-golden-flow-verification.artifact-receipt.json"
            ),
            "receipt_id": "AR-F04-0002-FORGE-GOLDEN-FLOW-VERIFICATION",
        },
        "global_status": {
            "implementation_gate": "fail",
            "completion_ready": False,
            "repository_fully_green": False,
            "next_attempt": "J02-0003",
        },
    }
    if rah_state is not None:
        result["rah_state"] = rah_state
    return result


def live_documents() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    assert_frozen_inputs()
    results = test_results()
    flow = flow_verification(results)
    phase = phase_reconciliation()
    regression = regression_impact(results)
    normalization = normalization_verification(results)
    dependency = dependency_status()
    checks = run_repository_checks()
    return flow, phase, regression, normalization, dependency, checks


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    flow, phase, regression, normalization, dependency, checks = live_documents()
    write_json(ATTEMPT / "forge-golden-flow-verification.json", flow)
    write_json(ATTEMPT / "phase-artifact-reconciliation.json", phase)
    write_json(ATTEMPT / "full-regression-impact.json", regression)
    write_json(
        ATTEMPT / "canonical-debt-reconciliation.json",
        regression["canonical_example_debt"],
    )
    write_json(ATTEMPT / "junit-normalization-verification.json", normalization)
    write_json(ATTEMPT / "dependency-status.json", dependency)
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_records()
        ),
        encoding="utf-8",
        newline="\n",
    )
    (ATTEMPT / "review.md").write_text(
        review_text(flow, regression, normalization), encoding="utf-8", newline="\n"
    )
    write_json(
        ATTEMPT / "forge-golden-flow-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "forge-golden-flow-verification.json"),
    )
    write_json(
        ATTEMPT / "report.json",
        report_document(flow, phase, regression, normalization, dependency, checks),
    )
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    flow, phase, regression, normalization, dependency, checks = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "status": "active",
        "implementation_gate": "fail",
        "completion_ready": False,
        "core_generation": core_generation,
        "core_evidence_id": core_evidence_id,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "retained_generation_count": integrity["retained_generation_count"],
        "generation_file_hashes_verified": integrity[
            "generation_file_hashes_verified"
        ],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
    }
    write_json(
        ATTEMPT / "report.json",
        report_document(
            flow,
            phase,
            regression,
            normalization,
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
    flow, phase, regression, normalization, dependency, checks = live_documents()
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict):
            raise SystemExit("F04-0002 RAH binding is not an object")
        if not re.fullmatch(r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))):
            raise SystemExit("F04-0002 core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if not re.fullmatch(r"E\d{4,}", str(rah_state.get(key))):
                raise SystemExit(f"F04-0002 {key} binding is malformed")
    expected = {
        "forge-golden-flow-verification.json": flow,
        "phase-artifact-reconciliation.json": phase,
        "full-regression-impact.json": regression,
        "canonical-debt-reconciliation.json": regression["canonical_example_debt"],
        "junit-normalization-verification.json": normalization,
        "dependency-status.json": dependency,
        "forge-golden-flow-verification.artifact-receipt.json": make_receipt(
            ATTEMPT / "forge-golden-flow-verification.json"
        ),
        "report.json": report_document(
            flow,
            phase,
            regression,
            normalization,
            dependency,
            checks,
            rah_state=rah_state,
        ),
    }
    for name, value in expected.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(value):
            raise SystemExit(f"stored F04-0002 evidence differs from live inputs: {name}")
    expected_review = review_text(flow, regression, normalization)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != expected_review:
        raise SystemExit("stored F04-0002 review differs from final bytes")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored F04-0002 commands differ from deterministic record")
    for line in expected_commands.splitlines():
        json.loads(line)
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"F04 root projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "f04_targeted": "8/8",
        "transitions": "17/17",
        "phase_artifact_sets": "14/14",
        "full_node": "457 passed, exact J02 x2 and S04 x1",
        "full_python": "986 passed, exact J02 x1",
        "complete_node_test_files": 52,
        "new_f04_failure_count": 0,
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
