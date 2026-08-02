"""Validation cascade, OOD challenge and replication-ceiling gate (V05).

The gate that stands between a validated candidate and a claim of advancement.
It composes the already-sealed validation cascade, the Red Queen out-of-
distribution challenge record, the statistical-admissibility receipt and the
independent-replication ceiling, and refuses any claim whose cascade did not
pass, whose out-of-distribution challenge it did not survive, whose statistical
admissibility was never granted, or whose replication evidence caps the
promotion ceiling below the configured level.  It advances nothing on a score,
holds no evaluator, holdout or promotion authority, mutates no input, and
resolves every decision to an immutable, re-derivable receipt.
"""

from __future__ import annotations

from .cascade_gate import (
    ADVANCE,
    FINDING_CODES,
    GATE_NAME,
    REFUSE,
    SchemaNotFound,
    ValidationCascadeRefused,
    cascade_pass_status,
    derive_validation_advancement,
    evaluate_validation_advancement,
    ood_challenge_class_token,
)

__all__ = [
    "ADVANCE",
    "FINDING_CODES",
    "GATE_NAME",
    "REFUSE",
    "SchemaNotFound",
    "ValidationCascadeRefused",
    "cascade_pass_status",
    "derive_validation_advancement",
    "evaluate_validation_advancement",
    "ood_challenge_class_token",
]
