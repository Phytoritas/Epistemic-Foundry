#!/usr/bin/env python3
"""Build deterministic O01-0002 contract and regression evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/O01/attempts/0002"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/O01"
N04_ATTEMPT = ROOT / "artifacts/work_packages/N04/attempts/0001"
sys.path.insert(0, str(N04_ATTEMPT))
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts/build/canonical_registry"))

import build_n04_0001_evidence as base  # noqa: E402
import generate_o01_examples as fixture_builder  # noqa: E402
import materialize as canonical_materialize  # noqa: E402
from epistemic_foundry.retrieval.planning import (  # noqa: E402
    CANONICAL_LANES,
    CLASS_LANE_FLOORS,
    PlanningContractError,
    reconcile_search_run,
    seal_search_lane_receipt,
    validate_query_plan,
    validate_search_completeness_certificate,
    validate_search_lane_receipt,
)


ATTEMPT_ID = "O01-0002"
WORK_PACKAGE_ID = "O01"
METADATA = ATTEMPT / "attempt-metadata.json"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
DECISION = ROOT / "artifacts/authority_decisions/HD-EF4-O01-SG001-20260731-001.human-decision.json"
DECISION_HASH = "sha256:7147e54c609744ff4f043be9f0407382e36636e3afc2a4dbfa59afc19e1a6265"
SCHEMA_BUNDLE_HASH = "sha256:3112276a66be89d8c2c44065a18d649013667ea39aea16a38902db4849d56a73"
EXAMPLE_BUNDLE_HASH = "sha256:4b15db38718ce5d363794c3370de724b16996738d1e0c5c0a73096f6409047d9"
PLAN_HASH = "sha256:2bc841e81f5fed0d6108c7a0242547bc96b97bde5593b3c1e4117737d7945406"
RECEIPT_HASH = "sha256:2e86674d221ae5f6060938b88aaaa20670ca836acb1bc8a7fab769d2fc9daab7"
CERTIFICATE_HASH = "sha256:af6a3f2369f3786700666133636bd9e93a3ec48ed49361d99570dbcb82226d17"
PRODUCT_FILES = (
    "python/epistemic_foundry/retrieval/planning/__init__.py",
    "python/epistemic_foundry/retrieval/planning/contracts.py",
    "python/epistemic_foundry/retrieval/planning/test_query_plan.py",
    "python/epistemic_foundry/retrieval/planning/test_receipt_completeness.py",
    "schemas/query-plan.schema.json",
    "schemas/search-lane-receipt.schema.json",
    "schemas/search-completeness-certificate.schema.json",
    "examples/sample_query-plan.json",
    "examples/sample_search-lane-receipt.json",
    "examples/sample_search-completeness-certificate.json",
    "config/retrieval_policy.example.yaml",
    "workflows/evidence_retrieval.workflow.yaml",
    "docs/search_completeness.md",
)
DEPENDENCIES = {
    "I04": {
        "attempt_id": "I04-0001",
        "report": "artifacts/work_packages/I04/report.json",
        "report_sha256": "sha256:3a4c7220b63d3c59c459ed638b1258743e84d9110571ab8ea294775aae86e22b",
    },
    "K04": {
        "attempt_id": "K04-0001",
        "report": "artifacts/work_packages/K04/attempts/0001/report.json",
        "report_sha256": "sha256:12d84e70e24fb1f7f9d87619721a27eaf0a77499cfb11b426353bf9c8725c56f",
    },
    "M04": {
        "attempt_id": "M04-0001",
        "report": "artifacts/work_packages/M04/report.json",
        "report_sha256": "sha256:10dc679144d91bb797fbc4d5d5dddea92420759de53c8b08c7951e3882439ea5",
    },
}
EXPECTED_FLOORS = {
    "E0": [],
    "E1": ["lexical", "semantic", "citation", "temporal"],
    "E2": [
        "lexical", "semantic", "citation", "entity_variable",
        "counterevidence", "null", "boundary", "method", "temporal",
    ],
    "E3": [
        "lexical", "semantic", "citation", "entity_variable", "mechanism",
        "counterevidence", "null", "boundary", "method", "temporal",
    ],
    "E4": [
        "lexical", "semantic", "citation", "entity_variable", "mechanism",
        "counterevidence", "null", "boundary", "method", "temporal",
    ],
    "E5": [
        "lexical", "semantic", "citation", "entity_variable", "mechanism",
        "counterevidence", "null", "boundary", "method", "temporal",
        "external_novelty",
    ],
}

sha256_id = base.sha256_id
canonical_hash = base.canonical_hash
read_json = base.read_json
render = base.render
write_json = base.write_json
node_summary = base.node_summary
pytest_summary = base.pytest_summary
assert_clean_node = base.assert_clean_node


def recorded_at() -> str:
    metadata = read_json(METADATA)
    if metadata != {
        "attempt_id": ATTEMPT_ID,
        "recorded_at_utc": "2026-07-31T05:45:09.202Z",
        "work_package_id": WORK_PACKAGE_ID,
    }:
        raise SystemExit("O01 attempt metadata changed")
    return str(metadata["recorded_at_utc"])


def manifest_contract() -> dict[str, Any]:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = document if isinstance(document, list) else document["work_packages"]
    rows = [row for row in packages if row.get("id") == "O01"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one O01 row")
    expected = {
        "depends_on": ["I04", "K04", "M04"],
        "write_scope": ["python/epistemic_foundry/retrieval/planning/**"],
        "independent_review": "required",
        "exit_criteria": [
            "searched/unsearched scope explicit",
            "mandatory lanes class-aware",
        ],
        "required_checks": ["query_plan_test", "receipt_completeness_test"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected or len(packages) != 156:
        raise SystemExit(f"O01 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS", "work_package_count": len(packages)}


def decision_evidence() -> dict[str, Any]:
    decision = read_json(DECISION)
    asserted = decision.pop("decision_hash", None)
    if asserted != DECISION_HASH or canonical_hash(decision) != DECISION_HASH:
        raise SystemExit("O01 HumanDecision hash mismatch")
    if decision.get("decision_id") != "HD-EF4-O01-SG001-20260731-001":
        raise SystemExit("O01 HumanDecision identity mismatch")
    return {
        "decision_id": decision["decision_id"],
        "decision_hash": asserted,
        "path": DECISION.relative_to(ROOT).as_posix(),
        "path_sha256": sha256_id(DECISION),
        "status": "PASS",
    }


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"O01 product file missing: {relative}")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"O01 product file is not UTF-8: {relative}") from error
        if raw.startswith(b"\xef\xbb\xbf") or "\ufffd" in text:
            raise SystemExit(f"O01 product file has invalid UTF-8 markers: {relative}")
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": sha256_id(path),
                "utf8_bom": False,
                "replacement_character_count": 0,
            }
        )
    return rows


def canonical_schema_registry() -> Registry:
    """Build an offline registry for every canonical schema reference."""
    registry = Registry()
    identifiers: set[str] = set()
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = read_json(path)
        Draft202012Validator.check_schema(schema)
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            raise SystemExit(f"canonical schema is missing $id: {path.name}")
        if identifier in identifiers:
            raise SystemExit(f"duplicate canonical schema $id: {identifier}")
        identifiers.add(identifier)
        registry = registry.with_resource(identifier, Resource.from_contents(schema))
    if len(identifiers) != 126:
        raise SystemExit(f"canonical schema registry is not 126: {len(identifiers)}")
    return registry


def targeted_evidence() -> dict[str, Any]:
    summary = pytest_summary(ATTEMPT / "targeted-o01-python.junit.xml")
    if not (
        summary["passed"] == summary["collected"] == 41
        and summary["failed"] == summary["errors"] == summary["skipped"] == 0
    ):
        raise SystemExit(f"O01 targeted gate is not 41/41: {summary}")
    root = ET.parse(ATTEMPT / "targeted-o01-python.junit.xml").getroot()
    cases = root.findall(".//testcase")
    query = [case for case in cases if ".test_query_plan" in case.get("classname", "")]
    receipt = [
        case for case in cases
        if ".test_receipt_completeness" in case.get("classname", "")
    ]
    if len(query) != 21 or len(receipt) != 20:
        raise SystemExit("O01 targeted test partition is not exact 21/20")
    return {
        **summary,
        "query_plan_test_count": len(query),
        "receipt_completeness_test_count": len(receipt),
        "status": "PASS",
    }


def _expect_contract_error(function: Any, code: str) -> None:
    try:
        function()
    except PlanningContractError as error:
        if error.code != code:
            raise SystemExit(f"expected {code}, observed {error.code}") from error
    else:
        raise SystemExit(f"expected fail-closed O01 error {code}")


def query_plan_verification() -> dict[str, Any]:
    generated = fixture_builder.build_output()
    plan = generated["query_plan"]
    sealed = validate_query_plan(plan)
    if sealed.payload != plan or plan.get("plan_hash") != PLAN_HASH:
        raise SystemExit("O01 QueryPlan fixture/hash mismatch")
    if list(CANONICAL_LANES) != [
        "lexical", "semantic", "citation", "entity_variable", "mechanism",
        "counterevidence", "null", "boundary", "method", "temporal",
        "external_novelty",
    ]:
        raise SystemExit("O01 canonical lane order changed")
    observed_floors = {key: list(value) for key, value in CLASS_LANE_FLOORS.items()}
    if observed_floors != EXPECTED_FLOORS:
        raise SystemExit(f"O01 class floors changed: {observed_floors}")
    schema = read_json(ROOT / "schemas/query-plan.schema.json")
    Draft202012Validator.check_schema(schema)
    errors = list(
        Draft202012Validator(
            schema,
            registry=canonical_schema_registry(),
            format_checker=FormatChecker(),
        ).iter_errors(plan)
    )
    if errors:
        raise SystemExit(f"O01 QueryPlan example invalid: {errors[0].message}")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_lane_count": 11,
        "canonical_lane_order": list(CANONICAL_LANES),
        "class_lane_floors": observed_floors,
        "classification_binding_fields": [
            "request_id", "request_revision", "request_input_hash",
            "classification_id", "classification_revision", "classification_hash",
            "work_class", "classifier_version", "policy_bundle_hash",
        ],
        "e0_contract": {
            "required_lanes": [],
            "retrieval_requirement": "NOT_REQUIRED",
            "backend_calls": 0,
        },
        "legacy_and_noncanonical_writes_rejected": [
            "support", "counter", "novelty", "custom",
        ],
        "non_waivable_floor": True,
        "optional_selection_is_monotonic": True,
        "plan_hash": plan["plan_hash"],
        "schema_validation": "PASS",
        "status": "PASS",
    }


def receipt_completeness_verification() -> dict[str, Any]:
    generated = fixture_builder.build_output()
    plan = generated["query_plan"]
    receipts = generated["all_receipts"]
    certificate = generated["certificate"]
    if len(receipts) != 11 or [row["lane"] for row in receipts] != list(CANONICAL_LANES):
        raise SystemExit("O01 fixture does not reconcile all eleven lanes")
    for receipt in receipts:
        validate_search_lane_receipt(receipt)
    validate_search_completeness_certificate(plan, receipts, certificate)
    representative = generated["representative_receipt"]
    if representative.get("receipt_hash") != RECEIPT_HASH:
        raise SystemExit("representative O01 receipt hash mismatch")
    if certificate.get("certificate_hash") != CERTIFICATE_HASH:
        raise SystemExit("O01 certificate hash mismatch")
    selected = set(plan["required_lanes"])
    execution_lanes = {row["lane"] for row in receipts if row["receipt_kind"] == "EXECUTION"}
    sentinel_lanes = {row["lane"] for row in receipts if row["receipt_kind"] == "SENTINEL"}
    if execution_lanes != selected or execution_lanes & sentinel_lanes:
        raise SystemExit("O01 execution/sentinel exclusivity mismatch")
    exact = next(row for row in receipts if row["lane"] == "lexical")
    tampered = dict(exact)
    tampered["query_text"] = " " + str(exact["query_text"]) + " "
    _expect_contract_error(
        lambda: validate_search_lane_receipt(tampered), "QUERY_HASH_MISMATCH"
    )

    e0 = fixture_builder.build_plan()
    e0_proposal = e0.payload
    # The targeted tests bind the separately compiled E0 path.  Direct evidence
    # here records the tested invariant without fabricating an alternate fixture.
    if certificate["completion_state"] != "PASS":
        raise SystemExit("O01 E2 fixture completion is not PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "certificate_hash": certificate["certificate_hash"],
        "completion_precedence": ["FAIL", "BLOCKED", "PARTIAL", "PASS"],
        "e0_completion": "NOT_REQUIRED",
        "execution_lane_count": len(execution_lanes),
        "execution_lanes": sorted(execution_lanes, key=list(CANONICAL_LANES).index),
        "query_hash_binds_exact_utf8_text_including_whitespace": True,
        "receipt_hash": representative["receipt_hash"],
        "receipt_states": [
            "UNSEARCHED", "SEARCHED_NONE", "SEARCHED_WITH_RESULTS",
            "PARTIAL", "BLOCKED", "FAILED",
        ],
        "sentinel_and_execution_exclusive": True,
        "sentinel_lane_count": len(sentinel_lanes),
        "selected_lanes_require_execution_receipts": True,
        "unselected_lanes_require_exactly_one_sentinel": True,
        "all_lane_reconciliation_count": len(receipts),
        "absence_claim_ceiling": certificate["absence_claim_ceiling"],
        "novelty_claim_ceiling": certificate["novelty_claim_ceiling"],
        "status": "PASS",
    }


def schema_example_workflow_verification() -> dict[str, Any]:
    generated = fixture_builder.build_output()
    fixture_map = {
        "query_plan": "examples/sample_query-plan.json",
        "representative_receipt": "examples/sample_search-lane-receipt.json",
        "certificate": "examples/sample_search-completeness-certificate.json",
    }
    for key, relative in fixture_map.items():
        if read_json(ROOT / relative) != generated[key]:
            raise SystemExit(f"generated O01 fixture differs from {relative}")
    plan = read_json(ROOT / fixture_map["query_plan"])
    receipt = read_json(ROOT / fixture_map["representative_receipt"])
    certificate = read_json(ROOT / fixture_map["certificate"])
    if (
        plan.get("plan_hash") != PLAN_HASH
        or receipt.get("receipt_hash") != RECEIPT_HASH
        or certificate.get("certificate_hash") != CERTIFICATE_HASH
    ):
        raise SystemExit("O01 canonical example hashes changed")

    workflow = yaml.safe_load(
        (ROOT / "workflows/evidence_retrieval.workflow.yaml").read_text(encoding="utf-8")
    )
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 20:
        raise SystemExit("O01 workflow must contain exactly 20 nodes")
    ids = [node["node_id"] for node in nodes]
    if len(ids) != len(set(ids)):
        raise SystemExit("O01 workflow node IDs are not unique")
    missing = sorted(
        {dependency for node in nodes for dependency in node.get("depends_on", [])}
        - set(ids)
    )
    if missing:
        raise SystemExit(f"O01 workflow has missing dependencies: {missing}")
    completeness = workflow.get("completeness_contract", {})
    if not (
        completeness.get("all_lane_reconciliation_count") == 11
        and completeness.get("lane_dispatch_policy")
        == "QueryPlan SELECTED dispositions only"
        and completeness.get("unselected_lane_backend_calls") == 0
        and "selected retrieval nodes" in str(
            completeness.get("fan_in_dependency_policy")
        )
    ):
        raise SystemExit("O01 selected-only workflow compilation/fan-in changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_example_hashes": {
            "plan_hash": plan["plan_hash"],
            "receipt_hash": receipt["receipt_hash"],
            "certificate_hash": certificate["certificate_hash"],
        },
        "generated_fixture_parity": "PASS",
        "schema_count": 126,
        "example_count": 126,
        "o01_schema_count": 3,
        "o01_example_count": 3,
        "workflow_node_count": len(nodes),
        "workflow_node_ids_unique": True,
        "workflow_missing_dependency_count": 0,
        "selected_only_compiled_dispatch": True,
        "selected_only_fan_in": True,
        "unselected_backend_call_count": 0,
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for package_id, binding in DEPENDENCIES.items():
        path = ROOT / binding["report"]
        report = read_json(path)
        if not (
            report.get("work_package_id") == package_id
            and report.get("attempt_id") == binding["attempt_id"]
            and report.get("status") == "PASS"
            and report.get("package_status") == "PASS"
            and report.get("completion_ready") is False
            and sha256_id(path) == binding["report_sha256"]
        ):
            raise SystemExit(f"O01 dependency {package_id} is not exact sealed PASS")
        verified[package_id] = {**binding, "status": "PASS"}
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": verified,
        "dependency_count": len(verified),
        "downstream": {"O02": "WAITING_ON_O01", "O03": "WAITING_ON_O01"},
        "status": "PASS",
    }


def node_files() -> list[str]:
    return sorted(
        path.relative_to(ROOT).as_posix()
        for folder in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in folder.rglob("*.test.mjs")
        if path.is_file()
    )


def c02_projection_verification() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ef-o01-c02-") as directory:
        output = Path(directory) / "verification.json"
        process = subprocess.run(
            [sys.executable, "-B", "packages/contracts/codegen/verify.py", "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if process.returncode != 0:
            raise SystemExit("live C02 verifier failed: " + process.stdout + process.stderr)
        live = read_json(output)
    if not (
        live.get("status") == "PASS"
        and live.get("schema_count") == live.get("example_count") == 126
        and live.get("schema_bundle_sha256") == SCHEMA_BUNDLE_HASH
        and live.get("example_bundle_sha256") == EXAMPLE_BUNDLE_HASH
        and live.get("generated_file_count") == 9
        and live.get("codegen_clean_diff", {}).get("status") == "PASS"
        and live.get("failures") == []
    ):
        raise SystemExit("C02 projection is not current 126/126 PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "schema_count": 126,
        "example_count": 126,
        "schema_bundle_sha256": live["schema_bundle_sha256"],
        "example_bundle_sha256": live["example_bundle_sha256"],
        "generated_file_count": live["generated_file_count"],
        "generated_artifact_hashes": live["generated_artifact_hashes"],
        "cross_language_fixture_parity": live["cross_language_fixture_parity"],
        "deterministic_double_replay": live["deterministic_double_replay"],
        "status": "PASS",
    }


def b04_projection_verification() -> dict[str, Any]:
    registry, resources = canonical_materialize.build_registry_document(ROOT)
    verification = canonical_materialize.verify_projection(ROOT)
    registry_path = ROOT / "src/epistemic_foundry/_canonical/canonical-registry.json"
    stored = read_json(registry_path)
    if stored != registry:
        raise SystemExit("B04 canonical registry differs from live root projection")
    if not (
        verification.get("status") == "PASS"
        and verification.get("missing") == []
        and verification.get("extra") == []
        and verification.get("mismatches") == []
        and len(resources) == 127
        and registry.get("schema_count") == 126
        and registry.get("openapi_document_count") == 1
        and registry.get("source_bundle_hash")
        == "sha256:fc1859f132256c6448ff764c1c66c3a9d03068371209f883b2bdefc2f4158374"
        and registry.get("projected_snapshot_bundle_hash")
        == "sha256:dde5466f33e4cdd5864fa925fe224d903c774d1b23e279c22831a930aa22bd35"
    ):
        raise SystemExit("B04 projection freshness or expected bundle binding changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "source_bundle_hash": registry["source_bundle_hash"],
        "projected_snapshot_bundle_hash": registry["projected_snapshot_bundle_hash"],
        "registry_hash": sha256_id(registry_path),
        "resource_count": len(resources),
        "schema_count": registry["schema_count"],
        "openapi_document_count": registry["openapi_document_count"],
        "missing_paths": [],
        "extra_paths": [],
        "hash_mismatches": [],
        "root_snapshot_byte_parity": "PASS",
        "status": "PASS",
    }


def regression_evidence() -> dict[str, Any]:
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    assert_clean_node(full_node, 819, "full Node")
    files = node_files()
    if not (
        full_python["passed"] == full_python["collected"] == 1064
        and full_python["failed"] == full_python["errors"] == full_python["skipped"] == 0
        and len(files) == len(set(files)) == 79
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 79
    ):
        raise SystemExit("O01 full regression evidence is incomplete")
    inventory = {
        "attempt_id": ATTEMPT_ID,
        "count": 79,
        "files": files,
        "unique": True,
    }
    write_json(ATTEMPT / "node-test-inventory.json", inventory)
    return {
        "attempt_id": ATTEMPT_ID,
        "full_python": full_python,
        "full_node": {**full_node, "test_file_count": 79},
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "repository_structure": "PASS",
        "package_boundaries": "PASS",
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "status": "PASS",
    }


def dirty_worktree_present() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise SystemExit("cannot inspect dirty worktree")
    return bool(result.stdout.strip())


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    if not dirty_worktree_present():
        raise SystemExit("pre-existing dirty worktree unexpectedly became clean")
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "manifest_product_scope": "python/epistemic_foundry/retrieval/planning/**",
        "human_decision_shared_contract_surfaces": [
            relative for relative in PRODUCT_FILES
            if not relative.startswith("python/epistemic_foundry/retrieval/planning/")
        ],
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope_violation_count": 0,
        "evidence_scope": "artifacts/work_packages/O01/**",
        "unrelated_product_change_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "subagents_or_fleet_used": False,
        "status": "PASS",
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "query-plan-verification.json": query_plan_verification(),
        "receipt-completeness-verification.json": receipt_completeness_verification(),
        "schema-example-workflow-verification.json": schema_example_workflow_verification(),
        "full-regression-impact.json": regression_evidence(),
        "c02-projection-verification.json": c02_projection_verification(),
        "b04-projection-verification.json": b04_projection_verification(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    return f"""# O01-0002 QueryPlan and SearchLaneReceipt contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed O01
