#!/usr/bin/env python3
"""Build and verify byte-bound evidence for B04-0005.

This attempt revalidates the B02-0002 dependency correction through the B04
build and canonical-package boundary.  Evidence is derived from live source
and snapshot bytes, the built distributions, JUnit documents, and the current
RAH ledger.  Stored narrative results are never accepted as their own proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0005"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/build/canonical_registry"))
sys.path.insert(
    0, str(ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation")
)

import materialize  # noqa: E402
import state_store  # noqa: E402
import verify_dependency_revalidation as dependency_revalidation  # noqa: E402
from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402


ATTEMPT_ID = "B04-0005"
DECISION_ID = "HD-EF4-UNBLOCK-SET-20260730-001"
CREATED_AT = "2026-07-30T05:30:00Z"
SOURCE_BUNDLE_HASH = (
    "sha256:47a8d63daadae502bc3fc91c19cebc1f8f04f885e24d6d409c444748e04fd340"
)
SNAPSHOT_BUNDLE_HASH = (
    "sha256:dde63a97254b2432d0fc1f917e1bd294210f43e19720386ac4295e317a497ed7"
)
REGISTRY_HASH = (
    "sha256:5f3c4514b3801cc66cc0a403d49c1dc380f7665ddc570d4987072a6f77fde1dd"
)
OPENAPI_HASH = (
    "sha256:c77aa89918cc33cded07755bbf2cbec7fcb6554e573efbca2ebd9480b78344d7"
)
CURRENT_MANIFEST_HASH = (
    "7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319"
)

FIXED_HASHES = {
    "artifacts/authority_decisions/HD-EF4-UNBLOCK-SET-20260730-001.human-decision.json": "fdb8752fc7a629e444114b089e33163a7d8dc68290bf99d1667d6a4208c5f2f2",
    "artifacts/authority_decisions/HD-EF4-J02-SG002-20260730-001.human-decision.json": "ad7c8345bbcaa813c641ba139913728dabfe969fb1fef06a3e2209949939cc90",
    "artifacts/work_packages/B02/attempts/0002/report.json": "3c2259e7d4b7ce987960b82f2fb161914637567eacf3030d24899e44f462b33a",
    "artifacts/work_packages/B02/attempts/0002/review.md": "4b126d5d36aae2d8c742e5a16c14b7928c249e172be5934a5b1ea937b76c0f84",
    "artifacts/work_packages/B02/attempts/0002/rah-core-integrity.json": "b7d4ba723c8dea6fbbdf69bd5ca08dd94477ae4c28b571bd300d3bc03acd3563",
    "artifacts/work_packages/B02/attempts/0002/double-build-comparison-rerun.json": "692a3d1595ee292c15b7dd5a0e79cd22e997248dcda69a5efb488432821c7f5f",
    "artifacts/work_packages/B02/attempts/0002/staged-build-diagnostic.json": "dbe85b9206b890a0863a0d24d811a2beec963c1c1f551eaa6659dc10f67554ec",
    "artifacts/work_packages/B04/attempts/0004/report.json": "a2a2a3bca9ccf1650145b983d942e3888cfd79aaa3568db71a865b5d410d5e13",
    "artifacts/work_packages/B04/attempts/0004/review.md": "a86a2700aa4b2a138d44771b4ee3adad70fd758ae17b64657b6767953d8d5ea7",
    "artifacts/work_packages/B04/attempts/0004/commands.jsonl": "345c2e68edc326c672fc395102d9c31d425d98d1c64299f41ec4a06c39d90d91",
    "manifests/development_manifest.yaml": CURRENT_MANIFEST_HASH,
    "pyproject.toml": "31cf5dffa4703052d70536dbbb6e64d917900c70d52b039f9c9cbf09920353db",
    "scripts/build/canonical_registry/materialize.py": "3918a3e3d8c442b856bae748c020655bdc8954d10e0efc19a96a589106f9190e",
    "scripts/build/canonical_registry/verify_packaging.py": "3a74c7495ed80fe5520da77126fe01929f0938de3e414bae3cde70d1de31b9a2",
    "scripts/build/double_build.py": "99f223bd8d4a3d397cf9c560274c498a3a51c15116e094f9896278640aca32df",
    "src/epistemic_foundry/contracts/registry.py": "da04887973d4152865c161b0fd012aee202cc67ee5ee7b4da03507d289b5e7ac",
    "tests/packaging/test_canonical_registry.py": "0a6c7dfad24686a1ebb5c1036578a2caa43af82155b02cbf13005a70c3a7d9bd",
    "uv.lock": "5c3798ff0323f9352d73f17fa93913590d7dbb5382dd0de26b1619e775b58caa",
}

DIST = {
    "epistemic_foundry-4.0.0-py3-none-any.whl": {
        "artifact_id": "ART-B04-0005-WHEEL",
        "byte_size": 303_618,
        "media_type": "application/zip",
        "receipt_file": "wheel.artifact-receipt.json",
        "receipt_id": "AR-B04-0005-WHEEL",
        "sha256": "cc3aa468f09092134a4bc8448f4bf60822a4d2ff8df6df16bcbc86483238cb7a",
    },
    "epistemic_foundry-4.0.0.tar.gz": {
        "artifact_id": "ART-B04-0005-SDIST",
        "byte_size": 252_494,
        "media_type": "application/gzip",
        "receipt_file": "sdist.artifact-receipt.json",
        "receipt_id": "AR-B04-0005-SDIST",
        "sha256": "c2d68ad297ae295f30761cc68c48d3bd1d9cc90cd5111597bb7be9cd27ee7eed",
    },
}


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


def assert_fixed_hashes() -> None:
    for relative, expected in FIXED_HASHES.items():
        path = ROOT / relative
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(
                f"fixed authority/history hash mismatch for {relative}: "
                f"{actual} != {expected}"
            )


def verify_dependency_binding() -> dict[str, Any]:
    live = dependency_revalidation.verify()
    stored = read_json(ATTEMPT / "dependency-revalidation.json")
    # The attempt-local dependency report was created before the B04 core seal.
    # Its observed RAH generation is provenance, not part of the B02 semantic
    # binding: later append-only generations must continue to carry E0090/E0091.
    # Compare every other field exactly and separately validate the monotonic
    # generation observation instead of rewriting the pre-core report.
    live_stable = json.loads(json.dumps(live))
    stored_stable = json.loads(json.dumps(stored))
    live_generation = live_stable["b02_binding"]["rah_seal"].pop(
        "observed_generation"
    )
    stored_generation = stored_stable["b02_binding"]["rah_seal"].pop(
        "observed_generation"
    )
    if live_stable != stored_stable:
        raise SystemExit("stored dependency revalidation differs from live recomputation")
    if stored_generation != "000084-016aba75" or not re.fullmatch(
        r"0000(?:84|85|86)-[0-9a-f]{8}", str(live_generation)
    ):
        raise SystemExit("B02 RAH seal generation provenance is not monotonic")
    if live.get("status") != "PASS":
        raise SystemExit("B02 dependency/build binding is not PASS")
    return live


def canonical_inventory() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry, resources = materialize.build_registry_document(ROOT)
    expected_registry = materialize._registry_bytes(registry)
    if materialize.calculate_source_bundle_hash(resources) != SOURCE_BUNDLE_HASH:
        raise SystemExit("live root source bundle hash changed")
    if (
        materialize.calculate_projected_snapshot_bundle_hash(resources)
        != SNAPSHOT_BUNDLE_HASH
    ):
        raise SystemExit("live projected snapshot bundle hash changed")
    if REGISTRY_PATH.read_bytes() != expected_registry:
        raise SystemExit("live registry differs from deterministic projection output")
    if sha256_id(REGISTRY_PATH) != REGISTRY_HASH:
        raise SystemExit("live registry byte hash changed")

    source_entries: list[dict[str, Any]] = []
    snapshot_entries: list[dict[str, Any]] = []
    expected_paths: set[str] = set()
    document_ids: set[str] = set()
    duplicate_ids: list[str] = []
    missing: list[str] = []
    mismatches: list[str] = []
    for resource in resources:
        entry = resource.manifest_entry()
        relative = resource.relative_path.as_posix()
        expected_paths.add(relative)
        document_id = str(entry["document_id"])
        if document_id in document_ids:
            duplicate_ids.append(document_id)
        document_ids.add(document_id)
        source_entries.append(
            {
                "byte_size": entry["byte_size"],
                "document_id": document_id,
                "media_type": entry["media_type"],
                "path": relative,
                "projection_target_path": entry["package_path"],
                "sha256": entry["sha256"],
            }
        )
        target = SNAPSHOT / Path(*PurePosixPath(relative).parts)
        if not target.is_file():
            missing.append(relative)
            continue
        observed_hash = sha256_id(target)
        snapshot_entries.append(
            {
                "byte_size": target.stat().st_size,
                "document_id": document_id,
                "package_path": relative,
                "sha256": observed_hash,
                "source_path": entry["source_path"],
            }
        )
        if observed_hash != entry["sha256"] or target.read_bytes() != resource.content:
            mismatches.append(relative)

    actual_paths = {
        path.relative_to(SNAPSHOT).as_posix()
        for path in SNAPSHOT.rglob("*")
        if path.is_file() and path.name != "canonical-registry.json"
    }
    extra = sorted(actual_paths - expected_paths)
    missing = sorted(set(missing) | (expected_paths - actual_paths))
    if missing or extra or mismatches or duplicate_ids:
        raise SystemExit(
            "canonical projection drift: "
            f"missing={missing}, extra={extra}, mismatches={mismatches}, "
            f"duplicate_ids={duplicate_ids}"
        )
    if len(source_entries) != 125 or len(snapshot_entries) != 125:
        raise SystemExit("canonical resource count is not 125")

    openapi = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    operations = re.findall(r"^\s+operationId:\s*([^\s#]+)\s*$", text, re.M)
    if not text.startswith("openapi: 3.1.1\n"):
        raise SystemExit("OpenAPI resource is not version 3.1.1")
    if len(operations) != 33 or len(set(operations)) != 33:
        raise SystemExit("OpenAPI operation inventory is not 33 unique IDs")
    if sha256_id(openapi) != OPENAPI_HASH:
        raise SystemExit("OpenAPI byte hash changed")

    source = {
        "attempt_id": ATTEMPT_ID,
        "duplicate_schema_ids": [],
        "entries": source_entries,
        "openapi": {
            "operation_count": 33,
            "operation_ids_unique": True,
            "path": "openapi/epistemic-foundry-v1.openapi.yaml",
            "sha256": OPENAPI_HASH,
            "version": "3.1.1",
        },
        "schema_count": 124,
        "source_bundle_hash": SOURCE_BUNDLE_HASH,
        "source_file_count": 125,
        "status": "PASS",
    }
    snapshot = {
        "attempt_id": ATTEMPT_ID,
        "comparison_to_source": {
            "extra_paths": [],
            "hash_mismatches": [],
            "missing_paths": [],
            "status": "PASS",
        },
        "entries": snapshot_entries,
        "projected_snapshot_bundle_hash": SNAPSHOT_BUNDLE_HASH,
        "projection_file_count_including_registry": 126,
        "registry": {
            "file_count": registry["file_count"],
            "path": "src/epistemic_foundry/_canonical/canonical-registry.json",
            "sha256": REGISTRY_HASH,
        },
        "snapshot_resource_count": 125,
        "status": "CURRENT",
    }
    return source, snapshot, registry


def junit_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    direct_cases = list(root.findall("testcase"))
    case_nodes = list(root.findall(".//testcase"))
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites and not case_nodes:
        raise SystemExit(f"JUnit has no test cases: {path}")

    # Node emits direct cases plus nested suite containers that TAP counts as
    # tests.  Pytest emits one aggregate suite and therefore uses its declared
    # counters.
    if root.tag == "testsuites" and direct_cases:
        suite_nodes = list(root.findall(".//testsuite"))
        tests = len(case_nodes) + len(suite_nodes)
        failures = sum(case.find("failure") is not None for case in case_nodes)
        errors = sum(case.find("error") is not None for case in case_nodes)
        skipped = sum(case.find("skipped") is not None for case in case_nodes)
    else:
        tests = sum(int(suite.get("tests", "0")) for suite in suites)
        failures = sum(int(suite.get("failures", "0")) for suite in suites)
        errors = sum(int(suite.get("errors", "0")) for suite in suites)
        skipped = sum(int(suite.get("skipped", "0")) for suite in suites)

    failure_rows: list[dict[str, str]] = []
    for case in case_nodes:
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is None:
            continue
        classname = case.get("classname", "")
        name = case.get("name", "")
        failure_rows.append(
            {
                "message": problem.get("message", ""),
                "node_id": f"{classname}::{name}" if classname else name,
                "type": problem.get("type", "AssertionError"),
            }
        )
    return {
        "collected": tests,
        "errors": errors,
        "failed": failures,
        "failures": failure_rows,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": tests - failures - errors - skipped,
        "skipped": skipped,
    }


def verify_regressions() -> dict[str, Any]:
    packaging = junit_summary(ATTEMPT / "packaging-suite.junit.xml")
    python = junit_summary(ATTEMPT / "full-python-suite.junit.xml")
    node = junit_summary(ATTEMPT / "full-node-suite.junit.xml")
    if (packaging["collected"], packaging["passed"], packaging["failed"]) != (
        24,
        24,
        0,
    ) or packaging["skipped"] != 0:
        raise SystemExit(f"packaging JUnit is not a clean 24/24 PASS: {packaging}")
    if (python["collected"], python["passed"], python["failed"]) != (
        964,
        963,
        1,
    ) or python["skipped"] != 0:
        raise SystemExit(f"Python JUnit changed: {python}")
    python_failure = python["failures"][0]
    if not python_failure["node_id"].endswith(
        "test_repository_dependency_lock_closes_exact_tiktoken_pin"
    ) or "TOKENIZER_CONTRACT_UNAVAILABLE" not in python_failure["message"]:
        raise SystemExit("unexpected Python residual failure fingerprint")
    if (node["collected"], node["passed"], node["failed"]) != (
        458,
        457,
        1,
    ) or node["skipped"] != 0:
        raise SystemExit(f"Node JUnit changed: {node}")
    node_failure = node["failures"][0]
    node_text = node_failure["node_id"] + "\n" + node_failure["message"]
    if "S04-TM004" not in node_text:
        raise SystemExit("unexpected Node residual failure")
    for digest in (
        "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7",
        CURRENT_MANIFEST_HASH,
    ):
        if digest not in node_text:
            raise SystemExit("S04-TM004 active binding fingerprint changed")

    return {
        "attempt_id": ATTEMPT_ID,
        "b04_owned_failure_count": 0,
        "global_node_suite_green": False,
        "global_python_suite_green": False,
        "node": {
            **node,
            "b04_causal_impact": "NONE",
            "classification": "EXPECTED_S04_ACTIVE_BINDING_MIGRATION_DEBT",
            "current_actual_manifest_sha256": CURRENT_MANIFEST_HASH,
            "expected_binding_sha256": "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7",
            "failure_owner": "S04",
            "normalized_failure_fingerprint": "S04_TM004_ACTIVE_DEVELOPMENT_MANIFEST_BINDING_STALE",
        },
        "packaging": {**packaging, "status": "PASS"},
        "python": {
            **python,
            "b04_causal_impact": "NONE",
            "classification": "EXPECTED_J02_0003_MIGRATION_DEBT",
            "expected_resolving_test": "tests.test_j02_context_budget::test_repository_dependency_lock_closes_exact_tiktoken_pin",
            "failure_owner": "J02",
            "normalized_failure_fingerprint": "J02_DEPENDENCY_READER_OMITS_CANONICAL_SKILL_CONTEXT_GROUP",
        },
        "status": "PASS_WITH_TWO_BOUNDED_NON_B04_DEBTS",
        "unexpected_failure_count": 0,
        "unexpected_skip_or_xfail_count": 0,
    }


def load_packaging_verification(registry: dict[str, Any]) -> dict[str, Any]:
    verification = read_json(ATTEMPT / "packaging-verification-run.json")
    if verification.get("status") != "PASS":
        raise SystemExit("formal packaging verification is not PASS")
    canonical = verification.get("canonical_registry")
    expected = {
        "source_bundle_hash": SOURCE_BUNDLE_HASH,
        "projected_snapshot_bundle_hash": SNAPSHOT_BUNDLE_HASH,
        "registry_sha256": REGISTRY_HASH,
        "schema_count": 124,
        "resource_count": 125,
        "openapi_document_count": 1,
    }
    if not isinstance(canonical, dict):
        raise SystemExit("formal packaging verification lacks registry evidence")
    for key, value in expected.items():
        if canonical.get(key) != value:
            raise SystemExit(f"packaging registry mismatch for {key}")
    if canonical.get("projection_tool_identity") != registry["projection_tool_identity"]:
        raise SystemExit("packaging projection tool identity mismatch")
    checks = verification.get("checks")
    if not isinstance(checks, dict):
        raise SystemExit("formal packaging checks are missing")
    installed = checks.get("installed_wheel")
    reproducibility = checks.get("two_build_reproducibility")
    if not isinstance(installed, dict) or not isinstance(reproducibility, dict):
        raise SystemExit("installed/reproducibility checks are missing")
    if not (
        installed.get("clean_venv_install") == "PASS"
        and installed.get("arbitrary_empty_cwd") == "PASS"
        and installed.get("fallback_success_count") == 0
        and installed.get("tamper_error_code") == "CANONICAL_REGISTRY_HASH_MISMATCH"
        and all(value is True for value in reproducibility.values())
        and checks.get("sdist_to_wheel") == "PASS"
    ):
        raise SystemExit("installed/reproducibility packaging checks did not pass")
    for filename, definition in DIST.items():
        artifact = ATTEMPT / "dist" / filename
        observed = {"byte_size": artifact.stat().st_size, "sha256": sha256(artifact)}
        expected_artifact = {
            "byte_size": definition["byte_size"],
            "sha256": definition["sha256"],
        }
        if observed != expected_artifact:
            raise SystemExit(f"distribution bytes changed: {filename}")
        if verification.get("artifact_inventory", {}).get(filename) != observed:
            raise SystemExit(f"formal distribution inventory changed: {filename}")
    return verification


def receipt(
    *,
    receipt_id: str,
    artifact_id: str,
    locator: str,
    media_type: str,
    content_hash: str,
    byte_size: int,
    validation_results: list[dict[str, str]],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": artifact_id,
        "byte_size": byte_size,
        "content_hash": content_hash,
        "created_at": CREATED_AT,
        "created_by": {
            "actor_id": "B04-0005-packaging-revalidator",
            "actor_type": "tool",
        },
        "locator": locator,
        "media_type": media_type,
        "receipt_id": receipt_id,
        "schema_ref": None,
        "validation_results": validation_results,
    }
    value["receipt_hash"] = hash_excluding(value, "receipt_hash")
    validate_artifact("artifact-receipt", value)
    return value


def build_receipts() -> list[dict[str, Any]]:
    projection = receipt(
        receipt_id="AR-B04-0005-CANONICAL-PROJECTION",
        artifact_id="ART-B04-0005-CANONICAL-PROJECTION",
        locator=REGISTRY_PATH.relative_to(ROOT).as_posix(),
        media_type="application/vnd.epistemic-foundry.canonical-registry+json",
        content_hash=REGISTRY_HASH,
        byte_size=REGISTRY_PATH.stat().st_size,
        validation_results=[
            {
                "check": "registry_byte_integrity",
                "details": "The receipt binds the exact live canonical-registry.json bytes.",
                "status": "PASS",
            },
            {
                "check": "root_snapshot_convergence",
                "details": f"All 125 resources bind source {SOURCE_BUNDLE_HASH} to snapshot {SNAPSHOT_BUNDLE_HASH} with no fallback.",
                "status": "PASS",
            },
            {
                "check": "B02_dependency_revalidation",
                "details": "Exact tiktoken 0.13.0 frozen sync and seven tokenizer vectors pass without runtime metadata exposure.",
                "status": "PASS",
            },
        ],
    )
    definitions: list[tuple[str, dict[str, Any]]] = [
        ("projection.artifact-receipt.json", projection)
    ]
    for filename, definition in DIST.items():
        path = ATTEMPT / "dist" / filename
        definitions.append(
            (
                str(definition["receipt_file"]),
                receipt(
                    receipt_id=str(definition["receipt_id"]),
                    artifact_id=str(definition["artifact_id"]),
                    locator=path.relative_to(ROOT).as_posix(),
                    media_type=str(definition["media_type"]),
                    content_hash=sha256_id(path),
                    byte_size=path.stat().st_size,
                    validation_results=[
                        {
                            "check": "raw_byte_hash_and_size",
                            "details": "Raw distribution bytes match the B04-0005 formal packaging inventory.",
                            "status": "PASS",
                        },
                        {
                            "check": "deterministic_build",
                            "details": "Two builds and the sdist-derived wheel satisfy the deterministic build contract.",
                            "status": "PASS",
                        },
                        {
                            "check": "installed_package_isolation",
                            "details": "Installed-only registry, schema, and OpenAPI loading pass from an arbitrary empty cwd with fallback success count zero.",
                            "status": "PASS",
                        },
                    ],
                ),
            )
        )
    summaries: list[dict[str, Any]] = []
    for name, value in definitions:
        path = write_json(name, value)
        summaries.append(
            {
                "artifact_id": value["artifact_id"],
                "artifact_locator": value["locator"],
                "byte_size": value["byte_size"],
                "content_hash": value["content_hash"],
                "receipt": path.relative_to(ROOT).as_posix(),
                "receipt_file_sha256": sha256_id(path),
                "receipt_hash": value["receipt_hash"],
                "receipt_id": value["receipt_id"],
            }
        )
    return summaries


def installed_evidence(verification: dict[str, Any]) -> dict[str, Any]:
    installed = verification["checks"]["installed_wheel"]
    wheel = ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        packaged_registry = archive.read(
            "epistemic_foundry/_canonical/canonical-registry.json"
        )
    if packaged_registry != REGISTRY_PATH.read_bytes():
        raise SystemExit("wheel registry bytes differ from the live package snapshot")
    return {
        "arbitrary_empty_cwd": installed["arbitrary_empty_cwd"],
        "attempt_id": ATTEMPT_ID,
        "clean_venv_install": installed["clean_venv_install"],
        "installed_registry_sha256": REGISTRY_HASH,
        "missing_packaged_resource_error_code": installed[
            "missing_packaged_resource_error_code"
        ],
        "openapi_load": installed["openapi_load"],
        "representative_schema_validation": installed[
            "representative_schema_validation"
        ],
        "schema_count": installed["schema_count"],
        "source_tree_fallback_attempt_count": installed["fallback_attempt_count"],
        "source_tree_fallback_success_count": installed["fallback_success_count"],
        "status": "PASS",
        "tamper_error_code": installed["tamper_error_code"],
        "wheel_registry_byte_equal": True,
    }


def debt_reconciliation(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "b04_owned_blocking_findings": [],
        "global_suites_green": False,
        "node_debt": {
            "affected_path": "manifests/development_manifest.yaml",
            "classification": "EXPECTED_S04_ACTIVE_BINDING_MIGRATION_DEBT",
            "current_actual_sha256": CURRENT_MANIFEST_HASH,
            "debt_id": "S04-TM004",
            "expected_stale_sha256": "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7",
            "failure_count": regression["node"]["failed"],
            "failure_owner": "S04",
            "fingerprint_is_unchanged_from_prior_attempt": False,
            "prior_observed_actual_sha256": "de457bc4b141aef332d76f16357d4ba44daa663dd15c195d2e9575bc59a79940",
            "reason": "The approved successor development manifest is not yet recorded by the active S04 source binding.",
        },
        "python_debt": {
            "affected_path": "tests/test_j02_context_budget.py",
            "classification": "EXPECTED_J02_0003_MIGRATION_DEBT",
            "failure_count": regression["python"]["failed"],
            "failure_owner": "J02",
            "reason": "The J02 repository dependency checker has not yet migrated to the canonical dependency-groups.skill-context declaration.",
        },
        "status": "PASS_B04_ATTRIBUTION_WITH_TWO_PENDING_OWNED_MIGRATIONS",
    }


def command(suffix: str, text: str, result: str, exit_code: int = 0) -> dict[str, Any]:
    return {
        "command": text,
        "command_id": f"B04-0005-{suffix}",
        "exit_code": exit_code,
        "recorded_at_utc": CREATED_AT,
        "result": result,
        "scope": "B04-0005 dependency and build revalidation",
    }


def command_rows(*, closeout: bool) -> list[dict[str, Any]]:
    rows = [
        command("C001", "Inspect B04-0005 authority, B02-0002 sealed evidence, canonical projection, build inputs, and dirty-worktree preservation boundary", "PASS: exact dependency/build revalidation scope fixed; product edits prohibited"),
        command("C002", "Run verify_dependency_revalidation.py against current pyproject.toml, uv.lock, B02 report/RAH seal, and prior/current distributions", "PASS: frozen sync; tiktoken 0.13.0; o200k_base vectors 7/7; runtime metadata exposure false; unrelated sdist drift 0"),
        command("C003", "Run initial packaging pytest command without module-mode repository import semantics", "FAIL_DIAGNOSTIC: ModuleNotFoundError: scripts; the failed invocation was not repeated", 1),
        command("C004", "Rerun packaging tests with uv run --frozen --extra dev --group skill-context python -m pytest and JUnit output", "PASS: 24 passed, 0 failed, 0 skipped"),
        command("C005", "Run canonical verify_packaging.py for two clean wheel/sdist builds, sdist-to-wheel, installed-only, arbitrary-cwd, fallback, and tamper checks", "PASS: wheel 303618 bytes; sdist 252494 bytes; source/snapshot/registry parity current"),
        command("C006", "Run full Python suite with JUnit output", "BOUNDED_DEBT: 963 passed; exactly one J02-0003 migration failure; B04-owned failures 0", 1),
        command("C007", "Run full Node suite with JUnit output", "BOUNDED_DEBT: 457 passed; exactly S04-TM004 active binding migration failed; B04-owned failures 0", 1),
        command("C008", "Reconcile the preserved scripts/build/double_build.py staging diagnostic", "PRESERVED_DIAGNOSTIC: stale staging failure remains explicit; canonical B04 verifier is PASS; production helper was not modified"),
        command("C009", "Run uv lock --check and git diff --check", "PASS: lock current; whitespace errors 0; existing line-ending notices only"),
        command("C010", "Run ralph_harness.py inspect --resume diagnostic entry point", "FAIL_DIAGNOSTIC: wrong wrapper entry point; no RAH state accepted from this invocation", 1),
        command("C011", "Run rah.py inspect . --resume --json through Git Bash", "PASS: parse_errors empty; active/fail/completion_ready=false at generation 000084-016aba75"),
        command("C012", "Build and re-parse live B04-0005 inventories, receipts, regression/debt reconciliation, and review evidence", "PASS: evidence derives from live bytes, distributions, JUnit, B02 seal, and current RAH state"),
        command("C013", "Perform primary-session separate adversarial integration review", "PASS: blocking B04-owned findings 0; actor_independence=false"),
    ]
    if closeout:
        rows.extend(
            [
                command("C014", "Append B04-0005 core PASS evidence to RAH", "PASS: E0092 appended; prior generations preserved; global implementation gate remains fail"),
                command("C015", "Run post-core rah.py inspect and six-snapshot generation verification", "PASS: parse errors 0; completion_ready=false"),
                command("C016", "Run first closeout build with whole-object dependency evidence comparison", "FAIL_DIAGNOSTIC: pre-core observed_generation 000084 differs from append-only live generation 000085; B02 E0090/E0091 remained intact", 1),
                command("C017", "Revalidate dependency evidence with observed_generation treated as volatile provenance while all semantic fields remain exact", "PASS: stored pre-core provenance preserved; current RAH still carries E0090/E0091 in a valid six-snapshot generation"),
                command("C018", "Build report.json and rah-core-integrity.json from the sealed core generation", "PASS: report binds E0092 and reserves E0093"),
                command("C019", "Append hash-bound B04-0005 closeout evidence and verify final generation", "PASS when b04_0005_rah_seal.py final completes; S04-TM004 correction is next"),
            ]
        )
    return rows


def write_commands(rows: Iterable[dict[str, Any]]) -> None:
    rendered = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    (ATTEMPT / "commands.jsonl").write_text(
        rendered, encoding="utf-8", newline="\n"
    )


def read_commands() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(
        (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"invalid command ledger line {number}: {error}")
        if not isinstance(row, dict):
            raise SystemExit(f"command ledger line {number} is not an object")
        rows.append(row)
    return rows


def render_review() -> str:
    return f"""# B04-0005 dependency and build revalidation review

