"""Role dispatch plans and candidate reconciliation (EF4-I25).

Contract source: `schemas/role-dispatch-plan.schema.json`.

Every dispatch resolves a RoleSpec carrying a tool ACL, an evidence ACL, a write
scope, a budget, and an expected count. The expected count is what makes
reconciliation possible: without it a silently dropped worker is
indistinguishable from a worker that had nothing to report, so a partial fan-in
would read as complete.

`reconcile_dispatch` therefore accounts for every expected identity across
completed, failed, cancelled, and missing, and refuses to report success while
any identity is unaccounted for.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Fields a RoleSpec must carry before a dispatch is legal, per
#: `role-dispatch-plan.schema.json`. `independence_group` is the one worth
#: naming: two roles in the same group are not independent evidence, so an
#: unlabeled role could be counted as corroboration of itself.
REQUIRED_ROLE_FIELDS: tuple[str, ...] = (
    "role_id",
    "host_agent_type",
    "model_tier",
    "tool_acl",
    "evidence_acl",
    "read_scope",
    "write_scope",
    "depends_on",
    "budget_tokens",
    "timeout_seconds",
    "independence_group",
)


class DispatchRefused(ValueError):
    """A dispatch plan or reconciliation violates the role contract."""


def role_blockers(role: Mapping[str, Any]) -> list[str]:
    """Missing RoleSpec fields, named individually."""
    missing = [field for field in REQUIRED_ROLE_FIELDS if field not in role or role[field] is None]
    return [f"role {role.get('role_id', '<unnamed>')} is missing {field}" for field in missing]


def build_role_dispatch_plan(
    *,
    session_id: str,
    roles: Sequence[Mapping[str, Any]],
    budget_envelope_id: str,
    fan_in_policy: str = "all_required",
    missing_result_policy: str = "fail_gate",
    max_concurrency: int = 4,
    expected_count: int | None = None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Build a dispatch plan with a resolved RoleSpec per role.

    `expected_count` defaults to the number of roles rather than being optional:
    an unstated expectation cannot be reconciled.
    """
    if not roles:
        raise DispatchRefused("a dispatch plan must define at least one role")
    problems: list[str] = []
    for role in roles:
        problems.extend(role_blockers(role))
    if problems:
        raise DispatchRefused(
            "refusing dispatch with incomplete RoleSpec(s): " + "; ".join(problems)
        )
    if max_concurrency < 1:
        raise DispatchRefused("max_concurrency must be at least 1")

    resolved_count = len(roles) if expected_count is None else int(expected_count)
    if resolved_count < 1:
        raise DispatchRefused(
            "expected_count must be at least 1; an unstated expectation cannot be reconciled"
        )

    plan: dict[str, Any] = {
        "plan_id": plan_id or new_id("RDP"),
        "session_id": session_id,
        "roles": [dict(role) for role in roles],
        "expected_count": resolved_count,
        "fan_in_policy": fan_in_policy,
        "missing_result_policy": missing_result_policy,
        "max_concurrency": int(max_concurrency),
        "budget_envelope_id": budget_envelope_id,
    }
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    validate_artifact("role-dispatch-plan", plan)
    return plan


def reconcile_dispatch(
    plan: Mapping[str, Any],
    *,
    completed_ids: Sequence[str],
    failed_ids: Sequence[str] = (),
    cancelled_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Account for every expected identity; report the unreconciled set.

    Returns a reconciliation summary rather than a bare bool so a caller must
    look at `missing` instead of a single truthy value.
    """
    expected = int(plan["expected_count"])
    accounted = list(completed_ids) + list(failed_ids) + list(cancelled_ids)
    duplicates = sorted({item for item in accounted if accounted.count(item) > 1})
    if duplicates:
        raise DispatchRefused(
            f"identity {duplicates} appears in more than one outcome bucket; a worker cannot "
            "have both completed and failed"
        )
    missing_count = expected - len(accounted)
    reconciled = missing_count == 0
    return {
        "plan_id": plan["plan_id"],
        "expected": expected,
        "completed": len(completed_ids),
        "failed": len(failed_ids),
        "cancelled": len(cancelled_ids),
        "missing": max(missing_count, 0),
        "over_reported": max(-missing_count, 0),
        "reconciled": reconciled,
    }


def dispatch_succeeded(plan: Mapping[str, Any], reconciliation: Mapping[str, Any]) -> bool:
    """True only for a fully reconciled, fully completed `all_required` fan-in.

    Under `all_required`, a failed or cancelled worker is not success. Under a
    quorum policy the caller must label the result partial, which is why this
    function refuses to answer True for anything but complete accounting.
    """
    if not reconciliation.get("reconciled"):
        return False
    if reconciliation.get("over_reported"):
        return False
    if str(plan["fan_in_policy"]) == "all_required":
        return int(reconciliation["completed"]) == int(reconciliation["expected"])
    return int(reconciliation["completed"]) > 0
