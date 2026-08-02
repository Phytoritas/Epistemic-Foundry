from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from .contracts import (
    CANONICAL_LANES,
    CLASS_LANE_FLOORS,
    PlanningContractError,
    compile_query_plan,
    validate_query_plan,
)


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
HASH_D = "sha256:" + "d" * 64
ROOT = Path(__file__).resolve().parents[4]


def proposal(work_class: str) -> dict[str, object]:
    e0 = work_class == "E0"
    return {
        "query_plan_id": f"QPLAN-{work_class}",
        "request_id": "REQ-1",
        "request_revision": 1,
        "request_input_hash": HASH_A,
        "classification_id": "EWC-" + "1" * 64,
        "classification_revision": 1,
        "classification_hash": HASH_B,
        "work_class": work_class,
        "classifier_version": "4.0.1-f01.1",
        "policy_bundle_hash": HASH_C,
        "insight_id": "INS-1",
        "insight_revision": 1,
        "canonical_relation": "bounded relation",
        "forward_queries": [] if e0 else ["bounded relation"],
        "reverse_queries": [] if e0 or work_class == "E1" else ["reverse relation"],
        "null_queries": [] if e0 or work_class == "E1" else ["null relation"],
        "boundary_queries": [] if e0 or work_class == "E1" else ["boundary relation"],
        "method_queries": [] if e0 or work_class == "E1" else ["measurement method"],
        "novelty_queries": ["external prior art"] if work_class == "E5" else [],
        "scope_partitions": [],
        "budget": {
            "max_queries": 0 if e0 else 40,
            "max_documents": 0 if e0 else 80,
            "max_seconds": 0 if e0 else 900,
        },
        "stop_rules": ["all selected lanes terminal"],
        "planner_prompt_hash": HASH_D,
        "created_at": "2026-07-31T00:00:00Z",
    }


@pytest.mark.parametrize("work_class", ["E0", "E1", "E2", "E3", "E4", "E5"])
def test_query_plan_test_exact_class_floor(work_class: str) -> None:
    plan = compile_query_plan(proposal(work_class)).payload

    assert plan["required_lanes"] == list(CLASS_LANE_FLOORS[work_class])
    assert plan["retrieval_requirement"] == ("NOT_REQUIRED" if work_class == "E0" else "REQUIRED")
    assert [row["lane"] for row in plan["lane_decisions"]] == list(CANONICAL_LANES)


def test_query_plan_test_optional_selection_can_only_add_a_lane() -> None:
    base = compile_query_plan(proposal("E1")).payload
    extended_proposal = proposal("E1")
    extended_proposal["reverse_queries"] = ["reverse relation"]
    extended_proposal["novelty_queries"] = ["external prior art"]
    extended = compile_query_plan(
        extended_proposal,
        selected_optional_lanes=["counterevidence", "external_novelty"],
        selection_evidence={"counterevidence": ["POLICY-1"]},
    ).payload

    assert set(base["required_lanes"]) < set(extended["required_lanes"])
    assert extended["required_lanes"] == [
        "lexical",
        "semantic",
        "citation",
        "counterevidence",
        "temporal",
        "external_novelty",
    ]


def test_query_plan_test_not_applicable_requires_typed_evidence() -> None:
    with pytest.raises(PlanningContractError) as raised:
        compile_query_plan(proposal("E1"), not_applicable_lanes=["mechanism"])
    assert raised.value.code == "APPLICABILITY_EVIDENCE_REQUIRED"

    plan = compile_query_plan(
        proposal("E1"),
        not_applicable_lanes=["mechanism"],
        applicability_evidence={"mechanism": ["GATE-NOT-APPLICABLE-1"]},
    ).payload
    decision = plan["lane_decisions"][4]
    assert decision["disposition"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("lane", ["lexical", "temporal"])
def test_query_plan_test_floor_lane_cannot_be_waived(lane: str) -> None:
    with pytest.raises(PlanningContractError) as raised:
        compile_query_plan(
            proposal("E1"),
            not_applicable_lanes=[lane],
            applicability_evidence={lane: ["WAIVER-1"]},
        )
    assert raised.value.code == "CLASS_FLOOR_WAIVER_FORBIDDEN"


@pytest.mark.parametrize("lane", ["support", "counter", "novelty", "custom", "unknown"])
def test_query_plan_test_noncanonical_lane_fails_closed(lane: str) -> None:
    with pytest.raises(PlanningContractError) as raised:
        compile_query_plan(proposal("E1"), selected_optional_lanes=[lane])
    expected = "LEGACY_LANE_REQUIRES_MIGRATION" if lane in {"counter", "novelty"} else "LANE_UNKNOWN"
    assert raised.value.code == expected


def test_query_plan_test_e0_cannot_select_retrieval() -> None:
    with pytest.raises(PlanningContractError) as raised:
        compile_query_plan(proposal("E0"), selected_optional_lanes=["lexical"])
    assert raised.value.code == "E0_RETRIEVAL_FORBIDDEN"


def test_query_plan_schema_rejects_selected_lane_in_e0() -> None:
    schema = json.loads((ROOT / "schemas/query-plan.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    candidate = compile_query_plan(proposal("E0")).payload
    candidate["lane_decisions"][0]["disposition"] = "SELECTED"
    candidate["lane_decisions"][0]["decision_reason"] = "POLICY_SELECTED"

    assert list(Draft202012Validator(schema).iter_errors(candidate))


def test_query_plan_schema_rejects_unselected_lane_in_e5() -> None:
    schema = json.loads((ROOT / "schemas/query-plan.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    candidate = compile_query_plan(proposal("E5")).payload
    candidate["lane_decisions"][-1]["disposition"] = "NOT_REQUIRED_FOR_CLASS"
    candidate["lane_decisions"][-1]["decision_reason"] = "NOT_REQUIRED_FOR_CLASS"

    assert list(Draft202012Validator(schema).iter_errors(candidate))


def test_query_plan_test_hash_binds_classification_and_lane_decisions() -> None:
    plan = compile_query_plan(proposal("E2")).payload
    validate_query_plan(plan)
    plan["classification_revision"] = 2

    with pytest.raises(PlanningContractError) as raised:
        validate_query_plan(plan)
    assert raised.value.code == "PLAN_HASH_MISMATCH"


def test_query_plan_test_input_order_and_replay_are_deterministic() -> None:
    original = proposal("E2")
    before = copy.deepcopy(original)
    reversed_input = dict(reversed(list(original.items())))

    first = compile_query_plan(original)
    second = compile_query_plan(reversed_input)

    assert original == before
    assert first.canonical_bytes == second.canonical_bytes
    assert first.payload["plan_hash"] == second.payload["plan_hash"]
    projection = first.payload
    projection["work_class"] = "E0"
    assert first.payload["work_class"] == "E2"


def test_query_plan_test_required_lanes_must_match_decisions() -> None:
    plan = compile_query_plan(proposal("E2")).payload
    plan["required_lanes"].remove("method")

    with pytest.raises(PlanningContractError) as raised:
        validate_query_plan(plan)
    assert raised.value.code in {"CLASS_FLOOR_VIOLATION", "LANE_SELECTION_MISMATCH"}
