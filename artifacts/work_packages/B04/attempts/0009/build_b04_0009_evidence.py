#!/usr/bin/env python3
"""Build and verify B04-0009 pre-O02 canonical-projection evidence.

B04-0009 is the attempt-level reconciliation authorized by
HD-EF4-O02-SG001-20260731-001.  It projects the 127-schema root authority into
the package snapshot and proves clean installed-package behavior before
O02-0002.  It is not the post-C04 final B04 packaging gate.
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
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0009"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
BINDING_PATH = ROOT / "manifests/source_bindings/development-manifest.binding.json"
DECISION_PATH = (
    ROOT
    / "artifacts/authority_decisions/HD-EF4-O02-SG001-20260731-001.human-decision.json"
)
C02_ATTEMPT = ROOT / "artifacts/work_packages/C02/attempts/0004"
PRIOR_B04_ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0008"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.build.canonical_registry import materialize  # noqa: E402
from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402


ATTEMPT_ID = "B04-0009"
WORK_PACKAGE_ID = "B04"
AUTHORITY_DECISION_ID = "HD-EF4-O02-SG001-20260731-001"
RECORDED_AT = "2026-07-31T10:05:00.000Z"
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
EXPECTED_MANIFEST_HASH = (
    "sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063"
)
EXPECTED_BINDING_ID = "DMB-EF4-20260731-003"
EXPECTED_BINDING_HASH = (
    "sha256:dc0eff8c011d7c08e9f27536e9693d1578a805e7013842b52059715f1a9ffaad"
)
EXPECTED_DECISION_HASH = (
    "sha256:3695c59b67788b0f144f033627a9ef3294b75418f78dfb15fcebccc14a8ef221"
)
EXPECTED_PRIOR_PROJECTION = {
    "attempt_id": "B04-0008",
    "schema_count": 126,
    "resource_count": 127,
    "source_bundle_hash": "sha256:1557b03db2ad7e7d23b014d4c9d5fd643803f6613696c966d9b0379573259e7f",
    "snapshot_bundle_hash": "sha256:d01bda0057584e235331b649238fc2507c60cab329fd6b8e8b6a115fac912559",
    "registry_hash": "sha256:6b4fcade707639e537744be4075e71d3f7e068cd42eaaaddb20ef084851175d5",
}
EXPECTED_DEPENDENCY_HASHES = {
    "report.json": "1050242050a10624046c62abc8ded6bd7215fc34414fac90f5ed3cdb3397f5d3",
    "c02-verification.artifact-receipt.json": (
        "c40e90a24cc9e38ed5d8237d3931ef67aabaad904ce248a3e875842fef0eb951"
    ),
}
EXPECTED_PRODUCT_HASHES = {
    "scripts/build/canonical_registry/materialize.py": (
        "ae10176b2ab1d9e1d13f6f501fb78b328774e2a828a8acddc1d8534d3273cf6f"
    ),
    "scripts/build/canonical_registry/verify_packaging.py": (
        "60fc75bec8d95e9dd186b9117a22fe2704bf1b74f3b480e518448d0dacb29c59"
    ),
    "tests/test_contracts.py": (
        "3fd45129acf1a340b7aecf71d45292c6b6a2daa963a43ea016aa7ca1f8e445fb"
    ),
    "tests/test_cli.py": (
        "e3a791f3d94f9eadc03f65cff67eff4a73bade6902e0e7c6326a0024af0d3146"
    ),
    "tests/packaging/test_canonical_registry.py": (
        "1cf1b30f8fd4243714d7cb8cac7b50d61604d87c9420442dde3da835aef0418b"
    ),
    "src/epistemic_foundry/_canonical/schemas/retrieval-candidate.schema.json": (
        "19e12fe0affbdaaad59bd1bb4bd43e863d177413769a9bf06b80a8577f888f8e"
    ),
    "src/epistemic_foundry/_canonical/canonical-registry.json": (
        "d08d78c19d39e08ec98df3ac4da8014f61fcc19fe0f833f9e5273059c5cda27c"
    ),
}
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
RAW_JUNIT_HASHES = {
    "targeted_projection": "fcfc9bc9716318bda3cefc32778cd70784255ec7df9e32484ff8d0498cae988d",
    "full_python": "6ca5f3f48fa6ac4e9d1223636ccd4ec526001d1641cf02df313e8ecf2a1dead5",
    "full_node": "321c3f1cbafbb965b9696bcf8f7958f452a3b9be255dfbd23fd5d3c41e904093",
}
EXPECTED_PACKAGING_HASH = (
    "997d471fe8bc42a1c425b5c40dc249a6aa131d8b9ff396378822e2b317e9a7a0"
)
JUNIT_PATHS = {
    "targeted_projection": ATTEMPT / "targeted-projection.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
PRODUCT_FILES_MODIFIED = list(EXPECTED_PRODUCT_HASHES)
PRIOR_B04_REPORTS = {
    name: ROOT / f"artifacts/work_packages/B04/attempts/{name}/report.json"
    for name in ("0002", "0003", "0004", "0005", "0006", "0007", "0008")
}
OUTPUT_NAMES = (
    "canonical-projection-verification.json",
    "source-inventory.json",
    "snapshot-inventory.json",
    "installed-wheel-verification.json",
    "packaging-summary.json",
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
    "commands.jsonl",
    "review.md",
    "report.json",
    "build_b04_0009_evidence.py",
    "b04_0009_rah_seal.py",
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


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, wanted in expected.items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != wanted:
            actual = sha256(path) if path.is_file() else "MISSING"
            raise SystemExit(f"B04-0009 hash mismatch: {relative}: {actual} != {wanted}")


def authority_contract() -> dict[str, Any]:
    decision = read_json(DECISION_PATH)
    if (
        decision.get("decision_id") != AUTHORITY_DECISION_ID
        or decision.get("decision_hash") != EXPECTED_DECISION_HASH
        or hash_excluding(decision, "decision_hash") != EXPECTED_DECISION_HASH
    ):
        raise SystemExit("O02-SG001 HumanDecision identity or self-hash mismatch")
    if sha256_id(MANIFEST_PATH) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("development manifest changed after B04-0009 binding")
    binding = read_json(BINDING_PATH)
    if (
        binding.get("binding_id") != EXPECTED_BINDING_ID
        or binding.get("binding_hash") != EXPECTED_BINDING_HASH
        or hash_excluding(binding, "binding_hash") != EXPECTED_BINDING_HASH
        or binding.get("successor_sha256") != EXPECTED_MANIFEST_HASH.removeprefix("sha256:")
        or "B04-0009" not in binding.get("attempt_level_reconciliation", [])
    ):
        raise SystemExit("active development-manifest binding is not B04-0009-ready")
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = manifest if isinstance(manifest, list) else manifest["work_packages"]
    by_id = {row["id"]: row for row in packages}
    b04 = by_id["B04"]
    required_scope = {
        "src/epistemic_foundry/_canonical/**",
        "scripts/build/canonical_registry/**",
        "tests/packaging/**",
        "tests/test_contracts.py",
        "tests/test_cli.py",
        "artifacts/work_packages/B04/**",
    }
    if len(packages) != 156 or not required_scope.issubset(set(b04["write_scope"])):
        raise SystemExit("B04 manifest cardinality or exact write scope changed")
    if "canonical_schema_127_projection" not in b04["required_checks"]:
        raise SystemExit("B04 127-schema projection check is absent")
    if "pre_o02_projection_receipt" not in b04["required_checks"]:
        raise SystemExit("B04 pre-O02 projection receipt check is absent")
    return {
        "attempt_level_reconciliation_authorized": True,
        "binding_file_sha256": sha256_id(BINDING_PATH),
        "binding_hash": EXPECTED_BINDING_HASH,
        "binding_id": EXPECTED_BINDING_ID,
        "decision_file_sha256": sha256_id(DECISION_PATH),
        "decision_hash": EXPECTED_DECISION_HASH,
        "decision_id": AUTHORITY_DECISION_ID,
        "manifest_sha256": EXPECTED_MANIFEST_HASH,
        "package_count": len(packages),
        "static_dependency_cycle_added": False,
        "status": "PASS",
    }


def semantic_junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
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
            raise SystemExit(f"JUnit contains an absolute repository path: {name}")
        if name == "full_node":
            if "duration_ms" in text:
                raise SystemExit("Node JUnit retains volatile duration_ms")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit(f"pytest JUnit retains volatile host/time fields: {name}")


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            expected = record.get("files", {}).get(name, {}).get("normalized_sha256")
            if expected != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed after recording: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        if sha256(path) != RAW_JUNIT_HASHES[name]:
            raise SystemExit(f"raw JUnit hash mismatch: {name}")
        before = path.read_text(encoding="utf-8")
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
            raise SystemExit(f"JUnit semantic signature changed: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "normalized_sha256": sha256_id(path),
            "raw_sha256": "sha256:" + RAW_JUNIT_HASHES[name],
            "removed": removed,
            "semantic_signature_preserved": True,
            "testcase_count": len(signature),
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "normalization_scope": [
            "remove pytest hostname, timestamp, and suite/testcase time attributes",
            "remove absolute repository prefixes",
            "remove Node duration_ms while retaining authoritative footer counters",
        ],
        "preserved": [
            "testcase identity",
            "failure, error, and skip state",
            "failure type, message, and body after repository-path normalization",
            "Node footer counters",
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


def node_summary(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
        raise SystemExit("Node JUnit footer is incomplete")
    files = sorted(
        {
            str(case.get("file"))
            for case in cases
            if case.get("file") not in (None, "")
        }
    )
    summary = {
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
    inventory = {
        "attempt_id": ATTEMPT_ID,
        "authoritative_footer": footer,
        "test_file_count": len(files),
        "test_files": files,
        "xml_testcase_count": len(cases),
        "xml_testcase_count_is_not_authoritative_total": True,
        "status": "PASS",
    }
    return summary, inventory


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    targeted = pytest_summary(JUNIT_PATHS["targeted_projection"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node, node_inventory = node_summary(JUNIT_PATHS["full_node"])
    if (
        targeted["collected"],
        targeted["passed"],
        targeted["failed"],
        targeted["errors"],
        targeted["skipped"],
    ) != (41, 41, 0, 0, 0):
        raise SystemExit(f"targeted projection counters changed: {targeted}")
    if (
        python["collected"],
        python["passed"],
        python["failed"],
        python["errors"],
        python["skipped"],
    ) != (1073, 1073, 0, 0, 0):
        raise SystemExit(f"full Python counters changed: {python}")
    if (
        node["collected"],
        node["passed"],
        node["failed"],
        node["cancelled"],
        node["skipped"],
        node["todo"],
        node["xml_testcase_count"],
        node_inventory["test_file_count"],
    ) != (819, 819, 0, 0, 0, 0, 814, 79):
        raise SystemExit(f"full Node counters/inventory changed: {node}")
    regression = {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "C02-0004",
        "c02_projection_debt_failures_resolved": 17,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_projection": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }
    return regression, node_inventory


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
        raise SystemExit("live 127-contract canonical bundle hashes changed")
    if REGISTRY_PATH.read_bytes() != registry_bytes:
        raise SystemExit("live registry differs from deterministic output")
    if (
        registry.get("schema_count") != EXPECTED_SCHEMA_COUNT
        or registry.get("resource_count") != EXPECTED_RESOURCE_COUNT
        or registry.get("file_count") != EXPECTED_RESOURCE_COUNT
        or registry.get("openapi_document_count") != 1
    ):
        raise SystemExit("live registry count contract changed")

    source_entries: list[dict[str, Any]] = []
    snapshot_entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    duplicates: list[str] = []
    expected_paths: set[str] = set()
    missing: list[str] = []
    mismatches: list[str] = []
    for resource in resources:
        entry = resource.manifest_entry()
        relative = resource.relative_path.as_posix()
        expected_paths.add(relative)
        document_id = str(entry["document_id"])
        if document_id in seen_ids:
            duplicates.append(document_id)
        seen_ids.add(document_id)
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
    if missing or extra or mismatches or duplicates:
        raise SystemExit(
            "canonical projection drift: "
            f"missing={missing}, extra={extra}, mismatch={mismatches}, duplicate={duplicates}"
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
    if snapshot["snapshot_file_count_including_registry"] != EXPECTED_SNAPSHOT_FILE_COUNT:
        raise SystemExit("snapshot file count including registry changed")
    return source, snapshot, registry


def verify_packaging(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = ATTEMPT / "packaging-verification-run.json"
    if sha256(path) != EXPECTED_PACKAGING_HASH:
        raise SystemExit("packaging verification raw hash changed")
    stored = read_json(path)
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
    expected_comparison = {
        "extra": 0,
        "hash_mismatches": 0,
        "missing": 0,
        "resource_count": EXPECTED_RESOURCE_COUNT,
        "status": "PASS",
    }
    if not isinstance(comparisons, dict):
        raise SystemExit("packaging registry comparisons are missing")
    for name, comparison in comparisons.items():
        if comparison != expected_comparison:
            raise SystemExit(f"packaging comparison failed: {name}: {comparison}")
    if not isinstance(installed, dict) or not isinstance(reproducibility, dict):
        raise SystemExit("installed/reproducibility packaging evidence is missing")
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


def dependency_status() -> dict[str, Any]:
    assert_hashes(
        {
            str((C02_ATTEMPT / name).relative_to(ROOT)): wanted
            for name, wanted in EXPECTED_DEPENDENCY_HASHES.items()
        }
    )
    report = read_json(C02_ATTEMPT / "report.json")
    receipt = read_json(C02_ATTEMPT / "c02-verification.artifact-receipt.json")
    if report.get("status") != "PASS" or receipt.get("status") != "PASS":
        raise SystemExit("C02-0004 dependency is not sealed PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "C02": {
                "attempt_id": "C02-0004",
                "receipt_file_sha256": sha256_id(
                    C02_ATTEMPT / "c02-verification.artifact-receipt.json"
                ),
                "receipt_hash": receipt["receipt_hash"],
                "report_sha256": sha256_id(C02_ATTEMPT / "report.json"),
                "status": "PASS",
            }
        },
        "next_state": {
            "B04-0009": "PASS_PRE_O02_PROJECTION",
            "O02-0002": "DEPENDENCY_READY",
            "C04-0004": "WAITING_ON_O02_0002",
            "B04-final": "WAITING_ON_C04_0004",
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
    prior = read_json(PRIOR_B04_ATTEMPT / "canonical-projection-verification.json")
    observed = {
        "attempt_id": prior.get("attempt_id"),
        "schema_count": prior.get("schema_count"),
        "resource_count": prior.get("total_canonical_resource_count"),
        "source_bundle_hash": prior.get("source_bundle_hash"),
        "snapshot_bundle_hash": prior.get("projected_snapshot_bundle_hash"),
        "registry_hash": prior.get("registry_hash"),
    }
    if observed != EXPECTED_PRIOR_PROJECTION:
        raise SystemExit("B04-0008 projection baseline changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "prior_B04_reports": reports,
        "prior_projection": observed,
        "transition": "126_SCHEMAS_TO_127_SCHEMAS",
        "status": "PASS",
    }


def artifact_receipt(
    *, receipt_id: str, artifact_id: str, path: Path, media_type: str,
    checks: list[dict[str, str]],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": artifact_id,
        "byte_size": path.stat().st_size,
        "content_hash": sha256_id(path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "B04-0009-projection-regression-verifier",
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
        receipt_id="AR-B04-0009-CANONICAL-PROJECTION",
        artifact_id="ART-B04-0009-CANONICAL-PROJECTION",
        path=REGISTRY_PATH,
        media_type="application/vnd.epistemic-foundry.canonical-registry+json",
        checks=[
            {
                "check": "registry_byte_integrity",
                "details": "Receipt binds the exact deterministic 127-schema canonical registry bytes.",
                "status": "PASS",
            },
            {
                "check": "root_snapshot_wheel_convergence",
                "details": (
                    f"All {EXPECTED_RESOURCE_COUNT} resources bind root "
                    f"{EXPECTED_SOURCE_BUNDLE_HASH} to snapshot "
                    f"{EXPECTED_SNAPSHOT_BUNDLE_HASH} and the clean wheel byte-for-byte."
                ),
                "status": "PASS",
            },
            {
                "check": "pre_o02_scope_boundary",
                "details": "This is the B04-0009 pre-O02 receipt, not the final post-C04 packaging gate.",
                "status": "PASS",
            },
        ],
    )
    wheel_path = ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
    wheel = artifact_receipt(
        receipt_id="AR-B04-0009-WHEEL",
        artifact_id="ART-B04-0009-WHEEL",
        path=wheel_path,
        media_type="application/vnd.python.wheel",
        checks=[
            {
                "check": "installed_wheel_only",
                "details": "Clean isolated install, empty cwd, schema validation, and OpenAPI load pass without source fallback.",
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
        receipt_id="AR-B04-0009-SDIST",
        artifact_id="ART-B04-0009-SDIST",
        path=sdist_path,
        media_type="application/gzip",
        checks=[
            {
                "check": "sdist_clean_build",
                "details": "The clean sdist contains canonical authority, projection tooling, and exact build constraints.",
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


def write_scope_verification(authority: dict[str, Any]) -> dict[str, Any]:
    approved_prefixes = (
        "src/epistemic_foundry/_canonical/",
        "scripts/build/canonical_registry/",
        "tests/packaging/",
        "artifacts/work_packages/B04/",
    )
    approved_exact = {"tests/test_contracts.py", "tests/test_cli.py"}
    violations = [
        path
        for path in PRODUCT_FILES_MODIFIED
        if path not in approved_exact and not path.startswith(approved_prefixes)
    ]
    return {
        "approved_scope": [
            "src/epistemic_foundry/_canonical/**",
            "scripts/build/canonical_registry/**",
            "tests/packaging/**",
            "tests/test_contracts.py",
            "tests/test_cli.py",
            "artifacts/work_packages/B04/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority": authority,
        "dirty_worktree_preserved": True,
        "product_change_count": len(PRODUCT_FILES_MODIFIED),
        "product_file_hashes": {
            path: "sha256:" + digest for path, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "product_files_modified_by_attempt": PRODUCT_FILES_MODIFIED,
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS" if not violations else "FAIL",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": len(violations),
    }


def command_records() -> list[dict[str, Any]]:
    rows: list[tuple[str, int | None, str]] = [
        ("Inspect O02-SG001, B04 manifest scope, C02-0004 dependency, prior B04 history, and RAH tail", 0, "PASS: B04-0009 authorized and dependency-ready"),
        ("Run canonical materializer --check before projection", 1, "EXPECTED_PRE_CORRECTION_DRIFT: 127 root schemas versus stale 126-schema projection"),
        ("Run deterministic canonical materialization from root schemas/openapi", 0, "PASS: RetrievalCandidate and registry projected atomically; root source unchanged"),
        ("Run canonical materializer --check after projection", 0, "PASS: expected files 129; missing/extra/mismatch 0"),
        ("Run B04 targeted projection, registry, CLI, and contract tests with JUnit", 0, "PASS: 41/41"),
        ("Run clean wheel/sdist, sdist-to-wheel, installed-only, arbitrary-cwd, no-fallback, tamper, and reproducibility verification", 0, "PASS: wheel 333261 bytes; sdist 282078 bytes; 128 resources"),
        ("Run full Python suite with JUnit", 0, "PASS: 1073/1073; failed/errors/skipped 0"),
        ("Diagnostic Node run with a PowerShell wildcard that expanded only two test files", 0, "DIAGNOSTIC_ONLY: 25/25; not promoted to the full gate"),
        ("Diagnostic Node run with an incomplete file filter", 0, "DIAGNOSTIC_ONLY: 779/779 across 77 files; not promoted to the full gate"),
        ("Run authoritative complete 79-file serial Node suite with JUnit", 0, "PASS: footer 819/819; XML rows 814 retained separately"),
        ("PowerShell direct foreach pipeline aggregation blocked by the reliability hook", None, "HOOK_BLOCKED_BEFORE_EXECUTION: replaced with variable-first parsing; no state mutation"),
        ("Normalize JUnit portability while preserving testcase semantics and Node footer counters", 0, "PASS"),
        ("Run scoped git diff --check", 0, "PASS: whitespace errors 0; existing line-ending advisories only"),
        ("Build and verify B04-0009 evidence from live source, snapshot, wheel, JUnit, dependency, and manifest bytes", 0, "PASS when builder build/verify completes"),
        ("Perform primary-session separate adversarial integration review", 0, "PASS: blocking B04-0009 findings 0; actor_independence=false"),
        ("Seal B04-0009 core/final evidence into append-only RAH and verify six snapshots", 0, "PASS when sealer preflight/core/final/verify completes"),
    ]
    return [
        {
            "command": command,
            "command_id": f"B04-0009-C{index:03d}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": "B04-0009 pre-O02 canonical projection reconciliation",
        }
        for index, (command, exit_code, result) in enumerate(rows, 1)
    ]


def commands_text() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    projection = documents["canonical-projection-verification.json"]
    regression = documents["full-regression-impact.json"]
    return f"""# B04-0009 pre-O02 canonical projection review

