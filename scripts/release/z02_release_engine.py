"""Z02 SBOM, signing, provenance and deterministic-bundle engine.

This module is the single deterministic engine behind the three Z02 required
checks -- ``sbom_test``, ``signature_test`` and ``zip_integrity_test``.  It
operates over the in-repo plugin payload rooted at ``plugins/epistemic-foundry``
(the exact fresh-install payload that Z01 composed from the sealed ``G04-0001``
marketplace lifecycle) and produces, as pure functions:

* a content-addressed SBOM of every shipped payload file;
* a release-provenance record composed from the canonical runtime module
  :mod:`epistemic_foundry.release.provenance` and validated against the
  declaring schema ``schemas/plugin-release-provenance.schema.json``;
* a byte-deterministic ZIP bundle whose clean, path-safe extraction is verified
  byte-for-byte against the payload.

Honesty boundary
----------------
Signing and provenance are modelled as a DECLARED, fail-closed construction,
not a real cryptographic release.  The four reproducible-build checks
(``reproducible_build``, ``sbom_generated``, ``manifest_complete``,
``clean_extraction``) are genuinely verified facts about the in-repo payload, so
the provenance record is honestly *describable*; but the signature list is empty,
so the canonical ``derive_signing_status`` returns ``UNSIGNED`` and the bundle is
*not shippable*.  Nothing here fabricates a signature, spawns a signing service,
or claims the v4 plugin is executable, validated or production-ready.  The one
real single-host install lifecycle remains sealed as ``G04-0001`` and is not
duplicated here.

Determinism
-----------
The engine contains no clock and no randomness.  Every record embeds a
caller-supplied ``generated_at`` timestamp and is hash-re-derivable through
:func:`record_sha256`; the ZIP is written with ``ZIP_STORED``, a fixed member
date and fixed permission bits, so re-running any builder with the same payload
and timestamp yields byte-identical bytes and hashes.  Refusals are typed codes
whose human-readable reason is always longer than fifty characters.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import yaml

from epistemic_foundry.release import provenance as canonical_provenance

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "epistemic-foundry"
PLUGIN_MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
MATRIX_PATH = REPO_ROOT / "manifests" / "compatibility_matrix.yaml"
PROVENANCE_SCHEMA = "schemas/plugin-release-provenance.schema.json"
RELEASE_WORKFLOW = "workflows/plugin_release.workflow.yaml"

#: Fixed DOS epoch used for every ZIP member so the archive carries no clock.
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

#: Fixed POSIX permission bits (``rw-r--r--``) stamped on every ZIP member so the
#: external attributes do not vary with the host umask.
FIXED_ZIP_MODE = 0o644

#: Declared, non-cryptographic builder identity for the reference construction.
BUILDER_IDENTITY = "epistemic-foundry-z02-reference-builder"

# Typed refusal codes -> reason builders.  Every reason is > 50 characters so a
# refused decision always carries an auditable, human-readable justification.
REFUSAL_REASONS: dict[str, str] = {
    "EF_Z02_SBOM_COMPONENT_MISSING": (
        "SBOM omits a payload file that is actually shipped, so the bill of materials "
        "under-represents the bundle and the completeness gate is refused fail-closed"
    ),
    "EF_Z02_SBOM_COMPONENT_EXTRA": (
        "SBOM lists a component that is absent from the shipped payload, so the bill of "
        "materials over-represents the bundle and the completeness gate is refused"
    ),
    "EF_Z02_SBOM_HASH_MISMATCH": (
        "SBOM component digest does not match the shipped payload file bytes, so the "
        "recorded bill of materials is stale or tampered and the gate is refused"
    ),
    "EF_Z02_SIGNATURE_OVERCLAIM": (
        "claimed signing status is stronger than the status derived from the signatures "
        "actually present, so an unsigned or invalid bundle would be labelled signed"
    ),
    "EF_Z02_PROVENANCE_NOT_REDERIVABLE": (
        "recorded provenance hash does not re-derive from the record contents, so the "
        "provenance document is not reproducible and cannot be trusted for verification"
    ),
    "EF_Z02_BUNDLE_PATH_UNSAFE": (
        "bundle member escapes the extraction root via an absolute path or parent "
        "traversal, so extracting it would overwrite files outside the target directory"
    ),
    "EF_Z02_BUNDLE_EXTRACT_MISMATCH": (
        "clean extraction of the bundle does not reproduce the payload bytes exactly, so "
        "the archive does not faithfully carry the declared payload and is refused"
    ),
    "EF_Z02_BUNDLE_NONDETERMINISTIC": (
        "re-building the bundle from the same payload yields different bytes, so the "
        "archive is not reproducible and its bundle hash cannot pin a fixed artifact"
    ),
}


def refusal(code: str, **extra: Any) -> dict[str, Any]:
    """Return a typed refusal object with a > 50 character reason."""

    reason = REFUSAL_REASONS[code]
    assert len(reason) > 50, f"refusal reason for {code} is too short"
    return {"code": code, "reason": reason, **extra}


def canonical_json(record: object) -> str:
    """Canonical JSON serialization used for hashing (matches Z01/kernel)."""

    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_sha256(record: object) -> str:
    """Canonical, hash-re-derivable digest of a structured record."""

    return (
        "sha256:" + hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    )


def digest_bytes(data: bytes) -> str:
    """Content-addressed digest of raw bytes in schema ``sha256:`` form."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    assert isinstance(value, dict), f"{path} is not an object"
    return value


