"""negative_adversarial — the gate refuses the ways a claim could overreach.

Each refusal here is a way a result could be made to say more than the three
surfaces support: a non-empirical run relabelled as empirical observation, a
failed or refuted run entered as a confirmation, a result whose surfaces do not
agree on which run they describe, an execution record or preregistration edited
after it was sealed, or a caller reaching for a decision the gate alone is
allowed to make.  The gate reports the whole ledger of policy refusals in one
pass and raises the structural ones that leave nothing to reconcile, and in
every case the caller's own inputs come back untouched.
"""

from __future__ import annotations

import copy

import pytest

from .contracts import (
    REJECT,
    ValidationReconciliationError,
    assess_reconciliation,
    reconcile_evidence,
)
from .fixtures import (
    ROOT,
    denied_execution_record,
    execution_record,
    experiment_result,
    preregistration,
    reconcile_arguments,
    reconciliation,
    scope_mapping,
)


def _raises(code: str, **overrides: object) -> ValidationReconciliationError:
    with pytest.raises(ValidationReconciliationError) as error:
        reconciliation(**overrides)
    assert error.value.code == code
    return error.value


def test_a_non_empirical_source_cannot_be_relabelled_empirical() -> None:
    record = reconciliation(candidate_evidence_class="primary_empirical")

    assert record["promotion_decision"] == REJECT
    assert record["non_empirical_guard_passed"] is False


def test_the_relabel_refusal_is_reported_in_the_ledger() -> None:
    ledger = _assess(candidate_evidence_class="secondary_empirical")

    assert "EVIDENCE_CLASS_OVERCLAIMED" in ledger["refusal_codes"]
    assert "evidence_class_preserved" not in ledger["criteria_satisfied"]


def test_a_confirmation_from_a_failed_run_is_refused() -> None:
    ledger = _assess(experiment_result=experiment_result(status="INVALIDATED"))

    assert "CONFIRMATION_WITHOUT_CLEAN_RUN" in ledger["refusal_codes"]
    assert ledger["promotion_decision"] == REJECT


def test_a_confirmation_from_a_falsified_run_is_refused() -> None:
    ledger = _assess(
        experiment_result=experiment_result(falsification_outcome="FALSIFIED")
    )

    assert "CONFIRMATION_WITHOUT_CLEAN_RUN" in ledger["refusal_codes"]


def test_both_overclaims_are_reported_in_one_pass() -> None:
    ledger = _assess(
        candidate_evidence_class="primary_empirical",
        experiment_result=experiment_result(falsification_outcome="FALSIFIED"),
    )

    assert {"EVIDENCE_CLASS_OVERCLAIMED", "CONFIRMATION_WITHOUT_CLEAN_RUN"} <= set(
        ledger["refusal_codes"]
    )


def test_a_denied_gate_is_read_not_re_adjudicated() -> None:
    # V04 does not re-run or overturn V03's gate; a DENIED run simply cannot
    # confirm, so the confirmation is rejected.
    record = reconciliation(execution_record=denied_execution_record())

    assert record["promotion_decision"] == REJECT


def test_surfaces_that_name_different_runs_cannot_reconcile() -> None:
    _raises("SURFACES_UNRECONCILED", run_id="VRUN-OTHER")
    _raises(
        "SURFACES_UNRECONCILED",
        experiment_result=experiment_result(run_id="VRUN-OTHER"),
    )
    _raises(
        "SURFACES_UNRECONCILED",
        experiment_result=experiment_result(result_id="VXRES-OTHER"),
    )


def test_an_edited_execution_record_is_refused() -> None:
    record = execution_record()
    record["run_id"] = "VRUN-EDITED"

    _raises("EXECUTION_UNSEALED", execution_record=record)


def test_an_edited_preregistration_is_refused() -> None:
    plan = preregistration()
    plan["preregistered_at"] = "2099-01-01T00:00:00Z"

    _raises("PREREGISTRATION_MUTATED", preregistration=plan)


def test_a_malformed_experiment_result_is_refused() -> None:
    _raises(
        "RESULT_SCHEMA_INVALID",
        experiment_result=experiment_result(status="NOT_A_STATUS"),
    )
    _raises(
        "INPUT_INVALID",
        target_evidence_role="not_a_role",
    )
    _raises(
        "INPUT_INVALID",
        candidate_evidence_class="not_a_class",
    )


def test_a_scope_missing_an_axis_is_refused() -> None:
    scope = scope_mapping()
    del scope["geography"]

    _raises("FIELD_SET_INVALID", scope_mapping=scope)


def test_a_structured_quality_adjustment_is_refused() -> None:
    _raises("INPUT_INVALID", quality_adjustments={"vector": [1, 2, 3]})
    _raises("INPUT_INVALID", quality_adjustments={"flag": True})


def test_a_caller_cannot_inject_the_decision() -> None:
    # The promotion decision and the guard flag are derived, never accepted;
    # a caller reaching for them is a TypeError, not a smuggled promotion.
    with pytest.raises(TypeError):
        reconcile_evidence(
            ROOT, **{**reconcile_arguments(), "promotion_decision": "PROMOTE"}
        )
    with pytest.raises(TypeError):
        reconcile_evidence(
            ROOT, **{**reconcile_arguments(), "non_empirical_guard_passed": True}
        )


def test_the_source_class_is_never_taken_from_the_caller() -> None:
    # There is no source-class argument; the class is read from the result, so
    # a caller cannot declare a class the run did not produce.
    with pytest.raises(TypeError):
        reconcile_evidence(
            ROOT,
            **{**reconcile_arguments(), "source_evidence_class": "primary_empirical"},
        )


def test_the_caller_inputs_are_not_mutated() -> None:
    arguments = reconcile_arguments()
    snapshot = copy.deepcopy(arguments)

    reconcile_evidence(ROOT, **arguments)

    assert arguments == snapshot


def _assess(**overrides: object) -> dict:
    arguments = reconcile_arguments()
    for field in (
        "reconciliation_id",
        "candidate_evidence_id",
        "scope_mapping",
        "quality_adjustments",
        "created_at",
    ):
        arguments.pop(field, None)
    arguments.update(overrides)
    return assess_reconciliation(ROOT, **arguments)


def test_a_quarantine_and_a_review_are_not_collapsed() -> None:
    # An untested clean run and a failed run reach different decisions, so a
    # broken pipeline never wears the same label as an honest null test.
    untested = reconciliation(
        target_evidence_role="method",
        experiment_result=experiment_result(falsification_outcome="NOT_APPLICABLE"),
    )
    failed = reconciliation(
        target_evidence_role="limitation",
        experiment_result=experiment_result(status="FAILED"),
    )

    assert untested["promotion_decision"] != failed["promotion_decision"]
