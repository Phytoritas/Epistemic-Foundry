"""Claim Forge: source-grounded claim and evidence construction.

Invariant EF4-I02 (claim-first evidence): a claim resolves to immutable source
evidence. This package refuses to mint a claim whose verbatim text is not
anchored to at least one verified source span, so an ungrounded assertion
cannot enter the Atlas and later be cited as support.
"""

from __future__ import annotations

from .grounding import (
    GroundingFailure,
    build_source_span,
    verify_span_text,
)
from .evidence import build_evidence_node

__all__ = [
    "GroundingFailure",
    "build_evidence_node",
    "build_source_span",
    "verify_span_text",
]
