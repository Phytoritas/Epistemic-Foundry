"""Novelty assessment and fitness vectors.

* EF4-I47: absent, empty, failed, or incomplete novelty assessment yields
  `NOT_ASSESSED`, never `POTENTIALLY_NOVEL` by default. "We did not find prior
  art" and "we did not look properly" produce the same empty result set, so
  novelty must be earned by a complete search rather than granted by silence.
* EF4-I45: a combined score may order search but cannot promote. The fitness
  vector keeps dimensions separate and carries its own hard-gate status, so a
  scalar cannot stand in for the gates.
"""

from __future__ import annotations

from .novelty import (
    NoveltyAssessmentRefused,
    assess_novelty,
    novelty_supports_claim,
)
from .fitness import FitnessViolation, build_fitness_vector, scalarize_for_ordering

__all__ = [
    "FitnessViolation",
    "NoveltyAssessmentRefused",
    "assess_novelty",
    "build_fitness_vector",
    "novelty_supports_claim",
    "scalarize_for_ordering",
]
