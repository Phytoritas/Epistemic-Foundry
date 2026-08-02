#!/usr/bin/env python3
"""Build and verify B04-0006 projection evidence and its SPEC_GAP boundary.

The 126-schema canonical projection is a verified B04 success.  The full
regression suites subsequently exposed runtime and derived-artifact migration
work for which the active development manifest does not provide a complete
pre-C04 ownership/order contract.  This builder recomputes both facts from
live bytes, JUnit, and the manifest.  It never treats the projection receipt
as evidence that the package or repository regression gate passed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0006"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/build/canonical_registry"))
sys.path.insert(
    0, str(ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation")
)

import materialize  # noqa: E402
import state_store  # noqa: E402
from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402


ATTEMPT_ID = "B04-0006"
SPEC_GAP_ID = "B04-SG002"
AUTHORITY_DECISION_ID = "HD-EF4-C01-SG004-20260730-001"
CREATED_AT = "2026-07-30T10:30:00Z"
EXPECTED_SOURCE_BUNDLE_HASH = (
    "sha256:1557b03db2ad7e7d23b014d4c9d5fd643803f6613696c966d9b0379573259e7f"
)
EXPECTED_SNAPSHOT_BUNDLE_HASH = (
    "sha256:d01bda0057584e235331b649238fc2507c60cab329fd6b8e8b6a115fac912559"
)
EXPECTED_REGISTRY_HASH = (
    "sha256:6b4fcade707639e537744be4075e71d3f7e068cd42eaaaddb20ef084851175d5"
)
EXPECTED_MANIFEST_HASH = (
    "8859303ea2fbe8d71655b2c244daf424a9742d4ce700bb93edddc20e3a06f23b"
)
EXPECTED_BINDING_HASH = (
    "0f87227ec902bf9c3e9b6f33111e2b1fa038323ef57752815239611caf6b273c"
)
EXPECTED_INPUT_HASHES = {
    "capture_projection_inventory.py": "3718360ae871fb4ad154d5a53c928f84603944958c248cf2e013a0d799dd80dc",
    "full-node-suite.junit.xml": "afee774cbcf78278e6fae4ece7eaab60e0ab56e1263429f634c3517d96a6bbf7",
    "full-python-failure-inventory.json": "e2bb4b61032fd7531a348fced3addc7e75ddfba5b883a7bda5bad8e044bd1090",
    "full-python-suite.junit.xml": "791b3713d793ae5fae16e86ba562ecc90aa4f03d0f988921990c5e89a45479b0",
    "packaging-verification-run.json": "401d182c1fe43aa45c2ae898a20d9a078bec10c7d23ba161706a59ed19143517",
    "parse_full_python_failures.py": "ef66c354450d7ecf0fd39a5408515cedabcaf6999655f47e33fbaa81fc30dc9c",
    "snapshot-inventory-postprojection.json": "01ca8f1dd1c6138ec2a8ffad83a66632daab34d2717baac69fbf55b60aaf9878",
    "snapshot-inventory-preprojection.json": "20228ba7efd115e8b4aea3beb7d3911f00725d5f314c4d986c9e2e75448ee3b8",
    "source-inventory-postprojection.json": "98ee294809a1593a93e041d41ee9a2bc89924839d7e0309e5234a8dcc143c913",
    "source-inventory-preprojection.json": "2093e8f5965e7f68e9569010a76d8b63e7a20b48d33013beb00d63500e8fada5",
    "targeted-projection.junit.xml": "84f3205f4f892f7c771ceefc5f6a0e3c4c3f34806263285312a2ad708aeb0f04",
}
DIST = {
    "epistemic_foundry-4.0.0-py3-none-any.whl": {
        "byte_size": 307_863,
        "sha256": "95cc1c1ef09be5cff3271072588e0a1cca98958339e0ff972f3dfeaa93136fb8",
    },
    "epistemic_foundry-4.0.0.tar.gz": {
        "byte_size": 256_787,
        "sha256": "afcff2501eb94514a2e562944e28c628ae098deb01f3b6f6bca3783fe11a4ed8",
    },
}
RUNTIME_PATHS = {
    "src/epistemic_foundry/foundry_kernel/gates.py": (
        "eb7f9ad9bb995dab1390e03cff7618d77da7c659eb7b0038837597b052c36f35"
    ),
    "src/epistemic_foundry/verifier_firewall/firewall.py": (
        "f99f37a0a884038b712a3f6e4f9031b5c943e6ea53d593664b8ff982d173df02"
    ),
}
DERIVED_PATHS = {
    "tests/golden/forge": "F04",
    "plugins/epistemic-foundry/skills/skill-inventory.json": "J02",
    "manifests/source_bindings/development-manifest.binding.json": "S04",
}


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


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def assert_immutable_inputs() -> None:
    for name, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256(ATTEMPT / name)
        if actual != expected:
            raise SystemExit(
                f"B04-0006 immutable input changed: {name}: {actual} != {expected}"
            )
    for name, expected in DIST.items():
        path = ATTEMPT / "dist" / name
        observed = {"byte_size": path.stat().st_size, "sha256": sha256(path)}
        if observed != expected:
            raise SystemExit(f"B04-0006 distribution bytes changed: {name}: {observed}")
    if sha256(MANIFEST_PATH) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("development manifest changed after B04-0006 regression capture")
    binding = ROOT / "manifests/source_bindings/development-manifest.binding.json"
    if sha256(binding) != EXPECTED_BINDING_HASH:
        raise SystemExit("S04 development-manifest binding changed after capture")
    for relative, expected in RUNTIME_PATHS.items():
        if sha256(ROOT / relative) != expected:
            raise SystemExit(f"unowned runtime path changed after capture: {relative}")


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
        raise SystemExit("live canonical root hash changed after B04-0006 projection")
    if REGISTRY_PATH.read_bytes() != registry_bytes:
        raise SystemExit("live canonical registry differs from deterministic output")
    if registry.get("schema_count") != 126 or registry.get("resource_count") != 127:
        raise SystemExit("canonical registry is not 126 schemas plus one OpenAPI resource")
    if registry.get("openapi_document_count") != 1:
        raise SystemExit("canonical registry OpenAPI count is not one")

    source_entries: list[dict[str, Any]] = []
    snapshot_entries: list[dict[str, Any]] = []
    document_ids: set[str] = set()
    duplicates: list[str] = []
    expected_paths: set[str] = set()
    missing: list[str] = []
    mismatches: list[str] = []
    for resource in resources:
        manifest_entry = resource.manifest_entry()
        relative = resource.relative_path.as_posix()
        expected_paths.add(relative)
        document_id = str(manifest_entry["document_id"])
        if document_id in document_ids:
            duplicates.append(document_id)
        document_ids.add(document_id)
        source_entries.append(
            {
                "byte_size": len(resource.content),
                "document_id": document_id,
                "media_type": manifest_entry["media_type"],
                "path": relative,
                "projection_target_path": manifest_entry["package_path"],
                "sha256": sha256_bytes(resource.content),
            }
        )
        target = SNAPSHOT / Path(*resource.relative_path.parts)
        if not target.is_file():
            missing.append(relative)
            continue
        content = target.read_bytes()
        observed_hash = sha256_bytes(content)
        snapshot_entries.append(
            {
                "byte_size": len(content),
                "document_id": document_id,
                "package_path": relative,
                "sha256": observed_hash,
                "source_path": manifest_entry["source_path"],
            }
        )
        if content != resource.content or observed_hash != manifest_entry["sha256"]:
            mismatches.append(relative)
    actual_paths = {
        path.relative_to(SNAPSHOT).as_posix()
        for path in SNAPSHOT.rglob("*")
        if path.is_file() and path.name != "canonical-registry.json"
    }
    extra = sorted(actual_paths - expected_paths)
    missing = sorted(set(missing) | (expected_paths - actual_paths))
    if missing or extra or mismatches or duplicates:
        raise SystemExit(
            "canonical projection drift: "
            f"missing={missing}, extra={extra}, mismatches={mismatches}, "
            f"duplicate_ids={duplicates}"
        )

    openapi = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    operation_ids = re.findall(r"^\s+operationId:\s*([^\s#]+)\s*$", text, re.M)
    if not text.startswith("openapi: 3.1.1\n"):
        raise SystemExit("OpenAPI authority is not version 3.1.1")
    if len(operation_ids) != 33 or len(set(operation_ids)) != 33:
        raise SystemExit("OpenAPI operation inventory is not 33 unique operations")

    source = {
        "attempt_id": ATTEMPT_ID,
        "duplicate_schema_ids": duplicates,
        "entries": source_entries,
        "openapi": {
            "operation_count": 33,
            "operation_ids_unique": True,
            "path": "openapi/epistemic-foundry-v1.openapi.yaml",
            "sha256": sha256_id(openapi),
            "version": "3.1.1",
        },
        "schema_count": 126,
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
        "projection_file_count_including_registry": len(snapshot_entries) + 1,
        "registry": {
            "path": "src/epistemic_foundry/_canonical/canonical-registry.json",
            "resource_count": registry["resource_count"],
            "schema_count": registry["schema_count"],
            "sha256": registry_hash,
        },
        "snapshot_resource_count": len(snapshot_entries),
        "status": "CURRENT",
    }
    return source, snapshot, registry


def verify_preprojection_history() -> dict[str, Any]:
    source = read_json(ATTEMPT / "source-inventory-preprojection.json")
    snapshot = read_json(ATTEMPT / "snapshot-inventory-preprojection.json")
    comparison = snapshot.get("comparison_to_source")
    if not isinstance(comparison, dict):
        raise SystemExit("preprojection snapshot has no comparison")
    expected_missing = [
        "schemas/document-registration-request.schema.json",
        "schemas/document-registration.schema.json",
    ]
    expected_mismatches = [
        "openapi/epistemic-foundry-v1.openapi.yaml",
        "schemas/document-manifest.schema.json",
        "schemas/evaluator-bundle.schema.json",
        "schemas/gate-decision.schema.json",
        "schemas/holdout-manifest.schema.json",
    ]
    if (
        source.get("source_bundle_hash") != EXPECTED_SOURCE_BUNDLE_HASH
        or comparison.get("status") != "STALE"
        or comparison.get("missing_paths") != expected_missing
        or comparison.get("hash_mismatches") != expected_mismatches
        or comparison.get("extra_paths") != []
        or snapshot.get("observed_registry_sha256")
        != "sha256:5f3c4514b3801cc66cc0a403d49c1dc380f7665ddc570d4987072a6f77fde1dd"
    ):
        raise SystemExit("preprojection stale-state evidence changed")
    return {
        "extra_paths": [],
        "hash_mismatches": expected_mismatches,
        "missing_paths": expected_missing,
        "observed_prior_registry_hash": snapshot["observed_registry_sha256"],
        "status": "VERIFIED_STALE_PRESTATE",
    }


def parse_pytest_junit(path: Path) -> tuple[dict[str, int], list[dict[str, Any]]]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {
        "collected": sum(int(suite.get("tests", "0")) for suite in suites),
        "errors": sum(int(suite.get("errors", "0")) for suite in suites),
        "failed": sum(int(suite.get("failures", "0")) for suite in suites),
        "skipped": sum(int(suite.get("skipped", "0")) for suite in suites),
    }
    rows: list[dict[str, Any]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        if problem is None:
            continue
        kind = "failure" if failure is not None else "error"
        classname = case.get("classname", "")
        name = case.get("name", "")
        node_id = f"{classname}::{name}" if classname else name
        raw_text = "\n".join(
            part for part in (problem.get("message", ""), problem.text or "") if part
        )
        rows.append(
            {
                "failure_kind": kind,
                "failure_type": problem.get("type", ""),
                "node_id": node_id,
                "raw_text": raw_text,
            }
        )
    if len(rows) != counts["failed"] + counts["errors"]:
        raise SystemExit("Python JUnit declared and observed problem counts differ")
    counts["passed"] = (
        counts["collected"]
        - counts["failed"]
        - counts["errors"]
        - counts["skipped"]
    )
    return counts, rows


def normalize_diagnostic(text: str) -> str:
    variants = {str(ROOT), str(ROOT).lower(), str(ROOT).replace("\\", "/")}
    for value in variants:
        text = text.replace(value, "<ROOT>")
    text = text.replace("\\", "/")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:24])[:6000]


def classify_python_problem(
    node_id: str, raw_text: str
) -> tuple[str, list[str], str]:
    haystack = f"{node_id}\n{raw_text}".lower().replace("\\", "/")
    if (
        "test_repository_dependency_lock_closes_exact_tiktoken_pin" in haystack
        or "tokenizer_contract_unavailable" in haystack
    ):
        return (
            "J02_TIKTOKEN_DEPENDENCY_DEBT",
            ["tests/test_j02_context_budget.py"],
            "J02",
        )
    if (
        "holdoutmanifest" in haystack
        or "holdout-manifest.schema.json" in haystack
        or "verifier_firewall/firewall.py" in haystack
        or "holdout_manifest_id" in haystack
        or "dataset_or_fixture_ids" in haystack
        or "access_principal_ids" in haystack
    ):
        return (
            "HOLDOUT_MANIFEST_RUNTIME_SCHEMA_DRIFT",
            ["src/epistemic_foundry/verifier_firewall/firewall.py"],
            "UNASSIGNED_RUNTIME_MIGRATION_OWNER",
        )
    if (
        "gatedecision" in haystack
        or "gate-decision.schema.json" in haystack
        or "foundry_kernel/gates.py" in haystack
        or "'gate_version' is a required property" in haystack
        or "'input_artifact_ids' is a required property" in haystack
        or "'policy_bundle_hash' is a required property" in haystack
        or "'blocker_ids' is a required property" in haystack
    ):
        return (
            "GATE_DECISION_RUNTIME_SCHEMA_DRIFT",
            ["src/epistemic_foundry/foundry_kernel/gates.py"],
            "UNASSIGNED_RUNTIME_MIGRATION_OWNER",
        )
    return ("UNCLASSIFIED_FULL_SUITE_FAILURE", [], "UNRESOLVED")


def live_python_inventory() -> dict[str, Any]:
    junit = ATTEMPT / "full-python-suite.junit.xml"
    counts, parsed = parse_pytest_junit(junit)
    classifications: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for problem in parsed:
        classification, paths, owner = classify_python_problem(
            problem["node_id"], problem["raw_text"]
        )
        classifications[classification] += 1
        kinds[problem["failure_kind"]] += 1
        rows.append(
            {
                "affected_runtime_paths": paths,
                "classification": classification,
                "failure_kind": problem["failure_kind"],
                "failure_type": problem["failure_type"],
                "migration_owner": owner,
                "node_id": problem["node_id"],
                "normalized_diagnostic": normalize_diagnostic(problem["raw_text"]),
            }
        )
    result = {
        "attempt_id": ATTEMPT_ID,
        "classification_counts": dict(sorted(classifications.items())),
        "completion_ready": False,
        "junit_path": junit.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(junit),
        "problem_kind_counts": dict(sorted(kinds.items())),
        "problems": rows,
        "suite": counts,
        "unclassified_problem_count": classifications.get(
            "UNCLASSIFIED_FULL_SUITE_FAILURE", 0
        ),
    }
    stored = read_json(ATTEMPT / "full-python-failure-inventory.json")
    if result != stored:
        raise SystemExit("stored Python failure inventory differs from live JUnit")
    if (
        counts != {
            "collected": 983,
            "errors": 15,
            "failed": 52,
            "passed": 916,
            "skipped": 0,
        }
        or result["classification_counts"]
        != {
            "GATE_DECISION_RUNTIME_SCHEMA_DRIFT": 51,
            "HOLDOUT_MANIFEST_RUNTIME_SCHEMA_DRIFT": 15,
            "J02_TIKTOKEN_DEPENDENCY_DEBT": 1,
        }
        or result["unclassified_problem_count"] != 0
    ):
        raise SystemExit("Python regression boundary changed")
    return result


def normalize_test_file(value: str) -> str:
    normalized = value.replace("\\", "/")
    root = str(ROOT).replace("\\", "/")
    if normalized.lower().startswith(root.lower() + "/"):
        return normalized[len(root) + 1 :]
    return normalized


def parse_tap_counter(comments: Iterable[str], label: str) -> int:
    matches: list[int] = []
    pattern = re.compile(rf"^\s*{re.escape(label)}\s+(\d+)\s*$")
    for comment in comments:
        match = pattern.match(comment)
        if match:
            matches.append(int(match.group(1)))
    if len(matches) != 1:
        raise SystemExit(f"Node JUnit lacks a unique TAP {label!r} counter: {matches}")
    return matches[0]


def live_node_inventory() -> dict[str, Any]:
    junit = ATTEMPT / "full-node-suite.junit.xml"
    root = ET.parse(junit).getroot()
    comments = re.findall(r"<!--\s*(.*?)\s*-->", junit.read_text(encoding="utf-8"))
    tap = {
        "tests": parse_tap_counter(comments, "tests"),
        "passed": parse_tap_counter(comments, "pass"),
        "failed": parse_tap_counter(comments, "fail"),
        "skipped": parse_tap_counter(comments, "skipped"),
    }
    if tap != {"tests": 458, "passed": 447, "failed": 11, "skipped": 0}:
        raise SystemExit(f"Node TAP totals changed: {tap}")
    failures: list[dict[str, Any]] = []
    owner_counts: Counter[str] = Counter()
    for case in root.findall(".//testcase"):
        problem = case.find("failure")
        if problem is None:
            continue
        path = normalize_test_file(case.get("file", ""))
        message = problem.get("message", "")
        if path.startswith("tests/golden/forge/"):
            owner = "F04"
            classification = "F04_GATE_DECISION_FIXTURE_DRIFT"
        elif path == "tests/node/j02-skill-context-loader.test.mjs":
            owner = "J02"
            classification = "J02_SEALED_INVENTORY_HASH_DRIFT"
        elif path == "tests/security/s04-threat-model-traceability.test.mjs":
            owner = "S04"
            classification = "S04_ACTIVE_MANIFEST_BINDING_DRIFT"
        else:
            owner = "UNRESOLVED"
            classification = "UNCLASSIFIED_NODE_FAILURE"
        owner_counts[owner] += 1
        failures.append(
            {
                "classification": classification,
                "failure_type": problem.get("type", ""),
                "file": path,
                "message": normalize_diagnostic(message),
                "name": case.get("name", ""),
                "owner": owner,
            }
        )
    if len(failures) != 10 or owner_counts != Counter({"F04": 7, "J02": 2, "S04": 1}):
        raise SystemExit(
            f"Node leaf failure boundary changed: count={len(failures)}, "
            f"owners={dict(owner_counts)}"
        )
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "failing_leaf_testcase_count": len(failures),
        "failures": failures,
        "junit_path": junit.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(junit),
        "leaf_failure_owner_counts": dict(sorted(owner_counts.items())),
        "tap_authoritative_totals": tap,
        "tap_failure_minus_leaf_failure_count": tap["failed"] - len(failures),
    }


def parse_manifest_packages() -> dict[str, dict[str, Any]]:
    """Parse only package id/write-scope blocks from the constrained manifest.

    A narrow parser avoids making evidence generation depend on a YAML package.
    The development manifest uses top-level ``- id`` records, scalar keys, and
    indented list items for write_scope; this function fails closed on duplicate
    package IDs.
    """

    packages: dict[str, dict[str, Any]] = {}
    current_id: str | None = None
    collecting_scope = False
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        package = re.match(r"^- id:\s*(\S+)\s*$", line)
        if package:
            current_id = package.group(1)
            if current_id in packages:
                raise SystemExit(f"duplicate package ID in manifest: {current_id}")
            packages[current_id] = {"write_scope": []}
            collecting_scope = False
            continue
        if current_id is None:
            continue
        if line == "  write_scope:":
            collecting_scope = True
            continue
        if collecting_scope:
            item = re.match(r"^  -\s+(.+?)\s*$", line)
            if item:
                packages[current_id]["write_scope"].append(item.group(1))
                continue
            if line and not line.startswith("    "):
                collecting_scope = False
    return packages


def scope_matches(path: str, scope: str) -> bool:
    path = path.rstrip("/")
    scope = scope.rstrip("/")
    if scope.endswith("/**"):
        return path == scope[:-3] or path.startswith(scope[:-2])
    return path == scope


def owners_for(path: str, packages: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        package_id
        for package_id, package in packages.items()
        if any(scope_matches(path, scope) for scope in package["write_scope"])
    )


def live_ownership_inventory() -> dict[str, Any]:
    packages = parse_manifest_packages()
    runtime = {
        path: owners_for(path, packages) for path in sorted(RUNTIME_PATHS)
    }
    derived = {
        path: {
            "expected_owner": expected,
            "manifest_owners": owners_for(path, packages),
        }
        for path, expected in sorted(DERIVED_PATHS.items())
    }
    if any(runtime.values()):
        raise SystemExit(f"runtime ownership assumption changed: {runtime}")
    for path, value in derived.items():
        if value["expected_owner"] not in value["manifest_owners"]:
            raise SystemExit(f"derived artifact owner missing for {path}: {value}")
    return {
        "development_manifest_sha256": "sha256:" + sha256(MANIFEST_PATH),
        "derived_artifact_ownership": derived,
        "runtime_migration_ownership": runtime,
        "status": "SPEC_GAP_RUNTIME_OWNER_AND_PRE_C04_ORDER_UNDEFINED",
        "unowned_runtime_path_count": sum(not owners for owners in runtime.values()),
    }


def verify_targeted_projection() -> dict[str, Any]:
    path = ATTEMPT / "targeted-projection.junit.xml"
    counts, problems = parse_pytest_junit(path)
    if counts != {
        "collected": 41,
        "errors": 0,
        "failed": 0,
        "passed": 41,
        "skipped": 0,
    } or problems:
        raise SystemExit(f"targeted projection suite is not 41/41 PASS: {counts}")
    return {**counts, "junit_sha256": sha256_id(path), "status": "PASS"}


def verify_packaging(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stored = read_json(ATTEMPT / "packaging-verification-run.json")
    canonical = stored.get("canonical_registry")
    checks = stored.get("checks")
    if stored.get("status") != "PASS" or not isinstance(canonical, dict) or not isinstance(checks, dict):
        raise SystemExit("packaging verification is not a structured PASS")
    expected = {
        "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        "projected_snapshot_bundle_hash": EXPECTED_SNAPSHOT_BUNDLE_HASH,
        "registry_sha256": EXPECTED_REGISTRY_HASH,
        "schema_count": 126,
        "resource_count": 127,
        "openapi_document_count": 1,
        "file_count": 127,
    }
    for key, value in expected.items():
        if canonical.get(key) != value:
            raise SystemExit(f"packaging evidence mismatch for {key}")
        if key != "registry_sha256" and registry.get(key) != value:
            raise SystemExit(f"live registry mismatch for {key}")
    comparisons = checks.get("registry_comparisons")
    installed = checks.get("installed_wheel")
    reproducibility = checks.get("two_build_reproducibility")
    if not isinstance(comparisons, dict) or not isinstance(installed, dict) or not isinstance(reproducibility, dict):
        raise SystemExit("packaging verification lacks comparison/install/rebuild evidence")
    for name, comparison in comparisons.items():
        if not isinstance(comparison, dict) or comparison != {
            "extra": 0,
            "hash_mismatches": 0,
            "missing": 0,
            "resource_count": 127,
            "status": "PASS",
        }:
            raise SystemExit(f"packaging comparison failed: {name}: {comparison}")
    if not (
        installed.get("clean_venv_install") == "PASS"
        and installed.get("arbitrary_empty_cwd") == "PASS"
        and installed.get("schema_count") == 126
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
        raise SystemExit("packaging installed/rebuild/fallback checks changed")

    wheel = ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
    prefix = "epistemic_foundry/_canonical/"
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        packaged_registry = archive.read(prefix + "canonical-registry.json")
        if packaged_registry != REGISTRY_PATH.read_bytes():
            raise SystemExit("wheel registry bytes differ from live registry")
        for entry in registry["resources"]:
            archive_name = prefix + str(entry["package_path"])
            if archive_name not in names:
                raise SystemExit(f"wheel is missing canonical resource: {archive_name}")
            wheel_bytes = archive.read(archive_name)
            root_bytes = (ROOT / str(entry["source_path"])).read_bytes()
            snapshot_bytes = (SNAPSHOT / str(entry["package_path"])).read_bytes()
            if wheel_bytes != root_bytes or wheel_bytes != snapshot_bytes:
                raise SystemExit(f"wheel canonical bytes diverge: {archive_name}")
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
        "verified_wheel_canonical_resource_count": len(registry["resources"]),
        "wheel_registry_byte_equal": True,
    }
    return stored, installed_evidence


def projection_receipt() -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "ART-B04-0006-CANONICAL-PROJECTION",
        "byte_size": REGISTRY_PATH.stat().st_size,
        "content_hash": sha256_id(REGISTRY_PATH),
        "created_at": CREATED_AT,
        "created_by": {
            "actor_id": "B04-0006-canonical-projection-verifier",
            "actor_type": "tool",
        },
        "locator": REGISTRY_PATH.relative_to(ROOT).as_posix(),
        "media_type": "application/vnd.epistemic-foundry.canonical-registry+json",
        "receipt_id": "AR-B04-0006-CANONICAL-PROJECTION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "registry_byte_integrity",
                "details": "Receipt content_hash and byte_size bind the exact live canonical-registry.json bytes.",
                "status": "PASS",
            },
            {
                "check": "root_snapshot_wheel_convergence",
                "details": (
                    "All 127 canonical resources bind root source "
                    f"{EXPECTED_SOURCE_BUNDLE_HASH} to snapshot "
                    f"{EXPECTED_SNAPSHOT_BUNDLE_HASH} and the built wheel byte-for-byte."
                ),
                "status": "PASS",
            },
            {
                "check": "receipt_scope_boundary",
                "details": (
                    "This receipt proves canonical projection integrity only; it does not prove "
                    "runtime, F04, J02, S04, package, C04, or repository conformance."
                ),
                "status": "PASS",
            },
        ],
    }
    value["receipt_hash"] = hash_excluding(value, "receipt_hash")
    validate_artifact("artifact-receipt", value)
    return value


def command(
    suffix: str, text: str, result: str, *, exit_code: int = 0
) -> dict[str, Any]:
    return {
        "command": text,
        "command_id": f"B04-0006-{suffix}",
        "exit_code": exit_code,
        "recorded_at_utc": CREATED_AT,
        "result": result,
        "scope": "B04-0006 projection and regression boundary",
    }


def command_rows(*, closeout: bool) -> list[dict[str, Any]]:
    rows = [
        command("C001", "Inspect HD-EF4-C01-SG004-20260730-001, B04 exact scope, prior projection evidence, and dirty-worktree preservation boundary", "PASS: pre-C04 B04 projection authorized; runtime/F04/J02/S04 corrections not authorized by that decision"),
        command("C002", "Capture the 126-schema root inventory and stale preprojection snapshot inventory", "PASS: old registry observed; two missing and five mismatched canonical resources recorded"),
        command("C003", "Run deterministic canonical materialization from root schemas/openapi to src/epistemic_foundry/_canonical", "PASS: atomic one-way projection produced 126 schemas plus one OpenAPI resource"),
        command("C004", "Run targeted canonical projection and packaging tests with JUnit", "PASS: 41 passed; 0 failed/errors/skipped"),
        command("C005", "Run formal clean wheel/sdist, sdist-to-wheel, installed-only, arbitrary-cwd, fallback, tamper, and deterministic rebuild verification", "PASS: wheel 307863 bytes; sdist 256787 bytes; 127 canonical resources current"),
        command("C006", "Run full Python suite with JUnit and parse every failure/error", "NON_GREEN: 916 passed, 52 failed, 15 errors; 51 GateDecision drift, 15 HoldoutManifest drift, one J02 debt", exit_code=1),
        command("C007", "Run full Node suite with JUnit and reconcile TAP totals separately from failing leaf testcases", "NON_GREEN: TAP 447/458 passed with 11 failures; ten failing leaves owned by F04=7, J02=2, S04=1", exit_code=1),
        command("C008", "Inspect development_manifest write scopes for runtime and derived-artifact failure paths", "SPEC_GAP: gates.py and firewall.py have no owner; F04/J02/S04 have owners but no authorized pre-C04 correction sequence"),
        command("C009", "Perform primary-session separate adversarial integration review", "PASS projection boundary; package status SPEC_GAP B04-SG002; actor_independence=false"),
        command("C010", "Write root B04-SG002 human-readable approval explanation", "PASS: exact blocker, evidence, bounded decision surface, and copy-ready unapproved draft recorded"),
        command("C011", "Build and verify B04-0006 machine-readable evidence from live root/snapshot/wheel/JUnit/manifest bytes", "PASS: projection success and ownership/order gap independently recomputed; completion_ready=false"),
    ]
    if closeout:
        rows.extend(
            [
                command("C012", "Append B04-0006 projection/regression audit and B04-SG002 documented gap to RAH", "PASS: E0106/E0107 appended; generation blocked; all prior generations preserved"),
                command("C013", "Build report.json and rah-core-integrity.json from the blocked core generation", "PASS: report preserves projection PASS and package SPEC_GAP separately; reserves E0108"),
                command("C014", "Append hash-bound B04-0006 closeout evidence and verify final generation", "PASS when b04_0006_rah_seal.py final completes; exact blocker and completion_ready=false remain"),
            ]
        )
    return rows


def write_commands(rows: Iterable[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    (ATTEMPT / "commands.jsonl").write_text(
        content, encoding="utf-8", newline="\n"
    )


def read_commands() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(
        (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"commands.jsonl line {number} is invalid: {error}")
        if not isinstance(value, dict):
            raise SystemExit(f"commands.jsonl line {number} is not an object")
        rows.append(value)
    return rows


def render_review() -> str:
    return f"""# B04-0006 pre-C04 projection review

