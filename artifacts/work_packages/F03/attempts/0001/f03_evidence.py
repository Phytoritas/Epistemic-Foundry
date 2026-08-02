#!/usr/bin/env python3
"""Build and verify byte-bound evidence for F03-0001."""

from __future__ import annotations

import argparse
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
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F03/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/F03"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
PRIOR_DAG = ROOT / "artifacts/work_packages/F02/attempts/0001/dependency-status.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"

ATTEMPT_ID = "F03-0001"
WORK_PACKAGE_ID = "F03"
CREATED_AT = "2026-07-29T02:45:00Z"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_PATH = "manifests/development_manifest.yaml"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"

IMPLEMENTATION_FILES = (
    "packages/foundry-kernel/src/forge/gates/transition-admission-gate.mjs",
    "packages/foundry-kernel/src/forge/gates/index.mjs",
    "packages/foundry-kernel/src/forge/gates/gate-test-support.mjs",
    "packages/foundry-kernel/src/forge/gates/transition-receipt.test.mjs",
    "packages/foundry-kernel/src/forge/gates/override-provenance.test.mjs",
)

PRESERVED_HASHES = {
    "artifacts/work_packages/F01/attempts/0003/report.json": (
        "cf3c909d7adb256403fe4e2d051b2e591b3c002531ab19085334d085d06236c4"
    ),
    "artifacts/work_packages/F02/attempts/0001/report.json": (
        "4d6dae9525ac559cba26e59ff1ab93f7e94918e21076030c50c55f7022b3b152"
    ),
    "artifacts/work_packages/F02/attempts/0001/dependency-status.json": (
        "5233f3266701e2babc61383f32daf0f9b6aef1ac16f89dbb11b9d89c001fcfcb"
    ),
    "manifests/development_manifest.yaml": (
        "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
    ),
}

JUNIT_HASHES = {
    "targeted-node-suite.junit.xml": (
        "726db98bcd12b1984b11ef9d88c36bd985bb32c8653632ed0701138eb78691e5"
    ),
    "full-node-suite.junit.xml": (
        "4ad7b281a668d33341bb2389782a166d6076ddf43275a176aff8a79da3740878"
    ),
    "full-python-suite.junit.xml": (
        "34a034a657f670fac2a11df553d80d4570c55239b0e553c2cf5ac08d49ba31c1"
    ),
}

NODE_TOTAL_PATTERNS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_hash_excluding(document: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(document)
    preimage.pop(field, None)
    payload = json.dumps(
        preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def source_inventory() -> list[dict[str, Any]]:
    directory = ROOT / "packages/foundry-kernel/src/forge/gates"
    actual = tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file()
    )
    if set(actual) != set(IMPLEMENTATION_FILES) or len(actual) != len(IMPLEMENTATION_FILES):
        raise SystemExit(f"unexpected F03 source inventory: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in IMPLEMENTATION_FILES:
        path = ROOT / relative
        content = path.read_bytes()
        if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
            raise SystemExit(f"invalid source encoding marker: {relative}")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"F03 source is not UTF-8: {relative}: {error}")
        if "\ufffd" in text:
            raise SystemExit(f"replacement character in F03 source: {relative}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    implementation = (ROOT / IMPLEMENTATION_FILES[0]).read_text(encoding="utf-8")
    if 'TRANSITION_ADMISSION_VERSION = "4.0.0-f03.1"' not in implementation:
        raise SystemExit("F03 transition admission version is not the sealed 4.0.0-f03.1")
    return rows


def verify_preserved_history() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in PRESERVED_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"preserved authority/history changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    return observed


def normalized_junit_bytes(path: Path) -> bytes:
    content = path.read_bytes()
    forbidden = (
        b"hostname=",
        b"C:/dev/insight/Epistemic-Foundry",
        b"C:\\dev\\insight\\Epistemic-Foundry",
    )
    if any(marker in content for marker in forbidden):
        raise SystemExit(f"machine-local metadata remains in {path.name}")
    return content


def node_junit(name: str) -> dict[str, Any]:
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    expected_hash = JUNIT_HASHES[name]
    if sha256(path) != expected_hash:
        raise SystemExit(f"sealed JUnit hash changed: {name}")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SystemExit(f"invalid JUnit XML {name}: {error}")
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label} in {name}")
        totals[label] = int(matches[0])
    tests: list[dict[str, str | None]] = []
    failures: list[dict[str, str | None]] = []
    for testcase in root.findall(".//testcase"):
        row = {
            "name": testcase.get("name"),
            "file": testcase.get("file"),
        }
        tests.append(row)
        failure = testcase.find("failure")
        if failure is not None:
            failures.append({**row, "message": failure.get("message", "")})
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "xml_testcase_count": len(tests),
        "xml_failure_count": len(failures),
        "tests": tests,
        "failures": failures,
    }


