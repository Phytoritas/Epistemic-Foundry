"""Operator/prompt qualification and context-budget integration gate (J06).

The gate composes the sealed J05 registry and prompt-workflow, the S05
inert-mutations gate and the budget-envelope module: it admits a mutation
operator to a run only when a prompt-affecting operator has been qualified out of
quarantine for a future run and the work's context tokens fit under a budget that
actually bounds spend.  It qualifies, meters and refuses; it never scores,
promotes or executes, and every admission resolves to a self-proving receipt.
"""

from __future__ import annotations

from .declarations import (
    BUDGET_ENVELOPE_KIND,
    CONTEXT_MANIFEST_KIND,
    FINDING_CODES,
    ContextBudgetGateError,
    budget_envelope_contract,
    context_accounting_contract,
)
from .gate import (
    ADMITTED,
    admit_operator_application,
    assess_context_budget,
    verify_gate_receipt,
)

__all__ = [
    "ADMITTED",
    "BUDGET_ENVELOPE_KIND",
    "CONTEXT_MANIFEST_KIND",
    "FINDING_CODES",
    "ContextBudgetGateError",
    "admit_operator_application",
    "assess_context_budget",
    "budget_envelope_contract",
    "context_accounting_contract",
    "verify_gate_receipt",
]