def load_matrix() -> dict:
    with MATRIX_PATH.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    assert isinstance(value, dict), f"{MATRIX_PATH} is not a mapping"
    return value


def plugin_identity() -> dict[str, str]:
    """Plugin id and version taken from the payload manifest, cross-checked.

    The version must agree between the payload manifest and the declaring
    compatibility matrix; a disagreement means the payload and the release
    contract describe different artifacts.
    """

    manifest = load_json(PLUGIN_MANIFEST_PATH)
    matrix = load_matrix()
    assert manifest["name"] == matrix["plugin"]["name"], "plugin name mismatch"
    assert manifest["version"] == matrix["version"], "plugin version mismatch"
    return {"plugin_id": str(manifest["name"]), "version": str(manifest["version"])}


def payload_inventory() -> list[dict[str, Any]]:
    """Deterministic content-addressed inventory of the declared payload.

    Files are hashed by bytes only and sorted by POSIX path, so the inventory is
    stable across runs and hosts.
    """

    entries = []
    for path in sorted(
        (p for p in PLUGIN_ROOT.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(PLUGIN_ROOT).as_posix(),
    ):
        data = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(PLUGIN_ROOT).as_posix(),
                "byte_size": len(data),
                "sha256": digest_bytes(data),
            }
        )
    return entries


def payload_content_hash() -> str:
    """Single content-address over the whole payload inventory."""

    return record_sha256(payload_inventory())


def manifest_hash() -> str:
    """Digest of the raw plugin manifest bytes."""

    return digest_bytes(PLUGIN_MANIFEST_PATH.read_bytes())


def builder_environment_hash() -> str:
    """Digest of a DECLARED reference build environment descriptor.

    No real toolchain fingerprint is captured; this is a fixed, honest
    description of the reference construction so the provenance record carries a
    stable, non-cryptographic environment digest.
    """

    descriptor = {
        "kind": "declared_reference_environment",
        "builder": BUILDER_IDENTITY,
        "note": (
            "Deterministic reference build over the in-repo payload; no real "
            "toolchain or host fingerprint is captured."
        ),
        "payload_root": "plugins/epistemic-foundry",
    }
    return record_sha256(descriptor)


# --------------------------------------------------------------------------- #
# SBOM
# --------------------------------------------------------------------------- #
def build_sbom(*, generated_at: str) -> dict[str, Any]:
    """Build a deterministic, content-addressed SBOM over the payload.

    The SBOM lists every shipped payload file as a component with its byte size
    and digest.  It is a reference bill of materials (there is no canonical SBOM
    schema in the repository); the provenance record, which *is* schema-governed,
    pins this SBOM by its digest.
    """

    inventory = payload_inventory()
    identity = plugin_identity()
    sbom: dict[str, Any] = {
        "schema_version": "z02-sbom/v1",
        "bom_format": "epistemic-foundry-payload-sbom",
        "work_package_id": "Z02",
        "sbom_status": "UNVERIFIED_REFERENCE_SBOM",
        "generated_at": generated_at,
        "declaring_source": PROVENANCE_SCHEMA,
        "subject": {
            "plugin_id": identity["plugin_id"],
            "version": identity["version"],
            "payload_root": "plugins/epistemic-foundry",
        },
        "components": inventory,
        "component_count": len(inventory),
        "payload_content_hash": record_sha256(inventory),
        "honesty_note": (
            "Reference bill of materials over the in-repo payload; not a scan of "
            "external dependencies and not a signed attestation."
        ),
    }
    sbom["sbom_sha256"] = record_sha256(
        {k: v for k, v in sbom.items() if k != "sbom_sha256"}
    )
    return sbom


