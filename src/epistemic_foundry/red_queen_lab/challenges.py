"""Challenge genomes, results, and co-evolution rounds.

Contract sources: `schemas/challenge-genome.schema.json`,
`schemas/challenge-result.schema.json`, `schemas/red-queen-round.schema.json`.

The design rule here is that survival must be earned. `survived_challenges`
counts a candidate as surviving only when at least one challenge actually ran
and every executed match resolved in the candidate's favour. `INCONCLUSIVE` and
`ERROR` are unresolved, not wins: treating a crashed adversary as a passed test
is the cheapest way to manufacture a robust-looking candidate.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Outcomes where the candidate withstood the challenge.
SURVIVING_OUTCOMES = frozenset({"SURVIVED"})

#: Outcomes that defeat or bound the candidate.
ADVERSE_OUTCOMES = frozenset({"REFUTED", "SCOPE_RESTRICTED"})

#: Outcomes that resolve nothing. They must never read as survival.
UNRESOLVED_OUTCOMES = frozenset({"INCONCLUSIVE", "ERROR", "METHOD_FAILURE"})

#: How many independent runs an apparent refutation needs before it counts
#: (EF4-I51). One adverse result can be a flake in the challenge itself, and
#: retracting a hypothesis on an unreplicated failure is as wrong as promoting on
#: an unreplicated success.
REFUTATION_REPLICATION_REQUIRED = 2


class RefutationNotReplicated(RuntimeError):
    """An apparent refutation has not been reproduced enough to stand."""


class ChallengeContractViolation(ValueError):
    """A challenge artifact or round violates the co-evolution contract."""


def build_challenge_genome(
    *,
    target_genome_id: str,
    challenge_class: str,
    construction: str,
    success_criterion: str,
    required_capabilities: Sequence[str],
    lineage_id: str,
    safety_class: str = "safe",
    challenge_genome_id: str | None = None,
) -> dict[str, Any]:
    """Build a challenge aimed at one target genome.

    `success_criterion` is required and non-empty: a challenge without a stated
    win condition cannot be adjudicated, so its result would be whatever the
    reader wants it to be.
    """
    if not success_criterion.strip():
        raise ChallengeContractViolation(
            "a challenge must state a success_criterion; an unadjudicable challenge proves nothing"
        )
    if not construction.strip():
        raise ChallengeContractViolation("a challenge must describe its construction to be reproducible")
    genome: dict[str, Any] = {
        "challenge_genome_id": challenge_genome_id or new_id("CG"),
        "target_genome_id": target_genome_id,
        "challenge_class": challenge_class,
        "construction": construction,
        "success_criterion": success_criterion,
        "required_capabilities": list(required_capabilities),
        "safety_class": safety_class,
        "lineage_id": lineage_id,
    }
    validate_artifact("challenge-genome", genome)
    return genome


def build_challenge_result(
    *,
    challenge_genome_id: str,
    target_candidate_id: str,
    stage_result_id: str,
    outcome: str,
    severity: str,
    observed_effect: str,
    reproduction_artifact_ids: Sequence[str] = (),
    challenge_result_id: str | None = None,
) -> dict[str, Any]:
    """Record one challenge match.

    An adverse outcome must carry a reproduction artifact: a refutation nobody
    can reproduce is an assertion, and the candidate's author would be right to
    dispute it.
    """
    if outcome in ADVERSE_OUTCOMES and not reproduction_artifact_ids:
        raise ChallengeContractViolation(
            f"outcome {outcome} requires at least one reproduction artifact; "
            "an irreproducible refutation is not evidence"
        )
    result: dict[str, Any] = {
        "challenge_result_id": challenge_result_id or new_id("CR"),
        "challenge_genome_id": challenge_genome_id,
        "target_candidate_id": target_candidate_id,
        "stage_result_id": stage_result_id,
        "outcome": outcome,
        "severity": severity,
        "observed_effect": observed_effect,
        "reproduction_artifact_ids": list(reproduction_artifact_ids),
    }
    result["result_hash"] = hash_excluding(result, "result_hash")
    validate_artifact("challenge-result", result)
    return result


def survived_challenges(
    candidate_id: str,
    results: Sequence[Mapping[str, Any]],
) -> bool:
    """True only when the candidate faced at least one challenge and won them all.

    Feeds `PromotionRequest.challenge_survived`. An unchallenged candidate
    returns False, so promotion cannot credit robustness that was never tested.
    """
    matches = [result for result in results if result.get("target_candidate_id") == candidate_id]
    if not matches:
        return False
    return all(str(result.get("outcome")) in SURVIVING_OUTCOMES for result in matches)


def unresolved_matches(results: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Matches that resolved nothing and still owe a rerun."""
    return [result for result in results if str(result.get("outcome")) in UNRESOLVED_OUTCOMES]


