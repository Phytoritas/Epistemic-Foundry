from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "retrieval" / "o02" / "backend-responses.json"
CONTRACTS_PATH = ROOT / "python" / "epistemic_foundry" / "retrieval" / "lanes" / "contracts.py"

# The checks above load the O02 component contracts directly from the component
# root, which is not what the wheel installs.  The checks at the end of this
# file exercise the shipped `src` lane runtime instead, because a lane whose
# component contracts pass while its shipped implementation misreports an
# unserved obligation would still license an unearned absence claim.
from epistemic_foundry.retrieval import lanes as shipped_lanes
from epistemic_foundry.retrieval import search_state as shipped_state


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


def load_planning():
    """The O01 planning contracts the backend request is now bound to."""
    name = "ef_o02_integrity_planning"
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
    """Compile the QueryPlan the fixture request is a lane projection of.

    Every backend call now binds to an exact O01 plan, so the fixture cannot
    seal a request without one. The forward queries are taken from the fixture's
    own query batch, which is what makes the projected lexical query hash equal
    the hash the fixture records.
    """
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


def bound_request(value=None):
    """The fixture request with its plan_hash bound to the compiled plan."""
    request = copy.deepcopy(value if value is not None else DATA["request"])
    request["plan_hash"] = QUERY_PLAN.payload["plan_hash"]
    return request


def sealed_request():
    return CONTRACTS.seal_backend_request(bound_request(), query_plan=QUERY_PLAN)


def sealed_response(request=None):
    request = request or sealed_request()
    return CONTRACTS.seal_backend_response(
        request, DATA["response_values"], query_plan=QUERY_PLAN
    )


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


def test_policy_and_workflow_bind_business_output_integrity_and_non_vector_assessment() -> None:
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
    assessment = policy["non_vector_release_guard"]
    assert assessment["raw_candidate_assessment_authority"] == "advisory_only"
    assert assessment["candidate_self_hash_release_authority"] is False
    assert set(assessment["accepted_non_vector_origins"]) == set(
        CONTRACTS.NON_VECTOR_CHANNELS
    )
    candidate_contract = workflow["retrieval_candidate_contract"]
    assert candidate_contract["business_output_schema_ref"] == (
        "schemas/retrieval-candidate.schema.json"
    )
    assert candidate_contract["result_envelope_role"] == "telemetry_sidecar_only"
    assert candidate_contract["silent_fallback_allowed"] is False
    assert candidate_contract["candidate_self_hash_release_authority"] is False
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
    second = CONTRACTS.seal_backend_request(reordered, query_plan=QUERY_PLAN)

    assert first.query_text == (
        '{"families":[{"family":"FORWARD","queries":'
        '["spaced retrieval practice delayed recall"]}],"lane":"lexical"}'
    )
    assert first.payload["query_hash"] == CONTRACTS.sha256_bytes(first.query_text.encode("utf-8"))
    assert first.request_hash == second.request_hash
    assert first.canonical_bytes == second.canonical_bytes


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.0, b"0"),
        (1.0, b"1"),
        (1e-6, b"0.000001"),
        (1e-7, b"1e-7"),
        (1e20, b"100000000000000000000"),
        (1e21, b"1e+21"),
        (333333333.33333329, b"333333333.3333333"),
        (2**68, b"295147905179352830000"),
    ],
)
def test_canonical_json_uses_ecmascript_binary64_number_text(
    value: int | float,
    expected: bytes,
) -> None:
    assert CONTRACTS.canonical_json(value) == expected


def test_canonical_json_uses_utf16_key_order_and_rejects_non_ijson_values() -> None:
    assert CONTRACTS.canonical_json({"\ue000": 1, "😀": 2}) == (
        '{"😀":2,"\ue000":1}'.encode("utf-8")
    )
    for value in (
        2**53 + 1,
        "\ud800",
        "\ufdd0",
        "\U0001fffe",
        {"\ufdd0": "forbidden key"},
    ):
        with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
            CONTRACTS.canonical_json(value)
        assert raised.value.code == "CANONICAL_JSON_INVALID"


