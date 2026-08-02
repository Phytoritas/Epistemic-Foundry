"""Evolution run specification and explicit legacy migration.

Contract source: :mod:`schemas/evolution-run-spec.schema.json`.

An identifier is not a pin.  The v4 write path therefore accepts only a
complete ``resolved_refs`` object and seals it into ``spec_hash`` before a run
can start.  Persisted pre-v4 records use the separate migration entry point;
the normal builder never infers references from the current checkout, process
environment, provider defaults, or a floating remote alias.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any, Sequence

from ..contracts import ContractViolation, default_registry, validate_artifact
from ..domain.hashing import hash_excluding, is_schema_digest, sha256_of_payload
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

LEGACY_RUN_SPEC_RESOLUTION_REQUIRED = "LEGACY_RUN_SPEC_RESOLUTION_REQUIRED"


def _schema_pointer(document: Mapping[str, Any], pointer: str) -> object:
    """Resolve a local RFC 6901 pointer without restating schema vocabulary."""
    current: object = document
    for raw_token in pointer.removeprefix("/").split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or token not in current:
            raise RuntimeError(f"canonical schema pointer does not resolve: {pointer}")
        current = current[token]
    return current


_EVOLUTION_RUN_SPEC_SCHEMA = default_registry().document("evolution-run-spec")
REQUIRED_RESOLVED_REF_KEYS: tuple[str, ...] = tuple(
    _schema_pointer(_EVOLUTION_RUN_SPEC_SCHEMA, "/properties/resolved_refs/required")
)

_REFERENCE_FIELDS: tuple[str, ...] = (
    "logical_id",
    "exact_version_or_revision",
    "content_hash",
    "resolver_id",
    "resolver_version",
    "resolved_artifact_locator",
    "resolved_at",
    "authority_source_class",
    "reproducibility_class",
)
_FLOATING_TOKEN = re.compile(
    r"(?:^|[/:@._-])(?:main|latest|head|stable|default)(?:$|[/:@._-])",
    re.IGNORECASE,
)
_VERSION_RANGE = re.compile(
    r"(?:[<>=~^*]|\|\||(?:^|[._/-])[xX](?:$|[._/-]))"
)
_MODEL_ALIASES = frozenset(
    str(value).lower()
    for value in _EVOLUTION_RUN_SPEC_SCHEMA["$defs"]["remote_model_disclosure"][
        "properties"
    ]["exact_exposed_model_identifier"]["not"]["enum"]
)


class LegacyRunSpecResolutionRequired(ValueError):
    """A legacy record cannot be resolved from supplied immutable evidence."""

    code = LEGACY_RUN_SPEC_RESOLUTION_REQUIRED

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


def _require_exact_version(reference_name: str, field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"resolved_refs.{reference_name}.{field_name} must be non-empty")
    if _FLOATING_TOKEN.search(value) or _VERSION_RANGE.search(value):
        raise ValueError(
            f"resolved_refs.{reference_name}.{field_name}={value!r} is floating or a "
            "version range; an exact immutable revision is required"
        )


def _validate_reference(reference_name: str, reference: object) -> None:
    if not isinstance(reference, Mapping):
        raise ValueError(f"resolved_refs.{reference_name} must be an object")
    missing = [field for field in _REFERENCE_FIELDS if field not in reference]
    if missing:
        raise ValueError(
            f"resolved_refs.{reference_name} is missing required pin fields: {missing}"
        )
    _require_exact_version(
        reference_name,
        "exact_version_or_revision",
        reference["exact_version_or_revision"],
    )
    _require_exact_version(reference_name, "resolver_version", reference["resolver_version"])
    if not is_schema_digest(reference["content_hash"]):
        raise ValueError(
            f"resolved_refs.{reference_name}.content_hash must be sha256:<64 lowercase hex>"
        )


def _validate_resolved_refs(
    resolved_refs: object,
    *,
    external_backend_enabled: bool,
    base_run_spec_id: str,
    evaluator_bundle_id: str,
    holdout_manifest_id: str,
    budget_envelope_id: str,
) -> dict[str, Any]:
    if not isinstance(resolved_refs, Mapping) or not resolved_refs:
        raise ValueError(
            "resolved_refs must be a non-empty complete mapping; v4 never infers or defaults pins"
        )

    missing = [key for key in REQUIRED_RESOLVED_REF_KEYS if key not in resolved_refs]
    if missing:
        raise ValueError(f"resolved_refs is missing required references: {missing}")

    external_present = "external_backend_manifest" in resolved_refs
    if external_backend_enabled and not external_present:
        raise ValueError(
            "external_backend_enabled=true requires resolved_refs.external_backend_manifest"
        )
    if not external_backend_enabled and external_present:
        raise ValueError(
            "external_backend_enabled=false forbids resolved_refs.external_backend_manifest"
        )

    for name, reference in resolved_refs.items():
        _validate_reference(str(name), reference)

    expected_bindings = {
        "base_run_spec": base_run_spec_id,
        "evaluator_bundle": evaluator_bundle_id,
        "holdout_manifest": holdout_manifest_id,
        "budget_envelope": budget_envelope_id,
    }
    for name, expected_logical_id in expected_bindings.items():
        observed = resolved_refs[name].get("logical_id")
        if observed != expected_logical_id:
            raise ValueError(
                f"resolved_refs.{name}.logical_id {observed!r} does not bind top-level "
                f"identifier {expected_logical_id!r}"
            )

    provider_reference = resolved_refs["provider_adapter_manifest"]
    remote_models = provider_reference.get("remote_models")
    if not isinstance(remote_models, Sequence) or isinstance(remote_models, (str, bytes)):
        raise ValueError("provider_adapter_manifest.remote_models must be a non-empty array")
    if not remote_models:
        raise ValueError("provider_adapter_manifest.remote_models must not be empty")
    for index, model in enumerate(remote_models):
        if not isinstance(model, Mapping):
            raise ValueError(f"remote_models[{index}] must be an object")
        identifier = str(model.get("exact_exposed_model_identifier", ""))
        if identifier.lower() in _MODEL_ALIASES or _FLOATING_TOKEN.search(identifier):
            raise ValueError(
                f"remote_models[{index}].exact_exposed_model_identifier={identifier!r} "
                "is an unversioned provider alias"
            )
        for digest_field in ("adapter_hash", "capability_report_hash"):
            if not is_schema_digest(model.get(digest_field)):
                raise ValueError(
                    f"remote_models[{index}].{digest_field} must be sha256:<64 lowercase hex>"
                )
        _require_exact_version(
            f"provider_adapter_manifest.remote_models[{index}]",
            "adapter_version",
            model.get("adapter_version"),
        )

    external_reference = resolved_refs.get("external_backend_manifest")
    if external_reference is not None:
        source_pin = external_reference.get("source_pin")
        if not isinstance(source_pin, Mapping) or not any(
            source_pin.get(field)
            for field in (
                "exact_source_commit",
                "immutable_package_digest",
                "immutable_container_digest",
            )
        ):
            raise ValueError(
                "external_backend_manifest.source_pin requires an exact source commit, "
                "immutable package digest, or immutable container digest"
            )

    # Copy at the authority boundary.  A caller mutating its input mapping after
    # sealing must not retroactively alter the returned spec.
    return copy.deepcopy(dict(resolved_refs))


def build_evolution_run_spec(
    *,
    base_run_spec_id: str,
    objective: str,
    population_types: Sequence[str],
    seed_genome_ids: Sequence[str],
    evaluator_bundle_id: str,
    holdout_manifest_id: str,
    operator_registry_version: str,
    max_generations: int,
    max_candidates: int,
    budget_envelope_id: str,
    selection_policy: str,
    stop_policy: str,
    random_seed: int,
    external_backend_enabled: bool,
    resolved_refs: Mapping[str, Mapping[str, Any]],
    evolution_run_id: str | None = None,
) -> dict[str, Any]:
    """Seal one v4 evolution run from explicit immutable references."""
    if max_generations < 1 or max_candidates < 1:
        raise ValueError(
            "max_generations and max_candidates must both be >= 1; an unbounded run "
            "cannot produce a stop certificate"
        )
    if not seed_genome_ids:
        raise ValueError("an evolution run must pin at least one seed genome")
    if not isinstance(external_backend_enabled, bool):
        raise ValueError("external_backend_enabled must be an explicit boolean")
    _require_exact_version("operator_registry", "operator_registry_version", operator_registry_version)

    pinned_refs = _validate_resolved_refs(
        resolved_refs,
        external_backend_enabled=external_backend_enabled,
        base_run_spec_id=base_run_spec_id,
        evaluator_bundle_id=evaluator_bundle_id,
        holdout_manifest_id=holdout_manifest_id,
        budget_envelope_id=budget_envelope_id,
    )

    spec: dict[str, Any] = {
        "evolution_run_id": evolution_run_id or new_id("ERS"),
        "base_run_spec_id": base_run_spec_id,
        "objective": objective,
        # Both fields are schema-declared sets, so canonical sorting happens
        # before the final spec hash is calculated.
        "population_types": sorted(population_types),
        "seed_genome_ids": sorted(seed_genome_ids),
        "evaluator_bundle_id": evaluator_bundle_id,
        "holdout_manifest_id": holdout_manifest_id,
        "operator_registry_version": operator_registry_version,
        "max_generations": int(max_generations),
        "max_candidates": int(max_candidates),
        "budget_envelope_id": budget_envelope_id,
        "selection_policy": selection_policy,
        "stop_policy": stop_policy,
        "random_seed": int(random_seed),
        "external_backend_enabled": external_backend_enabled,
        "resolved_refs": pinned_refs,
    }
    spec["spec_hash"] = hash_excluding(spec, "spec_hash")
    validate_artifact("evolution-run-spec", spec)
    return spec


def migrate_legacy_evolution_run_spec(
    legacy_spec: Mapping[str, Any],
    *,
    resolved_refs: Mapping[str, Mapping[str, Any]] | None,
    external_backend_enabled: bool,
    resolution_evidence_artifact_ids: Sequence[str],
    target_evolution_run_id: str,
    migration_id: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Migrate one persisted pre-v4 spec using supplied immutable evidence.

    The function intentionally cannot discover references.  The caller must
    supply a complete resolution plus the immutable evidence IDs from which it
    was derived.  Any missing or invalid pin is surfaced with the canonical
    fail-closed code instead of constructing a plausible-looking SHA-256.
    """
    if "resolved_refs" in legacy_spec:
        raise LegacyRunSpecResolutionRequired(
            "the supplied artifact already carries resolved_refs; validate it as a v4 write"
        )
    evidence_ids = tuple(resolution_evidence_artifact_ids)
    if not evidence_ids or any(not item for item in evidence_ids):
        raise LegacyRunSpecResolutionRequired(
            "immutable resolution evidence artifact IDs are required"
        )
    source_run_id = str(legacy_spec.get("evolution_run_id", ""))
    if not target_evolution_run_id or target_evolution_run_id == source_run_id:
        raise LegacyRunSpecResolutionRequired(
            "migration requires a distinct explicit target_evolution_run_id"
        )
    if resolved_refs is None:
        raise LegacyRunSpecResolutionRequired("no resolved reference set was supplied")

    required_legacy_fields = (
        "base_run_spec_id",
        "objective",
        "population_types",
        "seed_genome_ids",
        "evaluator_bundle_id",
        "holdout_manifest_id",
        "operator_registry_version",
        "max_generations",
        "max_candidates",
        "budget_envelope_id",
        "selection_policy",
        "stop_policy",
        "random_seed",
    )
    missing = [field for field in required_legacy_fields if field not in legacy_spec]
    if missing:
        raise LegacyRunSpecResolutionRequired(
            f"legacy artifact is missing fields required for migration: {missing}"
        )

    try:
        migrated = build_evolution_run_spec(
            base_run_spec_id=str(legacy_spec["base_run_spec_id"]),
            objective=str(legacy_spec["objective"]),
            population_types=legacy_spec["population_types"],
            seed_genome_ids=legacy_spec["seed_genome_ids"],
            evaluator_bundle_id=str(legacy_spec["evaluator_bundle_id"]),
            holdout_manifest_id=str(legacy_spec["holdout_manifest_id"]),
            operator_registry_version=str(legacy_spec["operator_registry_version"]),
            max_generations=int(legacy_spec["max_generations"]),
            max_candidates=int(legacy_spec["max_candidates"]),
            budget_envelope_id=str(legacy_spec["budget_envelope_id"]),
            selection_policy=str(legacy_spec["selection_policy"]),
            stop_policy=str(legacy_spec["stop_policy"]),
            random_seed=int(legacy_spec["random_seed"]),
            external_backend_enabled=external_backend_enabled,
            resolved_refs=resolved_refs,
            evolution_run_id=target_evolution_run_id,
        )
    except (ContractViolation, TypeError, ValueError) as exc:
        raise LegacyRunSpecResolutionRequired(str(exc)) from exc

    migration_record: dict[str, Any] = {
        "record_type": "EvolutionRunSpecMigrationRecord",
        "migration_id": migration_id or new_id("MR"),
        "source_schema_version": "3.0.0",
        "target_schema_version": "4.0.0",
        "source_evolution_run_id": source_run_id,
        "target_evolution_run_id": target_evolution_run_id,
        "source_artifact_hash": sha256_of_payload(dict(legacy_spec)),
        "target_spec_hash": migrated["spec_hash"],
        "resolution_evidence_artifact_ids": list(dict.fromkeys(evidence_ids)),
        "resolution_status": "RESOLVED",
        "failure_code": None,
        "recorded_at": recorded_at or utc_now_iso(),
    }
    migration_record["migration_hash"] = hash_excluding(
        migration_record, "migration_hash"
    )
    return {
        "migration_record": migration_record,
        "evolution_run_spec": migrated,
    }


