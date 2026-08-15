"""In-process composition of the sealed Q05, V05, P05 and V06 path."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from ...domain.hashing import hash_excluding, sha256_of_payload
from ...domain.vocabularies import promotion_rank
from ...evaluation.v4_q05 import ADMIT as Q05_ADMIT
from ...parliament.v4_p05 import CONVENE as P05_CONVENE
from ...parliament.v4_p05 import derive_promotion_parliament
from ..v4_v05 import ADVANCE as V05_ADVANCE
from ..v4_v05 import derive_validation_advancement
from .gate import (
    ExperimentReplicationRefused,
    derive_experiment_replication_integration,
    integration_hash_matches,
)


def _snapshot(value: object, *, label: str, active: set[int]) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ExperimentReplicationRefused(
                "INPUT_INVALID",
                f"{label} contains a non-finite number",
                {"label": label},
            )
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise ExperimentReplicationRefused(
                "INPUT_INVALID", f"{label} contains a cycle", {"label": label}
            )
        active.add(identity)
        try:
            materialized: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ExperimentReplicationRefused(
                        "INPUT_INVALID",
                        f"{label} contains a non-string mapping key",
                        {"key_type": type(key).__name__, "label": label},
                    )
                materialized[key] = _snapshot(
                    item, label=f"{label}.{key}", active=active
                )
            return materialized
        finally:
            active.remove(identity)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in active:
            raise ExperimentReplicationRefused(
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
    raise ExperimentReplicationRefused(
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
        raise RuntimeError(
            f"experiment/replication path composition integrity failure: {message}"
        )


def _receipt_hash_matches(receipt: Mapping[str, Any]) -> bool:
    return receipt.get("receipt_hash") == hash_excluding(
        dict(receipt), "receipt_hash"
    )


def _verify_postconditions(
    *,
    q05: Mapping[str, Any],
    validation: Mapping[str, Any],
    parliament: Mapping[str, Any],
    integration: Mapping[str, Any],
    candidate_id: str,
    promotion_level: str,
    requesting_role: str,
    adaptive_search_used: bool,
    replication_plan: Mapping[str, Any] | None,
    validation_created_at: str,
    parliament_created_at: str,
    integration_created_at: str,
) -> None:
    try:
        _require_composition(_receipt_hash_matches(q05), "Q05 receipt hash mismatch")
        _require_composition(
            _receipt_hash_matches(validation), "V05 receipt hash mismatch"
        )
        _require_composition(
            _receipt_hash_matches(parliament), "P05 receipt hash mismatch"
        )
        _require_composition(
            _receipt_hash_matches(integration)
            and integration_hash_matches(integration),
            "V06 receipt hash mismatch",
        )

        _require_composition(
            q05["candidate_id"]
            == validation["candidate_id"]
            == parliament["candidate_id"]
            == integration["candidate_id"]
            == candidate_id,
            "candidate mismatch",
        )
        q05_hash = q05["receipt_hash"]
        _require_composition(
            validation["statistical_admissibility_receipt_hash"] == q05_hash
            and parliament["statistical_receipt_hash"] == q05_hash
            and integration["statistical_admissibility_receipt_hash"] == q05_hash,
            "statistical clearance mismatch",
        )
        _require_composition(
            integration["validation_advancement_gate_id"] == validation["gate_id"]
            and integration["validation_advancement_receipt_hash"]
            == validation["receipt_hash"]
            and integration["promotion_parliament_gate_id"] == parliament["gate_id"]
            and integration["promotion_parliament_receipt_hash"]
            == parliament["receipt_hash"],
            "downstream receipt binding mismatch",
        )
        _require_composition(
            validation["requesting_role"]
            == parliament["requesting_role"]
            == integration["requesting_role"]
            == requesting_role,
            "requesting role mismatch",
        )
        _require_composition(
            validation["required_promotion_level"] == promotion_level
            and parliament["requested_level"] == promotion_level,
            "promotion level mismatch",
        )
        _require_composition(
            validation["adaptive_search_used"] is adaptive_search_used,
            "adaptive-search mismatch",
        )
        validation_ceiling = validation["replication_ceiling"]
        expected_parliament_ceiling = (
            validation_ceiling
            if promotion_rank(validation_ceiling) < promotion_rank(promotion_level)
            else promotion_level
        )
        _require_composition(
            parliament["promotion_ceiling"] == expected_parliament_ceiling,
            "replication ceiling mismatch",
        )
        expected_plan_id = (
            None
            if replication_plan is None
            else replication_plan["replication_plan_id"]
        )
        _require_composition(
            validation["replication_plan_id"] == expected_plan_id,
            "replication plan mismatch",
        )
        _require_composition(
            validation["created_at"] == validation_created_at
            and parliament["created_at"] == parliament_created_at
            and integration["created_at"] == integration_created_at,
            "timestamp mismatch",
        )
        _require_composition(
            integration["statistical_admitted"]
            == (
                q05["decision"] == Q05_ADMIT
                and q05["admissible_for_promotion_review"] is True
            ),
            "Q05 decision projection mismatch",
        )
        _require_composition(
            integration["validation_advanced"]
            == (
                validation["decision"] == V05_ADVANCE
                and validation["advanced"] is True
            ),
            "V05 decision projection mismatch",
        )
        _require_composition(
            integration["promotion_convened"]
            == (
                parliament["decision"] == P05_CONVENE
                and parliament["convened_for_promotion_authority"] is True
            ),
            "P05 decision projection mismatch",
        )
        _require_composition(
            parliament["grants_promotion"] is False
            and integration["grants_promotion"] is False
            and integration["parliament_grants_promotion"] is False,
            "promotion authority boundary mismatch",
        )
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "experiment/replication path composition integrity failure: "
            "malformed composed output"
        ) from error


def derive_experiment_replication_path(
    *,
    candidate_id: str,
    statistical_admissibility_receipt: Mapping[str, Any],
    promotion_level: str,
    requesting_role: str,
    adaptive_search_used: bool,
    replication_plan: Mapping[str, Any] | None,
    cascade_plan: Mapping[str, Any],
    stage_results: Sequence[Mapping[str, Any]],
    challenge_genomes: Sequence[Mapping[str, Any]],
    challenge_results: Sequence[Mapping[str, Any]],
    candidate_revision: int,
    lineage: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    red_queen_results: Sequence[Mapping[str, Any]],
    searched_adversarial_lanes: Sequence[str],
    requesting_principal_id: str,
    validation_created_at: str,
    parliament_created_at: str,
    integration_created_at: str,
    minority_reports: Sequence[Mapping[str, Any]] = (),
    replication_results: Sequence[Mapping[str, Any]] = (),
) -> MappingProxyType:
    """Derive the complete four-receipt path without executing any experiment."""
    if type(adaptive_search_used) is not bool:
        raise ExperimentReplicationRefused(
            "INPUT_INVALID",
            "adaptive_search_used must be a boolean",
            {"value_type": type(adaptive_search_used).__name__},
        )
    if replication_plan is not None and not isinstance(replication_plan, Mapping):
        raise ExperimentReplicationRefused(
            "INPUT_INVALID",
            "replication_plan must be a mapping or None",
            {"value_type": type(replication_plan).__name__},
        )

    try:
        snapshot = _snapshot(
            {
                "statistical_admissibility_receipt": statistical_admissibility_receipt,
                "replication_plan": replication_plan,
                "cascade_plan": cascade_plan,
                "stage_results": stage_results,
                "challenge_genomes": challenge_genomes,
                "challenge_results": challenge_results,
                "lineage": lineage,
                "adjudication": adjudication,
                "red_queen_results": red_queen_results,
                "searched_adversarial_lanes": searched_adversarial_lanes,
                "minority_reports": minority_reports,
                "replication_results": replication_results,
            },
            label="experiment/replication path inputs",
            active=set(),
        )
        fingerprint = sha256_of_payload(snapshot)
    except ExperimentReplicationRefused:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, IndexError) as error:
        raise ExperimentReplicationRefused(
            "INPUT_INVALID",
            "experiment/replication path inputs could not be snapshotted",
            {"error_type": type(error).__name__},
        ) from error

    v05_inputs = _thaw(snapshot)
    validation_receipt = derive_validation_advancement(
        candidate_id=candidate_id,
        cascade_plan=v05_inputs["cascade_plan"],
        stage_results=v05_inputs["stage_results"],
        challenge_genomes=v05_inputs["challenge_genomes"],
        challenge_results=v05_inputs["challenge_results"],
        admissibility_receipt=v05_inputs["statistical_admissibility_receipt"],
        adaptive_search_used=adaptive_search_used,
        required_promotion_level=promotion_level,
        requesting_role=requesting_role,
        replication_plan=v05_inputs["replication_plan"],
        created_at=validation_created_at,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "V05 mutated the input snapshot",
    )

    p05_inputs = _thaw(snapshot)
    parliament_receipt = derive_promotion_parliament(
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        requested_level=promotion_level,
        lineage=p05_inputs["lineage"],
        adjudication=p05_inputs["adjudication"],
        selective_admissibility=p05_inputs["statistical_admissibility_receipt"],
        red_queen_results=p05_inputs["red_queen_results"],
        searched_adversarial_lanes=p05_inputs["searched_adversarial_lanes"],
        requesting_principal_id=requesting_principal_id,
        requesting_role=requesting_role,
        adaptive_search_used=adaptive_search_used,
        minority_reports=p05_inputs["minority_reports"],
        replication_plan=p05_inputs["replication_plan"],
        replication_results=p05_inputs["replication_results"],
        created_at=parliament_created_at,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "P05 mutated the input snapshot",
    )

    v06_inputs = _thaw(snapshot)
    integration_receipt = derive_experiment_replication_integration(
        candidate_id=candidate_id,
        statistical_admissibility_receipt=v06_inputs[
            "statistical_admissibility_receipt"
        ],
        validation_advancement_receipt=validation_receipt,
        promotion_parliament_receipt=parliament_receipt,
        requesting_role=requesting_role,
        created_at=integration_created_at,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "V06 mutated the input snapshot",
    )
    _verify_postconditions(
        q05=snapshot["statistical_admissibility_receipt"],
        validation=validation_receipt,
        parliament=parliament_receipt,
        integration=integration_receipt,
        candidate_id=candidate_id,
        promotion_level=promotion_level,
        requesting_role=requesting_role,
        adaptive_search_used=adaptive_search_used,
        replication_plan=snapshot["replication_plan"],
        validation_created_at=validation_created_at,
        parliament_created_at=parliament_created_at,
        integration_created_at=integration_created_at,
    )
    return MappingProxyType(
        {
            "statistical_admissibility_receipt": _freeze(
                snapshot["statistical_admissibility_receipt"]
            ),
            "validation_advancement_receipt": _freeze(validation_receipt),
            "promotion_parliament_receipt": _freeze(parliament_receipt),
            "integration_receipt": _freeze(integration_receipt),
        }
    )
