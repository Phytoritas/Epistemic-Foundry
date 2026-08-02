from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "retrieval" / "o02" / "backend-responses.json"
CONTRACTS_PATH = ROOT / "python" / "epistemic_foundry" / "retrieval" / "lanes" / "contracts.py"


def load_contracts():
    name = "ef_o02_integrity_contracts"
    spec = importlib.util.spec_from_file_location(name, CONTRACTS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTRACTS = load_contracts()
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))


def sealed_request():
    return CONTRACTS.seal_backend_request(DATA["request"])


def sealed_response(request=None):
    request = request or sealed_request()
    return CONTRACTS.seal_backend_response(request, DATA["response_values"])


def candidate_validator() -> Draft202012Validator:
    schema_paths = list((ROOT / "schemas").glob("*.schema.json"))
    registry = Registry()
    loaded: dict[Path, dict[str, object]] = {}
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        loaded[path] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    candidate_schema = loaded[ROOT / "schemas" / "retrieval-candidate.schema.json"]
    return Draft202012Validator(candidate_schema, registry=registry)


def test_retrieval_candidate_schema_annotations_match_runtime_hash_contract() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "retrieval-candidate.schema.json").read_text(encoding="utf-8")
    )

    assert tuple(schema["x-canonical-identity"]["preimage_fields"]) == (
        CONTRACTS.CANDIDATE_IDENTITY_FIELDS
    )
    assert tuple(schema["x-canonical-hash"]["preimage_fields"]) == (
        CONTRACTS.CANDIDATE_HASH_FIELDS
    )
    assert schema["additionalProperties"] is False


def test_policy_and_workflow_bind_business_output_integrity_and_release_guard() -> None:
    policy = yaml.safe_load(
        (ROOT / "config" / "retrieval_policy.example.yaml").read_text(encoding="utf-8")
    )
    workflow = yaml.safe_load(
        (ROOT / "workflows" / "evidence_retrieval.workflow.yaml").read_text(encoding="utf-8")
    )

    assert policy["query_family_bindings"] == {
        lane: list(families) for lane, families in CONTRACTS.LANE_QUERY_FAMILIES.items()
    }
    assert policy["fusion_contract"]["k"] == 60
    assert policy["fusion_contract"]["learned_reranker_allowed"] is False
    assert policy["integrity_contract"]["silent_cross_channel_fallback_allowed"] is False
    assert set(policy["non_vector_release_guard"]["accepted_non_vector_origins"]) == set(
        CONTRACTS.NON_VECTOR_CHANNELS
    )
    candidate_contract = workflow["retrieval_candidate_contract"]
    assert candidate_contract["business_output_schema_ref"] == (
        "schemas/retrieval-candidate.schema.json"
    )
    assert candidate_contract["result_envelope_role"] == "telemetry_sidecar_only"
    assert candidate_contract["silent_fallback_allowed"] is False
    retrieval_nodes = [
        node
        for node in workflow["nodes"]
        if node["node_id"].startswith("retrieve_")
        and node["node_id"] != "retrieval_release_gate"
    ]
    assert len(retrieval_nodes) == 11
    for node in retrieval_nodes:
        checks = "\n".join(node["acceptance_checks"])
        assert "RetrievalCandidate business artifacts" in checks
        assert "no silent fallback or learned reranker" in checks


def test_provider_request_canonical_query_hash_and_replay_are_exact() -> None:
    first = sealed_request()
    reordered = dict(reversed(list(DATA["request"].items())))
    second = CONTRACTS.seal_backend_request(reordered)

    assert first.query_text == (
        '{"families":[{"family":"FORWARD","queries":'
        '["spaced retrieval practice delayed recall"]}],"lane":"lexical"}'
    )
    assert first.payload["query_hash"] == CONTRACTS.sha256_bytes(first.query_text.encode("utf-8"))
    assert first.request_hash == second.request_hash
    assert first.canonical_bytes == second.canonical_bytes


