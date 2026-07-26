"""Fail-closed artifact validation against the canonical schemas.

Every artifact that crosses a component boundary is validated here. The
failure mode is an exception, never a warning: a silently accepted malformed
artifact would propagate into a receipt and make the ledger untrustworthy.
"""

from __future__ import annotations

from typing import Any

from jsonschema.exceptions import ValidationError

from .registry import SchemaRegistry, default_registry


class ContractViolation(ValueError):
    """An artifact does not satisfy its canonical schema."""

    def __init__(self, schema_name: str, errors: list[str]) -> None:
        self.schema_name = schema_name
        self.errors = errors
        detail = "; ".join(errors[:5])
        suffix = "" if len(errors) <= 5 else f" (+{len(errors) - 5} more)"
        super().__init__(f"{schema_name}: {detail}{suffix}")


def _describe(error: ValidationError) -> str:
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"


def validate_artifact(
    schema_name: str,
    payload: Any,
    *,
    registry: SchemaRegistry | None = None,
) -> None:
    """Validate `payload`; raise `ContractViolation` listing every error.

    All errors are collected rather than raising on the first one, so a caller
    fixing an artifact sees the full contract gap in one pass.
    """
    active = registry or default_registry()
    validator = active.validator(schema_name)
    errors = [_describe(error) for error in validator.iter_errors(payload)]
    if errors:
        raise ContractViolation(schema_name, sorted(errors))


def artifact_errors(
    schema_name: str,
    payload: Any,
    *,
    registry: SchemaRegistry | None = None,
) -> list[str]:
    """Non-raising variant for reporting surfaces (audits, CLI diagnostics)."""
    active = registry or default_registry()
    validator = active.validator(schema_name)
    return sorted(_describe(error) for error in validator.iter_errors(payload))
