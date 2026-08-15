from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "retrieval" / "o02" / "backend-responses.json"
CONTRACTS_PATH = ROOT / "python" / "epistemic_foundry" / "retrieval" / "lanes" / "contracts.py"


def load_contracts():
    name = "ef_o02_guard_contracts"
    spec = importlib.util.spec_from_file_location(name, CONTRACTS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTRACTS = load_contracts()
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_planning():
    """The O01 planning contracts the backend request is now bound to."""
    name = "ef_o02_guard_planning"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "python" / "epistemic_foundry" / "retrieval" / "planning" / "contracts.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture_query_plan():
    """Compile the QueryPlan the fixture request is a lane projection of."""
    planning = load_planning()
    request = DATA["request"]
    forward = [
        query
        for family in request["query_batch"]["families"]
        for query in family["queries"]
    ]
    return planning.compile_query_plan(
        {
            "query_plan_id": request["query_plan_id"],
            "request_id": "REQ-O02-FIXTURE-0001",
            "request_revision": 1,
            "request_input_hash": "sha256:" + "a" * 64,
            "classification_id": "CLS-O02-FIXTURE-0001",
            "classification_revision": 1,
            "classification_hash": "sha256:" + "b" * 64,
            "work_class": "E1",
            "classifier_version": "1.0.0",
            "policy_bundle_hash": "sha256:" + "c" * 64,
            "insight_id": "INS-O02-FIXTURE-0001",
            "insight_revision": 1,
            "canonical_relation": "spaced retrieval improves delayed recall",
            "forward_queries": forward,
            "reverse_queries": [],
            "null_queries": [],
            "boundary_queries": [],
            "method_queries": [],
            "novelty_queries": [],
            "scope_partitions": [],
            "budget": {"max_queries": 8, "max_documents": 40, "max_seconds": 30},
            "stop_rules": ["exhausted_query_plan"],
            "planner_prompt_hash": "sha256:" + "d" * 64,
            "created_at": "2026-08-14T00:00:00Z",
        }
    )


QUERY_PLAN = fixture_query_plan()


def bound_request():
    """The fixture request with its plan_hash bound to the compiled plan."""
    request = copy.deepcopy(DATA["request"])
    request["plan_hash"] = QUERY_PLAN.payload["plan_hash"]
    return request


COMPLETE_LANES = {
    "lexical": "SEARCHED_WITH_RESULTS",
    "semantic": "SEARCHED_WITH_RESULTS",
    "citation": "SEARCHED_WITH_RESULTS",
    "temporal": "SEARCHED_NONE",
}


def candidates() -> list[dict[str, object]]:
    request = CONTRACTS.seal_backend_request(bound_request(), query_plan=QUERY_PLAN)
    response = CONTRACTS.seal_backend_response(request, DATA["response_values"], query_plan=QUERY_PLAN)
    return CONTRACTS.build_candidate_set(request, response, query_plan=QUERY_PLAN).candidate_payloads()


def reseal(candidate: dict[str, object]) -> dict[str, object]:
    candidate["candidate_id"] = CONTRACTS.compute_candidate_id(candidate)
    candidate["candidate_hash"] = CONTRACTS.compute_candidate_hash(candidate)
    return candidate


def test_non_vector_origin_satisfies_assessment_but_metadata_is_not_direct_evidence() -> None:
    result = CONTRACTS.assess_non_vector_origin(
        candidates(),
        required_lane_states=COMPLETE_LANES,
    )

    assert result.satisfies_non_vector_policy is True
    assert result.assessed_ceiling == "PASS"
    assert result.reason == "non_vector_origin_present"
    assert len(result.metadata_only_candidate_ids) == 1
    assert len(result.direct_evidence_candidate_ids) == 1
    assert set(result.metadata_only_candidate_ids).isdisjoint(result.direct_evidence_candidate_ids)


def test_vector_only_candidate_is_retained_but_release_ceiling_is_partial() -> None:
    semantic = next(row for row in candidates() if row["retrieval_channels"] == ["SEMANTIC"])
    assert semantic["multi_channel_verified"] is False

    result = CONTRACTS.assess_non_vector_origin(
        [semantic],
        required_lane_states=COMPLETE_LANES,
    )

    assert result.satisfies_non_vector_policy is False
    assert result.assessed_ceiling == "PARTIAL"
    assert result.reason == "vector_only_release"
    assert result.vector_only_candidate_ids == (semantic["candidate_id"],)


def test_semantic_only_execution_cannot_pass_even_with_a_candidate() -> None:
    semantic = next(row for row in candidates() if row["retrieval_channels"] == ["SEMANTIC"])
    result = CONTRACTS.assess_non_vector_origin(
        [semantic],
        required_lane_states={"semantic": "SEARCHED_WITH_RESULTS"},
    )

    assert result.satisfies_non_vector_policy is False
    assert result.assessed_ceiling == "PARTIAL"
    assert result.reason == "required_lane_incomplete"


def test_complete_bounded_all_searched_none_can_pass_without_candidates() -> None:
    result = CONTRACTS.assess_non_vector_origin(
        [],
        required_lane_states={lane: "SEARCHED_NONE" for lane in COMPLETE_LANES},
    )

    assert result.satisfies_non_vector_policy is True
    assert result.assessed_ceiling == "PASS"
    assert result.reason == "complete_zero_results"


def test_silent_fallback_is_always_a_failure() -> None:
    result = CONTRACTS.assess_non_vector_origin(
        candidates(),
        required_lane_states=COMPLETE_LANES,
        silent_fallback_count=1,
    )

    assert result.satisfies_non_vector_policy is False
    assert result.assessed_ceiling == "FAIL"
    assert result.reason == "silent_fallback_detected"
    assert result.silent_fallback_count == 1


def test_candidate_cannot_falsely_claim_multi_channel_verification() -> None:
    semantic = copy.deepcopy(next(row for row in candidates() if row["retrieval_channels"] == ["SEMANTIC"]))
    semantic["multi_channel_verified"] = True
    reseal(semantic)

    try:
        CONTRACTS.validate_retrieval_candidate(semantic)
    except CONTRACTS.RetrievalContractError as error:
        assert error.code == "FUSION_CONTRACT_VIOLATION"
    else:
        raise AssertionError("single-channel candidate falsely claimed multi-channel verification")


def test_empty_source_span_cannot_be_rehashed_into_direct_evidence() -> None:
    candidate = copy.deepcopy(
        next(row for row in candidates() if row["source_span_id"] is None)
    )
    candidate["source_span_id"] = ""
    candidate["candidate_hash"] = CONTRACTS.compute_candidate_hash(candidate)

    with pytest.raises(CONTRACTS.RetrievalContractError) as candidate_error:
        CONTRACTS.validate_retrieval_candidate(candidate)
    assert candidate_error.value.code == "FIELD_INVALID"

    with pytest.raises(CONTRACTS.RetrievalContractError) as release_error:
        CONTRACTS.assess_non_vector_origin(
            [candidate],
            required_lane_states=COMPLETE_LANES,
        )
    assert release_error.value.code == "FIELD_INVALID"


def test_release_guard_rejects_scalar_candidate_containers() -> None:
    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.assess_non_vector_origin(
            "RC-not-an-array",
            required_lane_states=COMPLETE_LANES,
        )

    assert raised.value.code == "TYPE_MISMATCH"


def test_release_guard_rejects_boolean_fallback_counts() -> None:
    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.assess_non_vector_origin(
            [],
            required_lane_states=COMPLETE_LANES,
            silent_fallback_count=True,
        )

    assert raised.value.code == "FIELD_INVALID"
