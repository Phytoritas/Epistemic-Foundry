"""Negative and adversarial checks for the U06 gate.

Every finding code in :data:`FINDING_CODES` is triggered here, together with the
crash/resume path (a persisted panel and dashboard re-derive their identity after
a restart) and the adversarial paths that matter most for an honest console: a
tampered or absent upstream surface yields an honest ``UNAVAILABLE`` panel rather
than a fabricated healthy one, an authority grab is refused before any surface is
touched, and a dashboard cannot overstate the completeness of the panels it
embeds.
"""

from __future__ import annotations

import copy
import json

import fixtures
import pytest
from epistemic_foundry.console.v4_u06 import usability_gate as gate

CA = fixtures.CREATED_AT
POPULATED = str(gate.ResultState.POPULATED)
EMPTY = str(gate.ResultState.EMPTY_CONFIRMED)
UNAVAILABLE = str(gate.ResultState.UNAVAILABLE)


def _refuse(func, *args, **kwargs) -> str:
    with pytest.raises(gate.UsabilityGateError) as caught:
        func(*args, **kwargs)
    return caught.value.code


def _panel(surface, payload, **kw):
    return gate.build_operator_panel(
        surface=surface, payload=payload, created_at=CA, **kw
    )


# -- input shape / routing / authority ------------------------------------


def test_input_invalid_on_blank_requesting_role() -> None:
    assert (
        _refuse(
            gate.build_operator_panel,
            surface=fixtures.SURFACES["pareto"],
            payload=fixtures.pareto_payload(),
            created_at=CA,
            requesting_role="  ",
        )
        == "INPUT_INVALID"
    )


def test_input_invalid_on_non_sequence_panels() -> None:
    assert (
        _refuse(gate.compose_operator_dashboard, panels={"not": "seq"}, created_at=CA)
        == "INPUT_INVALID"
    )


def test_input_invalid_on_blank_created_at() -> None:
    assert (
        _refuse(
            gate.build_operator_panel,
            surface=fixtures.SURFACES["pareto"],
            payload=fixtures.pareto_payload(),
            created_at="   ",
        )
        == "INPUT_INVALID"
    )


def test_surface_undeclared_is_refused_not_degraded() -> None:
    """An undeclared surface is a malformed request, not a degradable panel."""
    assert (
        _refuse(
            gate.build_operator_panel,
            surface="bogus_surface",
            payload={},
            created_at=CA,
        )
        == "SURFACE_UNDECLARED"
    )


def test_promotion_authority_refused_on_panel() -> None:
    assert (
        _refuse(
            gate.build_operator_panel,
            surface=fixtures.SURFACES["pareto"],
            payload=fixtures.pareto_payload(),
            created_at=CA,
            authority_request="promote the front leader",
        )
        == "PROMOTION_AUTHORITY_REFUSED"
    )


def test_authority_request_is_refused_before_any_panel_is_touched() -> None:
    """Even garbage panels cannot slip past the authority boundary."""
    assert (
        _refuse(
            gate.compose_operator_dashboard,
            panels="not-even-a-sequence",
            created_at=CA,
            authority_request={"grant": "promotion"},
        )
        == "PROMOTION_AUTHORITY_REFUSED"
    )


# -- receipt integrity -----------------------------------------------------


def test_receipt_drift_on_tampered_panel() -> None:
    panel = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    tampered = gate._thaw(panel)
    tampered["item_count"] = 99  # forge a field, keep the stored hash
    assert _refuse(gate.require_panel_identity, tampered) == "RECEIPT_DRIFT"


def test_receipt_drift_on_tampered_dashboard() -> None:
    panel = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    dashboard = gate.compose_operator_dashboard(panels=[panel], created_at=CA)
    tampered = gate._thaw(dashboard)
    tampered["complete"] = False if tampered["complete"] else True
    assert _refuse(gate.require_dashboard_identity, tampered) == "RECEIPT_DRIFT"


def test_dashboard_subpanel_tampered() -> None:
    panel = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    tampered = gate._thaw(panel)
    tampered["state"] = POPULATED  # unchanged value, but re-hash won't be redone
    tampered["item_count"] = 12345
    assert (
        _refuse(gate.compose_operator_dashboard, panels=[tampered], created_at=CA)
        == "DASHBOARD_SUBPANEL_TAMPERED"
    )


def test_dishonest_state_is_refused() -> None:
    """A failure may not be dressed as an emptiness or a populated finding."""
    assert (
        _refuse(
            gate._guard_honest_state,
            gate.ResultState.EMPTY_CONFIRMED,
            backend_error="the backend errored",
        )
        == "DISHONEST_STATE_REFUSED"
    )