def rollback_legacy_evolution_run_spec(
    migration_result: Mapping[str, Any], legacy_spec: Mapping[str, Any]
) -> dict[str, Any]:
    """Recover the immutable legacy payload after a failed migration rollout."""
    record = migration_result.get("migration_record")
    if not isinstance(record, Mapping):
        raise LegacyRunSpecResolutionRequired("migration result has no MigrationRecord")
    if record.get("source_artifact_hash") != sha256_of_payload(dict(legacy_spec)):
        raise LegacyRunSpecResolutionRequired(
            "rollback source does not match the MigrationRecord source hash"
        )
    return copy.deepcopy(dict(legacy_spec))


def evaluator_binding_changed(spec: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    """Return whether evaluator or holdout identity/content binding changed."""
    if (
        spec.get("evaluator_bundle_id") != other.get("evaluator_bundle_id")
        or spec.get("holdout_manifest_id") != other.get("holdout_manifest_id")
    ):
        return True
    try:
        left_refs = spec["resolved_refs"]
        right_refs = other["resolved_refs"]
        return any(
            left_refs[name] != right_refs[name]
            for name in ("evaluator_bundle", "holdout_manifest")
        )
    except (KeyError, TypeError):
        # An unsealed legacy object is not equivalent to a sealed v4 binding.
        return True
