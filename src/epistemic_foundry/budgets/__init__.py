"""Budget labelling, loop termination, and secret handling.

* EF4-I28: budgets are labeled `HARD_METERED`, `HARD_PREALLOCATED`,
  `SOFT_ESTIMATE`, or `UNMETERED`. An unlabeled budget is worse than no budget,
  because a `SOFT_ESTIMATE` read as `HARD_METERED` produces false confidence
  that spend is bounded.
* EF4-I27: every cycle carries a seen-set key, convergence rule, dry rounds,
  maximum rounds, budget, and escalation. A loop without a dedupe key can
  rediscover the same candidate forever and call it progress.
* EF4-I29: secrets are opaque handles, never copied into prompts, evidence,
  logs, or exports.
"""

from __future__ import annotations

from .envelope import (
    BudgetViolation,
    build_budget_envelope,
    spend_is_bounded,
)
from .loops import LoopContractViolation, build_loop_contract, loop_should_continue
from .secrets import SecretLeak, SecretHandle, assert_no_secret_material

__all__ = [
    "BudgetViolation",
    "LoopContractViolation",
    "SecretHandle",
    "SecretLeak",
    "assert_no_secret_material",
    "build_budget_envelope",
    "build_loop_contract",
    "loop_should_continue",
    "spend_is_bounded",
]
