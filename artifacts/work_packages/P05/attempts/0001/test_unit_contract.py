"""Unit and contract behaviour of the P05 promotion-Parliament gate.

These pin the convening decision on a complete, clean docket: the multi-
dimensional review it records, the dissent it preserves, the Red Queen evidence
it weighs, and the replication-bounded ceiling — and the load-bearing invariant
that convening is never itself promotion authority.
"""

from __future__ import annotations

import fixtures as f

from epistemic_foundry.parliament.v4_p05 import gate


def test_a_complete_clean_docket_is_convened() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    assert receipt["decision"] == gate.CONVENE
    assert receipt["finding_code"] is None
    assert receipt["convened_for_promotion_authority"] is True
    assert receipt["gate"] == gate.GATE_NAME
    assert receipt["gate_id"].startswith("EPP-")


def test_convening_is_never_promotion_authority() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    assert gate.parliament_grants_promotion() is False
    assert receipt["grants_promotion"] is False


def test_evaluate_returns_the_receipt_on_convene() -> None:
    receipt = gate.evaluate_promotion_parliament(**f.docket())
    assert receipt["decision"] == gate.CONVENE


def test_the_referenced_minority_dissent_is_preserved_in_the_receipt() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    assert receipt["preserved_minority_report_ids"] == ["MIN-P05-1"]
    assert receipt["dropped_minority_report_ids"] == []
    preserved = receipt["preserved_dissent"][0]
    assert preserved["minority_report_id"] == "MIN-P05-1"
    assert preserved["unresolved_test"]


def test_a_survived_red_queen_match_is_recorded() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    assert receipt["red_queen_challenged"] is True
    assert receipt["red_queen_survived"] is True
    assert receipt["red_queen_refuted"] == []
    assert receipt["adversarial_lanes_missing"] == []


def test_a_scope_restricted_challenge_is_kept_as_a_boundary_not_a_defeat() -> None:
    """A SCOPE_RESTRICTED outcome narrows scope; it does not withhold the docket."""
    receipt = gate.derive_promotion_parliament(
        **f.docket(red_queen_results=f.red_queen_results(outcome="SCOPE_RESTRICTED"))
    )
    # Not refuted, so still convened, but the boundary knowledge is preserved.
    assert receipt["red_queen_scope_restricted"] == [f.CANDIDATE_ID]


def test_the_ceiling_is_capped_at_what_replication_supports() -> None:
    """A high request with no qualifying replication is convened at a lower ceiling."""
    receipt = gate.derive_promotion_parliament(
        **f.docket(
            requested_level="REPLICATED",
            replication_plan=None,
            replication_results=[],
        )
    )
    assert receipt["decision"] == gate.CONVENE
    assert receipt["ceiling_lowered_by_replication"] is True
    assert receipt["promotion_ceiling"] == "EMPIRICALLY_TESTED"
    assert receipt["requested_level"] == "REPLICATED"


def test_a_qualifying_replication_plan_lifts_the_ceiling_to_the_request() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket(requested_level="REPLICATED"))
    assert receipt["ceiling_lowered_by_replication"] is False
    assert receipt["promotion_ceiling"] == "REPLICATED"


def test_the_receipt_records_the_promotion_gates_the_parliament_informs() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    assert receipt["informs_gate_decisions"] == [
        gate.STATISTICS_GATE,
        gate.RED_QUEEN_GATE,
        gate.REPLICATION_GATE,
        gate.PARLIAMENT_GATE,
    ]


def test_the_statistical_clearance_is_bound_by_its_receipt_hash() -> None:
    docket = f.docket()
    receipt = gate.derive_promotion_parliament(**docket)
    assert (
        receipt["statistical_receipt_hash"]
        == docket["selective_admissibility"]["receipt_hash"]
    )
    assert receipt["statistical_clearance_admitted"] is True
