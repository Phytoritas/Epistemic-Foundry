"""negative_and_adversarial_tests — every refusal fires under attack.

Each declared ``FINDING_CODES`` entry is provoked at least once, and the
adversarial cases are the ones this gate exists to stop at 2,000-document scale: a
declared count that does not match the ledger, a silent partial fan-in, a budget
that only forecasts spend, a measured cost or latency overrun, a surrogate that
accepted more than its budget, and a scale run that tries to become a
promotion-authority path.  A refusal that fired under the wrong code would be as
much a defect as no refusal at all, so every case asserts the exact code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.operations.v4_y06 import (
    qualification as mod,
)
from epistemic_foundry.operations.v4_y06 import (
    reconcile_qualification_counts,
    require_bounded_qualification_budget,
    require_no_scale_authority_capture,
    require_surrogate_within_ceiling,
)
from fixtures import (
    PROMOTION_CAPABILITY,
    bounded_budget,
    clean_fanout,
    expected_counts,
    measured_usage,
    soft_budget,
    triage,
)


def _code(excinfo: pytest.ExceptionInfo) -> str:
    return excinfo.value.code  # type: ignore[attr-defined]


# --- input integrity ----------------------------------------------------------


def test_empty_qualification_run_id_is_refused() -> None:
    fanout = clean_fanout()
    with pytest.raises(mod.OperationsQualificationError) as caught:
        reconcile_qualification_counts(
            qualification_run_id="",
            expected_counts=expected_counts(),
            proposed=fanout["proposed"],
            generated=fanout["generated"],
            evaluated=fanout["evaluated"],
            persisted=fanout["persisted"],
            effect_receipts=fanout["effect_receipts"],
            mutation_receipts=fanout["mutation_receipts"],
        )
    assert _code(caught) == "INPUT_INVALID"


def test_expected_count_for_an_unknown_stage_is_refused() -> None:
    fanout = clean_fanout()
    with pytest.raises(mod.OperationsQualificationError) as caught:
        reconcile_qualification_counts(
            qualification_run_id="Q",
            expected_counts={"retired": 1},
            proposed=fanout["proposed"],
            generated=fanout["generated"],
            evaluated=fanout["evaluated"],
            persisted=fanout["persisted"],
            effect_receipts=fanout["effect_receipts"],
            mutation_receipts=fanout["mutation_receipts"],
        )
    assert _code(caught) == "INPUT_INVALID"


def test_a_malformed_effect_receipt_is_refused_as_input() -> None:
    fanout = clean_fanout()
    with pytest.raises(mod.OperationsQualificationError) as caught:
        reconcile_qualification_counts(
            qualification_run_id="Q",
            expected_counts={},
            proposed=fanout["proposed"],
            generated=fanout["generated"],
            evaluated=fanout["evaluated"],
            persisted=fanout["persisted"],
            effect_receipts=[{"receipt_id": "E-1"}],  # missing required fields
            mutation_receipts=fanout["mutation_receipts"],
        )
    assert _code(caught) == "INPUT_INVALID"


def test_negative_surrogate_ceiling_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_surrogate_within_ceiling(triage_reports=[], surrogate_ceiling=-1)
    assert _code(caught) == "INPUT_INVALID"


def test_measured_usage_over_an_unknown_dimension_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_bounded_qualification_budget(
            budget_envelope=bounded_budget(),
            measured_cost=1.0,
            measured_usage={"gpu_hours": 5.0},
        )
    assert _code(caught) == "INPUT_INVALID"


def test_reshaped_surrogate_ladder_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRegistry:
        def document(self, kind: str) -> dict:
            return {"properties": {"triage_decision": {"enum": ["A", "B"]}}}

    mod._accept_decision_token.cache_clear()
    monkeypatch.setattr(mod, "default_registry", lambda: FakeRegistry())
    try:
        with pytest.raises(mod.OperationsQualificationError) as caught:
            mod._accept_decision_token()
        assert _code(caught) == "VOCABULARY_DRIFT"
    finally:
        mod._accept_decision_token.cache_clear()


# --- count reconciliation -----------------------------------------------------


def test_declared_count_that_does_not_match_the_ledger_is_refused() -> None:
    fanout = clean_fanout()
    with pytest.raises(mod.OperationsQualificationError) as caught:
        reconcile_qualification_counts(
            qualification_run_id="Q",
            expected_counts=expected_counts(persisted=99),
            proposed=fanout["proposed"],
            generated=fanout["generated"],
            evaluated=fanout["evaluated"],
            persisted=fanout["persisted"],
            effect_receipts=fanout["effect_receipts"],
            mutation_receipts=fanout["mutation_receipts"],
        )
    assert _code(caught) == "COUNT_DECLARATION_MISMATCH"


def test_a_silent_partial_fanin_is_refused() -> None:
    # CAND-2 is proposed, generated, evaluated and its effect succeeded, but it
    # never reaches the persisted set and no terminal state accounts for it.
    fanout = clean_fanout()
    with pytest.raises(mod.OperationsQualificationError) as caught:
        reconcile_qualification_counts(
            qualification_run_id="Q",
            expected_counts={},
            proposed=fanout["proposed"],
            generated=fanout["generated"],
            evaluated=fanout["evaluated"],
            persisted=["CAND-1"],
            effect_receipts=fanout["effect_receipts"],
            mutation_receipts=fanout["mutation_receipts"],
        )
    assert _code(caught) == "QUALIFICATION_FANIN_UNRECONCILED"


# --- cost and latency ---------------------------------------------------------


def test_soft_estimate_budget_for_qualification_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_bounded_qualification_budget(
            budget_envelope=soft_budget(),
            measured_cost=1.0,
            measured_usage={},
        )
    assert _code(caught) == "BUDGET_NOT_BOUNDED_FOR_QUALIFICATION"


def test_malformed_budget_envelope_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_bounded_qualification_budget(
            budget_envelope={"budget_id": "x"},
            measured_cost=1.0,
            measured_usage={},
        )
    assert _code(caught) == "BUDGET_ENVELOPE_INVALID"


def test_cost_overrun_is_refused_naming_the_cost_dimension() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_bounded_qualification_budget(
            budget_envelope=bounded_budget(soft_cost_amount=10.0),
            measured_cost=25.0,
            measured_usage={},
        )
    assert _code(caught) == "BUDGET_DIMENSION_OVERRUN"
    breached = {row["dimension"] for row in caught.value.context["overruns"]}
    assert breached == {mod.COST_DIMENSION}


def test_latency_overrun_is_refused_naming_the_latency_dimension() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_bounded_qualification_budget(
            budget_envelope=bounded_budget(),
            measured_cost=1.0,
            measured_usage=measured_usage(wall_seconds=9_999.0),
        )
    assert _code(caught) == "BUDGET_DIMENSION_OVERRUN"
    breached = {row["dimension"] for row in caught.value.context["overruns"]}
    assert "wall_seconds" in breached


# --- surrogate ceiling --------------------------------------------------------


def test_surrogate_report_waiving_direct_evaluation_is_refused() -> None:
    forged = dict(triage("CAND-1"))
    forged["direct_evaluation_required"] = False
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_surrogate_within_ceiling(triage_reports=[forged], surrogate_ceiling=5)
    assert _code(caught) == "SURROGATE_ORDERING_WAIVED"


def test_surrogate_accepting_more_than_the_ceiling_is_refused() -> None:
    reports = [triage("CAND-1"), triage("CAND-2"), triage("CAND-3")]
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_surrogate_within_ceiling(triage_reports=reports, surrogate_ceiling=2)
    assert _code(caught) == "SURROGATE_ACCEPTANCE_EXCEEDS_CEILING"
    assert caught.value.context["accepted_count"] == 3


# --- authority containment ----------------------------------------------------


def test_search_artifact_granted_promotion_authority_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_no_scale_authority_capture(
            authority_claims=[
                {
                    "capability_id": PROMOTION_CAPABILITY,
                    "holder_id": "CAND-1",
                    "holder_is_search_space": True,
                }
            ]
        )
    assert _code(caught) == "SCALE_RUN_ACQUIRES_PROMOTION_AUTHORITY"


def test_declared_protected_authority_to_a_search_artifact_is_refused() -> None:
    # A caller-declared protected authority is refused even when the capability is
    # not the canonical promotion-commit one.
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_no_scale_authority_capture(
            authority_claims=[
                {
                    "capability_id": "holdout:read",
                    "holder_id": "model-x",
                    "holder_is_search_space": True,
                    "protected_authority": True,
                }
            ]
        )
    assert _code(caught) == "SCALE_RUN_ACQUIRES_PROMOTION_AUTHORITY"


def test_score_bound_into_a_promotion_decision_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_no_scale_authority_capture(
            authority_claims=[
                {
                    "capability_id": PROMOTION_CAPABILITY,
                    "holder_id": "gate",
                    "holder_is_search_space": False,
                    "decision_basis": {"predicted_utility": 0.91},
                }
            ]
        )
    assert _code(caught) == "SCORE_BOUND_INTO_PROMOTION_FIELD"


def test_a_malformed_authority_claim_is_refused() -> None:
    with pytest.raises(mod.OperationsQualificationError) as caught:
        require_no_scale_authority_capture(authority_claims=["not-a-mapping"])
    assert _code(caught) == "INPUT_INVALID"
