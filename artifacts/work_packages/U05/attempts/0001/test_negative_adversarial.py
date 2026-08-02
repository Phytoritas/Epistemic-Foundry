"""Negative and adversarial checks for the U05 console.

Every finding code in :data:`FINDING_CODES` is triggered here, together with the
crash/resume path (a persisted view re-derives its identity after a restart) and
the adversarial paths (a tampered view is detected, an authority grab is refused,
and a candidate-generating role acquires nothing).
"""

from __future__ import annotations

import copy
import json

import fixtures
import pytest
from epistemic_foundry.console.v4_u05 import projection as engine


def _refuse(func, *args, **kwargs) -> str:
    with pytest.raises(engine.ConsoleProjectionRefused) as caught:
        func(*args, **kwargs)
    return caught.value.code


# -- input shape / routing / authority ------------------------------------


def test_input_invalid_on_non_mapping_snapshot() -> None:
    assert _refuse(engine.project_pareto_front, "not-a-mapping") == "INPUT_INVALID"


def test_input_invalid_on_non_sequence_niches() -> None:
    assert _refuse(engine.project_niche_map, {"not": "a sequence"}) == "INPUT_INVALID"


def test_input_invalid_on_blank_requesting_role() -> None:
    assert (
        _refuse(engine.project_lineages, fixtures.two_lineages(), requesting_role="  ")
        == "INPUT_INVALID"
    )


def test_surface_undeclared() -> None:
    assert (
        _refuse(engine.build_console_projection, surface="bogus_surface", payload={})
        == "SURFACE_UNDECLARED"
    )


def test_promotion_authority_refused() -> None:
    code = _refuse(
        engine.build_console_projection,
        surface=engine.SURFACE_PARETO_FRONT,
        payload={"snapshot": fixtures.pareto_snapshot()},
        authority_request="please promote the front leader",
    )
    assert code == "PROMOTION_AUTHORITY_REFUSED"


# -- Pareto front refusals -------------------------------------------------


def test_snapshot_refused_when_schema_rejects() -> None:
    snap = fixtures.pareto_snapshot(objective_dimensions=["only-one"])
    snap["snapshot_hash"] = engine.hash_excluding(snap, "snapshot_hash")
    assert _refuse(engine.project_pareto_front, snap) == "SNAPSHOT_REFUSED"


def test_snapshot_drift_when_hash_does_not_re_derive() -> None:
    snap = fixtures.pareto_snapshot()
    snap["hypervolume"] = 0.999  # sealed hash no longer matches the content
    assert _refuse(engine.project_pareto_front, snap) == "SNAPSHOT_DRIFT"


def test_front_pairing_incomplete() -> None:
    snap = fixtures.pareto_snapshot(
        candidate_ids=["cand-a", "cand-b"], fitness_vector_ids=["fv-a"]
    )
    snap["snapshot_hash"] = engine.hash_excluding(snap, "snapshot_hash")
    assert _refuse(engine.project_pareto_front, snap) == "FRONT_PAIRING_INCOMPLETE"


def test_front_reference_misaligned() -> None:
    snap = fixtures.pareto_snapshot(
        objective_dimensions=["novelty", "quality"], reference_point=[0.0]
    )
    snap["snapshot_hash"] = engine.hash_excluding(snap, "snapshot_hash")
    assert _refuse(engine.project_pareto_front, snap) == "FRONT_REFERENCE_MISALIGNED"


# -- niche refusals --------------------------------------------------------


def test_niche_refused_on_hash_drift() -> None:
    niche = fixtures.niche()
    niche["coverage_debt"] = 0.9  # niche_hash no longer matches
    assert _refuse(engine.project_niche_map, [niche]) == "NICHE_REFUSED"


def test_niche_refused_on_duplicate_cell() -> None:
    """Two niches with the same coordinates are refused by the sealed M05 map."""
    first = fixtures.niche(suffix="1", occupant_ids=["cand-a"], elite_id="cand-a")
    second = fixtures.niche(suffix="1", occupant_ids=["cand-b"], elite_id="cand-b")
    assert _refuse(engine.project_niche_map, [first, second]) == "NICHE_REFUSED"


# -- lineage refusals ------------------------------------------------------


def test_lineage_refused_when_schema_rejects() -> None:
    lineage = fixtures.lineage()
    del lineage["island_id"]  # required field
    assert _refuse(engine.project_lineages, [lineage]) == "LINEAGE_REFUSED"