def sbom_completeness_report(sbom: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed diff of a SBOM against the live payload.

    Refuses when the SBOM omits a shipped file, lists an absent one, or records a
    digest that does not match the file bytes.  The check is genuine: it hashes
    the payload again rather than trusting the SBOM's own digests.
    """

    live = {entry["path"]: entry["sha256"] for entry in payload_inventory()}
    listed = {
        str(component["path"]): str(component["sha256"])
        for component in sbom.get("components", [])
    }
    missing = sorted(set(live) - set(listed))
    extra = sorted(set(listed) - set(live))
    mismatched = sorted(
        path for path in set(live) & set(listed) if live[path] != listed[path]
    )
    refusals = []
    if missing:
        refusals.append(refusal("EF_Z02_SBOM_COMPONENT_MISSING", paths=missing))
    if extra:
        refusals.append(refusal("EF_Z02_SBOM_COMPONENT_EXTRA", paths=extra))
    if mismatched:
        refusals.append(refusal("EF_Z02_SBOM_HASH_MISMATCH", paths=mismatched))
    return {
        "component_count": len(listed),
        "payload_file_count": len(live),
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "refusals": refusals,
        "complete": not refusals,
    }


# --------------------------------------------------------------------------- #
# Deterministic bundle
# --------------------------------------------------------------------------- #
def build_bundle_bytes() -> bytes:
    """Build a byte-deterministic ZIP archive of the payload.

    ``ZIP_STORED`` (no compression), a fixed member date and fixed permission
    bits make the archive reproducible: identical payload bytes yield identical
    archive bytes and therefore an identical bundle hash.
    """

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in payload_inventory():
            info = zipfile.ZipInfo(filename=entry["path"], date_time=FIXED_ZIP_DATE)
            info.external_attr = FIXED_ZIP_MODE << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, (PLUGIN_ROOT / entry["path"]).read_bytes())
    return buffer.getvalue()


def bundle_hash() -> str:
    """Content-address of the deterministic bundle bytes."""

    return digest_bytes(build_bundle_bytes())


def is_safe_member(name: str) -> bool:
    """True only for a relative member path that stays inside the extract root."""

    if not name or name.endswith("/"):
        return bool(name) and not name.startswith("/")
    if "\\" in name or ":" in name:
        return False
    pure = PurePosixPath(name)
    if pure.is_absolute():
        return False
    return not any(part == ".." for part in pure.parts)


def verify_clean_extraction(bundle_bytes: bytes, destination: Path) -> dict[str, Any]:
    """Extract the bundle path-safely and prove byte-identity with the payload.

    Every member is checked for path safety *before* extraction, so an unsafe
    archive is refused rather than written outside the destination.  After a safe
    extraction the extracted tree is compared byte-for-byte with the payload.
    """

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
        names = archive.namelist()
        unsafe = sorted(name for name in names if not is_safe_member(name))
        if unsafe:
            return {
                "clean_extract": False,
                "member_count": len(names),
                "refusals": [refusal("EF_Z02_BUNDLE_PATH_UNSAFE", members=unsafe)],
            }
        archive.extractall(destination)

    inventory = payload_inventory()
    mismatched = []
    for entry in inventory:
        extracted = destination / entry["path"]
        if (
            not extracted.is_file()
            or digest_bytes(extracted.read_bytes()) != entry["sha256"]
        ):
            mismatched.append(entry["path"])
    extracted_files = sorted(
        p.relative_to(destination).as_posix()
        for p in destination.rglob("*")
        if p.is_file()
    )
    declared_files = sorted(entry["path"] for entry in inventory)
    surplus = sorted(set(extracted_files) - set(declared_files))
    refusals = []
    if mismatched or surplus:
        refusals.append(
            refusal(
                "EF_Z02_BUNDLE_EXTRACT_MISMATCH",
                mismatched=mismatched,
                surplus=surplus,
            )
        )
    return {
        "clean_extract": not refusals,
        "member_count": len(inventory),
        "mismatched": mismatched,
        "surplus": surplus,
        "refusals": refusals,
    }


def bundle_is_deterministic() -> bool:
    """True when two independent builds of the bundle are byte-identical."""

    return build_bundle_bytes() == build_bundle_bytes()


# --------------------------------------------------------------------------- #
# Provenance + signing (composed from the canonical runtime module)
# --------------------------------------------------------------------------- #
def _build_check(check_id: str, status: str, details: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "details": details,
        "remediation": [],
    }


def reproducible_build_checks(sbom: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The four EF4-I32 build checks as genuinely-verified facts.

    Each status reflects a real deterministic property of the in-repo payload:
    the bundle re-builds byte-identically, the SBOM was generated over the
    payload, the manifest and expected top-level agree, and the bundle
    clean-extracts to the payload bytes.
    """

    import tempfile

    matrix = load_matrix()
    declared_top = sorted(matrix["payload"]["expected_top_level"])
    actual_top = sorted(child.name for child in PLUGIN_ROOT.iterdir())
    completeness = sbom_completeness_report(sbom)
    with tempfile.TemporaryDirectory() as tmp:
        extraction = verify_clean_extraction(build_bundle_bytes(), Path(tmp))
    return [
        _build_check(
            "reproducible_build",
            "PASS" if bundle_is_deterministic() else "FAIL",
            "two independent ZIP_STORED builds compared byte-for-byte",
        ),
        _build_check(
            "sbom_generated",
            "PASS" if completeness["complete"] else "FAIL",
            "content-addressed SBOM covers every shipped payload file",
        ),
        _build_check(
            "manifest_complete",
            "PASS" if declared_top == actual_top else "FAIL",
            "payload top-level matches the declared compatibility matrix",
        ),
        _build_check(
            "clean_extraction",
            "PASS" if extraction["clean_extract"] else "FAIL",
            "deterministic bundle extracts to the payload bytes exactly",
        ),
    ]


def build_provenance(
    *,
    generated_at: str,
    sbom: Mapping[str, Any],
    signatures: Sequence[Mapping[str, Any]] = (),
    release_id: str = "REL-Z02-REFERENCE",
) -> dict[str, Any]:
    """Compose the canonical release-provenance record for the reference bundle.

    Delegates to :func:`epistemic_foundry.release.provenance.build_release_provenance`
    so the record is validated against the declaring schema and its signing status
    is *derived* from the signatures rather than asserted.  The source revision is
    content-addressed to the payload, so it is exact and never floating.
    """

    identity = plugin_identity()
    return canonical_provenance.build_release_provenance(
        plugin_id=identity["plugin_id"],
        version=identity["version"],
        source_revision=payload_content_hash(),
        source_hash=payload_content_hash(),
        bundle_hash=bundle_hash(),
        sbom_hash=str(sbom["sbom_sha256"]),
        manifest_hash=manifest_hash(),
        builder_identity=BUILDER_IDENTITY,
        builder_environment_hash=builder_environment_hash(),
        checks=reproducible_build_checks(sbom),
        signatures=list(signatures),
        release_id=release_id,
        created_at=generated_at,
    )


def signing_status_of(provenance: Mapping[str, Any]) -> str:
    """Derived signing status (delegates to the canonical derivation)."""

    return canonical_provenance.signing_status_of(provenance)


def verify_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed verification that a provenance record re-derives its hash.

    Re-computes the provenance hash from the record contents; a mismatch means
    the record is not reproducible and is refused.
    """

    from epistemic_foundry.domain.hashing import hash_excluding

    recomputed = hash_excluding(dict(provenance), "provenance_hash")
    matches = recomputed == provenance.get("provenance_hash")
    refusals = []
    if not matches:
        refusals.append(refusal("EF_Z02_PROVENANCE_NOT_REDERIVABLE"))
    return {
        "provenance_hash": provenance.get("provenance_hash"),
        "recomputed_hash": recomputed,
        "rederivable": matches,
        "signing_status": signing_status_of(provenance),
        "shippable": canonical_provenance.release_is_shippable(provenance),
        "refusals": refusals,
    }


def attest_signing_status(
    provenance: Mapping[str, Any], *, claimed_status: str
) -> dict[str, Any]:
    """Refuse any signing claim stronger than the derived status.

    The derivation is the authority; a caller cannot label an ``UNSIGNED`` or
    ``INVALID`` bundle as ``SIGNED``.  This is the fail-closed guard behind
    "unsigned build not labeled signed".
    """

    derived = signing_status_of(provenance)
    refusals = []
    if claimed_status != derived:
        refusals.append(
            refusal(
                "EF_Z02_SIGNATURE_OVERCLAIM",
                claimed_status=claimed_status,
                derived_status=derived,
            )
        )
    return {
        "claimed_status": claimed_status,
        "derived_status": derived,
        "honest": not refusals,
        "refusals": refusals,
    }
