"""EF4-I50 semantic islands and EF4-I64 the executable candidate sandbox."""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import sha256_of_payload
from epistemic_foundry.epistemic_species_archive.islands import (
    SPECIALIZATION_AXES,
    IslandPolicyViolation,
    MigrationRefused,
    build_island_state,
    migrate_candidate,
    migration_blockers,
    migration_history_preserved,
    specialization,
)
from epistemic_foundry.security.sandbox import (
    FORBIDDEN_CANDIDATE_CAPABILITIES,
    REQUIRED_QUOTAS,
    SandboxRefused,
    build_capability_lease,
    build_execution_receipt,
    build_sandbox_profile,
    execution_blockers,
    execution_is_accounted,
    require_execution_permitted,
)

QUOTAS = {
    "wall_clock_seconds": 60,
    "cpu_seconds": 45,
    "memory_bytes": 512 * 1024 * 1024,
    "disk_write_bytes": 10 * 1024 * 1024,
    "process_count": 4,
}


def an_island(**overrides: object) -> dict:
    kwargs: dict = {
        "evolution_run_id": "ERUN-1",
        "axis": "mechanism",
        "value": "stomatal-limitation",
        "candidate_ids": ["CAND-1", "CAND-2"],
        "archive_entry_ids": ["AE-1"],
        "generation": 3,
        "migration_policy": "ring-every-5-generations",
        "stagnation_rounds": 2,
    }
    kwargs.update(overrides)
    return build_island_state(**kwargs)  # type: ignore[arg-type]


# -- EF4-I50 typed specialization ----------------------------------------


def test_i50_specialization_axes_match_the_invariant() -> None:
    assert SPECIALIZATION_AXES == ("mechanism", "scope", "method", "evidence_state")


def test_i50_specialization_is_axis_qualified() -> None:
    assert specialization("scope", "greenhouse") == "scope:greenhouse"


def test_i50_untyped_axis_is_refused() -> None:
    with pytest.raises(IslandPolicyViolation) as excinfo:
        specialization("vibes", "something")
    assert "is not typed" in str(excinfo.value)


def test_i50_empty_specialization_value_is_refused() -> None:
    with pytest.raises(IslandPolicyViolation):
        specialization("mechanism", "   ")


def test_i50_island_without_a_migration_policy_is_refused() -> None:
    with pytest.raises(IslandPolicyViolation) as excinfo:
        an_island(migration_policy="")
    assert "migration policy" in str(excinfo.value)


def test_i50_outgoing_migrant_cannot_remain_a_resident() -> None:
    """One candidate counted on two islands inflates both occupancies."""
    with pytest.raises(IslandPolicyViolation) as excinfo:
        an_island(outgoing_migrant_ids=["CAND-1"])
    assert "counted on two islands" in str(excinfo.value)


# -- EF4-I50 compatibility-gated migration -------------------------------


def test_i50_migration_between_comparable_islands_succeeds() -> None:
    source = an_island()
    target = an_island(value="hydraulic-limitation", candidate_ids=["CAND-9"])
    new_source, new_target = migrate_candidate(source, target, candidate_id="CAND-1")
    assert migration_history_preserved(new_source, new_target, candidate_id="CAND-1")


def test_i50_both_sides_record_the_migration() -> None:
    source = an_island()
    target = an_island(value="hydraulic-limitation", candidate_ids=["CAND-9"])
    new_source, new_target = migrate_candidate(source, target, candidate_id="CAND-1")
    assert new_source["outgoing_migrant_ids"] == ["CAND-1"]
    assert new_target["incoming_migrant_ids"] == ["CAND-1"]
    assert "CAND-1" not in new_source["candidate_ids"]
    assert "CAND-1" in new_target["candidate_ids"]


def test_i50_one_sided_history_is_not_preserved_history() -> None:
    """A migrant recorded only on arrival reads as native to its new island."""
    source = an_island(candidate_ids=["CAND-2"])
    target = an_island(value="hydraulic-limitation", candidate_ids=["CAND-9", "CAND-1"],
                       incoming_migrant_ids=["CAND-1"])
    assert migration_history_preserved(source, target, candidate_id="CAND-1") is False


def test_i50_migration_across_axes_is_refused() -> None:
    source = an_island()
    target = an_island(axis="method", value="randomized-trial", candidate_ids=["CAND-9"])
    with pytest.raises(MigrationRefused) as excinfo:
        migrate_candidate(source, target, candidate_id="CAND-1")
    assert "not comparable" in str(excinfo.value)


def test_i50_migration_into_an_identical_specialization_is_refused() -> None:
    source = an_island()
    target = an_island(candidate_ids=["CAND-9"])
    with pytest.raises(MigrationRefused) as excinfo:
        migrate_candidate(source, target, candidate_id="CAND-1")
    assert "would not diversify" in str(excinfo.value)


def test_i50_cross_run_migration_is_refused() -> None:
    source = an_island()
    target = an_island(
        evolution_run_id="ERUN-2", value="hydraulic-limitation", candidate_ids=["CAND-9"]
    )
    with pytest.raises(MigrationRefused) as excinfo:
        migrate_candidate(source, target, candidate_id="CAND-1")
    assert "different evolution runs" in str(excinfo.value)


