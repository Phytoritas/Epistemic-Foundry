"""Crash recovery, future-only evaluator update and replay integration gate (W06).

W05 decides whether a run may resume from a sealed checkpoint; this package is the
integration gate a runtime calls when a *crashed* run must be recovered — proving
across the resume, the candidate roster, the replay and the schedule at once that
no candidate was lost or double-counted, that the resumed run reproduces the run
it continues, that no evaluator update rewrites the recovered run, and that every
composed record names the same evolution run.  It composes the sealed W05, N06,
reconciliation, replay and quarantine surfaces and re-implements none of them.
"""

from __future__ import annotations

from .gate import (
    FINDING_CODES,
    RecoveryGateError,
    recovery_hash_matches,
    reconcile_recovery,
    require_evaluator_update_future_only,
    require_recovered,
    require_recovered_reconciliation,
    verify_crash_recovery,
)

__all__ = [
    "FINDING_CODES",
    "RecoveryGateError",
    "reconcile_recovery",
    "recovery_hash_matches",
    "require_evaluator_update_future_only",
    "require_recovered",
    "require_recovered_reconciliation",
    "verify_crash_recovery",
]
