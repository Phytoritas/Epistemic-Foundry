#!/usr/bin/env python3
"""Deterministically verify the C01-0004 canonical-contract gate.

The product-owner decision HD-EF4-C01-SG003-20260728-001 deliberately moves
handwritten runtime migration to C03 and the repository-wide zero-failure gate
to C04.  This verifier therefore treats exactly the preserved 24 migration
failures as declared debt, but fails closed on a new node, a changed stable
fingerprint, a canonical contract failure, or a mutation of any C03-owned
runtime/test path.

Raw pytest messages are retained.  Fingerprint normalization removes only the
volatile ``(+N more)`` aggregate suffix and binds the node ID, exception type,
canonical schema, root-cause category, and stable required-field anchor.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = "artifacts/work_packages/C01/attempts/0004"

ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}

PROMOTION_LEVELS = [
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
]

GATE_ORDER = [
    "G00_PIN_RESOLUTION",
    "G01_POLICY_AUTHORITY",
    "G02_EVALUATOR_HOLDOUT_FIREWALL",
    "G03_SCHEMA_LINEAGE_COUNT",
    "G04_SOURCE_PROVENANCE",
    "G05_SEARCH_COVERAGE",
    "G06_METHOD_SCOPE_DEPENDENCY",
    "G07_VALIDATION_LEAKAGE",
    "G08_ADAPTIVE_STATISTICS",
    "G09_RED_QUEEN",
    "G10_REPLICATION_CEILING",
    "G11_PARLIAMENT",
    "G12_INDEPENDENT_ATTESTATION",
    "G13_HUMAN_POLICY_APPROVAL",
    "G14_ATOMIC_PROMOTION_COMMIT",
]

RESOLVED_REF_KEYS = {
    "base_run_spec",
    "schema_bundle",
    "workflow",
    "policy_bundle",
    "corpus_evidence_snapshot",
    "ontology",
    "domain_pack",
    "evaluator_bundle",
    "holdout_manifest",
    "operator_registry",
    "prompt_bundle",
    "model_routing_policy",
    "provider_adapter_manifest",
    "statistical_plan",
    "selection_policy",
    "stop_policy",
    "replication_policy",
    "archive_niche_policy",
    "budget_envelope",
    "execution_environment_toolchain_manifest",
}

RESOLVED_REF_FIELDS = {
    "logical_id",
    "exact_version_or_revision",
    "content_hash",
    "resolver_id",
    "resolver_version",
    "resolved_artifact_locator",
    "resolved_at",
    "authority_source_class",
    "reproducibility_class",
}

EXPECTED_C01_WRITE_SCOPE = [
    "schemas/**",
    "openapi/**",
    "docs/api_contract.md",
    "tests/contracts/openapi/**",
    "artifacts/work_packages/C01/**",
    "examples/sample_evolution-run-spec.json",
    "examples/sample_promotion-decision.json",
]

C01_0004_DECLARED_CHANGES = [
    "schemas/promotion-decision.schema.json",
    "docs/api_contract.md",
    "tests/contracts/openapi/test_scientific_contracts.py",
    f"{ATTEMPT}/c01-contract-verifier.py",
    f"{ATTEMPT}/runtime-migration-baseline.junit.xml",
    f"{ATTEMPT}/runtime-migration-residual.junit.xml",
    f"{ATTEMPT}/targeted-contracts.junit.xml",
    f"{ATTEMPT}/runtime-migration-impact.json",
    f"{ATTEMPT}/c01-contract-verification.json",
    f"{ATTEMPT}/dependency-status.json",
    f"{ATTEMPT}/commands.jsonl",
    f"{ATTEMPT}/review.md",
    f"{ATTEMPT}/report.json",
]

RUNTIME_HASHES = {
    "src/epistemic_foundry/evolution_chamber/run_spec.py":
        "b18ac50a737f2ffd2e948a67541737e6dad4feafc8f7262f464311bafc55eb4b",
    "src/epistemic_foundry/governance/promotion.py":
        "a05013fdd9ea83a51071f376075b540a2fc371bb7e9f2ff12f786feb0ba90e71",
    "tests/test_evolution_chamber.py":
        "8034125cb1f1e4a4dec9667dc8880f6e695eafbbfa14c15b4e8ec99bff3988d9",
    "tests/test_governance.py":
        "6e588dc71df2da2abade7e06fc1b8817c1eb1d66eca82972080f17cd278ec7fa",
    "tests/test_integration_forge_cycle.py":
        "a137c6f16c64ecfcc10c49d2d2dba96c360fcd0f25e7943f06d0a3fc19e4bc75",
}

HISTORY_HASHES = {
    "artifacts/work_packages/C01/attempts/0003/report.json":
        "d3f14a0f227bc7fa4743b7d2fbb266cb1999cd2524f4a93a9770b19910a130e5",
    "artifacts/work_packages/C01/attempts/0003/c01-regression-boundary-verification.json":
        "c0bf2ba5e156845731229bced427af3f390bcc3f77891fcd7e3075701fa27ee0",
    "artifacts/work_packages/C01/attempts/0003/review.md":
        "ed85ebe9b31e8bc223a3a50cefb05a77daaeebcb29aa80ee752df8fb7d05e3b8",
    "artifacts/work_packages/A05/attempts/0002/report.json":
        "c9c550de22f55d32898f0d33489bc9b0480de6eef4bca7baeb09fcf047c6062c",
    "artifacts/authority_decisions/HD-EF4-C01-SG003-20260728-001.human-decision.json":
        "bcce9f20f59712c78032a846e1ac368e8d0cf27141731df31478a1f7e976d38e",
}

CONTRACT_HASHES = {
    "manifests/development_manifest.yaml":
        "a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345",
    "schemas/evolution-run-spec.schema.json":
        "54f6934f33426c8706640038c25f63687097fad36f21c84d46fdf5b0d9b9291a",
    "schemas/promotion-decision.schema.json":
        "5a33e660aebed94c7a74de1fa8c8767f189b4367b70a830733fdda3c7d1caea7",
    "schemas/gate-decision.schema.json":
        "9f23594f912116cdaa2357c56e35c12f3a57606ce4793462245f86bfe9ad2559",
    "schemas/phase-artifact-set.schema.json":
        "4db66de7a172062d9742736681641a0d312fac2fe2a798606757996b53cb3fb6",
    "examples/sample_evolution-run-spec.json":
        "bf4bada986c682155388c83eb7913b5bd0c66ba4453527570f67d2bd2851cc3b",
    "examples/sample_promotion-decision.json":
        "d7512f0e94894c4dd85146879709778393a1f00c4856d1d67d9169004538312d",
    "openapi/epistemic-foundry-v1.openapi.yaml":
        "c77aa89918cc33cded07755bbf2cbec7fcb6554e573efbca2ebd9480b78344d7",
    "docs/api_contract.md":
        "317076f114f2e94d13b494487a3cbdfbcd061d31a1c225faefd6aebe17bc9b65",
    "tests/contracts/openapi/conftest.py":
        "437641ef742cc0be69b0a666f4c8e619c108dd2c1624f65b9afaf51202ebe5f0",
    "tests/contracts/openapi/test_openapi_contract.py":
        "737dd012fc3b7104763e189d2aea0998c90897856007058a715efd3f2c0471a4",
    "tests/contracts/openapi/test_scientific_contracts.py":
        "27296a0b77b21f00631936124c0738f2fca40b31ac23d040162b1b8dfd0f324c",
}

JUNIT_HASHES = {
    f"{ATTEMPT}/runtime-migration-baseline.junit.xml":
        "8b943d8dcf3596fc48fcc613d014e0deae29d4af796921850c335e90874896a5",
    f"{ATTEMPT}/runtime-migration-residual.junit.xml":
        "3fcad36fbf05967ccc36a8ca3769993e26a85483e615543001d340f48a53c32e",
    f"{ATTEMPT}/targeted-contracts.junit.xml":
        "cd9b7bddd532e924ec56c8f54ae30582e88007ce8f82a9332d5dcab656e90ddc",
}

NORMALIZATION = {
    "algorithm": "ef-c01-migration-fingerprint",
    "version": 1,
    "fields": [
        "pytest_node_id",
        "exception_type",
        "canonical_schema",
        "root_cause_category",
        "stable_required_field_anchor",
    ],
    "excluded_only": "volatile terminal aggregate suffix matching ' (+N more)'",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(relative: str) -> str:
    return _sha256_bytes((ROOT / relative).read_bytes())


def _hash_checks(expected: dict[str, str]) -> dict[str, dict[str, str]]:
    results: dict[str, dict[str, str]] = {}
    for relative, wanted in expected.items():
        actual = _sha256(relative)
        status = "PASS" if actual == wanted else "FAIL"
        results[relative] = {
            "expected_sha256": wanted,
            "actual_sha256": actual,
            "status": status,
        }
    if any(item["status"] != "PASS" for item in results.values()):
        raise RuntimeError("one or more hash-bound inputs changed")
    return results


def _load_json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{relative} must contain an object")
    return value


def _canonical_hash(document: dict[str, Any], excluded: str) -> str:
    payload = copy.deepcopy(document)
    payload.pop(excluded, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + _sha256_bytes(encoded)


def _schema_errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def _mapped_example(schema_path: Path) -> Path | None:
    stem = schema_path.name.removesuffix(".schema.json")
    candidates = [
        ALIASES.get(stem),
        f"sample_{stem}.json",
        f"sample_{stem.replace('-', '_')}.json",
    ]
    return next(
        (
            ROOT / "examples" / candidate
            for candidate in candidates
            if candidate and (ROOT / "examples" / candidate).is_file()
        ),
        None,
    )


def _schema_example_evidence() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("*.json"))
    registry = Registry()
    schemas: dict[str, dict[str, Any]] = {}
    schema_ids: list[str] = []

    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise RuntimeError(f"{path.name}: missing $id")
        schema_ids.append(schema_id)
        registry = registry.with_resource(schema_id, Resource.from_contents(schema))
        schemas[path.name] = schema

    failures: list[str] = []
    mapped: set[Path] = set()
    for path in schema_paths:
        example = _mapped_example(path)
        if example is None:
            failures.append(f"{path.name}: no mapped example")
            continue
        mapped.add(example)
        instance = json.loads(example.read_text(encoding="utf-8"))
        validator = Draft202012Validator(
            schemas[path.name],
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in validator.iter_errors(instance):
            location = "/".join(map(str, error.path)) or "<root>"
            failures.append(f"{example.name}:{location}: {error.message}")

    if len(schema_paths) != 124 or len(example_paths) != 124:
        failures.append("canonical schema/example count differs from 124/124")
    if len(schema_ids) != len(set(schema_ids)):
        failures.append("canonical schema $id values are not unique")
    if mapped != set(example_paths):
        failures.append("schema/example mapping is not one-to-one")
    if failures:
        raise RuntimeError(f"canonical schema/example validation failed: {failures[:5]}")

    scan_paths = [
        *schema_paths,
        *example_paths,
        ROOT / "openapi/epistemic-foundry-v1.openapi.yaml",
        ROOT / "docs/api_contract.md",
    ]
    forbidden_hits: list[str] = []
    for path in scan_paths:
        text = path.read_text(encoding="utf-8")
        for literal in ('"PILOT"', '"HYPOTHESIS_PASSPORT_ONLY"'):
            if literal in text:
                forbidden_hits.append(
                    f"{path.relative_to(ROOT).as_posix()}: {literal}"
                )
    if forbidden_hits:
        raise RuntimeError(f"legacy promotion literals remain: {forbidden_hits}")

    evolution_schema = schemas["evolution-run-spec.schema.json"]
    promotion_schema = schemas["promotion-decision.schema.json"]
    evolution = _load_json("examples/sample_evolution-run-spec.json")
    promotion = _load_json("examples/sample_promotion-decision.json")
    resolved_refs = evolution["resolved_refs"]

    if set(resolved_refs) != RESOLVED_REF_KEYS:
        raise RuntimeError("EvolutionRunSpec resolved_refs inventory changed")
    if set(evolution_schema["properties"]["resolved_refs"]["required"]) != RESOLVED_REF_KEYS:
        raise RuntimeError("EvolutionRunSpec schema required ref inventory changed")
    for key, reference in resolved_refs.items():
        if not RESOLVED_REF_FIELDS <= set(reference):
            raise RuntimeError(f"resolved ref {key} is incomplete")
        revision = str(reference["exact_version_or_revision"])
        if re.search(r"(?i)(^|[/_-])(main|master|latest|head)($|[/_-])", revision):
            raise RuntimeError(f"floating revision in {key}: {revision}")
        if re.search(r"(?:>=|<=|>|<|\^|~|\*)", revision):
            raise RuntimeError(f"version range in {key}: {revision}")

    if evolution["spec_hash"] != _canonical_hash(evolution, "spec_hash"):
        raise RuntimeError("EvolutionRunSpec fixture spec_hash does not recompute")
    if promotion["decision_hash"] != _canonical_hash(promotion, "decision_hash"):
        raise RuntimeError("PromotionDecision fixture decision_hash does not recompute")
    if promotion_schema["$defs"]["promotion_level"]["enum"] != PROMOTION_LEVELS:
        raise RuntimeError("canonical promotion level vocabulary changed")
    if promotion["gate_decision_ids"] != GATE_ORDER:
        raise RuntimeError("canonical promotion gate order changed")

    semantic_cases: dict[str, bool] = {}

    promote = copy.deepcopy(promotion)
    promote.update({
        "requested_level": "EMPIRICALLY_TESTED",
        "granted_level": "EMPIRICALLY_TESTED",
        "promotion_ceiling": "EMPIRICALLY_TESTED",
        "replication_status": "REPLICATED",
        "decision": "PROMOTE",
        "unresolved_limitations": [],
    })
    semantic_cases["promote_equal_accepts"] = not _schema_errors(promotion_schema, promote)
    promote["requested_level"] = "REPLICATED"
    semantic_cases["promote_mismatch_rejects"] = bool(
        _schema_errors(promotion_schema, promote)
    )

    conditional = copy.deepcopy(promotion)
    semantic_cases["conditional_lower_accepts"] = not _schema_errors(
        promotion_schema, conditional
    )
    conditional["granted_level"] = None
    semantic_cases["conditional_null_rejects"] = bool(
        _schema_errors(promotion_schema, conditional)
    )
    conditional["granted_level"] = conditional["requested_level"]
    semantic_cases["conditional_requested_level_rejects"] = bool(
        _schema_errors(promotion_schema, conditional)
    )

    for decision in ("REJECT", "UNDERDETERMINED", "BLOCKED"):
        non_grant = copy.deepcopy(promotion)
        non_grant.update({
            "granted_level": None,
            "replication_status": "REPLICATED",
            "decision": decision,
        })
        semantic_cases[f"{decision.lower()}_null_accepts"] = not _schema_errors(
            promotion_schema, non_grant
        )
        non_grant["granted_level"] = "EMPIRICALLY_TESTED"
        semantic_cases[f"{decision.lower()}_nonnull_rejects"] = bool(
            _schema_errors(promotion_schema, non_grant)
        )
    missing_grant = copy.deepcopy(promotion)
    missing_grant.pop("granted_level")
    semantic_cases["granted_level_remains_required"] = bool(
        _schema_errors(promotion_schema, missing_grant)
    )
    if not all(semantic_cases.values()):
        raise RuntimeError(f"PromotionDecision semantic case failed: {semantic_cases}")

    return {
        "schema_count": len(schema_paths),
        "example_count": len(example_paths),
        "valid_example_count": len(mapped),
        "unique_schema_id_count": len(set(schema_ids)),
        "schema_example_cardinality_matches": True,
        "legacy_promotion_literal_hits": forbidden_hits,
        "required_resolved_ref_count": len(RESOLVED_REF_KEYS),
        "floating_reference_hits": [],
        "promotion_levels": PROMOTION_LEVELS,
        "promotion_gate_order": GATE_ORDER,
        "promotion_semantic_cases": semantic_cases,
        "fixture_hashes": {
            "spec_hash": evolution["spec_hash"],
            "decision_hash": promotion["decision_hash"],
        },
        "status": "PASS",
    }


def _walk_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


def _resolve_pointer(document: dict[str, Any], pointer: str) -> Any:
    current: Any = document
    for raw in pointer.removeprefix("#/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[token]
    return current


def _openapi_evidence() -> dict[str, Any]:
    path = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("OpenAPI document must be an object")
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for route, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method.lower() in methods:
                operations.append((route, method.lower(), operation))
    operation_ids = [operation["operationId"] for _, _, operation in operations]
    if document.get("openapi") != "3.1.1":
        raise RuntimeError("OpenAPI version is not 3.1.1")
    if document.get("jsonSchemaDialect") != "https://json-schema.org/draft/2020-12/schema":
        raise RuntimeError("OpenAPI JSON Schema dialect changed")
    if document.get("servers") != [
        {"url": "/api/v1", "description": "Canonical v1 base path"}
    ]:
        raise RuntimeError("canonical OpenAPI base path changed")
    if len(operations) != 33 or len(set(operation_ids)) != 33:
        raise RuntimeError("OpenAPI operation inventory or uniqueness changed")

    mutation_count = 0
    reference_failures: list[str] = []
    external_refs: set[str] = set()
    for ref in _walk_refs(document):
        if ref.startswith("#/"):
            try:
                _resolve_pointer(document, ref.split("#", 1)[0] + "#" + ref.split("#", 1)[1])
            except Exception:
                reference_failures.append(ref)
        else:
            external_refs.add(ref.split("#", 1)[0])
    for ref in sorted(external_refs):
        target = (path.parent / ref).resolve()
        if not target.is_relative_to((ROOT / "schemas").resolve()) or not target.is_file():
            reference_failures.append(ref)
            continue
        schema = json.loads(target.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)

    for route, method, operation in operations:
        if "security" not in operation or "x-required-capabilities" not in operation:
            raise RuntimeError(f"{method.upper()} {route}: missing security contract")
        if method != "get":
            mutation_count += 1
            parameters = [*document["paths"][route].get("parameters", []), *operation.get("parameters", [])]
            resolved = [
                _resolve_pointer(document, item["$ref"])
                if isinstance(item, dict) and item.get("$ref", "").startswith("#/")
                else item
                for item in parameters
            ]
            key = next((item for item in resolved if item.get("name") == "Idempotency-Key"), None)
            if not key or key.get("required") is not True:
                raise RuntimeError(f"{method.upper()} {route}: missing Idempotency-Key")
    if reference_failures:
        raise RuntimeError(f"OpenAPI reference resolution failed: {reference_failures}")

    return {
        "canonical_file": "openapi/epistemic-foundry-v1.openapi.yaml",
        "openapi_version": document["openapi"],
        "json_schema_dialect": document["jsonSchemaDialect"],
        "base_path": "/api/v1",
        "operation_count": len(operations),
        "unique_operation_id_count": len(set(operation_ids)),
        "mutation_operation_count": mutation_count,
        "scientific_external_ref_count": len(external_refs),
        "reference_resolution_failures": reference_failures,
        "all_operations_have_explicit_security_and_capabilities": True,
        "all_mutations_require_idempotency_key": True,
        "external_validator": {
            "tool": "openapi-spec-validator",
            "version": "0.7.2",
            "command_id": "C01-0004-C005",
            "input_sha256": _sha256("openapi/epistemic-foundry-v1.openapi.yaml"),
            "exit_code": 0,
            "result": "OK",
        },
        "generated_client_dry_run": {
            "tool": "OpenAPI Generator CLI",
            "wrapper_version": "2.21.4",
            "generator_version": "7.14.0",
            "generator": "python",
            "command_id": "C01-0004-C006",
            "input_form": "repository-relative path",
            "input_sha256": _sha256("openapi/epistemic-foundry-v1.openapi.yaml"),
            "exit_code": 0,
            "wrote_repository_files": False,
        },
        "status": "PASS",
    }


def _junit_summary(relative: str) -> tuple[dict[str, int], dict[str, str]]:
    root = ET.parse(ROOT / relative).getroot()
    suite = next(root.iter("testsuite"))
    summary = {
        "tests": int(suite.get("tests", "0")),
        "failures": int(suite.get("failures", "0")),
        "errors": int(suite.get("errors", "0")),
        "skipped": int(suite.get("skipped", "0")),
    }
    failures: dict[str, str] = {}
    for testcase in root.iter("testcase"):
        failure = testcase.find("failure")
        if failure is None:
            continue
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        node_id = classname.replace(".", "/") + ".py::" + name
        failures[node_id] = failure.get("message", "")
    return summary, failures


def _failure_parts(node_id: str, message: str) -> dict[str, Any]:
    match = re.match(r"(?P<exception>[\w.]+): (?P<schema>[\w-]+): (?P<body>.*)", message)
    if match is None:
        raise RuntimeError(f"unparseable failure message for {node_id}: {message}")
    required = re.findall(r"'([^']+)' is a required property", match.group("body"))
    if match.group("schema") == "evolution-run-spec":
        category = "missing_required_resolved_reference_contract"
        anchor = ["external_backend_enabled", "resolved_refs"]
        affected = "src/epistemic_foundry/evolution_chamber/run_spec.py"
        contract_change = "EvolutionRunSpec requires external_backend_enabled and complete resolved_refs pins."
        expected_test = "C03: EvolutionRunSpec strict pin and legacy migration tests plus this node"
    elif match.group("schema") == "promotion-decision":
        category = "legacy_promotion_record_missing_canonical_pack_receipt_revision_fields"
        anchor = [
            "artifact_receipt_ids",
            "attestation_id",
            "candidate_revision",
            "commit_action_intent_id",
            "effect_receipt_id",
        ]
        affected = "src/epistemic_foundry/governance/promotion.py"
        contract_change = "PromotionDecision requires canonical levels, decision-scoped null, sealed pack, gates, revisions, and receipts."
        expected_test = "C03: PromotionDecision null/non-null, receipt-bound commit, and replay tests plus this node"
    else:
        raise RuntimeError(f"unexpected canonical schema in residual failure: {message}")
    if required[: len(anchor)] != anchor:
        raise RuntimeError(
            f"stable required-field anchor changed for {node_id}: {required!r}"
        )
    payload = {
        "normalization_algorithm": NORMALIZATION["algorithm"],
        "normalization_version": NORMALIZATION["version"],
        "pytest_node_id": node_id,
        "exception_type": match.group("exception"),
        "canonical_schema": match.group("schema"),
        "root_cause_category": category,
        "stable_required_field_anchor": anchor,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **payload,
        "normalized_fingerprint": "sha256:" + _sha256_bytes(encoded),
        "affected_runtime_path": affected,
        "canonical_contract_change": contract_change,
        "migration_owner": "C03",
        "expected_resolving_test": expected_test,
        "classification": "pre_existing_expected_migration_failure",
    }


def build_runtime_impact() -> dict[str, Any]:
    _hash_checks(JUNIT_HASHES)
    baseline_summary, baseline_failures = _junit_summary(
        f"{ATTEMPT}/runtime-migration-baseline.junit.xml"
    )
    residual_summary, residual_failures = _junit_summary(
        f"{ATTEMPT}/runtime-migration-residual.junit.xml"
    )
    if baseline_summary != {"tests": 848, "failures": 24, "errors": 0, "skipped": 0}:
        raise RuntimeError(f"unexpected baseline JUnit summary: {baseline_summary}")
    if residual_summary != {"tests": 855, "failures": 24, "errors": 0, "skipped": 0}:
        raise RuntimeError(f"unexpected residual JUnit summary: {residual_summary}")
    if set(baseline_failures) != set(residual_failures) or len(residual_failures) != 24:
        raise RuntimeError("baseline/residual failure node identity changed")

    records: list[dict[str, Any]] = []
    raw_changed = 0
    for node_id in sorted(residual_failures):
        baseline = baseline_failures[node_id]
        residual = residual_failures[node_id]
        baseline_parts = _failure_parts(node_id, baseline)
        residual_parts = _failure_parts(node_id, residual)
        if baseline_parts["normalized_fingerprint"] != residual_parts["normalized_fingerprint"]:
            raise RuntimeError(f"normalized failure fingerprint changed: {node_id}")
        changed = baseline != residual
        raw_changed += int(changed)
        baseline_suffix = re.search(r"\(\+(\d+) more\)$", baseline)
        residual_suffix = re.search(r"\(\+(\d+) more\)$", residual)
        records.append({
            **residual_parts,
            "raw_baseline_message": baseline,
            "raw_residual_message": residual,
            "raw_baseline_sha256": "sha256:" + _sha256_bytes(baseline.encode("utf-8")),
            "raw_residual_sha256": "sha256:" + _sha256_bytes(residual.encode("utf-8")),
            "raw_message_changed": changed,
            "baseline_aggregate_more_count": (
                int(baseline_suffix.group(1)) if baseline_suffix else None
            ),
            "residual_aggregate_more_count": (
                int(residual_suffix.group(1)) if residual_suffix else None
            ),
            "raw_change_explanation": (
                "The authorized decision-scoped granted_level schema refinement removed or "
                "reclassified secondary validation branches; the node, exception, canonical "
                "schema, root cause, and stable required-field anchor are unchanged."
                if changed else "Raw message is byte-identical."
            ),
        })

    return {
        "schema_version": 1,
        "artifact_id": "C01-0004-RUNTIME-MIGRATION-IMPACT",
        "work_package_id": "C01",
        "attempt_id": "C01-0004",
        "authority_decision_id": "HD-EF4-C01-SG003-20260728-001",
        "status": "EXPECTED_FAILURES_PENDING_C03",
        "normalization": NORMALIZATION,
        "baseline": {
            **baseline_summary,
            "passed": baseline_summary["tests"] - baseline_summary["failures"],
            "artifact": f"{ATTEMPT}/runtime-migration-baseline.junit.xml",
            "sha256": _sha256(f"{ATTEMPT}/runtime-migration-baseline.junit.xml"),
        },
        "residual": {
            **residual_summary,
            "passed": residual_summary["tests"] - residual_summary["failures"],
            "artifact": f"{ATTEMPT}/runtime-migration-residual.junit.xml",
            "sha256": _sha256(f"{ATTEMPT}/runtime-migration-residual.junit.xml"),
        },
        "expected_failure_count": 24,
        "same_node_ids": True,
        "normalized_fingerprint_parity": True,
        "raw_message_changed_count": raw_changed,
        "raw_message_unchanged_count": 24 - raw_changed,
        "new_failure_count": 0,
        "missing_baseline_failure_count": 0,
        "migration_owner": "C03",
        "failures": records,
    }


def _manifest_evidence() -> dict[str, Any]:
    document = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = document if isinstance(document, list) else document["work_packages"]
    by_id = {item["id"]: item for item in packages}
    if len(packages) != 156:
        raise RuntimeError("development manifest package count changed")
    if by_id["C01"]["depends_on"] != ["A04", "A05"]:
        raise RuntimeError("C01 dependency contract changed")
    if by_id["C01"]["write_scope"] != EXPECTED_C01_WRITE_SCOPE:
        raise RuntimeError("C01 exact write scope changed")
    if by_id["C02"]["depends_on"] != ["C01"]:
        raise RuntimeError("C02 dependency contract changed")
    if by_id["C03"]["depends_on"] != ["C01", "C02"]:
        raise RuntimeError("C03 dependency contract changed")
    if by_id["C04"]["depends_on"] != ["C02", "C03"]:
        raise RuntimeError("C04 dependency contract changed")
    if by_id["B04"]["depends_on"] != ["B02", "B03", "C04"]:
        raise RuntimeError("B04 dependency contract changed")
    if any(
        path not in by_id["C03"]["write_scope"]
        for path in RUNTIME_HASHES
    ):
        raise RuntimeError("C03 does not own every exact migration path")
    if any(path in by_id["C01"]["write_scope"] for path in RUNTIME_HASHES):
        raise RuntimeError("C01 improperly owns a C03 runtime migration path")
    return {
        "work_package_count": len(packages),
        "C01": {
            "depends_on": by_id["C01"]["depends_on"],
            "write_scope": by_id["C01"]["write_scope"],
        },
        "C02_depends_on": by_id["C02"]["depends_on"],
        "C03_depends_on": by_id["C03"]["depends_on"],
        "C04_depends_on": by_id["C04"]["depends_on"],
        "B04_depends_on": by_id["B04"]["depends_on"],
        "C03_exact_migration_paths": list(RUNTIME_HASHES),
        "status": "PASS",
    }


def _scope_matches(scope: str, relative: str) -> bool:
    if scope.endswith("/**"):
        prefix = scope[:-3]
        return relative == prefix or relative.startswith(prefix + "/")
    return relative == scope


def _write_scope_evidence() -> dict[str, Any]:
    violations = [
        relative
        for relative in C01_0004_DECLARED_CHANGES
        if not any(_scope_matches(scope, relative) for scope in EXPECTED_C01_WRITE_SCOPE)
    ]
    if violations:
        raise RuntimeError(f"C01-0004 declared write-scope violations: {violations}")
    return {
        "audit_method": (
            "All declared attempt-0004 outputs are matched against the exact C01 scope; "
            "the five C03-owned paths are additionally hash-bound to the pre-attempt values."
        ),
        "declared_change_count": len(C01_0004_DECLARED_CHANGES),
        "declared_changes": C01_0004_DECLARED_CHANGES,
        "violation_count": len(violations),
        "violations": violations,
        "runtime_boundary_hash_checks": _hash_checks(RUNTIME_HASHES),
        "status": "PASS",
    }


def _targeted_test_evidence() -> dict[str, Any]:
    summary, failures = _junit_summary(f"{ATTEMPT}/targeted-contracts.junit.xml")
    expected = {"tests": 71, "failures": 0, "errors": 0, "skipped": 0}
    if summary != expected or failures:
        raise RuntimeError(f"targeted C01 test result changed: {summary}")
    return {
        "command": (
            "python -m pytest tests/contracts/openapi "
            "tests/test_wire_literal_discipline.py -p no:cacheprovider --tb=short "
            f"--junitxml={ATTEMPT}/targeted-contracts.junit.xml"
        ),
        "exit_code": 0,
        "passed": 71,
        "failed": 0,
        "skipped": 0,
        "artifact": f"{ATTEMPT}/targeted-contracts.junit.xml",
        "sha256": _sha256(f"{ATTEMPT}/targeted-contracts.junit.xml"),
        "status": "PASS",
    }


def build_verification(impact: dict[str, Any]) -> dict[str, Any]:
    history = _hash_checks(HISTORY_HASHES)
    contract = _hash_checks(CONTRACT_HASHES)
    schema_examples = _schema_example_evidence()
    openapi = _openapi_evidence()
    manifest = _manifest_evidence()
    scope = _write_scope_evidence()
    targeted = _targeted_test_evidence()
    impact_bytes = (
        json.dumps(impact, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    decision = _load_json(
        "artifacts/authority_decisions/HD-EF4-C01-SG003-20260728-001.human-decision.json"
    )
    if decision["decision_hash"] != "sha256:4717a98cfc987dac28c9b113d843e6f0077947d42589523e8e4cee2f0be64f5b":
        raise RuntimeError("C01-SG003 HumanDecision canonical hash changed")

    return {
        "schema_version": 1,
        "probe_id": "C01-P004",
        "work_package_id": "C01",
        "attempt_id": "C01-0004",
        "authority_decision_id": "HD-EF4-C01-SG003-20260728-001",
        "authority_decision_hash": decision["decision_hash"],
        "package_status": "PASS",
        "contract_status": "CONFORMANT",
        "runtime_migration_status": "PENDING_C03",
        "full_suite_status": "EXPECTED_FAILURES_PENDING_C03",
        "repository_full_suite_status": "EXPECTED_MIGRATION_FAILURES",
        "expected_failure_count": 24,
        "migration_owner": "C03",
        "completion_ready": False,
        "history_hash_checks": history,
        "contract_input_hash_checks": contract,
        "manifest_contract": manifest,
        "write_scope_audit": scope,
        "canonical_contract": {
            "schema_examples": schema_examples,
            "openapi": openapi,
            "targeted_tests": targeted,
            "status": "PASS",
        },
        "runtime_migration_impact": {
            "artifact": f"{ATTEMPT}/runtime-migration-impact.json",
            "sha256": _sha256_bytes(impact_bytes),
            "baseline_passed": impact["baseline"]["passed"],
            "baseline_failed": impact["baseline"]["failures"],
            "residual_passed": impact["residual"]["passed"],
            "residual_failed": impact["residual"]["failures"],
            "normalized_fingerprint_parity": impact["normalized_fingerprint_parity"],
            "raw_message_changed_count": impact["raw_message_changed_count"],
            "new_failure_count": impact["new_failure_count"],
            "status": "EXPECTED_FAILURES_PENDING_C03",
        },
        "classification": {
            "C01_local_gate": "PASS",
            "full_suite_is_not_reported_pass": True,
            "residual_failures_are_not_hidden": True,
            "residual_failure_owner": "C03",
            "repository_zero_failure_gate_owner": "C04",
            "B04_may_start_now": False,
        },
        "status": "PASS",
    }


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--print-json", choices=("impact", "verification"))
    args = parser.parse_args()

    impact = build_runtime_impact()
    verification = build_verification(impact)
    impact_path = ROOT / ATTEMPT / "runtime-migration-impact.json"
    verification_path = ROOT / ATTEMPT / "c01-contract-verification.json"
    rendered_impact = _render(impact)
    rendered_verification = _render(verification)

    if args.write:
        impact_path.write_text(rendered_impact, encoding="utf-8", newline="\n")
        verification_path.write_text(rendered_verification, encoding="utf-8", newline="\n")
        print(f"PASS: wrote {impact_path.relative_to(ROOT)}")
        print(f"PASS: wrote {verification_path.relative_to(ROOT)}")
        return 0
    if args.check:
        if impact_path.read_text(encoding="utf-8") != rendered_impact:
            raise SystemExit(f"evidence differs from {impact_path}")
        if verification_path.read_text(encoding="utf-8") != rendered_verification:
            raise SystemExit(f"evidence differs from {verification_path}")
        print("PASS: C01-0004 evidence matches deterministic verifier output")
        return 0
    sys.stdout.write(
        rendered_impact if args.print_json == "impact" else rendered_verification
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
