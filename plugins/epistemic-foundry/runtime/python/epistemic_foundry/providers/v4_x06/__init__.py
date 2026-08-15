"""Provider diversity, cost, safety and reward-attribution integration gate (X06).

Composes the sealed X05 cross-provider routing, safe delayed-reward bandit,
fallback neutrality and external-backend boundary into one surface that attests a
routed set is diverse and cost-accounted, attributes a reward only through the
safe bandit, keeps every fallback provider-neutral and every backend advisory,
and binds the sealed sub-decisions into one immutable, re-derivable integration
receipt that a tampered sub-decision cannot be laundered into.
"""

from __future__ import annotations

from .gate import (
    BANDIT_STATE_KIND,
    FINDING_CODES,
    ROUTING_KIND,
    ProviderGateError,
    assert_composed_neutrality,
    attest_provider_diversity,
    attribute_provider_reward,
    integrate_provider_gate,
    refuse_backend_provider_authority,
)

__all__ = [
    "BANDIT_STATE_KIND",
    "FINDING_CODES",
    "ROUTING_KIND",
    "ProviderGateError",
    "assert_composed_neutrality",
    "attest_provider_diversity",
    "attribute_provider_reward",
    "integrate_provider_gate",
    "refuse_backend_provider_authority",
]
