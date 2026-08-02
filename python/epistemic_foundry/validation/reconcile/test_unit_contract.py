"""unit_contract — the gate reconciles three surfaces into one honest claim.

These are the behaviours the exit criteria name, exercised one surface at a
time.  A clean, uncontested, honestly-classed result promotes.  A run that did
not cleanly execute, or a result that was falsified or inconclusive, is kept for
human review rather than dropped or promoted.  A clean run that tested nothing
falsifiable is quarantined.  The class a source produced is copied forward
verbatim, and the decision is categorical the whole way down: the same result
under a different quality vector reconciles identically.
"""

from __future__ import annotations


from .contracts import (
    PROMOTE,
    QUARANTINE,
    REJECT,
    REQUIRE_HUMAN_REVIEW,
    assess_reconciliation,
    reconcile_evidence,
)
from .fixtures import (
    ROOT,
    denied_execution_record,
    experiment_result,
    reconcile_arguments,
    reconciliation,
)


def test_a_clean_uncontested_result_promotes() -> None:
    record = reconciliation()

    assert record["promotion_decision"] == PROMOTE
    assert record["non_empirical_guard_passed"] is True
    assert record["target_evidence_role"] == "support"
    assert record["reasons"]


def test_the_source_class_is_copied_forward_verbatim() -> None:
    record = reconciliation(
        experiment_result=experiment_result(evidence_class="benchmark"),
        candidate_evidence_class="benchmark",
    )

    assert record["source_evidence_class"] == "benchmark"


def test_a_failed_run_is_not_a_confirmation() -> None:
    # The one clean run reused, but the result reports it did not complete: a
    # support role can no longer be entered, and the whole thing is rejected.
    record = reconciliation(experiment_result=experiment_result(status="FAILED"))

    assert record["promotion_decision"] == REJECT
    assert (
        "confirmation_supported"
        not in assess_reconciliation(ROOT, **_assess_args(status="FAILED"))[
            "criteria_satisfied"
        ]
    )


def test_a_denied_execution_gate_cannot_confirm() -> None:
    record = reconciliation(execution_record=denied_execution_record())

    assert record["promotion_decision"] == REJECT


def test_a_falsified_result_is_reviewed_not_dropped() -> None:
    record = reconciliation(
        target_evidence_role="counter",
        experiment_result=experiment_result(falsification_outcome="FALSIFIED"),
    )

    assert record["promotion_decision"] == REQUIRE_HUMAN_REVIEW


def test_an_inconclusive_result_is_reviewed() -> None:
    record = reconciliation(
        target_evidence_role="null",
        experiment_result=experiment_result(falsification_outcome="INCONCLUSIVE"),
    )

    assert record["promotion_decision"] == REQUIRE_HUMAN_REVIEW


def test_a_clean_run_that_tested_nothing_is_quarantined() -> None:
    record = reconciliation(
        target_evidence_role="method",
        experiment_result=experiment_result(falsification_outcome="NOT_APPLICABLE"),
    )

    assert record["promotion_decision"] == QUARANTINE


def test_a_non_empirical_source_may_promote_at_its_own_class() -> None:
    # Modeling evidence entered as modeling is not a relabel; it promotes.
    record = reconciliation(
        experiment_result=experiment_result(evidence_class="formal"),
        candidate_evidence_class="formal",
    )

    assert record["promotion_decision"] == PROMOTE
    assert record["non_empirical_guard_passed"] is True


def test_an_empirical_source_may_be_an_empirical_candidate() -> None:
    record = reconciliation(
        experiment_result=experiment_result(
            evidence_class="prospective_empirical", result_type="prospective_experiment"
        ),
        candidate_evidence_class="primary_empirical",
    )

    assert record["non_empirical_guard_passed"] is True
    assert record["promotion_decision"] == PROMOTE


def test_the_decision_ignores_the_quality_vector() -> None:
    base = reconciliation()
    generous = reconciliation(
        quality_adjustments={"directness": 0.99, "replication": 0.99}
    )

    assert base["promotion_decision"] == generous["promotion_decision"]
    assert base["non_empirical_guard_passed"] == generous["non_empirical_guard_passed"]


def test_the_assessment_reports_every_criterion() -> None:
    ledger = assess_reconciliation(ROOT, **_assess_args())

    assert set(ledger["criteria"]) >= set(ledger["criteria_satisfied"])
    assert ledger["refusal_codes"] == []
    assert ledger["promotion_decision"] == PROMOTE


def test_the_preregistration_is_optional_context() -> None:
    # A reconciliation can be produced without a preregistration; supplying one
    # only adds the guarantee that the falsification rule was not edited after
    # the fact, so both paths reach the same decision here.
    with_plan = reconciliation()
    without_plan = reconcile_evidence(
        ROOT, **{**reconcile_arguments(), "preregistration": None}
    )

    assert with_plan["promotion_decision"] == without_plan["promotion_decision"]


def _assess_args(**overrides: object) -> dict:
    result_overrides = {
        key: overrides.pop(key)
        for key in ("status", "falsification_outcome", "evidence_class")
        if key in overrides
    }
    arguments = reconcile_arguments()
    for field in (
        "reconciliation_id",
        "candidate_evidence_id",
        "scope_mapping",
        "quality_adjustments",
        "created_at",
    ):
        arguments.pop(field, None)
    if result_overrides:
        arguments["experiment_result"] = experiment_result(**result_overrides)
    arguments.update(overrides)
    return arguments
