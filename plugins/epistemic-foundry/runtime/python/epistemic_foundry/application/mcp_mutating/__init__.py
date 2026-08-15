"""T02 MCP mutating tool surface.

Composed onto the sealed T01 kernel: the same ``ToolService`` runs the same
frozen authorization order, the same shared result and error envelopes carry
the answer, and T02 contributes only the mutating catalog, the mutation
payload, the closed mutation subcode, and the receipt-bound lifecycle.
"""

from .handler_factory import MutationHandler, build_mutating_registry
from .ports import (
    DRY_RUN_OPERATION_ID,
    EFFECT_STATUSES,
    ActionIntentStorePort,
    AttemptTransition,
    ApprovalResolverPort,
    ApprovalVerdict,
    CapabilityLeasePort,
    EffectExecutorPort,
    EffectOutcome,
    EffectReceiptStorePort,
    IdempotencyReservationPort,
    LeaseGrant,
    PolicyDecision,
    PolicyEvaluatorPort,
    Reservation,
    RevisionPort,
)
from .reconciliation import (
    TERMINAL_STATUSES,
    UNRESOLVED_STATUS,
    ReconciliationProbePort,
    is_unresolved,
    outstanding_receipts,
    reconcile,
    reconciliation_report,
)
from .service import (
    EXPECTED_MUTATING_TOOL_COUNT,
    MUTATION_ERROR_CODES,
    MUTATION_ERROR_MAPPING,
    MUTATING_SIDE_EFFECT_CLASS,
    MutatingToolCatalog,
    MutatingToolSpec,
    MutationError,
    load_catalog_set,
    load_mutating_catalog,
    semantic_fingerprint,
)

__all__ = [
    "ActionIntentStorePort",
    "AttemptTransition",
    "ApprovalResolverPort",
    "ApprovalVerdict",
    "CapabilityLeasePort",
    "DRY_RUN_OPERATION_ID",
    "EFFECT_STATUSES",
    "EXPECTED_MUTATING_TOOL_COUNT",
    "EffectExecutorPort",
    "EffectOutcome",
    "EffectReceiptStorePort",
    "IdempotencyReservationPort",
    "LeaseGrant",
    "MUTATING_SIDE_EFFECT_CLASS",
    "MUTATION_ERROR_CODES",
    "MUTATION_ERROR_MAPPING",
    "MutatingToolCatalog",
    "MutatingToolSpec",
    "MutationError",
    "MutationHandler",
    "PolicyDecision",
    "PolicyEvaluatorPort",
    "ReconciliationProbePort",
    "Reservation",
    "RevisionPort",
    "TERMINAL_STATUSES",
    "UNRESOLVED_STATUS",
    "build_mutating_registry",
    "is_unresolved",
    "load_catalog_set",
    "load_mutating_catalog",
    "outstanding_receipts",
    "reconcile",
    "reconciliation_report",
    "semantic_fingerprint",
]
