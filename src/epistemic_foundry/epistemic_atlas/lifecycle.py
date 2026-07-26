"""Claim lifecycle transitions and retraction propagation.

Contract source: `schemas/claim-lifecycle-event.schema.json`.

Two rules are enforced beyond the schema shape:

* A retracted or rejected claim is terminal. Reviving it as `verified` would
  erase the retraction from the reader's view, so a new claim must supersede it
  instead.
* `superseded` requires a superseding claim id. A claim marked superseded by
  nothing has silently vanished from the atlas.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Statuses from which a claim does not return. Correcting the record means
#: issuing a new claim, not reopening a retraction.
TERMINAL_STATUSES: frozenset[str] = frozenset({"retracted", "rejected"})

#: Reason codes that indicate the underlying source changed under the claim.
SOURCE_INTEGRITY_REASONS: frozenset[str] = frozenset(
    {"source_corrected", "source_retracted"}
)


class LifecycleViolation(ValueError):
    """A claim transition would erase or orphan part of the record."""


def terminal_statuses() -> frozenset[str]:
    """Statuses a claim cannot transition out of."""
    return TERMINAL_STATUSES


def build_lifecycle_event(
    *,
    claim_id: str,
    claim_version: int,
    from_status: str | None,
    to_status: str,
    reason_code: str,
    reason_text: str,
    actor_id: str,
    superseding_claim_id: str | None = None,
    affected_evidence_ids: Sequence[str] = (),
    event_id: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Record one claim status transition.

    `reason_text` is required and non-empty: a reason code alone tells a later
    reader what category the change fell into but not why it was made.
    """
    if from_status in TERMINAL_STATUSES:
        raise LifecycleViolation(
            f"claim {claim_id} is {from_status}, which is terminal; issue a superseding claim "
            "rather than reopening the record"
        )
    if to_status == "superseded" and not superseding_claim_id:
        raise LifecycleViolation(
            f"claim {claim_id} cannot be superseded by nothing; a superseded claim with no "
            "successor has silently vanished from the atlas"
        )
    if not reason_text.strip():
        raise LifecycleViolation(
            "a lifecycle event requires reason_text; a reason_code alone does not explain why"
        )
    if reason_code in SOURCE_INTEGRITY_REASONS and not affected_evidence_ids:
        raise LifecycleViolation(
            f"reason {reason_code} requires affected_evidence_ids; a source change that lists "
            "no dependent evidence leaves stale support in place"
        )

    event: dict[str, Any] = {
        "event_id": event_id or new_id("CLE"),
        "claim_id": claim_id,
        "claim_version": int(claim_version),
        "from_status": from_status,
        "to_status": to_status,
        "reason_code": reason_code,
        "reason_text": reason_text,
        "superseding_claim_id": superseding_claim_id,
        "affected_evidence_ids": list(affected_evidence_ids),
        "actor_id": actor_id,
        "occurred_at": occurred_at or utc_now_iso(),
    }
    event["event_hash"] = hash_excluding(event, "event_hash")
    validate_artifact("claim-lifecycle-event", event)
    return event


def retraction_invalidates(
    events: Sequence[Mapping[str, Any]],
    evidence_nodes: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Evidence ids that must be invalidated because their source changed.

    Returns ids present in both the retraction events and the live evidence set,
    so a caller cannot mistake a stale id for a current dependency.
    """
    touched: set[str] = set()
    for event in events:
        if str(event.get("reason_code")) in SOURCE_INTEGRITY_REASONS:
            touched.update(str(item) for item in event.get("affected_evidence_ids", []))
    live = {str(node.get("evidence_id")) for node in evidence_nodes}
    return sorted(touched & live)


def unsearched_scopes_reported(snapshot: Mapping[str, Any]) -> bool:
    """True when the snapshot carries an explicit unsearched-scope field.

    Coverage before confidence: a snapshot that omits the field entirely lets an
    unsearched region read as an absence of counterevidence. An empty list is a
    legitimate claim (nothing left unsearched); a missing key is not.
    """
    return "unsearched_scopes" in snapshot
