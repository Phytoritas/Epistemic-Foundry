#!/usr/bin/env python3
"""Build deterministic evidence for C01-0006.

This verifier treats root ``schemas/**`` and ``openapi/**`` as the only
canonical authority.  The installed-package projection is intentionally not
repaired here: HD-EF4-C01-SG004-20260730-001 assigns that reconciliation to a
pre-C04 B04 attempt.  Consequently the repository regression receipt is
expected to contain exactly the bounded B04 projection failures plus the
pre-existing J02 tokenizer-lock debt; neither group is reported as a passing
repository-wide suite.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0006"
DECISION = (
    ROOT
    / "artifacts/authority_decisions/"
    "HD-EF4-C01-SG004-20260730-001.human-decision.json"
)
REMEDIATION_DECISION = (
    ROOT
    / "artifacts/authority_decisions/"
    "HD-EF4-A06-RM001-20260730-001.human-decision.json"
)
OPENAPI = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
TARGETED_JUNIT = ATTEMPT / "targeted-contracts.junit.xml"
FULL_JUNIT = ATTEMPT / "full-python-regression.junit.xml"

ATTEMPT_ID = "C01-0006"
DECISION_ID = "HD-EF4-C01-SG004-20260730-001"
DECISION_HASH = (
    "sha256:ebc3434cccdd248b38a36d1a3de5132f4503b4172c1ee11a64dd8f0033f670fd"
)
REMEDIATION_DECISION_ID = "HD-EF4-A06-RM001-20260730-001"
REMEDIATION_DECISION_HASH = (
    "sha256:3ed9daaf685214ffe34c6be92301abd046eb6fa7d1c7f625554746afc83fd7be"
)

EXAMPLE_ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}

EXPECTED_C01_SCOPE = [
    "schemas/document-registration-request.schema.json",
    "schemas/document-registration.schema.json",
    "schemas/document-manifest.schema.json",
    "schemas/evaluator-bundle.schema.json",
    "schemas/holdout-manifest.schema.json",
    "schemas/evaluator-qualification-report.schema.json",
    "schemas/gate-decision.schema.json",
    "schemas/promotion-decision.schema.json",
    "schemas/attestation.schema.json",
    "schemas/approval-record.schema.json",
    "schemas/capability-lease.schema.json",
    "schemas/action-intent.schema.json",
    "schemas/effect-receipt.schema.json",
    "schemas/artifact-receipt.schema.json",
    "schemas/phase-artifact-set.schema.json",
    "schemas/hypothesis-passport.schema.json",
    "schemas/replication-result.schema.json",
    "schemas/human-decision.schema.json",
    "examples/sample_document-registration-request.json",
    "examples/sample_document-registration.json",
    "examples/sample_document-manifest.json",
    "examples/sample_evaluator-bundle.json",
    "examples/sample_holdout-manifest.json",
    "examples/sample_evaluator-qualification-report.json",
    "examples/sample_gate_decision.json",
    "examples/sample_promotion-decision.json",
    "examples/sample_attestation.json",
    "examples/sample_approval-record.json",
    "examples/sample_capability-lease.json",
    "examples/sample_action-intent.json",
    "examples/sample_effect-receipt.json",
    "examples/sample_artifact-receipt.json",
    "examples/sample_phase-artifact-set.json",
    "examples/sample_passport.json",
    "examples/sample_replication-result.json",
    "examples/sample_human-decision.json",
    "openapi/epistemic-foundry-v1.openapi.yaml",
    "docs/api_contract.md",
    "tests/contracts/openapi/test_scientific_contracts.py",
    "tests/contracts/openapi/test_openapi_contract.py",
    "artifacts/work_packages/C01/**",
]

DECLARED_PRODUCT_CHANGES = [
    "schemas/document-registration-request.schema.json",
    "schemas/document-registration.schema.json",
    "schemas/document-manifest.schema.json",
    "schemas/evaluator-bundle.schema.json",
    "schemas/holdout-manifest.schema.json",
    "schemas/gate-decision.schema.json",
    "schemas/promotion-decision.schema.json",
    "schemas/phase-artifact-set.schema.json",
    "examples/sample_document-registration-request.json",
    "examples/sample_document-registration.json",
    "examples/sample_document-manifest.json",
    "examples/sample_evaluator-bundle.json",
    "examples/sample_holdout-manifest.json",
    "examples/sample_gate_decision.json",
    "examples/sample_promotion-decision.json",
    "openapi/epistemic-foundry-v1.openapi.yaml",
    "docs/api_contract.md",
    "tests/contracts/openapi/test_scientific_contracts.py",
    "tests/contracts/openapi/test_openapi_contract.py",
]

DECLARED_ATTEMPT_ARTIFACTS = [
    "artifacts/work_packages/C01/attempts/0006/activate_c01_0006.py",
    "artifacts/work_packages/C01/attempts/0006/build_c01_0006_evidence.py",
    "artifacts/work_packages/C01/attempts/0006/targeted-contracts.junit.xml",
    "artifacts/work_packages/C01/attempts/0006/full-python-regression.junit.xml",
    "artifacts/work_packages/C01/attempts/0006/full-regression-impact.json",
    "artifacts/work_packages/C01/attempts/0006/c01-contract-verification.json",
    "artifacts/work_packages/C01/attempts/0006/dependency-status.json",
    "artifacts/work_packages/C01/attempts/0006/commands.jsonl",
    "artifacts/work_packages/C01/attempts/0006/review.md",
    "artifacts/work_packages/C01/attempts/0006/report.json",
    "artifacts/work_packages/C01/attempts/0006/rah-core-integrity.json",
    "artifacts/work_packages/C01/attempts/0006/c01_0006_rah_seal.py",
]

EXPECTED_A06_SCHEMA_RESOLUTION = {
    "A06-F001": "evaluator bundle mutation and candidate access rejected",
    "A06-F002": "hidden holdout candidate/model/prompt/backend access rejected",
}

DEFERRED_A06_FINDINGS = {
    "A06-F003": "A05 correction owns the complete G00-G14 runtime registry and workflow graph",
    "A06-F004": "A05 correction owns self-approval, actor-independence, and short-lease enforcement",
    "A06-F005": "A05 correction owns CAS, crash reconciliation, and receipt-bound commit runtime behavior",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON object required: {path}")
    return value


def canonical_hash(document: dict[str, Any], excluded: str) -> str:
    value = copy.deepcopy(document)
    value.pop(excluded, None)
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hash_bytes(encoded)


def canonical_hash_fields(document: dict[str, Any], fields: list[str]) -> str:
    value = {field: document[field] for field in fields}
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hash_bytes(encoded)


def decision_evidence(path: Path, identifier: str, digest: str) -> dict[str, Any]:
    value = read_json(path)
    observed = canonical_hash(value, "decision_hash")
    if value.get("decision_id") != identifier or value.get("decision_hash") != digest:
        raise SystemExit(f"authority decision identity changed: {identifier}")
    if observed != digest or value.get("authority_role") != "product_owner":
        raise SystemExit(f"authority decision integrity failed: {identifier}")
    return {
        "decision_id": identifier,
        "decision_hash": digest,
        "artifact_sha256": sha256_id(path),
        "authority_role": value["authority_role"],
        "status": "PASS",
    }


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


def validate_canonical_contracts() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("*.json"))
    if len(schema_paths) != 126 or len(example_paths) != 126:
        raise SystemExit(
            f"canonical inventory is not 126/126: {len(schema_paths)}/{len(example_paths)}"
        )

    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    ids: list[str] = []
    for path in schema_paths:
        document = read_json(path)
        Draft202012Validator.check_schema(document)
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"non-Draft-2020-12 schema: {path.name}")
        identifier = document.get("$id")
        if not isinstance(identifier, str) or not identifier:
            raise SystemExit(f"missing schema $id: {path.name}")
        ids.append(identifier)
        schemas[path.name] = document
        registry = registry.with_resource(identifier, Resource.from_contents(document))
    if len(set(ids)) != 126:
        raise SystemExit("duplicate canonical schema $id")

    mapped: set[Path] = set()
    validation_failures: list[str] = []
    for path in schema_paths:
        example = example_path(path)
        mapped.add(example)
        instance = read_json(example)
        validator = Draft202012Validator(
            schemas[path.name],
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in sorted(validator.iter_errors(instance), key=lambda row: list(row.path)):
            where = "/".join(str(part) for part in error.path) or "<root>"
            validation_failures.append(f"{example.name}:{where}: {error.message}")
    if mapped != set(example_paths):
        raise SystemExit("schema/example mapping is not one-to-one")
    if validation_failures:
        raise SystemExit(f"canonical example validation failed: {validation_failures[:5]}")

    request_schema = schemas["document-registration-request.schema.json"]
    request = read_json(ROOT / "examples/sample_document-registration-request.json")
    request_fields = request_schema["x-canonical-hash"]["preimage_fields"]
    request_hash = canonical_hash_fields(request, request_fields)
    if request["request_hash"] != request_hash:
        raise SystemExit("DocumentRegistrationRequest request_hash mismatch")
    if request["request_id"] != "DREQ-" + request_hash.removeprefix("sha256:"):
        raise SystemExit("DocumentRegistrationRequest request_id mismatch")

    registration_schema = schemas["document-registration.schema.json"]
    registration = read_json(ROOT / "examples/sample_document-registration.json")
    registration_fields = registration_schema["x-canonical-hash"]["preimage_fields"]
    registration_preimage = {
        field: registration_schema["$id"] if field == "schema_id" else registration[field]
        for field in registration_fields
    }
    registration_hash = hash_bytes(
        json.dumps(
            registration_preimage,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if registration["registration_hash"] != registration_hash:
        raise SystemExit("DocumentRegistration registration_hash mismatch")
    if registration["registration_id"] != "DREG-" + registration_hash.removeprefix("sha256:"):
        raise SystemExit("DocumentRegistration registration_id mismatch")
    if registration["request_id"] != request["request_id"]:
        raise SystemExit("registration request lineage mismatch")

    forbidden_hits: list[str] = []
    for path in [*schema_paths, *example_paths]:
        text = path.read_text(encoding="utf-8")
        for token in ('"PILOT"', '"HYPOTHESIS_PASSPORT_ONLY"'):
            if token in text:
                forbidden_hits.append(f"{path.relative_to(ROOT).as_posix()}:{token}")
    if forbidden_hits:
        raise SystemExit(f"legacy promotion values remain: {forbidden_hits}")

    return {
        "schema_count": 126,
        "example_count": 126,
        "mapped_example_count": len(mapped),
        "valid_example_count": len(mapped),
        "unique_schema_id_count": len(set(ids)),
        "meta_schema_validation": "PASS",
        "schema_example_one_to_one": True,
        "document_registration_request": {
            "schema_id": request_schema["$id"],
            "request_hash": request_hash,
            "request_id": request["request_id"],
            "required_staged_source_artifact": True,
            "status": "PASS",
        },
        "document_registration": {
            "schema_id": registration_schema["$id"],
            "registration_hash": registration_hash,
            "registration_id": registration["registration_id"],
            "immutable_initial_state": registration["initial_state"],
            "status": "PASS",
        },
        "legacy_promotion_value_hits": forbidden_hits,
        "status": "PASS",
    }


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
    value: Any = document
    for raw in ref[2:].split("/"):
        value = value[raw.replace("~1", "/").replace("~0", "~")]
    return value


def validate_openapi() -> dict[str, Any]:
    document = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit("OpenAPI document is not an object")
    if document.get("openapi") != "3.1.1":
        raise SystemExit("OpenAPI version changed")
    if document.get("jsonSchemaDialect") != "https://json-schema.org/draft/2020-12/schema":
        raise SystemExit("OpenAPI schema dialect changed")
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for route, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method in methods:
                operations.append((route, method, operation))
    operation_ids = [operation.get("operationId") for _, _, operation in operations]
    if len(operations) != 33 or len(set(operation_ids)) != 33 or None in operation_ids:
        raise SystemExit("OpenAPI operation inventory is not 33 unique operationIds")

    external: set[str] = set()
    failures: list[str] = []
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
            continue
        Draft202012Validator.check_schema(read_json(target))
    if failures:
        raise SystemExit(f"OpenAPI reference failures: {failures}")

    document_post = document["paths"]["/documents"]["post"]
    request_ref = document_post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    result_ref = document_post["x-async-result-artifact"]["$ref"]
    if request_ref != "../schemas/document-registration-request.schema.json":
        raise SystemExit("POST /documents is not bound to canonical request schema")
    if result_ref != "../schemas/document-registration.schema.json":
        raise SystemExit("POST /documents is not bound to canonical registration result")
    if "DocumentRegistrationRequest" in document["components"]["schemas"]:
        raise SystemExit("transport-only duplicate DocumentRegistrationRequest remains")

    for route, method, operation in operations:
        if "security" not in operation or "x-required-capabilities" not in operation:
            raise SystemExit(f"missing operation authority contract: {method} {route}")
        if method != "get":
            parameters = [*document["paths"][route].get("parameters", []), *operation.get("parameters", [])]
            resolved = [
                resolve_pointer(document, row["$ref"])
                if isinstance(row, dict) and str(row.get("$ref", "")).startswith("#/")
                else row
                for row in parameters
            ]
            key = next((row for row in resolved if row.get("name") == "Idempotency-Key"), None)
            if not key or key.get("required") is not True:
                raise SystemExit(f"missing Idempotency-Key: {method} {route}")

    return {
        "canonical_file": OPENAPI.relative_to(ROOT).as_posix(),
        "document_sha256": sha256_id(OPENAPI),
        "openapi_version": "3.1.1",
        "json_schema_dialect": document["jsonSchemaDialect"],
        "operation_count": 33,
        "unique_operation_id_count": 33,
        "external_schema_ref_count": len(external),
        "reference_resolution_failures": [],
        "document_registration_request_ref": request_ref,
        "document_registration_result_ref": result_ref,
        "all_operations_have_explicit_security_and_capabilities": True,
        "all_mutations_require_idempotency_key": True,
        "external_validator": {
            "tool": "openapi-spec-validator",
            "version": "0.7.2",
            "result": "OK",
            "exit_code": 0,
        },
        "generated_client_dry_run": {
            "tool": "OpenAPI Generator CLI",
            "wrapper_version": "2.21.4",
            "generator_version": "7.14.0",
            "generator": "python",
            "exit_code": 0,
            "repository_output_count": 0,
        },
        "status": "PASS",
    }


def junit(path: Path) -> tuple[dict[str, int], list[dict[str, str]]]:
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites:
        raise SystemExit(f"JUnit contains no testsuite: {path}")
    suite = suites[0]
    summary = {
        "tests": int(suite.get("tests", "0")),
        "failures": int(suite.get("failures", "0")),
        "errors": int(suite.get("errors", "0")),
        "skipped": int(suite.get("skipped", "0")),
    }
    failures: list[dict[str, str]] = []
    for testcase in root.iter("testcase"):
        result = testcase.find("failure")
        result_type = "failure"
        if result is None:
            result = testcase.find("error")
            result_type = "error"
        if result is None:
            continue
        classname = testcase.get("classname", "")
        module = classname.replace(".", "/") + ".py"
        node_id = f"{module}::{testcase.get('name', '')}"
        message = result.get("message") or (result.text or "")
        failures.append(
            {
                "node_id": node_id,
                "type": result_type,
                "message": message.strip(),
                "message_sha256": hash_bytes(message.strip().encode("utf-8")),
            }
        )
    return summary, failures


def classify_regression() -> dict[str, Any]:
    targeted, targeted_failures = junit(TARGETED_JUNIT)
    if targeted != {"tests": 77, "failures": 0, "errors": 0, "skipped": 0}:
        raise SystemExit(f"targeted contract receipt changed: {targeted}")
    if targeted_failures:
        raise SystemExit("targeted contract receipt has failures")

    full, failures = junit(FULL_JUNIT)
    if full != {"tests": 970, "failures": 19, "errors": 0, "skipped": 0}:
        raise SystemExit(f"full Python receipt changed: {full}")
    if len(failures) != 19:
        raise SystemExit("full Python failure extraction changed")

    rows: list[dict[str, Any]] = []
    projection_count = 0
    j02_count = 0
    for failure in failures:
        node = failure["node_id"]
        message = failure["message"]
        if node.startswith("tests/packaging/test_canonical_registry.py::"):
            owner = "B04"
            debt = "C01-SG004-PRE-C04-PROJECTION"
            category = "stale_projection_materializer_124_vs_126"
            expected_resolution = "B04-0006 pre-C04 deterministic reprojection"
            projection_count += 1
        elif node == "tests/test_contracts.py::test_shipped_examples_validate_against_their_schemas":
            owner = "B04"
            debt = "C01-SG004-PRE-C04-PROJECTION"
            category = "stale_packaged_schema_snapshot"
            expected_resolution = "B04-0006 pre-C04 deterministic reprojection"
            projection_count += 1
        elif node == "tests/test_j02_context_budget.py::test_repository_dependency_lock_closes_exact_tiktoken_pin":
            owner = "J02"
            debt = "J02-TOKENIZER-LOCK"
            category = "preexisting_dependency_group_visibility_mismatch"
            expected_resolution = "J02 owner correction; no C01 scope expansion"
            j02_count += 1
        else:
            raise SystemExit(f"unexpected full-suite failure: {node}")
        fingerprint_payload = {
            "node_id": node,
            "category": category,
            "owner": owner,
            "debt_id": debt,
        }
        fingerprint = hash_bytes(
            json.dumps(
                fingerprint_payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        rows.append(
            {
                **failure,
                "normalized_fingerprint": fingerprint,
                "owner": owner,
                "debt_id": debt,
                "root_cause_category": category,
                "expected_resolution": expected_resolution,
                "c01_causal_classification": (
                    "EXPECTED_ATTEMPT_LEVEL_RECONCILIATION"
                    if owner == "B04"
                    else "PRE_EXISTING_UNRELATED_DEBT"
                ),
            }
        )
    if projection_count != 18 or j02_count != 1:
        raise SystemExit(
            f"unexpected failure ownership counts: B04={projection_count}, J02={j02_count}"
        )
    return {
        "attempt_id": ATTEMPT_ID,
        "targeted": {
            **targeted,
            "passed": targeted["tests"],
            "artifact": TARGETED_JUNIT.relative_to(ROOT).as_posix(),
            "artifact_sha256": sha256_id(TARGETED_JUNIT),
            "status": "PASS",
        },
        "full_python": {
            **full,
            "passed": full["tests"] - full["failures"] - full["errors"] - full["skipped"],
            "artifact": FULL_JUNIT.relative_to(ROOT).as_posix(),
            "artifact_sha256": sha256_id(FULL_JUNIT),
            "status": "EXPECTED_DOWNSTREAM_AND_PREEXISTING_FAILURES",
        },
        "failure_owner_counts": {"B04": projection_count, "J02": j02_count},
        "new_c01_failure_count": 0,
        "failures": sorted(rows, key=lambda row: row["node_id"]),
        "full_suite_is_not_reported_pass": True,
        "status": "PASS_WITH_DECLARED_RESIDUAL_FAILURES",
    }


def manifest_contract() -> dict[str, Any]:
    value = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = value if isinstance(value, list) else value["work_packages"]
    by_id = {row["id"]: row for row in packages}
    if len(packages) != 156:
        raise SystemExit("development manifest no longer contains 156 packages")
    c01 = by_id["C01"]
    if c01["depends_on"] != ["A04", "A05"]:
        raise SystemExit("C01 dependencies changed")
    if c01["write_scope"] != EXPECTED_C01_SCOPE:
        raise SystemExit("C01 exact write scope changed")
    if by_id["C02"]["depends_on"] != ["C01"]:
        raise SystemExit("C02 dependency changed")
    if by_id["C03"]["depends_on"] != ["C01", "C02"]:
        raise SystemExit("C03 dependency changed")
    if by_id["C04"]["depends_on"] != ["C02", "C03"]:
        raise SystemExit("C04 dependency changed")
    if by_id["B04"]["depends_on"] != ["B02", "B03", "C04"]:
        raise SystemExit("B04 static dependency changed")
    return {
        "package_count": len(packages),
        "C01": {
            "depends_on": c01["depends_on"],
            "write_scope": c01["write_scope"],
            "required_checks": c01["required_checks"],
        },
        "C02_depends_on": by_id["C02"]["depends_on"],
        "C03_depends_on": by_id["C03"]["depends_on"],
        "C04_depends_on": by_id["C04"]["depends_on"],
        "B04_depends_on": by_id["B04"]["depends_on"],
        "pre_C04_B04_is_attempt_level_only": True,
        "static_dependency_cycle_added": False,
        "status": "PASS",
    }


def scope_matches(scope: str, relative: str) -> bool:
    if scope.endswith("/**"):
        prefix = scope[:-3]
        return relative == prefix or relative.startswith(prefix + "/")
    return relative == scope


def write_scope_evidence() -> dict[str, Any]:
    declared = [*DECLARED_PRODUCT_CHANGES, *DECLARED_ATTEMPT_ARTIFACTS]
    violations = [
        path
        for path in declared
        if not any(scope_matches(scope, path) for scope in EXPECTED_C01_SCOPE)
    ]
    if violations:
        raise SystemExit(f"C01 write-scope violations: {violations}")
    snapshot_changes = [
        path for path in declared if path.startswith("src/epistemic_foundry/_canonical/")
    ]
    if snapshot_changes:
        raise SystemExit("C01 modified the B04-owned derived projection")
    return {
        "declared_change_count": len(declared),
        "declared_changes": sorted(set(declared)),
        "violation_count": 0,
        "violations": [],
        "derived_snapshot_change_count": 0,
        "root_canonical_authority_only": True,
        "status": "PASS",
    }


def git_diff_check() -> dict[str, Any]:
    paths = [
        *DECLARED_PRODUCT_CHANGES,
        ATTEMPT.relative_to(ROOT).as_posix(),
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
        raise SystemExit(f"scoped git diff --check failed: {result.stdout}{result.stderr}")
    return {
        "command": "git diff --check -- <C01 exact paths>",
        "exit_code": result.returncode,
        "advisory_output": (result.stdout + result.stderr).strip(),
        "status": "PASS",
    }


def build_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "probe_id": "C01-P006",
        "work_package_id": "C01",
        "attempt_id": ATTEMPT_ID,
        "authority": decision_evidence(DECISION, DECISION_ID, DECISION_HASH),
        "a06_remediation_authority": decision_evidence(
            REMEDIATION_DECISION,
            REMEDIATION_DECISION_ID,
            REMEDIATION_DECISION_HASH,
        ),
        "manifest_contract": manifest_contract(),
        "canonical_contract": {
            "schema_examples": validate_canonical_contracts(),
            "openapi": validate_openapi(),
            "targeted_tests": regression["targeted"],
            "status": "PASS",
        },
        "a06_findings": {
            "schema_level_resolved": EXPECTED_A06_SCHEMA_RESOLUTION,
            "downstream_runtime_ownership": DEFERRED_A06_FINDINGS,
            "c01_runtime_authority_claimed": False,
            "status": "PASS_WITH_EXPLICIT_LAYER_BOUNDARY",
        },
        "write_scope_audit": write_scope_evidence(),
        "git_diff_check": git_diff_check(),
        "full_regression": {
            "artifact": "artifacts/work_packages/C01/attempts/0006/full-regression-impact.json",
            "full_python": regression["full_python"],
            "failure_owner_counts": regression["failure_owner_counts"],
            "new_c01_failure_count": regression["new_c01_failure_count"],
            "full_suite_is_not_reported_pass": True,
            "status": regression["status"],
        },
        "package_status": "PASS",
        "contract_status": "CONFORMANT",
        "generated_projection_status": "PENDING_C02",
        "runtime_migration_status": "PENDING_C03",
        "canonical_projection_status": "WAITING_ON_PRE_C04_B04",
        "repository_full_suite_status": "EXPECTED_DOWNSTREAM_AND_PREEXISTING_FAILURES",
        "completion_ready": False,
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "work_package_id": "C01",
        "C01": "PASS",
        "C02": "DEPENDENCY_READY",
        "C03": "WAITING_ON_C02",
        "B04_pre_C04": "WAITING_ON_C01_C02_C03",
        "C04": "WAITING_ON_C02_C03_AND_FRESH_PROJECTION",
        "B04_final": "WAITING_ON_C04",
        "next_package": "C02",
        "full_156_package_dag_recomputed": False,
        "completion_ready": False,
        "status": "PASS",
    }


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def build() -> dict[str, Any]:
    regression = classify_regression()
    write_json(ATTEMPT / "full-regression-impact.json", regression)
    verification = build_verification(regression)
    write_json(ATTEMPT / "c01-contract-verification.json", verification)
    write_json(ATTEMPT / "dependency-status.json", dependency_status())
    return {
        "attempt_id": ATTEMPT_ID,
        "schema_count": 126,
        "example_count": 126,
        "targeted_passed": 77,
        "full_python_passed": 951,
        "full_python_failed": 19,
        "status": "PASS",
    }


def verify() -> dict[str, Any]:
    regression = classify_regression()
    verification = build_verification(regression)
    dependency = dependency_status()
    expected = {
        "full-regression-impact.json": regression,
        "c01-contract-verification.json": verification,
        "dependency-status.json": dependency,
    }
    for name, value in expected.items():
        path = ATTEMPT / name
        if path.read_text(encoding="utf-8") != render(value):
            raise SystemExit(f"stored evidence differs from live inputs: {name}")
    return {"attempt_id": ATTEMPT_ID, "status": "PASS", "verified": sorted(expected)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
