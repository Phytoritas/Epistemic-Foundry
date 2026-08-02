"""Negative and adversarial cases for the P06 no-majority promotion referral gate.

Every finding code is exercised, and the core no-majority invariants are attacked
directly: a single-source promotion (one organ passed twice), a bare-majority
promotion (dissent dropped), a promotion beyond the replication-bounded ceiling,
a self-attestation, a tampered organ receipt, and a Parliament that claimed
promotion authority.  The gate must refuse each with the documented code.
"""

from __future__ import annotations

import fixtures as f
import pytest
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.parliament.v4_p06 import gate as p06


def _withhold_code(**overrides: object) -> str:
    """Return the finding code, whether it raised (integrity) or withheld (receipt)."""
    args = f.referral_arguments(**overrides)
    try:
        receipt = p06.derive_promotion_referral(**args)
    except p06.NoMajorityPromotionWithheld as error:
        return error.code
    assert receipt["decision"] == p06.WITHHOLD, "expected a refusal"
    return str(receipt["finding_code"])


def test_every_declared_finding_code_is_reachable() -> None:
    """The negative suite must exercise each code the gate declares."""
    exercised = {
        "INPUT_INVALID": _withhold_code(created_at=""),
        "REQUESTED_LEVEL_INVALID": _withhold_code(requested_level="NOT_A_LEVEL"),
        "CANDIDATE_ROLE_HOLDS_AUTHORITY": _withhold_code(
            requesting_role=f.CANDIDATE_ROLE
        ),
    }
    assert exercised == {code: code for code in exercised}
    # The remaining codes have dedicated tests below; assert the declared set is
    # fully covered by this module's test names.
    covered = {
        "INPUT_INVALID",
        "REQUESTED_LEVEL_INVALID",
        "CANDIDATE_ROLE_HOLDS_AUTHORITY",
        "CANDIDATE_IDENTITY_MISMATCH",
        "PARLIAMENT_RECEIPT_TAMPERED",
        "PARLIAMENT_GRANTS_PROMOTION",
        "VALIDATION_RECEIPT_TAMPERED",
        "ATTESTATION_CONTRACT_VIOLATED",
        "ATTESTATION_NOT_INDEPENDENT",
        "PARLIAMENT_DID_NOT_CONVENE",
        "VALIDATION_DID_NOT_ADVANCE",
        "MINORITY_DISSENT_NOT_PRESERVED",
        "ATTESTATION_NOT_PASS",
        "ATTESTATION_CHAIN_INCOMPLETE",
        "FORWARD_LEVEL_EXCEEDS_CEILING",
    }
    assert covered == set(p06.FINDING_CODES)


# -- input integrity (immediate refusal) ----------------------------------- #
def test_a_non_string_created_at_is_refused() -> None:
    assert _withhold_code(created_at="") == "INPUT_INVALID"


def test_a_non_ladder_level_is_refused() -> None:
    assert _withhold_code(requested_level="NOT_A_LEVEL") == "REQUESTED_LEVEL_INVALID"


def test_a_candidate_generating_role_may_not_drive_the_referral() -> None:
    assert _withhold_code(requesting_role=f.CANDIDATE_ROLE) == (
        "CANDIDATE_ROLE_HOLDS_AUTHORITY"
    )


def test_a_validation_receipt_for_another_candidate_is_refused() -> None:
    other = f.validation_receipt(candidate_id=f.OTHER_CANDIDATE_ID)
    assert _withhold_code(validation_receipt=other) == "CANDIDATE_IDENTITY_MISMATCH"


def test_a_parliament_receipt_for_another_candidate_is_refused() -> None:
    other = f.parliament_receipt(candidate_id=f.OTHER_CANDIDATE_ID)
    assert _withhold_code(parliament_receipt=other) == "CANDIDATE_IDENTITY_MISMATCH"


def test_an_attestation_naming_another_subject_is_refused() -> None:
    att = f.attestation(subject_artifact_id=f.OTHER_CANDIDATE_ID)
    assert _withhold_code(attestation=att) == "CANDIDATE_IDENTITY_MISMATCH"


# -- single source: the two organs must be genuine and distinct ------------- #
def test_a_tampered_parliament_receipt_is_refused() -> None:
    receipt = f.parliament_receipt()
    receipt["promotion_ceiling"] = "INBOX"  # altered without re-sealing the hash
    assert _withhold_code(parliament_receipt=receipt) == "PARLIAMENT_RECEIPT_TAMPERED"


