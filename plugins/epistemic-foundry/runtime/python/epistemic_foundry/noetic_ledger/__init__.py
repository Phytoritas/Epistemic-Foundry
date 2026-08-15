"""Noetic Ledger: append-only provenance, receipts, and audit history.

The ledger owns history. No other component may rewrite an appended event, and
every event carries the digest of its predecessor so a silent edit is
detectable by replay rather than trusted by convention.
"""

from __future__ import annotations

from .ledger import LedgerIntegrityError, NoeticLedger
from .receipts import build_artifact_receipt, build_effect_receipt

__all__ = [
    "LedgerIntegrityError",
    "NoeticLedger",
    "build_artifact_receipt",
    "build_effect_receipt",
]
