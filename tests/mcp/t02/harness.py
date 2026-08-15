"""In-memory authority and evidence ports for the T02 lifecycle tests.

Nothing here reaches a live store: kernel binding is T04/T05.  The fakes are
deliberately strict — they record what was asked of them so a test can prove
that an effect was never attempted, not merely that it did not succeed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from epistemic_foundry.application.mcp_common import AuthContext, ToolService
from epistemic_foundry.application.mcp_common.contracts import (
    canonical_json_bytes,
    sha256_id,
)
from epistemic_foundry.application.mcp_mutating import (
    ApprovalVerdict,
    AttemptTransition,
    EffectOutcome,
    LeaseGrant,
    PolicyDecision,
    Reservation,
)

ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = "ws-t02"
PRINCIPAL = "principal-maker"
APPROVER = "principal-approver"
TARGET = "target-alpha"
FIXED_HASH = "sha256:" + "0" * 64
#: Approvals a policy demands for each catalog approval class.
APPROVALS_BY_CLASS = {
    "POLICY_CONDITIONAL": 0,
    "CONSENT_REQUIRED": 1,
    "HUMAN_REQUIRED": 1,
}


def sample_arguments(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Derive a schema-valid business-argument object from the catalog schema."""

    properties = schema["properties"]["arguments"]["properties"]
    built: dict[str, Any] = {}
    for key, declared in properties.items():
        if "enum" in declared:
            built[key] = declared["enum"][0]
        elif declared.get("pattern", "").startswith("^sha256:"):
            built[key] = FIXED_HASH
        else:
            built[key] = f"{key}-1"
    return built


def call_arguments(
    catalog: Any,
    tool: str,
    *,
    dry_run: bool = False,
    idempotency_key: str = "key-1",
    approval_record_ids: Sequence[str] = (),
    expected_revision: str | None = "rev-1",
    target_ref: str = TARGET,
    workspace_id: str = WORKSPACE,
) -> dict[str, Any]:
    """A complete, schema-valid call payload for one mutating tool."""

    schema = catalog.input_schema(tool)
    spec = catalog.spec(tool)
    return {
        "approval_record_ids": list(approval_record_ids),
        "arguments": sample_arguments(schema),
        "dry_run": dry_run,
        "expected_revision": expected_revision
        if spec.expected_revision_required
        else None,
        "idempotency_key": idempotency_key,
        "target_ref": target_ref,
        "workspace_id": workspace_id,
    }


