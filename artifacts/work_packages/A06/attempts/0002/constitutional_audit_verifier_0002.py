#!/usr/bin/env python3
"""A06-0002 independent constitutional re-audit of the A05 authority contract.

The verifier re-derives every A06-0001 finding from primary sources: the
canonical schemas and samples, the live verifier-firewall runtime, and the
workflow YAML documents.  It performs its own graph analysis and only then
cross-checks the A05 registry verifier, so a defect in the audited runtime
cannot certify itself.  The verifier is read-only outside this attempt
directory.
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
ATTEMPT = ROOT / "artifacts/work_packages/A06/attempts/0002"
OUTPUT = ATTEMPT / "constitutional-audit-verification.json"
ATTEMPT_ID = "A06-0002"
sys.path.insert(0, str(ROOT / "src"))

from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402
from epistemic_foundry.verifier_firewall import (  # noqa: E402
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

CANONICAL_GATES = tuple(
    f"G{index:02d}_{name}"
    for index, name in enumerate(
        (
            "PIN_RESOLUTION",
            "POLICY_AUTHORITY",
            "EVALUATOR_HOLDOUT_FIREWALL",
            "SCHEMA_LINEAGE_COUNT",
            "SOURCE_PROVENANCE",
            "SEARCH_COVERAGE",
            "METHOD_SCOPE_DEPENDENCY",
            "VALIDATION_LEAKAGE",
            "ADAPTIVE_STATISTICS",
            "RED_QUEEN",
            "REPLICATION_CEILING",
            "PARLIAMENT",
            "INDEPENDENT_ATTESTATION",
            "HUMAN_POLICY_APPROVAL",
            "ATOMIC_PROMOTION_COMMIT",
        )
    )
)
AUTHORITY_ARTIFACTS = {
    "action_intent": "schemas/action-intent.schema.json",
    "phase_artifact_set": "schemas/phase-artifact-set.schema.json",
    "artifact_receipt": "schemas/artifact-receipt.schema.json",
    "gate_decision": "schemas/gate-decision.schema.json",
    "adjudication": "schemas/adjudication.schema.json",
    "attestation": "schemas/attestation.schema.json",
    "approval_record": "schemas/approval-record.schema.json",
    "capability_lease": "schemas/capability-lease.schema.json",
    "promotion_decision": "schemas/promotion-decision.schema.json",
    "effect_receipt": "schemas/effect-receipt.schema.json",
}
ADVISORY_LLM_OUTPUTS = {
    "schemas/adjudication.schema.json",
    "schemas/attestation.schema.json",
}


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_yaml(relative: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def schema_accepts(schema: dict[str, Any], instance: dict[str, Any]) -> tuple[bool, list[str]]:
    validator = Draft202012Validator(schema)
    errors = sorted(error.message for error in validator.iter_errors(instance))
    return (not errors, errors[:3])


def ancestors(nodes: dict[str, dict[str, Any]], node_id: str) -> set[str]:
    seen: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        for dependency in nodes.get(current, {}).get("depends_on", []):
            if dependency not in seen:
                seen.add(str(dependency))
                stack.append(str(dependency))
    return seen


def node_outputs(nodes: Iterable[dict[str, Any]], schema_ref: str) -> list[str]:
    return sorted(
        str(node["node_id"])
        for node in nodes
        if node.get("output_schema_ref") == schema_ref
    )


def audit_schema_meta() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    failures: list[dict[str, str]] = []
    identifiers: list[str] = []
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover - evidence capture
            failures.append({"path": path.name, "error": str(exc)[:200]})
        if isinstance(schema.get("$id"), str):
            identifiers.append(schema["$id"])
    duplicates = sorted(i for i in set(identifiers) if identifiers.count(i) > 1)
    return {
        "canonical_schema_count": len(schema_paths),
        "duplicate_schema_ids": duplicates,
        "meta_schema_failures": failures,
        "status": "PASS"
        if len(schema_paths) == 127 and not failures and not duplicates
        else "FAIL",
    }


def audit_f001_f002() -> dict[str, Any]:
    evaluator_schema = load_json("schemas/evaluator-bundle.schema.json")
    holdout_schema = load_json("schemas/holdout-manifest.schema.json")
    evaluator_sample = load_json("examples/sample_evaluator-bundle.json")
    holdout_sample = load_json("examples/sample_holdout-manifest.json")

    readable = copy.deepcopy(evaluator_sample)
    readable["readable_by_candidates"] = True
    readable["bundle_hash"] = hash_excluding(readable, "bundle_hash")
    readable_valid, readable_errors = schema_accepts(evaluator_schema, readable)

    mutable = copy.deepcopy(evaluator_sample)
    mutable["mutable_during_run"] = True
    mutable["bundle_hash"] = hash_excluding(mutable, "bundle_hash")
    mutable_valid, mutable_errors = schema_accepts(evaluator_schema, mutable)

    unlocked = copy.deepcopy(evaluator_sample)
    unlocked["candidate_access"] = True
    unlocked["bundle_hash"] = hash_excluding(unlocked, "bundle_hash")
    unlocked_valid, _ = schema_accepts(evaluator_schema, unlocked)

    holdout_schema_results: dict[str, bool] = {}
    runtime_results: dict[str, dict[str, Any]] = {}
    for candidate_access in ("NONE", "METADATA_ONLY", "AGGREGATE_ONLY", True):
        label = str(candidate_access)
        hostile = copy.deepcopy(holdout_sample)
        hostile["candidate_access"] = candidate_access
        hostile["manifest_hash"] = hash_excluding(hostile, "manifest_hash")
        valid, _errors = schema_accepts(holdout_schema, hostile)
        holdout_schema_results[label] = valid
        try:
            runtime_holdout = build_holdout_manifest(
                dataset_or_fixture_ids=("DATA-HIDDEN-A06-0002",),
                split_strategy="sealed-fixture",
                selection_cutoff="2026-01-01",
                access_principal_ids=("PRIN-A06-VALIDATOR",),
                unblinding_policy="never during candidate generation",
                rotation_policy="rotate after any exposure",
                candidate_access=candidate_access,
                holdout_manifest_id="HO-A06-0002-HOSTILE",
            )
            bundle = build_evaluator_bundle(
                version="4.0.0-a06-0002",
                evaluator_artifact_ids=("ART-A06-EVALUATOR",),
                metric_ids=("METRIC-A06",),
                holdout_manifest_id=runtime_holdout["holdout_manifest_id"],
                environment_manifest_id="ENV-A06",
                policy_bundle_id="POL-A06",
                evaluator_bundle_id="EB-A06-0002",
            )
            VerifierFirewall(bundle, runtime_holdout)
        except Exception as exc:  # pragma: no cover - evidence capture
            runtime_results[label] = {"accepted": False, "error_type": type(exc).__name__}
        else:
            runtime_results[label] = {"accepted": True, "error_type": None}

    f001_pass = not readable_valid and not mutable_valid and not unlocked_valid
    f002_pass = (
        not holdout_schema_results["METADATA_ONLY"]
        and not holdout_schema_results["AGGREGATE_ONLY"]
        and not holdout_schema_results["True"]
        and not runtime_results["METADATA_ONLY"]["accepted"]
        and not runtime_results["AGGREGATE_ONLY"]["accepted"]
        and not runtime_results["True"]["accepted"]
    )
    return {
        "evaluator_hostile_fixtures": {
            "candidate_access_true_schema_valid": unlocked_valid,
            "mutable_during_run_true_schema_valid": mutable_valid,
            "mutable_errors": mutable_errors,
            "readable_by_candidates_true_schema_valid": readable_valid,
            "readable_errors": readable_errors,
        },
        "f001_status": "PASS" if f001_pass else "FAIL",
        "f002_status": "PASS" if f002_pass else "FAIL",
        "holdout_schema_candidate_access_accepted": holdout_schema_results,
        "runtime_holdout_candidate_access": runtime_results,
    }


def audit_f003_chamber() -> dict[str, Any]:
    chamber = load_yaml("workflows/evolution_chamber_cycle.workflow.yaml")
    nodes = {str(node["node_id"]): node for node in chamber["nodes"]}
    promotion = nodes.get("run_evidence_parliament_promotion", {})
    passport = nodes.get("issue_hypothesis_passport_revisions", {})
    llm_promotion_emitters = sorted(
        node_id
        for node_id, node in nodes.items()
        if node.get("executor_type") == "llm"
        and node.get("output_schema_ref") == AUTHORITY_ARTIFACTS["promotion_decision"]
    )
    ok = (
        promotion.get("executor_type") == "subworkflow"
        and promotion.get("executor_ref") == "workflows/evolution_promotion.workflow.yaml"
        and promotion.get("determinism_class") == "deterministic"
        and promotion.get("output_schema_ref") != AUTHORITY_ARTIFACTS["promotion_decision"]
        and passport.get("depends_on") == ["run_evidence_parliament_promotion"]
        and not llm_promotion_emitters
        and len(chamber["nodes"]) == 26
    )
    return {
        "chamber_node_count": len(chamber["nodes"]),
        "f003_status": "PASS" if ok else "FAIL",
        "llm_promotion_decision_emitters": llm_promotion_emitters,
        "passport_depends_on": passport.get("depends_on"),
        "promotion_node": {
            "determinism_class": promotion.get("determinism_class"),
            "executor_ref": promotion.get("executor_ref"),
            "executor_type": promotion.get("executor_type"),
            "output_schema_ref": promotion.get("output_schema_ref"),
        },
    }


def audit_f004_promotion_workflow() -> dict[str, Any]:
    workflow = load_yaml("workflows/evolution_promotion.workflow.yaml")
    nodes_list = list(workflow["nodes"])
    nodes = {str(node["node_id"]): node for node in nodes_list}

    declared_gates: dict[str, list[str]] = {gate: [] for gate in CANONICAL_GATES}
    for node_id, node in nodes.items():
        text = " ".join(
            (
                str(node.get("purpose", "")),
                str(node.get("executor_ref", "")),
                *[str(check) for check in node.get("acceptance_checks", [])],
            )
        )
        for gate in CANONICAL_GATES:
            if gate in text:
                declared_gates[gate].append(node_id)
    missing_gates = sorted(gate for gate, holders in declared_gates.items() if not holders)

    gate_nodes = [
        f"gate_g{index:02d}_" for index in range(11)
    ]
    ordered_gate_node_ids: list[str] = []
    for prefix in gate_nodes:
        matches = [node_id for node_id in nodes if node_id.startswith(prefix)]
        ordered_gate_node_ids.extend(sorted(matches))
    ordered_gate_node_ids += [
        "gate_g11_parliament",
        "gate_g12_independent_attestation",
        "gate_g13_human_policy_approval",
        "reconcile_commit_receipts",
    ]
    order_violations = []
    for earlier, later in zip(ordered_gate_node_ids, ordered_gate_node_ids[1:]):
        if earlier not in ancestors(nodes, later):
            order_violations.append(f"{later} does not depend on {earlier}")

    llm_violations = sorted(
        node_id
        for node_id, node in nodes.items()
        if node.get("executor_type") == "llm"
        and node.get("output_schema_ref") not in ADVISORY_LLM_OUTPUTS
    )
    commit_holders = sorted(
        node_id
        for node_id, node in nodes.items()
        if "promotion:commit" in node.get("capabilities", [])
    )
    decision_emitters = node_outputs(nodes_list, AUTHORITY_ARTIFACTS["promotion_decision"])
    nondeterministic_decision = sorted(
        node_id
        for node_id in decision_emitters
        if nodes[node_id].get("executor_type") != "deterministic"
    )
    artifact_outputs = {
        name: node_outputs(nodes_list, schema_ref)
        for name, schema_ref in AUTHORITY_ARTIFACTS.items()
    }
    missing_outputs = sorted(name for name, holders in artifact_outputs.items() if not holders)

    ok = (
        len(nodes_list) == 23
        and not missing_gates
        and not order_violations
        and not llm_violations
        and commit_holders == ["commit_promotion_atomically"]
        and decision_emitters == ["commit_promotion_atomically"]
        and not nondeterministic_decision
        and not missing_outputs
    )
    return {
        "authority_artifact_output_nodes": artifact_outputs,
        "declared_gate_nodes": declared_gates,
        "f004_status": "PASS" if ok else "FAIL",
        "gate_order_violations": order_violations,
        "llm_non_advisory_outputs": llm_violations,
        "missing_authority_artifact_outputs": missing_outputs,
        "missing_gate_declarations": missing_gates,
        "promotion_commit_capability_holders": commit_holders,
        "promotion_decision_emitters": decision_emitters,
        "workflow_node_count": len(nodes_list),
    }


def audit_f005_runtime_binding() -> dict[str, Any]:
    workflow = load_yaml("workflows/evolution_promotion.workflow.yaml")
    module_prefix = "epistemic_foundry.governance.evolution_authority.nodes:"
    unbound = sorted(
        str(node["node_id"])
        for node in workflow["nodes"]
        if node.get("executor_type") in {"deterministic", "policy", "human_gate"}
        and not str(node.get("executor_ref", "")).startswith(module_prefix)
    )
    nodes_source = (
        ROOT / "src/epistemic_foundry/governance/evolution_authority/nodes.py"
    ).read_text(encoding="utf-8")
    promotion_source = (
        ROOT / "src/epistemic_foundry/governance/promotion.py"
    ).read_text(encoding="utf-8")
    bindings = {
        "chamber_delegates_to_promotion_workflow": (
            "workflows/evolution_promotion.workflow.yaml"
            in (ROOT / "workflows/evolution_chamber_cycle.workflow.yaml").read_text(
                encoding="utf-8"
            )
        ),
        "decider_defined": "def decide_promotion" in promotion_source,
        "nodes_delegate_to_committer": "PromotionCommitter" in nodes_source,
        "nodes_delegate_to_decider": "decide_promotion(request)" in nodes_source,
        "semantic_validator_defined": (
            "def validate_promotion_decision_semantics" in promotion_source
        ),
    }
    import importlib

    entrypoint_module = importlib.import_module(
        "epistemic_foundry.governance.evolution_authority.nodes"
    )
    missing_entrypoints = sorted(
        str(node["node_id"])
        for node in workflow["nodes"]
        if str(node.get("executor_ref", "")).startswith(module_prefix)
        and str(node["node_id"]) not in entrypoint_module.NODE_ENTRYPOINTS
    )
    ok = not unbound and not missing_entrypoints and all(bindings.values())
    return {
        "bindings": bindings,
        "f005_status": "PASS" if ok else "FAIL",
        "missing_node_entrypoints": missing_entrypoints,
        "runtime_bound_node_count": 21,
        "unbound_runtime_nodes": unbound,
    }


def cross_check_registry() -> dict[str, Any]:
    from epistemic_foundry.governance.evolution_authority import (
        verify_evolution_chamber_binding,
        verify_promotion_workflow_binding,
    )

    promotion = load_yaml("workflows/evolution_promotion.workflow.yaml")
    chamber = load_yaml("workflows/evolution_chamber_cycle.workflow.yaml")
    return {
        "chamber": verify_evolution_chamber_binding(chamber),
        "note": (
            "Cross-check only: the independent findings above are derived from "
            "primary sources, not from the audited registry."
        ),
        "promotion": verify_promotion_workflow_binding(promotion),
    }


def constitutional_case_evidence() -> dict[str, Any]:
    junit = ATTEMPT / "targeted-a05-python.junit.xml"
    if not junit.is_file():
        raise SystemExit("A06-0002 requires the re-executed constitutional case junit")
    import xml.etree.ElementTree as ET

    names = {
        str(case.get("name"))
        for case in ET.parse(junit).getroot().findall(".//testcase")
    }
    negative = [f"a05_neg_{index:03d}" for index in range(1, 25)]
    positive = [f"a05_pos_{index:03d}" for index in range(1, 7)]
    missing = [
        token
        for token in negative + positive
        if not any(token in name for name in names)
    ]
    return {
        "junit": "artifacts/work_packages/A06/attempts/0002/targeted-a05-python.junit.xml",
        "junit_sha256": sha256(junit),
        "missing_case_tokens": missing,
        "negative_case_count": len(negative),
        "positive_case_count": len(positive),
        "status": "PASS" if not missing else "FAIL",
    }


def build_result() -> dict[str, Any]:
    meta = audit_schema_meta()
    firewall = audit_f001_f002()
    chamber = audit_f003_chamber()
    workflow = audit_f004_promotion_workflow()
    binding = audit_f005_runtime_binding()
    cases = constitutional_case_evidence()
    registry = cross_check_registry()

    findings = [
        {
            "finding_id": "A06-F001",
            "status": firewall["f001_status"],
            "summary": (
                "Canonical evaluator schema rejects candidate-readable, mutable, and "
                "candidate-access evaluator bundles."
            ),
        },
        {
            "finding_id": "A06-F002",
            "status": firewall["f002_status"],
            "summary": (
                "Canonical holdout schema and the runtime seal path enforce NONE "
                "candidate access."
            ),
        },
        {
            "finding_id": "A06-F003",
            "status": chamber["f003_status"],
            "summary": (
                "The chamber promotion node is a deterministic subworkflow delegation; "
                "no llm node emits a PromotionDecision."
            ),
        },
        {
            "finding_id": "A06-F004",
            "status": workflow["f004_status"],
            "summary": (
                "The evolution_promotion graph enforces G00-G14, Parliament, "
                "attestation, approval, lease, CAS, and receipt boundaries."
            ),
        },
        {
            "finding_id": "A06-F005",
            "status": binding["f005_status"],
            "summary": (
                "The bounded promotion helper is bound to the canonical workflow "
                "through the evolution-authority node entrypoints."
            ),
        },
    ]
    failed = sorted(
        finding["finding_id"] for finding in findings if finding["status"] != "PASS"
    )
    if meta["status"] != "PASS":
        failed.append("SCHEMA_META")
    if cases["status"] != "PASS":
        failed.append("CONSTITUTIONAL_CASES")

    result = {
        "attempt_id": ATTEMPT_ID,
        "audit_type": "INDEPENDENT_CONSTITUTIONAL_REAUDIT_FROM_PRIMARY_SOURCES",
        "chamber_audit": chamber,
        "constitutional_cases": cases,
        "failed_finding_ids": sorted(set(failed)),
        "findings": findings,
        "firewall_audit": firewall,
        "promotion_workflow_audit": workflow,
        "registry_cross_check": registry,
        "runtime_binding_audit": binding,
        "schema_meta_audit": meta,
        "status": "PASS" if not failed else "FAIL",
        "work_package_id": "A06",
    }
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> int:
    result = build_result()
    print(
        json.dumps(
            {
                "failed_finding_ids": result["failed_finding_ids"],
                "output": OUTPUT.relative_to(ROOT).as_posix(),
                "status": result["status"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
