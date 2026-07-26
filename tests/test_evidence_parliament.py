"""Adjudication cannot override deterministic gates or promote by itself."""

from __future__ import annotations

import pytest

from epistemic_foundry.evidence_parliament import (
    GateOverrideAttempted,
    build_adjudication,
    recommendation_is_binding,
)
from epistemic_foundry.foundry_kernel.gates import GateSpec, evaluate_gate, gate_decision


def _decision(name: str, satisfied: bool) -> dict:
    inputs = {"evidence_ids": ["EV-1"]} if satisfied else {}
    return gate_decision(
        evaluate_gate(GateSpec(name, ("evidence_ids",)), inputs),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs=inputs,
    )


def _adjudicate(**overrides) -> dict:
    kwargs = dict(
        run_id="RUN-0001",
        hypothesis_id="HYP-0001",
        gate_decisions=[_decision("leakage_audit", True)],
        brief_ids=["CB-0001"],
        cross_examination_ids=["CX-0001"],
        verdict="SUPPORTED",
        promotion_recommendation="CANDIDATE",
        rationale="support outweighs counterevidence within the stated scope",
        strongest_support_id="EV-0001",
        strongest_counterevidence_id="EV-0002",
    )
    kwargs.update(overrides)
    return build_adjudication(**kwargs)


def test_clean_gates_allow_an_advancing_recommendation() -> None:
    record = _adjudicate()
    assert record["promotion_recommendation"] == "CANDIDATE"
    assert record["deterministic_gate_override_attempted"] is False


def test_failed_gate_plus_advancing_recommendation_is_refused() -> None:
    """A deliberative verdict must not outrank a failed hard gate."""
    with pytest.raises(GateOverrideAttempted) as excinfo:
        _adjudicate(gate_decisions=[_decision("leakage_audit", False)])
    assert "cannot override a hard gate" in str(excinfo.value)


def test_override_attempt_is_recorded_not_discarded() -> None:
    """The attempt is evidence about the deliberation, so it persists."""
    record = _adjudicate(
        gate_decisions=[_decision("leakage_audit", False)],
        refuse_override=False,
    )
    assert record["deterministic_gate_override_attempted"] is True


def test_override_flag_is_derived_not_caller_supplied() -> None:
    """The party attempting an override cannot declare it did not happen."""
    import inspect

    params = inspect.signature(build_adjudication).parameters
    assert "deterministic_gate_override_attempted" not in params


def test_failed_gate_with_blocking_recommendation_is_allowed() -> None:
    """Reporting BLOCK against a failed gate is the honest outcome, not an override."""
    record = _adjudicate(
        gate_decisions=[_decision("leakage_audit", False)],
        verdict="UNDERDETERMINED",
        promotion_recommendation="BLOCK",
    )
    assert record["deterministic_gate_override_attempted"] is False


def test_inbox_triage_against_a_failed_gate_is_not_an_override() -> None:
    record = _adjudicate(
        gate_decisions=[_decision("leakage_audit", False)],
        verdict="UNDERDETERMINED",
        promotion_recommendation="INBOX",
    )
    assert record["deterministic_gate_override_attempted"] is False


def test_waived_gate_is_not_treated_as_failure() -> None:
    waived = gate_decision(
        evaluate_gate(GateSpec("style", ("x",), non_waivable=False), {}),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs={},
        waiver_authority="HUMAN-1",
        waiver_reason="cosmetic only, documented",
    )
    assert waived["status"] == "WAIVE"
    record = _adjudicate(gate_decisions=[waived])
    assert record["deterministic_gate_override_attempted"] is False


def test_minority_reports_and_unresolved_issues_persist() -> None:
    """Dissent stays attached; a clean verdict may not be bought by omission."""
    record = _adjudicate(
        minority_report_ids=["MR-0001", "MR-0002"],
        unresolved_issue_ids=["ISSUE-0001"],
    )
    assert record["minority_report_ids"] == ["MR-0001", "MR-0002"]
    assert record["unresolved_issue_ids"] == ["ISSUE-0001"]


def test_gate_decision_ids_are_bound_to_the_record() -> None:
    passing = _decision("leakage_audit", True)
    record = _adjudicate(gate_decisions=[passing])
    assert record["gate_decision_ids"] == [passing["gate_id"]]


def test_a_recommendation_is_never_promotion_authority() -> None:
    assert recommendation_is_binding(_adjudicate(promotion_recommendation="REPLICATED")) is False
