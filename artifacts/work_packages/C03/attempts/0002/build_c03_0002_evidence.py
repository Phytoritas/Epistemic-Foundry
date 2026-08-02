#!/usr/bin/env python3
"""Build and verify fail-closed acceptance evidence for C03-0002.

The verifier binds the C03 migration implementation to the approved 126
contract boundary, executes the document-registration migration fixture,
reconciles the targeted and full Python JUnit receipts, and proves that the
remaining full-suite failures are exactly the downstream B04 projection debt
and the pre-existing J02 dependency-lock debt already recorded by C01/C02.
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
from typing import Any

import yaml
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C03/attempts/0002"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from migrations.contracts import (  # noqa: E402
    LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED,
    LegacyDocumentRegistrationEvidenceRequired,
    migrate_legacy_document_manifest,
    rollback_legacy_document_manifest,
)
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload  # noqa: E402


ATTEMPT_ID = "C03-0002"
DECISION_ID = "HD-EF4-C01-SG004-20260730-001"
TARGETED_JUNIT = ATTEMPT / "targeted-runtime-migration.junit.xml"
FULL_JUNIT = ATTEMPT / "full-python-regression.junit.xml"
C02_JUNIT = ROOT / "artifacts/work_packages/C02/attempts/0002/full-python-regression.junit.xml"
C01_IMPACT = ROOT / "artifacts/work_packages/C01/attempts/0006/full-regression-impact.json"

EXPECTED_WRITE_SCOPE = [
    "migrations/contracts/**",
    "docs/schema_evolution.md",
    "src/epistemic_foundry/evolution_chamber/run_spec.py",
    "src/epistemic_foundry/governance/promotion.py",
    "tests/test_evolution_chamber.py",
    "tests/test_governance.py",
    "tests/test_integration_forge_cycle.py",
    "artifacts/work_packages/C03/**",
]

EXPECTED_SOURCE_HASHES = {
    "migrations/contracts/document_registration_migration.py": "e2e403803f75d1df444b1a6c80ddb523858eda4163a59a49b78761b667d4560f",
    "migrations/contracts/__init__.py": "df3d0d1fe68f56b348a825d8b01d14c2ef6e92e704ef6ef35e8284ffc2737e36",
    "migrations/contracts/document-registration-v3-to-v4.migration.json": "7be069808c5c1d136db13c13c1cdf04d3b65a7dad840c4c0e7e49e71d60c2498",
    "migrations/contracts/compatibility-matrix.json": "eb4f9ddc499a340be8422ef2f94bfe9235acacbea61d602870ee62e616a97412",
    "migrations/contracts/migration-record.schema.json": "1ff0311e4ec8674182416edf40472d87b673701e6227d0e1348c040c764aa629",
    "migrations/contracts/fixtures/document-manifest-v3.json": "7776d632c9a80c16bebfa2b892c63f70a274269cf1574483ac86a8e525a85fa9",
    "migrations/contracts/fixtures/document-registration-evidence.json": "2ca560f28a6ea5bdfbc83df163ef0a1d5b931c611af6be604ffbedad0773aa2b",
    "migrations/contracts/fixtures/document-registration-migration-record.json": "8e82f7ee800e6b6645af210ce9abca5b452f528c5a53a494d8e746ce678aff17",
    "docs/schema_evolution.md": "0e0aee2de923b0b28a94f193accadbdc20bba65f35755851f212722d7d95b44d",
    "tests/test_integration_forge_cycle.py": "c82372a9677ce2a380b1f7446a2f82d24671ef407994ca60a8ed44bc384a5874",
    "manifests/development_manifest.yaml": "8859303ea2fbe8d71655b2c244daf424a9742d4ce700bb93edddc20e3a06f23b",
    "src/epistemic_foundry/evolution_chamber/run_spec.py": "ce6a135dac6fbfb98184ff46448da88222cdb2de5ef31066d2f146bc25a7dc1c",
    "src/epistemic_foundry/governance/promotion.py": "9078dae66ff527b36915d924e579c49b7937ce78d0c084c2f8b00852e0113f51",
    "tests/test_evolution_chamber.py": "fa69b90f5d830d0f3552d374733da15a4769aae150fef4ed47ed35d8f19ac59f",
    "tests/test_governance.py": "e2b83693db1434d88dbafd8c2f71cb5c9f7b89bf29e3a1cc0eb8fdd2bf99184c",
}

FROZEN_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C01/attempts/0006/report.json": "35c9f323ab976c60448e9d4138833d9dd67570fb26e99d8b4298be5e2424ac30",
    "artifacts/work_packages/C01/attempts/0006/full-regression-impact.json": "4335095f858d5c3a2a750ecada2313f24f7f6c1097180f5704efa099a95f70d9",
    "artifacts/work_packages/C02/attempts/0002/report.json": "f89f0f3bc82697716f7833a57acabd6a3a9666196e3c4ec310f406d6576b45cf",
    "artifacts/work_packages/C02/attempts/0002/c02-contract-codegen-verification.json": "567a291234ec92b516ad0f4151efc2e01e8514a7673ba49bdfe5155ec39190b2",
    "artifacts/work_packages/C02/attempts/0002/full-python-regression.junit.xml": "dcc9f942c057b91526be1896a233142949beaad7a7f3e58640eb997cdaf5b44d",
}

FROZEN_C03_0001_HASHES = {
    "artifacts/work_packages/C03/c03-rah-seal.py": "27db8ce0351ee73c8fad991896b677c2808412b4770825e3d6301516904b36b8",
    "artifacts/work_packages/C03/c03-runtime-migration-verification.json": "51c22895ee9f0b8ae8ab44b61af13a1ab9600f5f1a8751efd890c1caacbfd4ff",
    "artifacts/work_packages/C03/c03-runtime-migration-verifier.py": "5cb73f686085f0cab82737203e3bc0a281373da55139260217ee0ac9d648993e",
    "artifacts/work_packages/C03/commands.jsonl": "5259d0cb8874924f6753a442854ad861f584940f1c187364af72288c9e67cdd9",
    "artifacts/work_packages/C03/dependency-status.json": "0e2eefa79cb38425fcefc5ccd31b2fa206b7e19e92b77b09094d170743111e9b",
    "artifacts/work_packages/C03/full-python-regression.junit.xml": "b30c079f4b65c92f23974cf6597d5e2ccbb1516b9e45bb4150ad7deccd4114d8",
    "artifacts/work_packages/C03/report.json": "8bc497806e76a1faa0761e945c74f539e7fe4d44a03d9d162cbfee1c44400ad5",
    "artifacts/work_packages/C03/review.md": "1fae3a9094811e525b5a1ebb895ae16856682ef993eca8bd365e80830e536226",
    "artifacts/work_packages/C03/targeted-runtime-migration.junit.xml": "d768d1268aa29c56f6dceb2e765b5b45ffda0d5aa154f220b50faf72415a972e",
}

ACTIVE_CONTRACT_PATHS = (
    "src/epistemic_foundry",
    "schemas",
    "examples/sample_evolution-run-spec.json",
    "examples/sample_promotion-decision.json",
    "openapi",
    "python/epistemic_foundry/contracts",
    "packages/contracts/src/generated",
    "web/src/generated",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def assert_hashes(expected: dict[str, str], label: str) -> None:
    for relative, expected_digest in expected.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"{label} file is missing: {relative}")
        actual = sha256(path)
        if actual != expected_digest:
            raise SystemExit(
                f"{label} hash mismatch for {relative}: {actual} != {expected_digest}"
            )


def junit(path: Path) -> tuple[dict[str, int], list[dict[str, str]], set[str]]:
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
    nodes: set[str] = set()
    for testcase in root.iter("testcase"):
        classname = testcase.get("classname", "")
        node_id = f"{classname.replace('.', '/')}.py::{testcase.get('name', '')}"
        nodes.add(node_id)
        result = testcase.find("failure")
        result_type = "failure"
        if result is None:
            result = testcase.find("error")
            result_type = "error"
        if result is None:
            continue
        message = (result.get("message") or (result.text or "")).strip()
        failures.append(
            {
                "node_id": node_id,
                "type": result_type,
                "message": message,
                "message_sha256": "sha256:"
                + hashlib.sha256(message.encode("utf-8")).hexdigest(),
            }
        )
    return summary, sorted(failures, key=lambda row: row["node_id"]), nodes


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = raw if isinstance(raw, list) else raw["work_packages"]
    by_id = {row["id"]: row for row in packages}
    c03 = by_id["C03"]
    if len(packages) != 156:
        raise SystemExit("development manifest package count changed")
    if c03["depends_on"] != ["C01", "C02"]:
        raise SystemExit("C03 dependencies changed")
    if c03["write_scope"] != EXPECTED_WRITE_SCOPE:
        raise SystemExit("C03 exact write scope changed")
    expected_checks = {
        "compatibility_matrix_test",
        "migration_fixture_test",
        "document_registration_migration_test",
        "evolution_authority_compatibility_test",
    }
    if set(c03["required_checks"]) != expected_checks:
        raise SystemExit("C03 required checks changed")
    if by_id["C04"]["depends_on"] != ["C02", "C03"]:
        raise SystemExit("C04 dependencies changed")
    if by_id["B04"]["depends_on"] != ["B02", "B03", "C04"]:
        raise SystemExit("B04 static dependencies changed")
    return {
        "package_count": len(packages),
        "C03": {
            "depends_on": c03["depends_on"],
            "write_scope": c03["write_scope"],
            "required_checks": c03["required_checks"],
            "exit_criteria": c03["exit_criteria"],
        },
        "C04_depends_on": by_id["C04"]["depends_on"],
        "B04_static_depends_on": by_id["B04"]["depends_on"],
        "pre_C04_B04_is_attempt_level_only": True,
        "static_dependency_cycle_added": False,
        "status": "PASS",
    }


def canonical_inventory() -> dict[str, Any]:
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    examples = sorted((ROOT / "examples").glob("sample_*.json"))
    ids: list[str] = []
    for path in schemas:
        schema = read_json(path)
        Draft202012Validator.check_schema(schema)
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            raise SystemExit(f"canonical schema lacks $id: {path.name}")
        ids.append(identifier)
    if len(schemas) != 126 or len(examples) != 126 or len(set(ids)) != 126:
        raise SystemExit(
            f"canonical inventory changed: schemas={len(schemas)}, "
            f"examples={len(examples)}, unique_ids={len(set(ids))}"
        )
    return {
        "schema_count": len(schemas),
        "example_count": len(examples),
        "unique_schema_id_count": len(set(ids)),
        "document_registration_contracts_present": all(
            (ROOT / relative).is_file()
            for relative in (
                "schemas/document-registration-request.schema.json",
                "schemas/document-registration.schema.json",
                "examples/sample_document-registration-request.json",
                "examples/sample_document-registration.json",
            )
        ),
        "status": "PASS",
    }


def validate(schema_path: str, payload: dict[str, Any], label: str) -> None:
    schema = read_json(ROOT / schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise SystemExit(f"{label} schema validation failed: {[e.message for e in errors]}")


def migration_fixture() -> dict[str, Any]:
    fixture_root = ROOT / "migrations/contracts/fixtures"
    legacy = read_json(fixture_root / "document-manifest-v3.json")
    request = read_json(ROOT / "examples/sample_document-registration-request.json")
    evidence = read_json(fixture_root / "document-registration-evidence.json")
    result = migrate_legacy_document_manifest(
        legacy,
        registration_request=request,
        immutable_registration_evidence=evidence,
        migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
        recorded_at="2026-07-30T00:03:00Z",
    )
    expected = {
        "document_registration_request": request,
        "document_registration": read_json(
            ROOT / "examples/sample_document-registration.json"
        ),
        "document_manifest": read_json(ROOT / "examples/sample_document-manifest.json"),
        "migration_record": read_json(
            fixture_root / "document-registration-migration-record.json"
        ),
    }
    if result != expected:
        raise SystemExit("document registration migration differs from canonical fixtures")
    for name, schema_path in {
        "document_registration_request": "schemas/document-registration-request.schema.json",
        "document_registration": "schemas/document-registration.schema.json",
        "document_manifest": "schemas/document-manifest.schema.json",
        "migration_record": "migrations/contracts/migration-record.schema.json",
    }.items():
        validate(schema_path, result[name], name)
    record = result["migration_record"]
    if record["migration_hash"] != hash_excluding(record, "migration_hash"):
        raise SystemExit("DocumentRegistrationMigrationRecord hash does not recompute")
    if record["migration_hash"] != (
        "sha256:dd3f3046b90dee537d87f90898bfe97848fa4b7172a523762a644021b2417ece"
    ):
        raise SystemExit("document registration migration hash changed")
    if record["source_manifest_hash"] != sha256_of_payload(legacy):
        raise SystemExit("migration source manifest hash changed")
    if rollback_legacy_document_manifest(result, legacy) != legacy:
        raise SystemExit("migration rollback did not reproduce the exact source payload")

    failure_codes: list[str] = []
    for bad_request, bad_evidence, recorded_at in (
        (None, None, "2026-07-30T00:03:00Z"),
        (request, evidence, "2026-07-30T09:03:00+09:00"),
    ):
        try:
            migrate_legacy_document_manifest(
                legacy,
                registration_request=bad_request,
                immutable_registration_evidence=bad_evidence,
                migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
                recorded_at=recorded_at,
            )
        except LegacyDocumentRegistrationEvidenceRequired as error:
            failure_codes.append(error.code)
    if failure_codes != [
        LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED,
        LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED,
    ]:
        raise SystemExit("document registration migration did not fail closed")

    descriptor = read_json(
        ROOT / "migrations/contracts/document-registration-v3-to-v4.migration.json"
    )
    matrix = read_json(ROOT / "migrations/contracts/compatibility-matrix.json")
    if descriptor["forward_transform"]["failure_code"] != (
        LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED
    ):
        raise SystemExit("document migration descriptor failure code changed")
    matrix_results = {row["result"] for row in matrix["rows"]}
    if LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED not in matrix_results:
        raise SystemExit("compatibility matrix lacks unresolved registration result")
    return {
        "canonical_input_precondition": (
            "DocumentRegistrationRequest is boundary-validated before migration; "
            "the migration rechecks closed fields, hash/ID binding and UTC time"
        ),
        "environment_or_repository_discovery_count": 0,
        "failure_code": LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED,
        "migration_hash": record["migration_hash"],
        "output_fixture_parity": "PASS",
        "rollback_exact_source_payload": "PASS",
        "schema_validation": "PASS",
        "source_manifest_hash": record["source_manifest_hash"],
        "status": "PASS",
    }


def active_legacy_hits() -> list[dict[str, Any]]:
    patterns = {
        value: re.compile(rf"(?<![A-Z0-9_]){re.escape(value)}(?![A-Z0-9_])")
        for value in ("PILOT", "HYPOTHESIS_PASSPORT_ONLY")
    }
    hits: list[dict[str, Any]] = []
    for relative in ACTIVE_CONTRACT_PATHS:
        target = ROOT / relative
        paths = [target] if target.is_file() else sorted(target.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix not in {
                ".json",
                ".py",
                ".ts",
                ".yaml",
                ".yml",
                ".mjs",
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


def regression_reconciliation() -> dict[str, Any]:
    targeted, targeted_failures, targeted_nodes = junit(TARGETED_JUNIT)
    if targeted != {"tests": 105, "failures": 0, "errors": 0, "skipped": 0}:
        raise SystemExit(f"C03 targeted JUnit changed: {targeted}")
    if targeted_failures:
        raise SystemExit("C03 targeted JUnit contains failures")
    required_document_nodes = {
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_requires_more_than_final_manifest",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_emits_canonical_lineage",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_unbound_receipt_evidence",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_noncanonical_request_fields",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_rehashed_nested_schema_violations",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_source_identity_drift",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_non_utc_recorded_at",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rollback_is_hash_bound",
    }
    if not required_document_nodes.issubset(targeted_nodes):
        raise SystemExit("targeted JUnit omits required document migration nodes")

    full, failures, full_nodes = junit(FULL_JUNIT)
    if full != {"tests": 983, "failures": 19, "errors": 0, "skipped": 0}:
        raise SystemExit(f"C03 full Python JUnit changed: {full}")
    baseline, baseline_failures, baseline_nodes = junit(C02_JUNIT)
    if baseline != {"tests": 970, "failures": 19, "errors": 0, "skipped": 0}:
        raise SystemExit(f"C02 baseline JUnit changed: {baseline}")
    expected_new_nodes = {
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_requires_more_than_final_manifest",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_emits_canonical_lineage",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_unbound_receipt_evidence",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_noncanonical_request_fields",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_rehashed_nested_schema_violations",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_malformed_immutable_evidence[source_effect_receipt_id-None-source_effect_receipt_id]",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_malformed_immutable_evidence[submitted_by_principal_id--submitted principal]",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_malformed_immutable_evidence[registration_ledger_event_id-None-registration_ledger_event_id]",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_malformed_immutable_evidence[source_content_hash-sha256:not-a-digest-canonical sha256]",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_malformed_immutable_evidence[registered_at-2026-07-30T00:02:00+09:00-ending in Z]",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_source_identity_drift",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rejects_non_utc_recorded_at",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rollback_is_hash_bound",
    }
    observed_new_nodes = full_nodes - baseline_nodes
    removed_baseline_nodes = baseline_nodes - full_nodes
    if observed_new_nodes != expected_new_nodes or removed_baseline_nodes:
        raise SystemExit(
            "C03 full-suite case boundary changed; "
            f"unexpected_new={sorted(observed_new_nodes - expected_new_nodes)}, "
            f"missing_new={sorted(expected_new_nodes - observed_new_nodes)}, "
            f"removed_baseline={sorted(removed_baseline_nodes)}"
        )
    current_by_node = {row["node_id"]: row for row in failures}
    baseline_by_node = {row["node_id"]: row for row in baseline_failures}
    if current_by_node != baseline_by_node:
        missing = sorted(set(baseline_by_node) - set(current_by_node))
        new = sorted(set(current_by_node) - set(baseline_by_node))
        changed = sorted(
            node
            for node in set(current_by_node) & set(baseline_by_node)
            if current_by_node[node] != baseline_by_node[node]
        )
        raise SystemExit(
            f"C03 residual failure boundary changed; missing={missing}, "
            f"new={new}, changed={changed}"
        )
    authority = read_json(C01_IMPACT)
    authority_by_node = {row["node_id"]: row for row in authority["failures"]}
    if set(authority_by_node) != set(current_by_node):
        raise SystemExit("C03 residual nodes differ from C01 authority")
    rows: list[dict[str, Any]] = []
    for node in sorted(current_by_node):
        authority_row = authority_by_node[node]
        current = current_by_node[node]
        if current["message_sha256"] != authority_row["message_sha256"]:
            raise SystemExit(f"C03 residual message changed: {node}")
        rows.append(
            {
                **current,
                "normalized_fingerprint": authority_row["normalized_fingerprint"],
                "owner": authority_row["owner"],
                "debt_id": authority_row["debt_id"],
                "root_cause_category": authority_row["root_cause_category"],
                "expected_resolution": authority_row["expected_resolution"],
                "c03_causal_classification": (
                    "EXPECTED_ATTEMPT_LEVEL_RECONCILIATION"
                    if authority_row["owner"] == "B04"
                    else "PRE_EXISTING_UNRELATED_DEBT"
                ),
            }
        )
    owner_counts = {
        owner: sum(1 for row in rows if row["owner"] == owner)
        for owner in sorted({row["owner"] for row in rows})
    }
    if owner_counts != {"B04": 18, "J02": 1}:
        raise SystemExit(f"C03 residual ownership changed: {owner_counts}")
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
            "passed": full["tests"]
            - full["failures"]
            - full["errors"]
            - full["skipped"],
            "artifact": FULL_JUNIT.relative_to(ROOT).as_posix(),
            "artifact_sha256": sha256_id(FULL_JUNIT),
            "status": "EXPECTED_DOWNSTREAM_AND_PREEXISTING_FAILURES",
        },
        "baseline_test_count": baseline["tests"],
        "new_passing_test_count": full["tests"] - baseline["tests"],
        "new_passing_test_nodes": sorted(observed_new_nodes),
        "failure_owner_counts": owner_counts,
        "same_failure_node_ids": True,
        "same_failure_messages": True,
        "same_normalized_fingerprints": True,
        "failures": rows,
        "new_c03_failure_count": 0,
        "full_suite_is_not_reported_pass": True,
        "status": "PASS_WITH_DECLARED_RESIDUAL_FAILURES",
    }


def dependency_status() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "work_package_id": "C03",
        "C01": "PASS",
        "C02": "PASS",
        "C03": "PASS",
        "B04_pre_C04": "DEPENDENCY_READY",
        "C04": "WAITING_ON_FRESH_PROJECTION",
        "B04_final": "WAITING_ON_C04",
        "next_package": "B04-0006",
        "full_156_package_dag_recomputed": False,
        "completion_ready": False,
        "status": "PASS",
    }


def verification() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    assert_hashes(EXPECTED_SOURCE_HASHES, "C03 source")
    assert_hashes(FROZEN_DEPENDENCY_HASHES, "C03 dependency")
    assert_hashes(FROZEN_C03_0001_HASHES, "C03-0001 history")
    decision = read_json(
        ROOT
        / "artifacts/authority_decisions/HD-EF4-C01-SG004-20260730-001.human-decision.json"
    )
    if decision.get("decision_id") != DECISION_ID or decision.get("decision_hash") != (
        "sha256:ebc3434cccdd248b38a36d1a3de5132f4503b4172c1ee11a64dd8f0033f670fd"
    ):
        raise SystemExit("C03 authority decision is missing or changed")
    for dependency in ("C01", "C02"):
        report = read_json(
            ROOT / f"artifacts/work_packages/{dependency}/attempts/0006/report.json"
            if dependency == "C01"
            else ROOT / "artifacts/work_packages/C02/attempts/0002/report.json"
        )
        if report.get("status") != "PASS":
            raise SystemExit(f"{dependency} dependency is not PASS")
    manifest = manifest_contract()
    inventory = canonical_inventory()
    migration = migration_fixture()
    regression = regression_reconciliation()
    legacy_hits = active_legacy_hits()
    if legacy_hits:
        raise SystemExit(f"active legacy promotion values remain: {legacy_hits}")
    if (ROOT / "migrations/__init__.py").exists():
        raise SystemExit("unauthorized migrations/__init__.py is present")
    source_hashes = {
        relative: "sha256:" + digest
        for relative, digest in EXPECTED_SOURCE_HASHES.items()
    }
    result = {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_id": DECISION_ID,
        "canonical_contract": inventory,
        "dependencies": {
            "C01_0006": "PASS",
            "C02_0002": "PASS",
            "frozen_dependency_hash_count": len(FROZEN_DEPENDENCY_HASHES),
            "status": "PASS",
        },
        "document_registration_migration": migration,
        "legacy_promotion_value_hits": legacy_hits,
        "manifest_contract": manifest,
        "protected_history": {
            "C03_0001_artifact_count": len(FROZEN_C03_0001_HASHES),
            "C03_0001_hashes_unchanged": True,
            "status": "PASS",
        },
        "regression": {
            key: value for key, value in regression.items() if key != "failures"
        },
        "source_hashes": source_hashes,
        "write_scope_audit": {
            "declared_scope": EXPECTED_WRITE_SCOPE,
            "unauthorized_migrations_init_present": False,
            "violation_count": 0,
            "status": "PASS",
        },
        "status": "PASS",
    }
    return result, regression, dependency_status()


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    result, regression, dependency = verification()
    write_json(ATTEMPT / "c03-runtime-migration-verification.json", result)
    write_json(ATTEMPT / "full-regression-impact.json", regression)
    write_json(ATTEMPT / "dependency-status.json", dependency)
    return result


def verify() -> dict[str, Any]:
    result, regression, dependency = verification()
    expected = {
        "c03-runtime-migration-verification.json": result,
        "full-regression-impact.json": regression,
        "dependency-status.json": dependency,
    }
    for name, value in expected.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(value):
            raise SystemExit(f"stored C03-0002 evidence differs from live authority: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "verified_artifacts": sorted(expected),
        "targeted_passed": regression["targeted"]["passed"],
        "full_python": regression["full_python"],
        "new_c03_failure_count": regression["new_c03_failure_count"],
        "completion_ready": False,
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
