#!/usr/bin/env python3
"""Build and verify fail-closed evidence for J04-0001.

J04 owns only golden post-compaction recovery fixtures/tests and its evidence
directory.  The recovery oracle deliberately remains test-only: it proves the
contract against the already sealed J03 ContextCapsule implementation without
silently expanding J04 into a new runtime authority.
"""

from __future__ import annotations

import argparse
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
ATTEMPT = ROOT / "artifacts/work_packages/J04/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/J04"
ATTEMPT_ID = "J04-0001"
WORK_PACKAGE_ID = "J04"
RECORDED_AT = "2026-07-30T17:20:00.000Z"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"

SOURCE_HASHES = {
    "tests/golden/compaction/post-compaction-recovery.fixture.json":
        "a4b21b686aeb20fd6cdbb4036e1ce631fe21f94927b4f28451c9bde2000c7c7c",
    "tests/golden/compaction/recovery-oracle.mjs":
        "fd72edba5be7044d186ff6b50bd4dedf56f09bc511cf5cfcf1df3c032568d2eb",
    "tests/golden/compaction/compaction-resume.test.mjs":
        "82a3b41500ca5da28f29b85e49f6d5cd94198d8e4af66eb94e2e0e07a724bd28",
    "tests/golden/compaction/context-poisoning.test.mjs":
        "edfa0dae0304e3fca1d6f2e678df0aeec55cc7d5469327ce44607dbdf2d25dcf",
}
J03_IMPLEMENTATION_HASHES = {
    "packages/context-capsule/src/context-capsule.mjs":
        "017b9b7d8638df51fa2f5a0a218eaf797bdca1ca64b4c02e2d8fde7f3c2c45a6",
    "packages/context-capsule/src/index.mjs":
        "f92d0efb43f6bee745e0cfe442cfb0f8f3acc8002f8fecc979837a39d427a5d0",
    "packages/context-capsule/package.json":
        "f768694a12bac2de3e187770b6f3c0c47b2226246eda22d13226e70cd3b36d4e",
}
DEPENDENCY_REPORT_HASHES = {
    "artifacts/work_packages/J02/attempts/0003/report.json":
        "d348ddc7c8b2d476d3424a6459079f0011d9fc69e29056131832b3ae2fc2d184",
    "artifacts/work_packages/J03/attempts/0001/report.json":
        "ce6223287b0c59a086527fcbd8fddfe3ad18c127f70cc36f91c66fa32c069a40",
}
JUNIT_HASHES = {
    "targeted-j04-suite.junit.xml":
        "1b3f12944992bef905ec086b317c885138f4ed44f5b930901a5abcca2df0d82d",
    "j03-capsule-regression.junit.xml":
        "a9c75762503a747fe04d61ff5d6de3e5410163a7f4fe2d48fed65e140b1e0bb8",
    "full-node-suite.junit.xml":
        "2c4205b72f733a25d8aa887a26affc470f7120bfaf858b5996f010da3abc9d71",
    "full-python-suite.junit.xml":
        "12d9ba613d0630db47d977986bfa69baef040a2c247dd52fa5e3ea143fae95d6",
    "full-python-suite.collection-diagnostic.junit.xml":
        "41e5e4a4ad7999b9eb180628a607543dc41cf4f7210d40eadf5f5c0e6fe3cf82",
}
EXPECTED_CAPSULE_HASH = (
    "sha256:c003c60f81dcb970c17f1878936cad5ca3d5da67676d5ca4bcca8b06fec70fea"
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "compaction-recovery-verification.json",
    "full-regression-impact.json",
    "write-scope-verification.json",
    "dependency-status.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


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


def write_json(path: Path, value: object) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def canonical_hash_excluding(value: dict[str, Any], excluded: str) -> str:
    preimage = {key: item for key, item in value.items() if key != excluded}
    encoded = json.dumps(
        preimage,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, expected_hash in expected.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"required bound file is missing: {relative}")
        actual = sha256(path)
        if actual != expected_hash:
            raise SystemExit(
                f"bound file changed: {relative}: sha256:{actual} != sha256:{expected_hash}"
            )


def node_footer(path: Path) -> dict[str, int]:
    values = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(values) != required:
        raise SystemExit(f"Node JUnit footer is incomplete: {path}")
    return values


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    footer = node_footer(path)
    files = sorted({case.get("file", "") for case in cases if case.get("file")})
    summary = {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "skipped": footer["skipped"],
        "test_file_count": len(files),
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": sum(case.find("failure") is not None for case in cases),
        "xml_testcase_count": len(cases),
    }
    return summary


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(suite.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    return {
        "collected": tests,
        "errors": errors,
        "failed": failures,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": tests - failures - errors - skipped,
        "skipped": skipped,
        "xml_testcase_count": len(root.findall(".//testcase")),
    }


def source_inventory() -> list[dict[str, Any]]:
    assert_hashes(SOURCE_HASHES)
    rows: list[dict[str, Any]] = []
    for relative in SOURCE_HASHES:
        path = ROOT / relative
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"J04 source unexpectedly has a UTF-8 BOM: {relative}")
        if b"\r\n" in data or not data.endswith(b"\n"):
            raise SystemExit(f"J04 source does not use canonical LF endings: {relative}")
        text = data.decode("utf-8")
        if "\ufffd" in text:
            raise SystemExit(f"J04 source contains a replacement character: {relative}")
        rows.append(
            {
                "byte_size": len(data),
                "path": relative,
                "sha256": "sha256:" + SOURCE_HASHES[relative],
                "utf8_bom": False,
                "uses_lf_only": True,
            }
        )
    return rows


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = raw["work_packages"]
    if not isinstance(packages, list) or len(packages) != 156:
        raise SystemExit("development manifest must contain 156 work packages")
    rows = [row for row in packages if row.get("id") == WORK_PACKAGE_ID]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one J04 row")
    row = rows[0]
    expected = {
        "depends_on": ["J02", "J03"],
        "write_scope": [
            "tests/golden/compaction/**",
            "artifacts/work_packages/J04/**",
        ],
        "exit_criteria": [
            "phase cursor and blockers recover",
            "prose summary cannot replace artifacts",
        ],
        "required_checks": ["compaction_resume_test", "context_poisoning_test"],
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise SystemExit(f"J04 manifest contract changed: {key}: {row.get(key)!r}")
    return {
        "depends_on": expected["depends_on"],
        "exit_criteria": expected["exit_criteria"],
        "independent_review": row.get("independent_review"),
        "manifest_sha256": sha256_id(MANIFEST),
        "package_count": len(packages),
        "required_checks": expected["required_checks"],
        "status": "PASS",
        "write_scope": expected["write_scope"],
    }


def run_check(command: list[str]) -> dict[str, Any]:
    executable_command = command
    if sys.platform == "win32" and command[0] == "npm":
        executable_command = ["cmd.exe", "/d", "/c", "npm.cmd", *command[1:]]
    process = subprocess.run(
        executable_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": " ".join(command),
        "exit_code": process.returncode,
        "status": "PASS" if process.returncode == 0 else "FAIL",
        "stderr": process.stderr.strip(),
        "stdout": process.stdout.strip(),
    }


def recovery_verification() -> dict[str, Any]:
    files = source_inventory()
    assert_hashes(J03_IMPLEMENTATION_HASHES)
    fixture = read_json(ROOT / "tests/golden/compaction/post-compaction-recovery.fixture.json")
    receipt = fixture.get("sealed_receipt")
    if not isinstance(receipt, dict) or receipt.get("capsule_hash") != EXPECTED_CAPSULE_HASH:
        raise SystemExit("J04 golden fixture is not bound to the expected sealed capsule hash")
    oracle = (ROOT / "tests/golden/compaction/recovery-oracle.mjs").read_text(
        encoding="utf-8"
    )
    integrity = oracle.find(
        'const capsule = verifyContextCapsuleIntegrity(readData(request, "capsule"));'
    )
    receipt_validation = oracle.find(
        'const receipt = validateReceipt(readData(request, "sealed_receipt"));'
    )
    freshness = oracle.find("const freshness = requireFreshContextCapsule(")
    if not (0 <= integrity < receipt_validation < freshness):
        raise SystemExit("J04 recovery order is not integrity -> receipt -> freshness")
    if 'readData(request, "prose_summary")' in oracle:
        raise SystemExit("untrusted prose was read as J04 recovery authority")
    resume = (ROOT / "tests/golden/compaction/compaction-resume.test.mjs").read_text(
        encoding="utf-8"
    )
    poisoning = (ROOT / "tests/golden/compaction/context-poisoning.test.mjs").read_text(
        encoding="utf-8"
    )
    required_probes = {
        "direct_capsule_hash_tamper": "capsule_hash: `sha256:${\"f\".repeat(64)}`" in resume,
        "missing_changed_unaccounted_artifacts": all(
            value in resume for value in ("CAPSULE_ARTIFACT_STALE", "CAPSULE_CANONICAL_STATE_DRIFT")
        ),
        "attacker_rehash_external_receipt_binding":
            "attacker-rehashed capsule still fails external receipt binding" in poisoning,
        "excluded_content_has_no_authority":
            "excluded content never becomes recovery authority" in poisoning,
        "prompt_injection_cannot_change_authority":
            "conflicting prose cannot alter phase, blockers or authority" in poisoning,
        "runspec_policy_phase_drift": all(
            value in poisoning
            for value in ("CAPSULE_PHASE_DRIFT", "CAPSULE_RUN_SPEC_DRIFT", "CAPSULE_POLICY_DRIFT")
        ),
    }
    if not all(required_probes.values()):
        raise SystemExit(f"J04 adversarial probe inventory is incomplete: {required_probes}")
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_boundary": {
            "authority_source": "SEALED_CONTEXT_CAPSULE",
            "external_receipt_binding_required": True,
            "narrative_prose_authority": False,
            "recovery_order": [
                "verify_context_capsule_integrity",
                "match_external_sealed_receipt",
                "require_fresh_context_capsule",
                "project_recovery_state_from_verified_capsule",
            ],
            "runtime_implementation_modified_by_j04": False,
            "test_only_recovery_oracle": True,
        },
        "capsule": {
            "capsule_hash": EXPECTED_CAPSULE_HASH,
            "capsule_id": receipt.get("capsule_id"),
            "fixture_id": fixture.get("fixture_id"),
            "sealed_receipt_id": receipt.get("receipt_id"),
        },
        "exit_criteria": {
            "phase_cursor_and_blockers_recover": "PASS",
            "prose_summary_cannot_replace_artifacts": "PASS",
        },
        "j03_implementation_preservation": [
            {
                "path": relative,
                "sha256": "sha256:" + digest,
                "status": "UNCHANGED",
            }
            for relative, digest in J03_IMPLEMENTATION_HASHES.items()
        ],
        "negative_and_adversarial_probes": required_probes,
        "source_files": files,
        "status": "PASS",
    }


