from __future__ import annotations

import copy

import pytest

from .contracts import (
    CANONICAL_LANES,
    PlanningContractError,
    _digest_bytes,
    _expected_lane_query_text,
    _hash_excluding,
    compile_query_plan,
    reconcile_search_run,
    seal_search_lane_receipt,
    validate_search_completeness_certificate,
    validate_search_lane_receipt,
)
from .test_query_plan import HASH_A, HASH_B, HASH_C, HASH_D, proposal


SCOPE = {
    "domain": "learning_science",
    "population": "adults",
    "entity_type": None,
    "entity_subtype": None,
    "unit_of_analysis": None,
    "setting": None,
    "geography": None,
    "jurisdiction": None,
    "language": None,
    "lifecycle_stage": None,
    "spatial_scale": None,
    "temporal_scale": None,
    "time_period": None,
    "measurement_time": None,
    "intervention_or_exposure": None,
    "comparator": None,
    "inclusion_criteria": [],
    "exclusion_criteria": [],
    "conditions": {},
    "domain_extensions": {},
}


def plan_for(work_class: str = "E2"):
    value = proposal(work_class)
    value["scope_partitions"] = [SCOPE]
    return compile_query_plan(value)


def receipt_proposal(
    plan,
    lane: str,
    state: str,
    *,
    suffix: str = "1",
) -> dict[str, object]:
    payload = plan.payload
    decision = next(row for row in payload["lane_decisions"] if row["lane"] == lane)
    sentinel = state == "UNSEARCHED"
    successful = state in {"SEARCHED_NONE", "SEARCHED_WITH_RESULTS", "PARTIAL"}
    results = [f"EV-{lane}-{suffix}"] if state == "SEARCHED_WITH_RESULTS" else []
    if state == "PARTIAL":
        results = [f"EV-{lane}-{suffix}"]
    stops = {
        "SEARCHED_NONE": "exhausted_query_plan",
        "SEARCHED_WITH_RESULTS": "saturation_reached",
        "PARTIAL": "budget_exhausted",
        "BLOCKED": "credential_unavailable",
        "FAILED": "provider_failure",
    }
    return {
        "receipt_id": f"SLR-{lane}-{suffix}",
        "run_id": "RUN-1",
        "query_plan_id": payload["query_plan_id"],
        "plan_hash": payload["plan_hash"],
        "lane": lane,
        "receipt_kind": "SENTINEL" if sentinel else "EXECUTION",
        "sentinel_reason": decision["disposition"] if sentinel else None,
        "lane_decision_evidence_ids": list(decision["evidence_ids"]),
        "query_text": None if sentinel else _expected_lane_query_text(payload, lane),
        "scope_filter": None if sentinel else copy.deepcopy(SCOPE),
        "corpus_snapshot_hash": HASH_A if successful else None,
        "index_versions": {"index": "1.0.0"} if successful else None,
        "result_ids": results if successful else None,
        "result_count": len(results) if successful else None,
        "excluded_count": 0 if successful else None,
        "stop_reason": None if sentinel else stops[state],
        "search_state": state,
        "recall_proxy": 0.8 if successful else None,
        "errors": [] if sentinel or state in {"SEARCHED_NONE", "SEARCHED_WITH_RESULTS"} else [f"{state.lower()} reason"],
        "started_at": None if sentinel or state in {"BLOCKED", "FAILED"} else "2026-07-31T00:00:00Z",
        "finished_at": None if sentinel or state in {"BLOCKED", "FAILED"} else "2026-07-31T00:01:00Z",
    }


def complete_receipts(plan, overrides: dict[str, str] | None = None):
    overrides = overrides or {}
    selected = set(plan.payload["required_lanes"])
    result = []
    for lane in CANONICAL_LANES:
        default = "SEARCHED_NONE" if lane in selected else "UNSEARCHED"
        result.append(
            seal_search_lane_receipt(
                receipt_proposal(plan, lane, overrides.get(lane, default)),
                query_plan=plan,
            )
        )
    return result


