"""Novelty assessment and fitness vectors.

* EF4-I47: absent, empty, failed, or incomplete novelty assessment yields
  `NOT_ASSESSED`, never `POTENTIALLY_NOVEL` by default. "We did not find prior
  art" and "we did not look properly" produce the same empty result set, so
  novelty must be earned by a complete search rather than granted by silence.
* EF4-I45: a combined score may order search but cannot promote. The fitness
  vector keeps dimensions separate and carries its own hard-gate status, so a
  scalar cannot stand in for the gates.
* EF4-I46: claim, mechanism, prediction, falsifier, scope, experiment, evidence,
  and external prior-art novelty stay separate dimensions, and none of them is
  support. A single novelty scalar would let one novel dimension carry the rest.
"""

from __future__ import annotations

from .novelty import (
    NoveltyAssessmentRefused,
    assess_novelty,
    novelty_supports_claim,
)
from .novelty_layers import (
    NOVELTY_LAYERS,
    NoveltyVectorRefused,
    build_novelty_vector,
    failed_novelty_vector,
    novel_layers,
    novelty_is_claimable,
    novelty_supports_promotion,
)
from .fitness import FitnessViolation, build_fitness_vector, scalarize_for_ordering

__all__ = [
    "FitnessViolation",
    "NOVELTY_LAYERS",
    "NoveltyAssessmentRefused",
    "NoveltyVectorRefused",
    "assess_novelty",
    "build_fitness_vector",
    "build_novelty_vector",
    "failed_novelty_vector",
    "novel_layers",
    "novelty_is_claimable",
    "novelty_supports_claim",
    "novelty_supports_promotion",
    "scalarize_for_ordering",
]
