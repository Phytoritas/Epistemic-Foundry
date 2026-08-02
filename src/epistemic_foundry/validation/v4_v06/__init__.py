"""Experiment/replication end-to-end integration gate (V06).

The gate that stands over the whole experiment/replication path for a single
candidate.  It composes the already-sealed statistical-admissibility receipt
(Q05), validation-cascade advancement receipt (V05) and promotion-Parliament
receipt (P05) and integrates the path only when all three cleared, all three
describe the one candidate, the two downstream gates rest on the same statistical
clearance this gate was handed, and no composed receipt was tampered with or
claimed an authority it may not hold.  It scores, selects, evaluates and promotes
nothing; promotion authority lives in ``governance.promotion``.  Every decision,
integrate or refuse, resolves to one immutable, re-derivable receipt, and no
input is ever mutated.
"""

from __future__ import annotations

from .gate import (
    CONCERN_PARLIAMENT,
    CONCERN_STATISTICS,
    CONCERN_VALIDATION,
    FINDING_CODES,
    GATE_ID_PREFIX,
    GATE_NAME,
    INTEGRATE,
    REFUSE,
    ExperimentReplicationRefused,
    derive_experiment_replication_integration,
    evaluate_experiment_replication_integration,
    integration_grants_promotion,
    integration_hash_matches,
)

__all__ = [
    "CONCERN_PARLIAMENT",
    "CONCERN_STATISTICS",
    "CONCERN_VALIDATION",
    "ExperimentReplicationRefused",
    "FINDING_CODES",
    "GATE_ID_PREFIX",
    "GATE_NAME",
    "INTEGRATE",
    "REFUSE",
    "derive_experiment_replication_integration",
    "evaluate_experiment_replication_integration",
    "integration_grants_promotion",
    "integration_hash_matches",
]
