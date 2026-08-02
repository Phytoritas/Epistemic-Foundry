"""negative_and_adversarial_tests — every refusal fires, and none can be evaded.

The gate exists to refuse the compositions no single sealed gate can see: a
candidate-generating role driving the decision, a sub-receipt of the wrong gate,
a tampered sub-receipt, a receipt describing a different candidate, a Parliament
receipt that claimed promotion authority, two downstream gates resting on
different statistical clearances, and each of the three sealed decisions failing
to clear.  Every finding code is exercised over a *genuine* sealed sub-receipt
wherever one exists, so the negative is a real refusal, not a forged shape.  The
adversarial cases prove the two ways a broken path is made to *look* clean —
re-sealing a tampered field, and swapping in a different-but-valid clearance —
are both refused.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.validation.v4_v06 import (
    FINDING_CODES,
    ExperimentReplicationRefused,
    evaluate_experiment_replication_integration as evaluate,
)
from fixtures import (
    CANDIDATE_ID,
    CANDIDATE_ROLE,
    CREATED_AT,
    GOVERNOR_ROLE,
    OTHER_CANDIDATE_ID,
    integration_arguments,
    p05_receipt,
    q05_receipt,
    v05_receipt,
)


def _reseal(receipt: dict) -> dict:
    """Re-derive a sub-receipt's own hash after mutating it — the forger's move."""
    receipt = dict(receipt)
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def _code(**arguments) -> str:
    """The finding code the *enforcing* entry point raises.

    ``evaluate`` raises on any non-integrated decision, so it covers both the
    input-integrity refusals (which ``derive`` also raises) and the substantive
    ones (which ``derive`` records on a REFUSE receipt), keeping the negative suite
    over one enforcement surface.
    """
    with pytest.raises(ExperimentReplicationRefused) as caught:
        evaluate(**arguments)
    return caught.value.code


# -- input integrity --------------------------------------------------------


def test_a_non_mapping_sub_receipt_is_refused() -> None:
    assert (
        _code(**integration_arguments(statistical_admissibility_receipt="not-a-map"))
        == "INPUT_INVALID"
    )


def test_a_blank_created_at_is_refused() -> None:
    assert _code(**integration_arguments(created_at="  ")) == "INPUT_INVALID"


def test_a_candidate_generating_role_may_not_drive_the_decision() -> None:
    assert (
        _code(**integration_arguments(requesting_role=CANDIDATE_ROLE))
        == "CANDIDATE_ROLE_HOLDS_AUTHORITY"
    )


# -- sub-receipt authenticity ----------------------------------------------


def test_a_sub_receipt_of_the_wrong_gate_is_refused() -> None:
    arguments = integration_arguments()
    impostor = dict(arguments["validation_advancement_receipt"])
    impostor["gate"] = "some-other-gate"
    arguments["validation_advancement_receipt"] = impostor
    assert _code(**arguments) == "SUBGATE_IDENTITY_MISMATCH"


def test_a_statistical_receipt_of_the_wrong_gate_is_refused() -> None:
    arguments = integration_arguments()
    impostor = dict(arguments["statistical_admissibility_receipt"])
    impostor["gate"] = "some-other-gate"
    arguments["statistical_admissibility_receipt"] = impostor
    assert _code(**arguments) == "SUBGATE_IDENTITY_MISMATCH"


def test_a_tampered_sub_receipt_is_refused() -> None:
    arguments = integration_arguments()
    tampered = dict(arguments["promotion_parliament_receipt"])
    tampered["message"] = "the docket was convened, honest"
    arguments["promotion_parliament_receipt"] = tampered
    assert _code(**arguments) == "SUBGATE_RECEIPT_TAMPERED"


def test_flipping_a_composed_decision_without_resealing_is_refused() -> None:
    """An adversary flips V05 to advanced without re-hashing: caught as tampered."""
    clearance = q05_receipt()
    refused = v05_receipt(admissibility_receipt=clearance, advance=False)
    refused = dict(refused)
    refused["advanced"] = True
    refused["decision"] = "ADVANCE"
    arguments = integration_arguments(
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=refused,
        promotion_parliament_receipt=p05_receipt(selective_admissibility=clearance),
    )
    assert _code(**arguments) == "SUBGATE_RECEIPT_TAMPERED"


# -- candidate binding ------------------------------------------------------


def test_a_statistical_receipt_for_a_different_candidate_is_refused() -> None:
    other = q05_receipt(candidate_id=OTHER_CANDIDATE_ID)
    assert (
        _code(**integration_arguments(statistical_admissibility_receipt=other))
        == "CANDIDATE_IDENTITY_MISMATCH"
    )


def test_a_validation_receipt_for_a_different_candidate_is_refused() -> None:
    other = v05_receipt(candidate_id=OTHER_CANDIDATE_ID)
    assert (
        _code(**integration_arguments(validation_advancement_receipt=other))
        == "CANDIDATE_IDENTITY_MISMATCH"
    )


# -- authority boundary -----------------------------------------------------


def test_a_parliament_receipt_that_claims_promotion_authority_is_refused() -> None:
    """A re-sealed grants_promotion=True passes tamper detection but not authority."""
    arguments = integration_arguments()
    claiming = dict(arguments["promotion_parliament_receipt"])
    claiming["grants_promotion"] = True
    arguments["promotion_parliament_receipt"] = _reseal(claiming)
    assert _code(**arguments) == "PARLIAMENT_HOLDS_PROMOTION_AUTHORITY"


# -- cross-receipt statistical consistency ----------------------------------


def test_a_different_but_valid_clearance_handed_to_the_gate_is_refused() -> None:
    """V05/P05 rest on one clearance; the gate is handed another, equally valid."""
    alternative = q05_receipt(suffix="ALT")
    assert (
        _code(**integration_arguments(statistical_admissibility_receipt=alternative))
        == "STATISTICAL_CLEARANCE_INCONSISTENT"
    )


def test_a_validation_receipt_resting_on_another_clearance_is_refused() -> None:
    handed = q05_receipt()
    other_clearance = q05_receipt(suffix="OTHER")
    arguments = integration_arguments(
        statistical_admissibility_receipt=handed,
        validation_advancement_receipt=v05_receipt(
            admissibility_receipt=other_clearance
        ),
        promotion_parliament_receipt=p05_receipt(selective_admissibility=handed),
    )
    assert _code(**arguments) == "STATISTICAL_CLEARANCE_INCONSISTENT"


# -- substantive refusals over genuine sealed sub-receipts ------------------


def test_a_refused_statistical_clearance_refuses_the_path() -> None:
    clearance = q05_receipt(admit=False)
    arguments = integration_arguments(
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=v05_receipt(admissibility_receipt=clearance),
        promotion_parliament_receipt=p05_receipt(selective_admissibility=clearance),
    )
    assert _code(**arguments) == "STATISTICAL_ADMISSIBILITY_REFUSED"


def test_a_refused_validation_advancement_refuses_the_path() -> None:
    clearance = q05_receipt()
    arguments = integration_arguments(
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=v05_receipt(
            admissibility_receipt=clearance, advance=False
        ),
        promotion_parliament_receipt=p05_receipt(selective_admissibility=clearance),
    )
    assert _code(**arguments) == "VALIDATION_ADVANCEMENT_REFUSED"


def test_a_withheld_promotion_docket_refuses_the_path() -> None:
    clearance = q05_receipt()
    arguments = integration_arguments(
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=v05_receipt(admissibility_receipt=clearance),
        promotion_parliament_receipt=p05_receipt(
            selective_admissibility=clearance, convene=False
        ),
    )
    assert _code(**arguments) == "PROMOTION_PARLIAMENT_WITHHELD"


# -- coverage: every declared finding code is exercised ---------------------


def test_every_declared_finding_code_is_exercised_by_this_suite() -> None:
    """No dead refusal: each declared code is provoked by a case above.

    A code that this gate can never reach would be documentation, not a decision,
    so this list is the same set as ``FINDING_CODES`` — a new code added to the
    gate without a negative test fails here.
    """
    exercised = {
        "INPUT_INVALID",
        "CANDIDATE_ROLE_HOLDS_AUTHORITY",
        "SUBGATE_IDENTITY_MISMATCH",
        "SUBGATE_RECEIPT_TAMPERED",
        "CANDIDATE_IDENTITY_MISMATCH",
        "PARLIAMENT_HOLDS_PROMOTION_AUTHORITY",
        "STATISTICAL_CLEARANCE_INCONSISTENT",
        "STATISTICAL_ADMISSIBILITY_REFUSED",
        "VALIDATION_ADVANCEMENT_REFUSED",
        "PROMOTION_PARLIAMENT_WITHHELD",
    }
    assert exercised == set(FINDING_CODES)


def test_created_at_and_role_are_still_bound_names() -> None:
    """Guard the fixtures the suite leans on stay the ones the gate reads."""
    assert CREATED_AT and GOVERNOR_ROLE and CANDIDATE_ID
