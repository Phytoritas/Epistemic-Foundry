"""Memory retention, deletion and legal-hold integration gate (L06).

L05 plans a forget; this package is what stands between that plan and a memory
that has actually changed.  A legal hold outranks every forget ground, an
execution is verified against the plan it claims to implement, and a sweep of
executed plans is audited by rebuilding the memory they left behind.
"""

from __future__ import annotations

from .gate import (
    FINDING_CODES,
    HOLD_AUTHORITY_FIELDS,
    HOLD_PLACEMENT_FIELDS,
    TOMBSTONE_FACT_FIELDS,
    LegalHoldRegister,
    MemoryGateError,
    audit_retention_sweep,
    hold_placement_hash,
    place_legal_hold,
    release_legal_hold,
    require_clean_sweep,
    require_forget_permitted,
    verify_deletion_execution,
    verify_plan_hash,
)
from .runtime import preflight_forget_plan

__all__ = [
    "FINDING_CODES",
    "HOLD_AUTHORITY_FIELDS",
    "HOLD_PLACEMENT_FIELDS",
    "LegalHoldRegister",
    "MemoryGateError",
    "TOMBSTONE_FACT_FIELDS",
    "audit_retention_sweep",
    "hold_placement_hash",
    "place_legal_hold",
    "preflight_forget_plan",
    "release_legal_hold",
    "require_clean_sweep",
    "require_forget_permitted",
    "verify_deletion_execution",
    "verify_plan_hash",
]
