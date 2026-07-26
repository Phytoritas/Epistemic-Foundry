"""Novelty is earned by a complete search; a score orders but never promotes."""

from __future__ import annotations

import pytest

from epistemic_foundry.evaluation import (
    FitnessViolation,
    assess_novelty,
    build_fitness_vector,
    novelty_supports_claim,
    scalarize_for_ordering,
)
from epistemic_foundry.evaluation.fitness import may_promote_on_score
from epistemic_foundry.evaluation.fitness import FITNESS_DIMENSIONS, unscored_dimensions
from epistemic_foundry.evaluation.novelty import unconditional_novelty

HASH = "sha256:" + "a" * 64


def _assess(**overrides) -> dict:
    kwargs = dict(
        run_id="RUN-1",
        subject_ref="HYP-1",
        statement_hash=HASH,
        corpus_snapshot_hash=HASH,
        search_completeness_certificate_id="SCC-1",
        searched_sources=["corpus", "prior-art-index"],
        unsearched_sources=[],
        closest_prior_art_refs=[],
        distinguishing_features=[],
        novelty_dimensions=["RELATION", "MECHANISM"],
        limitations=[],
        search_cutoff="2026-01-01",
        assessor_ref="AG-novelty-examiner",
        search_completeness="COMPLETE_FOR_POLICY",
    )
    kwargs.update(overrides)
    return assess_novelty(**kwargs)


# -- EF4-I47 novelty never defaults to novel ----------------------------


def test_i47_novelty_status_is_not_a_parameter() -> None:
    """Passing the status in is how an unassessed subject acquires a label."""
    import inspect

    params = inspect.signature(assess_novelty).parameters
    assert "novelty_status" not in params
    assert "promotion_ceiling" not in params


def test_i47_no_search_yields_not_assessed() -> None:
    assessment = _assess(searched_sources=[])
    assert assessment["novelty_status"] == "NOT_ASSESSED"
    assert assessment["promotion_ceiling"] == "NO_NOVELTY_CLAIM"
    assert novelty_supports_claim(assessment) is False


def test_i47_incomplete_search_yields_not_assessed() -> None:
    """A failed search and a thorough one both return no hits."""
    assessment = _assess(search_completeness="PARTIAL")
    assert assessment["novelty_status"] == "NOT_ASSESSED"


def test_i47_blocked_search_yields_not_assessed() -> None:
    assert _assess(search_completeness="BLOCKED")["novelty_status"] == "NOT_ASSESSED"


def test_i47_remaining_unsearched_sources_yield_search_conditional() -> None:
    assessment = _assess(unsearched_sources=["paywalled-journal-set"])
    assert assessment["novelty_status"] == "SEARCH_CONDITIONAL"
    assert assessment["promotion_ceiling"] == "SEARCH_CONDITIONAL"
    assert unconditional_novelty(assessment) is False


def test_i47_prior_art_without_distinction_is_known_prior_art() -> None:
    assessment = _assess(closest_prior_art_refs=["DOI-1"], distinguishing_features=[])
    assert assessment["novelty_status"] == "KNOWN_PRIOR_ART"
    assert novelty_supports_claim(assessment) is False


def test_i47_prior_art_with_distinction_is_corpus_novel_only() -> None:
    assessment = _assess(
        closest_prior_art_refs=["DOI-1"],
        distinguishing_features=["different population and retention interval"],
    )
    assert assessment["novelty_status"] == "CORPUS_NOVEL_ONLY"
    assert assessment["promotion_ceiling"] == "CORPUS_ONLY"


def test_i47_complete_search_with_no_prior_art_is_potentially_novel() -> None:
    assessment = _assess()
    assert assessment["novelty_status"] == "POTENTIALLY_NOVEL"
    assert assessment["promotion_ceiling"] == "ELIGIBLE_FOR_HUMAN_REVIEW"
    assert unconditional_novelty(assessment) is True


def test_i47_top_status_still_only_permits_human_review() -> None:
    """Novelty is not truth: the best outcome is eligibility, not support."""
    assert _assess()["promotion_ceiling"] == "ELIGIBLE_FOR_HUMAN_REVIEW"


