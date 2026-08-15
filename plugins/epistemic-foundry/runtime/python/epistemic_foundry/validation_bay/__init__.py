"""Validation Bay: the hard validation cascade.

A cascade spends budget in stages and stops early on a hard failure. Two rules
matter more than the arithmetic:

* A later stage may not run when an earlier hard stage failed. Skipping the
  order would let an expensive stage "rescue" a candidate that already failed a
  cheap contract check.
* An unrun stage is `NOT_RUN`, never an implicit pass. Aggregating absent stages
  as success is how a partial cascade becomes a false `PASS`.
"""

from __future__ import annotations

from .cascade import (
    CascadeViolation,
    aggregate_cascade_status,
    build_cascade_plan,
    build_stage_result,
    next_runnable_stage,
)

__all__ = [
    "CascadeViolation",
    "aggregate_cascade_status",
    "build_cascade_plan",
    "build_stage_result",
    "next_runnable_stage",
]
