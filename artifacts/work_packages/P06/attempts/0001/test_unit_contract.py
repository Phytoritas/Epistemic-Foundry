"""Unit and contract behaviour of the P06 no-majority promotion referral gate.

The happy path refers a sealed candidate that cleared two independent organs,
preserved its dissent and carried a complete, passing, independent attestation
chain, and the receipt records every dimension it rested on.  These tests pin
that contract and the gate's authority boundary: it never promotes.
"""

from __future__ import annotations

import fixtures as f
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.parliament.v4_p06 import gate as p06


def test_a_fully_cleared_sealed_candidate_is_referred() -> None:
    receipt = p06.evaluate_promotion_referral(**f.referral_arguments())
    assert receipt["decision"] == p06.REFER
    assert receipt["referred_to_promotion_authority"] is True
    assert receipt["finding_code"] is None


def test_the_referral_records_all_four_independent_dimensions() -> None:
    """The decision rests on more than one source, and the receipt says so."""
    receipt = p06.derive_promotion_referral(**f.referral_arguments())
    assert receipt["dimensions_cleared"] == [
        p06.DIMENSION_ATTESTATION,
        p06.DIMENSION_PARLIAMENT,
        p06.DIMENSION_DISSENT,
        p06.DIMENSION_VALIDATION,
    ]


def test_the_receipt_binds_both_sealed_organ_receipts() -> None:
    args = f.referral_arguments()
    receipt = p06.derive_promotion_referral(**args)
    assert receipt["parliament_gate_id"] == args["parliament_receipt"]["gate_id"]
    assert (
        receipt["parliament_receipt_hash"] == args["parliament_receipt"]["receipt_hash"]
    )
    assert receipt["validation_gate_id"] == args["validation_receipt"]["gate_id"]
    assert (
        receipt["validation_receipt_hash"] == args["validation_receipt"]["receipt_hash"]
    )
    assert receipt["attestation_hash"] == args["attestation"]["attestation_hash"]


def test_the_referral_preserves_the_dockets_dissent() -> None:
    args = f.referral_arguments()
    receipt = p06.derive_promotion_referral(**args)
    assert (
        receipt["preserved_minority_report_ids"]
        == args["parliament_receipt"]["preserved_minority_report_ids"]
    )
    assert receipt["preserved_minority_report_ids"]


def test_the_ceiling_is_the_lower_of_the_two_organ_ceilings() -> None:
    parliament = f.low_ceiling_parliament_receipt()
    validation = f.validation_receipt()
    receipt = p06.derive_promotion_referral(
        **f.referral_arguments(
            requested_level="EMPIRICALLY_TESTED",
            parliament_receipt=parliament,
            validation_receipt=validation,
            attestation=f.attestation(parliament=parliament, validation=validation),
        )
    )
    assert receipt["parliament_ceiling"] == "EMPIRICALLY_TESTED"
    assert receipt["validation_ceiling"] == f.TOP_LEVEL
    assert receipt["promotion_ceiling"] == "EMPIRICALLY_TESTED"


def test_the_gate_never_grants_promotion() -> None:
    assert p06.gate_grants_promotion() is False
    receipt = p06.derive_promotion_referral(**f.referral_arguments())
    assert receipt["grants_promotion"] is False
    assert receipt["informs_gate_decision"] == p06.ATTESTATION_GATE


def test_evaluate_returns_the_receipt_on_refer() -> None:
    receipt = p06.evaluate_promotion_referral(**f.referral_arguments())
    assert receipt["gate"] == p06.GATE_NAME
    assert receipt["gate_id"].startswith(p06.GATE_ID_PREFIX)


def test_a_withheld_referral_still_produces_a_re_derivable_receipt() -> None:
    """A substantive withholding is auditable: it raises with the same receipt."""
    args = f.referral_arguments(attestation=f.failing_attestation())
    try:
        p06.evaluate_promotion_referral(**args)
    except p06.NoMajorityPromotionWithheld as error:
        receipt = error.context["receipt"]
        assert receipt["decision"] == p06.WITHHOLD
        assert receipt["finding_code"] == "ATTESTATION_NOT_PASS"
        assert receipt["referred_to_promotion_authority"] is False
        assert hash_excluding(dict(receipt), "receipt_hash") == receipt["receipt_hash"]
    else:  # pragma: no cover - the withholding must raise
        raise AssertionError("a withheld referral must raise")


def test_no_input_is_mutated() -> None:
    args = f.referral_arguments()
    import copy

    snapshot = copy.deepcopy(args)
    p06.derive_promotion_referral(**args)
    assert args == snapshot
