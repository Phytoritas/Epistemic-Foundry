"""Append-only supersession validation for DocumentRegistration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ...domain.hashing import canonical_json
from .errors import (
    DOCUMENT_IMMUTABLE_HISTORY_MUTATION,
    DOCUMENT_LINEAGE_CYCLE,
    DOCUMENT_LINEAGE_SCOPE_MISMATCH,
    DOCUMENT_LINEAGE_UNKNOWN,
    fail,
)
from .hash import verify_registration_payload, verify_request_payload

RegistrationLookup = Callable[[str], Mapping[str, Any] | None]


def assert_registration_immutable(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    """Reject any attempt to rewrite a prior canonical registration."""
    if canonical_json(dict(before)) != canonical_json(dict(after)):
        fail(
            DOCUMENT_IMMUTABLE_HISTORY_MUTATION,
            "an existing DocumentRegistration cannot be mutated in place",
        )


def _validate_predecessor_chain(
    *,
    workspace_id: str,
    corpus_id: str,
    predecessor_id: str | None,
    lookup: RegistrationLookup,
    current_registration_id: str | None = None,
    maximum_depth: int = 10_000,
) -> tuple[str, ...]:
    """Validate an immutable predecessor chain nearest-first."""
    if predecessor_id is None:
        return ()
    if predecessor_id == current_registration_id:
        fail(DOCUMENT_LINEAGE_CYCLE, "a registration cannot supersede itself")

    visited = {current_registration_id} if current_registration_id is not None else set()
    lineage: list[str] = []
    while predecessor_id is not None:
        if predecessor_id in visited:
            fail(
                DOCUMENT_LINEAGE_CYCLE,
                "document registration supersession contains a cycle",
                {"registration_id": predecessor_id, "lineage": lineage},
            )
        if len(lineage) >= maximum_depth:
            fail(DOCUMENT_LINEAGE_CYCLE, "document registration lineage exceeds its bound")
        predecessor_raw = lookup(predecessor_id)
        if predecessor_raw is None:
            fail(
                DOCUMENT_LINEAGE_UNKNOWN,
                "supersedes_registration_id does not resolve to immutable history",
                {"registration_id": predecessor_id},
            )
        predecessor = verify_registration_payload(predecessor_raw)
        if predecessor["registration_id"] != predecessor_id:
            fail(
                DOCUMENT_IMMUTABLE_HISTORY_MUTATION,
                "lineage lookup returned a registration under the wrong immutable ID",
            )
        if (
            predecessor["workspace_id"] != workspace_id
            or predecessor["corpus_id"] != corpus_id
        ):
            fail(
                DOCUMENT_LINEAGE_SCOPE_MISMATCH,
                "a registration may supersede only a registration in the same workspace and corpus",
                {"registration_id": predecessor_id},
            )
        visited.add(predecessor_id)
        lineage.append(predecessor_id)
        predecessor_id = predecessor["supersedes_registration_id"]
    return tuple(lineage)


def validate_registration_predecessor(
    request: Mapping[str, Any],
    lookup: RegistrationLookup,
    *,
    maximum_depth: int = 10_000,
) -> tuple[str, ...]:
    """Preflight request lineage before any controlled publication effect."""
    current = verify_request_payload(request)
    return _validate_predecessor_chain(
        workspace_id=current["workspace_id"],
        corpus_id=current["corpus_id"],
        predecessor_id=current["supersedes_registration_id"],
        lookup=lookup,
        maximum_depth=maximum_depth,
    )


def validate_registration_lineage(
    registration: Mapping[str, Any],
    lookup: RegistrationLookup,
    *,
    maximum_depth: int = 10_000,
) -> tuple[str, ...]:
    """Validate one supersession chain and return predecessor IDs nearest first."""
    current = verify_registration_payload(registration)
    return _validate_predecessor_chain(
        workspace_id=current["workspace_id"],
        corpus_id=current["corpus_id"],
        predecessor_id=current["supersedes_registration_id"],
        lookup=lookup,
        current_registration_id=current["registration_id"],
        maximum_depth=maximum_depth,
    )


__all__ = [
    "RegistrationLookup",
    "assert_registration_immutable",
    "validate_registration_lineage",
    "validate_registration_predecessor",
]
