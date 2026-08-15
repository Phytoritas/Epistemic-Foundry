"""A05 independent-attestation input validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .registry import (
    ATTESTOR_CONFLICT_ROLES,
    EvolutionAuthorityError,
    verify_attestor_independence as _legacy_verify_attestor_independence,
)


def verify_attestor_independence(
    attestor_id: str, context: Mapping[str, Any]
) -> None:
    """Reject malformed or self/non-independent attestation contexts."""

    if type(attestor_id) is not str or not attestor_id:
        raise EvolutionAuthorityError(
            "ATTESTOR_INDEPENDENCE_VIOLATION", "attestor identity is missing"
        )
    if not isinstance(context, Mapping):
        raise EvolutionAuthorityError(
            "ATTESTOR_INDEPENDENCE_VIOLATION",
            "attestor independence context must be a mapping",
        )

    snapshot: dict[str, tuple[str, ...]] = {}
    for role in ATTESTOR_CONFLICT_ROLES:
        if role not in context:
            raise EvolutionAuthorityError(
                "ATTESTOR_INDEPENDENCE_VIOLATION",
                f"attestor conflict role {role!r} must be explicitly present",
            )
        members = context[role]
        if isinstance(members, (str, bytes, bytearray, Mapping)) or not isinstance(
            members, Sequence
        ):
            raise EvolutionAuthorityError(
                "ATTESTOR_INDEPENDENCE_VIOLATION",
                f"attestor conflict role {role!r} must be a non-string sequence",
            )
        role_members = tuple(members)
        for member in role_members:
            if type(member) is not str or not member:
                raise EvolutionAuthorityError(
                    "ATTESTOR_INDEPENDENCE_VIOLATION",
                    f"attestor conflict role {role!r} must contain non-empty strings",
                )
        snapshot[role] = role_members

    _legacy_verify_attestor_independence(attestor_id, snapshot)
