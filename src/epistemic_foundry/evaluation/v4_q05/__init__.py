"""Multi-objective fitness, hidden evaluation and selective-inference gate (Q05).

The gate that stands in front of promotion review for an adaptively-selected
candidate.  It composes the already-sealed multi-objective fitness, verifier
firewall and adaptive-search statistics surfaces and refuses any candidate whose
fitness is a scalar, whose hidden evaluation is not sealed, whose evaluator
feedback leaked, or whose best-of-many selection was never statistically
corrected.  It decides admissibility to *review* only and holds no promotion
authority; every decision resolves to an immutable, re-derivable receipt.
"""

from __future__ import annotations

from .gate import (
    ADMIT,
    FINDING_CODES,
    GATE_NAME,
    REFUSE,
    SchemaNotFound,
    SelectiveAdmissibilityRefused,
    derive_selective_admissibility,
    evaluate_selective_admissibility,
    hard_gate_pass_token,
)

__all__ = [
    "ADMIT",
    "FINDING_CODES",
    "GATE_NAME",
    "REFUSE",
    "SchemaNotFound",
    "SelectiveAdmissibilityRefused",
    "derive_selective_admissibility",
    "evaluate_selective_admissibility",
    "hard_gate_pass_token",
]
