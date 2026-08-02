from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path


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
COMPLETE_LANES = {
    "lexical": "SEARCHED_WITH_RESULTS",
    "semantic": "SEARCHED_WITH_RESULTS",
    "citation": "SEARCHED_WITH_RESULTS",
    "temporal": "SEARCHED_NONE",
}


def candidates() -> list[dict[str, object]]:
    request = CONTRACTS.seal_backend_request(DATA["request"])
    response = CONTRACTS.seal_backend_response(request, DATA["response_values"])
    return CONTRACTS.build_candidate_set(request, response).candidate_payloads()


def reseal(candidate: dict[str, object]) -> dict[str, object]:
    candidate["candidate_id"] = CONTRACTS.compute_candidate_id(candidate)
    candidate["candidate_hash"] = CONTRACTS.compute_candidate_hash(candidate)
    return candidate


def test_non_vector_origin_allows_release_but_metadata_is_not_direct_evidence() -> None:
    result = CONTRACTS.evaluate_non_vector_release(
        candidates(),
        required_lane_states=COMPLETE_LANES,
    )

    assert result.allowed is True
    assert result.run_ceiling == "PASS"
    assert result.reason == "non_vector_origin_present"
    assert len(result.metadata_only_candidate_ids) == 1
    assert len(result.direct_evidence_candidate_ids) == 1
    assert set(result.metadata_only_candidate_ids).isdisjoint(result.direct_evidence_candidate_ids)


def test_vector_only_candidate_is_retained_but_release_ceiling_is_partial() -> None:
    semantic = next(row for row in candidates() if row["retrieval_channels"] == ["SEMANTIC"])
    assert semantic["multi_channel_verified"] is False

    result = CONTRACTS.evaluate_non_vector_release(
        [semantic],
        required_lane_states=COMPLETE_LANES,
    )

    assert result.allowed is False
    assert result.run_ceiling == "PARTIAL"
    assert result.reason == "vector_only_release"
    assert result.vector_only_candidate_ids == (semantic["candidate_id"],)


def test_semantic_only_execution_cannot_pass_even_with_a_candidate() -> None:
    semantic = next(row for row in candidates() if row["retrieval_channels"] == ["SEMANTIC"])
    result = CONTRACTS.evaluate_non_vector_release(
        [semantic],
        required_lane_states={"semantic": "SEARCHED_WITH_RESULTS"},
    )

    assert result.allowed is False
    assert result.run_ceiling == "PARTIAL"
    assert result.reason == "required_lane_incomplete"


def test_complete_bounded_all_searched_none_can_pass_without_candidates() -> None:
    result = CONTRACTS.evaluate_non_vector_release(
        [],
        required_lane_states={lane: "SEARCHED_NONE" for lane in COMPLETE_LANES},
    )

    assert result.allowed is True
    assert result.run_ceiling == "PASS"
    assert result.reason == "complete_zero_results"


def test_silent_fallback_is_always_a_failure() -> None:
    result = CONTRACTS.evaluate_non_vector_release(
        candidates(),
        required_lane_states=COMPLETE_LANES,
        silent_fallback_count=1,
    )

    assert result.allowed is False
    assert result.run_ceiling == "FAIL"
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
