"""causal_overclaim_test — identification is derived, never declared.

Exit criterion under test: "colliders/confounders/time order assessed".  All
three assessments run on every evaluation, each can only lower the result, and
a declared status stronger than the derived one is refused rather than
recorded.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest

from .contracts import (
    IDENTIFICATION_LADDER,
    REQUIRED_ASSESSMENTS,
    CausalGateError,
    ConfounderState,
    Identification,
    InferenceMode,
    NodeRole,
    Relation,
    Sign,
    TimeOrderState,
    assess_colliders,
    assess_confounding,
    assess_time_order,
    evaluate_causal_gate,
    seal_mechanism_graph,
    validate_causal_gate,
)

CREATED_AT = "2026-08-01T12:00:00Z"
SUBJECT = "HYP-1"
ARGUMENT_GRAPH = "AG-1"


class DuplicateItemsMapping(Mapping[str, object]):
    def __init__(self, pairs: list[tuple[str, object]]) -> None:
        self.pairs = list(pairs)
        self.projected = dict(pairs)

    def __getitem__(self, key: str) -> object:
        return self.projected[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.projected)

    def __len__(self) -> int:
        return len(self.projected)

    def items(self) -> Iterator[tuple[str, object]]:
        return iter(self.pairs)


def node(node_id: str, role: str) -> dict[str, object]:
    return {"concept_id": f"CON-{node_id}", "node_id": node_id, "role": role}


def edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    relation: str = Relation.CAUSES.value,
    sign: str = Sign.POSITIVE.value,
    lag: str = "P1D",
) -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "lag": lag,
        "relation": relation,
        "sign": sign,
        "source": source,
        "target": target,
    }


def graph(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    *,
    assumptions: list[str] | None = None,
    declared: str = Identification.NOT_ASSESSED.value,
) -> dict[str, object]:
    return seal_mechanism_graph(
        {
            "assumptions": list(assumptions or []),
            "edges": edges,
            "graph_hash": "sha256:" + "0" * 64,
            "identification_status": declared,
            "mechanism_graph_id": "MG-1",
            "nodes": nodes,
        }
    )


def clean_graph(**kwargs) -> dict[str, object]:
    return graph(
        [
            node("X", NodeRole.CAUSE.value),
            node("Y", NodeRole.OUTCOME.value),
        ],
        [edge("E-1", "X", "Y")],
        **kwargs,
    )


def confounded_graph(**kwargs) -> dict[str, object]:
    return graph(
        [
            node("X", NodeRole.CAUSE.value),
            node("Y", NodeRole.OUTCOME.value),
            node("Z", NodeRole.CONFOUNDER.value),
        ],
        [edge("E-1", "X", "Y"), edge("E-2", "Z", "X"), edge("E-3", "Z", "Y")],
        **kwargs,
    )


def collider_graph(**kwargs) -> dict[str, object]:
    return graph(
        [
            node("X", NodeRole.CAUSE.value),
            node("W", NodeRole.CAUSE.value),
            node("C", NodeRole.MEDIATOR.value),
            node("Y", NodeRole.OUTCOME.value),
        ],
        [
            edge("E-1", "X", "Y"),
            edge("E-2", "X", "C"),
            edge("E-3", "W", "C"),
        ],
        **kwargs,
    )


def modes(
    *,
    inductive_status: str = "COMPLETE",
    deductive_status: str = "VALID",
    standing_conflicts: int = 0,
    selected: str | None = None,
    causal_identification: str = "NOT_ASSESSED",
) -> list[dict[str, object]]:
    return [
        {
            "artifact_id": "IS-1",
            "detail": {
                "causal_identification": causal_identification,
                "status": inductive_status,
            },
            "mode": InferenceMode.INDUCTIVE.value,
            "verdict": "positive association",
        },
        {
            "artifact_id": "PT-1",
            "detail": {"status": deductive_status},
            "mode": InferenceMode.DEDUCTIVE.value,
            "verdict": deductive_status,
        },
        {
            "artifact_id": "AP-1",
            "detail": {
                "selected_explanation_id": selected,
                "standing_conflict_count": standing_conflicts,
            },
            "mode": InferenceMode.ABDUCTIVE.value,
            "verdict": "open" if standing_conflicts else "no conflict",
        },
    ]


def evaluate(graph_payload, **kwargs):
    options = {
        "argument_graph_id": ARGUMENT_GRAPH,
        "created_at": CREATED_AT,
        "subject_id": SUBJECT,
    }
    options.update(kwargs)
    mode_verdicts = options.pop("mode_verdicts", None) or modes()
    return evaluate_causal_gate(graph_payload, mode_verdicts, **options)


def test_all_three_assessments_run_on_every_evaluation() -> None:
    record = evaluate(clean_graph()).payload

    assert sorted(record["assessments"]) == sorted(REQUIRED_ASSESSMENTS)
    assert record["assessments"]["collider"]["satisfied"] is True
    assert record["assessments"]["confounding"]["satisfied"] is True
    assert record["assessments"]["time_order"]["satisfied"] is False


def test_an_unqualified_lag_cannot_identify_even_a_clean_graph() -> None:
    record = evaluate(clean_graph()).payload

    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value
    assert record["identification_ceiling"] == Identification.IDENTIFIED.value
    assert record["ceiling_reasons"] == []


def test_an_unadjusted_confounder_blocks_identification() -> None:
    record = evaluate(confounded_graph()).payload

    confounding = record["assessments"]["confounding"]
    assert confounding["confounder_states"]["Z"] == ConfounderState.UNADJUSTED.value
    assert confounding["open_confounder_ids"] == ["Z"]
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_adjusting_the_confounder_does_not_substitute_for_time_order() -> None:
    record = evaluate(confounded_graph(), adjustment_set=["Z"]).payload

    assert record["assessments"]["confounding"]["satisfied"] is True
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_an_unmeasured_confounder_is_declared_but_still_open() -> None:
    record = evaluate(confounded_graph(), unmeasured_confounders=["Z"]).payload

    assert (
        record["assessments"]["confounding"]["confounder_states"]["Z"]
        == ConfounderState.UNMEASURED.value
    )
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_an_adjustment_for_an_undeclared_node_fails_closed() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(confounded_graph(), adjustment_set=["Q"])

    assert caught.value.code == "ADJUSTMENT_UNRESOLVED"


def test_an_unmeasured_undeclared_node_fails_closed() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(confounded_graph(), unmeasured_confounders=["Q"])

    assert caught.value.code == "ADJUSTMENT_UNRESOLVED"


def test_an_unmeasured_identifier_must_name_a_confounder_node() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(clean_graph(), unmeasured_confounders=["X"])

    assert caught.value.code == "ADJUSTMENT_UNRESOLVED"


def test_a_confounder_cannot_be_adjusted_and_unmeasured() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(
            confounded_graph(),
            adjustment_set=["Z"],
            unmeasured_confounders=["Z"],
        )

    assert caught.value.code == "INPUT_INVALID"


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("adjustment_set", "Z"),
        ("conditioned_on", "C"),
        ("unmeasured_confounders", "Z"),
        ("adjustment_set", {"Z": True}),
        ("conditioned_on", b"C"),
        ("unmeasured_confounders", [["Z"]]),
    ],
)
def test_assessment_identifier_inputs_must_be_json_arrays(
    argument: str, value: object
) -> None:
    payload = collider_graph() if argument == "conditioned_on" else confounded_graph()

    with pytest.raises(CausalGateError) as caught:
        evaluate(payload, **{argument: value})

    assert caught.value.code in {"INPUT_INVALID", "CANONICALIZATION_FAILED"}


def test_a_collider_is_detected_but_harmless_until_conditioned_on() -> None:
    record = evaluate(collider_graph()).payload

    assert record["assessments"]["collider"]["collider_ids"] == ["C"]
    assert record["assessments"]["collider"]["conditioned_collider_ids"] == []
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_conditioning_on_a_collider_blocks_identification() -> None:
    record = evaluate(collider_graph(), conditioned_on=["C"]).payload

    assert record["assessments"]["collider"]["conditioned_collider_ids"] == ["C"]
    assert record["assessments"]["collider"]["satisfied"] is False
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_conditioning_on_an_undeclared_node_fails_closed() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(collider_graph(), conditioned_on=["Q"])

    assert caught.value.code == "CONDITIONING_UNRESOLVED"


@pytest.mark.parametrize(
    "lag",
    ["unknown", "simultaneous", "none", "not_reported", "P1D", "garbage", "later-ish"],
)
def test_a_lag_that_establishes_no_order_blocks_identification(lag: str) -> None:
    payload = graph(
        [node("X", NodeRole.CAUSE.value), node("Y", NodeRole.OUTCOME.value)],
        [edge("E-1", "X", "Y", lag=lag)],
    )

    record = evaluate(payload).payload

    assert record["assessments"]["time_order"]["satisfied"] is False
    assert record["assessments"]["time_order"]["unestablished_edge_ids"] == ["E-1"]
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_a_duplicate_edge_id_cannot_overwrite_an_unknown_time_order() -> None:
    payload = graph(
        [node("X", NodeRole.CAUSE.value), node("Y", NodeRole.OUTCOME.value)],
        [
            edge("E-1", "X", "Y", lag="unknown"),
            edge("E-1", "X", "Y", lag="P1D"),
        ],
    )

    with pytest.raises(CausalGateError) as caught:
        evaluate(payload)

    assert caught.value.code == "DUPLICATE_EDGE"
    assert caught.value.context["edge_id"] == "E-1"


def test_graph_builder_rejects_duplicate_top_level_mapping_items() -> None:
    source = clean_graph()
    duplicate = DuplicateItemsMapping(
        [("mechanism_graph_id", "MG-shadow"), *source.items()]
    )

    with pytest.raises(CausalGateError) as caught:
        evaluate(duplicate)

    assert caught.value.code == "INPUT_INVALID"


def test_graph_sealer_rejects_duplicate_top_level_mapping_items() -> None:
    source = clean_graph()
    duplicate = DuplicateItemsMapping(
        [("mechanism_graph_id", "MG-shadow"), *source.items()]
    )

    with pytest.raises(CausalGateError) as caught:
        seal_mechanism_graph(duplicate)

    assert caught.value.code == "INPUT_INVALID"


def test_a_blank_lag_is_rejected_as_malformed_not_read_as_unknown() -> None:
    payload = graph(
        [node("X", NodeRole.CAUSE.value), node("Y", NodeRole.OUTCOME.value)],
        [edge("E-1", "X", "Y", lag="   ")],
    )

    with pytest.raises(CausalGateError) as caught:
        evaluate(payload)

    assert caught.value.code == "GRAPH_HASH_MISMATCH" or "lag" in str(caught.value)


def test_a_simultaneous_lag_is_distinguished_from_an_unknown_one() -> None:
    payload = graph(
        [node("X", NodeRole.CAUSE.value), node("Y", NodeRole.OUTCOME.value)],
        [edge("E-1", "X", "Y", lag="simultaneous")],
    )

    states = assess_time_order(
        {
            "edges": payload["edges"],
            "graph_hash": payload["graph_hash"],
            "mechanism_graph_id": payload["mechanism_graph_id"],
            "nodes": {"X": {}, "Y": {}},
        }
    )["edge_states"]

    assert states["E-1"] == TimeOrderState.SIMULTANEOUS.value


def test_a_purely_correlational_graph_establishes_no_time_order() -> None:
    payload = graph(
        [node("X", NodeRole.CAUSE.value), node("Y", NodeRole.OUTCOME.value)],
        [edge("E-1", "X", "Y", relation=Relation.CORRELATES.value)],
    )

    record = evaluate(payload).payload

    assert record["assessments"]["time_order"]["edge_states"] == {}
    assert record["assessments"]["time_order"]["satisfied"] is False
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_assumptions_cannot_override_missing_time_order() -> None:
    record = evaluate(clean_graph(assumptions=["no unmeasured confounding"])).payload

    assert record["assumptions"] == ["no unmeasured confounding"]
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_declaring_more_than_the_assessments_support_is_an_overclaim() -> None:
    with pytest.raises(CausalGateError) as caught:
        evaluate(confounded_graph(declared=Identification.IDENTIFIED.value))

    assert caught.value.code == "CAUSAL_OVERCLAIM"
    assert caught.value.context["declared"] == Identification.IDENTIFIED.value
    assert caught.value.context["derived"] == Identification.NOT_IDENTIFIED.value
    assert caught.value.context["failed_assessments"] == ["confounding"]


def test_declaring_identified_over_an_assumption_dependent_graph_is_an_overclaim() -> (
    None
):
    with pytest.raises(CausalGateError) as caught:
        evaluate(
            clean_graph(
                assumptions=["positivity"], declared=Identification.IDENTIFIED.value
            )
        )

    assert caught.value.code == "CAUSAL_OVERCLAIM"


def test_declaring_less_than_the_derived_status_is_allowed() -> None:
    record = evaluate(clean_graph(declared=Identification.NOT_ASSESSED.value)).payload

    assert (
        record["declared_identification_status"] == Identification.NOT_ASSESSED.value
    )
    assert record["identification_status"] == Identification.NOT_IDENTIFIED.value


def test_the_ladder_orders_weakest_to_strongest() -> None:
    assert IDENTIFICATION_LADDER == (
        "NOT_ASSESSED",
        "NOT_IDENTIFIED",
        "ASSUMPTION_DEPENDENT",
        "IDENTIFIED",
    )


def test_a_sealed_gate_cannot_be_upgraded_after_the_fact() -> None:
    from .contracts import _hash_excluding

    payload = evaluate(confounded_graph()).payload
    payload["identification_status"] = Identification.IDENTIFIED.value
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "IDENTIFICATION_STATUS_MISMATCH"


def test_a_tampered_gate_is_rejected() -> None:
    payload = evaluate(clean_graph()).payload
    payload["subject_id"] = "HYP-other"

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(payload)

    assert caught.value.code == "GATE_ID_MISMATCH"


def test_gate_validator_rejects_duplicate_top_level_mapping_items() -> None:
    payload = evaluate(clean_graph()).payload
    duplicate = DuplicateItemsMapping([("gate_id", "CG-shadow"), *payload.items()])

    with pytest.raises(CausalGateError) as caught:
        validate_causal_gate(duplicate)

    assert caught.value.code == "INPUT_INVALID"


def test_a_tampered_mechanism_graph_is_rejected() -> None:
    payload = clean_graph()
    payload["assumptions"] = ["smuggled in"]

    with pytest.raises(CausalGateError) as caught:
        evaluate(payload)

    assert caught.value.code == "GRAPH_HASH_MISMATCH"


def test_the_gate_is_deterministic_and_content_addressed() -> None:
    first = evaluate(clean_graph())
    second = evaluate(clean_graph())

    assert first.canonical_bytes == second.canonical_bytes
    assert first.payload["gate_id"].startswith("CG-")
    assert validate_causal_gate(first.payload).canonical_bytes == first.canonical_bytes


def test_assessment_helpers_agree_with_the_sealed_record() -> None:
    payload = confounded_graph()
    record = evaluate(payload, adjustment_set=["Z"]).payload
    nodes = {entry["node_id"]: entry for entry in payload["nodes"]}
    view = {
        "edges": payload["edges"],
        "graph_hash": payload["graph_hash"],
        "mechanism_graph_id": payload["mechanism_graph_id"],
        "nodes": nodes,
    }

    assert record["assessments"]["confounding"] == assess_confounding(view, ["Z"], ())
    assert record["assessments"]["collider"] == assess_colliders(view, ())
    assert record["assessments"]["time_order"] == assess_time_order(view)
