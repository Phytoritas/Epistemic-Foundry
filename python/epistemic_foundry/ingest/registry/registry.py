"""Immutable source registration, version lineage, and license binding (K01).

The content-addressed artifact store owns durable source-byte persistence and
receipts.  This component owns the deterministic document registry boundary:
it verifies those bytes against a canonical ``DocumentManifest``, retains an
append-only snapshot, rejects identity or lineage conflicts, and exposes the
license/access tuple that downstream retrieval, evidence, export, and deletion
adapters must carry forward.

No license is interpreted here.  In particular, ``open_access`` is not turned
into an export grant and ``unknown`` is not upgraded to a permissive default.
Policy enforcement remains the policy engine's responsibility.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from types import MappingProxyType
from typing import Final, Mapping, Sequence


DOCUMENT_REGISTRY_VERSION: Final = "4.0.0-k01.1"

_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
    r"[0-9]{2}:[0-9]{2}:(?P<second>[0-9]{2})(?:\.[0-9]+)?"
    r"(?:[Zz]|[+-][0-9]{2}:[0-9]{2})$"
)
_FIELDS: Final = frozenset(
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
_BIBLIOGRAPHIC_VERSIONS: Final = frozenset(
    {
        "preprint",
        "accepted_manuscript",
        "version_of_record",
        "correction",
        "retraction_notice",
        "other",
    }
)
_DOCUMENT_STATUSES: Final = frozenset(
    {"active", "corrected", "retracted", "withdrawn", "quarantined", "unknown"}
)
_LICENSE_STATUSES: Final = frozenset(
    {"licensed", "open_access", "fair_use_metadata_only", "restricted", "unknown"}
)
_MALWARE_STATUSES: Final = frozenset(
    {"not_run", "clean", "suspicious", "malicious"}
)
_PROMPT_INJECTION_STATUSES: Final = frozenset(
    {"not_run", "clean", "suspicious", "quarantined"}
)


class DocumentRegistryError(ValueError):
    """Typed fail-closed K01 component error."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise DocumentRegistryError(code, message, details)


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or "\x00" in value or (not allow_empty and not value.strip()):
        qualifier = "NUL-free string" if allow_empty else "non-empty NUL-free string"
        _fail("DOCUMENT_MANIFEST_INVALID", f"{label} must be a {qualifier}")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise DocumentRegistryError(
            "DOCUMENT_MANIFEST_INVALID",
            f"{label} must contain Unicode scalar values",
        ) from error
    return value


def _nullable_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label, allow_empty=True)


def _enum(value: object, label: str, allowed: frozenset[str]) -> str:
    candidate = _text(value, label)
    if candidate not in allowed:
        _fail(
            "DOCUMENT_MANIFEST_INVALID",
            f"{label} must use the closed canonical vocabulary",
            {"actual": candidate, "allowed": sorted(allowed)},
        )
    return candidate


def _timestamp(value: object) -> str:
    candidate = _text(value, "ingested_at")
    match = _RFC3339_PATTERN.fullmatch(candidate)
    if match is None:
        _fail("DOCUMENT_MANIFEST_INVALID", "ingested_at must be an RFC 3339 date-time")
    parse_candidate = candidate[:-1] + "+00:00" if candidate[-1] in "Zz" else candidate
    if match.group("second") == "60":
        parse_candidate = parse_candidate[:17] + "59" + parse_candidate[19:]
    try:
        parsed = datetime.fromisoformat(parse_candidate)
    except ValueError as error:
        raise DocumentRegistryError(
            "DOCUMENT_MANIFEST_INVALID",
            "ingested_at must be a real RFC 3339 date-time",
        ) from error
    if parsed.tzinfo is None:
        _fail("DOCUMENT_MANIFEST_INVALID", "ingested_at must include a timezone")
    return candidate


