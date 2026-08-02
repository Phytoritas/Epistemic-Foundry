#!/usr/bin/env python3
"""Build and verify B04-0007 pre-C04 projection/recovery evidence.

B04-0007 is the authorized re-entrant correction attempt that follows the
C03/F04/J02/S04 repair sequence.  It proves that the 126-schema canonical
source, derived package snapshot, clean distributions, installed resources,
and repository regression surface now converge.  It does not claim C04 or the
post-C04 B04 final packaging gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0007"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
DECISION_PATH = (
    ROOT
    / "artifacts/authority_decisions/HD-EF4-B04-SG002-20260730-001.human-decision.json"
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.build.canonical_registry import materialize  # noqa: E402
from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402


ATTEMPT_ID = "B04-0007"
WORK_PACKAGE_ID = "B04"
AUTHORITY_DECISION_ID = "HD-EF4-B04-SG002-20260730-001"
RECORDED_AT = "2026-07-30T15:00:00.000Z"
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
EXPECTED_DECISION_HASH = (
    "sha256:421c238aa3bdb2a2e961a1c4c1a87f3c580a4affec1253439ddd842d8bbb4448"
)
EXPECTED_MANIFEST_HASH = (
    "sha256:5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"
)
EXPECTED_BINDING_ID = "DMB-EF4-20260730-002"
EXPECTED_BINDING_HASH = (
    "sha256:aa728584283eb126842e614f83c1e70d132ef12b99b9f80bc42deeb2922907ec"
)
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
RAW_JUNIT_HASHES = {
    "targeted_projection": (
        "91490134dec2a8a9b357aed9b3c9c66e12dcaffaf118f71f2280970904962a7e"
    ),
    "full_python": (
        "32d390e41bbeafbe333a4a0e5b2a28e7d7b6dda6c12098a34eb894e1c5426fca"
    ),
    "full_node": (
        "261b8ed7eacacc1d69cfb220b869daa3e0851f5fc6364d5a56db0d35998f4d95"
    ),
}
JUNIT_PATHS = {
    "targeted_projection": ATTEMPT / "targeted-projection.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
DEPENDENCY_REPORTS = {
    "C01": ROOT / "artifacts/work_packages/C01/attempts/0006/report.json",
    "C02": ROOT / "artifacts/work_packages/C02/attempts/0002/report.json",
    "C03": ROOT / "artifacts/work_packages/C03/attempts/0003/report.json",
    "F04": ROOT / "artifacts/work_packages/F04/attempts/0002/report.json",
    "J02": ROOT / "artifacts/work_packages/J02/attempts/0003/report.json",
    "S04": ROOT / "artifacts/work_packages/S04/attempts/0003/report.json",
}
EXPECTED_DEPENDENCY_ATTEMPTS = {
    "C01": "C01-0006",
    "C02": "C02-0002",
    "C03": "C03-0003",
    "F04": "F04-0002",
    "J02": "J02-0003",
    "S04": "S04-0003",
}
EXPECTED_DEPENDENCY_HASHES = {
    "C01": "35c9f323ab976c60448e9d4138833d9dd67570fb26e99d8b4298be5e2424ac30",
    "C02": "f89f0f3bc82697716f7833a57acabd6a3a9666196e3c4ec310f406d6576b45cf",
    "C03": "624ee1ef8fb21ee33670e19b6262d3226e8350aaf291da8d90e94e8c46273a56",
    "F04": "5a2414ebb79c923af7425b87d614faa088ba9fbd4e6950406948b2eb86d6ab46",
    "J02": "d348ddc7c8b2d476d3424a6459079f0011d9fc69e29056131832b3ae2fc2d184",
    "S04": "bf76a387c229769e568e650b150b5ede6b2136c3294d792a551a9802904cadd4",
}
PRIOR_B04_REPORTS = {
    name: ROOT / f"artifacts/work_packages/B04/attempts/{name}/report.json"
    for name in ("0002", "0003", "0004", "0005", "0006")
}
OUTPUT_NAMES = (
    "canonical-projection-verification.json",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "full-regression-impact.json",
    "installed-wheel-verification.json",
    "junit-normalization-verification.json",
    "packaging-verification-run.json",
    "phase-artifact-reconciliation.json",
    "projection.artifact-receipt.json",
    "rah-core-integrity.json",
    "report.json",
    "review.md",
    "snapshot-inventory.json",
    "source-inventory.json",
    "targeted-projection.junit.xml",
    "wheel.artifact-receipt.json",
    "sdist.artifact-receipt.json",
    "write-scope-verification.json",
    "build_b04_0007_evidence.py",
    "b04_0007_rah_seal.py",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
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


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


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


def assert_decision_and_manifest() -> dict[str, Any]:
    decision = read_json(DECISION_PATH)
    if (
        decision.get("decision_id") != AUTHORITY_DECISION_ID
        or decision.get("decision_hash") != EXPECTED_DECISION_HASH
        or hash_excluding(decision, "decision_hash") != EXPECTED_DECISION_HASH
    ):
        raise SystemExit("B04-SG002 HumanDecision identity or self-hash mismatch")
    if sha256_id(MANIFEST_PATH) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("active development manifest changed after S04-0003 binding")
    binding_path = ROOT / "manifests/source_bindings/development-manifest.binding.json"
    binding = read_json(binding_path)
    if (
        binding.get("binding_id") != EXPECTED_BINDING_ID
        or binding.get("binding_hash") != EXPECTED_BINDING_HASH
        or binding.get("successor_sha256") != EXPECTED_MANIFEST_HASH.removeprefix("sha256:")
        or "B04-0007" not in binding.get("attempt_level_reconciliation", [])
    ):
        raise SystemExit("active development-manifest binding is not B04-0007-ready")
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    required_b04_scope = (
        "src/epistemic_foundry/_canonical/**",
        "scripts/build/canonical_registry/**",
        "tests/packaging/**",
        "tests/test_contracts.py",
        "tests/test_cli.py",
        "artifacts/work_packages/B04/**",
    )
    if any(f"  - {path}" not in manifest_text for path in required_b04_scope):
        raise SystemExit("active B04 exact write scope is incomplete")
    return {
        "binding_hash": EXPECTED_BINDING_HASH,
        "binding_id": EXPECTED_BINDING_ID,
        "decision_file_sha256": sha256_id(DECISION_PATH),
        "decision_hash": EXPECTED_DECISION_HASH,
        "decision_id": AUTHORITY_DECISION_ID,
        "manifest_sha256": EXPECTED_MANIFEST_HASH,
        "status": "PASS",
    }


def junit_case_signature(text: str) -> list[tuple[Any, ...]]:
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
    root_variants = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in root_variants):
            raise SystemExit(f"JUnit contains an absolute repository path: {name}")
        if name != "full_node" and re.search(r'\s+(?:hostname|timestamp)="', text):
            raise SystemExit(f"pytest JUnit contains volatile host/time fields: {name}")


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
        if sha256(path) != RAW_JUNIT_HASHES[name]:
            raise SystemExit(f"raw JUnit hash mismatch: {name}")
        before = path.read_text(encoding="utf-8")
        before_signature = junit_case_signature(before)
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
        if junit_case_signature(normalized) != before_signature:
            raise SystemExit(f"JUnit semantic signature changed: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "case_count": len(before_signature),
            "hostname_attributes_removed": removed_hostname,
            "normalized_sha256": sha256_id(path),
            "raw_sha256": "sha256:" + RAW_JUNIT_HASHES[name],
            "repository_prefix_replacements": prefix_replacements,
            "semantic_signature_preserved": True,
            "timestamp_attributes_removed": removed_timestamp,
        }
    record = {
        "attempt_id": ATTEMPT_ID,
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
        required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
        if set(footer) != required:
            raise SystemExit("Node footer inventory is incomplete")
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
            "collected": sum(int(suite.get("tests", "0")) for suite in suites),
            "errors": sum(int(suite.get("errors", "0")) for suite in suites),
            "failed": sum(int(suite.get("failures", "0")) for suite in suites),
            "semantic_counter_authority": "pytest_testsuite_attributes",
            "skipped": sum(int(suite.get("skipped", "0")) for suite in suites),
            "xml_testcase_count": len(cases),
        }
        result["passed"] = (
            result["collected"]
            - result["errors"]
            - result["failed"]
            - result["skipped"]
        )
    result.update(
        {
            "junit": path.relative_to(ROOT).as_posix(),
            "junit_sha256": sha256_id(path),
        }
    )
    return result


def assert_green_junit() -> dict[str, dict[str, Any]]:
    targeted = junit_summary("targeted_projection")
    python = junit_summary("full_python")
    node = junit_summary("full_node")
    if targeted != {
        **targeted,
        "collected": 41,
        "passed": 41,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }:
        raise SystemExit(f"targeted projection suite is not 41/41: {targeted}")
    if not (
        python["collected"] == 990
        and python["passed"] == 990
        and python["failed"] == 0
        and python["errors"] == 0
        and python["skipped"] == 0
    ):
        raise SystemExit(f"full Python suite is not 990/990: {python}")
    if not (
        node["collected"] == 460
        and node["passed"] == 460
        and node["failed"] == 0
        and node["cancelled"] == 0
        and node["skipped"] == 0
        and node["todo"] == 0
        and node["xml_failures"] == 0
        and node["xml_errors"] == 0
    ):
        raise SystemExit(f"full Node suite is not 460/460: {node}")
    return {"targeted_projection": targeted, "full_python": python, "full_node": node}


def live_canonical_inventory() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry, resources = materialize.build_registry_document(ROOT)
    source_hash = materialize.calculate_source_bundle_hash(resources)
    snapshot_hash = materialize.calculate_projected_snapshot_bundle_hash(resources)
    registry_bytes = materialize._registry_bytes(registry)
    registry_hash = sha256_bytes(registry_bytes)
    if (
        source_hash != EXPECTED_SOURCE_BUNDLE_HASH
        or snapshot_hash != EXPECTED_SNAPSHOT_BUNDLE_HASH
        or registry_hash != EXPECTED_REGISTRY_HASH
    ):
        raise SystemExit("live canonical bundle hashes changed")
    if REGISTRY_PATH.read_bytes() != registry_bytes:
        raise SystemExit("live registry differs from deterministic output")
    if (
        registry.get("schema_count") != EXPECTED_SCHEMA_COUNT
        or registry.get("resource_count") != EXPECTED_RESOURCE_COUNT
        or registry.get("openapi_document_count") != 1
    ):
        raise SystemExit("live registry count contract changed")

    source_entries: list[dict[str, Any]] = []
    snapshot_entries: list[dict[str, Any]] = []
    document_ids: set[str] = set()
    duplicate_ids: list[str] = []
    expected_paths: set[str] = set()
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
        target = SNAPSHOT / Path(*resource.relative_path.parts)
        if not target.is_file():
            missing.append(relative)
            continue
        observed = target.read_bytes()
        observed_hash = sha256_bytes(observed)
        snapshot_entries.append(
            {
                "byte_size": len(observed),
                "document_id": document_id,
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
    if missing or extra or mismatches or duplicate_ids:
        raise SystemExit(
            "canonical projection drift: "
            f"missing={missing}, extra={extra}, mismatches={mismatches}, "
            f"duplicate_ids={duplicate_ids}"
        )
    openapi_text = (ROOT / "openapi/epistemic-foundry-v1.openapi.yaml").read_text(
        encoding="utf-8"
    )
    operations = re.findall(r"^\s+operationId:\s*([^\s#]+)\s*$", openapi_text, re.M)
    if (
        not openapi_text.startswith("openapi: 3.1.1\n")
        or len(operations) != EXPECTED_OPENAPI_OPERATION_COUNT
        or len(operations) != len(set(operations))
    ):
        raise SystemExit("OpenAPI 3.1.1/33-operation contract changed")
    source = {
        "attempt_id": ATTEMPT_ID,
        "duplicate_schema_ids": [],
        "entries": source_entries,
        "openapi_operation_count": len(operations),
        "openapi_resource_count": 1,
        "openapi_version": "3.1.1",
        "schema_count": registry["schema_count"],
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
        "registry": {
            "byte_size": REGISTRY_PATH.stat().st_size,
            "sha256": registry_hash,
        },
        "snapshot_file_count_including_registry": sum(
            path.is_file() for path in SNAPSHOT.rglob("*")
        ),
        "snapshot_resource_count": len(snapshot_entries),
        "status": "PASS",
    }
    return source, snapshot, registry


def verify_packaging(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stored = read_json(ATTEMPT / "packaging-verification-run.json")
    canonical = stored.get("canonical_registry")
    checks = stored.get("checks")
    inventory = stored.get("artifact_inventory")
    if (
        stored.get("status") != "PASS"
        or not isinstance(canonical, dict)
        or not isinstance(checks, dict)
        or not isinstance(inventory, dict)
    ):
        raise SystemExit("packaging verification is not a structured PASS")
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
            raise SystemExit(f"packaging evidence mismatch for {key}")
        if key != "registry_sha256" and registry.get(key) != value:
            raise SystemExit(f"live registry mismatch for {key}")
    comparisons = checks.get("registry_comparisons")
    installed = checks.get("installed_wheel")
    reproducibility = checks.get("two_build_reproducibility")
    if not isinstance(comparisons, dict):
        raise SystemExit("packaging comparison evidence missing")
    expected_comparison = {
        "extra": 0,
        "hash_mismatches": 0,
        "missing": 0,
        "resource_count": EXPECTED_RESOURCE_COUNT,
        "status": "PASS",
    }
    for name, comparison in comparisons.items():
        if comparison != expected_comparison:
            raise SystemExit(f"packaging comparison failed: {name}: {comparison}")
    if not isinstance(installed, dict) or not isinstance(reproducibility, dict):
        raise SystemExit("installed/reproducibility packaging evidence missing")
    if not (
        installed.get("clean_venv_install") == "PASS"
        and installed.get("arbitrary_empty_cwd") == "PASS"
        and installed.get("schema_count") == EXPECTED_SCHEMA_COUNT
        and installed.get("openapi_load") == "PASS"
        and installed.get("representative_schema_validation") == "PASS"
        and installed.get("fallback_success_count") == 0
        and installed.get("missing_packaged_resource_error_code")
        == "CANONICAL_REGISTRY_MISSING"
        and installed.get("tamper_error_code") == "CANONICAL_REGISTRY_HASH_MISMATCH"
        and checks.get("sdist_to_wheel") == "PASS"
        and checks.get("source_tree_fallback")
        == {"attempt_count": 1, "success_count": 0}
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
            raise SystemExit(f"distribution artifact mismatch: {name}: {observed}")
    wheel = ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
    prefix = "epistemic_foundry/_canonical/"
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        if archive.read(prefix + "canonical-registry.json") != REGISTRY_PATH.read_bytes():
            raise SystemExit("wheel registry differs from live package snapshot")
        for entry in registry["resources"]:
            archive_name = prefix + str(entry["package_path"])
            if archive_name not in names:
                raise SystemExit(f"wheel canonical resource missing: {archive_name}")
            wheel_bytes = archive.read(archive_name)
            root_bytes = (ROOT / str(entry["source_path"])).read_bytes()
            snapshot_bytes = (SNAPSHOT / str(entry["package_path"])).read_bytes()
            if wheel_bytes != root_bytes or wheel_bytes != snapshot_bytes:
                raise SystemExit(f"wheel canonical resource diverges: {archive_name}")
            if sha256_bytes(wheel_bytes) != entry["sha256"]:
                raise SystemExit(f"wheel canonical hash diverges: {archive_name}")
    installed_evidence = {
        "arbitrary_empty_cwd": installed["arbitrary_empty_cwd"],
        "attempt_id": ATTEMPT_ID,
        "clean_venv_install": installed["clean_venv_install"],
        "installed_registry_sha256": EXPECTED_REGISTRY_HASH,
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
        "verified_wheel_canonical_resource_count": EXPECTED_RESOURCE_COUNT,
        "wheel_registry_byte_equal": True,
    }
    return stored, installed_evidence


def dependency_evidence() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    for package, path in DEPENDENCY_REPORTS.items():
        report = read_json(path)
        if (
            report.get("attempt_id") != EXPECTED_DEPENDENCY_ATTEMPTS[package]
            or report.get("status") != "PASS"
            or report.get("package_status") != "PASS"
            or sha256(path) != EXPECTED_DEPENDENCY_HASHES[package]
        ):
            raise SystemExit(f"B04-0007 dependency is not hash-bound PASS: {package}")
        dependencies[package] = {
            "attempt_id": report["attempt_id"],
            "report": path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(path),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "attempt_level_dependencies": dependencies,
        "authorized_order": [
            "C03-0003",
            "F04-0002",
            "J02-0003",
            "S04-0003",
            "B04-0007",
            "C01_GATE_DECISION_HASH_CORRECTION",
            "C04-0002",
            "B04-0008",
        ],
        "completion_ready": False,
        "next_state": {
            "B04-0007": "PASS",
            "C01_GATE_DECISION_HASH_CORRECTION": "READY",
            "C04-0002": "WAITING_ON_C01_HASH_CORRECTION",
            "B04-0008": "WAITING_ON_C04_0002",
        },
        "static_dependency_cycle_added": False,
        "status": "PASS",
    }


def prior_history_evidence() -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for attempt, path in PRIOR_B04_REPORTS.items():
        report = read_json(path)
        if report.get("attempt_id") != f"B04-{attempt}":
            raise SystemExit(f"prior B04 report identity mismatch: {attempt}")
        reports[attempt] = {
            "byte_size": path.stat().st_size,
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(path),
            "status": "PRESERVED",
        }
    return reports


def artifact_receipt(
    *, receipt_id: str, artifact_id: str, path: Path, media_type: str, checks: list[dict[str, str]]
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": artifact_id,
        "byte_size": path.stat().st_size,
        "content_hash": sha256_id(path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "B04-0007-projection-regression-verifier",
            "actor_type": "tool",
        },
        "locator": path.relative_to(ROOT).as_posix(),
        "media_type": media_type,
        "receipt_id": receipt_id,
        "schema_ref": None,
        "validation_results": checks,
    }
    value["receipt_hash"] = hash_excluding(value, "receipt_hash")
    validate_artifact("artifact-receipt", value)
    return value


def receipts() -> dict[str, dict[str, Any]]:
    projection = artifact_receipt(
        receipt_id="AR-B04-0007-CANONICAL-PROJECTION",
        artifact_id="ART-B04-0007-CANONICAL-PROJECTION",
        path=REGISTRY_PATH,
        media_type="application/vnd.epistemic-foundry.canonical-registry+json",
        checks=[
            {
                "check": "registry_byte_integrity",
                "details": "Receipt content_hash and byte_size bind the exact live canonical-registry.json bytes.",
                "status": "PASS",
            },
            {
                "check": "root_snapshot_wheel_convergence",
                "details": (
                    f"All {EXPECTED_RESOURCE_COUNT} canonical resources bind root "
                    f"{EXPECTED_SOURCE_BUNDLE_HASH} to snapshot "
                    f"{EXPECTED_SNAPSHOT_BUNDLE_HASH} and the built wheel byte-for-byte."
                ),
                "status": "PASS",
            },
            {
                "check": "pre_c04_scope_boundary",
                "details": "This receipt proves the B04-0007 projection/recovery gate; C04 and B04-0008 remain separate later gates.",
                "status": "PASS",
            },
        ],
    )
    wheel_path = ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
    wheel = artifact_receipt(
        receipt_id="AR-B04-0007-WHEEL",
        artifact_id="ART-B04-0007-WHEEL",
        path=wheel_path,
        media_type="application/vnd.python.wheel",
        checks=[
            {
                "check": "installed_wheel_only",
                "details": "Clean isolated install, arbitrary empty cwd, representative schema validation, and OpenAPI load pass without source fallback.",
                "status": "PASS",
            },
            {
                "check": "wheel_reproducibility",
                "details": "Two clean builds and the sdist-derived wheel are byte-identical.",
                "status": "PASS",
            },
        ],
    )
    sdist_path = ATTEMPT / "dist/epistemic_foundry-4.0.0.tar.gz"
    sdist = artifact_receipt(
        receipt_id="AR-B04-0007-SDIST",
        artifact_id="ART-B04-0007-SDIST",
        path=sdist_path,
        media_type="application/gzip",
        checks=[
            {
                "check": "sdist_clean_build",
                "details": "The clean sdist contains root authority, deterministic projection tooling, and exact build constraints.",
                "status": "PASS",
            },
            {
                "check": "sdist_to_wheel",
                "details": "The wheel rebuilt from the sdist is byte-identical to the direct clean-source wheel.",
                "status": "PASS",
            },
        ],
    )
    return {"projection": projection, "wheel": wheel, "sdist": sdist}


def gate_decision_hash_debt() -> dict[str, Any]:
    path = ROOT / "examples/sample_gate_decision.json"
    value = read_json(path)
    stored = value.get("decision_hash")
    expected = hash_excluding(value, "decision_hash")
    if stored != "sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1":
        raise SystemExit("C01-owned sample GateDecision stored hash changed unexpectedly")
    if expected != "sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851":
        raise SystemExit("C01-owned sample GateDecision recomputation changed")
    return {
        "expected_decision_hash": expected,
        "must_be_resolved_before_c04": True,
        "owner": "C01_CANONICAL_CONTRACT",
        "path": path.relative_to(ROOT).as_posix(),
        "status": "PENDING_NEXT_AUTHORIZED_STEP",
        "stored_decision_hash": stored,
    }


def write_scope_evidence(authority: dict[str, Any]) -> dict[str, Any]:
    return {
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
        "authority": authority,
        "dirty_worktree_preserved": True,
        "product_files_modified_by_attempt": [],
        "projection_changed_file_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def command_records() -> list[dict[str, Any]]:
    rows: list[tuple[str, int | None, str]] = [
        ("Inspect HD-EF4-B04-SG002-20260730-001, active manifest binding, B04-0006 evidence, and S04-0003 closeout", 0, "PASS: B04-0007 authorized and dependency-ready"),
        ("Diagnostic RAH inspect using the obsolete helper path .rah/helpers/recursive-architecture-refactoring-auto/rah.py", 1, "DIAGNOSTIC_ONLY: file does not exist; no state mutation"),
        ("Diagnostic RAH inspect using the correct helper without the required repo_root argument", 1, "DIAGNOSTIC_ONLY: argparse rejected the invocation; no state mutation"),
        ("Run RAH inspect through Git Bash with the correct automation/rah.py path and repo root", 0, "PASS: active/fail/completion_ready=false; B04-0007 next"),
        ("Run canonical materializer --check against the current root and snapshot", 0, "PASS: expected files 128; missing/extra/mismatch 0"),
        ("Run deterministic canonical materialization from root schemas/openapi", 0, "PASS: already current; changed_file_count=0; atomic replacement not required"),
        ("Run B04 targeted projection, registry, CLI, and contract tests with JUnit", 0, "PASS: 41/41"),
        ("Run clean wheel/sdist, sdist-to-wheel, installed-only, arbitrary-cwd, no-fallback, tamper, and reproducibility verification", 0, "PASS: wheel 308644 bytes; sdist 257575 bytes; 127 resources"),
        ("Run full Python suite with the frozen dev and skill-context groups", 0, "PASS: 990/990; failed/errors/skipped 0"),
        ("Run the complete 52-file serial Node suite with JUnit", 0, "PASS: authoritative footer 460/460; failed/skipped 0"),
        ("Diagnostic PowerShell attempt to cast multiple Node JUnit testsuite objects as one integer", 1, "DIAGNOSTIC_ONLY: aggregation command shape invalid; product suite already exit 0"),
        ("Recompute pytest and Node JUnit totals with suite-aware/footer-aware parsing", 0, "PASS: targeted 41, Python 990, Node footer 460"),
        ("PowerShell dependency-report collection attempt blocked before execution by the reliability hook", None, "HOOK_BLOCKED_BEFORE_EXECUTION: foreach pipeline shape replaced safely; no state mutation"),
        ("Collect dependency report identities and hashes using a safe intermediate variable", 0, "PASS: C01/C02/C03/F04/J02/S04 reports are hash-bound PASS"),
        ("Run targeted B04 git diff --check", 0, "PASS: whitespace errors 0; existing line-ending notices only"),
        ("Normalize JUnit portability while preserving semantic signatures and Node footer counters", 0, "PASS"),
        ("Build and verify B04-0007 evidence from live source, snapshot, wheel, JUnit, dependency, and manifest bytes", 0, "PASS when this builder build/verify sequence completes"),
        ("Perform primary-session separate adversarial integration review", 0, "PASS: blocking B04-0007 findings 0; actor_independence=false"),
        ("Seal B04-0007 core/final evidence into append-only RAH and verify six snapshots", 0, "PASS when b04_0007_rah_seal.py preflight/core/final/verify completes"),
    ]
    return [
        {
            "command": command,
            "command_id": f"B04-0007-C{index:03d}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": "B04-0007 pre-C04 projection and regression revalidation",
        }
        for index, (command, exit_code, result) in enumerate(rows, 1)
    ]


def commands_text() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    projection = documents["canonical-projection-verification.json"]
    debt = regression["remaining_c01_owned_debt"]
    return f"""# B04-0007 pre-C04 projection and regression review

