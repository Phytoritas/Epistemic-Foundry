"""Terminal release, clean-extraction and truthful-maturity composition (Z06).

The terminal package of the v4 A-Z graph.  It composes the sealed Z05 zero-trust
release (read from its frozen sealed report) and the thirteen sealed ``*06``
integration gates into one fail-closed, deterministic terminal verdict: a declared
bundle is proven to clean-extract byte-identically and to refuse zip-slip,
tampered and surplus members; every source is held to the acceptance-matrix
maturity floor with completion never claimed and every executable/validated/
production-ready/signed claim refused; and Z05 plus the thirteen ``*06`` gates are
reconciled as sealed PASS with every remaining conditional owned.

It composes and refuses.  Nothing here builds, extracts, signs or ships a release,
scores, promotes, mutates its inputs, reads a clock, draws entropy or raises the
maturity floor: the release stays an UNVERIFIED reference bundle at the
``SPEC_BUNDLE`` floor, signing stays fail-closed UNSIGNED, and ``completion_ready``
stays false.  This gate proves the maturity is stated honestly; it does not
certify the product finished.
"""

from __future__ import annotations

from .truthful_release import (
    CLEAN_EXTRACTION_PREFIX,
    COMPOSED_Z05_PREFIX,
    FINDING_CODES,
    FORBIDDEN_MATURITY_CLAIMS,
    RELEASE_ACCOUNTING_PREFIX,
    TERMINAL_VERDICT_PREFIX,
    TRUTHFUL_MATURITY_PREFIX,
    TruthfulReleaseError,
    compose_sealed_z05,
    reconcile_release_accounting,
    require_clean_extraction,
    require_truthful_maturity,
    seal_truthful_release,
)

__all__ = [
    "CLEAN_EXTRACTION_PREFIX",
    "COMPOSED_Z05_PREFIX",
    "FINDING_CODES",
    "FORBIDDEN_MATURITY_CLAIMS",
    "RELEASE_ACCOUNTING_PREFIX",
    "TERMINAL_VERDICT_PREFIX",
    "TRUTHFUL_MATURITY_PREFIX",
    "TruthfulReleaseError",
    "compose_sealed_z05",
    "reconcile_release_accounting",
    "require_clean_extraction",
    "require_truthful_maturity",
    "seal_truthful_release",
]
