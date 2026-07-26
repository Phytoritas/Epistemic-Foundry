"""EF4-I46: eight novelty layers stay separate, and none of them is support."""

from __future__ import annotations

import pytest

from epistemic_foundry.evaluation.novelty_layers import (
    NOVELTY_LAYERS,
    NoveltyVectorRefused,
    build_novelty_vector,
    failed_novelty_vector,
    novel_layers,
    novelty_is_claimable,
    novelty_supports_promotion,
)

FULL = {layer: 0.5 for layer in NOVELTY_LAYERS}


def a_vector(**overrides: object) -> dict:
    kwargs: dict = {
        "candidate_id": "CAND-001",
        "dimensions": dict(FULL),
        "nearest_candidate_ids": ["CAND-000"],
        "external_search_certificate_id": "SCC-001",
        "uncertainties": [],
        "external_search_completed": True,
    }
    kwargs.update(overrides)
    return build_novelty_vector(**kwargs)  # type: ignore[arg-type]


# -- EF4-I46 the eight layers stay separate ------------------------------


def test_i46_all_eight_layers_are_named_by_the_invariant() -> None:
    assert NOVELTY_LAYERS == (
        "claim_semantic",
        "mechanism_topology",
        "prediction_signature",
        "falsifier_signature",
        "scope_shift",
        "experiment_design",
        "evidence_basis",
        "external_prior_art",
    )


@pytest.mark.parametrize("dropped", NOVELTY_LAYERS)
def test_i46_an_omitted_layer_is_refused(dropped: str) -> None:
    """An absent layer would read as either zero or full novelty; it is neither."""
    dimensions = {layer: 0.5 for layer in NOVELTY_LAYERS if layer != dropped}
    with pytest.raises(NoveltyVectorRefused) as excinfo:
        a_vector(dimensions=dimensions)
    assert dropped in str(excinfo.value)


def test_i46_there_is_no_aggregate_novelty_field() -> None:
    """A single scalar would let one novel layer carry the other seven."""
    vector = a_vector()
    assert not {"novelty_score", "overall_novelty", "aggregate", "mean"} & set(vector)


def test_i46_layers_are_reported_by_name_not_by_count() -> None:
    dimensions = dict(FULL)
    dimensions["experiment_design"] = 0.9
    dimensions["claim_semantic"] = 0.1
    vector = a_vector(dimensions=dimensions)
    assert novel_layers(vector, threshold=0.8) == ["experiment_design"]


def test_i46_a_novel_design_for_a_known_claim_is_not_broadly_novel() -> None:
    dimensions = {layer: 0.05 for layer in NOVELTY_LAYERS}
    dimensions["experiment_design"] = 0.95
    vector = a_vector(dimensions=dimensions)
    assert novel_layers(vector, threshold=0.5) == ["experiment_design"]


def test_i46_invented_layer_is_refused() -> None:
    dimensions = dict(FULL)
    dimensions["vibe"] = 0.9
    with pytest.raises(NoveltyVectorRefused) as excinfo:
        a_vector(dimensions=dimensions)
    assert "not canonical novelty dimensions" in str(excinfo.value)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_i46_out_of_range_layer_is_refused(bad: float) -> None:
    dimensions = dict(FULL)
    dimensions["scope_shift"] = bad
    with pytest.raises(NoveltyVectorRefused) as excinfo:
        a_vector(dimensions=dimensions)
    assert "outside 0..1" in str(excinfo.value)


def test_i46_boolean_is_not_a_novelty_score() -> None:
    dimensions = dict(FULL)
    dimensions["evidence_basis"] = True
    with pytest.raises(NoveltyVectorRefused):
        a_vector(dimensions=dimensions)


# -- EF4-I46 status is derived from the search that ran ------------------


def test_i46_status_is_not_a_parameter() -> None:
    with pytest.raises(TypeError):
        build_novelty_vector(  # type: ignore[call-arg]
            candidate_id="CAND-001",
            dimensions=dict(FULL),
            nearest_candidate_ids=[],
            external_search_certificate_id="SCC-001",
            uncertainties=[],
            external_search_completed=True,
            assessment_status="ASSESSED",
        )


def test_i46_completed_clean_search_is_assessed() -> None:
    assert a_vector()["assessment_status"] == "ASSESSED"


def test_i46_completed_search_with_uncertainties_is_partial() -> None:
    assert a_vector(uncertainties=["one index was rate-limited"])["assessment_status"] == "PARTIAL"


def test_i46_no_external_search_cannot_be_fully_assessed() -> None:
    """"We did not look outside" must not become "nothing exists outside"."""
    assert a_vector(external_search_completed=False)["assessment_status"] == "PARTIAL"


def test_i46_no_search_and_no_local_novelty_is_unassessed() -> None:
    dimensions = {layer: 0.0 for layer in NOVELTY_LAYERS}
    vector = a_vector(dimensions=dimensions, external_search_completed=False)
    assert vector["assessment_status"] == "UNASSESSED"
    assert novelty_is_claimable(vector) is False


def test_i46_failed_assessment_records_reasons_and_claims_nothing() -> None:
    vector = failed_novelty_vector(
        candidate_id="CAND-001",
        external_search_certificate_id="SCC-001",
        reasons=["external index unreachable"],
    )
    assert vector["assessment_status"] == "FAILED"
    assert novelty_is_claimable(vector) is False
    assert novel_layers(vector, threshold=0.0) == []


def test_i46_failed_assessment_without_a_reason_is_refused() -> None:
    with pytest.raises(NoveltyVectorRefused):
        failed_novelty_vector(
            candidate_id="CAND-001",
            external_search_certificate_id="SCC-001",
            reasons=[],
        )


# -- EF4-I46 novelty is separate from support ---------------------------


def test_i46_maximum_novelty_on_every_layer_still_does_not_promote() -> None:
    vector = a_vector(dimensions={layer: 1.0 for layer in NOVELTY_LAYERS})
    assert novelty_supports_promotion(vector) is False


def test_i46_zero_novelty_also_does_not_promote() -> None:
    vector = a_vector(dimensions={layer: 0.0 for layer in NOVELTY_LAYERS})
    assert novelty_supports_promotion(vector) is False


def test_i46_threshold_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(NoveltyVectorRefused):
        novel_layers(a_vector(), threshold=1.5)