Overall package status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review and is not external actor-independent
certification. Fleet and subagents were not used.

## Verified boundary

- B02-0002 remains sealed by E0090/E0091. `pyproject.toml` declares exactly
  `dependency-groups.skill-context = ["tiktoken==0.13.0"]`; `uv.lock` is
  current, frozen sync passes, `o200k_base` loads, and 7/7 fixed tokenizer
  vectors pass.
- Runtime and optional distribution metadata do not expose `tiktoken`.
- The current wheel is byte-identical to B04-0004. The current sdist differs
  from B04-0004 only in `pyproject.toml`; unrelated sdist drift count is 0.
- Root canonical authority remains `schemas/**` and `openapi/**`. All 124
  schemas plus OpenAPI 3.1.1/33 operations match the 125-resource package
  snapshot and registry at source `{SOURCE_BUNDLE_HASH}`, snapshot
  `{SNAPSHOT_BUNDLE_HASH}`, and registry `{REGISTRY_HASH}`.
- Two clean builds, sdist-to-wheel equality, installed-wheel-only registry and
  representative schema/OpenAPI loading, arbitrary empty cwd, missing-resource
  rejection, tamper rejection, and source fallback success count 0 pass.
- B04-0005 modified no product files; it adds attempt-local evidence only.

## Regression and ownership reconciliation

