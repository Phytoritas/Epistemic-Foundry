"""The six A05 positive boundary controls: truthful lower states stay open."""

from __future__ import annotations

import pytest

from epistemic_foundry.governance.promotion import PromotionLevel
from epistemic_foundry.governance.promotion import (
    PromotionCommitter,
    decide_promotion,
)
from tests.test_integration_forge_cycle import (
    _candidate,
    _decision_and_effect,
    _promotion_gate_decisions,
    _promotion_request,
)


def test_a05_pos_001_inbox_truth_is_storable_without_higher_meaning() -> None:
    request = _promotion_request(
        requested_level=PromotionLevel.CANDIDATE,
        gate_decisions=_promotion_gate_decisions(
            not_required=(
                "G05_SEARCH_COVERAGE",
                "G08_ADAPTIVE_STATISTICS",
                "G09_RED_QUEEN",
                "G11_PARLIAMENT",
                "G12_INDEPENDENT_ATTESTATION",
            )
        ),
        parliament_adjudication_id=None,
        selective_inference_report_id=None,
        challenge_survived=False,
    )
    decision = decide_promotion(request)

    assert decision["decision"] == "PROMOTE"
    assert decision["granted_level"] == PromotionLevel.CANDIDATE
    assert decision["promotion_ceiling"] == PromotionLevel.REPLICATED


def test_a05_pos_002_policy_backed_not_required_approval_is_explicit() -> None:
    request = _promotion_request(
        human_approval_required=False,
        approval_record_ids=(),
        gate_decisions=_promotion_gate_decisions(
            not_required=("G12_INDEPENDENT_ATTESTATION", "G13_HUMAN_POLICY_APPROVAL")
        ),
    )
    decision = decide_promotion(request)

    assert decision["decision"] == "PROMOTE"
    assert decision["approval_record_ids"] == []
    g13 = next(
        gate
        for gate in request.gate_decisions
        if gate["name"] == "G13_HUMAN_POLICY_APPROVAL"
    )
    assert any("NOT_REQUIRED" in reason for reason in g13["reasons"])


def test_a05_pos_003_unreplicated_empirical_work_caps_at_empirically_tested() -> None:
    request = _promotion_request(
        current_level=PromotionLevel.CANDIDATE,
        requested_level=PromotionLevel.EMPIRICALLY_TESTED,
        attestation_id="ATT-1",
        replication_status="NOT_RUN",
        replication_result_ids=(),
    )
    decision = decide_promotion(request)

    assert decision["decision"] in {"CONDITIONAL", "UNDERDETERMINED"}
    assert decision["promotion_ceiling"] == PromotionLevel.EMPIRICALLY_TESTED
    assert decision["granted_level"] in (None, PromotionLevel.LITERATURE_GROUNDED)


def test_a05_pos_004_formal_equivalence_is_a_narrow_replication_exception() -> None:
    request = _promotion_request(
        current_level=PromotionLevel.EMPIRICALLY_TESTED,
        requested_level=PromotionLevel.REPLICATED,
        attestation_id="ATT-1",
        replication_status="FORMAL_EQUIVALENT",
    )
    decision = decide_promotion(request)

    assert decision["decision"] == "PROMOTE"
    assert decision["granted_level"] == PromotionLevel.REPLICATED


def test_a05_pos_005_full_evidence_promotion_commits_atomically() -> None:
    decision, effect = _decision_and_effect()
    result = PromotionCommitter().commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )

    assert decision["decision"] == "PROMOTE"
    assert result["state_changed"] is True
    assert result["candidate"]["revision"] == 2
    assert (
        result["candidate"]["promotion_history"][-1]["decision_id"]
        == (decision["decision_id"])
    )


def test_a05_pos_006_identical_retry_returns_the_same_logical_result() -> None:
    committer = PromotionCommitter()
    decision, effect = _decision_and_effect()
    first = committer.commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )
    replay = committer.commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )

    assert replay["replayed"] is True
    assert replay["decision_id"] == first["decision_id"]
    assert replay["request_hash"] == first["request_hash"]


@pytest.mark.parametrize(
    "level",
    [PromotionLevel.CANDIDATE, PromotionLevel.LITERATURE_GROUNDED],
)
def test_a05_pos_lower_levels_never_gain_attestation_meaning(level: str) -> None:
    request = _promotion_request(
        requested_level=level,
        gate_decisions=_promotion_gate_decisions(
            not_required=("G12_INDEPENDENT_ATTESTATION",)
        ),
    )
    decision = decide_promotion(request)

    assert decision["granted_level"] == level
    assert decision["attestation_id"] != "ATT-1"
