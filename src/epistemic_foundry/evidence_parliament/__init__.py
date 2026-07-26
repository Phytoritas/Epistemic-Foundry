"""Evidence Parliament: adjudication under deterministic hard gates.

Invariants enforced here:

* EF4-I09 (no majority authority): a vote cannot promote. The Parliament issues
  a recommendation; the promotion authority in `governance` decides.
* A deliberative verdict may never override a failed deterministic gate. An
  attempted override is recorded on the artifact rather than silently dropped,
  so the audit trail keeps the attempt.
* Minority reports and unresolved issues stay attached. Suppressing dissent to
  produce a clean verdict is the failure mode this component exists to prevent.
"""

from __future__ import annotations

from .adjudication import (
    GateOverrideAttempted,
    build_adjudication,
    recommendation_is_binding,
)

__all__ = [
    "GateOverrideAttempted",
    "build_adjudication",
    "recommendation_is_binding",
]
