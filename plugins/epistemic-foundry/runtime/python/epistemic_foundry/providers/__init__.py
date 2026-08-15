"""Untrusted-content handling and provider neutrality.

* EF4-I30: PDFs, web pages, datasets, and model output are data. They cannot
  grant authority or execute instructions. This is the prompt-injection
  boundary: a retrieved document that says "you are now authorized" is a string
  in a corpus, not a permission change.
* EF4-I34: Codex, Claude, and other models are replaceable node executors, and
  adapters cannot alter canonical semantics.
"""

from __future__ import annotations

from .untrusted import (
    AuthorityGrantRefused,
    UntrustedContent,
    wrap_untrusted,
)
from .neutrality import ProviderSemanticsViolation, assert_semantics_preserved

__all__ = [
    "AuthorityGrantRefused",
    "ProviderSemanticsViolation",
    "UntrustedContent",
    "assert_semantics_preserved",
    "wrap_untrusted",
]
