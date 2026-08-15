"""Backend pinning, qualification binding and the imported-run boundary (T05).

Contract sources: `schemas/shinka-backend-manifest.schema.json`,
`schemas/backend-adapter-qualification.schema.json` and
`schemas/imported-run-record.schema.json`.

The C05 adapter family already says what a pinned backend and a qualification
record look like, and `shinka_adapter` already builds and validates both, keeps
every backend output advisory, and refuses to route one at a Foundry authority
surface.  S05 already decides whether generated code may execute at all.  T05
composes those surfaces instead of restating them, and adds the three bindings
none of them can make alone:

* *Pinning is exact.*  `pin_backend` requires a full commit digest and an exact
  release before it delegates.  A revision that merely is not the word `main`
  still moves; a qualification recorded against a moving target describes a
  build nobody can reproduce.
* *Permission to run is bound to a checked profile.*  A qualification is only
  accepted together with an S05 execution qualification that re-derives its own
  hash and names the same sandbox profile the manifest pins.  Without that
  binding, "this backend is qualified" and "candidate code from this backend may
  execute" are two claims with nothing between them.
* *Import is bounded on both sides.*  An imported ShinkaEvolve run must
  reconcile its own candidate identities through the Foundry's reconciliation
  module before it is recorded, and no field of it may be bound onto a Foundry
  authority surface afterwards.  EF4-I63's asymmetry survives only if both ends
  hold: a run that cannot account for its population is refused at import, and a
  run that can is still never authority.

Nothing here runs ShinkaEvolve.  Every function returns a record or refuses.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ...budgets.envelope import (
    BOUNDING_ENFORCEMENT,
    LIMIT_DIMENSIONS,
)
from ...contracts import default_registry, validate_artifact
from ...evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
    ReconciliationFailed,
    reconcile_candidates,
    require_reconciled,
)
from ...security.v4_s05 import sandbox_classes
from ...shinka_adapter.backend import (
    REQUIRED_CAPABILITY_TESTS,
    build_backend_manifest,
    build_qualification,
)
from ...shinka_adapter.isolation import (
    BackendAuthorityRefused,
    import_backend_state,
    imported_state_is_authoritative,
    require_no_authority_routing,
)
from .findings import (
    _fail,
    assert_hash_rederives,
    require_identifier,
    require_identifiers,
    require_mapping,
    seal,
)
from .tool_surface import command_projection

QUALIFICATION_ARTIFACT = "backend-adapter-qualification"

#: A pinned revision is a full git commit digest or a content digest.  An
#: abbreviated hash is not a pin: it is a prefix that another object can grow
#: into, and it cannot be verified without the repository that produced it.
COMMIT_DIGEST = re.compile(r"^[0-9a-f]{40}$")
CONTENT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
#: An exact release, not a range, a tag alias or a wildcard.
EXACT_RELEASE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.\-]+)?$")

#: Fields the S05 execution qualification must carry for this binding to mean
#: anything.  They are read from the record rather than recomputed here.
EXECUTION_FIELDS: tuple[str, ...] = (
    "budget_enforcement",
    "budget_hash",
    "budget_id",
    "effect_receipt_channel_id",
    "evaluator_bundle_hash",
    "hard_limits",
    "qualification_hash",
    "sandbox_profile",
)


def qualification_statuses() -> tuple[str, ...]:
    """The verdict vocabulary, read from the schema that declares it.

    Read rather than restated: holding another schema's enum values as
    literals is what EF4-I22 forbids, and a vocabulary this package copied
    would keep accepting a verdict the contract had dropped.
    """
    document = default_registry().document(QUALIFICATION_ARTIFACT)
    return tuple(document["properties"]["status"]["enum"])


def _require_pinned(
    source_revision: object, package_version: object
) -> tuple[str, str]:
    revision = require_identifier(source_revision, "source_revision")
    version = require_identifier(package_version, "package_version")
    if COMMIT_DIGEST.fullmatch(revision) is None and (
        CONTENT_DIGEST.fullmatch(revision) is None
    ):
        _fail(
            "BACKEND_UNPINNED",
            "a backend revision must be a full commit or content digest",
            {"source_revision": revision},
        )
    if EXACT_RELEASE.fullmatch(version) is None:
        _fail(
            "BACKEND_UNPINNED",
            "a backend package version must be an exact release",
            {"package_version": version},
        )
    return revision, version


def pin_backend(
    *,
    backend_manifest_id: str,
    source_revision: str,
    package_version: str,
    **manifest_fields: Any,
) -> dict[str, Any]:
    """Build a canonical backend manifest pinned to one exact build.

    The remaining manifest fields are forwarded to the adapter's own builder,
    which validates them against the canonical schema and applies its own
    refusals (a floating revision, a missing license).  Those refusals are left
    to raise as themselves; wrapping them would hide which contract stopped the
    request.
    """
    revision, version = _require_pinned(source_revision, package_version)
    return build_backend_manifest(
        backend_manifest_id=require_identifier(
            backend_manifest_id, "backend_manifest_id"
        ),
        source_revision=revision,
        package_version=version,
        **manifest_fields,
    )


def assert_backend_pinned(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Re-check a manifest's pin and digest without trusting how it was built.

    `pin_backend` is not the only way a manifest can reach this package, so the
    pin is verified again wherever it matters rather than assumed from
    provenance.
    """
    value = dict(require_mapping(manifest, "backend manifest"))
    validate_artifact("shinka-backend-manifest", value)
    assert_hash_rederives(value, "manifest_hash", "backend manifest")
    _require_pinned(value.get("source_revision"), value.get("package_version"))
    return value


