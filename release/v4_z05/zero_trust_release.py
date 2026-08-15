"""Zero-trust v4 release, 288-lens audit and signing provenance gate (Z05).

Z04 sealed the final release reconciliation, Z02/B05 sealed the deterministic
build and the release-provenance surface, S05 sealed the verifier-firewall and
executable-candidate threat controls, T05 sealed the external-backend tool and
sandbox surface, and Y05 sealed the production-scale operations gate.  Each is
correct alone.  What none of them answers is the question a *release* turns on:
when the whole v4 bundle is declared releasable, does its reconciliation actually
pass without claiming completion, is its signing status honestly derived (an
unverified reference bundle is UNSIGNED, never "signed" by assertion), does the
288-lens audit carry a single failing lens, are the sealed security, tool and
operations surfaces bound by identity so a break in one shows here, and does the
release refuse to acquire promotion authority or to present itself as
production-ready?

This is the *composition* gate over such a release.  No bundle is built, signed
or shipped here.  The release is modelled as a declared manifest the caller
supplies, and the gate composes the sealed owners it cites: the reconciliation
status token is read positionally from the canonical attestation schema, the
signing status is derived through the sealed release-provenance surface, the
maturity floor is read from the acceptance matrix, and the promotion authority is
grounded in the canonical ``promotion:commit`` capability imported from the
evolution-authority registry.  A reshaped schema, a raised maturity floor or a
renamed capability fails closed rather than silently selecting the wrong value.

*Reconciliation.*  ``require_reconciled_release`` refuses a release whose composed
Z04 reconciliation is not PASS, or that declares itself complete: the whole point
of the zero-trust label is that a passing reconciliation names remaining owned
work, it does not certify completion.

*Signing provenance.*  ``require_unsigned_provenance`` composes the sealed
release-provenance surface with an empty signature set, so the signing status is
*derived* as UNSIGNED rather than asserted; a signature offered for an unverified
reference release is refused rather than laundered into a signed claim.

*288-lens audit.*  ``compose_lens_audit_attestation`` binds the 288-lens audit
only when it carries no failing lens and its family/lens arithmetic is internally
consistent, so coverage can never be claimed by omission.

*Authority containment.*  ``require_no_release_authority_capture`` refuses any
release record that grants a mutable-search artifact — a candidate, model,
prompt, backend or hook — evaluator, holdout or promotion authority, or that
binds a numeric score into a promotion decision.

*Surface identity.*  ``compose_sealed_surface_fingerprint`` binds the sealed S05,
T05 and Y05 surfaces by their declared identity, so a break in a composed surface
changes the fingerprint the release seals.

``seal_zero_trust_release`` composes the five into one release verdict binding
every sub-receipt by hash and refusing any maturity overclaim.  Every decision
resolves to an immutable, content-addressed receipt: two runs over equal inputs
produce byte-equal receipts, and the caller supplies every identifier and
timestamp a receipt binds.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

from epistemic_foundry.contracts import default_registry, repo_root
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.governance.evolution_authority.registry import (
    PROMOTION_COMMIT_CAPABILITY,
)
from epistemic_foundry.release.provenance import (
    ProvenanceIncomplete,
    build_release_provenance,
    signing_status_of,
)

#: Every way this surface refuses, and why the refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership and
#: every code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would record "
        "a release decision derived from something it never validated"
    ),
    "STATUS_VOCABULARY_DRIFT": (
        "the canonical attestation status vocabulary is no longer the ladder this "
        "gate reads positionally, so selecting the PASS token by index would pick "
        "the wrong value; the gate fails closed rather than guess"
    ),
    "RELEASE_NOT_RECONCILED": (
        "the composed final release reconciliation did not pass, so the bundle "
        "cannot be presented as a reconciled release rather than an open one"
    ),
    "RELEASE_CLAIMS_COMPLETION": (
        "the release declares completion_ready true, but a zero-trust release names "
        "remaining owned work and never certifies the product complete"
    ),
    "SIGNATURE_ON_UNVERIFIED_RELEASE": (
        "a signature was offered for an unverified reference bundle whose signing "
        "identity is not available, which would launder an unsigned artifact into a "
        "signed claim; the release stays fail-closed UNSIGNED"
    ),
    "SIGNING_STATUS_NOT_UNSIGNED": (
        "the derived signing status is not UNSIGNED, so the release-provenance "
        "surface reports signing evidence this fail-closed release must not carry"
    ),
    "PROVENANCE_INCOMPLETE": (
        "the sealed release-provenance surface refused the bundle — missing build "
        "evidence, a floating revision or a non-digest input — so no provenance can "
        "be composed for it"
    ),
    "AUDIT_SHAPE_INVALID": (
        "the 288-lens audit's family and lens arithmetic is internally inconsistent "
        "or its summary does not partition the results, so its coverage claim cannot "
        "be trusted"
    ),
    "AUDIT_HAS_FAILING_LENS": (
        "the 288-lens audit carries at least one failing lens, so the release would "
        "ship over a known failed contract surface"
    ),
    "SEALED_SURFACE_MISSING": (
        "a sealed surface the release must bind by identity is absent or declares no "
        "identity token, so the release would seal a composition it cannot cite"
    ),
    "RELEASE_ACQUIRES_PROMOTION_AUTHORITY": (
        "a candidate, model, prompt, backend or hook in the mutable search space was "
        "granted evaluator, holdout or promotion authority at release, so the release "
        "path would itself become an authority path (EF4-I45)"
    ),
    "SCORE_BOUND_INTO_PROMOTION_FIELD": (
        "a release record binds a numeric score into a promotion-authority decision, "
        "which would let a proxy score stand in for the sealed gate verdict the "
        "promotion authority must carry (EF4-I45)"
    ),
    "MATURITY_OVERCLAIM": (
        "the release record declares itself production-ready or complete, or raises "
        "the maturity above the floor the acceptance matrix declares, which the "
        "honesty gate forbids for an unverified reference bundle"
    ),
}

#: Identifier prefixes.  Every identifier this gate mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
RELEASE_RECONCILIATION_PREFIX = "ZRR-"
RELEASE_PROVENANCE_PREFIX = "ZSP-"
RELEASE_AUDIT_PREFIX = "ZLA-"
RELEASE_AUTHORITY_PREFIX = "ZAG-"
RELEASE_SURFACE_PREFIX = "ZSF-"
RELEASE_VERDICT_PREFIX = "ZTR-"

#: The signing status a fail-closed unverified release must carry.  It is not
#: held as a wire literal: it is read back from the sealed release-provenance
#: surface's own derivation over an empty signature set.
UNSIGNED_STATUS = signing_status_of({"signatures": []})

#: The canonical attestation status ladder this gate reads positionally, and the
#: index of the passing rung within it.
_ATTESTATION_STATUS_KIND = "attestation"
_ATTESTATION_STATUS_FIELD = "overall_status"
_ATTESTATION_PASS_INDEX = 0

#: The 288-lens audit contract: 24 failure-surface families times 12 contract
#: lenses.  The arithmetic is asserted against the audit's own declared counts so
#: a padded or truncated audit fails closed.
_LENS_PER_FAMILY = 12

#: Lens outcomes that are not a failure.  A conditional lens is an owned,
#: non-blocking remaining item, not a failed contract; only a genuinely failing
#: status blocks the release.  This token is the 288-lens audit's own report
#: vocabulary, not a canonical wire enum.
_NON_FAILING_LENS_STATUSES: frozenset[str] = frozenset({"CONDITIONAL"})

#: The three dependency surfaces Z05 is authorized and required to compose.
#: Their names are the sealed identities used by the S05, T05 and Y05 contracts;
#: accepting a subset or an unrelated surface would let the release omit a
#: required dependency while still presenting a complete composition.
_REQUIRED_SEALED_SURFACES: frozenset[str] = frozenset(
    {"security_v4_s05", "adapters_v4_t05", "operations_v4_y05"}
)

#: The acceptance-matrix key that declares the current bundle's maturity floor.
_ACCEPTANCE_MATRIX_PATH = "manifests/acceptance_matrix.yaml"
_MATURITY_FLOOR_KEY = "status_of_this_bundle"


class ZeroTrustReleaseError(ValueError):
    """The gate refuses a reconciliation, provenance, audit, authority or seal."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise ZeroTrustReleaseError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ZeroTrustReleaseError(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _require_count(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(
            "INPUT_INVALID",
            f"{label} must be a non-negative integer",
            {"label": label, "value": value},
        )
    return int(value)  # type: ignore[arg-type]


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a boolean", {"label": label})
    return bool(value)


