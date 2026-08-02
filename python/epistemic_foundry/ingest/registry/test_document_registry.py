from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from .registry import (
    DOCUMENT_REGISTRY_VERSION,
    DocumentRecord,
    DocumentRegistry,
    DocumentRegistryError,
    register_document,
)


ROOT = Path(__file__).resolve().parents[4]


def source(label: str = "v1") -> bytes:
    return f"immutable source bytes: {label}\n".encode()


def manifest(label: str = "v1", **overrides: object) -> dict[str, object]:
    value = json.loads(
        (ROOT / "examples/sample_document-manifest.json").read_text(encoding="utf-8")
    )
    value.update(
        {
            "document_id": f"DOC-{label}",
            "paper_id": "PAPER-1",
            "paper_version_id": f"PV-{label}",
            "content_hash": "sha256:" + hashlib.sha256(source(label)).hexdigest(),
            "parser_artifact_ids": [],
            "ingested_at": "2026-07-30T00:00:00.000Z",
        }
    )
    value.update(overrides)
    return value


def test_document_registry_test_registers_exact_source_and_canonical_manifest() -> None:
    registry = DocumentRegistry()

    result = register_document(registry, source(), manifest())

    assert result.created is True
    assert result.record.registry_version == DOCUMENT_REGISTRY_VERSION
    assert result.record.source_bytes == source()
    assert registry.get_document("DOC-v1") is result.record
    assert registry.get_version("PV-v1") is result.record
    Draft202012Validator(
        json.loads((ROOT / "schemas/document-manifest.schema.json").read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    ).validate(result.record.manifest)


def test_document_registry_test_source_hash_mismatch_fails_closed() -> None:
    with pytest.raises(DocumentRegistryError) as raised:
        DocumentRegistry().register_document(b"different", manifest())

    assert raised.value.code == "DOCUMENT_SOURCE_HASH_MISMATCH"


def test_document_registry_test_copies_mutable_source_and_manifest_inputs() -> None:
    registry = DocumentRegistry()
    mutable_source = bytearray(source())
    mutable_manifest = manifest()
    before = copy.deepcopy(mutable_manifest)

    record = registry.register_document(mutable_source, mutable_manifest).record
    mutable_source[0] = ord("X")
    mutable_manifest["status"] = "retracted"
    mutable_manifest["parser_artifact_ids"].append("ART-late")  # type: ignore[union-attr]

    assert record.source_bytes == source()
    assert record.manifest == before


def test_document_registry_test_returned_manifest_is_a_fresh_projection() -> None:
    record = DocumentRegistry().register_document(source(), manifest()).record
    first = record.manifest
    first["status"] = "retracted"

    assert record.manifest["status"] == "active"


def test_document_registry_test_exact_retry_reuses_original_record() -> None:
    registry = DocumentRegistry()
    first = registry.register_document(source(), manifest())
    replay = registry.register_document(source(), dict(reversed(list(manifest().items()))))

    assert first.created is True
    assert replay.created is False
    assert replay.record is first.record
    assert len(registry) == 1


@pytest.mark.parametrize("identity", ["document_id", "paper_version_id"])
def test_document_registry_test_identity_rebinding_is_rejected(identity: str) -> None:
    registry = DocumentRegistry()
    registry.register_document(source(), manifest())
    conflict = manifest("v2", supersedes_version_id="PV-v1")
    conflict[identity] = manifest()[identity]
    if identity == "paper_version_id":
        # Isolate identity rebinding from the independently tested
        # self-supersession boundary.
        conflict["supersedes_version_id"] = None

    with pytest.raises(DocumentRegistryError) as raised:
        registry.register_document(source("v2"), conflict)

    assert raised.value.code == "DOCUMENT_REGISTRATION_CONFLICT"
    assert len(registry) == 1


def test_document_registry_test_valid_version_lineage_is_append_only() -> None:
    registry = DocumentRegistry()
    first = registry.register_document(source(), manifest()).record
    second = registry.register_document(
        source("v2"),
        manifest(
            "v2",
            bibliographic_version="correction",
            supersedes_version_id="PV-v1",
            status="corrected",
        ),
    ).record

    assert second.supersedes_version_id == "PV-v1"
    assert first.manifest["status"] == "active"
    assert [record.paper_version_id for record in registry.records()] == ["PV-v1", "PV-v2"]


def test_document_registry_test_missing_predecessor_is_rejected_without_partial_append() -> None:
    registry = DocumentRegistry()

    with pytest.raises(DocumentRegistryError) as raised:
        registry.register_document(
            source("v2"), manifest("v2", supersedes_version_id="PV-missing")
        )

    assert raised.value.code == "DOCUMENT_PREDECESSOR_NOT_FOUND"
    assert registry.records() == ()


def test_document_registry_test_cross_paper_supersession_is_rejected() -> None:
    registry = DocumentRegistry()
    registry.register_document(source(), manifest())

    with pytest.raises(DocumentRegistryError) as raised:
        registry.register_document(
            source("v2"),
            manifest("v2", paper_id="PAPER-2", supersedes_version_id="PV-v1"),
        )

    assert raised.value.code == "DOCUMENT_LINEAGE_CONFLICT"
    assert len(registry) == 1


def test_document_registry_test_self_supersession_is_rejected() -> None:
    with pytest.raises(DocumentRegistryError) as raised:
        DocumentRegistry().register_document(
            source(), manifest(supersedes_version_id="PV-v1")
        )

    assert raised.value.code == "DOCUMENT_LINEAGE_INVALID"


def test_document_registry_test_same_bytes_may_have_distinct_explicit_identity() -> None:
    registry = DocumentRegistry()
    first_manifest = manifest()
    registry.register_document(source(), first_manifest)
    second_manifest = manifest(
        "alias",
        document_id="DOC-alias",
        paper_id="PAPER-2",
        paper_version_id="PV-alias",
        content_hash=first_manifest["content_hash"],
    )

    registry.register_document(source(), second_manifest)

    assert len(registry) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_hash", "sha256:NOT-A-HASH"),
        ("bibliographic_version", "draft"),
        ("status", "deleted"),
        ("malware_scan_status", "trusted"),
        ("prompt_injection_scan_status", "ignored"),
        ("ingested_at", "2026-07-30 00:00:00"),
    ],
)
def test_document_registry_test_invalid_canonical_field_fails_closed(
    field: str, value: object
) -> None:
    candidate = manifest()
    candidate[field] = value

    with pytest.raises(DocumentRegistryError) as raised:
        DocumentRegistry().register_document(source(), candidate)

    assert raised.value.code == "DOCUMENT_MANIFEST_INVALID"


