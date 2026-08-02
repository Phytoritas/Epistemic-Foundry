#!/usr/bin/env python3
"""Build and verify the fail-closed C01-0008 closeout evidence.

C01-0008 successfully adds the strict canonical RetrievalCandidate contract and
raises the root authority inventory to 127 schemas and 127 matching examples.
The targeted contract gate is green.  The repository-wide gate, however,
exposes two kinds of downstream debt:

* 17 Python failures are the already ordered B04-0009 projection debt; and
* three new Node failures are stale J02/S04 authority projections that are not
  in C01's write scope or in the product-owner's authorized serial sequence.

The second category is therefore recorded as C01-SG005.  This builder does not
modify either downstream authority projection and never turns the attempt into
a PASS.  It normalizes volatile JUnit fields, validates the live contract,
records exact failure fingerprints, and emits deterministic closeout artifacts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0008"
SCHEMA = ROOT / "schemas/retrieval-candidate.schema.json"
EXAMPLE = ROOT / "examples/sample_retrieval-candidate.json"
OPENAPI = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
MASTER_SPEC = ROOT / "MASTER_SPEC.md"
DECISION = (
    ROOT
    / "artifacts/authority_decisions/HD-EF4-O02-SG001-20260731-001.human-decision.json"
)
J02_INVENTORY = ROOT / "plugins/epistemic-foundry/skills/skill-inventory.json"
S04_BINDING = ROOT / "manifests/source_bindings/development-manifest.binding.json"
O01_REPORT = ROOT / "artifacts/work_packages/O01/attempts/0002/report.json"

TARGETED_JUNIT = ATTEMPT / "targeted-contracts.junit.xml"
PYTHON_JUNIT = ATTEMPT / "full-python-suite.junit.xml"
NODE_JUNIT = ATTEMPT / "full-node-suite.junit.xml"

ATTEMPT_ID = "C01-0008"
WORK_PACKAGE_ID = "C01"
SPEC_GAP_ID = "C01-SG005"
RECORDED_AT = "2026-07-31T07:20:00.000Z"
EXPECTED_SCHEMA_COUNT = 127
EXPECTED_EXAMPLE_COUNT = 127
EXPECTED_OPERATION_COUNT = 33
EXPECTED_SCHEMA_HASH = (
    "sha256:19e12fe0affbdaaad59bd1bb4bd43e863d177413769a9bf06b80a8577f888f8e"
)
EXPECTED_EXAMPLE_HASH = (
    "sha256:e8cf70b16ec3ca22c7fa5782c7f1a130abafc8b8824dcceedec4fc54540d00c7"
)
EXPECTED_MASTER_HASH = (
    "sha256:a204288fb2b1e550cebf023424785774da30941cb7615fecb34f7b44822aff75"
)
EXPECTED_MANIFEST_HASH = (
    "sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063"
)
PRIOR_J02_MASTER_HASH = (
    "sha256:d4854c916594610e0503f9b017c57b0dbac9f52eef78b825b922fdf26b1a0fe3"
)
PRIOR_S04_MANIFEST_HASH = (
    "sha256:5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"
)
EXPECTED_J02_FILE_HASH = (
    "sha256:093a0892377db04f66dfb49c2f1848067de5334e50c96f85990a7968405d211c"
)
EXPECTED_S04_FILE_HASH = (
    "sha256:603bb4d082ce53ab902a3c3ab36abd9eb3331e44d105ec75e967c694bed50dbf"
)
EXPECTED_CANDIDATE_ID = (
    "RC-bead81fad2a047285297611ac44e28646e764716b42fc53f07fecddff5aa3a3b"
)
EXPECTED_QUERY_HASH = (
    "sha256:3cc4c6b54c5e182f3f1c25d505244f0ed601221adb0654293f006732099fb309"
)
EXPECTED_CANDIDATE_HASH = (
    "sha256:6125d56bf4d2097f3081b85d522bdfcb0cbad008bc6c693bc89f5e579ddc72da"
)
RAW_JUNIT_HASHES = {
    "targeted": "6a56ea1b23b9a80a9af28f526ad1078baded5c90399c3cf55cea7dd5f1d2453e",
    "python": "da39f64da3764ec5c98a94a27f27a7f64682007e0ff15a7e11df15a3e4ee0b3f",
    "node": "01e12e9941d4ac3378ea8636175eac9e15dfd287d62701eab505239fe9f95719",
}
JUNIT_PATHS = {
    "targeted": TARGETED_JUNIT,
    "python": PYTHON_JUNIT,
    "node": NODE_JUNIT,
}
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
EXAMPLE_ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}
PYTHON_FAILURE_NAMES = (
    "test_source_projection_is_current_and_complete",
    "test_registry_v2_binds_source_snapshot_paths_and_projection_tool",
    "test_runtime_accepts_registry_v2_external_projection",
    "test_materialization_is_deterministic",
    "test_materialize_atomically_replaces_complete_existing_projection",
    "test_second_rename_failure_restores_old_tree",
    "test_source_mutation_before_swap_fails_without_live_change",
    "test_source_mutation_after_swap_rolls_back_old_tree",
    "test_materialize_preserves_unrelated_empty_directory",
    "test_missing_packaged_resource_fails_closed",
    "test_one_byte_tamper_fails_closed",
    "test_duplicate_document_id_fails_closed",
    "test_registry_v2_binding_tamper_fails_closed[projected_snapshot_bundle_hash-sha256:0000000000000000000000000000000000000000000000000000000000000000]",
    "test_registry_v2_binding_tamper_fails_closed[projection_tool_identity-unapproved.projector]",
    "test_registry_v2_binding_tamper_fails_closed[projection_tool_version-999.0.0]",
    "test_registry_v2_binding_tamper_fails_closed[source_revision-sha256:0000000000000000000000000000000000000000000000000000000000000000]",
    "test_unregistered_extra_resource_fails_closed",
)
NODE_FAILURES = {
    (
        "tests/node/j02-skill-context-loader.test.mjs::"
        "loader verifies all sealed production files and authority pointers"
    ): "J02",
    (
        "tests/node/j02-skill-context-loader.test.mjs::"
        "ResolvedSkillContext is identical across 100 repeated sealed loads"
    ): "J02",
    (
        "tests/security/s04-threat-model-traceability.test.mjs::"
        "S04-TM004 traceability source bindings fail on undocumented contract drift"
    ): "S04",
}
OUTPUT_NAMES = (
    "build_c01_0008_evidence.py",
    "c01_0008_rah_seal.py",
    "canonical-contract-verification.json",
    "retrieval-candidate-verification.json",
    "full-regression-impact.json",
    "write-scope-verification.json",
    "phase-artifact-reconciliation.json",
    "dependency-status.json",
    "junit-normalization-verification.json",
    "commands.jsonl",
    "review.md",
    "report.json",
    "rah-core-integrity.json",
    "targeted-contracts.junit.xml",
    "full-python-suite.junit.xml",
    "full-node-suite.junit.xml",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


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


def example_path(schema_path: Path) -> Path:
    stem = schema_path.name.removesuffix(".schema.json")
    candidates = (
        EXAMPLE_ALIASES.get(stem),
        f"sample_{stem}.json",
        f"sample_{stem.replace('-', '_')}.json",
    )
    for candidate in candidates:
        if candidate and (ROOT / "examples" / candidate).is_file():
            return ROOT / "examples" / candidate
    raise SystemExit(f"no matching example for {schema_path.name}")


def walk_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def resolve_pointer(document: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(ref)
    current: Any = document
    for raw in ref[2:].split("/"):
        current = current[raw.replace("~1", "/").replace("~0", "~")]
    return current


def validate_canonical_contracts() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("*.json"))
    if len(schema_paths) != EXPECTED_SCHEMA_COUNT:
        raise SystemExit(f"expected 127 schemas, found {len(schema_paths)}")
    if len(example_paths) != EXPECTED_EXAMPLE_COUNT:
        raise SystemExit(f"expected 127 examples, found {len(example_paths)}")

    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    identifiers: list[str] = []
    for path in schema_paths:
        schema = read_json(path)
        Draft202012Validator.check_schema(schema)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"non-Draft-2020-12 schema: {path.name}")
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            raise SystemExit(f"missing schema $id: {path.name}")
        identifiers.append(identifier)
        schemas[path.name] = schema
        registry = registry.with_resource(identifier, Resource.from_contents(schema))
    if len(set(identifiers)) != EXPECTED_SCHEMA_COUNT:
        raise SystemExit("canonical schema IDs are not unique")

    mapped: set[Path] = set()
    failures: list[str] = []
    for schema_path in schema_paths:
        example = example_path(schema_path)
        mapped.add(example)
        validator = Draft202012Validator(
            schemas[schema_path.name],
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in sorted(
            validator.iter_errors(read_json(example)), key=lambda row: list(row.path)
        ):
            location = "/".join(str(part) for part in error.path) or "<root>"
            failures.append(f"{example.name}:{location}:{error.message}")
    if mapped != set(example_paths):
        raise SystemExit("canonical schema/example mapping is not one-to-one")
    if failures:
        raise SystemExit(f"canonical example validation failed: {failures[:5]}")

    return {
        "draft": "2020-12",
        "example_count": len(example_paths),
        "mapped_example_count": len(mapped),
        "meta_schema_validation": "PASS",
        "schema_count": len(schema_paths),
        "schema_example_one_to_one": True,
        "unique_schema_id_count": len(set(identifiers)),
        "valid_example_count": len(mapped),
        "status": "PASS",
    }


def validate_openapi() -> dict[str, Any]:
    document = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit("OpenAPI document is not an object")
    if document.get("openapi") != "3.1.1":
        raise SystemExit("OpenAPI version is not 3.1.1")
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for route, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method in methods:
                operations.append((route, method, operation))
    operation_ids = [row[2].get("operationId") for row in operations]
    if (
        len(operations) != EXPECTED_OPERATION_COUNT
        or len(set(operation_ids)) != EXPECTED_OPERATION_COUNT
        or None in operation_ids
    ):
        raise SystemExit("OpenAPI does not have 33 unique operationIds")
    failures: list[str] = []
    external: set[str] = set()
    for ref in walk_refs(document):
        if ref.startswith("#/"):
            try:
                resolve_pointer(document, ref)
            except (KeyError, TypeError, ValueError):
                failures.append(ref)
            continue
        relative = ref.split("#", 1)[0]
        external.add(relative)
        target = (OPENAPI.parent / relative).resolve()
        if not target.is_relative_to((ROOT / "schemas").resolve()) or not target.is_file():
            failures.append(ref)
        else:
            Draft202012Validator.check_schema(read_json(target))
    if failures:
        raise SystemExit(f"OpenAPI reference failures: {failures}")
    return {
        "canonical_file": OPENAPI.relative_to(ROOT).as_posix(),
        "document_sha256": sha256_id(OPENAPI),
        "external_schema_ref_count": len(external),
        "json_schema_dialect": document.get("jsonSchemaDialect"),
        "openapi_version": document["openapi"],
        "operation_count": len(operations),
        "reference_resolution_failures": [],
        "unique_operation_id_count": len(set(operation_ids)),
        "status": "PASS",
    }


def candidate_verification() -> dict[str, Any]:
    if sha256_id(SCHEMA) != EXPECTED_SCHEMA_HASH:
        raise SystemExit("RetrievalCandidate schema bytes changed")
    if sha256_id(EXAMPLE) != EXPECTED_EXAMPLE_HASH:
        raise SystemExit("RetrievalCandidate example bytes changed")
    schema = read_json(SCHEMA)
    fixture = read_json(EXAMPLE)
    Draft202012Validator.check_schema(schema)

    all_schemas = [read_json(path) for path in sorted((ROOT / "schemas").glob("*.schema.json"))]
    registry = Registry()
    for item in all_schemas:
        registry = registry.with_resource(str(item["$id"]), Resource.from_contents(item))
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    errors = sorted(validator.iter_errors(fixture), key=lambda row: list(row.path))
    if errors:
        raise SystemExit(f"RetrievalCandidate fixture errors: {[row.message for row in errors]}")

    identity_fields = schema["x-canonical-identity"]["preimage_fields"]
    content_fields = schema["x-canonical-hash"]["preimage_fields"]
    identity = canonical_hash({field: fixture[field] for field in identity_fields})
    candidate_id = "RC-" + identity.removeprefix("sha256:")
    query_hash = "sha256:" + hashlib.sha256(fixture["query_text"].encode("utf-8")).hexdigest()
    content_hash = canonical_hash({field: fixture[field] for field in content_fields})
    if candidate_id != fixture.get("candidate_id") or candidate_id != EXPECTED_CANDIDATE_ID:
        raise SystemExit("RetrievalCandidate candidate_id does not recompute")
    if query_hash != fixture.get("query_hash") or query_hash != EXPECTED_QUERY_HASH:
        raise SystemExit("RetrievalCandidate query_hash does not recompute")
    if content_hash != fixture.get("candidate_hash") or content_hash != EXPECTED_CANDIDATE_HASH:
        raise SystemExit("RetrievalCandidate candidate_hash does not recompute")

    ranks = [rank for rank in fixture["channel_ranks"].values() if rank is not None]
    rrf = sum(1 / (60 + rank) for rank in ranks)
    if not math.isclose(rrf, fixture["fusion_score"], rel_tol=0, abs_tol=1e-15):
        raise SystemExit("RetrievalCandidate RRF(k=60) score does not recompute")
    observed_channels = {
        channel for channel, rank in fixture["channel_ranks"].items() if rank is not None
    }
    scored_channels = {
        channel for channel, score in fixture["raw_scores"].items() if score is not None
    }
    if observed_channels != scored_channels or observed_channels != set(fixture["retrieval_channels"]):
        raise SystemExit("RetrievalCandidate channel rank/score nullability is inconsistent")
    if fixture["source_span_id"] is not None:
        raise SystemExit("canonical fixture must exercise the metadata-only boundary")

    missing = copy.deepcopy(fixture)
    missing.pop("candidate_hash")
    unknown = copy.deepcopy(fixture)
    unknown["unknown"] = "not-allowed"
    if not list(validator.iter_errors(missing)) or not list(validator.iter_errors(unknown)):
        raise SystemExit("RetrievalCandidate schema is not fail-closed")
    tampered = copy.deepcopy(fixture)
    tampered["backend_response_hash"] = "sha256:" + "0" * 64
    tampered_hash = canonical_hash({field: tampered[field] for field in content_fields})
    if tampered_hash == fixture["candidate_hash"]:
        raise SystemExit("RetrievalCandidate semantic tamper was not detected")

    return {
        "attempt_id": ATTEMPT_ID,
        "candidate_hash": content_hash,
        "candidate_id": candidate_id,
        "channel_nullability": "PASS",
        "fixture_sha256": sha256_id(EXAMPLE),
        "lane": fixture["lane"],
        "metadata_only_boundary": "PASS",
        "query_family": fixture["query_family"],
        "query_hash": query_hash,
        "relation_direction": fixture["relation_direction"],
        "rrf_k60_recomputation": "PASS",
        "schema_sha256": sha256_id(SCHEMA),
        "schema_validation": "PASS",
        "tamper_rejection": "PASS",
        "unknown_and_missing_field_rejection": "PASS",
        "status": "PASS",
    }


def manifest_contract() -> dict[str, Any]:
    if sha256_id(MASTER_SPEC) != EXPECTED_MASTER_HASH:
        raise SystemExit("MASTER_SPEC changed after the C01-0008 regression capture")
    if sha256_id(MANIFEST) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("development manifest changed after the C01-0008 regression capture")
    value = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = value if isinstance(value, list) else value["work_packages"]
    by_id = {row["id"]: row for row in packages}
    if len(packages) != 156:
        raise SystemExit("development manifest does not contain 156 packages")
    if by_id["C01"]["depends_on"] != ["A04", "A05"]:
        raise SystemExit("C01 dependency contract changed")
    if "schemas/retrieval-candidate.schema.json" not in by_id["C01"]["write_scope"]:
        raise SystemExit("C01 does not own RetrievalCandidate schema")
    if "examples/sample_retrieval-candidate.json" not in by_id["C01"]["write_scope"]:
        raise SystemExit("C01 does not own RetrievalCandidate example")
    if "plugins/epistemic-foundry/skills/skill-inventory.json" not in by_id["J02"]["write_scope"]:
        raise SystemExit("J02 ownership of skill-inventory.json is missing")
    if "manifests/source_bindings/development-manifest.binding.json" not in by_id["S04"]["write_scope"]:
        raise SystemExit("S04 ownership of development-manifest.binding.json is missing")
    if any(
        path in by_id["C01"]["write_scope"]
        for path in (
            "plugins/epistemic-foundry/skills/skill-inventory.json",
            "manifests/source_bindings/development-manifest.binding.json",
        )
    ):
        raise SystemExit("C01 improperly owns a J02/S04 authority projection")
    return {
        "C01_dependencies": by_id["C01"]["depends_on"],
        "C01_owns_retrieval_candidate": True,
        "C01_owns_J02_or_S04_projection": False,
        "J02_projection_owner": "plugins/epistemic-foundry/skills/skill-inventory.json",
        "S04_projection_owner": "manifests/source_bindings/development-manifest.binding.json",
        "manifest_sha256": sha256_id(MANIFEST),
        "master_spec_sha256": sha256_id(MASTER_SPEC),
        "package_count": len(packages),
        "status": "PASS",
    }


def junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        rows.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                problem.get("message", "") if problem is not None else "",
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
        if name != "node":
            if re.search(r'\s+(?:hostname|timestamp|time)="', text):
                raise SystemExit(f"pytest JUnit retains volatile fields: {name}")
        elif "duration_ms" in text:
            raise SystemExit("Node JUnit retains duration_ms")


def normalize_junit_files() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        migrated = False
        root_prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
        root_values = (str(ROOT), str(ROOT).replace("\\", "/"))
        for name, path in JUNIT_PATHS.items():
            file_record = record.get("files", {}).get(name, {})
            expected = file_record.get("normalized_sha256")
            if expected != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed: {name}")
            before = path.read_text(encoding="utf-8")
            signature = junit_signature(before)
            normalized = before
            removed_count = 0
            for prefix in root_prefixes:
                count = normalized.count(prefix)
                normalized = normalized.replace(prefix, "")
                removed_count += count
            for value in root_values:
                count = normalized.count(value)
                normalized = normalized.replace(value, ".")
                removed_count += count
            if removed_count:
                if junit_signature(normalized) != signature:
                    raise SystemExit(f"JUnit semantic signature changed: {name}")
                path.write_text(normalized, encoding="utf-8", newline="\n")
                removed = file_record.setdefault("removed", {})
                removed["repository_prefixes"] = (
                    int(removed.get("repository_prefixes", 0)) + removed_count
                )
                file_record["normalized_sha256"] = sha256_id(path)
                migrated = True
        if migrated:
            record["normalization_scope"] = [
                "remove pytest hostname, timestamp, and suite/testcase time attributes",
                "remove absolute repository prefixes from all JUnit evidence",
                "remove Node duration_ms while preserving authoritative footer counters",
            ]
            write_json("junit-normalization-verification.json", record)
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        if sha256(path) != RAW_JUNIT_HASHES[name]:
            raise SystemExit(f"raw JUnit hash mismatch: {name}")
        before = path.read_text(encoding="utf-8")
        signature = junit_signature(before)
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
        if name == "node":
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
        if junit_signature(normalized) != signature:
            raise SystemExit(f"JUnit semantic signature changed: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "case_count": len(signature),
            "normalized_sha256": sha256_id(path),
            "raw_sha256": "sha256:" + RAW_JUNIT_HASHES[name],
            "removed": removed,
            "semantic_signature_preserved": True,
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "normalization_scope": [
            "remove pytest hostname, timestamp, and suite/testcase time attributes",
            "remove absolute repository prefixes from all JUnit evidence",
            "remove Node duration_ms while preserving authoritative footer counters",
        ],
        "preserved": [
            "testcase identity",
            "failure, error, and skip state",
            "failure type and message",
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
    result["passed"] = result["collected"] - result["errors"] - result["failed"] - result["skipped"]
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
        raise SystemExit("Node JUnit footer is incomplete")
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


def normalize_problem(value: str) -> str:
    normalized = value.replace(str(ROOT), "<REPO>").replace(
        str(ROOT).replace("\\", "/"), "<REPO>"
    )
    normalized = re.sub(
        r"[A-Za-z]:[/\\][^\n\r'\"]*?(?=(?:[/\\]tests|[/\\]scripts|\n|\r|'|\"))",
        "<ABSOLUTE_PATH>",
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def failure_records(path: Path, *, node: bool) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    records: list[dict[str, Any]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        if problem is None:
            continue
        if node:
            file_name = str(case.get("file", "")).replace("\\", "/")
            node_id = f"{file_name}::{case.get('name', '')}"
        else:
            node_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        normalized = {
            "message": normalize_problem(problem.get("message", "")),
            "node_id": node_id,
            "problem_type": problem.get("type", ""),
        }
        records.append(
            {
                **normalized,
                "normalized_failure_fingerprint": canonical_hash(normalized),
            }
        )
    return records


def authority_projection_drift() -> dict[str, Any]:
    if sha256_id(J02_INVENTORY) != EXPECTED_J02_FILE_HASH:
        raise SystemExit("J02 inventory changed after J02-0003")
    if sha256_id(S04_BINDING) != EXPECTED_S04_FILE_HASH:
        raise SystemExit("S04 binding changed after S04-0003")
    j02_report = read_json(ROOT / "artifacts/work_packages/J02/attempts/0003/report.json")
    s04_report = read_json(ROOT / "artifacts/work_packages/S04/attempts/0003/report.json")
    j02_recorded = next(
        row["sha256"]
        for row in j02_report["changed_files"]
        if row["path"] == "plugins/epistemic-foundry/skills/skill-inventory.json"
    )
    s04_recorded = s04_report["source_binding"]["manifest_sha256"]
    if j02_recorded != EXPECTED_J02_FILE_HASH:
        raise SystemExit("J02-0003 does not bind the live inventory bytes")
    if s04_report["source_binding"]["status"] != "PASS":
        raise SystemExit("S04-0003 prior binding was not PASS")

    inventory = read_json(J02_INVENTORY)
    master_bindings = [
        source["sha256"]
        for reference in inventory["references"]
        for source in reference["authority_sources"]
        if source.get("path") == "MASTER_SPEC.md"
    ]
    if not master_bindings or set(master_bindings) != {PRIOR_J02_MASTER_HASH}:
        raise SystemExit("J02 stale MASTER_SPEC binding is not the expected prior hash")
    binding = read_json(S04_BINDING)
    if binding.get("successor_sha256") != PRIOR_S04_MANIFEST_HASH.removeprefix("sha256:"):
        raise SystemExit("S04 stale manifest successor is not the expected prior hash")
    if s04_recorded != PRIOR_S04_MANIFEST_HASH:
        raise SystemExit("S04-0003 report does not bind the expected prior manifest")
    return {
        "C01_modified_J02_or_S04_files": False,
        "J02": {
            "current_file_sha256": sha256_id(J02_INVENTORY),
            "current_master_spec_sha256": sha256_id(MASTER_SPEC),
            "master_spec_binding_count": len(master_bindings),
            "owner": "J02",
            "prior_attempt": "J02-0003",
            "stale_master_spec_sha256": PRIOR_J02_MASTER_HASH,
            "target_path": J02_INVENTORY.relative_to(ROOT).as_posix(),
        },
        "S04": {
            "current_binding_file_sha256": sha256_id(S04_BINDING),
            "current_manifest_sha256": sha256_id(MANIFEST),
            "owner": "S04",
            "prior_attempt": "S04-0003",
            "stale_successor_sha256": PRIOR_S04_MANIFEST_HASH,
            "target_path": S04_BINDING.relative_to(ROOT).as_posix(),
        },
        "classification": "UNAUTHORIZED_CROSS_PACKAGE_CORRECTION_SPEC_GAP",
        "status": "SPEC_GAP",
    }


def regression_evidence() -> dict[str, Any]:
    targeted = pytest_summary(TARGETED_JUNIT)
    python = pytest_summary(PYTHON_JUNIT)
    node = node_summary(NODE_JUNIT)
    if not (
        targeted["collected"] == targeted["passed"] == 104
        and targeted["failed"] == targeted["errors"] == targeted["skipped"] == 0
    ):
        raise SystemExit(f"targeted C01 suite is not 104/104: {targeted}")
    if not (
        python["collected"] == 1073
        and python["passed"] == 1056
        and python["failed"] == 17
        and python["errors"] == python["skipped"] == 0
    ):
        raise SystemExit(f"full Python counters changed: {python}")
    if not (
        node["collected"] == 820
        and node["passed"] == 817
        and node["failed"] == 3
        and node["cancelled"] == node["skipped"] == node["todo"] == 0
        and node["xml_failure_count"] == 3
        and node["xml_error_count"] == 0
    ):
        raise SystemExit(f"full Node counters changed: {node}")

    python_failures = failure_records(PYTHON_JUNIT, node=False)
    if {row["node_id"] for row in python_failures} != {
        f"tests.packaging.test_canonical_registry::{name}" for name in PYTHON_FAILURE_NAMES
    }:
        raise SystemExit("Python failure identity set changed")
    for row in python_failures:
        if "expected 126 canonical schemas, found 127" not in row["message"]:
            raise SystemExit(f"unexpected Python failure signature: {row['node_id']}")
        row.update(
            {
                "affected_runtime_path": "scripts/build/canonical_registry/materialize.py",
                "classification": "EXPECTED_B04_0009_PROJECTION_DEBT",
                "owner": "B04",
                "resolving_attempt": "B04-0009",
            }
        )

    node_failures = failure_records(NODE_JUNIT, node=True)
    if {row["node_id"] for row in node_failures} != set(NODE_FAILURES):
        raise SystemExit("Node failure identity set changed")
    for row in node_failures:
        owner = NODE_FAILURES[row["node_id"]]
        if owner == "J02" and "authority source has changed" not in row["message"]:
            raise SystemExit("J02 failure signature changed")
        if owner == "S04" and "active manifest does not match the bound successor" not in row["message"]:
            raise SystemExit("S04 failure signature changed")
        row.update(
            {
                "classification": "UNAUTHORIZED_CROSS_PACKAGE_CORRECTION_SPEC_GAP",
                "owner": owner,
                "resolving_attempt": f"{owner}-0004",
            }
        )

    baseline = read_json(O01_REPORT)["regression"]["full_node"]
    if baseline.get("collected") != 819 or baseline.get("passed") != 819 or baseline.get("failed") != 0:
        raise SystemExit("O01-0002 green Node baseline changed")
    projection = authority_projection_drift()
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_projection_drift": projection,
        "baseline": {
            "attempt_id": "O01-0002",
            "full_node": "PASS_819_OF_819",
            "report_sha256": sha256_id(O01_REPORT),
        },
        "full_node": node,
        "full_python": python,
        "node_failures": node_failures,
        "node_new_failure_count": len(node_failures),
        "python_failures": python_failures,
        "python_projection_debt_failure_count": len(python_failures),
        "targeted_contracts": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
        "status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
    }


def git_diff_check() -> dict[str, Any]:
    paths = [
        "MASTER_SPEC.md",
        "manifests/acceptance_matrix.yaml",
        "manifests/development_manifest.yaml",
        "docs/api_contract.md",
        "docs/retrieval_contract.md",
        "schemas/retrieval-candidate.schema.json",
        "examples/sample_retrieval-candidate.json",
        "tests/contracts/openapi/test_scientific_contracts.py",
        "tests/contracts/openapi/test_openapi_contract.py",
        "tests/contracts/test_k01_document_contracts.py",
        "tests/test_f01_epistemic_work_classifier.py",
        "artifacts/work_packages/C01/attempts/0008",
    ]
    result = subprocess.run(
        ["git", "diff", "--check", "--", *paths],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"C01-0008 scoped git diff --check failed: {result.stdout}{result.stderr}")
    return {
        "advisory_output": (result.stdout + result.stderr).strip(),
        "command": "git diff --check -- <C01-0008 bounded product and attempt paths>",
        "exit_code": 0,
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    projection = authority_projection_drift()
    return {
        "attempt_id": ATTEMPT_ID,
        "approved_C01_product_surface": [
            "schemas/retrieval-candidate.schema.json",
            "examples/sample_retrieval-candidate.json",
            "MASTER_SPEC.md",
            "manifests/acceptance_matrix.yaml",
            "manifests/development_manifest.yaml",
            "docs/api_contract.md",
            "docs/retrieval_contract.md",
            "tests/contracts/openapi/test_scientific_contracts.py",
            "tests/contracts/openapi/test_openapi_contract.py",
            "tests/contracts/test_k01_document_contracts.py",
            "tests/test_f01_epistemic_work_classifier.py",
        ],
        "attempt_artifact_scope": "artifacts/work_packages/C01/attempts/0008/**",
        "cross_package_files_modified_by_C01_0008": [],
        "J02_file_matches_J02_0003": projection["J02"]["current_file_sha256"] == EXPECTED_J02_FILE_HASH,
        "S04_file_matches_S04_0003": projection["S04"]["current_binding_file_sha256"] == EXPECTED_S04_FILE_HASH,
        "dirty_worktree_preserved": True,
        "reset_clean_stash_commit_push_performed": False,
        "schema_weakening_count": 0,
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "authorized_order_before_gap": [
            "C01-0008",
            "C02-0004",
            "B04-0009",
            "O02-0002",
            "C04-0004",
            "NEXT_UNUSED_B04_FINAL",
        ],
        "C01-0008": "SPEC_GAP_C01_SG005",
        "C02-0004": "WAITING_ON_C01",
        "B04-0009": "WAITING_ON_C01_AND_C02",
        "O02-0002": "WAITING_ON_B04_0009",
        "C04-0004": "WAITING_ON_O02_0002_AND_FRESH_PROJECTION",
        "completion_ready": False,
        "global_implementation_gate": "fail",
        "recommended_resolving_order_requiring_product_owner_decision": [
            "J02-0004",
            "S04-0004",
            "C01-0009",
            "C02-0004",
            "B04-0009",
            "O02-0002",
            "C04-0004",
            "NEXT_UNUSED_B04_FINAL",
        ],
        "static_dependency_cycle_added": False,
        "status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
    }


def command_records() -> list[dict[str, Any]]:
    rows: list[tuple[str, int | None, str]] = [
        ("Inspect HD-EF4-O02-SG001 and C01-0008 exact write scope", 0, "PASS"),
        ("Implement strict RetrievalCandidate schema and deterministic example", 0, "PASS"),
        ("Run C01 targeted contract suite with JUnit", 0, "PASS: 104/104"),
        ("Run full Python regression suite with JUnit", 1, "EXPECTED_DEBT: 1056 passed, 17 B04-0009 projection failures"),
        ("Run full Node regression suite with JUnit", 1, "SPEC_GAP: 817 passed, 3 new J02/S04 authority-projection failures"),
        ("Compare Node failures to O01-0002 green 819/819 baseline", 0, "PASS: all three current failures are new"),
        ("Verify J02 and S04 projection files match their prior PASS attempt hashes", 0, "PASS: C01-0008 did not modify either file"),
        ("Run scoped git diff --check", 0, "PASS: no whitespace error; line-ending advisories remain visible"),
        ("Normalize volatile JUnit fields while preserving semantic signatures", 0, "PASS when builder completes"),
        ("Build and verify C01-0008 deterministic evidence", 0, "PASS when builder completes"),
        ("Perform primary-session separate adversarial contract review", 0, "PASS review; package remains SPEC_GAP; actor_independence=false"),
    ]
    return [
        {
            "command": command,
            "command_id": f"C01-0008-C{index:03d}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": "C01-0008 RetrievalCandidate contract and fail-closed regression closeout",
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
    return f"""# C01-0008 independent contract review

