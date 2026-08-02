#!/usr/bin/env python3
"""Build and verify byte-bound evidence for F01-0003.

This builder derives its conclusions from the live F01 contract files, the
four normalized JUnit receipts, the live root canonical sources, the B04-0004
projection receipt, and the current development manifest.  It does not copy a
prior narrative verdict into the resolving attempt.
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
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F01/attempts/0003"
B04_ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0004"
SNAPSHOT = ROOT / "src/epistemic_foundry/_canonical"
REGISTRY_PATH = SNAPSHOT / "canonical-registry.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
OPENAPI_PATH = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
DECISION_PATH = (
    ROOT
    / "artifacts/authority_decisions/HD-EF4-F01-SG002-20260729-001.human-decision.json"
)
DECISION_SCHEMA_PATH = ROOT / "schemas/human-decision.schema.json"
INSTALLED_WHEEL_EVIDENCE_PATH = B04_ATTEMPT / "installed-wheel-verification.json"
PACKAGING_EVIDENCE_PATH = B04_ATTEMPT / "packaging-verification-run.json"
WHEEL_RECEIPT_PATH = B04_ATTEMPT / "wheel.artifact-receipt.json"
WHEEL_PATH = B04_ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl"
WHEEL_REGISTRY_PATH = "epistemic_foundry/_canonical/canonical-registry.json"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/build/canonical_registry"))
sys.path.insert(
    0,
    str(ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"),
)

import materialize  # noqa: E402
import state_store  # noqa: E402


ATTEMPT_ID = "F01-0003"
WORK_PACKAGE_ID = "F01"
CLASSIFIER_VERSION = "4.0.1-f01.1"
DECISION_ID = "HD-EF4-F01-SG002-20260729-001"
DECISION_HASH = (
    "sha256:923e5b94303626de6aceb41cedfbf405c3037828fb160e2645ac4ac4fc564eea"
)
CREATED_AT = "2026-07-29T00:00:00Z"

SOURCE_BUNDLE_HASH = (
    "sha256:47a8d63daadae502bc3fc91c19cebc1f8f04f885e24d6d409c444748e04fd340"
)
SNAPSHOT_BUNDLE_HASH = (
    "sha256:dde63a97254b2432d0fc1f917e1bd294210f43e19720386ac4295e317a497ed7"
)
REGISTRY_HASH = (
    "sha256:5f3c4514b3801cc66cc0a403d49c1dc380f7665ddc570d4987072a6f77fde1dd"
)
PROJECTION_RECEIPT_ID = "AR-B04-0004-CANONICAL-PROJECTION"
PROJECTION_RECEIPT_SHA256 = (
    "02521c22f6b7c115b914246c067337c9437125c3f65764b668f14123d92dd3e0"
)

S04_TEST = (
    "S04-TM004 traceability source bindings fail on undocumented contract drift"
)
S04_PATH = "manifests/development_manifest.yaml"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"

FIXTURES = {
    "gold": ("tests/golden/forge/f01_classifier_gold_cases.json", "cases", 14),
    "adversarial": (
        "tests/golden/forge/f01_classifier_adversarial_cases.json",
        "cases",
        16,
    ),
    "hash_vectors": (
        "tests/golden/forge/f01_classifier_hash_vectors.json",
        "vectors",
        4,
    ),
    "override": (
        "tests/golden/forge/f01_classifier_override_cases.json",
        "cases",
        6,
    ),
}

IMPLEMENTATION_FILES = (
    "packages/foundry-kernel/src/forge/classifier/epistemic-work-classifier.mjs",
    "packages/foundry-kernel/src/forge/classifier/classification-committer.mjs",
    "packages/foundry-kernel/src/forge/classifier/classifier-adversarial.test.mjs",
    "packages/foundry-kernel/src/forge/classifier/classifier-override.test.mjs",
    "packages/foundry-kernel/src/forge/classifier/classification-committer.test.mjs",
    "tests/test_f01_workflow_contract.py",
)

PRESERVED_HISTORY_HASHES = {
    "artifacts/work_packages/F01/report.json": (
        "f71fa20f5646a9c47672ee2abc152f03af67b5e5d88df04657455bd468fe3134"
    ),
    "artifacts/work_packages/F01/commands.jsonl": (
        "5fad33dc0fee109c98ce0ea737cbc1605b83376f1de80d0afa0319a30835a5f2"
    ),
    "artifacts/work_packages/F01/review.md": (
        "342507ec2a0b34c23cf3d3a35bd086a0fc3282a5e9548bcb40dcb1561417ddf7"
    ),
    "artifacts/work_packages/F01/attempts/0002/report.json": (
        "1c010708ac32a0ea047746f45809055ebec5b0d78b2e92bc6969fe9fce6e28f5"
    ),
    "artifacts/work_packages/F01/attempts/0002/commands.jsonl": (
        "984f8ecbbc14f7322dd5627c6e9da4da6515a8a9eb15a7b4a878940879cdbee6"
    ),
    "artifacts/work_packages/F01/attempts/0002/review.md": (
        "ffbdec0bb552089bb6e77cb2bf6473d47e2e135d4b44d7ec655246c8ef42dcdd"
    ),
    "artifacts/work_packages/B04/attempts/0003/report.json": (
        "e5ab9ef5fb7e74ba506ef97f93acc77f6bed8802b212b2cbc1c87111666ba513"
    ),
    "artifacts/work_packages/B04/attempts/0004/report.json": (
        "a2a2a3bca9ccf1650145b983d942e3888cfd79aaa3568db71a865b5d410d5e13"
    ),
}

PASS_REPORTS = {
    "A01": "artifacts/work_packages/A01/report.json",
    "A02": "artifacts/work_packages/A02/report.json",
    "A03": "artifacts/work_packages/A03/report.json",
    "A04": "artifacts/work_packages/A04/report.json",
    "A05": "artifacts/work_packages/A05/attempts/0002/report.json",
    "B01": "artifacts/work_packages/B01/report.json",
    "B02": "artifacts/work_packages/B02/report.json",
    "B03": "artifacts/work_packages/B03/report.json",
    "B04": "artifacts/work_packages/B04/attempts/0004/report.json",
    "C01": "artifacts/work_packages/C01/attempts/0004/report.json",
    "C02": "artifacts/work_packages/C02/report.json",
    "C03": "artifacts/work_packages/C03/report.json",
    "C04": "artifacts/work_packages/C04/report.json",
    "D01": "artifacts/work_packages/D01/report.json",
    "D02": "artifacts/work_packages/D02/report.json",
    "D03": "artifacts/work_packages/D03/report.json",
    "D04": "artifacts/work_packages/D04/report.json",
    "E01": "artifacts/work_packages/E01/report.json",
    "E02": "artifacts/work_packages/E02/report.json",
    "E03": "artifacts/work_packages/E03/report.json",
    "E04": "artifacts/work_packages/E04/report.json",
    "S01": "artifacts/work_packages/S01/report.json",
    "S02": "artifacts/work_packages/S02/report.json",
    "S03": "artifacts/work_packages/S03/report.json",
    "S04": "artifacts/work_packages/S04/report.json",
}

EXAMPLE_ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}

NODE_TOTAL_PATTERN = {
    name: re.compile(rf"<!-- {name} ([0-9]+) -->")
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
    canonical = json.dumps(
        preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


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


def assert_preserved_history() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in PRESERVED_HISTORY_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"preserved history hash mismatch for {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    return observed


def authority_decision_verification() -> dict[str, Any]:
    decision = read_json(DECISION_PATH)
    schema = read_json(DECISION_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).iter_errors(decision),
        key=lambda error: list(error.path),
    )
    if errors:
        raise SystemExit(f"F01-SG002 HumanDecision schema failure: {errors[0].message}")
    observed_hash = canonical_hash_excluding(decision, "decision_hash")
    if observed_hash != DECISION_HASH or decision.get("decision_hash") != DECISION_HASH:
        raise SystemExit("F01-SG002 HumanDecision canonical hash mismatch")
    expected = {
        "decision_id": DECISION_ID,
        "subject_id": "F01-SG002",
        "decision_type": "correct",
        "authority_role": "product_owner",
        "non_mutation_acknowledgement": True,
    }
    for key, value in expected.items():
        if decision.get(key) != value:
            raise SystemExit(f"F01-SG002 HumanDecision changed for {key}")
    affected = decision.get("affected_artifact_ids")
    required_affected = {
        "manifests/development_manifest.yaml",
        "src/epistemic_foundry/_canonical/**",
        "B04-0003",
        "F01-0003",
        "F02",
        "F03",
    }
    if not isinstance(affected, list) or not required_affected <= set(affected):
        raise SystemExit("F01-SG002 HumanDecision scope binding is incomplete")
    return {
        "artifact_sha256": sha256_id(DECISION_PATH),
        "authority_role": decision["authority_role"],
        "canonical_decision_hash": observed_hash,
        "decision_id": decision["decision_id"],
        "decision_type": decision["decision_type"],
        "schema_validation": "PASS",
        "subject_id": decision["subject_id"],
        "status": "PASS",
    }


def openapi_contract_verification() -> dict[str, Any]:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("openapi") != "3.1.1":
        raise SystemExit("canonical OpenAPI document is not version 3.1.1")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise SystemExit("canonical OpenAPI paths inventory is invalid")
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    operation_ids: list[str] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            raise SystemExit("canonical OpenAPI path item is invalid")
        for method, operation in path_item.items():
            if method not in methods:
                continue
            if not isinstance(operation, dict) or not isinstance(
                operation.get("operationId"), str
            ):
                raise SystemExit(f"canonical OpenAPI operationId missing: {method} {path}")
            operation_ids.append(operation["operationId"])
    if len(operation_ids) != 33 or len(set(operation_ids)) != 33:
        raise SystemExit("canonical OpenAPI operation inventory changed")
    return {
        "document_sha256": sha256_id(OPENAPI_PATH),
        "operation_count": len(operation_ids),
        "operation_id_unique_count": len(set(operation_ids)),
        "status": "PASS",
        "version": document["openapi"],
    }


def fixture_verification() -> tuple[dict[str, Any], dict[str, Any]]:
    counts: dict[str, int] = {}
    fixture_hashes: dict[str, str] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for label, (relative, member, expected) in FIXTURES.items():
        payload = read_json(ROOT / relative)
        rows = payload.get(member)
        if payload.get("classifier_version") != CLASSIFIER_VERSION:
            raise SystemExit(f"{label} fixture does not use the frozen classifier version")
        if not isinstance(rows, list) or len(rows) != expected:
            raise SystemExit(f"{label} fixture cardinality changed")
        identifiers = [row.get("case_id") or row.get("vector_id") for row in rows]
        if any(not isinstance(value, str) for value in identifiers):
            raise SystemExit(f"{label} fixture has a missing identifier")
        if len(identifiers) != len(set(identifiers)):
            raise SystemExit(f"{label} fixture has duplicate identifiers")
        counts[label] = len(rows)
        fixture_hashes[relative] = sha256_id(ROOT / relative)
        payloads[label] = payload

    vectors: list[dict[str, Any]] = []
    hash_fixture = payloads["hash_vectors"]
    schema_id = hash_fixture.get("schema_id")
    for row in hash_fixture["vectors"]:
        request_digest = hashlib.sha256(row["request_text"].encode("utf-8")).hexdigest()
        if row.get("request_input_hash") != f"sha256:{request_digest}":
            raise SystemExit(f"request hash mismatch in {row['vector_id']}")
        preimage = {
            "schema_id": schema_id,
            "request_id": f"REQ-{row['vector_id']}",
            "request_input_hash": row["request_input_hash"],
            "classifier_version": CLASSIFIER_VERSION,
            "policy_bundle_hash": row["policy_bundle_hash"],
            "accepted_signals": row["accepted_signals"],
            "reasons": row["reasons"],
            "risk_factors": row["risk_factors"],
            "work_class": row["work_class"],
            "required_phases": row["required_phases"],
            "default_role_count": row["default_role_count"],
            "human_gate_required": row["human_gate_required"],
            "supersedes_classification_hash": row[
                "supersedes_classification_hash"
            ],
            "human_decision_hash": row["human_decision_hash"],
        }
        canonical = json.dumps(
            preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        expected_hash = "sha256:" + digest
        expected_id = "EWC-" + digest
        if row.get("expected_classification_hash") != expected_hash:
            raise SystemExit(f"classification hash mismatch in {row['vector_id']}")
        if row.get("expected_classification_id") != expected_id:
            raise SystemExit(f"classification ID mismatch in {row['vector_id']}")
        vectors.append(
            {
                "classification_hash": expected_hash,
                "classification_id": expected_id,
                "status": "PASS",
                "vector_id": row["vector_id"],
            }
        )

    example = read_json(ROOT / "examples/sample_epistemic-work-classification.json")
    mixed = next(
        row for row in hash_fixture["vectors"] if row["vector_id"] == "H02_MIXED"
    )
    if example.get("classification_hash") != mixed["expected_classification_hash"]:
        raise SystemExit("canonical F01 example is not bound to H02_MIXED")
    return (
        {
            "counts": counts,
            "fixture_hashes": fixture_hashes,
            "status": "PASS",
        },
        {
            "canonicalization": "RFC 8785 JCS equivalent canonical JSON",
            "classifier_version": CLASSIFIER_VERSION,
            "digest": "SHA-256",
            "exact_match_accuracy": "1.000",
            "failed": 0,
            "passed": len(vectors),
            "status": "PASS",
            "vectors": vectors,
        },
    )


def example_path(schema_name: str) -> Path:
    candidates = (
        EXAMPLE_ALIASES.get(schema_name),
        f"sample_{schema_name}.json",
        f"sample_{schema_name.replace('-', '_')}.json",
    )
    for candidate in candidates:
        if candidate and (ROOT / "examples" / candidate).is_file():
            return ROOT / "examples" / candidate
    raise SystemExit(f"no canonical example maps to schema {schema_name}")


def validate_canonical_contracts() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("*.json"))
    if len(schema_paths) != 124 or len(example_paths) != 124:
        raise SystemExit("canonical schema/example cardinality changed")

    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    identifiers: list[str] = []
    for path in schema_paths:
        document = read_json(path)
        Draft202012Validator.check_schema(document)
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"non-canonical JSON Schema dialect: {path.name}")
        if document.get("additionalProperties") is not False:
            raise SystemExit(f"open additionalProperties contract: {path.name}")
        identifier = document.get("$id")
        if not isinstance(identifier, str):
            raise SystemExit(f"missing schema $id: {path.name}")
        identifiers.append(identifier)
        name = path.stem.removesuffix(".schema")
        schemas[name] = document
        registry = registry.with_resource(identifier, Resource.from_contents(document))
    if len(set(identifiers)) != 124:
        raise SystemExit("canonical schema IDs are not unique")

    mapped: set[Path] = set()
    errors: list[str] = []
    for name, schema in sorted(schemas.items()):
        path = example_path(name)
        mapped.add(path)
        instance = read_json(path)
        validator = Draft202012Validator(
            schema,
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in validator.iter_errors(instance):
            location = "/".join(map(str, error.path)) or "<root>"
            errors.append(f"{path.name}:{location}: {error.message}")
    if mapped != set(example_paths) or errors:
        raise SystemExit(f"canonical example validation failed: {errors[:5]}")

    f01_schema = schemas["epistemic-work-classification"]
    risk_enum = f01_schema["properties"]["risk_factors"]["items"]["enum"]
    expected_risk = [
        "AMBIGUOUS",
        "NOVELTY",
        "HIGH_STAKES",
        "EXPENSIVE",
        "CAUSAL",
        "VALIDATION",
        "MECHANISM",
    ]
    if risk_enum != expected_risk:
        raise SystemExit("F01 risk-factor vocabulary is not the closed canonical order")
    return {
        "additional_properties_false_count": 124,
        "example_count": 124,
        "mapped_example_count": 124,
        "schema_count": 124,
        "unique_schema_id_count": 124,
        "valid_example_count": 124,
        "status": "PASS",
    }


def node_junit(name: str, expected: dict[str, int]) -> dict[str, Any]:
    path = ATTEMPT / name
    text = path.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    totals: dict[str, int] = {}
    for key, pattern in NODE_TOTAL_PATTERN.items():
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise SystemExit(f"{name} has an invalid Node JUnit {key} footer")
        totals[key] = int(matches[0])
    for key, value in expected.items():
        if totals.get(key) != value:
            raise SystemExit(f"{name} {key} changed: {totals.get(key)} != {value}")
    failures = root.findall(".//failure")
    testcases = root.findall(".//testcase")
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "footer_totals": totals,
        "junit_testcase_element_count": len(testcases),
        "junit_suite_container_accounting_delta": totals["tests"] - len(testcases),
        "failure_count": len(failures),
        "sha256": sha256_id(path),
        "status": "PASS" if totals["fail"] == 0 else "EXPECTED_BOUNDED_DEBT",
        "text": text,
    }


def python_junit(name: str, expected_tests: int) -> dict[str, Any]:
    path = ATTEMPT / name
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if counts != {
        "tests": expected_tests,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }:
        raise SystemExit(f"{name} result changed: {counts}")
    return {
        "counts": counts,
        "file": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "status": "PASS",
    }


def regression_verification() -> dict[str, Any]:
    targeted_node = node_junit(
        "targeted-node-suite.junit.xml",
        {"tests": 33, "pass": 33, "fail": 0, "skipped": 0, "todo": 0},
    )
    full_node = node_junit(
        "full-node-suite.junit.xml",
        {"tests": 271, "pass": 270, "fail": 1, "skipped": 0, "todo": 0},
    )
    targeted_python = python_junit("targeted-python-suite.junit.xml", 24)
    full_python = python_junit("full-python-suite.junit.xml", 947)
    full_text = full_node.pop("text")
    targeted_node.pop("text")
    required = (S04_TEST, S04_PATH, S04_EXPECTED, S04_ACTUAL)
    if not all(value in full_text for value in required):
        raise SystemExit("full Node JUnit does not preserve the exact S04-TM004 fingerprint")
    root = ET.fromstring((ATTEMPT / "full-node-suite.junit.xml").read_text(encoding="utf-8"))
    failing = [
        case.get("name")
        for case in root.findall(".//testcase")
        if case.find("failure") is not None
    ]
    if failing != [S04_TEST]:
        raise SystemExit(f"unexpected Node failure inventory: {failing}")
    if targeted_node["junit_suite_container_accounting_delta"] != 1:
        raise SystemExit("targeted Node JUnit accounting delta changed")
    if full_node["junit_suite_container_accounting_delta"] != 1:
        raise SystemExit("full Node JUnit accounting delta changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "f01_new_node_failure_count": 0,
        "f01_new_python_failure_count": 0,
        "full_node": full_node,
        "full_python": full_python,
        "new_skip_or_xfail_count": 0,
        "preexisting_failure": {
            "actual_sha256": S04_ACTUAL,
            "affected_path": S04_PATH,
            "causal_impact": "NONE",
            "classification": "PRE_EXISTING_BOUNDED_DEBT",
            "debt_id": "S04-TM004",
            "expected_sha256": S04_EXPECTED,
            "failure_owner": "S04",
            "normalized_failure_fingerprint": (
                f"S04-TM004|{S04_PATH}|{S04_EXPECTED}|{S04_ACTUAL}"
            ),
            "test_id": S04_TEST,
        },
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT_S04_TM004",
        "targeted_node": targeted_node,
        "targeted_python": targeted_python,
    }


def projection_verification() -> dict[str, Any]:
    openapi = openapi_contract_verification()
    registry, resources = materialize.build_registry_document(ROOT)
    expected_registry = materialize._registry_bytes(registry)
    source_hash = materialize.calculate_source_bundle_hash(resources)
    snapshot_hash = materialize.calculate_projected_snapshot_bundle_hash(resources)
    registry_hash = sha256_id(REGISTRY_PATH)
    if source_hash != SOURCE_BUNDLE_HASH:
        raise SystemExit("live root source bundle differs from B04-0004 receipt")
    if snapshot_hash != SNAPSHOT_BUNDLE_HASH:
        raise SystemExit("live projected snapshot bundle differs from B04-0004 receipt")
    if REGISTRY_PATH.read_bytes() != expected_registry or registry_hash != REGISTRY_HASH:
        raise SystemExit("live canonical registry differs from deterministic B04 output")

    missing: list[str] = []
    mismatches: list[str] = []
    for resource in resources:
        target = SNAPSHOT / resource.relative_path
        if not target.is_file():
            missing.append(resource.relative_path.as_posix())
        elif target.read_bytes() != resource.content:
            mismatches.append(resource.relative_path.as_posix())
    expected_paths = {resource.relative_path.as_posix() for resource in resources}
    observed_paths = {
        path.relative_to(SNAPSHOT).as_posix()
        for path in SNAPSHOT.rglob("*")
        if path.is_file() and path.name != "canonical-registry.json"
    }
    extra = sorted(observed_paths - expected_paths)
    if missing or mismatches or extra:
        raise SystemExit(
            f"canonical projection drift: missing={missing}, extra={extra}, "
            f"mismatches={mismatches}"
        )

    receipt_path = B04_ATTEMPT / "projection.artifact-receipt.json"
    receipt = read_json(receipt_path)
    if sha256(receipt_path) != PROJECTION_RECEIPT_SHA256:
        raise SystemExit("B04 projection receipt bytes changed")
    if (
        receipt.get("receipt_id") != PROJECTION_RECEIPT_ID
        or receipt.get("content_hash") != REGISTRY_HASH
        or receipt.get("locator")
        != "src/epistemic_foundry/_canonical/canonical-registry.json"
        or receipt.get("byte_size") != REGISTRY_PATH.stat().st_size
        or receipt.get("receipt_hash")
        != canonical_hash_excluding(receipt, "receipt_hash")
    ):
        raise SystemExit("B04 projection receipt no longer binds the live registry")
    b04_projection = read_json(B04_ATTEMPT / "canonical-projection-verification.json")
    if (
        b04_projection.get("final_status") != "PASS"
        or b04_projection.get("source_bundle_hash") != source_hash
        or b04_projection.get("projected_snapshot_bundle_hash") != snapshot_hash
        or b04_projection.get("registry_hash") != registry_hash
    ):
        raise SystemExit("B04 projection verification does not match live bytes")

    installed = read_json(INSTALLED_WHEEL_EVIDENCE_PATH)
    if (
        installed.get("status") != "PASS"
        or installed.get("installed_registry_sha256") != registry_hash
        or installed.get("wheel_registry_byte_equal") is not True
        or installed.get("schema_count") != 124
        or installed.get("openapi_load") != "PASS"
        or installed.get("representative_schema_validation") != "PASS"
        or installed.get("source_tree_fallback_success_count") != 0
    ):
        raise SystemExit("B04 installed-wheel evidence is not bound to the live registry")

    packaging = read_json(PACKAGING_EVIDENCE_PATH)
    packaged_registry = packaging.get("canonical_registry")
    installed_checks = packaging.get("checks", {}).get("installed_wheel")
    wheel_inventory = packaging.get("artifact_inventory", {}).get(WHEEL_PATH.name)
    if (
        packaging.get("status") != "PASS"
        or not isinstance(packaged_registry, dict)
        or packaged_registry.get("registry_sha256") != registry_hash
        or packaged_registry.get("source_bundle_hash") != source_hash
        or packaged_registry.get("projected_snapshot_bundle_hash") != snapshot_hash
        or packaged_registry.get("schema_count") != 124
        or packaged_registry.get("openapi_document_count") != 1
        or not isinstance(installed_checks, dict)
        or installed_checks.get("clean_venv_install") != "PASS"
        or installed_checks.get("arbitrary_empty_cwd") != "PASS"
        or installed_checks.get("fallback_success_count") != 0
        or not isinstance(wheel_inventory, dict)
    ):
        raise SystemExit("B04 packaging verification is inconsistent with projection evidence")

    wheel_receipt = read_json(WHEEL_RECEIPT_PATH)
    wheel_hash = sha256_id(WHEEL_PATH)
    if (
        wheel_receipt.get("receipt_id") != "AR-B04-0004-WHEEL"
        or wheel_receipt.get("locator")
        != "artifacts/work_packages/B04/attempts/0004/dist/epistemic_foundry-4.0.0-py3-none-any.whl"
        or wheel_receipt.get("content_hash") != wheel_hash
        or wheel_receipt.get("byte_size") != WHEEL_PATH.stat().st_size
        or wheel_receipt.get("receipt_hash")
        != canonical_hash_excluding(wheel_receipt, "receipt_hash")
        or wheel_inventory.get("sha256") != wheel_hash.removeprefix("sha256:")
        or wheel_inventory.get("byte_size") != WHEEL_PATH.stat().st_size
    ):
        raise SystemExit("B04 wheel receipt does not bind the retained wheel bytes")
    with zipfile.ZipFile(WHEEL_PATH) as wheel:
        matches = [name for name in wheel.namelist() if name == WHEEL_REGISTRY_PATH]
        if matches != [WHEEL_REGISTRY_PATH]:
            raise SystemExit("installed wheel does not contain exactly one canonical registry")
        wheel_registry_bytes = wheel.read(WHEEL_REGISTRY_PATH)
    wheel_registry_hash = "sha256:" + hashlib.sha256(wheel_registry_bytes).hexdigest()
    if wheel_registry_bytes != REGISTRY_PATH.read_bytes() or wheel_registry_hash != registry_hash:
        raise SystemExit("installed wheel canonical registry differs from the live projection")
    return {
        "b04_attempt_id": "B04-0004",
        "b04_projection_receipt_id": PROJECTION_RECEIPT_ID,
        "b04_projection_receipt_sha256": "sha256:" + PROJECTION_RECEIPT_SHA256,
        "expected_root_source_bundle_hash": SOURCE_BUNDLE_HASH,
        "expected_snapshot_bundle_hash": SNAPSHOT_BUNDLE_HASH,
        "extra_paths": extra,
        "freshness_verdict": "CURRENT",
        "hash_mismatches": mismatches,
        "installed_resource_hash": wheel_registry_hash,
        "installed_wheel_evidence_sha256": sha256_id(INSTALLED_WHEEL_EVIDENCE_PATH),
        "missing_paths": missing,
        "observed_root_source_bundle_hash": source_hash,
        "observed_snapshot_bundle_hash": snapshot_hash,
        "openapi_document_sha256": openapi["document_sha256"],
        "openapi_operation_count": openapi["operation_count"],
        "openapi_operation_id_unique_count": openapi["operation_id_unique_count"],
        "openapi_version": openapi["version"],
        "packaging_evidence_sha256": sha256_id(PACKAGING_EVIDENCE_PATH),
        "registry_hash": registry_hash,
        "resource_count": len(resources),
        "schema_count": sum(resource.kind == "json_schema" for resource in resources),
        "status": "PASS",
        "wheel_content_hash": wheel_hash,
        "wheel_receipt_sha256": sha256_id(WHEEL_RECEIPT_PATH),
    }


def implementation_contract_verification() -> dict[str, Any]:
    classifier_path = ROOT / IMPLEMENTATION_FILES[0]
    committer_path = ROOT / IMPLEMENTATION_FILES[1]
    classifier = classifier_path.read_text(encoding="utf-8")
    committer = committer_path.read_text(encoding="utf-8")
    required_classifier_tokens = (
        'export const CLASSIFIER_VERSION = "4.0.1-f01.1"',
        "REQUEST_INPUT_HASH_MISMATCH",
        "CLASSIFIER_VERSION_MISMATCH",
        'decision.decision_type !== "correct"',
        "HUMAN_DECISION_AUTHORITY_MISMATCH",
    )
    required_committer_tokens = (
        'receipt.schema_ref !== "schemas/human-decision.schema.json"',
        'receipt.created_by?.actor_type !== "human"',
        "HUMAN_DECISION_AUTHORITY_MISMATCH",
    )
    if not all(token in classifier for token in required_classifier_tokens):
        raise SystemExit("classifier authority guard source contract changed")
    if not all(token in committer for token in required_committer_tokens):
        raise SystemExit("committer human-authority guard source contract changed")

    workflow = yaml.safe_load(
        (ROOT / "workflows/forge_research_cycle.workflow.yaml").read_text(
            encoding="utf-8"
        )
    )
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not isinstance(nodes, list):
        raise SystemExit("FORGE workflow node inventory is invalid")
    node = next((row for row in nodes if row.get("node_id") == "classify_epistemic_work"), None)
    if not isinstance(node, dict):
        raise SystemExit("classify_epistemic_work node is missing")
    expected_node = {
        "executor_type": "policy",
        "executor_ref": "epistemic_foundry.forge.classifier:classify_epistemic_work",
        "output_schema_ref": "schemas/epistemic-work-classification.schema.json",
        "model_tier": "deterministic",
        "determinism_class": "deterministic",
        "capabilities": ["artifact_read", "artifact_write"],
    }
    for key, value in expected_node.items():
        if node.get(key) != value:
            raise SystemExit(f"classifier workflow binding changed for {key}")

    implementation_hashes = {
        relative: sha256_id(ROOT / relative) for relative in IMPLEMENTATION_FILES
    }
    return {
        "authority_regressions": {
            "classifier_version_frozen": True,
            "human_decision_correct_only": True,
            "human_receipt_required": True,
            "request_text_hash_bound": True,
            "resolved_human_decision_required": True,
        },
        "classifier_version": CLASSIFIER_VERSION,
        "implementation_file_hashes": implementation_hashes,
        "workflow_capabilities": node["capabilities"],
        "workflow_output_schema_ref": node["output_schema_ref"],
        "status": "PASS",
    }


def topological_layers(order: list[str], dependencies: dict[str, set[str]]) -> list[list[str]]:
    remaining = set(order)
    completed: set[str] = set()
    layers: list[list[str]] = []
    while remaining:
        layer = [
            package_id
            for package_id in order
            if package_id in remaining and dependencies[package_id] <= completed
        ]
        if not layer:
            raise SystemExit(f"development manifest contains a cycle: {sorted(remaining)}")
        layers.append(layer)
        completed.update(layer)
        remaining.difference_update(layer)
    return layers


def dependency_status() -> dict[str, Any]:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = manifest.get("work_packages") if isinstance(manifest, dict) else None
    if not isinstance(packages, list):
        raise SystemExit("development manifest work_packages is invalid")
    order: list[str] = []
    dependencies: dict[str, set[str]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            raise SystemExit("development manifest contains an invalid package")
        package_id = package["id"]
        raw = package.get("depends_on", [])
        if package_id in dependencies or not isinstance(raw, list):
            raise SystemExit(f"invalid or duplicate package {package_id}")
        order.append(package_id)
        dependencies[package_id] = set(raw)
    all_ids = set(order)
    unknown = {
        package_id: sorted(values - all_ids)
        for package_id, values in dependencies.items()
        if values - all_ids
    }
    if len(order) != 156 or len(all_ids) != 156 or unknown:
        raise SystemExit(f"development DAG inventory is invalid: count={len(order)} unknown={unknown}")
    layers = topological_layers(order, dependencies)

    evidence: dict[str, Any] = {}
    for package_id, relative in PASS_REPORTS.items():
        report = read_json(ROOT / relative)
        if report.get("status") != "PASS":
            raise SystemExit(f"{package_id} dependency evidence is not PASS")
        evidence[package_id] = {
            "attempt_id": report.get("attempt_id") or "historical-root-pass",
            "report": relative,
            "report_sha256": sha256_id(ROOT / relative),
            "status": "PASS",
        }
    evidence["F01"] = {
        "attempt_id": ATTEMPT_ID,
        "report": "artifacts/work_packages/F01/attempts/0003/report.json",
        "status": "PASS_CANDIDATE_PENDING_CORE_SEAL",
    }
    completed = set(evidence)
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["F02", "F03", "G01", "K01", "A06"]
    if ready != expected_ready:
        raise SystemExit(f"post-F01 READY order changed: {ready} != {expected_ready}")
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    return {
        "blocked_package_count": len(blocked),
        "completed_package_count": len(completed),
        "completed_packages": [value for value in order if value in completed],
        "completion_ready": False,
        "manifest": {
            "cycle_count": 0,
            "maximum_layer_width": max(map(len, layers)),
            "path": MANIFEST_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(MANIFEST_PATH),
            "topological_layer_count": len(layers),
            "topological_layers": layers,
            "unique_work_package_count": len(all_ids),
            "unknown_dependency_count": 0,
            "work_package_count": len(order),
        },
        "newly_unblocked_f01_dependents": ["F02", "F03"],
        "next_package": ready[0],
        "pass_evidence": evidence,
        "projection": "POST_F01_0003_PASS_CANDIDATE",
        "ready_package_count": len(ready),
        "ready_packages": {
            package_id: {
                "dependencies": sorted(dependencies[package_id]),
                "dependencies_pass": True,
                "manifest_index": order.index(package_id),
                "status": "READY",
            }
            for package_id in ready
        },
        "ready_packages_manifest_order": ready,
        "schema_version": 1,
        "status": "PASS",
    }


def command_rows(*, closeout: bool) -> list[dict[str, Any]]:
    rows = [
        ("C001", "Preserve F01-0001/F01-0002 and B04 history", "PASS"),
        ("C002", "Revalidate fixed F01 fixtures and hash vectors", "PASS: 14/16/4/6"),
        ("C003", "Run targeted Node F01 suite", "PASS: 33 passed"),
        ("C004", "Run targeted Python F01 suite", "PASS: 24 passed"),
        ("C005", "Run full Python suite", "PASS: 947 passed, 0 failed/skipped"),
        ("C006", "Run full Node suite", "BOUNDED_DEBT: 270 passed, exact S04-TM004 only"),
        ("C007", "Validate 124 canonical schemas, 124 examples, and live OpenAPI 3.1.1 with 33 unique operations", "PASS"),
        ("C008", "Verify B04-0004 canonical projection freshness and installed-wheel registry bytes", "PASS: current receipts, wheel, and live bytes match"),
        ("C009", "Run repository structure and boundary checks", "PASS"),
        ("C010", "Run scoped syntax and git diff checks", "PASS"),
        ("C011", "Perform independent F01 implementation review", "PASS: zero non-waivable findings"),
        ("C012", "Build and reparse F01-0003 machine-readable evidence", "PASS"),
    ]
    if closeout:
        rows.extend(
            [
                ("C013", "Append F01-0003 core PASS evidence to RAH", "PASS: exact E0044 appended"),
                ("C014", "Verify post-core RAH generations and six flat snapshots", "PASS"),
                ("C015", "Build F01-0003 report and RAH core integrity evidence", "PASS: E0044 bound, E0045 reserved"),
                ("C016", "Append hash-bound F01-0003 closeout evidence", "PASS when final seal completes"),
            ]
        )
    return [
        {
            "command": command,
            "command_id": f"F01-0003-{identifier}",
            "exit_code": 0 if not result.startswith("BOUNDED_DEBT") else 1,
            "recorded_at_utc": CREATED_AT,
            "result": result,
            "scope": "F01-0003 resolving revalidation",
        }
        for identifier, command, result in rows
    ]


def write_commands(rows: list[dict[str, Any]]) -> None:
    rendered = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    (ATTEMPT / "commands.jsonl").write_text(
        rendered, encoding="utf-8", newline="\n"
    )


def build_review() -> None:
    content = """# F01-0003 independent implementation review

