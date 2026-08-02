"""Provenance and receipt audit for the Q06 governance-integration gate.

Every govern-or-refuse decision resolves to one immutable receipt that is a pure
function of its inputs.  These tests confirm the receipt re-derives its own hash,
that its identifier is a deterministic function of the decision's binding fields,
that it binds both composed sealed verdicts and the winner's-curse selective
report by hash, and that a tampered receipt is detected rather than trusted.
"""

from __future__ import annotations

import fixtures as fx
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evaluation.v4_q06 import gate as engine


def test_receipt_re_derives_its_own_hash() -> None:
    receipt = engine.derive_governance_integration(**fx.gate_arguments())
    assert engine.governance_hash_matches(receipt)
    assert hash_excluding(dict(receipt), "receipt_hash") == receipt["receipt_hash"]


def test_refuse_receipt_re_derives_its_own_hash() -> None:
    receipt = engine.derive_governance_integration(
        **fx.gate_arguments(
            calibration_report=fx.calibration_report(
                status=fx._non_passing_calibration_status()
            )
        )
    )
    assert receipt["decision"] == engine.REFUSE
    assert engine.governance_hash_matches(receipt)


def test_gate_id_is_deterministic_across_runs() -> None:
    first = engine.derive_governance_integration(**fx.gate_arguments())
    second = engine.derive_governance_integration(**fx.gate_arguments())
    assert first["gate_id"] == second["gate_id"]
    assert first["receipt_hash"] == second["receipt_hash"]


def test_receipt_binds_the_composed_verdicts_by_hash() -> None:
    args = fx.gate_arguments()
    receipt = engine.derive_governance_integration(**args)
    admissibility = args["admissibility_receipt"]
    advancement = args["advancement_receipt"]
    assert (
        receipt["statistical_admissibility_receipt_hash"]
        == admissibility["receipt_hash"]
    )
    assert receipt["statistical_admissibility_gate_id"] == admissibility["gate_id"]
    assert receipt["validation_advancement_receipt_hash"] == advancement["receipt_hash"]
    assert receipt["validation_advancement_gate_id"] == advancement["gate_id"]
    # The advancement receipt independently binds the same Q05 clearance.
    assert (
        advancement["statistical_admissibility_receipt_hash"]
        == admissibility["receipt_hash"]
    )
    # The winner's-curse selective report is the one Q05 accounted for.
    assert receipt["selective_report_hash"] == admissibility["selective_report_hash"]


def test_a_tampered_receipt_fails_the_hash_check() -> None:
    receipt = engine.derive_governance_integration(**fx.gate_arguments())
    tampered = dict(receipt)
    tampered["decision"] = engine.GOVERN
    tampered["cleared_for_promotion_review"] = True
    tampered["finding_code"] = None
    tampered["candidate_id"] = "HG-INJECTED"
    assert not engine.governance_hash_matches(tampered)


def test_gate_id_changes_with_the_decision_binding() -> None:
    governed = engine.derive_governance_integration(**fx.gate_arguments())
    refused = engine.derive_governance_integration(
        **fx.gate_arguments(
            calibration_report=fx.calibration_report(
                status=fx._non_passing_calibration_status()
            )
        )
    )
    assert governed["gate_id"] != refused["gate_id"]
    assert governed["receipt_hash"] != refused["receipt_hash"]


def test_receipt_records_the_governed_evaluation_and_concerns() -> None:
    receipt = engine.derive_governance_integration(**fx.gate_arguments())
    assert receipt["evaluation_id"] == fx.EVALUATION_ID
    assert receipt["calibration_report_id"] == "CAL-Q06-1"
    assert receipt["selective_inference_report_id"] == "SIR-Q06-1"
    assert engine.CONCERN_WINNER_CURSE in receipt["concerns_gated"]
    assert len(receipt["concerns_gated"]) == 4
