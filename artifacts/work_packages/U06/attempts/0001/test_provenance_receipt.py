"""Provenance and receipt audit for the U06 gate.

A panel and a dashboard are receipts: their identifiers and hashes are a pure
function of the record's own content, so any field is bound into the identity and
tampering with any of them is detectable.  A populated panel's provenance points
back at the sealed U05 view it projected, and no panel or dashboard ever emits a
promotion, holdout or evaluator field or claims authority it does not hold.
"""

from __future__ import annotations

import fixtures
import pytest
from epistemic_foundry.console.v4_u05 import projection as u05
from epistemic_foundry.console.v4_u06 import usability_gate as gate

CA = fixtures.CREATED_AT


def _panel(surface, payload, **kw):
    return gate.build_operator_panel(
        surface=surface, payload=payload, created_at=CA, **kw
    )


def _panels() -> list:
    return [
        _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload()),
        _panel(fixtures.SURFACES["niche"], None),
        _panel(fixtures.SURFACES["challenge"], fixtures.empty_challenge_payload()),
    ]


def test_panel_id_is_content_bound_and_prefixed() -> None:
    for panel in _panels():
        assert panel["panel_id"].startswith(gate.PANEL_ID_PREFIX)
        gate.require_panel_identity(panel)


def test_dashboard_id_is_content_bound_and_prefixed() -> None:
    dashboard = gate.compose_operator_dashboard(panels=_panels(), created_at=CA)
    assert dashboard["dashboard_id"].startswith(gate.DASHBOARD_ID_PREFIX)
    gate.require_dashboard_identity(dashboard)


def test_hash_re_derives_from_body() -> None:
    for panel in _panels():
        record = gate._thaw(panel)
        assert record["panel_hash"] == gate.hash_excluding(dict(record), "panel_hash")


def test_tampering_any_panel_field_breaks_identity() -> None:
    panel = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    record = gate._thaw(panel)
    for field in ("surface", "state", "reason", "requesting_role", "created_at"):
        mutated = dict(record)
        mutated[field] = "TAMPERED"
        with pytest.raises(gate.UsabilityGateError) as caught:
            gate.require_panel_identity(mutated)
        assert caught.value.code == "RECEIPT_DRIFT"


def test_authority_markers_are_invariant() -> None:
    for panel in _panels():
        assert panel["readonly"] is True
        assert panel["grants_authority"] is False
    dashboard = gate.compose_operator_dashboard(panels=_panels(), created_at=CA)
    assert dashboard["readonly"] is True
    assert dashboard["grants_authority"] is False


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
        if hasattr(node, "items"):
            for key, value in node.items():
                assert key not in forbidden, key
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    dashboard = gate.compose_operator_dashboard(panels=_panels(), created_at=CA)
    walk(gate._thaw(dashboard))


def test_distinct_inputs_produce_distinct_receipts() -> None:
    a = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    b = _panel(
        fixtures.SURFACES["pareto"],
        {
            "snapshot": fixtures.pareto_snapshot(
                candidate_ids=["z"], fitness_vector_ids=["fz"]
            )
        },
    )
    assert a["panel_id"] != b["panel_id"]
    assert a["panel_hash"] != b["panel_hash"]


def test_populated_panel_provenance_points_back_at_the_sealed_view() -> None:
    """A populated panel's source hash equals the U05 view's own view_hash."""
    payload = fixtures.pareto_payload()
    panel = _panel(fixtures.SURFACES["pareto"], payload)
    view = u05.project_pareto_front(payload["snapshot"])
    assert panel["source_view_id"] == view["view_id"]
    assert panel["source_view_hash"] == view["view_hash"]
    # The referenced view is itself independently re-derivable.
    u05.require_view_identity(view)


def test_dashboard_binds_the_panel_ids_it_embeds() -> None:
    panels = _panels()
    dashboard = gate.compose_operator_dashboard(panels=panels, created_at=CA)
    assert set(dashboard["panel_ids"]) == {panel["panel_id"] for panel in panels}
    for embedded in dashboard["panels"]:
        gate.require_panel_identity(embedded)
