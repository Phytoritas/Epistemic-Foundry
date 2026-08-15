"""Shared wire vocabularies (EF4-I22).

`CLI, MCP, HTTP, persistence and UI models derive from canonical schemas;
duplicated wire literals are forbidden.`

A vocabulary belongs here when two or more components serialize *the same*
schema list. Tokens that merely look alike stay separate: `null` as an evidence
role and `null` as an archive entry class are different vocabularies that happen
to share a spelling, and forcing them to share a constant would invent coupling
the schemas do not have.

What is centralized here is the opposite case — lists that are genuinely one
vocabulary read by several modules, where a second copy would drift the moment
the schema gains a value.
"""

from __future__ import annotations

#: Promotion ladder from `hypothesis-passport.schema.json` promotion_level.
#: Read by the passport (to bound status combinations) and by method
#: comparability (to cap what weak evidence can support).
PROMOTION_LADDER: tuple[str, ...] = (
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
)

#: Evidence classes from `evidence-node.schema.json` evidence_class. Read by
#: method comparability (for promotion ceilings) and by the relabeling guard
#: (to define the empirical boundary).
EVIDENCE_CLASSES: tuple[str, ...] = (
    "primary_empirical",
    "secondary_empirical",
    "modeling",
    "formal",
    "benchmark",
    "review",
    "background",
    "methodological",
    "user_generated",
)

#: Evidence classes recording direct empirical observation.
EMPIRICAL_EVIDENCE_CLASSES: frozenset[str] = frozenset(
    {"primary_empirical", "secondary_empirical"}
)

#: Evidence classes that are derived, simulated, formal, or secondhand.
NON_EMPIRICAL_EVIDENCE_CLASSES: frozenset[str] = frozenset(
    set(EVIDENCE_CLASSES) - EMPIRICAL_EVIDENCE_CLASSES
)


def promotion_rank(level: str) -> int:
    """Position of `level` in the ladder; raises for an unknown level."""
    try:
        return PROMOTION_LADDER.index(level)
    except ValueError as exc:
        raise ValueError(f"unknown promotion level {level!r}") from exc