def test_i50_non_resident_candidate_cannot_migrate() -> None:
    source = an_island()
    target = an_island(value="hydraulic-limitation", candidate_ids=["CAND-9"])
    with pytest.raises(MigrationRefused) as excinfo:
        migrate_candidate(source, target, candidate_id="CAND-absent")
    assert "not resident" in str(excinfo.value)


def test_i50_every_blocker_is_reported_together() -> None:
    source = an_island()
    target = an_island(
        evolution_run_id="ERUN-2", axis="scope", value="field", candidate_ids=["CAND-9"]
    )
    blockers = migration_blockers(source, target, candidate_id="CAND-absent")
    assert len(blockers) == 3


def test_i50_receiving_a_migrant_does_not_reset_stagnation() -> None:
    """Inbound traffic is not progress; a dead island stays visibly dead."""
    source = an_island()
    target = an_island(
        value="hydraulic-limitation", candidate_ids=["CAND-9"], stagnation_rounds=7
    )
    _, new_target = migrate_candidate(source, target, candidate_id="CAND-1")
    assert new_target["stagnation_rounds"] == 7


# -- EF4-I64 sandbox profile --------------------------------------------


def a_profile(**overrides: object) -> dict:
    kwargs: dict = {
        "profile_name": "candidate-default",
        "declared_capabilities": ["compute", "artifact_write"],
        "quotas": dict(QUOTAS),
        "network_policy": "DENY_ALL",
    }
    kwargs.update(overrides)
    return build_sandbox_profile(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("dropped", REQUIRED_QUOTAS)
def test_i64_an_unbounded_resource_is_refused(dropped: str) -> None:
    quotas = {name: value for name, value in QUOTAS.items() if name != dropped}
    with pytest.raises(SandboxRefused) as excinfo:
        a_profile(quotas=quotas)
    assert dropped in str(excinfo.value)


def test_i64_zero_quota_is_not_a_bound() -> None:
    quotas = dict(QUOTAS)
    quotas["cpu_seconds"] = 0
    with pytest.raises(SandboxRefused):
        a_profile(quotas=quotas)


@pytest.mark.parametrize("capability", sorted(FORBIDDEN_CANDIDATE_CAPABILITIES))
def test_i64_profile_cannot_declare_a_self_scoring_capability(capability: str) -> None:
    with pytest.raises(SandboxRefused) as excinfo:
        a_profile(declared_capabilities=["compute", capability])
    assert "own evaluator or the hidden holdout" in str(excinfo.value)


def test_i64_allowlist_policy_with_no_hosts_is_refused() -> None:
    """Silently behaving like DENY_ALL would hide a missing configuration."""
    with pytest.raises(SandboxRefused) as excinfo:
        a_profile(network_policy="ALLOWLIST", network_allowlist=[])
    assert "empty allowlist" in str(excinfo.value)


def test_i64_allowlist_under_a_non_allowlist_policy_is_refused() -> None:
    with pytest.raises(SandboxRefused) as excinfo:
        a_profile(network_policy="DENY_ALL", network_allowlist=["example.invalid"])
    assert "would ignore" in str(excinfo.value)


def test_i64_undeclared_network_policy_is_refused() -> None:
    with pytest.raises(SandboxRefused):
        a_profile(network_policy="PERMISSIVE")


# -- EF4-I64 capability leases ------------------------------------------


def a_lease(**overrides: object) -> dict:
    kwargs: dict = {
        "principal_id": "CAND-1",
        "capabilities": ["compute", "artifact_write"],
        "resource_scopes": ["workspace/tmp"],
        "issued_at": "2026-07-27T00:00:00+00:00",
        "expires_at": "2026-07-27T01:00:00+00:00",
        "fencing_token": 7,
        "policy_hash": sha256_of_payload({"policy": "PB-1"}),
        "approval_ids": ["APR-1"],
    }
    kwargs.update(overrides)
    return build_capability_lease(**kwargs)  # type: ignore[arg-type]


def test_i64_candidate_lease_is_always_agent_standing() -> None:
    """A candidate cannot lease itself the broader standing of a service."""
    assert a_lease()["principal_type"] == "agent"


def test_i64_holdout_read_cannot_be_leased() -> None:
    with pytest.raises(SandboxRefused) as excinfo:
        a_lease(capabilities=["compute", "holdout_read"])
    assert "can score itself" in str(excinfo.value)


def test_i64_empty_lease_is_a_construction_bug() -> None:
    with pytest.raises(SandboxRefused):
        a_lease(capabilities=[])


def test_i64_unexpiring_lease_is_refused() -> None:
    with pytest.raises(SandboxRefused) as excinfo:
        a_lease(expires_at="2026-07-27T00:00:00+00:00")
    assert "cannot bound an execution" in str(excinfo.value)


def test_i64_revocation_state_is_explicit() -> None:
    lease = a_lease()
    assert lease["revoked"] is False
    assert lease["revocation_reason"] is None


@pytest.mark.parametrize("bad", [0, -1, "FT-1"])
def test_i64_a_non_monotonic_fence_is_refused(bad: object) -> None:
    with pytest.raises(SandboxRefused) as excinfo:
        a_lease(fencing_token=bad)
    assert "monotonic fence" in str(excinfo.value)


# -- EF4-I64 execution gate --------------------------------------------


def gate_kwargs(**overrides: object) -> dict:
    kwargs: dict = {
        "profile": a_profile(),
        "lease": a_lease(),
        "requested_capabilities": ["compute"],
        "now": "2026-07-27T00:30:00+00:00",
        "evaluator_bundle_id": "EB-1",
        "holdout_manifest_id": "HM-1",
        "reachable_resource_ids": ["workspace/tmp"],
    }
    kwargs.update(overrides)
    return kwargs


def test_i64_a_fully_declared_execution_is_permitted() -> None:
    require_execution_permitted(**gate_kwargs())


def test_i64_undeclared_capability_is_denied() -> None:
    blockers = execution_blockers(**gate_kwargs(requested_capabilities=["network"]))
    assert any("not declared" in blocker for blocker in blockers)


def test_i64_reachable_evaluator_bundle_denies_execution() -> None:
    blockers = execution_blockers(
        **gate_kwargs(reachable_resource_ids=["workspace/tmp", "EB-1"])
    )
    assert any("could alter what judges it" in blocker for blocker in blockers)


def test_i64_reachable_holdout_denies_execution() -> None:
    blockers = execution_blockers(
        **gate_kwargs(reachable_resource_ids=["workspace/tmp", "HM-1"])
    )
    assert any("read the test it is measured on" in blocker for blocker in blockers)


def test_i64_expired_lease_denies_execution() -> None:
    blockers = execution_blockers(**gate_kwargs(now="2026-07-27T02:00:00+00:00"))
    assert any("not valid at" in blocker for blocker in blockers)


def test_i64_revoked_lease_denies_execution() -> None:
    lease = dict(a_lease())
    lease["revoked"] = True
    blockers = execution_blockers(**gate_kwargs(lease=lease))
    assert any("revoked" in blocker for blocker in blockers)


def test_i64_open_egress_denies_execution() -> None:
    profile = a_profile(
        declared_capabilities=["compute", "network"], network_policy="ALLOW_ALL"
    )
    lease = a_lease(capabilities=["compute", "network"])
    blockers = execution_blockers(
        **gate_kwargs(profile=profile, lease=lease, requested_capabilities=["network"])
    )
    assert any("exfiltrates the holdout" in blocker for blocker in blockers)


def test_i64_refusal_lists_every_blocker_at_once() -> None:
    with pytest.raises(SandboxRefused) as excinfo:
        require_execution_permitted(
            **gate_kwargs(
                requested_capabilities=["network"],
                reachable_resource_ids=["EB-1", "HM-1"],
                now="2026-07-27T09:00:00+00:00",
            )
        )
    message = str(excinfo.value)
    assert "not valid at" in message
    assert "not declared" in message
    assert "judges it" in message


# -- EF4-I64 effect receipts -------------------------------------------


def a_receipt(**overrides: object) -> dict:
    kwargs: dict = {
        "intent_id": "AI-1",
        "run_id": "RUN-1",
        "external_operation_id": "OP-1",
        "idempotency_key": "IK-1",
        "started_at": "2026-07-27T00:00:00+00:00",
        "finished_at": "2026-07-27T00:00:30+00:00",
        "exit_code": 0,
        "quota_exceeded": False,
        "result_artifact_ids": ["ART-1"],
        "error_artifact_ids": [],
        "observed_state_hash": sha256_of_payload({"state": "after"}),
    }
    kwargs.update(overrides)
    return build_execution_receipt(**kwargs)  # type: ignore[arg-type]


def test_i64_clean_execution_succeeds_and_needs_no_reconciliation() -> None:
    receipt = a_receipt()
    assert receipt["status"] == "SUCCEEDED"
    assert execution_is_accounted(receipt) is True


def test_i64_unobserved_outcome_is_unknown_not_failed() -> None:
    """An unreceipted effect may have happened, so it needs reconciliation."""
    receipt = a_receipt(exit_code=None)
    assert receipt["status"] == "UNKNOWN"
    assert receipt["reconciliation_required"] is True
    assert execution_is_accounted(receipt) is False


def test_i64_quota_kill_is_a_failure() -> None:
    receipt = a_receipt(exit_code=137, quota_exceeded=True)
    assert receipt["status"] == "FAILED"


def test_i64_status_is_not_a_parameter() -> None:
    with pytest.raises(TypeError):
        build_execution_receipt(  # type: ignore[call-arg]
            intent_id="AI-1",
            run_id="RUN-1",
            external_operation_id="OP-1",
            idempotency_key="IK-1",
            started_at="2026-07-27T00:00:00+00:00",
            finished_at="2026-07-27T00:00:30+00:00",
            exit_code=1,
            quota_exceeded=False,
            result_artifact_ids=[],
            error_artifact_ids=[],
            observed_state_hash=sha256_of_payload({"state": "after"}),
            status="SUCCEEDED",
        )