@pytest.mark.parametrize(
    ("lane", "families", "expected_code"),
    [
        ("counterevidence", ["FORWARD"], "INVALID_QUERY_FAMILY_BINDING"),
        ("null", ["FORWARD"], "INVALID_QUERY_FAMILY_BINDING"),
        ("unknown", ["FORWARD"], "LANE_UNKNOWN"),
    ],
)
def test_lane_query_family_binding_fails_closed(
    lane: str,
    families: list[str],
    expected_code: str,
) -> None:
    request = copy.deepcopy(DATA["request"])
    request["lane"] = lane
    request["query_families"] = families
    request["query_batch"]["lane"] = lane

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.seal_backend_request(request)

    assert raised.value.code == expected_code


def test_temporal_and_external_novelty_require_bounded_scope_contracts() -> None:
    temporal = copy.deepcopy(DATA["request"])
    temporal["lane"] = "temporal"
    temporal["query_batch"]["lane"] = "temporal"
    temporal["query_hash"] = CONTRACTS.sha256_bytes(
        CONTRACTS.canonical_json(temporal["query_batch"])
    )
    with pytest.raises(CONTRACTS.RetrievalContractError) as temporal_error:
        CONTRACTS.seal_backend_request(temporal)
    assert temporal_error.value.code == "TEMPORAL_FILTER_REQUIRED"

    novelty = copy.deepcopy(DATA["request"])
    novelty["lane"] = "external_novelty"
    novelty["query_families"] = ["NOVELTY"]
    novelty["query_batch"] = {
        "families": [{"family": "NOVELTY", "queries": ["external prior art"]}],
        "lane": "external_novelty",
    }
    novelty["query_hash"] = CONTRACTS.sha256_bytes(CONTRACTS.canonical_json(novelty["query_batch"]))
    with pytest.raises(CONTRACTS.RetrievalContractError) as novelty_error:
        CONTRACTS.seal_backend_request(novelty)
    assert novelty_error.value.code == "EXTERNAL_NOVELTY_SCOPE_REQUIRED"


def test_backend_response_dedupe_rrf_cutoff_and_candidate_schema() -> None:
    request = sealed_request()
    result = CONTRACTS.build_candidate_set(request, sealed_response(request))

    assert result.outcome.search_state == "SEARCHED_WITH_RESULTS"
    assert result.raw_hit_count == 4
    assert result.duplicate_count == 1
    assert result.cutoff_count == 0
    assert result.excluded_count == 1
    assert result.run_ceiling == "PASS"
    assert len(result.candidates) == 2

    support = next(row for row in result.candidates if row["source_span_id"] is not None)
    metadata = next(row for row in result.candidates if row["source_span_id"] is None)
    assert support["retrieval_channels"] == ["LEXICAL", "CITATION_GRAPH"]
    assert support["fusion_method"] == "RRF_K60"
    assert math.isclose(support["fusion_score"], 2 / 61, rel_tol=0, abs_tol=1e-15)
    assert support["duplicate_candidate_ids"] == [support["candidate_id"]]
    assert metadata["retrieval_channels"] == ["SEMANTIC"]
    assert metadata["fusion_method"] == "SINGLE_CHANNEL"
    assert metadata["multi_channel_verified"] is False

    validator = candidate_validator()
    for candidate in result.candidates:
        assert list(validator.iter_errors(candidate)) == []
        CONTRACTS.validate_retrieval_candidate(candidate)


def test_candidate_set_replay_is_byte_identical() -> None:
    request = sealed_request()
    response = sealed_response(request)

    first = CONTRACTS.build_candidate_set(request, response)
    second = CONTRACTS.build_candidate_set(request, copy.deepcopy(response))

    assert CONTRACTS.canonical_json(first.candidate_payloads()) == CONTRACTS.canonical_json(
        second.candidate_payloads()
    )


