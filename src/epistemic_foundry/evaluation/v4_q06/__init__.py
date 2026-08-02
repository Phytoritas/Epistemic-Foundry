"""Calibration, winner's-curse and statistical-governance integration gate (Q06).

The gate that stands in front of promotion review for one adaptively-selected
candidate and asks whether its statistical admissibility (Q05), validation
advancement (V05), confidence calibration and winner's-curse accounting describe
one coherent, statistically-governed selection.  It composes the already-sealed
verdicts — binding the V05 advancement receipt to the Q05 clearance by hash
rather than importing the ``validation`` component and closing a forbidden
top-level cycle — and refuses any selection Q05 did not admit, V05 did not
advance, the calibration report did not pass, or whose winner's-curse the
selective-inference surface does not permit to advance without replication.  No
single dimension carries the decision; it scores, selects, evaluates and
promotes nothing, holds no evaluator, holdout or promotion authority, mutates no
input, and resolves every decision to an immutable, re-derivable receipt.
"""

from __future__ import annotations

from .gate import (
    FINDING_CODES,
    GATE_ID_PREFIX,
    GATE_NAME,
    GOVERN,
    REFUSE,
    GovernanceIntegrationRefused,
    SchemaNotFound,
    calibration_pass_status,
    derive_governance_integration,
    evaluate_governance_integration,
    governance_hash_matches,
)

__all__ = [
    "FINDING_CODES",
    "GATE_ID_PREFIX",
    "GATE_NAME",
    "GOVERN",
    "GovernanceIntegrationRefused",
    "REFUSE",
    "SchemaNotFound",
    "calibration_pass_status",
    "derive_governance_integration",
    "evaluate_governance_integration",
    "governance_hash_matches",
]
