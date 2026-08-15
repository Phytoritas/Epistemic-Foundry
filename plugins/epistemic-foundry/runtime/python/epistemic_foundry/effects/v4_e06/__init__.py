"""Public E06 concurrent candidate effect and idempotency gate API.

The gate composes the sealed E05 reconciliation engine rather than repeating
it, so the only thing exported here is the concurrency and idempotency surface;
E05's own names stay in ``epistemic_foundry.effects.v4_e05``.
"""

from .gate import (
    BEGIN,
    COMMIT,
    EFFECT,
    FINDING_CODES,
    LANE_PHASES,
    ConcurrentEffectError,
    check_serializability,
    fingerprint_payload,
    normalize_actions,
    require_concurrent_effect_gate,
    run_concurrency_gate,
    settle_interleaving,
)

__all__ = [
    "BEGIN",
    "COMMIT",
    "EFFECT",
    "FINDING_CODES",
    "LANE_PHASES",
    "ConcurrentEffectError",
    "check_serializability",
    "fingerprint_payload",
    "normalize_actions",
    "require_concurrent_effect_gate",
    "run_concurrency_gate",
    "settle_interleaving",
]
