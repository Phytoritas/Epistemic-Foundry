"""The single typed failure surface for A05 promotion authority.

``EvolutionAuthorityError`` is declared once in :mod:`.registry` and re-exported
here so the promotion runtime modules share one exception type.  A second
exception class would let a caller catch one and miss the other, which is how a
fail-closed refusal quietly becomes a fallback.
"""

from __future__ import annotations

from .registry import EvolutionAuthorityError

__all__ = ["EvolutionAuthorityError"]