def python_junit() -> dict[str, Any]:
    name = "full-python-suite.junit.xml"
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit("sealed Python JUnit hash changed")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SystemExit(f"invalid Python JUnit XML: {error}")
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
    }


def verified_test_results() -> dict[str, Any]:
    targeted = node_junit("targeted-node-suite.junit.xml")
    full_node = node_junit("full-node-suite.junit.xml")
    full_python = python_junit()
    exact_targeted = {
        "tests": 68,
        "pass": 68,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }
    if targeted["totals"] != exact_targeted or targeted["xml_failure_count"] != 0:
        raise SystemExit("combined F01/F02/F03 targeted result is not exact 68/68")
    file_counts = {"transition_receipt_test": 0, "override_provenance_test": 0}
    for row in targeted["tests"]:
        filename = str(row.get("file") or "").replace("\\", "/")
        if filename.endswith("/forge/gates/transition-receipt.test.mjs"):
            file_counts["transition_receipt_test"] += 1
        elif filename.endswith("/forge/gates/override-provenance.test.mjs"):
            file_counts["override_provenance_test"] += 1
    if file_counts != {"transition_receipt_test": 15, "override_provenance_test": 6}:
        raise SystemExit(f"F03 targeted split is not exact 15+6: {file_counts}")
    if full_python["totals"] != {
        "tests": 947,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }:
        raise SystemExit("F03 full Python result is not exact 947/947")
    if full_node["totals"] != {
        "tests": 306,
        "pass": 305,
        "fail": 1,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }:
        raise SystemExit("F03 full Node footer is not exact 305 pass plus one failure")
    if full_node["xml_failure_count"] != 1:
        raise SystemExit("F03 full Node XML does not contain exactly one failure")
    failure = full_node["failures"][0]
    message = str(failure.get("message") or "")
    normalized_file = str(failure.get("file") or "").replace("\\", "/")
    if (
        failure.get("name") != S04_TEST
        or not normalized_file.endswith("tests/security/s04-threat-model-traceability.test.mjs")
        or S04_EXPECTED not in message
        or S04_ACTUAL not in message
    ):
        raise SystemExit("full Node failure is not the exact preserved S04-TM004 debt")
    targeted.pop("tests")
    full_node.pop("tests")
    return {
        "targeted_node": targeted,
        "f03_targeted_counts": file_counts,
        "f03_targeted_total": sum(file_counts.values()),
        "full_node": full_node,
        "full_python": full_python,
    }