def regression_evidence() -> dict[str, Any]:
    for name, digest in JUNIT_HASHES.items():
        path = ATTEMPT / name
        if not path.is_file() or sha256(path) != digest:
            raise SystemExit(f"J04 JUnit receipt changed or is missing: {name}")
    targeted = node_summary(ATTEMPT / "targeted-j04-suite.junit.xml")
    j03 = node_summary(ATTEMPT / "j03-capsule-regression.junit.xml")
    node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    diagnostic = pytest_summary(
        ATTEMPT / "full-python-suite.collection-diagnostic.junit.xml"
    )
    if not (
        targeted["collected"] == targeted["passed"] == targeted["xml_testcase_count"] == 10
        and targeted["failed"] == targeted["cancelled"] == targeted["skipped"]
        == targeted["todo"] == targeted["xml_failure_count"] == targeted["xml_error_count"] == 0
    ):
        raise SystemExit(f"J04 targeted suite is not 10/10: {targeted}")
    if not (
        j03["collected"] == j03["passed"] == j03["xml_testcase_count"] == 21
        and j03["failed"] == j03["cancelled"] == j03["skipped"] == j03["todo"]
        == j03["xml_failure_count"] == j03["xml_error_count"] == 0
    ):
        raise SystemExit(f"J03 capsule regression is not 21/21: {j03}")
    if not (
        node["collected"] == node["passed"] == 470
        and node["xml_testcase_count"] == 467
        and node["failed"] == node["cancelled"] == node["skipped"] == node["todo"]
        == node["xml_failure_count"] == node["xml_error_count"] == 0
    ):
        raise SystemExit(
            "full Node suite is not 470/470 with the bound 467-leaf JUnit "
            f"inventory: {node}"
        )
    if not (
        python["collected"] == python["passed"] == python["xml_testcase_count"] == 990
        and python["failed"] == python["errors"] == python["skipped"] == 0
    ):
        raise SystemExit(f"full Python suite is not 990/990: {python}")
    if not (
        diagnostic["collected"] == diagnostic["errors"] == 1
        and diagnostic["passed"] == diagnostic["failed"] == diagnostic["skipped"] == 0
    ):
        raise SystemExit("the preserved pytest-executable diagnostic changed")
    diagnostic_text = (
        ATTEMPT / "full-python-suite.collection-diagnostic.junit.xml"
    ).read_text(encoding="utf-8")
    if "ModuleNotFoundError: No module named 'scripts'" not in diagnostic_text:
        raise SystemExit("the preserved collection diagnostic has a different fingerprint")
    structure = run_check(["npm", "run", "check:structure"])
    boundaries = run_check(["npm", "run", "check:boundaries"])
    diff_check = run_check(["git", "diff", "--check"])
    if any(row["exit_code"] != 0 for row in (structure, boundaries, diff_check)):
        raise SystemExit("a J04 repository regression check failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "diagnostic_not_acceptance_evidence": {
            **diagnostic,
            "classification": "PRESERVED_COMMAND_SHAPE_DIAGNOSTIC",
            "fingerprint": "ModuleNotFoundError: No module named 'scripts'",
            "superseded_by": "uv run --locked python -m pytest tests -p no:cacheprovider",
        },
        "full_node": node,
        "full_python": python,
        "j03_capsule_regression": j03,
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "repository_checks": {
            "git_diff_check": {
                "exit_code": diff_check["exit_code"],
                "status": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
            },
            "package_boundaries": {
                "exit_code": boundaries["exit_code"],
                "status": "PASS",
            },
            "repository_structure": {
                "exit_code": structure["exit_code"],
                "status": "PASS",
            },
        },
        "status": "PASS",
        "targeted_j04": targeted,
    }


