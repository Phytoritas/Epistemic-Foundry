"""Timestamp helpers.

Canonical schemas require RFC 3339 `date-time`. A naive local timestamp is
rejected here rather than silently serialized, because an offset-less time in
a receipt makes the audit trail ambiguous.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Current UTC time as RFC 3339 with an explicit `+00:00` offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_iso(moment: datetime) -> str:
    """Serialize an aware datetime; refuse naive input."""
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError("refusing to serialize a naive datetime into a receipt")
    return moment.isoformat(timespec="seconds")
