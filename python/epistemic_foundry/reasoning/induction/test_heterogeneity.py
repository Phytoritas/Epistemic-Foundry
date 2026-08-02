"""heterogeneity_test — heterogeneity statistics and moderator retention.

Exit criterion under test: "moderators and nulls retained".  Every moderator
and level observed survives into the output whether or not it discriminates,
because an absent moderator is indistinguishable from one never examined.  The
heterogeneity statistics are checked against hand-computed values so a silent
change in the estimator cannot pass.
"""

from __future__ import annotations

import math

import pytest

from .contracts import (
    MINIMUM_QUANTITATIVE_FINDINGS,
    Direction,
    Heterogeneity,
    InductiveSynthesisError,
    ModeratorStatus,
    heterogeneity_report,
    moderator_report,
    validate_synthesis,
)
from .test_induction_fixture import (
    CREATED_AT,
    default_findings,
    finding,
    sealed_pack,
)


def quantitative(evidence_id: str, effect: float, error: float, **kwargs):
    return finding(
        evidence_id,
        Direction.POSITIVE.value if effect > 0 else Direction.NEGATIVE.value,
        effect_size=effect,
        standard_error=error,
        **kwargs,
    )


def test_identical_effects_have_no_excess_heterogeneity() -> None:
    findings = [
        quantitative("EVN-0001", 0.5, 0.1),
        quantitative("EVN-0002", 0.5, 0.1),
        quantitative("EVN-0003", 0.5, 0.1),
    ]

    report = heterogeneity_report(findings, {})

    assert report["q_statistic"] == 0.0
    assert report["i_squared"] == 0.0
    assert report["tau_squared"] == 0.0
    assert report["classification"] == Heterogeneity.LOW.value
    assert report["pooled_effect"] == 0.5
    assert report["degrees_of_freedom"] == 2
    assert report["reason"] is None


def test_q_i_squared_and_tau_match_the_hand_computation() -> None:
    findings = [
        quantitative("EVN-0001", 0.0, 1.0),
        quantitative("EVN-0002", 2.0, 1.0),
    ]

    report = heterogeneity_report(findings, {})

    # w = 1 each, pooled = 1.0, Q = 1*(0-1)^2 + 1*(2-1)^2 = 2, df = 1.
    assert report["pooled_effect"] == 1.0
    assert report["q_statistic"] == 2.0
    assert report["degrees_of_freedom"] == 1
    assert report["i_squared"] == pytest.approx(0.5)
    # tau2 = (Q - df) / (sum(w) - sum(w^2)/sum(w)) = 1 / (2 - 2/2) = 1.0
    assert report["tau_squared"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("spread", "expected"),
    [
        (0.0, Heterogeneity.LOW.value),
        (0.9, Heterogeneity.MODERATE.value),
        (1.2, Heterogeneity.SUBSTANTIAL.value),
        (3.0, Heterogeneity.CONSIDERABLE.value),
    ],
)
def test_the_cochrane_bands_partition_the_i_squared_range(
    spread: float, expected: str
) -> None:
    findings = [
        quantitative("EVN-0001", -spread, 1.0),
        quantitative("EVN-0002", spread, 1.0),
    ]

    report = heterogeneity_report(findings, {})

    assert report["classification"] == expected


def test_a_band_boundary_falls_into_the_more_cautious_band() -> None:
    """I-squared exactly 0.5 is SUBSTANTIAL, not MODERATE.

    The published bands overlap; the implementation partitions the range with
    a strict upper bound so a boundary value is never rounded downward into a
    more reassuring classification.
    """

    findings = [
        quantitative("EVN-0001", -1.0, 1.0),
        quantitative("EVN-0002", 1.0, 1.0),
    ]

    report = heterogeneity_report(findings, {})

    assert report["i_squared"] == pytest.approx(0.5)
    assert report["classification"] == Heterogeneity.SUBSTANTIAL.value


def test_dependent_replications_cannot_inflate_precision() -> None:
    findings = [
        quantitative("EVN-0001", 0.0, 1.0),
        quantitative("EVN-0002", 2.0, 1.0),
    ]

    unweighted = heterogeneity_report(findings, {})
    halved = heterogeneity_report(findings, {"EVN-0001": 0.5, "EVN-0002": 0.5})

    # Halving both independence weights halves Q: the same disagreement is
    # observed, but with half the effective information behind it.
    assert unweighted["q_statistic"] == 2.0
    assert halved["q_statistic"] == 1.0
    assert halved["pooled_effect"] == unweighted["pooled_effect"]
    assert halved["i_squared"] == 0.0
    assert halved["classification"] == Heterogeneity.LOW.value


