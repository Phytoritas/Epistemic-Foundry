"""Canonical request and registration hashing for K01.

The two artifact schemas define their hash preimages.  This module is the
runtime implementation of those tables; volatile receipt, event, and time
fields never enter a business identity digest.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, NoReturn
from urllib.parse import urlsplit

from ...contracts import ContractViolation, validate_artifact
from ...domain.hashing import canonical_json, is_schema_digest, sha256_hex, sha256_of_payload
from .errors import (
    DOCUMENT_CONTRACT_INVALID,
    DOCUMENT_REGISTRATION_HASH_MISMATCH,
    DOCUMENT_REGISTRATION_ID_MISMATCH,
    DOCUMENT_REQUEST_HASH_MISMATCH,
    DOCUMENT_REQUEST_ID_MISMATCH,
    fail,
)

DOCUMENT_REGISTRATION_REQUEST_SCHEMA_ID = (
    "https://epistemic-foundry.local/schemas/"
    "document-registration-request.schema.json"
)
DOCUMENT_REGISTRATION_SCHEMA_ID = (
    "https://epistemic-foundry.local/schemas/document-registration.schema.json"
)
DOCUMENT_REGISTRATION_SCHEMA_VERSION = "4.0.0"

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

_DREQ_ID = re.compile(r"^DREQ-[0-9a-f]{64}$")
_DREG_ID = re.compile(r"^DREG-[0-9a-f]{64}$")


def _contract_error(schema_name: str, error: ContractViolation) -> NoReturn:
    fail(
        DOCUMENT_CONTRACT_INVALID,
        f"{schema_name} violates its canonical JSON Schema",
        {"schema_name": schema_name, "errors": list(error.errors)},
    )


def _utc_timestamp(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(DOCUMENT_CONTRACT_INVALID, f"{field} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(DOCUMENT_CONTRACT_INVALID, f"{field} is not a valid RFC 3339 timestamp")
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        fail(DOCUMENT_CONTRACT_INVALID, f"{field} must resolve to UTC")


def _validate_origin(origin: object) -> None:
    if not isinstance(origin, Mapping):
        fail(DOCUMENT_CONTRACT_INVALID, "source_origin must be an object")
    uri = origin.get("original_uri")
    if uri is not None:
        if not isinstance(uri, str) or any(character.isspace() for character in uri):
            fail(DOCUMENT_CONTRACT_INVALID, "source_origin.original_uri must be an absolute URI")
        parsed = urlsplit(uri)
        if not parsed.scheme or parsed.scheme.lower() == "file":
            fail(
                DOCUMENT_CONTRACT_INVALID,
                "source_origin.original_uri must be non-file provenance, never a local path",
            )
    retrieved_at = origin.get("retrieved_at")
    if retrieved_at is not None:
        _utc_timestamp(retrieved_at, "source_origin.retrieved_at")


def canonicalize_identifier_hints(value: object) -> list[dict[str, Any]]:
    """Return unique identifier hints in their deterministic semantic order."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        fail(DOCUMENT_CONTRACT_INVALID, "external_identifier_hints must be an array")
    hints: list[dict[str, Any]] = []
    fingerprints: set[bytes] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            fail(DOCUMENT_CONTRACT_INVALID, f"external_identifier_hints[{index}] must be an object")
        hint = copy.deepcopy(dict(raw))
        fingerprint = canonical_json(hint)
        if fingerprint in fingerprints:
            fail(DOCUMENT_CONTRACT_INVALID, "external_identifier_hints contains a duplicate")
        fingerprints.add(fingerprint)
        hints.append(hint)
    hints.sort(key=canonical_json)
    return hints


def _require_canonical_hint_order(payload: Mapping[str, Any]) -> None:
    raw = payload.get("external_identifier_hints")
    canonical = canonicalize_identifier_hints(raw)
    if raw != canonical:
        fail(
            DOCUMENT_CONTRACT_INVALID,
            "external_identifier_hints must be stored in canonical JSON order",
        )


