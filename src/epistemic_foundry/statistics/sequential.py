"""Sequential-testing ledger.

Contract source: `schemas/sequential-testing-ledger.schema.json`.

Every interim look at a result spends error budget. A run that peeks repeatedly
and stops when the numbers look good has an error rate far above its nominal
alpha, so the ledger tracks spend per entry and refuses a look once the budget is
gone. Refusing is the point: continuing to test on an exhausted budget produces a
result whose stated significance is arithmetically wrong.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Policies that account for repeated looks. `fixed_horizon` does not, so a
#: ledger using it must record exactly one entry.
SEQUENTIAL_POLICIES: frozenset[str] = frozenset(
    {"alpha_spending", "e_value", "bayesian_monitoring"}
)


class SequentialBudgetExhausted(RuntimeError):
    """A further look would exceed the error budget."""


#: The canonical spend field on a ledger entry
#: (`sequential-testing-ledger.schema.json` requires test_id, generation,
#: statistic, threshold, spent, decision).
SPEND_FIELD = "spent"


def remaining_alpha(initial_budget: float, entries: Sequence[Mapping[str, Any]]) -> float:
    """Budget left after the recorded looks.

    Clamped at zero: a negative remainder would read as a small positive budget in
    a naive comparison, which is the arithmetic that lets an over-spent run keep
    testing.
    """
    spent = sum(float(entry.get(SPEND_FIELD, 0.0)) for entry in entries)
    return max(initial_budget - spent, 0.0)


def build_sequential_ledger(
    *,
    family_id: str,
    testing_policy: str,
    initial_budget: float,
    entries: Sequence[Mapping[str, Any]],
    selection_events: Sequence[Mapping[str, Any]],
    ledger_id: str | None = None,
) -> dict[str, Any]:
    """Record the looks taken and the budget left.

    A `fixed_horizon` policy with more than one entry is refused: that policy has
    no provision for interim analysis, so multiple looks under it are unaccounted
    peeking rather than a planned sequence.
    """
    if initial_budget <= 0:
        raise SequentialBudgetExhausted(
            "a sequential ledger needs a positive initial budget; zero budget cannot support "
            "any look"
        )
    if testing_policy == "fixed_horizon" and len(entries) > 1:
        raise SequentialBudgetExhausted(
            f"fixed_horizon policy recorded {len(entries)} looks; that policy has no provision "
            "for interim analysis, so repeated looks are unaccounted peeking"
        )

    spent = sum(float(entry.get(SPEND_FIELD, 0.0)) for entry in entries)
    if spent > initial_budget + 1e-12:
        raise SequentialBudgetExhausted(
            f"looks spent {spent:.6f} of a {initial_budget:.6f} budget; a result computed past "
            "the budget has an arithmetically wrong significance"
        )

    ledger: dict[str, Any] = {
        "ledger_id": ledger_id or new_id("STL"),
        "family_id": family_id,
        "testing_policy": testing_policy,
        "initial_budget": float(initial_budget),
        "entries": [dict(entry) for entry in entries],
        "remaining_budget": remaining_alpha(initial_budget, entries),
        "selection_events": [dict(event) for event in selection_events],
    }
    ledger["ledger_hash"] = hash_excluding(ledger, "ledger_hash")
    validate_artifact("sequential-testing-ledger", ledger)
    return ledger


def may_take_another_look(ledger: Mapping[str, Any], *, cost: float) -> bool:
    """Whether one more look of `cost` fits in the remaining budget."""
    return float(ledger["remaining_budget"]) >= cost > 0


def require_budget_for_look(ledger: Mapping[str, Any], *, cost: float) -> None:
    """Raise when a further look would overspend."""
    if not may_take_another_look(ledger, cost=cost):
        raise SequentialBudgetExhausted(
            f"look costing {cost} exceeds the remaining budget "
            f"{ledger['remaining_budget']}; stop or widen the preregistered budget"
        )