Overall projection status: `PASS`

Overall package status: `SPEC_GAP` (`{SPEC_GAP_ID}`)

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external actor-independent certification.
Fleet and subagents were not used.

## Projection boundary

- Root authority remains `schemas/**` and `openapi/**`; the package snapshot is
  derived only from those roots.
- 126 schemas plus OpenAPI 3.1.1/33 operations produce 127 canonical resources.
- Source `{EXPECTED_SOURCE_BUNDLE_HASH}`, snapshot
  `{EXPECTED_SNAPSHOT_BUNDLE_HASH}`, and registry `{EXPECTED_REGISTRY_HASH}`
  are recomputed from live bytes.
- Missing, extra, hash-mismatched, and duplicate-ID counts are all zero after
  projection. The stored stale prestate retains two missing and five mismatched
  resources and the prior registry hash.
- Targeted projection tests are 41/41. Clean wheel/sdist, sdist-to-wheel,
  installed-wheel-only loading, arbitrary empty cwd, tamper/missing rejection,
  deterministic rebuild, and source fallback success count zero pass.
- The projection receipt binds the live registry and proves projection
  integrity only. It does not prove runtime or repository conformance.

## Adversarial regression and ownership review

- Full Python is not green: 916 passed, 52 failed, 15 errors. The 67 problems
  resolve exactly to 51 `GATE_DECISION_RUNTIME_SCHEMA_DRIFT`, 15
  `HOLDOUT_MANIFEST_RUNTIME_SCHEMA_DRIFT`, and one existing J02 dependency debt.