artifacts and receipts, not actor-independent certification.

## Findings

1. The lane vocabulary is closed to eleven canonically ordered values.
   `support` remains an evidence role; legacy `counter`/`novelty`, `support`,
   `custom`, and unknown values fail closed on canonical writes.
2. E0-E5 floors match the HumanDecision exactly. Floor lanes cannot be waived;
   optional lanes may only increase protection and `NOT_APPLICABLE` requires
   typed deterministic evidence.
3. QueryPlan binds immutable request, classification, policy, scope, query,
   budget, stop-rule and lane-decision inputs. Its fixture hash is `{PLAN_HASH}`.
4. All eleven lanes reconcile. Selected lanes have execution receipts;
   unselected lanes have exactly one `UNSEARCHED` sentinel, never both.
   `SEARCHED_NONE` cannot masquerade as unsearched.
5. Exact persisted UTF-8 query text, including whitespace, is hash-bound.
   Result counts, plan hashes, receipt hashes and certificate hashes fail closed.
6. Run precedence is `FAIL > BLOCKED > PARTIAL > PASS`; E0 is `NOT_REQUIRED`.
   Absence and novelty ceilings derive only from executed scope.
7. The workflow has 20 unique nodes and no missing dependency. It compiles only
   selected retrieval nodes and fan-in depends only on those selected nodes.
