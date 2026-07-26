"""EF4-I53: the adaptive-search statistical artifacts are required as a set."""

from __future__ import annotations

import pytest

from epistemic_foundry.statistics import (
    REQUIRED_ARTIFACTS,
    SearchStatisticsIncomplete,
    build_multiplicity_adjustment,
    build_search_statistics_record,
    build_selective_inference_report,
    build_sequential_ledger,
    missing_statistical_artifacts,
    require_search_statistics,
    search_permits_promotion,
)


def _look(spent: float, index: int) -> dict:
    return {
        "test_id": f"T-{index}",
        "generation": index,
        "statistic": 1.96,
        "threshold": 2.24,
        "spent": spent,
        "decision": "continue",
    }


def a_ledger(**overrides: object) -> dict:
    kwargs: dict = {
        "family_id": "FAM-1",
        "testing_policy": "alpha_spending",
        "initial_budget": 0.05,
        "entries": [_look(0.01, 1), _look(0.01, 2)],
        "selection_events": ["G5 top-decile cut"],
    }
    kwargs.update(overrides)
    return build_sequential_ledger(**kwargs)  # type: ignore[arg-type]


def an_adjustment(**overrides: object) -> dict:
    kwargs: dict = {
        "family_id": "FAM-1",
        "method": "BH_FDR",
        "raw_test_count": 40,
        "target_error_rate": 0.05,
        "adjusted_results": [
            {
                "test_id": "T-1",
                "raw_value": 0.001,
                "adjusted_value": 0.02,
                "decision": "reject_null",
            }
        ],
        "assumptions": ["tests are positively dependent within the family"],
    }
    kwargs.update(overrides)
    return build_multiplicity_adjustment(**kwargs)  # type: ignore[arg-type]


def a_report(**overrides: object) -> dict:
    kwargs: dict = {
        "candidate_id": "CAND-1",
        "selection_mechanism": "top-1 of Pareto front by combined score",
        "selection_events": ["G5 top-decile cut"],
        "naive_estimate": 0.42,
        "bias_corrected_estimate": 0.31,
        "correction_method": "conditional-likelihood shrinkage",
        "uncertainty_interval": [0.08, 0.54],
        "candidates_considered": 3,
        "replication_count": 1,
    }
    kwargs.update(overrides)
    return build_selective_inference_report(**kwargs)  # type: ignore[arg-type]


def a_record(**overrides: object) -> dict:
    kwargs: dict = {
        "evolution_run_id": "ERUN-1",
        "family_id": "FAM-1",
        "candidate_id": "CAND-1",
        "sequential_ledger": a_ledger(),
        "multiplicity_adjustment": an_adjustment(),
        "selective_report": a_report(),
        "hidden_exposure_log_id": "HEL-1",
        "candidate_lineage_id": "CL-1",
        "replication_result_id": "RR-1",
    }
    kwargs.update(overrides)
    return build_search_statistics_record(**kwargs)  # type: ignore[arg-type]


# -- EF4-I53 the set is required -----------------------------------------


def test_i53_every_required_artifact_is_named_by_the_spec() -> None:
    assert REQUIRED_ARTIFACTS == (
        "sequential_testing_ledger_id",
        "multiple_testing_adjustment_id",
        "selective_inference_report_id",
        "hidden_exposure_log_id",
        "candidate_lineage_id",
        "replication_result_id",
    )


def test_i53_a_complete_record_binds_all_five_artifacts() -> None:
    record = a_record()
    assert missing_statistical_artifacts(record) == []
    require_search_statistics(record)


@pytest.mark.parametrize(
    "field", ["hidden_exposure_log_id", "candidate_lineage_id", "replication_result_id"]
)
def test_i53_a_missing_artifact_is_refused_by_name(field: str) -> None:
    with pytest.raises(SearchStatisticsIncomplete) as excinfo:
        a_record(**{field: ""})
    assert field in str(excinfo.value)


def test_i53_an_empty_id_does_not_satisfy_key_presence() -> None:
    record = dict(a_record())
    record["candidate_lineage_id"] = "   "
    assert missing_statistical_artifacts(record) == ["candidate_lineage_id"]
    with pytest.raises(SearchStatisticsIncomplete):
        require_search_statistics(record)


# -- EF4-I53 the set must describe one family ----------------------------


def test_i53_ledger_for_another_family_is_refused() -> None:
    with pytest.raises(SearchStatisticsIncomplete) as excinfo:
        a_record(sequential_ledger=a_ledger(family_id="FAM-other"))
    assert "unrelated artifacts" in str(excinfo.value)


def test_i53_adjustment_for_another_family_is_refused() -> None:
    with pytest.raises(SearchStatisticsIncomplete) as excinfo:
        a_record(multiplicity_adjustment=an_adjustment(family_id="FAM-other"))
    assert "multiplicity adjustment covers family" in str(excinfo.value)


def test_i53_report_for_another_candidate_is_refused() -> None:
    with pytest.raises(SearchStatisticsIncomplete) as excinfo:
        a_record(selective_report=a_report(candidate_id="CAND-other"))
    assert "selective-inference report covers candidate" in str(excinfo.value)


def test_i53_every_mismatch_is_reported_together() -> None:
    with pytest.raises(SearchStatisticsIncomplete) as excinfo:
        a_record(
            sequential_ledger=a_ledger(family_id="FAM-x"),
            multiplicity_adjustment=an_adjustment(family_id="FAM-y"),
            selective_report=a_report(candidate_id="CAND-z"),
        )
    message = str(excinfo.value)
    assert message.count(";") == 2


def test_i53_correcting_for_fewer_tests_than_looks_is_refused() -> None:
    """An under-correction is the direction that produces false positives."""
    ledger = a_ledger(entries=[_look(0.005, index) for index in range(1, 6)])
    with pytest.raises(SearchStatisticsIncomplete) as excinfo:
        a_record(sequential_ledger=ledger, multiplicity_adjustment=an_adjustment(raw_test_count=2))
    assert "under-states the false-positive rate" in str(excinfo.value)


# -- EF4-I53 promotion consequences -------------------------------------


def test_i53_selection_events_are_carried_onto_the_record() -> None:
    assert a_record()["selection_events"] == ["G5 top-decile cut"]


def test_i53_a_complete_low_risk_record_permits_promotion() -> None:
    record = a_record()
    assert record["winner_curse_risk"] == "low"
    assert search_permits_promotion(record) is True


def test_i53_heavy_selection_without_replication_does_not_permit_promotion() -> None:
    record = a_record(
        selective_report=a_report(candidates_considered=120, replication_count=0)
    )
    assert record["promotion_recommendation"] == "BLOCK"
    assert search_permits_promotion(record) is False


def test_i53_an_incomplete_record_cannot_pass_on_a_copied_recommendation() -> None:
    """Completeness is checked before the recommendation is read."""
    record = dict(a_record())
    record["promotion_recommendation"] = "ALLOW"
    record["hidden_exposure_log_id"] = ""
    assert search_permits_promotion(record) is False
