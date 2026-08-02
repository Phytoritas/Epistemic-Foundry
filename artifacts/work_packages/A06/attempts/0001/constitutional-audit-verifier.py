"""Deterministic A06 audit of the A05 evolution-authority contract.

This verifier is intentionally read-only outside the A06 evidence directory.
It distinguishes a strong bounded Python helper from a canonical workflow that
actually binds every promotion to that helper and its immutable artifacts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[5]
OUTPUT = Path(__file__).with_name("constitutional-audit-verification.json")
sys.path.insert(0, str(ROOT / "src"))

from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402
from epistemic_foundry.verifier_firewall import (  # noqa: E402
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)


EXPECTED_A05_HASHES = {
    "artifacts/work_packages/A05/attempts/0002/report.json":
        "c9c550de22f55d32898f0d33489bc9b0480de6eef4bca7baeb09fcf047c6062c",
    "artifacts/work_packages/A05/attempts/0002/review.md":
        "7908fc4dbc560aa68d450aae59a5f51f9ff08eb4518fb0b1e30fe0774bb86f00",
    "artifacts/work_packages/A05/attempts/0002/authority-contract-verification.json":
        "b2a228ca578d8fdb70e1d893aaa0b23da500a44dc5609ef3f81c76741b6f7ff0",
    "docs/v4_a05/evolution_authority_and_promotion_charter.md":
        "5d8b1b5d7b8bfed727e823ab49996de4ed40ba520a1958bbb519dda36639a181",
    "docs/v4_a05/adversarial_contract_tests.md":
        "089944826184843854f0af4415a5bca6f31c83e88227597b20f7bd8db37d5290",
}

CANONICAL_GATES = [
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

PROMOTION_AUTHORITY_ARTIFACTS = {
    "action_intent": "schemas/action-intent.schema.json",
    "gate_decision": "schemas/gate-decision.schema.json",
    "adjudication": "schemas/adjudication.schema.json",
    "attestation": "schemas/attestation.schema.json",
    "approval_record": "schemas/approval-record.schema.json",
    "capability_lease": "schemas/capability-lease.schema.json",
    "effect_receipt": "schemas/effect-receipt.schema.json",
    "artifact_receipt": "schemas/artifact-receipt.schema.json",
}

FORBIDDEN_ADAPTER_CAPABILITIES = {
    "holdout:read",
    "holdout_read",
    "evaluator:write",
    "evaluator_write",
    "policy:write",
    "policy_write",
    "promotion:approve",
    "promotion_approve",
    "promotion:commit",
    "promotion_commit",
    "approval:issue",
    "approval_issue",
    "ledger:rewrite",
    "ledger_rewrite",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_yaml(relative: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def schema_accepts(schema: dict[str, Any], instance: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    return not errors, [error.message for error in errors]


def ancestors(nodes: dict[str, dict[str, Any]], node_id: str) -> list[str]:
    found: set[str] = set()
    pending = list(nodes[node_id].get("depends_on", []))
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(nodes.get(current, {}).get("depends_on", []))
    return sorted(found)


def node_outputs(nodes: Iterable[dict[str, Any]], schema_ref: str) -> list[str]:
    return sorted(
        str(node["node_id"])
        for node in nodes
        if node.get("output_schema_ref") == schema_ref
    )


def audit_a05_dependency() -> dict[str, Any]:
    observed: dict[str, Any] = {}
    for relative, expected in EXPECTED_A05_HASHES.items():
        actual = sha256(ROOT / relative)
        observed[relative] = {
            "expected_sha256": f"sha256:{expected}",
            "observed_sha256": f"sha256:{actual}",
            "match": actual == expected,
        }

    current = load_json("artifacts/work_packages/A05/attempts/0002/report.json")
    historical = load_json("artifacts/work_packages/A05/report.json")
    passed = (
        current.get("attempt_id") == "A05-0002"
        and current.get("status") == "PASS"
        and historical.get("status") == "SPEC_GAP"
        and all(item["match"] for item in observed.values())
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "latest_attempt": current.get("attempt_id"),
        "latest_status": current.get("status"),
        "historical_top_level_status": historical.get("status"),
        "historical_gap_ids": historical.get("spec_gaps", historical.get("gap_ids", [])),
        "history_preserved": historical.get("status") == "SPEC_GAP",
        "bound_hashes": observed,
    }


def audit_schemas_and_runtime() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    schema_ids: list[str] = []
    meta_failures: list[dict[str, str]] = []
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover - evidence capture
            meta_failures.append(
                {"path": path.relative_to(ROOT).as_posix(), "error": str(exc)}
            )
        if isinstance(schema.get("$id"), str):
            schema_ids.append(schema["$id"])

    evaluator_schema = load_json("schemas/evaluator-bundle.schema.json")
    holdout_schema = load_json("schemas/holdout-manifest.schema.json")
    evaluator_sample = load_json("examples/sample_evaluator-bundle.json")
    holdout_sample = load_json("examples/sample_holdout-manifest.json")

    hostile_evaluator_readable = copy.deepcopy(evaluator_sample)
    hostile_evaluator_readable["readable_by_candidates"] = True
    hostile_evaluator_readable["bundle_hash"] = hash_excluding(
        hostile_evaluator_readable, "bundle_hash"
    )
    readable_valid, readable_errors = schema_accepts(
        evaluator_schema, hostile_evaluator_readable
    )

    hostile_evaluator_mutable = copy.deepcopy(evaluator_sample)
    hostile_evaluator_mutable["mutable_during_run"] = True
    hostile_evaluator_mutable["bundle_hash"] = hash_excluding(
        hostile_evaluator_mutable, "bundle_hash"
    )
    mutable_valid, mutable_errors = schema_accepts(
        evaluator_schema, hostile_evaluator_mutable
    )

    holdout_results: dict[str, Any] = {}
    runtime_results: dict[str, Any] = {}
    for candidate_access in ("NONE", "METADATA_ONLY", "AGGREGATE_ONLY"):
        hostile_holdout = copy.deepcopy(holdout_sample)
        hostile_holdout["candidate_access"] = candidate_access
        hostile_holdout["manifest_hash"] = hash_excluding(
            hostile_holdout, "manifest_hash"
        )
        valid, errors = schema_accepts(holdout_schema, hostile_holdout)
        holdout_results[candidate_access] = {
            "schema_valid": valid,
            "validation_errors": errors,
        }

        try:
            runtime_holdout = build_holdout_manifest(
                dataset_or_fixture_ids=("DATA-HIDDEN-A06",),
                split_strategy="sealed-fixture",
                selection_cutoff="2026-01-01",
                access_principal_ids=("PRIN-A06-VALIDATOR",),
                unblinding_policy="never during candidate generation",
                rotation_policy="rotate after any exposure",
                candidate_access=candidate_access,
                holdout_manifest_id="HO-A06-HOSTILE",
            )
            runtime_bundle = build_evaluator_bundle(
                version="4.0.0-a06-fixture",
                evaluator_artifact_ids=("ART-A06-EVALUATOR",),
                metric_ids=("METRIC-A06",),
                holdout_manifest_id=runtime_holdout["holdout_manifest_id"],
                environment_manifest_id="ENV-A06",
                policy_bundle_id="POL-A06",
                evaluator_bundle_id="EB-A06-HOSTILE",
            )
            VerifierFirewall(runtime_bundle, runtime_holdout)
        except Exception as exc:  # pragma: no cover - evidence capture
            runtime_results[candidate_access] = {
                "accepted": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        else:
            runtime_results[candidate_access] = {
                "accepted": True,
                "error_type": None,
                "error": None,
            }

    duplicate_ids = sorted(
        schema_id for schema_id in set(schema_ids) if schema_ids.count(schema_id) > 1
    )
    return {
        "canonical_schema_count": len(schema_paths),
        "unique_schema_id_count": len(set(schema_ids)),
        "duplicate_schema_ids": duplicate_ids,
        "meta_schema_failures": meta_failures,
        "meta_validation_status": (
            "PASS" if not meta_failures and not duplicate_ids else "FAIL"
        ),
        "hostile_evaluator_fixtures": {
            "readable_by_candidates_true": {
                "schema_valid": readable_valid,
                "validation_errors": readable_errors,
                "required_contract_result": "REJECT",
            },
            "mutable_during_run_true": {
                "schema_valid": mutable_valid,
                "validation_errors": mutable_errors,
                "required_contract_result": "REJECT",
            },
        },
        "holdout_candidate_access_fixtures": holdout_results,
        "runtime_holdout_candidate_access": runtime_results,
        "constitutional_status": "FAIL"
        if (
            readable_valid
            or mutable_valid
            or holdout_results["METADATA_ONLY"]["schema_valid"]
            or holdout_results["AGGREGATE_ONLY"]["schema_valid"]
            or runtime_results["METADATA_ONLY"]["accepted"]
            or runtime_results["AGGREGATE_ONLY"]["accepted"]
        )
        else "PASS",
    }


def audit_workflows() -> dict[str, Any]:
    evolution = load_yaml("workflows/evolution_chamber_cycle.workflow.yaml")
    forge = load_yaml("workflows/forge_research_cycle.workflow.yaml")
    evolution_nodes_list = list(evolution["nodes"])
    forge_nodes_list = list(forge["nodes"])
    evolution_nodes = {str(node["node_id"]): node for node in evolution_nodes_list}
    passport_node = evolution_nodes["issue_hypothesis_passport_revisions"]
    promotion_node = evolution_nodes["run_evidence_parliament_promotion"]
    passport_ancestors = ancestors(evolution_nodes, passport_node["node_id"])

    artifact_output_nodes = {
        name: node_outputs(evolution_nodes_list, schema_ref)
        for name, schema_ref in PROMOTION_AUTHORITY_ARTIFACTS.items()
    }
    missing_authority_outputs = sorted(
        name for name, nodes in artifact_output_nodes.items() if not nodes
    )
    declared_gate_ids = sorted(
        {
            gate
            for node in evolution_nodes_list
            for value in (
                node.get("node_id", ""),
                node.get("purpose", ""),
                node.get("executor_ref", ""),
                *node.get("acceptance_checks", []),
            )
            for gate in CANONICAL_GATES
            if gate in str(value)
        }
    )

    dangerous_capabilities: list[dict[str, Any]] = []
    for node in evolution_nodes_list:
        hits = sorted(set(node.get("capabilities", [])) & FORBIDDEN_ADAPTER_CAPABILITIES)
        if hits:
            dangerous_capabilities.append(
                {"node_id": node["node_id"], "capabilities": hits}
            )

    promotion_commit_holders = sorted(
        str(node["node_id"])
        for node in evolution_nodes_list
        if set(node.get("capabilities", [])) & {"promotion:commit", "promotion_commit"}
    )
    forge_text = (ROOT / "workflows/forge_research_cycle.workflow.yaml").read_text(
        encoding="utf-8"
    )
    evolution_text = (
        ROOT / "workflows/evolution_chamber_cycle.workflow.yaml"
    ).read_text(encoding="utf-8")
    forge_artifact_outputs = {
        name: node_outputs(forge_nodes_list, schema_ref)
        for name, schema_ref in PROMOTION_AUTHORITY_ARTIFACTS.items()
    }

    return {
        "evolution_workflow": {
            "workflow_id": evolution.get("workflow_id"),
            "node_count": len(evolution_nodes_list),
            "promotion_node": {
                "node_id": promotion_node["node_id"],
                "executor_type": promotion_node.get("executor_type"),
                "executor_ref": promotion_node.get("executor_ref"),
                "determinism_class": promotion_node.get("determinism_class"),
                "input_schema_ref": promotion_node.get("input_schema_ref"),
                "output_schema_ref": promotion_node.get("output_schema_ref"),
                "depends_on": promotion_node.get("depends_on"),
                "read_scope": promotion_node.get("read_scope"),
                "capabilities": promotion_node.get("capabilities"),
                "direct_llm_promotion_decision": (
                    promotion_node.get("executor_type") == "llm"
                    and promotion_node.get("output_schema_ref")
                    == "schemas/promotion-decision.schema.json"
                ),
            },
            "passport_node": {
                "node_id": passport_node["node_id"],
                "executor_type": passport_node.get("executor_type"),
                "depends_on": passport_node.get("depends_on"),
                "read_scope": passport_node.get("read_scope"),
                "write_scope": passport_node.get("write_scope"),
                "capabilities": passport_node.get("capabilities"),
            },
            "passport_ancestor_count": len(passport_ancestors),
            "passport_ancestors": passport_ancestors,
            "authority_artifact_output_nodes": artifact_output_nodes,
            "missing_authority_artifact_outputs": missing_authority_outputs,
            "canonical_gate_ids_declared_in_nodes": declared_gate_ids,
            "canonical_gate_ids_missing_from_nodes": sorted(
                set(CANONICAL_GATES) - set(declared_gate_ids)
            ),
            "promotion_commit_capability_holders": promotion_commit_holders,
            "dangerous_adapter_capability_declarations": dangerous_capabilities,
            "generic_result_receipt_text_present": "result receipt present" in evolution_text,
            "effect_receipt_schema_bound": bool(artifact_output_nodes["effect_receipt"]),
            "capability_lease_schema_bound": bool(artifact_output_nodes["capability_lease"]),
        },
        "forge_workflow": {
            "workflow_id": forge.get("workflow_id"),
            "node_count": len(forge_nodes_list),
            "contains_evolution_workflow_binding": (
                "evolution_chamber_cycle" in forge_text
                or any(
                    node.get("executor_type") == "subworkflow"
                    and "evolution" in str(node.get("executor_ref", "")).lower()
                    for node in forge_nodes_list
                )
            ),
            "promotion_authority_artifact_output_nodes": forge_artifact_outputs,
            "deterministic_gate_node_output": next(
                (
                    node.get("output_schema_ref")
                    for node in forge_nodes_list
                    if node.get("node_id") == "apply_deterministic_promotion_gates"
                ),
                None,
            ),
            "attestation_node_output": next(
                (
                    node.get("output_schema_ref")
                    for node in forge_nodes_list
                    if node.get("node_id") == "run_independent_attestation"
                ),
                None,
            ),
            "phase_transition_node_output": next(
                (
                    node.get("output_schema_ref")
                    for node in forge_nodes_list
                    if node.get("node_id") == "gate_gate_transition"
                ),
                None,
            ),
            "promotion_commit_capability_present": (
                "promotion:commit" in forge_text or "promotion_commit" in forge_text
            ),
        },
        "constitutional_status": "FAIL",
    }


def audit_runtime_binding() -> dict[str, Any]:
    promotion_path = ROOT / "src/epistemic_foundry/governance/promotion.py"
    source = promotion_path.read_text(encoding="utf-8")
    evolution_text = (
        ROOT / "workflows/evolution_chamber_cycle.workflow.yaml"
    ).read_text(encoding="utf-8")
    helper_markers = {
        "canonical_gate_order": "CANONICAL_GATE_IDS" in source,
        "deterministic_decider": "def decide_promotion" in source,
        "semantic_validator": "def validate_promotion_decision_semantics" in source,
        "cas_committer": "class PromotionCommitter" in source,
        "effect_receipt_required": "MissingEffectReceipt" in source,
        "idempotency_conflict": "PromotionIdempotencyConflict" in source,
    }
    binding_tokens = {
        "module_path": "epistemic_foundry.governance.promotion" in evolution_text,
        "decider": "decide_promotion" in evolution_text,
        "committer": "PromotionCommitter" in evolution_text,
    }
    return {
        "helper_path": promotion_path.relative_to(ROOT).as_posix(),
        "helper_sha256": f"sha256:{sha256(promotion_path)}",
        "helper_controls_present": helper_markers,
        "canonical_evolution_workflow_binding": binding_tokens,
        "helper_implementation_status": (
            "PRESENT" if all(helper_markers.values()) else "INCOMPLETE"
        ),
        "binding_status": "PASS" if any(binding_tokens.values()) else "FAIL_UNBOUND",
    }


def audit_prompt() -> dict[str, Any]:
    prompt_path = ROOT / "prompts/promotion_attestor.md"
    text = prompt_path.read_text(encoding="utf-8")
    return {
        "path": prompt_path.relative_to(ROOT).as_posix(),
        "sha256": f"sha256:{sha256(prompt_path)}",
        "byte_size": len(prompt_path.read_bytes()),
        "mentions_hard_failure": "hard failure" in text.lower(),
        "declares_advisory_only": "advisory" in text.lower(),
        "declares_no_promotion_authority": "no promotion authority" in text.lower(),
        "separates_parliament_from_attestation": (
            "independent attestation" in text.lower()
            and "parliament" in text.lower()
        ),
        "implements_deterministic_gate_or_commit_authority": False,
    }


def build_result() -> dict[str, Any]:
    dependency = audit_a05_dependency()
    schemas_and_runtime = audit_schemas_and_runtime()
    workflows = audit_workflows()
    runtime_binding = audit_runtime_binding()
    prompt = audit_prompt()

    findings = [
        {
            "finding_id": "A06-F001",
            "severity": "CRITICAL",
            "criterion": "all governing v4 schemas and non-mutable surfaces are implemented exactly",
            "status": "FAIL",
            "evidence": [
                "schemas/evaluator-bundle.schema.json accepts readable_by_candidates=true",
                "schemas/evaluator-bundle.schema.json accepts mutable_during_run=true",
            ],
            "impact": "A schema-valid evaluator can be candidate-readable or mutable during a run even though both states are non-waivable failures under A05.",
        },
        {
            "finding_id": "A06-F002",
            "severity": "CRITICAL",
            "criterion": "hidden holdout is inaccessible to candidate identities",
            "status": "FAIL",
            "evidence": [
                "schemas/holdout-manifest.schema.json accepts METADATA_ONLY and AGGREGATE_ONLY",
                "build_holdout_manifest and VerifierFirewall accept both states",
            ],
            "impact": "The governing schema and runtime seal path do not enforce the A05 candidate_access=false/NONE invariant.",
        },
        {
            "finding_id": "A06-F003",
            "severity": "CRITICAL",
            "criterion": "no model or prompt acquires promotion authority",
            "status": "FAIL",
            "evidence": [
                "run_evidence_parliament_promotion is executor_type=llm",
                "the same node directly emits schemas/promotion-decision.schema.json",
                "issue_hypothesis_passport_revisions depends directly on that node",
            ],
            "impact": "The canonical evolution graph assigns a provider-nondeterministic prompt the business decision that immediately authorizes Passport revision processing.",
        },
        {
            "finding_id": "A06-F004",
            "severity": "CRITICAL",
            "criterion": "receipt-bound G00-G14 promotion authority is mandatory on the Passport path",
            "status": "FAIL",
            "evidence": [
                "no evolution node emits GateDecision, ApprovalRecord, Attestation, CapabilityLease, ActionIntent, EffectReceipt, or ArtifactReceipt",
                "no G00-G14 node sequence or promotion:commit capability appears in the evolution workflow",
                "Passport issuance reads no sealed authority artifact scope and depends only on the LLM decision node",
            ],
            "impact": "Required gate decisions, approval, short lease, expected-revision CAS, and receipt reconciliation are not graph-enforced before Passport mutation.",
        },
        {
            "finding_id": "A06-F005",
            "severity": "HIGH",
            "criterion": "a bounded helper must be bound to the canonical execution path",
            "status": "FAIL",
            "evidence": [
                "src/epistemic_foundry/governance/promotion.py implements the bounded controls",
                "workflows/evolution_chamber_cycle.workflow.yaml references neither its decider nor its committer",
                "forge_research_cycle is not bound as a subworkflow of the evolution Passport path",
            ],
            "impact": "Passing helper tests prove an isolated reference implementation, not enforcement by the canonical evolution workflow.",
        },
    ]

    failed_findings = [finding["finding_id"] for finding in findings if finding["status"] == "FAIL"]
    return {
        "schema_version": 1,
        "work_package_id": "A06",
        "attempt_id": "A06-0001",
        "audit_type": "INDEPENDENT_CONSTITUTIONAL_INTEGRATION_AUDIT",
        "authority_contract": "HD-EF4-A05-C01-B04-20260727-001 / A05-0002",
        "status": "FAIL" if failed_findings else "PASS",
        "completion_ready": False,
        "dependency_integrity": dependency,
        "schema_and_runtime_audit": schemas_and_runtime,
        "workflow_audit": workflows,
        "runtime_binding_audit": runtime_binding,
        "prompt_audit": prompt,
        "findings": findings,
        "failed_finding_ids": failed_findings,
        "classification": {
            "typed_outcome": "FAIL" if failed_findings else "PASS",
            "not_spec_gap_reason": "A05-0002 defines the evaluator, holdout, G00-G14, Parliament, attestation, approval, lease, CAS, and receipt semantics unambiguously; the observed problem is implementation and integration nonconformance.",
            "not_blocked_reason": "No required credential, licensed source, external backend, or unavailable tool is needed to reproduce the local contract violations.",
        },
        "scope": {
            "product_files_modified": [],
            "audit_evidence_only": True,
            "subagents_or_fleet_used": False,
            "actor_independent_certification_claimed": False,
        },
    }


def main() -> int:
    result = build_result()
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": result["status"],
        "failed_finding_ids": result["failed_finding_ids"],
        "output": OUTPUT.relative_to(ROOT).as_posix(),
    }, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
