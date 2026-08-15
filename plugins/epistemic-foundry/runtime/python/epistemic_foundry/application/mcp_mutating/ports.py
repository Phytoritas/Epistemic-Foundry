"""Injected ports for the T02 mutation lifecycle.

Every authority and evidence artifact is created by the server behind these
ports.  A client may never supply a CapabilityLease or an EffectReceipt, and
no port here reaches a live store: kernel binding is a later work package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

#: EffectReceipt statuses (schemas/effect-receipt.schema.json).  This module is
#: the single declaring site for the effect-status vocabulary in this package;
#: everything else derives from these names and the projection below.
EFFECT_STATUSES: Final = (
    "SUCCEEDED",
    "FAILED",
    "UNKNOWN",
    "ROLLED_BACK",
    "NOT_EXECUTED",
)
#: The one status that leaves the obligation open.
UNRESOLVED_STATUS: Final = "UNKNOWN"
#: status -> (committed, reconciliation_required).  ``committed`` is tri-state:
#: an unresolved effect is never rendered as ``False``, which would falsely
#: claim that nothing happened.
STATUS_PROJECTION: Final = {
    status: (
        None if status == UNRESOLVED_STATUS else status == EFFECT_STATUSES[0],
        status == UNRESOLVED_STATUS,
    )
    for status in EFFECT_STATUSES
}
#: The synthetic operation id a dry run records instead of a real effect.
DRY_RUN_OPERATION_ID: Final = "urn:epistemic-foundry:non-effect:dry-run"
@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Result of policy evaluation for one candidate mutation."""

    required_capabilities: tuple[str, ...]
    required_approval_count: int
    policy_hash: str
    risk_class: str
    max_lease_seconds: int = 300


@dataclass(frozen=True, slots=True)
class ApprovalVerdict:
    """Verified approval evidence for one candidate mutation.

    ``approver_ids`` are returned so the service itself rejects self-approval
    rather than trusting the resolver to have done it.
    """

    approval_ids: tuple[str, ...]
    verified: bool
    approver_ids: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class LeaseGrant:
    """A server-issued capability lease covering the exact target scope."""

    lease_id: str
    capabilities: tuple[str, ...]
    resource_scopes: tuple[str, ...]
    expires_at: str
    fencing_token: int
    policy_hash: str
    approval_ids: tuple[str, ...]
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class Reservation:
    """Idempotency reservation for one semantic request fingerprint."""

    idempotency_key: str
    fingerprint: str
    created: bool
    revision: int = 0
    stored_intent_id: str | None = None
    stored_attempt_id: str | None = None
    stored_receipt_id: str | None = None


@dataclass(frozen=True, slots=True)
class AttemptTransition:
    """Linearizable durable-Attempt transition for one reservation."""

    attempt: Mapping[str, Any]
    attempt_id: str
    intent_id: str
    started_at: str
    reservation: Reservation
    execute_permitted: bool


@dataclass(frozen=True, slots=True)
class EffectOutcome:
    """The adapter's report of an attempted external effect.

    ``FAILED`` requires affirmative proof that nothing was committed.  Without
    that proof the adapter must report ``UNKNOWN``, which keeps the obligation
    open instead of claiming the effect did not happen.
    """

    status: str
    external_operation_id: str | None
    observed_state_hash: str
    new_revision: str | None = None
    result_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    error_artifact_ids: tuple[str, ...] = field(default_factory=tuple)


class PolicyEvaluatorPort(Protocol):
    def evaluate(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> PolicyDecision: ...


class ApprovalResolverPort(Protocol):
    def verify(
        self,
        *,
        operation: str,
        candidate_id: str,
        approval_record_ids: Sequence[str],
        principal_id: str,
        policy: PolicyDecision,
    ) -> ApprovalVerdict: ...


class CapabilityLeasePort(Protocol):
    def issue(
        self,
        *,
        principal_id: str,
        workspace_id: str,
        target_ref: str,
        policy: PolicyDecision,
        approval_ids: Sequence[str],
    ) -> LeaseGrant: ...

    def revalidate(self, lease: LeaseGrant, *, at: str) -> LeaseGrant: ...


class IdempotencyReservationPort(Protocol):
    """Monotonic lifecycle CAS; only a fresh durable Attempt permits execution."""

    def reserve(self, *, idempotency_key: str, fingerprint: str) -> Reservation: ...

    def bind_intent(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        expected_revision: int,
        intent_id: str,
    ) -> Reservation: ...

    def begin_attempt(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        expected_revision: int,
        intent_id: str,
        intent_hash: str,
        attempt_id: str,
        started_at: str,
        dry_run: bool,
    ) -> AttemptTransition: ...

    def bind_receipt(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        expected_revision: int,
        attempt_id: str,
        receipt_id: str,
    ) -> Reservation: ...


class RevisionPort(Protocol):
    def current(self, *, workspace_id: str, target_ref: str) -> str | None: ...


class ActionIntentStorePort(Protocol):
    """Create-or-load immutable ActionIntents by deterministic identity."""

    def persist(self, intent: Mapping[str, Any]) -> Mapping[str, Any]: ...


class EffectExecutorPort(Protocol):
    def execute(
        self,
        *,
        operation: str,
        intent: Mapping[str, Any],
        lease: LeaseGrant,
        arguments: Mapping[str, Any],
    ) -> EffectOutcome: ...

    def preview(
        self,
        *,
        operation: str,
        intent: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any] | None: ...


class EffectReceiptStorePort(Protocol):
    """Append-only Attempt receipt lineage with deterministic current tails."""

    def persist(
        self, receipt: Mapping[str, Any], *, attempt_id: str | None = None
    ) -> Mapping[str, Any]: ...

    def find(self, receipt_id: str) -> Mapping[str, Any] | None: ...

    def find_for_attempt(self, attempt_id: str) -> Mapping[str, Any] | None: ...

    def precedes(
        self, *, attempt_id: str, receipt_id: str, tail_receipt_id: str
    ) -> bool: ...
