"""Promotion authority and dependency-corrected support."""

from __future__ import annotations

import dataclasses

import pytest

from epistemic_foundry.governance import (
    PromotionRequest,
    adjusted_support_count,
    build_dependency_cluster,
    decide_promotion,
)
from epistemic_foundry.governance.dependency import corrected_support
from epistemic_foundry.governance.promotion import ABSENT_REFERENCE, promoted


def _complete_request(**overrides) -> PromotionRequest:
    """A request that satisfies every named promotion requirement."""
    base = PromotionRequest(
        candidate_id="CAND-0001",
        requested_level="SUPPORTED",
        hard_gate_status="PASS",
        fitness_vector_id="FV-0001",
        parliament_adjudication_id="ADJ-0001",
        selective_inference_report_id="SIR-0001",
        replication_result_ids=("REP-0001",),
        approval_record_ids=("APR-0001",),
        grounded_evidence_ids=("EV-0001",),
        dependency_cluster_ids=("EDC-0001",),
        challenge_survived=True,
        leakage_detected=False,
    )
    return dataclasses.replace(base, **overrides)


# -- the constitutional rule -------------------------------------------


def test_promotion_request_exposes_no_scalar_score_field() -> None:
    """A scalar must not be representable as promotion input."""
    fields = {f.name for f in dataclasses.fields(PromotionRequest)}
    for forbidden in ("score", "combined_score", "confidence", "novelty", "correct", "votes"):
        assert forbidden not in fields


def test_complete_evidence_promotes() -> None:
    decision = decide_promotion(_complete_request())
    assert decision["decision"] == "PROMOTE"
    assert decision["granted_level"] == "SUPPORTED"
    assert promoted(decision) is True


def test_missing_grounded_evidence_is_underdetermined() -> None:
    decision = decide_promotion(_complete_request(grounded_evidence_ids=()))
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] == "NONE"
    assert "grounded source evidence" in decision["rationale"]


def test_missing_dependency_correction_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(dependency_cluster_ids=()))["decision"] == "UNDERDETERMINED"


def test_missing_parliament_adjudication_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(parliament_adjudication_id=None))["decision"] == "UNDERDETERMINED"


def test_missing_multiplicity_accounting_is_underdetermined() -> None:
    assert (
        decide_promotion(_complete_request(selective_inference_report_id=None))["decision"]
        == "UNDERDETERMINED"
    )


def test_absent_reference_sentinel_never_accompanies_a_promotion() -> None:
    """The schema forbids null ids, so absence uses a sentinel.

    A sentinel is only safe if it cannot coexist with PROMOTE; otherwise the
    record would assert an adjudication that was never produced.
    """
    for override in ({"parliament_adjudication_id": None}, {"selective_inference_report_id": None}):
        decision = decide_promotion(_complete_request(**override))
        assert ABSENT_REFERENCE in decision.values()
        assert decision["decision"] != "PROMOTE"
    promoted_decision = decide_promotion(_complete_request())
    assert ABSENT_REFERENCE not in promoted_decision.values()


def test_unchallenged_candidate_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(challenge_survived=False))["decision"] == "UNDERDETERMINED"


def test_required_replication_absent_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(replication_result_ids=()))["decision"] == "UNDERDETERMINED"


def test_required_human_approval_absent_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(approval_record_ids=()))["decision"] == "UNDERDETERMINED"


def test_incompatible_method_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(method_compatible=False))["decision"] == "UNDERDETERMINED"


# -- blockers outrank everything ---------------------------------------


def test_leakage_blocks_even_with_complete_evidence() -> None:
    """Leakage invalidates; it is never absorbed as a score penalty."""
    decision = decide_promotion(_complete_request(leakage_detected=True))
    assert decision["decision"] == "BLOCKED"
    assert decision["granted_level"] == "NONE"
    assert "INVALIDATED" in decision["rationale"]


def test_failed_hard_cascade_blocks() -> None:
    decision = decide_promotion(_complete_request(hard_gate_status="FAIL"))
    assert decision["decision"] == "BLOCKED"


def test_partial_cascade_is_conditional_not_promotion() -> None:
    decision = decide_promotion(_complete_request(hard_gate_status="PARTIAL"))
    assert decision["decision"] == "CONDITIONAL"
    assert decision["granted_level"] == "NONE"
    assert promoted(decision) is False


def test_blocker_outranks_missing_requirements() -> None:
    decision = decide_promotion(
        _complete_request(leakage_detected=True, grounded_evidence_ids=())
    )
    assert decision["decision"] == "BLOCKED"


# -- dependency correction ---------------------------------------------


def test_correlated_evidence_counts_as_one_unit() -> None:
    """Five reanalyses of one dataset are one independent unit."""
    cluster = build_dependency_cluster(
        run_id="RUN-0001",
        evidence_ids=["EV-1", "EV-2", "EV-3", "EV-4", "EV-5"],
        dependency_types=["SAME_DATASET"],
        representative_evidence_ids=["EV-1"],
        independence_confidence=0.9,
        rationale="all five reanalyze dataset DF-001",
        provenance_refs=["DF-001"],
        independent_unit_count=1,
    )
    assert cluster["support_count_raw"] == 5
    assert cluster["support_count_adjusted"] == 1


def test_adjustment_may_only_reduce_support() -> None:
    with pytest.raises(ValueError):
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=["EV-1"],
            dependency_types=["SAME_COHORT"],
            representative_evidence_ids=["EV-1"],
            independence_confidence=0.5,
            rationale="inflation attempt",
            provenance_refs=["DF-001"],
            independent_unit_count=1,
            support_count_adjusted=9,
        )


def test_empty_cluster_is_refused() -> None:
    with pytest.raises(ValueError):
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=[],
            dependency_types=["UNKNOWN"],
            representative_evidence_ids=[],
            independence_confidence=1.0,
            rationale="empty",
            provenance_refs=["DF-001"],
        )


def test_independent_units_are_counted_per_cluster() -> None:
    assert adjusted_support_count([["EV-1", "EV-2"], ["EV-3"], []]) == 2


def test_corrected_support_sums_adjusted_counts() -> None:
    clusters = [
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=["EV-1", "EV-2"],
            dependency_types=["SAME_TEAM_SERIES"],
            representative_evidence_ids=["EV-1"],
            independence_confidence=0.7,
            rationale="same lab",
            provenance_refs=["DF-001"],
            independent_unit_count=1,
        ),
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=["EV-3"],
            dependency_types=["UNKNOWN"],
            representative_evidence_ids=["EV-3"],
            independence_confidence=1.0,
            rationale="separate cohort",
            provenance_refs=["DF-002"],
            independent_unit_count=1,
        ),
    ]
    assert corrected_support(clusters) == 2
