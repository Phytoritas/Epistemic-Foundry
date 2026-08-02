"""Explicit legacy ``DocumentManifest`` to v4 registration migration.

The pre-registration manifest alone is insufficient to reconstruct the new
``DocumentRegistrationRequest`` and ``DocumentRegistration`` artifacts.  This
entry point therefore accepts a separately sealed canonical request and a
closed immutable-evidence bundle.  It never discovers bytes, invents receipts,
or treats final-manifest metadata as proof of an earlier registration effect.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from epistemic_foundry.domain.hashing import (
    hash_excluding,
    is_schema_digest,
    sha256_of_payload,
)


LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED = (
    "LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED"
)

DOCUMENT_REGISTRATION_REQUEST_SCHEMA_ID = (
    "https://epistemic-foundry.local/schemas/"
    "document-registration-request.schema.json"
)
DOCUMENT_REGISTRATION_SCHEMA_ID = (
    "https://epistemic-foundry.local/schemas/document-registration.schema.json"
)

REQUEST_HASH_FIELDS = (
    "workspace_id",
    "corpus_id",
    "staged_source_artifact_id",
    "declared_filename",
    "declared_media_type",
    "source_origin",
    "declared_license_status",
    "access_policy_ref",
    "confidentiality",
    "external_identifier_hints",
    "supersedes_registration_id",
    "idempotency_key",
)

REQUEST_FIELDS = frozenset(
    (*REQUEST_HASH_FIELDS, "request_id", "requested_at", "request_hash")
)

SOURCE_ORIGIN_FIELDS = frozenset(
    {"kind", "original_uri", "source_system", "retrieved_at"}
)
EXTERNAL_IDENTIFIER_HINT_FIELDS = frozenset(
    {"scheme", "value", "declared_by", "verified"}
)
SOURCE_ORIGIN_KINDS = frozenset(
    {"UPLOAD", "LOCAL_IMPORT", "REMOTE_FETCH", "EXISTING_ARTIFACT"}
)
EXTERNAL_IDENTIFIER_SCHEMES = frozenset(
    {"DOI", "PMID", "PMCID", "ARXIV", "ISBN", "URL", "OTHER"}
)
LICENSE_STATUSES = frozenset(
    {"licensed", "open_access", "fair_use_metadata_only", "restricted", "unknown"}
)
CONFIDENTIALITY_LEVELS = frozenset(
    {"public", "internal", "restricted", "secret"}
)
MEDIA_TYPE_PATTERN = re.compile(r"^[^\s/]+/[^\s/]+$")
REGISTRATION_ID_PATTERN = re.compile(r"^DREG-[0-9a-f]{64}$")
URI_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")

REGISTRATION_HASH_FIELDS = (
    "schema_id",
    "schema_version",
    "workspace_id",
    "corpus_id",
    "source_blob_artifact_id",
    "source_content_hash",
    "byte_size",
    "detected_media_type",
    "original_filename",
    "source_origin",
    "license_status",
    "access_policy_ref",
    "confidentiality",
    "external_identifier_hints",
    "supersedes_registration_id",
    "initial_state",
    "submitted_by_principal_id",
    "request_hash",
    "idempotency_key",
)

LEGACY_DOCUMENT_MANIFEST_FIELDS = frozenset(
    {
        "document_id",
        "paper_id",
        "paper_version_id",
        "content_hash",
        "original_filename",
        "media_type",
        "source_uri",
        "doi",
        "bibliographic_version",
        "supersedes_version_id",
        "status",
        "license_status",
        "access_policy_ref",
        "parser_artifact_ids",
        "source_integrity_report_id",
        "malware_scan_status",
        "prompt_injection_scan_status",
        "ingested_at",
        "provenance_manifest_id",
    }
)

EVIDENCE_FIELDS = frozenset(
    {
        "source_blob_artifact_id",
        "source_content_hash",
        "byte_size",
        "detected_media_type",
        "original_filename",
        "submitted_by_principal_id",
        "action_intent_id",
        "source_effect_receipt_id",
        "source_artifact_receipt_id",
        "registration_artifact_receipt_id",
        "registration_ledger_event_id",
        "manifest_finalized_event_id",
        "registered_at",
        "supersedes_document_manifest_id",
        "immutable_evidence_ids",
    }
)


class LegacyDocumentRegistrationEvidenceRequired(ValueError):
    """Raised when immutable historical registration evidence is incomplete."""

    code = LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


def _fail(detail: str) -> None:
    raise LegacyDocumentRegistrationEvidenceRequired(detail)


def _plain_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an explicit mapping")
    return copy.deepcopy(dict(value))


def _closed_fields(
    payload: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = set(payload)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        _fail(f"{label} field mismatch; missing={missing}, extra={extra}")


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty string")
    return value


def _utc_timestamp(value: object, label: str) -> str:
    timestamp = _nonempty_text(value, label)
    if not timestamp.endswith("Z"):
        _fail(f"{label} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError:
        _fail(f"{label} must be a valid RFC 3339 UTC timestamp")
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        _fail(f"{label} must resolve to UTC")
    return timestamp


def _enum(value: object, allowed: frozenset[str], label: str) -> str:
    text = _nonempty_text(value, label)
    if text not in allowed:
        _fail(f"{label} is outside the canonical vocabulary")
    return text


def _filename(value: object, label: str) -> str:
    filename = _nonempty_text(value, label)
    if (
        "/" in filename
        or "\\" in filename
        or re.match(r"^[A-Za-z]:", filename)
        or filename in {".", ".."}
    ):
        _fail(f"{label} must be a basename without a local or relative path")
    return filename


def _media_type(value: object, label: str) -> str:
    media_type = _nonempty_text(value, label)
    if not MEDIA_TYPE_PATTERN.fullmatch(media_type):
        _fail(f"{label} must be a canonical media type")
    return media_type


def _optional_uri(value: object, label: str) -> str | None:
    if value is None:
        return None
    uri = _nonempty_text(value, label)
    if any(character.isspace() for character in uri):
        _fail(f"{label} must not contain whitespace")
    parsed = urlsplit(uri)
    if (
        not parsed.scheme
        or not URI_SCHEME_PATTERN.fullmatch(parsed.scheme)
        or parsed.scheme.lower() == "file"
    ):
        _fail(f"{label} must be a non-file absolute URI")
    return uri


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _nonempty_text(value, label)


def _verify_source_origin(value: object) -> None:
    origin = _plain_mapping(value, "DocumentRegistrationRequest source_origin")
    _closed_fields(origin, SOURCE_ORIGIN_FIELDS, "source_origin")
    _enum(origin.get("kind"), SOURCE_ORIGIN_KINDS, "source_origin kind")
    _optional_uri(origin.get("original_uri"), "source_origin original_uri")
    _optional_text(origin.get("source_system"), "source_origin source_system")
    retrieved_at = origin.get("retrieved_at")
    if retrieved_at is not None:
        _utc_timestamp(retrieved_at, "source_origin retrieved_at")


def _verify_external_identifier_hints(value: object) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("external_identifier_hints must be an array")
    fingerprints: set[str] = set()
    for index, raw_hint in enumerate(value):
        hint = _plain_mapping(raw_hint, f"external_identifier_hints[{index}]")
        _closed_fields(
            hint,
            EXTERNAL_IDENTIFIER_HINT_FIELDS,
            f"external_identifier_hints[{index}]",
        )
        _enum(
            hint.get("scheme"),
            EXTERNAL_IDENTIFIER_SCHEMES,
            f"external_identifier_hints[{index}] scheme",
        )
        _nonempty_text(
            hint.get("value"), f"external_identifier_hints[{index}] value"
        )
        _nonempty_text(
            hint.get("declared_by"),
            f"external_identifier_hints[{index}] declared_by",
        )
        if hint.get("verified") is not False:
            _fail(f"external_identifier_hints[{index}] verified must be false")
        fingerprint = sha256_of_payload(hint)
        if fingerprint in fingerprints:
            _fail("external_identifier_hints must contain unique items")
        fingerprints.add(fingerprint)


def _verify_request(request: Mapping[str, Any]) -> None:
    _closed_fields(request, REQUEST_FIELDS, "DocumentRegistrationRequest")
    for field in (
        "workspace_id",
        "corpus_id",
        "staged_source_artifact_id",
        "access_policy_ref",
        "idempotency_key",
    ):
        _nonempty_text(request.get(field), f"DocumentRegistrationRequest {field}")
    _filename(request.get("declared_filename"), "declared_filename")
    _media_type(request.get("declared_media_type"), "declared_media_type")
    _verify_source_origin(request.get("source_origin"))
    _enum(
        request.get("declared_license_status"),
        LICENSE_STATUSES,
        "declared_license_status",
    )
    _enum(
        request.get("confidentiality"),
        CONFIDENTIALITY_LEVELS,
        "confidentiality",
    )
    _verify_external_identifier_hints(request.get("external_identifier_hints"))
    supersedes = request.get("supersedes_registration_id")
    if supersedes is not None and (
        not isinstance(supersedes, str)
        or not REGISTRATION_ID_PATTERN.fullmatch(supersedes)
    ):
        _fail("supersedes_registration_id must be null or a canonical DREG ID")
    expected_hash = sha256_of_payload(
        {field: request[field] for field in REQUEST_HASH_FIELDS}
    )
    if request.get("request_hash") != expected_hash:
        _fail("DocumentRegistrationRequest request_hash mismatch")
    if request.get("request_id") != "DREQ-" + expected_hash.removeprefix("sha256:"):
        _fail("DocumentRegistrationRequest request_id is not hash-bound")
    _utc_timestamp(request.get("requested_at"), "DocumentRegistrationRequest requested_at")


def _evidence_ids(evidence: Mapping[str, Any]) -> list[str]:
    raw = evidence.get("immutable_evidence_ids")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        _fail("immutable_evidence_ids must be a non-empty sequence")
    values = [_nonempty_text(value, "immutable evidence ID") for value in raw]
    if not values or len(values) != len(set(values)):
        _fail("immutable_evidence_ids must be non-empty and unique")
    required_bindings = {
        _nonempty_text(evidence[field], field)
        for field in (
            "source_blob_artifact_id",
            "action_intent_id",
            "source_effect_receipt_id",
            "source_artifact_receipt_id",
            "registration_artifact_receipt_id",
            "registration_ledger_event_id",
            "manifest_finalized_event_id",
        )
    }
    absent = sorted(required_bindings - set(values))
    if absent:
        _fail(f"immutable evidence does not bind required artifacts/receipts: {absent}")
    return values


def _build_registration(
    request: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    registration: dict[str, Any] = {
        "registration_id": "",
        "schema_version": "4.0.0",
        "workspace_id": request["workspace_id"],
        "corpus_id": request["corpus_id"],
        "source_blob_artifact_id": evidence["source_blob_artifact_id"],
        "source_content_hash": evidence["source_content_hash"],
        "byte_size": evidence["byte_size"],
        "detected_media_type": evidence["detected_media_type"],
        "original_filename": evidence["original_filename"],
        "source_origin": copy.deepcopy(request["source_origin"]),
        "license_status": request["declared_license_status"],
        "access_policy_ref": request["access_policy_ref"],
        "confidentiality": request["confidentiality"],
        "external_identifier_hints": copy.deepcopy(
            request["external_identifier_hints"]
        ),
        "supersedes_registration_id": request["supersedes_registration_id"],
        "initial_state": "REGISTERED_UNSCREENED",
        "submitted_by_principal_id": evidence["submitted_by_principal_id"],
        "request_id": request["request_id"],
        "request_hash": request["request_hash"],
        "idempotency_key": request["idempotency_key"],
        "action_intent_id": evidence["action_intent_id"],
        "source_effect_receipt_id": evidence["source_effect_receipt_id"],
        "source_artifact_receipt_id": evidence["source_artifact_receipt_id"],
        "registration_artifact_receipt_id": evidence[
            "registration_artifact_receipt_id"
        ],
        "ledger_event_id": evidence["registration_ledger_event_id"],
        "registered_at": evidence["registered_at"],
        "registration_hash": "",
    }
    preimage = {
        field: (
            DOCUMENT_REGISTRATION_SCHEMA_ID
            if field == "schema_id"
            else registration[field]
        )
        for field in REGISTRATION_HASH_FIELDS
    }
    registration_hash = sha256_of_payload(preimage)
    registration["registration_hash"] = registration_hash
    registration["registration_id"] = "DREG-" + registration_hash.removeprefix(
        "sha256:"
    )
    return registration


def migrate_legacy_document_manifest(
    legacy_manifest: Mapping[str, Any],
    *,
    registration_request: Mapping[str, Any] | None,
    immutable_registration_evidence: Mapping[str, Any] | None,
    migration_id: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Create v4 registration lineage only from explicit immutable evidence.

    No field is inferred from the current environment.  The source manifest is
    retained byte-semantically through a source hash, while the target manifest
    is a new object containing the canonical registration lineage fields.
    """
    legacy = _plain_mapping(legacy_manifest, "legacy DocumentManifest")
    _closed_fields(legacy, LEGACY_DOCUMENT_MANIFEST_FIELDS, "legacy DocumentManifest")
    request = _plain_mapping(registration_request, "DocumentRegistrationRequest")
    evidence = _plain_mapping(
        immutable_registration_evidence, "immutable registration evidence"
    )
    _closed_fields(evidence, EVIDENCE_FIELDS, "immutable registration evidence")
    _verify_request(request)
    evidence_ids = _evidence_ids(evidence)
    _nonempty_text(migration_id, "migration_id")
    _utc_timestamp(recorded_at, "recorded_at")

    if not is_schema_digest(evidence.get("source_content_hash")):
        _fail("source_content_hash must be a canonical sha256 digest")
    _filename(evidence.get("original_filename"), "evidence original_filename")
    _media_type(evidence.get("detected_media_type"), "evidence detected_media_type")
    _nonempty_text(evidence.get("submitted_by_principal_id"), "submitted principal")
    _utc_timestamp(evidence.get("registered_at"), "registered_at")
    supersedes_manifest = evidence.get("supersedes_document_manifest_id")
    if supersedes_manifest is not None:
        _nonempty_text(supersedes_manifest, "supersedes_document_manifest_id")

    if evidence.get("source_content_hash") != legacy.get("content_hash"):
        _fail("source content hash does not match the legacy manifest")
    if evidence.get("detected_media_type") != legacy.get("media_type"):
        _fail("detected media type does not match the legacy manifest")
    if evidence.get("original_filename") != legacy.get("original_filename"):
        _fail("original filename does not match the legacy manifest")
    if not isinstance(evidence.get("byte_size"), int) or evidence["byte_size"] < 0:
        _fail("byte_size must be a non-negative integer proven by source evidence")

    registration = _build_registration(request, evidence)
    migrated_manifest = {
        "registration_id": registration["registration_id"],
        "registration_hash": registration["registration_hash"],
        "source_blob_artifact_id": registration["source_blob_artifact_id"],
        "source_artifact_receipt_id": registration[
            "source_artifact_receipt_id"
        ],
        "registration_artifact_receipt_id": registration[
            "registration_artifact_receipt_id"
        ],
        "derived_from_registration_id": registration["registration_id"],
        "supersedes_document_manifest_id": evidence[
            "supersedes_document_manifest_id"
        ],
        "lineage_event_ids": [
            evidence["registration_ledger_event_id"],
            evidence["manifest_finalized_event_id"],
        ],
        **copy.deepcopy(legacy),
    }
    if len(set(migrated_manifest["lineage_event_ids"])) != 2:
        _fail("registration and final-manifest lineage events must be distinct")

    migration_record: dict[str, Any] = {
        "record_type": "DocumentRegistrationMigrationRecord",
        "migration_id": migration_id,
        "source_schema_version": "3.0.0",
        "target_schema_version": "4.0.0",
        "source_document_id": legacy["document_id"],
        "source_manifest_hash": sha256_of_payload(legacy),
        "target_request_id": request["request_id"],
        "target_request_hash": request["request_hash"],
        "target_registration_id": registration["registration_id"],
        "target_registration_hash": registration["registration_hash"],
        "target_manifest_hash": sha256_of_payload(migrated_manifest),
        "immutable_evidence_ids": evidence_ids,
        "resolution_status": "RESOLVED",
        "failure_code": None,
        "recorded_at": recorded_at,
    }
    migration_record["migration_hash"] = hash_excluding(
        migration_record, "migration_hash"
    )
    return {
        "document_registration_request": copy.deepcopy(request),
        "document_registration": registration,
        "document_manifest": migrated_manifest,
        "migration_record": migration_record,
    }


def rollback_legacy_document_manifest(
    migration_result: Mapping[str, Any], legacy_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the exact legacy payload only when its source hash still matches."""
    result = _plain_mapping(migration_result, "migration result")
    record = result.get("migration_record")
    if not isinstance(record, Mapping):
        _fail("migration result has no DocumentRegistrationMigrationRecord")
    legacy = _plain_mapping(legacy_manifest, "legacy DocumentManifest")
    if record.get("record_type") != "DocumentRegistrationMigrationRecord":
        _fail("migration result has the wrong MigrationRecord type")
    if record.get("source_manifest_hash") != sha256_of_payload(legacy):
        _fail("rollback source does not match the MigrationRecord source hash")
    return legacy
