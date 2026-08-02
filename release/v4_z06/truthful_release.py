"""Terminal release, clean-extraction and truthful-maturity gate (Z06).

Z06 is the terminal package of the v4 A-Z graph.  Z05 sealed the zero-trust
release composition, and thirteen sealed ``*06`` integration gates each closed
their own layer.  Each is correct alone.  What none of them answers is the one
question the *bundle as a whole* turns on, the assertion MASTER_SPEC section 2
makes: this bundle **specifies** the v4 target architecture, canonical contracts,
workflows, plugin blueprint, migration, acceptance gates and A-Z implementation
graph, and it does **not** claim that a working v4 runtime, qualified evaluator,
hidden holdout, Shinka adapter, production database, sandbox, UI, security review
or 2,000-document deployment exists.  A terminal gate that certified completion
would be the exact overclaim the whole architecture is built to refuse.

So this gate proves the maturity is stated *honestly*, not that the product is
finished.  It is a composition gate: nothing is built, extracted, signed or
shipped here.  Three declared, fail-closed, deterministic gate families compose
already-sealed owners.

*Clean extraction.*  ``require_clean_extraction`` re-uses the sealed
release-provenance surface (composed through Z05, which requires the
``clean_extraction`` build check) and then proves a *declared* bundle manifest
extracts byte-identically: every member path is refused if it escapes the
extraction root (zip-slip — absolute, drive-qualified or ``..``-traversing), a
member whose extracted content hash does not match its declared digest is refused
as tampered, and the extracted member set must equal the declared set exactly so
neither a surplus nor a missing member can ride along.  No archive is written.

*Truthful maturity.*  ``require_truthful_maturity`` holds every declared source to
the acceptance-matrix floor: its release level must be exactly the floor the
matrix declares (read through the composed Z05 surface, never restated here),
``completion_ready`` must be false, and any maturity claim that presents the
bundle as executable, validated, production-ready, generally available, signed,
shippable or certified is refused with a typed finding.

*Independent release accounting.*  ``reconcile_release_accounting`` reconciles
that Z05 and the thirteen ``*06`` gates are each sealed PASS with completion not
claimed, that the expected and provided package sets match exactly (no missing and
no surplus package), and that every remaining conditional carries an owner.

``seal_truthful_release`` composes the sealed Z05 verdict — read from its **frozen
sealed report** rather than re-run, exactly as Z05 composed Z04 — with the three
families into one terminal verdict binding every sub-receipt by hash and refusing
any maturity overclaim.  Everything is deterministic: no clock, no randomness, the
caller supplies every identifier and timestamp, and two runs over equal inputs
produce byte-equal receipts.  ``completion_ready`` stays false in everything this
gate emits; the post-terminal closeout is not this gate's to make.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Mapping, Sequence

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload

from v4_z05.zero_trust_release import (
    UNSIGNED_STATUS,
    ZeroTrustReleaseError,
    reconciled_status_token,
    release_level_floor,
    require_unsigned_provenance,
)

#: Every way this terminal gate refuses, and why the refusal exists.  A refusal
#: whose code is absent here is a bug, not a decision, so ``_fail`` checks
#: membership and every code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would record "
        "a terminal release decision derived from something it never validated"
    ),
    "CLEAN_EXTRACTION_PROVENANCE_REFUSED": (
        "the composed release-provenance surface refused the bundle — a missing "
        "clean-extraction build check, a floating revision or a non-digest input — "
        "so the release cannot be described as clean-extractable at all"
    ),
    "BUNDLE_MEMBER_UNSAFE_PATH": (
        "a declared or extracted bundle member has a path that escapes the "
        "extraction root — absolute, drive-qualified or traversing with ``..`` — "
        "which is the zip-slip write-outside-root a clean extraction must refuse"
    ),
    "BUNDLE_MEMBER_TAMPERED": (
        "an extracted member's content hash does not match the digest the bundle "
        "manifest declares, so the extraction is not byte-identical to what was "
        "sealed and the member has been tampered with or corrupted"
    ),
    "BUNDLE_SURPLUS_MEMBER": (
        "the extraction produced a member the bundle manifest does not declare, so "
        "a surplus file would ride along in a bundle claimed to be clean"
    ),
    "BUNDLE_MISSING_MEMBER": (
        "the bundle manifest declares a member the extraction did not produce, so "
        "the extracted tree is not the sealed bundle it claims to reproduce"
    ),
    "MATURITY_LEVEL_ABOVE_FLOOR": (
        "a source declares a release level other than the acceptance-matrix floor, "
        "raising the maturity above what the canonical evidence supports for an "
        "unverified reference bundle"
    ),
    "SOURCE_CLAIMS_COMPLETION": (
        "a source declares completion_ready true, but the terminal gate proves the "
        "bundle is stated as incomplete and the post-terminal closeout is not made "
        "here"
    ),
    "FORBIDDEN_MATURITY_CLAIM": (
        "a source carries a maturity claim presenting the bundle as executable, "
        "validated, production-ready, generally available, signed, shippable or "
        "certified, which the honesty gate forbids for a specification bundle"
    ),
    "ACCOUNTING_PACKAGE_NOT_SEALED": (
        "a composed package is not sealed PASS, so the terminal release would be "
        "accounted over a layer that has not itself passed"
    ),
    "ACCOUNTING_PACKAGE_CLAIMS_COMPLETION": (
        "a composed package declares completion_ready true, which would let a layer "
        "smuggle a completion claim into the terminal accounting"
    ),
    "ACCOUNTING_MISSING_PACKAGE": (
        "an expected composed package is absent from the provided accounting, so the "
        "terminal reconciliation would pass over a layer it never checked"
    ),
    "ACCOUNTING_SURPLUS_PACKAGE": (
        "the accounting provides a package the expected composition does not name, "
        "so the reconciliation would silently admit an unaccounted layer"
    ),
    "ACCOUNTING_UNOWNED_CONDITIONAL": (
        "a remaining conditional in a composed package declares no owner, so a "
        "known open item would ship without anyone accountable for closing it"
    ),
    "TERMINAL_MATURITY_OVERCLAIM": (
        "the terminal verdict was asked to declare the bundle production-ready or "
        "complete, which the truthful-maturity gate forbids: this gate proves the "
        "maturity is stated honestly, it does not certify the product finished"
    ),
    "COMPOSED_Z05_NOT_SEALED": (
        "the composed frozen Z05 zero-trust release report is not sealed PASS, so "
        "the terminal gate cannot compose it as a passing release"
    ),
    "COMPOSED_Z05_CLAIMS_COMPLETION": (
        "the composed frozen Z05 report declares completion_ready true, which a "
        "zero-trust release never does; the terminal gate refuses to compose it"
    ),
}

#: Identifier prefixes.  Every identifier this gate mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
CLEAN_EXTRACTION_PREFIX = "ZCE-"
TRUTHFUL_MATURITY_PREFIX = "ZTM-"
RELEASE_ACCOUNTING_PREFIX = "ZRA-"
COMPOSED_Z05_PREFIX = "ZC5-"
TERMINAL_VERDICT_PREFIX = "ZTV-"

#: Maturity claims a specification bundle must never carry.  These are Z06's own
#: honesty vocabulary, not canonical wire enums: the schema-and-type suite proves
#: none of them collides with a canonical schema enum value, so holding them here
#: is not a duplicated wire literal (EF4-I22).  They are matched on token/phrase
#: boundaries so ``ga`` does not fire inside ``organization``.
FORBIDDEN_MATURITY_CLAIMS: frozenset[str] = frozenset(
    {
        "executable",
        "validated",
        "production-ready",
        "production ready",
        "generally available",
        "ga",
        "signed",
        "shippable",
        "certified",
    }
)


class TruthfulReleaseError(ValueError):
    """The terminal gate refuses a clean-extraction, maturity, accounting or seal."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise TruthfulReleaseError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise TruthfulReleaseError(code, message, context)


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


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a boolean", {"label": label})
    return bool(value)


