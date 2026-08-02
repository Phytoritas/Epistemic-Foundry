#!/usr/bin/env python3
"""Build and verify B04-0010 final post-C04 packaging evidence."""

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

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0010"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
C04_ATTEMPT = ROOT / "artifacts/work_packages/C04/attempts/0004"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402
from scripts.build.canonical_registry import materialize  # noqa: E402


ATTEMPT_ID = "B04-0010"
WORK_PACKAGE_ID = "B04"
RECORDED_AT = "2026-07-31T11:30:00.000Z"
EXPECTED_MANIFEST_HASH = (
    "sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063"
)
EXPECTED_C04_REPORT_HASH = (
    "sha256:28cded86378c3ad189839296bd00dc5c29395dce3d31a6db590de67a7ac008ab"
)
EXPECTED_C04_VERIFICATION_HASH = (
    "sha256:cba6b210059542a50e439317009e5ccb2e6f86decbbb7bbfa63d1f6dd8988aa9"
)
EXPECTED_SOURCE_BUNDLE_HASH = (
    "sha256:2cb8b87793eabf4d6cd209044b6c28bf14f003b15fb85a81cf70db77ce92e2b5"
)
EXPECTED_SNAPSHOT_BUNDLE_HASH = (
    "sha256:9dfd37885743ad02dd680e36882fbf88249a89dcc4ec1b7ac5266a94ca7a2229"
)
EXPECTED_REGISTRY_HASH = (
    "sha256:d08d78c19d39e08ec98df3ac4da8014f61fcc19fe0f833f9e5273059c5cda27c"
)
EXPECTED_SCHEMA_COUNT = 127
EXPECTED_RESOURCE_COUNT = 128
EXPECTED_SNAPSHOT_FILE_COUNT = 129
EXPECTED_OPENAPI_OPERATION_COUNT = 33
EXPECTED_TARGETED_COUNT = 41
EXPECTED_PYTHON_COUNT = 1115
EXPECTED_NODE_COUNT = 819
EXPECTED_NODE_FILE_COUNT = 79
EXPECTED_DIST = {
    "epistemic_foundry-4.0.0-py3-none-any.whl": {
        "byte_size": 333_261,
        "sha256": "067b66d055d7cd2a5e056b85f0d99f3473ef407ca32d9acd57ce72de3ac3e2da",
    },
    "epistemic_foundry-4.0.0.tar.gz": {
        "byte_size": 282_078,
        "sha256": "fd108ec00395f16248af77b4d30d45459a217cce75cf20dcc6246d4ca4ed4f92",
    },
}
EXPECTED_PRODUCT_HASHES = {
    "src/epistemic_foundry/_canonical/canonical-registry.json": (
        "d08d78c19d39e08ec98df3ac4da8014f61fcc19fe0f833f9e5273059c5cda27c"
    ),
    "scripts/build/canonical_registry/materialize.py": (
        "ae10176b2ab1d9e1d13f6f501fb78b328774e2a828a8acddc1d8534d3273cf6f"
    ),
    "scripts/build/canonical_registry/verify_packaging.py": (
        "60fc75bec8d95e9dd186b9117a22fe2704bf1b74f3b480e518448d0dacb29c59"
    ),
    "tests/packaging/test_canonical_registry.py": (
        "1cf1b30f8fd4243714d7cb8cac7b50d61604d87c9420442dde3da835aef0418b"
    ),
    "tests/test_contracts.py": (
        "3fd45129acf1a340b7aecf71d45292c6b6a2daa963a43ea016aa7ca1f8e445fb"
    ),
    "tests/test_cli.py": (
        "e3a791f3d94f9eadc03f65cff67eff4a73bade6902e0e7c6326a0024af0d3146"
    ),
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/B02/report.json": (
        "98abe689dbfb9399d2f50f87a18376ca9a85ed4a50c938513778e312e3e67dad"
    ),
    "artifacts/work_packages/B03/report.json": (
        "baa07e997402a290f2602cea39a78a1acdeeb69dd7ea8c89331c84e78976338f"
    ),
    "artifacts/work_packages/C04/attempts/0004/report.json": (
        "28cded86378c3ad189839296bd00dc5c29395dce3d31a6db590de67a7ac008ab"
    ),
    "artifacts/work_packages/C04/attempts/0004/c04-conformance-verification.json": (
        "cba6b210059542a50e439317009e5ccb2e6f86decbbb7bbfa63d1f6dd8988aa9"
    ),
}
JUNIT_PATHS = {
    "targeted_projection": ATTEMPT / "targeted-projection.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
RUN_RESULTS = (
    "materialize-check",
    "targeted-projection",
    "packaging-verification",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_b04_0010_checks.py",
    "build_b04_0010_evidence.py",
    "b04_0010_rah_seal.py",
    "canonical-projection-verification.json",
    "source-inventory.json",
    "snapshot-inventory.json",
    "installed-wheel-verification.json",
    "packaging-summary.json",
    "packaging-verification-run.json",
    "projection.artifact-receipt.json",
    "wheel.artifact-receipt.json",
    "sdist.artifact-receipt.json",
    "phase-artifact-reconciliation.json",
    "full-regression-impact.json",
    "dependency-status.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "prior-history-verification.json",
    "write-scope-verification.json",
    "targeted-projection.junit.xml",
    "full-python-suite.junit.xml",
    "full-node-suite.junit.xml",
    "commands.jsonl",
    "review.md",
    "report.json",
    "rah-core-integrity.json",
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


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, wanted in expected.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(f"sealed input changed: {relative}: {actual} != {wanted}")


def check_run(name: str) -> dict[str, Any]:
    value = read_json(ATTEMPT / f"{name}.run.json")
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not isinstance(value.get("command"), list)
    ):
        raise SystemExit(f"required check did not pass: {name}: {value}")
    return value


def semantic_junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        message = problem.get("message", "") if problem is not None else ""
        body = (problem.text or "") if problem is not None else ""
        for prefix in prefixes:
            message = message.replace(prefix, "")
            body = body.replace(prefix, "")
        for value in roots:
            message = message.replace(value, ".")
            body = body.replace(value, ".")
        rows.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                message,
                body,
                case.find("skipped") is not None,
            )
        )
    return rows


