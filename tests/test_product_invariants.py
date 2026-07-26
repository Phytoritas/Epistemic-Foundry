"""One executable check per product invariant EF4-I01..EF4-I09.

`manifests/product_invariants.yaml` states 64 invariants. The first nine are the
constitutional core quoted in MASTER_SPEC Part II; each test below names the
invariant and exercises the code that enforces it, so an invariant cannot be
satisfied by documentation alone.
"""

from __future__ import annotations

import dataclasses

import pytest

from epistemic_foundry.claim_forge import build_source_span, verify_span_text
from epistemic_foundry.claim_forge.grounding import GroundingFailure
from epistemic_foundry.evidence_parliament import GateOverrideAttempted, build_adjudication
from epistemic_foundry.foundry_kernel.gates import GateSpec, evaluate_gate, gate_decision
from epistemic_foundry.governance import PromotionRequest, build_dependency_cluster
from epistemic_foundry.ingest import (
    IntakeRejected,
    admit_insight,
    intake_blockers,
    promotion_ceiling_for,
    stratify_by_method,
)
from epistemic_foundry.ingest.comparability import exceeds_method_ceiling
from epistemic_foundry.retrieval import (
    LaneCoverageFailure,
    SearchState,
    is_absence_of_evidence,
    missing_lanes,
    require_lane_coverage,
)

ALL_LANES = ("support", "counter", "null", "boundary", "method")


# -- EF4-I01 Kernel authority -------------------------------------------


def test_i01_shell_never_owns_canonical_state() -> None:
    """Plugin shell, hooks and SDKs never own state, policy, gates or replay."""
    from epistemic_foundry import plugin_shell

    exported = set(plugin_shell.__all__)
    for forbidden in ("apply_transition", "decide_promotion", "gate_decision", "NoeticLedger"):
        assert forbidden not in exported


# -- EF4-I02 Claim-first evidence ---------------------------------------


def test_i02_promoted_claim_resolves_to_immutable_source_span() -> None:
    document = "Prefix. The measured effect persisted at fourteen days. Suffix."
    finding = "The measured effect persisted at fourteen days."
    start = document.index(finding)
    span = build_source_span(
        document_id="DOC-1",
        paper_version_id="PV-1",
        page=1,
        section="Results",
        semantic_unit="results",
        char_start=start,
        char_end=start + len(finding),
        verbatim_text=finding,
        parser_name="grobid",
        parser_version="0.8.0",
        provenance_manifest_id="PM-1",
    )
    verify_span_text(span, document)
    with pytest.raises(GroundingFailure):
        verify_span_text(span, document.replace("persisted", "vanished"))


# -- EF4-I03 Falsifiable intake -----------------------------------------


def _admissible_insight() -> dict:
    return {
        "scope": {
            "domain": "learning_science",
            "population": "adults",
            "unit_of_analysis": "learner",
        },
        "prediction_ids": ["PRED-1"],
        "falsifier_ids": ["FALS-1"],
    }


def test_i03_insight_without_falsifier_cannot_enter_observe() -> None:
    insight = _admissible_insight()
    insight["falsifier_ids"] = []
    with pytest.raises(IntakeRejected) as excinfo:
        admit_insight(insight)
    assert "cannot be wrong" in str(excinfo.value)


def test_i03_insight_without_predictions_or_scope_is_rejected() -> None:
    assert len(intake_blockers({"scope": {}, "prediction_ids": [], "falsifier_ids": []})) == 3
    admit_insight(_admissible_insight())


# -- EF4-I04 Coverage before confidence ---------------------------------


def test_i04_missing_lanes_are_reported_before_a_verdict() -> None:
    states = {"support": SearchState.SEARCHED_WITH_RESULTS}
    assert missing_lanes(states) == ["boundary", "counter", "method", "null"]


# -- EF4-I05 Search-state type safety -----------------------------------


def test_i05_four_search_states_stay_distinct() -> None:
    assert len({state.value for state in SearchState}) == 4


