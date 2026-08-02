"""unit_and_contract_tests — the gate composes the sealed surfaces correctly.

These tests drive the happy path of every gate: a clean reward signal is
admitted with its embedded S05 leakage audit, a future-only evaluator update is
governed against an independent qualification of the future bundle, and the two
sealed sub-receipts compose into one integration record.  The contract is that
each decision is *derived* from the composed records — the fitness vector's own
hard-gate status, the routing receipt's own reward basis, the firewall's own
leakage set, the proposal's own governance flags — rather than asserted by the
caller.
"""

from __future__ import annotations

from epistemic_foundry.security.v4_s06 import (
    EVALUATOR_RECEIPT_PREFIX,
    INTEGRATION_RECEIPT_PREFIX,
    REWARD_RECEIPT_PREFIX,
    govern_evaluator_update,
    integrate_evolution_security_gate,
    refuse_reward_hacking,
)
from fixtures import (
    CURRENT_BUNDLE_ID,
    FUTURE_BUNDLE_ID,
    FUTURE_RUN_ID,
    RUN_ID,
    evaluator_arguments,
    reward_arguments,
)


def test_clean_reward_signal_is_admitted_with_its_audit() -> None:
    receipt = refuse_reward_hacking(**reward_arguments())
    assert receipt["receipt_id"].startswith(REWARD_RECEIPT_PREFIX)
    assert receipt["candidate_id"] == "CAND-1"
    audit = receipt["leakage_audit"]
    assert audit["detected_exposures"] == []
    assert audit["required_actions"] == []
    # The audit id is deterministic, not the S05 builder's random default, so the
    # whole receipt replays.
    assert receipt["leakage_audit_id"] == audit["leakage_audit_id"]


def test_a_future_only_evaluator_update_is_governed() -> None:
    receipt = govern_evaluator_update(**evaluator_arguments())
    assert receipt["receipt_id"].startswith(EVALUATOR_RECEIPT_PREFIX)
    assert receipt["source_run_id"] == RUN_ID
    assert receipt["target_run_id"] == FUTURE_RUN_ID
    assert receipt["current_evaluator_bundle_id"] == CURRENT_BUNDLE_ID
    assert receipt["future_evaluator_bundle_id"] == FUTURE_BUNDLE_ID
    # The governance node is composed from J05's workflow reader, not asserted.
    assert receipt["governance_node_id"] == "verify_no_retroactive_effect"


def test_the_governance_receipt_binds_the_qualification_of_the_future_bundle() -> None:
    receipt = govern_evaluator_update(**evaluator_arguments())
    assert receipt["qualification_report_id"] == "EQR-FUTURE"
    assert (
        receipt["future_evaluator_bundle_id"] != receipt["current_evaluator_bundle_id"]
    )


def test_the_integration_gate_binds_both_sub_receipts() -> None:
    reward = refuse_reward_hacking(**reward_arguments())
    update = govern_evaluator_update(**evaluator_arguments())
    integration = integrate_evolution_security_gate(
        run_id=RUN_ID,
        reward_receipt=reward,
        evaluator_update_receipt=update,
    )
    assert integration["receipt_id"].startswith(INTEGRATION_RECEIPT_PREFIX)
    assert (
        integration["components"]["reward_hacking_receipt_id"] == reward["receipt_id"]
    )
    assert (
        integration["components"]["evaluator_update_receipt_id"] == update["receipt_id"]
    )
    assert "evaluator_update_future_only" in integration["concerns_gated"]


def test_the_integration_gate_runs_without_an_evaluator_update() -> None:
    reward = refuse_reward_hacking(**reward_arguments())
    integration = integrate_evolution_security_gate(
        run_id=RUN_ID, reward_receipt=reward
    )
    assert "evaluator_update_receipt_id" not in integration["components"]
    assert "evaluator_update_future_only" not in integration["concerns_gated"]
    assert "reward_hacking_refusal" in integration["concerns_gated"]
