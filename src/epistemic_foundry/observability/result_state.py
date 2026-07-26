"""Distinct result states (EF4-I23).

A retrieval or evaluation call can end in four materially different ways, and
collapsing them is the failure this module prevents:

* `EMPTY_CONFIRMED` — the backend answered and there is nothing. A real finding.
* `DEGRADED` — the backend answered partially; results exist but are incomplete.
* `UNAVAILABLE` — the backend could not be reached or errored. Nothing is known.
* `POPULATED` — the backend answered with results.

`is_empty_research_finding` is True only for `EMPTY_CONFIRMED`. An `UNAVAILABLE`
call rendered as "no results found" tells a reader that nothing exists when in
fact nothing was searched, which is the most misleading output a research tool
can produce.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Sequence


class ResultState(str, Enum):
    """How a backend call actually ended."""

    POPULATED = "POPULATED"
    EMPTY_CONFIRMED = "EMPTY_CONFIRMED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class ResultStateViolation(ValueError):
    """A result state was reported in a way that hides a failure."""


def classify_result(
    *,
    backend_reachable: bool,
    backend_error: str | None,
    results: Sequence[Any],
    partial: bool = False,
) -> ResultState:
    """Derive the result state from what actually happened.

    An unreachable or errored backend yields `UNAVAILABLE` even when `results` is
    an empty list, because an empty list from a failed call carries no
    information about the world.
    """
    if not backend_reachable or backend_error:
        return ResultState.UNAVAILABLE
    if partial:
        return ResultState.DEGRADED
    return ResultState.POPULATED if results else ResultState.EMPTY_CONFIRMED


def is_empty_research_finding(state: ResultState | str) -> bool:
    """True only when emptiness is a confirmed observation about the world."""
    return ResultState(state) is ResultState.EMPTY_CONFIRMED


def supports_absence_claim(state: ResultState | str) -> bool:
    """Whether this state licenses saying "nothing exists in scope".

    `DEGRADED` does not: a partial answer cannot establish absence in the part
    that was never returned.
    """
    return is_empty_research_finding(state)


def require_honest_state(
    state: ResultState | str,
    *,
    backend_error: str | None,
) -> None:
    """Raise when a failed call is being reported as a confirmed emptiness."""
    resolved = ResultState(state)
    if backend_error and resolved is not ResultState.UNAVAILABLE:
        raise ResultStateViolation(
            f"backend reported error {backend_error!r} but the result state is {resolved}; "
            "a failure must not be presented as a research finding"
        )
