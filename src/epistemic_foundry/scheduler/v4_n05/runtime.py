"""One-shot process-local composition of the N05 schedule verdict path."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .lanes import (
    FINDING_CODES,
    LaneEvent,
    ScheduleError,
    require_valid_schedule,
    seal_schedule_verdict,
    verdict_hash_matches,
    verify_schedule,
)


def _snapshot(value: object, *, label: str, active: set[int]) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ScheduleError(
                "INPUT_INVALID",
                f"{label} contains a non-finite number",
                {"label": label},
            )
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise ScheduleError(
                "INPUT_INVALID", f"{label} contains a cycle", {"label": label}
            )
        active.add(identity)
        try:
            copied: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ScheduleError(
                        "INPUT_INVALID",
                        f"{label} contains a non-string mapping key",
                        {"key_type": type(key).__name__, "label": label},
                    )
                copied[key] = _snapshot(
                    item,
                    label=f"{label}.{key}",
                    active=active,
                )
            return copied
        finally:
            active.remove(identity)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in active:
            raise ScheduleError(
                "INPUT_INVALID", f"{label} contains a cycle", {"label": label}
            )
        active.add(identity)
        try:
            return [
                _snapshot(item, label=f"{label}[{position}]", active=active)
                for position, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    raise ScheduleError(
        "INPUT_INVALID",
        f"{label} contains a non-JSON-compatible value",
        {"label": label, "value_type": type(value).__name__},
    )


def _require_events(events: object) -> tuple[LaneEvent, ...]:
    if isinstance(events, (str, bytes, bytearray)) or not isinstance(events, Sequence):
        raise ScheduleError("INPUT_INVALID", "events must be a sequence")
    return tuple(events)  # type: ignore[arg-type,return-value]


def _require_schedule_id(schedule_id: object) -> str:
    if not isinstance(schedule_id, str) or not schedule_id.strip():
        raise ScheduleError("INPUT_INVALID", "schedule_id must be a non-empty string")
    return schedule_id


def _verify_postconditions(
    *, report: Mapping[str, Any], verdict: Mapping[str, Any], schedule_id: str
) -> None:
    try:
        expected_findings = {
            field: len(report.get(field) or ()) for field in sorted(FINDING_CODES)
        }
        reconciliation = report["reconciliation"]
        if not (
            verdict_hash_matches(verdict)
            and verdict["schedule_id"] == schedule_id
            and verdict["valid"] is True
            and verdict["valid"] is bool(report["valid"])
            and verdict["reconciled"] is bool(reconciliation["reconciled"])
            and verdict["reconciliation_scope"] == report["reconciliation_scope"]
            and verdict["bounds"] == report["bounds"]
            and verdict["phase_binding"] == report["phase_binding"]
            and verdict["lane_ledgers"] == report["lane_ledgers"]
            and verdict["findings"] == expected_findings
        ):
            raise RuntimeError("schedule verdict composition integrity failure")
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "schedule verdict composition integrity failure: malformed owner output"
        ) from error


def derive_schedule_verdict(
    repository_root: str | Path,
    *,
    proposed: Sequence[str],
    events: Sequence[LaneEvent],
    lane_limits: Mapping[str, Mapping[str, Any]],
    schedule_id: str,
    failure_ledger: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Verify and seal a supplied schedule without executing or persisting it."""
    identifier = _require_schedule_id(schedule_id)
    event_snapshot = _require_events(events)
    snapshot = _snapshot(
        {
            "proposed": proposed,
            "lane_limits": lane_limits,
            "failure_ledger": failure_ledger,
            "cancelled": cancelled,
            "effect_receipts": effect_receipts,
            "mutation_receipts": mutation_receipts,
        },
        label="schedule inputs",
        active=set(),
    )

    report = verify_schedule(
        repository_root,
        proposed=snapshot["proposed"],
        events=event_snapshot,
        lane_limits=snapshot["lane_limits"],
        failure_ledger=snapshot["failure_ledger"],
        cancelled=snapshot["cancelled"],
        effect_receipts=snapshot["effect_receipts"],
        mutation_receipts=snapshot["mutation_receipts"],
    )
    require_valid_schedule(report)
    verdict = seal_schedule_verdict(report, schedule_id=identifier)
    _verify_postconditions(report=report, verdict=verdict, schedule_id=identifier)
    return verdict
