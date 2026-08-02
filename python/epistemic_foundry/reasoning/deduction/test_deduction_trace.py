"""deduction_trace_test — premises are source-bound or ledgered assumptions.

Exit criterion under test: "premises source-bound or assumptions".  Nothing a
conclusion rests on may be silently unsupported: a premise must cite evidence,
an unevidenced statement must be an assumption, and the engine derives the
load-bearing assumptions itself so an undeclared one is a failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .contracts import (
    EdgeType,
    Grounding,
    NodeStatus,
    NodeType,
    ProofTraceError,
    TraceStatus,
    build_proof_trace,
    seal_argument_graph,
    validate_proof_trace,
)

ROOT = Path(__file__).resolve().parents[4]
CREATED_AT = "2026-08-01T10:00:00Z"


def graph_schema_validator() -> Draft202012Validator:
    schemas = ROOT / "schemas"
    registry = Registry()
    for name in ("scope-vector.schema.json", "argument-graph.schema.json"):
        document = json.loads((schemas / name).read_text(encoding="utf-8"))
        registry = registry.with_resource(
            name, Resource.from_contents(document, default_specification=DRAFT202012)
        )
        registry = registry.with_resource(
            str(document["$id"]),
            Resource.from_contents(document, default_specification=DRAFT202012),
        )
    schema = json.loads(
        (schemas / "argument-graph.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, registry=registry)


def scope(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "comparator": None,
        "conditions": {},
        "domain": "agronomy",
        "domain_extensions": {},
        "entity_subtype": None,
        "entity_type": "crop",
        "exclusion_criteria": [],
        "geography": None,
        "inclusion_criteria": [],
        "intervention_or_exposure": None,
        "jurisdiction": None,
        "language": None,
        "lifecycle_stage": None,
        "measurement_time": None,
        "population": "greenhouse strawberry",
        "setting": None,
        "spatial_scale": None,
        "temporal_scale": None,
        "time_period": None,
        "unit_of_analysis": None,
    }
    value.update(overrides)
    return value


def node(
    node_id: str,
    node_type: str,
    *,
    evidence_ids: list[str] | None = None,
    status: str = NodeStatus.ASSERTED.value,
    statement: str | None = None,
    node_scope: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "argument_node_id": node_id,
        "evidence_ids": list(evidence_ids or []),
        "node_type": node_type,
        "scope": node_scope if node_scope is not None else scope(),
        "statement": statement or f"statement for {node_id}",
        "status": status,
    }


def edge(
    edge_id: str,
    from_id: str,
    to_id: str,
    edge_type: str = EdgeType.DEDUCTIVELY_IMPLIES.value,
    *,
    rule_ref: str | None = "RULE-modus-ponens",
    confidence: float | None = None,
) -> dict[str, object]:
    return {
        "confidence": confidence,
        "edge_id": edge_id,
        "edge_type": edge_type,
        "from_id": from_id,
        "rule_ref": rule_ref,
        "to_id": to_id,
    }


def graph(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    *,
    hidden_assumption_ids: list[str] | None = None,
    unresolved_objection_ids: list[str] | None = None,
) -> dict[str, object]:
    return seal_argument_graph(
        {
            "argument_graph_id": "AG-1",
            "created_at": CREATED_AT,
            "edges": edges,
            "graph_hash": "sha256:" + "0" * 64,
            "hidden_assumption_ids": list(hidden_assumption_ids or []),
            "hypothesis_id": "HYP-1",
            "nodes": nodes,
            "proof_trace_artifact_id": None,
            "run_id": "RUN-1",
            "unresolved_objection_ids": list(unresolved_objection_ids or []),
        }
    )


def grounded_graph() -> dict[str, object]:
    return graph(
        [
            node("N-premise-a", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-premise-b", NodeType.PREMISE.value, evidence_ids=["EVN-2"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [
            edge("E-1", "N-premise-a", "N-conclusion"),
            edge("E-2", "N-premise-b", "N-conclusion"),
        ],
    )


def assumed_graph() -> dict[str, object]:
    return graph(
        [
            node("N-assume", NodeType.ASSUMPTION.value),
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
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


def test_the_fixture_graphs_satisfy_the_canonical_schema() -> None:
    validator = graph_schema_validator()

    for candidate in (grounded_graph(), assumed_graph()):
        assert sorted(validator.iter_errors(candidate), key=str) == []


def test_a_fully_grounded_trace_is_valid_and_carries_no_assumptions() -> None:
    trace = build_proof_trace(grounded_graph()).payload

    assert trace["status"] == TraceStatus.VALID.value
    assert trace["assumption_ledger"] == []
    assert trace["conclusions"][0]["premise_ids"] == ["N-premise-a", "N-premise-b"]
    assert trace["conclusions"][0]["assumption_ids"] == []
    assert trace["conclusions"][0]["support_is_complete"] is True
    assert trace["proof_trace_id"].startswith("PT-")


def test_a_premise_without_evidence_is_refused() -> None:
    broken = graph(
        [
            node("N-premise", NodeType.PREMISE.value),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [edge("E-1", "N-premise", "N-conclusion")],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(broken)

    assert caught.value.code == "PREMISE_UNGROUNDED"
    assert caught.value.context["node_id"] == "N-premise"


def test_an_unevidenced_statement_may_stand_only_as_a_ledgered_assumption() -> None:
    trace = build_proof_trace(assumed_graph()).payload

    assert trace["status"] == TraceStatus.CONDITIONAL.value
    assert [entry["assumption_id"] for entry in trace["assumption_ledger"]] == [
        "N-assume"
    ]
    assert trace["assumption_ledger"][0]["grounding"] == Grounding.UNGROUNDED.value
    assert trace["assumption_ledger"][0]["dependents"] == ["N-conclusion"]
    assert trace["conclusions"][0]["assumption_ids"] == ["N-assume"]


def test_an_assumption_with_partial_evidence_is_recorded_as_such() -> None:
    supported = graph(
        [
            node("N-assume", NodeType.ASSUMPTION.value, evidence_ids=["EVN-9"]),
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
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
    )

    trace = build_proof_trace(supported).payload

    assert (
        trace["assumption_ledger"][0]["grounding"]
        == Grounding.PARTIALLY_SUPPORTED.value
    )
    assert trace["assumption_ledger"][0]["evidence_ids"] == ["EVN-9"]


def test_an_undeclared_load_bearing_assumption_fails_closed() -> None:
    undeclared = assumed_graph()
    undeclared["hidden_assumption_ids"] = []
    undeclared = seal_argument_graph(undeclared)

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(undeclared)

    assert caught.value.code == "HIDDEN_ASSUMPTION_UNDECLARED"
    assert caught.value.context["derived"] == ["N-assume"]


def test_declaring_an_assumption_that_nothing_rests_on_fails_closed() -> None:
    overdeclared = grounded_graph()
    overdeclared["hidden_assumption_ids"] = ["N-premise-a"]
    overdeclared = seal_argument_graph(overdeclared)

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(overdeclared)

    assert caught.value.code == "HIDDEN_ASSUMPTION_UNDECLARED"


def test_a_hidden_assumption_id_must_reference_a_declared_node() -> None:
    dangling = assumed_graph()
    dangling["hidden_assumption_ids"] = ["N-ghost"]
    dangling = seal_argument_graph(dangling)

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(dangling)

    assert caught.value.code == "HIDDEN_ASSUMPTION_UNKNOWN"


def test_an_unsupported_intermediate_node_cannot_carry_a_conclusion() -> None:
    floating = graph(
        [
            node("N-claim", NodeType.PREDICTION.value),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [edge("E-1", "N-claim", "N-conclusion")],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(floating)

    assert caught.value.code == "SUPPORT_UNGROUNDED"
    assert caught.value.context["unsupported"] == ["N-claim"]


def test_a_conclusion_with_no_support_is_refused() -> None:
    isolated = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [
            edge(
                "E-1",
                "N-premise",
                "N-conclusion",
                EdgeType.COMPETES_WITH.value,
                rule_ref=None,
            )
        ],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(isolated)

    assert caught.value.code == "CONCLUSION_UNSUPPORTED"


def test_a_deductive_edge_must_name_its_rule() -> None:
    unruled = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [edge("E-1", "N-premise", "N-conclusion", rule_ref=None)],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(unruled)

    assert caught.value.code == "RULE_UNDECLARED"


def test_an_edge_endpoint_must_exist() -> None:
    dangling = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [
            edge("E-1", "N-premise", "N-conclusion"),
            edge("E-2", "N-ghost", "N-conclusion"),
        ],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(dangling)

    assert caught.value.code == "EDGE_UNRESOLVED"


def test_a_supporting_cycle_is_refused() -> None:
    looped = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-mid", NodeType.CLAIM.value, evidence_ids=["EVN-2"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [
            edge("E-1", "N-premise", "N-mid"),
            edge("E-2", "N-mid", "N-conclusion"),
            edge("E-3", "N-conclusion", "N-mid"),
        ],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(looped)

    assert caught.value.code == "PROOF_CYCLE"


def test_rejected_support_marks_the_trace_broken() -> None:
    contested = graph(
        [
            node(
                "N-premise",
                NodeType.PREMISE.value,
                evidence_ids=["EVN-1"],
                status=NodeStatus.REJECTED.value,
            ),
            node("N-good", NodeType.PREMISE.value, evidence_ids=["EVN-2"]),
            node(
                "N-conclusion",
                NodeType.CONCLUSION.value,
                status=NodeStatus.CHALLENGED.value,
            ),
        ],
        [
            edge("E-1", "N-premise", "N-conclusion"),
            edge("E-2", "N-good", "N-conclusion"),
        ],
    )

    trace = build_proof_trace(contested).payload

    assert trace["status"] == TraceStatus.BROKEN.value
    assert trace["broken_edges"] == [
        {
            "conclusion_id": "N-conclusion",
            "node_id": "N-premise",
            "reason": "REJECTED_SUPPORT",
        }
    ]
    assert trace["conclusions"][0]["support_is_complete"] is False


def test_a_conclusion_on_rejected_support_cannot_be_accepted() -> None:
    overclaimed = graph(
        [
            node(
                "N-premise",
                NodeType.PREMISE.value,
                evidence_ids=["EVN-1"],
                status=NodeStatus.REJECTED.value,
            ),
            node(
                "N-conclusion",
                NodeType.CONCLUSION.value,
                status=NodeStatus.ACCEPTED.value,
            ),
        ],
        [edge("E-1", "N-premise", "N-conclusion")],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(overclaimed)

    assert caught.value.code == "BROKEN_EDGE"


def test_a_standing_objection_must_be_declared() -> None:
    objected = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
            node("N-objection", NodeType.OBJECTION.value),
        ],
        [
            edge("E-1", "N-premise", "N-conclusion"),
            edge(
                "E-2",
                "N-objection",
                "N-conclusion",
                EdgeType.ATTACKS.value,
                rule_ref=None,
            ),
        ],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(objected)

    assert caught.value.code == "OBJECTION_UNDECLARED"
    assert caught.value.context["derived"] == ["N-objection"]


def test_a_rebutted_objection_is_no_longer_standing() -> None:
    answered = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
            node("N-objection", NodeType.OBJECTION.value),
            node("N-response", NodeType.RESPONSE.value, evidence_ids=["EVN-3"]),
        ],
        [
            edge("E-1", "N-premise", "N-conclusion"),
            edge(
                "E-2",
                "N-objection",
                "N-conclusion",
                EdgeType.ATTACKS.value,
                rule_ref=None,
            ),
            edge(
                "E-3", "N-response", "N-objection", EdgeType.REBUTS.value, rule_ref=None
            ),
        ],
    )

    trace = build_proof_trace(answered).payload

    assert trace["unresolved_objection_ids"] == []
    assert trace["status"] == TraceStatus.VALID.value


def test_a_tampered_graph_hash_is_rejected() -> None:
    tampered = grounded_graph()
    tampered["hypothesis_id"] = "HYP-other"

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(tampered)

    assert caught.value.code == "GRAPH_HASH_MISMATCH"


def test_the_trace_is_deterministic_and_content_addressed() -> None:
    first = build_proof_trace(assumed_graph())
    second = build_proof_trace(assumed_graph())

    assert first.canonical_bytes == second.canonical_bytes
    assert validate_proof_trace(first.payload).canonical_bytes == first.canonical_bytes


def test_a_tampered_trace_is_rejected() -> None:
    payload = build_proof_trace(assumed_graph()).payload
    payload["status"] = TraceStatus.VALID.value

    with pytest.raises(ProofTraceError) as caught:
        validate_proof_trace(payload)

    assert caught.value.code == "TRACE_HASH_MISMATCH"


def test_stripping_an_assumption_from_a_rehashed_ledger_fails_closed() -> None:
    from .contracts import _hash_excluding

    payload = build_proof_trace(assumed_graph()).payload
    payload["assumption_ledger"] = []
    payload["trace_hash"] = _hash_excluding(payload, "trace_hash")

    with pytest.raises(ProofTraceError) as caught:
        validate_proof_trace(payload)

    assert caught.value.code == "ASSUMPTION_UNLEDGERED"
    assert caught.value.context["assumption_ids"] == ["N-assume"]


def test_a_duplicate_node_id_is_refused() -> None:
    duplicated = graph(
        [
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-1"]),
            node("N-premise", NodeType.PREMISE.value, evidence_ids=["EVN-2"]),
            node("N-conclusion", NodeType.CONCLUSION.value),
        ],
        [edge("E-1", "N-premise", "N-conclusion")],
    )

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(duplicated)

    assert caught.value.code == "DUPLICATE_NODE"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("node_type", "vibe", "NODE_TYPE_INVALID"),
        ("status", "probably", "NODE_STATUS_INVALID"),
    ],
)
def test_non_canonical_node_vocabulary_is_refused(
    field: str, value: str, code: str
) -> None:
    invalid = grounded_graph()
    invalid["nodes"][0][field] = value  # type: ignore[index]
    invalid = seal_argument_graph(invalid)

    with pytest.raises(ProofTraceError) as caught:
        build_proof_trace(invalid)

    assert caught.value.code == code