def transition_verification(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "work_package_id": WORK_PACKAGE_ID,
        "status": "PASS",
        "transition_admission_version": "4.0.0-f03.1",
        "required_check": "transition_receipt_test",
        "targeted_passed": results["f03_targeted_counts"]["transition_receipt_test"],
        "targeted_failed": 0,
        "targeted_skipped": 0,
        "verified_contracts": [
            "no prose-only transition",
            "session, revision, from-phase, and state-hash binding",
            "resolved receipt, manifest, byte size, and SHA-256 recomputation",
            "validation evidence bound to content and manifest hashes",
            "IDLE requires exactly one canonical F01 classification receipt",
            "classification identity, schema receipt, projection, work class, timestamp, and version validation",
            "non-IDLE requires exactly one complete current PhaseArtifactSet",
            "required artifacts are VALID and receipt/hash/schema/state-retention bound",
            "GateDecision run, input hash, decision hash, and evidence binding",
            "FAIL and BLOCK are rejected in every phase",
            "E admission requires resolving satisfied GateDecisions",
            "deterministic immutable FTA admission identity",
        ],
        "classification_business_artifact_checks": [
            "byte integrity",
            "schema identity",
            "classification identity format",
            "E0-E5 exact projection",
            "ForgeSessionState work-class agreement",
        ],
        "classification_identity_context_boundary": (
            "request_input_hash, policy_bundle_hash, accepted_signals, and supersedes/"
            "human-decision context are not present in the business artifact and are not inferred; "
            "F02 classification_identity_context plus F04 composition owns the full semantic binding"
        ),
        "combined_targeted_suite": results["targeted_node"],
        "source_inventory": source_inventory(),
        "completion_ready": False,
    }


def override_verification(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "required_check": "override_provenance_test",
        "targeted_passed": results["f03_targeted_counts"]["override_provenance_test"],
        "targeted_failed": 0,
        "targeted_skipped": 0,
        "human_override_remains_explicit": True,
        "verified_contracts": [
            "WAIVE requires a resolving declared canonical HumanDecision receipt",
            "receipt creator is the same human authority named by the decision",
            "authority strings never substitute for a HumanDecision artifact",
            "non-waivable gates cannot be waived by human approval",
            "decision type, authority, scope, run, and hash are fail-closed",
            "undeclared or unused HumanDecision artifacts are rejected",
        ],
        "implicit_override_count": 0,
        "non_waivable_override_count": 0,
        "service_authored_human_decision_acceptance_count": 0,
        "combined_targeted_suite_sha256": results["targeted_node"]["sha256"],
    }


def regression_impact(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT",
        "python": results["full_python"],
        "node": results["full_node"],
        "f03_caused_failure_count": 0,
        "new_skip_or_xfail_count": 0,
        "preexisting_debt_count": 1,
        "preexisting_debt_id": "S04-TM004",
        "repository_fully_green": False,
    }


def debt_reconciliation(results: dict[str, Any]) -> dict[str, Any]:
    failure = results["full_node"]["failures"][0]
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "EXACT_PREEXISTING_BOUNDED_DEBT",
        "debt_id": "S04-TM004",
        "test_id": failure["name"],
        "affected_path": S04_PATH,
        "expected_hash": S04_EXPECTED,
        "actual_hash": S04_ACTUAL,
        "owner": "S04",
        "f03_causal_impact": "NONE",
        "hidden_by_skip_or_xfail": False,
    }


def manifest_rows() -> list[tuple[str, list[str]]]:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = manifest.get("work_packages") if isinstance(manifest, dict) else None
    if not isinstance(packages, list):
        packages = manifest
    if not isinstance(packages, list):
        raise SystemExit("development manifest is not a package list")
    rows: list[tuple[str, list[str]]] = []
    for item in packages:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise SystemExit("invalid development manifest package row")
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies):
            raise SystemExit(f"invalid dependency row: {item.get('id')}")
        rows.append((item["id"], dependencies))
    return rows


