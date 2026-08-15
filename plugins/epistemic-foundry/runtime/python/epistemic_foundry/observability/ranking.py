"""Ranking integrity (EF4-I24).

A map labeled "ranked" must use a declared algorithm, and baseline centrality,
query relevance, and risk must stay separate signals.

The reason these three cannot be blended into one number: centrality says how
connected a node is regardless of the question, relevance says how well it
matches this question, and risk says how much harm a wrong answer causes. A
single score hides which of the three drove the ordering, so a reader cannot
tell a central-but-irrelevant node from a relevant-but-peripheral one.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: Signals that must remain separately reported.
SEPARATE_SIGNALS: tuple[str, ...] = ("baseline_centrality", "query_relevance", "risk")

#: Ranking algorithms the runtime can name. An unnamed algorithm is refused.
DECLARED_ALGORITHMS: frozenset[str] = frozenset(
    {"pagerank", "betweenness", "degree", "bm25", "hybrid_declared", "insertion_order"}
)


class RankingIntegrityError(ValueError):
    """A ranked label is unsupported or blends separate signals."""


def require_declared_ranking(
    *,
    labeled_ranked: bool,
    algorithm: str | None,
    entries: Sequence[Mapping[str, Any]],
) -> None:
    """Raise unless a ranked label is backed by a named algorithm and separate signals.

    `insertion_order` is a legitimate algorithm name for an unranked listing, but
    it may not be labeled ranked: calling arrival order a ranking invents an
    authority the ordering does not have.
    """
    if not labeled_ranked:
        return
    if not algorithm:
        raise RankingIntegrityError(
            "a map labeled ranked must name its algorithm; an unnamed ranking cannot be "
            "reproduced or challenged"
        )
    if algorithm not in DECLARED_ALGORITHMS:
        raise RankingIntegrityError(
            f"unknown ranking algorithm {algorithm!r}; declare it before labeling output ranked"
        )
    if algorithm == "insertion_order":
        raise RankingIntegrityError(
            "insertion order is not a ranking; labeling arrival order as ranked invents an "
            "authority the ordering does not have"
        )
    for index, entry in enumerate(entries):
        missing = [signal for signal in SEPARATE_SIGNALS if signal not in entry]
        if missing:
            raise RankingIntegrityError(
                f"entry {index} is missing separately reported signal(s) {missing}; a blended "
                "score hides which signal drove the ordering"
            )


def signals_are_separate(entry: Mapping[str, Any]) -> bool:
    """True when all three signals are individually present."""
    return all(signal in entry for signal in SEPARATE_SIGNALS)
