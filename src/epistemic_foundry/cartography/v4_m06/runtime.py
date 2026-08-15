"""In-process composition of one current M05 coverage path through M06."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from ...contracts import ContractViolation
from ...domain.hashing import hash_excluding, sha256_of_payload
from ..v4_m05 import CartographyError, NicheMap, build_coverage_map
from .gate import (
    bind_derived_record,
    build_map_agreement_record,
    build_map_revision,
    require_current_revision,
)


def _require_composition(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"current coverage composition integrity failure: {message}")


def _snapshot(value: object, *, label: str, active: set[int]) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise RuntimeError(f"{label} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise RuntimeError(f"{label} contains a cycle")
        active.add(identity)
        try:
            copied: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise RuntimeError(f"{label} contains a non-string mapping key")
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
            raise RuntimeError(f"{label} contains a cycle")
        active.add(identity)
        try:
            return [
                _snapshot(item, label=f"{label}[{position}]", active=active)
                for position, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    raise RuntimeError(
        f"{label} contains a non-JSON-compatible value of type "
        f"{type(value).__name__}"
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


def _hash_matches(record: Mapping[str, Any], field: str) -> bool:
    return record.get(field) == hash_excluding(dict(record), field)


def _capture_niche_map(niche_map: NicheMap) -> dict[str, Any]:
    if not isinstance(niche_map, NicheMap):
        raise RuntimeError("niche_map must be an M05 NicheMap")
    niche_ids_before = tuple(niche_map.niche_ids())
    niches: list[dict[str, Any]] = []
    for niche_id in niche_ids_before:
        captured = _snapshot(
            niche_map.niche(niche_id),
            label=f"niche_map.{niche_id}",
            active=set(),
        )
        _require_composition(isinstance(captured, dict), "captured niche is malformed")
        _require_composition(
            captured.get("niche_id") == niche_id,
            "captured niche identity changed",
        )
        _require_composition(
            _hash_matches(captured, "niche_hash"),
            "captured niche hash mismatch",
        )
        niches.append(captured)
    occupancy = _snapshot(
        niche_map.occupants(),
        label="niche_map.occupancy",
        active=set(),
    )
    niche_ids_after = tuple(niche_map.niche_ids())
    _require_composition(
        niche_ids_before == niche_ids_after,
        "niche identities changed during capture",
    )
    reconstructed = NicheMap(_thaw(niches))
    _require_composition(
        reconstructed.niche_ids() == niche_ids_before
        and reconstructed.occupants() == occupancy,
        "captured niche map does not reconstruct exactly",
    )
    return {
        "niches": niches,
        "niche_ids": list(niche_ids_before),
        "occupancy": occupancy,
    }


def _captured_map(snapshot: Mapping[str, Any]) -> NicheMap:
    return NicheMap(_thaw(snapshot["niche_map"]["niches"]))


def _verify_postconditions(
    *,
    snapshot: Mapping[str, Any],
    agreement: Mapping[str, Any],
    coverage: Mapping[str, Any],
    revision: Mapping[str, Any],
    binding: Mapping[str, Any],
    cascade: Mapping[str, Any],
    evolution_run_id: str,
    generation: int,
    serving_generation: int,
    map_id: str,
    agreement_record_id: str,
    revision_id: str,
    cascade_id: str,
) -> None:
    try:
        _require_composition(
            _hash_matches(agreement, "record_hash"), "agreement hash mismatch"
        )
        _require_composition(
            _hash_matches(coverage, "map_hash"), "coverage hash mismatch"
        )
        _require_composition(
            _hash_matches(revision, "revision_hash"), "revision hash mismatch"
        )
        _require_composition(
            _hash_matches(cascade, "cascade_hash"), "cascade hash mismatch"
        )
        _require_composition(
            agreement["record_id"] == agreement_record_id
            and coverage["map_id"] == map_id
            and revision["revision_id"] == revision_id
            and cascade["cascade_id"] == cascade_id,
            "record identity mismatch",
        )

        expected_niche_ids = snapshot["niche_map"]["niche_ids"]
        expected_occupancy = snapshot["niche_map"]["occupancy"]
        expected_niche_hashes = {
            niche["niche_id"]: niche["niche_hash"]
            for niche in snapshot["niche_map"]["niches"]
        }
        _require_composition(
            agreement["niche_ids"]
            == coverage["niche_ids"]
            == sorted(revision["niche_hashes"])
            == expected_niche_ids,
            "niche identity mismatch",
        )
        _require_composition(
            revision["niche_hashes"] == expected_niche_hashes,
            "niche content mismatch",
        )
        _require_composition(
            agreement["occupancy"] == revision["occupancy"] == expected_occupancy,
            "map occupancy mismatch",
        )
        _require_composition(
            agreement["counts"]["niches"] == len(expected_niche_hashes)
            and agreement["counts"]["occupants"] == len(expected_occupancy)
            and coverage["occupied_niches"]
            == len(set(expected_occupancy.values())),
            "map population count mismatch",
        )
        _require_composition(
            coverage["evolution_run_id"]
            == revision["evolution_run_id"]
            == cascade["evolution_run_id"]
            == evolution_run_id,
            "evolution run mismatch",
        )
        _require_composition(
            coverage["generation"]
            == revision["generation"]
            == binding["source_generation"]
            == cascade["revision_generation"]
            == generation,
            "generation mismatch",
        )
        _require_composition(
            binding
            == {
                "record_hash": coverage["map_hash"],
                "record_id": coverage["map_id"],
                "record_kind": "coverage_map",
                "source_generation": revision["generation"],
                "source_revision_hash": revision["revision_hash"],
            },
            "coverage binding mismatch",
        )
        _require_composition(
            cascade["is_current"] is True
            and cascade["revision_id"] == revision["revision_id"]
            and cascade["revision_hash"] == revision["revision_hash"]
            and cascade["serving_generation"] == serving_generation == generation,
            "current revision mismatch",
        )
        _require_composition(
            cascade["bound_records"] == [binding]
            and cascade["unbound_records"] == []
            and cascade["rebuild_required"] == []
            and cascade["counts"]
            == {
                "bound_records": 1,
                "rebuild_required": 0,
                "unbound_records": 0,
            },
            "staleness cascade binding mismatch",
        )
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise RuntimeError(
            "current coverage composition integrity failure: malformed owner output"
        ) from error


def derive_current_coverage_path(
    *,
    niche_map: NicheMap,
    archive_entries: Sequence[Mapping[str, Any]],
    evolution_run_id: str,
    generation: int,
    lineage_entropy: float,
    stagnant_niche_ids: Sequence[str],
    map_id: str,
    agreement_record_id: str,
    revision_id: str,
    cascade_id: str,
    serving_generation: int,
) -> MappingProxyType:
    """Derive and bind one current coverage path without serving or rebuilding it."""
    for label, identifier in (
        ("map_id", map_id),
        ("agreement_record_id", agreement_record_id),
        ("revision_id", revision_id),
        ("cascade_id", cascade_id),
    ):
        if not isinstance(identifier, str) or not identifier.strip():
            raise RuntimeError(f"{label} must be a non-empty string")

    try:
        map_snapshot = _capture_niche_map(niche_map)
        mutable_snapshot = _snapshot(
            {
                "archive_entries": archive_entries,
                "stagnant_niche_ids": stagnant_niche_ids,
            },
            label="current coverage inputs",
            active=set(),
        )
        snapshot = {
            "niche_map": map_snapshot,
            **mutable_snapshot,
        }
        fingerprint = sha256_of_payload(snapshot)
    except (CartographyError, ContractViolation):
        raise
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError) as error:
        raise RuntimeError("current coverage inputs could not be snapshotted") from error

    agreement_inputs = _thaw(snapshot)
    map_agreement_record = build_map_agreement_record(
        niche_map=_captured_map(snapshot),
        archive_entries=agreement_inputs["archive_entries"],
        record_id=agreement_record_id,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "agreement call mutated the input snapshot",
    )

    coverage_inputs = _thaw(snapshot)
    coverage_map = build_coverage_map(
        niche_map=_captured_map(snapshot),
        evolution_run_id=evolution_run_id,
        generation=generation,
        lineage_entropy=lineage_entropy,
        stagnant_niche_ids=coverage_inputs["stagnant_niche_ids"],
        map_id=map_id,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "coverage call mutated the input snapshot",
    )

    map_revision = build_map_revision(
        niche_map=_captured_map(snapshot),
        evolution_run_id=evolution_run_id,
        generation=generation,
        revision_id=revision_id,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "revision call mutated the input snapshot",
    )

    coverage_binding = bind_derived_record(
        record=_thaw(coverage_map),
        record_kind="coverage_map",
        revision=_thaw(map_revision),
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "binding call mutated the input snapshot",
    )
    staleness_cascade = require_current_revision(
        revision=_thaw(map_revision),
        serving_generation=serving_generation,
        derived_records=[_thaw(coverage_binding)],
        cascade_id=cascade_id,
    )
    _require_composition(
        sha256_of_payload(snapshot) == fingerprint,
        "current-revision call mutated the input snapshot",
    )
    _verify_postconditions(
        snapshot=snapshot,
        agreement=map_agreement_record,
        coverage=coverage_map,
        revision=map_revision,
        binding=coverage_binding,
        cascade=staleness_cascade,
        evolution_run_id=evolution_run_id,
        generation=generation,
        serving_generation=serving_generation,
        map_id=map_id,
        agreement_record_id=agreement_record_id,
        revision_id=revision_id,
        cascade_id=cascade_id,
    )
    return MappingProxyType(
        {
            "map_agreement_record": _freeze(map_agreement_record),
            "coverage_map": _freeze(coverage_map),
            "map_revision": _freeze(map_revision),
            "coverage_binding": _freeze(coverage_binding),
            "staleness_cascade": _freeze(staleness_cascade),
        }
    )
