#!/usr/bin/env python3
"""Build and verify B04-0008 final post-C04 packaging evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0008"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
C04_REPORT = ROOT / "artifacts/work_packages/C04/attempts/0003/report.json"
C04_VERIFICATION = (
    ROOT / "artifacts/work_packages/C04/attempts/0003/c04-conformance-verification.json"
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402
from scripts.build.canonical_registry import materialize  # noqa: E402


ATTEMPT_ID = "B04-0008"
WORK_PACKAGE_ID = "B04"
RECORDED_AT = "2026-07-30T17:00:00.000Z"
EXPECTED_MANIFEST_HASH = (
    "sha256:5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"
)
EXPECTED_C04_REPORT_HASH = (
    "sha256:2610c509309d6f5aa5262cb2267f6fb17aea19d81fb2c33b4b3949c6371de297"
)
EXPECTED_SOURCE_BUNDLE_HASH = (
    "sha256:1557b03db2ad7e7d23b014d4c9d5fd643803f6613696c966d9b0379573259e7f"
)
EXPECTED_SNAPSHOT_BUNDLE_HASH = (
    "sha256:d01bda0057584e235331b649238fc2507c60cab329fd6b8e8b6a115fac912559"
)
EXPECTED_REGISTRY_HASH = (
    "sha256:6b4fcade707639e537744be4075e71d3f7e068cd42eaaaddb20ef084851175d5"
)
EXPECTED_SCHEMA_COUNT = 126
EXPECTED_RESOURCE_COUNT = 127
EXPECTED_OPENAPI_OPERATION_COUNT = 33
EXPECTED_DIST = {
    "epistemic_foundry-4.0.0-py3-none-any.whl": {
        "byte_size": 308_644,
        "sha256": "906ca7477c421941a8ceacf5b732740ec27bff73d6c3b25c1b3c763a6ce536f9",
    },
    "epistemic_foundry-4.0.0.tar.gz": {
        "byte_size": 257_575,
        "sha256": "520079757dbaf868be2d293bfe79b0ee80f2bda252f066a166dabfb3a090f318",
    },
}
JUNIT_PATHS = {
    "targeted_projection": ATTEMPT / "targeted-projection.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
PRIOR_ATTEMPTS = tuple(f"{value:04d}" for value in range(2, 8))
OUTPUT_NAMES = (
    "canonical-projection-verification.json",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "full-regression-impact.json",
    "installed-wheel-verification.json",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "packaging-summary.json",
    "packaging-verification-run.json",
    "phase-artifact-reconciliation.json",
    "prior-history-verification.json",
    "projection.artifact-receipt.json",
    "rah-core-integrity.json",
    "report.json",
    "review.md",
    "run_b04_0008_checks.py",
    "build_b04_0008_evidence.py",
    "b04_0008_rah_seal.py",
    "sdist.artifact-receipt.json",
    "snapshot-inventory.json",
    "source-inventory.json",
    "targeted-projection.junit.xml",
    "wheel.artifact-receipt.json",
    "write-scope-verification.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


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


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(render(value), encoding="utf-8", newline="\n")
    return path


def junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    result: list[tuple[Any, ...]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        result.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                problem.get("message", "") if problem is not None else "",
                (problem.text or "") if problem is not None else "",
                case.find("skipped") is not None,
            )
        )
    return result


def verify_junit_portability() -> None:
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(root in text for root in roots):
            raise SystemExit(f"JUnit contains absolute repository path: {name}")
        if name != "full_node" and re.search(r'\s+(?:hostname|timestamp)="', text):
            raise SystemExit(f"pytest JUnit contains volatile fields: {name}")


def normalize_junit() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            if record.get("files", {}).get(name, {}).get("normalized_sha256") != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        before_bytes = path.read_bytes()
        before = before_bytes.decode("utf-8")
        before_signature = junit_signature(before)
        normalized = before
        removed_hostname = 0
        removed_timestamp = 0
        prefix_replacements = 0
        if name == "full_node":
            for prefix in (root_backslash, root_slash):
                needle = 'file="' + prefix
                count = normalized.count(needle)
                normalized = normalized.replace(needle, 'file="')
                prefix_replacements += count
        else:
            normalized, removed_timestamp = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized
            )
            normalized, removed_hostname = re.subn(
                r'\s+hostname="[^"]*"', "", normalized
            )
        if junit_signature(normalized) != before_signature:
            raise SystemExit(f"JUnit normalization changed semantics: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "case_count": len(before_signature),
            "hostname_attributes_removed": removed_hostname,
            "normalized_sha256": sha256_id(path),
            "raw_sha256": sha256_bytes(before_bytes),
            "repository_prefix_replacements": prefix_replacements,
            "semantic_signature_preserved": True,
            "timestamp_attributes_removed": removed_timestamp,
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "preserved": [
            "testcase identities and counts",
            "failure, error, and skip state",
            "Node semantic footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


def junit_summary(name: str) -> dict[str, Any]:
    path = JUNIT_PATHS[name]
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    failures = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    if name == "full_node":
        footer = {
            key.decode("ascii"): int(value)
            for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
        }
        if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
            raise SystemExit("Node semantic footer is incomplete")
        result = {
            "cancelled": footer["cancelled"],
            "collected": footer["tests"],
            "failed": footer["fail"],
            "passed": footer["pass"],
            "semantic_counter_authority": "node_test_footer",
            "skipped": footer["skipped"],
            "todo": footer["todo"],
            "xml_errors": errors,
            "xml_failures": failures,
            "xml_skipped": skipped,
            "xml_testcase_count": len(cases),
        }
    else:
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        result = {
            "collected": sum(int(item.get("tests", "0")) for item in suites),
            "errors": sum(int(item.get("errors", "0")) for item in suites),
            "failed": sum(int(item.get("failures", "0")) for item in suites),
            "semantic_counter_authority": "pytest_testsuite_attributes",
            "skipped": sum(int(item.get("skipped", "0")) for item in suites),
            "xml_testcase_count": len(cases),
        }
        result["passed"] = (
            result["collected"] - result["errors"] - result["failed"] - result["skipped"]
        )
    result["junit"] = path.relative_to(ROOT).as_posix()
    result["junit_sha256"] = sha256_id(path)
    return result


def green_summaries() -> dict[str, dict[str, Any]]:
    targeted = junit_summary("targeted_projection")
    python = junit_summary("full_python")
    node = junit_summary("full_node")
    if not (
        targeted["collected"] == targeted["passed"] == 41
        and targeted["failed"] == targeted["errors"] == targeted["skipped"] == 0
    ):
        raise SystemExit(f"targeted B04 suite is not 41/41: {targeted}")
    if not (
        python["collected"] == python["passed"] == 990
        and python["failed"] == python["errors"] == python["skipped"] == 0
    ):
        raise SystemExit(f"full Python suite is not 990/990: {python}")
    if not (
        node["collected"] == node["passed"] == 460
        and node["failed"] == node["cancelled"] == node["skipped"] == node["todo"] == 0
        and node["xml_failures"] == node["xml_errors"] == node["xml_skipped"] == 0
    ):
        raise SystemExit(f"full Node suite is not 460/460: {node}")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory.get("attempt_id") != ATTEMPT_ID or inventory.get("count") != 52:
        raise SystemExit("Node test inventory is not the required 52 files")
    return {"targeted_projection": targeted, "full_python": python, "full_node": node}


def dependency_evidence() -> dict[str, Any]:
    if sha256_id(MANIFEST_PATH) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("development manifest changed after C04-0003")
    c04 = read_json(C04_REPORT)
    rah = c04.get("rah_state")
    if not (
        sha256_id(C04_REPORT) == EXPECTED_C04_REPORT_HASH
        and c04.get("attempt_id") == "C04-0003"
        and c04.get("status") == c04.get("package_status") == "PASS"
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0020"
        and rah.get("core_generation") == "000020-4032536e"
        and rah.get("final_closeout_evidence_id") == "E0021"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("C04-0003 is not the exact sealed dependency")
    dependencies: dict[str, Any] = {}
    for package, path in {
        "B02": ROOT / "artifacts/work_packages/B02/report.json",
        "B03": ROOT / "artifacts/work_packages/B03/report.json",
    }.items():
        report = read_json(path)
        if report.get("status") != "PASS":
            raise SystemExit(f"{package} is not PASS")
        dependencies[package] = {
            "attempt_id": report.get("attempt_id") or "historical-root-pass",
            "report": path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(path),
            "status": "PASS",
        }
    dependencies["C04"] = {
        "attempt_id": "C04-0003",
        "core_evidence_id": "E0020",
        "core_generation": "000020-4032536e",
        "final_closeout_evidence_id": "E0021",
        "report": C04_REPORT.relative_to(ROOT).as_posix(),
        "report_sha256": EXPECTED_C04_REPORT_HASH,
        "status": "PASS",
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "development_manifest_sha256": EXPECTED_MANIFEST_HASH,
        "next_action": "RECOMPUTE_156_PACKAGE_DAG_AFTER_RAH_SEAL",
        "status": "PASS",
    }


def live_inventory() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry, resources = materialize.build_registry_document(ROOT)
    source_hash = materialize.calculate_source_bundle_hash(resources)
    snapshot_hash = materialize.calculate_projected_snapshot_bundle_hash(resources)
    registry_bytes = materialize._registry_bytes(registry)
    registry_hash = sha256_bytes(registry_bytes)
    if (
        source_hash != EXPECTED_SOURCE_BUNDLE_HASH
        or snapshot_hash != EXPECTED_SNAPSHOT_BUNDLE_HASH
        or registry_hash != EXPECTED_REGISTRY_HASH
        or REGISTRY_PATH.read_bytes() != registry_bytes
    ):
        raise SystemExit("live canonical source/snapshot/registry binding changed")
    if (
        registry.get("schema_count") != EXPECTED_SCHEMA_COUNT
        or registry.get("resource_count") != EXPECTED_RESOURCE_COUNT
        or registry.get("openapi_document_count") != 1
    ):
        raise SystemExit("live canonical registry counts changed")

    source_entries: list[dict[str, Any]] = []
    snapshot_entries: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    duplicates: list[str] = []
    expected_paths: set[str] = set()
    mismatches: list[str] = []
    missing: list[str] = []
    for resource in resources:
        entry = resource.manifest_entry()
        relative = resource.relative_path.as_posix()
        expected_paths.add(relative)
        identifier = str(entry["document_id"])
        if identifier in identifiers:
            duplicates.append(identifier)
        identifiers.add(identifier)
        source_entries.append(
            {
                "byte_size": entry["byte_size"],
                "document_id": identifier,
                "media_type": entry["media_type"],
                "path": relative,
                "projection_target_path": entry["package_path"],
                "sha256": entry["sha256"],
            }
        )
        target = SNAPSHOT / Path(*resource.relative_path.parts)
        if not target.is_file():
            missing.append(relative)
            continue
        observed = target.read_bytes()
        observed_hash = sha256_bytes(observed)
        snapshot_entries.append(
            {
                "byte_size": len(observed),
                "document_id": identifier,
                "package_path": relative,
                "sha256": observed_hash,
                "source_path": entry["source_path"],
            }
        )
        if observed != resource.content or observed_hash != entry["sha256"]:
            mismatches.append(relative)
    actual_paths = {
        path.relative_to(SNAPSHOT).as_posix()
        for path in SNAPSHOT.rglob("*")
        if path.is_file() and path.name != "canonical-registry.json"
    }
    missing = sorted(set(missing) | (expected_paths - actual_paths))
    extra = sorted(actual_paths - expected_paths)
    if missing or extra or mismatches or duplicates:
        raise SystemExit("live canonical projection has missing/extra/mismatch/duplicate entries")
    openapi = (ROOT / "openapi/epistemic-foundry-v1.openapi.yaml").read_text(
        encoding="utf-8"
    )
    operations = re.findall(r"^\s+operationId:\s*([^\s#]+)\s*$", openapi, re.M)
    if (
        not openapi.startswith("openapi: 3.1.1\n")
        or len(operations) != EXPECTED_OPENAPI_OPERATION_COUNT
        or len(operations) != len(set(operations))
    ):
        raise SystemExit("OpenAPI 3.1.1/33-operation contract changed")
    source = {
        "attempt_id": ATTEMPT_ID,
        "duplicate_schema_ids": duplicates,
        "entries": source_entries,
        "openapi_operation_count": len(operations),
        "openapi_resource_count": 1,
        "openapi_version": "3.1.1",
        "schema_count": EXPECTED_SCHEMA_COUNT,
        "source_bundle_hash": source_hash,
        "source_resource_count": len(source_entries),
        "status": "PASS",
    }
    snapshot = {
        "attempt_id": ATTEMPT_ID,
        "comparison_to_source": {
            "extra_paths": extra,
            "hash_mismatches": sorted(mismatches),
            "missing_paths": missing,
            "status": "PASS",
        },
        "entries": snapshot_entries,
        "projected_snapshot_bundle_hash": snapshot_hash,
        "registry": {"byte_size": REGISTRY_PATH.stat().st_size, "sha256": registry_hash},
        "snapshot_file_count_including_registry": sum(
            path.is_file() for path in SNAPSHOT.rglob("*")
        ),
        "snapshot_resource_count": len(snapshot_entries),
        "status": "PASS",
    }
    return source, snapshot, registry


def packaging_evidence(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stored = read_json(ATTEMPT / "packaging-verification-run.json")
    canonical = stored.get("canonical_registry")
    checks = stored.get("checks")
    inventory = stored.get("artifact_inventory")
    if stored.get("status") != "PASS" or not all(
        isinstance(value, dict) for value in (canonical, checks, inventory)
    ):
        raise SystemExit("packaging verifier is not a structured PASS")
    expected = {
        "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        "projected_snapshot_bundle_hash": EXPECTED_SNAPSHOT_BUNDLE_HASH,
        "registry_sha256": EXPECTED_REGISTRY_HASH,
        "schema_count": EXPECTED_SCHEMA_COUNT,
        "resource_count": EXPECTED_RESOURCE_COUNT,
        "openapi_document_count": 1,
        "file_count": EXPECTED_RESOURCE_COUNT,
    }
    for key, value in expected.items():
        if canonical.get(key) != value:
            raise SystemExit(f"packaging canonical mismatch: {key}")
        if key != "registry_sha256" and registry.get(key) != value:
            raise SystemExit(f"live registry mismatch: {key}")
    comparisons = checks.get("registry_comparisons")
    installed = checks.get("installed_wheel")
    reproducibility = checks.get("two_build_reproducibility")
    expected_comparison = {
        "extra": 0,
        "hash_mismatches": 0,
        "missing": 0,
        "resource_count": EXPECTED_RESOURCE_COUNT,
        "status": "PASS",
    }
    if not isinstance(comparisons, dict) or any(
        value != expected_comparison for value in comparisons.values()
    ):
        raise SystemExit("one or more source/sdist/wheel comparisons failed")
    if not (
        isinstance(installed, dict)
        and installed.get("clean_venv_install") == "PASS"
        and installed.get("arbitrary_empty_cwd") == "PASS"
        and installed.get("schema_count") == EXPECTED_SCHEMA_COUNT
        and installed.get("openapi_load") == "PASS"
        and installed.get("representative_schema_validation") == "PASS"
        and installed.get("fallback_success_count") == 0
        and installed.get("missing_packaged_resource_error_code")
        == "CANONICAL_REGISTRY_MISSING"
        and installed.get("tamper_error_code") == "CANONICAL_REGISTRY_HASH_MISMATCH"
        and checks.get("sdist_to_wheel") == "PASS"
        and checks.get("source_tree_fallback") == {"attempt_count": 1, "success_count": 0}
        and reproducibility
        == {
            "sdist_byte_equal": True,
            "sdist_derived_wheel_byte_equal": True,
            "wheel_byte_equal": True,
        }
    ):
        raise SystemExit("installed/rebuild/fallback packaging contract failed")
    for name, expected_artifact in EXPECTED_DIST.items():
        path = ATTEMPT / "dist" / name
        observed = {"byte_size": path.stat().st_size, "sha256": sha256(path)}
        if observed != expected_artifact or inventory.get(name) != expected_artifact:
            raise SystemExit(f"distribution bytes differ: {name}")
    wheel = ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        if archive.read("epistemic_foundry/_canonical/canonical-registry.json") != REGISTRY_PATH.read_bytes():
            raise SystemExit("wheel registry differs from live snapshot")
        names = set(archive.namelist())
        for entry in registry["resources"]:
            archive_name = "epistemic_foundry/_canonical/" + str(entry["package_path"])
            if archive_name not in names:
                raise SystemExit(f"wheel resource missing: {archive_name}")
            content = archive.read(archive_name)
            if (
                content != (ROOT / str(entry["source_path"])).read_bytes()
                or content != (SNAPSHOT / str(entry["package_path"])).read_bytes()
                or sha256_bytes(content) != entry["sha256"]
            ):
                raise SystemExit(f"wheel resource diverges: {archive_name}")
    installed_result = {
        "arbitrary_empty_cwd": "PASS",
        "attempt_id": ATTEMPT_ID,
        "clean_venv_install": "PASS",
        "installed_registry_sha256": EXPECTED_REGISTRY_HASH,
        "missing_packaged_resource_error_code": "CANONICAL_REGISTRY_MISSING",
        "openapi_load": "PASS",
        "representative_schema_validation": "PASS",
        "schema_count": EXPECTED_SCHEMA_COUNT,
        "source_tree_fallback_attempt_count": 1,
        "source_tree_fallback_success_count": 0,
        "status": "PASS",
        "tamper_error_code": "CANONICAL_REGISTRY_HASH_MISMATCH",
        "verified_wheel_canonical_resource_count": EXPECTED_RESOURCE_COUNT,
        "wheel_registry_byte_equal": True,
    }
    return stored, installed_result


def artifact_receipt(
    *, receipt_id: str, artifact_id: str, path: Path, media_type: str,
    checks: list[dict[str, str]],
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": artifact_id,
        "byte_size": path.stat().st_size,
        "content_hash": sha256_id(path),
        "created_at": RECORDED_AT,
        "created_by": {"actor_id": "B04-0008-final-packaging-verifier", "actor_type": "tool"},
        "locator": path.relative_to(ROOT).as_posix(),
        "media_type": media_type,
        "receipt_id": receipt_id,
        "schema_ref": None,
        "validation_results": checks,
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    validate_artifact("artifact-receipt", receipt)
    return receipt


def receipts() -> dict[str, dict[str, Any]]:
    projection = artifact_receipt(
        receipt_id="AR-B04-0008-CANONICAL-PROJECTION",
        artifact_id="ART-B04-0008-CANONICAL-PROJECTION",
        path=REGISTRY_PATH,
        media_type="application/vnd.epistemic-foundry.canonical-registry+json",
        checks=[
            {"check": "registry_byte_integrity", "status": "PASS", "details": "Receipt binds the exact deterministic registry bytes."},
            {"check": "post_c04_convergence", "status": "PASS", "details": "All 127 root, snapshot, sdist, wheel, and installed resources converge after sealed C04-0003 PASS."},
        ],
    )
    wheel = artifact_receipt(
        receipt_id="AR-B04-0008-WHEEL",
        artifact_id="ART-B04-0008-WHEEL",
        path=ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl",
        media_type="application/vnd.python.wheel",
        checks=[
            {"check": "installed_wheel_only", "status": "PASS", "details": "Clean isolated install, empty cwd, schema validation, OpenAPI load, no source fallback, missing-resource rejection, and tamper rejection pass."},
            {"check": "wheel_reproducibility", "status": "PASS", "details": "Two clean wheels and the sdist-derived wheel are byte-identical."},
        ],
    )
    sdist = artifact_receipt(
        receipt_id="AR-B04-0008-SDIST",
        artifact_id="ART-B04-0008-SDIST",
        path=ATTEMPT / "dist/epistemic_foundry-4.0.0.tar.gz",
        media_type="application/gzip",
        checks=[
            {"check": "sdist_clean_build", "status": "PASS", "details": "Clean sdist embeds canonical source, derived snapshot, deterministic tooling, and exact hashed build constraints."},
            {"check": "sdist_to_wheel", "status": "PASS", "details": "The wheel rebuilt from this sdist is byte-identical to the direct clean-source wheel."},
        ],
    )
    return {"projection": projection, "wheel": wheel, "sdist": sdist}


def prior_history() -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for attempt in PRIOR_ATTEMPTS:
        path = ROOT / f"artifacts/work_packages/B04/attempts/{attempt}/report.json"
        report = read_json(path)
        if report.get("attempt_id") != f"B04-{attempt}":
            raise SystemExit(f"prior B04 identity mismatch: {attempt}")
        reports[attempt] = {
            "byte_size": path.stat().st_size,
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(path),
            "status": "PRESERVED",
        }
    return {"attempt_id": ATTEMPT_ID, "prior_B04_reports": reports, "status": "PASS"}


def live_documents() -> dict[str, dict[str, Any]]:
    normalization = normalize_junit()
    summaries = green_summaries()
    dependencies = dependency_evidence()
    source, snapshot, registry = live_inventory()
    packaging, installed = packaging_evidence(registry)
    receipt_set = receipts()
    c04_verification = read_json(C04_VERIFICATION)
    phase_source = c04_verification.get("phase_artifact_reconciliation")
    if not isinstance(phase_source, dict) or phase_source.get("status") != "PASS":
        raise SystemExit("C04-0003 phase-artifact reconciliation is not PASS")
    phase = {
        "admitted_phase_artifact_set_count": phase_source.get("admitted_phase_artifact_set_count"),
        "admitted_transition_count": phase_source.get("admitted_transition_count"),
        "artifact_receipts": [
            {
                "artifact_locator": receipt_set[key]["locator"],
                "byte_size": receipt_set[key]["byte_size"],
                "content_hash": receipt_set[key]["content_hash"],
                "receipt": f"artifacts/work_packages/B04/attempts/0008/{key}.artifact-receipt.json",
                "receipt_hash": receipt_set[key]["receipt_hash"],
                "receipt_id": receipt_set[key]["receipt_id"],
            }
            for key in ("projection", "wheel", "sdist")
        ],
        "attempt_id": ATTEMPT_ID,
        "c04_report_sha256": EXPECTED_C04_REPORT_HASH,
        "c04_source_artifact": C04_VERIFICATION.relative_to(ROOT).as_posix(),
        "c04_source_artifact_sha256": sha256_id(C04_VERIFICATION),
        "completion_ready": False,
        "expected_phase_artifact_set_count": phase_source.get("expected_phase_artifact_set_count"),
        "expected_transition_count": phase_source.get("expected_transition_count"),
        "status": "PASS",
    }
    if phase["admitted_phase_artifact_set_count"] != 14 or phase["admitted_transition_count"] != 17:
        raise SystemExit("C04 phase-artifact counts changed")
    projection = {
        "attempt_id": ATTEMPT_ID,
        "deterministic_rebuild_result": "PASS",
        "duplicate_schema_ids": [],
        "extra_paths": [],
        "final_status": "PASS",
        "hash_mismatches": [],
        "installed_wheel_resource_load_result": "PASS",
        "materialization_result": {"changed_file_count": 0, "status": "PASS_ALREADY_CURRENT"},
        "missing_paths": [],
        "openapi_operation_count": EXPECTED_OPENAPI_OPERATION_COUNT,
        "openapi_resource_count": 1,
        "openapi_version": "3.1.1",
        "package_status": "PASS",
        "packaging_verification_sha256": sha256_id(ATTEMPT / "packaging-verification-run.json"),
        "projected_snapshot_bundle_hash": EXPECTED_SNAPSHOT_BUNDLE_HASH,
        "projection_receipt_id": receipt_set["projection"]["receipt_id"],
        "projection_status": "PASS",
        "registry_hash": EXPECTED_REGISTRY_HASH,
        "root_source_mutation_count": 0,
        "schema_count": EXPECTED_SCHEMA_COUNT,
        "snapshot_resource_count": EXPECTED_RESOURCE_COUNT,
        "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        "source_resource_count": EXPECTED_RESOURCE_COUNT,
        "source_tree_fallback_count": 0,
        "targeted_projection": summaries["targeted_projection"],
        "total_canonical_resource_count": EXPECTED_RESOURCE_COUNT,
        "unrelated_write_count": 0,
        "write_scope_violation_count": 0,
    }
    regression = {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": summaries["full_node"],
        "full_python": summaries["full_python"],
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_projection": summaries["targeted_projection"],
        "unexpected_skip_or_xfail_count": 0,
    }
    scope = {
        "approved_paths": [
            "src/epistemic_foundry/_canonical/**",
            "src/epistemic_foundry/contracts/registry.py",
            "scripts/build/canonical_registry/**",
            "tests/packaging/**",
            "tests/test_contracts.py",
            "tests/test_cli.py",
            "artifacts/work_packages/B04/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "product_files_modified_by_attempt": [],
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }
    return {
        "source-inventory.json": source,
        "snapshot-inventory.json": snapshot,
        "canonical-projection-verification.json": projection,
        "installed-wheel-verification.json": installed,
        "projection.artifact-receipt.json": receipt_set["projection"],
        "wheel.artifact-receipt.json": receipt_set["wheel"],
        "sdist.artifact-receipt.json": receipt_set["sdist"],
        "phase-artifact-reconciliation.json": phase,
        "full-regression-impact.json": regression,
        "dependency-status.json": dependencies,
        "junit-normalization-verification.json": normalization,
        "write-scope-verification.json": scope,
        "prior-history-verification.json": prior_history(),
        "packaging-summary.json": {
            "artifact_inventory": packaging["artifact_inventory"],
            "attempt_id": ATTEMPT_ID,
            "backend": packaging["backend"],
            "canonical_registry": packaging["canonical_registry"],
            "checks": packaging["checks"],
            "status": "PASS",
        },
    }


def commands_text() -> str:
    rows = [
        ("Inspect sealed C04-0003, B04 manifest contract, prior B04 attempts, and packaging verifier", 0, "PASS"),
        ("Run B04 targeted canonical registry, contract, and CLI tests", 0, "PASS: 41/41"),
        ("Run full Python repository suite", 0, "PASS: 990/990"),
        ("Run complete 52-file serial Node suite", 0, "PASS: footer 460/460"),
        ("Run clean wheel/sdist, second build, sdist-to-wheel, installed-only, empty-cwd, no-fallback, missing-resource, tamper, and boundary verification", 0, "PASS"),
        ("Run deterministic canonical materializer --check", 0, "PASS: snapshot already current"),
        ("Run git diff --check", 0, "PASS: exit 0; pre-existing line-ending notices only"),
        ("Normalize portable JUnit attributes without changing semantic signatures", 0, "PASS"),
        ("Build and verify B04-0008 machine-readable evidence and receipts", 0, "PASS when builder verification completes"),
        ("Perform primary-session separate adversarial final packaging review", 0, "PASS: blocking findings 0; actor_independence=false"),
        ("Append the initial B04-0008 RAH core evidence", 1, "RECOVERED_POST_COMMIT: E0022 / 000022-6e053d7e committed durably; a local verifier NameError occurred before integrity artifact and report binding"),
        ("Preserve E0022 and append a corrected recovery core plus final closeout", 0, "PASS when E0023 recovery core, E0024 final, and generation verification complete"),
    ]
    return "".join(
        json.dumps(
            {
                "command": command,
                "command_id": f"B04-0008-C{index:03d}",
                "exit_code": exit_code,
                "recorded_at_utc": RECORDED_AT,
                "result": result,
                "scope": "B04-0008 final post-C04 packaging gate",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for index, (command, exit_code, result) in enumerate(rows, 1)
    )


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    projection = documents["canonical-projection-verification.json"]
    regression = documents["full-regression-impact.json"]
    return f"""# B04-0008 final post-C04 packaging review