# -- challenge refusals ----------------------------------------------------


def test_challenge_genome_refused_on_invalid_class() -> None:
    genome = fixtures.challenge_genome()
    genome["challenge_class"] = "not-a-declared-challenge-class"
    assert (
        _refuse(engine.project_challenge_board, [genome], [])
        == "CHALLENGE_GENOME_REFUSED"
    )


def test_challenge_result_refused_on_invalid_outcome() -> None:
    genome = fixtures.challenge_genome()
    result = fixtures.challenge_result()
    result["outcome"] = "not-a-declared-outcome"
    assert (
        _refuse(engine.project_challenge_board, [genome], [result])
        == "CHALLENGE_RESULT_REFUSED"
    )


def test_result_drift_when_hash_does_not_re_derive() -> None:
    genome = fixtures.challenge_genome()
    result = fixtures.challenge_result()
    result["observed_effect"] = "a different, still-valid effect string"
    assert _refuse(engine.project_challenge_board, [genome], [result]) == "RESULT_DRIFT"


def test_challenge_target_missing() -> None:
    genome = fixtures.challenge_genome(challenge_genome_id="CG-present")
    result = fixtures.challenge_result(challenge_genome_id="CG-absent")
    assert (
        _refuse(engine.project_challenge_board, [genome], [result])
        == "CHALLENGE_TARGET_MISSING"
    )


def test_every_finding_code_is_exercised() -> None:
    """Guard: the negatives above must cover the whole catalogue."""
    exercised = {
        "INPUT_INVALID",
        "SURFACE_UNDECLARED",
        "PROMOTION_AUTHORITY_REFUSED",
        "SNAPSHOT_REFUSED",
        "SNAPSHOT_DRIFT",
        "FRONT_PAIRING_INCOMPLETE",
        "FRONT_REFERENCE_MISALIGNED",
        "NICHE_REFUSED",
        "LINEAGE_REFUSED",
        "CHALLENGE_GENOME_REFUSED",
        "CHALLENGE_RESULT_REFUSED",
        "RESULT_DRIFT",
        "CHALLENGE_TARGET_MISSING",
    }
    assert exercised == set(engine.FINDING_CODES)


# -- crash / resume --------------------------------------------------------


def test_persisted_view_re_derives_after_restart() -> None:
    """A view serialized to disk and reloaded must still re-derive its identity."""
    view = engine.project_niche_map(fixtures.two_niches())
    on_disk = json.dumps(engine._thaw(view), sort_keys=True)
    reloaded = json.loads(on_disk)
    recovered = engine.require_view_identity(reloaded)
    assert recovered["view_id"] == view["view_id"]
    assert recovered["view_hash"] == view["view_hash"]


# -- adversarial -----------------------------------------------------------


def test_tampered_persisted_view_is_detected() -> None:
    view = engine.project_lineages(fixtures.two_lineages())
    tampered = engine._thaw(view)
    tampered["counts"]["lineages"] = 99  # forge a field, keep the stored hash
    assert _refuse(engine.require_view_identity, tampered) == "INPUT_INVALID"


def test_candidate_generating_role_acquires_no_authority() -> None:
    """A mutable-search role may read but is granted nothing (EF4 evolution integrity)."""
    view = engine.build_console_projection(
        surface=engine.SURFACE_CHALLENGE_BOARD,
        payload={
            "genomes": [fixtures.challenge_genome()],
            "challenge_results": [fixtures.challenge_result()],
        },
        requesting_role="ef-challenge-evolver",
    )
    assert view["grants_authority"] is False
    assert view["readonly"] is True


def test_authority_request_is_refused_before_any_surface_is_touched() -> None:
    """Even a malformed payload cannot slip past the authority boundary."""
    code = _refuse(
        engine.build_console_projection,
        surface="also-bogus",
        payload="not-even-a-mapping",
        authority_request={"grant": "promotion"},
    )
    assert code == "PROMOTION_AUTHORITY_REFUSED"


def test_undeclared_finding_code_cannot_be_raised() -> None:
    """`_fail` refuses to emit a code that is not documented."""
    code = _refuse(engine._fail, "NOT_A_REAL_CODE", "should not escape")
    assert code == "INPUT_INVALID"


def test_input_unmutated_even_on_refusal() -> None:
    snap = fixtures.pareto_snapshot()
    snap["hypervolume"] = 0.999
    before = copy.deepcopy(snap)
    _refuse(engine.project_pareto_front, snap)
    assert snap == before
