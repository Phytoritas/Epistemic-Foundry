"""Deterministic resolution of unresolved effects.

An UNKNOWN EffectReceipt is a standing obligation, not an outcome.  Nothing
here may invent a terminal status: a probe that cannot observe the external
operation leaves the receipt UNKNOWN and the obligation open.  Reconciliation
is the only path that closes it, and it always appends a new receipt rather
than editing the unresolved one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, Protocol

from ..mcp_common.contracts import canonical_json_bytes, sha256_id
from .ports import (
    EFFECT_STATUSES,
    UNRESOLVED_STATUS,
    EffectOutcome,
    EffectReceiptStorePort,
)
from .service import MutationError

#: Statuses that close the obligation; the unresolved one is excluded by
#: construction rather than by a second hand-written list.
TERMINAL_STATUSES: Final = tuple(
    status for status in EFFECT_STATUSES if status != UNRESOLVED_STATUS
)


class ReconciliationProbePort(Protocol):
    """Observes the external system for a previously attempted operation."""

    def observe(
        self, *, operation: str, external_operation_id: str, intent: Mapping[str, Any]
    ) -> EffectOutcome | None: ...


def is_unresolved(receipt: Mapping[str, Any]) -> bool:
    """True when the receipt still owes a terminal outcome."""

    return str(receipt.get("status")) == UNRESOLVED_STATUS or bool(
        receipt.get("reconciliation_required")
    )


def outstanding_receipts(
    receipts: Iterable[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Every receipt whose obligation is still open, in stored order."""

    ordered = tuple(receipts)
    resolved_ids = {
        str(receipt["reconciles_receipt_id"])
        for receipt in ordered
        if receipt.get("reconciles_receipt_id") is not None
    }
    return tuple(
        receipt
        for receipt in ordered
        if is_unresolved(receipt)
        and str(receipt.get("receipt_id") or "") not in resolved_ids
    )


def reconcile(
    *,
    intent: Mapping[str, Any],
    unresolved: Mapping[str, Any],
    probe: ReconciliationProbePort,
    receipts: EffectReceiptStorePort,
) -> Mapping[str, Any]:
    """Append a resolving receipt for one unresolved effect.

    Returns the unresolved receipt unchanged when the probe cannot observe the
    operation, so a caller can distinguish "still unknown" from "resolved".
    """

    if not is_unresolved(unresolved):
        raise MutationError(
            "RECONCILIATION_FAILED",
            "the receipt is already terminal and must not be reconciled again",
            action_intent_id=str(intent.get("intent_id") or ""),
            effect_receipt_id=str(unresolved.get("receipt_id") or ""),
        )
    operation_id = unresolved.get("external_operation_id")
    if not isinstance(operation_id, str) or not operation_id:
        return unresolved
    observed = probe.observe(
        operation=str(intent["action_type"]),
        external_operation_id=operation_id,
        intent=intent,
    )
    if observed is None:
        return unresolved
    if observed.status not in TERMINAL_STATUSES:
        raise MutationError(
            "RECONCILIATION_FAILED",
            f"a probe may only report a terminal status, not {observed.status!r}",
            action_intent_id=str(intent.get("intent_id") or ""),
            effect_receipt_id=str(unresolved.get("receipt_id") or ""),
            reconciliation_required=True,
        )
    if observed.external_operation_id != operation_id:
        raise MutationError(
            "RECONCILIATION_FAILED",
            "the probe observed a different external operation than the receipt",
            action_intent_id=str(intent.get("intent_id") or ""),
            effect_receipt_id=str(unresolved.get("receipt_id") or ""),
            reconciliation_required=True,
        )
    return receipts.persist(
        {
            "error_artifact_ids": list(observed.error_artifact_ids),
            "external_operation_id": observed.external_operation_id,
            "idempotency_key": unresolved["idempotency_key"],
            "intent_id": unresolved["intent_id"],
            "new_revision": observed.new_revision,
            "observed_state_hash": observed.observed_state_hash,
            "reconciliation_required": False,
            "reconciles_receipt_id": unresolved["receipt_id"],
            "result_artifact_ids": list(observed.result_artifact_ids),
            "status": observed.status,
        }
    )


def reconciliation_report(
    *,
    intents: Sequence[Mapping[str, Any]],
    attempts: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Exact accounting of intents, durable Attempts, and receipt obligations."""

    intent_ids = {str(intent["intent_id"]) for intent in intents}
    attempted_intent_ids = {str(attempt["intent_id"]) for attempt in attempts}
    by_intent: dict[str, list[Mapping[str, Any]]] = {}
    for receipt in receipts:
        by_intent.setdefault(str(receipt["intent_id"]), []).append(receipt)
    unresolved: list[str] = []
    missing: list[str] = []
    for intent in intents:
        intent_id = str(intent["intent_id"])
        if intent_id not in attempted_intent_ids:
            continue
        bound = by_intent.get(intent_id, [])
        if not bound:
            missing.append(intent_id)
        elif all(is_unresolved(receipt) for receipt in bound):
            unresolved.append(intent_id)
    orphaned_attempts = sorted(attempted_intent_ids - intent_ids)
    orphaned = sorted(set(by_intent) - intent_ids)
    report = {
        "attempt_count": len(attempts),
        "intent_count": len(intents),
        "intents_missing_receipts": sorted(missing),
        "orphaned_attempt_intent_ids": orphaned_attempts,
        "orphaned_receipt_intent_ids": orphaned,
        "receipt_count": len(receipts),
        "reconciled": not (missing or unresolved or orphaned_attempts or orphaned),
        "unresolved_intent_ids": sorted(unresolved),
    }
    report["report_hash"] = sha256_id(canonical_json_bytes(report))
    return report