def request_preimage(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Select exactly the fields sealed by ``request_hash``."""
    try:
        return {field: copy.deepcopy(payload[field]) for field in REQUEST_HASH_FIELDS}
    except KeyError as error:
        fail(DOCUMENT_CONTRACT_INVALID, f"request hash field is missing: {error.args[0]}")


def compute_request_hash(payload: Mapping[str, Any]) -> str:
    return sha256_of_payload(request_preimage(payload))


def request_id_for_hash(request_hash: str) -> str:
    if not is_schema_digest(request_hash):
        fail(DOCUMENT_CONTRACT_INVALID, "request_hash must be sha256:<64 lowercase hex>")
    return "DREQ-" + request_hash.removeprefix("sha256:")


def seal_request_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize hints and compute a request identity without inventing time."""
    sealed = copy.deepcopy(dict(payload))
    sealed["external_identifier_hints"] = canonicalize_identifier_hints(
        sealed.get("external_identifier_hints")
    )
    request_hash = compute_request_hash(sealed)
    sealed["request_hash"] = request_hash
    sealed["request_id"] = request_id_for_hash(request_hash)
    verify_request_payload(sealed)
    return sealed


def verify_request_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the schema plus hash/ID semantics and return a defensive copy."""
    candidate = copy.deepcopy(dict(payload))
    try:
        validate_artifact("document-registration-request", candidate)
    except ContractViolation as error:
        _contract_error("document-registration-request", error)
    _validate_origin(candidate["source_origin"])
    _utc_timestamp(candidate["requested_at"], "requested_at")
    _require_canonical_hint_order(candidate)
    expected_hash = compute_request_hash(candidate)
    if candidate["request_hash"] != expected_hash:
        fail(
            DOCUMENT_REQUEST_HASH_MISMATCH,
            "request_hash does not match the canonical request preimage",
            {"actual": candidate["request_hash"], "expected": expected_hash},
        )
    expected_id = request_id_for_hash(expected_hash)
    if candidate["request_id"] != expected_id or not _DREQ_ID.fullmatch(candidate["request_id"]):
        fail(
            DOCUMENT_REQUEST_ID_MISMATCH,
            "request_id is not bound to request_hash",
            {"actual": candidate["request_id"], "expected": expected_id},
        )
    return candidate


def registration_preimage(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Select exactly the fields sealed by ``registration_hash``."""
    preimage: dict[str, Any] = {}
    for field in REGISTRATION_HASH_FIELDS:
        if field == "schema_id":
            preimage[field] = DOCUMENT_REGISTRATION_SCHEMA_ID
        else:
            try:
                preimage[field] = copy.deepcopy(payload[field])
            except KeyError:
                fail(DOCUMENT_CONTRACT_INVALID, f"registration hash field is missing: {field}")
    return preimage


def compute_registration_hash(payload: Mapping[str, Any]) -> str:
    return sha256_of_payload(registration_preimage(payload))


def registration_id_for_hash(registration_hash: str) -> str:
    if not is_schema_digest(registration_hash):
        fail(DOCUMENT_CONTRACT_INVALID, "registration_hash must be sha256:<64 lowercase hex>")
    return "DREG-" + registration_hash.removeprefix("sha256:")


def seal_registration_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and hash an otherwise complete initial registration."""
    sealed = copy.deepcopy(dict(payload))
    sealed["external_identifier_hints"] = canonicalize_identifier_hints(
        sealed.get("external_identifier_hints")
    )
    registration_hash = compute_registration_hash(sealed)
    sealed["registration_hash"] = registration_hash
    sealed["registration_id"] = registration_id_for_hash(registration_hash)
    verify_registration_payload(sealed)
    return sealed


def verify_registration_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an immutable registration and its content-derived identity."""
    candidate = copy.deepcopy(dict(payload))
    try:
        validate_artifact("document-registration", candidate)
    except ContractViolation as error:
        _contract_error("document-registration", error)
    _validate_origin(candidate["source_origin"])
    _utc_timestamp(candidate["registered_at"], "registered_at")
    _require_canonical_hint_order(candidate)
    if candidate["schema_version"] != DOCUMENT_REGISTRATION_SCHEMA_VERSION:
        fail(DOCUMENT_CONTRACT_INVALID, "unsupported DocumentRegistration schema_version")
    if candidate["initial_state"] != "REGISTERED_UNSCREENED":
        fail(DOCUMENT_CONTRACT_INVALID, "initial_state must be REGISTERED_UNSCREENED")
    expected_hash = compute_registration_hash(candidate)
    if candidate["registration_hash"] != expected_hash:
        fail(
            DOCUMENT_REGISTRATION_HASH_MISMATCH,
            "registration_hash does not match the canonical registration preimage",
            {"actual": candidate["registration_hash"], "expected": expected_hash},
        )
    expected_id = registration_id_for_hash(expected_hash)
    if candidate["registration_id"] != expected_id or not _DREG_ID.fullmatch(
        candidate["registration_id"]
    ):
        fail(
            DOCUMENT_REGISTRATION_ID_MISMATCH,
            "registration_id is not bound to registration_hash",
            {"actual": candidate["registration_id"], "expected": expected_id},
        )
    return candidate


def content_hash(content: bytes) -> str:
    """Hash immutable source or artifact bytes without JSON reinterpretation."""
    return sha256_hex(bytes(content))


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    return canonical_json(copy.deepcopy(dict(payload)))


def parse_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(bytes(content).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(
            DOCUMENT_CONTRACT_INVALID,
            f"{label} is not canonical UTF-8 JSON",
            {"parse_error": str(error)},
        )
    if not isinstance(value, dict):
        fail(DOCUMENT_CONTRACT_INVALID, f"{label} must be a JSON object")
    return value

__all__ = [
    "DOCUMENT_REGISTRATION_REQUEST_SCHEMA_ID",
    "DOCUMENT_REGISTRATION_SCHEMA_ID",
    "DOCUMENT_REGISTRATION_SCHEMA_VERSION",
    "REQUEST_HASH_FIELDS",
    "REGISTRATION_HASH_FIELDS",
    "canonical_payload_bytes",
    "canonicalize_identifier_hints",
    "compute_registration_hash",
    "compute_request_hash",
    "content_hash",
    "parse_json_object",
    "registration_id_for_hash",
    "registration_preimage",
    "request_id_for_hash",
    "request_preimage",
    "seal_registration_payload",
    "seal_request_payload",
    "verify_registration_payload",
    "verify_request_payload",
]
