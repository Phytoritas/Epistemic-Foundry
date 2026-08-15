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

from ..domain.vocabularies import EVIDENCE_CLASSES, PROMOTION_LADDER, promotion_rank

#: How far up the ladder each evidence class can carry a claim on its own,
#: expressed as ladder indices over the shared vocabularies so neither the class
#: names nor the level names are re-spelled in this module. Index 5 is the top of
#: PROMOTION_LADDER (REPLICATED); index 1 is CANDIDATE.
_CEILING_RANK: dict[str, int] = {
    EVIDENCE_CLASSES[0]: 5,  # primary_empirical
    EVIDENCE_CLASSES[1]: 3,  # secondary_empirical
    EVIDENCE_CLASSES[2]: 2,  # modeling
    EVIDENCE_CLASSES[3]: 3,  # formal
    EVIDENCE_CLASSES[4]: 4,  # benchmark
    EVIDENCE_CLASSES[5]: 2,  # review
    EVIDENCE_CLASSES[6]: 1,  # background
    EVIDENCE_CLASSES[7]: 2,  # methodological
    EVIDENCE_CLASSES[8]: 1,  # user_generated
}

#: Default class for evidence that does not declare one: the weakest tier.
_DEFAULT_CLASS = EVIDENCE_CLASSES[6]

#: Public view: evidence class -> highest supportable promotion level.
METHOD_CEILING: dict[str, str] = {
    name: PROMOTION_LADDER[rank] for name, rank in _CEILING_RANK.items()
}

#: The passport promotion ladder, shared so a new level cannot appear in one
#: module and be missing from the other.
PROMOTION_ORDER = PROMOTION_LADDER


def stratify_by_method(
    evidence_nodes: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Group evidence by `evidence_class`.

    Returned as separate strata rather than a merged list, so a caller cannot
    accidentally pool incompatible methods by iterating one flat sequence.
    """
    strata: dict[str, list[Mapping[str, Any]]] = {}
    for node in evidence_nodes:
        strata.setdefault(str(node.get("evidence_class", _DEFAULT_CLASS)), []).append(node)
    return strata


def promotion_ceiling_for(evidence_nodes: Sequence[Mapping[str, Any]]) -> str:
    """Highest promotion level the available methods can support.

    With no evidence the ceiling is `INBOX`: nothing has been established.
    """
    if not evidence_nodes:
        return PROMOTION_LADDER[0]
    ranks = [
        _CEILING_RANK.get(str(node.get("evidence_class", _DEFAULT_CLASS)), 1)
        for node in evidence_nodes
    ]
    return PROMOTION_LADDER[max(ranks)]


def exceeds_method_ceiling(
    requested_level: str,
    evidence_nodes: Sequence[Mapping[str, Any]],
) -> bool:
    """True when `requested_level` is above what the methods can support."""
    ceiling = promotion_ceiling_for(evidence_nodes)
    return promotion_rank(requested_level) > promotion_rank(ceiling)
