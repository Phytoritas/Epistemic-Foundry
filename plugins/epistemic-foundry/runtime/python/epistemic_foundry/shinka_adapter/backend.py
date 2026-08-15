"""Backend pinning, qualification, and advisory-signal mapping.

Contract sources: `schemas/shinka-backend-manifest.schema.json`,
`schemas/backend-adapter-qualification.schema.json`.

Two refusals define the adapter:

* An unpinned backend cannot be used. Without an exact revision and package
  version, a later upstream change silently alters search behaviour while the
  manifest still claims the qualified configuration.
* An unrecognized backend signal is an error, not a passthrough.
  `map_backend_signals` classifies every key it is given; anything unknown raises
  `UnmappableBackendSignal`, because a signal that reaches Foundry unclassified
  could be read downstream as evidence.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Backend outputs that are search signals only. They may steer exploration and
#: may never be treated as Foundry evidence or promotion input.
ADVISORY_BACKEND_SIGNALS: frozenset[str] = frozenset(
    {
        "combined_score",
        "correct",
        "novelty",
        "novelty_score",
        "island",
        "island_id",
        "archive",
        "archive_state",
        "lineage",
        "bandit_state",
        "operator_bandit",
        "fitness",
        "public_metric",
    }
)

#: Statuses that permit backend use at all.
USABLE_QUALIFICATION_STATUSES = frozenset({"QUALIFIED", "CONDITIONAL"})

#: The six capability tests `backend-adapter-qualification.schema.json` requires.
#: Each is a boolean, so a qualification cannot omit a dimension it did not
#: check — it has to say False.
REQUIRED_CAPABILITY_TESTS: tuple[str, ...] = (
    "deterministic_seed",
    "sandbox_isolation",
    "candidate_count_reconciliation",
    "effect_receipts",
    "resume_integrity",
    "evaluator_separation",
)

#: Capability tests that must hold before a backend may be called QUALIFIED.
#: `evaluator_separation` is non-negotiable: a backend that can see the
#: evaluator or holdout breaks the Verifier Firewall regardless of its scores.
QUALIFICATION_CRITICAL_TESTS: tuple[str, ...] = (
    "sandbox_isolation",
    "effect_receipts",
    "evaluator_separation",
)


class BackendNotQualified(PermissionError):
    """The backend is unpinned, unqualified, or rejected."""


class UnmappableBackendSignal(ValueError):
    """A backend signal has no defined Foundry mapping."""


def build_backend_manifest(
    *,
    backend_name: str,
    source_repository: str,
    source_revision: str,
    package_version: str,
    license: str,
    supported_candidate_types: Sequence[str],
    enabled_features: Sequence[str],
    disabled_features: Sequence[str],
    sandbox_profile_id: str,
    adapter_version: str,
    backend_manifest_id: str | None = None,
) -> dict[str, Any]:
    """Pin one backend build.

    A floating revision (`main`, `HEAD`, `latest`) is refused: the qualification
    result would describe a build that no longer exists.
    """
    floating = {"main", "master", "head", "latest", "trunk", ""}
    if source_revision.strip().lower() in floating:
        raise BackendNotQualified(
            f"refusing floating source_revision {source_revision!r}: pin an exact revision so "
            "the qualification result describes the build that actually runs"
        )
    if not license.strip():
        raise BackendNotQualified(
            "a backend manifest must record its license; Apache-2.0 obligations are a "
            "release requirement, not an optional note"
        )
    manifest: dict[str, Any] = {
        "backend_manifest_id": backend_manifest_id or new_id("SBM"),
        "backend_name": backend_name,
        "source_repository": source_repository,
        "source_revision": source_revision,
        "package_version": package_version,
        "license": license,
        "supported_candidate_types": list(supported_candidate_types),
        "enabled_features": list(enabled_features),
        "disabled_features": list(disabled_features),
        "sandbox_profile_id": sandbox_profile_id,
        "adapter_version": adapter_version,
    }
    manifest["manifest_hash"] = hash_excluding(manifest, "manifest_hash")
    validate_artifact("shinka-backend-manifest", manifest)
    return manifest


def build_qualification(
    *,
    backend_manifest_id: str,
    capability_tests: Mapping[str, Any],
    known_limitations: Sequence[str],
    status: str,
    allowed_release_level: str,
    qualification_id: str | None = None,
) -> dict[str, Any]:
    """Record a qualification outcome.

    A `QUALIFIED` verdict requires at least one executed capability test: an
    untested backend declared qualified is the ambiguity this contract exists to
    remove.
    """
    missing = [name for name in REQUIRED_CAPABILITY_TESTS if name not in capability_tests]
    if missing:
        raise BackendNotQualified(
            f"capability_tests is missing required dimension(s) {missing}; a qualification "
            "must state False rather than omit a check it did not run"
        )
    if status == "QUALIFIED":
        unmet = [name for name in QUALIFICATION_CRITICAL_TESTS if not capability_tests.get(name)]
        if unmet:
            raise BackendNotQualified(
                f"refusing QUALIFIED while critical capability test(s) {unmet} do not hold; "
                "a backend that fails isolation, receipts, or evaluator separation cannot be "
                "qualified regardless of its search performance"
            )
    record: dict[str, Any] = {
        "qualification_id": qualification_id or new_id("BAQ"),
        "backend_manifest_id": backend_manifest_id,
        "capability_tests": dict(capability_tests),
        "known_limitations": list(known_limitations),
        "status": status,
        "allowed_release_level": allowed_release_level,
    }
    record["qualification_hash"] = hash_excluding(record, "qualification_hash")
    validate_artifact("backend-adapter-qualification", record)
    return record


def assert_usable(manifest: Mapping[str, Any], qualification: Mapping[str, Any]) -> None:
    """Raise unless this qualification permits using this backend."""
    if qualification["backend_manifest_id"] != manifest["backend_manifest_id"]:
        raise BackendNotQualified(
            f"qualification targets {qualification['backend_manifest_id']!r} but the manifest is "
            f"{manifest['backend_manifest_id']!r}"
        )
    if str(qualification["status"]) not in USABLE_QUALIFICATION_STATUSES:
        raise BackendNotQualified(
            f"backend qualification status {qualification['status']} does not permit use"
        )


def map_backend_signals(signals: Mapping[str, Any]) -> dict[str, Any]:
    """Classify backend outputs; refuse anything without a defined mapping.

    Returns `{"advisory": {...}}` — deliberately a single bucket. There is no
    `evidence` key, because no raw backend output may become Foundry evidence
    without passing through the normal claim/evidence/validation path.
    """
    unknown = sorted(set(signals) - ADVISORY_BACKEND_SIGNALS)
    if unknown:
        raise UnmappableBackendSignal(
            f"backend signal(s) {unknown} have no defined Foundry mapping; failing closed "
            "rather than passing unclassified values into the runtime"
        )
    return {"advisory": {key: signals[key] for key in sorted(signals)}}


def signal_is_promotion_authority(name: str) -> bool:
    """Always False: no backend signal is promotion authority.

    Explicit predicate so a caller asking "can this score promote?" finds a
    documented no rather than writing a truthiness check on a raw score.
    """
    return False
