"""Unit and contract checks for the R06 crossover safety gate.

These exercise the gate's derivation contract on well-formed inputs: every axis
is read from the parents' own artifacts, the compatible decision is reached only
when all four agree, the two entry points stay consistent, and the decision
never consults a promotion or evaluation field.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.reasoning.v4_r06 import gate
from fixtures import (
    crossover_report,
    empty_scope_vector,
    gate_arguments,
    genome,
    measurement,
    measurement_report,
    mechanism_graph,
    scope_vector,
)


def test_a_fully_compatible_crossover_is_allowed() -> None:
    receipt = gate.evaluate_crossover_safety(**gate_arguments())
    assert receipt["decision"] == "ALLOW"
    assert receipt["derived_axes"] == {
        "scope_compatibility": "compatible",
        "measurement_compatibility": "compatible",
        "causal_compatibility": "compatible",
        "unit_compatibility": "compatible",
    }


def test_the_causal_axis_is_read_from_each_parents_mechanism_graph() -> None:
    receipt = gate.derive_crossover_safety(**gate_arguments())
    reasons = receipt["derived_reasons"]["causal_compatibility"]
    assert any(gate.IDENTIFIED in reason for reason in reasons)
    assert receipt["derived_axes"]["causal_compatibility"] == "compatible"


def test_two_identified_parents_are_the_only_compatible_causal_pair() -> None:
    receipt = gate.derive_crossover_safety(
        **gate_arguments(
            mechanism_graphs=[
                mechanism_graph("MG-1", identification_status="ASSUMPTION_DEPENDENT"),
                mechanism_graph("MG-2", identification_status="ASSUMPTION_DEPENDENT"),
            ],
            crossover_report=crossover_report(
                causal_compatibility="requires_new_assumption",
                required_repairs=["ledger the shared assumption"],
            ),
        )
    )
    assert receipt["derived_axes"]["causal_compatibility"] == "requires_new_assumption"
    assert receipt["decision"] == "REFUSE"


def test_the_measurement_axis_is_mapped_from_the_reports_own_verdict() -> None:
    receipt = gate.derive_crossover_safety(
        **gate_arguments(
            measurement_report=measurement_report(
                compatibility_status="CONVERTIBLE", construct_equivalence="PARTIAL"
            ),
            crossover_report=crossover_report(
                measurement_compatibility="stratify",
                required_repairs=["stratify by method"],
            ),
        )
    )
    assert receipt["derived_axes"]["measurement_compatibility"] == "stratify"


def test_the_unit_axis_is_read_from_the_two_measurements_units() -> None:
    receipt = gate.derive_crossover_safety(
        **gate_arguments(
            measurement_report=measurement_report(
                right=measurement("MC-HG-2", unit="umol m-2 s-1"),
                required_transformations=["scale mmol to umol"],
            ),
            crossover_report=crossover_report(
                unit_compatibility="convertible",
                required_repairs=["convert mmol to umol"],
            ),
        )
    )
    assert receipt["derived_axes"]["unit_compatibility"] == "convertible"


def test_the_scope_axis_is_derived_by_comparing_the_two_scope_vectors() -> None:
    shared = scope_vector()
    receipt = gate.derive_crossover_safety(
        **gate_arguments(scope_vectors={"SV-1": shared})
    )
    assert receipt["derived_axes"]["scope_compatibility"] == "compatible"


def test_a_scope_field_one_parent_leaves_open_is_not_a_conflict() -> None:
    # HG-1 declares a geography HG-2 leaves null: a gap, not a contradiction.
    receipt = gate.derive_crossover_safety(
        **gate_arguments(
            parents=[
                genome("HG-1", scope="SV-1", measurement="MC-HG-1"),
                genome("HG-2", mechanism="MG-2", scope="SV-2", measurement="MC-HG-2"),
            ],
            scope_vectors={
                "SV-1": scope_vector(geography="NL"),
                "SV-2": scope_vector(geography=None),
            },
        )
    )
    assert receipt["derived_axes"]["scope_compatibility"] == "compatible"
    assert receipt["decision"] == "ALLOW"


def test_the_receipt_names_every_artifact_the_decision_rested_on() -> None:
    receipt = gate.evaluate_crossover_safety(**gate_arguments())
    assert receipt["candidate_ids"] == ["HG-1", "HG-2"]
    assert len(receipt["mechanism_graph_hashes"]) == 2
    assert len(receipt["scope_vector_hashes"]) == 2
    assert receipt["measurement_report_id"] == "MCR-R06-1"
    assert receipt["crossover_report_id"] == "CCR-R06-1"


def test_derive_returns_a_receipt_where_evaluate_would_raise() -> None:
    arguments = gate_arguments(
        mechanism_graphs=[
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2", identification_status="NOT_IDENTIFIED"),
        ]
    )
    receipt = gate.derive_crossover_safety(**arguments)
    assert receipt["decision"] == "REFUSE"
    assert receipt["finding_code"] == "REPORT_AXIS_MISMATCH"
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_the_gate_decision_never_consults_a_promotion_field() -> None:
    # The measurement report carries a promotion_ceiling; the gate is a
    # pre-crossover safety check and must not read promotion authority into its
    # decision, so flipping the ceiling cannot change the outcome.
    baseline = gate.evaluate_crossover_safety(**gate_arguments())
    flipped = gate.evaluate_crossover_safety(
        **gate_arguments(
            measurement_report=measurement_report(promotion_ceiling="BLOCK_AGGREGATION")
        )
    )
    assert baseline["decision"] == flipped["decision"] == "ALLOW"


def test_an_empty_scope_leaves_the_axis_unexamined() -> None:
    receipt = gate.derive_crossover_safety(
        **gate_arguments(
            scope_vectors={"SV-1": empty_scope_vector()},
            crossover_report=crossover_report(scope_compatibility="unknown"),
        )
    )
    assert receipt["derived_axes"]["scope_compatibility"] == "unknown"
    assert receipt["decision"] == "REFUSE"
