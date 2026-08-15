"""Fitness vectors that order search without promoting (EF4-I45).

Contract source: `schemas/fitness-vector.schema.json`.

`scalarize_for_ordering` exists and is deliberately named for what it may be used
for: ordering a search frontier. It returns a bare float with no accompanying
status, so a caller cannot mistake it for a verdict, and `build_fitness_vector`
keeps `dimensions` separate alongside an explicit `hard_gate_status`.

The vector refuses to report a passing gate status while carrying gate failures,
which is the inconsistency that would let a scalar-driven search declare a
candidate ready.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.ids import new_id
from ..domain.time import utc_now_iso


class FitnessViolation(ValueError):
    """A fitness vector contradicts its own gate status."""


#: The fifteen dimensions `fitness-vector.schema.json` requires. All are
#: mandatory, which is a stronger contract than it first appears: a partial vector
#: cannot pass as complete, so a candidate scored only on the dimensions that
#: favour it is rejected rather than silently ranked.
FITNESS_DIMENSIONS: tuple[str, ...] = (
    "grounding",
    "support",
    "counterevidence_resistance",
    "predictive_accuracy",
    "calibration",
    "robustness",
    "causal_identifiability",
    "falsifiability",
    "novelty",
    "parsimony",
    "information_gain",
    "coverage_value",
    "replicability",
    "cost_efficiency",
    "safety",
)


def unscored_dimensions(dimensions: Mapping[str, Any]) -> list[str]:
    """Required dimensions this vector does not score."""
    return sorted(set(FITNESS_DIMENSIONS) - set(dimensions))


def missing_uncertainty(uncertainty: Mapping[str, Any]) -> list[str]:
    """Dimensions scored without a stated uncertainty.

    The schema mirrors every dimension in `uncertainty`, which encodes a real
    rule: a point estimate with no stated uncertainty invites comparison it cannot
    support.
    """
    return sorted(set(FITNESS_DIMENSIONS) - set(uncertainty))


def build_fitness_vector(
    *,
    candidate_id: str,
    hard_gate_status: str,
    hard_gate_failures: Sequence[str],
    dimensions: Mapping[str, Any],
    uncertainty: Mapping[str, Any],
    evidence_receipt_ids: Sequence[str],
    pareto_rank: int,
    domination_count: int,
    fitness_vector_id: str | None = None,
    computed_at: str | None = None,
) -> dict[str, Any]:
    """Build a fitness vector with separated dimensions.

    A `PASS` status alongside recorded failures is refused: the two cannot both be
    true, and permitting it would let a high-scoring candidate carry a passing
    label while its gates failed.
    """
    if hard_gate_status == "PASS" and hard_gate_failures:
        raise FitnessViolation(
            f"candidate {candidate_id} reports hard_gate_status PASS while carrying "
            f"{len(hard_gate_failures)} gate failure(s); a scalar score cannot reconcile that"
        )
    if hard_gate_status in {"FAIL", "PARTIAL"} and not hard_gate_failures:
        raise FitnessViolation(
            f"candidate {candidate_id} reports hard_gate_status {hard_gate_status} with no named "
            "failure; an unexplained non-pass cannot be acted on"
        )
    if not dimensions:
        raise FitnessViolation(
            "a fitness vector must carry at least one named dimension; a vector with no "
            "dimensions is a scalar wearing a vector's name"
        )
    missing = unscored_dimensions(dimensions)
    if missing:
        raise FitnessViolation(
            f"candidate {candidate_id} is unscored on {missing}; a partial vector would let a "
            "candidate be ranked only on the dimensions that favour it"
        )
    absent_uncertainty = missing_uncertainty(uncertainty)
    if absent_uncertainty:
        raise FitnessViolation(
            f"candidate {candidate_id} states no uncertainty for {absent_uncertainty}; a point "
            "estimate with no uncertainty invites comparison it cannot support"
        )

    vector: dict[str, Any] = {
        "fitness_vector_id": fitness_vector_id or new_id("FV"),
        "candidate_id": candidate_id,
        "hard_gate_status": hard_gate_status,
        "hard_gate_failures": list(hard_gate_failures),
        "dimensions": dict(dimensions),
        "uncertainty": dict(uncertainty),
        "evidence_receipt_ids": list(evidence_receipt_ids),
        "pareto_rank": int(pareto_rank),
        "domination_count": int(domination_count),
        "computed_at": computed_at or utc_now_iso(),
    }
    validate_artifact("fitness-vector", vector)
    return vector


def scalarize_for_ordering(
    vector: Mapping[str, Any],
    weights: Mapping[str, float] | None = None,
) -> float:
    """Collapse dimensions into one number, for search ordering only.

    Returns a bare float deliberately: there is no status or verdict attached, so
    the result cannot be mistaken for a promotion signal. Callers deciding
    promotion must use `governance.decide_promotion`, which has no score input.
    """
    dimensions = vector.get("dimensions") or {}
    if not dimensions:
        return 0.0
    active = weights or {name: 1.0 for name in dimensions}
    total = 0.0
    weight_sum = 0.0
    for name, value in dimensions.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        weight = float(active.get(name, 0.0))
        total += float(value) * weight
        weight_sum += abs(weight)
    return total / weight_sum if weight_sum else 0.0


def may_promote_on_score(vector: Mapping[str, Any]) -> bool:
    """Always False: a fitness vector is search guidance, not promotion authority.

    Kept explicit so a caller asking "is this candidate good enough?" finds a
    documented no rather than writing a threshold comparison.
    """
    return False
