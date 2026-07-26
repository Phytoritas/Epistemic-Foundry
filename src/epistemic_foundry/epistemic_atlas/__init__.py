"""Epistemic Atlas: claim lifecycle and searched-scope accounting.

Invariant EF4-I04 (coverage before confidence): a coverage snapshot records
which scopes were searched *and which were not*. An atlas that reports only
what it found lets an unsearched region read as an absence of counterevidence.

Invariant EF4-I02 also lands here: a retracted source must propagate to the
claims that depended on it, so `retraction_invalidates` names the affected
evidence rather than leaving it silently in place.
"""

from __future__ import annotations

from .lifecycle import (
    LifecycleViolation,
    build_lifecycle_event,
    retraction_invalidates,
    terminal_statuses,
)

__all__ = [
    "LifecycleViolation",
    "build_lifecycle_event",
    "retraction_invalidates",
    "terminal_statuses",
]
