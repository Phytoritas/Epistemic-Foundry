"""argument_graph_validation — the three inference modes stay separate.

Exit criterion under test: "inference modes remain separate".  Induction,
deduction, and abduction each contribute their own verdict; none may stand in
for causal identification, each can only lower the ceiling, and a payload that
merges them into one score is refused.  The MechanismGraph and the R02
ArgumentGraph are both validated against their canonical schemas so the gate is
bound to the shared contracts rather than to a local convention.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .contracts import (
    INFERENCE_MODES,
    CausalGateError,
    Identification,
    InferenceMode,
    identification_ceiling,
    validate_causal_gate,
)
from .test_causal_overclaim import (
    ARGUMENT_GRAPH,
    clean_graph,
    collider_graph,
    evaluate,
    modes,
)

ROOT = Path(__file__).resolve().parents[4]


def mechanism_schema_validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "mechanism-graph.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def argument_schema_validator() -> Draft202012Validator:
    schemas = ROOT / "schemas"
    registry = Registry()
    for name in ("scope-vector.schema.json", "argument-graph.schema.json"):
        document = json.loads((schemas / name).read_text(encoding="utf-8"))
        for key in (name, str(document["$id"])):
            registry = registry.with_resource(
                key, Resource.from_contents(document, default_specification=DRAFT202012)
            )
    schema = json.loads(
        (schemas / "argument-graph.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, registry=registry)


def test_the_mechanism_graph_fixtures_satisfy_the_canonical_schema() -> None:
    validator = mechanism_schema_validator()

    for candidate in (clean_graph(), collider_graph()):
        assert sorted(validator.iter_errors(candidate), key=str) == []


def test_the_r02_argument_graph_fixture_satisfies_the_canonical_schema() -> None:
    from deduction.test_deduction_trace import grounded_graph

    validator = argument_schema_validator()

    assert sorted(validator.iter_errors(grounded_graph()), key=str) == []


def test_the_gate_records_one_verdict_per_mode_and_never_merges_them() -> None:
    record = evaluate(clean_graph()).payload

    assert [entry["mode"] for entry in record["mode_verdicts"]] == sorted(
        INFERENCE_MODES
    )
    for verdict in record["mode_verdicts"]:
        assert sorted(verdict) == ["artifact_id", "detail", "mode", "verdict"]


def test_a_missing_mode_fails_closed() -> None:
    partial = [
        entry for entry in modes() if entry["mode"] != InferenceMode.ABDUCTIVE.value
    ]

    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), mode_verdicts=partial)

    assert caught.value.code == "MODE_MISSING"
    assert caught.value.context["modes"] == ["ABDUCTIVE"]


def test_a_duplicated_mode_fails_closed() -> None:
    duplicated = [*modes(), modes()[0]]

    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), mode_verdicts=duplicated)

    assert caught.value.code == "MODE_DUPLICATED"


def test_an_unknown_mode_fails_closed() -> None:
    invalid = modes()
    invalid[0]["mode"] = "VIBES"

    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), mode_verdicts=invalid)

    assert caught.value.code == "MODE_INVALID"


def test_an_inductive_synthesis_carrying_a_causal_verdict_is_a_mode_collapse() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), mode_verdicts=modes(causal_identification="IDENTIFIED"))

    assert caught.value.code == "MODE_COLLAPSE"
    assert caught.value.context["artifact_id"] == "IS-1"


def test_an_aporia_record_arriving_pre_selected_is_a_mode_collapse() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), mode_verdicts=modes(selected="EXP-1"))

    assert caught.value.code == "MODE_COLLAPSE"
    assert caught.value.context["artifact_id"] == "AP-1"


def test_a_live_competing_explanation_caps_identification() -> None:
    record = evaluate(clean_graph(), mode_verdicts=modes(standing_conflicts=2)).payload

    assert record["identification_ceiling"] == Identification.ASSUMPTION_DEPENDENT.value
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value
    assert (
        "2 conflict(s) still carry competing explanations" in record["ceiling_reasons"]
    )


def test_a_broken_deductive_trace_caps_identification_at_not_identified() -> None:
    record = evaluate(
        clean_graph(), mode_verdicts=modes(deductive_status="BROKEN")
    ).payload

    assert record["identification_ceiling"] == Identification.NOT_IDENTIFIED.value
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value
    assert "the deductive trace rests on rejected support" in record["ceiling_reasons"]


def test_a_conditional_deductive_trace_caps_at_assumption_dependent() -> None:
    record = evaluate(
        clean_graph(), mode_verdicts=modes(deductive_status="CONDITIONAL")
    ).payload

    assert record["identification_ceiling"] == Identification.ASSUMPTION_DEPENDENT.value
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value
    assert (
        "the deductive trace depends on ledgered assumptions"
        in record["ceiling_reasons"]
    )


def test_an_incomplete_inductive_synthesis_caps_at_assumption_dependent() -> None:
    record = evaluate(
        clean_graph(), mode_verdicts=modes(inductive_status="PARTIAL")
    ).payload

    assert record["identification_ceiling"] == Identification.ASSUMPTION_DEPENDENT.value
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value
    assert "inductive synthesis is not complete" in record["ceiling_reasons"]


def test_no_mode_can_raise_the_ceiling_above_what_the_graph_supports() -> None:
    # Every mode is as favourable as it can be, yet the conditioned collider
    # still decides the outcome.
    record = evaluate(collider_graph(), conditioned_on=["C"]).payload

    assert record["identification_ceiling"] == Identification.IDENTIFIED.value
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_the_weakest_ceiling_wins_when_several_modes_object() -> None:
    ceiling, reasons = identification_ceiling(
        modes(
            inductive_status="PARTIAL",
            deductive_status="BROKEN",
            standing_conflicts=1,
        )
    )

    assert ceiling == Identification.NOT_IDENTIFIED.value
    assert len(reasons) == 3


def test_the_gate_names_the_argument_graph_it_was_bound_to() -> None:
    record = evaluate(clean_graph()).payload

    assert record["argument_graph_id"] == ARGUMENT_GRAPH


def test_a_sealed_gate_with_an_incomplete_mode_set_is_rejected() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(clean_graph()).payload
    payload["mode_verdicts"] = payload["mode_verdicts"][:2]
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "MODE_MISSING"


def test_a_sealed_gate_may_not_exceed_its_recorded_ceiling() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(clean_graph(), mode_verdicts=modes(standing_conflicts=1)).payload
    payload["identification_status"] = Identification.IDENTIFIED.value
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "IDENTIFICATION_STATUS_MISMATCH"


@pytest.mark.parametrize("value", [False, "0", 0.5, -1])
def test_aporia_conflict_count_is_not_coerced(value: object) -> None:
    verdicts = modes()
    abductive = next(
        entry for entry in verdicts if entry["mode"] == InferenceMode.ABDUCTIVE.value
    )
    abductive["detail"]["standing_conflict_count"] = value

    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), mode_verdicts=verdicts)

    assert caught.value.code == "INPUT_INVALID"


def test_rehashing_a_mode_detail_cannot_launder_the_ceiling() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(clean_graph()).payload
    abductive = next(
        entry
        for entry in payload["mode_verdicts"]
        if entry["mode"] == InferenceMode.ABDUCTIVE.value
    )
    abductive["detail"]["standing_conflict_count"] = 1
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "CEILING_MISMATCH"


def test_rehashing_a_failed_assessment_as_satisfied_is_rejected() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(collider_graph(), conditioned_on=["C"]).payload
    payload["assessments"]["collider"]["satisfied"] = True
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "ASSESSMENT_INCONSISTENT"


def test_gate_assessments_must_share_the_exact_mechanism_graph_hash() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(clean_graph()).payload
    payload["mechanism_graph_hash"] = "sha256:" + "f" * 64
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "ASSESSMENT_BINDING_MISMATCH"


def test_rehashing_time_order_as_established_is_fail_closed() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(clean_graph()).payload
    payload["assessments"]["time_order"]["edge_states"]["E-1"] = "ESTABLISHED"
    payload["assessments"]["time_order"]["unestablished_edge_ids"] = []
    payload["assessments"]["time_order"]["satisfied"] = True
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "TIME_ORDER_UNQUALIFIED"


def test_a_sealed_gate_missing_an_assessment_is_rejected() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(clean_graph()).payload
    del payload["assessments"]["collider"]
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "ASSESSMENT_INCOMPLETE"


def test_an_edge_endpoint_must_reference_a_declared_node() -> None:
    from .contracts import seal_mechanism_graph
    from .test_causal_overclaim import edge, node

    with pytest.raises(CausalGateError) as caught:
        seal_mechanism_graph(
            {
                "assumptions": [],
                "edges": [edge("E-1", "X", "GHOST")],
                "graph_hash": "sha256:" + "0" * 64,
                "identification_status": Identification.NOT_ASSESSED.value,
                "mechanism_graph_id": "MG-1",
                "nodes": [node("X", "cause")],
            }
        )

    assert caught.value.code == "EDGE_UNRESOLVED"