def qualify_backend_adapter(
    *,
    binding_id: str,
    qualification_id: str,
    manifest: Mapping[str, Any],
    capability_tests: Mapping[str, Any],
    known_limitations: Sequence[str],
    status: str,
    allowed_release_level: str,
    execution_qualification: Mapping[str, Any],
) -> dict[str, Any]:
    """Qualify a pinned backend and bind the qualification to its executor.

    Three refusals shape the record.  An unpinned manifest is refused before
    any capability is read.  A capability the manifest does not declare as
    enabled — or one it explicitly disables — cannot be claimed true, because a
    qualification is a statement about the build in front of it and not about
    the backend in general.  An execution qualification that does not
    re-derive its own hash, or that names a different sandbox profile than the
    manifest pins, leaves the executor unbound.

    The proposed-but-unprojected evolution commands are carried into the record
    from the sealed tool surface, so the qualification states which parts of the
    proposed CLI it does not and cannot serve.
    """
    pinned = assert_backend_pinned(manifest)
    declared_statuses = qualification_statuses()
    verdict = require_identifier(status, "status")
    if verdict not in declared_statuses:
        _fail(
            "QUALIFICATION_STATUS_UNDECLARED",
            "the verdict is not one the canonical schema declares",
            {"declared": list(declared_statuses), "status": verdict},
        )

    tests = dict(require_mapping(capability_tests, "capability_tests"))
    enabled = set(pinned.get("enabled_features") or ())
    disabled = set(pinned.get("disabled_features") or ())
    claimed = {name for name in REQUIRED_CAPABILITY_TESTS if tests.get(name) is True}
    undeclared = sorted(claimed - enabled)
    contradicted = sorted(claimed & disabled)
    if undeclared or contradicted:
        _fail(
            "CAPABILITY_OVERCLAIMED",
            "the qualification claims capabilities the manifest does not declare",
            {
                "contradicted": contradicted,
                "enabled_features": sorted(enabled),
                "undeclared": undeclared,
            },
        )

    execution = dict(
        require_mapping(execution_qualification, "execution_qualification")
    )
    missing = [field for field in EXECUTION_FIELDS if field not in execution]
    if missing:
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the execution qualification is missing fields this binding reads",
            {"missing": missing},
        )
    execution_hash = assert_hash_rederives(
        execution, "qualification_hash", "execution_qualification"
    )
    budget_id = require_identifier(execution["budget_id"], "budget_id")
    budget_hash = require_identifier(execution["budget_hash"], "budget_hash")
    if (
        execution["budget_hash"] != budget_hash
        or CONTENT_DIGEST.fullmatch(budget_hash) is None
    ):
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the execution qualification does not name a canonical budget digest",
            {"budget_hash": execution["budget_hash"]},
        )
    budget_enforcement = require_identifier(
        execution["budget_enforcement"], "budget_enforcement"
    )
    if (
        execution["budget_enforcement"] != budget_enforcement
        or budget_enforcement not in BOUNDING_ENFORCEMENT
    ):
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the execution qualification is not governed by a bounding budget",
            {
                "budget_enforcement": execution["budget_enforcement"],
                "bounding_enforcement": sorted(BOUNDING_ENFORCEMENT),
            },
        )
    hard_limits = dict(require_mapping(execution["hard_limits"], "hard_limits"))
    missing_dimensions = [
        dimension for dimension in LIMIT_DIMENSIONS if dimension not in hard_limits
    ]
    unexpected_dimensions = [
        str(dimension)
        for dimension in hard_limits
        if dimension not in LIMIT_DIMENSIONS
    ]
    if missing_dimensions or unexpected_dimensions:
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the execution qualification does not bind every canonical hard limit",
            {
                "missing_dimensions": missing_dimensions,
                "unexpected_dimensions": sorted(unexpected_dimensions),
            },
        )
    normalized_limits = {
        dimension: hard_limits[dimension] for dimension in LIMIT_DIMENSIONS
    }
    for dimension, limit in normalized_limits.items():
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
        ):
            _fail(
                "INPUT_INVALID",
                f"hard_limits[{dimension}] must be null or a non-negative integer",
                {"dimension": dimension, "value": limit},
            )
    if all(normalized_limits[dimension] is None for dimension in LIMIT_DIMENSIONS):
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the execution qualification binds no effective hard limit",
            {"hard_limits": normalized_limits},
        )
    profile = require_identifier(execution["sandbox_profile"], "sandbox_profile")
    declared_classes = sandbox_classes()
    if profile not in declared_classes:
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the executor profile is not a declared sandbox class",
            {"declared": list(declared_classes), "sandbox_profile": profile},
        )
    pinned_profile = require_identifier(
        pinned.get("sandbox_profile_id"), "sandbox_profile_id"
    )
    if profile != pinned_profile:
        _fail(
            "EXECUTION_PROFILE_UNBOUND",
            "the executor profile is not the profile the manifest pins",
            {"manifest_profile": pinned_profile, "sandbox_profile": profile},
        )

    qualification = build_qualification(
        qualification_id=require_identifier(qualification_id, "qualification_id"),
        backend_manifest_id=require_identifier(
            pinned.get("backend_manifest_id"), "backend_manifest_id"
        ),
        capability_tests=tests,
        known_limitations=list(known_limitations),
        status=verdict,
        allowed_release_level=require_identifier(
            allowed_release_level, "allowed_release_level"
        ),
    )

    projection = command_projection()
    return seal(
        {
            "backend_manifest_id": qualification["backend_manifest_id"],
            "binding_id": require_identifier(binding_id, "binding_id"),
            "budget_enforcement": budget_enforcement,
            "budget_hash": budget_hash,
            "budget_id": budget_id,
            "effect_receipt_channel_id": require_identifier(
                execution["effect_receipt_channel_id"], "effect_receipt_channel_id"
            ),
            "evaluator_bundle_hash": require_identifier(
                execution["evaluator_bundle_hash"], "evaluator_bundle_hash"
            ),
            "execution_qualification_hash": execution_hash,
            "executor_sandbox_profile": profile,
            "manifest_hash": pinned["manifest_hash"],
            "package_version": pinned["package_version"],
            "proposed_unavailable_commands": projection[
                "proposed_unavailable_commands"
            ],
            "qualification": qualification,
            "registrable_commands": projection["available_commands"],
            "source_revision": pinned["source_revision"],
            "surface_id": projection["surface_id"],
            "surface_version": projection["surface_version"],
        },
        "binding_hash",
    )