def test_exact_large_binary64_integer_survives_sealed_request_roundtrip() -> None:
    request_value = copy.deepcopy(DATA["request"])
    request_value["deterministic_seed"] = 2**68

    sealed = CONTRACTS.seal_backend_request(request_value, query_plan=QUERY_PLAN)
    rebuilt = CONTRACTS.validate_sealed_backend_request(sealed, query_plan=QUERY_PLAN)

    assert b'"deterministic_seed":295147905179352830000' in sealed.canonical_bytes
    assert rebuilt.payload["deterministic_seed"] == 2**68


def test_public_lane_policy_and_candidate_results_cannot_be_mutated_in_place() -> None:
    with pytest.raises(TypeError):
        CONTRACTS.LANE_QUERY_FAMILIES["lexical"] = ("REVERSE",)

    result = CONTRACTS.build_candidate_set(sealed_request(), sealed_response(), query_plan=QUERY_PLAN)
    exposed = result.candidates
    original_locator = exposed[0]["source_locator"]
    exposed[0]["source_locator"] = "fixture:caller-mutation"

    assert result.candidates[0]["source_locator"] == original_locator

    validated = CONTRACTS.validate_backend_response(
        sealed_request(), sealed_response()
, query_plan=QUERY_PLAN)
    response_payload = validated.payload
    response_payload["hits"][0]["source_locator"] = "fixture:caller-mutation"
    assert not hasattr(validated, "_payload")
    assert validated.payload["hits"][0]["source_locator"] != "fixture:caller-mutation"


def test_sealed_request_is_rederived_before_every_authority_use() -> None:
    request = sealed_request()
    response = sealed_response(request)
    forged = CONTRACTS.SealedBackendRequest(
        _canonical_bytes=request.canonical_bytes,
        request_hash="sha256:" + "0" * 64,
        query_text=request.query_text,
    )

    assert not hasattr(request, "_payload")
    for operation in (
        lambda: CONTRACTS.validate_sealed_backend_request(forged, query_plan=QUERY_PLAN),
        lambda: CONTRACTS.seal_backend_response(forged, DATA["response_values"], query_plan=QUERY_PLAN),
        lambda: CONTRACTS.validate_backend_response(forged, response, query_plan=QUERY_PLAN),
        lambda: CONTRACTS.build_candidate_set(forged, response, query_plan=QUERY_PLAN),
    ):
        with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
            operation()
        assert raised.value.code == "REQUEST_INTEGRITY_INVALID"


def test_deep_sealed_request_is_typed_invalid_at_every_authority_use() -> None:
    request = sealed_request()
    response = sealed_response(request)
    deeply_nested = (b"[" * 2000) + b"0" + (b"]" * 2000)
    forged = CONTRACTS.SealedBackendRequest(
        _canonical_bytes=deeply_nested,
        request_hash="sha256:" + "0" * 64,
        query_text="{}",
    )

    for operation in (
        lambda: CONTRACTS.validate_sealed_backend_request(forged, query_plan=QUERY_PLAN),
        lambda: CONTRACTS.seal_backend_response(forged, DATA["response_values"], query_plan=QUERY_PLAN),
        lambda: CONTRACTS.validate_backend_response(forged, response, query_plan=QUERY_PLAN),
        lambda: CONTRACTS.build_candidate_set(forged, response, query_plan=QUERY_PLAN),
    ):
        with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
            operation()
        assert raised.value.code == "REQUEST_INTEGRITY_INVALID"


def test_nested_inputs_are_snapshotted_without_deepcopy_callbacks() -> None:
    class DeepcopyTrap:
        called = False

        def __deepcopy__(self, memo):
            self.called = True
            raise AssertionError("caller callback must not run")

    request_value = copy.deepcopy(DATA["request"])
    trap = DeepcopyTrap()
    request_value["scope_filter"]["domain_extensions"]["trap"] = trap

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.seal_backend_request(request_value, query_plan=QUERY_PLAN)

    assert raised.value.code == "CANONICAL_JSON_INVALID"
    assert trap.called is False


