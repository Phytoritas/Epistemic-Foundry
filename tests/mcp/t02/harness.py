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

from epistemic_foundry.application.mcp_common import (
    AuthContext,
    McpContractError,
    ToolService,
)
from epistemic_foundry.application.mcp_common.contracts import (
    canonical_json_bytes,
    sha256_id,
)
from epistemic_foundry.application.mcp_mutating import (
    DRY_RUN_OPERATION_ID,
    ApprovalVerdict,
    AttemptTransition,
    EffectOutcome,
    LeaseGrant,
    MutationError,
    MutationRuntimeRequest,
    PolicyDecision,
    Reservation,
)
from epistemic_foundry.application.mcp_mutating.ports import STATUS_PROJECTION

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


def _sample_value(declared: Mapping[str, Any], *, key: str) -> Any:
    """Build the smallest deterministic JSON value admitted by one schema node."""

    if "const" in declared:
        return declared["const"]
    if "enum" in declared:
        return declared["enum"][0]
    if declared.get("pattern", "").startswith("^sha256:"):
        return FIXED_HASH
    if declared.get("format") == "date-time":
        return "2026-08-01T08:00:00Z"

    declared_type = declared.get("type")
    if isinstance(declared_type, list):
        declared_type = next(
            (candidate for candidate in declared_type if candidate != "null"),
            "null",
        )
    if declared_type == "object":
        properties = declared.get("properties", {})
        required = set(declared.get("required", properties))
        return {
            child_key: _sample_value(child, key=child_key)
            for child_key, child in properties.items()
            if child_key in required or "const" in child
        }
    if declared_type == "array":
        minimum = int(declared.get("minItems", 0))
        item_schema = declared.get("items", {})
        return [
            _sample_value(item_schema, key=f"{key}_item") for _ in range(minimum)
        ]
    if declared_type == "boolean":
        return True
    if declared_type == "integer":
        return int(declared.get("minimum", 1))
    if declared_type == "number":
        return float(declared.get("minimum", 1))
    if declared_type == "null":
        return None
    return f"{key}-1"


