"""Adaptive-search statistics: multiplicity, sequential testing, winner's curse.

The three requirements MASTER_EXECUTION_PROMPT section 5 pins together:

* a sequential-testing ledger, because peeking at results and stopping when they
  look good inflates the error rate no fixed-horizon test would allow;
* a multiplicity policy, because searching many candidates guarantees some pass a
  threshold by chance;
* a selective-inference report, because the *reason* a candidate was selected is
  that its estimate was extreme, so the naive estimate is biased upward by
  construction.
"""

from __future__ import annotations

from .sequential import (
    SequentialBudgetExhausted,
    build_sequential_ledger,
    remaining_alpha,
)
from .selective import (
    SelectiveInferenceRefused,
    build_selective_inference_report,
    winner_curse_risk_for,
)
from .multiplicity import build_multiplicity_adjustment, effective_test_count

__all__ = [
    "SelectiveInferenceRefused",
    "SequentialBudgetExhausted",
    "build_multiplicity_adjustment",
    "build_selective_inference_report",
    "build_sequential_ledger",
    "effective_test_count",
    "remaining_alpha",
    "winner_curse_risk_for",
]
