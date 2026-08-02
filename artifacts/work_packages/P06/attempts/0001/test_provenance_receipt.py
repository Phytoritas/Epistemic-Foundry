"""Provenance and receipt discipline for the P06 referral gate.

Every decision, refer or withhold, resolves to one immutable receipt that is a
pure function of its inputs: no clock, no random draw, an id and hash that
re-derive byte for byte from the receipt's own published fields, and a record
that binds the content hashes of every organ and attestation it composed so a
tampered upstream decision cannot be laundered into it.
"""

from __future__ import annotations

import copy

import fixtures as f
from epistemic_foundry.domain.hashing import canonical_json, hash_excluding, sha256_hex
from epistemic_foundry.parliament.v4_p06 import gate as p06


def test_two_runs_over_equal_inputs_are_byte_equal() -> None:
    first = p06.derive_promotion_referral(**f.referral_arguments())
    second = p06.derive_promotion_referral(**f.referral_arguments())
    assert canonical_json(first) == canonical_json(second)


def test_a_withheld_decision_is_replay_stable() -> None:
    args = f.referral_arguments(attestation=f.failing_attestation())
    first = p06.derive_promotion_referral(**args)
    second = p06.derive_promotion_referral(
        **f.referral_arguments(attestation=f.failing_attestation())
    )
    assert canonical_json(first) == canonical_json(second)
    assert first["decision"] == p06.WITHHOLD


def test_the_receipt_hash_re_derives_from_the_receipt_body() -> None:
    receipt = p06.derive_promotion_referral(**f.referral_arguments())
    assert hash_excluding(dict(receipt), "receipt_hash") == receipt["receipt_hash"]


def test_the_gate_id_re_derives_from_the_published_fields() -> None:
    receipt = p06.derive_promotion_referral(**f.referral_arguments())
    expected = (
        p06.GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": receipt["candidate_id"],
                    "created_at": receipt["created_at"],
                    "decision": receipt["decision"],
                    "parliament_receipt_hash": receipt["parliament_receipt_hash"],
                    "validation_receipt_hash": receipt["validation_receipt_hash"],
                    "attestation_hash": receipt["attestation_hash"],
                    "requested_level": receipt["requested_level"],
                }
            )
        )[len("sha256:") :]
    )
    assert receipt["gate_id"] == expected


def test_a_different_created_at_changes_the_receipt() -> None:
    """The caller supplies the stamp; there is no clock inside the gate."""
    base = p06.derive_promotion_referral(**f.referral_arguments())
    later = p06.derive_promotion_referral(
        **f.referral_arguments(created_at="2027-01-01T00:00:00+00:00")
    )
    assert base["gate_id"] != later["gate_id"]
    assert base["receipt_hash"] != later["receipt_hash"]


def test_a_tampered_referral_receipt_is_detectable() -> None:
    receipt = p06.derive_promotion_referral(**f.referral_arguments())
    receipt["promotion_ceiling"] = "INBOX"
    assert hash_excluding(dict(receipt), "receipt_hash") != receipt["receipt_hash"]


def test_the_receipt_binds_the_content_hashes_it_composed() -> None:
    args = f.referral_arguments()
    receipt = p06.derive_promotion_referral(**args)
    assert (
        receipt["parliament_receipt_hash"] == args["parliament_receipt"]["receipt_hash"]
    )
    assert (
        receipt["validation_receipt_hash"] == args["validation_receipt"]["receipt_hash"]
    )
    assert receipt["attestation_hash"] == args["attestation"]["attestation_hash"]


def test_altering_a_composed_receipt_changes_the_referral_identity() -> None:
    """A different upstream decision yields a different, non-interchangeable id."""
    base = p06.derive_promotion_referral(**f.referral_arguments())
    low_parliament = f.low_ceiling_parliament_receipt()
    altered = p06.derive_promotion_referral(
        **f.referral_arguments(
            requested_level="EMPIRICALLY_TESTED",
            parliament_receipt=low_parliament,
            attestation=f.attestation(parliament=low_parliament),
        )
    )
    assert base["parliament_receipt_hash"] != altered["parliament_receipt_hash"]
    assert base["gate_id"] != altered["gate_id"]


def test_evaluate_and_derive_agree_on_the_referred_receipt() -> None:
    args = f.referral_arguments()
    derived = p06.derive_promotion_referral(**args)
    enforced = p06.evaluate_promotion_referral(**f.referral_arguments())
    assert canonical_json(derived) == canonical_json(enforced)


def test_inputs_are_not_mutated_by_derivation() -> None:
    args = f.referral_arguments()
    snapshot = copy.deepcopy(args)
    p06.derive_promotion_referral(**args)
    assert args == snapshot
