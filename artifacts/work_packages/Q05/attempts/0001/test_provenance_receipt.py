"""Provenance and receipt checks for the Q05 admissibility gate.

Every decision resolves to an immutable receipt that re-derives from its own
published fields, replays byte for byte, binds the sealed hidden evaluation and
statistical record by hash, and never mutates the inputs it was handed. A refusal
carries the same receipt on the raised error, so the record of why a candidate
was stopped short of promotion review is as auditable as an admission — and it
never contains the hidden holdout content it stands in front of.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import canonical_json, hash_excluding, sha256_hex
from epistemic_foundry.evaluation.v4_q05 import gate
from epistemic_foundry.evaluation.v4_q05.gate import SelectiveAdmissibilityRefused
from fixtures import fitness_vector, gate_arguments


def test_the_receipt_hash_covers_the_receipt() -> None:
    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_the_gate_id_is_a_pure_function_of_the_decision_content() -> None:
    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    expected = (
        gate.GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": receipt["candidate_id"],
                    "created_at": receipt["created_at"],
                    "decision": receipt["decision"],
                    "evaluator_bundle_hash": receipt["evaluator_bundle_hash"],
                    "fitness_vector_id": receipt["fitness_vector_id"],
                    "search_statistics_record_hash": receipt[
                        "search_statistics_record_hash"
                    ],
                }
            )
        )[len("sha256:") :]
    )
    assert receipt["gate_id"] == expected


def test_an_admitted_decision_replays_byte_for_byte() -> None:
    first = gate.evaluate_selective_admissibility(**gate_arguments())
    second = gate.evaluate_selective_admissibility(**gate_arguments())
    assert first == second


def test_a_refused_decision_replays_byte_for_byte() -> None:
    arguments = gate_arguments(
        fitness_vector=fitness_vector(
            hard_gate_status="FAIL", hard_gate_failures=["G02"]
        )
    )
    first = gate.derive_selective_admissibility(**arguments)
    second = gate.derive_selective_admissibility(**arguments)
    assert first == second
    assert first["decision"] == gate.REFUSE


def test_a_refusal_carries_the_immutable_receipt_on_the_error() -> None:
    arguments = gate_arguments(
        fitness_vector=fitness_vector(
            hard_gate_status="FAIL", hard_gate_failures=["G02"]
        )
    )
    try:
        gate.evaluate_selective_admissibility(**arguments)
    except SelectiveAdmissibilityRefused as error:
        receipt = error.context["receipt"]
        assert receipt["decision"] == gate.REFUSE
        assert receipt["finding_code"] == error.code
        assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]
    else:  # pragma: no cover - the fitness above always refuses
        raise AssertionError("the gate should have refused")


def test_the_receipt_binds_the_sealed_evaluator_by_hash() -> None:
    from epistemic_foundry.verifier_firewall.firewall import VerifierFirewall

    arguments = gate_arguments()
    receipt = gate.evaluate_selective_admissibility(**arguments)
    firewall = VerifierFirewall(
        arguments["evaluator_bundle"],
        arguments["holdout_manifest"],
        holdout_read_principal_ids=arguments["holdout_read_principal_ids"],
    )
    assert receipt["evaluator_bundle_hash"] == firewall.sealed_hash
    assert (
        receipt["holdout_manifest_hash"]
        == arguments["holdout_manifest"]["manifest_hash"]
    )


def test_the_receipt_binds_the_statistical_record_by_hash() -> None:
    arguments = gate_arguments()
    receipt = gate.evaluate_selective_admissibility(**arguments)
    assert receipt["search_statistics_record_hash"] == sha256_hex(
        canonical_json(arguments["search_statistics"])
    )
    assert receipt["selective_report_hash"] == sha256_hex(
        canonical_json(arguments["selective_report"])
    )


def test_the_receipt_never_carries_hidden_holdout_content() -> None:
    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    text = repr(receipt)
    for handle in ("HID-Q05-1", "OOD-Q05-1", "ADV-Q05-1"):
        assert handle not in text


def test_the_gate_never_mutates_the_inputs_it_was_given() -> None:
    arguments = gate_arguments()
    snapshot = copy.deepcopy(arguments)
    gate.evaluate_selective_admissibility(**arguments)
    assert arguments == snapshot
