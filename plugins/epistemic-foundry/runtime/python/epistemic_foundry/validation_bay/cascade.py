"""Cascade planning, stage results, and fail-closed aggregation.

Contract sources: `schemas/validation-cascade-plan.schema.json` and
`schemas/stage-evaluation-result.schema.json`.

`aggregate_cascade_status` returns a `hard_gate_status` in the vocabulary the
promotion authority consumes (`PASS`, `FAIL`, `PARTIAL`). It is deliberately
pessimistic: any FAIL/BLOCKED/ERROR makes the cascade FAIL, any NOT_RUN or
PARTIAL keeps it PARTIAL, and only a fully executed, fully passing cascade
reports PASS.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Stage outcomes that stop the cascade.
TERMINAL_FAILURE_STATUSES = frozenset({"FAIL", "BLOCKED", "ERROR"})

#: Stage outcomes that leave the cascade incomplete.
INCOMPLETE_STATUSES = frozenset({"PARTIAL", "NOT_RUN"})


class CascadeViolation(RuntimeError):
    """A stage was run or aggregated out of contract order."""


def build_cascade_plan(
    *,
    candidate_class: str,
    stages: Sequence[Mapping[str, Any]],
    max_total_budget: float,
    early_stop_policy: str,
    cascade_plan_id: str | None = None,
) -> dict[str, Any]:
    """Build a cascade plan.

    Budget fractions are checked against the total: a plan whose stages claim
    more than the whole budget cannot be executed as written, and discovering
    that mid-run would mean abandoning a partially validated candidate.
    """
    if not stages:
        raise CascadeViolation("a cascade plan must define at least one stage")
    total_fraction = sum(float(stage.get("budget_fraction", 0.0)) for stage in stages)
    if total_fraction > 1.0 + 1e-9:
        raise CascadeViolation(
            f"stage budget fractions sum to {total_fraction:.4f}, which exceeds the plan budget"
        )
    seen: set[str] = set()
    for stage in stages:
        stage_id = str(stage.get("stage_id"))
        if stage_id in seen:
            raise CascadeViolation(f"duplicate stage_id {stage_id!r} in cascade plan")
        seen.add(stage_id)

    plan: dict[str, Any] = {
        "cascade_plan_id": cascade_plan_id or new_id("VCP"),
        "candidate_class": candidate_class,
        "stages": [dict(stage) for stage in stages],
        "max_total_budget": float(max_total_budget),
        "early_stop_policy": early_stop_policy,
    }
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    validate_artifact("validation-cascade-plan", plan)
    return plan


def build_stage_result(
    *,
    cascade_plan_id: str,
    candidate_id: str,
    stage_id: str,
    status: str,
    metric_values: Mapping[str, Any],
    uncertainty_summary: str,
    started_at: str,
    artifact_ids: Sequence[str] = (),
    effect_receipt_ids: Sequence[str] = (),
    completed_at: str | None = None,
    stage_result_id: str | None = None,
) -> dict[str, Any]:
    """Record one stage outcome."""
    result: dict[str, Any] = {
        "stage_result_id": stage_result_id or new_id("SER"),
        "cascade_plan_id": cascade_plan_id,
        "candidate_id": candidate_id,
        "stage_id": stage_id,
        "status": status,
        "metric_values": dict(metric_values),
        "uncertainty_summary": uncertainty_summary,
        "artifact_ids": list(artifact_ids),
        "effect_receipt_ids": list(effect_receipt_ids),
        "started_at": started_at,
        "completed_at": completed_at or utc_now_iso(),
    }
    result["result_hash"] = hash_excluding(result, "result_hash")
    validate_artifact("stage-evaluation-result", result)
    return result


def next_runnable_stage(
    plan: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> str | None:
    """Next stage id to execute, or None when the cascade must stop.

    Returns None once any stage has terminally failed: a later stage may not be
    used to overturn an earlier hard failure.
    """
    by_stage = {str(result["stage_id"]): result for result in results}
    for stage in plan["stages"]:
        stage_id = str(stage["stage_id"])
        recorded = by_stage.get(stage_id)
        if recorded is None:
            return stage_id
        status = str(recorded["status"])
        if status in TERMINAL_FAILURE_STATUSES:
            return None
        if status == "NOT_RUN":
            return stage_id
    return None


def assert_stage_order(plan: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
    """Raise when a stage ran after an earlier stage terminally failed."""
    order = [str(stage["stage_id"]) for stage in plan["stages"]]
    positions = {stage_id: index for index, stage_id in enumerate(order)}
    failed_at: int | None = None
    for result in sorted(results, key=lambda item: positions.get(str(item["stage_id"]), 10**6)):
        stage_id = str(result["stage_id"])
        index = positions.get(stage_id)
        if index is None:
            raise CascadeViolation(f"stage result {stage_id!r} is not part of plan {plan['cascade_plan_id']}")
        status = str(result["status"])
        if failed_at is not None and status != "NOT_RUN":
            raise CascadeViolation(
                f"stage {stage_id!r} ran after stage {order[failed_at]!r} terminally failed; "
                "a later stage cannot overturn an earlier hard failure"
            )
        if status in TERMINAL_FAILURE_STATUSES:
            failed_at = index


def aggregate_cascade_status(
    plan: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> str:
    """Reduce stage results to `PASS`, `FAIL`, or `PARTIAL`.

    Absent stages count as `NOT_RUN`, so an unfinished cascade can never report
    `PASS`.
    """
    assert_stage_order(plan, results)
    by_stage = {str(result["stage_id"]): str(result["status"]) for result in results}
    statuses = [by_stage.get(str(stage["stage_id"]), "NOT_RUN") for stage in plan["stages"]]

    if any(status in TERMINAL_FAILURE_STATUSES for status in statuses):
        return "FAIL"
    if any(status in INCOMPLETE_STATUSES for status in statuses):
        return "PARTIAL"
    return "PASS"
