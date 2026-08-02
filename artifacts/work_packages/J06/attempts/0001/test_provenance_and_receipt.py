"""provenance_and_receipt_audit — every admission is a self-proving receipt.

Nothing in J06 scores, selects or promotes; what it must instead prove is that
each receipt it emits re-derives byte for byte from the fields it publishes, that
replaying the same identified admission reproduces the identical receipt — the
property a crash/resume relies on, since re-deriving from canonical inputs after
an interruption must land on the same decision — and that the inputs it was
handed are never mutated in the process.  On the identified path there is no
clock and no random draw, so determinism here is a property of the gate rather
than of the environment it ran in.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.operators.v4_j06 import (
    admit_operator_application,
    assess_context_budget,
    verify_gate_receipt,
)
from fixtures import (
    admission_arguments,
    budget_envelope,
    context_manifest,
    hypothesis_admission_arguments,
)

# --- each receipt re-derives its own digest ------------------------------


def test_the_receipt_hash_covers_the_receipt() -> None:
    receipt = admit_operator_application(**admission_arguments())

    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")
    assert verify_gate_receipt(receipt) == receipt["receipt_hash"]


def test_the_non_prompt_receipt_hash_covers_the_receipt() -> None:
    receipt = admit_operator_application(**hypothesis_admission_arguments())

    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")
    assert verify_gate_receipt(receipt) == receipt["receipt_hash"]


# --- an identified admission replays byte for byte (crash/resume) ---------


def test_an_identified_admission_replays_byte_for_byte() -> None:
    first = admit_operator_application(**admission_arguments())
    second = admit_operator_application(**admission_arguments())

    assert first == second
    assert first["receipt_hash"] == second["receipt_hash"]


def test_the_context_budget_assessment_replays_byte_for_byte() -> None:
    first = assess_context_budget(
        context_manifest=context_manifest(), budget_envelope=budget_envelope()
    )
    second = assess_context_budget(
        context_manifest=context_manifest(), budget_envelope=budget_envelope()
    )

    assert first == second


def test_resuming_a_gate_decision_reaches_the_same_verdict() -> None:
    # A resume re-derives the decision from the same canonical inputs; the receipt
    # it lands on must be identical to the one produced before the interruption.
    before = admit_operator_application(**admission_arguments())
    resumed = admit_operator_application(**admission_arguments())

    assert verify_gate_receipt(resumed) == before["receipt_hash"]


# --- the receipt names its own provenance --------------------------------


def test_the_receipt_names_the_operator_record_by_hash() -> None:
    args = admission_arguments()
    record = args["registry"].record(args["operator_id"])

    receipt = admit_operator_application(**args)

    assert receipt["operator_record_hash"] == record["record_hash"]


def test_the_receipt_names_its_budget_and_manifest_provenance() -> None:
    args = admission_arguments()
    envelope = args["budget_envelope"]
    manifest = args["context_manifest"]

    receipt = admit_operator_application(**args)
    assessment = receipt["budget_assessment"]

    assert assessment["budget_hash"] == envelope["budget_hash"]
    assert assessment["context_hash"] == manifest["context_hash"]


# --- inputs are never mutated --------------------------------------------


def test_admission_never_mutates_the_inputs_it_was_given() -> None:
    manifest = context_manifest()
    envelope = budget_envelope()
    evidence = ["QUAL-J06-1", "QUAL-J06-2"]
    before = (
        copy.deepcopy(manifest),
        copy.deepcopy(envelope),
        copy.deepcopy(evidence),
    )

    admit_operator_application(
        **admission_arguments(
            context_manifest=manifest,
            budget_envelope=envelope,
            qualification_evidence_ids=evidence,
        )
    )

    assert (manifest, envelope, evidence) == before


def test_the_budget_check_never_mutates_the_documents_it_was_given() -> None:
    manifest = context_manifest()
    envelope = budget_envelope()
    before = (copy.deepcopy(manifest), copy.deepcopy(envelope))

    assess_context_budget(context_manifest=manifest, budget_envelope=envelope)

    assert (manifest, envelope) == before


def test_the_gate_grants_no_evaluator_holdout_or_promotion_authority() -> None:
    # The receipt is a qualification-and-budget decision; it carries no field that
    # would let a candidate, prompt or backend acquire judging authority.
    receipt = admit_operator_application(**admission_arguments())
    keys = " ".join(receipt).lower()
    for word in ("evaluator", "holdout", "promotion", "score", "fitness"):
        assert word not in keys
