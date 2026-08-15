"""scope_widening_test — a deduction may narrow a scope but never widen it.

Exit criterion under test: "scope widening rejected".  A conclusion is sound
only where all its premises hold, so dropping a boundary the premises carried,
or moving to a value no premise covers, is a refusal rather than a weaker
result.
"""

from __future__ import annotations

import pytest

from .contracts import (
    SCOPE_MAP_FIELDS,
    SCOPE_SCALAR_FIELDS,
    SCOPE_SET_FIELDS,
    EdgeType,
    NodeType,
    ProofTraceError,
    TraceStatus,
    build_proof_trace,
    scope_widening,
)
from .test_deduction_trace import edge, graph, node, scope


def intervention(name: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "category": "treatment",
        "duration": None,
        "frequency": None,
        "max_value": None,
        "min_value": None,
        "name": name,
        "rate": None,
        "route_or_delivery": None,
        "unit": None,
    }
    value.update(overrides)
    return value


def two_premise_graph(
    premise_scopes: list[dict[str, object]],
    conclusion_scope: dict[str, object],
) -> dict[str, object]:
    nodes = [
        node(
            f"N-premise-{index}",
            NodeType.PREMISE.value,
            evidence_ids=[f"EVN-{index}"],
            node_scope=premise_scope,
        )
        for index, premise_scope in enumerate(premise_scopes)
    ]
    nodes.append(
        node("N-conclusion", NodeType.CONCLUSION.value, node_scope=conclusion_scope)
    )
    edges = [
        edge(f"E-{index}", f"N-premise-{index}", "N-conclusion")
        for index in range(len(premise_scopes))
    ]
    return graph(nodes, edges)


def test_an_identical_scope_is_not_widening() -> None:
    assert scope_widening([scope()], scope()) == []


def test_narrowing_a_scalar_is_allowed() -> None:
    findings = scope_widening([scope(geography=None)], scope(geography="NL"))

    assert findings == []


def test_dropping_a_scalar_boundary_is_widening() -> None:
    findings = scope_widening([scope(geography="NL")], scope(geography=None))

    assert findings == [
        {"field": "geography", "kind": "DROPPED_BOUNDARY", "premise_values": ["NL"]}
    ]


def test_moving_to_a_value_no_premise_covers_is_refused() -> None:
    findings = scope_widening([scope(geography="NL")], scope(geography="JP"))

    assert findings == [
        {"field": "geography", "kind": "UNCOVERED_VALUE", "premise_values": ["NL"]}
    ]


def test_a_value_covered_by_one_premise_is_accepted() -> None:
    findings = scope_widening(
        [scope(geography="NL"), scope(geography="JP")], scope(geography="JP")
    )

    assert findings == []


def test_dropping_an_inclusion_criterion_is_widening() -> None:
    findings = scope_widening(
        [scope(inclusion_criteria=["soilless", "heated"])],
        scope(inclusion_criteria=["soilless"]),
    )

    assert findings == [
        {
            "dropped": ["heated"],
            "field": "inclusion_criteria",
            "kind": "DROPPED_CRITERIA",
        }
    ]


def test_adding_a_criterion_narrows_and_is_allowed() -> None:
    findings = scope_widening(
        [scope(inclusion_criteria=["soilless"])],
        scope(inclusion_criteria=["heated", "soilless"]),
    )

    assert findings == []


def test_criteria_from_every_premise_must_survive() -> None:
    findings = scope_widening(
        [
            scope(exclusion_criteria=["diseased"]),
            scope(exclusion_criteria=["stressed"]),
        ],
        scope(exclusion_criteria=["diseased"]),
    )

    assert findings == [
        {
            "dropped": ["stressed"],
            "field": "exclusion_criteria",
            "kind": "DROPPED_CRITERIA",
        }
    ]


