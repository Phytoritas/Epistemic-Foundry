"""Method comparability and promotion ceilings (EF4-I07).

Method-incompatible evidence is stratified rather than pooled. Averaging an
observational correlation with a randomized trial produces a number that
describes neither, so `stratify_by_method` groups evidence and
`promotion_ceiling_for` caps how far the weakest available method can carry a
claim.

The ceiling is deliberately set by the *strongest* method present, not by a
blend: a randomized trial is not weakened by the existence of weaker
corroboration, but weak evidence alone cannot reach the top of the ladder.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: Highest promotion level each evidence class can support on its own.
#: Levels come from `hypothesis-passport.schema.json` promotion_level.
METHOD_CEILING: dict[str, str] = {
    "primary_empirical": "REPLICATED",
    "benchmark": "EMPIRICALLY_TESTED",
    "secondary_empirical": "VALIDATION_SCREENED",
    "formal": "VALIDATION_SCREENED",
    "modeling": "LITERATURE_GROUNDED",
    "review": "LITERATURE_GROUNDED",
    "methodological": "LITERATURE_GROUNDED",
    "background": "CANDIDATE",
    "user_generated": "CANDIDATE",
}

#: Same ordering as the passport promotion ladder.
PROMOTION_ORDER: tuple[str, ...] = (
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
)


def stratify_by_method(
    evidence_nodes: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Group evidence by `evidence_class`.

    Returned as separate strata rather than a merged list, so a caller cannot
    accidentally pool incompatible methods by iterating one flat sequence.
    """
    strata: dict[str, list[Mapping[str, Any]]] = {}
    for node in evidence_nodes:
        strata.setdefault(str(node.get("evidence_class", "background")), []).append(node)
    return strata


def promotion_ceiling_for(evidence_nodes: Sequence[Mapping[str, Any]]) -> str:
    """Highest promotion level the available methods can support.

    With no evidence the ceiling is `INBOX`: nothing has been established.
    """
    if not evidence_nodes:
        return "INBOX"
    ceilings = [
        METHOD_CEILING.get(str(node.get("evidence_class", "background")), "CANDIDATE")
        for node in evidence_nodes
    ]
    return max(ceilings, key=PROMOTION_ORDER.index)


def exceeds_method_ceiling(
    requested_level: str,
    evidence_nodes: Sequence[Mapping[str, Any]],
) -> bool:
    """True when `requested_level` is above what the methods can support."""
    ceiling = promotion_ceiling_for(evidence_nodes)
    return PROMOTION_ORDER.index(requested_level) > PROMOTION_ORDER.index(ceiling)