class FakePolicyEvaluator:
    def __init__(self, catalog: Any, *, grant_capability: bool = True) -> None:
        self._by_operation = {
            spec.handler_operation: spec for spec in catalog.tools.values()
        }
        self._grant = grant_capability
        self.calls: list[str] = []

    def evaluate(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> PolicyDecision:
        self.calls.append(operation)
        spec = self._by_operation[operation]
        return PolicyDecision(
            max_lease_seconds=300,
            policy_hash=FIXED_HASH,
            required_approval_count=APPROVALS_BY_CLASS[spec.approval_class],
            required_capabilities=(spec.capability,)
            if self._grant
            else ("mcp.write.none",),
            risk_class=spec.risk_class,
        )


@dataclass
class ApprovalRecord:
    approval_id: str
    approver_id: str
    operation: str
    valid: bool = True


class FakeApprovalResolver:
    def __init__(self, records: Sequence[ApprovalRecord] = ()) -> None:
        self._records = {record.approval_id: record for record in records}
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def verify(
        self,
        *,
        operation: str,
        candidate_id: str,
        approval_record_ids: Sequence[str],
        principal_id: str,
        policy: PolicyDecision,
    ) -> ApprovalVerdict:
        self.calls.append((operation, tuple(approval_record_ids)))
        resolved = [self._records.get(identifier) for identifier in approval_record_ids]
        if any(record is None for record in resolved):
            # An inaccessible record is not disclosed as missing.
            return ApprovalVerdict(
                approval_ids=(),
                code="APPROVAL_INVALID",
                reason="approval evidence did not resolve",
                verified=False,
            )
        if any(not record.valid for record in resolved):
            return ApprovalVerdict(
                approval_ids=(),
                code="APPROVAL_DENIED",
                reason="an approval record is denied or expired",
                verified=False,
            )
        if any(record.operation != operation for record in resolved):
            return ApprovalVerdict(
                approval_ids=(),
                code="APPROVAL_INVALID",
                reason="approval evidence is bound to a different operation",
                verified=False,
            )
        return ApprovalVerdict(
            approval_ids=tuple(record.approval_id for record in resolved),
            approver_ids=tuple(record.approver_id for record in resolved),
            verified=True,
        )


class FakeLeaseIssuer:
    def __init__(
        self,
        *,
        scope_override: str | None = None,
        revoke_before_effect: bool = False,
        drop_approval_binding: bool = False,
    ) -> None:
        self._scope_override = scope_override
        self._revoke = revoke_before_effect
        self._drop_binding = drop_approval_binding
        self.issued: list[LeaseGrant] = []
        self.revalidations = 0

    def issue(
        self,
        *,
        principal_id: str,
        workspace_id: str,
        target_ref: str,
        policy: PolicyDecision,
        approval_ids: Sequence[str],
    ) -> LeaseGrant:
        scope = self._scope_override or f"{workspace_id}:{target_ref}"
        grant = LeaseGrant(
            approval_ids=() if self._drop_binding else tuple(approval_ids),
            capabilities=tuple(policy.required_capabilities),
            expires_at="2026-08-01T09:00:00Z",
            fencing_token=len(self.issued) + 1,
            lease_id=f"lease-{len(self.issued) + 1}",
            policy_hash=policy.policy_hash,
            resource_scopes=(scope,),
        )
        self.issued.append(grant)
        return grant

    def revalidate(self, lease: LeaseGrant, *, at: str) -> LeaseGrant:
        self.revalidations += 1
        if self._revoke:
            return LeaseGrant(
                approval_ids=lease.approval_ids,
                capabilities=lease.capabilities,
                expires_at=lease.expires_at,
                fencing_token=lease.fencing_token,
                lease_id=lease.lease_id,
                policy_hash=lease.policy_hash,
                resource_scopes=lease.resource_scopes,
                revoked=True,
            )
        return lease


class FakeIdempotencyStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.attempts: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _attempt_record(
        *,
        attempt_id: str,
        fingerprint: str,
        idempotency_key: str,
        intent_id: str,
        started_at: str,
    ) -> dict[str, Any]:
        record = {
            "attempt_id": attempt_id,
            "attempt_number": 1,
            "idempotency_key": idempotency_key,
            "intent_hash": fingerprint,
            "intent_id": intent_id,
            "run_id": "run-t02",
            "started_at": started_at,
        }
        record["attempt_hash"] = sha256_id(canonical_json_bytes(record))
        return record

    def seed(
        self,
        key: str,
        fingerprint: str,
        *,
        intent_id: str | None,
        attempt_id: str | None = None,
        receipt_id: str | None,
    ) -> None:
        self.records[key] = {
            "attempt_id": attempt_id,
            "fingerprint": fingerprint,
            "intent_id": intent_id,
            "receipt_id": receipt_id,
            "revision": sum(
                entry is not None for entry in (intent_id, attempt_id, receipt_id)
            ),
        }
        if attempt_id is not None:
            if intent_id is None:
                raise ValueError("an Attempt requires an ActionIntent")
            self.attempts[attempt_id] = self._attempt_record(
                attempt_id=attempt_id,
                fingerprint=fingerprint,
                idempotency_key=key,
                intent_id=intent_id,
                started_at="2026-08-01T08:00:00Z",
            )

    def _reservation(self, key: str, *, created: bool = False) -> Reservation:
        record = self.records[key]
        return Reservation(
            created=created,
            fingerprint=str(record["fingerprint"]),
            idempotency_key=key,
            revision=int(record["revision"]),
            stored_attempt_id=record["attempt_id"],
            stored_intent_id=record["intent_id"],
            stored_receipt_id=record["receipt_id"],
        )

    def _current(
        self, key: str, fingerprint: str, expected_revision: int
    ) -> dict[str, Any]:
        record = self.records[key]
        if record["fingerprint"] != fingerprint:
            raise RuntimeError("idempotency fingerprint conflict")
        if record["revision"] != expected_revision:
            raise RuntimeError("stale idempotency reservation revision")
        return record

    def reserve(self, *, idempotency_key: str, fingerprint: str) -> Reservation:
        existing = self.records.get(idempotency_key)
        if existing is None:
            self.records[idempotency_key] = {
                "attempt_id": None,
                "fingerprint": fingerprint,
                "intent_id": None,
                "receipt_id": None,
                "revision": 0,
            }
            return self._reservation(idempotency_key, created=True)
        return self._reservation(idempotency_key)

    def bind_intent(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        expected_revision: int,
        intent_id: str,
    ) -> Reservation:
        record = self.records[idempotency_key]
        if record["fingerprint"] != fingerprint:
            raise RuntimeError("idempotency fingerprint conflict")
        if record["intent_id"] is not None:
            if record["intent_id"] != intent_id:
                raise RuntimeError("ActionIntent identity conflict")
            return self._reservation(idempotency_key)
        record = self._current(idempotency_key, fingerprint, expected_revision)
        record["intent_id"] = intent_id
        record["revision"] += 1
        return self._reservation(idempotency_key)

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
    ) -> AttemptTransition:
        record = self.records[idempotency_key]
        if record["fingerprint"] != fingerprint:
            raise RuntimeError("idempotency fingerprint conflict")
        if record["intent_id"] != intent_id:
            raise RuntimeError("Attempt ActionIntent binding conflict")
        if record["attempt_id"] is not None:
            if record["attempt_id"] != attempt_id:
                raise RuntimeError("Attempt identity conflict")
            stored = self.attempts[attempt_id]
            return AttemptTransition(
                attempt=dict(stored),
                attempt_id=attempt_id,
                execute_permitted=False,
                intent_id=intent_id,
                reservation=self._reservation(idempotency_key),
                started_at=str(stored["started_at"]),
            )
        record = self._current(idempotency_key, fingerprint, expected_revision)
        self.attempts[attempt_id] = self._attempt_record(
            attempt_id=attempt_id,
            fingerprint=intent_hash,
            idempotency_key=idempotency_key,
            intent_id=intent_id,
            started_at=started_at,
        )
        record["attempt_id"] = attempt_id
        record["revision"] += 1
        return AttemptTransition(
            attempt=dict(self.attempts[attempt_id]),
            attempt_id=attempt_id,
            execute_permitted=True,
            intent_id=intent_id,
            reservation=self._reservation(idempotency_key),
            started_at=started_at,
        )

    def bind_receipt(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        expected_revision: int,
        attempt_id: str,
        receipt_id: str,
    ) -> Reservation:
        record = self.records[idempotency_key]
        if record["fingerprint"] != fingerprint:
            raise RuntimeError("idempotency fingerprint conflict")
        if record["attempt_id"] != attempt_id:
            raise RuntimeError("EffectReceipt Attempt binding conflict")
        if record["receipt_id"] is not None:
            if record["receipt_id"] != receipt_id:
                raise RuntimeError("EffectReceipt identity conflict")
            return self._reservation(idempotency_key)
        record = self._current(idempotency_key, fingerprint, expected_revision)
        record["receipt_id"] = receipt_id
        record["revision"] += 1
        return self._reservation(idempotency_key)


