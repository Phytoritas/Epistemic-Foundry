"""Canonical-schema access and validation.

`schemas/*.schema.json` is the authority for every artifact shape. This package
loads those files at runtime instead of restating their fields in Python, so a
schema edit cannot drift away from the code that writes the artifact.
"""

from __future__ import annotations

from .registry import (
    SchemaNotFound,
    SchemaRegistry,
    default_registry,
    repo_root,
)
from .validation import ContractViolation, validate_artifact

__all__ = [
    "ContractViolation",
    "SchemaNotFound",
    "SchemaRegistry",
    "default_registry",
    "repo_root",
    "validate_artifact",
]
