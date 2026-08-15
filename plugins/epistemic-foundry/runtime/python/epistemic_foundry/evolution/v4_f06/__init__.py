"""FORGE-EVOLVE lifecycle integration and replay gate (F06).

The gate that stands between a FORGE session and the EVOLVE run it hands off to.
It composes the already-sealed F05 EVOLVE state machine, I05 genome intake and
R05 operator registry, and refuses any run whose lifecycle transitions or stop
certificate are inconsistent, whose evaluator changed mid-run, whose seed
population or candidate set does not reconcile, or whose own replay report is not
an honest byte-for-byte reproduction.  Each decision resolves to an immutable,
re-derivable receipt; the gate acquires no evaluator, holdout or promotion
authority and neither scores nor selects a candidate.
"""

from __future__ import annotations

from .gate import (
    ADMIT,
    FINDING_CODES,
    REFUSE,
    SEED_GENOME_KIND,
    STOP_REASONS,
    LifecycleReplayRefused,
    derive_lifecycle_replay,
    evaluate_lifecycle_replay,
    evolve_handoff_phase,
    replay_vocabulary,
)

__all__ = [
    "ADMIT",
    "FINDING_CODES",
    "REFUSE",
    "SEED_GENOME_KIND",
    "STOP_REASONS",
    "LifecycleReplayRefused",
    "derive_lifecycle_replay",
    "evaluate_lifecycle_replay",
    "evolve_handoff_phase",
    "replay_vocabulary",
]
