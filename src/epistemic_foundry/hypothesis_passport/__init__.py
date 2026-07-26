"""Hypothesis Passport: the reportable state of one hypothesis.

`AGENTS.md`: novelty, fitness, evaluator survival, and model confidence are
distinct from scientific support. The passport is where that separation becomes
visible, so it carries `epistemic_status`, `causal_status`, `novelty_status`,
and `promotion_level` as independent fields rather than one verdict.

A passport also has to be able to go stale. When its evidence is invalidated or
its search scope changes, the honest state is `stale` with recorded reasons, not
a silently preserved conclusion.
"""

from __future__ import annotations

from .passport import (
    PassportViolation,
    build_passport,
    mark_stale,
    status_dimensions_are_independent,
)

__all__ = [
    "PassportViolation",
    "build_passport",
    "mark_stale",
    "status_dimensions_are_independent",
]
