"""Cascade ordering and fail-closed aggregation."""

from __future__ import annotations

import pytest

from epistemic_foundry.validation_bay import (
    CascadeViolation,
    aggregate_cascade_status,
    build_cascade_plan,
    build_stage_result,
    next_runnable_stage,
)

STAGES = (
    {
        "stage_id": "S0",
        "stage_class": "contract",
        "entry_rule": "always",
        "pass_rule": "all hard contracts valid",
        "failure_action": "reject",
        "budget_fraction": 0.02,
    },
    {
        "stage_id": "S1",
        "stage_class": "static",
        "entry_rule": "after S0",
        "pass_rule": "screening threshold met",
        "failure_action": "reject",
        "budget_fraction": 0.18,
    },
    {
        "stage_id": "S5",
        "stage_class": "holdout",
        "entry_rule": "top Pareto candidates only",
        "pass_rule": "preregistered threshold met",
        "failure_action": "restrict",
        "budget_fraction": 0.45,
    },
)


@pytest.fixture()
def plan() -> dict:
    return build_cascade_plan(
        candidate_class="hypothesis",
        stages=STAGES,
        max_total_budget=100.0,
        early_stop_policy="Stop on non-waivable hard failure.",
    )


def _result(plan: dict, stage_id: str, status: str) -> dict:
    return build_stage_result(
        cascade_plan_id=plan["cascade_plan_id"],
        candidate_id="CAND-0001",
        stage_id=stage_id,
        status=status,
        metric_values={"score": 0.5},
        uncertainty_summary="95% CI [0.40, 0.60]",
        started_at="2026-07-27T00:00:00+00:00",
    )


# -- planning -----------------------------------------------------------


def test_plan_requires_at_least_one_stage() -> None:
    with pytest.raises(CascadeViolation):
        build_cascade_plan(
            candidate_class="hypothesis",
            stages=(),
            max_total_budget=100.0,
            early_stop_policy="none",
        )


def test_overcommitted_budget_is_refused() -> None:
    """A plan claiming more than the whole budget cannot be executed as written."""
    greedy = [dict(stage, budget_fraction=0.6) for stage in STAGES]
    with pytest.raises(CascadeViolation) as excinfo:
        build_cascade_plan(
            candidate_class="hypothesis",
            stages=greedy,
            max_total_budget=100.0,
            early_stop_policy="none",
        )
    assert "exceeds the plan budget" in str(excinfo.value)


def test_duplicate_stage_ids_are_refused() -> None:
    with pytest.raises(CascadeViolation):
        build_cascade_plan(
            candidate_class="hypothesis",
            stages=(STAGES[0], STAGES[0]),
            max_total_budget=100.0,
            early_stop_policy="none",
        )


# -- ordering -----------------------------------------------------------


def test_first_stage_runs_first(plan: dict) -> None:
    assert next_runnable_stage(plan, []) == "S0"


def test_cascade_advances_in_plan_order(plan: dict) -> None:
    assert next_runnable_stage(plan, [_result(plan, "S0", "PASS")]) == "S1"


def test_cascade_stops_after_a_hard_failure(plan: dict) -> None:
    """A later stage must not be reachable once an earlier stage failed."""
    assert next_runnable_stage(plan, [_result(plan, "S0", "FAIL")]) is None


def test_running_a_stage_after_a_failure_is_a_violation(plan: dict) -> None:
    """The expensive holdout stage cannot rescue a failed contract check."""
    results = [_result(plan, "S0", "FAIL"), _result(plan, "S5", "PASS")]
    with pytest.raises(CascadeViolation) as excinfo:
        aggregate_cascade_status(plan, results)
    assert "cannot overturn an earlier hard failure" in str(excinfo.value)


def test_unknown_stage_result_is_refused(plan: dict) -> None:
    with pytest.raises(CascadeViolation):
        aggregate_cascade_status(plan, [_result(plan, "S99", "PASS")])


# -- aggregation --------------------------------------------------------


def test_fully_passing_cascade_is_pass(plan: dict) -> None:
    results = [_result(plan, stage["stage_id"], "PASS") for stage in STAGES]
    assert aggregate_cascade_status(plan, results) == "PASS"


def test_unrun_stage_keeps_the_cascade_partial(plan: dict) -> None:
    """An absent stage is NOT_RUN, never an implicit pass."""
    results = [_result(plan, "S0", "PASS"), _result(plan, "S1", "PASS")]
    assert aggregate_cascade_status(plan, results) == "PARTIAL"


def test_empty_results_are_partial_not_pass(plan: dict) -> None:
    assert aggregate_cascade_status(plan, []) == "PARTIAL"


def test_any_hard_failure_makes_the_cascade_fail(plan: dict) -> None:
    results = [_result(plan, "S0", "PASS"), _result(plan, "S1", "FAIL")]
    assert aggregate_cascade_status(plan, results) == "FAIL"


def test_blocked_and_error_are_failures_not_gaps(plan: dict) -> None:
    for status in ("BLOCKED", "ERROR"):
        results = [_result(plan, "S0", status)]
        assert aggregate_cascade_status(plan, results) == "FAIL"


def test_partial_stage_keeps_the_cascade_partial(plan: dict) -> None:
    results = [
        _result(plan, "S0", "PASS"),
        _result(plan, "S1", "PARTIAL"),
        _result(plan, "S5", "PASS"),
    ]
    assert aggregate_cascade_status(plan, results) == "PARTIAL"


def test_aggregated_status_feeds_the_promotion_authority(plan: dict) -> None:
    """The three outputs must match promotion-decision hard_gate_status."""
    assert aggregate_cascade_status(plan, []) in {"PASS", "FAIL", "PARTIAL"}