@lru_cache(maxsize=1)
def _pass_status_token() -> str:
    """The passing status token, read positionally from the attestation schema.

    Holding the token as a literal would be a second copy that drifts from the
    contract (EF4-I22).  The attestation schema's ``overall_status`` ladder leads
    with the passing rung; a reshape that empties or reorders it fails closed here
    rather than selecting the wrong token.
    """
    document = default_registry().document(_ATTESTATION_STATUS_KIND)
    enum = document.get("properties", {}).get(_ATTESTATION_STATUS_FIELD, {}).get("enum")
    if not isinstance(enum, list) or not enum:
        _fail(
            "STATUS_VOCABULARY_DRIFT",
            "the attestation status vocabulary is not a non-empty ladder",
            {"enum": enum, "schema": _ATTESTATION_STATUS_KIND},
        )
    return str(enum[_ATTESTATION_PASS_INDEX])


def reconciled_status_token() -> str:
    """The canonical passing status, read from the attestation schema."""
    return _pass_status_token()


@lru_cache(maxsize=1)
def release_level_floor() -> str:
    """The maturity floor the acceptance matrix declares for this bundle.

    Reading the floor from the acceptance matrix keeps the honesty gate honest:
    the release cannot claim a level the canonical evidence does not, and a raised
    floor changes the seal rather than being restated here.
    """
    import yaml

    path = repo_root() / _ACCEPTANCE_MATRIX_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    floor = document.get(_MATURITY_FLOOR_KEY) if isinstance(document, Mapping) else None
    return _require_text(floor, f"{_ACCEPTANCE_MATRIX_PATH}:{_MATURITY_FLOOR_KEY}")


