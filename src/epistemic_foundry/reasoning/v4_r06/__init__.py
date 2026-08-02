"""Causal/measurement/scope crossover safety integration gate (R06).

The gate that stands in front of a typed hypothesis crossover.  It composes the
already-sealed R04 causal, measurement, scope and Evolution Chamber surfaces and
refuses any splice whose parents mix incompatible causal identification, an
incomparable measurement contract, or a conflicting scope — deriving every axis
from the parents' own referenced artifacts and never trusting an asserted
report.  Each decision resolves to an immutable, re-derivable receipt.
"""

from __future__ import annotations

from .gate import (
    COMPATIBLE_TOKEN,
    COMPATIBILITY_AXES,
    FINDING_CODES,
    CrossoverSafetyRefused,
    derive_crossover_safety,
    evaluate_crossover_safety,
    genome_reference_fields,
    identification_statuses,
    scope_scalar_fields,
)

__all__ = [
    "COMPATIBILITY_AXES",
    "COMPATIBLE_TOKEN",
    "FINDING_CODES",
    "CrossoverSafetyRefused",
    "derive_crossover_safety",
    "evaluate_crossover_safety",
    "genome_reference_fields",
    "identification_statuses",
    "scope_scalar_fields",
]
