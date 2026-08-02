"""Fixtures for the S05 threat-control suites.

The firewall, holdout and evaluator bundle are sealed through their own
builders so every fixture is a record those modules actually accept, and the
target manifest validates against its canonical schema — a fixture the schema
would refuse tests nothing but the fixture.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

RUN_ID = "ER-S05-9"
HIDDEN_HANDLE = "HP-1"
OOD_HANDLE = "OOD-1"
ADVERSARIAL_HANDLE = "ADV-1"
AUDITOR = "auditor-1"


def sealed_holdout(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_id": "EV-1",
        "split_strategy": "hash-partition",
        "public_partition_refs": ["PUB-1"],
        "hidden_partition_handles": [HIDDEN_HANDLE],
        "ood_partition_handles": [OOD_HANDLE],
        "adversarial_partition_handles": [ADVERSARIAL_HANDLE],
        "content_hashes": ["sha256:" + "c" * 64],
        "acl_policy_hash": "sha256:" + "d" * 64,
        "log_redaction_policy": "strip-holdout-refs",
        "cache_isolation_policy": "per-run-namespace",
        "holdout_id": "HO-1",
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
        "qualification_report_id": "EQR-1",
        "holdout_manifest_id": "HO-1",
        "evaluator_id": "EV-1",
        "sealed_at": "2026-08-02T00:00:00Z",
    }
    keywords.update(overrides)
    return build_evaluator_bundle(**keywords)


def firewall() -> VerifierFirewall:
    return VerifierFirewall(
        sealed_bundle(), sealed_holdout(), holdout_read_principal_ids=[AUDITOR]
    )


def empty_scope() -> dict[str, Any]:
    scope: dict[str, Any] = {
        key: None
        for key in (
            "domain",
            "population",
            "entity_type",
            "entity_subtype",
            "unit_of_analysis",
            "setting",
            "geography",
            "jurisdiction",
            "language",
            "lifecycle_stage",
            "spatial_scale",
            "temporal_scale",
            "time_period",
            "measurement_time",
            "intervention_or_exposure",
            "comparator",
        )
    }
    scope.update(
        {
            "inclusion_criteria": [],
            "exclusion_criteria": [],
            "conditions": {},
            "domain_extensions": {},
        }
    )
    return scope


def target_manifest(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "allowed_data_classes": ["internal"],
        "approval_policy": "high_risk_only",
        "artifact_hashes": ["sha256:" + "a" * 64],
        "capability_requirements": [],
        "constraints": [],
        "entrypoint": "run.py",
        "identifiability_notes": [],
        "inputs": [],
        "interface_version": "1.0.0",
        "network_policy": "disabled",
        "outputs": [],
        "parameters": [],
        "provenance_manifest_id": "PROV-1",
        "reproducibility_contract": {
            "container_digest_required": True,
            "environment_capture": True,
            "seed_control": True,
        },
        "safety_class": "bounded_compute",
        "sandbox_profile": "bounded_compute",
        "state_variables": [],
        "supply_chain_attestation_artifact_id": "ATT-1",
        "supported_actions": ["simulate"],
        "target_id": "vt-s05-target",
        "target_type": "simulation_model",
        "validation_scope": empty_scope(),
        "version": "1.0.0",
    }
    payload.update(overrides)
    return payload


def prompt_proposal(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "proposal_id": "PMP-1",
        "proposed_prompt_genome_id": "PG-NEW",
        "source_run_id": "ER-S05-1",
        "status": "QUARANTINED",
    }
    payload.update(overrides)
    return payload


def qualification_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "candidate_kind": "experiment-genome",
        "target_manifest": target_manifest(),
        "hard_limits": {"tokens": 100_000, "wall_seconds": 600},
        "effect_receipt_channel_id": "ER-CH-1",
        "firewall": firewall(),
        "qualification_id": "EXQ-S05-1",
    }
    arguments.update(overrides)
    return arguments