def test_one_quantitative_finding_is_undetermined_not_low() -> None:
    report = heterogeneity_report([quantitative("EVN-0001", 0.5, 0.1)], {})

    assert MINIMUM_QUANTITATIVE_FINDINGS == 2
    assert report["classification"] == Heterogeneity.UNDETERMINED.value
    assert report["reason"] == "fewer than two quantitative findings"
    assert report["i_squared"] is None
    assert report["q_statistic"] is None
    assert report["tau_squared"] is None
    assert report["pooled_effect"] is None


def test_purely_qualitative_findings_are_undetermined() -> None:
    report = heterogeneity_report(
        [
            finding("EVN-0001", Direction.POSITIVE.value),
            finding("EVN-0002", Direction.NEGATIVE.value),
        ],
        {},
    )

    assert report["classification"] == Heterogeneity.UNDETERMINED.value
    assert report["quantitative_finding_count"] == 0
    assert report["included_evidence_ids"] == []


def test_a_zero_independence_weight_is_undetermined_rather_than_infinite() -> None:
    findings = [
        quantitative("EVN-0001", 0.0, 1.0),
        quantitative("EVN-0002", 2.0, 1.0),
    ]

    report = heterogeneity_report(findings, {"EVN-0001": 0.0})

    assert report["classification"] == Heterogeneity.UNDETERMINED.value
    assert report["reason"] == "a finding carries no positive independence weight"


def test_included_evidence_is_reported_so_exclusions_are_visible() -> None:
    findings = [
        quantitative("EVN-0001", 0.5, 0.1),
        quantitative("EVN-0002", 0.7, 0.1),
        finding("EVN-0401", Direction.UNKNOWN.value),
    ]

    report = heterogeneity_report(findings, {})

    assert report["included_evidence_ids"] == ["EVN-0001", "EVN-0002"]
    assert report["quantitative_finding_count"] == 2


def test_the_statistics_are_finite_and_reproducible() -> None:
    findings = [
        quantitative("EVN-0001", 0.31234567891, 0.0917),
        quantitative("EVN-0002", -0.7654321, 0.1234),
        quantitative("EVN-0003", 0.05, 0.2),
    ]

    first = heterogeneity_report(findings, {"EVN-0001": 0.5})
    second = heterogeneity_report(findings, {"EVN-0001": 0.5})

    assert first == second
    for key in ("q_statistic", "i_squared", "tau_squared", "pooled_effect"):
        assert math.isfinite(float(first[key]))


def test_a_moderator_whose_levels_agree_is_kept_not_pruned() -> None:
    findings = [
        finding(
            "EVN-0001",
            Direction.POSITIVE.value,
            moderator_levels={"population": "adult"},
        ),
        finding(
            "EVN-0002",
            Direction.POSITIVE.value,
            moderator_levels={"population": "child"},
        ),
    ]

    report = moderator_report(findings, {})

    assert [entry["moderator"] for entry in report] == ["population"]
    assert report[0]["status"] == ModeratorStatus.NOT_DISCRIMINATING.value
    assert [level["level"] for level in report[0]["levels"]] == ["adult", "child"]


def test_a_moderator_whose_levels_disagree_is_a_candidate() -> None:
    findings = [
        finding(
            "EVN-0001",
            Direction.POSITIVE.value,
            moderator_levels={"population": "adult"},
        ),
        finding(
            "EVN-0002",
            Direction.NEGATIVE.value,
            moderator_levels={"population": "child"},
        ),
    ]

    report = moderator_report(findings, {})

    assert report[0]["status"] == ModeratorStatus.CANDIDATE.value
    assert report[0]["distinct_dominant_direction_count"] == 2
    assert [level["dominant_direction"] for level in report[0]["levels"]] == [
        Direction.POSITIVE.value,
        Direction.NEGATIVE.value,
    ]


