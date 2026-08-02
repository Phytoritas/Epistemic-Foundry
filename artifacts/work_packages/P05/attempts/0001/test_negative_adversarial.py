"""Negative and adversarial coverage for the P05 promotion-Parliament gate.

Every finding code the gate declares is exercised here, and a coverage test
fails if a new code is added without a case.  Integrity failures raise before any
receipt exists; substantive Parliament findings resolve to a WITHHOLD receipt
that ``evaluate_`` re-raises, so a caught refusal still carries its auditable
record.  The adversary the suite models is a candidate that would acquire
promotion on a partial docket: a dropped dissent, an unrun or refuted challenge,
an uncorrected statistic, or a role that should never hold authority.
"""

from __future__ import annotations

import fixtures as f
import pytest

from epistemic_foundry.parliament.v4_p05 import gate


def _tampered_adjudication() -> dict:
    record = f.adjudication()
    record["rationale"] = "changed after the hash was sealed"
    return record


def _tampered_minority() -> dict:
    report = f.minority_report()
    report["minority_claim"] = "changed after the hash was sealed"
    return report


def _tampered_clearance() -> dict:
    receipt = f.statistical_clearance()
    receipt["message"] = "changed after the hash was sealed"
    return receipt


#: code -> docket override that makes ``derive_`` raise before any receipt.
INTEGRITY_CASES: dict[str, dict] = {
    "INPUT_INVALID": {"candidate_id": ""},
    "REQUESTED_LEVEL_INVALID": {"requested_level": "NOT_A_CANONICAL_LEVEL"},
    "CANDIDATE_IDENTITY_MISMATCH": {"lineage": f.lineage(candidate_id="OTHER-CAND")},
    "LINEAGE_CONTRACT_VIOLATED": {"lineage": f.lineage(generation="not-an-integer")},
    "ADJUDICATION_CONTRACT_VIOLATED": {"adjudication": _tampered_adjudication()},
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": {"requesting_role": f.CANDIDATE_ROLE},
    "MINORITY_REPORT_CONTRACT_VIOLATED": {"minority_reports": [_tampered_minority()]},
    "STATISTICAL_CLEARANCE_CONTRACT_VIOLATED": {
        "selective_admissibility": _tampered_clearance()
    },
    "REPLICATION_RESULT_CONTRACT_VIOLATED": {
        "replication_results": [f.replication_result(status="NOT_A_STATUS")]
    },
}

#: code -> docket override that makes ``derive_`` return a WITHHOLD receipt.
DECISION_CASES: dict[str, dict] = {
    "PROMOTION_DIMENSION_MISSING": {"selective_admissibility": {}},
    "STATISTICAL_CLEARANCE_ABSENT": {
        "selective_admissibility": f.statistical_clearance(admit=False)
    },
    "PARLIAMENT_GATE_OVERRIDE": {
        "adjudication": f.adjudication(
            all_gates_pass=False,
            promotion_recommendation="CANDIDATE",
            refuse_override=False,
        )
    },
    "MINORITY_DISSENT_DROPPED": {
        "adjudication": f.adjudication(minority_report_ids=["MIN-NEVER-SUPPLIED"]),
        "minority_reports": [],
    },
    "RED_QUEEN_EVIDENCE_ABSENT": {"red_queen_results": []},
    "RED_QUEEN_REFUTED": {"red_queen_results": f.red_queen_results(outcome="REFUTED")},
    "RED_QUEEN_UNRESOLVED": {
        "red_queen_results": f.red_queen_results(outcome="INCONCLUSIVE")
    },
    "ADVERSARIAL_COVERAGE_INCOMPLETE": {
        "searched_adversarial_lanes": f.searched_adversarial_lanes()[:-1]
    },
    "REPLICATION_BLOCKED": {
        "replication_results": [
            f.replication_result(status="FAILED", promotion_effect="BLOCK")
        ]
    },
}


@pytest.mark.parametrize("code", sorted(INTEGRITY_CASES))
def test_integrity_failures_raise_with_their_code(code: str) -> None:
    with pytest.raises(gate.PromotionParliamentWithheld) as caught:
        gate.derive_promotion_parliament(**f.docket(**INTEGRITY_CASES[code]))
    assert caught.value.code == code


@pytest.mark.parametrize("code", sorted(DECISION_CASES))
def test_substantive_findings_withhold_with_their_code(code: str) -> None:
    receipt = gate.derive_promotion_parliament(**f.docket(**DECISION_CASES[code]))
    assert receipt["decision"] == gate.WITHHOLD
    assert receipt["finding_code"] == code
    assert receipt["convened_for_promotion_authority"] is False
    # ``evaluate_`` re-raises the same finding, still carrying the receipt.
    with pytest.raises(gate.PromotionParliamentWithheld) as caught:
        gate.evaluate_promotion_parliament(**f.docket(**DECISION_CASES[code]))
    assert caught.value.code == code
    assert caught.value.context["receipt"]["finding_code"] == code


def test_a_parliament_that_claims_binding_authority_is_refused(monkeypatch) -> None:
    """If the recommendation ever reported itself as authority, refuse.

    The composed surface documents ``recommendation_is_binding`` as always False;
    forcing it True proves the gate fails closed rather than trusting a Parliament
    that acquired promotion authority.
    """
    monkeypatch.setattr(gate, "recommendation_is_binding", lambda _: True)
    with pytest.raises(gate.PromotionParliamentWithheld) as caught:
        gate.derive_promotion_parliament(**f.docket())
    assert caught.value.code == "PARLIAMENT_RECOMMENDATION_NOT_AUTHORITY"


def test_a_searched_lane_outside_the_canonical_vocabulary_is_rejected() -> None:
    with pytest.raises(gate.PromotionParliamentWithheld) as caught:
        gate.derive_promotion_parliament(
            **f.docket(searched_adversarial_lanes=["not-a-declared-lane"])
        )
    assert caught.value.code == "INPUT_INVALID"


def test_a_candidate_generating_role_never_drives_the_decision() -> None:
    """No candidate/model/prompt/backend role acquires convening authority."""
    from epistemic_foundry.verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES

    for role in sorted(CANDIDATE_GENERATING_ROLES):
        with pytest.raises(gate.PromotionParliamentWithheld) as caught:
            gate.derive_promotion_parliament(**f.docket(requesting_role=role))
        assert caught.value.code == "CANDIDATE_ROLE_HOLDS_AUTHORITY"


def test_every_declared_finding_code_is_exercised() -> None:
    """No finding code may exist without a negative case proving it can fire."""
    exercised = (
        set(INTEGRITY_CASES)
        | set(DECISION_CASES)
        | {"PARLIAMENT_RECOMMENDATION_NOT_AUTHORITY"}
    )
    assert exercised == set(gate.FINDING_CODES), (
        f"uncovered finding codes: {sorted(set(gate.FINDING_CODES) - exercised)}"
    )