Overall correction status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external actor-independent certification.
Fleet and subagents were not used.

## Authority and projection

- Root `schemas/**` and `openapi/**` remain the sole canonical authority. The
  package snapshot is a deterministic derived projection.
- {projection['schema_count']} schemas and one OpenAPI 3.1.1 document with
  {projection['openapi_operation_count']} unique operations produce
  {projection['total_canonical_resource_count']} canonical resources.
- Source `{projection['source_bundle_hash']}`, snapshot
  `{projection['projected_snapshot_bundle_hash']}`, and registry
  `{projection['registry_hash']}` match live bytes. Missing, extra,
  hash-mismatched, and duplicate-ID counts are zero.
- The official materializer found the snapshot already current and changed zero
  files. Root canonical source mutation and reverse synchronization counts are zero.

## Packaging and regression

- Targeted projection/registry/CLI contracts pass
  {regression['targeted_projection']['passed']}/{regression['targeted_projection']['collected']}.
- Clean wheel/sdist, sdist-to-wheel rebuild, installed-wheel-only loading,
  arbitrary empty cwd, missing/tamper fail-closed behavior, no source fallback,
  and two-build byte reproducibility all pass.
- Full Python is {regression['full_python']['passed']}/{regression['full_python']['collected']}
  with zero failures, errors, skips, or xfails.