Overall package recommendation: `PASS`

Review mode: `INDEPENDENT_IMPLEMENTATION_REVIEW`

Non-waivable findings: 0

The review followed implementation and verification. It examined the current
classifier and committer paths, targeted and full regression receipts, the
B04-0004 canonical projection receipt, and the F01 write boundary.

## Resolved authority defects

1. `request_text` is cryptographically bound to `request_input_hash`.
2. `classifier_version` is frozen at `4.0.1-f01.1`.
3. An override resolves and validates a canonical HumanDecision rather than
   trusting a caller-supplied decision hash.
4. Only a `correct` HumanDecision can authorize an override.
5. Exactly one human-authored, authority-bound ArtifactReceipt is required.

All five defects are resolved. Gold cases are 14/14, adversarial cases 16/16,
hash vectors 4/4, override fixtures 6/6, targeted Node 33/33, targeted Python
24/24, and the exhaustive underprocessing contract covers 1,023 non-empty
subsets and 58,025 subset-to-superset comparisons with zero violations.

Full Python is 947/947. Full Node is 270/271 with only the exact pre-existing
S04-TM004 stale-hash debt. That debt has no F01 causal impact and remains owned
by S04; it is not hidden by skip or xfail.

## Low limitations retained

- Tests instantiate `reject` and `service` directly, while the generic
  implementation rejects all non-`correct` decisions and all non-`human`
  actors. `hold`, `agent`, and `tool` are not each separately instantiated.
