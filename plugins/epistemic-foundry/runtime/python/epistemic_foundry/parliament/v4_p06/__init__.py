"""No-majority promotion and sealed-candidate attestation referral gate (P06).

The gate composes two already-sealed decision organs — the P05 evolution-promotion
Parliament and the V05 validation cascade — with an independent sealed-candidate
attestation, and decides whether a sealed candidate may be *referred* to the
promotion authority.  A referral is refused unless both organs independently
cleared the candidate, the convened docket preserved its dissent, and the
attestation chain passed and covered both organ receipts, so a promotion can
never be reduced to a single score or a bare majority.  It never promotes:
promotion authority lives in :mod:`epistemic_foundry.governance.promotion`, and
:func:`gate_grants_promotion` records that in one place.
"""

from __future__ import annotations

from .gate import (
    FINDING_CODES,
    GATE_NAME,
    REFER,
    WITHHOLD,
    NoMajorityPromotionWithheld,
    SchemaNotFound,
    attestation_pass_status,
    derive_promotion_referral,
    evaluate_promotion_referral,
    gate_grants_promotion,
)

__all__ = [
    "FINDING_CODES",
    "GATE_NAME",
    "NoMajorityPromotionWithheld",
    "REFER",
    "SchemaNotFound",
    "WITHHOLD",
    "attestation_pass_status",
    "derive_promotion_referral",
    "evaluate_promotion_referral",
    "gate_grants_promotion",
]
