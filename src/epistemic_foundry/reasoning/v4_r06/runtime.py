"""Gate-first in-process runtime for one typed scientific crossover."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from ...domain.hashing import hash_excluding, sha256_of_payload
from ..v4_r05 import apply_typed_crossover
from .gate import CrossoverSafetyRefused, evaluate_crossover_safety


def _snapshot(value: object, *, label: str, active: set[int]) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise CrossoverSafetyRefused(
                "INPUT_INVALID",
                f"{label} contains a non-finite number",
                {"label": label},
            )
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise CrossoverSafetyRefused(
                "INPUT_INVALID",
                f"{label} contains a cycle",
                {"label": label},
            )
        active.add(identity)
        try:
            result: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise CrossoverSafetyRefused(
                        "INPUT_INVALID",
                        f"{label} contains a non-string mapping key",
                        {"key_type": type(key).__name__, "label": label},
                    )
                result[key] = _snapshot(
                    item,
                    label=f"{label}.{key}",
                    active=active,
                )
            return result
        finally:
            active.remove(identity)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in active:
            raise CrossoverSafetyRefused(
                "INPUT_INVALID",
                f"{label} contains a cycle",
                {"label": label},
            )
        active.add(identity)
        try:
            return [
                _snapshot(item, label=f"{label}[{position}]", active=active)
                for position, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    raise CrossoverSafetyRefused(
        "INPUT_INVALID",
        f"{label} contains a non-JSON-compatible value",
        {"label": label, "value_type": type(value).__name__},
    )


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


def _require_composition(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"safe crossover composition integrity failure: {message}")


def _verify_postconditions(
    *,
    safety_receipt: Mapping[str, Any],
    application_record: Mapping[str, Any],
    crossover_report: Mapping[str, Any],
    created_at: str,
) -> None:
    try:
        _require_composition(
            safety_receipt["receipt_hash"]
            == hash_excluding(dict(safety_receipt), "receipt_hash"),
            "safety receipt hash mismatch",
        )
        _require_composition(
            application_record["record_hash"]
            == hash_excluding(dict(application_record), "record_hash"),
            "application record hash mismatch",
        )
        _require_composition(
            application_record["child_hash"]
            == sha256_of_payload(application_record["child"]),
            "child hash mismatch",
        )
        _require_composition(
            safety_receipt["created_at"] == created_at
            and application_record["created_at"] == created_at,
            "timestamp mismatch",
        )
        safety_parents = dict(
            zip(
                safety_receipt["candidate_ids"],
                safety_receipt["parent_genome_hashes"],
                strict=True,
            )
        )
        application_parents = dict(
            zip(
                application_record["parent_genome_ids"],
                application_record["parent_genome_hashes"],
                strict=True,
            )
        )
        _require_composition(
            len(safety_parents) == 2
            and len(application_parents) == 2
            and safety_parents == application_parents,
            "parent identity or content mismatch",
        )
        _require_composition(
            safety_receipt["crossover_report_id"]
            == application_record["crossover_report_id"]
            == crossover_report["report_id"],
            "crossover report identity mismatch",
        )
        _require_composition(
            safety_receipt["crossover_report_hash"]
            == crossover_report["report_hash"],
            "crossover report hash mismatch",
        )
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "safe crossover composition integrity failure: malformed composed output"
        ) from error


def apply_safe_typed_crossover(
    *,
    operator_id: str,
    parents: Sequence[Mapping[str, Any]],
    parent_lineages: Sequence[Mapping[str, Any]],
    inherited_fields: Sequence[str],
    mechanism_graphs: Sequence[Mapping[str, Any]],
    scope_vectors: Mapping[str, Mapping[str, Any]],
    measurement_report: Mapping[str, Any],
    crossover_report: Mapping[str, Any],
    created_at: str,
    child_genome_id: str | None = None,
) -> MappingProxyType:
    """Evaluate R06 once, then apply the same snapshotted crossover once."""
    snapshot = _snapshot(
        {
            "parents": parents,
            "parent_lineages": parent_lineages,
            "inherited_fields": inherited_fields,
            "mechanism_graphs": mechanism_graphs,
            "scope_vectors": scope_vectors,
            "measurement_report": measurement_report,
            "crossover_report": crossover_report,
        },
        label="crossover inputs",
        active=set(),
    )
    fingerprint = sha256_of_payload(snapshot)

    safety_inputs = _thaw(snapshot)
    safety_receipt = evaluate_crossover_safety(
        parents=safety_inputs["parents"],
        mechanism_graphs=safety_inputs["mechanism_graphs"],
        scope_vectors=safety_inputs["scope_vectors"],
        measurement_report=safety_inputs["measurement_report"],
        crossover_report=safety_inputs["crossover_report"],
        created_at=created_at,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "the safety gate mutated its input snapshot",
    )

    application_inputs = _thaw(snapshot)
    application_record = apply_typed_crossover(
        operator_id=operator_id,
        parents=application_inputs["parents"],
        parent_lineages=application_inputs["parent_lineages"],
        inherited_fields=application_inputs["inherited_fields"],
        compatibility_report=application_inputs["crossover_report"],
        created_at=created_at,
        child_genome_id=child_genome_id,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "the crossover operator mutated its input snapshot",
    )
    _verify_postconditions(
        safety_receipt=safety_receipt,
        application_record=application_record,
        crossover_report=snapshot["crossover_report"],
        created_at=created_at,
    )
    return MappingProxyType(
        {
            "safety_receipt": _freeze(safety_receipt),
            "application_record": _freeze(application_record),
        }
    )
