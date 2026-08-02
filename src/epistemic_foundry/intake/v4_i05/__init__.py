"""Hypothesis genome intake, eligibility screening and seed bootstrap (I05).

The door evolution enters through: what may be admitted as a hypothesis genome,
why a submission was refused, and what seed population the survivors are
allowed to become.
"""

from __future__ import annotations

from .screening import (
    FINDING_CODES,
    GENOME_KIND,
    SCREEN_CODES,
    SEED_GENERATION,
    SIGNATURE_FIELDS,
    GenomeIntakeError,
    bootstrap_seed_population,
    genome_contract,
    genome_signature,
    intakeable_genome_kind,
    mutable_genome_kinds,
    require_fully_eligible,
    screen_genome,
    screen_submissions,
)

__all__ = [
    "FINDING_CODES",
    "GENOME_KIND",
    "GenomeIntakeError",
    "SCREEN_CODES",
    "SEED_GENERATION",
    "SIGNATURE_FIELDS",
    "bootstrap_seed_population",
    "genome_contract",
    "genome_signature",
    "intakeable_genome_kind",
    "mutable_genome_kinds",
    "require_fully_eligible",
    "screen_genome",
    "screen_submissions",
]
