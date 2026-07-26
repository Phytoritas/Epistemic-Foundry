"""Peeking spends budget; selection biases estimates; correlation shrinks counts."""

from __future__ import annotations

import pytest

from epistemic_foundry.statistics import (
    SelectiveInferenceRefused,
    SequentialBudgetExhausted,
    build_multiplicity_adjustment,
    build_selective_inference_report,
    build_sequential_ledger,
    effective_test_count,
    remaining_alpha,
    winner_curse_risk_for,
)
from epistemic_foundry.statistics.selective import permits_promotion_without_replication
from epistemic_foundry.statistics.sequential import (
    may_take_another_look,
    require_budget_for_look,
)


def _look(spent: float, index: int = 1) -> dict:
    """A ledger entry carrying every canonical field."""
    return {
        "test_id": f"T-{index}",
        "generation": index,
        "statistic": 1.96,
        "threshold": 2.24,
        "spent": spent,
        "decision": "continue",
    }


def _ledger(**overrides) -> dict:
    kwargs = dict(
        family_id="FAM-1",
        testing_policy="alpha_spending",
        initial_budget=0.05,
        entries=[_look(0.01, 1), _look(0.01, 2)],
        selection_events=[],
    )
    kwargs.update(overrides)
    return build_sequential_ledger(**kwargs)


# -- sequential testing -------------------------------------------------


def test_looks_spend_the_error_budget() -> None:
    ledger = _ledger()
    assert ledger["remaining_budget"] == pytest.approx(0.03)


def test_remaining_budget_never_goes_negative() -> None:
    """A negative remainder would read as a small positive budget."""
    assert remaining_alpha(0.05, [_look(0.09)]) == 0.0


def test_spend_field_matches_the_schema() -> None:
    """The ledger reads `spent`; an alias would silently sum to zero."""
    from epistemic_foundry.statistics.sequential import SPEND_FIELD

    assert SPEND_FIELD in _look(0.01)
    assert remaining_alpha(0.05, [_look(0.02)]) == pytest.approx(0.03)


def test_overspent_ledger_is_refused() -> None:
    with pytest.raises(SequentialBudgetExhausted) as excinfo:
        _ledger(entries=[_look(0.04, 1), _look(0.04, 2)])
    assert "arithmetically wrong significance" in str(excinfo.value)


def test_fixed_horizon_cannot_take_repeated_looks() -> None:
    """That policy has no provision for interim analysis."""
    with pytest.raises(SequentialBudgetExhausted) as excinfo:
        _ledger(testing_policy="fixed_horizon")
    assert "unaccounted peeking" in str(excinfo.value)


def test_fixed_horizon_with_one_look_is_fine() -> None:
    ledger = _ledger(testing_policy="fixed_horizon", entries=[_look(0.05)])
    assert ledger["remaining_budget"] == pytest.approx(0.0)


def test_zero_budget_ledger_is_refused() -> None:
    with pytest.raises(SequentialBudgetExhausted):
        _ledger(initial_budget=0.0)


def test_further_look_is_refused_once_budget_is_gone() -> None:
    ledger = _ledger(entries=[_look(0.05)])
    assert may_take_another_look(ledger, cost=0.01) is False
    with pytest.raises(SequentialBudgetExhausted) as excinfo:
        require_budget_for_look(ledger, cost=0.01)
    assert "exceeds the remaining budget" in str(excinfo.value)


def test_affordable_look_is_permitted() -> None:
    require_budget_for_look(_ledger(), cost=0.02)


# -- winner's curse -----------------------------------------------------


def test_replication_is_what_lowers_winner_curse_risk() -> None:
    """An independent repeat is not subject to the original selection."""
    assert winner_curse_risk_for(candidates_considered=200, selection_events=5, replication_count=2) == "low"
    assert winner_curse_risk_for(candidates_considered=200, selection_events=5, replication_count=0) == "high"


def test_heavy_search_without_replication_is_high_risk() -> None:
    assert winner_curse_risk_for(candidates_considered=100, selection_events=1, replication_count=0) == "high"


def test_small_search_with_one_replication_is_low_risk() -> None:
    assert winner_curse_risk_for(candidates_considered=3, selection_events=1, replication_count=1) == "low"