Package recommendation: `SPEC_GAP ({SPEC_GAP_ID})`

Implementation finding: `VERIFIED`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents are
forbidden by the active product-owner contract, so this is a procedurally
separate primary-session review, not external actor-independent certification.

## Contract result

- The active authority is exactly 127 Draft 2020-12 schemas and 127 matching
  examples. All schemas meta-validate, all `$id` values are unique, mapping is
  one-to-one, and all examples validate.
- RetrievalCandidate is strict (`additionalProperties=false`), recomputes
  candidate ID `{EXPECTED_CANDIDATE_ID}`, query hash `{EXPECTED_QUERY_HASH}`,
  and content hash `{EXPECTED_CANDIDATE_HASH}`. Missing fields, unknown fields,
  and semantic tampering fail closed.
- OpenAPI remains 3.1.1 with 33 unique operations and resolvable canonical
  schema references.
- The targeted C01 gate is {regression['targeted_contracts']['passed']}/
  {regression['targeted_contracts']['collected']} with zero failures or skips.

## Regression disposition

- Full Python is {regression['full_python']['passed']} passed and
  {regression['full_python']['failed']} failed. Every failure is the exact
  `expected 126 canonical schemas, found 127` B04 materializer signature and is
  classified `EXPECTED_B04_0009_PROJECTION_DEBT`; B04-0009 is already ordered
  after C02-0004.
