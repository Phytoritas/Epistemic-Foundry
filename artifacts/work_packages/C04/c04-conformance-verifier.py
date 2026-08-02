#!/usr/bin/env python3
"""Fail-closed repository conformance verifier for work package C04.

C04 owns no implementation surface.  This verifier therefore consumes the
fresh JUnit receipts and independently composes the canonical schemas,
examples, OpenAPI document, generated projections, migrated handwritten
runtime, promotion commit authority, and append-only ledger into one bounded
integration verdict.  It never treats an unimplemented HTTP/MCP/persistence
adapter as implemented merely because its transport contract exists.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib.util
import inspect
import json
import py_compile
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "C04"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "codegen"))

import generate as contract_codegen  # noqa: E402
from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload  # noqa: E402
from epistemic_foundry.domain.status import ForgePhase, WorkClass  # noqa: E402
from epistemic_foundry.evolution_chamber.run_spec import (  # noqa: E402
    build_evolution_run_spec,
)
from epistemic_foundry.foundry_kernel import ForgeKernel  # noqa: E402
from epistemic_foundry.foundry_kernel.gates import (  # noqa: E402
    GateSpec,
    evaluate_gate,
    gate_decision,
)
from epistemic_foundry.governance.promotion import (  # noqa: E402
    CANONICAL_GATE_IDS,
    MissingEffectReceipt,
    PromotionCommitter,
    PromotionLevel,
    PromotionRequest,
    decide_promotion,
    promotion_idempotency_key,
)
from epistemic_foundry.noetic_ledger import (  # noqa: E402
    NoeticLedger,
    build_effect_receipt,
)


ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}

PROMOTION_LADDER = (
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
)

EXPECTED_C04_DEPENDENCIES = ("C02", "C03")
EXPECTED_C04_WRITE_SCOPE = ("artifacts/work_packages/C04/**",)
EXPECTED_C04_CHECKS = (
    "contract_surface_conformance",
    "phase_artifact_reconciliation",
    "full_python_suite",
    "canonical_schema_example_validation",
    "openapi_validation",
    "generated_contract_parity",
    "legacy_enum_absence",
    "migration_allowlist_empty",
    "runtime_schema_semantic_parity",
    "independent_integration_review",
)

FROZEN_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C01/attempts/0004/report.json": (
        "424f40396e93bd6826bf5ad85c3580cac7bd4ea8171b93f24816bc6a78c4a5d6"
    ),
    "artifacts/work_packages/C01/attempts/0004/c01-contract-verification.json": (
        "c60a154ff342a802de5f8333b3cbad8bdfdc4c15a4f6c735a51c47e0ef7abc64"
    ),
    "artifacts/work_packages/C02/report.json": (
        "2f9a92ead5a97ecc47d2a70d2101bb4a302a6868710621511869c6e6f202d2e1"
    ),
    "artifacts/work_packages/C02/c02-contract-codegen-verification.json": (
        "df55f11d6c3650868c67f73a1d67b0d586598bba10c4740888815255fbb516bf"
    ),
    "artifacts/work_packages/C03/report.json": (
        "8bc497806e76a1faa0761e945c74f539e7fe4d44a03d9d162cbfee1c44400ad5"
    ),
    "artifacts/work_packages/C03/c03-runtime-migration-verification.json": (
        "51c22895ee9f0b8ae8ab44b61af13a1ab9600f5f1a8751efd890c1caacbfd4ff"
    ),
    "artifacts/work_packages/C03/c03-runtime-migration-verifier.py": (
        "5cb73f686085f0cab82737203e3bc0a281373da55139260217ee0ac9d648993e"
    ),
    "artifacts/work_packages/C03/full-python-regression.junit.xml": (
        "b30c079f4b65c92f23974cf6597d5e2ccbb1516b9e45bb4150ad7deccd4114d8"
    ),
    "manifests/development_manifest.yaml": (
        "a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345"
    ),
    "artifacts/authority_decisions/HD-EF4-C01-SG003-20260728-001.human-decision.json": (
        "bcce9f20f59712c78032a846e1ac368e8d0cf27141731df31478a1f7e976d38e"
    ),
}

ACTIVE_SURFACES = (
    "schemas",
    "examples/sample_evolution-run-spec.json",
    "examples/sample_promotion-decision.json",
    "openapi",
    "docs/api_contract.md",
    "src/epistemic_foundry",
    "python/epistemic_foundry/contracts",
    "packages/contracts/src/generated",
    "web/src/generated",
)

RUNTIME_TEST_PATHS = (
    "tests/test_evolution_chamber.py",
    "tests/test_governance.py",
    "tests/test_integration_forge_cycle.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def record_check(
    checks: dict[str, Any],
    failures: list[str],
    name: str,
    function: Any,
) -> None:
    """Run one check and retain a typed failure instead of aborting early."""
    try:
        value = function()
        if isinstance(value, dict):
            checks[name] = {"status": "PASS", **value}
        else:
            checks[name] = {"status": "PASS", "result": value}
    except Exception as exc:  # fail-closed evidence capture
        message = f"{type(exc).__name__}: {exc}"
        checks[name] = {"status": "FAIL", "error": message}
        failures.append(f"{name}: {message}")


def canonical_node_id(testcase: ET.Element) -> str:
    classname = testcase.attrib.get("classname", "")
    return f"{classname.replace('.', '/')}.py::{testcase.attrib.get('name', '')}"


def parse_junit(path: Path) -> tuple[dict[str, Any], set[str], set[str]]:
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites:
        raise ValueError(f"{path} has no testsuite")
    suite = suites[0]
    tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    nodes: set[str] = set()
    nonpassing: set[str] = set()
    for case in root.iter("testcase"):
        node = canonical_node_id(case)
        nodes.add(node)
        if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
            nonpassing.add(node)
    return (
        {
            "artifact": path.relative_to(ROOT).as_posix(),
            "sha256": f"sha256:{sha256(path)}",
            "tests": tests,
            "passed": tests - failures - errors - skipped,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        },
        nodes,
        nonpassing,
    )


def verify_manifest() -> dict[str, Any]:
    manifest = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = {item["id"]: item for item in manifest["work_packages"]}
    c04 = packages["C04"]
    b04 = packages["B04"]
    if tuple(c04["depends_on"]) != EXPECTED_C04_DEPENDENCIES:
        raise ValueError("C04 dependencies changed")
    if tuple(c04["write_scope"]) != EXPECTED_C04_WRITE_SCOPE:
        raise ValueError("C04 write scope changed")
    if tuple(c04["required_checks"]) != EXPECTED_C04_CHECKS:
        raise ValueError("C04 required-check inventory changed")
    if tuple(b04["depends_on"]) != ("B02", "B03", "C04"):
        raise ValueError("B04 is not gated on B02, B03, and C04")
    return {
        "c04_dependencies": c04["depends_on"],
        "c04_write_scope": c04["write_scope"],
        "c04_required_checks": c04["required_checks"],
        "b04_dependencies": b04["depends_on"],
    }


def verify_frozen_dependencies() -> dict[str, Any]:
    hashes: dict[str, str] = {}
    mismatches: list[str] = []
    for relative, expected in FROZEN_DEPENDENCY_HASHES.items():
        actual = sha256(ROOT / relative)
        hashes[relative] = f"sha256:{actual}"
        if actual != expected:
            mismatches.append(relative)
    if mismatches:
        raise ValueError(f"frozen dependency hashes changed: {mismatches}")
    decision = load_json(
        ROOT
        / "artifacts/authority_decisions/HD-EF4-C01-SG003-20260728-001.human-decision.json"
    )
    expected_decision_hash = (
        "sha256:4717a98cfc987dac28c9b113d843e6f0077947d42589523e8e4cee2f0be64f5b"
    )
    if decision.get("decision_hash") != expected_decision_hash:
        raise ValueError("HumanDecision canonical decision hash changed")
    return {"hashes": hashes, "authority_decision_hash": expected_decision_hash}


def mapped_example(schema_path: Path) -> Path | None:
    stem = schema_path.name.removesuffix(".schema.json")
    names = (
        ALIASES.get(stem),
        f"sample_{stem}.json",
        f"sample_{stem.replace('-', '_')}.json",
    )
    candidates = {
        ROOT / "examples" / name
        for name in names
        if name is not None and (ROOT / "examples" / name).is_file()
    }
    if len(candidates) != 1:
        return None
    return candidates.pop()


def verify_schemas_examples() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("sample_*.json"))
    registry = Registry()
    documents: dict[str, dict[str, Any]] = {}
    schema_ids: list[str] = []
    for path in schema_paths:
        schema = load_json(path)
        if not isinstance(schema, dict):
            raise TypeError(f"{path.name} is not an object")
        Draft202012Validator.check_schema(schema)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise ValueError(f"{path.name} has no $id")
        schema_ids.append(schema_id)
        registry = registry.with_resource(schema_id, Resource.from_contents(schema))
        documents[path.name] = schema

    mapped: set[Path] = set()
    invalid: list[dict[str, Any]] = []
    for path in schema_paths:
        example_path = mapped_example(path)
        if example_path is None:
            invalid.append({"schema": path.name, "errors": ["no unique example"]})
            continue
        mapped.add(example_path)
        example = load_json(example_path)
        errors = sorted(
            Draft202012Validator(
                documents[path.name],
                registry=registry,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            ).iter_errors(example),
            key=lambda item: list(item.path),
        )
        if errors:
            invalid.append(
                {
                    "schema": path.name,
                    "example": example_path.name,
                    "errors": [error.message for error in errors],
                }
            )
    if len(schema_paths) != 124 or len(example_paths) != 124:
        raise ValueError(
            f"canonical count changed: schemas={len(schema_paths)}, examples={len(example_paths)}"
        )
    if len(set(schema_ids)) != 124:
        raise ValueError("canonical schema $id values are not unique")
    if mapped != set(example_paths):
        raise ValueError("schema/example mapping is not one-to-one")
    if invalid:
        raise ValueError(f"schema/example validation failed: {invalid[:3]}")
    return {
        "schema_count": len(schema_paths),
        "example_count": len(example_paths),
        "valid_example_count": len(mapped),
        "unique_schema_id_count": len(set(schema_ids)),
    }


def walk_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def resolve_pointer(document: Mapping[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"not an internal pointer: {ref}")
    current: Any = document
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[token]
    return current


def openapi_operations(document: Mapping[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    return [
        (route, method, operation)
        for route, item in document["paths"].items()
        for method, operation in item.items()
        if method in methods
    ]


def verify_openapi() -> dict[str, Any]:
    path = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("OpenAPI document is not an object")
    if document.get("openapi") != "3.1.1":
        raise ValueError("OpenAPI version is not 3.1.1")
    if document.get("jsonSchemaDialect") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("OpenAPI dialect changed")
    if document.get("servers") != [{"url": "/api/v1", "description": "Canonical v1 base path"}]:
        raise ValueError("OpenAPI base path changed")
    operations = openapi_operations(document)
    operation_ids = [operation.get("operationId") for _, _, operation in operations]
    if len(operations) != 33 or len(set(operation_ids)) != 33 or None in operation_ids:
        raise ValueError("OpenAPI operation inventory/uniqueness changed")

    external_refs: set[str] = set()
    for ref in walk_refs(document):
        if ref.startswith("#/"):
            resolve_pointer(document, ref)
        else:
            external_refs.add(ref.split("#", 1)[0])
    for ref in external_refs:
        target = (path.parent / unquote(ref)).resolve()
        if not target.is_relative_to((ROOT / "schemas").resolve()) or not target.is_file():
            raise ValueError(f"OpenAPI external reference escapes canonical schemas: {ref}")
        Draft202012Validator.check_schema(load_json(target))
    for route, method, operation in operations:
        if "security" not in operation or "x-required-capabilities" not in operation:
            raise ValueError(f"{method.upper()} {route} lacks explicit security/capability")
        if method != "get":
            parameters = [*document["paths"][route].get("parameters", []), *operation.get("parameters", [])]
            resolved = [
                resolve_pointer(document, item["$ref"])
                if isinstance(item, dict) and str(item.get("$ref", "")).startswith("#/")
                else item
                for item in parameters
            ]
            key = next((item for item in resolved if item.get("name") == "Idempotency-Key"), None)
            if not key or key.get("required") is not True:
                raise ValueError(f"{method.upper()} {route} lacks Idempotency-Key")
    return {
        "canonical_file": path.relative_to(ROOT).as_posix(),
        "sha256": f"sha256:{sha256(path)}",
        "version": document["openapi"],
        "operation_count": len(operations),
        "unique_operation_id_count": len(set(operation_ids)),
        "scientific_external_ref_count": len(external_refs),
        "all_references_resolved": True,
        "all_operations_have_security_and_capabilities": True,
        "all_mutations_require_idempotency_key": True,
    }


def verify_codegen() -> dict[str, Any]:
    expected = contract_codegen.expected_files(ROOT)
    failures = contract_codegen.check_files(ROOT, expected)
    inventory = contract_codegen.generated_inventory(ROOT)
    if failures or len(expected) != 9 or inventory != set(expected):
        raise ValueError(
            f"generated contract drift: expected={len(expected)}, actual={len(inventory)}, failures={failures}"
        )
    manifest_paths = (
        ROOT / "packages/contracts/src/generated/contract-manifest.json",
        ROOT / "python/epistemic_foundry/contracts/contract-manifest.json",
        ROOT / "web/src/generated/contract-manifest.json",
    )
    manifest_bytes = [path.read_bytes() for path in manifest_paths]
    if len(set(manifest_bytes)) != 1:
        raise ValueError("generated manifests are not byte-equal")

    with tempfile.TemporaryDirectory(prefix="ef-c04-pycompile-") as temp:
        py_compile.compile(
            ROOT / "python/epistemic_foundry/contracts/models.py",
            cfile=str(Path(temp) / "models.pyc"),
            doraise=True,
        )
    module_path = ROOT / "python/epistemic_foundry/contracts/models.py"
    spec = importlib.util.spec_from_file_location("ef_c04_generated_models", module_path)
    if spec is None or spec.loader is None:
        raise ValueError("generated Python model import spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if len(module.MODEL_NAMES) != 124 or len(module.SCHEMA_IDS) != 124:
        raise ValueError("generated Python model inventory changed")
    manifest = json.loads(manifest_bytes[0])
    if module.CONTRACT_BUNDLE_SHA256 != manifest["schema_bundle_sha256"]:
        raise ValueError("generated Python bundle hash differs from manifest")
    return {
        "generated_file_count": len(expected),
        "generated_files": sorted(path.as_posix() for path in expected),
        "manifest_byte_equality": True,
        "schema_count": manifest["schema_count"],
        "example_count": manifest["example_count"],
        "schema_bundle_sha256": manifest["schema_bundle_sha256"],
        "example_bundle_sha256": manifest["example_bundle_sha256"],
        "python_model_count": len(module.MODEL_NAMES),
    }


def run_json_command(command: list[str]) -> dict[str, Any]:
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"command did not emit JSON ({command}): {process.stdout[-500:]} {process.stderr[-500:]}"
        ) from exc
    if process.returncode != 0 or payload.get("status") != "PASS":
        raise ValueError(
            f"command failed ({command}): exit={process.returncode}, payload={payload}, stderr={process.stderr[-500:]}"
        )
    return {
        "command": command,
        "exit_code": process.returncode,
        "reported_status": payload["status"],
        "schema_count": payload.get("schema_count"),
        "example_count": payload.get("example_count"),
        "failures": payload.get("failures", []),
    }


def verify_node_fixture() -> dict[str, Any]:
    return run_json_command(["node", "packages/contracts/codegen/cross_language_fixture.mjs"])


def verify_junits() -> dict[str, Any]:
    full, full_nodes, full_nonpassing = parse_junit(
        PACKAGE / "full-python-conformance.junit.xml"
    )
    targeted, targeted_nodes, targeted_nonpassing = parse_junit(
        PACKAGE / "targeted-contract-conformance.junit.xml"
    )
    if full["tests"] < 824 or any(full[field] != 0 for field in ("failures", "errors", "skipped")):
        raise ValueError(f"full Python conformance suite is not zero-failure/zero-skip: {full}")
    if targeted["tests"] != 163 or any(
        targeted[field] != 0 for field in ("failures", "errors", "skipped")
    ):
        raise ValueError(f"targeted contract suite is not 163/163 PASS: {targeted}")
    impact = load_json(
        ROOT / "artifacts/work_packages/C01/attempts/0004/runtime-migration-impact.json"
    )
    debt_nodes = {entry["pytest_node_id"] for entry in impact["failures"]}
    missing_debt = sorted(debt_nodes - full_nodes)
    if len(debt_nodes) != 24 or missing_debt or full_nonpassing or targeted_nonpassing:
        raise ValueError(
            f"migration debt/JUnit reconciliation failed: debt={len(debt_nodes)}, missing={missing_debt}, "
            f"full_nonpassing={sorted(full_nonpassing)}, targeted_nonpassing={sorted(targeted_nonpassing)}"
        )
    return {
        "full_python_suite": full,
        "targeted_contract_suite": targeted,
        "migration_authority_count": len(debt_nodes),
        "passing_migration_debt_count": len(debt_nodes & full_nodes),
        "migration_allowlist_remaining": 0,
        "targeted_node_count": len(targeted_nodes),
    }


def active_legacy_hits() -> list[dict[str, Any]]:
    values = ("PIL" + "OT", "HYPOTHESIS_PASSPORT" + "_ONLY")
    patterns = {
        value: re.compile(rf"(?<![A-Z0-9_]){re.escape(value)}(?![A-Z0-9_])")
        for value in values
    }
    hits: list[dict[str, Any]] = []
    for relative in ACTIVE_SURFACES:
        target = ROOT / relative
        files = [target] if target.is_file() else sorted(target.rglob("*"))
        for path in files:
            if not path.is_file() or "__pycache__" in path.parts or path.suffix not in {
                ".json",
                ".py",
                ".ts",
                ".mjs",
                ".md",
                ".yaml",
                ".yml",
            }:
                continue
            text = path.read_text(encoding="utf-8")
            for value, pattern in patterns.items():
                for match in pattern.finditer(text):
                    hits.append(
                        {
                            "value": value,
                            "path": path.relative_to(ROOT).as_posix(),
                            "offset": match.start(),
                        }
                    )
    return hits


def verify_legacy_and_suppression() -> dict[str, Any]:
    legacy_hits = active_legacy_hits()
    suppression_hits: list[str] = []
    pattern = re.compile(r"pytest\.(?:mark\.(?:xfail|skip)|skip\s*\()")
    for relative in RUNTIME_TEST_PATHS:
        if pattern.search((ROOT / relative).read_text(encoding="utf-8")):
            suppression_hits.append(relative)
    if legacy_hits or suppression_hits:
        raise ValueError(
            f"active legacy/suppression hits: legacy={legacy_hits}, suppression={suppression_hits}"
        )
    return {
        "active_legacy_promotion_value_hits": legacy_hits,
        "c01_sg003_xfail_or_skip_suppression_hits": suppression_hits,
    }


def schema_errors(schema: dict[str, Any], instance: Mapping[str, Any]) -> list[str]:
    return [
        error.message
        for error in Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).iter_errors(dict(instance))
    ]


def verify_runtime_schema_semantics() -> dict[str, Any]:
    evolution_schema = load_json(ROOT / "schemas/evolution-run-spec.schema.json")
    promotion_schema = load_json(ROOT / "schemas/promotion-decision.schema.json")
    evolution_sample = load_json(ROOT / "examples/sample_evolution-run-spec.json")
    promotion_sample = load_json(ROOT / "examples/sample_promotion-decision.json")

    signature = inspect.signature(build_evolution_run_spec)
    resolved_parameter = signature.parameters["resolved_refs"]
    if resolved_parameter.default is not inspect.Parameter.empty:
        raise ValueError("runtime resolved_refs has a default")
    if "resolved_refs" not in evolution_schema["required"]:
        raise ValueError("schema resolved_refs is optional")
    if "default" in evolution_schema["properties"]["resolved_refs"]:
        raise ValueError("schema resolved_refs has a default")

    base = {
        key: copy.deepcopy(value)
        for key, value in evolution_sample.items()
        if key not in {"evolution_run_id", "spec_hash"}
    }
    accepted = build_evolution_run_spec(**base, evolution_run_id="ER-C04-PROBE")
    if accepted["spec_hash"] != hash_excluding(accepted, "spec_hash"):
        raise ValueError("runtime EvolutionRunSpec spec_hash mismatch")
    rejected: dict[str, bool] = {}
    for name, refs in (
        ("missing", None),
        ("empty", {}),
    ):
        payload = dict(base)
        if refs is None:
            payload.pop("resolved_refs")
        else:
            payload["resolved_refs"] = refs
        try:
            build_evolution_run_spec(**payload, evolution_run_id=f"ER-C04-{name}")
        except (TypeError, ValueError):
            rejected[name] = True
        else:
            rejected[name] = False

    for name, revision in (
        ("floating", "latest"),
        ("range", ">=4.0"),
    ):
        payload = copy.deepcopy(base)
        payload["resolved_refs"]["workflow"]["exact_version_or_revision"] = revision
        try:
            build_evolution_run_spec(**payload, evolution_run_id=f"ER-C04-{name}")
        except ValueError:
            rejected[name] = True
        else:
            rejected[name] = False
    payload = copy.deepcopy(base)
    payload["resolved_refs"]["provider_adapter_manifest"]["remote_models"][0][
        "exact_exposed_model_identifier"
    ] = "gpt-4o"
    try:
        build_evolution_run_spec(**payload, evolution_run_id="ER-C04-ALIAS")
    except ValueError:
        rejected["unversioned_model_alias"] = True
    else:
        rejected["unversioned_model_alias"] = False
    if not all(rejected.values()):
        raise ValueError(f"EvolutionRunSpec fail-closed cases did not reject: {rejected}")

    if tuple(promotion_schema["$defs"]["promotion_level"]["enum"]) != PROMOTION_LADDER:
        raise ValueError("schema promotion ladder changed")
    if tuple(level.value for level in PromotionLevel) != PROMOTION_LADDER:
        raise ValueError("runtime promotion ladder differs from schema")

    cases: dict[str, bool] = {}
    promote = copy.deepcopy(promotion_sample)
    promote.update(
        {
            "requested_level": "EMPIRICALLY_TESTED",
            "granted_level": "EMPIRICALLY_TESTED",
            "promotion_ceiling": "EMPIRICALLY_TESTED",
            "replication_status": "REPLICATED",
            "decision": "PROMOTE",
            "unresolved_limitations": [],
        }
    )
    promote["decision_hash"] = hash_excluding(promote, "decision_hash")
    cases["promote_equal_schema_accepts"] = not schema_errors(promotion_schema, promote)
    promote["requested_level"] = "REPLICATED"
    promote["decision_hash"] = hash_excluding(promote, "decision_hash")
    cases["promote_mismatch_schema_rejects"] = bool(schema_errors(promotion_schema, promote))

    conditional = copy.deepcopy(promotion_sample)
    cases["conditional_lower_schema_accepts"] = not schema_errors(
        promotion_schema, conditional
    )
    conditional["granted_level"] = conditional["requested_level"]
    conditional["decision_hash"] = hash_excluding(conditional, "decision_hash")
    cases["conditional_requested_schema_rejects"] = bool(
        schema_errors(promotion_schema, conditional)
    )
    conditional["granted_level"] = None
    conditional["decision_hash"] = hash_excluding(conditional, "decision_hash")
    cases["conditional_null_schema_rejects"] = bool(
        schema_errors(promotion_schema, conditional)
    )
    for verdict in ("REJECT", "UNDERDETERMINED", "BLOCKED"):
        record = copy.deepcopy(promotion_sample)
        record.update(
            {
                "decision": verdict,
                "granted_level": None,
                "replication_status": "REPLICATED",
            }
        )
        record["decision_hash"] = hash_excluding(record, "decision_hash")
        cases[f"{verdict.lower()}_null_schema_accepts"] = not schema_errors(
            promotion_schema, record
        )
        record["granted_level"] = "EMPIRICALLY_TESTED"
        record["decision_hash"] = hash_excluding(record, "decision_hash")
        cases[f"{verdict.lower()}_nonnull_schema_rejects"] = bool(
            schema_errors(promotion_schema, record)
        )
    if not all(cases.values()):
        raise ValueError(f"promotion schema semantic case failed: {cases}")
    return {
        "promotion_ladder": list(PROMOTION_LADDER),
        "resolved_refs_required_without_default": True,
        "evolution_acceptance_spec_hash": accepted["spec_hash"],
        "evolution_rejection_cases": rejected,
        "promotion_schema_cases": cases,
    }


def phase_e_pack(session_id: str) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    schema = load_json(ROOT / "schemas/phase-artifact-set.schema.json")
    annotation = schema["x-phase-e-promotion-pack"]
    kinds = list(annotation["core_required_kinds"])
    kinds.extend(annotation["conditional_required_kinds"]["VALIDATION_SCREENED_OR_HIGHER"])
    kinds.extend(annotation["conditional_required_kinds"]["HUMAN_APPROVAL_REQUIRED"])
    if tuple(annotation["gate_sequence"]) != CANONICAL_GATE_IDS:
        raise ValueError("PhaseArtifactSet gate sequence differs from promotion runtime")
    artifacts = [
        {
            "artifact_id": f"ART-C04-{index:02d}",
            "kind": kind,
            "schema_ref": f"urn:ef:c04:{kind}",
            "content_hash": sha256_of_payload({"kind": kind, "probe": "C04"}),
            "receipt_id": f"AR-C04-{index:02d}",
            "status": "VALID",
        }
        for index, kind in enumerate(kinds)
    ]
    artifact_set: dict[str, Any] = {
        "set_id": "PAS-C04-E-1",
        "session_id": session_id,
        "phase": "E",
        "required_artifacts": artifacts,
        "optional_artifacts": [],
        "complete": True,
        "missing_kinds": [],
        "validated_at": "2026-07-28T00:00:00+00:00",
    }
    artifact_set["set_hash"] = hash_excluding(artifact_set, "set_hash")
    validate_artifact("phase-artifact-set", artifact_set)
    present = {item["kind"] for item in artifacts}
    missing = sorted(set(kinds) - present)
    if missing or len(present) != len(kinds):
        raise ValueError(f"Phase E pack kind reconciliation failed: {missing}")
    return (
        artifact_set,
        tuple(item["artifact_id"] for item in artifacts),
        tuple(item["receipt_id"] for item in artifacts),
    )


def promotion_gate_decisions() -> tuple[dict[str, Any], ...]:
    return tuple(
        gate_decision(
            evaluate_gate(
                GateSpec(gate_id, ("binding",), evidence_ids=(f"ART-{gate_id}-C04",)),
                {"binding": f"sealed-{gate_id}"},
            ),
            run_id="RUN-C04-PROMOTION",
            policy_version="4.0.0-c04",
            inputs={"binding": f"sealed-{gate_id}"},
            evaluated_at="2026-07-28T00:00:00+00:00",
        )
        for gate_id in CANONICAL_GATE_IDS
    )


def build_probe_request(
    *,
    artifact_set: Mapping[str, Any],
    artifact_ids: tuple[str, ...],
    receipt_ids: tuple[str, ...],
    gates: tuple[dict[str, Any], ...],
    effect_receipt_id: str,
) -> PromotionRequest:
    pack_hash = str(artifact_set["set_hash"])
    policy_hash = "sha256:" + "c" * 64
    key = promotion_idempotency_key(
        candidate_id="CAND-C04-1",
        candidate_revision=1,
        requested_level=PromotionLevel.CANDIDATE,
        promotion_pack_hash=pack_hash,
        policy_bundle_hash=policy_hash,
    )
    return PromotionRequest(
        candidate_id="CAND-C04-1",
        candidate_revision=1,
        current_level=PromotionLevel.INBOX,
        requested_level=PromotionLevel.CANDIDATE,
        policy_promotion_ceiling=PromotionLevel.REPLICATED,
        hard_gate_status="PASS",
        fitness_vector_id="FV-C04-1",
        phase_e_artifact_set_id=str(artifact_set["set_id"]),
        promotion_pack_artifact_ids=artifact_ids,
        promotion_pack_hash=pack_hash,
        gate_decision_ids=CANONICAL_GATE_IDS,
        artifact_receipt_ids=receipt_ids,
        effect_receipt_id=effect_receipt_id,
        request_action_intent_id="AI-C04-REQUEST-PROMOTION",
        commit_action_intent_id="AI-C04-COMMIT-PROMOTION",
        policy_bundle_hash=policy_hash,
        idempotency_key=key,
        parliament_adjudication_id="ADJ-C04-1",
        attestation_id="ATT-C04-1",
        replication_status="REPLICATED",
        selective_inference_report_id="SIR-C04-1",
        gate_decisions=gates,
        replication_result_ids=("REP-C04-1",),
        approval_record_ids=("APR-C04-1",),
        grounded_evidence_ids=("EV-C04-1",),
        dependency_cluster_ids=("EDC-C04-1",),
        challenge_survived=True,
    )


def verify_forge_promotion_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ef-c04-forge-") as temp:
        ledger = NoeticLedger(Path(temp) / "ledger.jsonl")
        kernel = ForgeKernel(ledger)
        state = kernel.open_session(
            workspace_id="WS-C04",
            run_spec_id="RUN-C04-PROMOTION",
            work_class=WorkClass.E3,
            policy_hash="sha256:" + "c" * 64,
            corpus_snapshot_hash="sha256:" + "d" * 64,
            session_id="FS-C04-1",
            actor_id="ACTOR-C04-KERNEL",
        )
        for phase in (
            ForgePhase.FRAME,
            ForgePhase.OBSERVE,
            ForgePhase.REASON,
            ForgePhase.GATE,
        ):
            request = kernel.build_request(
                state,
                to_phase=phase,
                actor_id="ACTOR-C04-BOUNDED-MAKER",
                actor_role="bounded_maker",
                reason=f"C04 probe advance to {phase.value}",
            )
            state = kernel.apply_transition(state, request)

        gates = promotion_gate_decisions()
        export_request = kernel.build_request(
            state,
            to_phase=ForgePhase.EXPORT,
            actor_id="ACTOR-C04-BOUNDED-MAKER",
            actor_role="bounded_maker",
            reason="C04 probe export after G00-G14 PASS",
            gate_result_ids=tuple(gate["gate_id"] for gate in gates),
        )
        state = kernel.apply_transition(state, export_request, gate_decisions=gates)
        if state["phase"] != "E" or state["revision"] != 5:
            raise ValueError("FORGE probe did not reach phase E at revision 5")

        artifact_set, artifact_ids, receipt_ids = phase_e_pack(state["session_id"])
        request_without_receipt = build_probe_request(
            artifact_set=artifact_set,
            artifact_ids=artifact_ids,
            receipt_ids=receipt_ids,
            gates=gates,
            effect_receipt_id="EF-C04-EXPECTED",
        )
        crash_decision = decide_promotion(request_without_receipt)
        candidate = {
            "candidate_id": "CAND-C04-1",
            "revision": 1,
            "promotion_level": "INBOX",
            "promotion_history": [],
        }
        original_candidate = copy.deepcopy(candidate)
        crash_rejected = False
        try:
            PromotionCommitter().commit(
                candidate,
                crash_decision,
                expected_revision=1,
                effect_receipt=None,
            )
        except MissingEffectReceipt:
            crash_rejected = True
        if not crash_rejected or candidate != original_candidate:
            raise ValueError("crash before EffectReceipt changed candidate state")

        effect = build_effect_receipt(
            intent_id=request_without_receipt.commit_action_intent_id,
            run_id="RUN-C04-PROMOTION",
            status="SUCCEEDED",
            idempotency_key=request_without_receipt.idempotency_key,
            started_at="2026-07-28T00:00:00+00:00",
            finished_at="2026-07-28T00:00:01+00:00",
            result_artifact_ids=(artifact_set["set_id"],),
        )
        request = dataclasses.replace(
            request_without_receipt, effect_receipt_id=effect["receipt_id"]
        )
        decision = decide_promotion(request)
        committer = PromotionCommitter()
        committed = committer.commit(
            candidate,
            decision,
            expected_revision=1,
            effect_receipt=effect,
        )
        replay = committer.commit(
            committed["candidate"],
            decision,
            expected_revision=2,
            effect_receipt=effect,
        )
        promoted_candidate = committed["candidate"]
        if not (
            decision["decision"] == "PROMOTE"
            and decision["granted_level"] == "CANDIDATE"
            and committed["state_changed"] is True
            and promoted_candidate["revision"] == 2
            and promoted_candidate["promotion_level"] == "CANDIDATE"
            and promoted_candidate["promotion_history"][-1]["effect_receipt_id"]
            == effect["receipt_id"]
            and replay["replayed"] is True
            and replay["candidate"] == promoted_candidate
        ):
            raise ValueError("receipt-bound commit or replay invariants failed")

        promotion_event = ledger.append(
            event_type="promotion.committed",
            aggregate_type="hypothesis_candidate",
            aggregate_id=candidate["candidate_id"],
            actor_id="ACTOR-C04-PROMOTION-COMMITTER",
            run_id="RUN-C04-PROMOTION",
            payload={
                "decision_id": decision["decision_id"],
                "effect_receipt_id": effect["receipt_id"],
                "candidate_revision": promoted_candidate["revision"],
                "promotion_level": promoted_candidate["promotion_level"],
            },
        )
        ledger.verify()
        return {
            "forge_final_phase": state["phase"],
            "forge_revision": state["revision"],
            "phase_e_required_kind_count": len(artifact_set["required_artifacts"]),
            "phase_e_complete": artifact_set["complete"],
            "gate_decision_count": len(gates),
            "decision": decision["decision"],
            "granted_level": decision["granted_level"],
            "candidate_revision_after_commit": promoted_candidate["revision"],
            "candidate_level_after_commit": promoted_candidate["promotion_level"],
            "effect_receipt_bound": True,
            "crash_without_receipt_rejected_without_mutation": crash_rejected,
            "idempotent_replay_returned_original_result": replay["replayed"],
            "ledger_event_count": ledger.length(),
            "ledger_chain_verified": True,
        }


def verify_surface_claim_boundary() -> dict[str, Any]:
    reports = [
        load_json(ROOT / "artifacts/work_packages/C01/attempts/0004/report.json"),
        load_json(ROOT / "artifacts/work_packages/C02/report.json"),
        load_json(ROOT / "artifacts/work_packages/C03/report.json"),
    ]
    overclaims: list[str] = []
    for report in reports:
        for statement in report.get("not_verified", []):
            lowered = str(statement).lower()
            if any(term in lowered for term in ("rest handler", "persistence", "transport behavior")):
                break
        else:
            overclaims.append(str(report.get("work_package_id")))
    if overclaims:
        raise ValueError(f"dependency reports omit runtime transport limitation: {overclaims}")
    return {
        "canonical_contract_shapes_checked": [
            "OpenAPI REST v1",
            "generated Python transport models",
            "generated TypeScript transport models",
            "generated UI descriptors",
            "handwritten EvolutionRunSpec and PromotionDecision runtime semantics",
        ],
        "unimplemented_runtime_claims": [],
        "explicitly_not_claimed": [
            "production HTTP handlers",
            "MCP transport runtime",
            "durable persistence adapters",
            "external actor-independent certification",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "c04-conformance-verification.json",
    )
    args = parser.parse_args()
    checks: dict[str, Any] = {}
    failures: list[str] = []

    record_check(checks, failures, "manifest_contract", verify_manifest)
    record_check(checks, failures, "frozen_dependencies", verify_frozen_dependencies)
    record_check(checks, failures, "canonical_schema_example_validation", verify_schemas_examples)
    record_check(checks, failures, "openapi_validation", verify_openapi)
    record_check(checks, failures, "generated_contract_parity", verify_codegen)
    record_check(checks, failures, "cross_language_fixture_parity", verify_node_fixture)
    record_check(checks, failures, "python_suite_and_migration_allowlist", verify_junits)
    record_check(checks, failures, "legacy_enum_and_suppression_absence", verify_legacy_and_suppression)
    record_check(checks, failures, "runtime_schema_semantic_parity", verify_runtime_schema_semantics)
    record_check(checks, failures, "forge_promotion_receipt_probe", verify_forge_promotion_probe)
    record_check(checks, failures, "contract_surface_claim_boundary", verify_surface_claim_boundary)

    generated_hashes = {
        path.relative_to(ROOT).as_posix(): f"sha256:{sha256(path)}"
        for path in sorted(
            [
                *(ROOT / "packages/contracts/src/generated").glob("*"),
                *(ROOT / "python/epistemic_foundry/contracts").glob("*"),
                *(ROOT / "web/src/generated").glob("*"),
            ]
        )
        if path.is_file() and "__pycache__" not in path.parts
    }
    result = {
        "schema_version": 1,
        "work_package_id": "C04",
        "attempt_id": "C04-0001",
        "authority_decision_id": "HD-EF4-C01-SG003-20260728-001",
        "check": "c04_repository_contract_conformance",
        "status": "PASS" if not failures else "FAIL",
        "package_status": "PASS" if not failures else "FAIL",
        "contract_status": "CONFORMANT" if not failures else "NONCONFORMANT",
        "repository_full_suite_status": "ZERO_FAILURE" if not failures else "FAIL",
        "completion_ready": False,
        "checks": checks,
        "generated_artifact_hashes": generated_hashes,
        "failures": failures,
        "next_package_if_pass": "B04" if not failures else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
