#!/usr/bin/env python3
"""Deterministic A05 probe for evolution and promotion authority contracts.

The probe is intentionally read-only. It checks whether the canonical schemas
and workflow can represent and enforce the higher-authority requirements in
MASTER_EXECUTION_PROMPT.md sections 5 and 8. It does not treat a safe helper
function as workflow enforcement unless the canonical workflow references it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]


def _json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _yaml(path: str) -> dict[str, Any]:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a YAML mapping")
    return value


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _node_identity_text(node: dict[str, Any]) -> str:
    """Text owned by a node, excluding dependency names and downstream edges."""
    return " ".join(
        str(node.get(field, ""))
        for field in ("node_id", "purpose", "executor_type", "executor_ref", "output_schema_ref")
    ).lower()


def _unsafe_promotion_fixture(*, hard_gate_status: str) -> dict[str, Any]:
    return {
        "decision_id": f"PD-unsafe-{hard_gate_status.lower()}",
        "candidate_id": "CAND-unsafe",
        "requested_level": "REPLICATED",
        "granted_level": "REPLICATED",
        "hard_gate_status": hard_gate_status,
        "fitness_vector_id": "FV-unsafe",
        "parliament_adjudication_id": "ABSENT-not-produced",
        "replication_result_ids": [],
        "selective_inference_report_id": "ABSENT-not-produced",
        "minority_report_ids": [],
        "decision": "PROMOTE",
        "rationale": "Adversarial fixture: promotion without resolving authority artifacts.",
        "approval_record_ids": [],
        "decision_hash": "sha256:" + "0" * 64,
    }


def _schema_errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        error.message
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def build_probe() -> dict[str, Any]:
    evolution_schema_path = "schemas/evolution-run-spec.schema.json"
    base_run_schema_path = "schemas/run-spec.schema.json"
    promotion_schema_path = "schemas/promotion-decision.schema.json"
    workflow_path = "workflows/evolution_chamber_cycle.workflow.yaml"
    safe_runtime_path = "src/epistemic_foundry/governance/promotion.py"

    evolution_schema = _json(evolution_schema_path)
    base_run_schema = _json(base_run_schema_path)
    promotion_schema = _json(promotion_schema_path)
    workflow = _yaml(workflow_path)

    Draft202012Validator.check_schema(evolution_schema)
    Draft202012Validator.check_schema(base_run_schema)
    Draft202012Validator.check_schema(promotion_schema)

    unsafe_fixtures = [
        _unsafe_promotion_fixture(hard_gate_status="FAIL"),
        _unsafe_promotion_fixture(hard_gate_status="PARTIAL"),
        _unsafe_promotion_fixture(hard_gate_status="PASS"),
    ]
    fixture_results = []
    for fixture in unsafe_fixtures:
        errors = _schema_errors(promotion_schema, fixture)
        fixture_results.append(
            {
                "hard_gate_status": fixture["hard_gate_status"],
                "decision": fixture["decision"],
                "granted_level": fixture["granted_level"],
                "replication_result_count": len(fixture["replication_result_ids"]),
                "approval_record_count": len(fixture["approval_record_ids"]),
                "schema_result": "ACCEPTED" if not errors else "REJECTED",
                "errors": errors,
            }
        )

    evolution_properties = set(evolution_schema.get("properties", {}))
    base_properties = set(base_run_schema.get("properties", {}))
    base_run_types = set(base_run_schema["properties"]["run_type"].get("enum", []))
    binding_audit = [
        {
            "higher_authority_requirement": "target claim or research objective",
            "available_direct_fields": ["objective"],
            "status": "BOUND",
        },
        {
            "higher_authority_requirement": "mutable genome classes and forbidden authority fields",
            "available_direct_fields": ["population_types"],
            "missing_semantics": ["forbidden authority fields"],
            "status": "PARTIAL",
        },
        {
            "higher_authority_requirement": "initial population and lineage",
            "available_direct_fields": ["seed_genome_ids"],
            "missing_semantics": ["initial lineage binding"],
            "status": "PARTIAL",
        },
        {
            "higher_authority_requirement": "semantic islands and migration rules",
            "available_direct_fields": [],
            "status": "MISSING",
        },
        {
            "higher_authority_requirement": "mutation and crossover operators",
            "available_direct_fields": ["operator_registry_version"],
            "status": "BOUND",
        },
        {
            "higher_authority_requirement": "parent and model routing policy",
            "available_direct_fields": ["selection_policy"],
            "indirect_base_run_fields": ["model_policy_version"],
            "missing_semantics": ["explicit parent policy binding", "explicit model-routing binding"],
            "status": "AMBIGUOUS",
        },
        {
            "higher_authority_requirement": "evaluator bundle and qualification report",
            "available_direct_fields": ["evaluator_bundle_id"],
            "missing_semantics": ["evaluator qualification report binding"],
            "status": "PARTIAL",
        },
        {
            "higher_authority_requirement": "public, hidden, OOD, adversarial and replication stages",
            "available_direct_fields": ["holdout_manifest_id"],
            "missing_semantics": [
                "public stage plan",
                "hidden stage plan",
                "OOD stage plan",
                "adversarial stage plan",
                "replication stage plan",
            ],
            "status": "PARTIAL",
        },
        {
            "higher_authority_requirement": "novelty vector and prior-art boundary",
            "available_direct_fields": [],
            "status": "MISSING",
        },
        {
            "higher_authority_requirement": "fitness vector and hard gates",
            "available_direct_fields": [],
            "status": "MISSING",
        },
        {
            "higher_authority_requirement": "adaptive-search statistical policy",
            "available_direct_fields": [],
            "status": "MISSING",
        },
        {
            "higher_authority_requirement": "archive and negative-knowledge retention",
            "available_direct_fields": [],
            "status": "MISSING",
        },
        {
            "higher_authority_requirement": "hard/soft budgets, concurrency and stop rules",
            "available_direct_fields": [
                "budget_envelope_id",
                "max_generations",
                "max_candidates",
                "stop_policy",
            ],
            "indirect_base_run_fields": ["budget.max_concurrency"],
            "missing_semantics": [
                "declared EvolutionRunSpec-to-RunSpec resolution contract",
            ],
            "status": "AMBIGUOUS",
        },
    ]

    nodes = workflow.get("nodes", [])
    node_by_id = {node["node_id"]: node for node in nodes}
    promotion_node = node_by_id["run_evidence_parliament_promotion"]
    passport_node = node_by_id["issue_hypothesis_passport_revisions"]
    standalone_parliament_nodes = [
        node["node_id"]
        for node in nodes
        if node["node_id"] != promotion_node["node_id"]
        and "parliament" in _node_identity_text(node)
    ]
    standalone_attestation_nodes = [
        node["node_id"]
        for node in nodes
        if node["node_id"] != promotion_node["node_id"]
        and "attest" in _node_identity_text(node)
    ]
    human_authority_nodes = [
        node["node_id"]
        for node in nodes
        if any(
            token in _node_identity_text(node)
            for token in ("human_decision", "approval-record", "human approval", "human_review")
        )
    ]
    output_schemas = {str(node.get("output_schema_ref", "")) for node in nodes}
    workflow_text = (ROOT / workflow_path).read_text(encoding="utf-8")
    safe_runtime_gate_referenced = (
        "epistemic_foundry.governance.promotion" in workflow_text
        or "decide_promotion" in workflow_text
    )

    required_pin_field_names = {
        "forbidden_authority_fields",
        "island_policy_id",
        "migration_policy_id",
        "parent_selection_policy_id",
        "model_routing_policy_id",
        "evaluator_qualification_report_id",
        "validation_cascade_plan_id",
        "novelty_policy_id",
        "prior_art_boundary_id",
        "fitness_policy_id",
        "hard_gate_policy_id",
        "statistical_policy_id",
        "archive_policy_id",
        "negative_memory_policy_id",
        "max_concurrency",
    }

    authority_paths = [
        "MASTER_SPEC.md",
        "MASTER_EXECUTION_PROMPT.md",
        "manifests/development_manifest.yaml",
        evolution_schema_path,
        base_run_schema_path,
        promotion_schema_path,
        workflow_path,
        "prompts/promotion_attestor.md",
        safe_runtime_path,
    ]

    return {
        "probe_id": "A05-P001",
        "work_package_id": "A05",
        "status": "SPEC_GAP",
        "authority_bindings": {path: _sha256(path) for path in authority_paths},
        "schema_meta_validation": {
            "evolution_run_spec": "PASS",
            "base_run_spec": "PASS",
            "promotion_decision": "PASS",
        },
        "promotion_schema_probe": {
            "unsafe_fixtures": fixture_results,
            "all_unsafe_fixtures_schema_valid": all(
                item["schema_result"] == "ACCEPTED" for item in fixture_results
            ),
            "conditional_constraint_keywords_present": sorted(
                {"if", "then", "else", "oneOf", "anyOf", "allOf", "dependentSchemas"}
                & set(_walk_keys(promotion_schema))
            ),
            "finding": (
                "The canonical schema accepts PROMOTE with FAIL or PARTIAL hard gates, "
                "and accepts promotion with empty replication and approval arrays."
            ),
        },
        "evolution_run_spec_probe": {
            "additional_properties_allowed": evolution_schema.get("additionalProperties"),
            "direct_property_names": sorted(evolution_properties),
            "base_run_property_names": sorted(base_properties),
            "base_run_has_evolution_run_type": "evolve" in base_run_types,
            "explicit_required_pin_fields_absent": sorted(
                required_pin_field_names - evolution_properties
            ),
            "binding_audit": binding_audit,
            "non_bound_binding_count": sum(
                item["status"] != "BOUND" for item in binding_audit
            ),
            "finding": (
                "EvolutionRunSpec is closed to additional properties but does not explicitly "
                "bind most mandatory per-run search, evaluator-qualification, stage, statistics, "
                "archive, and concurrency semantics; the base RunSpec link has no canonical "
                "resolution rule and its run_type vocabulary has no evolve value."
            ),
        },
        "workflow_probe": {
            "promotion_node": {
                "node_id": promotion_node["node_id"],
                "executor_type": promotion_node["executor_type"],
                "executor_ref": promotion_node["executor_ref"],
                "output_schema_ref": promotion_node["output_schema_ref"],
                "depends_on": promotion_node["depends_on"],
                "required_policy_checks": promotion_node["required_policy_checks"],
                "determinism_class": promotion_node["determinism_class"],
            },
            "passport_node": {
                "node_id": passport_node["node_id"],
                "executor_type": passport_node["executor_type"],
                "depends_on": passport_node["depends_on"],
                "required_policy_checks": passport_node["required_policy_checks"],
            },
            "promotion_to_passport_is_direct_edge": passport_node["depends_on"]
            == [promotion_node["node_id"]],
            "standalone_parliament_nodes": standalone_parliament_nodes,
            "standalone_attestation_nodes": standalone_attestation_nodes,
            "human_authority_nodes": human_authority_nodes,
            "adjudication_artifact_produced": "schemas/adjudication.schema.json" in output_schemas,
            "attestation_artifact_produced": "schemas/attestation.schema.json" in output_schemas,
            "approval_artifact_produced": "schemas/approval-record.schema.json" in output_schemas,
            "safe_runtime_gate_referenced": safe_runtime_gate_referenced,
            "finding": (
                "A provider-nondeterministic LLM node emits PromotionDecision and directly "
                "unlocks deterministic Passport issuance. The workflow produces no separate "
                "Parliament adjudication, independent attestation, or human approval artifact, "
                "and it does not reference the safe governance promotion function."
            ),
        },
        "runtime_contrast": {
            "safe_runtime_path": safe_runtime_path,
            "workflow_references_safe_runtime": safe_runtime_gate_referenced,
            "finding": (
                "governance/promotion.py refuses failed gates and missing evidence, but the "
                "canonical workflow does not bind that helper as its promotion executor or a "
                "post-LLM deterministic gate."
            ),
        },
        "decision": {
            "typed_outcome": "SPEC_GAP",
            "gap_ids": ["A05-SG001", "A05-SG002"],
            "reason": (
                "A05 cannot repair higher-authority canonical schemas or workflows from its "
                "docs-and-evidence-only write scope without inventing shared semantics."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        type=Path,
        help="Compare the deterministic payload with a checked-in JSON artifact.",
    )
    args = parser.parse_args()

    rendered = json.dumps(build_probe(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check is not None:
        expected = args.check.read_text(encoding="utf-8")
        if expected != rendered:
            raise SystemExit(f"probe output differs from {args.check}")
        print(f"PASS: probe output matches {args.check}")
        return 0

    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
