"""Unit and contract tests for the Q06 governance-integration gate.

These pin the three composed decision concerns to their sealed owners: the Q05
admissibility must have admitted, the V05 advancement must have advanced, and the
calibration report must pass — with the winner's-curse deflation bound to the
admission rather than re-decided.  The happy path governs the selection as
cleared; each concern, varied alone, changes the verdict in the direction its
owner defines, and no single concern carries the decision.
"""

from __future__ import annotations

import copy

import fixtures as fx
import pytest
from epistemic_foundry.evaluation.v4_q06 import gate as engine


def test_happy_path_governs() -> None:
    receipt = engine.derive_governance_integration(**fx.gate_arguments())
    assert receipt["decision"] == engine.GOVERN
    assert receipt["cleared_for_promotion_review"] is True
    assert receipt["finding_code"] is None


def test_evaluate_returns_on_govern() -> None:
    receipt = engine.evaluate_governance_integration(**fx.gate_arguments())
    assert receipt["decision"] == engine.GOVERN


def test_evaluate_raises_on_refuse_and_carries_the_receipt() -> None:
    with pytest.raises(engine.GovernanceIntegrationRefused) as excinfo:
        engine.evaluate_governance_integration(
            **fx.gate_arguments(
                calibration_report=fx.calibration_report(
                    status=fx._non_passing_calibration_status()
                )
            )
        )
    assert excinfo.value.code == "CALIBRATION_NOT_PASSED"
    assert excinfo.value.context["receipt"]["decision"] == engine.REFUSE


def test_derivation_is_deterministic() -> None:
    first = engine.derive_governance_integration(**fx.gate_arguments())
    second = engine.derive_governance_integration(**fx.gate_arguments())
    assert first == second


def test_inputs_are_not_mutated() -> None:
    arguments = fx.gate_arguments()
    snapshot = copy.deepcopy(arguments)
    engine.derive_governance_integration(**arguments)
    assert arguments == snapshot


def test_admissibility_must_have_admitted() -> None:
    report = fx.selective_report(replication_count=0)
    clearance = fx.admissibility_receipt(report=report)
    refused = engine.derive_governance_integration(
        **fx.gate_arguments(
            admissibility_receipt=clearance,
            advancement_receipt=fx.advancement_receipt(admissibility=clearance),
            selective_report=report,
        )
    )
    assert refused["decision"] == engine.REFUSE
    assert refused["finding_code"] == "ADMISSIBILITY_NOT_ADMITTED"


def test_advancement_must_have_advanced() -> None:
    clearance = fx.admissibility_receipt()
    refused = engine.derive_governance_integration(
        **fx.gate_arguments(
            admissibility_receipt=clearance,
            advancement_receipt=fx.advancement_receipt(
                admissibility=clearance, advanced=False
            ),
        )
    )
    assert refused["decision"] == engine.REFUSE
    assert refused["finding_code"] == "ADVANCEMENT_NOT_ADVANCED"


def test_calibration_must_pass() -> None:
    refused = engine.derive_governance_integration(
        **fx.gate_arguments(
            calibration_report=fx.calibration_report(
                status=fx._non_passing_calibration_status()
            )
        )
    )
    assert refused["decision"] == engine.REFUSE
    assert refused["finding_code"] == "CALIBRATION_NOT_PASSED"


def test_no_single_concern_carries_the_decision() -> None:
    """Each concern alone flips a govern to a refuse; none alone governs."""
    baseline = engine.derive_governance_integration(**fx.gate_arguments())
    assert baseline["decision"] == engine.GOVERN
    # Calibration alone can refuse even with admissibility and advancement intact.
    only_calibration_broken = engine.derive_governance_integration(
        **fx.gate_arguments(
            calibration_report=fx.calibration_report(
                status=fx._non_passing_calibration_status()
            )
        )
    )
    assert only_calibration_broken["decision"] == engine.REFUSE
    # And the sealed statistical admission alone can refuse with calibration intact.
    report = fx.selective_report(replication_count=0)
    clearance = fx.admissibility_receipt(report=report)
    only_admission_broken = engine.derive_governance_integration(
        **fx.gate_arguments(
            admissibility_receipt=clearance,
            advancement_receipt=fx.advancement_receipt(admissibility=clearance),
            selective_report=report,
        )
    )
    assert only_admission_broken["decision"] == engine.REFUSE


def test_calibration_pass_status_matches_the_schema_first_rung() -> None:
    from epistemic_foundry.contracts import default_registry

    document = default_registry().document("calibration-report")
    assert (
        engine.calibration_pass_status()
        == document["properties"]["calibration_status"]["enum"][0]
    )
