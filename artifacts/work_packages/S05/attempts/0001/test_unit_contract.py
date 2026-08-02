"""unit_and_contract_tests — a properly bounded execution is qualified.

The gates must be passable, or every erasure obligation and every legitimate
run would dead-end: a closed-network bounded target qualifies, an allowlisted
network qualifies when its capabilities are declared, an approved proposal
activates for a future run, a clean audit passes with no required actions,
and full coverage of the threat register is accepted.
"""

from __future__ import annotations

from epistemic_foundry.budgets.envelope import LIMIT_DIMENSIONS
from epistemic_foundry.security.v4_s05 import (
    build_leakage_audit,
    build_threat_coverage,
    qualify_candidate_execution,
    require_inert_mutations,
    threat_register,
)
from fixtures import (
    ADVERSARIAL_HANDLE,
    RUN_ID,
    firewall,
    prompt_proposal,
    qualification_arguments,
    target_manifest,
)


def test_a_closed_network_bounded_target_qualifies() -> None:
    record = qualify_candidate_execution(**qualification_arguments())

    assert record["qualification_id"] == "EXQ-S05-1"
    assert record["target_id"] == "vt-s05-target"
    assert record["capability_requirements"] == []


def test_an_allowlisted_network_with_declared_capabilities_qualifies() -> None:
    record = qualify_candidate_execution(
        **qualification_arguments(
            target_manifest=target_manifest(
                network_policy="allowlist",
                capability_requirements=["net.fetch:api.example.org"],
            )
        )
    )

    assert record["capability_requirements"] == ["net.fetch:api.example.org"]


def test_a_high_risk_target_qualifies_when_approval_covers_it() -> None:
    record = qualify_candidate_execution(
        **qualification_arguments(
            target_manifest=target_manifest(
                safety_class="high_risk", approval_policy="all_effects"
            )
        )
    )

    assert record["safety_class"] == "high_risk"


def test_every_declared_sandbox_class_is_acceptable() -> None:
    from epistemic_foundry.security.v4_s05 import sandbox_classes

    for profile in sandbox_classes():
        record = qualify_candidate_execution(
            **qualification_arguments(
                target_manifest=target_manifest(sandbox_profile=profile)
            )
        )
        assert record["sandbox_profile"] == profile


def test_the_quota_record_normalizes_every_declared_dimension() -> None:
    record = qualify_candidate_execution(**qualification_arguments())

    assert tuple(record["hard_limits"]) == LIMIT_DIMENSIONS
    assert record["hard_limits"]["wall_seconds"] == 600
    assert record["hard_limits"]["network_bytes"] is None


def test_the_qualification_binds_the_sealed_evaluator_hash() -> None:
    guard = firewall()
    record = qualify_candidate_execution(**qualification_arguments(firewall=guard))

    assert record["evaluator_bundle_hash"] == guard.sealed_hash


def test_the_qualification_names_the_threats_it_exercised() -> None:
    record = qualify_candidate_execution(**qualification_arguments())

    assert record["threats_controlled"] == [
        "candidate mutates evaluator",
        "candidate reads holdout",
        "shell/network abuse",
        "unsafe challenge",
    ]


def test_an_inert_proposal_outside_the_active_surface_is_tolerated() -> None:
    gate = require_inert_mutations(
        target_run_id=RUN_ID,
        active_prompt_genome_ids=["PG-BASE"],
        proposals=[prompt_proposal()],
    )

    assert gate["released_activations"] == 0
    assert gate["proposals_examined"] == 1


def test_an_approved_proposal_activates_for_a_future_run() -> None:
    gate = require_inert_mutations(
        target_run_id=RUN_ID,
        active_prompt_genome_ids=["PG-NEW"],
        proposals=[prompt_proposal(status="APPROVED")],
    )

    assert gate["released_activations"] == 1


def test_an_empty_surface_needs_no_proposals_at_all() -> None:
    gate = require_inert_mutations(
        target_run_id=RUN_ID, active_prompt_genome_ids=[], proposals=[]
    )

    assert gate["active_prompt_genome_count"] == 0
    assert gate["released_activations"] == 0


def test_a_clean_audit_passes_with_no_required_actions() -> None:
    audit = build_leakage_audit(
        firewall=firewall(),
        run_or_bundle_id=RUN_ID,
        surfaces_checked=["cache", "log", "tool"],
        observed_artifact_ids=["UNRELATED-1"],
        access_log_artifact_id="AL-1",
        leakage_audit_id="LKA-CLEAN",
    )

    assert audit["detected_exposures"] == []
    assert audit["required_actions"] == []


def test_extra_surfaces_beyond_the_floor_are_welcome() -> None:
    audit = build_leakage_audit(
        firewall=firewall(),
        run_or_bundle_id=RUN_ID,
        surfaces_checked=["cache", "log", "tool", "clipboard"],
        observed_artifact_ids=[],
        access_log_artifact_id="AL-1",
        leakage_audit_id="LKA-WIDE",
    )

    assert "clipboard" in audit["surfaces_checked"]


def test_an_adversarial_partition_exposure_is_detected_too() -> None:
    audit = build_leakage_audit(
        firewall=firewall(),
        run_or_bundle_id=RUN_ID,
        surfaces_checked=["cache", "log", "tool"],
        observed_artifact_ids=[ADVERSARIAL_HANDLE],
        access_log_artifact_id="AL-1",
        leakage_audit_id="LKA-ADV",
    )

    assert audit["detected_exposures"] == [ADVERSARIAL_HANDLE]
    assert audit["required_actions"]


def test_full_coverage_of_the_register_is_accepted() -> None:
    register = threat_register()
    coverage = build_threat_coverage(
        run_id=RUN_ID,
        control_evidence={
            threat: [f"EV-{index}"] for index, threat in enumerate(register)
        },
        coverage_id="ETC-S05-1",
    )

    assert len(coverage["threats"]) == len(register)
    for threat, row in coverage["threats"].items():
        assert row["control"] == register[threat]
        assert row["evidence_artifact_ids"]


def test_the_records_are_deterministic() -> None:
    assert qualify_candidate_execution(
        **qualification_arguments()
    ) == qualify_candidate_execution(**qualification_arguments())


def test_the_records_are_serialisable_evidence() -> None:
    import json

    register = threat_register()
    for record in (
        qualify_candidate_execution(**qualification_arguments()),
        build_threat_coverage(
            run_id=RUN_ID,
            control_evidence={threat: ["EV-1"] for threat in register},
            coverage_id="ETC-S05-2",
        ),
    ):
        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True)) == (
            record
        )
