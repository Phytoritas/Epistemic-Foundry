"""Non-destructive preflight for one L05 forget plan through the L06 hold gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..v4_l05 import LineageMemory, plan_forget, require_executable_forget
from .gate import (
    LegalHoldRegister,
    MemoryGateError,
    require_forget_permitted,
    verify_plan_hash,
)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryGateError(
            "INPUT_INVALID",
            f"{label} must be a non-empty string",
            {"label": label},
        )
    return value


def preflight_forget_plan(
    *,
    entries: Sequence[Mapping[str, Any]],
    lineage: LineageMemory,
    candidate_ids: Sequence[str],
    authority: Mapping[str, Any],
    requested_at: str,
    plan_id: str,
    register: LegalHoldRegister,
    candidate_classes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build and check a forget plan against the supplied hold snapshot.

    This is a synchronous, non-destructive preflight.  The returned plan is not
    an execution authorization: an effect owner must re-check current holds and
    reconcile the actual deletion through ``verify_deletion_execution``.
    """
    identifier = _require_text(plan_id, "plan_id")
    timestamp = _require_text(requested_at, "requested_at")
    if not isinstance(lineage, LineageMemory):
        raise MemoryGateError(
            "INPUT_INVALID",
            "lineage must be an L05 LineageMemory",
            {"value_type": type(lineage).__name__},
        )
    if not isinstance(register, LegalHoldRegister):
        raise MemoryGateError(
            "INPUT_INVALID",
            "register must be an L06 LegalHoldRegister",
            {"value_type": type(register).__name__},
        )

    plan = plan_forget(
        entries=entries,
        lineage=lineage,
        candidate_ids=candidate_ids,
        authority=authority,
        requested_at=timestamp,
        plan_id=identifier,
    )
    verified_hash = verify_plan_hash(plan)
    require_executable_forget(plan)
    require_forget_permitted(
        plan=plan,
        register=register,
        candidate_classes=candidate_classes,
    )

    if (
        plan.get("plan_id") != identifier
        or plan.get("requested_at") != timestamp
        or plan.get("plan_hash") != verified_hash
    ):
        raise RuntimeError("forget preflight composition integrity failure")
    return plan
