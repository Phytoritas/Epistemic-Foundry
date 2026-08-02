#!/usr/bin/env python3
"""Verify the C01-0003 implementation boundary and C01-SG003.

This verifier deliberately does not modify runtime producers or their tests.
It proves four facts together:

1. the authorized C01 schema, example, OpenAPI, and contract-test surface is
   internally conformant;
2. the full Python regression contains exactly the 24 failures introduced
   when legacy runtime producers validate against the strengthened schemas;
3. no work package owns the affected runtime producer or regression-test
   paths; and
4. the authority contract does not define which closed promotion level a
   non-promotion decision records when no current Passport level is supplied.

Those facts make the boundary a shared-contract/ownership gap.  The verifier
must never be used to weaken the schema, restore a legacy enum, or authorize
runtime work inside C01.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[5]

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

EXPECTED_C01_WRITE_SCOPE = [
    "schemas/**",
    "openapi/**",
    "docs/api_contract.md",
    "tests/contracts/openapi/**",
    "artifacts/work_packages/C01/**",
    "examples/sample_evolution-run-spec.json",
    "examples/sample_promotion-decision.json",
]

AFFECTED_PATHS = [
    "src/epistemic_foundry/evolution_chamber/run_spec.py",
    "src/epistemic_foundry/governance/promotion.py",
    "tests/test_evolution_chamber.py",
    "tests/test_governance.py",
    "tests/test_integration_forge_cycle.py",
]

EXPECTED_FAILURES = [
    "tests/test_evolution_chamber.py::test_run_spec_pins_evaluator_and_holdout",
    "tests/test_evolution_chamber.py::test_evaluator_swap_between_specs_is_detectable",
    "tests/test_governance.py::test_complete_evidence_promotes",
    "tests/test_governance.py::test_missing_grounded_evidence_is_underdetermined",
    "tests/test_governance.py::test_missing_dependency_correction_is_underdetermined",
    "tests/test_governance.py::test_missing_parliament_adjudication_is_underdetermined",
    "tests/test_governance.py::test_missing_multiplicity_accounting_is_underdetermined",
    "tests/test_governance.py::test_absent_reference_sentinel_never_accompanies_a_promotion",
    "tests/test_governance.py::test_unchallenged_candidate_is_underdetermined",
    "tests/test_governance.py::test_required_replication_absent_is_underdetermined",
    "tests/test_governance.py::test_required_human_approval_absent_is_underdetermined",
    "tests/test_governance.py::test_incompatible_method_is_underdetermined",
    "tests/test_governance.py::test_leakage_blocks_even_with_complete_evidence",
    "tests/test_governance.py::test_failed_hard_cascade_blocks",
    "tests/test_governance.py::test_partial_cascade_is_conditional_not_promotion",
    "tests/test_governance.py::test_blocker_outranks_missing_requirements",
    "tests/test_integration_forge_cycle.py::test_full_cycle_promotes_only_with_complete_evidence",
    "tests/test_integration_forge_cycle.py::test_partial_cascade_blocks_promotion_end_to_end",
    "tests/test_integration_forge_cycle.py::test_failed_cascade_blocks_promotion_end_to_end",
    "tests/test_integration_forge_cycle.py::test_leakage_invalidates_the_cycle",
    "tests/test_integration_forge_cycle.py::test_unchallenged_candidate_cannot_promote_end_to_end",
    "tests/test_integration_forge_cycle.py::test_refuted_candidate_cannot_promote_end_to_end",
    "tests/test_integration_forge_cycle.py::test_inconclusive_challenge_cannot_promote_end_to_end",
    "tests/test_integration_forge_cycle.py::test_surviving_every_challenge_promotes_end_to_end",
]

HISTORY_HASHES = {
    "artifacts/work_packages/C01/report.json":
        "14d1815150ba37ebc416d637afbb1514fbbb024f9fe6940ed7b976ce33b60d68",
    "artifacts/work_packages/C01/attempts/0002/report.json":
        "c8100002239cf826c9fe521f86f84295e1cdec3bbe5e49f210c4a7e124d31369",
    "artifacts/work_packages/C01/attempts/0002/example-scope-conflict-verification.json":
        "2f0d871c00af463360548e2282b4512a0028b0632179211ee0461d31eeac24c8",
    "artifacts/work_packages/A05/attempts/0002/report.json":
        "c9c550de22f55d32898f0d33489bc9b0480de6eef4bca7baeb09fcf047c6062c",
    "artifacts/authority_decisions/HD-EF4-C01-SG002-20260728-001.human-decision.json":
        "2c471aea25a4410c53dffbb793c546de395df4301e1ff98375129c3c79c146d6",
}

C01_INPUT_HASHES = {
    "manifests/development_manifest.yaml":
        "2af2704c5e518e3b86b3fcfc8887fe2fad6ccd3c74f36c95c652a0cfddc16b6c",
    "schemas/evolution-run-spec.schema.json":
        "54f6934f33426c8706640038c25f63687097fad36f21c84d46fdf5b0d9b9291a",
    "schemas/promotion-decision.schema.json":
        "d498e62bf42221ca6c4438235dc8f9a88d26d99d7bf29bb7b2160937a8c404ca",
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
        "4074c4afd82781c18ddb885455694ee095da05c9806cdb8d2d93f8334c309d92",
    "tests/contracts/openapi/conftest.py":
        "437641ef742cc0be69b0a666f4c8e619c108dd2c1624f65b9afaf51202ebe5f0",
    "tests/contracts/openapi/test_scientific_contracts.py":
        "fc86bcb30bf2c21057ba609f3a906f7369c72d91ad8616b2989c5aeb34064235",
    "tests/contracts/openapi/test_openapi_contract.py":
        "737dd012fc3b7104763e189d2aea0998c90897856007058a715efd3f2c0471a4",
}

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


def _sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _hash_checks(expected: dict[str, str]) -> dict[str, dict[str, str]]:
    checks: dict[str, dict[str, str]] = {}
    for relative, wanted in expected.items():
        actual = _sha256(relative)
        checks[relative] = {
            "expected_sha256": wanted,
            "actual_sha256": actual,
            "status": "PASS" if actual == wanted else "FAIL",
        }
    if any(item["status"] != "PASS" for item in checks.values()):
        raise RuntimeError("one or more bound files changed")
    return checks


def _json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{relative} must contain a JSON object")
    return value


def _manifest_packages() -> list[dict[str, Any]]:
    value = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = value if isinstance(value, list) else value.get("work_packages", [])
    if not isinstance(packages, list):
        raise TypeError("development manifest work_packages must be a list")
    return packages


def _scope_matches(scope: str, relative: str) -> bool:
    if scope.endswith("/**"):
        prefix = scope[:-3]
        return relative == prefix or relative.startswith(prefix + "/")
    return scope == relative


def _path_owners(packages: list[dict[str, Any]], relative: str) -> list[str]:
    owners: list[str] = []
    for package in packages:
        if any(_scope_matches(str(scope), relative) for scope in package.get("write_scope", [])):
            owners.append(str(package["id"]))
    return owners


def _canonical_hash(document: dict[str, Any], excluded_field: str) -> str:
    payload = copy.deepcopy(document)
    payload.pop(excluded_field, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _schema_example_evidence() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("*.json"))
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    ids: list[str] = []

    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise RuntimeError(f"{path.name} has no $id")
        ids.append(schema_id)
        registry = registry.with_resource(schema_id, Resource.from_contents(schema))
        schemas[path.name] = schema

    failures: list[str] = []
    mapped: set[str] = set()
    for path in schema_paths:
        stem = path.name.removesuffix(".schema.json")
        candidates = [
            ALIASES.get(stem),
            f"sample_{stem}.json",
            f"sample_{stem.replace('-', '_')}.json",
        ]
        example_path = next(
            (
                ROOT / "examples" / candidate
                for candidate in candidates
                if candidate and (ROOT / "examples" / candidate).exists()
            ),
            None,
        )
        if example_path is None:
            failures.append(f"{path.name}: no canonical example")
            continue
        mapped.add(example_path.name)
        instance = json.loads(example_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(
            schemas[path.name],
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in validator.iter_errors(instance):
            location = "/".join(map(str, error.path)) or "<root>"
            failures.append(f"{example_path.name}:{location}: {error.message}")

    extras = sorted(path.name for path in example_paths if path.name not in mapped)
    if len(schema_paths) != 124 or len(example_paths) != 124:
        failures.append("canonical schema/example cardinality changed")
    if len(ids) != len(set(ids)):
        failures.append("canonical schema $id values are not unique")
    if extras:
        failures.append(f"unmapped examples: {extras}")
    if failures:
        raise RuntimeError(f"schema/example validation failed: {failures[:5]}")

    forbidden = ['"PILOT"', '"HYPOTHESIS_PASSPORT_ONLY"']
    legacy_hits: list[str] = []
    for path in [*schema_paths, *example_paths]:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                legacy_hits.append(f"{path.relative_to(ROOT).as_posix()}: {token}")
    if legacy_hits:
        raise RuntimeError(f"legacy promotion values remain: {legacy_hits}")

    evolution_schema = schemas["evolution-run-spec.schema.json"]
    promotion_schema = schemas["promotion-decision.schema.json"]
    evolution_fixture = _json("examples/sample_evolution-run-spec.json")
    promotion_fixture = _json("examples/sample_promotion-decision.json")
    required_refs = evolution_schema["properties"]["resolved_refs"]["required"]

    if len(required_refs) != 20:
        raise RuntimeError("EvolutionRunSpec must require exactly 20 non-optional refs")
    if promotion_schema["$defs"]["promotion_level"]["enum"] != PROMOTION_LEVELS:
        raise RuntimeError("PromotionDecision level vocabulary changed")
    if promotion_fixture["gate_decision_ids"] != GATE_ORDER:
        raise RuntimeError("PromotionDecision gate order changed")
    if evolution_fixture["spec_hash"] != _canonical_hash(evolution_fixture, "spec_hash"):
        raise RuntimeError("EvolutionRunSpec fixture spec_hash does not recompute")
    if promotion_fixture["decision_hash"] != _canonical_hash(
        promotion_fixture, "decision_hash"
    ):
        raise RuntimeError("PromotionDecision fixture decision_hash does not recompute")

    return {
        "schema_count": len(schema_paths),
        "example_count": len(example_paths),
        "valid_example_count": len(mapped),
        "unique_schema_id_count": len(set(ids)),
        "legacy_promotion_value_hits": legacy_hits,
        "required_resolved_ref_count": len(required_refs),
        "external_backend_manifest_is_conditional": (
            "external_backend_manifest" not in required_refs
        ),
        "promotion_levels": PROMOTION_LEVELS,
        "gate_order": GATE_ORDER,
        "fixture_hashes": {
            "spec_hash": evolution_fixture["spec_hash"],
            "decision_hash": promotion_fixture["decision_hash"],
        },
        "promotion_fixture": {
            "requested_level": promotion_fixture["requested_level"],
            "granted_level": promotion_fixture["granted_level"],
            "promotion_ceiling": promotion_fixture["promotion_ceiling"],
            "replication_status": promotion_fixture["replication_status"],
            "decision": promotion_fixture["decision"],
        },
        "status": "PASS",
    }


def _openapi_evidence() -> dict[str, Any]:
    document = yaml.safe_load(
        (ROOT / "openapi/epistemic-foundry-v1.openapi.yaml").read_text(encoding="utf-8")
    )
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    operations: list[dict[str, str]] = []
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method.lower() not in methods:
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": operation["operationId"],
                }
            )
    operation_ids = [item["operation_id"] for item in operations]
    if document.get("openapi") != "3.1.1":
        raise RuntimeError("canonical OpenAPI version is not 3.1.1")
    if len(operations) != 33 or len(operation_ids) != len(set(operation_ids)):
        raise RuntimeError("canonical OpenAPI operation count or uniqueness changed")
    canonical_servers = [
        {"url": "/api/v1", "description": "Canonical v1 base path"}
    ]
    if document.get("servers") != canonical_servers:
        raise RuntimeError("canonical OpenAPI server base path changed")
    if any(not path.startswith("/") or path.startswith("/api/v1/") for path in document.get("paths", {})):
        raise RuntimeError("OpenAPI paths must be server-relative beneath /api/v1")
    return {
        "canonical_file": "openapi/epistemic-foundry-v1.openapi.yaml",
        "openapi_version": document["openapi"],
        "operation_count": len(operations),
        "unique_operation_id_count": len(set(operation_ids)),
        "servers": document["servers"],
        "all_paths_server_relative_beneath_api_v1": True,
        "status": "PASS",
    }


def _pytest_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    targeted_command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/contracts/openapi",
        "tests/test_wire_literal_discipline.py",
        "-p",
        "no:cacheprovider",
        "--tb=no",
    ]
    targeted = subprocess.run(
        targeted_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    targeted_output = targeted.stdout + targeted.stderr
    targeted_match = re.search(r"(\d+) passed", targeted_output)
    targeted_passed = int(targeted_match.group(1)) if targeted_match else -1
    if targeted.returncode != 0 or targeted_passed != 64:
        raise RuntimeError(
            f"targeted C01 contract tests changed: rc={targeted.returncode}, "
            f"passed={targeted_passed}"
        )

    full_command = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        "-p",
        "no:cacheprovider",
        "--tb=no",
    ]
    full = subprocess.run(
        full_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    full_output = full.stdout + full.stderr
    summary = re.search(r"(\d+) failed, (\d+) passed", full_output)
    if summary is None:
        raise RuntimeError("full regression summary was not parseable")
    failed_count = int(summary.group(1))
    passed_count = int(summary.group(2))
    failed_nodes = [
        node.replace("\\", "/")
        for node in re.findall(r"^FAILED (\S+)", full_output, flags=re.MULTILINE)
    ]
    if full.returncode != 1:
        raise RuntimeError(f"full regression exit code changed: {full.returncode}")
    if failed_count != 24 or passed_count != 824:
        raise RuntimeError(
            f"full regression counts changed: failed={failed_count}, passed={passed_count}"
        )
    if failed_nodes != EXPECTED_FAILURES:
        raise RuntimeError(
            "full regression failure identity changed: "
            f"observed={failed_nodes!r}; expected={EXPECTED_FAILURES!r}"
        )

    groups = {
        "tests/test_evolution_chamber.py": sum(
            node.startswith("tests/test_evolution_chamber.py") for node in failed_nodes
        ),
        "tests/test_governance.py": sum(
            node.startswith("tests/test_governance.py") for node in failed_nodes
        ),
        "tests/test_integration_forge_cycle.py": sum(
            node.startswith("tests/test_integration_forge_cycle.py") for node in failed_nodes
        ),
    }
    return (
        {
            "command": "python -m pytest tests/contracts/openapi tests/test_wire_literal_discipline.py -p no:cacheprovider --tb=no",
            "exit_code": targeted.returncode,
            "passed": targeted_passed,
            "failed": 0,
            "status": "PASS",
        },
        {
            "command": "python -m pytest tests -p no:cacheprovider --tb=no",
            "exit_code": full.returncode,
            "baseline_before_c01": 789,
            "current_collected": passed_count + failed_count,
            "passed": passed_count,
            "failed": failed_count,
            "failure_groups": groups,
            "failed_node_ids": failed_nodes,
            "status": "FAIL",
        },
    )


def _runtime_boundary_evidence(packages: list[dict[str, Any]]) -> dict[str, Any]:
    ownership = {path: _path_owners(packages, path) for path in AFFECTED_PATHS}
    if any(ownership.values()):
        raise RuntimeError(f"an affected runtime/test owner appeared: {ownership}")

    run_spec_text = (ROOT / AFFECTED_PATHS[0]).read_text(encoding="utf-8")
    promotion_text = (ROOT / AFFECTED_PATHS[1]).read_text(encoding="utf-8")
    regression_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8") for path in AFFECTED_PATHS[2:]
    )
    producer_missing = {
        "resolved_refs": "resolved_refs" not in run_spec_text,
        "external_backend_enabled": "external_backend_enabled" not in run_spec_text,
    }
    if not all(producer_missing.values()):
        raise RuntimeError("EvolutionRunSpec producer boundary changed")

    runtime_legacy = {
        "promotion_runtime_NONE_occurrences": promotion_text.count('"NONE"'),
        "regression_SUPPORTED_occurrences": regression_text.count('"SUPPORTED"'),
        "regression_NONE_occurrences": regression_text.count('"NONE"'),
        "current_level_occurrences_across_runtime_and_tests": (
            run_spec_text + promotion_text + regression_text
        ).count("current_level"),
    }
    if runtime_legacy != {
        "promotion_runtime_NONE_occurrences": 3,
        "regression_SUPPORTED_occurrences": 8,
        "regression_NONE_occurrences": 4,
        "current_level_occurrences_across_runtime_and_tests": 0,
    }:
        raise RuntimeError(f"legacy runtime/test literals changed: {runtime_legacy}")

    c01 = next(package for package in packages if package.get("id") == "C01")
    if list(c01.get("write_scope", [])) != EXPECTED_C01_WRITE_SCOPE:
        raise RuntimeError("C01 write scope differs from the exact authorized scope")

    return {
        "affected_path_owners": ownership,
        "all_affected_paths_have_zero_manifest_owners": True,
        "c01_write_scope": list(c01["write_scope"]),
        "c01_runtime_work_forbidden": True,
        "evolution_run_spec_producer_missing": producer_missing,
        "legacy_runtime_and_test_literals": runtime_legacy,
        "nonpromotion_level_contract": {
            "schema_granted_level_is_closed_six_level_enum": True,
            "runtime_uses_out_of_contract_NONE": True,
            "request_or_runtime_current_level_input_present": False,
            "authority_for_defaulting_to_INBOX_or_another_level_present": False,
            "finding": (
                "A non-promotion decision cannot lawfully retain or calculate a granted level "
                "from the current runtime input, and defaulting it to INBOX could launder a "
                "failed request into a lower scientific label without the new sealed request "
                "required by the A05 charter."
            ),
        },
        "status": "SPEC_GAP",
    }


def build_evidence() -> dict[str, Any]:
    history_checks = _hash_checks(HISTORY_HASHES)
    c01_checks = _hash_checks(C01_INPUT_HASHES)
    runtime_checks = _hash_checks(RUNTIME_HASHES)
    packages = _manifest_packages()
    schema_examples = _schema_example_evidence()
    openapi = _openapi_evidence()
    targeted_tests, full_regression = _pytest_evidence()
    runtime_boundary = _runtime_boundary_evidence(packages)

    return {
        "schema_version": 1,
        "probe_id": "C01-P003",
        "work_package_id": "C01",
        "attempt_id": "C01-0003",
        "status": "SPEC_GAP",
        "spec_gap_id": "C01-SG003",
        "authority_decision_id": "HD-EF4-C01-SG002-20260728-001",
        "history_hash_checks": history_checks,
        "c01_input_hash_checks": c01_checks,
        "runtime_boundary_hash_checks": runtime_checks,
        "c01_contract_validation": {
            "schema_examples": schema_examples,
            "openapi": openapi,
            "targeted_tests": targeted_tests,
            "status": "PASS",
        },
        "full_python_regression": full_regression,
        "runtime_boundary": runtime_boundary,
        "classification": {
            "typed_outcome": "SPEC_GAP",
            "not_fail_reason": (
                "The schema implementation is clear and its authorized surface passes, but "
                "C01 is expressly forbidden to implement runtime behavior, the manifest assigns "
                "no owner to the invalidated producers/tests, and one required non-promotion "
                "level semantic is undefined. This cannot be repaired as an in-scope code bug."
            ),
            "not_blocked_reason": (
                "No external tool, credential, backend, corpus, or licensed source is needed to "
                "state or reproduce the conflict."
            ),
            "schema_weakening_forbidden": True,
            "legacy_alias_reintroduction_forbidden": True,
        },
        "minimum_higher_order_decision": {
            "assign_runtime_migration_owner": AFFECTED_PATHS,
            "grant_exact_write_scope_only": True,
            "define_nonpromotion_granted_level_semantics": True,
            "choose_gate_sequence": (
                "Either authorize the migration before C01 PASS or explicitly move the full-suite "
                "regression gate to the named migration package; do not silently waive it."
            ),
            "not_requested": [
                "make resolved_refs optional",
                "restore SUPPORTED, NONE, PILOT, or HYPOTHESIS_PASSPORT_ONLY as promotion levels",
                "broaden C01 to runtime or Python implementation",
                "start B04 before C01 passes",
            ],
        },
        "dependency_state": {
            "A05": "PASS",
            "C01": "SPEC_GAP",
            "B04": "WAITING_ON_C01",
            "subsequent_dag_execution_started": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", type=Path)
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()
    if (args.check is None) == (not args.print_json):
        parser.error("choose exactly one of --check or --print-json")

    rendered = json.dumps(build_evidence(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.print_json:
        sys.stdout.write(rendered)
        return 0
    if args.check.read_text(encoding="utf-8") != rendered:
        raise SystemExit(f"evidence differs from {args.check}")
    print(f"PASS: evidence matches {args.check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
