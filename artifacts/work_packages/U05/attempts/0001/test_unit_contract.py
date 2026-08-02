"""Unit and contract checks for the U05 console happy path.

Each surface projects a sealed artifact into a deep-frozen, deterministic view
whose identity re-derives, whose authority markers never change, and whose input
is never mutated.  The dispatcher routes to the same projections and enforces the
authority boundary.
"""

from __future__ import annotations

import copy
from types import MappingProxyType

import fixtures
import pytest
from epistemic_foundry.console.v4_u05 import projection as engine


# -- Pareto front ----------------------------------------------------------


def test_pareto_projection_is_read_only_and_grants_no_authority() -> None:
    view = engine.project_pareto_front(fixtures.pareto_snapshot())
    assert view["surface"] == engine.SURFACE_PARETO_FRONT
    assert view["readonly"] is True
    assert view["grants_authority"] is False
    assert view["candidate_ids"] == ("cand-a", "cand-b")
    # Candidate/fitness pairing is preserved and ordered by candidate.
    assert dict(view["candidate_fitness_pairs"][0]) == {
        "candidate_id": "cand-a",
        "fitness_vector_id": "fv-a",
    }
    assert view["counts"]["candidates"] == 2
    engine.require_view_identity(view)


def test_pareto_projection_never_selects_a_winner() -> None:
    """A projection of a front is a set, not a promotion; no winner field exists."""
    view = engine.project_pareto_front(fixtures.pareto_snapshot())
    thawed = engine._thaw(view)
    for forbidden in ("winner", "selected", "promoted", "decision", "elite"):
        assert forbidden not in thawed


# -- niche map -------------------------------------------------------------


def test_niche_projection_reports_occupancy() -> None:
    view = engine.project_niche_map(fixtures.two_niches())
    assert view["counts"]["niches"] == 2
    assert view["counts"]["placed_candidates"] == 3
    assert set(view["occupancy"]) == {"cand-a", "cand-b", "cand-c"}
    engine.require_view_identity(view)


# -- lineages --------------------------------------------------------------


def test_lineage_projection_orders_by_candidate() -> None:
    view = engine.project_lineages(fixtures.two_lineages())
    assert view["candidate_ids"] == ("cand-a", "cand-b")
    assert view["counts"]["lineages"] == 2
    assert view["island_ids"] == ("island-1",)
    engine.require_view_identity(view)


# -- challenge board -------------------------------------------------------


def test_challenge_board_has_every_declared_bucket() -> None:
    genome = fixtures.challenge_genome()
    result = fixtures.challenge_result()
    view = engine.project_challenge_board([genome], [result])
    # Every outcome and severity bucket is present, even empty ones.
    assert set(view["results_by_outcome"]) == set(engine.challenge_outcome_vocabulary())
    assert set(view["results_by_severity"]) == set(
        engine.challenge_severity_vocabulary()
    )
    first_outcome = engine.challenge_outcome_vocabulary()[0]
    assert view["results_by_outcome"][first_outcome] == ("CR-1",)
    assert view["counts"]["challenge_results"] == 1
    engine.require_view_identity(view)


def test_challenge_board_computes_no_survival_verdict() -> None:
    genome = fixtures.challenge_genome()
    result = fixtures.challenge_result()
    thawed = engine._thaw(engine.project_challenge_board([genome], [result]))
    for forbidden in ("survived", "promoted", "verdict", "retracted", "admissible"):
        assert forbidden not in thawed


# -- determinism, freezing, immutability -----------------------------------


def test_projection_is_deterministic() -> None:
    snap = fixtures.pareto_snapshot()
    first = engine.project_pareto_front(snap)
    second = engine.project_pareto_front(copy.deepcopy(snap))
    assert first["view_id"] == second["view_id"]
    assert first["view_hash"] == second["view_hash"]
    assert engine._thaw(first) == engine._thaw(second)


def test_view_is_deep_frozen() -> None:
    view = engine.project_challenge_board(
        [fixtures.challenge_genome()], [fixtures.challenge_result()]
    )
    assert isinstance(view, MappingProxyType)
    with pytest.raises(TypeError):
        view["surface"] = "tampered"  # type: ignore[index]
    with pytest.raises((TypeError, AttributeError)):
        view["genomes"].append({})  # type: ignore[attr-defined]


def test_inputs_are_not_mutated() -> None:
    snap = fixtures.pareto_snapshot()
    niches = fixtures.two_niches()
    lineages = fixtures.two_lineages()
    genome = fixtures.challenge_genome()
    result = fixtures.challenge_result()
    snap_c = copy.deepcopy(snap)
    niches_c = copy.deepcopy(niches)
    lineages_c = copy.deepcopy(lineages)
    genome_c = copy.deepcopy(genome)
    result_c = copy.deepcopy(result)

    engine.project_pareto_front(snap)
    engine.project_niche_map(niches)
    engine.project_lineages(lineages)
    engine.project_challenge_board([genome], [result])

    assert snap == snap_c
    assert niches == niches_c
    assert lineages == lineages_c
    assert genome == genome_c
    assert result == result_c


# -- dispatcher ------------------------------------------------------------


def test_dispatcher_routes_every_surface() -> None:
    snap = fixtures.pareto_snapshot()
    assert (
        engine.build_console_projection(
            surface=engine.SURFACE_PARETO_FRONT, payload={"snapshot": snap}
        )["view_hash"]
        == engine.project_pareto_front(snap)["view_hash"]
    )
    assert (
        engine.build_console_projection(
            surface=engine.SURFACE_NICHE_MAP, payload={"niches": fixtures.two_niches()}
        )["surface"]
        == engine.SURFACE_NICHE_MAP
    )
    assert (
        engine.build_console_projection(
            surface=engine.SURFACE_LINEAGES,
            payload={"lineages": fixtures.two_lineages()},
        )["surface"]
        == engine.SURFACE_LINEAGES
    )
    assert (
        engine.build_console_projection(
            surface=engine.SURFACE_CHALLENGE_BOARD,
            payload={
                "genomes": [fixtures.challenge_genome()],
                "challenge_results": [fixtures.challenge_result()],
            },
        )["surface"]
        == engine.SURFACE_CHALLENGE_BOARD
    )


def test_dispatcher_records_requesting_role_but_grants_nothing() -> None:
    view = engine.build_console_projection(
        surface=engine.SURFACE_LINEAGES,
        payload={"lineages": fixtures.two_lineages()},
        requesting_role="ef-hypothesis-mutator",
    )
    # A candidate-generating role may READ; the projection still grants nothing.
    assert view["requesting_role"] == "ef-hypothesis-mutator"
    assert view["grants_authority"] is False
    assert view["readonly"] is True