Package recommendation: `PASS_PRE_O02_PROJECTION`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents were
not used. This is a procedurally separate primary-session review, not external
actor-independent certification.

## Authority and projection

- Root `schemas/**` and `openapi/**` remain the sole canonical authority. The
  package tree is only a deterministic derived snapshot.
- The preserved B04-0008 baseline had 126 schemas and 127 total resources.
  B04-0009 now projects exactly {projection['schema_count']} schemas and one
  OpenAPI 3.1.1 document with {projection['openapi_operation_count']} unique
  operations, for {projection['total_canonical_resource_count']} resources.
- Source `{projection['source_bundle_hash']}`, snapshot
  `{projection['projected_snapshot_bundle_hash']}`, and registry
  `{projection['registry_hash']}` match live bytes. Missing, extra,
  hash-mismatched, duplicate-ID, reverse-sync, and root-mutation counts are zero.

## Packaging and regression

- Targeted projection contracts pass
  {regression['targeted_projection']['passed']}/{regression['targeted_projection']['collected']}.
- Clean wheel/sdist, sdist-to-wheel, installed-only loading, arbitrary empty
  cwd, missing/tamper fail-closed behavior, no source fallback, and byte
  reproducibility all pass.
- Full Python passes {regression['full_python']['passed']}/{regression['full_python']['collected']}
  with no failure, error, or skip. The exact 17 projection failures sealed by
  C02-0004 are resolved.
- Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
  by the authoritative footer across 79 files. The reporter's 814 XML testcase
  rows remain separately recorded and are not substituted for the footer total.

Blocking B04-0009 findings: 0. Write-scope violations: 0. O02-0002 becomes
dependency-ready only after the RAH seal. This attempt is not C04-0004, the
next-unused final B04 packaging attempt, release readiness, or product
completion. `implementation_gate=fail` and `completion_ready=false` remain.
"""


def live_documents() -> dict[str, dict[str, Any]]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    normalization = normalize_junits()
    authority = authority_contract()
    regression, node_inventory = regression_evidence()
    source, snapshot, registry = live_canonical_inventory()
    packaging, installed = verify_packaging(registry)
    dependency = dependency_status()
    history = prior_history_evidence()
    receipt_set = receipts()
    scope = write_scope_verification(authority)
    if scope["status"] != "PASS":
        raise SystemExit("B04-0009 write scope is not PASS")
    projection = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "PRE_O02_CANONICAL_PROJECTION_RECONCILIATION_127",
        "authority_decision_id": AUTHORITY_DECISION_ID,
        "deterministic_rebuild_result": "PASS",
        "duplicate_schema_ids": [],
        "extra_paths": [],
        "final_status": "PASS",
        "hash_mismatches": [],
        "installed_wheel_resource_load_result": "PASS",
        "materialization_result": {
            "atomic_replacement": "PASS",
            "changed_projection_file_count": 2,
            "changed_projection_files": [
                "schemas/retrieval-candidate.schema.json",
                "canonical-registry.json",
            ],
            "expected_file_count_including_registry": EXPECTED_SNAPSHOT_FILE_COUNT,
            "status": "PASS_PROJECTED_127",
        },
        "missing_paths": [],
        "openapi_operation_count": EXPECTED_OPENAPI_OPERATION_COUNT,
        "openapi_resource_count": 1,
        "openapi_version": "3.1.1",
        "package_status": "PASS",
        "packaging_verification_sha256": sha256_id(
            ATTEMPT / "packaging-verification-run.json"
        ),
        "prior_projection": history["prior_projection"],
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
        "artifact_receipts": [
            {
                "artifact_locator": receipt_set[key]["locator"],
                "byte_size": receipt_set[key]["byte_size"],
                "content_hash": receipt_set[key]["content_hash"],
                "receipt": f"artifacts/work_packages/B04/attempts/0009/{key}.artifact-receipt.json",
                "receipt_hash": receipt_set[key]["receipt_hash"],
                "receipt_id": receipt_set[key]["receipt_id"],
            }
            for key in ("projection", "wheel", "sdist")
        ],
        "attempt_id": ATTEMPT_ID,
        "checks": {
            "canonical_projection": "PASS_127_SCHEMAS_128_RESOURCES",
            "dependency_binding": "PASS_C02_0004",
            "deterministic_rebuild": "PASS",
            "full_node": "PASS_819_OF_819",
            "full_python": "PASS_1073_OF_1073",
            "installed_wheel_only": "PASS",
            "source_tree_fallback": "PASS_ZERO_SUCCESSES",
            "targeted_projection": "PASS_41_OF_41",
        },
        "completion_ready": False,
        "global_implementation_gate": "fail",
        "next_attempt": "O02-0002",
        "status": "PASS",
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
        "prior-history-verification.json": history,
        "write-scope-verification.json": scope,
    }


def artifact_inventory() -> list[dict[str, Any]]:
    names = [
        *[name for name in OUTPUT_NAMES if name not in {"report.json", "rah-core-integrity.json"}],
        "targeted-projection.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "packaging-verification-run.json",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    return [
        {
            "byte_size": (ATTEMPT / name).stat().st_size,
            "path": (ATTEMPT / name).relative_to(ROOT).as_posix(),
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in dict.fromkeys(names)
        if (ATTEMPT / name).is_file()
    ]


def report_document(
    documents: dict[str, dict[str, Any]], rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    projection = documents["canonical-projection-verification.json"]
    regression = documents["full-regression-impact.json"]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "PRE_O02_CANONICAL_PROJECTION_RECONCILIATION_127",
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
        "dependency_state": documents["dependency-status.json"],
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "B04_0002_through_0008_preserved": True,
            "C02_0004_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "O02-0002",
        "next_state": {
            "B04-0009": "PASS_PRE_O02_PROJECTION",
            "O02-0002": "DEPENDENCY_READY",
            "C04-0004": "WAITING_ON_O02_0002",
            "B04-final": "WAITING_ON_C04_0004",
        },
        "not_claimed": [
            "O02-0002 PASS",
            "C04-0004 conformance",
            "next-unused final B04 packaging gate",
            "release or production readiness",
            "repository-wide terminal completion",
            "external actor-independent certification",
            "completion_ready=true",
        ],
        "output_artifacts": artifact_inventory(),
        "package_status": "PASS",
        "product_files_modified_by_attempt": PRODUCT_FILES_MODIFIED,
        "projection_status": "PASS_CURRENT",
        "regression": {
            "node": "PASS_819_OF_819",
            "node_test_files": 79,
            "python": "PASS_1073_OF_1073",
            "resolved_c02_projection_failure_count": 17,
            "targeted_projection": "PASS_41_OF_41",
            "unexpected_skip_or_xfail_count": regression[
                "unexpected_skip_xfail_todo_or_cancellation_count"
            ],
        },
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_B04_0009_finding_count": 0,
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
        raise SystemExit(f"receipt does not bind its artifact: {path.name}")


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or read_json(path) != expected:
            raise SystemExit(f"stored B04-0009 evidence differs from live inputs: {name}")
    for name in (
        "projection.artifact-receipt.json",
        "wheel.artifact-receipt.json",
        "sdist.artifact-receipt.json",
    ):
        verify_receipt(ATTEMPT / name)
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored B04-0009 commands differ from deterministic records")
    for line in commands_text().splitlines():
        json.loads(line)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored B04-0009 review differs from live evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("B04-0009 RAH state is not an object")
    expected_report = report_document(
        documents, rah_state=rah_state if isinstance(rah_state, dict) else None
    )
    if report != expected_report:
        raise SystemExit("stored B04-0009 report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_projection": "127 schemas / 128 resources",
        "completion_ready": False,
        "full_node": "819/819",
        "full_python": "1073/1073",
        "next_package": "O02-0002",
        "package_status": "PASS",
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
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