@pytest.mark.parametrize(
    ("field", "replacement", "expected_code"),
    [
        ("corpus_snapshot_hash", "sha256:" + "0" * 64, "STALE_RETRIEVAL_SNAPSHOT"),
        ("plan_hash", "sha256:" + "1" * 64, "RESPONSE_BINDING_MISMATCH"),
        ("query_hash", "sha256:" + "2" * 64, "RESPONSE_BINDING_MISMATCH"),
    ],
)
def test_resealed_response_binding_mismatches_fail_integrity(
    field: str,
    replacement: str,
    expected_code: str,
) -> None:
    request = sealed_request()
    response = sealed_response(request)
    response[field] = replacement
    response["response_hash"] = CONTRACTS.sha256_bytes(
        CONTRACTS.canonical_json({key: value for key, value in response.items() if key != "response_hash"})
    )

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.validate_backend_response(request, response)

    assert raised.value.code == expected_code
    assert raised.value.stop_reason == "integrity_failure"


def test_unresealed_backend_or_candidate_mutation_fails_hash_validation() -> None:
    request = sealed_request()
    response = sealed_response(request)
    response["hits"][0]["raw_rank"] = 99
    with pytest.raises(CONTRACTS.RetrievalContractError) as response_error:
        CONTRACTS.validate_backend_response(request, response)
    assert response_error.value.code == "BACKEND_RESPONSE_HASH_MISMATCH"

    candidate = CONTRACTS.build_candidate_set(request, sealed_response(request)).candidate_payloads()[0]
    candidate["source_locator"] = "fixture:tampered"
    with pytest.raises(CONTRACTS.RetrievalContractError) as candidate_error:
        CONTRACTS.validate_retrieval_candidate(candidate)
    assert candidate_error.value.code in {"CANDIDATE_ID_MISMATCH", "CANDIDATE_HASH_MISMATCH"}


@pytest.mark.parametrize(
    "case",
    DATA["terminal_cases"],
    ids=[row["case_id"] for row in DATA["terminal_cases"]],
)
def test_typed_terminal_and_no_fallback_semantics(case: dict[str, object]) -> None:
    request = sealed_request()
    values = {
        "backend_receipt_id": f"BREC-{case['case_id']}",
        "executed_query_families": (
            request.payload["query_families"] if case["status"] == "PARTIAL" else []
        ),
        "status": case["status"],
        "complete": case["complete"],
        "interrupted": case["interrupted"],
        "error_code": case["error_code"],
        "hits": [],
    }
    response = CONTRACTS.seal_backend_response(request, values)
    result = CONTRACTS.build_candidate_set(request, response)

    assert result.outcome.search_state == case["expected_state"]
    assert result.outcome.stop_reason == case["expected_reason"]
    assert result.candidates == ()
    assert result.run_ceiling == "PARTIAL"


def test_partial_response_preserves_validated_candidates_with_partial_ceiling() -> None:
    request = sealed_request()
    values = copy.deepcopy(DATA["response_values"])
    values.update(
        {
            "status": "PARTIAL",
            "complete": False,
            "interrupted": True,
            "error_code": "BOUNDED_TIMEOUT",
        }
    )
    response = CONTRACTS.seal_backend_response(request, values)
    result = CONTRACTS.build_candidate_set(request, response)

    assert result.outcome.search_state == "PARTIAL"
    assert len(result.candidates) == 2
    assert result.run_ceiling == "PARTIAL"


def test_complete_response_cannot_hide_missing_query_family() -> None:
    request_value = copy.deepcopy(DATA["request"])
    request_value["lane"] = "counterevidence"
    request_value["query_families"] = ["FORWARD", "REVERSE"]
    request_value["query_batch"] = {
        "families": [
            {"family": "FORWARD", "queries": ["support query"]},
            {"family": "REVERSE", "queries": ["reverse query"]},
        ],
        "lane": "counterevidence",
    }
    request_value["query_hash"] = CONTRACTS.sha256_bytes(
        CONTRACTS.canonical_json(request_value["query_batch"])
    )
    request = CONTRACTS.seal_backend_request(request_value)
    values = copy.deepcopy(DATA["response_values"])
    values["hits"] = []
    values["executed_query_families"] = ["FORWARD"]
    response = CONTRACTS.seal_backend_response(request, values)

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.validate_backend_response(request, response)

    assert raised.value.code == "INCOMPLETE_QUERY_FAMILY_EXECUTION"