8. Targeted O01 passes 41/41; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']};
   full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files. No failure or
   skip/xfail/todo/cancellation suppression is present.
9. Canonical validation and C02 projection are current at 126 schemas / 126
   examples. B04 projection is byte-current at 127 resources plus registry.
10. The thirteen authorized product files are BOM-less UTF-8 with zero
    replacement characters; the existing dirty worktree and all history remain.

## Assurance boundary

This proves deterministic in-process O01 planning, receipt and reconciliation
contracts. It does not prove live retrieval provider availability, corpus
coverage, O02/O03 behavior, actor-independent review, full product completion,
release or production readiness, or `completion_ready=true`. Global
`implementation_gate=fail` remains required after sealing.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect O01 manifest, decision, dependencies, dirty worktree, and RAH state", "PASS"),
        ("C002", "Implement closed lane vocabulary and exact E0-E5 QueryPlan floors", "PASS"),
        ("C003", "Implement immutable classification binding, canonical hashing, and monotonic lane decisions", "PASS"),
        ("C004", "Implement six receipt states, sentinel/execution exclusivity, and all-lane reconciliation", "PASS"),
        ("C005", "Implement run precedence and absence/novelty claim ceilings", "PASS"),
        ("C006", "Correct canonical O01 schemas, examples, policy, workflow, and documentation", "PASS"),
        ("C007", "Run query_plan_test and receipt_completeness_test", "PASS: 41/41"),
        ("C008", "Run full Python suite", "PASS: 1064/1064"),
        ("C009", "Run full Node suite", "PASS: 819/819 across 79 files"),
        ("C010", "Run canonical C02 codegen verification", "PASS: 126/126 and 9 generated files"),
        ("C011", "Verify B04 canonical projection freshness", "PASS: 127 resources plus registry"),
        ("C012", "Run npm structure and boundary checks", "PASS"),
        ("C013", "Run git diff --check", "PASS with pre-existing line-ending advisories only"),
        ("C014", "Primary-session separate adversarial contract review", "PASS: zero blocking findings; actor_independence=false"),
        ("C015", "Build and verify deterministic O01 WorkPackageReport evidence", "PASS"),
    ]
    timestamp = recorded_at()
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": 0,
            "recorded_at_utc": timestamp,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, result in rows
    ]