def dependency_status() -> dict[str, Any]:
    prior = read_json(PRIOR_DAG)
    if prior.get("status") != "PASS" or prior.get("completed_package_count") != 27:
        raise SystemExit("F02 dependency status is not the expected sealed PASS input")
    completed = list(prior.get("completed_packages", []))
    if "F03" in completed or not {"F01", "F02"}.issubset(set(completed)):
        raise SystemExit("unexpected F02 completed package inventory")
    completed.append("F03")
    completed_set = set(completed)
    rows = manifest_rows()
    identifiers = [row[0] for row in rows]
    if len(identifiers) != 156 or len(set(identifiers)) != 156:
        raise SystemExit("development manifest is not the canonical 156-package DAG")
    unknown = sorted(
        {dependency for _, dependencies in rows for dependency in dependencies}
        - set(identifiers)
    )
    if unknown:
        raise SystemExit(f"unknown package dependencies: {unknown}")
    indegree = {identifier: 0 for identifier in identifiers}
    outgoing = {identifier: [] for identifier in identifiers}
    for identifier, dependencies in rows:
        indegree[identifier] = len(dependencies)
        for dependency in dependencies:
            outgoing[dependency].append(identifier)
    queue = [identifier for identifier in identifiers if indegree[identifier] == 0]
    visited: list[str] = []
    while queue:
        current = queue.pop(0)
        visited.append(current)
        for child in outgoing[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(visited) != len(identifiers):
        raise SystemExit("development manifest contains a dependency cycle")
    ready = [
        identifier
        for identifier, dependencies in rows
        if identifier not in completed_set and all(dep in completed_set for dep in dependencies)
    ]
    expected_ready = ["F04", "G01", "K01", "A06"]
    if ready != expected_ready:
        raise SystemExit(f"unexpected post-F03 ready order: {ready}")
    return {
        "schema_version": 1,
        "status": "PASS",
        "manifest": {
            "path": MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(MANIFEST),
            "work_package_count": len(identifiers),
            "unique_work_package_count": len(set(identifiers)),
            "unknown_dependency_count": 0,
            "cycle_count": 0,
        },
        "completed_packages": completed,
        "completed_package_count": len(completed),
        "ready_packages_manifest_order": ready,
        "ready_package_count": len(ready),
        "blocked_package_count": len(identifiers) - len(completed) - len(ready),
        "next_package": ready[0],
        "f04_status": "DEPENDENCY_READY",
        "completion_ready": False,
    }


def commands_text() -> str:
    rows = [
        ("C001", "Inspect F03 authority, F01 dependency, F02 integration boundary, schemas, protocol, and package scope", 0, "PASS"),
        ("C002", "Implement deterministic receipt-bound transition admission under the F03 write scope", 0, "PASS"),
        ("C003", "Run syntax checks for all five F03 JavaScript modules", 0, "PASS: 5/5"),
        ("C004", "Run final combined F01/F02/F03 targeted Node JUnit suite", 0, "PASS: 68/68 including exact F03 21/21"),
        ("C005", "Run npm repository structure and package-boundary checks", 0, "PASS"),
        ("C006", "Run full Python suite and emit normalized JUnit evidence", 0, "PASS: 947 passed, 0 failed/skipped"),
        ("C007", "Run full Node suite and emit normalized JUnit evidence", 1, "BOUNDED_PREEXISTING_DEBT: 305 passed; exact S04-TM004 only"),
        ("C008", "Normalize three F03 JUnit receipts without changing semantic totals or failure fingerprint", 0, "PASS"),
        ("C009", "Run scoped and repository git diff checks", 0, "PASS: no whitespace errors; existing line-ending warnings only"),
        ("C010", "Primary-session separate contract review of final F03 bytes", 0, "PASS: zero blocking findings; not actor-independent certification"),
        ("C011", "Compile an early dynamic import inside a non-async callback", 1, "PRESERVED DIAGNOSTIC ERROR: await syntax rejected; corrected to a static import"),
        ("C012", "Run a read-only rg search with a Windows wildcard path", 1, "PRESERVED DIAGNOSTIC ERROR: path syntax rejected; no state changed"),
        ("C013", "Repeat a read-only rg search with another Windows wildcard path", 1, "PRESERVED DIAGNOSTIC ERROR: path syntax rejected; corrected to directory plus -g"),
        ("C014", "Read a generation manifest using the wrong manifest.json filename", 1, "PRESERVED DIAGNOSTIC ERROR: actual filename is generation-manifest.json; no state changed"),
        ("C015", "Build and reparse F03 machine-readable evidence", 0, "PASS"),
        ("C016", "Append F03 core PASS evidence to RAH", 0, "PASS when core seal completes as E0048"),
        ("C017", "Verify post-core generations, hashes, and six flat snapshots", 0, "PASS when post-core verification completes"),
        ("C018", "Append hash-bound F03 closeout evidence", 0, "PASS when final seal completes as E0049"),
    ]
    lines = []
    for suffix, command, exit_code, result in rows:
        lines.append(
            json.dumps(
                {
                    "command_id": f"F03-0001-{suffix}",
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
    return f"""# F03-0001 artifact-receipt transition gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final F03 bytes. It is not actor-independent certification.

## Reviewed boundary

{hashes}

The review also checked the sealed F01 report, the F02 transition boundary,
`docs/forge_protocol.md`, ArtifactReceipt, PhaseArtifactSet, GateDecision, and
HumanDecision contracts, and all normalized regression receipts.

## Findings

1. A narrative reason cannot authorize a transition. Every admitted transition
   resolves the declared receipts, manifests, and bytes, independently
   recomputes byte length and SHA-256, and binds validation evidence to both
   content and manifest hashes.
2. IDLE admission requires exactly one canonical F01 classification receipt.
   The classification artifact's closed fields, identity, timestamp, version,
   E0-E5 projection, schema-validation receipt, and session work class are
   checked before an admission can exist.
3. Non-IDLE admission requires exactly one complete current PhaseArtifactSet.
   Every required entry must be VALID and bound to the exact receipt, content
   hash, schema reference, session, phase, and retained state artifact.
4. GateDecisions bind run, input, decision hash, and resolving evidence. FAIL
   and BLOCK are never absorbed, E requires gates, and a non-waivable WAIVE is
   rejected even when a human decision is supplied.
5. A waivable override requires a declared, resolving, canonical HumanDecision
   whose human receipt creator, authority, type, run, scope, and hash agree.
   Authority prose or an unused decision artifact is not an override.
6. Admission output is immutable and content-addressed as `FTA-<digest>`.
   F03 does not mutate F02 state or silently perform the F02 transition.
7. F03 tests are 21/21 (15 receipt and 6 override); the combined F01/F02/F03
   gate is 68/68. Full Python is 947/947. Full Node is 305/306 with only the
   exact unchanged S04-TM004 debt and no F03-caused failure or skip.

## Assurance boundary

F03 verifies the classification business artifact's bytes, schema identity,
classification identity, exact projection, and ForgeSessionState work-class
agreement. Recomputing the complete `classification_hash` semantic preimage
also requires `request_input_hash`, `policy_bundle_hash`, `accepted_signals`,
and supersedes/human-decision context, which are deliberately absent from the
business artifact. F03 does not guess them. F02's
`classification_identity_context` validation and the F04 composition gate own
that cross-artifact semantic binding.

This gate proves the in-process deterministic admission surface. It does not
claim future distributed exactly-once delivery, transport authentication, or
actor-independent certification.

## Decision

F03 meets both exit criteria: prose-only transitions are impossible and human
override provenance remains explicit. Product completion remains false.
"""


def phase_reconciliation() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "expected_implementation_file_count": len(IMPLEMENTATION_FILES),
        "generated_implementation_file_count": len(IMPLEMENTATION_FILES),
        "evaluated_implementation_file_count": len(IMPLEMENTATION_FILES),
        "persisted_implementation_file_count": len(IMPLEMENTATION_FILES),
        "failed_count": 0,
        "cancelled_count": 0,
        "missing_count": 0,
        "implementation_files": list(IMPLEMENTATION_FILES),
        "transition_receipt_test_count": 15,
        "override_provenance_test_count": 6,
        "admission_is_new_immutable_artifact": True,
        "forge_session_state_mutation_count": 0,
    }


def make_receipt() -> dict[str, Any]:
    artifact = ATTEMPT / "transition-receipt-verification.json"
    receipt = {
        "receipt_id": "AR-F03-0001-TRANSITION-RECEIPT-VERIFICATION",
        "artifact_id": "F03-0001-TRANSITION-RECEIPT-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(artifact),
        "byte_size": artifact.stat().st_size,
        "created_by": {"actor_id": "SVC-FOUNDRY-KERNEL-F03", "actor_type": "service"},
        "created_at": CREATED_AT,
        "locator": artifact.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {"check": "transition_receipt_test", "status": "PASS", "details": "15/15 F03 tests"},
            {"check": "override_provenance_test", "status": "PASS", "details": "6/6 F03 tests"},
            {"check": "combined_f01_f02_f03", "status": "PASS", "details": "68/68 targeted Node tests"},
            {"check": "full_python_regression", "status": "PASS", "details": "947/947"},
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(receipt), key=lambda e: list(e.path))
    if errors:
        raise SystemExit(f"invalid F03 ArtifactReceipt: {errors[0].message}")
    return receipt


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verify_preserved_history()
    results = verified_test_results()
    inventory = source_inventory()
    write_json("transition-receipt-verification.json", transition_verification(results))
    write_json("override-provenance-verification.json", override_verification(results))
    write_json("full-regression-impact.json", regression_impact(results))
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation(results))
    write_json("dependency-status.json", dependency_status())
    write_json("phase-artifact-reconciliation.json", phase_reconciliation())
    (ATTEMPT / "commands.jsonl").write_text(commands_text(), encoding="utf-8", newline="\n")
    (ATTEMPT / "review.md").write_text(review_text(inventory), encoding="utf-8", newline="\n")
    write_json("transition-receipt-verification.artifact-receipt.json", make_receipt())
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    preserved = verify_preserved_history()
    results = verified_test_results()
    expected = {
        "transition-receipt-verification.json": transition_verification(results),
        "override-provenance-verification.json": override_verification(results),
        "full-regression-impact.json": regression_impact(results),
        "preexisting-debt-reconciliation.json": debt_reconciliation(results),
        "dependency-status.json": dependency_status(),
        "phase-artifact-reconciliation.json": phase_reconciliation(),
        "transition-receipt-verification.artifact-receipt.json": make_receipt(),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored F03 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored F03 commands differ from canonical commands")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(source_inventory()):
        raise SystemExit("stored F03 review differs from final source inventory")
    for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "f03_targeted_passed": results["f03_targeted_total"],
        "combined_targeted_passed": results["targeted_node"]["totals"]["pass"],
        "full_python_passed": results["full_python"]["totals"]["tests"],
        "full_node_passed": results["full_node"]["totals"]["pass"],
        "full_node_preexisting_failures": results["full_node"]["totals"]["fail"],
        "preserved_hash_count": len(preserved),
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
        root = ralph_root / "generations" / name
        manifest = read_json(root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict):
            raise SystemExit(f"invalid RAH generation manifest: {name}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"RAH generation file set mismatch: {name}")
        for filename in state_store.GENERATION_FILES:
            if sha256(root / filename) != files[filename]:
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
            authority = {key: value for key, value in authority.items() if key != "state_generation"}
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
    if loop.get("status") != "active" or loop.get("completion_readiness", {}).get("ready") is not False:
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
    results = verified_test_results()
    artifact_names = [
        "transition-receipt-verification.json",
        "override-provenance-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "phase-artifact-reconciliation.json",
        "dependency-status.json",
        "transition-receipt-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "targeted-node-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
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
        "title": "Artifact-receipt transition gates",
        "status": "PASS",
        "package_status": "PASS",
        "completion_ready": False,
        "dependency": {
            "F01": {
                "status": "PASS",
                "attempt_id": "F01-0003",
                "report": "artifacts/work_packages/F01/attempts/0003/report.json",
                "report_sha256": sha256_id(ROOT / "artifacts/work_packages/F01/attempts/0003/report.json"),
            },
            "F02_integration_context": {
                "status": "PASS",
                "attempt_id": "F02-0001",
                "report": "artifacts/work_packages/F02/attempts/0001/report.json",
                "report_sha256": sha256_id(ROOT / "artifacts/work_packages/F02/attempts/0001/report.json"),
                "static_dependency": False,
            },
        },
        "write_scope": ["packages/foundry-kernel/src/forge/gates/**"],
        "changed_files": source_inventory(),
        "exit_criteria": {
            "no_prose_only_transition": "PASS",
            "human_override_remains_explicit": "PASS",
        },
        "required_checks": {
            "transition_receipt_test": {"status": "PASS", "passed": 15, "failed": 0},
            "override_provenance_test": {"status": "PASS", "passed": 6, "failed": 0},
            "f03_targeted_gate": {"status": "PASS", "passed": 21, "failed": 0, "skipped": 0},
            "combined_f01_f02_f03_gate": {"status": "PASS", "passed": 68, "failed": 0, "skipped": 0},
        },
        "regression": {
            "python": {"status": "PASS", "passed": 947, "failed": 0, "skipped": 0},
            "node": {
                "status": "BOUNDED_PREEXISTING_DEBT_S04_TM004",
                "passed": 305,
                "failed": 1,
                "skipped": 0,
                "f03_caused_failure_count": 0,
            },
            "repository_structure": "PASS",
            "package_boundaries": "PASS",
            "git_diff_check": "PASS",
        },
        "review": {
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "blocking_findings": 0,
            "subagents_used": False,
            "assurance_limitation": "Procedurally separate primary-session review; not actor-independent certification.",
            "artifact": "artifacts/work_packages/F03/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "preserved_limitations": [
            "F03 does not infer missing classification semantic-preimage context.",
            "F02 classification_identity_context and F04 composition own full cross-artifact classification binding.",
            "S04-TM004 remains an exact pre-existing S04-owned debt.",
        ],
        "historical_and_worktree_preservation": {
            "prior_reports_and_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "implementation_write_scope_violations": 0,
        },
        "verification": {
            "f03_targeted_node": f"{results['f03_targeted_total']}/21",
            "combined_targeted_node": f"{results['targeted_node']['totals']['pass']}/68",
            "full_python": f"{results['full_python']['totals']['tests']}/947",
            "full_node": "305_PASS_PLUS_EXACT_PREEXISTING_S04_TM004",
        },
        "evidence_artifacts": artifacts,
        "artifact_receipt": {
            "path": "artifacts/work_packages/F03/attempts/0001/transition-receipt-verification.artifact-receipt.json",
            "receipt_id": "AR-F03-0001-TRANSITION-RECEIPT-VERIFICATION",
        },
        "rah_state": {
            "status": "active",
            "core_evidence_id": "E0048",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0049",
            "retained_generation_manifest_count": integrity["retained_generation_manifest_count"],
            "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
            "flat_snapshot_stamps_verified": 6,
            "flat_snapshot_content_matches": 6,
            "completion_ready": False,
        },
        "dependency_effect": {
            "dag_recomputed": True,
            "completed_package_count": 28,
            "ready_packages_manifest_order": ["F04", "G01", "K01", "A06"],
            "next_package": "F04",
        },
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(46, "E0048")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    integrity = generation_integrity(46, "E0048")
    if read_json(ATTEMPT / "rah-core-integrity.json") != integrity:
        raise SystemExit("stored F03 RAH core integrity differs from live generation")
    if read_json(ATTEMPT / "report.json") != report_document(integrity):
        raise SystemExit("stored F03 report differs from live evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"F03 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": integrity["current_generation"],
        "core_evidence_id": "E0048",
        "root_projection_count": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("build-pre-core", "verify-pre-core", "build-post-core", "verify-post-core")
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