def _string_array(value: object, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("DOCUMENT_MANIFEST_INVALID", f"{label} must be an array")
    return [
        _text(entry, f"{label}[{index}]", allow_empty=True)
        for index, entry in enumerate(value)
    ]


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise DocumentRegistryError(
            "DOCUMENT_MANIFEST_INVALID",
            "document manifest must be finite canonical JSON",
        ) from error


def _source_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    _fail("DOCUMENT_SOURCE_INVALID", "source_bytes must be bytes-like")


def _manifest_snapshot(value: object) -> tuple[dict[str, object], bytes]:
    if not isinstance(value, Mapping):
        _fail("DOCUMENT_MANIFEST_INVALID", "manifest must be an object")
    snapshot = dict(value)
    if any(type(key) is not str for key in snapshot):
        _fail("DOCUMENT_MANIFEST_INVALID", "manifest keys must be strings")
    actual = frozenset(snapshot)
    if actual != _FIELDS:
        _fail(
            "DOCUMENT_MANIFEST_INVALID",
            "manifest must contain exactly the canonical DocumentManifest fields",
            {
                "missing": sorted(_FIELDS - actual),
                "unexpected": sorted(actual - _FIELDS),
            },
        )

    normalized: dict[str, object] = {
        "document_id": _text(snapshot["document_id"], "document_id"),
        "paper_id": _text(snapshot["paper_id"], "paper_id"),
        "paper_version_id": _text(snapshot["paper_version_id"], "paper_version_id"),
        "content_hash": _text(snapshot["content_hash"], "content_hash"),
        "original_filename": _text(snapshot["original_filename"], "original_filename"),
        "media_type": _text(snapshot["media_type"], "media_type"),
        "source_uri": _nullable_text(snapshot["source_uri"], "source_uri"),
        "doi": _nullable_text(snapshot["doi"], "doi"),
        "bibliographic_version": _enum(
            snapshot["bibliographic_version"],
            "bibliographic_version",
            _BIBLIOGRAPHIC_VERSIONS,
        ),
        "supersedes_version_id": _nullable_text(
            snapshot["supersedes_version_id"], "supersedes_version_id"
        ),
        "status": _enum(snapshot["status"], "status", _DOCUMENT_STATUSES),
        "license_status": _enum(
            snapshot["license_status"], "license_status", _LICENSE_STATUSES
        ),
        "access_policy_ref": _text(snapshot["access_policy_ref"], "access_policy_ref"),
        "parser_artifact_ids": _string_array(
            snapshot["parser_artifact_ids"], "parser_artifact_ids"
        ),
        "source_integrity_report_id": _text(
            snapshot["source_integrity_report_id"], "source_integrity_report_id"
        ),
        "malware_scan_status": _enum(
            snapshot["malware_scan_status"], "malware_scan_status", _MALWARE_STATUSES
        ),
        "prompt_injection_scan_status": _enum(
            snapshot["prompt_injection_scan_status"],
            "prompt_injection_scan_status",
            _PROMPT_INJECTION_STATUSES,
        ),
        "ingested_at": _timestamp(snapshot["ingested_at"]),
        "provenance_manifest_id": _text(
            snapshot["provenance_manifest_id"], "provenance_manifest_id"
        ),
    }
    if _SHA256_PATTERN.fullmatch(normalized["content_hash"]) is None:  # type: ignore[arg-type]
        _fail(
            "DOCUMENT_MANIFEST_INVALID",
            "content_hash must be sha256 followed by 64 lowercase hex characters",
        )
    if normalized["supersedes_version_id"] == normalized["paper_version_id"]:
        _fail(
            "DOCUMENT_LINEAGE_INVALID",
            "a paper version cannot supersede itself",
        )
    return normalized, _canonical_json(normalized)


@dataclass(frozen=True, slots=True)
class LicenseBinding:
    """Exact source restriction tuple propagated without policy inference."""

    document_id: str
    paper_version_id: str
    content_hash: str
    license_status: str
    access_policy_ref: str

    def __post_init__(self) -> None:
        _text(self.document_id, "LicenseBinding.document_id")
        _text(self.paper_version_id, "LicenseBinding.paper_version_id")
        if type(self.content_hash) is not str or _SHA256_PATTERN.fullmatch(self.content_hash) is None:
            _fail(
                "DOCUMENT_RECORD_INVALID",
                "LicenseBinding.content_hash must be canonical SHA-256",
            )
        _enum(
            self.license_status,
            "LicenseBinding.license_status",
            _LICENSE_STATUSES,
        )
        _text(self.access_policy_ref, "LicenseBinding.access_policy_ref")

    def as_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "paper_version_id": self.paper_version_id,
            "content_hash": self.content_hash,
            "license_status": self.license_status,
            "access_policy_ref": self.access_policy_ref,
        }


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """Immutable registry snapshot for one exact source version."""

    registry_version: str
    _manifest_json: bytes = field(repr=False)
    _source_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if self.registry_version != DOCUMENT_REGISTRY_VERSION:
            _fail(
                "DOCUMENT_RECORD_INVALID",
                "DocumentRecord.registry_version is not the active K01 contract version",
            )
        if type(self._manifest_json) is not bytes or type(self._source_bytes) is not bytes:
            _fail(
                "DOCUMENT_RECORD_INVALID",
                "DocumentRecord snapshots must be immutable bytes",
            )
        try:
            decoded = json.loads(self._manifest_json.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DocumentRegistryError(
                "DOCUMENT_RECORD_INVALID",
                "DocumentRecord manifest snapshot is not UTF-8 JSON",
            ) from error
        normalized, canonical = _manifest_snapshot(decoded)
        if canonical != self._manifest_json:
            _fail(
                "DOCUMENT_RECORD_INVALID",
                "DocumentRecord manifest snapshot is not canonical JSON",
            )
        observed_hash = "sha256:" + hashlib.sha256(self._source_bytes).hexdigest()
        if observed_hash != normalized["content_hash"]:
            _fail(
                "DOCUMENT_RECORD_INVALID",
                "DocumentRecord source bytes do not match the sealed content_hash",
                {"expected": normalized["content_hash"], "observed": observed_hash},
            )

    @property
    def manifest_json(self) -> bytes:
        return self._manifest_json

    @property
    def source_bytes(self) -> bytes:
        return self._source_bytes

    @property
    def manifest(self) -> dict[str, object]:
        value = json.loads(self._manifest_json.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("registered DocumentManifest is not an object")
        return value

    @property
    def document_id(self) -> str:
        return str(self.manifest["document_id"])

    @property
    def paper_id(self) -> str:
        return str(self.manifest["paper_id"])

    @property
    def paper_version_id(self) -> str:
        return str(self.manifest["paper_version_id"])

    @property
    def content_hash(self) -> str:
        return str(self.manifest["content_hash"])

    @property
    def supersedes_version_id(self) -> str | None:
        value = self.manifest["supersedes_version_id"]
        return None if value is None else str(value)

    @property
    def license_binding(self) -> LicenseBinding:
        manifest = self.manifest
        return LicenseBinding(
            document_id=str(manifest["document_id"]),
            paper_version_id=str(manifest["paper_version_id"]),
            content_hash=str(manifest["content_hash"]),
            license_status=str(manifest["license_status"]),
            access_policy_ref=str(manifest["access_policy_ref"]),
        )


@dataclass(frozen=True, slots=True)
class DocumentRegistration:
    """One registration attempt; retries point to the original record."""

    record: DocumentRecord
    created: bool


class DocumentRegistry:
    """Thread-safe append-only in-memory projection of canonical registrations."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._records: list[DocumentRecord] = []
        self._by_document_id: dict[str, DocumentRecord] = {}
        self._by_version_id: dict[str, DocumentRecord] = {}

    def register_document(
        self,
        source_bytes: bytes | bytearray | memoryview,
        manifest: Mapping[str, object],
    ) -> DocumentRegistration:
        """Verify and append one source, or return its exact prior registration."""

        source = _source_bytes(source_bytes)
        normalized, manifest_json = _manifest_snapshot(manifest)
        observed_hash = "sha256:" + hashlib.sha256(source).hexdigest()
        expected_hash = str(normalized["content_hash"])
        if observed_hash != expected_hash:
            _fail(
                "DOCUMENT_SOURCE_HASH_MISMATCH",
                "source bytes do not match DocumentManifest.content_hash",
                {"expected": expected_hash, "observed": observed_hash},
            )

        document_id = str(normalized["document_id"])
        version_id = str(normalized["paper_version_id"])
        with self._lock:
            document_record = self._by_document_id.get(document_id)
            version_record = self._by_version_id.get(version_id)
            if document_record is not None or version_record is not None:
                if (
                    document_record is not None
                    and document_record is version_record
                    and document_record.manifest_json == manifest_json
                    and document_record.source_bytes == source
                ):
                    return DocumentRegistration(record=document_record, created=False)
                _fail(
                    "DOCUMENT_REGISTRATION_CONFLICT",
                    "document_id or paper_version_id is already bound to another registration",
                    {
                        "document_id": document_id,
                        "paper_version_id": version_id,
                        "document_id_exists": document_record is not None,
                        "paper_version_id_exists": version_record is not None,
                    },
                )

            supersedes = normalized["supersedes_version_id"]
            if supersedes is not None:
                predecessor = self._by_version_id.get(str(supersedes))
                if predecessor is None:
                    _fail(
                        "DOCUMENT_PREDECESSOR_NOT_FOUND",
                        "supersedes_version_id must reference an existing immutable version",
                        {"supersedes_version_id": supersedes},
                    )
                if predecessor.paper_id != normalized["paper_id"]:
                    _fail(
                        "DOCUMENT_LINEAGE_CONFLICT",
                        "a paper version may supersede only a version of the same paper_id",
                        {
                            "paper_id": normalized["paper_id"],
                            "predecessor_paper_id": predecessor.paper_id,
                        },
                    )

            record = DocumentRecord(
                registry_version=DOCUMENT_REGISTRY_VERSION,
                _manifest_json=manifest_json,
                _source_bytes=source,
            )
            self._records.append(record)
            self._by_document_id[document_id] = record
            self._by_version_id[version_id] = record
            return DocumentRegistration(record=record, created=True)

    def get_document(self, document_id: str) -> DocumentRecord:
        key = _text(document_id, "document_id")
        with self._lock:
            record = self._by_document_id.get(key)
        if record is None:
            _fail("DOCUMENT_NOT_FOUND", "document_id is not registered", {"document_id": key})
        return record

    def get_version(self, paper_version_id: str) -> DocumentRecord:
        key = _text(paper_version_id, "paper_version_id")
        with self._lock:
            record = self._by_version_id.get(key)
        if record is None:
            _fail(
                "DOCUMENT_VERSION_NOT_FOUND",
                "paper_version_id is not registered",
                {"paper_version_id": key},
            )
        return record

    def records(self) -> tuple[DocumentRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


def register_document(
    registry: DocumentRegistry,
    source_bytes: bytes | bytearray | memoryview,
    manifest: Mapping[str, object],
) -> DocumentRegistration:
    """Workflow-facing deterministic registration entry point."""

    if type(registry) is not DocumentRegistry:
        _fail("DOCUMENT_REGISTRY_INVALID", "registry must be a DocumentRegistry")
    return registry.register_document(source_bytes, manifest)


def propagate_license(record: DocumentRecord) -> LicenseBinding:
    """Return the exact retained restriction tuple; make no allow/deny decision."""

    if type(record) is not DocumentRecord:
        _fail("DOCUMENT_RECORD_INVALID", "record must be an immutable DocumentRecord")
    return record.license_binding
