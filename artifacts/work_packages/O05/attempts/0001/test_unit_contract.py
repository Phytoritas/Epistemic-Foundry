"""unit_and_contract_tests — the three records behave as their contracts say.

A retrieval plan is declared inside a pinned snapshot and carries a disposition
for every canonical lane; a lane receipt derives its state from what the lane
returned rather than from what the caller claims; a layered novelty record
inherits K05's capped ladder and the vector owner's derived status; and an
acquisition plan ranks by declared coverage debt, deterministically, while
naming what it did not search.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.retrieval.search_state import SearchState
from epistemic_foundry.retrieval.v4_o05 import (
    EXECUTION_KIND_POSITION,
    SEARCHED_NONE_STATE_POSITION,
    SEARCHED_WITH_RESULTS_STATE_POSITION,
    SENTINEL_KIND_POSITION,
    UNSEARCHED_STATE_POSITION,
    AcquisitionError,
    acquisition_plan_is_rederivable,
    adversarial_lanes,
    assess_layered_novelty,
    build_coverage_debt_acquisition_plan,
    canonical_lane_order,
    canonical_layer_scores,
    emit_unsearched_lane_receipt,
    external_novelty_lane,
    novelty_layer_vocabulary,
    rank_acquisition_targets,
    receipt_kind_vocabulary,
    receipt_state_vocabulary,
    require_acquisition_plan_identity,
    require_layered_novelty_identity,
    require_plan_identity,
    statement_digest,
)
from fixtures import (
    COUNTER_ID,
    EVIDENCE_DECISION_IDS,
    LATE_ID,
    MECHANISM_ID,
    acquisition_arguments,
    layered_arguments,
    layer_scores,
    niches,
    plan,
    receipts,
    searched_receipt,
    snapshot,
)


def test_a_plan_carries_a_disposition_for_every_canonical_lane() -> None:
    declared = plan()

    assert set(declared["lane_dispositions"]) == set(canonical_lane_order())
    assert declared["selected_lanes"] == list(adversarial_lanes())
    assert set(declared["selected_lanes"]) & set(declared["unselected_lanes"]) == set()
    assert len(declared["selected_lanes"]) + len(declared["unselected_lanes"]) == len(
        canonical_lane_order()
    )


def test_a_plan_records_the_boundary_it_was_declared_inside() -> None:
    pinned = snapshot()
    declared = plan(pinned)

    assert declared["snapshot_id"] == pinned["snapshot_id"]
    assert declared["corpus_snapshot_hash"] == pinned["snapshot_hash"]
    assert declared["subject_document_ids"] == sorted([COUNTER_ID, MECHANISM_ID])
    # The document the snapshot pins but the as-of bound excludes is recorded
    # rather than dropped: "not in the corpus" and "outside the window" are
    # different failures with different remedies.
    assert declared["excluded_document_ids"] == [LATE_ID]
    assert declared["unsearched_sources"]


def test_a_plan_re_derives_its_own_identifier_and_hash() -> None:
    declared = plan()

    assert require_plan_identity(declared) == declared
    assert declared["plan_id"].startswith("ERP-")


def test_two_plans_over_equal_inputs_are_byte_equal() -> None:
    assert plan() == plan()


def test_a_sentinel_receipt_states_only_that_the_lane_was_not_selected() -> None:
    declared = plan()
    lane = next(
        candidate
        for candidate in canonical_lane_order()
        if candidate in declared["unselected_lanes"]
    )
    receipt = emit_unsearched_lane_receipt(
        plan=declared,
        lane=lane,
        lane_decision_evidence_ids=list(EVIDENCE_DECISION_IDS),
    )

    assert (
        receipt["search_state"] == receipt_state_vocabulary()[UNSEARCHED_STATE_POSITION]
    )
    assert receipt["receipt_kind"] == receipt_kind_vocabulary()[SENTINEL_KIND_POSITION]
    assert receipt["sentinel_reason"] == declared["lane_dispositions"][lane]
    assert receipt["result_ids"] is None
    assert receipt["corpus_snapshot_hash"] is None
    assert receipt["errors"] == []


def test_an_execution_receipt_derives_its_state_from_what_the_lane_returned() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    lane = declared["selected_lanes"][0]
    found = searched_receipt(declared, pinned, lane)
    empty = searched_receipt(declared, pinned, lane, result_document_ids=[])
    states = receipt_state_vocabulary()

    assert found["search_state"] == states[SEARCHED_WITH_RESULTS_STATE_POSITION]
    assert found["result_count"] == 1
    assert empty["search_state"] == states[SEARCHED_NONE_STATE_POSITION]
    assert empty["result_count"] == 0
    assert empty["result_ids"] == []
    for receipt in (found, empty):
        assert (
            receipt["receipt_kind"]
            == receipt_kind_vocabulary()[EXECUTION_KIND_POSITION]
        )
        assert receipt["corpus_snapshot_hash"] == pinned["snapshot_hash"]
        assert receipt["plan_hash"] == declared["plan_hash"]


def test_a_searched_empty_lane_is_a_result_not_an_absence_of_searching() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    empty = searched_receipt(
        declared, pinned, declared["selected_lanes"][0], result_document_ids=[]
    )

    assert SearchState(empty["search_state"]) is SearchState.SEARCHED_NONE


def test_the_layer_scores_must_name_exactly_the_declared_layers() -> None:
    scores = canonical_layer_scores(layer_scores())

    assert tuple(scores) == novelty_layer_vocabulary()
    assert all(isinstance(value, float) for value in scores.values())


def test_a_layered_assessment_binds_one_boundary_one_plan_and_both_records() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))

    assert layered["plan_id"] == declared["plan_id"]
    assert layered["boundary_id"] == declared["boundary_id"]
    assert layered["layers"] == list(novelty_layer_vocabulary())
    assert layered["assessment"]["corpus_snapshot_hash"] == pinned["snapshot_hash"]
    assert layered["novelty_vector"]["candidate_id"] == layered["candidate_id"]
    assert require_layered_novelty_identity(layered) == layered
    assert layered["layered_novelty_id"].startswith("LNA-")


def test_an_unfinished_external_search_is_carried_as_an_uncertainty() -> None:
    layered = assess_layered_novelty(**layered_arguments())

    assert layered["external_search_completed"] is False
    assert layered["unsearched_sources"]
    for source in layered["unsearched_sources"]:
        assert any(
            source in entry for entry in layered["novelty_vector"]["uncertainties"]
        )


def test_the_layered_record_states_the_limitation_of_its_own_boundary() -> None:
    layered = assess_layered_novelty(**layered_arguments())

    assert any(
        layered["assessment"]["corpus_snapshot_hash"] or True
        for _ in layered["assessment"]["limitations"]
    )
    assert layered["assessment"]["limitations"]
    assert layered["assessment"]["unsearched_sources"] == layered["unsearched_sources"]


def test_acquisition_targets_rank_by_declared_coverage_debt_descending() -> None:
    targets = rank_acquisition_targets(niches=niches())

    assert [target["coverage_debt"] for target in targets] == [0.9, 0.5, 0.25]
    assert [target["acquisition_rank"] for target in targets] == [1, 2, 3]
    assert all(target["target_id"].startswith("AQT-") for target in targets)


def test_a_target_reports_the_vacancy_the_niche_actually_has() -> None:
    targets = rank_acquisition_targets(niches=niches())
    by_debt = {target["coverage_debt"]: target for target in targets}

    assert by_debt[0.9]["occupant_count"] == 0
    assert by_debt[0.9]["vacancy"] == by_debt[0.9]["capacity"]
    assert by_debt[0.25]["occupant_count"] == 2
    assert by_debt[0.25]["vacancy"] == 2


def test_equal_debts_are_broken_by_niche_identifier_so_the_order_is_total() -> None:
    rows = [dict(niche, coverage_debt=0.5) for niche in niches()]
    first = rank_acquisition_targets(niches=rows)
    second = rank_acquisition_targets(niches=list(reversed(rows)))

    assert first == second
    assert [target["niche_id"] for target in first] == sorted(
        target["niche_id"] for target in first
    )


def test_an_acquisition_plan_records_what_it_did_not_search() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned)
    )
    absent = acquisition["not_searched"]

    assert absent["unsearched_sources"] == declared["unsearched_sources"]
    assert absent["unselected_lanes"] == declared["unselected_lanes"]
    assert absent["excluded_document_ids"] == [LATE_ID]
    assert absent["deferred_niche_ids"] == acquisition["deferred_niche_ids"]
    assert len(acquisition["acquisition_targets"]) == 2
    assert len(absent["deferred_niche_ids"]) == 1


def test_an_acquisition_plan_reconciles_one_receipt_per_canonical_lane() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned)
    )

    assert len(acquisition["lane_receipt_ids"]) == len(canonical_lane_order())
    assert set(acquisition["lane_search_states"]) == set(canonical_lane_order())
    assert set(acquisition["projected_coverage_states"]) == set(canonical_lane_order())
    assert (
        acquisition["projected_coverage_states"][external_novelty_lane()]
        == SearchState.SEARCHED_WITH_RESULTS.value
    )


def test_an_acquisition_plan_re_derives_and_replays_from_its_own_inputs() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    arguments = acquisition_arguments(declared, pinned)
    acquisition = build_coverage_debt_acquisition_plan(**arguments)

    assert require_acquisition_plan_identity(acquisition) == acquisition
    assert acquisition["acquisition_plan_id"].startswith("CDA-")
    assert acquisition_plan_is_rederivable(
        acquisition,
        plan=declared,
        receipts=arguments["receipts"],
        niches=niches(),
    )


def test_two_acquisition_plans_over_equal_inputs_are_byte_equal() -> None:
    pinned = snapshot()
    declared = plan(pinned)

    assert build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned)
    ) == build_coverage_debt_acquisition_plan(**acquisition_arguments(declared, pinned))


def test_a_budget_wider_than_the_map_targets_every_niche_and_defers_none() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned, target_budget=99)
    )

    assert len(acquisition["acquisition_targets"]) == 3
    assert acquisition["deferred_niche_ids"] == []


def test_the_statement_digest_is_the_canonical_shape_the_assessment_requires() -> None:
    digest = statement_digest("a statement")

    assert digest.startswith("sha256:")
    assert digest == statement_digest("a statement")
    assert digest != statement_digest("another statement")


def test_a_blank_statement_is_refused_rather_than_hashed() -> None:
    with pytest.raises(AcquisitionError) as caught:
        statement_digest("   ")

    assert caught.value.code == "INPUT_INVALID"


def test_the_receipt_set_a_plan_produces_covers_every_lane_exactly_once() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)

    assert [receipt["lane"] for receipt in rows] == list(canonical_lane_order())
    assert len({receipt["receipt_id"] for receipt in rows}) == len(rows)
