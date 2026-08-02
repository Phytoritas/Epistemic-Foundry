"""Provenance and receipt checks for the R06 crossover safety gate.

Every gate decision resolves to an immutable receipt that re-derives from its
own published fields, replays byte for byte, is independent of the caller's
parent order, and never mutates the inputs it was handed. A refusal carries the
same receipt on the raised error, so the record of why a splice was stopped is
as auditable as an allow.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import canonical_json, hash_excluding, sha256_hex
from epistemic_foundry.reasoning.v4_r06 import gate
from epistemic_foundry.reasoning.v4_r06.gate import CrossoverSafetyRefused
from fixtures import gate_arguments, mechanism_graph


def test_the_receipt_hash_covers_the_receipt() -> None:
    receipt = gate.evaluate_crossover_safety(**gate_arguments())
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_the_gate_id_is_a_pure_function_of_the_decision_content() -> None:
    receipt = gate.evaluate_crossover_safety(**gate_arguments())
    expected = (
        "XSG-"
        + sha256_hex(
            canonical_json(
                {
                    "candidate_ids": receipt["candidate_ids"],
                    "created_at": receipt["created_at"],
                    "crossover_report_hash": receipt["crossover_report_hash"],
                    "decision": receipt["decision"],
                    "mechanism_graph_hashes": receipt["mechanism_graph_hashes"],
                }
            )
        )[len("sha256:") :]
    )
    assert receipt["gate_id"] == expected


def test_an_allowed_decision_replays_byte_for_byte() -> None:
    first = gate.evaluate_crossover_safety(**gate_arguments())
    second = gate.evaluate_crossover_safety(**gate_arguments())
    assert first == second


def test_a_refused_decision_replays_byte_for_byte() -> None:
    arguments = gate_arguments(
        mechanism_graphs=[
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2", identification_status="NOT_IDENTIFIED"),
        ]
    )
    first = gate.derive_crossover_safety(**arguments)
    second = gate.derive_crossover_safety(**arguments)
    assert first == second
    assert first["decision"] == "REFUSE"


def test_the_receipt_is_independent_of_the_parent_order() -> None:
    arguments = gate_arguments()
    receipt = gate.evaluate_crossover_safety(**arguments)
    swapped = gate_arguments()
    swapped["parents"] = list(reversed(swapped["parents"]))
    swapped["mechanism_graphs"] = list(reversed(swapped["mechanism_graphs"]))
    other = gate.evaluate_crossover_safety(**swapped)
    assert receipt["receipt_hash"] == other["receipt_hash"]


def test_a_refusal_carries_the_immutable_receipt_on_the_error() -> None:
    arguments = gate_arguments(
        mechanism_graphs=[
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2", identification_status="NOT_IDENTIFIED"),
        ]
    )
    try:
        gate.evaluate_crossover_safety(**arguments)
    except CrossoverSafetyRefused as error:
        receipt = error.context["receipt"]
        assert receipt["decision"] == "REFUSE"
        assert receipt["finding_code"] == error.code
        assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]
    else:  # pragma: no cover - the arguments above always refuse
        raise AssertionError("the gate should have refused")


def test_the_receipt_records_the_hash_of_every_input_artifact() -> None:
    arguments = gate_arguments()
    receipt = gate.evaluate_crossover_safety(**arguments)
    graphs_by_id = {
        graph["mechanism_graph_id"]: graph for graph in arguments["mechanism_graphs"]
    }
    parents = sorted(arguments["parents"], key=lambda item: item["genome_id"])
    for parent, expected_hash in zip(parents, receipt["mechanism_graph_hashes"]):
        graph = graphs_by_id[parent["mechanism_graph_id"]]
        assert graph["graph_hash"] == expected_hash


def test_the_gate_never_mutates_the_inputs_it_was_given() -> None:
    arguments = gate_arguments()
    snapshot = copy.deepcopy(arguments)
    gate.evaluate_crossover_safety(**arguments)
    assert arguments == snapshot
