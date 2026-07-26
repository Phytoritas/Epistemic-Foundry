"""Crossover compatibility (EF4-I50).

Contract source: `schemas/crossover-compatibility-report.schema.json`.

"Semantic collage is rejected" is the rule. Two hypotheses whose scopes,
measurements, units, or causal assumptions disagree cannot be spliced into a
third that inherits the strengths of both: the offspring would assert something
neither parent's evidence supports. So the decision is derived from the four
compatibility axes and `unknown` on any axis yields `NOT_ASSESSED` rather than a
permissive default — an unexamined axis is not a compatible one.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Axis values that block crossover outright.
BLOCKING_VALUES: frozenset[str] = frozenset({"incompatible"})

#: Axis values that permit crossover only after a named repair.
REPAIRABLE_VALUES: frozenset[str] = frozenset(
    {"conditional", "stratify", "convertible", "requires_new_assumption"}
)

#: The four axes that must all be examined.
COMPATIBILITY_AXES: tuple[str, ...] = (
    "scope_compatibility",
    "measurement_compatibility",
    "causal_compatibility",
    "unit_compatibility",
)


class CrossoverRejected(ValueError):
    """A crossover would splice incompatible parents."""


def build_crossover_report(
    *,
    candidate_ids: Sequence[str],
    scope_compatibility: str,
    measurement_compatibility: str,
    causal_compatibility: str,
    unit_compatibility: str,
    conflicts: Sequence[str],
    required_repairs: Sequence[str],
    report_id: str | None = None,
) -> dict[str, Any]:
    """Assess a crossover, deriving the decision from the four axes.

    `decision` is not a parameter. A caller able to assert `ALLOW` could splice
    parents whose measurements were never compared.
    """
    if len(candidate_ids) < 2:
        raise CrossoverRejected("a crossover requires at least two parent candidates")

    axes = {
        "scope_compatibility": scope_compatibility,
        "measurement_compatibility": measurement_compatibility,
        "causal_compatibility": causal_compatibility,
        "unit_compatibility": unit_compatibility,
    }
    values = set(axes.values())

    if "unknown" in values:
        decision = "NOT_ASSESSED"
    elif values & BLOCKING_VALUES:
        decision = "REJECT"
    elif values & REPAIRABLE_VALUES:
        if not required_repairs:
            raise CrossoverRejected(
                f"axes {sorted(values & REPAIRABLE_VALUES)} need repair but required_repairs is "
                "empty; an unnamed repair cannot be performed or reviewed"
            )
        decision = "ALLOW_WITH_REPAIR"
    else:
        decision = "ALLOW"

    report: dict[str, Any] = {
        "report_id": report_id or new_id("CCR"),
        "candidate_ids": list(candidate_ids),
        **axes,
        "conflicts": list(conflicts),
        "required_repairs": list(required_repairs),
        "decision": decision,
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("crossover-compatibility-report", report)
    return report


def crossover_permitted(report: Mapping[str, Any]) -> bool:
    """True only for an unconditional ALLOW.

    `ALLOW_WITH_REPAIR` is not permission to splice; it is permission to attempt
    the named repair first, and `NOT_ASSESSED` is the absence of an assessment.
    """
    return str(report.get("decision")) == "ALLOW"


def unexamined_axes(report: Mapping[str, Any]) -> list[str]:
    """Axes recorded as `unknown`, so a reviewer sees what was never compared."""
    return sorted(axis for axis in COMPATIBILITY_AXES if str(report.get(axis)) == "unknown")