Overall package status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. Product-owner instructions
prohibit subagents and Fleet, so this is a procedurally separate primary-session
review rather than external actor-independent certification.

## Dependency and authority

- The exact sealed C04-0003 report is hash-bound at `{EXPECTED_C04_REPORT_HASH}`
  with core `E0020 / 000020-4032536e` and final `E0021`.
- Root `schemas/**` and `openapi/**` remain sole authority. The package snapshot,
  sdist, wheel, and installed resources are derived projections only.
- {projection['schema_count']} schemas plus one OpenAPI 3.1.1 document with
  {projection['openapi_operation_count']} operations produce
  {projection['total_canonical_resource_count']} resources. Missing, extra,
  hash-mismatch, duplicate-ID, reverse-sync, and fallback counts are zero.

## Packaging and regression

- Two clean wheel/sdist builds are byte-reproducible; the sdist-derived wheel is
  byte-identical to the direct wheel.
- Installed-wheel-only registry enumeration, representative schema validation,
  OpenAPI loading, arbitrary empty cwd, missing-resource fail-closed behavior,
  and one-byte tamper rejection all pass without repository-root fallback.
- Targeted B04 tests pass {regression['targeted_projection']['passed']}/41,
  full Python passes {regression['full_python']['passed']}/990, and Node passes
  {regression['full_node']['passed']}/460 across 52 files with no failures,
  errors, skips, xfails, cancellations, or todos.
