"""negative_and_adversarial_tests — every declared refusal, actually raised.

Each finding code this package declares is exercised here, and the suite ends
by asserting that no declared code is left untested: a refusal nothing can
trigger is a refusal that does not exist.  The adversarial cases are the ones
that look valid — a boundary declared over a *different* snapshot, a lane
result the snapshot never pinned, a blocked lane presented inside an otherwise
complete receipt set, and an external layer declared complete while the
boundary still names sources nobody searched.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.evidence.v4_k05 import (
    declare_prior_art_boundary,
    pin_corpus_snapshot,
)
from epistemic_foundry.retrieval.v4_o05 import (
    FINDING_CODES,
    AcquisitionError,
    assess_layered_novelty,
    build_coverage_debt_acquisition_plan,
    build_evolution_retrieval_plan,
    canonical_lane_order,
    canonical_layer_scores,
    coverage_state,
    emit_unsearched_lane_receipt,
    external_novelty_lane,
    rank_acquisition_targets,
    receipt_state_vocabulary,
    require_acquisition_plan_identity,
    require_layered_novelty_identity,
    require_plan_identity,
    stop_reason_vocabulary,
)
from fixtures import (
    AS_OF_DATE,
    CORPUS_ID,
    EVIDENCE_DECISION_IDS,
    LATE_ID,
    MECHANISM_ID,
    PINNED_AT,
    QUERY_PLAN_ID,
    RUN_ID,
    SEARCHED_SOURCES,
    UNSEARCHED_SOURCES,
    acquisition_arguments,
    boundary,
    documents,
    lane_dispositions,
    layered_arguments,
    layer_scores,
    niches,
    plan,
    receipts,
    searched_receipt,
    snapshot,
)

RAISED: set[str] = set()

#: Imported under its own name so the local helper below stays readable.
boundary_for = boundary


def refused(call) -> AcquisitionError:  # type: ignore[no-untyped-def]
    with pytest.raises(AcquisitionError) as caught:
        call()
    RAISED.add(caught.value.code)
    return caught.value


def other_snapshot() -> dict:
    """A second pinned corpus: the same builder, deliberately different bytes."""
    return pin_corpus_snapshot(
        corpus_id=CORPUS_ID, documents=documents()[:3], pinned_at=PINNED_AT
    )


def other_boundary() -> dict:
    return declare_prior_art_boundary(
        snapshot=other_snapshot(),
        as_of_date=AS_OF_DATE,
        searched_sources=list(SEARCHED_SOURCES),
        unsearched_sources=list(UNSEARCHED_SOURCES),
    )


# -- retrieval plan --------------------------------------------------------


def test_a_plan_naming_an_unpinned_document_is_refused() -> None:
    error = refused(lambda: plan(subject_document_ids=["DOC-NOWHERE"]))

    assert error.code == "DOCUMENT_OUTSIDE_SNAPSHOT"
    assert error.context["document_ids"] == ["DOC-NOWHERE"]


def test_a_plan_naming_a_document_after_the_as_of_bound_is_refused() -> None:
    error = refused(lambda: plan(subject_document_ids=[LATE_ID]))

    assert error.code == "DOCUMENT_AFTER_AS_OF"
    assert error.context["document_ids"] == [LATE_ID]


def test_a_plan_naming_no_subject_document_is_refused() -> None:
    error = refused(lambda: plan(subject_document_ids=[]))

    assert error.code == "INPUT_INVALID"


def test_a_boundary_over_a_different_snapshot_is_refused() -> None:
    error = refused(lambda: plan(boundary=other_boundary()))

    assert error.code == "BOUNDARY_NOT_FROM_SNAPSHOT"


def test_a_tampered_snapshot_surfaces_the_corpus_boundary_refusal() -> None:
    pinned = snapshot()
    declared = boundary_for(pinned)
    error = refused(
        lambda: build_evolution_retrieval_plan(
            snapshot=dict(pinned, corpus_id="RELABELLED"),
            boundary=declared,
            run_id=RUN_ID,
            query_plan_id=QUERY_PLAN_ID,
            subject_document_ids=[MECHANISM_ID],
            lane_dispositions=lane_dispositions(),
        )
    )

    assert error.code == "SNAPSHOT_BOUNDARY_REFUSED"
    assert error.context["corpus_finding_code"] == "SNAPSHOT_DRIFT"


def test_a_plan_omitting_a_canonical_lane_is_refused() -> None:
    dispositions = lane_dispositions()
    dispositions.pop(canonical_lane_order()[0])
    error = refused(lambda: plan(lane_dispositions=dispositions))

    assert error.code == "LANE_COVERAGE_INCOMPLETE"
    assert error.context["missing"] == [canonical_lane_order()[0]]


def test_a_plan_naming_a_lane_outside_the_vocabulary_is_refused() -> None:
    error = refused(
        lambda: plan(lane_dispositions=lane_dispositions(invented_lane="SELECTED"))
    )

    assert error.code == "LANE_UNDECLARED"
    assert error.context["undeclared"] == ["invented_lane"]


def test_a_plan_carrying_an_undeclared_disposition_is_refused() -> None:
    lane = canonical_lane_order()[0]
    error = refused(
        lambda: plan(lane_dispositions=lane_dispositions(**{lane: "MAYBE"}))
    )

    assert error.code == "DISPOSITION_UNDECLARED"
    assert error.context["lane"] == lane


def test_a_relabelled_plan_does_not_re_derive_its_identity() -> None:
    tampered = dict(plan(), run_id="SOMEONE-ELSES-RUN")
    error = refused(lambda: require_plan_identity(tampered))

    assert error.code == "PLAN_DRIFT"


# -- lane receipts ---------------------------------------------------------


def test_a_selected_lane_cannot_carry_an_unsearched_sentinel() -> None:
    declared = plan()
    error = refused(
        lambda: emit_unsearched_lane_receipt(
            plan=declared,
            lane=declared["selected_lanes"][0],
            lane_decision_evidence_ids=list(EVIDENCE_DECISION_IDS),
        )
    )

    assert error.code == "LANE_DISPOSITION_CONFLICT"


def test_an_unselected_lane_cannot_carry_an_execution_receipt() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    error = refused(
        lambda: searched_receipt(declared, pinned, declared["unselected_lanes"][0])
    )

    assert error.code == "LANE_DISPOSITION_CONFLICT"


def test_a_receipt_for_a_lane_outside_the_vocabulary_is_refused() -> None:
    declared = plan()
    error = refused(
        lambda: emit_unsearched_lane_receipt(
            plan=declared,
            lane="invented_lane",
            lane_decision_evidence_ids=list(EVIDENCE_DECISION_IDS),
        )
    )

    assert error.code == "LANE_UNDECLARED"


def test_a_lane_returning_an_unpinned_document_is_refused() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    error = refused(
        lambda: searched_receipt(
            declared,
            pinned,
            declared["selected_lanes"][0],
            result_document_ids=[MECHANISM_ID, "DOC-NOWHERE"],
        )
    )

    assert error.code == "RESULT_OUTSIDE_SNAPSHOT"
    assert error.context["document_ids"] == ["DOC-NOWHERE"]


def test_a_receipt_bound_to_a_snapshot_the_plan_does_not_pin_is_refused() -> None:
    declared = plan()
    error = refused(
        lambda: searched_receipt(
            declared, other_snapshot(), declared["selected_lanes"][0]
        )
    )

    assert error.code == "BOUNDARY_NOT_FROM_SNAPSHOT"


def test_a_lane_returning_the_same_document_twice_is_refused() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    error = refused(
        lambda: searched_receipt(
            declared,
            pinned,
            declared["selected_lanes"][0],
            result_document_ids=[MECHANISM_ID, MECHANISM_ID],
        )
    )

    assert error.code == "INPUT_INVALID"


def test_a_receipt_the_canonical_schema_rejects_is_never_emitted() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    error = refused(
        lambda: searched_receipt(
            declared,
            pinned,
            declared["selected_lanes"][0],
            lane_decision_evidence_ids=[],
        )
    )

    assert error.code == "RECEIPT_REFUSED"
    assert error.context["errors"]


def test_a_search_state_outside_the_receipt_vocabulary_is_refused() -> None:
    error = refused(lambda: coverage_state("MOSTLY_SEARCHED"))

    assert error.code == "RECEIPT_STATE_UNDECLARED"


# -- layered novelty -------------------------------------------------------


def test_a_layer_the_vector_schema_does_not_declare_is_refused() -> None:
    scores = layer_scores()
    scores["vibe"] = 0.5
    error = refused(lambda: canonical_layer_scores(scores))

    assert error.code == "NOVELTY_LAYER_UNDECLARED"
    assert error.context["undeclared"] == ["vibe"]


def test_an_omitted_layer_is_refused_rather_than_read_as_zero() -> None:
    scores = layer_scores()
    scores.pop(next(iter(scores)))
    error = refused(lambda: canonical_layer_scores(scores))

    assert error.code == "NOVELTY_LAYER_UNDECLARED"
    assert error.context["missing"]


def test_a_non_numeric_layer_score_is_refused() -> None:
    scores = layer_scores()
    scores[next(iter(scores))] = "high"
    error = refused(lambda: canonical_layer_scores(scores))

    assert error.code == "NOVELTY_LAYER_UNDECLARED"


def test_a_corpus_bounded_search_cannot_declare_the_external_layer_complete() -> None:
    error = refused(
        lambda: assess_layered_novelty(
            **layered_arguments(external_search_completed=True)
        )
    )

    assert error.code == "EXTERNAL_LAYER_UNBOUNDED"
    assert error.context["unsearched_sources"] == sorted(UNSEARCHED_SOURCES)


def test_a_layer_score_outside_the_unit_interval_surfaces_the_owners_refusal() -> None:
    error = refused(
        lambda: assess_layered_novelty(
            **layered_arguments(layer_scores=layer_scores(claim_semantic=1.5))
        )
    )

    assert error.code == "VECTOR_REFUSED"


def test_an_assessment_bound_to_another_plans_boundary_is_refused() -> None:
    error = refused(
        lambda: assess_layered_novelty(**layered_arguments(boundary=other_boundary()))
    )

    assert error.code == "BOUNDARY_NOT_FROM_SNAPSHOT"


def test_a_prior_art_reference_outside_the_boundary_surfaces_k05s_refusal() -> None:
    error = refused(
        lambda: assess_layered_novelty(
            **layered_arguments(closest_prior_art_refs=["DOC-NOWHERE"])
        )
    )

    assert error.code == "SNAPSHOT_BOUNDARY_REFUSED"
    assert error.context["corpus_finding_code"] == "PRIOR_ART_OUTSIDE_BOUNDARY"


def test_a_relabelled_layered_record_does_not_re_derive_its_identity() -> None:
    layered = assess_layered_novelty(**layered_arguments())
    tampered = dict(layered, candidate_id="SOMEONE-ELSES-CANDIDATE")
    error = refused(lambda: require_layered_novelty_identity(tampered))

    assert error.code == "PLAN_DRIFT"


# -- coverage-debt acquisition --------------------------------------------


def test_ranking_with_no_niche_at_all_is_refused() -> None:
    error = refused(lambda: rank_acquisition_targets(niches=[]))

    assert error.code == "ACQUISITION_TARGETS_EMPTY"


def test_a_coverage_debt_outside_its_declared_range_is_refused() -> None:
    rows = niches()
    rows[0] = dict(rows[0], coverage_debt=1.5)
    error = refused(lambda: rank_acquisition_targets(niches=rows))

    assert error.code == "COVERAGE_DEBT_OUT_OF_RANGE"
    assert error.context["coverage_debt"] == 1.5


def test_a_negative_coverage_debt_is_refused_by_the_same_bound() -> None:
    rows = niches()
    rows[0] = dict(rows[0], coverage_debt=-0.1)
    error = refused(lambda: rank_acquisition_targets(niches=rows))

    assert error.code == "COVERAGE_DEBT_OUT_OF_RANGE"


def test_a_duplicated_map_cell_surfaces_the_cartography_refusal() -> None:
    rows = niches()
    error = refused(lambda: rank_acquisition_targets(niches=[*rows, rows[0]]))

    assert error.code == "NICHE_REFUSED"
    assert error.context["cartography_finding_code"] == "CELL_DUPLICATED"


def test_a_niche_the_schema_rejects_is_refused_before_it_is_ranked() -> None:
    rows = niches()
    rows[0] = {key: value for key, value in rows[0].items() if key != "elite_id"}
    error = refused(lambda: rank_acquisition_targets(niches=rows))

    assert error.code == "NICHE_REFUSED"


def test_a_budget_that_selects_nothing_is_refused() -> None:
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(target_budget=0)
        )
    )

    assert error.code == "TARGET_BUDGET_INVALID"


def test_a_non_integer_budget_is_refused() -> None:
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(target_budget="2")
        )
    )

    assert error.code == "TARGET_BUDGET_INVALID"


def test_a_negative_generation_is_refused() -> None:
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(generation=-1)
        )
    )

    assert error.code == "INPUT_INVALID"


def test_receipts_from_another_plan_are_refused() -> None:
    pinned = snapshot()
    first = plan(pinned)
    second = plan(pinned, run_id="ER-O05-2")
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(second, pinned, receipts=receipts(first, pinned))
        )
    )

    assert error.code == "RECEIPT_NOT_FROM_PLAN"


def test_a_receipt_set_missing_a_lane_is_refused() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)[1:]
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(declared, pinned, receipts=rows)
        )
    )

    assert error.code == "LANE_COVERAGE_INCOMPLETE"
    assert error.context["missing"] == [canonical_lane_order()[0]]


def test_two_receipts_for_one_lane_are_refused() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(declared, pinned, receipts=[*rows, rows[0]])
        )
    )

    assert error.code == "LANE_COVERAGE_INCOMPLETE"


def test_a_malformed_receipt_in_the_set_is_refused() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)
    rows[0] = dict(rows[0], lane_decision_evidence_ids=[])
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(declared, pinned, receipts=rows)
        )
    )

    assert error.code == "RECEIPT_REFUSED"


def test_a_blocked_adversarial_lane_cannot_ground_an_acquisition_plan() -> None:
    # The adversarial case: a receipt set that is complete, internally valid and
    # bound to the right plan, in which one selected adversarial lane never
    # actually answered. Treating that lane as covered is the exact failure the
    # search-state vocabulary exists to block.
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)
    lane = external_novelty_lane()
    states = receipt_state_vocabulary()
    stops = stop_reason_vocabulary()
    for position, receipt in enumerate(rows):
        if receipt["lane"] != lane:
            continue
        rows[position] = dict(
            receipt,
            search_state=states[states.index("BLOCKED")],
            result_ids=None,
            result_count=None,
            excluded_count=None,
            recall_proxy=None,
            stop_reason=stops[stops.index("policy_blocked")],
            errors=["the provider refused the query"],
        )
    error = refused(
        lambda: build_coverage_debt_acquisition_plan(
            **acquisition_arguments(declared, pinned, receipts=rows)
        )
    )

    assert error.code == "MANDATORY_LANE_UNCOVERED"
    assert error.context["lanes"] == [lane]


def test_a_relabelled_acquisition_plan_does_not_re_derive_its_identity() -> None:
    acquisition = build_coverage_debt_acquisition_plan(**acquisition_arguments())
    tampered = dict(acquisition, evolution_run_id="SOMEONE-ELSES-RUN")
    error = refused(lambda: require_acquisition_plan_identity(tampered))

    assert error.code == "PLAN_DRIFT"


def test_every_declared_finding_code_is_actually_reachable() -> None:
    # This runs last by declaration order and is what keeps the code table
    # honest: a refusal nothing can trigger is a refusal that does not exist.
    assert RAISED == set(FINDING_CODES), sorted(set(FINDING_CODES) - RAISED)