@pytest.mark.parametrize(
    "state",
    ["UNSEARCHED", "SEARCHED_NONE", "SEARCHED_WITH_RESULTS", "PARTIAL", "BLOCKED", "FAILED"],
)
def test_receipt_completeness_test_all_six_states_are_typed(state: str) -> None:
    plan = plan_for("E1")
    lane = "mechanism" if state == "UNSEARCHED" else "lexical"
    receipt = seal_search_lane_receipt(
        receipt_proposal(plan, lane, state), query_plan=plan
    )

    assert receipt.payload["search_state"] == state
    validate_search_lane_receipt(receipt.payload)


def test_receipt_completeness_test_unsearched_execution_fields_are_null() -> None:
    plan = plan_for("E1")
    receipt = seal_search_lane_receipt(
        receipt_proposal(plan, "mechanism", "UNSEARCHED"), query_plan=plan
    ).payload

    for field in (
        "query_text",
        "query_hash",
        "scope_filter",
        "corpus_snapshot_hash",
        "index_versions",
        "result_ids",
        "result_count",
        "excluded_count",
        "stop_reason",
        "recall_proxy",
        "started_at",
        "finished_at",
    ):
        assert receipt[field] is None


def test_receipt_completeness_test_zero_results_are_not_unsearched() -> None:
    plan = plan_for("E1")
    searched = seal_search_lane_receipt(
        receipt_proposal(plan, "lexical", "SEARCHED_NONE"), query_plan=plan
    ).payload

    assert searched["receipt_kind"] == "EXECUTION"
    assert searched["result_count"] == 0
    assert searched["corpus_snapshot_hash"] == HASH_A


def test_receipt_completeness_test_scope_vector_contract_is_enforced_at_both_boundaries() -> None:
    shorthand = {"domain": "learning_science", "population": "adults"}
    plan_value = proposal("E1")
    plan_value["scope_partitions"] = [shorthand]

    with pytest.raises(PlanningContractError) as raised:
        compile_query_plan(plan_value)
    assert raised.value.code == "INPUT_INVALID"

    plan = plan_for("E1")
    receipt_value = receipt_proposal(plan, "lexical", "SEARCHED_NONE")
    receipt_value["scope_filter"] = shorthand
    with pytest.raises(PlanningContractError) as raised:
        seal_search_lane_receipt(receipt_value, query_plan=plan)
    assert raised.value.code == "INPUT_INVALID"


def test_receipt_completeness_test_result_count_and_query_hash_fail_closed() -> None:
    plan = plan_for("E1")
    receipt = seal_search_lane_receipt(
        receipt_proposal(plan, "lexical", "SEARCHED_WITH_RESULTS"), query_plan=plan
    ).payload
    receipt["result_count"] = 0
    with pytest.raises(PlanningContractError) as raised:
        validate_search_lane_receipt(receipt)
    assert raised.value.code == "RESULT_COUNT_MISMATCH"

    receipt = seal_search_lane_receipt(
        receipt_proposal(plan, "lexical", "SEARCHED_NONE"), query_plan=plan
    ).payload
    receipt["query_text"] = "tampered"
    with pytest.raises(PlanningContractError) as raised:
        validate_search_lane_receipt(receipt)
    assert raised.value.code == "QUERY_HASH_MISMATCH"


def test_receipt_completeness_test_query_hash_binds_exact_persisted_whitespace() -> None:
    plan_value = proposal("E1")
    plan_value["scope_partitions"] = [SCOPE]
    plan_value["forward_queries"] = ["  exact query text  "]
    plan = compile_query_plan(plan_value)
    proposal_value = receipt_proposal(plan, "lexical", "SEARCHED_NONE")

    receipt = seal_search_lane_receipt(proposal_value, query_plan=plan).payload

    assert "  exact query text  " in receipt["query_text"]
    validate_search_lane_receipt(receipt)

    receipt["query_text"] = receipt["query_text"].replace(
        "  exact query text  ", "exact query text"
    )
    with pytest.raises(PlanningContractError) as raised:
        validate_search_lane_receipt(receipt)
    assert raised.value.code == "QUERY_HASH_MISMATCH"


