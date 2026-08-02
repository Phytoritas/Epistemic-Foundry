"""Fixtures for the T06 backend integration gate suites.

Every input is a record the surface it comes from actually accepts.  The
evaluator bundle and holdout are sealed through the verifier firewall's own
builders, the execution qualification is produced by S05's real
`qualify_candidate_execution`, and the backend bindings are produced by T05's
`qualify_backend_adapter` rather than hand-written to look like one.  T06 is a
gate over T05's records, so a hand-forged binding would let these suites pass
while the composition they exist to prove was never exercised.

Two backends are built, not one.  A fallback chain with a single member cannot
show that a substitute is qualified separately from the primary, and cannot
show that degrading is recorded, so the whole second half of this package would
be untestable against one backend.

Nothing here is randomized and no fixture reads a clock: every identifier and
instant is supplied, so every digest these suites re-derive is stable across
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
from epistemic_foundry.adapters.v4_t06 import (
    backend_member,
    build_chain,
    declare_fallback_chain,
    native_core_member,
    open_qualification,
    requalify,
)
from epistemic_foundry.security.v4_s05 import qualify_candidate_execution
from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

AUDITOR = "auditor-t06"
SANDBOX_PROFILE = "bounded_compute"
SEALED_AT = "2026-08-02T00:00:00Z"

PRIMARY_MANIFEST_ID = "SBM-T06-PRIMARY"
STANDBY_MANIFEST_ID = "SBM-T06-STANDBY"
PRIMARY_COMMIT = "a" * 40
STANDBY_COMMIT = "b" * 40
SNAPSHOT_HASH = "sha256:" + "c" * 64

#: Validity windows, and the instants that fall inside and outside them.  The
#: standby outlives the primary on purpose: a fallback that expired at the same
#: moment as the thing it substitutes for could never be shown to serve.  Every
#: expiry judgement in these suites is made against one of these instants rather
#: than against a clock.
ISSUED_AT = "2026-08-02T00:00:00+00:00"
EXPIRES_AT = "2026-09-01T00:00:00+00:00"
STANDBY_EXPIRES_AT = "2026-10-01T00:00:00+00:00"
WITHIN_WINDOW = "2026-08-15T00:00:00+00:00"
AFTER_EXPIRY = "2026-09-02T00:00:00+00:00"
AFTER_STANDBY_EXPIRY = "2026-10-02T00:00:00+00:00"
REQUALIFIED_AT = "2026-08-20T00:00:00+00:00"
REQUALIFIED_EXPIRES_AT = "2026-10-01T00:00:00+00:00"

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

#: What a routed request asks the chain for.  The standby holds a strict subset
#: and the core holds none, which is the only shape a fallback may take.
PRIMARY_CAPABILITIES = ("candidate-search", "genome-mutation")
STANDBY_CAPABILITIES = ("candidate-search",)
REQUESTED_CAPABILITIES = ("candidate-search", "genome-mutation")


def sealed_holdout(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_id": "EV-T06",
        "split_strategy": "hash-partition",
        "public_partition_refs": ["PUB-1"],
        "hidden_partition_handles": ["HP-1"],
        "ood_partition_handles": ["OOD-1"],
        "adversarial_partition_handles": ["ADV-1"],
        "content_hashes": ["sha256:" + "d" * 64],
        "acl_policy_hash": "sha256:" + "e" * 64,
        "log_redaction_policy": "strip-holdout-refs",
        "cache_isolation_policy": "per-run-namespace",
        "holdout_id": "HO-T06",
        "sealed_at": SEALED_AT,
    }
    keywords.update(overrides)
    return build_holdout_manifest(**keywords)


def sealed_bundle(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_version": "1.0.0",
        "code_artifact_id": "CA-T06",
        "code_hash": "sha256:" + "1" * 64,
        "metric_contract_hash": "sha256:" + "2" * 64,
        "environment_digest": "sha256:" + "3" * 64,
        "dependency_lock_hash": "sha256:" + "4" * 64,
        "data_contract_hash": "sha256:" + "5" * 64,
        "policy_bundle_hash": "sha256:" + "6" * 64,
        "qualification_report_id": "EQR-T06",
        "holdout_manifest_id": "HO-T06",
        "evaluator_id": "EV-T06",
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
        "provenance_manifest_id": "PROV-T06",
        "reproducibility_contract": {
            "container_digest_required": True,
            "environment_capture": True,
            "seed_control": True,
        },
        "safety_class": SANDBOX_PROFILE,
        "sandbox_profile": SANDBOX_PROFILE,
        "state_variables": [],
        "supply_chain_attestation_artifact_id": "ATT-T06",
        "supported_actions": ["simulate"],
        "target_id": "vt-t06-target",
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
        "effect_receipt_channel_id": "ER-CH-T06",
        "firewall": firewall(),
        "qualification_id": "EXQ-T06-1",
    }
    keywords.update(overrides)
    return qualify_candidate_execution(**keywords)


def backend_manifest(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "backend_manifest_id": PRIMARY_MANIFEST_ID,
        "backend_name": "ShinkaEvolve",
        "source_repository": "https://example.invalid/shinka-evolve.git",
        "source_revision": PRIMARY_COMMIT,
        "package_version": "0.3.1",
        "license": "Apache-2.0",
        "supported_candidate_types": ["experiment-genome", "hypothesis-genome"],
        "enabled_features": list(ENABLED_FEATURES),
        "disabled_features": list(DISABLED_FEATURES),
        "sandbox_profile_id": SANDBOX_PROFILE,
        "adapter_version": "4.0.0-t06.1",
    }
    keywords.update(overrides)
    return pin_backend(**keywords)


def capability_tests(**overrides: Any) -> dict[str, bool]:
    tests = {name: True for name in ENABLED_FEATURES}
    tests.update({name: False for name in DISABLED_FEATURES})
    tests.update(overrides)
    return tests


def usable_status(position: int = 1) -> str:
    """A verdict that permits serving, chosen positionally.

    Read from the schema's own ordering rather than named, so this fixture
    holds no canonical enum literal.  Position 0 is the strongest verdict and
    position 1 the conditional one; both permit use.
    """
    return qualification_statuses()[position]


def rejecting_status() -> str:
    """The verdict that never permits serving, again chosen positionally."""
    return qualification_statuses()[2]


def binding(**overrides: Any) -> dict[str, Any]:
    """A sealed T05 binding for the primary backend."""
    arguments: dict[str, Any] = {
        "binding_id": "T06-BIND-1",
        "qualification_id": "BAQ-T06-1",
        "manifest": backend_manifest(),
        "capability_tests": capability_tests(),
        "known_limitations": ["resume integrity is not exercised by this build"],
        "status": usable_status(),
        "allowed_release_level": "internal-preview",
        "execution_qualification": execution_qualification(),
    }
    arguments.update(overrides)
    return qualify_backend_adapter(**arguments)


def standby_binding(**overrides: Any) -> dict[str, Any]:
    """A sealed T05 binding for a second, independently qualified backend."""
    arguments: dict[str, Any] = {
        "binding_id": "T06-BIND-STANDBY",
        "qualification_id": "BAQ-T06-STANDBY",
        "manifest": backend_manifest(
            backend_manifest_id=STANDBY_MANIFEST_ID,
            source_revision=STANDBY_COMMIT,
            package_version="0.3.2",
        ),
        "capability_tests": capability_tests(),
        "known_limitations": ["standby build; resume integrity is not exercised"],
        "status": usable_status(),
        "allowed_release_level": "internal-preview",
        "execution_qualification": execution_qualification(),
    }
    arguments.update(overrides)
    return qualify_backend_adapter(**arguments)


def genesis(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "lifecycle_id": "T06-LIFE-1",
        "binding": binding(),
        "issued_at": ISSUED_AT,
        "expires_at": EXPIRES_AT,
    }
    keywords.update(overrides)
    return open_qualification(**keywords)


def chain(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {"chain_id": "T06-CHAIN-1", "records": [genesis()]}
    keywords.update(overrides)
    return build_chain(**keywords)


def standby_chain(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "chain_id": "T06-CHAIN-STANDBY",
        "records": [
            open_qualification(
                lifecycle_id="T06-LIFE-STANDBY",
                binding=standby_binding(),
                issued_at=ISSUED_AT,
                expires_at=STANDBY_EXPIRES_AT,
            )
        ],
    }
    keywords.update(overrides)
    return build_chain(**keywords)


def second_binding(**overrides: Any) -> dict[str, Any]:
    """A distinct T05 binding for the same backend, for requalification."""
    arguments: dict[str, Any] = {
        "binding_id": "T06-BIND-2",
        "qualification_id": "BAQ-T06-2",
    }
    arguments.update(overrides)
    return binding(**arguments)


def requalified(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "previous": genesis(),
        "binding": second_binding(),
        "issued_at": REQUALIFIED_AT,
        "expires_at": REQUALIFIED_EXPIRES_AT,
    }
    keywords.update(overrides)
    return requalify(**keywords)


def requalified_chain(**overrides: Any) -> dict[str, Any]:
    first = genesis()
    keywords: dict[str, Any] = {
        "chain_id": "T06-CHAIN-1",
        "records": [first, requalified(previous=first)],
    }
    keywords.update(overrides)
    return build_chain(**keywords)


def rejecting_chain(**overrides: Any) -> dict[str, Any]:
    """A chain whose only verdict never permitted serving."""
    keywords: dict[str, Any] = {
        "chain_id": "T06-CHAIN-REJECTED",
        "records": [
            open_qualification(
                lifecycle_id="T06-LIFE-REJECTED",
                binding=binding(
                    binding_id="T06-BIND-REJECTED",
                    qualification_id="BAQ-T06-REJECTED",
                    status=rejecting_status(),
                ),
                issued_at=ISSUED_AT,
                expires_at=EXPIRES_AT,
            )
        ],
    }
    keywords.update(overrides)
    return build_chain(**keywords)


def members(**overrides: Any) -> list[dict[str, Any]]:
    declared: dict[str, Any] = {
        "primary": backend_member(
            member_id="primary-backend",
            chain=chain(),
            capabilities=list(PRIMARY_CAPABILITIES),
        ),
        "standby": backend_member(
            member_id="standby-backend",
            chain=standby_chain(),
            capabilities=list(STANDBY_CAPABILITIES),
        ),
        "core": native_core_member(),
    }
    declared.update(overrides)
    return [declared["primary"], declared["standby"], declared["core"]]


def fallback_chain(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {"chain_id": "T06-FALL-1", "members": members()}
    keywords.update(overrides)
    return declare_fallback_chain(**keywords)


def identities(count: int = 3) -> list[str]:
    return [f"cand-{index}" for index in range(count)]


def imported_run(**overrides: Any) -> dict[str, Any]:
    reached = identities()
    arguments: dict[str, Any] = {
        "import_id": "IMP-T06-1",
        "source_run_id": "shinka-run-11",
        "target_session_id": "SES-T06-1",
        "source_version": "0.3.1",
        "target_version": "4.0.0",
        "source_snapshot_hash": SNAPSHOT_HASH,
        "migration_plan_id": "MIG-T06-1",
        "unconverted_fields": ["island_state", "operator_bandit"],
        "imported_at": ISSUED_AT,
        "candidate_identities": {
            stage: list(reached)
            for stage in ("proposed", "generated", "evaluated", "persisted")
        },
    }
    arguments.update(overrides)
    return import_shinka_run(**arguments)