def test_a_single_level_moderator_is_underdetermined_not_dismissed() -> None:
    findings = [
        finding(
            "EVN-0001", Direction.POSITIVE.value, moderator_levels={"assay": "elisa"}
        ),
        finding(
            "EVN-0002", Direction.POSITIVE.value, moderator_levels={"assay": "elisa"}
        ),
    ]

    report = moderator_report(findings, {})

    assert report[0]["status"] == ModeratorStatus.UNDERDETERMINED.value
    assert report[0]["levels"][0]["evidence_ids"] == ["EVN-0001", "EVN-0002"]


def test_moderator_strata_are_independence_weighted() -> None:
    findings = [
        finding(
            "EVN-0001", Direction.POSITIVE.value, moderator_levels={"site": "north"}
        ),
        finding(
            "EVN-0002", Direction.POSITIVE.value, moderator_levels={"site": "north"}
        ),
        finding(
            "EVN-0003", Direction.POSITIVE.value, moderator_levels={"site": "south"}
        ),
    ]

    report = moderator_report(findings, {"EVN-0001": 0.5, "EVN-0002": 0.5})
    levels = {level["level"]: level for level in report[0]["levels"]}

    assert levels["north"]["adjusted_weight"] == 1.0
    assert levels["south"]["adjusted_weight"] == 1.0
    assert levels["north"]["evidence_ids"] == ["EVN-0001", "EVN-0002"]


def test_a_null_stratum_is_never_absorbed_into_its_neighbours() -> None:
    findings = [
        finding(
            "EVN-0001", Direction.POSITIVE.value, moderator_levels={"dose": "high"}
        ),
        finding("EVN-0002", Direction.NULL.value, moderator_levels={"dose": "low"}),
    ]

    report = moderator_report(findings, {})
    levels = {level["level"]: level for level in report[0]["levels"]}

    assert levels["low"]["dominant_direction"] == Direction.NULL.value
    assert levels["low"]["direction_summary"][Direction.NULL.value]["raw_count"] == 1.0
    assert report[0]["status"] == ModeratorStatus.CANDIDATE.value


def test_every_moderator_in_the_input_survives_the_full_synthesis() -> None:
    pack, clusters = sealed_pack()
    findings = default_findings()
    moderators = {
        "EVN-0001": {"population": "adult", "assay": "elisa"},
        "EVN-0002": {"population": "adult", "assay": "pcr"},
        "EVN-0003": {"population": "child", "assay": "elisa"},
        "EVN-0101": {"population": "child"},
        "EVN-0201": {"assay": "pcr"},
        "EVN-0301": {"site": "north"},
    }
    for row in findings:
        row["moderator_levels"] = moderators.get(str(row["evidence_id"]), {})

    from .contracts import synthesize

    payload = synthesize(pack, clusters, findings, created_at=CREATED_AT).payload

    assert [entry["moderator"] for entry in payload["moderators"]] == [
        "assay",
        "population",
        "site",
    ]
    observed_levels = {
        entry["moderator"]: sorted(level["level"] for level in entry["levels"])
        for entry in payload["moderators"]
    }
    assert observed_levels == {
        "assay": ["elisa", "pcr"],
        "population": ["adult", "child"],
        "site": ["north"],
    }


def test_stripping_a_moderator_level_from_a_sealed_synthesis_fails_closed() -> None:
    from .contracts import _hash_excluding, _synthesis_id, synthesize

    pack, clusters = sealed_pack()
    findings = default_findings()
    findings[0]["moderator_levels"] = {"population": "adult"}
    findings[1]["moderator_levels"] = {"population": "child"}
    payload = synthesize(pack, clusters, findings, created_at=CREATED_AT).payload
    payload["moderators"][0]["levels"] = []
    payload["synthesis_id"] = _synthesis_id(payload)
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "MODERATOR_LEVEL_DROPPED"


def test_an_undetermined_heterogeneity_must_state_why() -> None:
    from .contracts import _hash_excluding, _synthesis_id, synthesize

    pack, clusters = sealed_pack()
    findings = [
        finding(str(row["evidence_id"]), str(row["direction"]))
        for row in default_findings()
    ]
    payload = synthesize(pack, clusters, findings, created_at=CREATED_AT).payload
    assert (
        payload["heterogeneity"]["classification"] == Heterogeneity.UNDETERMINED.value
    )

    payload["heterogeneity"]["reason"] = None
    payload["synthesis_id"] = _synthesis_id(payload)
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "HETEROGENEITY_UNEXPLAINED"