def test_no_candidates_yields_unknown_risk() -> None:
    assert winner_curse_risk_for(candidates_considered=0, selection_events=0, replication_count=0) == "unknown"


def _report(**overrides) -> dict:
    kwargs = dict(
        candidate_id="CAND-1",
        selection_mechanism="top-1 of Pareto front by combined score",
        selection_events=["S5 top-decile cut"],
        naive_estimate=0.42,
        bias_corrected_estimate=0.31,
        correction_method="conditional-likelihood shrinkage",
        uncertainty_interval=[0.08, 0.54],
        candidates_considered=120,
    )
    kwargs.update(overrides)
    return build_selective_inference_report(**kwargs)


def test_report_derives_risk_and_recommendation() -> None:
    """The party that selected the candidate must not grade its own bias."""
    import inspect

    params = inspect.signature(build_selective_inference_report).parameters
    assert "winner_curse_risk" not in params
    assert "promotion_recommendation" not in params


def test_heavy_selection_without_replication_blocks() -> None:
    report = _report()
    assert report["winner_curse_risk"] == "high"
    assert report["promotion_recommendation"] == "BLOCK"
    assert permits_promotion_without_replication(report) is False


def test_heavy_selection_with_replication_requires_replicate_first() -> None:
    report = _report(replication_count=1)
    assert report["promotion_recommendation"] == "REPLICATE_FIRST"


def test_light_selection_with_replication_allows() -> None:
    report = _report(candidates_considered=3, replication_count=1)
    assert report["winner_curse_risk"] == "low"
    assert report["promotion_recommendation"] == "ALLOW"


def test_correction_may_not_inflate_the_estimate() -> None:
    """Moving the estimate away from the null is not a correction."""
    with pytest.raises(SelectiveInferenceRefused) as excinfo:
        _report(bias_corrected_estimate=0.55)
    assert "not a correction" in str(excinfo.value)


def test_correction_may_shrink_toward_zero() -> None:
    assert _report(bias_corrected_estimate=0.05)["bias_corrected_estimate"] == pytest.approx(0.05)


def test_unnamed_correction_method_is_refused() -> None:
    with pytest.raises(SelectiveInferenceRefused) as excinfo:
        _report(correction_method="  ")
    assert "cannot be reproduced or challenged" in str(excinfo.value)


# -- multiplicity -------------------------------------------------------


def test_independent_tests_keep_their_full_count() -> None:
    assert effective_test_count(50, mean_correlation=0.0) == 50


def test_perfectly_correlated_tests_collapse_to_one() -> None:
    assert effective_test_count(50, mean_correlation=1.0) == 1


def test_partial_correlation_interpolates() -> None:
    count = effective_test_count(50, mean_correlation=0.5)
    assert 1 < count < 50


def test_effective_count_never_exceeds_the_raw_count() -> None:
    """Correcting for comparisons nobody made buries real effects."""
    assert effective_test_count(4, mean_correlation=-1.0) == 4


def test_zero_tests_is_refused() -> None:
    with pytest.raises(ValueError):
        effective_test_count(0)


def _adjustment(**overrides) -> dict:
    kwargs = dict(
        family_id="FAM-1",
        method="BH_FDR",
        raw_test_count=40,
        target_error_rate=0.05,
        adjusted_results=[
            {
                "test_id": "T-1",
                "raw_value": 0.001,
                "adjusted_value": 0.02,
                "decision": "reject_null",
            }
        ],
        assumptions=["tests are positively dependent within the family"],
    )
    kwargs.update(overrides)
    return build_multiplicity_adjustment(**kwargs)


def test_adjustment_records_effective_count() -> None:
    adjustment = _adjustment(mean_correlation=0.75)
    assert adjustment["raw_test_count"] == 40
    assert adjustment["effective_test_count"] < 40


def test_adjustment_without_assumptions_is_refused() -> None:
    with pytest.raises(ValueError) as excinfo:
        _adjustment(assumptions=[])
    assert "dependence assumption" in str(excinfo.value)


@pytest.mark.parametrize("rate", [0.0, 1.0, -0.1, 1.5])
def test_invalid_error_rate_is_refused(rate: float) -> None:
    with pytest.raises(ValueError):
        _adjustment(target_error_rate=rate)