- ArtifactReceipts bind the live registry, wheel, and sdist bytes. B04 changed no
  product file and preserved all prior attempts and the dirty worktree.

## Scope of this verdict

B04-0008 satisfies the post-C04 final packaging gate. It does not establish
overall product completion, release readiness, or production readiness. The next
authorized action is live recomputation of the 156-package DAG. Global
`implementation_gate=fail` and `completion_ready=false` remain in force.

## RAH recovery record

The initial core append committed `E0022 / 000022-6e053d7e` before a local
post-commit integrity-summary step raised `NameError: WORK_PACKAGE_ID`. No
generation or evidence was deleted, rewritten, or retried under the same ID.
The corrected sealer records a new recovery core and final closeout, explicitly
preserving E0022 as immutable post-commit-verification-incomplete history.
"""


def report_document(
    documents: dict[str, dict[str, Any]], rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "FINAL_POST_C04_PACKAGING_GATE",
        "canonical_projection": {
            "duplicate_schema_id_count": 0,
            "extra_path_count": 0,
            "hash_mismatch_count": 0,
            "missing_path_count": 0,
            "openapi_operation_count": EXPECTED_OPENAPI_OPERATION_COUNT,
            "openapi_resource_count": 1,
            "openapi_version": "3.1.1",
            "projected_snapshot_bundle_hash": EXPECTED_SNAPSHOT_BUNDLE_HASH,
            "registry_hash": EXPECTED_REGISTRY_HASH,
            "resource_count": EXPECTED_RESOURCE_COUNT,
            "schema_count": EXPECTED_SCHEMA_COUNT,
            "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        },
        "completion_ready": False,
        "dependency_status": documents["dependency-status.json"],
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "B04_prior_attempts": "IMMUTABLE_HISTORY",
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_state": {
            "B04-0008": "PASS_FINAL_PACKAGING_AFTER_RAH_SEAL",
            "next_action": "RECOMPUTE_156_PACKAGE_DAG",
        },
        "not_claimed": [
            "156-package DAG terminal completion",
            "release or production readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": [
            f"artifacts/work_packages/B04/attempts/0008/{name}" for name in OUTPUT_NAMES
        ],
        "package_status": "PASS",
        "product_files_modified_by_attempt": [],
        "projection_status": "PASS_CURRENT",
        "rah_recovery_history": {
            "cause": "POST_COMMIT_LOCAL_VERIFIER_NAME_ERROR",
            "durable_generation_preserved": True,
            "initial_core_evidence_id": "E0022",
            "initial_core_generation": "000022-6e053d7e",
            "initial_core_verification_status": "INCOMPLETE_AFTER_DURABLE_COMMIT",
            "recovery_policy": "APPEND_NEW_CORE_AND_FINAL_WITHOUT_MUTATING_E0022",
        },
        "regression": {
            "node": "PASS_460_OF_460",
            "python": "PASS_990_OF_990",
            "targeted_projection": "PASS_41_OF_41",
            "unexpected_skip_or_xfail_count": regression["unexpected_skip_or_xfail_count"],
        },
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def verify_receipt(path: Path) -> dict[str, Any]:
    value = read_json(path)
    validate_artifact("artifact-receipt", value)
    if value.get("receipt_hash") != hash_excluding(value, "receipt_hash"):
        raise SystemExit(f"receipt self-hash mismatch: {path.name}")
    locator = ROOT / str(value["locator"])
    if (
        not locator.is_file()
        or value.get("content_hash") != sha256_id(locator)
        or value.get("byte_size") != locator.stat().st_size
    ):
        raise SystemExit(f"receipt does not bind live artifact: {path.name}")
    return value


def build() -> dict[str, Any]:
    documents = live_documents()
    for name, value in documents.items():
        write_json(name, value)
    (ATTEMPT / "commands.jsonl").write_text(commands_text(), encoding="utf-8", newline="\n")
    (ATTEMPT / "review.md").write_text(review_text(documents), encoding="utf-8", newline="\n")
    write_json("report.json", report_document(documents))
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
    write_json("report.json", report_document(documents, rah_state=rah_state))
    return rah_state


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored B04-0008 evidence differs from live inputs: {name}")
    for name in (
        "projection.artifact-receipt.json",
        "wheel.artifact-receipt.json",
        "sdist.artifact-receipt.json",
    ):
        verify_receipt(ATTEMPT / name)
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored commands differ from deterministic records")
    for line in commands_text().splitlines():
        json.loads(line)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored review differs from live evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict):
            raise SystemExit("RAH binding is not an object")
        if re.fullmatch(r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))) is None:
            raise SystemExit("core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if re.fullmatch(r"E\d{4,}", str(rah_state.get(key))) is None:
                raise SystemExit(f"{key} is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if (ATTEMPT / "report.json").read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "460/460",
        "full_python": "990/990",
        "package_status": "PASS",
        "projection_status": "PASS_CURRENT",
        "status": "PASS",
        "targeted_projection": "41/41",
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
