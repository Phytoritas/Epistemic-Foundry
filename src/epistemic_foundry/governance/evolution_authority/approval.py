"""A05 self-approval input validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .registry import (
    EvolutionAuthorityError,
    verify_approval_independence as _legacy_verify_approval_independence,
)


def verify_approval_independence(
    approver_id: str, maker_ids: Sequence[str]
) -> None:
    """Reject malformed maker collections and maker self-approval."""

    if type(approver_id) is not str or not approver_id:
        raise EvolutionAuthorityError(
            "SELF_APPROVAL_FORBIDDEN", "approver identity is missing"
        )
    if isinstance(maker_ids, (str, bytes, bytearray, Mapping)) or not isinstance(
        maker_ids, Sequence
    ):
        raise EvolutionAuthorityError(
            "SELF_APPROVAL_FORBIDDEN",
            "maker identities must be a non-string sequence",
        )

    makers = tuple(maker_ids)
    if not makers:
        raise EvolutionAuthorityError(
            "SELF_APPROVAL_FORBIDDEN",
            "maker identities must be explicitly present and non-empty",
        )
    for maker_id in makers:
        if type(maker_id) is not str or not maker_id:
            raise EvolutionAuthorityError(
                "SELF_APPROVAL_FORBIDDEN",
                "maker identities must contain non-empty strings",
            )

    _legacy_verify_approval_independence(approver_id, makers)
