"""Typed refusals shared by the T05 evolution backend adapter surface.

Every way this package refuses lives in one table, so a refusal cannot be
raised under a code no reviewer can look up, and every record this package
emits carries a digest that is re-derived from its own content rather than
declared.  The two helpers exist together because they answer the same
question from opposite sides: ``_fail`` says why a record was never built,
``assert_hash_rederives`` says whether a record that claims to exist is the
one that was built.
"""

from __future__ import annotations

from typing import Any, Mapping

from ...domain.hashing import hash_excluding

#: Every way this package refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "BACKEND_AUTHORITY_LEAK": (
        "an imported backend field was bound onto a Foundry authority surface; "
        "another engine's bookkeeping would become a promotion or evaluator "
        "input without ever passing a Foundry gate"
    ),
    "BACKEND_UNPINNED": (
        "the backend names no exact commit digest or no exact release, so the "
        "qualification would describe a build that can change underneath it "
        "while still claiming to be the qualified configuration"
    ),
    "CAPABILITY_OVERCLAIMED": (
        "the qualification claims a capability the backend manifest does not "
        "declare as enabled, or claims one the manifest explicitly disables, "
        "which converts an untested dimension into a qualified one"
    ),
    "EXECUTION_PROFILE_UNBOUND": (
        "the qualification is not bound to a re-derivable S05 execution "
        "qualification for the sandbox profile the executor will run under, so "
        "nothing ties the backend's permission to run to a checked profile"
    ),
    "EXECUTOR_UNPROJECTED": (
        "an executor was requested for a command the sealed tool surface does "
        "not project; registering it would make the adapter advertise a CLI or "
        "MCP operation that the host surface cannot route"
    ),
    "IMPORT_COUNTS_UNRECONCILED": (
        "an imported run's candidate identities do not account for one another "
        "across the pipeline stages, so the import would carry a population "
        "whose gaps are invisible once the counts are collapsed"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this package requires, and continuing would "
        "produce a record it never actually validated"
    ),
    "QUALIFICATION_STATUS_UNDECLARED": (
        "the qualification verdict is not one the canonical schema declares, so "
        "downstream readers would have to guess how strong the verdict is"
    ),
    "RECORD_HASH_MISMATCH": (
        "a record does not re-derive the digest it declares, so it is not the "
        "record that was sealed and its contents are not evidence of anything"
    ),
    "SURFACE_UNREADABLE": (
        "the sealed evolution tool surface could not be read as the declaration "
        "this package requires, so the projected command set is unknown and no "
        "executor registration can be shown to be honest"
    ),
}


class AdapterGateError(ValueError):
    """A pinning, qualification, import or registration request was refused."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise AdapterGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise AdapterGateError(code, message, context)


def require_mapping(value: object, label: str) -> Mapping[str, Any]:
    """Refuse anything that is not a mapping before it is read as a record."""
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def require_identifier(value: object, label: str) -> str:
    """Refuse a blank or non-string identifier.

    Identifiers are always supplied by the caller in this package rather than
    minted, because a minted id would make every record non-reproducible and
    the digests below would stop being a replay check.
    """
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value).strip()


def require_identifiers(values: object, label: str) -> tuple[str, ...]:
    """Refuse a sequence that is not a list of usable identifiers."""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        _fail("INPUT_INVALID", f"{label} must be an array", {"label": label})
    return tuple(
        require_identifier(entry, f"{label}[{index}]")
        for index, entry in enumerate(values)  # type: ignore[arg-type]
    )


def seal(record: dict[str, Any], hash_field: str) -> dict[str, Any]:
    """Attach the digest of everything else in the record."""
    sealed = dict(record)
    sealed[hash_field] = hash_excluding(sealed, hash_field)
    return sealed


def assert_hash_rederives(
    record: Mapping[str, Any], hash_field: str, label: str
) -> str:
    """Re-derive a record's digest from its content; a declared digest proves
    nothing on its own."""
    value = require_mapping(record, label)
    declared = value.get(hash_field)
    if not isinstance(declared, str) or not declared:
        _fail(
            "RECORD_HASH_MISMATCH",
            f"{label} declares no {hash_field}",
            {"label": label, "hash_field": hash_field},
        )
    derived = hash_excluding(dict(value), hash_field)
    if derived != declared:
        _fail(
            "RECORD_HASH_MISMATCH",
            f"{label} does not re-derive its own {hash_field}",
            {"declared": declared, "derived": derived, "label": label},
        )
    return str(declared)
