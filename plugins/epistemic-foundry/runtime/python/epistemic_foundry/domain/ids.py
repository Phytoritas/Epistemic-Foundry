"""Identifier minting.

Canonical schemas bound most ids to 3..128 characters, so the prefix plus a
hex suffix is kept short. Ids are opaque: nothing in the runtime may parse
meaning out of an id, because that would make the id a hidden contract.
"""

from __future__ import annotations

import secrets

MIN_ID_LENGTH = 3
MAX_ID_LENGTH = 128


def new_id(prefix: str, *, entropy_bytes: int = 8) -> str:
    """Return `<prefix>-<hex>`; raises when the shape would break a schema."""
    cleaned = prefix.strip()
    if not cleaned:
        raise ValueError("id prefix must be non-empty")
    if entropy_bytes < 4:
        raise ValueError("entropy_bytes must be >= 4 to keep ids collision-safe")
    candidate = f"{cleaned}-{secrets.token_hex(entropy_bytes)}"
    if not MIN_ID_LENGTH <= len(candidate) <= MAX_ID_LENGTH:
        raise ValueError(
            f"minted id length {len(candidate)} outside schema bounds "
            f"{MIN_ID_LENGTH}..{MAX_ID_LENGTH}"
        )
    return candidate