def test_receipt_completeness_test_sealer_rejects_unrelated_query_text() -> None:
    plan = plan_for("E1")
    proposal_value = receipt_proposal(plan, "lexical", "SEARCHED_NONE")
    proposal_value["query_text"] = "unrelated query text"

    with pytest.raises(PlanningContractError) as raised:
        seal_search_lane_receipt(proposal_value, query_plan=plan)
    assert raised.value.code == "RECEIPT_QUERY_MISMATCH"


@pytest.mark.parametrize(
    "different_queries",
    [
        ["first query", "second query", "extra query"],
        ["second query", "first query"],
    ],
    ids=["extra-query", "reordered-query-batch"],
)
def test_receipt_completeness_test_sealer_rejects_byte_different_query_batch(
    different_queries: list[str],
) -> None:
    plan_value = proposal("E1")
    plan_value["scope_partitions"] = [SCOPE]
    plan_value["forward_queries"] = ["first query", "second query"]
    plan = compile_query_plan(plan_value)
    proposal_value = receipt_proposal(plan, "lexical", "SEARCHED_NONE")

    different_plan_value = copy.deepcopy(plan_value)
    different_plan_value["forward_queries"] = different_queries
    different_plan = compile_query_plan(different_plan_value)
    proposal_value["query_text"] = _expected_lane_query_text(
        different_plan.payload, "lexical"
    )

    with pytest.raises(PlanningContractError) as raised:
        seal_search_lane_receipt(proposal_value, query_plan=plan)
    assert raised.value.code == "RECEIPT_QUERY_MISMATCH"


def test_receipt_completeness_test_reconciliation_rejects_self_consistent_unbound_query() -> None:
    plan = plan_for("E1")
    receipts = complete_receipts(plan)

    forged = next(row.payload for row in receipts if row.payload["lane"] == "lexical")
    unrelated_plan_value = proposal("E1")
    unrelated_plan_value["scope_partitions"] = [SCOPE]
    unrelated_plan_value["forward_queries"] = ["unrelated query"]
    unrelated_plan = compile_query_plan(unrelated_plan_value)
    forged_query_text = _expected_lane_query_text(
        unrelated_plan.payload, "lexical"
    )
    forged["query_text"] = forged_query_text
    forged["query_hash"] = _digest_bytes(forged_query_text.encode("utf-8"))
    forged["receipt_hash"] = _hash_excluding(forged, "receipt_hash")
    validate_search_lane_receipt(forged)
    forged_receipts = [
        forged if row.payload["lane"] == "lexical" else row for row in receipts
    ]

    with pytest.raises(PlanningContractError) as raised:
        reconcile_search_run(
            plan,
            forged_receipts,
            certificate_id="SCC-FORGED",
            run_id="RUN-1",
            subject_ref="INS-1",
            generated_at="2026-07-31T00:02:00Z",
        )
    assert raised.value.code == "RECEIPT_QUERY_MISMATCH"


def test_receipt_completeness_test_all_eleven_lanes_reconcile() -> None:
    plan = plan_for("E2")
    receipts = complete_receipts(plan, {"lexical": "SEARCHED_WITH_RESULTS"})
    certificate = reconcile_search_run(
        plan,
        receipts,
        certificate_id="SCC-1",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-07-31T00:02:00Z",
    )

    payload = certificate.payload
    assert len(payload["lane_reconciliations"]) == 11
    assert payload["completion_state"] == "PASS"
    assert payload["unsearched_lanes"] == ["mechanism", "external_novelty"]
    assert payload["absence_claim_ceiling"] == "CORPUS_CONDITIONAL"
    assert payload["novelty_claim_ceiling"] == "NOT_ASSESSED"
    validate_search_completeness_certificate(plan, receipts, payload)


def test_receipt_completeness_test_missing_selected_receipt_fails() -> None:
    plan = plan_for("E1")
    receipts = [row for row in complete_receipts(plan) if row.payload["lane"] != "lexical"]

    with pytest.raises(PlanningContractError) as raised:
        reconcile_search_run(
            plan,
            receipts,
            certificate_id="SCC-1",
            run_id="RUN-1",
            subject_ref="INS-1",
            generated_at="2026-07-31T00:02:00Z",
        )
    assert raised.value.code == "LANE_RECONCILIATION_MISSING"