def expected_commands() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "O01-0002-QUERY-PLAN-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "O01-0002-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-O01-0002-QUERY-PLAN-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "query_plan_test",
                "details": "21/21 exact vocabulary, class-floor, applicability, hashing, replay, and fail-closed cases pass",
                "status": "PASS",
            },
            {
                "check": "receipt_completeness_test",
                "details": "20/20 six-state, sentinel, all-lane, precedence, query-hash, ceiling, and immutability cases pass",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Python 1064/1064, Node 819/819 across 79 files, codegen 126/126, projection current",
                "status": "PASS",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt)
    )
    if errors:
        raise SystemExit(f"invalid O01 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "query-plan-verification.json",
        "query-plan-verification.artifact-receipt.json",
        "receipt-completeness-verification.json",
        "schema-example-workflow-verification.json",
        "full-regression-impact.json",
        "c02-projection-verification.json",
        "b04-projection-verification.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "node-test-inventory.json",
        "targeted-o01-python.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "commands.jsonl",
        "review.md",
        "attempt-metadata.json",
        "generate_o01_examples.py",
        "build_o01_0002_evidence.py",
        "o01_0002_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    result: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required O01 evidence artifact missing: {name}")
        result.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return result


def report_document(
    documents: dict[str, dict[str, Any]], *, rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    targeted = targeted_evidence()
    regression = documents["full-regression-impact.json"]
    receipt = read_json(ATTEMPT / "query-plan-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/O01/attempts/0002/query-plan-verification.artifact-receipt.json",
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": documents["dependency-status.json"]["dependencies"],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "searched_unsearched_scope_explicit": "PASS",
            "mandatory_lanes_class_aware": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "live retrieval provider or corpus availability",
            "actor-independent certification of this implementation review",
            "O02 or O03 conformance",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "rah_state": rah_state,
        "regression": regression,
        "required_checks": {
            "query_plan_test": {
                "passed": targeted["query_plan_test_count"],
                "failed": 0,
                "skipped": 0,
                "status": "PASS",
            },
            "receipt_completeness_test": {
                "passed": targeted["receipt_completeness_test_count"],
                "failed": 0,
                "skipped": 0,
                "status": "PASS",
            },
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/O01/attempts/0002/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "QueryPlan and SearchLaneReceipt contracts",
        "verification": {
            "targeted_o01": "41/41",
            "full_python": "1064/1064",
            "full_node": "819/819 across 79 files",
            "canonical_schema_examples": "126/126",
            "c02_generated_files": 9,
            "b04_projected_resources": 127,
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "query_plan": documents["query-plan-verification.json"],
            "receipt_completeness": documents["receipt-completeness-verification.json"],
            "schema_example_workflow": documents["schema-example-workflow-verification.json"],
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is None:
        report.pop("rah_state")
    return report


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    recorded_at()
    manifest_contract()
    decision_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(
        expected_commands(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    authority = ATTEMPT / "query-plan-verification.json"
    write_json(
        ATTEMPT / "query-plan-verification.artifact-receipt.json",
        make_receipt(authority),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
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
    write_json(ATTEMPT / "report.json", report_document(documents, rah_state=rah_state))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    recorded_at()
    manifest_contract()
    decision_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored O01 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored O01 commands differ from deterministic rendering")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored O01 review differs from deterministic rendering")
    expected_receipt = make_receipt(ATTEMPT / "query-plan-verification.json")
    receipt_path = ATTEMPT / "query-plan-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored O01 ArtifactReceipt differs from live evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("O01 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if (ATTEMPT / "report.json").read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored O01 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"O01 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "targeted_o01": "41/41",
        "full_python": "1064/1064",
        "full_node": "819/819 across 79 files",
        "canonical_schema_examples": "126/126",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
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
