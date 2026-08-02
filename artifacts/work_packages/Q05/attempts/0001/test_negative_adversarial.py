"""Negative and adversarial coverage for the Q05 admissibility gate.

Every finding code in ``gate.FINDING_CODES`` is provoked here, and the module
asserts at the end that no code was left untested. The adversarial cases are the
ones this gate exists for: a scalar masquerading as a vector, a candidate role
reaching for authority, a leaked holdout, a tampered statistical record, and a
selection whose winner's-curse correction was never applied.
"""

from __future__ import annotations

import copy

import pytest
from epistemic_foundry.evaluation.v4_q05 import gate
from epistemic_foundry.evaluation.v4_q05.gate import SelectiveAdmissibilityRefused
from fixtures import (
    fitness_vector,
    gate_arguments,
    scalar_fitness,
    search_statistics,
    selective_report,
)

_SEEN: set[str] = set()


def _refuse(**arguments: object) -> SelectiveAdmissibilityRefused:
    """Run the enforcing gate, capture the refusal, and record its code."""
    with pytest.raises(SelectiveAdmissibilityRefused) as excinfo:
        gate.evaluate_selective_admissibility(**arguments)
    _SEEN.add(excinfo.value.code)
    return excinfo.value


def test_input_invalid_on_a_non_mapping_statistical_record() -> None:
    error = _refuse(**gate_arguments(search_statistics=123))
    assert error.code == "INPUT_INVALID"


def test_fitness_not_vector_on_a_scalar_score() -> None:
    error = _refuse(**gate_arguments(fitness_vector=scalar_fitness()))
    assert error.code == "FITNESS_NOT_VECTOR"


def test_fitness_vector_contract_violated_on_an_out_of_range_dimension() -> None:
    broken = fitness_vector()
    broken["dimensions"] = {**broken["dimensions"], "grounding": 2.0}
    error = _refuse(**gate_arguments(fitness_vector=broken))
    assert error.code == "FITNESS_VECTOR_CONTRACT_VIOLATED"


def test_fitness_hard_gate_not_passed_is_a_refuse_decision() -> None:
    failing = fitness_vector(hard_gate_status="FAIL", hard_gate_failures=["G02"])
    error = _refuse(**gate_arguments(fitness_vector=failing))
    assert error.code == "FITNESS_HARD_GATE_NOT_PASSED"
    assert error.context["receipt"]["decision"] == gate.REFUSE


def test_score_grants_promotion_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the fitness surface ever claimed a score may promote, the gate refuses."""
    monkeypatch.setattr(gate, "may_promote_on_score", lambda vector: True)
    error = _refuse(**gate_arguments())
    assert error.code == "SCORE_GRANTS_PROMOTION"


def test_candidate_identity_mismatch_across_artifacts() -> None:
    stranger = selective_report(candidate_id="HG-OTHER")
    error = _refuse(**gate_arguments(selective_report=stranger))
    assert error.code == "CANDIDATE_IDENTITY_MISMATCH"


def test_hidden_evaluation_firewall_broken_on_a_readable_bundle() -> None:
    from fixtures import evaluator_bundle

    readable = evaluator_bundle(candidate_access=True)
    error = _refuse(**gate_arguments(evaluator_bundle=readable))
    assert error.code == "HIDDEN_EVALUATION_FIREWALL_BROKEN"


def test_hidden_result_disclosure_unapproved_without_an_approval() -> None:
    error = _refuse(**gate_arguments(disclose_hidden_result=True))
    assert error.code == "HIDDEN_RESULT_DISCLOSURE_UNAPPROVED"


def test_hidden_result_disclosure_unapproved_without_holdout_access() -> None:
    error = _refuse(
        **gate_arguments(
            disclose_hidden_result=True,
            unblinding_approval_id="UNBLIND-1",
            requesting_principal_id="stranger",
            holdout_read_principal_ids=[],
        )
    )
    assert error.code == "HIDDEN_RESULT_DISCLOSURE_UNAPPROVED"


def test_candidate_role_holds_authority_is_refused() -> None:
    error = _refuse(**gate_arguments(requesting_role="candidate_generator"))
    assert error.code == "CANDIDATE_ROLE_HOLDS_AUTHORITY"


def test_evaluator_feedback_leaked_invalidates_the_comparison() -> None:
    from fixtures import HIDDEN_HANDLE

    error = _refuse(**gate_arguments(leaked_ids=[HIDDEN_HANDLE]))
    assert error.code == "EVALUATOR_FEEDBACK_LEAKED"


def test_search_record_contract_violated_on_a_tampered_record() -> None:
    tampered = search_statistics(report=selective_report())
    tampered["evolution_run_id"] = "RUN-TAMPERED"  # content changed, hash not re-sealed
    error = _refuse(**gate_arguments(search_statistics=tampered))
    assert error.code == "SEARCH_RECORD_CONTRACT_VIOLATED"


def test_uncorrected_adaptive_selection_on_a_missing_artifact() -> None:
    incomplete = search_statistics(report=selective_report(), replication_result_id="")
    error = _refuse(**gate_arguments(search_statistics=incomplete))
    assert error.code == "UNCORRECTED_ADAPTIVE_SELECTION"
    assert error.context["receipt"]["decision"] == gate.REFUSE


def test_selective_accounting_misbound_when_record_and_report_disagree() -> None:
    clearing = selective_report()
    blocking = selective_report(replication_count=0, candidates_considered=100)
    error = _refuse(
        **gate_arguments(
            search_statistics=search_statistics(report=clearing),
            selective_report=blocking,
        )
    )
    assert error.code == "SELECTIVE_ACCOUNTING_MISBOUND"


def test_selection_not_statistically_cleared_on_a_blocking_verdict() -> None:
    blocking = selective_report(replication_count=0, candidates_considered=100)
    error = _refuse(
        **gate_arguments(
            search_statistics=search_statistics(report=blocking),
            selective_report=blocking,
        )
    )
    assert error.code == "SELECTION_NOT_STATISTICALLY_CLEARED"
    assert error.context["receipt"]["decision"] == gate.REFUSE


def test_the_gate_never_mutates_inputs_even_when_it_refuses() -> None:
    arguments = gate_arguments(leaked_ids=["HID-Q05-1"])
    snapshot = copy.deepcopy(arguments)
    with pytest.raises(SelectiveAdmissibilityRefused):
        gate.evaluate_selective_admissibility(**arguments)
    assert arguments == snapshot


def test_every_finding_code_was_exercised() -> None:
    """The suite is only complete when every documented refusal was provoked."""
    assert _SEEN == set(gate.FINDING_CODES), set(gate.FINDING_CODES) - _SEEN