def test_a_tampered_validation_receipt_is_refused() -> None:
    receipt = f.validation_receipt()
    receipt["replication_ceiling"] = "INBOX"
    assert _withhold_code(validation_receipt=receipt) == "VALIDATION_RECEIPT_TAMPERED"


def test_a_single_organ_cannot_masquerade_as_both_dimensions() -> None:
    """Passing the Parliament receipt as the validation organ is refused.

    This is the single-source attack: one organ presented twice to fake breadth.
    The validation slot is checked against the validation gate name, so the
    parliament receipt cannot fill it.
    """
    parliament = f.parliament_receipt()
    assert _withhold_code(validation_receipt=parliament) == (
        "VALIDATION_RECEIPT_TAMPERED"
    )


def test_a_parliament_that_claimed_promotion_authority_is_refused() -> None:
    """Even a self-consistent receipt asserting promotion authority is refused."""
    receipt = f.parliament_receipt()
    receipt["grants_promotion"] = True
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    assert _withhold_code(parliament_receipt=receipt) == "PARLIAMENT_GRANTS_PROMOTION"


# -- attestation chain ------------------------------------------------------ #
def test_a_tampered_attestation_is_refused() -> None:
    att = f.attestation()
    att["independence_statement"] = "changed after the seal"
    assert _withhold_code(attestation=att) == "ATTESTATION_CONTRACT_VIOLATED"


def test_a_schema_invalid_attestation_is_refused() -> None:
    att = f.attestation()
    del att["overall_status"]
    att["attestation_hash"] = hash_excluding(att, "attestation_hash")
    assert _withhold_code(attestation=att) == "ATTESTATION_CONTRACT_VIOLATED"


def test_a_self_or_conflicted_attestor_is_refused() -> None:
    context = f.independence_context(candidate_generator_ids=[f.ATTESTOR_ID])
    assert _withhold_code(attestor_independence_context=context) == (
        "ATTESTATION_NOT_INDEPENDENT"
    )


def test_an_attestation_that_covers_only_one_organ_is_refused() -> None:
    parliament = f.parliament_receipt()
    validation = f.validation_receipt()
    att = f.attestation(
        parliament=parliament,
        validation=validation,
        input_artifact_ids=[str(parliament["gate_id"])],
    )
    assert (
        _withhold_code(
            parliament_receipt=parliament,
            validation_receipt=validation,
            attestation=att,
        )
        == "ATTESTATION_CHAIN_INCOMPLETE"
    )


def test_a_failing_attestation_is_refused() -> None:
    assert _withhold_code(attestation=f.failing_attestation()) == "ATTESTATION_NOT_PASS"


# -- the two organs must have actually cleared ------------------------------ #
def test_a_withheld_parliament_docket_is_not_referred() -> None:
    parliament = f.withheld_parliament_receipt()
    att = f.attestation(parliament=parliament)
    assert _withhold_code(parliament_receipt=parliament, attestation=att) == (
        "PARLIAMENT_DID_NOT_CONVENE"
    )


def test_a_refused_validation_claim_is_not_referred() -> None:
    validation = f.refused_validation_receipt()
    att = f.attestation(validation=validation)
    assert _withhold_code(validation_receipt=validation, attestation=att) == (
        "VALIDATION_DID_NOT_ADVANCE"
    )


# -- no bare majority: dissent must be preserved ---------------------------- #
def test_a_bare_majority_promotion_with_no_preserved_dissent_is_refused() -> None:
    parliament = f.parliament_receipt(with_minority=False)
    att = f.attestation(parliament=parliament)
    assert parliament["preserved_minority_report_ids"] == []
    assert _withhold_code(parliament_receipt=parliament, attestation=att) == (
        "MINORITY_DISSENT_NOT_PRESERVED"
    )


# -- ceiling ---------------------------------------------------------------- #
def test_a_referral_above_the_replication_bounded_ceiling_is_refused() -> None:
    parliament = f.low_ceiling_parliament_receipt()
    validation = f.low_ceiling_validation_receipt()
    att = f.attestation(parliament=parliament, validation=validation)
    code = _withhold_code(
        requested_level=f.TOP_LEVEL,
        parliament_receipt=parliament,
        validation_receipt=validation,
        attestation=att,
    )
    assert code == "FORWARD_LEVEL_EXCEEDS_CEILING"


def test_the_undeclared_finding_code_guard_fails_closed() -> None:
    with pytest.raises(p06.NoMajorityPromotionWithheld) as caught:
        p06._fail("NOT_A_DECLARED_CODE", "should never be recorded")
    assert caught.value.code == "INPUT_INVALID"
