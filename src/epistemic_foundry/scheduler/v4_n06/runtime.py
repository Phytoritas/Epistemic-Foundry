"""One-shot process-local composition of the N06 integration record path."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from ...domain.hashing import is_schema_digest, sha256_of_payload
from .integration import (
    FINDING_CODES,
    NO_REQUIREMENTS,
    NO_RESOURCES,
    IntegrationError,
    LaneEvent,
    LockEvent,
    WaitEdge,
    integration_hash_matches,
    require_integrated_run,
    seal_integration_record,
    verify_integration,
)


_Event = TypeVar("_Event", LaneEvent, LockEvent, WaitEdge)
_INTEGRITY_PREFIX = "integration record composition integrity failure"


def _input_error(message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise IntegrationError("INPUT_INVALID", message, context)


def _snapshot(value: object, *, label: str, active: set[int]) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _input_error(
                f"{label} contains a non-finite number",
                {"label": label},
            )
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            _input_error(f"{label} contains a cycle", {"label": label})
        active.add(identity)
        try:
            copied: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    _input_error(
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
            _input_error(f"{label} contains a cycle", {"label": label})
        active.add(identity)
        try:
            return [
                _snapshot(item, label=f"{label}[{position}]", active=active)
                for position, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    _input_error(
        f"{label} contains a non-JSON-compatible value",
        {"label": label, "value_type": type(value).__name__},
    )


def _capture_events(
    value: object,
    *,
    event_type: type[_Event],
    label: str,
) -> tuple[_Event, ...]:
    if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(
        value, Sequence
    ):
        _input_error(f"{label} must be a sequence", {"label": label})
    try:
        captured = tuple(value)
    except Exception as error:
        _input_error(
            f"{label} could not be materialized",
            {"error_type": type(error).__name__, "label": label},
        )
    for position, event in enumerate(captured):
        if not isinstance(event, event_type):
            _input_error(
                f"{label}[{position}] must be a {event_type.__name__}",
                {
                    "label": label,
                    "position": position,
                    "value_type": type(event).__name__,
                },
            )
    return captured  # type: ignore[return-value]


def _require_run_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        _input_error("run_id must be a non-empty string", {"label": "run_id"})
    return str(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _require_integrity(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: {message}")


def _snapshot_inputs(value: object) -> dict[str, Any]:
    try:
        snapshot = _snapshot(value, label="integration inputs", active=set())
    except IntegrationError:
        raise
    except Exception as error:
        _input_error(
            "integration inputs could not be snapshotted",
            {"error_type": type(error).__name__},
        )
    if not isinstance(snapshot, dict):  # pragma: no cover - root is constructed here
        _input_error("integration inputs must snapshot to a mapping")
    return snapshot


def _input_fingerprint(value: Mapping[str, Any]) -> str:
    try:
        return sha256_of_payload(value)
    except Exception as error:
        _input_error(
            "integration inputs could not be canonically hashed",
            {"error_type": type(error).__name__},
        )


def _owner_fingerprint(value: Mapping[str, Any], label: str) -> str:
    try:
        return sha256_of_payload(value)
    except Exception as error:
        raise RuntimeError(
            f"{_INTEGRITY_PREFIX}: malformed {label}"
        ) from error


def _detached_owner_output(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: malformed {label}")
    try:
        snapshot = _snapshot(value, label=label, active=set())
    except Exception as error:
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: malformed {label}") from error
    if not isinstance(snapshot, dict):  # pragma: no cover - mapping snapshots to dict
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: malformed {label}")
    return snapshot


def _verify_postconditions(
    *,
    report: Mapping[str, Any],
    record: Mapping[str, Any],
    run_id: str,
) -> None:
    try:
        expected_findings = {
            field: len(report.get(field) or ()) for field in sorted(FINDING_CODES)
        }
        _require_integrity(
            report["integrated"] is True and record["integrated"] is True,
            "the owner path did not produce an integrated result",
        )
        _require_integrity(
            record["run_id"] == run_id,
            "run identifier mismatch",
        )
        _require_integrity(
            record["findings"] == expected_findings,
            "finding projection mismatch",
        )
        _require_integrity(
            record["admission_policy"] == report["admission_policy"]
            and record["progress_horizon"] == report["progress_horizon"]
            and record["resource_capacities"] == report["resource_capacities"],
            "integration report projection mismatch",
        )
        _require_integrity(
            is_schema_digest(record["schedule_hash"]),
            "schedule hash is not a canonical digest",
        )
        _require_integrity(
            integration_hash_matches(record),
            "integration record hash mismatch",
        )
    except RuntimeError:
        raise
    except (IntegrationError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: malformed owner output") from error


def derive_integration_record(
    repository_root: str | Path,
    *,
    proposed: Sequence[str],
    events: Sequence[LaneEvent],
    lane_limits: Mapping[str, Mapping[str, Any]],
    admission_policy: str,
    progress_horizon: int,
    worker_assignments: Mapping[str, str],
    run_id: str,
    resource_capacities: Mapping[str, int] = NO_RESOURCES,
    lock_events: Sequence[LockEvent] = (),
    lock_requirements: Mapping[str, Sequence[str]] = NO_REQUIREMENTS,
    wait_edges: Sequence[WaitEdge] = (),
    refusal_ledger: Sequence[Mapping[str, Any]] = (),
    failure_ledger: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> MappingProxyType:
    """Verify, require and seal one declared N06 run without executing it."""
    identifier = _require_run_id(run_id)
    event_snapshot = _capture_events(
        events,
        event_type=LaneEvent,
        label="events",
    )
    lock_snapshot = _capture_events(
        lock_events,
        event_type=LockEvent,
        label="lock_events",
    )
    wait_snapshot = _capture_events(
        wait_edges,
        event_type=WaitEdge,
        label="wait_edges",
    )
    snapshot = _snapshot_inputs(
        {
            "admission_policy": admission_policy,
            "cancelled": cancelled,
            "effect_receipts": effect_receipts,
            "failure_ledger": failure_ledger,
            "lane_limits": lane_limits,
            "lock_requirements": lock_requirements,
            "mutation_receipts": mutation_receipts,
            "progress_horizon": progress_horizon,
            "proposed": proposed,
            "refusal_ledger": refusal_ledger,
            "resource_capacities": resource_capacities,
            "worker_assignments": worker_assignments,
        }
    )
    input_fingerprint = _input_fingerprint(snapshot)

    inputs = _thaw(snapshot)
    report = verify_integration(
        repository_root,
        proposed=inputs["proposed"],
        events=event_snapshot,
        lane_limits=inputs["lane_limits"],
        admission_policy=inputs["admission_policy"],
        progress_horizon=inputs["progress_horizon"],
        worker_assignments=inputs["worker_assignments"],
        resource_capacities=inputs["resource_capacities"],
        lock_events=lock_snapshot,
        lock_requirements=inputs["lock_requirements"],
        wait_edges=wait_snapshot,
        refusal_ledger=inputs["refusal_ledger"],
        failure_ledger=inputs["failure_ledger"],
        cancelled=inputs["cancelled"],
        effect_receipts=inputs["effect_receipts"],
        mutation_receipts=inputs["mutation_receipts"],
    )
    _require_integrity(
        _owner_fingerprint(snapshot, "integration input snapshot")
        == input_fingerprint,
        "verification mutated the detached input snapshot",
    )

    report_snapshot = _detached_owner_output(report, "integration report")
    report_fingerprint = _owner_fingerprint(report_snapshot, "integration report")
    require_integrated_run(_thaw(report_snapshot))
    _require_integrity(
        _owner_fingerprint(report_snapshot, "integration report")
        == report_fingerprint,
        "integration requirement mutated the report snapshot",
    )

    record = seal_integration_record(
        _thaw(report_snapshot),
        run_id=identifier,
    )
    _require_integrity(
        _owner_fingerprint(report_snapshot, "integration report")
        == report_fingerprint,
        "integration sealing mutated the report snapshot",
    )
    record_snapshot = _detached_owner_output(record, "integration record")
    _verify_postconditions(
        report=report_snapshot,
        record=record_snapshot,
        run_id=identifier,
    )

    return MappingProxyType(
        {
            "integration_report": _freeze(report_snapshot),
            "integration_record": _freeze(record_snapshot),
        }
    )
