"""Cross-provider mutation routing and the safe delayed-reward bandit gate (X05).

Composes ``providers/neutrality.py`` (provider neutrality), ``evaluation/
bandits.py`` (the safe delayed-reward bandit vocabulary), the N05 schedule gate
(exact fan-in) and the T05 external-backend boundary (non-authority) into one
surface that keeps mutation routing provider-neutral and the bandit safe, with
every decision resolving to an immutable, re-derivable receipt.
"""

from __future__ import annotations

from .routing import (
    BANDIT_STATE_KIND,
    FINDING_CODES,
    ROUTING_KIND,
    MutationRoutingError,
    admit_bandit_reward,
    assert_fallback_neutral,
    reconcile_routed_fanin,
    route_external_backend_neutral,
    route_mutation,
    seal_safe_bandit_state,
)

__all__ = [
    "BANDIT_STATE_KIND",
    "FINDING_CODES",
    "ROUTING_KIND",
    "MutationRoutingError",
    "admit_bandit_reward",
    "assert_fallback_neutral",
    "reconcile_routed_fanin",
    "route_external_backend_neutral",
    "route_mutation",
    "seal_safe_bandit_state",
]
