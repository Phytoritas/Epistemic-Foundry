"""Downstream invalidation on correction or retraction (EF4-I38).

Contract source: `schemas/update-impact-report.schema.json`.

`dependent_closure` walks the dependency graph transitively. A one-hop
invalidation is the common bug: retracting a document invalidates the claims that
cite it, but the Passports built from those claims keep asserting a conclusion
whose foundation is gone. Following the closure is what makes the correction
actually applied rather than merely recorded.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Trigger types that invalidate rather than merely add. `new_document` is
#: excluded: new evidence may change a conclusion but does not make existing
#: artifacts unsound, so it warrants reassessment rather than invalidation.
INVALIDATING_TRIGGERS: frozenset[str] = frozenset(
    {
        "document_correction",
        "document_retraction",
        "claim_correction",
        "ontology_update",
        "policy_update",
        "schema_migration",
    }
)

#: Remediation actions from `update-impact-report.schema.json` required_actions.
#: `no_action` is deliberately not usable for an invalidating trigger: see
#: `build_impact_report`.
REMEDIATION_ACTIONS: tuple[str, ...] = (
    "reparse",
    "reextract",
    "reretrieve",
    "redeliberate",
    "revalidate",
    "human_review",
    "no_action",
)

#: The one action that is not a remediation.
NO_ACTION = "no_action"


def dependent_closure(
    seeds: Sequence[str],
    dependents: Mapping[str, Sequence[str]],
) -> list[str]:
    """All artifacts reachable from `seeds`, transitively.

    Cycles are tolerated: a visited set bounds the walk, because a dependency
    graph built from real provenance can contain a loop and an unbounded walk
    would hang rather than report.
    """
    seen: set[str] = set()
    frontier = [str(seed) for seed in seeds]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(str(child) for child in dependents.get(current, ()))
    return sorted(seen - {str(seed) for seed in seeds})


def build_impact_report(
    *,
    trigger_event_id: str,
    trigger_type: str,
    affected_claim_ids: Sequence[str],
    affected_evidence_ids: Sequence[str],
    affected_pack_ids: Sequence[str],
    affected_passport_ids: Sequence[str],
    required_actions: Sequence[str],
    priority: str = "P1",
    invalidated_artifact_ids: Sequence[str] | None = None,
    impact_report_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record the blast radius of one update.

    For an invalidating trigger, `invalidated_artifact_ids` defaults to the union
    of every affected id rather than to an empty list: an invalidating change that
    reports nothing invalidated has recorded the trigger without applying it.
    """
    affected_union = sorted(
        {
            *(str(item) for item in affected_claim_ids),
            *(str(item) for item in affected_evidence_ids),
            *(str(item) for item in affected_pack_ids),
            *(str(item) for item in affected_passport_ids),
        }
    )
    if invalidated_artifact_ids is None:
        invalidated = affected_union if trigger_type in INVALIDATING_TRIGGERS else []
    else:
        invalidated = [str(item) for item in invalidated_artifact_ids]

    if trigger_type in INVALIDATING_TRIGGERS and affected_union and not invalidated:
        raise ValueError(
            f"trigger {trigger_type} affects {len(affected_union)} artifact(s) but invalidates "
            "none; an invalidating change that invalidates nothing has been recorded rather "
            "than applied"
        )
    if not required_actions:
        raise ValueError(
            "an impact report must state required actions; a blast radius with no follow-up "
            "is a notification, not a remediation"
        )
    if trigger_type in INVALIDATING_TRIGGERS and set(required_actions) == {NO_ACTION}:
        raise ValueError(
            f"trigger {trigger_type} invalidates artifacts but requires {NO_ACTION}; an "
            "invalidation with no remediation leaves dependents void and unaddressed"
        )

    report: dict[str, Any] = {
        "impact_report_id": impact_report_id or new_id("UIR"),
        "trigger_event_id": trigger_event_id,
        "trigger_type": trigger_type,
        "affected_claim_ids": list(affected_claim_ids),
        "affected_evidence_ids": list(affected_evidence_ids),
        "affected_pack_ids": list(affected_pack_ids),
        "affected_passport_ids": list(affected_passport_ids),
        "invalidated_artifact_ids": invalidated,
        "required_actions": list(required_actions),
        "priority": priority,
        "created_at": created_at or utc_now_iso(),
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("update-impact-report", report)
    return report


def trigger_invalidates(trigger_type: str) -> bool:
    """Whether this trigger voids dependents rather than prompting reassessment."""
    return trigger_type in INVALIDATING_TRIGGERS