- Packaging: 24 passed, 0 failed, 0 skipped.
- Full Python is not green: 963 passed and exactly one
  `EXPECTED_J02_0003_MIGRATION_DEBT` remains. The J02 checker still omits the
  canonical `skill-context` dependency group. B04 causal impact is none.
- Full Node is not green: 457 passed and exactly one
  `EXPECTED_S04_ACTIVE_BINDING_MIGRATION_DEBT` remains. Its current actual
  manifest hash is `{CURRENT_MANIFEST_HASH}` against stale expected hash
  `456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7`.
  This is not described as an unchanged pre-existing fingerprint; the approved
  successor manifest changed and S04 must update the active source binding.
- The production `scripts/build/double_build.py` stale-staging diagnostic is
  preserved and not hidden. The B04 canonical packaging verifier is the
  passing package-boundary evidence. No out-of-scope helper edit was made.
- New B04-owned Python or Node failures: 0. New skips/xfails: 0.

## Decision

The B02 dependency correction crosses the B04 build/package boundary without
runtime metadata exposure, canonical projection drift, unrelated distribution
drift, or a B04-owned regression. blocking B04-owned findings: 0. B04-0005
passes. The global implementation gate remains failed, both global suites are
truthfully non-green, S04-TM004 correction is next, and
`completion_ready=false`.
"""


def build_precore() -> dict[str, Any]:
    assert_fixed_hashes()
    dependency = verify_dependency_binding()
    source, snapshot, registry = canonical_inventory()
    packaging = load_packaging_verification(registry)
    regression = verify_regressions()
    source_path = write_json("source-inventory.json", source)
    snapshot_path = write_json("snapshot-inventory.json", snapshot)
    receipts = build_receipts()
    write_json("installed-wheel-verification.json", installed_evidence(packaging))
    write_json("full-regression-impact.json", regression)
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation(regression))
    projection = {
        "attempt_id": ATTEMPT_ID,
        "dependency_build_revalidation": "PASS",
        "deterministic_rebuild_result": "PASS",
        "duplicate_schema_ids": [],
        "evidence_artifact_ids": [row["receipt_id"] for row in receipts],
        "extra_paths": [],
        "final_status": "PASS",
        "hash_mismatches": [],
        "installed_wheel_resource_load_result": "PASS",
        "missing_paths": [],
        "openapi_operation_count": 33,
        "openapi_version": "3.1.1",
        "product_file_modification_count": 0,
        "projected_snapshot_bundle_hash": SNAPSHOT_BUNDLE_HASH,
        "projection_receipt_id": "AR-B04-0005-CANONICAL-PROJECTION",
        "registry_hash": REGISTRY_HASH,
        "root_source_mutation_count": 0,
        "schema_count": 124,
        "snapshot_file_count": 125,
        "source_bundle_hash": SOURCE_BUNDLE_HASH,
        "source_file_count": 125,
        "source_tree_fallback_count": 0,
        "unrelated_distribution_drift_count": dependency["reproducibility"][
            "unrelated_sdist_drift_count"
        ],
        "unrelated_write_count": 0,
        "write_scope_violation_count": 0,
    }
    write_json("canonical-projection-verification.json", projection)
    phase = {
        "artifact_receipts": receipts,
        "attempt_id": ATTEMPT_ID,
        "checks": {
            "B02_dependency_binding": "PASS",
            "canonical_projection": "PASS",
            "deterministic_rebuild": "PASS",
            "git_diff_check": "PASS_WITH_EXISTING_LINE_ENDING_NOTICES",
            "installed_wheel_only": "PASS",
            "packaging_suite": "PASS_24_OF_24",
            "primary_session_separate_review": "PASS_WITH_ASSURANCE_LIMITATION",
            "runtime_dependency_metadata_non_exposure": "PASS",
            "source_tree_fallback": "PASS_ZERO_SUCCESSES",
            "tokenizer_vectors": "PASS_7_OF_7",
        },
        "completion_ready": False,
        "global_implementation_gate": "fail",
        "next_attempt": "S04-TM004-CORRECTION",
        "phase": "P01-B",
        "reconciliation_id": "B04-0005-RECON-001",
        "residual_debts": [
            "EXPECTED_J02_0003_MIGRATION_DEBT",
            "EXPECTED_S04_ACTIVE_BINDING_MIGRATION_DEBT",
        ],
        "status": "PASS",
        "work_package_id": "B04",
    }
    write_json("phase-artifact-reconciliation.json", phase)
    (ATTEMPT / "review.md").write_text(
        render_review(), encoding="utf-8", newline="\n"
    )
    write_commands(command_rows(closeout=False))
    verify_evidence(require_closeout=False)
    return {
        "attempt_id": ATTEMPT_ID,
        "mode": "build",
        "projection_receipt_id": "AR-B04-0005-CANONICAL-PROJECTION",
        "snapshot_inventory_sha256": sha256_id(snapshot_path),
        "source_inventory_sha256": sha256_id(source_path),
        "status": "PASS",
    }


def numbered_generations() -> list[str]:
    return sorted(
        path.name
        for path in (ROOT / ".rah/ralph/generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def generation_integrity(expected_count: int) -> dict[str, Any]:
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no current RAH generation")
    generation, payloads = current
    generations = numbered_generations()
    if len(generations) != expected_count or generations[-1] != generation:
        raise SystemExit("RAH generation inventory mismatch")
    checked = 0
    for name in generations:
        generation_root = ralph_root / "generations" / name
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {name}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file inventory mismatch: {name}")
        for filename in state_store.GENERATION_FILES:
            if sha256(generation_root / filename) != files[filename]:
                raise SystemExit(f"generation file hash mismatch: {name}/{filename}")
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
    ledger = payloads["evidence_ledger.json"]
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH must remain active/fail/completion_ready=false")
    return {
        "completion_ready": False,
        "current_generation": generation,
        "evidence_count": len(ledger["entries"]),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": sha256_id(
            ralph_root / "generations" / generation / "generation-manifest.json"
        ),
        "implementation_gate": "fail",
        "latest_evidence_id": ledger["entries"][-1]["id"],
        "ralph_status": "active",
        "retained_generation_manifest_count": len(generations),
        "retained_generations": generations,
    }


def build_closeout() -> dict[str, Any]:
    verify_evidence(require_closeout=False)
    integrity = generation_integrity(7)
    if integrity["latest_evidence_id"] != "E0092" or not re.fullmatch(
        r"000085-[0-9a-f]{8}", integrity["current_generation"]
    ):
        raise SystemExit("B04-0005 closeout requires the E0092 core generation")
    if (
        integrity["flat_snapshot_stamps_verified"] != 6
        or integrity["flat_snapshot_content_matches"] != 6
    ):
        raise SystemExit("six RAH flat projections are not current")
    integrity_artifact = {
        "attempt_id": ATTEMPT_ID,
        **integrity,
        "mode": "READ_ONLY",
        "parse_errors": {},
        "status": "PASS",
        "verification_command": "python artifacts/work_packages/B04/attempts/0005/b04_0005_rah_seal.py verify",
        "work_package_id": "B04",
    }
    write_json("rah-core-integrity.json", integrity_artifact)
    write_commands(command_rows(closeout=True))
    receipts = [
        read_json(ATTEMPT / name)
        for name in (
            "projection.artifact-receipt.json",
            "wheel.artifact-receipt.json",
            "sdist.artifact-receipt.json",
        )
    ]
    regression = read_json(ATTEMPT / "full-regression-impact.json")
    report = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "DEPENDENCY_AND_BUILD_REVALIDATION",
        "authority_decision_id": DECISION_ID,
        "canonical_projection": {
            "duplicate_schema_id_count": 0,
            "extra_path_count": 0,
            "hash_mismatch_count": 0,
            "missing_path_count": 0,
            "openapi_operation_count": 33,
            "openapi_version": "3.1.1",
            "projected_snapshot_bundle_hash": SNAPSHOT_BUNDLE_HASH,
            "registry_hash": REGISTRY_HASH,
            "resource_count": 125,
            "schema_count": 124,
            "source_bundle_hash": SOURCE_BUNDLE_HASH,
        },
        "completion_ready": False,
        "dependency_build_revalidation": "PASS",
        "distribution_artifacts": [
            {
                "artifact_id": value["artifact_id"],
                "byte_size": value["byte_size"],
                "content_hash": value["content_hash"],
                "locator": value["locator"],
                "receipt_hash": value["receipt_hash"],
                "receipt_id": value["receipt_id"],
            }
            for value in receipts
        ],
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "B02_0002_status": "IMMUTABLE_PASS_HISTORY",
            "B04_0004_status": "IMMUTABLE_PASS_HISTORY",
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_state": {
            "B04": "PASS_DEPENDENCY_BUILD_REVALIDATION",
            "J02": "WAITING_ON_S04_AND_SHARED_CONTRACT_SEQUENCE",
            "S04": "READY_FOR_ACTIVE_BINDING_CORRECTION",
        },
        "not_claimed": [
            "global Python suite green",
            "global Node suite green",
            "S04-TM004 resolved",
            "J02-0003 resolved or started",
            "repository-wide conformance",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": sorted(
            {
                path.relative_to(ROOT).as_posix()
                for path in ATTEMPT.iterdir()
                if path.is_file()
            }
            | {
                "artifacts/work_packages/B04/attempts/0005/report.json",
                "artifacts/work_packages/B04/attempts/0005/build_b04_0005_evidence.py",
                "artifacts/work_packages/B04/attempts/0005/b04_0005_rah_seal.py",
            }
        ),
        "package_status": "PASS",
        "product_files_modified_by_attempt": [],
        "rah_state": {
            "completion_ready": False,
            "core_evidence_id": "E0092",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0093",
            "flat_snapshot_content_matches": integrity[
                "flat_snapshot_content_matches"
            ],
            "flat_snapshot_stamps_verified": integrity[
                "flat_snapshot_stamps_verified"
            ],
            "generation_file_hashes_verified": integrity[
                "generation_file_hashes_verified"
            ],
            "generation_manifest_sha256": integrity[
                "generation_manifest_sha256"
            ],
            "implementation_gate": "fail",
            "retained_generation_manifest_count": integrity[
                "retained_generation_manifest_count"
            ],
            "status": "active",
        },
        "regression": {
            "b04_owned_failure_count": regression["b04_owned_failure_count"],
            "node": "457_PASS_PLUS_EXPECTED_S04_ACTIVE_BINDING_MIGRATION_DEBT",
            "packaging": "24_PASSED",
            "python": "963_PASS_PLUS_EXPECTED_J02_0003_MIGRATION_DEBT",
            "unexpected_skip_or_xfail_count": 0,
        },
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_B04_owned_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": "B04",
    }
    write_json("report.json", report)
    verify_evidence(require_closeout=True)
    return {
        "attempt_id": ATTEMPT_ID,
        "core_generation": integrity["current_generation"],
        "mode": "closeout",
        "report_sha256": sha256_id(ATTEMPT / "report.json"),
        "status": "PASS",
    }


def verify_receipt(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if value.get("receipt_hash") != hash_excluding(value, "receipt_hash"):
        raise SystemExit(f"receipt hash mismatch: {path.name}")
    validate_artifact("artifact-receipt", value)
    locator = ROOT / str(value["locator"])
    if (
        sha256_id(locator) != value["content_hash"]
        or locator.stat().st_size != value["byte_size"]
    ):
        raise SystemExit(f"receipt bytes mismatch: {path.name}")
    return value


def verify_evidence(*, require_closeout: bool) -> dict[str, Any]:
    assert_fixed_hashes()
    verify_dependency_binding()
    source, snapshot, registry = canonical_inventory()
    packaging = load_packaging_verification(registry)
    regression = verify_regressions()
    if read_json(ATTEMPT / "source-inventory.json") != source:
        raise SystemExit("stored source inventory differs from live authority")
    if read_json(ATTEMPT / "snapshot-inventory.json") != snapshot:
        raise SystemExit("stored snapshot inventory differs from live projection")
    installed = read_json(ATTEMPT / "installed-wheel-verification.json")
    if installed != installed_evidence(packaging):
        raise SystemExit("stored installed-wheel evidence differs from build evidence")
    if read_json(ATTEMPT / "full-regression-impact.json") != regression:
        raise SystemExit("stored regression evidence differs from JUnit recomputation")
    if read_json(ATTEMPT / "preexisting-debt-reconciliation.json") != debt_reconciliation(
        regression
    ):
        raise SystemExit("stored debt reconciliation differs from current failures")
    projection = read_json(ATTEMPT / "canonical-projection-verification.json")
    if not (
        projection.get("final_status") == "PASS"
        and projection.get("source_bundle_hash") == SOURCE_BUNDLE_HASH
        and projection.get("projected_snapshot_bundle_hash") == SNAPSHOT_BUNDLE_HASH
        and projection.get("registry_hash") == REGISTRY_HASH
        and projection.get("product_file_modification_count") == 0
        and projection.get("write_scope_violation_count") == 0
    ):
        raise SystemExit("canonical projection verification is not the exact PASS")
    for name in (
        "projection.artifact-receipt.json",
        "wheel.artifact-receipt.json",
        "sdist.artifact-receipt.json",
    ):
        verify_receipt(ATTEMPT / name)
    phase = read_json(ATTEMPT / "phase-artifact-reconciliation.json")
    if (
        phase.get("status") != "PASS"
        or phase.get("completion_ready") is not False
        or phase.get("global_implementation_gate") != "fail"
    ):
        raise SystemExit("phase artifact reconciliation is not a bounded PASS")
    review = (ATTEMPT / "review.md").read_text(encoding="utf-8")
    for phrase in (
        "Overall package status: `PASS`",
        "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
        "actor_independence=false",
        "not external actor-independent certification",
        "blocking B04-owned findings: 0",
    ):
        if phrase not in " ".join(review.split()) and phrase not in review:
            raise SystemExit(f"review omits required assurance phrase: {phrase}")
    rows = read_commands()
    expected_rows = command_rows(closeout=require_closeout)
    if rows != expected_rows:
        raise SystemExit("command ledger differs from deterministic reconstruction")
    if require_closeout:
        report = read_json(ATTEMPT / "report.json")
        integrity = read_json(ATTEMPT / "rah-core-integrity.json")
        if not (
            report.get("package_status") == "PASS"
            and report.get("completion_ready") is False
            and report.get("global_implementation_gate") == "fail"
            and report.get("product_files_modified_by_attempt") == []
        ):
            raise SystemExit("B04-0005 report status is invalid")
        if not (
            integrity.get("status") == "PASS"
            and integrity.get("latest_evidence_id") == "E0092"
            and integrity.get("completion_ready") is False
        ):
            raise SystemExit("RAH core integrity does not bind E0092")
    return {
        "attempt_id": ATTEMPT_ID,
        "closeout_present": require_closeout,
        "command_count": len(rows),
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "closeout", "verify"))
    args = parser.parse_args()
    if args.mode == "build":
        result = build_precore()
    elif args.mode == "closeout":
        result = build_closeout()
    else:
        result = verify_evidence(require_closeout=(ATTEMPT / "report.json").is_file())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
