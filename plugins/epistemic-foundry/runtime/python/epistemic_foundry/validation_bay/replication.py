"""Independent preregistered replication (EF4-I58).

Contract source: `schemas/replication-plan.schema.json`.

"High scientific promotion after adaptive evolution requires an appropriate
independent preregistered replication or an explicit lower ceiling."

Two properties make a replication worth anything after adaptive search:

* Preregistration. Metrics and the success rule are fixed before the replication
  runs, because an adaptive search has already explored the space of analyses that
  favour the candidate, and choosing the analysis afterwards re-runs that search on
  the replication itself.
* Executor independence. A replication run by the party that produced the original
  result shares its assumptions, tooling, and blind spots, so agreement is weak
  evidence.

`promotion_ceiling_after_search` returns the ceiling rather than a boolean, so a
caller that cannot obtain a qualifying replication receives an explicit lower
ceiling instead of a refusal it might route around.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.vocabularies import PROMOTION_LADDER

#: Independence levels that make agreement meaningful. Anything weaker shares the
#: original's assumptions and tooling.
INDEPENDENT_EXECUTORS: frozenset[str] = frozenset({"independent_team", "third_party"})

#: Replication classes from `replication-plan.schema.json`. `multi_seed` is the
#: weakest: rerunning the same code on new seeds tests stability, not
#: independence, so it does not lift the post-search ceiling on its own.
REPLICATION_CLASSES: tuple[str, ...] = (
    "independent_code",
    "independent_data",
    "independent_team",
    "cross_method",
    "cross_scope",
    "multi_seed",
)

#: Classes that establish independence rather than mere stability.
INDEPENDENT_CLASSES: frozenset[str] = frozenset(
    {"independent_code", "independent_data", "independent_team", "cross_method", "cross_scope"}
)


class ReplicationPlanRefused(ValueError):
    """A replication plan cannot support the claim it is meant to license."""


def build_replication_plan(
    *,
    candidate_id: str,
    replication_class: str,
    executor_independence: str,
    environment_ids: Sequence[str],
    data_ids: Sequence[str],
    seeds: Sequence[int],
    preregistered_metrics: Sequence[str],
    success_rule: str,
    failure_rule: str,
    replication_plan_id: str | None = None,
) -> dict[str, Any]:
    """Build a replication plan with both rules fixed in advance.

    A plan with a success rule but no failure rule is refused: without a stated
    way to fail, any outcome can be read as support, which is exactly the freedom
    preregistration exists to remove.
    """
    if replication_class not in REPLICATION_CLASSES:
        raise ReplicationPlanRefused(
            f"unknown replication_class {replication_class!r}; known classes: "
            f"{list(REPLICATION_CLASSES)}"
        )
    if not preregistered_metrics:
        raise ReplicationPlanRefused(
            f"replication of {candidate_id} preregisters no metrics; choosing the metric after "
            "the run re-runs the adaptive search on the replication itself"
        )
    if not success_rule.strip():
        raise ReplicationPlanRefused("a replication plan requires a preregistered success rule")
    if not failure_rule.strip():
        raise ReplicationPlanRefused(
            f"replication of {candidate_id} states no failure rule; without a stated way to fail, "
            "any outcome can be read as support"
        )
    if not seeds:
        raise ReplicationPlanRefused(
            "a replication plan must pin its seeds; an unpinned seed makes the run unreproducible "
            "even by its own authors"
        )

    plan: dict[str, Any] = {
        "replication_plan_id": replication_plan_id or new_id("RP"),
        "candidate_id": candidate_id,
        "replication_class": replication_class,
        "executor_independence": executor_independence,
        "environment_ids": list(environment_ids),
        "data_ids": list(data_ids),
        "seeds": [int(seed) for seed in seeds],
        "preregistered_metrics": list(preregistered_metrics),
        "success_rule": success_rule,
        "failure_rule": failure_rule,
    }
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    validate_artifact("replication-plan", plan)
    return plan


def replication_qualifies(plan: Mapping[str, Any]) -> bool:
    """Whether this plan can license high promotion after adaptive search.

    `multi_seed` is excluded even with an independent executor: rerunning the same
    code on new seeds measures stability, and a result can be perfectly stable and
    still wrong for the same reason every time.
    """
    return (
        str(plan.get("executor_independence")) in INDEPENDENT_EXECUTORS
        and str(plan.get("replication_class")) in INDEPENDENT_CLASSES
        and bool(plan.get("preregistered_metrics"))
        and bool(str(plan.get("failure_rule") or "").strip())
    )


def promotion_ceiling_after_search(
    *,
    adaptive_search_used: bool,
    replication_plan: Mapping[str, Any] | None,
) -> str:
    """Highest promotion level the available replication evidence supports.

    Returns an explicit ceiling rather than raising, so a run without a qualifying
    replication receives a documented lower bound instead of a refusal it might
    route around. Without adaptive search the ladder is unconstrained by this rule.
    """
    if not adaptive_search_used:
        return PROMOTION_LADDER[-1]
    if replication_plan is None:
        return "EMPIRICALLY_TESTED"
    if replication_qualifies(replication_plan):
        return PROMOTION_LADDER[-1]
    return "EMPIRICALLY_TESTED"