def test_dropping_a_condition_is_widening() -> None:
    findings = scope_widening(
        [scope(conditions={"co2_ppm": 800})],
        scope(conditions={}),
    )

    assert findings == [{"field": "conditions.co2_ppm", "kind": "DROPPED_CONDITION"}]


def test_altering_a_condition_value_is_refused() -> None:
    findings = scope_widening(
        [scope(conditions={"co2_ppm": 800})],
        scope(conditions={"co2_ppm": 400}),
    )

    assert findings == [{"field": "conditions.co2_ppm", "kind": "ALTERED_CONDITION"}]


def test_a_domain_extension_is_governed_like_a_condition() -> None:
    findings = scope_widening(
        [scope(domain_extensions={"cultivar": "Sonata"})],
        scope(domain_extensions={}),
    )

    assert findings == [
        {"field": "domain_extensions.cultivar", "kind": "DROPPED_CONDITION"}
    ]


@pytest.mark.parametrize(
    ("premise_value", "conclusion_value"),
    [(True, 1), (1, True), ([True], [1]), ([1], [True])],
)
def test_json_boolean_and_number_conditions_are_not_equal(
    premise_value: object, conclusion_value: object
) -> None:
    findings = scope_widening(
        [scope(conditions={"flag": premise_value})],
        scope(conditions={"flag": conclusion_value}),
    )

    assert findings == [
        {"field": "conditions.flag", "kind": "ALTERED_CONDITION"}
    ]