def test_completeness_cannot_be_overstated() -> None:
    """A dashboard resealed to claim completeness over a bad panel is refused."""
    good = _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload())
    absent = _panel(fixtures.SURFACES["niche"], None)
    dashboard = gate.compose_operator_dashboard(panels=[good, absent], created_at=CA)

    forged = gate._thaw(dashboard)
    forged["complete"] = True
    forged["unavailable_surfaces"] = []
    del forged["dashboard_id"]
    del forged["dashboard_hash"]
    forged["dashboard_id"] = gate.DASHBOARD_ID_PREFIX + gate._digest_body(forged)
    forged["dashboard_hash"] = gate.hash_excluding(forged, "dashboard_hash")

    # The forgery re-derives its own identity: the hash check passes.
    gate.require_dashboard_identity(forged)
    # But the independent completeness audit recomputes from the panels and refuses.
    assert (
        _refuse(gate.audit_dashboard_completeness, forged) == "COMPLETENESS_OVERSTATED"
    )


def test_every_finding_code_is_exercised() -> None:
    """Guard: the negatives above must cover the whole catalogue."""
    exercised = {
        "INPUT_INVALID",
        "SURFACE_UNDECLARED",
        "PROMOTION_AUTHORITY_REFUSED",
        "RECEIPT_DRIFT",
        "DASHBOARD_SUBPANEL_TAMPERED",
        "DISHONEST_STATE_REFUSED",
        "COMPLETENESS_OVERSTATED",
    }
    assert exercised == set(gate.FINDING_CODES)


def test_undeclared_finding_code_cannot_be_raised() -> None:
    assert (
        _refuse(gate._fail, "NOT_A_REAL_CODE", "should not escape") == "INPUT_INVALID"
    )


# -- honest degradation: a bad upstream never becomes a healthy panel ------


def test_tampered_upstream_yields_honest_unavailable_not_healthy() -> None:
    """A drifted snapshot must degrade honestly, never fabricate a populated panel."""
    snapshot = fixtures.pareto_snapshot()
    snapshot["hypervolume"] = 0.999  # sealed hash no longer matches the content
    panel = _panel(fixtures.SURFACES["pareto"], {"snapshot": snapshot})
    assert panel["state"] == UNAVAILABLE
    assert panel["available"] is False
    assert panel["state"] not in {POPULATED, EMPTY}
    assert panel["finding_code"] == "SNAPSHOT_DRIFT"
    assert panel["source_view_id"] is None  # nothing was projected
    gate.require_panel_identity(panel)


def test_absent_upstream_yields_unavailable_never_empty_confirmed() -> None:
    """EF4-I23: a missing surface is UNAVAILABLE, never a confirmed emptiness."""
    panel = _panel(fixtures.SURFACES["challenge"], None)
    assert panel["state"] == UNAVAILABLE
    assert panel["state"] != EMPTY


def test_malformed_upstream_payload_yields_unavailable() -> None:
    panel = _panel(fixtures.SURFACES["niche"], "not-a-mapping")
    assert panel["state"] == UNAVAILABLE
    assert panel["available"] is False


def test_upstream_input_is_not_mutated_on_degradation() -> None:
    snapshot = fixtures.pareto_snapshot()
    snapshot["hypervolume"] = 0.999
    payload = {"snapshot": snapshot}
    before = copy.deepcopy(payload)
    _panel(fixtures.SURFACES["pareto"], payload)
    assert payload == before


# -- crash / resume --------------------------------------------------------


def test_persisted_panel_re_derives_after_restart() -> None:
    panel = _panel(fixtures.SURFACES["niche"], fixtures.niche_payload())
    on_disk = json.dumps(gate._thaw(panel), sort_keys=True)
    recovered = gate.require_panel_identity(json.loads(on_disk))
    assert recovered["panel_id"] == panel["panel_id"]
    assert recovered["panel_hash"] == panel["panel_hash"]


def test_persisted_dashboard_re_derives_after_restart() -> None:
    panels = [
        _panel(fixtures.SURFACES["pareto"], fixtures.pareto_payload()),
        _panel(fixtures.SURFACES["niche"], None),
    ]
    dashboard = gate.compose_operator_dashboard(panels=panels, created_at=CA)
    on_disk = json.dumps(gate._thaw(dashboard), sort_keys=True)
    recovered = gate.require_dashboard_identity(json.loads(on_disk))
    assert recovered["dashboard_id"] == dashboard["dashboard_id"]
    gate.audit_dashboard_completeness(recovered)
