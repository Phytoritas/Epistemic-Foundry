#!/usr/bin/env python3
"""Fail-closed acceptance verifier for work package C03.

The verifier reconciles the C01 migration-debt authority, the C03 JUnit
receipts, the executable migration fixtures, frozen C01/C02 evidence, and the
manifest ownership boundary.  It emits a machine-readable result even on a
contract failure, then exits non-zero so a narrative report cannot hide it.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "C03"
sys.path.insert(0, str(ROOT / "src"))

from epistemic_foundry.domain.hashing import (  # noqa: E402
    hash_excluding,
    sha256_of_payload,
)
from epistemic_foundry.evolution_chamber.run_spec import (  # noqa: E402
    LEGACY_RUN_SPEC_RESOLUTION_REQUIRED,
    LegacyRunSpecResolutionRequired,
    build_evolution_run_spec,
    migrate_legacy_evolution_run_spec,
    rollback_legacy_evolution_run_spec,
)
from epistemic_foundry.governance.promotion import (  # noqa: E402
    LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED,
    LegacyPromotionLevelReviewRequired,
    migrate_legacy_promotion_level,
)


FROZEN_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C01/attempts/0004/runtime-migration-impact.json": (
        "3c35cc5cfe003055f2e039a4837e74527a843c4ed6795eee1d28b56954d36877"
    ),
    "artifacts/work_packages/C01/attempts/0004/report.json": (
        "424f40396e93bd6826bf5ad85c3580cac7bd4ea8171b93f24816bc6a78c4a5d6"
    ),
    "artifacts/work_packages/C02/c02-contract-codegen-verification.json": (
        "df55f11d6c3650868c67f73a1d67b0d586598bba10c4740888815255fbb516bf"
    ),
    "artifacts/work_packages/C02/full-python-regression.junit.xml": (
        "13ca652d4efad7ff290781a42834d9b61a0cb82a8f81fece852c356beea6f5bc"
    ),
    "artifacts/work_packages/C02/report.json": (
        "2f9a92ead5a97ecc47d2a70d2101bb4a302a6868710621511869c6e6f202d2e1"
    ),
}

C03_SOURCE_PATHS = (
    "docs/schema_evolution.md",
    "src/epistemic_foundry/evolution_chamber/run_spec.py",
    "src/epistemic_foundry/governance/promotion.py",
    "tests/test_evolution_chamber.py",
    "tests/test_governance.py",
    "tests/test_integration_forge_cycle.py",
)

EXPECTED_WRITE_SCOPE = (
    "migrations/contracts/**",
    "docs/schema_evolution.md",
    "src/epistemic_foundry/evolution_chamber/run_spec.py",
    "src/epistemic_foundry/governance/promotion.py",
    "tests/test_evolution_chamber.py",
    "tests/test_governance.py",
    "tests/test_integration_forge_cycle.py",
    "artifacts/work_packages/C03/**",
)

REQUIRED_TEST_NODES = (
    "tests/test_evolution_chamber.py::test_missing_resolved_refs_is_rejected_at_the_write_boundary",
    "tests/test_evolution_chamber.py::test_floating_reference_is_rejected",
    "tests/test_evolution_chamber.py::test_unversioned_provider_alias_is_rejected",
    "tests/test_evolution_chamber.py::test_unresolvable_legacy_spec_fails_closed",
    "tests/test_evolution_chamber.py::test_migration_fixture_executes_forward_transform_and_exact_rollback",
    "tests/test_governance.py::test_partial_cascade_is_conditional_not_promotion",
    "tests/test_governance.py::test_non_granting_decisions_require_null[REJECT-overrides0]",
    "tests/test_governance.py::test_non_granting_decisions_require_null[UNDERDETERMINED-overrides1]",
    "tests/test_governance.py::test_non_granting_decisions_require_null[BLOCKED-overrides2]",
    "tests/test_governance.py::test_legacy_level_migration_requires_record_specific_review",
    "tests/test_governance.py::test_gate_decisions_are_structured_hash_bound_and_complete",
    "tests/test_integration_forge_cycle.py::test_promotion_accepts_canonical_generated_gate_decisions",
    "tests/test_integration_forge_cycle.py::test_crash_before_effect_receipt_does_not_promote",
    "tests/test_integration_forge_cycle.py::test_blocked_decision_with_receipt_preserves_candidate_state",
)

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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_node_id(testcase: ET.Element) -> str:
    classname = testcase.attrib["classname"]
    module = classname.replace(".", "/")
    return f"{module}.py::{testcase.attrib['name']}"


def parse_junit(path: Path) -> tuple[dict[str, Any], set[str]]:
    root = ET.parse(path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        raise ValueError(f"{path} has no testsuite")
    tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    nodes = {canonical_node_id(case) for case in suite.findall("testcase")}
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
    )


def active_legacy_hits() -> list[dict[str, Any]]:
    patterns = {
        value: re.compile(rf"(?<![A-Z0-9_]){re.escape(value)}(?![A-Z0-9_])")
        for value in ("PILOT", "HYPOTHESIS_PASSPORT_ONLY")
    }
    hits: list[dict[str, Any]] = []
    for relative in ACTIVE_CONTRACT_PATHS:
        target = ROOT / relative
        files = [target] if target.is_file() else sorted(target.rglob("*"))
        for path in files:
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


def fixture_verification() -> dict[str, Any]:
    fixture_root = ROOT / "migrations" / "contracts" / "fixtures"
    legacy = json.loads(
        (fixture_root / "evolution-run-spec-v3.json").read_text(encoding="utf-8")
    )
    resolution = json.loads(
        (fixture_root / "evolution-run-spec-resolution.json").read_text(
            encoding="utf-8"
        )
    )
    expected_record = json.loads(
        (fixture_root / "evolution-run-spec-migration-record.json").read_text(
            encoding="utf-8"
        )
    )
    sample = json.loads(
        (ROOT / "examples" / "sample_evolution-run-spec.json").read_text(
            encoding="utf-8"
        )
    )
    result = migrate_legacy_evolution_run_spec(
        legacy,
        resolved_refs=sample["resolved_refs"],
        external_backend_enabled=resolution["external_backend_enabled"],
        resolution_evidence_artifact_ids=resolution[
            "resolution_evidence_artifact_ids"
        ],
        target_evolution_run_id=resolution["target_evolution_run_id"],
        migration_id=resolution["migration_id"],
        recorded_at=resolution["recorded_at"],
    )
    record = result["migration_record"]
    migrated = result["evolution_run_spec"]
    schema = json.loads(
        (ROOT / "migrations" / "contracts" / "migration-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    record_errors = [
        error.message
        for error in Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).iter_errors(record)
    ]
    if record_errors:
        raise ValueError(f"EvolutionRunSpec MigrationRecord invalid: {record_errors}")
    if sha256_of_payload(legacy) != resolution["expected_source_artifact_hash"]:
        raise ValueError("legacy source fixture hash mismatch")
    if migrated["spec_hash"] != resolution["expected_target_spec_hash"]:
        raise ValueError("migrated EvolutionRunSpec hash mismatch")
    if record["migration_hash"] != resolution["expected_migration_hash"]:
        raise ValueError("EvolutionRunSpec MigrationRecord hash mismatch")
    if record != expected_record:
        raise ValueError("generated MigrationRecord differs from canonical fixture")
    if rollback_legacy_evolution_run_spec(result, legacy) != legacy:
        raise ValueError("exact rollback did not reproduce the source fixture")

    unresolved_code = None
    try:
        migrate_legacy_evolution_run_spec(
            legacy,
            resolved_refs=None,
            external_backend_enabled=False,
            resolution_evidence_artifact_ids=("ART-RESOLUTION-1",),
            target_evolution_run_id="ER-UNRESOLVED-V4",
        )
    except LegacyRunSpecResolutionRequired as exc:
        unresolved_code = exc.code
    if unresolved_code != LEGACY_RUN_SPEC_RESOLUTION_REQUIRED:
        raise ValueError("unresolvable legacy run spec did not fail closed")

    promotion_record = json.loads(
        (fixture_root / "promotion-level-review.json").read_text(encoding="utf-8")
    )
    promotion_errors = [
        error.message
        for error in Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).iter_errors(promotion_record)
    ]
    if promotion_errors:
        raise ValueError(f"PromotionLevel MigrationRecord invalid: {promotion_errors}")
    migrated_level = migrate_legacy_promotion_level(
        promotion_record["source_level"], migration_record=promotion_record
    )
    legacy_review_code = None
    try:
        migrate_legacy_promotion_level("PILOT")
    except LegacyPromotionLevelReviewRequired as exc:
        legacy_review_code = exc.code
    if legacy_review_code != LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED:
        raise ValueError("unreviewed legacy promotion level did not fail closed")

    return {
        "status": "PASS",
        "evolution_run_spec": {
            "source_artifact_hash": resolution["expected_source_artifact_hash"],
            "target_spec_hash": resolution["expected_target_spec_hash"],
            "migration_hash": resolution["expected_migration_hash"],
            "record_schema_valid": True,
            "exact_rollback": True,
            "unresolved_failure_code": unresolved_code,
        },
        "promotion_level": {
            "source_level": promotion_record["source_level"],
            "target_level": migrated_level,
            "migration_hash": promotion_record["migration_hash"],
            "record_schema_valid": True,
            "unreviewed_failure_code": legacy_review_code,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "c03-runtime-migration-verification.json",
    )
    args = parser.parse_args()
    failures: list[str] = []

    manifest = yaml.safe_load(
        (ROOT / "manifests" / "development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = {entry["id"]: entry for entry in manifest["work_packages"]}
    c03 = packages["C03"]
    manifest_check = {
        "dependencies": c03["depends_on"],
        "write_scope": c03["write_scope"],
        "required_checks": c03["required_checks"],
    }
    if tuple(c03["depends_on"]) != ("C01", "C02"):
        failures.append("C03 dependencies are not exactly C01 and C02")
    if tuple(c03["write_scope"]) != EXPECTED_WRITE_SCOPE:
        failures.append("C03 write_scope differs from the authoritative bounded scope")
    if tuple(c03["required_checks"]) != (
        "compatibility_matrix_test",
        "migration_fixture_test",
    ):
        failures.append("C03 required checks changed")

    frozen_hashes: dict[str, str] = {}
    for relative, expected in FROZEN_DEPENDENCY_HASHES.items():
        actual = sha256(ROOT / relative)
        frozen_hashes[relative] = f"sha256:{actual}"
        if actual != expected:
            failures.append(f"frozen dependency hash mismatch: {relative}")

    targeted, targeted_nodes = parse_junit(
        PACKAGE / "targeted-runtime-migration.junit.xml"
    )
    full, full_nodes = parse_junit(PACKAGE / "full-python-regression.junit.xml")
    if targeted != {
        **targeted,
        "tests": 92,
        "passed": 92,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }:
        failures.append("targeted runtime migration JUnit is not 92/92 PASS")
    if full["tests"] < 824 or any(
        full[field] != 0 for field in ("failures", "errors", "skipped")
    ):
        failures.append("full Python JUnit is not zero-failure/zero-skip")

    impact = json.loads(
        (
            ROOT
            / "artifacts"
            / "work_packages"
            / "C01"
            / "attempts"
            / "0004"
            / "runtime-migration-impact.json"
        ).read_text(encoding="utf-8")
    )
    debt_nodes = [entry["pytest_node_id"] for entry in impact["failures"]]
    missing_debt_nodes = sorted(set(debt_nodes) - full_nodes)
    if len(debt_nodes) != 24 or missing_debt_nodes:
        failures.append("C01 migration debt does not reconcile 24/24 to passing nodes")
    missing_required_tests = sorted(set(REQUIRED_TEST_NODES) - targeted_nodes)
    if missing_required_tests:
        failures.append("targeted JUnit is missing required C03 tests")

    try:
        fixture_result = fixture_verification()
    except Exception as exc:  # fail-closed evidence capture
        fixture_result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        failures.append("executable migration fixture verification failed")

    signature = inspect.signature(build_evolution_run_spec)
    resolved_refs_required = (
        signature.parameters["resolved_refs"].default is inspect.Parameter.empty
    )
    if not resolved_refs_required:
        failures.append("build_evolution_run_spec resolved_refs has a default")

    legacy_hits = active_legacy_hits()
    if legacy_hits:
        failures.append("active canonical/runtime artifacts contain legacy promotion values")

    skip_pattern = re.compile(r"pytest\.(?:mark\.(?:xfail|skip)|skip\s*\()")
    suppression_hits = []
    for relative in C03_SOURCE_PATHS[3:]:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if skip_pattern.search(text):
            suppression_hits.append(relative)
    if suppression_hits:
        failures.append("C03 tests contain xfail/skip suppression")

    compatibility = json.loads(
        (ROOT / "migrations" / "contracts" / "compatibility-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    if compatibility["compatibility_window"].get("silent_fallback") is not False:
        failures.append("compatibility matrix permits silent fallback")
    if compatibility["rollback"].get("exact_source_hash_required") is not True:
        failures.append("compatibility matrix does not require hash-bound rollback")
    if compatibility["backfill"].get("partial_success_is_not_batch_success") is not True:
        failures.append("compatibility matrix permits partial batch success")

    source_hashes = {
        relative: f"sha256:{sha256(ROOT / relative)}" for relative in C03_SOURCE_PATHS
    }
    migration_hashes = {
        path.relative_to(ROOT).as_posix(): f"sha256:{sha256(path)}"
        for path in sorted((ROOT / "migrations" / "contracts").rglob("*"))
        if path.is_file()
    }
    result = {
        "work_package_id": "C03",
        "attempt_id": "C03-0001",
        "authority_decision_id": "HD-EF4-C01-SG003-20260728-001",
        "check": "c03_runtime_migration_verification",
        "status": "PASS" if not failures else "FAIL",
        "manifest": manifest_check,
        "frozen_dependencies": {
            "status": "PASS"
            if not any("frozen dependency" in item for item in failures)
            else "FAIL",
            "hashes": frozen_hashes,
        },
        "targeted_runtime_migration": targeted,
        "full_python_suite": full,
        "migration_debt_reconciliation": {
            "status": "PASS" if not missing_debt_nodes and len(debt_nodes) == 24 else "FAIL",
            "authority_failure_count": len(debt_nodes),
            "passing_node_count": len(set(debt_nodes) & full_nodes),
            "missing_node_ids": missing_debt_nodes,
            "authority_artifact": "artifacts/work_packages/C01/attempts/0004/runtime-migration-impact.json",
        },
        "required_test_reconciliation": {
            "status": "PASS" if not missing_required_tests else "FAIL",
            "required_count": len(REQUIRED_TEST_NODES),
            "present_count": len(set(REQUIRED_TEST_NODES) & targeted_nodes),
            "missing_node_ids": missing_required_tests,
        },
        "migration_fixtures": fixture_result,
        "strict_runtime": {
            "resolved_refs_required_without_default": resolved_refs_required,
            "active_legacy_promotion_value_hits": legacy_hits,
            "xfail_or_skip_suppression_hits": suppression_hits,
        },
        "compatibility_matrix": {
            "status": "PASS"
            if compatibility["compatibility_window"].get("silent_fallback") is False
            and compatibility["rollback"].get("exact_source_hash_required") is True
            and compatibility["backfill"].get("partial_success_is_not_batch_success") is True
            else "FAIL",
            "read_window": compatibility["compatibility_window"]["read_window"],
            "write_window": compatibility["compatibility_window"]["write_window"],
            "silent_fallback": compatibility["compatibility_window"]["silent_fallback"],
            "rollback": compatibility["rollback"],
            "backfill": compatibility["backfill"],
        },
        "source_hashes": source_hashes,
        "migration_artifact_hashes": migration_hashes,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