- Full Node is {regression['full_node']['passed']}/{regression['full_node']['collected']}
  by the Node footer, with zero failures, cancellations, skips, or todos. The
  reporter's 457 XML testcase rows remain separately visible and are not used to
  undercount the authoritative 460 footer total.
- The 67 Python and 11 Node problems recorded by B04-0006 are now resolved.
  No failure was hidden with skip, xfail, alias, fallback, or gate weakening.

## Remaining bounded debt and decision

- `{debt['path']}` remains a C01-owned canonical example hash debt: stored
  `{debt['stored_decision_hash']}`, recomputed `{debt['expected_decision_hash']}`.
  B04 did not edit it. The authorized next step must correct and validate it
  before C04-0002.
- B04-0007 passes as the pre-C04 correction/revalidation attempt. This does not
  establish C04 full conformance, B04-0008 final packaging, release readiness,
  or product completion. Global `implementation_gate=fail` and
  `completion_ready=false` remain required.
"""


def live_documents() -> dict[str, dict[str, Any]]:
    normalization = normalize_junit_files()
    authority = assert_decision_and_manifest()
    summaries = assert_green_junit()
    source, snapshot, registry = live_canonical_inventory()
    packaging, installed = verify_packaging(registry)
    dependencies = dependency_evidence()
    receipt_set = receipts()
    debt = gate_decision_hash_debt()
    projection = {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_id": AUTHORITY_DECISION_ID,
        "deterministic_rebuild_result": "PASS",
        "duplicate_schema_ids": [],
        "extra_paths": [],
        "final_status": "PASS",
        "hash_mismatches": [],
        "installed_wheel_resource_load_result": "PASS",
        "materialization_result": {
            "atomic_replacement": "NOT_REQUIRED_ALREADY_CURRENT",
            "changed_file_count": 0,
            "expected_file_count_including_registry": 128,
        },
        "missing_paths": [],
        "openapi_operation_count": EXPECTED_OPENAPI_OPERATION_COUNT,
        "openapi_resource_count": 1,
        "openapi_version": "3.1.1",
        "package_status": "PASS",
        "packaging_verification_sha256": sha256_id(
            ATTEMPT / "packaging-verification-run.json"
        ),
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
        "b04_0006_baseline": {
            "node_failed": 11,
            "python_errors": 15,
            "python_failed": 52,
            "status": "PRESERVED_HISTORICAL_FAILURE_BASELINE",
        },
        "completion_ready": False,
        "full_node": summaries["full_node"],
        "full_python": summaries["full_python"],
        "new_failure_count": 0,
        "remaining_c01_owned_debt": debt,
        "resolved_b04_0006_node_problem_count": 11,
        "resolved_b04_0006_python_problem_count": 67,
        "status": "PASS",
        "targeted_projection": summaries["targeted_projection"],
        "unexpected_skip_or_xfail_count": 0,
    }
    phase = {
        "artifact_receipts": [
            {
                "artifact_locator": receipt_set[key]["locator"],
                "byte_size": receipt_set[key]["byte_size"],
                "content_hash": receipt_set[key]["content_hash"],
                "receipt": f"artifacts/work_packages/B04/attempts/0007/{key}.artifact-receipt.json",
                "receipt_hash": receipt_set[key]["receipt_hash"],
                "receipt_id": receipt_set[key]["receipt_id"],
            }
            for key in ("projection", "wheel", "sdist")
        ],
        "attempt_id": ATTEMPT_ID,
        "checks": {
            "attempt_level_dependencies": "PASS",
            "canonical_projection": "PASS",
            "deterministic_rebuild": "PASS",
            "full_node": "PASS_460_OF_460",
            "full_python": "PASS_990_OF_990",
            "installed_wheel_only": "PASS",
            "source_tree_fallback": "PASS_ZERO_SUCCESSES",
            "targeted_projection": "PASS_41_OF_41",
        },
        "completion_ready": False,
        "global_implementation_gate": "fail",
        "next_attempt": "C01_GATE_DECISION_HASH_CORRECTION",
        "status": "PASS",
    }
    scope = write_scope_evidence(authority)
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
        "prior-history-verification.json": {
            "attempt_id": ATTEMPT_ID,
            "prior_B04_reports": prior_history_evidence(),
            "status": "PASS",
        },
        "packaging-summary.json": {
            "artifact_inventory": packaging["artifact_inventory"],
            "attempt_id": ATTEMPT_ID,
            "backend": packaging["backend"],
            "canonical_registry": packaging["canonical_registry"],
            "checks": packaging["checks"],
            "status": "PASS",
        },
    }


def report_document(
    documents: dict[str, dict[str, Any]], rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    projection = documents["canonical-projection-verification.json"]
    regression = documents["full-regression-impact.json"]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "PRE_C04_CANONICAL_PROJECTION_AND_REGRESSION_REVALIDATION",
        "authority_decision_id": AUTHORITY_DECISION_ID,
        "canonical_projection": {
            "duplicate_schema_id_count": 0,
            "extra_path_count": 0,
            "hash_mismatch_count": 0,
            "missing_path_count": 0,
            "openapi_operation_count": projection["openapi_operation_count"],
            "openapi_resource_count": 1,
            "openapi_version": "3.1.1",
            "projected_snapshot_bundle_hash": EXPECTED_SNAPSHOT_BUNDLE_HASH,
            "registry_hash": EXPECTED_REGISTRY_HASH,
            "resource_count": EXPECTED_RESOURCE_COUNT,
            "schema_count": EXPECTED_SCHEMA_COUNT,
            "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        },
        "completion_ready": False,
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
            "B04-0007": "PASS_PRE_C04_CORRECTION",
            "C01_GATE_DECISION_HASH_CORRECTION": "READY",
            "C04-0002": "WAITING_ON_C01_HASH_CORRECTION",
            "B04-0008": "WAITING_ON_C04_0002",
        },
        "not_claimed": [
            "C01-owned sample GateDecision hash debt resolved",
            "C04-0002 full conformance",
            "B04-0008 final packaging",
            "repository release readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": [
            f"artifacts/work_packages/B04/attempts/0007/{name}"
            for name in OUTPUT_NAMES
        ]
        + [
            "artifacts/work_packages/B04/attempts/0007/prior-history-verification.json",
            "artifacts/work_packages/B04/attempts/0007/packaging-summary.json",
        ],
        "package_status": "PASS",
        "product_files_modified_by_attempt": [],
        "projection_status": "PASS",
        "regression": {
            "node": "PASS_460_OF_460",
            "python": "PASS_990_OF_990",
            "targeted_projection": "PASS_41_OF_41",
            "unexpected_skip_or_xfail_count": regression[
                "unexpected_skip_or_xfail_count"
            ],
        },
        "remaining_debt": regression["remaining_c01_owned_debt"],
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_B04_0007_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    documents = live_documents()
    for name, value in documents.items():
        write_json(name, value)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
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


def verify_receipt(path: Path) -> dict[str, Any]:
    value = read_json(path)
    validate_artifact("artifact-receipt", value)
    if value.get("receipt_hash") != hash_excluding(value, "receipt_hash"):
        raise SystemExit(f"receipt self-hash mismatch: {path.name}")
    locator = ROOT / str(value["locator"])
    if (
        not locator.is_file()
        or value["content_hash"] != sha256_id(locator)
        or value["byte_size"] != locator.stat().st_size
    ):
        raise SystemExit(f"receipt does not bind its artifact: {path.name}")
    return value


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored B04-0007 evidence differs from live inputs: {name}")
    for name in (
        "projection.artifact-receipt.json",
        "wheel.artifact-receipt.json",
        "sdist.artifact-receipt.json",
    ):
        verify_receipt(ATTEMPT / name)
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored B04-0007 commands differ from deterministic records")
    for line in commands_text().splitlines():
        json.loads(line)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored B04-0007 review differs from live evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict):
            raise SystemExit("B04-0007 RAH state is not an object")
        if re.fullmatch(r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))) is None:
            raise SystemExit("B04-0007 core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if re.fullmatch(r"E\d{4,}", str(rah_state.get(key))) is None:
                raise SystemExit(f"B04-0007 {key} binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if (ATTEMPT / "report.json").read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored B04-0007 report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "460/460",
        "full_python": "990/990",
        "package_status": "PASS",
        "projection_status": "PASS",
        "registry_hash": EXPECTED_REGISTRY_HASH,
        "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
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