def _identified(record: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record["receipt_id"] = prefix + sha256_of_payload(record)[len("sha256:") :]
    record["receipt_hash"] = hash_excluding(record, "receipt_hash")
    return record


@lru_cache(maxsize=1)
def _forbidden_claim_pattern() -> re.Pattern[str]:
    """One boundary-anchored pattern matching every forbidden maturity phrase.

    The phrases are escaped and joined longest-first so a multiword phrase wins
    over a bare token, and each is anchored on non-alphanumeric boundaries so a
    short token such as ``ga`` matches only when it stands alone.
    """
    phrases = sorted(FORBIDDEN_MATURITY_CLAIMS, key=len, reverse=True)
    body = "|".join(re.escape(phrase) for phrase in phrases)
    return re.compile(rf"(?<![a-z0-9])(?:{body})(?![a-z0-9])", re.IGNORECASE)


def _is_unsafe_member_path(path: str) -> bool:
    """Whether a member path would extract outside the bundle root.

    A safe member is a relative POSIX path with no ``..`` component and no drive
    or root anchor.  Backslashes are normalised to forward slashes first so a
    Windows-style ``..\\`` traversal or ``C:\\`` drive is caught the same way.
    """
    if not path or not path.strip():
        return True
    normalised = path.replace("\\", "/")
    if normalised.startswith("/"):
        return True
    # A drive-qualified head (``C:``) or any drive-relative segment escapes root.
    if re.match(r"^[A-Za-z]:", normalised):
        return True
    segments = normalised.split("/")
    return any(segment in ("..", "") for segment in segments)


def require_clean_extraction(
    *,
    bundle_id: str,
    provenance_inputs: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    extracted: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Prove a declared bundle clean-extracts, re-using the sealed provenance.

    The clean-extraction property is grounded twice.  First it is composed: the
    sealed release-provenance surface (through Z05) is asked to describe the
    bundle, which itself requires the ``clean_extraction`` build check to have
    passed; a surface that refuses fails closed here.  Then it is proven over a
    *declared* manifest: every declared and extracted member path is refused if it
    escapes the extraction root (zip-slip), each extracted member's content hash
    must match its declared digest (byte-identical, no tamper), and the extracted
    member set must equal the declared set (no surplus, no missing).  No archive is
    read or written.  The receipt is content-addressed and binds both the composed
    provenance hash and the bundle's own content digest.
    """
    identifier = _require_text(bundle_id, "bundle_id")
    try:
        provenance = require_unsigned_provenance(
            **_require_mapping(provenance_inputs, "provenance_inputs")
        )
    except ZeroTrustReleaseError as error:
        _fail(
            "CLEAN_EXTRACTION_PROVENANCE_REFUSED",
            f"the composed release-provenance surface refused the bundle: {error}",
            {"composed_code": error.code},
        )

    declared_rows = _require_sequence(members, "members")
    extracted_rows = _require_sequence(extracted, "extracted")

    declared: dict[str, str] = {}
    for index, entry in enumerate(declared_rows):
        row = _require_mapping(entry, f"members[{index}]")
        path = _require_text(row.get("path"), f"members[{index}].path")
        digest = _require_text(row.get("digest"), f"members[{index}].digest")
        if _is_unsafe_member_path(path):
            _fail(
                "BUNDLE_MEMBER_UNSAFE_PATH",
                "a declared bundle member escapes the extraction root",
                {"path": path},
            )
        declared[path] = digest

    observed: dict[str, str] = {}
    for index, entry in enumerate(extracted_rows):
        row = _require_mapping(entry, f"extracted[{index}]")
        path = _require_text(row.get("path"), f"extracted[{index}].path")
        content_hash = _require_text(
            row.get("content_hash"), f"extracted[{index}].content_hash"
        )
        if _is_unsafe_member_path(path):
            _fail(
                "BUNDLE_MEMBER_UNSAFE_PATH",
                "an extracted bundle member escapes the extraction root",
                {"path": path},
            )
        observed[path] = content_hash

    for path in sorted(declared):
        if path not in observed:
            _fail(
                "BUNDLE_MISSING_MEMBER",
                "the bundle declares a member the extraction did not produce",
                {"path": path},
            )
    for path in sorted(observed):
        if path not in declared:
            _fail(
                "BUNDLE_SURPLUS_MEMBER",
                "the extraction produced a member the bundle does not declare",
                {"path": path},
            )
    for path in sorted(declared):
        if observed[path] != declared[path]:
            _fail(
                "BUNDLE_MEMBER_TAMPERED",
                "an extracted member's content hash does not match its declared digest",
                {"path": path},
            )

    receipt: dict[str, Any] = {
        "bundle_id": identifier,
        "clean_extracted": True,
        "member_count": len(declared),
        "bundle_digest": sha256_of_payload(sorted(declared.items())),
        "provenance_receipt_hash": provenance["receipt_hash"],
        "signing_status": str(provenance["signing_status"]),
    }
    return _identified(receipt, CLEAN_EXTRACTION_PREFIX)


def require_truthful_maturity(
    *,
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Refuse any source that overstates the bundle's maturity.

    The floor is the maturity level the acceptance matrix declares, read through
    the composed Z05 surface rather than restated here, so a raised floor changes
    the seal instead of being silently duplicated.  Every source must sit exactly
    at the floor, must not declare completion, and must carry no claim presenting
    the bundle as executable, validated, production-ready, generally available,
    signed, shippable or certified.  The gate PASSES by proving the maturity is
    stated honestly.  The receipt is content-addressed.
    """
    rows = _require_sequence(sources, "sources")
    floor = release_level_floor()
    pattern = _forbidden_claim_pattern()

    summary: list[dict[str, Any]] = []
    for index, entry in enumerate(rows):
        source = _require_mapping(entry, f"sources[{index}]")
        source_id = _require_text(
            source.get("source_id"), f"sources[{index}].source_id"
        )
        level = _require_text(
            source.get("release_level"), f"sources[{index}].release_level"
        )
        if level != floor:
            _fail(
                "MATURITY_LEVEL_ABOVE_FLOOR",
                "a source declares a release level other than the acceptance floor",
                {"source_id": source_id, "release_level": level, "floor": floor},
            )
        completion = source.get("completion_ready")
        if completion is not False:
            _fail(
                "SOURCE_CLAIMS_COMPLETION",
                "a source declares completion_ready true",
                {"source_id": source_id, "completion_ready": completion},
            )
        claims = _require_sequence(source.get("claims", []), f"sources[{index}].claims")
        for claim_index, claim in enumerate(claims):
            text = _require_text(claim, f"sources[{index}].claims[{claim_index}]")
            match = pattern.search(text)
            if match:
                _fail(
                    "FORBIDDEN_MATURITY_CLAIM",
                    "a source carries a forbidden maturity claim",
                    {
                        "source_id": source_id,
                        "claim_text": text,
                        "matched": match.group(0),
                    },
                )
        summary.append(
            {
                "source_id": source_id,
                "release_level": level,
                "completion_ready": False,
                "claim_count": len(claims),
            }
        )

    receipt: dict[str, Any] = {
        "release_level": floor,
        "completion_ready": False,
        "source_count": len(summary),
        "sources": summary,
    }
    return _identified(receipt, TRUTHFUL_MATURITY_PREFIX)


def reconcile_release_accounting(
    *,
    expected_package_ids: Sequence[str],
    packages: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile that every composed package is sealed PASS without overclaim.

    The expected composition — Z05 and the thirteen ``*06`` gates — and the
    provided accounting must match exactly: an expected package absent from the
    accounting, or a provided package the composition does not name, each fails
    closed.  Every provided package must be sealed PASS (the passing token read
    through the composed Z05 surface), must not declare completion, and every
    remaining conditional it carries must name an owner.  The receipt is
    content-addressed and binds each package's report hash.
    """
    expected = {
        _require_text(pkg, "expected_package_ids[]")
        for pkg in _require_sequence(expected_package_ids, "expected_package_ids")
    }
    rows = _require_sequence(packages, "packages")
    pass_token = reconciled_status_token()

    summary: list[dict[str, Any]] = []
    provided: set[str] = set()
    for index, entry in enumerate(rows):
        package = _require_mapping(entry, f"packages[{index}]")
        package_id = _require_text(
            package.get("package_id"), f"packages[{index}].package_id"
        )
        status = _require_text(package.get("status"), f"packages[{index}].status")
        report_hash = _require_text(
            package.get("report_hash"), f"packages[{index}].report_hash"
        )
        if status != pass_token:
            _fail(
                "ACCOUNTING_PACKAGE_NOT_SEALED",
                "a composed package is not sealed PASS",
                {"package_id": package_id, "status": status},
            )
        completion = package.get("completion_ready")
        if completion is not False:
            _fail(
                "ACCOUNTING_PACKAGE_CLAIMS_COMPLETION",
                "a composed package declares completion_ready true",
                {"package_id": package_id, "completion_ready": completion},
            )
        conditionals = _require_sequence(
            package.get("conditionals", []), f"packages[{index}].conditionals"
        )
        for cond_index, conditional in enumerate(conditionals):
            row = _require_mapping(
                conditional, f"packages[{index}].conditionals[{cond_index}]"
            )
            owner = row.get("owner")
            if not isinstance(owner, str) or not owner.strip():
                _fail(
                    "ACCOUNTING_UNOWNED_CONDITIONAL",
                    "a remaining conditional declares no owner",
                    {"package_id": package_id, "conditional_entry": dict(row)},
                )
        provided.add(package_id)
        summary.append(
            {
                "package_id": package_id,
                "status": status,
                "completion_ready": False,
                "report_hash": report_hash,
                "conditional_count": len(conditionals),
            }
        )

    missing = sorted(expected - provided)
    if missing:
        _fail(
            "ACCOUNTING_MISSING_PACKAGE",
            "an expected composed package is absent from the accounting",
            {"missing": missing},
        )
    surplus = sorted(provided - expected)
    if surplus:
        _fail(
            "ACCOUNTING_SURPLUS_PACKAGE",
            "the accounting provides a package the composition does not name",
            {"surplus": surplus},
        )

    receipt: dict[str, Any] = {
        "expected_count": len(expected),
        "reconciled_count": len(summary),
        "all_sealed": True,
        "packages": sorted(summary, key=lambda item: item["package_id"]),
    }
    return _identified(receipt, RELEASE_ACCOUNTING_PREFIX)


def compose_sealed_z05(
    *,
    z05: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose the sealed Z05 zero-trust release from its frozen report facts.

    The Z05 live gate is repo-state dependent by design, so — exactly as Z05
    composed Z04 — this reads the *frozen sealed report* rather than re-running the
    gate.  The facts must show a passing release that does not claim completion; a
    report that is not PASS or that declares completion fails closed.  The receipt
    binds the report facts' own content hash so a regression that flipped Z05's
    status or completion flag changes the terminal verdict.
    """
    facts = _require_mapping(z05, "z05")
    status = _require_text(facts.get("status"), "z05.status")
    if status != reconciled_status_token():
        _fail(
            "COMPOSED_Z05_NOT_SEALED",
            "the composed frozen Z05 report is not sealed PASS",
            {"status": status, "expected": reconciled_status_token()},
        )
    completion = facts.get("completion_ready")
    if completion is not False:
        _fail(
            "COMPOSED_Z05_CLAIMS_COMPLETION",
            "the composed frozen Z05 report declares completion_ready true",
            {"completion_ready": completion},
        )

    receipt: dict[str, Any] = {
        "composed_package": _require_text(
            facts.get("work_package_id"), "z05.work_package_id"
        ),
        "status": status,
        "completion_ready": False,
        "z05_report_hash": sha256_of_payload(facts),
    }
    return _identified(receipt, COMPOSED_Z05_PREFIX)


def seal_truthful_release(
    *,
    release_id: str,
    z05: Mapping[str, Any],
    clean_extraction_inputs: Mapping[str, Any],
    maturity_sources: Sequence[Mapping[str, Any]],
    expected_package_ids: Sequence[str],
    accounting_packages: Sequence[Mapping[str, Any]],
    completion_ready: bool = False,
    production_ready: bool = False,
) -> dict[str, Any]:
    """Compose the terminal gate and seal one truthful-release verdict.

    The frozen Z05 release, the clean-extraction proof, the truthful-maturity
    proof and the independent release accounting each refuse independently; only
    when all four hold does this seal a terminal verdict.  Before sealing, the
    honesty floor is enforced: a verdict asked to declare the bundle
    production-ready or complete is refused, and the release level is fixed to the
    acceptance-matrix floor and the signing status to the composed fail-closed
    UNSIGNED, never a caller claim.  The verdict binds each sub-receipt by hash, so
    it cannot be forged without reproducing every gate it depends on, and it is
    content-addressed with no clock or random draw.  ``completion_ready`` stays
    false: the post-terminal closeout is not this gate's to make.
    """
    identifier = _require_text(release_id, "release_id")
    if _require_bool(completion_ready, "completion_ready"):
        _fail(
            "TERMINAL_MATURITY_OVERCLAIM",
            "a terminal release must not declare completion_ready true",
            {"completion_ready": completion_ready},
        )
    if _require_bool(production_ready, "production_ready"):
        _fail(
            "TERMINAL_MATURITY_OVERCLAIM",
            "a terminal release must not declare production_ready true",
            {"production_ready": production_ready},
        )

    composed_z05 = compose_sealed_z05(z05=z05)
    clean = require_clean_extraction(
        **_require_mapping(clean_extraction_inputs, "clean_extraction_inputs")
    )
    maturity = require_truthful_maturity(sources=maturity_sources)
    accounting = reconcile_release_accounting(
        expected_package_ids=expected_package_ids, packages=accounting_packages
    )

    verdict: dict[str, Any] = {
        "release_id": identifier,
        "terminal": True,
        "release_passed": True,
        "release_level": release_level_floor(),
        "signing_status": UNSIGNED_STATUS,
        "completion_ready": False,
        "production_ready": False,
        "z05_receipt_id": composed_z05["receipt_id"],
        "z05_receipt_hash": composed_z05["receipt_hash"],
        "clean_extraction_receipt_id": clean["receipt_id"],
        "clean_extraction_receipt_hash": clean["receipt_hash"],
        "maturity_receipt_id": maturity["receipt_id"],
        "maturity_receipt_hash": maturity["receipt_hash"],
        "accounting_receipt_id": accounting["receipt_id"],
        "accounting_receipt_hash": accounting["receipt_hash"],
    }
    return _identified(verdict, TERMINAL_VERDICT_PREFIX)


__all__ = [
    "CLEAN_EXTRACTION_PREFIX",
    "COMPOSED_Z05_PREFIX",
    "FINDING_CODES",
    "FORBIDDEN_MATURITY_CLAIMS",
    "RELEASE_ACCOUNTING_PREFIX",
    "TERMINAL_VERDICT_PREFIX",
    "TRUTHFUL_MATURITY_PREFIX",
    "TruthfulReleaseError",
    "compose_sealed_z05",
    "reconcile_release_accounting",
    "require_clean_extraction",
    "require_truthful_maturity",
    "seal_truthful_release",
]
