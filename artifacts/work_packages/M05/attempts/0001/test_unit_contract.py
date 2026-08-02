"""unit_and_contract_tests — the map answers its three questions correctly.

Where does a candidate sit: cell identity is derived and occupancy is a
function.  How concentrated is the population: the entropy figures agree with
hand-computed values on known populations.  What would a change touch: the
blast radius reaches exactly the descendants, their cells and their islands.
"""

from __future__ import annotations

import math

from epistemic_foundry.cartography.v4_m05 import (
    NicheMap,
    build_coverage_map,
    build_lineage_diversity_report,
    compute_blast_radius,
)
from epistemic_foundry.memory.v4_l05 import LineageMemory
from fixtures import (
    RUN_ID,
    THRESHOLDS,
    lineage_record,
    models,
    niche,
    population,
)


def report(memory: LineageMemory, **overrides: object) -> dict:
    arguments: dict = {
        "lineage": memory,
        "evolution_run_id": RUN_ID,
        "generation": 3,
        "model_attribution": models(memory),
        "thresholds": dict(THRESHOLDS),
        "report_id": "LDR-M05-U",
    }
    arguments.update(overrides)
    return build_lineage_diversity_report(**arguments)


def test_the_map_places_each_candidate_in_exactly_one_cell() -> None:
    board = NicheMap([niche("a", ["C1", "C2"], elite_id="C1"), niche("b", ["D1"])])

    assert board.niche_of("C1") == board.niche_of("C2")
    assert board.niche_of("D1") != board.niche_of("C1")
    assert board.niche_of("GHOST") is None
    assert len(board.occupants()) == 3


def test_an_empty_cell_is_part_of_the_map_but_not_occupied() -> None:
    board = NicheMap([niche("a", ["C1"]), niche("b", [])])

    assert len(board.niche_ids()) == 2
    assert len(board.occupied_niche_ids()) == 1


def test_a_single_founder_population_has_zero_entropy() -> None:
    memory = LineageMemory(
        [
            lineage_record("C1", [], 1),
            lineage_record("C2", ["C1"], 2),
            lineage_record("C3", ["C2"], 3),
        ]
    )
    result = report(
        memory, thresholds={**THRESHOLDS, "effective_lineage_count_min": 1.0}
    )

    assert result["lineage_entropy"] == 0.0
    assert result["effective_lineage_count"] == 1.0
    assert result["dominant_lineage_share"] == 1.0


def test_uniform_founders_reach_maximal_entropy() -> None:
    memory = LineageMemory(
        [
            lineage_record(f"F{index}", [], 1, operators=(f"MO-{index}",))
            for index in range(1, 5)
        ]
    )
    result = report(
        memory, thresholds={**THRESHOLDS, "dominant_lineage_share_max": 0.3}
    )

    assert result["lineage_entropy"] == round(math.log(4), 6)
    # Coherence beats prettiness: the effective count is the exponential of
    # the *published* entropy, so it lands at 3.999999 rather than 4.0 and a
    # reader can re-derive it exactly from the report's own fields.
    assert result["effective_lineage_count"] == round(
        math.exp(result["lineage_entropy"]), 6
    )
    assert result["dominant_lineage_share"] == 0.25
    assert result["inbreeding_alerts"] == []


def test_the_effective_count_is_the_exponential_of_the_entropy() -> None:
    result = report(population())

    assert result["effective_lineage_count"] == round(
        math.exp(result["lineage_entropy"]), 6
    )


def test_the_dominant_share_matches_the_founder_arithmetic() -> None:
    # population(): C1 founds four of five candidates, D1 founds one.
    result = report(population())

    assert result["dominant_lineage_share"] == round(4 / 5, 6)


def test_operator_entropy_defaults_to_the_lineage_records() -> None:
    memory = LineageMemory(
        [
            lineage_record("A1", [], 1, operators=("MO-A",)),
            lineage_record("B1", [], 1, operators=("MO-B",)),
        ]
    )
    result = report(
        memory, thresholds={**THRESHOLDS, "dominant_lineage_share_max": 0.6}
    )

    assert result["operator_entropy"] == round(math.log(2), 6)


def test_an_explicit_operator_attribution_overrides_the_records() -> None:
    memory = LineageMemory([lineage_record("A1", [], 1), lineage_record("B1", [], 1)])
    result = report(
        memory,
        operator_attribution={"A1": ["MO-X"], "B1": ["MO-X"]},
        thresholds={**THRESHOLDS, "dominant_lineage_share_max": 0.6},
    )

    assert result["operator_entropy"] == 0.0
    assert "OPERATOR_MONOCULTURE" in result["inbreeding_alerts"]


def test_distinct_models_raise_model_entropy() -> None:
    memory = LineageMemory(
        [
            lineage_record("A1", [], 1, operators=("MO-A",)),
            lineage_record("B1", [], 1, operators=("MO-B",)),
        ]
    )
    result = report(
        memory,
        model_attribution={"A1": "model-a", "B1": "model-b"},
        thresholds={**THRESHOLDS, "dominant_lineage_share_max": 0.6},
    )

    assert result["model_entropy"] == round(math.log(2), 6)