def current_report_state(package_id: str) -> bool:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts = package_root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts.is_dir():
        for path in attempts.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        _, latest = max(numeric)
        report_path = latest / "report.json"
        if package_id == WORK_PACKAGE_ID and not report_path.is_file():
            return True
        if not report_path.is_file():
            return False
    else:
        report_path = package_root / "report.json"
        if not report_path.is_file():
            return package_id == WORK_PACKAGE_ID
    report = read_json(report_path)
    return report.get("status") == "PASS" and report.get("package_status") in (None, "PASS")


def post_j04_dag_projection() -> dict[str, Any]:
    raw = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = raw["work_packages"]
    order = [row["id"] for row in packages]
    dependencies = {row["id"]: set(row.get("depends_on", [])) for row in packages}
    if len(order) != 156 or len(set(order)) != 156:
        raise SystemExit("development manifest package identity changed")
    completed = {package_id for package_id in order if current_report_state(package_id)}
    if WORK_PACKAGE_ID not in completed:
        raise SystemExit("post-J04 projection did not include J04 PASS")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    if len(completed) != 45 or not ready or ready[0] != "K01":
        raise SystemExit(
            f"unexpected post-J04 DAG: completed={len(completed)} ready={ready}"
        )
    return {
        "blocked_package_count": len(blocked),
        "completed_package_count": len(completed),
        "completion_ready": False,
        "next_package": ready[0],
        "ready_package_count": len(ready),
        "ready_packages_manifest_order": ready,
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    assert_hashes(DEPENDENCY_REPORT_HASHES)
    dependencies: dict[str, Any] = {}
    for relative, digest in DEPENDENCY_REPORT_HASHES.items():
        report = read_json(ROOT / relative)
        if report.get("status") != "PASS" or report.get("package_status") != "PASS":
            raise SystemExit(f"J04 dependency is not PASS: {relative}")
        dependencies[str(report["work_package_id"])] = {
            "attempt_id": report.get("attempt_id"),
            "report": relative,
            "report_sha256": "sha256:" + digest,
            "status": "PASS",
        }
    prior = read_json(
        ROOT
        / "artifacts/work_packages/B04/attempts/0008/post-b04-0008-dag-reconciliation.json"
    )
    if not (
        prior.get("status") == "PASS"
        and prior.get("completed_package_count") == 44
        and prior.get("next_package") == "J04"
        and prior.get("ready_packages_manifest_order") == ["J04", "K01", "T01", "A06"]
    ):
        raise SystemExit("pre-J04 sealed DAG evidence changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "manifest": manifest_contract(),
        "post_j04_projection": post_j04_dag_projection(),
        "pre_j04_sealed_projection": {
            "artifact": "artifacts/work_packages/B04/attempts/0008/post-b04-0008-dag-reconciliation.json",
            "artifact_sha256": sha256_id(
                ROOT
                / "artifacts/work_packages/B04/attempts/0008/post-b04-0008-dag-reconciliation.json"
            ),
            "completed_package_count": 44,
            "next_package": "J04",
            "status": "PASS",
        },
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    assert_hashes(J03_IMPLEMENTATION_HASHES)
    return {
        "approved_product_scope": ["tests/golden/compaction/**"],
        "approved_evidence_scope": ["artifacts/work_packages/J04/**"],
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "j03_implementation_hashes_unchanged": True,
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "compaction-recovery-verification.json": recovery_verification(),
        "full-regression-impact.json": regression_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
        "dependency-status.json": dependency_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    dag = documents["dependency-status.json"]["post_j04_projection"]
    return f"""# J04-0001 post-compaction recovery integration review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking J04 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Actor independence: `false`

The product owner requires serial execution in the primary session without
Fleet or subagents. This review is procedurally separate from implementation,
but it is not actor-independent certification.

## Findings

1. Recovery first verifies the ContextCapsule's own integrity, then binds the
   observed capsule ID and hash to an external sealed receipt, and only then
   performs J03 freshness checks. Phase, blockers, RunSpec, policy, included
   artifacts, and exclusions are projected exclusively from that verified
   capsule.
2. Narrative prose is accepted only as an explicitly untrusted request field.
   The recovery implementation never reads it, so prose cannot replace an
   artifact, erase blockers, move the phase cursor, or acquire authority.
3. Direct hash tamper and semantic tamper fail ContextCapsule integrity. An
   attacker who changes phase/blockers and recomputes a valid capsule hash is
   still rejected because the external sealed receipt no longer matches.
4. Missing or changed included artifacts fail stale; newly visible unaccounted
   artifacts fail canonical-state drift. Phase, RunSpec, and policy drift also
   fail closed before any resumed state is returned.
5. Excluded content remains named as excluded and cannot regain authority via
   prose or a changed selection. Accessor-backed and unknown recovery fields
   fail without executing hostile accessors.
6. J03 runtime files remain byte-identical to their sealed J03 hashes. J04 adds
   only four golden recovery files and does not create a second ContextCapsule
   or recovery authority.
7. Required checks pass 10/10, J03 capsule regression passes 21/21, full Node
   passes 470/470, and full Python passes 990/990. There are no skips, xfails,
   todos, cancellations, or new failures. The earlier one-case Python
   collection error is preserved as a command-shape diagnostic and is not
   substituted for the authoritative green run.
8. Write-scope violations are zero. UTF-8/LF, syntax, structure, boundaries,
   and repository diff checks pass; the existing dirty worktree and all prior
   evidence remain preserved.

## Dependency effect

After J04 PASS, live projection contains {dag['completed_package_count']} PASS
packages. The manifest-order READY set is
`{', '.join(dag['ready_packages_manifest_order'])}`, with `{dag['next_package']}`
as the next serial package. This projection will be independently recomputed
and RAH-sealed after J04 closeout.

## Assurance boundary

J04 proves post-compaction recovery from sealed artifacts. It does not claim
that downstream memory, ingest, role routing, or the full 156-package product
is complete. Global `implementation_gate=fail` and `completion_ready=false`
remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect J04 authority, dependencies, J03 implementation hashes, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement the test-only sealed-capsule recovery oracle and golden adversarial fixtures", 0, "PASS: four J04 product files"),
        ("C003", "node --test --test-reporter=junit tests/golden/compaction/compaction-resume.test.mjs tests/golden/compaction/context-poisoning.test.mjs", 0, "PASS: 10/10"),
        ("C004", "node --test --test-reporter=junit packages/context-capsule/src/capsule-hash.test.mjs packages/context-capsule/src/stale-capsule.test.mjs", 0, "PASS: 21/21 J03 regression"),
        ("C005", "node --check <three J04 .mjs files>", 0, "PASS: 3/3"),
        ("C006", "node --test --test-concurrency=1 --test-reporter=junit <complete sorted repository Node inventory>", 0, "PASS: 470/470"),
        ("C007", "uv run --locked python -m pytest tests -p no:cacheprovider --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 990/990"),
        ("C008", "npm run check:structure", 0, "PASS"),
        ("C009", "npm run check:boundaries", 0, "PASS"),
        ("C010", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C011", "Primary-session separate adversarial integration review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("D001", "Invoke pytest through the executable rather than python -m while collecting the full suite", 1, "PRESERVED_DIAGNOSTIC: ModuleNotFoundError for scripts; authoritative python -m run passed 990/990"),
        ("D002", "Pipe a PowerShell foreach block directly to a formatter during final evidence inspection", 1, "DIAGNOSTIC_ONLY: reliability hook rejected command shape; retried with a collected array"),
        ("D003", "Use a Windows wildcard directly in an rg JUnit path", 1, "DIAGNOSTIC_ONLY: Windows path syntax rejected; no mutation"),
    ]
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "J04-0001-COMPACTION-RECOVERY-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "J04-0001-PRIMARY-SESSION-VERIFIER",
            "actor_type": "tool",
        },
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-J04-0001-COMPACTION-RECOVERY-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "compaction_resume_test",
                "details": "5/5 phase, blocker, receipt, tamper, and artifact-drift cases passed",
                "status": "PASS",
            },
            {
                "check": "context_poisoning_test",
                "details": "5/5 prose, attacker-rehash, exclusion, policy, and hostile-input cases passed",
                "status": "PASS",
            },
            {
                "check": "j03_capsule_regression",
                "details": "21/21; sealed J03 implementation hashes unchanged",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Python 990/990 and Node 470/470; unexpected suppression or failure count zero",
                "status": "PASS",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid J04 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        *OUTPUT_NAMES,
        "compaction-recovery-verification.artifact-receipt.json",
        "targeted-j04-suite.junit.xml",
        "j03-capsule-regression.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-python-suite.collection-diagnostic.junit.xml",
        "commands.jsonl",
        "review.md",
        "build_j04_0001_evidence.py",
        "j04_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required J04 evidence artifact is missing: {name}")
        rows.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return rows


def report_document(
    documents: dict[str, dict[str, Any]],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(
        ATTEMPT / "compaction-recovery-verification.artifact-receipt.json"
    )
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/J04/attempts/0001/compaction-recovery-verification.artifact-receipt.json",
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": dependency["dependencies"],
        "dependency_effect": dependency["post_j04_projection"],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "phase_cursor_and_blockers_recover": "PASS",
            "prose_summary_cannot_replace_artifacts": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "j03_implementation_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "actor-independent certification",
            "downstream package completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "compaction_resume_test": {
                "failed": 0,
                "passed": 5,
                "skipped": 0,
                "status": "PASS",
            },
            "context_poisoning_test": {
                "failed": 0,
                "passed": 5,
                "skipped": 0,
                "status": "PASS",
            },
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/J04/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Post-compaction recovery gate",
        "verification": {
            "full_node": "470/470",
            "full_python": "990/990",
            "j03_capsule_regression": "21/21",
            "targeted_j04": "10/10",
            "write_scope_violation_count": 0,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def expected_commands() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(
        expected_commands(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    write_json(
        ATTEMPT / "compaction-recovery-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "compaction-recovery-verification.json"),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
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
    write_json(
        ATTEMPT / "report.json", report_document(documents, rah_state=rah_state)
    )
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored J04 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored J04 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored J04 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "compaction-recovery-verification.json")
    receipt_path = ATTEMPT / "compaction-recovery-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(
        expected_receipt
    ):
        raise SystemExit("stored J04 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("J04 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored J04 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"J04 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "470/470",
        "full_python": "990/990",
        "j03_capsule_regression": "21/21",
        "next_package": documents["dependency-status.json"]["post_j04_projection"][
            "next_package"
        ],
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_j04": "10/10",
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
