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

    return tuple(receipt for receipt in receipts if is_unresolved(receipt))


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
    observed = probe.observe(
        operation=str(intent["action_type"]),
        external_operation_id=str(unresolved["external_operation_id"]),
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
    if observed.external_operation_id != str(unresolved["external_operation_id"]):
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
    receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Exact accounting of intents, receipts, and open obligations."""

    by_intent: dict[str, list[Mapping[str, Any]]] = {}
    for receipt in receipts:
        by_intent.setdefault(str(receipt["intent_id"]), []).append(receipt)
    unresolved: list[str] = []
    missing: list[str] = []
    for intent in intents:
        intent_id = str(intent["intent_id"])
        bound = by_intent.get(intent_id, [])
        if not bound:
            missing.append(intent_id)
        elif all(is_unresolved(receipt) for receipt in bound):
            unresolved.append(intent_id)
    orphaned = sorted(set(by_intent) - {str(intent["intent_id"]) for intent in intents})
    report = {
        "intent_count": len(intents),
        "intents_missing_receipts": sorted(missing),
        "orphaned_receipt_intent_ids": orphaned,
        "receipt_count": len(receipts),
        "reconciled": not (missing or unresolved or orphaned),
        "unresolved_intent_ids": sorted(unresolved),
    }
    report["report_hash"] = sha256_id(canonical_json_bytes(report))
    return report
