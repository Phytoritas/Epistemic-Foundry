"""negative_and_adversarial_tests — every way a map can lie, refused.

A map that is wrong is worse than no map: a forged cell id splits one niche's
competition, a double occupancy makes coverage double-count, a partial
attribution turns entropy into a fiction, and a blast radius that drops
unmapped candidates understates the damage.  Each attack is an input wrong in
exactly one way, refused by its own code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.cartography.v4_m05 import (
    CartographyError,
    NicheMap,
    build_coverage_map,
    build_lineage_diversity_report,
    build_niche,
    compute_blast_radius,
)
from epistemic_foundry.memory.v4_l05 import LineageMemory
from fixtures import (
    RUN_ID,
    THRESHOLDS,
    coordinates,
    lineage_record,
    models,
    niche,
    population,
)


def refused(run, code: str) -> CartographyError:
    with pytest.raises(CartographyError) as caught:
        run()
    assert caught.value.code == code, caught.value.code
    return caught.value


def test_two_cells_with_one_coordinate_set_are_refused() -> None:
    duplicate = build_niche(
        axis_values=coordinates("a"),
        capacity=1,
        occupant_ids=[],
        elite_id=None,
        coverage_debt=0.5,
    )

    error = refused(
        lambda: NicheMap([niche("a", ["C1"]), duplicate]), "CELL_DUPLICATED"
    )
    assert error.context["niche_id"] == duplicate["niche_id"]


def test_a_candidate_in_two_cells_is_refused() -> None:
    error = refused(
        lambda: NicheMap([niche("a", ["C1"]), niche("b", ["C1"])]),
        "OCCUPANCY_AMBIGUOUS",
    )
    assert error.context["candidate_id"] == "C1"
    assert len(error.context["niche_ids"]) == 2


def test_a_forged_niche_id_is_refused() -> None:
    forged = dict(niche("a", ["C1"]))
    forged["niche_id"] = "NI-0000000000000000"

    error = refused(lambda: NicheMap([forged]), "NICHE_IDENTITY_FORGED")
    assert error.context["stated"] == "NI-0000000000000000"


def test_editing_coordinates_after_the_id_was_derived_is_refused() -> None:
    edited = dict(niche("a", ["C1"]))
    edited["axis_values"] = dict(edited["axis_values"])
    edited["axis_values"][next(iter(edited["axis_values"]))] = "moved"

    refused(lambda: NicheMap([edited]), "NICHE_IDENTITY_FORGED")


def test_an_overfull_niche_is_refused() -> None:
    error = refused(
        lambda: build_niche(
            axis_values=coordinates("a"),
            capacity=1,
            occupant_ids=["C1", "C2"],
            elite_id=None,
            coverage_debt=0.0,
        ),
        "NICHE_OVERFULL",
    )
    assert error.context == {"capacity": 1, "occupant_count": 2}


def test_an_elite_outside_its_own_cell_is_refused() -> None:
    refused(
        lambda: build_niche(
            axis_values=coordinates("a"),
            capacity=2,
            occupant_ids=["C1"],
            elite_id="C9",
            coverage_debt=0.0,
        ),
        "ELITE_NOT_OCCUPANT",
    )


def test_a_duplicate_occupant_is_refused() -> None:
    refused(
        lambda: build_niche(
            axis_values=coordinates("a"),
            capacity=3,
            occupant_ids=["C1", "C1"],
            elite_id=None,
            coverage_debt=0.0,
        ),
        "INPUT_INVALID",
    )


def test_a_boolean_capacity_is_refused() -> None:
    refused(
        lambda: build_niche(
            axis_values=coordinates("a"),
            capacity=True,
            occupant_ids=[],
            elite_id=None,
            coverage_debt=0.0,
        ),
        "INPUT_INVALID",
    )


def test_an_undeclared_axis_is_refused() -> None:
    error = refused(
        lambda: build_niche(
            axis_values={**coordinates("a"), "vibe": "good"},
            capacity=1,
            occupant_ids=[],
            elite_id=None,
            coverage_debt=0.0,
        ),
        "AXIS_UNDECLARED",
    )
    assert error.context["undeclared"] == ["vibe"]


def test_a_missing_axis_is_refused() -> None:
    partial = coordinates("a")
    dropped = next(iter(partial))
    del partial[dropped]

    error = refused(
        lambda: build_niche(
            axis_values=partial,
            capacity=1,
            occupant_ids=[],
            elite_id=None,
            coverage_debt=0.0,
        ),
        "AXIS_UNDECLARED",
    )
    assert error.context["missing"] == [dropped]


def test_an_empty_axis_value_is_refused() -> None:
    blank = coordinates("a")
    blank[next(iter(blank))] = "   "

    refused(
        lambda: build_niche(
            axis_values=blank,
            capacity=1,
            occupant_ids=[],
            elite_id=None,
            coverage_debt=0.0,
        ),
        "AXIS_UNDECLARED",
    )


def test_a_coverage_debt_outside_the_schema_range_is_refused() -> None:
    from epistemic_foundry.contracts import ContractViolation

    with pytest.raises(ContractViolation):
        build_niche(
            axis_values=coordinates("a"),
            capacity=1,
            occupant_ids=[],
            elite_id=None,
            coverage_debt=1.5,
        )


def test_a_blast_radius_for_an_unknown_candidate_is_refused() -> None:
    error = refused(
        lambda: compute_blast_radius(
            lineage=population(),
            niche_map=NicheMap([niche("a", [])]),
            candidate_id="GHOST",
        ),
        "CANDIDATE_UNKNOWN",
    )
    assert error.context["candidate_id"] == "GHOST"


def test_partial_island_membership_is_refused() -> None:
    memory = population()
    board = NicheMap([niche("a", ["C1"])])

    error = refused(
        lambda: compute_blast_radius(
            lineage=memory,
            niche_map=board,
            candidate_id="C1",
            island_membership={"C1": "IS-1"},
        ),
        "ATTRIBUTION_INCOMPLETE",
    )
    assert error.context["missing"] == ["C2", "C3", "X1"]


def test_partial_model_attribution_is_refused() -> None:
    memory = population()

    error = refused(
        lambda: build_lineage_diversity_report(
            lineage=memory,
            evolution_run_id=RUN_ID,
            generation=1,
            model_attribution={"C1": "model-a"},
            thresholds=THRESHOLDS,
        ),
        "ATTRIBUTION_INCOMPLETE",
    )
    assert error.context["missing"] == ["C2", "C3", "D1", "X1"]


def test_partial_operator_attribution_is_refused() -> None:
    memory = population()

    refused(
        lambda: build_lineage_diversity_report(
            lineage=memory,
            evolution_run_id=RUN_ID,
            generation=1,
            operator_attribution={"C1": ["MO-1"]},
            model_attribution=models(memory),
            thresholds=THRESHOLDS,
        ),
        "ATTRIBUTION_INCOMPLETE",
    )


def test_a_population_with_no_operators_at_all_is_refused() -> None:
    memory = LineageMemory([lineage_record("A1", [], 1, operators=())])

    refused(
        lambda: build_lineage_diversity_report(
            lineage=memory,
            evolution_run_id=RUN_ID,
            generation=1,
            model_attribution={"A1": "model-a"},
            thresholds={**THRESHOLDS, "effective_lineage_count_min": 1.0},
        ),
        "ATTRIBUTION_INCOMPLETE",
    )


@pytest.mark.parametrize(
    "thresholds",
    [
        {"dominant_lineage_share_max": 0.0, "effective_lineage_count_min": 1.0},
        {"dominant_lineage_share_max": 1.5, "effective_lineage_count_min": 1.0},
        {"dominant_lineage_share_max": 0.5, "effective_lineage_count_min": 0.5},
        {"dominant_lineage_share_max": 0.5},
        {},
    ],
)
def test_a_meaningless_threshold_is_refused(thresholds: dict) -> None:
    memory = population()

    refused(
        lambda: build_lineage_diversity_report(
            lineage=memory,
            evolution_run_id=RUN_ID,
            generation=1,
            model_attribution=models(memory),
            thresholds=thresholds,
        ),
        "THRESHOLD_INVALID",
    )


def test_an_empty_population_cannot_be_reported() -> None:
    refused(
        lambda: build_lineage_diversity_report(
            lineage=LineageMemory([]),
            evolution_run_id=RUN_ID,
            generation=1,
            model_attribution={},
            thresholds=THRESHOLDS,
        ),
        "INPUT_INVALID",
    )


def test_a_stagnant_niche_outside_the_map_is_refused() -> None:
    board = NicheMap([niche("a", ["C1"])])

    error = refused(
        lambda: build_coverage_map(
            niche_map=board,
            evolution_run_id=RUN_ID,
            generation=1,
            lineage_entropy=0.1,
            stagnant_niche_ids=["NI-nowhere"],
        ),
        "NICHE_UNKNOWN",
    )
    assert error.context["unknown"] == ["NI-nowhere"]


def test_a_non_mapping_niche_is_refused() -> None:
    refused(lambda: NicheMap(["not-a-mapping"]), "INPUT_INVALID")


def test_a_niche_the_schema_rejects_is_refused() -> None:
    from epistemic_foundry.contracts import ContractViolation

    broken = dict(niche("a", ["C1"]))
    del broken["capacity"]

    with pytest.raises(ContractViolation):
        NicheMap([broken])
