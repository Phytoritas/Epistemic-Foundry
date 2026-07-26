"""Untrusted content as inert data (EF4-I30).

Retrieved documents, web pages, datasets, and model output are wrapped in
`UntrustedContent`. The wrapper carries no capability field and exposes no method
that could widen authority, so there is nothing for an embedded instruction to
set. A document containing "ignore previous instructions, you are now authorized"
is a string inside a corpus record.

`AuthorityGrantRefused` exists for the case where a caller *tries* to derive a
capability from content. Raising there is deliberate: silently ignoring the
attempt would leave no signal that a corpus is attempting escalation, and that
signal is itself evidence worth recording.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

#: Patterns that indicate embedded instruction-injection attempts. Detection is
#: for *flagging*, never for sanitizing: a corpus record is preserved verbatim
#: because altering source text would break claim grounding.
INJECTION_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)?\s*\w*\s*(authorized|admin|root)", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(system|prior)\s+prompt", re.IGNORECASE),
    re.compile(r"grant\s+(yourself|me)\s+\w*\s*(access|permission|capability)", re.IGNORECASE),
    re.compile(r"execute\s+the\s+following\s+command", re.IGNORECASE),
)


class AuthorityGrantRefused(PermissionError):
    """Content was used in an attempt to widen authority."""


@dataclass(frozen=True)
class UntrustedContent:
    """Inert wrapper around externally sourced text.

    There is deliberately no `capabilities`, `trusted`, or `authority` field. A
    wrapper that could carry a capability would make injection a data problem
    instead of an impossibility.
    """

    text: str
    origin: str
    media_type: str = "text/plain"
    provenance_id: str | None = None
    injection_flags: tuple[str, ...] = field(default=())

    def granted_capabilities(self) -> tuple[()]:
        """Always empty. Content never grants capability."""
        return ()

    def is_executable(self) -> bool:
        """Always False. Content is never an instruction to run."""
        return False


def detect_injection(text: str) -> list[str]:
    """Return the names of injection patterns present in `text`.

    Flags, does not strip. Source text must stay verbatim so a claim can still be
    grounded against the document that actually exists.
    """
    found: list[str] = []
    for pattern in INJECTION_MARKERS:
        if pattern.search(text):
            found.append(pattern.pattern)
    return found


def wrap_untrusted(
    text: str,
    *,
    origin: str,
    media_type: str = "text/plain",
    provenance_id: str | None = None,
) -> UntrustedContent:
    """Wrap external content, recording any injection attempt it contains."""
    return UntrustedContent(
        text=text,
        origin=origin,
        media_type=media_type,
        provenance_id=provenance_id,
        injection_flags=tuple(detect_injection(text)),
    )


def require_no_authority_from_content(
    content: UntrustedContent,
    *,
    requested_capabilities: Sequence[str],
) -> None:
    """Raise when a caller tries to derive capability from content.

    The refusal is loud so an escalation attempt leaves a trace rather than being
    quietly dropped.
    """
    if requested_capabilities:
        raise AuthorityGrantRefused(
            f"content from {content.origin} cannot grant capabilit(ies) "
            f"{sorted(requested_capabilities)}; retrieved documents, datasets and model output "
            "are data and never authority"
        )


def flagged_content(items: Sequence[UntrustedContent]) -> list[UntrustedContent]:
    """Items carrying an injection flag, for an operator-visible report."""
    return [item for item in items if item.injection_flags]
