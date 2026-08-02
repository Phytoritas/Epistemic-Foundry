#!/usr/bin/env python3
"""Build fail-closed evidence for the S04-0004 binding-only contract gap."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/S04/attempts/0004"
ATTEMPT_ID = "S04-0004"
WORK_PACKAGE_ID = "S04"
SPEC_GAP_ID = "S04-SG001"
RECORDED_AT = "2026-07-31T08:37:00.515Z"

BINDING_REL = "manifests/source_bindings/development-manifest.binding.json"
MANIFEST_REL = "manifests/development_manifest.yaml"
TEST_REL = "tests/security/s04-threat-model-traceability.test.mjs"
PATCH_REL = (
    "artifacts/authority_decisions/"
    "HD-EF4-B04-SG002-20260730-001.manifest-patch-plan.json"
)
DECISION_REL = (
    "artifacts/authority_decisions/"
    "HD-EF4-C01-SG005-20260731-001.human-decision.json"
)

EXPECTED_HASHES = {
    TEST_REL: "9e853f6ab584191d9e4899135522a4aa2d39860f14f6af388f815dcbdb1d3ef6",
    DECISION_REL: "c7faa17fab992b701749c7fc492b2aa7d03442cfa6e065d58f154c79c50113ab",
    PATCH_REL: "52110dfd9603f3af9fa29546cb3aa049fc983268dfaeabae4733e989a18d1792",
    BINDING_REL: "603bb4d082ce53ab902a3c3ab36abd9eb3331e44d105ec75e967c694bed50dbf",
    MANIFEST_REL: "6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063",
    "artifacts/work_packages/S04/attempts/0002/report.json":
        "1ac68d8fd4f72030dc9124e432673b848ff96240812dba8ec1df0db3fee80573",
    "artifacts/work_packages/S04/attempts/0003/report.json":
        "bf76a387c229769e568e650b150b5ede6b2136c3294d792a551a9802904cadd4",
    "artifacts/work_packages/J02/attempts/0004/report.json":
        "6512cbf890ccd3e6d4d719fa6e504263cfcaafc3e9931536362dfcc8ab50cd0c",
}

EXPECTED_ACTIVE_BINDING_ID = "DMB-EF4-20260730-002"
EXPECTED_PATCH_PLAN_ID = "MP-EF4-B04-SG002-20260730-001"
EXPECTED_OLD_SUCCESSOR = "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"
EXPECTED_CURRENT_MANIFEST = EXPECTED_HASHES[MANIFEST_REL]
RAW_JUNIT_SHA256 = "f01a0018474e768c834b46bcc08d82eb91b5b3f8abe131191869bfafc6a57f2b"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def assert_hash(relative: str) -> str:
    path = ROOT / relative
    observed = sha256(path)
    expected = EXPECTED_HASHES[relative]
    if observed != expected:
        raise SystemExit(f"preserved authority/history changed: {relative}: {observed}")
    return "sha256:" + observed


def canonical_hash_excluding(value: dict[str, Any], field: str) -> str:
    preimage = {key: item for key, item in value.items() if key != field}
    encoded = json.dumps(
        preimage,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def normalize_junit() -> dict[str, Any]:
    path = ATTEMPT / "targeted-source-binding.junit.xml"
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        if record.get("normalized_sha256") != sha256_id(path):
            raise SystemExit("normalized S04-0004 JUnit changed")
        return record
    if sha256(path) != RAW_JUNIT_SHA256:
        raise SystemExit("raw S04-0004 JUnit hash mismatch")
    before = path.read_text(encoding="utf-8")
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    normalized = before.replace(root_backslash, "REPO_ROOT/").replace(
        root_slash, "REPO_ROOT/"
    )
    before_root = ET.fromstring(before)
    after_root = ET.fromstring(normalized)
    def testcase_signature(root: ET.Element) -> list[tuple[str | None, ...]]:
        rows: list[tuple[str | None, ...]] = []
        for case in root.findall(".//testcase"):
            failure = case.find("failure")
            rows.append(
                (
                    case.get("name"),
                    case.get("classname"),
                    failure.get("message") if failure is not None else None,
                )
            )
        return rows

    before_rows = testcase_signature(before_root)
    after_rows = testcase_signature(after_root)
    if before_rows != after_rows:
        raise SystemExit("JUnit semantic signature changed during normalization")
    path.write_text(normalized, encoding="utf-8", newline="\n")
    record = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "raw_sha256": "sha256:" + RAW_JUNIT_SHA256,
        "normalized_sha256": sha256_id(path),
        "repository_prefix_replacement_count": before.count(root_backslash)
        + before.count(root_slash),
        "testcase_count": len(after_rows),
        "semantic_signature_preserved": True,
    }
    write_json(record_path, record)
    return record


def junit_result() -> dict[str, Any]:
    path = ATTEMPT / "targeted-source-binding.junit.xml"
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    failures = [case for case in cases if case.find("failure") is not None]
    if len(cases) != 4 or len(failures) != 1:
        raise SystemExit("S04 targeted result is not the expected 3 pass / 1 fail")
    failure = failures[0]
    if not str(failure.get("name")).startswith("S04-TM004"):
        raise SystemExit("unexpected S04 targeted failure")
    body = ET.tostring(failure, encoding="unicode")
    for value in (EXPECTED_CURRENT_MANIFEST, EXPECTED_OLD_SUCCESSOR):
        if value not in body:
            raise SystemExit("S04-TM004 failure does not contain the exact hash conflict")
    return {
        "command_exit_code": 1,
        "tests": 4,
        "passed": 3,
        "failed": 1,
        "skipped": 0,
        "failure_test": failure.get("name"),
        "actual_manifest_sha256": "sha256:" + EXPECTED_CURRENT_MANIFEST,
        "expected_bound_successor_sha256": "sha256:" + EXPECTED_OLD_SUCCESSOR,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
    }


def extract_test_contract(test_source: str) -> dict[str, Any]:
    def require(pattern: str, label: str) -> re.Match[str]:
        match = re.search(pattern, test_source, flags=re.MULTILINE)
        if match is None:
            raise SystemExit(f"S04 test contract missing {label}")
        return match

    active_id = require(
        r'^const ACTIVE_BINDING_ID = "([^"]+)";$', "ACTIVE_BINDING_ID"
    ).group(1)
    patch_path = require(
        r'^\s*"(artifacts/authority_decisions/HD-EF4-B04-SG002-[^"]+\.manifest-patch-plan\.json)";$',
        "PATCH_PLAN_PATH",
    ).group(1)
    decisions_block = require(
        r"const AUTHORIZING_DECISION_IDS = Object\.freeze\(\[([\s\S]*?)\]\);",
        "AUTHORIZING_DECISION_IDS",
    ).group(1)
    decision_ids = re.findall(r'"([A-Z0-9-]+)"', decisions_block)
    required_assertions = {
        "binding_id_equals_constant": "assert.equal(binding.binding_id, ACTIVE_BINDING_ID);",
        "manifest_equals_binding_successor": "sha256(binding.source_path),\n    binding.successor_sha256",
        "patch_successor_equals_binding_successor": "patchPlan.successor_sha256, binding.successor_sha256",
        "binding_decisions_equal_constant": "binding.authorizing_decision_ids, AUTHORIZING_DECISION_IDS",
        "patch_decisions_equal_constant": "patchPlan.authorizing_decision_ids, AUTHORIZING_DECISION_IDS",
    }
    missing = [name for name, needle in required_assertions.items() if needle not in test_source]
    if missing:
        raise SystemExit(f"S04 test lost required constraints: {missing}")
    return {
        "active_binding_id_constant": active_id,
        "patch_plan_path_constant": patch_path,
        "authorizing_decision_ids_constant": decision_ids,
        "required_assertions": {name: True for name in required_assertions},
    }


def audit() -> dict[str, Any]:
    history = {relative: assert_hash(relative) for relative in EXPECTED_HASHES}
    normalization = normalize_junit()
    result = junit_result()
    binding = read_json(ROOT / BINDING_REL)
    patch = read_json(ROOT / PATCH_REL)
    decision = read_json(ROOT / DECISION_REL)
    test_contract = extract_test_contract((ROOT / TEST_REL).read_text(encoding="utf-8"))

    if binding.get("binding_id") != EXPECTED_ACTIVE_BINDING_ID:
        raise SystemExit("unexpected current binding ID")
    if binding.get("successor_sha256") != EXPECTED_OLD_SUCCESSOR:
        raise SystemExit("unexpected current binding successor")
    if binding.get("binding_hash") != canonical_hash_excluding(binding, "binding_hash"):
        raise SystemExit("current binding self-hash invalid")
    if patch.get("patch_plan_id") != EXPECTED_PATCH_PLAN_ID:
        raise SystemExit("unexpected patch plan ID")
    if patch.get("successor_sha256") != EXPECTED_OLD_SUCCESSOR:
        raise SystemExit("unexpected immutable patch-plan successor")
    if patch.get("patch_plan_hash") != canonical_hash_excluding(patch, "patch_plan_hash"):
        raise SystemExit("patch-plan self-hash invalid")
    if decision.get("decision_hash") != canonical_hash_excluding(decision, "decision_hash"):
        raise SystemExit("C01-SG005 HumanDecision self-hash invalid")

    binding_only_candidate = dict(binding)
    binding_only_candidate.update(
        {
            "binding_id": "DMB-EF4-20260731-003",
            "parent_sha256": EXPECTED_OLD_SUCCESSOR,
            "successor_sha256": EXPECTED_CURRENT_MANIFEST,
            "supersedes_binding_id": EXPECTED_ACTIVE_BINDING_ID,
            "supersedes_binding_hash": binding["binding_hash"],
            "authorizing_decision_ids": [decision["decision_id"]],
        }
    )
    binding_only_candidate["binding_hash"] = canonical_hash_excluding(
        binding_only_candidate, "binding_hash"
    )

    contradictions = [
        {
            "id": "C1_IMMUTABLE_PATCH_SUCCESSOR",
            "constraint": "test requires patchPlan.successor_sha256 == binding.successor_sha256",
            "patch_plan_value": "sha256:" + str(patch["successor_sha256"]),
            "required_new_binding_value": "sha256:" + EXPECTED_CURRENT_MANIFEST,
            "satisfied_by_binding_only_candidate": False,
        },
        {
            "id": "C2_HARDCODED_BINDING_ID",
            "constraint": "test requires binding.binding_id == DMB-EF4-20260730-002",
            "required_new_revision_id": binding_only_candidate["binding_id"],
            "satisfied_by_binding_only_candidate": False,
        },
        {
            "id": "C3_HARDCODED_AUTHORIZING_DECISIONS",
            "constraint": (
                "test requires binding and patch plan authorizing_decision_ids to equal "
                "[HD-EF4-B04-SG002-20260730-001]"
            ),
            "required_new_authorizing_decision": decision["decision_id"],
            "satisfied_by_binding_only_candidate": False,
        },
        {
            "id": "C4_PATCH_PLAN_SCOPE_NOT_AUTHORIZED",
            "constraint": (
                "HD-EF4-C01-SG005-20260731-001 authorizes only the binding file and "
                "S04 attempt evidence; it does not authorize a new patch plan or test edit"
            ),
            "satisfied_by_binding_only_candidate": False,
        },
    ]
    proof = {
        "current_manifest_sha256": "sha256:" + EXPECTED_CURRENT_MANIFEST,
        "current_binding_successor_sha256": "sha256:" + str(binding["successor_sha256"]),
        "immutable_patch_plan_successor_sha256": "sha256:" + str(patch["successor_sha256"]),
        "required_equalities": [
            "sha256(manifest) == binding.successor_sha256",
            "patch_plan.successor_sha256 == binding.successor_sha256",
        ],
        "derived_requirement": "sha256(manifest) == patch_plan.successor_sha256",
        "derived_requirement_holds": EXPECTED_CURRENT_MANIFEST == patch["successor_sha256"],
        "binding_only_solution_exists": False,
        "contradictions": contradictions,
    }
    if proof["derived_requirement_holds"] or any(
        row["satisfied_by_binding_only_candidate"] for row in contradictions
    ):
        raise SystemExit("binding-only impossibility proof did not close")

    return {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "work_package_id": WORK_PACKAGE_ID,
        "spec_gap_id": SPEC_GAP_ID,
        "status": "SPEC_GAP",
        "classification": {
            "typed_outcome": "SPEC_GAP",
            "not_fail_reason": (
                "The requested new binding revision cannot satisfy the immutable active test "
                "and patch-plan contract within the exact binding-only write scope."
            ),
            "not_blocked_reason": (
                "No credential, service, toolchain, licensed source, or host capability is missing."
            ),
        },
        "authority_decision": {
            "decision_id": decision["decision_id"],
            "decision_hash": decision["decision_hash"],
            "decision_file_sha256": history[DECISION_REL],
            "authorized_product_paths": [BINDING_REL],
            "authorized_evidence_paths": ["artifacts/work_packages/S04/attempts/0004/**"],
            "new_patch_plan_authorized": False,
            "test_edit_authorized": False,
        },
        "test_contract": test_contract,
        "targeted_result": result,
        "junit_normalization": normalization,
        "impossibility_proof": proof,
        "binding_only_candidate": binding_only_candidate,
        "product_mutation_performed": False,
        "preserved_hashes": history,
        "required_product_owner_decision": {
            "minimum_scope_additions": [
                TEST_REL,
                "artifacts/authority_decisions/<new-decision>.manifest-patch-plan.json",
            ],
            "required_semantics": [
                "assign the next immutable binding ID and its supersedes linkage",
                "authorize a patch plan binding the prior manifest hash to the current manifest hash",
                "bind the latest HumanDecision in authorizing_decision_ids",
                "make S04-TM004 validate the active revision rather than fixed revision 002",
            ],
            "preserve_existing_binding_and_patch_plan_as_immutable_history": True,
        },
        "resume_condition": (
            "A product-owner HumanDecision must authorize the exact S04 test and new patch-plan "
            "paths and define their revision/lineage relationship; S04 must then run a new attempt."
        ),
        "recorded_at_utc": RECORDED_AT,
    }


def build() -> dict[str, Any]:
    verification = audit()
    write_json(ATTEMPT / "binding-only-impossibility-verification.json", verification)
    dependency = {
        "attempt_id": ATTEMPT_ID,
        "status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
        "dependencies": {"S02": "PASS", "S03": "PASS", "J02-0004": "PASS"},
        "next_state": {
            "S04": "SPEC_GAP_S04_SG001",
            "C01-0009": "NOT_STARTED_WAITING_ON_S04_PASS",
            "C02-0004": "NOT_STARTED",
            "B04-0009": "NOT_STARTED",
            "O02-0002": "NOT_STARTED",
            "C04-0004": "NOT_STARTED",
            "B04-final": "NOT_STARTED",
        },
        "completion_ready": False,
    }
    write_json(ATTEMPT / "dependency-status.json", dependency)
    report = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "ACTIVE_SOURCE_BINDING_CORRECTION",
        "work_package_id": WORK_PACKAGE_ID,
        "status": "SPEC_GAP",
        "package_status": "SPEC_GAP",
        "implementation_status": "NOT_STARTED_FAIL_CLOSED",
        "spec_gap_id": SPEC_GAP_ID,
        "authority_decision_id": "HD-EF4-C01-SG005-20260731-001",
        "completion_ready": False,
        "global_implementation_gate": "fail",
        "product_files_modified_by_attempt": [],
        "output_artifacts": [
            "artifacts/work_packages/S04/attempts/0004/binding-only-impossibility-verification.json",
            "artifacts/work_packages/S04/attempts/0004/dependency-status.json",
            "artifacts/work_packages/S04/attempts/0004/targeted-source-binding.junit.xml",
            "artifacts/work_packages/S04/attempts/0004/junit-normalization-verification.json",
            "artifacts/work_packages/S04/attempts/0004/commands.jsonl",
            "artifacts/work_packages/S04/attempts/0004/review.md",
            "artifacts/work_packages/S04/attempts/0004/report.json",
            "artifacts/work_packages/S04/attempts/0004/rah-core-integrity.json",
            "artifacts/work_packages/S04/attempts/0004/build_s04_0004_evidence.py",
            "artifacts/work_packages/S04/attempts/0004/s04_0004_rah_seal.py",
        ],
        "targeted_validation": verification["targeted_result"],
        "spec_gap": {
            "id": SPEC_GAP_ID,
            "classification": "SPEC_GAP",
            "summary": (
                "The binding-only correction scope cannot satisfy S04-TM004 because the test "
                "also freezes the previous binding ID, immutable patch-plan successor, and "
                "authorizing-decision list."
            ),
            "required_product_owner_decision": verification[
                "required_product_owner_decision"
            ],
        },
        "historical_preservation": {
            "prior_S04_attempts_preserved": True,
            "J02_0004_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "not_claimed": [
            "S04-0004 PASS",
            "C01-0009 start",
            "repository conformance",
            "completion_ready=true",
        ],
        "resume_condition": verification["resume_condition"],
    }
    write_json(ATTEMPT / "report.json", report)
    return verification


def verify() -> dict[str, Any]:
    expected = audit()
    stored = read_json(ATTEMPT / "binding-only-impossibility-verification.json")
    if stored != expected:
        raise SystemExit("stored binding-only proof differs from live authority")
    dependency = read_json(ATTEMPT / "dependency-status.json")
    report = read_json(ATTEMPT / "report.json")
    if dependency.get("status") != "SPEC_GAP" or report.get("status") != "SPEC_GAP":
        raise SystemExit("S04-0004 artifacts do not preserve SPEC_GAP")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "verified_outcome": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
        "binding_only_solution_exists": False,
        "product_mutation_count": 0,
        "verification_sha256": sha256_id(
            ATTEMPT / "binding-only-impossibility-verification.json"
        ),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