def test_receipt_completeness_test_duplicate_unsearched_sentinel_fails() -> None:
    plan = plan_for("E1")
    receipts = complete_receipts(plan)
    extra = seal_search_lane_receipt(
        receipt_proposal(plan, "mechanism", "UNSEARCHED", suffix="2"),
        query_plan=plan,
    )

    with pytest.raises(PlanningContractError) as raised:
        reconcile_search_run(
            plan,
            [*receipts, extra],
            certificate_id="SCC-1",
            run_id="RUN-1",
            subject_ref="INS-1",
            generated_at="2026-07-31T00:02:00Z",
        )
    assert raised.value.code == "UNSEARCHED_SENTINEL_COUNT"


def test_receipt_completeness_test_unselected_execution_conflicts_with_sentinel() -> None:
    plan = plan_for("E1")
    receipts = complete_receipts(plan)
    execution = seal_search_lane_receipt(
        receipt_proposal(plan, "mechanism", "SEARCHED_NONE", suffix="2"),
        query_plan=plan,
    )

    with pytest.raises(PlanningContractError) as raised:
        reconcile_search_run(
            plan,
            [*receipts, execution],
            certificate_id="SCC-1",
            run_id="RUN-1",
            subject_ref="INS-1",
            generated_at="2026-07-31T00:02:00Z",
        )
    assert raised.value.code == "UNSEARCHED_SENTINEL_COUNT"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"lexical": "PARTIAL"}, "PARTIAL"),
        ({"lexical": "BLOCKED", "semantic": "PARTIAL"}, "BLOCKED"),
        ({"lexical": "FAILED", "semantic": "BLOCKED", "citation": "PARTIAL"}, "FAIL"),
    ],
)
def test_receipt_completeness_test_run_status_precedence(overrides: dict[str, str], expected: str) -> None:
    plan = plan_for("E1")
    certificate = reconcile_search_run(
        plan,
        complete_receipts(plan, overrides),
        certificate_id="SCC-1",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-07-31T00:02:00Z",
    ).payload

    assert certificate["completion_state"] == expected


def test_receipt_completeness_test_e0_is_explicit_not_required() -> None:
    plan = plan_for("E0")
    certificate = reconcile_search_run(
        plan,
        complete_receipts(plan),
        certificate_id="SCC-E0",
        run_id="RUN-1",
        subject_ref="REQ-1",
        generated_at="2026-07-31T00:02:00Z",
    ).payload

    assert certificate["completion_state"] == "NOT_REQUIRED"
    assert certificate["absence_claim_ceiling"] == "NONE"
    assert certificate["unsearched_lanes"] == list(CANONICAL_LANES)


def test_receipt_completeness_test_external_novelty_controls_only_novelty_ceiling() -> None:
    plan = plan_for("E5")
    none_found = reconcile_search_run(
        plan,
        complete_receipts(plan),
        certificate_id="SCC-E5-1",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-07-31T00:02:00Z",
    ).payload
    prior_art = reconcile_search_run(
        plan,
        complete_receipts(plan, {"external_novelty": "SEARCHED_WITH_RESULTS"}),
        certificate_id="SCC-E5-2",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-07-31T00:02:00Z",
    ).payload

    assert none_found["novelty_claim_ceiling"] == "SEARCH_CONDITIONAL"
    assert prior_art["novelty_claim_ceiling"] == "PRIOR_ART_FOUND"
    assert none_found["absence_claim_ceiling"] == "EXTERNAL_CONDITIONAL"


def test_receipt_completeness_test_reconciliation_does_not_mutate_inputs() -> None:
    plan = plan_for("E1")
    receipts = complete_receipts(plan)
    before_plan = plan.canonical_bytes
    before_receipts = [row.canonical_bytes for row in receipts]

    reconcile_search_run(
        plan,
        receipts,
        certificate_id="SCC-1",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-07-31T00:02:00Z",
    )

    assert plan.canonical_bytes == before_plan
    assert [row.canonical_bytes for row in receipts] == before_receipts
