"""Provenance and receipt audit for the O06 integration gate.

Every certificate and every decision must be a pure, re-derivable function of its
inputs: the ids and hashes recompute from the records' own published fields, two
runs over equal inputs are byte-equal, no input is mutated, and a refusal is as
auditable as an admission.  The gate's composition of the sealed Q05 receipt is
checked to be recorded by hash rather than by a copied hidden score.
"""

from __future__ import annotations

import copy

import fixtures as f
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.retrieval.v4_o06 import (
    ADMIT,
    CERTIFICATE_ID_PREFIX,
    GATE_ID_PREFIX,
    REFUSE,
    build_search_completeness_certificate,
    derive_search_integrity_admissibility,
)


def test_certificate_hash_rederives_from_its_own_fields() -> None:
    certificate = f.certificate()
    recomputed = hash_excluding(dict(certificate), "certificate_hash")
    assert certificate["certificate_hash"] == recomputed


def test_certificate_id_is_content_addressed() -> None:
    certificate = f.certificate()
    body = {
        key: value
        for key, value in certificate.items()
        if key not in {"certificate_id", "certificate_hash"}
    }
    expected = CERTIFICATE_ID_PREFIX + sha256_of_payload(body)[len("sha256:") :]
    assert certificate["certificate_id"] == expected


def test_gate_receipt_hash_rederives_from_its_own_fields() -> None:
    receipt = derive_search_integrity_admissibility(**f.gate_arguments())
    recomputed = hash_excluding(dict(receipt), "receipt_hash")
    assert receipt["receipt_hash"] == recomputed


def test_gate_id_is_derived_from_the_bound_evidence() -> None:
    receipt = derive_search_integrity_admissibility(**f.gate_arguments())
    expected = (
        GATE_ID_PREFIX
        + sha256_of_payload(
            {
                "candidate_id": receipt["candidate_id"],
                "certificate_hash": receipt["certificate_hash"],
                "created_at": receipt["created_at"],
                "decision": receipt["decision"],
                "novelty_assessment_id": receipt["novelty_assessment_id"],
                "subject_ref": receipt["subject_ref"],
            }
        )[len("sha256:") :]
    )
    assert receipt["gate_id"] == expected


def test_decisions_are_deterministic() -> None:
    first = derive_search_integrity_admissibility(**f.gate_arguments())
    second = derive_search_integrity_admissibility(**f.gate_arguments())
    assert first == second


def test_certificate_build_does_not_mutate_its_inputs() -> None:
    arguments = f.certificate_arguments()
    before = copy.deepcopy(arguments)
    build_search_completeness_certificate(**arguments)
    assert arguments == before


def test_gate_does_not_mutate_its_inputs() -> None:
    arguments = f.gate_arguments()
    before = copy.deepcopy(arguments)
    derive_search_integrity_admissibility(**arguments)
    assert arguments == before


def test_refusal_still_produces_an_auditable_receipt() -> None:
    """Over well-formed inputs a refusal is a receipt, not a bare exception."""
    pinned = f.snapshot()
    declared = f.plan(pinned)
    from epistemic_foundry.retrieval.v4_o05 import canonical_lane_order

    order = canonical_lane_order()
    receipts = f.receipts(declared, pinned)
    required = f.required_lanes()[0]
    receipts[order.index(required)] = f.failed_receipt(receipts[order.index(required)])
    certificate = build_search_completeness_certificate(
        plan=declared,
        receipts=receipts,
        work_class=f.WORK_CLASS,
        required_lanes=f.required_lanes(),
        subject_ref=f.SUBJECT_REF,
        generated_at=f.GENERATED_AT,
    )
    assessment = f.novelty_assessment(certificate["certificate_id"], pinned)
    receipt = derive_search_integrity_admissibility(
        **f.gate_arguments(certificate=certificate, novelty_assessment=assessment)
    )
    assert receipt["decision"] == REFUSE
    assert receipt["finding_code"] == "NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH"
    assert receipt["admissible_for_promotion_review"] is False
    assert receipt["receipt_hash"] == hash_excluding(dict(receipt), "receipt_hash")


def test_gate_records_the_sealed_admissibility_receipt_by_hash() -> None:
    """The composition is recorded by the Q05 receipt's own hash, not a score."""
    sealed = f.admissibility_receipt()
    receipt = derive_search_integrity_admissibility(
        **f.gate_arguments(admissibility_receipt=sealed)
    )
    assert receipt["admissibility_receipt_hash"] == sealed["receipt_hash"]
    assert receipt["decision"] == ADMIT


def test_receipt_holds_no_promotion_authority() -> None:
    """The gate forwards to review; the receipt grants no promotion of any kind."""
    receipt = derive_search_integrity_admissibility(**f.gate_arguments())
    # The only promotion-facing field is the boolean forward flag, and no field
    # carries a promotion decision, ladder rung or score.
    assert isinstance(receipt["admissible_for_promotion_review"], bool)
    for key, value in receipt.items():
        assert "promot" not in str(value).lower() or key == "message"
