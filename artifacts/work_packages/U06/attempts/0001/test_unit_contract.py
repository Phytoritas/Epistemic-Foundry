"""Unit and contract checks for the U06 gate happy path.

Each panel resolves to one of the four honest-UI states from what actually
happened, carries the two authority markers that never change, and re-derives its
own identity.  The dashboard composes panels and reports completeness only when
every surface is populated, never overstating what the operator can see.
"""

from __future__ import annotations

import copy
from types import MappingProxyType

import fixtures
import pytest
from epistemic_foundry.console.v4_u06 import usability_gate as gate

CA = fixtures.CREATED_AT
POPULATED = str(gate.ResultState.POPULATED)
EMPTY = str(gate.ResultState.EMPTY_CONFIRMED)
DEGRADED = str(gate.ResultState.DEGRADED)
UNAVAILABLE = str(gate.ResultState.UNAVAILABLE)


def _panel(surface: str, payload, **kw):
    return gate.build_operator_panel(
        surface=surface, payload=payload, created_at=CA, **kw
    )


# -- the four honest-UI states --------------------------------------------


def test_populated_panel_reports_a_readable_surface() -> None:
    panel = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    assert panel["state"] == POPULATED
    assert panel["available"] is True
    assert panel["item_count"] == 2
    assert panel["readonly"] is True
    assert panel["grants_authority"] is False
    assert panel["source_view_hash"].startswith("sha256:")
    gate.require_panel_identity(panel)


def test_empty_confirmed_is_distinct_from_a_failure() -> None:
    """A clean, current, genuinely empty surface is EMPTY_CONFIRMED, not UNAVAILABLE."""
    panel = _panel(fixtures.SURFACES["challenge"], fixtures.empty_challenge_payload())
    assert panel["state"] == EMPTY
    assert panel["available"] is True
    assert panel["item_count"] == 0
    assert panel["state"] != UNAVAILABLE
    gate.require_panel_identity(panel)


def test_degraded_panel_is_flagged_when_built_against_a_superseded_revision() -> None:
    panel = _panel(
        fixtures.SURFACES["lineages"],
        fixtures.lineage_payload(),
        current_revision="r2",
        source_revision="r1",
    )
    assert panel["state"] == DEGRADED
    assert panel["is_stale"] is True
    # DEGRADED is distinct from both EMPTY_CONFIRMED and UNAVAILABLE (EF4-I23).
    assert panel["state"] not in {EMPTY, UNAVAILABLE}


def test_absent_surface_is_unavailable_not_empty() -> None:
    panel = _panel(fixtures.SURFACES["niche"], None)
    assert panel["state"] == UNAVAILABLE
    assert panel["available"] is False
    assert panel["source_view_id"] is None
    assert panel["item_count"] is None


def test_matching_revision_is_not_degraded() -> None:
    panel = _panel(
        fixtures.SURFACES["pareto"],
        fixtures.pareto_payload(),
        current_revision="r1",
        source_revision="r1",
    )
    assert panel["state"] == POPULATED
    assert panel["is_stale"] is False


# -- determinism, freezing, immutability -----------------------------------


def test_panel_is_deterministic() -> None:
    first = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    second = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    assert first["panel_id"] == second["panel_id"]
    assert first["panel_hash"] == second["panel_hash"]
    assert gate._thaw(first) == gate._thaw(second)


def test_panel_and_dashboard_are_deep_frozen() -> None:
    panel = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    assert isinstance(panel, MappingProxyType)
    with pytest.raises(TypeError):
        panel["state"] = "tampered"  # type: ignore[index]
    dashboard = gate.compose_operator_dashboard(panels=[panel], created_at=CA)
    assert isinstance(dashboard, MappingProxyType)
    with pytest.raises((TypeError, AttributeError)):
        dashboard["panels"].append({})  # type: ignore[attr-defined]


def test_inputs_are_not_mutated() -> None:
    payload = fixtures.pareto_payload()
    guard = copy.deepcopy(payload)
    _panel(fixtures.SURFACES["pareto"], payload)
    assert payload == guard


# -- dashboard completeness is honest --------------------------------------


def test_dashboard_is_complete_only_when_every_surface_is_populated() -> None:
    panels = [
        _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload()),
        _panel(fixtures.SURFACES["niche"], fixtures.niche_payload()),
        _panel(fixtures.SURFACES["lineages"], fixtures.lineage_payload()),
        _panel(fixtures.SURFACES["challenge"], fixtures.challenge_payload()),
    ]
    dashboard = gate.compose_operator_dashboard(panels=panels, created_at=CA)
    assert dashboard["complete"] is True
    assert dashboard["counts"]["available"] == 4
    assert dashboard["unavailable_surfaces"] == ()
    gate.require_dashboard_identity(dashboard)
    gate.audit_dashboard_completeness(dashboard)


def test_dashboard_never_overstates_a_mixed_screen() -> None:
    panels = [
        _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload()),
        _panel(fixtures.SURFACES["niche"], None),  # unavailable
        _panel(fixtures.SURFACES["challenge"], fixtures.empty_challenge_payload()),
        _panel(
            fixtures.SURFACES["lineages"],
            fixtures.lineage_payload(),
            current_revision="r2",
            source_revision="r1",
        ),
    ]
    dashboard = gate.compose_operator_dashboard(panels=panels, created_at=CA)
    assert dashboard["complete"] is False
    assert dashboard["unavailable_surfaces"] == (fixtures.SURFACES["niche"],)
    assert dashboard["degraded_surfaces"] == (fixtures.SURFACES["lineages"],)
    assert dashboard["empty_surfaces"] == (fixtures.SURFACES["challenge"],)
    assert dict(dashboard["state_counts"]) == {
        POPULATED: 1,
        EMPTY: 1,
        DEGRADED: 1,
        UNAVAILABLE: 1,
    }
    gate.audit_dashboard_completeness(dashboard)


def test_dashboard_is_deterministic_and_order_independent() -> None:
    a = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    b = _panel(fixtures.SURFACES["niche"], None)
    first = gate.compose_operator_dashboard(panels=[a, b], created_at=CA)
    second = gate.compose_operator_dashboard(panels=[b, a], created_at=CA)
    assert first["dashboard_id"] == second["dashboard_id"]
    assert first["dashboard_hash"] == second["dashboard_hash"]


def test_dashboard_records_requesting_role_but_grants_nothing() -> None:
    panel = _panel(
        fixtures.SURFACES["challenge"],
        fixtures.challenge_payload(),
        requesting_role="ef-challenge-evolver",
    )
    dashboard = gate.compose_operator_dashboard(
        panels=[panel], created_at=CA, requesting_role="ef-challenge-evolver"
    )
    assert dashboard["requesting_role"] == "ef-challenge-evolver"
    assert dashboard["grants_authority"] is False
    assert dashboard["readonly"] is True