- Full Node is {regression['full_node']['passed']} passed and
  {regression['full_node']['failed']} failed by the authoritative Node footer.
  O01-0002 previously passed 819/819. The two J02 failures bind the old
  MASTER_SPEC hash in `skill-inventory.json`; the S04 failure binds the old
  development-manifest successor hash.
- `skill-inventory.json` still has the exact J02-0003 PASS hash and
  `development-manifest.binding.json` still has the exact S04-0003 PASS hash.
  C01-0008 did not modify either downstream-owned file.

## Blocking decision

C01 owns neither downstream projection. The active decision authorizes the
serial sequence beginning with C01-0008 but does not authorize J02-0004 or
S04-0004 correction attempts. Continuing by editing those files would expand
authority without a product-owner decision. Therefore the correct package
result is SPEC_GAP, not PASS, FAIL, or BLOCKED.

The recommended prospective order is J02-0004, S04-0004, C01-0009
revalidation, then the previously authorized C02-0004 → B04-0009 → O02-0002 →
C04-0004 → final B04 sequence. No downstream attempt starts before the new
decision. Existing attempts, RAH evidence/generations, and the dirty worktree
remain preserved; `completion_ready=false`.
"""


def live_documents() -> dict[str, dict[str, Any]]:
    normalization = normalize_junit_files()
    canonical = validate_canonical_contracts()
    candidate = candidate_verification()
    openapi = validate_openapi()
    manifest = manifest_contract()
    regression = regression_evidence()
    scope = write_scope_evidence()
    diff = git_diff_check()
    dependency = dependency_status()
    return {
        "canonical-contract-verification.json": {
            "attempt_id": ATTEMPT_ID,
            "canonical_contract": canonical,
            "git_diff_check": diff,
            "manifest_contract": manifest,
            "openapi": openapi,
            "package_status": "SPEC_GAP",
            "retrieval_candidate": candidate,
            "spec_gap_id": SPEC_GAP_ID,
            "status": "CONFORMANT_WITH_CROSS_PACKAGE_PROJECTION_GAP",
        },
        "retrieval-candidate-verification.json": candidate,
        "full-regression-impact.json": regression,
        "junit-normalization-verification.json": normalization,
        "write-scope-verification.json": scope,
        "dependency-status.json": dependency,
        "phase-artifact-reconciliation.json": {
            "attempt_id": ATTEMPT_ID,
            "checks": {
                "canonical_contract": "PASS_127_OF_127",
                "full_node": "SPEC_GAP_817_PASS_3_J02_S04_FAILURES",
                "full_python": "EXPECTED_B04_0009_DEBT_1056_PASS_17_FAILURES",
                "openapi": "PASS_3_1_1_33_OPERATIONS",
                "retrieval_candidate": "PASS",
                "targeted_contracts": "PASS_104_OF_104",
            },
            "completion_receipt_claimed": False,
            "completion_ready": False,
            "global_implementation_gate": "fail",
            "next_attempt": None,
            "status": "SPEC_GAP",
            "spec_gap_id": SPEC_GAP_ID,
        },
    }


def report_document(
    documents: dict[str, dict[str, Any]], rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "CANONICAL_RETRIEVAL_CANDIDATE_MIGRATION",
        "blocker": SPEC_GAP_ID,
        "canonical_contract": {
            "example_count": 127,
            "openapi_operation_count": 33,
            "openapi_version": "3.1.1",
            "schema_count": 127,
            "schema_example_one_to_one": True,
            "status": "PASS",
        },
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "C01_prior_attempts": "IMMUTABLE_HISTORY",
            "J02_0003_and_S04_0003_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "VERIFIED",
        "next_state": documents["dependency-status.json"],
        "not_claimed": [
            "C01 package PASS",
            "J02-0004 or S04-0004 authority",
            "C02-0004 start",
            "B04-0009 projection",
            "O02-0002 implementation",
            "C04-0004 conformance",
            "final B04 packaging",
            "repository release readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": [
            f"artifacts/work_packages/C01/attempts/0008/{name}" for name in OUTPUT_NAMES
        ],
        "package_status": "SPEC_GAP",
        "regression": {
            "node": "SPEC_GAP_817_PASS_3_J02_S04_FAILURES",
            "python": "EXPECTED_B04_0009_DEBT_1056_PASS_17_FAILURES",
            "targeted": "PASS_104_OF_104",
            "unexpected_skip_xfail_todo_or_cancellation_count": 0,
        },
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_C01_0008_implementation_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_REVIEW_PACKAGE_SPEC_GAP",
        },
        "spec_gap_id": SPEC_GAP_ID,
        "status": "SPEC_GAP",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": documents["write-scope-verification.json"],
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
    *,
    core_generation: str,
    contract_audit_evidence_id: str,
    documented_gap_evidence_id: str,
    final_closeout_evidence_id: str,
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "completion_ready": False,
        "contract_audit_evidence_id": contract_audit_evidence_id,
        "core_generation": core_generation,
        "documented_gap_evidence_id": documented_gap_evidence_id,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "blocked",
    }
    write_json("report.json", report_document(documents, rah_state=rah_state))
    return rah_state


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored C01-0008 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored C01-0008 commands differ from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored C01-0008 review differs from live evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict) or rah_state.get("status") != "blocked":
            raise SystemExit("invalid C01-0008 RAH report binding")
    if report != report_document(documents, rah_state=rah_state):
        raise SystemExit("stored C01-0008 report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "full_node": "817 passed, 3 J02/S04 failures",
        "full_python": "1056 passed, 17 B04-0009 projection failures",
        "implementation_status": "VERIFIED",
        "package_status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
        "status": "PASS_EVIDENCE_VERIFICATION",
        "targeted_contracts": "104/104",
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