def test_crossover_across_lineages_is_not_an_inbreeding_alert() -> None:
    memory = LineageMemory(
        [
            lineage_record("A1", [], 1, operators=("MO-A",)),
            lineage_record("B1", [], 1, operators=("MO-B",)),
            lineage_record(
                "AB", ["A1", "B1"], 2, operators=("MO-A",), crossover=("A1", "B1")
            ),
        ]
    )
    result = report(
        memory,
        thresholds={
            "dominant_lineage_share_max": 0.7,
            "effective_lineage_count_min": 1.0,
        },
    )

    assert "CROSSOVER_WITHIN_SINGLE_LINEAGE" not in result["inbreeding_alerts"]


def test_every_alert_carries_its_recommended_action() -> None:
    # population() trips all four: X1 crosses two branches of one founder,
    # C1's lineage holds four of five candidates, the effective count 1.65
    # sits under the 2.0 floor, and every record shares one operator.
    result = report(population())

    assert result["inbreeding_alerts"] == [
        "CROSSOVER_WITHIN_SINGLE_LINEAGE",
        "DOMINANT_LINEAGE_SHARE_EXCEEDED",
        "EFFECTIVE_LINEAGE_COUNT_BELOW_MINIMUM",
        "OPERATOR_MONOCULTURE",
    ]
    assert len(result["recommended_actions"]) == len(result["inbreeding_alerts"])


def test_the_blast_radius_reaches_exactly_the_descendants() -> None:
    memory = population()
    board = NicheMap(
        [
            niche("a", ["C1", "C2"], elite_id="C1"),
            niche("b", ["C3", "X1"], elite_id="X1"),
            niche("c", ["D1"], elite_id="D1"),
        ]
    )
    radius = compute_blast_radius(lineage=memory, niche_map=board, candidate_id="C1")

    assert radius["affected_candidate_ids"] == ["C1", "C2", "C3", "X1"]
    assert len(radius["affected_niche_ids"]) == 2
    assert radius["counts"]["elites_at_risk"] == 2
    assert "D1" not in radius["affected_candidate_ids"]


def test_a_leaf_blast_radius_is_only_itself() -> None:
    memory = population()
    board = NicheMap([niche("a", ["X1"])])
    radius = compute_blast_radius(lineage=memory, niche_map=board, candidate_id="X1")

    assert radius["affected_candidate_ids"] == ["X1"]
    assert radius["descendant_ids"] == []
    assert radius["counts"]["affected_candidates"] == 1


def test_unmapped_candidates_are_named_rather_than_dropped() -> None:
    memory = population()
    board = NicheMap([niche("a", ["C1"])])
    radius = compute_blast_radius(lineage=memory, niche_map=board, candidate_id="C1")

    assert radius["unmapped_candidate_ids"] == ["C2", "C3", "X1"]
    assert radius["counts"]["affected_candidates"] == 4


def test_island_membership_appears_when_supplied() -> None:
    memory = population()
    board = NicheMap([niche("a", ["C1", "C2", "C3", "X1", "D1"], capacity=5)])
    membership = {c: ("IS-2" if c == "X1" else "IS-1") for c in memory.candidates()}
    radius = compute_blast_radius(
        lineage=memory, niche_map=board, candidate_id="C1", island_membership=membership
    )

    assert radius["affected_islands"] == ["IS-1", "IS-2"]


def test_the_coverage_ratio_is_derived_from_the_cells() -> None:
    board = NicheMap([niche("a", ["C1"]), niche("b", []), niche("c", [])])
    record = build_coverage_map(
        niche_map=board,
        evolution_run_id=RUN_ID,
        generation=2,
        lineage_entropy=0.1,
        map_id="QDM-M05-U",
    )

    assert record["total_niches"] == 3
    assert record["occupied_niches"] == 1
    assert record["coverage_ratio"] == round(1 / 3, 6)


def test_a_declared_stagnant_niche_is_recorded() -> None:
    empty = niche("b", [])
    board = NicheMap([niche("a", ["C1"]), empty])
    record = build_coverage_map(
        niche_map=board,
        evolution_run_id=RUN_ID,
        generation=2,
        lineage_entropy=0.1,
        stagnant_niche_ids=[empty["niche_id"]],
        map_id="QDM-M05-U2",
    )

    assert record["stagnant_niche_ids"] == [empty["niche_id"]]


def test_the_report_and_radius_are_deterministic() -> None:
    memory = population()
    board = NicheMap([niche("a", ["C1"])])

    assert report(memory) == report(memory)
    assert compute_blast_radius(
        lineage=memory, niche_map=board, candidate_id="C1"
    ) == compute_blast_radius(lineage=memory, niche_map=board, candidate_id="C1")


def test_the_records_are_serialisable_evidence() -> None:
    import json

    memory = population()
    board = NicheMap([niche("a", ["C1"])])
    for record in (
        report(memory),
        compute_blast_radius(lineage=memory, niche_map=board, candidate_id="C1"),
        niche("z", ["Z1"], elite_id="Z1"),
    ):
        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True)) == (
            record
        )