class FakeRevisionStore:
    def __init__(
        self, revisions: Mapping[tuple[str, str], str | None] | None = None
    ) -> None:
        self.revisions = dict(revisions or {})

    def current(self, *, workspace_id: str, target_ref: str) -> str | None:
        return self.revisions.get((workspace_id, target_ref), "rev-1")


class FakeIntentStore:
    def __init__(self) -> None:
        self.intents: list[dict[str, Any]] = []

    def persist(self, intent: Mapping[str, Any]) -> Mapping[str, Any]:
        stored = dict(intent)
        intent_id = str(stored["intent_id"])
        existing = self.find(intent_id)
        if existing is not None:
            if dict(existing) != stored:
                raise RuntimeError("ActionIntent identity conflict")
            return existing
        self.intents.append(stored)
        return stored

    def find(self, intent_id: str) -> Mapping[str, Any] | None:
        for intent in self.intents:
            if intent["intent_id"] == intent_id:
                return intent
        return None


@dataclass
class FakeExecutor:
    outcome: EffectOutcome | None = None
    executions: list[str] = field(default_factory=list)
    previews: list[str] = field(default_factory=list)

    def execute(
        self,
        *,
        operation: str,
        intent: Mapping[str, Any],
        lease: LeaseGrant,
        arguments: Mapping[str, Any],
    ) -> EffectOutcome:
        self.executions.append(operation)
        return self.outcome or EffectOutcome(
            external_operation_id=f"op-{len(self.executions)}",
            new_revision="rev-2",
            observed_state_hash=FIXED_HASH,
            status="SUCCEEDED",
        )

    def preview(
        self,
        *,
        operation: str,
        intent: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.previews.append(operation)
        return {"would_change": sorted(arguments)}


class FakeReceiptStore:
    def __init__(self) -> None:
        self.receipts: list[dict[str, Any]] = []
        self.attempt_tails: dict[str, str] = {}
        self.receipt_attempts: dict[str, str] = {}

    def persist(
        self, receipt: Mapping[str, Any], *, attempt_id: str | None = None
    ) -> Mapping[str, Any]:
        predecessor = receipt.get("reconciles_receipt_id")
        if attempt_id is None and predecessor is not None:
            attempt_id = self.receipt_attempts.get(str(predecessor))
            if attempt_id is None:
                raise RuntimeError("reconciliation predecessor is not Attempt-bound")
        if attempt_id is not None and predecessor is None:
            receipt_id = f"receipt-{attempt_id}"
        else:
            receipt_id = f"receipt-{len(self.receipts) + 1}"
        stored = {**receipt, "receipt_id": receipt_id}
        existing = self.find(receipt_id)
        if existing is not None:
            if dict(existing) != stored:
                raise RuntimeError("EffectReceipt identity conflict")
            return existing
        if (
            attempt_id is not None
            and predecessor is None
            and attempt_id in self.attempt_tails
        ):
            raise RuntimeError("Attempt already has an execution receipt")
        self.receipts.append(stored)
        if attempt_id is not None:
            self.receipt_attempts[receipt_id] = attempt_id
            self.attempt_tails[attempt_id] = receipt_id
        return stored

    def find(self, receipt_id: str) -> Mapping[str, Any] | None:
        for receipt in self.receipts:
            if receipt["receipt_id"] == receipt_id:
                return receipt
        return None

    def find_for_attempt(self, attempt_id: str) -> Mapping[str, Any] | None:
        receipt_id = self.attempt_tails.get(attempt_id)
        return self.find(receipt_id) if receipt_id is not None else None

    def precedes(
        self, *, attempt_id: str, receipt_id: str, tail_receipt_id: str
    ) -> bool:
        if self.receipt_attempts.get(receipt_id) != attempt_id:
            return False
        current = self.find(tail_receipt_id)
        while current is not None:
            current_id = str(current["receipt_id"])
            if current_id == receipt_id:
                return True
            predecessor = current.get("reconciles_receipt_id")
            current = self.find(str(predecessor)) if predecessor is not None else None
        return False


@dataclass
class Harness:
    catalog: Any
    service: ToolService
    policy: FakePolicyEvaluator
    approvals: FakeApprovalResolver
    leases: FakeLeaseIssuer
    idempotency: FakeIdempotencyStore
    revisions: FakeRevisionStore
    intents: FakeIntentStore
    executor: FakeExecutor
    receipts: FakeReceiptStore

    def auth(self, tool: str, *, principal_id: str = PRINCIPAL) -> AuthContext:
        return AuthContext(
            capabilities=frozenset({self.catalog.spec(tool).capability}),
            principal_id=principal_id,
            workspace_id=WORKSPACE,
        )

    def call(
        self,
        tool: str,
        *,
        request_id: str = "req-1",
        auth: AuthContext | None = None,
        **kwargs,
    ) -> tuple[dict[str, Any], bool]:
        return self.service.call(
            tool,
            call_arguments(self.catalog, tool, **kwargs),
            auth or self.auth(tool),
            request_id=request_id,
        )
