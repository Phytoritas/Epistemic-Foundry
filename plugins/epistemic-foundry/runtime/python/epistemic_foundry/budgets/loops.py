"""Loop contracts with mandatory termination conditions (EF4-I27).

Contract source: `schemas/loop-contract.schema.json`.

`loop_should_continue` enforces four independent stop conditions: iteration
count, cost, wall clock, and dry rounds. Any one of them ending the loop is
enough. The dry-round rule is the one that catches the subtle failure: a loop
that keeps producing already-seen candidates is not converging, it is spinning,
and without a dedupe key it would report each rediscovery as progress.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.status import NonconvergenceOutcome


class LoopContractViolation(ValueError):
    """A loop contract omits a termination condition."""


def build_loop_contract(
    *,
    workflow_id: str,
    entry_node_id: str,
    exit_node_id: str,
    state_artifact_id: str,
    convergence_metric: str,
    convergence_predicate: str,
    max_iterations: int,
    max_cost_units: float,
    max_wall_seconds: int,
    dry_rounds_required: int,
    dedupe_key: str,
    seen_set_scope: str = "run",
    on_nonconvergence: str = NonconvergenceOutcome.ESCALATE.value,
    loop_id: str | None = None,
) -> dict[str, Any]:
    """Seal a loop contract with every stop condition present.

    Each bound must be positive. A zero or negative maximum is not an
    "unlimited" shorthand here — it would make the loop unbounded while the
    contract claims otherwise, which is the misreading this check prevents.
    """
    for name, value in (
        ("max_iterations", max_iterations),
        ("max_cost_units", max_cost_units),
        ("max_wall_seconds", max_wall_seconds),
    ):
        if value <= 0:
            raise LoopContractViolation(
                f"{name} must be positive; a non-positive bound leaves the loop unbounded while "
                "the contract claims a limit"
            )
    if dry_rounds_required < 1:
        raise LoopContractViolation(
            "dry_rounds_required must be at least 1; without a dry-round rule a loop that keeps "
            "rediscovering seen candidates reports spinning as progress"
        )
    if not dedupe_key.strip():
        raise LoopContractViolation(
            "a loop contract requires a dedupe_key; with no seen-set key novelty cannot be "
            "distinguished from rediscovery"
        )

    contract: dict[str, Any] = {
        "loop_id": loop_id or new_id("LC"),
        "workflow_id": workflow_id,
        "entry_node_id": entry_node_id,
        "exit_node_id": exit_node_id,
        "state_artifact_id": state_artifact_id,
        "convergence_metric": convergence_metric,
        "convergence_predicate": convergence_predicate,
        "max_iterations": int(max_iterations),
        "max_cost_units": float(max_cost_units),
        "max_wall_seconds": int(max_wall_seconds),
        "dry_rounds_required": int(dry_rounds_required),
        "dedupe_key": dedupe_key,
        "seen_set_scope": seen_set_scope,
        "on_nonconvergence": on_nonconvergence,
    }
    contract["contract_hash"] = hash_excluding(contract, "contract_hash")
    validate_artifact("loop-contract", contract)
    return contract


def loop_should_continue(
    contract: Mapping[str, Any],
    *,
    iteration: int,
    cost_units: float,
    wall_seconds: int,
    consecutive_dry_rounds: int,
    converged: bool = False,
) -> tuple[bool, str]:
    """Return `(continue, reason)`; any single bound ends the loop.

    Reasons are returned rather than logged so a caller records why the loop
    stopped instead of inferring it from an absent result.
    """
    if converged:
        return False, "convergence predicate satisfied"
    if iteration >= int(contract["max_iterations"]):
        return False, f"max_iterations {contract['max_iterations']} reached"
    if cost_units >= float(contract["max_cost_units"]):
        return False, f"max_cost_units {contract['max_cost_units']} reached"
    if wall_seconds >= int(contract["max_wall_seconds"]):
        return False, f"max_wall_seconds {contract['max_wall_seconds']} reached"
    if consecutive_dry_rounds >= int(contract["dry_rounds_required"]):
        return (
            False,
            f"{consecutive_dry_rounds} consecutive dry round(s) with no novel candidate",
        )
    return True, "within all bounds"


def nonconvergence_outcome(contract: Mapping[str, Any]) -> str:
    """What a non-converged loop must report, per its contract."""
    return str(contract["on_nonconvergence"])