def refutation_stands(
    challenge_genome_id: str,
    candidate_id: str,
    results: Sequence[Mapping[str, Any]],
) -> bool:
    """True only when the same challenge refuted the candidate repeatedly.

    Counts independent runs of one challenge against one candidate. A single
    adverse result may be a flake in the challenge rather than a defect in the
    hypothesis, so `REFUTATION_REPLICATION_REQUIRED` runs must agree before the
    refutation is treated as established.
    """
    matching = [
        result
        for result in results
        if str(result.get("challenge_genome_id")) == challenge_genome_id
        and str(result.get("target_candidate_id")) == candidate_id
        and str(result.get("outcome")) in ADVERSE_OUTCOMES
    ]
    return len(matching) >= REFUTATION_REPLICATION_REQUIRED


def require_replicated_refutation(
    challenge_genome_id: str,
    candidate_id: str,
    results: Sequence[Mapping[str, Any]],
) -> None:
    """Raise unless an apparent refutation has replicated."""
    if not refutation_stands(challenge_genome_id, candidate_id, results):
        raise RefutationNotReplicated(
            f"challenge {challenge_genome_id} against {candidate_id} has not replicated "
            f"{REFUTATION_REPLICATION_REQUIRED} times; retracting on an unreplicated failure is "
            "as wrong as promoting on an unreplicated success"
        )


def partition_adverse_outcomes(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Split adverse results into refutations and boundary restrictions.

    A `SCOPE_RESTRICTED` outcome narrows where a claim holds; `REFUTED` says it
    does not hold. Returning them as separate lists keeps the boundary knowledge a
    restriction produces, which a single "failed" bucket would erase.
    """
    refuted: list[str] = []
    restricted: list[str] = []
    for result in results:
        outcome = str(result.get("outcome"))
        target = str(result.get("target_candidate_id"))
        if outcome == "REFUTED":
            refuted.append(target)
        elif outcome == "SCOPE_RESTRICTED":
            restricted.append(target)
    return {"refuted": sorted(set(refuted)), "scope_restricted": sorted(set(restricted))}


def build_red_queen_round(
    *,
    evolution_run_id: str,
    generation: int,
    hypothesis_candidate_ids: Sequence[str],
    challenge_candidate_ids: Sequence[str],
    results: Sequence[Mapping[str, Any]],
    challenge_overfit_checks: Sequence[str],
    new_boundary_condition_ids: Sequence[str] = (),
    match_ids: Sequence[str] | None = None,
    round_id: str | None = None,
) -> dict[str, Any]:
    """Summarize one co-evolution round from its actual match results.

    Survivor and refuted sets are derived from `results`, never supplied: a
    caller-declared survivor list is how an unchallenged candidate ends up
    counted as robust.
    """
    if not challenge_overfit_checks:
        raise ChallengeContractViolation(
            "a round must record challenge_overfit_checks; co-evolved challenges can overfit "
            "their target and then measure nothing"
        )
    refuted = sorted(
        {
            str(result["target_candidate_id"])
            for result in results
            if str(result.get("outcome")) in ADVERSE_OUTCOMES
        }
    )
    survivors = sorted(
        candidate_id
        for candidate_id in hypothesis_candidate_ids
        if survived_challenges(candidate_id, results)
    )
    overlap = set(survivors) & set(refuted)
    if overlap:
        raise ChallengeContractViolation(
            f"candidate(s) {sorted(overlap)} appear as both survivor and refuted"
        )

    round_record: dict[str, Any] = {
        "round_id": round_id or new_id("RQR"),
        "evolution_run_id": evolution_run_id,
        "generation": int(generation),
        "hypothesis_candidate_ids": list(hypothesis_candidate_ids),
        "challenge_candidate_ids": list(challenge_candidate_ids),
        "match_ids": list(
            match_ids
            if match_ids is not None
            else [str(result["challenge_result_id"]) for result in results]
        ),
        "survivor_ids": survivors,
        "refuted_ids": refuted,
        "new_boundary_condition_ids": list(new_boundary_condition_ids),
        "challenge_overfit_checks": list(challenge_overfit_checks),
    }
    round_record["round_hash"] = hash_excluding(round_record, "round_hash")
    validate_artifact("red-queen-round", round_record)
    return round_record