def test_i05_only_a_completed_empty_search_is_absence_of_evidence() -> None:
    """Unsearched and failed lanes are ignorance, not absence."""
    assert is_absence_of_evidence(SearchState.SEARCHED_NONE) is True
    assert is_absence_of_evidence(SearchState.UNSEARCHED) is False
    assert is_absence_of_evidence(SearchState.SEARCH_FAILED) is False


# -- EF4-I06 Adversarial retrieval --------------------------------------


def test_i06_counter_and_null_lanes_are_mandatory() -> None:
    complete = {lane: SearchState.SEARCHED_NONE for lane in ALL_LANES}
    require_lane_coverage(complete)
    del complete["counter"]
    with pytest.raises(LaneCoverageFailure):
        require_lane_coverage(complete)


def test_i06_a_failed_lane_does_not_satisfy_coverage() -> None:
    states = {lane: SearchState.SEARCHED_NONE for lane in ALL_LANES}
    states["counter"] = SearchState.SEARCH_FAILED
    with pytest.raises(LaneCoverageFailure):
        require_lane_coverage(states)


# -- EF4-I07 Method comparability ---------------------------------------


def test_i07_incompatible_methods_are_stratified_not_pooled() -> None:
    nodes = [
        {"evidence_id": "EV-1", "evidence_class": "primary_empirical"},
        {"evidence_id": "EV-2", "evidence_class": "modeling"},
        {"evidence_id": "EV-3", "evidence_class": "modeling"},
    ]
    strata = stratify_by_method(nodes)
    assert sorted(strata) == ["modeling", "primary_empirical"]
    assert len(strata["modeling"]) == 2


def test_i07_weak_methods_impose_a_promotion_ceiling() -> None:
    modeling_only = [{"evidence_id": "EV-1", "evidence_class": "modeling"}]
    assert promotion_ceiling_for(modeling_only) == "LITERATURE_GROUNDED"
    assert exceeds_method_ceiling("REPLICATED", modeling_only) is True
    assert exceeds_method_ceiling("CANDIDATE", modeling_only) is False


def test_i07_no_evidence_means_an_inbox_ceiling() -> None:
    assert promotion_ceiling_for([]) == "INBOX"


# -- EF4-I08 Dependency-adjusted evidence -------------------------------


def test_i08_shared_dataset_is_one_unit_not_many_votes() -> None:
    cluster = build_dependency_cluster(
        run_id="RUN-1",
        evidence_ids=["EV-1", "EV-2", "EV-3"],
        dependency_types=["SAME_DATASET"],
        representative_evidence_ids=["EV-1"],
        independence_confidence=0.9,
        rationale="three analyses of one dataset",
        provenance_refs=["DF-1"],
        independent_unit_count=1,
    )
    assert cluster["support_count_raw"] == 3
    assert cluster["support_count_adjusted"] == 1


# -- EF4-I09 No majority authority --------------------------------------


def test_i09_agent_agreement_cannot_promote() -> None:
    """A Parliament recommendation is not promotion, and gates outrank verdicts."""
    failing = gate_decision(
        evaluate_gate(GateSpec("leakage_audit", ("evidence_ids",)), {}),
        run_id="RUN-1",
        policy_version="4.0.0",
        inputs={},
    )
    with pytest.raises(GateOverrideAttempted):
        build_adjudication(
            run_id="RUN-1",
            hypothesis_id="HYP-1",
            gate_decisions=[failing],
            brief_ids=["CB-1"],
            cross_examination_ids=["CX-1"],
            verdict="SUPPORTED",
            promotion_recommendation="REPLICATED",
            rationale="all nine agents agreed",
            strongest_support_id="EV-1",
            strongest_counterevidence_id="EV-2",
        )


def test_i09_promotion_request_has_no_vote_field() -> None:
    fields = {f.name for f in dataclasses.fields(PromotionRequest)}
    for forbidden in ("votes", "agent_count", "majority", "agreement"):
        assert forbidden not in fields
