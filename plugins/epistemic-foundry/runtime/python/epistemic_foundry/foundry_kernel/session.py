"""FORGE session authority: optimistic concurrency plus gate-backed advance.

Contract sources: `schemas/forge-session-state.schema.json` and
`schemas/forge-transition-request.schema.json`.

Three refusals define this component:

* A stale `expected_revision` is a conflict, not a retry. Two actors advancing
  the same session from the same revision must not both win.
* An illegal phase edge is refused even when every receipt is present.
* Entering Export without a passing gate result is refused. This is the
  promotion boundary: receipts and gates, never confidence.

Each accepted transition appends one event to the Noetic Ledger before the new
state is returned, so history exists for every state change.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.status import ActorType, ForgePhase, SessionStatus, WorkClass
from ..domain.time import utc_now_iso
from ..noetic_ledger import NoeticLedger
from .gates import SATISFIED_GATE_STATUSES, all_passed
from .transitions import (
    ILLEGAL_TRANSITION_REASON,
    allowed_targets,
    is_legal_transition,
    requires_gate_evidence,
)

SESSION_SCHEMA = "forge-session-state"
REQUEST_SCHEMA = "forge-transition-request"


class RevisionConflict(RuntimeError):
    """The request's `expected_revision` does not match current state."""


class TransitionRejected(RuntimeError):
    """The requested transition violates the lifecycle or gate contract."""


class ForgeKernel:
    """Owns one session's canonical state and its transition authority."""

    def __init__(self, ledger: NoeticLedger) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> NoeticLedger:
        return self._ledger

    # -- state construction ---------------------------------------------

    def open_session(
        self,
        *,
        workspace_id: str,
        run_spec_id: str,
        work_class: WorkClass,
        policy_hash: str,
        corpus_snapshot_hash: str,
        session_id: str | None = None,
        actor_id: str = "ACTOR-kernel",
    ) -> dict[str, Any]:
        """Create an IDLE session at revision 0 and record its creation."""
        state: dict[str, Any] = {
            "session_id": session_id or new_id("FS"),
            "workspace_id": workspace_id,
            "revision": 0,
            "phase": str(ForgePhase.IDLE),
            "work_class": str(work_class),
            "status": str(SessionStatus.ACTIVE),
            "run_spec_id": run_spec_id,
            "hypothesis_revision_ids": [],
            "artifact_ids": [],
            "open_blockers": [],
            "phase_history": [],
            "policy_hash": policy_hash,
            "corpus_snapshot_hash": corpus_snapshot_hash,
            "updated_at": utc_now_iso(),
        }
        state["state_hash"] = hash_excluding(state, "state_hash")
        validate_artifact(SESSION_SCHEMA, state)
        self._ledger.append(
            event_type="forge.session.opened",
            aggregate_type="forge_session",
            aggregate_id=state["session_id"],
            actor_id=actor_id,
            run_id=run_spec_id,
            payload=state,
        )
        return state

    def build_request(
        self,
        state: dict[str, Any],
        *,
        to_phase: ForgePhase,
        actor_id: str,
        actor_role: str,
        reason: str,
        actor_type: str = ActorType.AGENT.value,
        artifact_receipt_ids: Sequence[str] = (),
        gate_result_ids: Sequence[str] = (),
        human_decision_id: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Render a schema-valid transition request against `state`."""
        request: dict[str, Any] = {
            "request_id": new_id("FTR"),
            "session_id": state["session_id"],
            "expected_revision": state["revision"] if expected_revision is None else expected_revision,
            "from_phase": state["phase"],
            "to_phase": str(to_phase),
            "actor": {"actor_id": actor_id, "actor_type": actor_type, "role": actor_role},
            "artifact_receipt_ids": list(artifact_receipt_ids),
            "gate_result_ids": list(gate_result_ids),
            "human_decision_id": human_decision_id,
            "reason": reason,
            "idempotency_key": new_id("idem", entropy_bytes=8),
            "requested_at": utc_now_iso(),
        }
        validate_artifact(REQUEST_SCHEMA, request)
        return request

    # -- transition authority -------------------------------------------

    def apply_transition(
        self,
        state: dict[str, Any],
        request: dict[str, Any],
        *,
        gate_decisions: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        """Validate and apply one transition; return the new state.

        The supplied `state` is never mutated: a rejected transition must leave
        the caller's view of canonical state untouched.
        """
        validate_artifact(SESSION_SCHEMA, state)
        validate_artifact(REQUEST_SCHEMA, request)

        if request["session_id"] != state["session_id"]:
            raise TransitionRejected(
                f"request targets session {request['session_id']!r}, state is {state['session_id']!r}"
            )

        if int(request["expected_revision"]) != int(state["revision"]):
            raise RevisionConflict(
                f"expected_revision {request['expected_revision']} != current revision "
                f"{state['revision']}; refetch state and retry"
            )

        from_phase = ForgePhase(state["phase"])
        to_phase = ForgePhase(request["to_phase"])

        if ForgePhase(request["from_phase"]) is not from_phase:
            raise TransitionRejected(
                f"request from_phase {request['from_phase']!r} does not match state phase "
                f"{state['phase']!r}"
            )

        if not is_legal_transition(from_phase, to_phase):
            legal = ", ".join(sorted(str(phase) for phase in allowed_targets(from_phase)))
            raise TransitionRejected(
                f"{ILLEGAL_TRANSITION_REASON}: {from_phase} -> {to_phase}; legal targets: {legal or 'none'}"
            )

        if requires_gate_evidence(to_phase):
            if not request["gate_result_ids"]:
                raise TransitionRejected(
                    f"entering {to_phase} requires gate_result_ids; refusing promotion without gate evidence"
                )
            if not gate_decisions:
                raise TransitionRejected(
                    f"entering {to_phase} requires resolving gate decisions, none supplied"
                )
            supplied_ids = {decision.get("gate_id") for decision in gate_decisions}
            unresolved = [rid for rid in request["gate_result_ids"] if rid not in supplied_ids]
            if unresolved:
                raise TransitionRejected(
                    f"gate_result_ids do not resolve to supplied decisions: {sorted(unresolved)}"
                )
            if not all_passed(gate_decisions):
                failing = [
                    f"{decision.get('name')}={decision.get('status')}"
                    for decision in gate_decisions
                    if decision.get("status") not in SATISFIED_GATE_STATUSES
                ]
                raise TransitionRejected(
                    f"refusing {to_phase}: unsatisfied gate(s) {', '.join(failing)}"
                )

        event = self._ledger.append(
            event_type=f"forge.phase.{from_phase.value.lower()}_to_{to_phase.value.lower()}",
            aggregate_type="forge_session",
            aggregate_id=state["session_id"],
            actor_id=request["actor"]["actor_id"],
            run_id=state["run_spec_id"],
            payload=request,
        )

        new_state = dict(state)
        new_state["revision"] = int(state["revision"]) + 1
        new_state["phase"] = str(to_phase)
        new_state["phase_history"] = list(state["phase_history"]) + [
            {
                "from": str(from_phase),
                "to": str(to_phase),
                "event_id": event["event_id"],
                "at": event["occurred_at"],
            }
        ]
        new_state["updated_at"] = utc_now_iso()
        new_state.pop("state_hash", None)
        new_state["state_hash"] = hash_excluding(new_state, "state_hash")
        validate_artifact(SESSION_SCHEMA, new_state)
        return new_state
