"""negative_and_adversarial_tests — every refusal is reachable and typed.

Each finding code the gate declares is driven by an input that should trip it,
and the adversarial cases target the boundaries the gate exists to hold: a
hard-gate-failed candidate whose proxy dimensions are routed as reward, a reward
that learns only from the immediate proxy basis, feedback carrying a holdout
handle, a proposal that waives its own no-retroactivity flag, an update aimed at
the run that produced it, a qualification of the current bundle masquerading as
an independent one, and a tampered sub-gate receipt.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.operators.v4_j05 import MutationOperatorError
from epistemic_foundry.security.v4_s06 import (
    GovernanceGateError,
    govern_evaluator_update,
    integrate_evolution_security_gate,
    refuse_reward_hacking,
)
from epistemic_foundry.security.v4_s06 import governance_gate as gate
from fixtures import (
    CURRENT_BUNDLE_ID,
    FAIL,
    HIDDEN_HANDLE,
    IMMEDIATE_PROXY,
    QUARANTINED,
    REJECTED,
    RUN_ID,
    evaluator_arguments,
    evaluator_proposal,
    fitness_vector,
    qualification_report,
    reward_arguments,
    routing_receipt,
)


def _code(call) -> str:
    with pytest.raises(GovernanceGateError) as caught:
        call()
    return caught.value.code


# -- input integrity ------------------------------------------------------


def test_a_non_mapping_fitness_vector_is_input_invalid() -> None:
    assert _code(
        lambda: refuse_reward_hacking(**reward_arguments(fitness_vector=[]))
    ) == ("INPUT_INVALID")


def test_a_blank_run_id_is_input_invalid() -> None:
    assert _code(
        lambda: refuse_reward_hacking(**reward_arguments(run_or_bundle_id=" "))
    ) == ("INPUT_INVALID")


def test_a_mis_sized_vocabulary_is_refused() -> None:
    assert _code(lambda: gate._enum(gate.FITNESS_KIND, "hard_gate_status", 9)) == (
        "VOCABULARY_DRIFT"
    )


# -- reward-hacking -------------------------------------------------------


def test_a_malformed_fitness_vector_is_refused() -> None:
    broken = fitness_vector()
    broken.pop("dimensions")
    assert (
        _code(lambda: refuse_reward_hacking(**reward_arguments(fitness_vector=broken)))
        == "FITNESS_CONTRACT_VIOLATED"
    )


def test_a_malformed_routing_receipt_is_refused() -> None:
    broken = routing_receipt(policy="not-a-policy")
    assert (
        _code(lambda: refuse_reward_hacking(**reward_arguments(routing_receipt=broken)))
        == "ROUTING_CONTRACT_VIOLATED"
    )


def test_rewarding_a_hard_gate_failed_candidate_is_refused() -> None:
    failed = fitness_vector(hard_gate_status=FAIL, hard_gate_failures=["G07"])
    assert (
        _code(lambda: refuse_reward_hacking(**reward_arguments(fitness_vector=failed)))
        == "REWARD_HACKING_HARD_GATE_FAILED"
    )


def test_an_immediate_proxy_only_reward_basis_is_refused() -> None:
    proxy = routing_receipt(reward_basis=IMMEDIATE_PROXY)
    assert (
        _code(lambda: refuse_reward_hacking(**reward_arguments(routing_receipt=proxy)))
        == "REWARD_BASIS_IMMEDIATE_PROXY_ONLY"
    )


def test_feedback_carrying_a_holdout_handle_is_refused() -> None:
    assert (
        _code(
            lambda: refuse_reward_hacking(
                **reward_arguments(feedback_artifact_ids=["FB-1", HIDDEN_HANDLE])
            )
        )
        == "REWARD_FEEDBACK_LEAKAGE"
    )


def test_an_incomplete_leakage_surface_set_surfaces_the_audit_refusal() -> None:
    assert (
        _code(lambda: refuse_reward_hacking(**reward_arguments(surfaces_checked=[])))
        == "LEAKAGE_AUDIT_REFUSED"
    )


# -- evaluator-update governance ------------------------------------------


def test_a_malformed_proposal_is_refused() -> None:
    broken = evaluator_proposal()
    broken.pop("defect_class")
    assert (
        _code(lambda: govern_evaluator_update(**evaluator_arguments(proposal=broken)))
        == "EVALUATOR_PROPOSAL_CONTRACT_VIOLATED"
    )


def test_a_proposal_that_waives_no_retroactivity_is_refused() -> None:
    from epistemic_foundry.domain.hashing import hash_excluding

    waiving = evaluator_proposal()
    waiving["retroactive_effect_prohibited"] = False
    waiving["proposal_hash"] = hash_excluding(waiving, "proposal_hash")
    assert (
        _code(lambda: govern_evaluator_update(**evaluator_arguments(proposal=waiving)))
        == "EVALUATOR_UPDATE_RETROACTIVE_PERMITTED"
    )


def test_a_drifted_current_evaluator_bundle_is_refused() -> None:
    arguments = evaluator_arguments()
    # Poke the sealed record so it no longer re-hashes: an evaluator update that
    # has already mutated the current run's bundle must fail closed.
    arguments["firewall"]._bundle["evaluator_version"] = "9.9.9"
    assert (
        _code(lambda: govern_evaluator_update(**arguments)) == "EVALUATOR_BUNDLE_DRIFT"
    )


def test_a_reachable_holdout_is_refused() -> None:
    class _ReachableFirewall:
        bundle_id = CURRENT_BUNDLE_ID

        def verify_self(self) -> None:
            return None

        def may_read_holdout(self, principal_id: str, role: str) -> bool:
            return True

    assert (
        _code(
            lambda: govern_evaluator_update(
                **evaluator_arguments(firewall=_ReachableFirewall())
            )
        )
        == "HOLDOUT_REACHABLE"
    )


def test_an_unapproved_proposal_is_refused() -> None:
    held = evaluator_proposal(status=QUARANTINED)
    assert (
        _code(lambda: govern_evaluator_update(**evaluator_arguments(proposal=held)))
        == "EVALUATOR_UPDATE_NOT_APPROVED"
    )


def test_an_update_aimed_at_the_source_run_is_retroactive() -> None:
    assert (
        _code(
            lambda: govern_evaluator_update(**evaluator_arguments(target_run_id=RUN_ID))
        )
        == "EVALUATOR_UPDATE_RETROACTIVE"
    )


def test_a_malformed_qualification_report_is_refused() -> None:
    broken = qualification_report()
    broken.pop("qualification_status")
    assert (
        _code(
            lambda: govern_evaluator_update(
                **evaluator_arguments(qualification_report=broken)
            )
        )
        == "EVALUATOR_QUALIFICATION_CONTRACT_VIOLATED"
    )


def test_an_unqualified_report_is_refused() -> None:
    rejected = qualification_report(qualification_status=REJECTED)
    assert (
        _code(
            lambda: govern_evaluator_update(
                **evaluator_arguments(qualification_report=rejected)
            )
        )
        == "EVALUATOR_QUALIFICATION_NOT_QUALIFIED"
    )


def test_a_report_that_re_qualifies_the_current_bundle_is_not_independent() -> None:
    not_independent = qualification_report(evaluator_bundle_id=CURRENT_BUNDLE_ID)
    assert (
        _code(
            lambda: govern_evaluator_update(
                **evaluator_arguments(qualification_report=not_independent)
            )
        )
        == "EVALUATOR_QUALIFICATION_NOT_INDEPENDENT"
    )


def test_a_missing_workflow_node_is_surfaced_as_drift(monkeypatch) -> None:
    def _raise() -> str:
        raise MutationOperatorError(
            "WORKFLOW_CONTRACT_DRIFT", "the node is gone", {"path": "workflow"}
        )

    monkeypatch.setattr(gate, "governance_retroactivity_node", _raise)
    assert _code(lambda: govern_evaluator_update(**evaluator_arguments())) == (
        "WORKFLOW_CONTRACT_DRIFT"
    )


# -- integration ----------------------------------------------------------


def test_a_tampered_sub_gate_receipt_is_refused() -> None:
    reward = refuse_reward_hacking(**reward_arguments())
    reward["candidate_id"] = "SWAPPED"
    assert (
        _code(
            lambda: integrate_evolution_security_gate(
                run_id=RUN_ID, reward_receipt=reward
            )
        )
        == "INTEGRATION_SUBGATE_TAMPERED"
    )


def test_a_tampered_evaluator_sub_receipt_is_refused() -> None:
    reward = refuse_reward_hacking(**reward_arguments())
    update = govern_evaluator_update(**evaluator_arguments())
    update["target_run_id"] = "ELSEWHERE"
    assert (
        _code(
            lambda: integrate_evolution_security_gate(
                run_id=RUN_ID,
                reward_receipt=reward,
                evaluator_update_receipt=update,
            )
        )
        == "INTEGRATION_SUBGATE_TAMPERED"
    )
