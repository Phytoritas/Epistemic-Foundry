"""Fixtures for the V01 ValidationTarget suites.

Every manifest here is built through ``build_target_manifest`` rather than
written out by hand, so each fixture is a document this component actually
accepts and the canonical schema actually validates — a fixture the schema
would refuse tests nothing but the fixture.  The one hand-written document is
``raw_manifest``, which exists so the negative suite can bypass the builder and
hand the screen something the schema refuses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import build_target_manifest, empty_scope_vector

ROOT = Path(__file__).resolve().parents[4]
REPORT_ID = "VTER-V01-1"
SCREENED_AT = "2026-08-01T00:00:00Z"
ENTRYPOINT = "targets/reservoir/run.py"
ARTIFACT_HASH = "sha256:" + "a" * 64
LIBRARY_HASH = "sha256:" + "b" * 64


def port(identifier: str, data_type: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": identifier,
        "data_type": data_type,
        "unit": None,
        "required": True,
        "schema_ref": None,
        "temporal_support": None,
    }
    value.update(overrides)
    return value


def artifacts(**overrides: str) -> dict[str, str]:
    value = {
        ENTRYPOINT: ARTIFACT_HASH,
        "targets/reservoir/hydrology.py": LIBRARY_HASH,
    }
    value.update(overrides)
    return value


def empty_scope() -> dict[str, Any]:
    """A scope vector that is structurally complete and bounds nothing."""

    return empty_scope_vector(ROOT)


def bounded_scope(**overrides: Any) -> dict[str, Any]:
    scope = empty_scope()
    scope.update(
        {
            "domain": "hydrology",
            "population": "managed upland reservoirs",
            "entity_type": "reservoir",
            "unit_of_analysis": "reservoir-season",
            "setting": "temperate upland catchment",
            "temporal_scale": "season",
            "time_period": "2020-2025",
        }
    )
    scope.update(overrides)
    return scope


def manifest_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "target_id": "vt-reservoir-sim",
        "version": "1.4.0",
        "target_type": "simulation_model",
        "interface_version": "2.0.0",
        "entrypoint": ENTRYPOINT,
        "artifacts": artifacts(),
        "inputs": [
            port("rainfall_series", "timeseries", unit="mm", temporal_support="daily")
        ],
        "outputs": [port("storage_estimate", "number", unit="m3")],
        "parameters": [port("seed", "integer")],
        "state_variables": [port("reservoir_level", "number", unit="m")],
        "constraints": ["{seed} >= 0", "{reservoir_level} <= 12.5"],
        "supported_actions": ["simulate", "perturb"],
        "validation_scope": bounded_scope(),
        "identifiability_notes": ["inflow and abstraction are not separable"],
        "capability_requirements": ["compute.cpu"],
        "safety_class": "bounded_compute",
        "approval_policy": "high_risk_only",
        "provenance_manifest_id": "PROV-V01-1",
        "sandbox_profile": "bounded-compute-v1",
        "network_policy": "disabled",
        "supply_chain_attestation_artifact_id": "ATT-V01-1",
        "reproducibility_contract": {
            "container_digest_required": True,
            "environment_capture": True,
            "seed_control": True,
        },
        "allowed_data_classes": ["internal", "public"],
    }
    arguments.update(overrides)
    return arguments


def target_manifest(**overrides: Any) -> dict[str, Any]:
    return build_target_manifest(ROOT, **manifest_arguments(**overrides))


def raw_manifest(**overrides: Any) -> dict[str, Any]:
    """A built manifest mutated afterwards, to reach the screen unrepaired."""

    manifest = target_manifest()
    manifest.update(overrides)
    return manifest
