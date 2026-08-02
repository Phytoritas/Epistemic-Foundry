"""unit_and_contract_tests — the gate composes the three sealed receipts correctly.

These tests drive the happy path: a candidate whose Q05 clearance, V05 advancement
and P05 convening all cleared, all name the one candidate, and rest on the one
statistical clearance, is integrated into a single end-to-end record.  The
contract is that every field of that record is *derived* from the composed
receipts — their own decisions, their own hashes, their own gate ids — rather than
asserted by the caller, and that the gate advances no authority: it integrates a
cleared path and promotes nothing.
"""

from __future__ import annotations

from epistemic_foundry.validation.v4_v06 import (
    GATE_ID_PREFIX,
    GATE_NAME,
    INTEGRATE,
    ExperimentReplicationRefused,
    derive_experiment_replication_integration,
    evaluate_experiment_replication_integration,
    integration_grants_promotion,
    integration_hash_matches,
)
from fixtures import (
    CANDIDATE_ID,
    GOVERNOR_ROLE,
    integration_arguments,
    p05_receipt,
    q05_receipt,
    v05_receipt,
)


def test_a_clean_end_to_end_path_is_integrated() -> None:
    receipt = derive_experiment_replication_integration(**integration_arguments())
    assert receipt["decision"] == INTEGRATE
    assert receipt["integrated"] is True
    assert receipt["finding_code"] is None
    assert receipt["gate"] == GATE_NAME
    assert receipt["gate_id"].startswith(GATE_ID_PREFIX)
    assert receipt["candidate_id"] == CANDIDATE_ID
    assert receipt["requesting_role"] == GOVERNOR_ROLE


def test_the_receipt_binds_each_composed_sub_receipt_by_its_own_identity() -> None:
    arguments = integration_arguments()
    receipt = derive_experiment_replication_integration(**arguments)
    statistical = arguments["statistical_admissibility_receipt"]
    validation = arguments["validation_advancement_receipt"]
    parliament = arguments["promotion_parliament_receipt"]
    assert (
        receipt["statistical_admissibility_receipt_hash"] == statistical["receipt_hash"]
    )
    assert receipt["statistical_admissibility_gate_id"] == statistical["gate_id"]
    assert receipt["validation_advancement_receipt_hash"] == validation["receipt_hash"]
    assert receipt["validation_advancement_gate_id"] == validation["gate_id"]
    assert receipt["promotion_parliament_receipt_hash"] == parliament["receipt_hash"]
    assert receipt["promotion_parliament_gate_id"] == parliament["gate_id"]


def test_the_cleared_flags_are_read_from_the_composed_decisions() -> None:
    receipt = derive_experiment_replication_integration(**integration_arguments())
    assert receipt["statistical_admitted"] is True
    assert receipt["validation_advanced"] is True
    assert receipt["promotion_convened"] is True


def test_the_receipt_records_all_three_reconciled_concerns() -> None:
    receipt = derive_experiment_replication_integration(**integration_arguments())
    assert receipt["concerns_gated"] == sorted(
        (
            "statistical_admissibility",
            "validation_advancement",
            "promotion_parliament_convening",
        )
    )


def test_the_gate_holds_and_records_no_promotion_authority() -> None:
    receipt = derive_experiment_replication_integration(**integration_arguments())
    assert integration_grants_promotion() is False
    assert receipt["grants_promotion"] is False
    assert receipt["parliament_grants_promotion"] is False


def test_evaluate_returns_the_receipt_on_an_integrated_path() -> None:
    receipt = evaluate_experiment_replication_integration(**integration_arguments())
    assert receipt["decision"] == INTEGRATE
    assert integration_hash_matches(receipt) is True


def test_evaluate_raises_on_a_refused_path_carrying_the_receipt() -> None:
    clearance = q05_receipt(admit=False)
    arguments = dict(
        candidate_id=CANDIDATE_ID,
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=v05_receipt(admissibility_receipt=clearance),
        promotion_parliament_receipt=p05_receipt(selective_admissibility=clearance),
        requesting_role=GOVERNOR_ROLE,
        created_at="2026-08-02T00:00:00+00:00",
    )
    try:
        evaluate_experiment_replication_integration(**arguments)
    except ExperimentReplicationRefused as error:
        assert error.code == "STATISTICAL_ADMISSIBILITY_REFUSED"
        assert error.context["receipt"]["decision"] == "REFUSE"
        assert error.context["receipt"]["integrated"] is False
    else:  # pragma: no cover - the gate must refuse
        raise AssertionError("a refused path was integrated")


def test_the_message_and_finding_code_travel_together_on_refusal() -> None:
    clearance = q05_receipt()
    arguments = dict(
        candidate_id=CANDIDATE_ID,
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=v05_receipt(
            admissibility_receipt=clearance, advance=False
        ),
        promotion_parliament_receipt=p05_receipt(selective_admissibility=clearance),
        requesting_role=GOVERNOR_ROLE,
        created_at="2026-08-02T00:00:00+00:00",
    )
    receipt = derive_experiment_replication_integration(**arguments)
    assert receipt["decision"] == "REFUSE"
    assert receipt["finding_code"] == "VALIDATION_ADVANCEMENT_REFUSED"
    assert receipt["message"]
    assert receipt["validation_advanced"] is False
    # The prior link cleared, so the gate names the earliest broken one only.
    assert receipt["statistical_admitted"] is True
