"""Leakage, reward-hacking and evaluator-update governance integration gate (S06).

The gate composes the S05 threat controls, the J05 quarantine workflow reader and
the governance quarantine into one integration surface.  It refuses proxy scores
that would acquire reward authority, evaluator updates that are not future-only
and independently qualified, and feedback that carries holdout material — then
resolves every decision to an immutable, re-derivable receipt.  Nothing here
scores, promotes or executes anything.
"""

from __future__ import annotations

from .governance_gate import (
    CONCERN_EVALUATOR_UPDATE,
    CONCERN_FEEDBACK_ISOLATION,
    CONCERN_REWARD_HACKING,
    EVALUATOR_PROPOSAL_KIND,
    EVALUATOR_QUALIFICATION_KIND,
    EVALUATOR_RECEIPT_PREFIX,
    FINDING_CODES,
    FITNESS_KIND,
    HOLDOUT_DENIAL_PROBE,
    INTEGRATION_RECEIPT_PREFIX,
    LEAKAGE_AUDIT_PREFIX,
    REWARD_RECEIPT_PREFIX,
    ROUTING_KIND,
    GovernanceGateError,
    govern_evaluator_update,
    integrate_evolution_security_gate,
    refuse_reward_hacking,
)

__all__ = [
    "CONCERN_EVALUATOR_UPDATE",
    "CONCERN_FEEDBACK_ISOLATION",
    "CONCERN_REWARD_HACKING",
    "EVALUATOR_PROPOSAL_KIND",
    "EVALUATOR_QUALIFICATION_KIND",
    "EVALUATOR_RECEIPT_PREFIX",
    "FINDING_CODES",
    "FITNESS_KIND",
    "HOLDOUT_DENIAL_PROBE",
    "INTEGRATION_RECEIPT_PREFIX",
    "LEAKAGE_AUDIT_PREFIX",
    "REWARD_RECEIPT_PREFIX",
    "ROUTING_KIND",
    "GovernanceGateError",
    "govern_evaluator_update",
    "integrate_evolution_security_gate",
    "refuse_reward_hacking",
]
