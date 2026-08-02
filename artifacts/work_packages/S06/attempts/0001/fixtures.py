"""Fixtures for the S06 governance-integration gate suites.

Every fixture is a record its owning module actually accepts: the firewall,
holdout and evaluator bundle are sealed through the S05/firewall builders, the
evaluator mutation proposal through the governance quarantine builder, and the
fitness vector, routing receipt and qualification report validate against their
canonical schemas — a fixture the schema would refuse tests nothing but itself.

Test fixtures are outside ``src`` and may name canonical tokens directly; the
wire-literal discipline (EF4-I22) applies to the shipped gate, not to a fixture
that must construct a record carrying a specific status.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.governance.quarantine import build_evaluator_mutation_proposal
from epistemic_foundry.security.v4_s05 import required_leakage_surfaces
from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

RUN_ID = "ER-S06-7"
FUTURE_RUN_ID = "ER-S06-8"
HIDDEN_HANDLE = "HP-1"
OOD_HANDLE = "OOD-1"
ADVERSARIAL_HANDLE = "ADV-1"
AUDITOR = "auditor-1"
CURRENT_BUNDLE_ID = "EV-CURRENT"
FUTURE_BUNDLE_ID = "EV-FUTURE"

#: Canonical tokens named directly because a fixture must build a record that
#: carries them; the gate itself reads these positionally from the schema.
APPROVED_FOR_FUTURE = "APPROVED_FOR_FUTURE"
QUARANTINED = "QUARANTINED"
QUALIFIED = "QUALIFIED"
REJECTED = "REJECTED"
PASS = "PASS"
FAIL = "FAIL"
IMMEDIATE_PROXY = "immediate_proxy"
DELAYED_HOLDOUT = "delayed_holdout"

DIMENSION_KEYS = (
    "grounding",
    "support",
    "counterevidence_resistance",
    "predictive_accuracy",
    "calibration",
    "robustness",
    "causal_identifiability",
    "falsifiability",
    "novelty",
    "parsimony",
    "information_gain",
    "coverage_value",
    "replicability",
    "cost_efficiency",
    "safety",
)


def sealed_holdout(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_id": CURRENT_BUNDLE_ID,
        "split_strategy": "hash-partition",
        "public_partition_refs": ["PUB-1"],
        "hidden_partition_handles": [HIDDEN_HANDLE],
        "ood_partition_handles": [OOD_HANDLE],
        "adversarial_partition_handles": [ADVERSARIAL_HANDLE],
        "content_hashes": ["sha256:" + "c" * 64],
        "acl_policy_hash": "sha256:" + "d" * 64,
        "log_redaction_policy": "strip-holdout-refs",
        "cache_isolation_policy": "per-run-namespace",
        "holdout_id": "HO-6",
        "sealed_at": "2026-08-02T00:00:00Z",
    }
    keywords.update(overrides)
    return build_holdout_manifest(**keywords)


def sealed_bundle(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_version": "1.0.0",
        "code_artifact_id": "CA-1",
        "code_hash": "sha256:" + "1" * 64,
        "metric_contract_hash": "sha256:" + "2" * 64,
        "environment_digest": "sha256:" + "3" * 64,
        "dependency_lock_hash": "sha256:" + "4" * 64,
        "data_contract_hash": "sha256:" + "5" * 64,
        "policy_bundle_hash": "sha256:" + "6" * 64,
        "qualification_report_id": "EQR-CURRENT",
        "holdout_manifest_id": "HO-6",
        "evaluator_id": CURRENT_BUNDLE_ID,
        "sealed_at": "2026-08-02T00:00:00Z",
    }
    keywords.update(overrides)
    return build_evaluator_bundle(**keywords)


def firewall(**overrides: Any) -> VerifierFirewall:
    principals = overrides.pop("holdout_read_principal_ids", [AUDITOR])
    return VerifierFirewall(
        sealed_bundle(), sealed_holdout(), holdout_read_principal_ids=principals
    )


def leaky_firewall() -> VerifierFirewall:
    """A firewall whose allowlist wrongly grants a candidate-generating role.

    The manifest is still clean; only the runtime principal list is misconfigured
    so ``may_read_holdout`` would return true for a generator if the firewall did
    not deny generators unconditionally.  Used to exercise the reachability probe.
    """
    return VerifierFirewall(
        sealed_bundle(),
        sealed_holdout(),
        holdout_read_principal_ids=["S06-HOLDOUT-DENIAL-PROBE"],
    )


def fitness_vector(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "fitness_vector_id": "FV-1",
        "candidate_id": "CAND-1",
        "hard_gate_status": PASS,
        "hard_gate_failures": [],
        "dimensions": {key: 0.5 for key in DIMENSION_KEYS},
        "uncertainty": {key: 0.1 for key in DIMENSION_KEYS},
        "evidence_receipt_ids": ["FER-1"],
        "pareto_rank": 0,
        "domination_count": 0,
        "computed_at": "2026-08-02T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def routing_receipt(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "receipt_id": "MRR-1",
        "task_class": "hypothesis_mutation",
        "eligible_model_ids": ["m-a", "m-b"],
        "selected_model_id": "m-a",
        "policy": "ucb",
        "reward_basis": DELAYED_HOLDOUT,
        "estimated_cost": 0.02,
        "estimated_latency_ms": 1200,
        "exploration_probability": 0.1,
        "safety_constraints": ["no-network"],
        "receipt_hash": "sha256:" + "a" * 64,
    }
    payload.update(overrides)
    return payload


def evaluator_proposal(**overrides: Any) -> dict[str, Any]:
    """A future-only evaluator proposal, approved for a future run.

    Built through the governance quarantine so the future-only flags are the
    ones that builder forces, then advanced to the approved status and re-sealed.
    """
    status = overrides.pop("status", APPROVED_FOR_FUTURE)
    keywords: dict[str, Any] = {
        "proposal_id": "EMP-S06-1",
        "source_run_id": RUN_ID,
        "current_evaluator_bundle_id": CURRENT_BUNDLE_ID,
        "defect_class": "false_negative",
        "evidence_artifact_ids": ["EV-DEFECT-1"],
        "proposed_change": "tighten the counterevidence rubric",
    }
    keywords.update(overrides)
    proposal = build_evaluator_mutation_proposal(**keywords)
    proposal["status"] = status
    proposal["proposal_hash"] = hash_excluding(proposal, "proposal_hash")
    return proposal


def qualification_report(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "report_id": "EQR-FUTURE",
        "evaluator_bundle_id": FUTURE_BUNDLE_ID,
        "baseline_comparison": "current-vs-shadow",
        "metamorphic_pass_rate": 0.98,
        "adversarial_pass_rate": 0.95,
        "leakage_audit_id": "LKA-FUTURE",
        "calibration_report_id": "CAL-FUTURE",
        "known_blind_spots": [],
        "qualification_status": QUALIFIED,
        "promotion_ceiling": "REPLICATED",
        "report_hash": "sha256:" + "b" * 64,
    }
    payload.update(overrides)
    return payload


def clean_surfaces() -> list[str]:
    """The minimum leakage surfaces EF4-I44 names, read from the invariant."""
    return list(required_leakage_surfaces())


def reward_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "fitness_vector": fitness_vector(),
        "routing_receipt": routing_receipt(),
        "firewall": firewall(),
        "run_or_bundle_id": RUN_ID,
        "feedback_artifact_ids": ["FB-1", "FB-2"],
        "surfaces_checked": clean_surfaces(),
        "access_log_artifact_id": "ACL-1",
    }
    arguments.update(overrides)
    return arguments


def evaluator_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "proposal": evaluator_proposal(),
        "target_run_id": FUTURE_RUN_ID,
        "qualification_report": qualification_report(),
        "firewall": firewall(),
    }
    arguments.update(overrides)
    return arguments