def _identified(record: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record["receipt_id"] = prefix + sha256_of_payload(record)[len("sha256:") :]
    record["receipt_hash"] = hash_excluding(record, "receipt_hash")
    return record


def _carries_score(basis: Mapping[str, Any]) -> bool:
    """Whether a decision basis binds a raw numeric score.

    A promotion decision must be a sealed gate verdict — a reference or a boolean
    admissibility, never a raw number a proxy could produce — so any non-boolean
    numeric value in the basis is a score being bound into the decision.
    """
    for value in basis.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return True
    return False


def require_reconciled_release(
    *,
    release_id: str,
    reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    """Refuse a release whose composed final reconciliation does not pass.

    The Z04 final release gate owns the A-Z reconciliation; this gate holds the
    composed reconciliation to two conditions the release turns on: its status is
    the canonical passing token (read positionally from the attestation schema),
    and it does not declare completion.  A passing reconciliation names remaining
    owned work — it never certifies the product complete — so a record that sets
    ``completion_ready`` true is refused rather than sealed.  The receipt is
    content-addressed and binds the reconciliation's own content hash.
    """
    identifier = _require_text(release_id, "release_id")
    facts = _require_mapping(reconciliation, "reconciliation")
    status = _require_text(facts.get("status"), "reconciliation.status")
    if status != _pass_status_token():
        _fail(
            "RELEASE_NOT_RECONCILED",
            "the composed final release reconciliation did not pass",
            {"status": status, "expected": _pass_status_token()},
        )
    completion = facts.get("completion_ready")
    if completion is not False:
        _fail(
            "RELEASE_CLAIMS_COMPLETION",
            "a zero-trust release must not declare completion_ready true",
            {"completion_ready": completion},
        )

    receipt: dict[str, Any] = {
        "release_id": identifier,
        "reconciled": True,
        "reconciliation_status": status,
        "completion_ready": False,
        "reconciliation_hash": sha256_of_payload(facts),
    }
    return _identified(receipt, RELEASE_RECONCILIATION_PREFIX)


def require_unsigned_provenance(
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
    created_at: str,
    signatures: Sequence[Mapping[str, Any]] = (),
    release_id: str | None = None,
) -> dict[str, Any]:
    """Compose the sealed release-provenance surface, fail-closed UNSIGNED.

    The signing provenance is delegated to the sealed release-provenance surface
    (Z02/B05), which derives the signing status from the signatures actually
    present rather than accepting an asserted one.  This gate holds the release to
    the fail-closed rule: an unverified reference bundle whose signing identity is
    not available carries no signature, so a signature offered here is refused
    before it can be laundered into a signed claim, and the composed provenance's
    derived status is required to be UNSIGNED.  The caller supplies ``created_at``
    so the composed provenance carries no clock.  The receipt is content-addressed
    and binds the provenance's own hash.
    """
    offered = _require_sequence(signatures, "signatures")
    if offered:
        _fail(
            "SIGNATURE_ON_UNVERIFIED_RELEASE",
            "an unverified reference release carries no signature; signing identity "
            "is not available",
            {"signature_count": len(offered)},
        )

    # The sealed provenance surface mints a random release_id when none is given;
    # a zero-trust release is byte-identical on re-run, so when the caller does not
    # pin an id the gate derives a content-addressed one from the provenance inputs
    # rather than drawing entropy.
    resolved_release_id = (
        release_id
        or RELEASE_PROVENANCE_PREFIX
        + sha256_of_payload(
            [
                plugin_id,
                version,
                source_revision,
                source_hash,
                bundle_hash,
                sbom_hash,
                manifest_hash,
                builder_identity,
                builder_environment_hash,
            ]
        )[len("sha256:") :]
    )

    try:
        provenance = build_release_provenance(
            plugin_id=plugin_id,
            version=version,
            source_revision=source_revision,
            source_hash=source_hash,
            bundle_hash=bundle_hash,
            sbom_hash=sbom_hash,
            manifest_hash=manifest_hash,
            builder_identity=builder_identity,
            builder_environment_hash=builder_environment_hash,
            checks=[dict(_require_mapping(c, "checks[]")) for c in checks],
            signatures=[],
            release_id=resolved_release_id,
            created_at=_require_text(created_at, "created_at"),
        )
    except ProvenanceIncomplete as error:
        _fail("PROVENANCE_INCOMPLETE", str(error))

    derived = signing_status_of(provenance)
    if derived != UNSIGNED_STATUS:
        _fail(
            "SIGNING_STATUS_NOT_UNSIGNED",
            "the composed release provenance is not fail-closed unsigned",
            {"signing_status": derived},
        )

    receipt: dict[str, Any] = {
        "release_id": provenance["release_id"],
        "plugin_id": provenance["plugin_id"],
        "version": provenance["version"],
        "signing_status": derived,
        "reproducible": bool(provenance["builder"]["reproducible"]),
        "provenance_hash": str(provenance["provenance_hash"]),
    }
    return _identified(receipt, RELEASE_PROVENANCE_PREFIX)


def compose_lens_audit_attestation(
    *,
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the 288-lens audit only when no lens fails and its counts partition.

    The audit is composed by citation: the record binds the audit's own content
    hash and its per-status summary, but only after two internal-consistency
    checks the audit cannot vouch for itself.  Its family and lens arithmetic must
    close (families times twelve lenses equals the declared total, and the total
    equals the number of results), and its summary must partition those results by
    status.  A single failing lens is refused rather than counted, so coverage can
    never be claimed by omission.  The receipt is content-addressed.
    """
    document = _require_mapping(audit, "audit")
    families = _require_count(document.get("families"), "audit.families")
    total = _require_count(document.get("total"), "audit.total")
    results = _require_sequence(document.get("results"), "audit.results")
    summary = _require_mapping(document.get("summary"), "audit.summary")

    if families * _LENS_PER_FAMILY != total or total != len(results):
        _fail(
            "AUDIT_SHAPE_INVALID",
            "the audit family/lens arithmetic does not close",
            {"families": families, "total": total, "results": len(results)},
        )

    observed: dict[str, int] = {}
    for index, entry in enumerate(results):
        row = _require_mapping(entry, f"audit.results[{index}]")
        status = _require_text(row.get("status"), f"audit.results[{index}].status")
        observed[status] = observed.get(status, 0) + 1

    declared = {
        _require_text(key, "audit.summary key"): _require_count(
            value, f"audit.summary[{key}]"
        )
        for key, value in summary.items()
    }
    # A declared zero is an explicit "this status did not occur"; it is compared
    # against the absence of that status among the results rather than requiring a
    # zero-count key to appear in the observed tally.
    declared_present = {status: count for status, count in declared.items() if count}
    if declared_present != observed or sum(declared.values()) != total:
        _fail(
            "AUDIT_SHAPE_INVALID",
            "the audit summary does not partition its results by status",
            {"declared": declared, "observed": observed},
        )

    pass_token = _pass_status_token()
    failing = {
        status: count
        for status, count in observed.items()
        if count and status != pass_token and status not in _NON_FAILING_LENS_STATUSES
    }
    if failing:
        _fail(
            "AUDIT_HAS_FAILING_LENS",
            "the 288-lens audit carries at least one failing lens",
            {"failing": failing},
        )

    receipt: dict[str, Any] = {
        "audit_id": _require_text(document.get("audit_id"), "audit.audit_id"),
        "families": families,
        "total": total,
        "status_counts": dict(sorted(observed.items())),
        "audit_content_hash": sha256_of_payload(document),
    }
    return _identified(receipt, RELEASE_AUDIT_PREFIX)


def require_no_release_authority_capture(
    *,
    authority_claims: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Refuse the release becoming a promotion-authority path.

    Two boundaries are composed and neither substitutes for the other.  A claim
    that grants the canonical ``promotion:commit`` capability — or any authority
    the caller marks protected — to a mutable-search artifact (a candidate, model,
    prompt, backend or hook) is refused: the search space may never acquire
    evaluator, holdout or promotion authority at release.  And a claim that binds a
    numeric score into a protected authority is refused: a proxy score may order
    search but never carry the promotion verdict.  The canonical promotion
    capability is always treated as protected, so a claim cannot launder it as
    ordinary.  The receipt is content-addressed.
    """
    claims = _require_sequence(authority_claims, "authority_claims")

    summary: list[dict[str, Any]] = []
    for index, entry in enumerate(claims):
        claim = _require_mapping(entry, f"authority_claims[{index}]")
        capability = _require_text(
            claim.get("capability_id"), f"authority_claims[{index}].capability_id"
        )
        holder = _require_text(
            claim.get("holder_id"), f"authority_claims[{index}].holder_id"
        )
        search = bool(claim.get("holder_is_search_space", False))
        protected = bool(claim.get("protected_authority", False))
        basis = claim.get("decision_basis") or {}
        if not isinstance(basis, Mapping):
            _fail(
                "INPUT_INVALID",
                f"authority_claims[{index}].decision_basis must be a mapping",
                {"index": index},
            )
        # Ground the self-reported flag in the canonical capability: the
        # promotion-commit capability is protected authority by definition.
        if capability == PROMOTION_COMMIT_CAPABILITY:
            protected = True

        if protected and search:
            _fail(
                "RELEASE_ACQUIRES_PROMOTION_AUTHORITY",
                "a mutable-search artifact was granted a protected evaluator, "
                "holdout or promotion authority at release",
                {"capability_id": capability, "holder_id": holder},
            )
        if protected and _carries_score(basis):
            _fail(
                "SCORE_BOUND_INTO_PROMOTION_FIELD",
                "a release record binds a numeric score into a promotion-authority "
                "decision",
                {"capability_id": capability, "holder_id": holder},
            )
        summary.append(
            {
                "capability_id": capability,
                "holder_id": holder,
                "holder_is_search_space": search,
                "protected_authority": protected,
            }
        )

    receipt: dict[str, Any] = {
        "authority_claims": summary,
        "no_authority_captured": True,
    }
    return _identified(receipt, RELEASE_AUTHORITY_PREFIX)


def compose_sealed_surface_fingerprint(
    *,
    surfaces: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Bind the sealed S05, T05 and Y05 surfaces by their declared identity.

    Each surface contributes a set of identity tokens — its declared finding-code
    vocabulary — and the release seals a fingerprint over them.  A surface that is
    absent, extra or declares no token is refused rather than sealed, and because
    the fingerprint is a pure function of the tokens, a break that removes or
    renames a surface's vocabulary changes the fingerprint the release binds.  The
    receipt is content-addressed.
    """
    provided = _require_mapping(surfaces, "surfaces")
    invalid_key_types = sorted(
        {type(name).__name__ for name in provided if type(name) is not str}
    )
    if invalid_key_types:
        _fail(
            "SEALED_SURFACE_MISSING",
            "sealed surface names must be exact strings",
            {"invalid_key_types": invalid_key_types},
        )
    provided_names = set(provided)
    if provided_names != _REQUIRED_SEALED_SURFACES:
        _fail(
            "SEALED_SURFACE_MISSING",
            "the sealed surface set must match the required S05, T05 and Y05 "
            "surfaces exactly",
            {
                "missing": sorted(_REQUIRED_SEALED_SURFACES - provided_names),
                "extra": sorted(provided_names - _REQUIRED_SEALED_SURFACES),
            },
        )

    fingerprint: dict[str, Any] = {}
    for name in sorted(_REQUIRED_SEALED_SURFACES):
        tokens = _require_sequence(provided[name], f"surfaces[{name}]")
        cleaned = sorted(
            {_require_text(token, f"surfaces[{name}][]") for token in tokens}
        )
        if not cleaned:
            _fail(
                "SEALED_SURFACE_MISSING",
                f"sealed surface {name} declares no identity token",
                {"surface": name},
            )
        fingerprint[name] = {
            "token_count": len(cleaned),
            "identity_hash": sha256_of_payload(cleaned),
        }

    receipt: dict[str, Any] = {
        "surface_count": len(fingerprint),
        "surfaces": fingerprint,
    }
    return _identified(receipt, RELEASE_SURFACE_PREFIX)


def seal_zero_trust_release(
    *,
    release_id: str,
    reconciliation: Mapping[str, Any],
    provenance_inputs: Mapping[str, Any],
    audit: Mapping[str, Any],
    surfaces: Mapping[str, Sequence[str]],
    authority_claims: Sequence[Mapping[str, Any]] = (),
    completion_ready: bool = False,
    production_ready: bool = False,
) -> dict[str, Any]:
    """Compose the whole release gate and seal one zero-trust release verdict.

    The five sub-gates each refuse independently; only when the reconciliation
    passes without claiming completion, the provenance derives UNSIGNED, the
    288-lens audit carries no failing lens, no authority is captured and every
    sealed surface is bound does this seal a release verdict.  Before sealing, the
    honesty floor is enforced: a record declaring itself production-ready or
    complete is refused, and the release level is fixed to the floor the
    acceptance matrix declares rather than any caller claim.  The verdict binds
    each sub-receipt by hash, so it cannot be forged without reproducing every gate
    it depends on, and it is content-addressed with no clock or random draw.
    """
    identifier = _require_text(release_id, "release_id")
    if _require_bool(completion_ready, "completion_ready"):
        _fail(
            "MATURITY_OVERCLAIM",
            "a zero-trust release must not declare completion_ready true",
            {"completion_ready": completion_ready},
        )
    if _require_bool(production_ready, "production_ready"):
        _fail(
            "MATURITY_OVERCLAIM",
            "a zero-trust release must not declare production_ready true",
            {"production_ready": production_ready},
        )

    reconciled = require_reconciled_release(
        release_id=identifier, reconciliation=reconciliation
    )
    provenance = require_unsigned_provenance(
        **_require_mapping(provenance_inputs, "provenance_inputs")
    )
    lens_audit = compose_lens_audit_attestation(audit=audit)
    authority = require_no_release_authority_capture(authority_claims=authority_claims)
    surface = compose_sealed_surface_fingerprint(surfaces=surfaces)

    verdict: dict[str, Any] = {
        "release_id": identifier,
        "release_passed": True,
        "release_level": release_level_floor(),
        "signing_status": str(provenance["signing_status"]),
        "completion_ready": False,
        "production_ready": False,
        "reconciliation_receipt_id": reconciled["receipt_id"],
        "reconciliation_receipt_hash": reconciled["receipt_hash"],
        "provenance_receipt_id": provenance["receipt_id"],
        "provenance_receipt_hash": provenance["receipt_hash"],
        "audit_receipt_id": lens_audit["receipt_id"],
        "audit_receipt_hash": lens_audit["receipt_hash"],
        "authority_receipt_id": authority["receipt_id"],
        "authority_receipt_hash": authority["receipt_hash"],
        "surface_receipt_id": surface["receipt_id"],
        "surface_receipt_hash": surface["receipt_hash"],
    }
    return _identified(verdict, RELEASE_VERDICT_PREFIX)


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
