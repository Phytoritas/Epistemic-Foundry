"""Falsifiable-intake gate (EF4-I03).

An insight must carry scope, at least one prediction, and at least one falsifier
before it may enter Observe or Parliament. The falsifier requirement is the
load-bearing one: a proposal that no observation could contradict cannot be
wrong, and admitting it spends evaluation budget on a question no evidence will
ever settle.

`intake_blockers` returns every reason at once so an author fixes the whole gap
in one revision rather than discovering the next missing field on resubmission.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: Scope fields that must be populated for an insight to be locatable.
REQUIRED_SCOPE_FIELDS: tuple[str, ...] = ("domain", "population", "unit_of_analysis")


class IntakeRejected(ValueError):
    """An insight is not admissible to Observe or Parliament."""


def intake_blockers(insight: Mapping[str, Any]) -> list[str]:
    """Every reason this insight cannot be admitted."""
    blockers: list[str] = []

    scope = insight.get("scope")
    if not isinstance(scope, Mapping) or not scope:
        blockers.append("missing scope: an insight with no scope cannot be located or compared")
    else:
        empty = [
            field
            for field in REQUIRED_SCOPE_FIELDS
            if not str(scope.get(field) or "").strip()
        ]
        if empty:
            blockers.append(f"scope is missing required field(s): {sorted(empty)}")

    predictions = insight.get("prediction_ids") or insight.get("predictions") or []
    if not isinstance(predictions, Sequence) or isinstance(predictions, (str, bytes)) or not predictions:
        blockers.append("missing predictions: an insight that predicts nothing cannot be tested")

    falsifiers = insight.get("falsifier_ids") or insight.get("falsifiers") or []
    if not isinstance(falsifiers, Sequence) or isinstance(falsifiers, (str, bytes)) or not falsifiers:
        blockers.append(
            "missing falsifier: an insight no observation could contradict cannot be wrong, "
            "so it cannot enter Observe or Parliament"
        )

    return blockers


def admit_insight(insight: Mapping[str, Any]) -> None:
    """Raise `IntakeRejected` listing every blocker, or return on success."""
    blockers = intake_blockers(insight)
    if blockers:
        raise IntakeRejected("; ".join(blockers))


def is_admissible(insight: Mapping[str, Any]) -> bool:
    """Non-raising variant for triage surfaces."""
    return not intake_blockers(insight)
