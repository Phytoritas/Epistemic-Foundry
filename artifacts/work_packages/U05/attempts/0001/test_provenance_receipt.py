"""Provenance and receipt audit for the U05 console.

A projection is a receipt: its ``view_id`` and ``view_hash`` are a pure function
of the record's own content, so any projected field is bound into the identity
and tampering with any of them is detectable.  The audit also confirms the two
authority markers are always the same values and that no promotion, holdout or
evaluator field is ever emitted.
"""

from __future__ import annotations

import fixtures
import pytest
from epistemic_foundry.console.v4_u05 import projection as engine


def _all_views() -> list:
    return [
        engine.project_pareto_front(fixtures.pareto_snapshot()),
        engine.project_niche_map(fixtures.two_niches()),
        engine.project_lineages(fixtures.two_lineages()),
        engine.project_challenge_board(
            [fixtures.challenge_genome()], [fixtures.challenge_result()]
        ),
    ]


def test_view_id_is_content_bound_and_prefixed() -> None:
    for view in _all_views():
        assert view["view_id"].startswith(engine.VIEW_ID_PREFIX)
        engine.require_view_identity(view)


def test_view_hash_re_derives_from_body() -> None:
    for view in _all_views():
        record = engine._thaw(view)
        recomputed = engine.hash_excluding(dict(record), "view_hash")
        assert record["view_hash"] == recomputed


def test_tampering_any_projected_field_breaks_identity() -> None:
    view = engine.project_pareto_front(fixtures.pareto_snapshot())
    record = engine._thaw(view)
    for field in ("surface", "candidate_ids", "hypervolume", "requesting_role"):
        mutated = dict(record)
        original = mutated[field]
        mutated[field] = "TAMPERED" if not isinstance(original, list) else ["x"]
        with pytest.raises(engine.ConsoleProjectionRefused) as caught:
            engine.require_view_identity(mutated)
        assert caught.value.code == "INPUT_INVALID"


def test_authority_markers_are_invariant_across_surfaces() -> None:
    for view in _all_views():
        assert view["readonly"] is True
        assert view["grants_authority"] is False


def test_no_authority_or_promotion_field_is_ever_emitted() -> None:
    forbidden = {
        "promotion",
        "promotion_level",
        "promoted",
        "holdout",
        "evaluator",
        "evaluator_score",
        "fitness_score",
        "verdict",
        "decision",
        "winner",
        "admissible_for_promotion_review",
    }

    def walk(node: object) -> None:
        if isinstance(node, (dict,)) or hasattr(node, "items"):
            for key, value in node.items():
                assert key not in forbidden, key
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    for view in _all_views():
        walk(engine._thaw(view))


def test_distinct_inputs_produce_distinct_receipts() -> None:
    a = engine.project_lineages(
        [fixtures.lineage(candidate_id="cand-a", lineage_id="LIN-a")]
    )
    b = engine.project_lineages(
        [fixtures.lineage(candidate_id="cand-z", lineage_id="LIN-z")]
    )
    assert a["view_id"] != b["view_id"]
    assert a["view_hash"] != b["view_hash"]


def test_snapshot_hash_is_carried_into_the_receipt() -> None:
    """The projection's provenance points back at the sealed source hash."""
    snap = fixtures.pareto_snapshot()
    view = engine.project_pareto_front(snap)
    assert view["snapshot_hash"] == snap["snapshot_hash"]
