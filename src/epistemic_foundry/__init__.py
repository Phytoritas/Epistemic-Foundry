"""Epistemic Foundry v4 runtime.

Authority order (MASTER_SPEC.md > manifests/* > schemas/workflows > roles >
AGENTS.md) is a product invariant, not a convention: nothing in this package
may widen a contract defined by a canonical schema.

Maturity: the modules here are `IMPLEMENTED` only for the capabilities whose
tests pass under `tests/`. Everything else in the v4 bundle stays `SPECIFIED`
or `REFERENCE_BLUEPRINT`. See `docs/status_taxonomy.md`.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "4.0.0"
