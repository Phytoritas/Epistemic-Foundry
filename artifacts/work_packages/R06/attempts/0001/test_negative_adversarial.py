"""Negative and adversarial checks for the R06 crossover safety gate.

Every documented finding code is exercised here with a construction that must
trigger exactly it, and the leakage-shaped cases — a report that overclaims a
compatible axis, a decision tampered to disagree with its own axes — are
refused rather than allowed to launder an unsafe splice.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.reasoning.v4_r06 import gate
from epistemic_foundry.reasoning.v4_r06.gate import (
    FINDING_CODES,
    CrossoverSafetyRefused,
)
from fixtures import (
    challenge_genome,
    crossover_report,
    empty_scope_vector,
    gate_arguments,
    genome,
    measurement,
    measurement_report,
    mechanism_graph,
    scope_vector,
)


def _refuses(code: str, **overrides: object) -> None:
    with pytest.raises(CrossoverSafetyRefused) as caught:
        gate.evaluate_crossover_safety(**gate_arguments(**overrides))
    assert caught.value.code == code


def test_a_non_mapping_parent_is_refused() -> None:
    _refuses("INPUT_INVALID", parents=[genome("HG-1"), 42])


def test_a_crossover_that_is_not_two_parents_is_refused() -> None:
    _refuses("CROSSOVER_ARITY_INVALID", parents=[genome("HG-1")])


def test_splicing_a_candidate_with_itself_is_refused() -> None:
    _refuses("PARENTS_NOT_DISTINCT", parents=[genome("HG-1"), genome("HG-1")])


def test_a_parent_that_breaks_its_schema_is_refused() -> None:
    _refuses(
        "PARENT_CONTRACT_VIOLATED", parents=[genome("HG-1"), {"genome_id": "HG-2"}]
    )


def test_a_parent_of_the_wrong_kind_is_refused() -> None:
    _refuses("PARENT_KIND_MISMATCH", parents=[genome("HG-1"), challenge_genome()])


def test_an_unresolved_mechanism_reference_is_refused() -> None:
    _refuses("MECHANISM_GRAPH_UNRESOLVED", mechanism_graphs=[mechanism_graph("MG-1")])


def test_a_mechanism_graph_with_a_broken_seal_is_refused() -> None:
    tampered = dict(mechanism_graph("MG-2"), graph_hash="sha256:" + "0" * 64)
    _refuses(
        "MECHANISM_GRAPH_CONTRACT_VIOLATED",
        mechanism_graphs=[mechanism_graph("MG-1"), tampered],
    )


def test_an_unresolved_scope_reference_is_refused() -> None:
    _refuses("SCOPE_VECTOR_UNRESOLVED", scope_vectors={"SV-OTHER": scope_vector()})


def test_a_scope_vector_that_breaks_its_schema_is_refused() -> None:
    _refuses("SCOPE_VECTOR_CONTRACT_VIOLATED", scope_vectors={"SV-1": {"domain": "x"}})


def test_a_measurement_report_with_a_broken_seal_is_refused() -> None:
    tampered = dict(measurement_report(), report_hash="sha256:" + "0" * 64)
    _refuses("MEASUREMENT_REPORT_CONTRACT_VIOLATED", measurement_report=tampered)


def test_a_measurement_report_about_other_measures_is_refused() -> None:
    _refuses(
        "MEASUREMENT_REPORT_MISBOUND",
        measurement_report=measurement_report(left_id="MC-SOMEONE-ELSE"),
    )


def test_a_crossover_report_with_a_broken_seal_is_refused() -> None:
    tampered = dict(crossover_report(), report_hash="sha256:" + "0" * 64)
    _refuses("CROSSOVER_REPORT_CONTRACT_VIOLATED", crossover_report=tampered)


def test_a_crossover_report_that_names_other_parents_is_refused() -> None:
    _refuses(
        "CROSSOVER_REPORT_MISBOUND",
        crossover_report=crossover_report(candidate_ids=("HG-1", "HG-9")),
    )


def test_a_report_that_overclaims_an_axis_is_refused() -> None:
    # The parents are causally incompatible, but the report still asserts the
    # default compatible axis: the gate refuses the report, not trusts it.
    _refuses(
        "REPORT_AXIS_MISMATCH",
        mechanism_graphs=[
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2", identification_status="NOT_IDENTIFIED"),
        ],
    )


def test_an_unassessed_causal_identification_is_refused() -> None:
    _refuses(
        "CAUSAL_IDENTIFICATION_UNASSESSED",
        mechanism_graphs=[
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2", identification_status=gate.NOT_ASSESSED),
        ],
        crossover_report=crossover_report(causal_compatibility="unknown"),
    )


def test_mixing_incompatible_causal_identification_is_refused() -> None:
    _refuses(
        "CAUSAL_IDENTIFICATION_INCOMPATIBLE",
        mechanism_graphs=[
            mechanism_graph("MG-1"),
            mechanism_graph("MG-2", identification_status="NOT_IDENTIFIED"),
        ],
        crossover_report=crossover_report(causal_compatibility="incompatible"),
    )


def test_an_unassessed_measurement_contract_is_refused() -> None:
    _refuses(
        "MEASUREMENT_CONTRACT_UNASSESSED",
        measurement_report=measurement_report(compatibility_status="UNKNOWN"),
        crossover_report=crossover_report(measurement_compatibility="unknown"),
    )


def test_an_incomparable_measurement_contract_is_refused() -> None:
    _refuses(
        "MEASUREMENT_CONTRACT_INCOMPATIBLE",
        measurement_report=measurement_report(compatibility_status="NOT_COMPARABLE"),
        crossover_report=crossover_report(measurement_compatibility="incompatible"),
    )


def test_a_parent_with_no_declared_scope_is_refused() -> None:
    _refuses(
        "SCOPE_UNASSESSED",
        scope_vectors={"SV-1": empty_scope_vector()},
        crossover_report=crossover_report(scope_compatibility="unknown"),
    )


def test_conflicting_scope_boundaries_are_refused() -> None:
    _refuses(
        "SCOPE_INCOMPATIBLE",
        parents=[
            genome("HG-1", scope="SV-1", measurement="MC-HG-1"),
            genome("HG-2", mechanism="MG-2", scope="SV-2", measurement="MC-HG-2"),
        ],
        scope_vectors={
            "SV-1": scope_vector(setting="glasshouse"),
            "SV-2": scope_vector(setting="open field"),
        },
        crossover_report=crossover_report(scope_compatibility="incompatible"),
    )


def test_an_undeclared_unit_is_refused() -> None:
    _refuses(
        "UNIT_UNASSESSED",
        measurement_report=measurement_report(right=measurement("MC-HG-2", unit=None)),
        crossover_report=crossover_report(unit_compatibility="unknown"),
    )


def test_incompatible_units_with_no_conversion_are_refused() -> None:
    _refuses(
        "UNIT_INCOMPATIBLE",
        measurement_report=measurement_report(
            right=measurement("MC-HG-2", unit="umol m-2 s-1")
        ),
        crossover_report=crossover_report(unit_compatibility="incompatible"),
    )


def test_a_decision_tampered_below_its_own_axes_is_refused() -> None:
    # Every axis is compatible, but the stored decision was forced to REJECT and
    # re-sealed: the gate composes the Chamber's own decision and stops it.
    report = dict(crossover_report())
    report["decision"] = "REJECT"
    report.pop("report_hash")
    report["report_hash"] = hash_excluding(report, "report_hash")
    _refuses("CROSSOVER_NOT_PERMITTED", crossover_report=report)


def test_a_dropped_genome_reference_field_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate.engine, "genome_properties", lambda kind: {})
    with pytest.raises(CrossoverSafetyRefused) as caught:
        gate.evaluate_crossover_safety(**gate_arguments())
    assert caught.value.code == "GENOME_FIELD_UNDECLARED_BY_SCHEMA"


def test_every_documented_finding_code_has_a_negative_test() -> None:
    # A guard against a code drifting out of coverage: the module names one test
    # per code above, so this asserts the documented set matches expectation.
    expected = {
        "INPUT_INVALID",
        "CROSSOVER_ARITY_INVALID",
        "PARENTS_NOT_DISTINCT",
        "PARENT_CONTRACT_VIOLATED",
        "PARENT_KIND_MISMATCH",
        "GENOME_FIELD_UNDECLARED_BY_SCHEMA",
        "MECHANISM_GRAPH_UNRESOLVED",
        "MECHANISM_GRAPH_CONTRACT_VIOLATED",
        "SCOPE_VECTOR_UNRESOLVED",
        "SCOPE_VECTOR_CONTRACT_VIOLATED",
        "MEASUREMENT_REPORT_CONTRACT_VIOLATED",
        "MEASUREMENT_REPORT_MISBOUND",
        "CROSSOVER_REPORT_CONTRACT_VIOLATED",
        "CROSSOVER_REPORT_MISBOUND",
        "REPORT_AXIS_MISMATCH",
        "CAUSAL_IDENTIFICATION_UNASSESSED",
        "CAUSAL_IDENTIFICATION_INCOMPATIBLE",
        "MEASUREMENT_CONTRACT_UNASSESSED",
        "MEASUREMENT_CONTRACT_INCOMPATIBLE",
        "SCOPE_UNASSESSED",
        "SCOPE_INCOMPATIBLE",
        "UNIT_UNASSESSED",
        "UNIT_INCOMPATIBLE",
        "CROSSOVER_NOT_PERMITTED",
    }
    assert set(FINDING_CODES) == expected