- Full Node is not green: TAP records 458 tests, 447 pass, 11 fail, 0 skipped;
  JUnit contains ten failing leaf testcases (F04=7, J02=2, S04=1). The TAP and
  leaf totals are intentionally recorded separately.
- The active manifest assigns no writer to
  `src/epistemic_foundry/foundry_kernel/gates.py` or
  `src/epistemic_foundry/verifier_firewall/firewall.py`.
- F04, J02, and S04 own their derived paths, but the current decision does not
  authorize a pre-C04 correction sequence for those packages. B04 cannot invent
  that ordering or broaden another package's scope.
- No runtime, fixture, inventory, binding, schema, or test gate was weakened.

## Decision

The deterministic canonical projection is verified `PASS`. B04-0006 as a
package is `SPEC_GAP` because `{SPEC_GAP_ID}` requires a product-owner decision
assigning bounded runtime migration ownership and authorizing the pre-C04
F04/J02/S04 correction sequence. `C04-0002` and final B04 packaging must not
start. The projection receipt is not package-PASS evidence. The dirty worktree
and all prior attempts/RAH history remain preserved; `completion_ready=false`.
"""


def build_projection_verification(
    *,
    source: dict[str, Any],
    snapshot: dict[str, Any],
    packaging: dict[str, Any],
    targeted: dict[str, Any],
    prestate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_id": AUTHORITY_DECISION_ID,
        "deterministic_rebuild_result": "PASS",
        "duplicate_schema_ids": [],
        "extra_paths": [],
        "final_status": "PASS",
        "hash_mismatches": [],
        "installed_wheel_resource_load_result": "PASS",
        "missing_paths": [],
        "openapi_operation_count": 33,
        "openapi_resource_count": 1,
        "openapi_version": "3.1.1",
        "package_status": "SPEC_GAP",
        "packaging_verification_sha256": sha256_id(
            ATTEMPT / "packaging-verification-run.json"
        ),
        "preprojection_stale_state": prestate,
        "projected_snapshot_bundle_hash": snapshot[
            "projected_snapshot_bundle_hash"
        ],
        "projection_receipt_id": "AR-B04-0006-CANONICAL-PROJECTION",
        "projection_status": "PASS",
        "registry_hash": snapshot["registry"]["sha256"],
        "root_source_mutation_count": 0,
        "schema_count": source["schema_count"],
        "snapshot_resource_count": snapshot["snapshot_resource_count"],
        "source_bundle_hash": source["source_bundle_hash"],
        "source_resource_count": source["source_resource_count"],
        "source_tree_fallback_count": packaging["checks"]["source_tree_fallback"][
            "success_count"
        ],
        "spec_gap_id": SPEC_GAP_ID,
        "targeted_projection": targeted,
        "total_canonical_resource_count": 127,
        "unrelated_write_count": 0,
        "write_scope_violation_count": 0,
    }


def dependency_status(
    ownership: dict[str, Any], python: dict[str, Any], node: dict[str, Any]
) -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    for package in ("C01", "C02", "C03"):
        attempts = sorted((ROOT / f"artifacts/work_packages/{package}/attempts").iterdir())
        reports = [path / "report.json" for path in attempts if (path / "report.json").is_file()]
        if not reports:
            raise SystemExit(f"no report found for dependency {package}")
        report_path = reports[-1]
        report = read_json(report_path)
        if report.get("status") != "PASS" or report.get("package_status") != "PASS":
            raise SystemExit(f"dependency is not PASS: {package}: {report_path}")
        dependencies[package] = {
            "attempt_id": report.get("attempt_id"),
            "report": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(report_path),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "blocker": {
            "id": SPEC_GAP_ID,
            "reason": (
                "The current manifest has no runtime migration owner for GateDecision "
                "or HoldoutManifest producers and no authorized pre-C04 F04/J02/S04 "
                "correction sequence."
            ),
            "required_authority": "product_owner_human_decision",
            "status": "OPEN",
        },
        "completion_ready": False,
        "dependencies": dependencies,
        "forbidden_next_steps": ["C04-0002", "B04 final packaging"],
        "node_problem_count": node["tap_authoritative_totals"]["failed"],
        "ownership": ownership,
        "package_status": "SPEC_GAP",
        "projection_status": "PASS",
        "python_problem_count": python["suite"]["failed"] + python["suite"]["errors"],
        "status": "WAITING_ON_PRODUCT_OWNER_DECISION",
    }


def build_precore() -> dict[str, Any]:
    assert_immutable_inputs()
    source, snapshot, registry = live_canonical_inventory()
    prestate = verify_preprojection_history()
    targeted = verify_targeted_projection()
    packaging, installed = verify_packaging(registry)
    python = live_python_inventory()
    node = live_node_inventory()
    ownership = live_ownership_inventory()

    write_json("source-inventory.json", source)
    write_json("snapshot-inventory.json", snapshot)
    write_json("node-failure-inventory.json", node)
    write_json("installed-wheel-verification.json", installed)
    regression = {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "node": node,
        "package_status": "SPEC_GAP",
        "projection_causal_impact": "CANONICAL_CONTRACT_ACTIVATION_EXPOSED_UNMIGRATED_RUNTIME_AND_DERIVED_ARTIFACTS",
        "projection_status": "PASS",
        "python": {
            key: copy.deepcopy(value)
            for key, value in python.items()
            if key != "problems"
        },
        "python_problem_count": len(python["problems"]),
        "spec_gap_id": SPEC_GAP_ID,
        "status": "NON_GREEN_REQUIRES_AUTHORIZED_CORRECTION",
        "unexpected_skip_or_xfail_count": 0,
    }
    write_json("full-regression-impact.json", regression)
    write_json("dependency-status.json", dependency_status(ownership, python, node))
    receipt = projection_receipt()
    write_json("projection.artifact-receipt.json", receipt)
    projection = build_projection_verification(
        source=source,
        snapshot=snapshot,
        packaging=packaging,
        targeted=targeted,
        prestate=prestate,
    )
    write_json("canonical-projection-verification.json", projection)
    (ATTEMPT / "review.md").write_text(
        render_review(), encoding="utf-8", newline="\n"
    )
    write_commands(command_rows(closeout=False))
    verify_evidence(require_closeout=False)
    return {
        "attempt_id": ATTEMPT_ID,
        "mode": "build",
        "package_status": "SPEC_GAP",
        "projection_receipt_hash": receipt["receipt_hash"],
        "projection_status": "PASS",
        "spec_gap_id": SPEC_GAP_ID,
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
                key: value for key, value in authority.items() if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "blocked"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH is not blocked/fail/not-ready with six current flats")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": generation,
        "evidence_count": len(payloads["evidence_ledger.json"]["entries"]),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": sha256_id(
            ralph_root / "generations" / generation / "generation-manifest.json"
        ),
        "implementation_gate": "fail",
        "latest_evidence_id": payloads["evidence_ledger.json"]["entries"][-1]["id"],
        "mode": "READ_ONLY",
        "parse_errors": {},
        "ralph_status": "blocked",
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "PASS",
        "work_package_id": "B04",
    }


def build_closeout() -> dict[str, Any]:
    verify_evidence(require_closeout=False)
    integrity = generation_integrity(20)
    if (
        integrity["latest_evidence_id"] != "E0107"
        or not re.fullmatch(r"000098-[0-9a-f]{8}", integrity["current_generation"])
    ):
        raise SystemExit("B04-0006 closeout requires blocked E0107 core generation")
    write_json("rah-core-integrity.json", integrity)
    write_commands(command_rows(closeout=True))
    regression = read_json(ATTEMPT / "full-regression-impact.json")
    report = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "PRE_C04_CANONICAL_PROJECTION_RECONCILIATION",
        "authority_decision_id": AUTHORITY_DECISION_ID,
        "blocker": SPEC_GAP_ID,
        "canonical_projection": {
            "duplicate_schema_id_count": 0,
            "extra_path_count": 0,
            "hash_mismatch_count": 0,
            "missing_path_count": 0,
            "openapi_operation_count": 33,
            "openapi_resource_count": 1,
            "openapi_version": "3.1.1",
            "projected_snapshot_bundle_hash": EXPECTED_SNAPSHOT_BUNDLE_HASH,
            "registry_hash": EXPECTED_REGISTRY_HASH,
            "resource_count": 127,
            "schema_count": 126,
            "source_bundle_hash": EXPECTED_SOURCE_BUNDLE_HASH,
        },
        "completion_ready": False,
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "B04_prior_attempts": "IMMUTABLE_HISTORY",
            "C01_0001_through_0005": "IMMUTABLE_SPEC_GAP_HISTORY",
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "VERIFIED_PROJECTION_ONLY",
        "next_state": {
            "B04": "WAITING_ON_PRODUCT_OWNER_DECISION",
            "C04": "PROHIBITED_UNTIL_AUTHORIZED_CORRECTIONS_AND_REVALIDATION_PASS",
            "final_B04": "PROHIBITED_UNTIL_C04_PASS",
        },
        "not_claimed": [
            "B04 package PASS",
            "runtime conformance",
            "F04/J02/S04 conformance",
            "global Python suite green",
            "global Node suite green",
            "C04-0002 started or passed",
            "final B04 packaging started or passed",
            "repository-wide conformance",
            "release or production readiness",
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
                "artifacts/work_packages/B04/attempts/0006/report.json",
                "artifacts/work_packages/B04/attempts/0006/build_b04_0006_evidence.py",
                "artifacts/work_packages/B04/attempts/0006/b04_0006_rah_seal.py",
            }
        ),
        "package_status": "SPEC_GAP",
        "product_files_modified_by_evidence_closeout": [],
        "projection_status": "PASS",
        "rah_state": {
            "audit_evidence_id": "E0106",
            "completion_ready": False,
            "core_generation": integrity["current_generation"],
            "documented_gap_evidence_id": "E0107",
            "final_closeout_evidence_id": "E0108",
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
            "retained_generation_count": integrity["retained_generation_count"],
            "status": "blocked",
        },
        "regression": {
            "node": regression["node"]["tap_authoritative_totals"],
            "node_failing_leaf_testcases": regression["node"][
                "failing_leaf_testcase_count"
            ],
            "python": regression["python"]["suite"],
            "unexpected_skip_or_xfail_count": 0,
        },
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
            "package_status": "SPEC_GAP",
            "projection_status": "PASS",
        },
        "spec_gap": {
            "id": SPEC_GAP_ID,
            "required_decision": (
                "Assign bounded runtime migration ownership and exact write scope for "
                "gates.py, firewall.py, and related tests, and authorize the pre-C04 "
                "F04/J02/S04 correction sequence."
            ),
            "status": "OPEN",
        },
        "status": "SPEC_GAP",
        "work_package_id": "B04",
    }
    write_json("report.json", report)
    verify_evidence(require_closeout=True)
    return {
        "attempt_id": ATTEMPT_ID,
        "core_generation": integrity["current_generation"],
        "mode": "closeout",
        "package_status": "SPEC_GAP",
        "projection_status": "PASS",
        "report_sha256": sha256_id(ATTEMPT / "report.json"),
        "status": "PASS",
    }


def verify_receipt(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if value.get("receipt_hash") != hash_excluding(value, "receipt_hash"):
        raise SystemExit("projection receipt self-hash mismatch")
    validate_artifact("artifact-receipt", value)
    locator = ROOT / str(value["locator"])
    if (
        sha256_id(locator) != value["content_hash"]
        or locator.stat().st_size != value["byte_size"]
    ):
        raise SystemExit("projection receipt does not bind live registry bytes")
    return value


def verify_evidence(*, require_closeout: bool) -> dict[str, Any]:
    assert_immutable_inputs()
    source, snapshot, registry = live_canonical_inventory()
    prestate = verify_preprojection_history()
    targeted = verify_targeted_projection()
    packaging, installed = verify_packaging(registry)
    python = live_python_inventory()
    node = live_node_inventory()
    ownership = live_ownership_inventory()
    expected: dict[str, dict[str, Any]] = {
        "source-inventory.json": source,
        "snapshot-inventory.json": snapshot,
        "node-failure-inventory.json": node,
        "installed-wheel-verification.json": installed,
        "full-regression-impact.json": {
            "attempt_id": ATTEMPT_ID,
            "completion_ready": False,
            "node": node,
            "package_status": "SPEC_GAP",
            "projection_causal_impact": "CANONICAL_CONTRACT_ACTIVATION_EXPOSED_UNMIGRATED_RUNTIME_AND_DERIVED_ARTIFACTS",
            "projection_status": "PASS",
            "python": {
                key: copy.deepcopy(value)
                for key, value in python.items()
                if key != "problems"
            },
            "python_problem_count": len(python["problems"]),
            "spec_gap_id": SPEC_GAP_ID,
            "status": "NON_GREEN_REQUIRES_AUTHORIZED_CORRECTION",
            "unexpected_skip_or_xfail_count": 0,
        },
        "dependency-status.json": dependency_status(ownership, python, node),
        "canonical-projection-verification.json": build_projection_verification(
            source=source,
            snapshot=snapshot,
            packaging=packaging,
            targeted=targeted,
            prestate=prestate,
        ),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored B04-0006 evidence differs from live recomputation: {name}")
    receipt = verify_receipt(ATTEMPT / "projection.artifact-receipt.json")
    if receipt != projection_receipt():
        raise SystemExit("projection receipt differs from deterministic reconstruction")
    review = (ATTEMPT / "review.md").read_text(encoding="utf-8")
    normalized_review = " ".join(review.split())
    for phrase in (
        "Overall projection status: `PASS`",
        "Overall package status: `SPEC_GAP` (`B04-SG002`)",
        "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
        "actor_independence=false",
        "Full Python is not green",
        "Full Node is not green",
        "`C04-0002` and final B04 packaging must not start",
        "projection receipt is not package-PASS evidence",
    ):
        if phrase not in normalized_review:
            raise SystemExit(f"review omits required boundary phrase: {phrase}")
    rows = read_commands()
    if rows != command_rows(closeout=require_closeout):
        raise SystemExit("commands.jsonl differs from deterministic reconstruction")
    if require_closeout:
        report = read_json(ATTEMPT / "report.json")
        integrity = read_json(ATTEMPT / "rah-core-integrity.json")
        if not (
            report.get("status") == "SPEC_GAP"
            and report.get("package_status") == "SPEC_GAP"
            and report.get("projection_status") == "PASS"
            and report.get("blocker") == SPEC_GAP_ID
            and report.get("completion_ready") is False
            and report.get("product_files_modified_by_evidence_closeout") == []
        ):
            raise SystemExit("B04-0006 report does not preserve the split status")
        if not (
            integrity.get("status") == "PASS"
            and integrity.get("latest_evidence_id") == "E0107"
            and integrity.get("completion_ready") is False
            and integrity.get("ralph_status") == "blocked"
        ):
            raise SystemExit("RAH core integrity does not bind blocked E0107")
    return {
        "attempt_id": ATTEMPT_ID,
        "closeout_present": require_closeout,
        "command_count": len(rows),
        "package_status": "SPEC_GAP",
        "projection_status": "PASS",
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
        result = verify_evidence(
            require_closeout=(ATTEMPT / "report.json").is_file()
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
