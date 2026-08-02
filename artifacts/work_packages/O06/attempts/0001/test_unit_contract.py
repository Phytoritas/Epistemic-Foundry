"""Unit and contract behaviour for the O06 integration gate.

The certificate reconciliation is exercised across every completion branch it
derives, the claim ceilings are checked against the completion they follow from,
and the gate is checked to admit a complete, statistically-cleared claim while
composing — never restating — the sealed O05, K05 and Q05 surfaces.
"""

from __future__ import annotations

import fixtures as f
import pytest
from epistemic_foundry.retrieval.v4_o05 import canonical_lane_order
from epistemic_foundry.retrieval.v4_o06 import (
    ADMIT,
    REFUSE,
    SearchIntegrityRefused,
    build_search_completeness_certificate,
    certificate_earns_novelty,
    derive_search_integrity_admissibility,
    evaluate_search_integrity_admissibility,
    require_certificate_identity,
)


def _certificate_with(kind) -> dict:
    """A certificate whose first required lane carries a degraded receipt."""
    pinned = f.snapshot()
    declared = f.plan(pinned)
    order = canonical_lane_order()
    receipts = f.receipts(declared, pinned)
    required = f.required_lanes()[0]
    receipts[order.index(required)] = kind(receipts[order.index(required)])
    return build_search_completeness_certificate(
        plan=declared,
        receipts=receipts,
        work_class=f.WORK_CLASS,
        required_lanes=f.required_lanes(),
        subject_ref=f.SUBJECT_REF,
        generated_at=f.GENERATED_AT,
    )


def test_happy_path_certificate_reconciles_to_pass() -> None:
    certificate = f.certificate()
    assert certificate["completion_state"] == "PASS"
    assert set(certificate["required_lanes"]) == set(f.required_lanes())
    assert set(certificate["completed_lanes"]) >= set(f.required_lanes())
    assert certificate["failed_lanes"] == []
    assert certificate["known_failures"] == []


def test_certificate_is_deterministic_over_equal_inputs() -> None:
    assert f.certificate()["certificate_hash"] == f.certificate()["certificate_hash"]
    assert f.certificate()["certificate_id"] == f.certificate()["certificate_id"]


def test_certificate_ceilings_follow_completion_and_coverage() -> None:
    """A complete run with unsearched external scope earns only a conditional claim."""
    certificate = f.certificate()
    assert certificate["novelty_claim_ceiling"] == "SEARCH_CONDITIONAL"
    assert certificate["absence_claim_ceiling"] == "CORPUS_CONDITIONAL"
    assert certificate_earns_novelty(certificate) is True


def test_partial_receipt_drives_partial_completion() -> None:
    certificate = _certificate_with(f.partial_receipt)
    assert certificate["completion_state"] == "PARTIAL"
    assert certificate["novelty_claim_ceiling"] == "NOT_ASSESSED"
    assert certificate["absence_claim_ceiling"] == "NONE"
    assert certificate_earns_novelty(certificate) is False


def test_blocked_receipt_drives_blocked_completion() -> None:
    certificate = _certificate_with(f.blocked_receipt)
    assert certificate["completion_state"] == "BLOCKED"
    assert certificate["blocked_lanes"]
    assert certificate["known_failures"]
    assert certificate_earns_novelty(certificate) is False


def test_failed_receipt_drives_failed_completion() -> None:
    certificate = _certificate_with(f.failed_receipt)
    assert certificate["completion_state"] == "FAIL"
    assert certificate["failed_lanes"]
    assert certificate_earns_novelty(certificate) is False


def test_certificate_reconciled_states_are_the_receipts_own_states() -> None:
    """The reconciliation relabels no lane; each reconciled state is its receipt's."""
    certificate = f.certificate()
    by_lane = {row["lane"]: row for row in certificate["lane_reconciliations"]}
    selected = set(f.plan()["selected_lanes"])
    for lane, row in by_lane.items():
        assert row["selected"] is (lane in selected)
        if lane in selected:
            assert row["reconciled_state"] != "UNSEARCHED"
            assert row["executed_scope_ids"] == certificate["searched_scope"]
        else:
            assert row["reconciled_state"] == "UNSEARCHED"
            assert row["executed_scope_ids"] == []
            assert row["unsearched_scope_ids"]


def test_certificate_rederives_its_own_identity() -> None:
    certificate = f.certificate()
    assert require_certificate_identity(certificate) == certificate


def test_gate_admits_a_complete_and_cleared_claim() -> None:
    receipt = evaluate_search_integrity_admissibility(**f.gate_arguments())
    assert receipt["decision"] == ADMIT
    assert receipt["admissible_for_promotion_review"] is True
    assert receipt["finding_code"] is None
    assert receipt["novelty_claim_stated"] is True


def test_gate_forwards_but_never_promotes() -> None:
    """The gate forwards to review; it holds and grants no promotion authority."""
    receipt = evaluate_search_integrity_admissibility(**f.gate_arguments())
    assert "admissible_for_promotion_review" in receipt
    assert "promotion" not in receipt.get("decision", "").lower()
    # The forwarded claim carries the sealed Q05 receipt hash, not a hidden score.
    assert receipt["admissibility_receipt_hash"].startswith("sha256:")


def test_gate_refusal_carries_the_receipt_and_code() -> None:
    with pytest.raises(SearchIntegrityRefused) as excinfo:
        evaluate_search_integrity_admissibility(**f.gate_arguments(certificate=None))
    assert excinfo.value.code == "CERTIFICATE_MISSING"


def test_gate_over_incomplete_certificate_refuses_novelty_claim() -> None:
    pinned = f.snapshot()
    certificate = _certificate_with(f.failed_receipt)
    assessment = f.novelty_assessment(certificate["certificate_id"], pinned)
    receipt = derive_search_integrity_admissibility(
        **f.gate_arguments(certificate=certificate, novelty_assessment=assessment)
    )
    assert receipt["decision"] == REFUSE
    assert receipt["finding_code"] == "NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH"


def test_evaluate_and_derive_agree_on_admit() -> None:
    derived = derive_search_integrity_admissibility(**f.gate_arguments())
    enforced = evaluate_search_integrity_admissibility(**f.gate_arguments())
    assert derived["receipt_hash"] == enforced["receipt_hash"]
