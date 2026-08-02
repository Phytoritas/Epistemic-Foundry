"""negative_and_adversarial_tests — every refusal fires under attack.

Each declared ``FINDING_CODES`` entry is provoked at least once, and the
adversarial cases are the ones this package exists to stop at production scale: an
eviction that would drop negative memory, an eviction that would empty a niche, a
surrogate used to skip a stage or to promote, a promotion decision that does not
carry the gate's verdict, a budget that only forecasts spend, and a run that
sheds load without recording it.  A refusal that fired under the wrong code would
be as much a defect as no refusal at all, so every case asserts the exact code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.operations.v4_y05 import scaling as mod
from epistemic_foundry.operations.v4_y05 import (
    bind_triage_to_gate,
    build_scaled_quality_diversity_map,
    plan_diversity_preserving_rebalance,
    reconcile_shed_load,
    require_bounded_production_budget,
    require_surrogate_never_promotes,
    triage_at_scale,
)
from epistemic_foundry.scheduler.v4_n05 import LANES, LaneEvent
from fixtures import (
    GATE_ADMIT,
    archive_population,
    bounded_budget,
    gate_receipt,
    lane_limits,
    qd_map,
    repo_root,
    schedule_events,
    soft_budget,
    triage_report,
)


def _code(excinfo: pytest.ExceptionInfo) -> str:
    return excinfo.value.code  # type: ignore[attr-defined]


# --- input integrity ----------------------------------------------------------


def test_empty_evolution_run_id_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        build_scaled_quality_diversity_map(
            evolution_run_id="",
            generation=1,
            niche_ids=["n1"],
            occupied_niche_ids=["n1"],
            lineage_entropy=1.0,
        )
    assert _code(caught) == "INPUT_INVALID"


def test_negative_capacity_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        plan_diversity_preserving_rebalance(
            quality_diversity_map=qd_map(),
            archive_entries=archive_population(),
            capacity=-1,
        )
    assert _code(caught) == "INPUT_INVALID"


def test_enum_reader_refuses_a_reshaped_vocabulary() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        mod._enum(mod.SURROGATE_KIND, "triage_decision", 2)
    assert _code(caught) == "VOCABULARY_DRIFT"


# --- quality-diversity scaling ------------------------------------------------


def test_map_with_occupied_niche_outside_the_map_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        build_scaled_quality_diversity_map(
            evolution_run_id="ER",
            generation=1,
            niche_ids=["n1"],
            occupied_niche_ids=["n2"],
            lineage_entropy=1.0,
        )
    assert _code(caught) == "QD_MAP_CONTRACT_VIOLATED"


def test_rebalance_over_an_invalid_map_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        plan_diversity_preserving_rebalance(
            quality_diversity_map={"map_id": "x"},
            archive_entries=[],
            capacity=0,
        )
    assert _code(caught) == "QD_MAP_CONTRACT_VIOLATED"


def test_evicting_protected_negative_memory_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        plan_diversity_preserving_rebalance(
            quality_diversity_map=qd_map(),
            archive_entries=archive_population(),
            capacity=1,
            requested_eviction_ids=["AE-c3"],  # the protected null
        )
    assert _code(caught) == "REBALANCE_EVICTS_PROTECTED_MEMORY"


def test_evicting_a_niche_last_occupant_is_refused() -> None:
    # AE-c3 is the sole occupant of niche-b; removing it would empty the niche.
    # It is also protected, so target the diversity guard with a non-protected
    # sole occupant instead.
    entries = archive_population()
    with pytest.raises(mod.OperationsScalingError) as caught:
        plan_diversity_preserving_rebalance(
            quality_diversity_map=qd_map(),
            archive_entries=entries,
            capacity=1,
            requested_eviction_ids=["AE-c1", "AE-c2"],  # empties niche-a together
        )
    assert _code(caught) == "DIVERSITY_COLLAPSE_UNDER_SCALING"


def test_rebalance_with_a_malformed_migration_action_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        plan_diversity_preserving_rebalance(
            quality_diversity_map=qd_map(),
            archive_entries=archive_population(),
            capacity=10,
            migration_actions=[{"candidate_id": "c1"}],  # missing required fields
        )
    assert _code(caught) == "REBALANCE_PLAN_CONTRACT_VIOLATED"


def test_requested_eviction_of_an_unknown_entry_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        plan_diversity_preserving_rebalance(
            quality_diversity_map=qd_map(),
            archive_entries=archive_population(),
            capacity=2,
            requested_eviction_ids=["AE-unknown"],
        )
    assert _code(caught) == "INPUT_INVALID"


# --- surrogate triage ---------------------------------------------------------


def test_triage_with_negative_uncertainty_violates_the_contract() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        triage_at_scale(
            candidate_id="c1",
            surrogate_model_id="s",
            predicted_utility=0.5,
            predictive_uncertainty=-1.0,
            ood_score=0.1,
            calibration_window_id="w",
        )
    assert _code(caught) == "SURROGATE_REPORT_CONTRACT_VIOLATED"


def test_surrogate_used_to_skip_a_hidden_stage_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        require_surrogate_never_promotes(triage_report(), stage_class="holdout")
    assert _code(caught) == "SURROGATE_SKIPS_REQUIRED_STAGE"


def test_surrogate_used_to_skip_replication_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        require_surrogate_never_promotes(triage_report(), stage_class="replication")
    assert _code(caught) == "SURROGATE_SKIPS_REQUIRED_STAGE"


def test_surrogate_routed_as_a_promotion_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        require_surrogate_never_promotes(
            triage_report(), stage_class="screening", drives_promotion=True
        )
    assert _code(caught) == "SURROGATE_DRIVES_PROMOTION"


def test_surrogate_report_waiving_direct_evaluation_is_refused() -> None:
    forged = dict(triage_report())
    forged["direct_evaluation_required"] = False
    with pytest.raises(mod.OperationsScalingError) as caught:
        require_surrogate_never_promotes(forged, stage_class="screening")
    assert _code(caught) == "SURROGATE_DIRECT_EVALUATION_WAIVED"


# --- promotion authority binding ----------------------------------------------


def test_binding_without_the_gate_verdict_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        bind_triage_to_gate(
            triage_report=triage_report(),
            gate_receipt={"decision": "MAYBE", "candidate_id": "c1"},
        )
    assert _code(caught) == "PROMOTION_AUTHORITY_NOT_FROM_GATE"


def test_binding_mismatched_candidates_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        bind_triage_to_gate(
            triage_report=triage_report(candidate_id="c1"),
            gate_receipt=gate_receipt(decision=GATE_ADMIT, candidate_id="c2"),
        )
    assert _code(caught) == "TRIAGE_GATE_CANDIDATE_MISMATCH"


def test_binding_a_stage_waived_triage_is_refused() -> None:
    forged = dict(triage_report())
    forged["direct_evaluation_required"] = False
    with pytest.raises(mod.OperationsScalingError) as caught:
        bind_triage_to_gate(triage_report=forged, gate_receipt=gate_receipt())
    assert _code(caught) == "SURROGATE_DIRECT_EVALUATION_WAIVED"


# --- budgets and production load ----------------------------------------------


def test_unbounded_budget_for_production_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        require_bounded_production_budget(soft_budget())
    assert _code(caught) == "BUDGET_NOT_BOUNDED_FOR_PRODUCTION"


def test_malformed_budget_envelope_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        require_bounded_production_budget({"budget_id": "x"})
    assert _code(caught) == "BUDGET_ENVELOPE_INVALID"


def test_shedding_load_under_an_unbounded_budget_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        reconcile_shed_load(
            repo_root(),
            budget_envelope=soft_budget(),
            proposed=["C-1"],
            events=schedule_events("C-1"),
            lane_limits=lane_limits(),
            schedule_id="S",
        )
    assert _code(caught) == "BUDGET_NOT_BOUNDED_FOR_PRODUCTION"


def test_shed_candidate_not_recorded_as_cancelled_is_refused() -> None:
    with pytest.raises(mod.OperationsScalingError) as caught:
        reconcile_shed_load(
            repo_root(),
            budget_envelope=bounded_budget(),
            proposed=["C-1"],
            events=schedule_events("C-1"),
            lane_limits=lane_limits(),
            schedule_id="S",
            shed_candidate_ids=["C-9"],
        )
    assert _code(caught) == "LOAD_SHED_DISHONEST_COMPLETION"


def test_incomplete_fanin_under_shedding_is_refused() -> None:
    """A candidate proposed but never concluded or cancelled is a partial fan-out."""
    events = [
        LaneEvent(LANES[0], "enqueue", "C-1"),
        LaneEvent(LANES[0], "start", "C-1"),
    ]
    with pytest.raises(mod.OperationsScalingError) as caught:
        reconcile_shed_load(
            repo_root(),
            budget_envelope=bounded_budget(),
            proposed=["C-1"],
            events=events,
            lane_limits=lane_limits(),
            schedule_id="S",
        )
    assert _code(caught) == "LOAD_SHED_FANIN_UNACCOUNTED"