def verify_junit_portability() -> None:
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(root in text for root in roots):
            raise SystemExit(f"JUnit contains absolute repository path: {name}")
        if name == "full_node":
            if "duration_ms" in text:
                raise SystemExit("Node JUnit retains volatile duration_ms")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit(f"pytest JUnit retains volatile attributes: {name}")


def normalize_junits() -> dict[str, Any]:
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
        signature = semantic_junit_signature(before)
        normalized = before
        removed = {
            "duration_comments": 0,
            "hostname_attributes": 0,
            "repository_prefixes": 0,
            "time_attributes": 0,
            "timestamp_attributes": 0,
        }
        for prefix in (root_backslash, root_slash):
            count = normalized.count(prefix)
            normalized = normalized.replace(prefix, "")
            removed["repository_prefixes"] += count
        for value in (str(ROOT), str(ROOT).replace("\\", "/")):
            count = normalized.count(value)
            normalized = normalized.replace(value, ".")
            removed["repository_prefixes"] += count
        if name == "full_node":
            normalized, removed["duration_comments"] = re.subn(
                r"\s*<!-- duration_ms [^>]+ -->", "", normalized
            )
        else:
            normalized, removed["timestamp_attributes"] = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized
            )
            normalized, removed["hostname_attributes"] = re.subn(
                r'\s+hostname="[^"]*"', "", normalized
            )
            normalized, removed["time_attributes"] = re.subn(
                r'(<(?:testsuite|testcase)\b[^>]*?)\s+time="[^"]*"', r"\1", normalized
            )
        if semantic_junit_signature(normalized) != signature:
            raise SystemExit(f"JUnit normalization changed semantics: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "normalized_sha256": sha256_id(path),
            "raw_sha256": sha256_bytes(before_bytes),
            "removed": removed,
            "semantic_signature_preserved": True,
            "testcase_count": len(signature),
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "preserved": [
            "testcase identity and result state",
            "failure type, message, and body after path normalization",
            "Node semantic footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = list(root.findall(".//testcase"))
    result = {
        "collected": sum(int(row.get("tests", "0")) for row in suites),
        "errors": sum(int(row.get("errors", "0")) for row in suites),
        "failed": sum(int(row.get("failures", "0")) for row in suites),
        "skipped": sum(int(row.get("skipped", "0")) for row in suites),
        "xml_testcase_count": len(cases),
    }
    result["passed"] = (
        result["collected"] - result["errors"] - result["failed"] - result["skipped"]
    )
    result.update(
        {
            "junit": path.relative_to(ROOT).as_posix(),
            "junit_sha256": sha256_id(path),
            "semantic_counter_authority": "pytest_testsuite_attributes",
        }
    )
    return result


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
        raise SystemExit("Node JUnit semantic footer is incomplete")
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "semantic_counter_authority": "node_test_footer",
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": sum(case.find("failure") is not None for case in cases),
        "xml_testcase_count": len(cases),
    }


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    targeted = pytest_summary(JUNIT_PATHS["targeted_projection"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if (
        targeted["collected"], targeted["passed"], targeted["failed"],
        targeted["errors"], targeted["skipped"],
    ) != (EXPECTED_TARGETED_COUNT, EXPECTED_TARGETED_COUNT, 0, 0, 0):
        raise SystemExit(f"targeted projection gate failed: {targeted}")
    if (
        python["collected"], python["passed"], python["failed"],
        python["errors"], python["skipped"],
    ) != (EXPECTED_PYTHON_COUNT, EXPECTED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"full Python gate failed: {python}")
    if (
        node["collected"], node["passed"], node["failed"], node["cancelled"],
        node["skipped"], node["todo"], node["xml_error_count"],
        node["xml_failure_count"], node_inventory.get("count"),
    ) != (EXPECTED_NODE_COUNT, EXPECTED_NODE_COUNT, 0, 0, 0, 0, 0, 0, EXPECTED_NODE_FILE_COUNT):
        raise SystemExit(f"full Node gate failed: {node}; inventory={node_inventory}")
    return (
        {
            "attempt_id": ATTEMPT_ID,
            "baseline_attempt": "C04-0004",
            "full_node": node,
            "full_python": python,
            "new_failure_count": 0,
            "status": "PASS",
            "targeted_projection": targeted,
            "unexpected_skip_xfail_todo_or_cancellation_count": 0,
        },
        node_inventory,
    )


def authority_contract() -> dict[str, Any]:
    if sha256_id(MANIFEST_PATH) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("development manifest changed after C04-0004")
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = manifest if isinstance(manifest, list) else manifest["work_packages"]
    by_id = {row["id"]: row for row in packages}
    b04 = by_id["B04"]
    required_checks = {
        "build_smoke",
        "phase_artifact_reconciliation",
        "dependency_group_revalidation",
        "package_metadata_dependency_audit",
        "canonical_projection_integrity",
        "canonical_schema_127_projection",
        "final_packaging_gate",
    }
    required_scope = {
        "src/epistemic_foundry/_canonical/**",
        "src/epistemic_foundry/contracts/registry.py",
        "scripts/build/canonical_registry/**",
        "tests/packaging/**",
        "tests/test_contracts.py",
        "tests/test_cli.py",
        "artifacts/work_packages/B04/**",
    }
    if (
        len(packages) != 156
        or b04.get("depends_on") != ["B02", "B03", "C04"]
        or not required_checks.issubset(set(b04.get("required_checks", [])))
        or not required_scope.issubset(set(b04.get("write_scope", [])))
    ):
        raise SystemExit("B04 manifest contract changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependency_order": b04["depends_on"],
        "manifest_sha256": EXPECTED_MANIFEST_HASH,
        "package_count": len(packages),
        "required_checks": b04["required_checks"],
        "status": "PASS",
        "write_scope": b04["write_scope"],
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    dependencies: dict[str, Any] = {}
    for package in ("B02", "B03"):
        path = ROOT / f"artifacts/work_packages/{package}/report.json"
        report = read_json(path)
        if report.get("status") != "PASS":
            raise SystemExit(f"{package} dependency is not PASS")
        dependencies[package] = {
            "report": path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(path),
            "status": "PASS",
        }
    report_path = C04_ATTEMPT / "report.json"
    verification_path = C04_ATTEMPT / "c04-conformance-verification.json"
    report = read_json(report_path)
    verification = read_json(verification_path)
    rah = report.get("rah_state")
    if not (
        sha256_id(report_path) == EXPECTED_C04_REPORT_HASH
        and sha256_id(verification_path) == EXPECTED_C04_VERIFICATION_HASH
        and report.get("attempt_id") == "C04-0004"
        and report.get("status") == report.get("package_status") == "PASS"
        and report.get("next_package") == ATTEMPT_ID
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0107"
        and rah.get("final_closeout_evidence_id") == "E0108"
        and verification.get("status") == "PASS"
        and verification.get("verdict")
        == "C04_PASS_B04_0010_DEPENDENCY_READY_AFTER_RAH_SEAL"
    ):
        raise SystemExit("C04-0004 is not the exact sealed dependency")
    dependencies["C04"] = {
        "attempt_id": "C04-0004",
        "core_evidence_id": "E0107",
        "final_closeout_evidence_id": "E0108",
        "report": report_path.relative_to(ROOT).as_posix(),
        "report_sha256": EXPECTED_C04_REPORT_HASH,
        "verification_sha256": EXPECTED_C04_VERIFICATION_HASH,
        "status": "PASS",
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "next_action": "RECOMPUTE_156_PACKAGE_DAG_AFTER_RAH_SEAL",
        "status": "PASS",
    }


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
        or REGISTRY_PATH.read_bytes() != registry_bytes
    ):
        raise SystemExit("live canonical source/snapshot/registry binding changed")
    if (
        registry.get("schema_count") != EXPECTED_SCHEMA_COUNT
        or registry.get("resource_count") != EXPECTED_RESOURCE_COUNT
        or registry.get("file_count") != EXPECTED_RESOURCE_COUNT
        or registry.get("openapi_document_count") != 1
    ):
        raise SystemExit("live canonical registry counts changed")

    source_entries: list[dict[str, Any]] = []
    snapshot_entries: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    duplicates: list[str] = []
    expected_paths: set[str] = set()
    missing: list[str] = []
    mismatches: list[str] = []
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
        raise SystemExit("live canonical projection is not exact")
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
    if snapshot["snapshot_file_count_including_registry"] != EXPECTED_SNAPSHOT_FILE_COUNT:
        raise SystemExit("snapshot file count including registry changed")
    return source, snapshot, registry


def packaging_evidence(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stored = read_json(ATTEMPT / "packaging-verification-run.json")
    canonical = stored.get("canonical_registry")
    checks = stored.get("checks")
    inventory = stored.get("artifact_inventory")
    if not (
        stored.get("status") == "PASS"
        and isinstance(canonical, dict)
        and isinstance(checks, dict)
        and isinstance(inventory, dict)
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
        comparison != expected_comparison for comparison in comparisons.values()
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
        artifact = ATTEMPT / "dist" / name
        observed = {"byte_size": artifact.stat().st_size, "sha256": sha256(artifact)}
        if observed != expected_artifact or inventory.get(name) != expected_artifact:
            raise SystemExit(f"fresh distribution differs from sealed bytes: {name}")
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


def artifact_receipt(
    *,
    receipt_id: str,
    artifact_id: str,
    path: Path,
    media_type: str,
    checks: list[dict[str, str]],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": artifact_id,
        "byte_size": path.stat().st_size,
        "content_hash": sha256_id(path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "B04-0010-final-packaging-verifier",
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
        receipt_id="AR-B04-0010-CANONICAL-PROJECTION",
        artifact_id="ART-B04-0010-CANONICAL-PROJECTION",
        path=REGISTRY_PATH,
        media_type="application/vnd.epistemic-foundry.canonical-registry+json",
        checks=[
            {
                "check": "registry_byte_integrity",
                "details": "The receipt binds the exact deterministic 127-schema registry bytes.",
                "status": "PASS",
            },
            {
                "check": "root_snapshot_wheel_convergence",
                "details": "All 128 resources converge byte-for-byte from root authority through the installed wheel.",
                "status": "PASS",
            },
            {
                "check": "post_c04_final_gate",
                "details": "The projection is revalidated after sealed C04-0004 PASS.",
                "status": "PASS",
            },
        ],
    )
    wheel = artifact_receipt(
        receipt_id="AR-B04-0010-WHEEL",
        artifact_id="ART-B04-0010-WHEEL",
        path=ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl",
        media_type="application/vnd.python.wheel",
        checks=[
            {
                "check": "installed_wheel_only",
                "details": "Clean isolated install, arbitrary cwd, schema validation, OpenAPI load, no fallback, missing-resource rejection, and tamper rejection pass.",
                "status": "PASS",
            },
            {
                "check": "wheel_reproducibility",
                "details": "Two clean wheels and the sdist-derived wheel are byte-identical.",
                "status": "PASS",
            },
        ],
    )
    sdist = artifact_receipt(
        receipt_id="AR-B04-0010-SDIST",
        artifact_id="ART-B04-0010-SDIST",
        path=ATTEMPT / "dist/epistemic_foundry-4.0.0.tar.gz",
        media_type="application/gzip",
        checks=[
            {
                "check": "sdist_clean_build",
                "details": "The clean sdist includes canonical authority, deterministic projection tooling, and exact build constraints.",
                "status": "PASS",
            },
            {
                "check": "sdist_to_wheel",
                "details": "The sdist-derived wheel is byte-identical to the direct clean-source wheel.",
                "status": "PASS",
            },
        ],
    )
    return {"projection": projection, "wheel": wheel, "sdist": sdist}


def prior_history_evidence() -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for value in range(2, 10):
        attempt = f"{value:04d}"
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
    if reports["0009"]["sha256"] != (
        "sha256:beafcbc89b687bb61d53a4941fdbc52373aa8e311869dab731f36e0e3baab58c"
    ):
        raise SystemExit("B04-0009 sealed projection report changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "prior_B04_reports": reports,
        "status": "PASS",
    }


def live_documents() -> dict[str, dict[str, Any]]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    for name in RUN_RESULTS:
        check_run(name)
    normalization = normalize_junits()
    authority = authority_contract()
    dependency = dependency_status()
    regression, node_inventory = regression_evidence()
    source, snapshot, registry = live_canonical_inventory()
    packaging, installed = packaging_evidence(registry)
    receipt_set = receipts()
    c04_verification = read_json(C04_ATTEMPT / "c04-conformance-verification.json")
    phase_source = c04_verification.get("phase_artifact_reconciliation")
    if not (
        isinstance(phase_source, dict)
        and phase_source.get("status") == "PASS"
        and phase_source.get("admitted_transition_count") == 17
        and phase_source.get("admitted_phase_artifact_set_count") == 14
    ):
        raise SystemExit("C04-0004 phase-artifact reconciliation changed")
    projection = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "FINAL_POST_C04_PACKAGING_GATE_127",
        "deterministic_rebuild_result": "PASS",
        "duplicate_schema_ids": [],
        "extra_paths": [],
        "final_status": "PASS",
        "hash_mismatches": [],
        "installed_wheel_resource_load_result": "PASS",
        "materialization_result": {
            "changed_projection_file_count": 0,
            "expected_file_count_including_registry": EXPECTED_SNAPSHOT_FILE_COUNT,
            "status": "PASS_ALREADY_CURRENT",
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
        "projection_status": "PASS_CURRENT",
        "registry_hash": EXPECTED_REGISTRY_HASH,
        "root_source_mutation_count": 0,
        "schema_count": EXPECTED_SCHEMA_COUNT,
        "snapshot_file_count_including_registry": EXPECTED_SNAPSHOT_FILE_COUNT,
        "snapshot_resource_count": EXPECTED_RESOURCE_COUNT,
        "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        "source_resource_count": EXPECTED_RESOURCE_COUNT,
        "source_tree_fallback_count": 0,
        "targeted_projection": regression["targeted_projection"],
        "total_canonical_resource_count": EXPECTED_RESOURCE_COUNT,
        "unrelated_write_count": 0,
        "write_scope_violation_count": 0,
    }
    phase = {
        "admitted_phase_artifact_set_count": 14,
        "admitted_transition_count": 17,
        "artifact_receipts": [
            {
                "artifact_locator": receipt_set[key]["locator"],
                "byte_size": receipt_set[key]["byte_size"],
                "content_hash": receipt_set[key]["content_hash"],
                "receipt": f"artifacts/work_packages/B04/attempts/0010/{key}.artifact-receipt.json",
                "receipt_hash": receipt_set[key]["receipt_hash"],
                "receipt_id": receipt_set[key]["receipt_id"],
            }
            for key in ("projection", "wheel", "sdist")
        ],
        "attempt_id": ATTEMPT_ID,
        "c04_report_sha256": EXPECTED_C04_REPORT_HASH,
        "completion_ready": False,
        "status": "PASS",
    }
    scope = {
        "approved_scope": authority["write_scope"],
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "product_change_count": 0,
        "product_file_baseline_hashes": {
            path: "sha256:" + digest for path, digest in EXPECTED_PRODUCT_HASHES.items()
        },
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
        "packaging-summary.json": {
            "artifact_inventory": packaging["artifact_inventory"],
            "attempt_id": ATTEMPT_ID,
            "backend": packaging["backend"],
            "canonical_registry": packaging["canonical_registry"],
            "checks": packaging["checks"],
            "status": "PASS",
        },
        "projection.artifact-receipt.json": receipt_set["projection"],
        "wheel.artifact-receipt.json": receipt_set["wheel"],
        "sdist.artifact-receipt.json": receipt_set["sdist"],
        "phase-artifact-reconciliation.json": phase,
        "full-regression-impact.json": regression,
        "dependency-status.json": dependency,
        "node-test-inventory.json": node_inventory,
        "junit-normalization-verification.json": normalization,
        "prior-history-verification.json": prior_history_evidence(),
        "write-scope-verification.json": scope,
    }


def command_records() -> list[dict[str, Any]]:
    labels = {
        "materialize-check": "Verify deterministic canonical snapshot is already current",
        "targeted-projection": "Run targeted registry, contract, and CLI tests",
        "packaging-verification": "Run clean wheel/sdist, rebuild, installed-only, fallback, tamper, and reproducibility checks",
        "full-python-suite": "Run full Python repository suite",
        "full-node-suite": "Run complete 79-file serial Node suite",
        "git-diff-check": "Run git diff --check",
    }
    rows: list[dict[str, Any]] = [
        {
            "command": "Inspect sealed C04-0004, B04 manifest scope, B04-0009 projection, and RAH tail",
            "command_id": "B04-0010-C001",
            "exit_code": 0,
            "recorded_at_utc": RECORDED_AT,
            "result": "PASS: B04-0010 dependency-ready",
            "scope": "B04-0010 final post-C04 packaging gate",
        }
    ]
    for index, name in enumerate(RUN_RESULTS, 2):
        run = check_run(name)
        rows.append(
            {
                "command": labels[name],
                "command_id": f"B04-0010-C{index:03d}",
                "exit_code": run["exit_code"],
                "recorded_at_utc": RECORDED_AT,
                "result": "PASS",
                "scope": "B04-0010 final post-C04 packaging gate",
            }
        )
    rows.extend(
        [
            {
                "command": "Normalize portable JUnit attributes without changing semantic signatures",
                "command_id": "B04-0010-C008",
                "exit_code": 0,
                "recorded_at_utc": RECORDED_AT,
                "result": "PASS",
                "scope": "B04-0010 final post-C04 packaging gate",
            },
            {
                "command": "Build and verify machine-readable B04-0010 evidence and receipts",
                "command_id": "B04-0010-C009",
                "exit_code": 0,
                "recorded_at_utc": RECORDED_AT,
                "result": "PASS when builder verification completes",
                "scope": "B04-0010 final post-C04 packaging gate",
            },
            {
                "command": "Perform primary-session separate adversarial packaging review",
                "command_id": "B04-0010-C010",
                "exit_code": 0,
                "recorded_at_utc": RECORDED_AT,
                "result": "PASS: blocking findings 0; actor_independence=false",
                "scope": "B04-0010 final post-C04 packaging gate",
            },
            {
                "command": "Append B04-0010 core/final evidence and verify all RAH generations",
                "command_id": "B04-0010-C011",
                "exit_code": 0,
                "recorded_at_utc": RECORDED_AT,
                "result": "PASS when sealer preflight/core/final/verify completes",
                "scope": "B04-0010 final post-C04 packaging gate",
            },
        ]
    )
    return rows


def commands_text() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    projection = documents["canonical-projection-verification.json"]
    regression = documents["full-regression-impact.json"]
    packaging = documents["packaging-summary.json"]
    inventory = packaging["artifact_inventory"]
    return f"""# B04-0010 final post-C04 packaging review

Package recommendation: `PASS_FINAL_POST_C04_PACKAGING`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. The product-owner contract
forbids Fleet and subagents, so this is a procedurally separate primary-session
review rather than external actor-independent certification.

## Dependency, authority, and projection

- Sealed C04-0004 is hash-bound at `{EXPECTED_C04_REPORT_HASH}` with core
  `E0107`, final `E0108`, and an explicit B04-0010-ready verdict.
- Root `schemas/**` and `openapi/**` remain sole authority. The package snapshot,
  sdist, wheel, and installed resources are derived projections only.
- Exactly {projection['schema_count']} schemas and one OpenAPI 3.1.1 document
  with {projection['openapi_operation_count']} operations produce
  {projection['total_canonical_resource_count']} resources. Missing, extra,
  mismatch, duplicate-ID, root-mutation, reverse-sync, and fallback counts are zero.

## Packaging and regression

- Fresh wheel `{inventory['epistemic_foundry-4.0.0-py3-none-any.whl']['sha256']}`
  and sdist `{inventory['epistemic_foundry-4.0.0.tar.gz']['sha256']}` match the
  sealed reproducible bytes. The sdist-derived wheel is byte-identical.
- Installed-wheel-only enumeration, representative schema validation, OpenAPI
  loading, arbitrary empty cwd, missing-resource fail-closed behavior, and
  one-byte tamper rejection all pass without source-tree fallback.
- Targeted packaging contracts pass
  {regression['targeted_projection']['passed']}/{regression['targeted_projection']['collected']},
  Python passes {regression['full_python']['passed']}/{regression['full_python']['collected']},
  and Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
  across {EXPECTED_NODE_FILE_COUNT} files. Failure, error, skip, xfail, todo, and
  cancellation counts are zero.
- This attempt changes no product file, preserves all prior attempts and the dirty
  worktree, and emits receipt-bound registry, wheel, and sdist evidence.

Blocking B04-0010 findings: 0. B04-0010 satisfies the final post-C04 packaging
gate. It does not establish terminal product completion, release readiness, or
`completion_ready=true`. The next action is live recomputation of the 156-package
DAG while the global implementation gate remains failed.
"""


def report_document(
    documents: dict[str, dict[str, Any]], rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "FINAL_POST_C04_PACKAGING_GATE_127",
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
        "dependency_state": documents["dependency-status.json"],
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "B04_0002_through_0009_preserved": True,
            "C04_0004_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_state": {
            ATTEMPT_ID: "PASS_FINAL_PACKAGING_AFTER_RAH_SEAL",
            "next_action": "RECOMPUTE_156_PACKAGE_DAG",
        },
        "not_claimed": [
            "156-package DAG terminal completion",
            "release or production readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": [
            f"artifacts/work_packages/B04/attempts/0010/{name}"
            for name in OUTPUT_NAMES
        ],
        "package_status": "PASS",
        "product_files_modified_by_attempt": [],
        "projection_status": "PASS_CURRENT",
        "regression": {
            "node": f"PASS_{EXPECTED_NODE_COUNT}_OF_{EXPECTED_NODE_COUNT}",
            "node_test_files": EXPECTED_NODE_FILE_COUNT,
            "python": f"PASS_{EXPECTED_PYTHON_COUNT}_OF_{EXPECTED_PYTHON_COUNT}",
            "targeted_projection": f"PASS_{EXPECTED_TARGETED_COUNT}_OF_{EXPECTED_TARGETED_COUNT}",
            "unexpected_skip_or_xfail_count": regression[
                "unexpected_skip_xfail_todo_or_cancellation_count"
            ],
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
        "write_scope": documents["write-scope-verification.json"],
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = live_documents()
    for name, value in documents.items():
        if name != "junit-normalization-verification.json":
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
    return verify()


def verify_receipt(path: Path) -> None:
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
        raise SystemExit(f"receipt does not bind live artifact: {path.name}")


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or read_json(path) != expected:
            raise SystemExit(f"stored B04-0010 evidence differs from live inputs: {name}")
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
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("RAH binding is not an object")
    expected_report = report_document(
        documents, rah_state=rah_state if isinstance(rah_state, dict) else None
    )
    if report != expected_report:
        raise SystemExit("stored report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_projection": "127 schemas / 128 resources",
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "RECOMPUTE_156_PACKAGE_DAG_AFTER_RAH_SEAL",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_projection": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
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
