"""negative_and_adversarial_tests — every way candidate code escapes, refused.

Each attack is the concrete escape the threat model registers: an open
network, an undeclared capability, a missing quota, an unaccounted effect, an
undeclared sandbox, a generator that can see the holdout, a quarantined
prompt on the active surface, a retroactive evaluator edit, and an audit that
skips a channel.  Each is an input wrong in exactly one way, refused by its
own code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.security.v4_s05 import (
    ThreatControlError,
    build_leakage_audit,
    build_threat_coverage,
    qualify_candidate_execution,
    require_inert_mutations,
    threat_register,
)
from epistemic_foundry.verifier_firewall.firewall import EvaluatorDrift
from fixtures import (
    HIDDEN_HANDLE,
    RUN_ID,
    firewall,
    prompt_proposal,
    qualification_arguments,
    sealed_bundle,
    target_manifest,
)


def refused(run, code: str) -> ThreatControlError:
    with pytest.raises(ThreatControlError) as caught:
        run()
    assert caught.value.code == code, caught.value.code
    return caught.value


def test_a_kind_outside_the_sealed_search_space_is_refused() -> None:
    error = refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(candidate_kind="evaluator-bundle")
        ),
        "CANDIDATE_KIND_UNQUALIFIED",
    )
    assert "evaluator-bundle" not in error.context["mutable_search_space"]
    assert len(error.context["mutable_search_space"]) == 4


def test_the_open_network_policy_is_refused_outright() -> None:
    refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(
                target_manifest=target_manifest(
                    network_policy="unrestricted_with_approval",
                    approval_policy="all_effects",
                )
            )
        ),
        "NETWORK_POLICY_OPEN",
    )


def test_an_allowlist_without_capabilities_is_refused() -> None:
    refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(
                target_manifest=target_manifest(network_policy="allowlist")
            )
        ),
        "CAPABILITY_UNDECLARED",
    )


def test_a_high_risk_target_with_no_approval_is_refused() -> None:
    refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(
                target_manifest=target_manifest(
                    safety_class="high_risk", approval_policy="none"
                )
            )
        ),
        "APPROVAL_MISSING",
    )


def test_an_execution_with_no_quota_at_all_is_refused() -> None:
    refused(
        lambda: qualify_candidate_execution(**qualification_arguments(hard_limits={})),
        "QUOTA_MISSING",
    )


def test_all_null_quotas_are_refused() -> None:
    refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(
                hard_limits={"tokens": None, "wall_seconds": None}
            )
        ),
        "QUOTA_MISSING",
    )


def test_a_misnamed_quota_dimension_is_refused_not_ignored() -> None:
    error = refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(hard_limits={"max_tokens": 5})
        ),
        "QUOTA_MISSING",
    )
    assert "max_tokens" in str(error)


def test_a_blank_receipt_channel_is_refused() -> None:
    refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(effect_receipt_channel_id="   ")
        ),
        "RECEIPT_CHANNEL_MISSING",
    )


def test_an_undeclared_sandbox_profile_is_refused() -> None:
    error = refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(
                target_manifest=target_manifest(sandbox_profile="plugin_host_process")
            )
        ),
        "SANDBOX_CLASS_UNDECLARED",
    )
    assert error.context["profile"] == "plugin_host_process"
    assert len(error.context["declared"]) == 5


def test_a_manifest_the_schema_rejects_is_refused() -> None:
    from epistemic_foundry.contracts import ContractViolation

    broken = target_manifest()
    del broken["reproducibility_contract"]

    with pytest.raises(ContractViolation):
        qualify_candidate_execution(**qualification_arguments(target_manifest=broken))


def test_a_drifted_evaluator_bundle_is_detected() -> None:
    guard = firewall()
    tampered = sealed_bundle()
    tampered["metric_contract_hash"] = "sha256:" + "f" * 64

    with pytest.raises(EvaluatorDrift):
        guard.assert_unchanged(tampered)


def test_a_quarantined_prompt_on_the_active_surface_is_refused() -> None:
    error = refused(
        lambda: require_inert_mutations(
            target_run_id=RUN_ID,
            active_prompt_genome_ids=["PG-NEW"],
            proposals=[prompt_proposal()],
        ),
        "QUARANTINED_INFLUENCE",
    )
    assert error.context["held"][0]["proposed_prompt_genome_id"] == "PG-NEW"


@pytest.mark.parametrize("status", ["QUARANTINED", "TESTING", "REJECTED"])
def test_every_inert_status_is_held_at_the_gate(status: str) -> None:
    refused(
        lambda: require_inert_mutations(
            target_run_id=RUN_ID,
            active_prompt_genome_ids=["PG-NEW"],
            proposals=[prompt_proposal(status=status)],
        ),
        "QUARANTINED_INFLUENCE",
    )


def test_every_unreleased_activation_is_reported_at_once() -> None:
    error = refused(
        lambda: require_inert_mutations(
            target_run_id=RUN_ID,
            active_prompt_genome_ids=["PG-A", "PG-B"],
            proposals=[
                prompt_proposal(proposal_id="PMP-A", proposed_prompt_genome_id="PG-A"),
                prompt_proposal(
                    proposal_id="PMP-B",
                    proposed_prompt_genome_id="PG-B",
                    status="TESTING",
                ),
            ],
        ),
        "QUARANTINED_INFLUENCE",
    )
    assert len(error.context["held"]) == 2


def test_applying_a_proposal_to_its_own_source_run_is_refused() -> None:
    refused(
        lambda: require_inert_mutations(
            target_run_id="ER-S05-1",
            active_prompt_genome_ids=["PG-NEW"],
            proposals=[prompt_proposal(status="APPROVED")],
        ),
        "RETROACTIVE_MUTATION",
    )


def test_an_audit_that_skips_a_named_surface_is_refused() -> None:
    error = refused(
        lambda: build_leakage_audit(
            firewall=firewall(),
            run_or_bundle_id=RUN_ID,
            surfaces_checked=["tool", "log"],
            observed_artifact_ids=[],
            access_log_artifact_id="AL-1",
        ),
        "LEAKAGE_SURFACE_MISSING",
    )
    assert error.context["missing"] == ["cache"]


def test_a_hidden_partition_exposure_fails_the_audit_with_actions() -> None:
    audit = build_leakage_audit(
        firewall=firewall(),
        run_or_bundle_id=RUN_ID,
        surfaces_checked=["cache", "log", "tool"],
        observed_artifact_ids=[HIDDEN_HANDLE, "UNRELATED-1"],
        access_log_artifact_id="AL-1",
        leakage_audit_id="LKA-EXPOSED",
    )

    assert audit["detected_exposures"] == [HIDDEN_HANDLE]
    assert len(audit["required_actions"]) == 4


def test_an_uncovered_threat_is_refused() -> None:
    register = threat_register()
    partial = {threat: ["EV-1"] for threat in list(register)[:-1]}

    error = refused(
        lambda: build_threat_coverage(run_id=RUN_ID, control_evidence=partial),
        "THREAT_UNCOVERED",
    )
    assert error.context["uncovered"] == [list(register)[-1]]


def test_empty_evidence_for_a_threat_counts_as_uncovered() -> None:
    register = threat_register()
    hollow = {threat: [] for threat in register}

    refused(
        lambda: build_threat_coverage(run_id=RUN_ID, control_evidence=hollow),
        "THREAT_UNCOVERED",
    )


def test_an_invented_threat_is_refused_rather_than_recorded() -> None:
    register = threat_register()
    padded = {**{threat: ["EV-1"] for threat in register}, "vibes attack": ["EV-2"]}

    error = refused(
        lambda: build_threat_coverage(run_id=RUN_ID, control_evidence=padded),
        "THREAT_UNDECLARED",
    )
    assert error.context["undeclared"] == ["vibes attack"]


def test_a_non_mapping_input_is_refused() -> None:
    refused(
        lambda: qualify_candidate_execution(
            **qualification_arguments(target_manifest="not-a-mapping")
        ),
        "INPUT_INVALID",
    )
    refused(
        lambda: require_inert_mutations(
            target_run_id=RUN_ID,
            active_prompt_genome_ids=["PG-A"],
            proposals=["not-a-mapping"],
        ),
        "INPUT_INVALID",
    )
