"""Foundry Kernel: provider-neutral authority over FORGE state and gates.

Constitutional boundary (`AGENTS.md`, MASTER_SPEC Part II): the kernel owns
canonical state, policy, capabilities, effects, and replay. Plugin shells,
model providers, and search backends are adapters — none of them may advance a
session or promote a claim.
"""

from __future__ import annotations

from .gates import GateEvaluation, evaluate_gate, gate_decision
from .session import (
    ForgeKernel,
    RevisionConflict,
    TransitionRejected,
)
from .transitions import ILLEGAL_TRANSITION_REASON, allowed_targets, is_legal_transition

__all__ = [
    "ForgeKernel",
    "GateEvaluation",
    "ILLEGAL_TRANSITION_REASON",
    "RevisionConflict",
    "TransitionRejected",
    "allowed_targets",
    "evaluate_gate",
    "gate_decision",
    "is_legal_transition",
]
