"""Red Queen Lab: adversarial challenge co-evolution.

A candidate that no challenge attacked has not survived anything. This package
therefore refuses to report survival without at least one executed challenge,
and treats an inconclusive or errored match as unresolved rather than as a win
for the candidate.
"""

from __future__ import annotations

from .challenges import (
    ChallengeContractViolation,
    build_challenge_genome,
    build_challenge_result,
    build_red_queen_round,
    survived_challenges,
)

__all__ = [
    "ChallengeContractViolation",
    "build_challenge_genome",
    "build_challenge_result",
    "build_red_queen_round",
    "survived_challenges",
]
