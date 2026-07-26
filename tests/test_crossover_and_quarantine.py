"""Semantic collage is rejected; judge changes never apply retroactively."""

from __future__ import annotations

import inspect

import pytest

from epistemic_foundry.evolution_chamber.crossover import (
    COMPATIBILITY_AXES,
    CrossoverRejected,
    build_crossover_report,
    crossover_permitted,
    unexamined_axes,
)
from epistemic_foundry.governance.quarantine import (
    QuarantineViolation,
    build_evaluator_mutation_proposal,
    build_prompt_mutation_proposal,
    may_influence_run,
    require_not_retroactive,
)


def _report(**overrides) -> dict:
    kwargs = dict(
        candidate_ids=["CAND-1", "CAND-2"],
        scope_compatibility="compatible",
        measurement_compatibility="compatible",
        causal_compatibility="compatible",
        unit_compatibility="compatible",
        conflicts=[],
        required_repairs=[],
    )
    kwargs.update(overrides)
    return build_crossover_report(**kwargs)


# -- EF4-I51 crossover compatibility ------------------------------------


def test_i51_decision_is_derived_not_asserted() -> None:
    """A caller able to assert ALLOW could splice uncompared measurements."""
    assert "decision" not in inspect.signature(build_crossover_report).parameters


def test_i51_fully_compatible_parents_may_cross() -> None:
    report = _report()
    assert report["decision"] == "ALLOW"
    assert crossover_permitted(report) is True


@pytest.mark.parametrize("axis", COMPATIBILITY_AXES)
def test_i51_any_incompatible_axis_rejects(axis: str) -> None:
    report = _report(**{axis: "incompatible"})
    assert report["decision"] == "REJECT"
    assert crossover_permitted(report) is False


@pytest.mark.parametrize("axis", COMPATIBILITY_AXES)
def test_i51_unknown_axis_is_not_assessed_not_permitted(axis: str) -> None:
    """An unexamined axis is not a compatible one."""
    report = _report(**{axis: "unknown"})
    assert report["decision"] == "NOT_ASSESSED"
    assert crossover_permitted(report) is False
    assert unexamined_axes(report) == [axis]


def test_i51_repairable_axis_requires_a_named_repair() -> None:
    with pytest.raises(CrossoverRejected) as excinfo:
        _report(measurement_compatibility="stratify", required_repairs=[])
    assert "unnamed repair" in str(excinfo.value)


def test_i51_repair_permits_only_conditional_crossover() -> None:
    """ALLOW_WITH_REPAIR authorizes the repair, not the splice."""
    report = _report(
        unit_compatibility="convertible",
        required_repairs=["convert grams to millimoles before merging"],
    )
    assert report["decision"] == "ALLOW_WITH_REPAIR"
    assert crossover_permitted(report) is False


def test_i51_incompatible_outranks_repairable() -> None:
    report = _report(
        scope_compatibility="incompatible",
        unit_compatibility="convertible",
        required_repairs=["convert units"],
    )
    assert report["decision"] == "REJECT"


def test_i51_single_parent_is_not_a_crossover() -> None:
    with pytest.raises(CrossoverRejected):
        _report(candidate_ids=["CAND-1"])


# -- EF4-I55 prompt genome quarantine -----------------------------------


def _prompt_proposal(**overrides) -> dict:
    kwargs = dict(
        source_prompt_genome_id="PG-1",
        proposed_prompt_genome_id="PG-2",
        motivation="reduce false-negative extraction on table captions",
        changed_sections=["extraction_instructions"],
        risk_analysis=["may increase spurious extraction from figure legends"],
        qualification_plan_id="QP-1",
    )
    kwargs.update(overrides)
    return build_prompt_mutation_proposal(**kwargs)


def test_i55_proposal_is_born_quarantined() -> None:
    proposal = _prompt_proposal()
    assert proposal["status"] == "QUARANTINED"
    assert may_influence_run(proposal) is False


def test_i55_status_cannot_be_asserted_at_creation() -> None:
    """A proposal born APPROVED would bypass independent qualification."""
    assert "status" not in inspect.signature(build_prompt_mutation_proposal).parameters


def test_i55_unspecified_change_is_refused() -> None:
    with pytest.raises(QuarantineViolation) as excinfo:
        _prompt_proposal(changed_sections=[])
    assert "cannot be qualified" in str(excinfo.value)


def test_i55_unanalyzed_risk_is_refused() -> None:
    """Prompts shape what the evaluator sees, so an unanalyzed change is unbounded."""
    with pytest.raises(QuarantineViolation) as excinfo:
        _prompt_proposal(risk_analysis=["  "])
    assert "unbounded" in str(excinfo.value)


def test_i55_empty_risk_list_is_refused() -> None:
    with pytest.raises(QuarantineViolation):
        _prompt_proposal(risk_analysis=[])


# -- EF4-I56 evaluator defect handling ----------------------------------


def _evaluator_proposal(**overrides) -> dict:
    kwargs = dict(
        source_run_id="RUN-1",
        current_evaluator_bundle_id="EB-1",
        defect_class="metric_misalignment",
        evidence_artifact_ids=["ART-defect-1"],
        proposed_change="add a discrimination floor to METRIC-accuracy",
    )
    kwargs.update(overrides)
    return build_evaluator_mutation_proposal(**kwargs)


def test_i56_retroactive_effect_is_forced_prohibited() -> None:
    """A caller able to set this false could re-score completed candidates."""
    proposal = _evaluator_proposal()
    assert proposal["retroactive_effect_prohibited"] is True
    assert proposal["qualification_required"] is True
    params = inspect.signature(build_evaluator_mutation_proposal).parameters
    assert "retroactive_effect_prohibited" not in params
    assert "qualification_required" not in params


def test_i56_defect_claim_needs_evidence() -> None:
    with pytest.raises(QuarantineViolation) as excinfo:
        _evaluator_proposal(evidence_artifact_ids=[])
    assert "cannot justify changing the judge" in str(excinfo.value)


def test_i56_invented_defect_class_is_refused() -> None:
    """The qualification process has no procedure for an unknown class."""
    with pytest.raises(QuarantineViolation) as excinfo:
        _evaluator_proposal(defect_class="metric_saturation")
    assert "no procedure for it" in str(excinfo.value)


def test_i56_proposal_cannot_be_applied_to_its_own_run() -> None:
    """Rewriting the judgments of the run that produced it is the abuse forbidden."""
    proposal = _evaluator_proposal()
    with pytest.raises(QuarantineViolation) as excinfo:
        require_not_retroactive(proposal, target_run_id="RUN-1")
    assert "never rewrite completed judgments" in str(excinfo.value)


def test_i56_quarantined_proposal_cannot_influence_a_new_run_either() -> None:
    proposal = _evaluator_proposal()
    with pytest.raises(QuarantineViolation) as excinfo:
        require_not_retroactive(proposal, target_run_id="RUN-2")
    assert "may not influence any run" in str(excinfo.value)


def test_i56_approved_proposal_may_target_a_new_sealed_run() -> None:
    approved = dict(_evaluator_proposal())
    approved["status"] = "APPROVED"
    require_not_retroactive(approved, target_run_id="RUN-2")


def test_i56_approved_proposal_still_cannot_target_its_source_run() -> None:
    approved = dict(_evaluator_proposal())
    approved["status"] = "APPROVED"
    with pytest.raises(QuarantineViolation):
        require_not_retroactive(approved, target_run_id="RUN-1")
