"""Budget envelopes with explicit enforcement labels (EF4-I28).

Contract source: `schemas/budget-envelope.schema.json`.

`spend_is_bounded` is the point of the label. Only `HARD_METERED` and
`HARD_PREALLOCATED` actually bound spend; `SOFT_ESTIMATE` is a forecast and
`UNMETERED` is nothing at all. Treating an estimate as a limit produces false
confidence that a run cannot overspend, which is exactly the failure the
labelling requirement exists to prevent.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Enforcement labels that actually bound spend.
BOUNDING_ENFORCEMENT: frozenset[str] = frozenset({"HARD_METERED", "HARD_PREALLOCATED"})

#: Labels that describe an expectation rather than a limit.
ADVISORY_ENFORCEMENT: frozenset[str] = frozenset({"SOFT_ESTIMATE", "UNMETERED"})

#: The six limit dimensions `budget-envelope.schema.json` requires. All are
#: nullable, so "no limit on this dimension" must be written as an explicit null
#: rather than omitted — an absent key would be indistinguishable from an
#: oversight.
LIMIT_DIMENSIONS: tuple[str, ...] = (
    "tokens",
    "calls",
    "wall_seconds",
    "concurrency",
    "storage_bytes",
    "network_bytes",
)


def normalize_hard_limits(limits: Mapping[str, Any]) -> dict[str, Any]:
    """Fill unspecified dimensions with explicit nulls.

    Refuses unknown dimensions: a typo like `max_tokens` would otherwise sit in
    the envelope looking like a limit while enforcing nothing.
    """
    unknown = sorted(set(limits) - set(LIMIT_DIMENSIONS))
    if unknown:
        raise BudgetViolation(
            f"unknown hard limit dimension(s) {unknown}; a misnamed limit enforces nothing "
            f"while looking like a bound. Known dimensions: {list(LIMIT_DIMENSIONS)}"
        )
    return {name: limits.get(name) for name in LIMIT_DIMENSIONS}


class BudgetViolation(ValueError):
    """A budget envelope is internally inconsistent or mislabeled."""


def build_budget_envelope(
    *,
    enforcement: str,
    hard_limits: Mapping[str, Any],
    soft_cost_currency: str,
    soft_cost_amount: float,
    metering_authority: str,
    breach_policy: str,
    budget_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Seal a budget envelope.

    A hard enforcement label with no hard limits is refused: the label would
    claim a bound that nothing enforces. `UNMETERED` with a `CANCEL` breach
    policy is also refused, since there is no meter to detect the breach.
    """
    normalized = normalize_hard_limits(hard_limits)
    if enforcement in BOUNDING_ENFORCEMENT and all(
        normalized[name] is None for name in LIMIT_DIMENSIONS
    ):
        raise BudgetViolation(
            f"enforcement {enforcement} declares a bound but hard_limits is empty; the label "
            "would claim a limit nothing enforces"
        )
    if enforcement == "UNMETERED" and breach_policy in {"CANCEL", "PAUSE_AND_ESCALATE"}:
        raise BudgetViolation(
            f"enforcement UNMETERED cannot use breach_policy {breach_policy}: with no meter "
            "there is nothing to detect a breach"
        )
    if soft_cost_amount < 0:
        raise BudgetViolation("soft_cost_amount cannot be negative")

    envelope: dict[str, Any] = {
        "budget_id": budget_id or new_id("BE"),
        "enforcement": enforcement,
        "hard_limits": normalized,
        "soft_cost_currency": soft_cost_currency,
        "soft_cost_amount": float(soft_cost_amount),
        "metering_authority": metering_authority,
        "breach_policy": breach_policy,
        "created_at": created_at or utc_now_iso(),
    }
    envelope["budget_hash"] = hash_excluding(envelope, "budget_hash")
    validate_artifact("budget-envelope", envelope)
    return envelope


def spend_is_bounded(envelope: Mapping[str, Any]) -> bool:
    """True only when the label denotes an enforced limit.

    A `SOFT_ESTIMATE` is a forecast, not a ceiling. Callers that need a guarantee
    must check this rather than the presence of a number.
    """
    return str(envelope.get("enforcement")) in BOUNDING_ENFORCEMENT


def requires_escalation_on_breach(envelope: Mapping[str, Any]) -> bool:
    """Whether a breach must interrupt rather than warn."""
    return str(envelope.get("breach_policy")) in {"CANCEL", "PAUSE_AND_ESCALATE"}
