"""Adjudication records.

Contract source: `schemas/adjudication.schema.json`.

The schema carries a field most designs would omit:
`deterministic_gate_override_attempted`. Its presence encodes a policy — an
attempted override is evidence about the deliberation, so it is recorded rather
than discarded. This module computes that flag from the inputs instead of
trusting a caller-supplied boolean, because the party attempting an override is
the last one who should get to declare it did not happen.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Verdicts that assert the hypothesis holds to some degree.
POSITIVE_VERDICTS = frozenset({"ENTAILED", "SUPPORTED", "CONDITIONAL"})

#: Recommendations above plain triage. Reaching any of these while a
#: deterministic gate failed is an override attempt.
ADVANCING_RECOMMENDATIONS = frozenset(
    {
        "CANDIDATE",
        "LITERATURE_GROUNDED",
        "VALIDATION_SCREENED",
        "EMPIRICALLY_TESTED",
        "REPLICATED",
    }
)


class GateOverrideAttempted(PermissionError):
    """A deliberative verdict tried to advance past a failed deterministic gate."""


def _gates_failed(gate_decisions: Sequence[dict[str, Any]]) -> list[str]:
    """Names of gates that did not pass or receive a legitimate waiver."""
    return [
        str(decision.get("name"))
        for decision in gate_decisions
        if decision.get("status") not in {"PASS", "WAIVE"}
    ]


def build_adjudication(
    *,
    run_id: str,
    hypothesis_id: str,
    gate_decisions: Sequence[dict[str, Any]],
    brief_ids: Sequence[str],
    cross_examination_ids: Sequence[str],
    verdict: str,
    promotion_recommendation: str,
    rationale: str,
    strongest_support_id: str | None,
    strongest_counterevidence_id: str | None,
    minority_report_ids: Sequence[str] = (),
    unresolved_issue_ids: Sequence[str] = (),
    scope_narrowing: Sequence[str] = (),
    adjudication_id: str | None = None,
    created_at: str | None = None,
    refuse_override: bool = True,
) -> dict[str, Any]:
    """Build an adjudication record bound to its deterministic gate results.

    When a gate failed and the deliberation still recommends advancement, the
    attempt is recorded. With `refuse_override` (the default) the call also
    raises, so a caller must handle the conflict rather than persist a verdict
    that contradicts a hard gate.
    """
    failed = _gates_failed(gate_decisions)
    advancing = promotion_recommendation in ADVANCING_RECOMMENDATIONS
    override_attempted = bool(failed) and advancing

    record: dict[str, Any] = {
        "adjudication_id": adjudication_id or new_id("ADJ"),
        "run_id": run_id,
        "hypothesis_id": hypothesis_id,
        "gate_decision_ids": [str(decision["gate_id"]) for decision in gate_decisions],
        "brief_ids": list(brief_ids),
        "cross_examination_ids": list(cross_examination_ids),
        "minority_report_ids": list(minority_report_ids),
        "verdict": verdict,
        "scope_narrowing": list(scope_narrowing),
        "strongest_support_id": strongest_support_id,
        "strongest_counterevidence_id": strongest_counterevidence_id,
        "unresolved_issue_ids": list(unresolved_issue_ids),
        "promotion_recommendation": promotion_recommendation,
        "rationale": rationale,
        "deterministic_gate_override_attempted": override_attempted,
        "created_at": created_at or utc_now_iso(),
    }
    record["adjudication_hash"] = hash_excluding(record, "adjudication_hash")
    validate_artifact("adjudication", record)

    if override_attempted and refuse_override:
        raise GateOverrideAttempted(
            f"adjudication recommends {promotion_recommendation} while deterministic gate(s) "
            f"{', '.join(sorted(failed))} did not pass; a verdict cannot override a hard gate"
        )
    return record


def recommendation_is_binding(adjudication: dict[str, Any]) -> bool:
    """Always False: a Parliament recommendation is never promotion authority.

    Kept as an explicit predicate rather than an omission so a caller reaching
    for "did the Parliament approve this?" finds a documented no instead of
    inventing its own truthy check on `promotion_recommendation`.
    """
    return False