def test_document_registry_test_unknown_field_fails_closed() -> None:
    candidate = manifest()
    candidate["model_confidence"] = 0.99

    with pytest.raises(DocumentRegistryError) as raised:
        DocumentRegistry().register_document(source(), candidate)

    assert raised.value.code == "DOCUMENT_MANIFEST_INVALID"


def test_document_registry_test_unknown_lookup_is_typed() -> None:
    registry = DocumentRegistry()

    with pytest.raises(DocumentRegistryError) as document_error:
        registry.get_document("DOC-missing")
    with pytest.raises(DocumentRegistryError) as version_error:
        registry.get_version("PV-missing")

    assert document_error.value.code == "DOCUMENT_NOT_FOUND"
    assert version_error.value.code == "DOCUMENT_VERSION_NOT_FOUND"


def test_document_registry_test_direct_record_construction_cannot_bypass_hash_gate() -> None:
    canonical = json.dumps(
        manifest(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    with pytest.raises(DocumentRegistryError) as raised:
        DocumentRecord(
            registry_version=DOCUMENT_REGISTRY_VERSION,
            _manifest_json=canonical,
            _source_bytes=b"forged source bytes",
        )

    assert raised.value.code == "DOCUMENT_RECORD_INVALID"


def test_document_registry_test_direct_record_requires_canonical_manifest_bytes() -> None:
    noncanonical = json.dumps(manifest(), ensure_ascii=False, indent=2).encode("utf-8")

    with pytest.raises(DocumentRegistryError) as raised:
        DocumentRecord(
            registry_version=DOCUMENT_REGISTRY_VERSION,
            _manifest_json=noncanonical,
            _source_bytes=source(),
        )

    assert raised.value.code == "DOCUMENT_RECORD_INVALID"
