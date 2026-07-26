"""Verifier Firewall: immutable evaluators and least-privilege holdouts.

Constitutional rules enforced here (MASTER_EXECUTION_PROMPT section 7):

* The current `EvaluatorBundle` is immutable for the duration of a run.
* Hidden and OOD artifacts are least privilege; candidate-generating roles hold
  no read capability over them.
* Any leakage, evaluator drift, or unqualified evaluator update invalidates the
  affected comparisons. Invalidation is an outcome, not a score penalty.
"""

from __future__ import annotations

from .firewall import (
    EvaluatorDrift,
    HoldoutAccessDenied,
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

__all__ = [
    "EvaluatorDrift",
    "HoldoutAccessDenied",
    "VerifierFirewall",
    "build_evaluator_bundle",
    "build_holdout_manifest",
]
