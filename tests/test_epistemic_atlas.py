"""Retractions propagate; terminal statuses stay terminal."""

from __future__ import annotations

import pytest

from epistemic_foundry.epistemic_atlas import (
    LifecycleViolation,
    build_lifecycle_event,
    retraction_invalidates,
    terminal_statuses,
)
from epistemic_foundry.epistemic_atlas.lifecycle import unsearched_scopes_reported


def _event(**overrides) -> dict:
    kwargs = dict(
        claim_id="CLM-0001",
        claim_version=1,
        from_status="candidate",
        to_status="verified",
        reason_code="grounding_verified",
        reason_text="all source spans re-read and matched",
        actor_id="ACTOR-reviewer",
    )
    kwargs.update(overrides)
    return build_lifecycle_event(**kwargs)


# -- transitions --------------------------------------------------------


def test_ordinary_transition_is_recorded() -> None:
    event = _event()
    assert event["to_status"] == "verified"
    assert event["event_hash"].startswith("sha256:")


def test_claim_creation_allows_a_null_from_status() -> None:
    event = _event(from_status=None, reason_code="created", reason_text="extracted from PV-001-01")
    assert event["from_status"] is None


@pytest.mark.parametrize("status", sorted(terminal_statuses()))
def test_terminal_status_cannot_be_reopened(status: str) -> None:
    """Reviving a retraction would erase it from the reader's view."""
    with pytest.raises(LifecycleViolation) as excinfo:
        _event(from_status=status, to_status="verified")
    assert "terminal" in str(excinfo.value)


def test_supersede_requires_a_successor() -> None:
    """A superseded claim with no successor has vanished from the atlas."""
    with pytest.raises(LifecycleViolation) as excinfo:
        _event(to_status="superseded", reason_code="duplicate_merge", reason_text="merged")
    assert "superseded by nothing" in str(excinfo.value)


def test_supersede_with_a_successor_is_allowed() -> None:
    event = _event(
        to_status="superseded",
        reason_code="duplicate_merge",
        reason_text="merged into CLM-0002",
        superseding_claim_id="CLM-0002",
    )
    assert event["superseding_claim_id"] == "CLM-0002"


def test_reason_text_is_required() -> None:
    with pytest.raises(LifecycleViolation):
        _event(reason_text="   ")


# -- retraction propagation --------------------------------------------


def test_source_retraction_must_name_affected_evidence() -> None:
    """A source change listing no dependents leaves stale support in place."""
    with pytest.raises(LifecycleViolation) as excinfo:
        _event(
            to_status="retracted",
            reason_code="source_retracted",
            reason_text="publisher retracted PV-001-01",
            affected_evidence_ids=[],
        )
    assert "leaves stale support in place" in str(excinfo.value)


def test_source_correction_also_requires_affected_evidence() -> None:
    with pytest.raises(LifecycleViolation):
        _event(
            reason_code="source_corrected",
            reason_text="erratum issued",
            affected_evidence_ids=[],
        )


def test_retraction_invalidates_only_live_evidence() -> None:
    events = [
        _event(
            to_status="retracted",
            reason_code="source_retracted",
            reason_text="publisher retracted PV-001-01",
            affected_evidence_ids=["EV-1", "EV-2", "EV-gone"],
        )
    ]
    live = [{"evidence_id": "EV-1"}, {"evidence_id": "EV-2"}, {"evidence_id": "EV-3"}]
    assert retraction_invalidates(events, live) == ["EV-1", "EV-2"]


def test_non_source_reasons_do_not_invalidate_evidence() -> None:
    events = [_event(affected_evidence_ids=["EV-1"])]
    assert retraction_invalidates(events, [{"evidence_id": "EV-1"}]) == []


# -- coverage accounting ------------------------------------------------


def test_missing_unsearched_scopes_is_not_reported_coverage() -> None:
    """An omitted field lets an unsearched region read as no counterevidence."""
    assert unsearched_scopes_reported({"axes": []}) is False


def test_empty_unsearched_scopes_is_a_legitimate_claim() -> None:
    assert unsearched_scopes_reported({"unsearched_scopes": []}) is True