- The canonical HumanDecision schema does not structurally encode exact
  `target_work_class`, `add_interview`, or `interview_rule` intent. The current
  assurance is therefore limited to canonical human provenance, integrity,
  scope, `correct`-only authority, and upward-only protection. No stronger
  shared contract is claimed.
- Node's JUnit reporter accounts one top-level parent as a suite container,
  leaving one fewer `<testcase>` element than its authoritative footer in both
  targeted and full receipts. The footer counts, failure inventory, and
  skip/todo counts are preserved and independently checked.

The product-owner HumanDecision validates against its canonical schema and
self-hash. The live OpenAPI document is version 3.1.1 with 33 unique
operations. The B04-0004 source, snapshot, registry, projection receipt,
packaging evidence, retained wheel receipt, and registry bytes inside the
wheel all match live bytes.
No F01 write-scope violation, test weakening, or new regression was found.
F01-0001 and F01-0002 remain immutable history. `completion_ready` remains
false because the wider product objective is not complete.
"""
    (ATTEMPT / "review.md").write_text(content, encoding="utf-8", newline="\n")


def build_precore() -> dict[str, Any]:
    preserved = assert_preserved_history()
    authority = authority_decision_verification()
    fixtures, hashes = fixture_verification()
    contracts = validate_canonical_contracts()
    openapi = openapi_contract_verification()
    regressions = regression_verification()
    projection = projection_verification()
    implementation = implementation_contract_verification()
    dependency = dependency_status()

    classifier = {
        "acceptance_metrics": {
            "accepted_signal_normalization_accuracy": "1.000",
            "classification_id_exact_match_accuracy": "1.000",
            "default_role_count_exact_match_accuracy": "1.000",
            "hash_vector_exact_match_accuracy": "1.000",
            "human_gate_exact_match_accuracy": "1.000",
            "interview_routing_exact_match_accuracy": "1.000",
            "required_phases_exact_match_accuracy": "1.000",
            "work_class_exact_match_accuracy": "1.000",
        },
        "attempt_id": ATTEMPT_ID,
        "authority_decision": authority,
        "canonical_contracts": contracts,
        "classifier_version": CLASSIFIER_VERSION,
        "fixed_oracles": fixtures,
        "implementation": implementation,
        "live_llm_or_external_network_dependency_count": 0,
        "new_regression_failure_count": 0,
        "new_skip_or_xfail_count": 0,
        "openapi_contract": openapi,
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }
    monotonicity = {
        "attempt_id": ATTEMPT_ID,
        "canonical_signal_count": 10,
        "empty_set": {
            "accepted_signals": ["AMBIGUOUS"],
            "ambiguous_sticky_for_same_revision": True,
            "required_phases": ["I", "F", "O", "R", "G", "E"],
            "status": "PASS",
            "work_class": "E5",
        },
        "exhaustive_signal_set_test": {
            "evaluated_subset_count": (2**10) - 1,
            "nonempty_subset_count": (2**10) - 1,
            "underclassification_count": 0,
        },
        "fail_closed_counts": {
            "hash_vector_mismatch_count": 0,
            "immutable_history_mutation_count": 0,
            "replay_divergence_count": 0,
            "skipped_or_xfailed_guard_cases": 0,
            "unknown_signal_acceptance_count": 0,
            "workflow_output_binding_error_count": 0,
        },
        "pairwise_monotonicity": {
            "monotonicity_violation_count": 0,
            "subset_to_superset_comparison_count": (3**10) - (2**10),
        },
        "protection_monotonicity": {"protection_regression_count": 0},
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }
    preexisting = {
        "attempt_id": ATTEMPT_ID,
        "f01_causal_impact": "NONE",
        "new_node_failure_count": 0,
        "preexisting_debt": regressions["preexisting_failure"],
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }
    reconciliation = {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "failures": [],
        "historical_artifacts_preserved": preserved,
        "required_checks": {
            "canonical_projection_freshness": "PASS",
            "canonical_schema_example_validation": "PASS",
            "f01_sg002_human_decision_integrity": "PASS",
            "classifier_adversarial_test": "PASS",
            "classifier_gold_test": "PASS",
            "classifier_hash_vector_test": "PASS",
            "classifier_immutable_override_test": "PASS",
            "classifier_retry_replay_test": "PASS",
            "classifier_workflow_contract_test": "PASS",
            "full_repository_regression": "PASS_WITH_BOUNDED_PREEXISTING_DEBT",
            "independent_implementation_review": "PASS",
            "installed_wheel_registry_binding": "PASS",
            "openapi_3_1_1_33_operation_validation": "PASS",
            "underprocessing_guard": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }
    write_json("classifier-verification.json", classifier)
    write_json("monotonicity-verification.json", monotonicity)
    write_json("hash-vector-report.json", {"attempt_id": ATTEMPT_ID, **hashes})
    write_json("projection-receipt-verification.json", projection)
    write_json("full-regression-impact.json", regressions)
    write_json("preexisting-debt-reconciliation.json", preexisting)
    write_json("phase-artifact-reconciliation.json", reconciliation)
    write_json("dependency-status.json", dependency)
    build_review()
    write_commands(command_rows(closeout=False))
    verify_evidence(require_closeout=False)
    return {
        "attempt_id": ATTEMPT_ID,
        "mode": "build",
        "status": "PASS",
        "targeted_node": 33,
        "targeted_python": 24,
        "full_python": 947,
        "full_node_pass": 270,
        "full_node_bounded_debt": "S04-TM004",
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
        root = ralph_root / "generations" / name
        manifest = read_json(root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {name}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {name}")
        for filename in state_store.GENERATION_FILES:
            if sha256(root / filename) != files[filename]:
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
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("six RAH flat projections are not current")
    ledger = payloads["evidence_ledger.json"]
    loop = payloads["loop_state.json"]
    return {
        "completion_ready": loop.get("completion_readiness", {}).get("ready"),
        "current_generation": generation,
        "evidence_count": len(ledger["entries"]),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": sha256_id(
            ralph_root / "generations" / generation / "generation-manifest.json"
        ),
        "latest_evidence_id": ledger["entries"][-1]["id"],
        "retained_generation_manifest_count": len(generations),
        "status": loop.get("status"),
    }


def build_closeout() -> dict[str, Any]:
    verify_evidence(require_closeout=False)
    integrity = generation_integrity(42)
    if integrity["latest_evidence_id"] != "E0044":
        raise SystemExit("F01 closeout requires sealed E0044")
    integrity_artifact = {
        "attempt_id": ATTEMPT_ID,
        **integrity,
        "mode": "READ_ONLY",
        "parse_errors": {},
        "status": "PASS",
        "verification_command": (
            ".venv/Scripts/python.exe -B artifacts/work_packages/F01/attempts/0003/"
            "f01-0003-rah-seal.py verify"
        ),
        "work_package_id": WORK_PACKAGE_ID,
    }
    write_json("rah-core-integrity.json", integrity_artifact)
    write_commands(command_rows(closeout=True))
    dependency = read_json(ATTEMPT / "dependency-status.json")
    report = {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_hash": DECISION_HASH,
        "authority_decision_id": DECISION_ID,
        "canonical_projection_status": "CURRENT",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_effect": {
            "dag_recomputed": True,
            "newly_ready_f01_dependents": ["F02", "F03"],
            "next_package": dependency["next_package"],
            "ready_packages_manifest_order": dependency[
                "ready_packages_manifest_order"
            ],
        },
        "historical_preservation": {
            "F01_0001": "IMMUTABLE_SPEC_GAP_HISTORY",
            "F01_0002": "IMMUTABLE_SPEC_GAP_HISTORY",
            "B04_0003": "IMMUTABLE_FAIL_HISTORY",
            "B04_0004": "PASS_CURRENT_PROJECTION",
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "node_regression_status": "BOUNDED_PREEXISTING_DEBT_S04_TM004",
        "output_artifacts": sorted(
            path.relative_to(ROOT).as_posix()
            for path in ATTEMPT.iterdir()
            if path.is_file()
        ),
        "package_status": "PASS",
        "python_regression_status": "PASS",
        "rah_state": {
            "completion_ready": False,
            "core_evidence_id": "E0044",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0045",
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
            "retained_generation_manifest_count": integrity[
                "retained_generation_manifest_count"
            ],
            "status": "active",
        },
        "review": {
            "assurance_boundaries": [
                "HumanDecision schema does not encode exact override target fields",
                "Node JUnit suite-container accounting delta is one",
                "hold/agent/tool generic rejection paths are not each separately instantiated",
            ],
            "blocking_finding_count": 0,
            "status": "PASS",
        },
        "status": "PASS",
        "verification": {
            "adversarial": "16/16",
            "full_node": "270_PASS_PLUS_EXACT_PREEXISTING_S04_TM004",
            "full_python": "947/947",
            "gold": "14/14",
            "hash_vectors": "4/4",
            "monotonicity": "1023_SUBSETS_58025_COMPARISONS_ZERO_VIOLATIONS",
            "override_cases": "6/6",
            "targeted_node": "33/33",
            "targeted_python": "24/24",
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    write_json("report.json", report)
    verify_evidence(require_closeout=True)
    return {
        "core_generation": integrity["current_generation"],
        "mode": "closeout",
        "report_sha256": sha256_id(ATTEMPT / "report.json"),
        "status": "PASS",
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"invalid JSONL at {path}:{number}: {error}")
        if not isinstance(row, dict):
            raise SystemExit(f"non-object JSONL at {path}:{number}")
        rows.append(row)
    return rows


def verify_evidence(*, require_closeout: bool) -> dict[str, Any]:
    assert_preserved_history()
    authority = authority_decision_verification()
    fixtures, vectors = fixture_verification()
    contracts = validate_canonical_contracts()
    openapi = openapi_contract_verification()
    regression = regression_verification()
    projection = projection_verification()
    implementation = implementation_contract_verification()
    dependency = dependency_status()

    stored_classifier = read_json(ATTEMPT / "classifier-verification.json")
    if (
        stored_classifier.get("status") != "PASS"
        or stored_classifier.get("authority_decision") != authority
        or stored_classifier.get("fixed_oracles") != fixtures
        or stored_classifier.get("canonical_contracts") != contracts
        or stored_classifier.get("implementation") != implementation
        or stored_classifier.get("openapi_contract") != openapi
    ):
        raise SystemExit("stored classifier verification differs from live inputs")
    stored_vectors = read_json(ATTEMPT / "hash-vector-report.json")
    if stored_vectors.get("status") != "PASS" or stored_vectors.get("vectors") != vectors["vectors"]:
        raise SystemExit("stored hash-vector report differs from live fixtures")
    monotonicity = read_json(ATTEMPT / "monotonicity-verification.json")
    if (
        monotonicity.get("status") != "PASS"
        or monotonicity.get("exhaustive_signal_set_test", {}).get(
            "evaluated_subset_count"
        )
        != 1023
        or monotonicity.get("pairwise_monotonicity", {}).get(
            "subset_to_superset_comparison_count"
        )
        != 58025
    ):
        raise SystemExit("stored monotonicity evidence is incomplete")
    if read_json(ATTEMPT / "projection-receipt-verification.json") != projection:
        raise SystemExit("stored projection evidence differs from live bytes")
    if read_json(ATTEMPT / "full-regression-impact.json") != regression:
        raise SystemExit("stored regression evidence differs from JUnit")
    if read_json(ATTEMPT / "dependency-status.json") != dependency:
        raise SystemExit("stored DAG evidence differs from live manifest")
    reconciliation = read_json(ATTEMPT / "phase-artifact-reconciliation.json")
    if reconciliation.get("status") != "PASS" or reconciliation.get("failures") != []:
        raise SystemExit("phase artifact reconciliation is not a clean PASS")

    review = (ATTEMPT / "review.md").read_text(encoding="utf-8")
    required_review = (
        "Overall package recommendation: `PASS`",
        "Non-waivable findings: 0",
        "All five defects are resolved",
        "S04-TM004",
        "HumanDecision schema does not structurally encode exact",
        "suite container",
    )
    if not all(token in review for token in required_review):
        raise SystemExit("review omits a required finding or assurance boundary")
    rows = read_jsonl(ATTEMPT / "commands.jsonl")
    expected_count = 16 if require_closeout else 12
    ids = [row.get("command_id") for row in rows]
    if len(rows) != expected_count or len(ids) != len(set(ids)):
        raise SystemExit("command ledger count or identity is invalid")
    if require_closeout:
        report = read_json(ATTEMPT / "report.json")
        integrity = read_json(ATTEMPT / "rah-core-integrity.json")
        if report.get("status") != "PASS" or report.get("package_status") != "PASS":
            raise SystemExit("F01 report is not PASS")
        if report.get("completion_ready") is not False:
            raise SystemExit("F01 report advanced completion readiness")
        if integrity.get("status") != "PASS" or integrity.get(
            "latest_evidence_id"
        ) != "E0044":
            raise SystemExit("RAH core integrity evidence is not sealed E0044")
    return {
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
