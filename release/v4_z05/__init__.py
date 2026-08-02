"""Zero-trust v4 release composition surface (Z05).

The package composes already-sealed surfaces into one fail-closed, deterministic
zero-trust release record.  It reconciles the sealed final release gate (Z04),
derives the signing provenance through the release-provenance surface (Z02/B05)
with the signing status *derived* rather than asserted, composes the 288-lens
evolution audit, binds the sealed security (S05), tool/sandbox (T05) and
operations (Y05) surfaces by identity, and refuses any record that would present
the release as production-ready or complete.

It composes and refuses.  Nothing here scores, promotes, mutates its inputs,
reads a clock, draws entropy, or raises the maturity floor: the release stays an
UNVERIFIED reference bundle and ``completion_ready`` stays false.
"""

from __future__ import annotations

from .zero_trust_release import (
    FINDING_CODES,
    RELEASE_AUTHORITY_PREFIX,
    RELEASE_AUDIT_PREFIX,
    RELEASE_PROVENANCE_PREFIX,
    RELEASE_RECONCILIATION_PREFIX,
    RELEASE_SURFACE_PREFIX,
    RELEASE_VERDICT_PREFIX,
    UNSIGNED_STATUS,
    ZeroTrustReleaseError,
    compose_lens_audit_attestation,
    compose_sealed_surface_fingerprint,
    reconciled_status_token,
    release_level_floor,
    require_no_release_authority_capture,
    require_reconciled_release,
    require_unsigned_provenance,
    seal_zero_trust_release,
)

__all__ = [
    "FINDING_CODES",
    "RELEASE_AUDIT_PREFIX",
    "RELEASE_AUTHORITY_PREFIX",
    "RELEASE_PROVENANCE_PREFIX",
    "RELEASE_RECONCILIATION_PREFIX",
    "RELEASE_SURFACE_PREFIX",
    "RELEASE_VERDICT_PREFIX",
    "UNSIGNED_STATUS",
    "ZeroTrustReleaseError",
    "compose_lens_audit_attestation",
    "compose_sealed_surface_fingerprint",
    "reconciled_status_token",
    "release_level_floor",
    "require_no_release_authority_capture",
    "require_reconciled_release",
    "require_unsigned_provenance",
    "seal_zero_trust_release",
]