def test_projected_duplicate_mapping_keys_fail_before_sealing() -> None:
    class DuplicateItems(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise KeyError(key)

        def __iter__(self) -> Iterator[str]:
            return iter(("run_id", "run_id"))

        def __len__(self) -> int:
            return 2

        def items(self):
            return (("run_id", "RUN-1"), ("run_id", "RUN-2"))

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.seal_backend_request(DuplicateItems(), query_plan=QUERY_PLAN)

    assert raised.value.code == "CANONICAL_JSON_INVALID"


def test_candidate_hash_input_uses_the_same_recursive_snapshot_boundary() -> None:
    class DeepcopyTrap:
        called = False

        def __deepcopy__(self, memo):
            self.called = True
            raise AssertionError("caller callback must not run")

    candidate = CONTRACTS.build_candidate_set(
        sealed_request(), sealed_response()
, query_plan=QUERY_PLAN).candidate_payloads()[0]
    trap = DeepcopyTrap()
    candidate["scope_filter"]["domain_extensions"]["trap"] = trap

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.compute_candidate_hash(candidate)

    assert raised.value.code == "CANONICAL_JSON_INVALID"
    assert trap.called is False


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
        CONTRACTS.seal_backend_request(request, query_plan=QUERY_PLAN)

    assert raised.value.code == expected_code


def test_temporal_and_external_novelty_require_bounded_scope_contracts() -> None:
    temporal = copy.deepcopy(DATA["request"])
    temporal["lane"] = "temporal"
    temporal["query_batch"]["lane"] = "temporal"
    temporal["query_hash"] = CONTRACTS.sha256_bytes(
        CONTRACTS.canonical_json(temporal["query_batch"])
    )
    with pytest.raises(CONTRACTS.RetrievalContractError) as temporal_error:
        CONTRACTS.seal_backend_request(temporal, query_plan=QUERY_PLAN)
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
        CONTRACTS.seal_backend_request(novelty, query_plan=QUERY_PLAN)
    assert novelty_error.value.code == "EXTERNAL_NOVELTY_SCOPE_REQUIRED"


def test_backend_response_dedupe_rrf_cutoff_and_candidate_schema() -> None:
    request = sealed_request()
    result = CONTRACTS.build_candidate_set(request, sealed_response(request), query_plan=QUERY_PLAN)

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

    first = CONTRACTS.build_candidate_set(request, response, query_plan=QUERY_PLAN)
    second = CONTRACTS.build_candidate_set(request, copy.deepcopy(response), query_plan=QUERY_PLAN)

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
        CONTRACTS.validate_backend_response(request, response, query_plan=QUERY_PLAN)

    assert raised.value.code == expected_code
    assert raised.value.stop_reason == "integrity_failure"


def test_unresealed_backend_or_candidate_mutation_fails_hash_validation() -> None:
    request = sealed_request()
    response = sealed_response(request)
    response["hits"][0]["raw_rank"] = 99
    with pytest.raises(CONTRACTS.RetrievalContractError) as response_error:
        CONTRACTS.validate_backend_response(request, response, query_plan=QUERY_PLAN)
    assert response_error.value.code == "BACKEND_RESPONSE_HASH_MISMATCH"

    candidate = CONTRACTS.build_candidate_set(request, sealed_response(request), query_plan=QUERY_PLAN).candidate_payloads()[0]
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
    response = CONTRACTS.seal_backend_response(request, values, query_plan=QUERY_PLAN)
    result = CONTRACTS.build_candidate_set(request, response, query_plan=QUERY_PLAN)

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
    response = CONTRACTS.seal_backend_response(request, values, query_plan=QUERY_PLAN)
    result = CONTRACTS.build_candidate_set(request, response, query_plan=QUERY_PLAN)

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
    request = CONTRACTS.seal_backend_request(request_value, query_plan=QUERY_PLAN)
    values = copy.deepcopy(DATA["response_values"])
    values["hits"] = []
    values["executed_query_families"] = ["FORWARD"]
    response = CONTRACTS.seal_backend_response(request, values, query_plan=QUERY_PLAN)

    with pytest.raises(CONTRACTS.RetrievalContractError) as raised:
        CONTRACTS.validate_backend_response(request, response, query_plan=QUERY_PLAN)

    assert raised.value.code == "INCOMPLETE_QUERY_FAMILY_EXECUTION"


# ---------------------------------------------------------------------------
# Shipped `src` lane runtime: selected-but-unservable lanes
# ---------------------------------------------------------------------------


def shipped_context() -> "shipped_lanes.LaneContext":
    return shipped_lanes.LaneContext(
        run_id="RUN-o02",
        query_plan_id="QP-o02",
        plan_hash="sha256:" + "1" * 64,
        policy_bundle_hash="sha256:" + "2" * 64,
        capability_lease_id="TEST-LEASE",
        cutoff_policy_id="TEST-CUTOFF",
        corpus_snapshot_hash="sha256:" + "3" * 64,
        index_versions={"lexical_fts5": "1"},
        lane_decision_evidence_ids=("EV-1",),
        started_at="2026-08-14T00:00:00Z",
        finished_at="2026-08-14T00:00:01Z",
    )


def test_shipped_selected_unservable_lane_is_blocked_not_unsearched() -> None:
    """A lane the plan selected is owed a search; UNSEARCHED would retract it."""
    result = shipped_lanes.blocked_lane_result(
        shipped_context(), "semantic", queries=["stomatal conductance"]
    )
    receipt = result.receipt

    assert receipt["search_state"] == shipped_state.RECEIPT_STATE_BLOCKED
    assert receipt["receipt_kind"] == shipped_state.RECEIPT_KIND_EXECUTION
    assert receipt["sentinel_reason"] is None
    assert receipt["stop_reason"] == shipped_state.STOP_REASON_BACKEND_UNAVAILABLE
    assert receipt["errors"], "a blocked receipt must say why the search did not run"
    # Null, not zero: a count of zero is indistinguishable from a completed
    # empty search, which is exactly the inference this state exists to block.
    assert receipt["result_ids"] is None
    assert receipt["result_count"] is None
    assert receipt["excluded_count"] is None
    assert receipt["recall_proxy"] is None
    # The receipt still names the search that went unrun.
    assert receipt["query_text"]
    assert receipt["query_hash"]
    assert result.is_absence_of_evidence is False


def test_shipped_declined_lane_is_a_sentinel_with_no_backend_fields() -> None:
    result = shipped_lanes.absent_lane_result(shipped_context(), "semantic")
    receipt = result.receipt

    assert receipt["search_state"] == shipped_state.RECEIPT_STATE_UNSEARCHED
    assert receipt["receipt_kind"] == shipped_state.RECEIPT_KIND_SENTINEL
    assert receipt["sentinel_reason"]
    assert receipt["query_text"] is None
    assert receipt["corpus_snapshot_hash"] is None
    assert receipt["stop_reason"] is None
    assert receipt["errors"] == []


def test_shipped_blocked_receipt_binds_the_lane_query_family() -> None:
    """A NULL lane answered with a FORWARD query reports a different search."""
    result = shipped_lanes.blocked_lane_result(
        shipped_context(), "null", queries=["no effect"]
    )
    batch = json.loads(result.receipt["query_text"])

    assert [family["family"] for family in batch["families"]] == [
        shipped_state.QUERY_FAMILY_NULL
    ]


def test_shipped_multi_family_lane_refuses_a_single_family_blocked_receipt() -> None:
    """counterevidence needs FORWARD and REVERSE; one batch cannot name both."""
    with pytest.raises(shipped_lanes.LaneContractError) as raised:
        shipped_lanes.blocked_lane_result(
            shipped_context(), "counterevidence", queries=["support query"]
        )

    assert "FORWARD" in str(raised.value) and "REVERSE" in str(raised.value)


def test_shipped_blocked_receipt_rejects_a_non_blocked_stop_reason() -> None:
    with pytest.raises(shipped_lanes.LaneContractError):
        shipped_lanes.blocked_lane_receipt(
            shipped_context(),
            "semantic",
            queries=["q"],
            stop_reason=shipped_state.STOP_REASON_EXHAUSTED_QUERY_PLAN,
        )


def test_shipped_blocked_receipt_errors_stay_unique() -> None:
    """The receipt schema requires unique errors; duplicates must not survive."""
    receipt = shipped_lanes.blocked_lane_receipt(
        shipped_context(),
        "semantic",
        queries=["q"],
        errors=("same reason", "same reason", "  "),
    )

    assert receipt["errors"] == ["same reason"]


def test_shipped_reconciliation_separates_blocked_from_unsearched() -> None:
    context = shipped_context()
    reconciliation = shipped_lanes.reconcile_lanes(
        context,
        [shipped_lanes.blocked_lane_result(context, "semantic", queries=["q"])],
    )

    assert reconciliation["blocked_lanes"] == ["semantic"]
    assert "semantic" not in reconciliation["unsearched_lanes"]
    assert len(reconciliation["unsearched_lanes"]) == 10
    assert (
        reconciliation["receipt_states"]["semantic"]
        == shipped_state.RECEIPT_STATE_BLOCKED
    )
    assert reconciliation["all_lane_reconciliation_count"] == 11
    # A blocked lane answered nothing, so it cannot support an absence claim.
    assert reconciliation["absence_of_evidence_lanes"] == []


def test_shipped_blocked_receipt_satisfies_the_canonical_schema() -> None:
    schema_paths = list((ROOT / "schemas").glob("*.schema.json"))
    registry = Registry()
    loaded: dict[Path, dict[str, object]] = {}
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        loaded[path] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(
        loaded[ROOT / "schemas" / "search-lane-receipt.schema.json"], registry=registry
    )

    context = shipped_context()
    for result in (
        shipped_lanes.blocked_lane_result(context, "semantic", queries=["q"]),
        shipped_lanes.absent_lane_result(context, "mechanism"),
    ):
        assert list(validator.iter_errors(result.receipt)) == []


def test_shipped_run_ceiling_separates_silence_from_a_completed_empty_search() -> None:
    """An empty run and a completed empty search are not the same ceiling.

    A run that searched nothing cannot claim PASS; a lane that genuinely
    searched and found nothing can, because `SEARCHED_NONE` is a real result.
    Collapsing the two is how an unsearched run acquires an unearned ceiling.
    """
    context = shipped_context()

    empty = shipped_lanes.reconcile_lanes(context, [])
    assert empty["candidate_count"] == 0
    assert empty["absence_of_evidence_lanes"] == []
    assert empty["run_ceiling"] == shipped_state.RUN_CEILING_PARTIAL

    # A blocked lane answered nothing either, so it must not lift the ceiling.
    blocked = shipped_lanes.reconcile_lanes(
        context,
        [shipped_lanes.blocked_lane_result(context, "semantic", queries=["q"])],
    )
    assert blocked["run_ceiling"] == shipped_state.RUN_CEILING_PARTIAL
    assert blocked["absence_of_evidence_lanes"] == []


def test_shipped_backend_request_binds_the_lane_query_families() -> None:
    """The provider request carries the lane's own families, not always FORWARD."""
    batch = shipped_lanes._family_query_batch(
        "boundary", shipped_state.QUERY_FAMILY_BOUNDARY, ["threshold"]
    )
    _, query_hash = shipped_lanes._query_text_and_hash(batch)
    request = shipped_lanes._backend_request(
        shipped_context(), "boundary", batch, query_hash
    )

    assert request["query_families"] == [shipped_state.QUERY_FAMILY_BOUNDARY]
    assert request["canonical_query_batch"]["families"][0]["family"] == (
        shipped_state.QUERY_FAMILY_BOUNDARY
    )


def test_shipped_lane_query_families_match_the_canonical_workflow() -> None:
    """The workflow fixes which families the adversarial lanes accept."""
    workflow = yaml.safe_load(
        (ROOT / "workflows" / "evidence_retrieval.workflow.yaml").read_text(
            encoding="utf-8"
        )
    )
    checks_by_lane = {
        node["node_id"].removeprefix("retrieve_"): " ".join(
            node.get("acceptance_checks", [])
        )
        for node in workflow["nodes"]
        if node["node_id"].startswith("retrieve_")
    }

    # The four lanes whose families the workflow states explicitly.
    assert "both FORWARD and REVERSE" in checks_by_lane["counterevidence"]
    assert "only the NULL query family" in checks_by_lane["null"]
    assert "only the BOUNDARY query family" in checks_by_lane["boundary"]
    assert "only the METHOD query family" in checks_by_lane["method"]

    families = shipped_state.LANE_QUERY_FAMILIES
    assert families["counterevidence"] == (
        shipped_state.QUERY_FAMILY_FORWARD,
        shipped_state.QUERY_FAMILY_REVERSE,
    )
    assert families["null"] == (shipped_state.QUERY_FAMILY_NULL,)
    assert families["boundary"] == (shipped_state.QUERY_FAMILY_BOUNDARY,)
    assert families["method"] == (shipped_state.QUERY_FAMILY_METHOD,)
    assert set(families) == set(shipped_state.CANONICAL_LANES)


def test_shipped_lane_query_families_cannot_be_edited_at_runtime() -> None:
    """These values are hashed into sealed receipts; a runtime edit would
    silently change what a past query binding meant."""
    with pytest.raises(TypeError):
        shipped_state.LANE_QUERY_FAMILIES["null"] = ("FORWARD",)  # type: ignore[index]


def test_shipped_blocked_receipt_replays_to_the_same_hash() -> None:
    """Nothing in the lane runtime reads a clock, so replay is byte-stable."""
    first = shipped_lanes.blocked_lane_receipt(
        shipped_context(), "semantic", queries=["stomatal conductance"]
    )
    second = shipped_lanes.blocked_lane_receipt(
        shipped_context(), "semantic", queries=["stomatal conductance"]
    )

    assert first == second
    assert first["receipt_hash"] == second["receipt_hash"]


def test_shipped_query_batch_trims_and_deduplicates_before_hashing() -> None:
    """Two spellings of the same query set must not seal two different searches."""
    plain = shipped_lanes._family_query_batch("lexical", "FORWARD", ["a", "b"])
    noisy = shipped_lanes._family_query_batch(
        "lexical", "FORWARD", ["  a  ", "b", "a"]
    )

    assert plain == noisy
    assert (
        shipped_lanes._query_text_and_hash(plain)
        == shipped_lanes._query_text_and_hash(noisy)
    )


def test_shipped_query_batch_refuses_an_empty_query_set() -> None:
    with pytest.raises(shipped_lanes.LaneContractError):
        shipped_lanes._family_query_batch("lexical", "FORWARD", ["   ", ""])


def test_shipped_rrf_uses_the_declared_constant_and_a_stable_tie_break() -> None:
    """`RRF(d) = sum(1 / (k + rank))` with k fixed at 60, ties broken by key."""
    assert shipped_lanes.RRF_K == 60

    fused = shipped_lanes.rrf_fuse({"A": ["x", "y"], "B": ["y", "x"]})
    # Both documents rank 1 in one channel and 2 in the other, so the scores
    # tie exactly and the key decides.
    assert [row["key"] for row in fused] == ["x", "y"]
    assert fused[0]["rrf_score"] == pytest.approx(fused[1]["rrf_score"])
    assert fused[0]["channel_count"] == 2
