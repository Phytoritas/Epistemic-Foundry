"""Release provenance and installability evidence (EF4-I32, EF4-I35, EF4-I36).

Contract sources: `schemas/plugin-release-provenance.schema.json`,
`schemas/plugin-install-state.schema.json` and
`schemas/plugin-health-report.schema.json`.

Three invariants share one theme: a release claim is only as good as the evidence
that was actually collected, and missing evidence is not a pass.

* *EF4-I32 — Release provenance.* "Shipped bundles require reproducible build
  evidence, SBOM, manifest, clean extraction and signing status." Every one of
  those is a distinct digest or check, so `signing_status` is derived from the
  signatures present rather than asserted. An unsigned bundle is `UNSIGNED`, not
  "signing not applicable".
* *EF4-I35 — Installability is tested.* "Fresh install, PATH-less execution,
  upgrade, downgrade, uninstall and cross-platform paths are product acceptance
  tests." A `NOT_RUN` install check is the common way an untested path ships, so
  `NOT_RUN` is treated as failing the gate while remaining visibly distinct from
  `FAIL` in the report.
* *EF4-I36 — Remote messaging minimized.* "Remote notification/approval adapters
  are optional and cannot execute arbitrary commands or export raw evidence by
  default." The refusal is on the capability, not on the message content: an
  adapter that *can* execute a command is a remote execution surface whether or
  not any particular message uses it.

This module deliberately does not raise the release level. Collecting provenance
proves the bundle is describable, not that the product works, and
`cli/main.py` keeps the honest `SPEC_BUNDLE / PARTIAL_IMPLEMENTATION` label.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, is_schema_digest
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Build-provenance checks EF4-I32 requires by name.
REQUIRED_BUILD_CHECKS: tuple[str, ...] = (
    "reproducible_build",
    "sbom_generated",
    "manifest_complete",
    "clean_extraction",
)

#: Install paths EF4-I35 requires as product acceptance tests.
REQUIRED_INSTALL_CHECKS: tuple[str, ...] = (
    "fresh_install",
    "pathless_execution",
    "upgrade",
    "downgrade",
    "uninstall",
    "cross_platform_paths",
)

#: Capabilities a remote notification or approval adapter may never hold.
FORBIDDEN_REMOTE_CAPABILITIES: frozenset[str] = frozenset(
    {
        "command_execution",
        "shell",
        "arbitrary_command",
        "raw_evidence_export",
        "source_text_export",
        "holdout_read",
    }
)

#: Check statuses that satisfy a gate. `NOT_RUN` is excluded: an unrun check is
#: not a passing one, and it is the status a skipped acceptance test carries.
SATISFYING_CHECK_STATUSES: frozenset[str] = frozenset({"PASS", "WARN"})


class ProvenanceIncomplete(ValueError):
    """Release provenance is missing required evidence."""


class RemoteAdapterRefused(PermissionError):
    """A remote messaging adapter requests a forbidden capability."""


def _check_status(checks: Sequence[Mapping[str, Any]], check_id: str) -> str:
    for check in checks:
        if str(check.get("check_id")) == check_id:
            return str(check.get("status", "NOT_RUN"))
    return "NOT_RUN"


def unsatisfied_checks(
    checks: Sequence[Mapping[str, Any]], required: Sequence[str]
) -> list[str]:
    """Required checks that are failing or were never run, reported by name."""
    return [
        check_id
        for check_id in required
        if _check_status(checks, check_id) not in SATISFYING_CHECK_STATUSES
    ]


def derive_signing_status(signatures: Sequence[Mapping[str, Any]]) -> str:
    """Derive the signing status from the signatures actually present.

    Never a parameter. A builder that both signs and reports its signing status
    can label an unsigned bundle as signed, and the signature list is the only
    evidence that distinguishes the two.
    """
    if not signatures:
        return "UNSIGNED"
    incomplete = [
        signature
        for signature in signatures
        if not str(signature.get("signature", "")).strip()
        or not str(signature.get("identity", "")).strip()
    ]
    if incomplete:
        return "INVALID"
    return "SIGNED"


def build_release_provenance(
    *,
    plugin_id: str,
    version: str,
    source_revision: str,
    source_hash: str,
    bundle_hash: str,
    sbom_hash: str,
    manifest_hash: str,
    builder_identity: str,
    builder_environment_hash: str,
    checks: Sequence[Mapping[str, Any]],
    signatures: Sequence[Mapping[str, Any]],
    release_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record release provenance, refusing a bundle that cannot be described.

    `builder.reproducible` is derived from the `reproducible_build` check rather
    than accepted, because a builder asserting its own reproducibility is the
    party with the least incentive to notice that the check did not run.

    A floating source revision is refused: without an exact revision, the bundle
    hash identifies an artifact whose inputs cannot be recovered.
    """
    for label, digest in (
        ("source_hash", source_hash),
        ("bundle_hash", bundle_hash),
        ("sbom_hash", sbom_hash),
        ("manifest_hash", manifest_hash),
        ("builder_environment_hash", builder_environment_hash),
    ):
        if not is_schema_digest(digest):
            raise ProvenanceIncomplete(
                f"{label} must be a sha256 digest, got {digest!r}; a bundle whose inputs are "
                "not digest-identified cannot be rebuilt or compared"
            )
    if source_revision.strip() in {"", "main", "master", "HEAD", "latest"}:
        raise ProvenanceIncomplete(
            f"source_revision {source_revision!r} is floating; a later upstream change would "
            "alter the build while the provenance still names this revision"
        )

    missing = unsatisfied_checks(checks, REQUIRED_BUILD_CHECKS)
    if missing:
        raise ProvenanceIncomplete(
            f"release provenance is missing build evidence {missing}; a NOT_RUN check is not a "
            "passing one"
        )

    provenance: dict[str, Any] = {
        "release_id": release_id or new_id("REL"),
        "plugin_id": plugin_id,
        "version": version,
        "source_revision": source_revision,
        "source_hash": source_hash,
        "bundle_hash": bundle_hash,
        "sbom_hash": sbom_hash,
        "manifest_hash": manifest_hash,
        "builder": {
            "identity": builder_identity,
            "environment_hash": builder_environment_hash,
            "reproducible": _check_status(checks, "reproducible_build") == "PASS",
        },
        "checks": [dict(check) for check in checks],
        "signatures": [dict(signature) for signature in signatures],
        "created_at": created_at or utc_now_iso(),
    }
    provenance["provenance_hash"] = hash_excluding(provenance, "provenance_hash")
    validate_artifact("plugin-release-provenance", provenance)
    return provenance


