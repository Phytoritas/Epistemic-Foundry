"""The receipt-bound mutation handler and its registry factory.

The handler runs the CAPABILITY_AUTHORIZATION sub-order (target scope →
candidate identity → policy → approval requirement → approval verification →
self-approval denial → lease issuance) and then HANDLER_EXECUTION (idempotency
→ persist intent → revalidate lease → expected revision → effect or dry run →
persist receipt → reconcile).  A dry run records the intent and a
NOT_EXECUTED receipt so replay can tell an intentional non-effect from crash
ambiguity.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..mcp_common.contracts import (
    AuthContext,
    McpContractError,
    ToolSpec,
    canonical_json_bytes,
    result_envelope,
    sha256_id,
)
from .ports import (
    DRY_RUN_OPERATION_ID,
    STATUS_PROJECTION,
    UNOBSERVED_OPERATION_ID,
    ActionIntentStorePort,
    ApprovalResolverPort,
    CapabilityLeasePort,
    EffectExecutorPort,
    EffectOutcome,
    EffectReceiptStorePort,
    IdempotencyReservationPort,
    PolicyEvaluatorPort,
    Reservation,
    RevisionPort,
)
from .service import (
    MutatingToolCatalog,
    MutatingToolSpec,
    MutationError,
    semantic_fingerprint,
)


class MutationHandler:
    """Uniform MUTATING_EFFECT execution over the injected authority ports."""

    def __init__(
        self,
        catalog: MutatingToolCatalog,
        *,
        policy: PolicyEvaluatorPort,
        approvals: ApprovalResolverPort,
        leases: CapabilityLeasePort,
        idempotency: IdempotencyReservationPort,
        revisions: RevisionPort,
        intents: ActionIntentStorePort,
        executor: EffectExecutorPort,
        receipts: EffectReceiptStorePort,
    ) -> None:
        self._catalog = catalog
        self._policy = policy
        self._approvals = approvals
        self._leases = leases
        self._idempotency = idempotency
        self._revisions = revisions
        self._intents = intents
        self._executor = executor
        self._receipts = receipts

    def execute(
        self,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        auth: AuthContext,
        *,
        request_id: str,
        generated_at: str,
    ) -> dict[str, Any]:
        mutating: MutatingToolSpec = self._catalog.spec(spec.name)
        workspace_id = str(arguments["workspace_id"])
        target_ref = str(arguments["target_ref"])
        dry_run = bool(arguments["dry_run"])
        expected_revision = arguments["expected_revision"]
        business_arguments = dict(arguments.get("arguments", {}))

        # --- CAPABILITY_AUTHORIZATION ------------------------------------
        resource_scope = f"{workspace_id}:{target_ref}"
        candidate_id = "AIC-" + sha256_id(
            canonical_json_bytes(
                {
                    "idempotency_key": arguments["idempotency_key"],
                    "resource_scope": resource_scope,
                    "tool": mutating.name,
                }
            )
        ).removeprefix("sha256:")
        policy = self._policy.evaluate(
            mutating.handler_operation, workspace_id, business_arguments
        )
        if mutating.capability not in policy.required_capabilities:
            raise MutationError(
                "LEASE_DENIED",
                "policy does not grant the capability this tool declares",
                intent_candidate_id=candidate_id,
            )
        declared = tuple(arguments["approval_record_ids"])
        if policy.required_approval_count > 0 and not declared:
            raise MutationError(
                "APPROVAL_REQUIRED",
                f"{mutating.name} requires {policy.required_approval_count} approval(s)",
                intent_candidate_id=candidate_id,
            )
        verdict = self._approvals.verify(
            operation=mutating.handler_operation,
            candidate_id=candidate_id,
            approval_record_ids=declared,
            principal_id=str(auth.principal_id),
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
        if str(auth.principal_id) in verdict.approver_ids:
            raise MutationError(
                "SELF_APPROVAL_FORBIDDEN",
                "the requesting principal may not approve its own mutation",
                intent_candidate_id=candidate_id,
            )
        lease = self._leases.issue(
            principal_id=str(auth.principal_id),
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
        if mutating.capability not in lease.capabilities:
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

        # --- HANDLER_EXECUTION -------------------------------------------
        fingerprint = semantic_fingerprint(
            tool=mutating.name, auth=auth, arguments=arguments
        )
        reservation = self._idempotency.reserve(
            idempotency_key=str(arguments["idempotency_key"]), fingerprint=fingerprint
        )
        if not reservation.created:
            if reservation.fingerprint != fingerprint:
                raise McpContractError(
                    "IDEMPOTENCY_CONFLICT",
                    "the idempotency key was reused with a different semantic request",
                )
            replay = self._replay(
                spec,
                mutating,
                reservation,
                request_id=request_id,
                workspace_id=workspace_id,
                generated_at=generated_at,
                lease_id=lease.lease_id,
                dry_run=dry_run,
                expected_revision=expected_revision,
            )
            # A reservation with no persisted intent means the effect could not
            # have started, so the lifecycle simply continues below.
            if replay is not None:
                return replay

        intent = self._intents.persist(
            {
                "action_type": mutating.handler_operation,
                "approval_record_ids": list(verdict.approval_ids),
                "arguments_hash": sha256_id(canonical_json_bytes(business_arguments)),
                "candidate_id": candidate_id,
                "idempotency_key": str(arguments["idempotency_key"]),
                "required_capabilities": list(policy.required_capabilities),
                "risk_class": mutating.risk_class,
                "target_ref": target_ref,
            }
        )
        intent_id = str(intent["intent_id"])

        revalidated = self._leases.revalidate(lease, at=generated_at)
        if revalidated.revoked:
            raise MutationError(
                "LEASE_INVALID",
                "the lease was revoked before the effect",
                intent_candidate_id=candidate_id,
                action_intent_id=intent_id,
            )

        observed = self._revisions.current(
            workspace_id=workspace_id, target_ref=target_ref
        )
        if mutating.expected_revision_required and observed != expected_revision:
            raise MutationError(
                "REVISION_CONFLICT",
                "the target moved between request and execution",
                intent_candidate_id=candidate_id,
                action_intent_id=intent_id,
            )

        preview: Mapping[str, Any] | None = None
        if dry_run:
            preview = self._executor.preview(
                operation=mutating.handler_operation,
                intent=intent,
                arguments=business_arguments,
            )
            outcome = EffectOutcome(
                external_operation_id=DRY_RUN_OPERATION_ID,
                observed_state_hash=sha256_id(
                    canonical_json_bytes({"observed": observed})
                ),
                status="NOT_EXECUTED",
            )
        else:
            outcome = self._executor.execute(
                arguments=business_arguments,
                intent=intent,
                lease=revalidated,
                operation=mutating.handler_operation,
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
                "idempotency_key": str(arguments["idempotency_key"]),
                "intent_id": intent_id,
                "new_revision": outcome.new_revision,
                "observed_state_hash": outcome.observed_state_hash,
                "reconciliation_required": STATUS_PROJECTION[outcome.status][1],
                "result_artifact_ids": list(outcome.result_artifact_ids),
                "status": outcome.status,
            }
        )
        self._idempotency.bind(
            idempotency_key=str(arguments["idempotency_key"]),
            intent_id=intent_id,
            receipt_id=str(receipt["receipt_id"]),
        )
        return self._envelope(
            spec,
            mutating,
            request_id=request_id,
            workspace_id=workspace_id,
            generated_at=generated_at,
            intent_id=intent_id,
            lease_id=revalidated.lease_id,
            receipt=receipt,
            dry_run=dry_run,
            expected_revision=expected_revision,
            observed_revision=observed,
            new_revision=outcome.new_revision,
            preview=preview,
        )

    def _replay(
        self,
        spec: ToolSpec,
        mutating: MutatingToolSpec,
        reservation: Reservation,
        *,
        request_id: str,
        workspace_id: str,
        generated_at: str,
        lease_id: str,
        dry_run: bool,
        expected_revision: Any,
    ) -> dict[str, Any] | None:
        """Answer a replayed idempotency key from durable evidence only.

        Returns ``None`` when no intent was ever persisted, because the effect
        could not have started and the caller may continue the lifecycle.
        """

        stored = (
            self._receipts.find(reservation.stored_receipt_id)
            if reservation.stored_receipt_id
            else None
        )
        if stored is None:
            if reservation.stored_intent_id is None:
                return None
            # An intent without a receipt is crash ambiguity: the effect may
            # have happened.  Record it as UNKNOWN rather than claiming either
            # outcome, and leave the obligation open for reconciliation.
            stored = self._receipts.persist(
                {
                    "error_artifact_ids": [],
                    "external_operation_id": UNOBSERVED_OPERATION_ID,
                    "idempotency_key": reservation.idempotency_key,
                    "intent_id": reservation.stored_intent_id,
                    "new_revision": None,
                    "observed_state_hash": sha256_id(
                        canonical_json_bytes({"observed": None})
                    ),
                    "reconciliation_required": True,
                    "result_artifact_ids": [],
                    "status": "UNKNOWN",
                }
            )
            self._idempotency.bind(
                idempotency_key=reservation.idempotency_key,
                intent_id=reservation.stored_intent_id,
                receipt_id=str(stored["receipt_id"]),
            )
        return self._envelope(
            spec,
            mutating,
            request_id=request_id,
            workspace_id=workspace_id,
            generated_at=generated_at,
            intent_id=str(stored["intent_id"]),
            lease_id=lease_id,
            receipt=stored,
            dry_run=dry_run,
            expected_revision=expected_revision,
            observed_revision=expected_revision,
            new_revision=stored.get("new_revision"),
            preview=None,
        )

    def _envelope(
        self,
        spec: ToolSpec,
        mutating: MutatingToolSpec,
        *,
        request_id: str,
        workspace_id: str,
        generated_at: str,
        intent_id: str,
        lease_id: str,
        receipt: Mapping[str, Any],
        dry_run: bool,
        expected_revision: Any,
        observed_revision: Any,
        new_revision: Any,
        preview: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        status = str(receipt["status"])
        committed, reconciliation_required = STATUS_PROJECTION[status]
        payload = {
            "mutation": {
                "action_intent_id": intent_id,
                "capability_lease_id": lease_id,
                "committed": committed,
                "dry_run": dry_run,
                "effect_receipt_id": str(receipt["receipt_id"]),
                "effect_status": status,
                "expected_revision": expected_revision,
                "new_revision": new_revision if status == "SUCCEEDED" else None,
                "observed_revision": observed_revision,
                "reconciliation_required": reconciliation_required,
            },
            "preview": dict(preview) if preview is not None else None,
        }
        self._catalog.validate_result_payload(payload)
        return result_envelope(
            spec,
            request_id=request_id,
            workspace_id=workspace_id,
            read_model_state="READY" if status == "SUCCEEDED" else "DEGRADED",
            data=payload,
            receipts=[
                {
                    "artifact_id": intent_id,
                    "receipt_id": str(receipt["receipt_id"]),
                    "sha256": sha256_id(canonical_json_bytes(dict(receipt))),
                }
            ],
            degradation_reason=None
            if status == "SUCCEEDED"
            else f"effect status {status}",
            generated_at=generated_at,
        )


def build_mutating_registry(
    catalog: MutatingToolCatalog,
    handler: MutationHandler,
) -> dict[str, MutationHandler]:
    """One handler per catalog row; the catalog is the only source of names."""

    return {name: handler for name in catalog.tool_names}