# -- EF4-I45 a score orders but does not promote ------------------------


def _all_dimensions(**overrides) -> dict:
    """Every required dimension scored, so the vector is complete."""
    scored = {name: 0.5 for name in FITNESS_DIMENSIONS}
    scored.update(overrides)
    return scored


def _all_uncertainty(**overrides) -> dict:
    """An uncertainty width per dimension, as the schema requires."""
    widths = {name: 0.05 for name in FITNESS_DIMENSIONS}
    widths.update(overrides)
    return widths


def _vector(**overrides) -> dict:
    kwargs = dict(
        candidate_id="CAND-1",
        hard_gate_status="PASS",
        hard_gate_failures=[],
        dimensions=_all_dimensions(grounding=0.82, coverage_value=0.64),
        uncertainty=_all_uncertainty(),
        evidence_receipt_ids=["EF-1"],
        pareto_rank=1,
        domination_count=0,
    )
    kwargs.update(overrides)
    return build_fitness_vector(**kwargs)


def test_i45_vector_keeps_dimensions_separate() -> None:
    vector = _vector()
    assert set(vector["dimensions"]) == set(FITNESS_DIMENSIONS)
    assert vector["dimensions"]["grounding"] == 0.82
    assert vector["dimensions"]["coverage_value"] == 0.64


def test_i45_scalarization_returns_a_bare_number() -> None:
    """No status is attached, so it cannot be mistaken for a verdict."""
    score = scalarize_for_ordering(_vector())
    assert isinstance(score, float)
    assert 0.0 < score < 1.0


def test_i45_a_score_never_promotes() -> None:
    assert may_promote_on_score(_vector()) is False


def test_i45_passing_status_with_failures_is_refused() -> None:
    """A high score cannot reconcile a passing label with failed gates."""
    with pytest.raises(FitnessViolation) as excinfo:
        _vector(hard_gate_status="PASS", hard_gate_failures=["leakage_audit"])
    assert "cannot reconcile" in str(excinfo.value)


def test_i45_non_pass_status_needs_a_named_failure() -> None:
    with pytest.raises(FitnessViolation) as excinfo:
        _vector(hard_gate_status="FAIL", hard_gate_failures=[])
    assert "unexplained non-pass" in str(excinfo.value)


def test_i45_vector_without_dimensions_is_refused() -> None:
    with pytest.raises(FitnessViolation) as excinfo:
        _vector(dimensions={})
    assert "scalar wearing a vector" in str(excinfo.value)


def test_i45_partial_vector_is_refused() -> None:
    """Scoring only the favourable dimensions must not produce a ranking."""
    partial = {"grounding": 0.9, "novelty": 0.9}
    with pytest.raises(FitnessViolation) as excinfo:
        _vector(dimensions=partial)
    assert "only on the dimensions that favour it" in str(excinfo.value)
    assert "safety" in str(excinfo.value)


def test_i45_unscored_dimensions_are_reportable() -> None:
    assert unscored_dimensions({"grounding": 0.5}) == sorted(set(FITNESS_DIMENSIONS) - {"grounding"})
    assert unscored_dimensions(_all_dimensions()) == []


def test_i45_score_without_uncertainty_is_refused() -> None:
    """A point estimate with no uncertainty invites comparison it cannot support."""
    with pytest.raises(FitnessViolation) as excinfo:
        _vector(uncertainty={"grounding": 0.05})
    assert "no uncertainty" in str(excinfo.value)


def test_i45_weighted_ordering_respects_weights() -> None:
    vector = _vector(dimensions=_all_dimensions(grounding=1.0, coverage_value=0.0))
    grounding_only = scalarize_for_ordering(vector, {"grounding": 1.0, "coverage_value": 0.0})
    balanced = scalarize_for_ordering(vector)
    assert grounding_only > balanced


def test_i45_not_assessed_gate_status_is_representable() -> None:
    """An unevaluated candidate is NOT_ASSESSED, not a silent pass."""
    vector = _vector(hard_gate_status="NOT_ASSESSED", hard_gate_failures=[])
    assert vector["hard_gate_status"] == "NOT_ASSESSED"