def signing_status_of(provenance: Mapping[str, Any]) -> str:
    """The derived signing status of a recorded release."""
    return derive_signing_status(provenance.get("signatures", []))


def release_is_shippable(provenance: Mapping[str, Any]) -> bool:
    """True only for complete build evidence and a valid signature.

    An unsigned bundle may legitimately be *recorded* — that is how an internal
    build is described — but it is not shippable. Keeping the record and the
    verdict separate is what lets an unsigned build exist without being mislabeled.
    """
    if unsatisfied_checks(provenance.get("checks", []), REQUIRED_BUILD_CHECKS):
        return False
    return signing_status_of(provenance) == "SIGNED"


def install_acceptance_blockers(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Install paths EF4-I35 requires that are failing or untested.

    Reported together so an installer fixes the whole matrix in one pass, and by
    name so "untested downgrade" is never summarized as "5 of 6 passed".
    """
    return unsatisfied_checks(checks, REQUIRED_INSTALL_CHECKS)


def installability_is_demonstrated(checks: Sequence[Mapping[str, Any]]) -> bool:
    """True only when every required install path was actually exercised."""
    return not install_acceptance_blockers(checks)


def build_remote_adapter_profile(
    *,
    adapter_name: str,
    capabilities: Sequence[str],
    enabled_by_default: bool,
    approval_required: bool,
) -> dict[str, Any]:
    """Seal a remote notification/approval adapter profile.

    Two refusals, both on capability rather than on usage:

    * a command-execution or raw-evidence capability is refused outright, since
      holding it makes the adapter a remote execution or exfiltration surface
      regardless of what any single message does;
    * an adapter enabled by default is refused, because "optional" that ships on
      is not optional for the user who never chose it.
    """
    forbidden = sorted(set(capabilities) & FORBIDDEN_REMOTE_CAPABILITIES)
    if forbidden:
        raise RemoteAdapterRefused(
            f"remote adapter {adapter_name} requests {forbidden}; a notification channel that "
            "can execute commands or export raw evidence is not a notification channel"
        )
    if enabled_by_default:
        raise RemoteAdapterRefused(
            f"remote adapter {adapter_name} is enabled by default; a remote messaging surface "
            "the user never opted into is not optional"
        )
    return {
        "adapter_name": adapter_name,
        "capabilities": sorted(set(capabilities)),
        "enabled_by_default": False,
        "approval_required": bool(approval_required),
    }


def remote_adapter_may_export_evidence(profile: Mapping[str, Any]) -> bool:
    """Always False: no remote adapter exports raw evidence by default.

    A profile cannot reach True because `build_remote_adapter_profile` refuses the
    capability that would grant it. The predicate exists so the answer is
    discoverable at the call site rather than inferred from the absence of a flag.
    """
    return False
