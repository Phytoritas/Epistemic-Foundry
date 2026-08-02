"""Deterministic K01 document registration boundary."""

from .registry import (
    DOCUMENT_REGISTRY_VERSION,
    DocumentRecord,
    DocumentRegistration,
    DocumentRegistry,
    DocumentRegistryError,
    LicenseBinding,
    propagate_license,
    register_document,
)

__all__ = [
    "DOCUMENT_REGISTRY_VERSION",
    "DocumentRecord",
    "DocumentRegistration",
    "DocumentRegistry",
    "DocumentRegistryError",
    "LicenseBinding",
    "propagate_license",
    "register_document",
]