def sample_arguments(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Derive schema-valid business arguments, including nested JSON values."""

    arguments_schema = schema["properties"]["arguments"]
    properties = arguments_schema["properties"]
    required = set(arguments_schema.get("required", properties))
    return {
        key: _sample_value(declared, key=key)
        for key, declared in properties.items()
        if key in required or "const" in declared
    }


def call_arguments(
    catalog: Any,
    tool: str,
    *,
    dry_run: bool = False,
    idempotency_key: str = "key-0001",
    approval_record_ids: Sequence[str] = (),
    expected_revision: str | None = "rev-1",
    target_ref: str | None = None,
    workspace_id: str = WORKSPACE,
) -> dict[str, Any]:
    """A complete, schema-valid call payload for one mutating tool."""

    schema = catalog.input_schema(tool)
    spec = catalog.spec(tool)
    business_arguments = sample_arguments(schema)
    if target_ref is None:
        canonical_target_field = {
            "mutate_work_classify": "request_id",
            "mutate_session_open": "session_id",
        }.get(spec.handler_operation)
        target_ref = (
            str(business_arguments[canonical_target_field])
            if canonical_target_field is not None
            else TARGET
        )
    return {
        "approval_record_ids": list(approval_record_ids),
        "arguments": business_arguments,
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
    preview_failures_remaining: int = 0
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
        if self.preview_failures_remaining > 0:
            self.preview_failures_remaining -= 1
            raise RuntimeError("preview failed")
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


class FakeMutationRuntime:
    """Compound test runtime preserving the full strict lifecycle evidence."""

    def __init__(
        self,
        *,
        approvals: FakeApprovalResolver,
        executor: FakeExecutor,
        idempotency: FakeIdempotencyStore,
        intents: FakeIntentStore,
        leases: FakeLeaseIssuer,
        policy: FakePolicyEvaluator,
        receipts: FakeReceiptStore,
        revisions: FakeRevisionStore,
    ) -> None:
        self._approvals = approvals
        self._executor = executor
        self._idempotency = idempotency
        self._intents = intents
        self._leases = leases
        self._policy = policy
        self._receipts = receipts
        self._revisions = revisions
        self.requests: list[MutationRuntimeRequest] = []

    def execute(self, request: MutationRuntimeRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        arguments = request.validated_arguments
        workspace_id = str(arguments["workspace_id"])
        target_ref = str(arguments["target_ref"])
        idempotency_key = str(arguments["idempotency_key"])
        dry_run = bool(arguments["dry_run"])
        expected_revision = arguments["expected_revision"]
        business_arguments = dict(arguments.get("arguments", {}))
        resource_scope = f"{workspace_id}:{target_ref}"
        candidate_id = "AIC-" + sha256_id(
            canonical_json_bytes(
                {
                    "idempotency_key": idempotency_key,
                    "resource_scope": resource_scope,
                    "tool": request.tool_name,
                }
            )
        ).removeprefix("sha256:")

        policy = self._policy.evaluate(
            request.handler_operation,
            workspace_id,
            business_arguments,
        )
        if request.capability not in policy.required_capabilities:
            raise MutationError(
                "LEASE_DENIED",
                "policy does not grant the capability this tool declares",
                intent_candidate_id=candidate_id,
            )
        declared_approvals = tuple(arguments["approval_record_ids"])
        if policy.required_approval_count > 0 and not declared_approvals:
            raise MutationError(
                "APPROVAL_REQUIRED",
                f"{request.tool_name} requires "
                f"{policy.required_approval_count} approval(s)",
                intent_candidate_id=candidate_id,
            )
        verdict = self._approvals.verify(
            operation=request.handler_operation,
            candidate_id=candidate_id,
            approval_record_ids=declared_approvals,
            principal_id=str(request.auth.principal_id),
            policy=policy,
        )
        if not verdict.verified:
            raise MutationError(
                verdict.code or "APPROVAL_INVALID",
                verdict.reason or "approval evidence did not verify",
                intent_candidate_id=candidate_id,
            )
        if len(verdict.approval_ids) < policy.required_approval_count:
            raise MutationError(
                "APPROVAL_REQUIRED",
                "fewer verified approvals than the policy requires",
                intent_candidate_id=candidate_id,
            )
        if str(request.auth.principal_id) in verdict.approver_ids:
            raise MutationError(
                "SELF_APPROVAL_FORBIDDEN",
                "the requesting principal may not approve its own mutation",
                intent_candidate_id=candidate_id,
            )

        lease = self._leases.issue(
            principal_id=str(request.auth.principal_id),
            workspace_id=workspace_id,
            target_ref=target_ref,
            policy=policy,
            approval_ids=verdict.approval_ids,
        )
        if resource_scope not in lease.resource_scopes:
            raise MutationError(
                "LEASE_INVALID",
                "the issued lease does not cover the exact target scope",
                intent_candidate_id=candidate_id,
            )
        if request.capability not in lease.capabilities:
            raise MutationError(
                "LEASE_INVALID",
                "the issued lease does not carry the required capability",
                intent_candidate_id=candidate_id,
            )
        if tuple(lease.approval_ids) != tuple(verdict.approval_ids):
            raise MutationError(
                "LEASE_INVALID",
                "the lease approval binding differs from the verified approvals",
                intent_candidate_id=candidate_id,
            )

        reservation = self._idempotency.reserve(
            idempotency_key=idempotency_key,
            fingerprint=request.semantic_fingerprint,
        )
        if not reservation.created:
            if reservation.fingerprint != request.semantic_fingerprint:
                raise McpContractError(
                    "IDEMPOTENCY_CONFLICT",
                    "the idempotency key was reused with a different semantic request",
                )
            replay = self._replay(
                request=request,
                reservation=reservation,
                candidate_id=candidate_id,
                lease_id=lease.lease_id,
                dry_run=dry_run,
                expected_revision=expected_revision,
            )
            if replay is not None:
                return replay

        intent_body = {
            "action_type": request.handler_operation,
            "approval_record_ids": list(verdict.approval_ids),
            "arguments_hash": sha256_id(canonical_json_bytes(business_arguments)),
            "candidate_id": candidate_id,
            "idempotency_key": idempotency_key,
            "required_capabilities": list(policy.required_capabilities),
            "risk_class": request.risk_class,
            "target_ref": target_ref,
        }
        intent_id = "intent-" + sha256_id(
            canonical_json_bytes(intent_body)
        ).removeprefix("sha256:")
        if reservation.stored_intent_id not in (None, intent_id):
            raise MutationError(
                "RECONCILIATION_FAILED",
                "the reservation is bound to a different ActionIntent",
                intent_candidate_id=candidate_id,
                action_intent_id=reservation.stored_intent_id,
                reconciliation_required=True,
            )
        intent = self._intents.persist({**intent_body, "intent_id": intent_id})
        reservation = self._idempotency.bind_intent(
            idempotency_key=idempotency_key,
            fingerprint=request.semantic_fingerprint,
            expected_revision=reservation.revision,
            intent_id=intent_id,
        )

        revalidated = self._leases.revalidate(lease, at=request.generated_at)
        if revalidated.revoked:
            raise MutationError(
                "LEASE_INVALID",
                "the lease was revoked before the effect",
                intent_candidate_id=candidate_id,
                action_intent_id=intent_id,
            )

        observed_revision = self._revisions.current(
            workspace_id=workspace_id,
            target_ref=target_ref,
        )
        if (
            request.expected_revision_required
            and observed_revision != expected_revision
        ):
            raise MutationError(
                "REVISION_CONFLICT",
                "the target moved between request and execution",
                intent_candidate_id=candidate_id,
                action_intent_id=intent_id,
            )

        preview: Mapping[str, Any] | None = None
        if dry_run:
            preview = self._executor.preview(
                operation=request.handler_operation,
                intent=intent,
                arguments=business_arguments,
            )

        intent_hash = sha256_id(canonical_json_bytes(dict(intent)))
        attempt_id = "attempt-" + sha256_id(
            canonical_json_bytes(
                {
                    "dry_run": dry_run,
                    "intent_hash": intent_hash,
                }
            )
        ).removeprefix("sha256:")
        transition = self._idempotency.begin_attempt(
            idempotency_key=idempotency_key,
            fingerprint=request.semantic_fingerprint,
            expected_revision=reservation.revision,
            intent_id=intent_id,
            intent_hash=intent_hash,
            attempt_id=attempt_id,
            started_at=request.generated_at,
            dry_run=dry_run,
        )
        if not transition.execute_permitted:
            replay = self._replay(
                request=request,
                reservation=transition.reservation,
                candidate_id=candidate_id,
                lease_id=revalidated.lease_id,
                dry_run=dry_run,
                expected_revision=expected_revision,
            )
            if replay is None:
                raise AssertionError("an existing Attempt must be replayable or open")
            return replay

        if dry_run:
            outcome = EffectOutcome(
                external_operation_id=DRY_RUN_OPERATION_ID,
                observed_state_hash=sha256_id(
                    canonical_json_bytes({"observed": observed_revision})
                ),
                status="NOT_EXECUTED",
            )
        else:
            outcome = self._executor.execute(
                operation=request.handler_operation,
                intent=intent,
                lease=revalidated,
                arguments=business_arguments,
            )
        if outcome.status not in STATUS_PROJECTION:
            raise MutationError(
                "RECONCILIATION_FAILED",
                f"executor returned a non-canonical status {outcome.status!r}",
                intent_candidate_id=candidate_id,
                action_intent_id=intent_id,
                reconciliation_required=True,
            )
        if dry_run and outcome.external_operation_id != DRY_RUN_OPERATION_ID:
            raise MutationError(
                "RECONCILIATION_FAILED",
                "a dry run reported a real external operation",
                intent_candidate_id=candidate_id,
                action_intent_id=intent_id,
                reconciliation_required=True,
            )

        receipt = self._receipts.persist(
            {
                "error_artifact_ids": list(outcome.error_artifact_ids),
                "external_operation_id": outcome.external_operation_id,
                "idempotency_key": idempotency_key,
                "intent_id": intent_id,
                "new_revision": outcome.new_revision,
                "observed_state_hash": outcome.observed_state_hash,
                "reconciliation_required": STATUS_PROJECTION[outcome.status][1],
                "result_artifact_ids": list(outcome.result_artifact_ids),
                "status": outcome.status,
            },
            attempt_id=attempt_id,
        )
        self._idempotency.bind_receipt(
            idempotency_key=idempotency_key,
            fingerprint=request.semantic_fingerprint,
            expected_revision=transition.reservation.revision,
            attempt_id=attempt_id,
            receipt_id=str(receipt["receipt_id"]),
        )
        return self._payload(
            receipt=receipt,
            intent_id=intent_id,
            lease_id=revalidated.lease_id,
            dry_run=dry_run,
            expected_revision=expected_revision,
            observed_revision=observed_revision,
            preview=preview,
        )

    def _replay(
        self,
        *,
        request: MutationRuntimeRequest,
        reservation: Reservation,
        candidate_id: str,
        lease_id: str,
        dry_run: bool,
        expected_revision: Any,
    ) -> Mapping[str, Any] | None:
        """Replay terminal evidence or expose a durable open Attempt."""

        attempt_id = reservation.stored_attempt_id
        if attempt_id is None:
            if reservation.stored_receipt_id is not None:
                raise MutationError(
                    "RECONCILIATION_FAILED",
                    "an EffectReceipt is bound without a durable Attempt",
                    intent_candidate_id=candidate_id,
                    action_intent_id=reservation.stored_intent_id,
                    effect_receipt_id=reservation.stored_receipt_id,
                    reconciliation_required=True,
                )
            return None
        if reservation.stored_intent_id is None:
            raise MutationError(
                "RECONCILIATION_FAILED",
                "a durable Attempt is not bound to an ActionIntent",
                intent_candidate_id=candidate_id,
                reconciliation_required=True,
            )

        bound_id = reservation.stored_receipt_id
        tail = self._receipts.find_for_attempt(attempt_id)
        if tail is None:
            if bound_id is not None:
                raise MutationError(
                    "RECONCILIATION_FAILED",
                    "the reservation-bound EffectReceipt cannot be resolved",
                    intent_candidate_id=candidate_id,
                    action_intent_id=reservation.stored_intent_id,
                    effect_receipt_id=bound_id,
                    reconciliation_required=True,
                )
            raise MutationError(
                "EFFECT_RECONCILING",
                "a durable Attempt has no resolving EffectReceipt yet",
                intent_candidate_id=candidate_id,
                action_intent_id=reservation.stored_intent_id,
                reconciliation_required=True,
            )
        tail_id = str(tail["receipt_id"])
        if str(tail.get("idempotency_key")) != reservation.idempotency_key:
            raise MutationError(
                "RECONCILIATION_FAILED",
                "the EffectReceipt is bound to a different idempotency key",
                intent_candidate_id=candidate_id,
                action_intent_id=reservation.stored_intent_id,
                effect_receipt_id=tail_id,
                reconciliation_required=True,
            )
        if str(tail["intent_id"]) != reservation.stored_intent_id:
            raise MutationError(
                "RECONCILIATION_FAILED",
                "the EffectReceipt is bound to a different ActionIntent",
                intent_candidate_id=candidate_id,
                action_intent_id=reservation.stored_intent_id,
                effect_receipt_id=tail_id,
                reconciliation_required=True,
            )

        if bound_id is None:
            self._idempotency.bind_receipt(
                idempotency_key=reservation.idempotency_key,
                fingerprint=request.semantic_fingerprint,
                expected_revision=reservation.revision,
                attempt_id=attempt_id,
                receipt_id=tail_id,
            )
        else:
            bound = self._receipts.find(bound_id)
            if bound is None or (
                tail_id != bound_id
                and not self._receipts.precedes(
                    attempt_id=attempt_id,
                    receipt_id=bound_id,
                    tail_receipt_id=tail_id,
                )
            ):
                raise MutationError(
                    "RECONCILIATION_FAILED",
                    "the current EffectReceipt is outside the bound Attempt lineage",
                    intent_candidate_id=candidate_id,
                    action_intent_id=reservation.stored_intent_id,
                    effect_receipt_id=tail_id,
                    reconciliation_required=True,
                )

        return self._payload(
            receipt=tail,
            intent_id=reservation.stored_intent_id,
            lease_id=lease_id,
            dry_run=dry_run,
            expected_revision=expected_revision,
            observed_revision=expected_revision,
            preview=None,
        )

    @staticmethod
    def _payload(
        *,
        receipt: Mapping[str, Any],
        intent_id: str,
        lease_id: str,
        dry_run: bool,
        expected_revision: Any,
        observed_revision: Any,
        preview: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        status = str(receipt["status"])
        committed, reconciliation_required = STATUS_PROJECTION[status]
        return {
            "mutation": {
                "action_intent_id": intent_id,
                "capability_lease_id": lease_id,
                "committed": committed,
                "dry_run": dry_run,
                "effect_receipt_id": str(receipt["receipt_id"]),
                "effect_status": status,
                "expected_revision": expected_revision,
                "new_revision": receipt.get("new_revision")
                if status == "SUCCEEDED"
                else None,
                "observed_revision": observed_revision,
                "reconciliation_required": reconciliation_required,
            },
            "preview": dict(preview) if preview is not None else None,
        }


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
    runtime: FakeMutationRuntime

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
