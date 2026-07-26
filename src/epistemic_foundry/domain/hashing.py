"""Deterministic canonicalization and hashing.

Every canonical schema that carries a `*_hash` field pins the format
`^sha256:[0-9a-f]{64}$`. Replay, receipt verification, and the ledger hash
chain are only meaningful if two runs over equal content produce byte-equal
digests, so canonicalization is fixed here once: sorted keys, no insignificant
whitespace, UTF-8, and no NaN/Infinity (JSON has no such literals, and
accepting them would make a digest unreproducible across parsers).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SHA256_PREFIX = "sha256:"


def canonical_json(payload: Any) -> bytes:
    """Serialize `payload` to the one canonical byte form used for hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the schema-shaped digest (`sha256:<64 lowercase hex>`)."""
    return f"{SHA256_PREFIX}{hashlib.sha256(data).hexdigest()}"


def sha256_of_payload(payload: Any) -> str:
    """Canonicalize then hash; the pairing used by every receipt writer."""
    return sha256_hex(canonical_json(payload))


def is_schema_digest(value: object) -> bool:
    """True when `value` matches the canonical digest shape."""
    if not isinstance(value, str) or not value.startswith(SHA256_PREFIX):
        return False
    hex_part = value[len(SHA256_PREFIX) :]
    return len(hex_part) == 64 and all(char in "0123456789abcdef" for char in hex_part)


def hash_excluding(payload: dict[str, Any], *exclude: str) -> str:
    """Digest a record while omitting self-referential hash fields.

    A record cannot contain its own digest, so `receipt_hash`, `event_hash`,
    and `state_hash` are computed over the record with that field removed.
    """
    reduced = {key: value for key, value in payload.items() if key not in exclude}
    return sha256_of_payload(reduced)
