"""unit_and_contract_tests — the happy paths hold their contracts.

Every surface produces a receipt or a canonical artifact that satisfies its
schema and re-derives its own identifier and hash, and every receipt is a pure
function of its inputs.  These tests exercise the compositions the way a
production run would: summarize niche coverage at scale, rebalance without
dropping negative memory or a niche, triage a candidate, keep the surrogate
triage-only, bind it to the admissibility gate, attest a bounded budget and
reconcile a shed-load schedule.
"""

from __future__ import annotations

from epistemic_foundry.contracts import validate_artifact
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.operations.v4_y05 import (
    bind_triage_to_gate,
    plan_diversity_preserving_rebalance,
    reconcile_shed_load,
    require_bounded_production_budget,
    require_surrogate_never_promotes,
)
from fixtures import (
    EVALUATE_NOW,
    GATE_ADMIT,
    GATE_REFUSE,
    archive_population,
    bounded_budget,
    gate_receipt,
    lane_limits,
    qd_map,
    repo_root,
    schedule_events,
    triage_report,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_scaled_quality_diversity_map_is_valid_and_coverage_is_derived() -> None:
    record = qd_map()
    validate_artifact("quality-diversity-map", dict(record))
    assert record["occupied_niches"] == 2
    assert record["total_niches"] == 3
    assert record["coverage_ratio"] == round(2 / 3, 6)
    assert record["map_id"].startswith("YQM-")


def test_quality_diversity_map_is_a_pure_function_of_its_inputs() -> None:
    assert qd_map() == qd_map()


def test_rebalance_preserves_protected_memory_and_niche_coverage() -> None:
    plan = plan_diversity_preserving_rebalance(
        quality_diversity_map=qd_map(),
        archive_entries=archive_population(),
        capacity=2,
    )
    validate_artifact("archive-rebalance-plan", dict(plan))
    # The protected null is never an eviction candidate; it is listed as protected.
    assert "AE-c3" in plan["protected_entry_ids"]
    assert "AE-c3" not in plan["eviction_candidates"]
    # The one eviction leaves niche-a still occupied by AE-c2.
    assert plan["eviction_candidates"] == ["AE-c1"]
    assert plan["approval_required"] is True
    assert plan["plan_id"].startswith("YQR-")
    assert plan["plan_hash"] == hash_excluding(dict(plan), "plan_hash")


def test_rebalance_at_capacity_evicts_nothing() -> None:
    plan = plan_diversity_preserving_rebalance(
        quality_diversity_map=qd_map(),
        archive_entries=archive_population(),
        capacity=10,
    )
    assert plan["eviction_candidates"] == []
    assert plan["approval_required"] is False


def test_triage_forces_direct_evaluation_and_orders_only() -> None:
    report = triage_report()
    validate_artifact("surrogate-triage-report", dict(report))
    assert report["triage_decision"] == EVALUATE_NOW
    assert report["direct_evaluation_required"] is True
    assert report["report_id"].startswith("YST-")
    # A stage a surrogate may legitimately order in front of is not refused.
    assert require_surrogate_never_promotes(report, stage_class="screening") is report


def test_bind_triage_to_gate_carries_the_gate_verdict() -> None:
    for decision, admissible in ((GATE_ADMIT, True), (GATE_REFUSE, False)):
        binding = bind_triage_to_gate(
            triage_report=triage_report(),
            gate_receipt=gate_receipt(decision=decision),
        )
        assert binding["gate_decision"] == decision
        assert binding["admissible_for_promotion_review"] is admissible
        assert binding["surrogate_orders_only"] is True
        assert binding["receipt_id"].startswith("YPB-")
        assert _rederives(binding)


def test_require_bounded_production_budget_attests_a_bounded_envelope() -> None:
    attestation = require_bounded_production_budget(bounded_budget())
    assert attestation["spend_is_bounded"] is True
    assert attestation["escalates_on_breach"] is False  # MARK_PARTIAL only warns
    assert attestation["receipt_id"].startswith("YBA-")
    assert _rederives(attestation)


def test_escalating_breach_policy_is_reported() -> None:
    from fixtures import CANCEL

    attestation = require_bounded_production_budget(
        bounded_budget(breach_policy=CANCEL)
    )
    assert attestation["escalates_on_breach"] is True


def test_reconcile_shed_load_seals_a_verdict_for_a_complete_schedule() -> None:
    attestation = reconcile_shed_load(
        repo_root(),
        budget_envelope=bounded_budget(),
        proposed=["C-1"],
        events=schedule_events("C-1"),
        lane_limits=lane_limits(),
        schedule_id="SCH-0001",
    )
    assert attestation["schedule_valid"] is True
    assert attestation["schedule_id"] == "SCH-0001"
    assert attestation["shed_recorded_as_cancelled"] is True
    assert attestation["receipt_id"].startswith("YLS-")
    assert _rederives(attestation)


def test_reconcile_shed_load_accounts_for_an_honestly_cancelled_shed_candidate() -> (
    None
):
    attestation = reconcile_shed_load(
        repo_root(),
        budget_envelope=bounded_budget(),
        proposed=["C-1", "C-2"],
        events=schedule_events("C-1"),
        lane_limits=lane_limits(),
        schedule_id="SCH-0002",
        shed_candidate_ids=["C-2"],
        cancelled=["C-2"],
    )
    assert attestation["schedule_valid"] is True
    assert attestation["shed_candidate_ids"] == ["C-2"]
