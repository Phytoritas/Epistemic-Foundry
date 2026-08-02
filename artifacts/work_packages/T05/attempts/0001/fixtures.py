"""Fixtures for the T05 evolution backend adapter suites.

Every fixture is a record the surface it comes from actually accepts: the
firewall, holdout and evaluator bundle are sealed through the verifier
firewall's own builders, the validation-target manifest validates against its
canonical schema, and the execution qualification is produced by S05's real
`qualify_candidate_execution` rather than hand-written to look like one.  A
fixture the owning module would refuse tests nothing but the fixture.

Nothing here is randomized and no fixture reads a clock: every identifier and
timestamp is supplied, so the digests these suites re-derive are stable across
runs and across machines.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.adapters.v4_t05 import (
    import_shinka_run,
    pin_backend,
    qualification_statuses,
    qualify_backend_adapter,
)
from epistemic_foundry.security.v4_s05 import qualify_candidate_execution
from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

RUN_ID = "ER-T05-1"
AUDITOR = "auditor-t05"
SANDBOX_PROFILE = "bounded_compute"
IMPORTED_AT = "2026-08-02T00:00:00Z"
SEALED_AT = "2026-08-02T00:00:00Z"
COMMIT = "a" * 40
SNAPSHOT_HASH = "sha256:" + "b" * 64

#: The six capability dimensions the qualification schema requires, split so a
#: fixture can enable exactly the ones it claims.
ENABLED_FEATURES = (
    "candidate_count_reconciliation",
    "deterministic_seed",
    "effect_receipts",
    "evaluator_separation",
    "sandbox_isolation",
)
DISABLED_FEATURES = ("resume_integrity",)


def sealed_holdout(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_id": "EV-T05",
        "split_strategy": "hash-partition",
        "public_partition_refs": ["PUB-1"],
        "hidden_partition_handles": ["HP-1"],
        "ood_partition_handles": ["OOD-1"],
        "adversarial_partition_handles": ["ADV-1"],
        "content_hashes": ["sha256:" + "c" * 64],
        "acl_policy_hash": "sha256:" + "d" * 64,
        "log_redaction_policy": "strip-holdout-refs",
        "cache_isolation_policy": "per-run-namespace",
        "holdout_id": "HO-T05",
        "sealed_at": SEALED_AT,
    }
    keywords.update(overrides)
    return build_holdout_manifest(**keywords)


def sealed_bundle(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_version": "1.0.0",
        "code_artifact_id": "CA-T05",
        "code_hash": "sha256:" + "1" * 64,
        "metric_contract_hash": "sha256:" + "2" * 64,
        "environment_digest": "sha256:" + "3" * 64,
        "dependency_lock_hash": "sha256:" + "4" * 64,
        "data_contract_hash": "sha256:" + "5" * 64,
        "policy_bundle_hash": "sha256:" + "6" * 64,
        "qualification_report_id": "EQR-T05",
        "holdout_manifest_id": "HO-T05",
        "evaluator_id": "EV-T05",
        "sealed_at": SEALED_AT,
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
        "provenance_manifest_id": "PROV-T05",
        "reproducibility_contract": {
            "container_digest_required": True,
            "environment_capture": True,
            "seed_control": True,
        },
        "safety_class": SANDBOX_PROFILE,
        "sandbox_profile": SANDBOX_PROFILE,
        "state_variables": [],
        "supply_chain_attestation_artifact_id": "ATT-T05",
        "supported_actions": ["simulate"],
        "target_id": "vt-t05-target",
        "target_type": "simulation_model",
        "validation_scope": empty_scope(),
        "version": "1.0.0",
    }
    payload.update(overrides)
    return payload


def execution_qualification(**overrides: Any) -> dict[str, Any]:
    """A real S05 execution qualification for the executor profile."""
    keywords: dict[str, Any] = {
        "candidate_kind": "experiment-genome",
        "target_manifest": target_manifest(),
        "hard_limits": {"tokens": 100_000, "wall_seconds": 600},
        "effect_receipt_channel_id": "ER-CH-T05",
        "firewall": firewall(),
        "qualification_id": "EXQ-T05-1",
    }
    keywords.update(overrides)
    return qualify_candidate_execution(**keywords)


def backend_manifest(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "backend_manifest_id": "SBM-T05-1",
        "backend_name": "ShinkaEvolve",
        "source_repository": "https://example.invalid/shinka-evolve.git",
        "source_revision": COMMIT,
        "package_version": "0.3.1",
        "license": "Apache-2.0",
        "supported_candidate_types": ["experiment-genome", "hypothesis-genome"],
        "enabled_features": list(ENABLED_FEATURES),
        "disabled_features": list(DISABLED_FEATURES),
        "sandbox_profile_id": SANDBOX_PROFILE,
        "adapter_version": "4.0.0-t05.1",
    }
    keywords.update(overrides)
    return pin_backend(**keywords)


def capability_tests(**overrides: Any) -> dict[str, bool]:
    tests = {name: True for name in ENABLED_FEATURES}
    tests.update({name: False for name in DISABLED_FEATURES})
    tests.update(overrides)
    return tests


def binding_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "binding_id": "T05-BIND-1",
        "qualification_id": "BAQ-T05-1",
        "manifest": backend_manifest(),
        "capability_tests": capability_tests(),
        "known_limitations": ["resume integrity is not exercised by this build"],
        # Index 1 of the declared verdict vocabulary: the conditional verdict.
        # Read positionally so this fixture holds no schema enum literal.
        "status": qualification_statuses()[1],
        "allowed_release_level": "internal-preview",
        "execution_qualification": execution_qualification(),
    }
    arguments.update(overrides)
    return arguments


def binding(**overrides: Any) -> dict[str, Any]:
    return qualify_backend_adapter(**binding_arguments(**overrides))


def identities(count: int = 3) -> list[str]:
    return [f"cand-{index}" for index in range(count)]


def import_arguments(**overrides: Any) -> dict[str, Any]:
    reached = identities()
    arguments: dict[str, Any] = {
        "import_id": "IMP-T05-1",
        "source_run_id": "shinka-run-7",
        "target_session_id": "SES-T05-1",
        "source_version": "0.3.1",
        "target_version": "4.0.0",
        "source_snapshot_hash": SNAPSHOT_HASH,
        "migration_plan_id": "MIG-T05-1",
        "unconverted_fields": ["island_state", "operator_bandit"],
        "imported_at": IMPORTED_AT,
        "candidate_identities": {
            stage: list(reached)
            for stage in ("proposed", "generated", "evaluated", "persisted")
        },
    }
    arguments.update(overrides)
    return arguments


def imported_run(**overrides: Any) -> dict[str, Any]:
    return import_shinka_run(**import_arguments(**overrides))
