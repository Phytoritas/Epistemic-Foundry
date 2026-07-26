"""Secrets as opaque handles (EF4-I29).

A secret is represented by a handle that carries a reference, never the value.
`SecretHandle.__repr__` and `__str__` both return the reference, so a secret
cannot leak through an f-string, a log line, a prompt, or a serialized artifact
by accident — the usual path by which credentials end up in a transcript.

`assert_no_secret_material` scans an outbound payload for known secret values
and for handle objects rendered incorrectly, and raises rather than redacting.
Silent redaction would hide the fact that a code path tried to send a secret.
"""

from __future__ import annotations

import json
from typing import Any, Iterable


class SecretLeak(RuntimeError):
    """Secret material was found in an outbound payload."""


class SecretHandle:
    """An opaque reference to a secret held outside the process.

    The value is never stored on the instance. A handle resolves through an
    external provider at use time, so there is nothing on the object for a
    serializer to find.
    """

    __slots__ = ("_reference", "_provider")

    def __init__(self, reference: str, provider: str = "env") -> None:
        if not reference.strip():
            raise ValueError("a secret handle requires a non-empty reference")
        self._reference = reference
        self._provider = provider

    @property
    def reference(self) -> str:
        return self._reference

    @property
    def provider(self) -> str:
        return self._provider

    def __repr__(self) -> str:
        return f"SecretHandle(provider={self._provider!r}, reference={self._reference!r})"

    def __str__(self) -> str:
        return f"<secret:{self._provider}:{self._reference}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretHandle):
            return NotImplemented
        return (self._reference, self._provider) == (other._reference, other._provider)

    def __hash__(self) -> int:
        return hash((self._reference, self._provider))


def _render(payload: Any) -> str:
    """Serialize a payload the way an outbound channel would."""
    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)


def assert_no_secret_material(
    payload: Any,
    *,
    known_secret_values: Iterable[str] = (),
) -> None:
    """Raise `SecretLeak` when a secret value appears in `payload`.

    Raising beats redacting: a silent redaction would let a code path keep
    attempting to send secrets while the output looks clean.
    """
    rendered = _render(payload)
    for value in known_secret_values:
        text = str(value)
        if not text.strip():
            continue
        if text in rendered:
            raise SecretLeak(
                f"outbound payload contains secret material (length {len(text)}); secrets must "
                "travel as opaque handles, never as values"
            )


def handle_is_opaque(handle: SecretHandle, secret_value: str) -> bool:
    """True when neither rendering of the handle exposes the value."""
    return secret_value not in repr(handle) and secret_value not in str(handle)
