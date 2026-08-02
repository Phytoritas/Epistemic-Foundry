from __future__ import annotations

import hashlib

import pytest

from .registry import (
    DocumentRegistry,
    DocumentRegistryError,
    LicenseBinding,
    propagate_license,
)
from .test_document_registry import manifest, source


@pytest.mark.parametrize(
    "license_status",
    ["licensed", "open_access", "fair_use_metadata_only", "restricted", "unknown"],
)
def test_license_propagation_test_preserves_every_canonical_status(
    license_status: str,
) -> None:
    record = DocumentRegistry().register_document(
        source(),
        manifest(license_status=license_status, access_policy_ref=f"POL-{license_status}"),
    ).record

    binding = propagate_license(record)

    assert binding.license_status == license_status
    assert binding.access_policy_ref == f"POL-{license_status}"
    assert binding.content_hash == "sha256:" + hashlib.sha256(source()).hexdigest()
    assert binding.as_dict() == {
        "document_id": "DOC-v1",
        "paper_version_id": "PV-v1",
        "content_hash": record.content_hash,
        "license_status": license_status,
        "access_policy_ref": f"POL-{license_status}",
    }


def test_license_propagation_test_restricted_source_is_not_upgraded() -> None:
    record = DocumentRegistry().register_document(
        source(),
        manifest(license_status="restricted", access_policy_ref="POL-RAW-CONTENT-DENIED"),
    ).record

    binding = propagate_license(record)

    assert binding.license_status == "restricted"
    assert binding.access_policy_ref == "POL-RAW-CONTENT-DENIED"


def test_license_propagation_test_unknown_source_is_not_defaulted() -> None:
    record = DocumentRegistry().register_document(
        source(), manifest(license_status="unknown", access_policy_ref="POL-REVIEW-REQUIRED")
    ).record

    assert propagate_license(record).license_status == "unknown"


def test_license_propagation_test_retry_cannot_change_restrictions() -> None:
    registry = DocumentRegistry()
    original = manifest(license_status="restricted", access_policy_ref="POL-RESTRICTED")
    registry.register_document(source(), original)
    changed = manifest(license_status="open_access", access_policy_ref="POL-OPEN")

    with pytest.raises(DocumentRegistryError) as raised:
        registry.register_document(source(), changed)

    assert raised.value.code == "DOCUMENT_REGISTRATION_CONFLICT"
    binding = propagate_license(registry.get_version("PV-v1"))
    assert (binding.license_status, binding.access_policy_ref) == (
        "restricted",
        "POL-RESTRICTED",
    )


def test_license_propagation_test_retraction_and_trust_state_remain_visible() -> None:
    record = DocumentRegistry().register_document(
        source(),
        manifest(
            bibliographic_version="retraction_notice",
            status="retracted",
            license_status="restricted",
            access_policy_ref="POL-RETRACTED",
            malware_scan_status="suspicious",
            prompt_injection_scan_status="quarantined",
        ),
    ).record

    retained = record.manifest
    assert retained["bibliographic_version"] == "retraction_notice"
    assert retained["status"] == "retracted"
    assert retained["malware_scan_status"] == "suspicious"
    assert retained["prompt_injection_scan_status"] == "quarantined"
    assert propagate_license(record).license_status == "restricted"


def test_license_propagation_test_binding_projection_cannot_mutate_record() -> None:
    record = DocumentRegistry().register_document(source(), manifest()).record
    projection = propagate_license(record).as_dict()
    projection["license_status"] = "restricted"

    assert propagate_license(record).license_status == "open_access"


def test_license_propagation_test_rejects_non_record_input() -> None:
    with pytest.raises(DocumentRegistryError) as raised:
        propagate_license({})  # type: ignore[arg-type]

    assert raised.value.code == "DOCUMENT_RECORD_INVALID"


def test_license_propagation_test_direct_binding_rejects_noncanonical_status() -> None:
    with pytest.raises(DocumentRegistryError):
        LicenseBinding(
            document_id="DOC-1",
            paper_version_id="PV-1",
            content_hash="sha256:" + "a" * 64,
            license_status="implicitly_allowed",
            access_policy_ref="POL-1",
        )