def test_scope_scalar_fields_reject_non_string_values() -> None:
    malformed = two_premise_graph(
        [scope(geography="NL")], scope(geography=1)
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(malformed)

    assert caught.value.code == "INPUT_INVALID"


def test_scope_maps_reject_nested_non_scalar_values() -> None:
    malformed = two_premise_graph(
        [scope(conditions={"nested": {"value": 1}})],
        scope(conditions={"nested": {"value": 1}}),
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(malformed)

    assert caught.value.code == "INPUT_INVALID"


def test_schema_legal_empty_criteria_strings_remain_representable() -> None:
    trace = build_proof_trace(
        two_premise_graph(
            [scope(inclusion_criteria=[""])],
            scope(inclusion_criteria=[""]),
        )
    ).payload

    assert trace["status"] == TraceStatus.VALID.value


def test_dropping_an_intervention_boundary_is_widening() -> None:
    findings = scope_widening(
        [scope(intervention_or_exposure=intervention("nitrogen"))],
        scope(intervention_or_exposure=None),
    )

    assert len(findings) == 1
    assert findings[0]["field"] == "intervention_or_exposure"
    assert findings[0]["kind"] == "DROPPED_BOUNDARY"


def test_changing_an_intervention_is_outside_the_premise_scope() -> None:
    findings = scope_widening(
        [scope(intervention_or_exposure=intervention("nitrogen"))],
        scope(intervention_or_exposure=intervention("phosphorus")),
    )

    assert len(findings) == 1
    assert findings[0]["field"] == "intervention_or_exposure"
    assert findings[0]["kind"] == "UNCOVERED_VALUE"


def test_narrowing_an_intervention_range_is_allowed() -> None:
    findings = scope_widening(
        [
            scope(
                intervention_or_exposure=intervention(
                    "nitrogen", min_value=0, max_value=100, unit="kg/ha"
                )
            )
        ],
        scope(
            intervention_or_exposure=intervention(
                "nitrogen", min_value=20, max_value=60, unit="kg/ha"
            )
        ),
    )

    assert findings == []


def test_no_premises_means_nothing_to_widen_against() -> None:
    assert scope_widening([], scope(geography=None)) == []


def test_every_scalar_field_is_actually_checked() -> None:
    for field in SCOPE_SCALAR_FIELDS:
        findings = scope_widening([scope(**{field: "bound"})], scope(**{field: None}))

        assert findings == [
            {"field": field, "kind": "DROPPED_BOUNDARY", "premise_values": ["bound"]}
        ], field


def test_every_set_and_map_field_is_actually_checked() -> None:
    for field in SCOPE_SET_FIELDS:
        findings = scope_widening([scope(**{field: ["x"]})], scope(**{field: []}))
        assert findings == [
            {"dropped": ["x"], "field": field, "kind": "DROPPED_CRITERIA"}
        ], field
    for field in SCOPE_MAP_FIELDS:
        findings = scope_widening([scope(**{field: {"k": 1}})], scope(**{field: {}}))
        assert findings == [{"field": f"{field}.k", "kind": "DROPPED_CONDITION"}], field


def test_multiple_widenings_are_reported_together_and_sorted() -> None:
    findings = scope_widening(
        [scope(geography="NL", inclusion_criteria=["heated"], conditions={"c": 1})],
        scope(geography=None, inclusion_criteria=[], conditions={}),
    )

    assert [entry["field"] for entry in findings] == [
        "conditions.c",
        "geography",
        "inclusion_criteria",
    ]


def test_a_widened_conclusion_is_refused_by_the_engine() -> None:
    widened = two_premise_graph(
        [scope(geography="NL"), scope(geography="NL")], scope(geography=None)
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(widened)

    assert caught.value.code == "SCOPE_WIDENED"
    assert caught.value.context["node_id"] == "N-conclusion"
    assert caught.value.context["findings"][0]["kind"] == "DROPPED_BOUNDARY"


def test_the_engine_refuses_a_dropped_intervention_boundary() -> None:
    widened = two_premise_graph(
        [scope(intervention_or_exposure=intervention("nitrogen"))],
        scope(intervention_or_exposure=None),
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(widened)

    assert caught.value.code == "SCOPE_WIDENED"
    assert caught.value.context["findings"][0]["field"] == "intervention_or_exposure"


def test_a_narrowed_conclusion_is_accepted_and_recorded() -> None:
    narrowed = two_premise_graph(
        [scope(geography="NL"), scope(geography="NL")],
        scope(geography="NL", inclusion_criteria=["heated"]),
    )

    trace = build_proof_trace(narrowed).payload

    assert trace["scope_checks"] == [
        {"conclusion_id": "N-conclusion", "findings": [], "premise_count": 2}
    ]


def test_an_assumption_scope_does_not_license_a_wider_conclusion() -> None:
    # The assumption is unconstrained, but the premise is not: an unevidenced
    # statement must never be able to launder a scope the evidence never had.
    widened = graph(
        [
            node(
                "N-premise",
                NodeType.PREMISE.value,
                evidence_ids=["EVN-1"],
                node_scope=scope(geography="NL"),
            ),
            node(
                "N-assume",
                NodeType.ASSUMPTION.value,
                node_scope=scope(geography=None),
            ),
            node(
                "N-conclusion",
                NodeType.CONCLUSION.value,
                node_scope=scope(geography=None),
            ),
        ],
        [
            edge("E-1", "N-premise", "N-conclusion"),
            edge(
                "E-2",
                "N-assume",
                "N-conclusion",
                EdgeType.DEPENDS_ON_ASSUMPTION.value,
                rule_ref=None,
            ),
        ],
        hidden_assumption_ids=["N-assume"],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(widened)

    assert caught.value.code == "SCOPE_WIDENED"


def test_a_sealed_trace_may_not_carry_an_unresolved_widening() -> None:
    from .contracts import _hash_excluding, validate_proof_trace

    narrowed = two_premise_graph([scope(), scope()], scope())
    payload = build_proof_trace(narrowed).payload
    payload["scope_checks"][0]["findings"] = [
        {"field": "geography", "kind": "DROPPED_BOUNDARY", "premise_values": ["NL"]}
    ]
    payload["trace_hash"] = _hash_excluding(payload, "trace_hash")

    with pytest.raises(ProofTraceError) as caught:
        validate_proof_trace(payload)

    assert caught.value.code == "SCOPE_WIDENED"