def _reconciliation_input(
    candidate_identities: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Validate the stage keys against the module that owns the vocabulary."""
    supplied = require_mapping(candidate_identities, "candidate_identities")
    accepted = set(STAGES) | set(TERMINAL_DISPOSITIONS)
    unknown = sorted(set(supplied) - accepted)
    absent = [stage for stage in STAGES if stage not in supplied]
    if unknown or absent:
        _fail(
            "INPUT_INVALID",
            "candidate_identities must name every pipeline stage and nothing else",
            {
                "accepted_stages": sorted(accepted),
                "missing_stages": absent,
                "unknown_stages": unknown,
            },
        )
    normalized = {
        str(stage): list(require_identifiers(values, f"candidate_identities[{stage}]"))
        for stage, values in sorted(supplied.items())
    }
    for stage, identities in normalized.items():
        if len(identities) != len(set(identities)):
            seen: set[str] = set()
            for identity in identities:
                if identity in seen:
                    _fail(
                        "INPUT_INVALID",
                        f"candidate_identities[{stage}] names {identity} more than once",
                        {"duplicate_identity": identity, "stage": stage},
                    )
                seen.add(identity)
    return normalized


def import_shinka_run(
    *,
    import_id: str,
    source_run_id: str,
    target_session_id: str,
    source_version: str,
    target_version: str,
    source_snapshot_hash: str,
    migration_plan_id: str,
    unconverted_fields: Sequence[str],
    imported_at: str,
    candidate_identities: Mapping[str, Any],
) -> dict[str, Any]:
    """Record an imported ShinkaEvolve run as a non-authoritative translation.

    The counts are reconciled first, through the Foundry's own reconciliation
    module, because an import that cannot account for its own population would
    otherwise become a run history whose gaps are invisible.  `imported_at` is
    required from the caller rather than read from a clock, so the record is
    reproducible and the import can be replayed.

    The returned envelope states its own standing: `authoritative` is derived
    from the adapter's boundary predicate, never asserted here.
    """
    stages = _reconciliation_input(candidate_identities)
    report = reconcile_candidates(**stages)
    try:
        require_reconciled(report)
    except ReconciliationFailed as error:
        _fail(
            "IMPORT_COUNTS_UNRECONCILED",
            str(error),
            {
                "counts": report["counts"],
                "gaps": sorted(report["gaps"]),
                "missing": report["missing"],
                "unknown_identities": sorted(report["unknown_identities"]),
            },
        )

    record = import_backend_state(
        import_id=require_identifier(import_id, "import_id"),
        source_version=require_identifier(source_version, "source_version"),
        target_version=require_identifier(target_version, "target_version"),
        source_run_id=require_identifier(source_run_id, "source_run_id"),
        target_session_id=require_identifier(target_session_id, "target_session_id"),
        source_snapshot_hash=require_identifier(
            source_snapshot_hash, "source_snapshot_hash"
        ),
        migration_plan_id=require_identifier(migration_plan_id, "migration_plan_id"),
        unconverted_fields=list(unconverted_fields),
        imported_at=require_identifier(imported_at, "imported_at"),
    )
    authoritative = imported_state_is_authoritative(record)
    if authoritative:  # pragma: no cover - the predicate is constant by contract
        _fail(
            "BACKEND_AUTHORITY_LEAK",
            "an imported run reported itself as Foundry authority",
            {"import_id": record["import_id"]},
        )
    return seal(
        {
            "authoritative": authoritative,
            "imported_run": record,
            "reconciliation": report,
        },
        "import_hash",
    )


def require_no_imported_authority(
    *,
    imported: Mapping[str, Any],
    bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Refuse to bind any imported backend field onto Foundry authority.

    `bindings` maps an imported backend field to the Foundry destination it
    would be written to.  Both halves of the refusal are delegated to the
    adapter module that owns them: a destination the constitution reserves for
    the kernel is refused, and so is a field the adapter has not classified as
    advisory — an unclassified field cannot be shown to stay outside authority
    in the first place.
    """
    envelope = dict(require_mapping(imported, "imported"))
    assert_hash_rederives(envelope, "import_hash", "imported")
    record = dict(require_mapping(envelope.get("imported_run"), "imported_run"))
    assert_hash_rederives(record, "record_hash", "imported_run")
    if envelope.get("authoritative") is not False:
        _fail(
            "BACKEND_AUTHORITY_LEAK",
            "the import envelope does not record itself as non-authoritative",
            {"import_id": record.get("import_id")},
        )

    routes = {
        require_identifier(field, "bindings key"): require_identifier(
            surface, f"bindings[{field}]"
        )
        for field, surface in require_mapping(bindings, "bindings").items()
    }
    try:
        require_no_authority_routing(routes)
    except BackendAuthorityRefused as error:
        _fail(
            "BACKEND_AUTHORITY_LEAK",
            str(error),
            {"bindings": dict(sorted(routes.items()))},
        )
    return seal(
        {
            "accepted_bindings": dict(sorted(routes.items())),
            "authoritative": False,
            "import_id": require_identifier(record.get("import_id"), "import_id"),
            "record_hash": record["record_hash"],
        },
        "gate_hash",
    )
