"""Evolution-promotion Parliament, Red Queen and minority-lineage gate (P05).

The gate convenes a sealed candidate's multi-dimensional promotion docket — the
Parliament adjudication, preserved minority dissent, Red Queen adversarial
evidence, the Q05 statistical clearance, an intact lineage, and a
replication-bounded ceiling — and decides whether it may be forwarded to the
promotion authority.  It never promotes: promotion authority lives in
:mod:`epistemic_foundry.governance.promotion`, and
:func:`parliament_grants_promotion` records that in one place.
"""

from __future__ import annotations

from .gate import (
    CONVENE,
    FINDING_CODES,
    GATE_NAME,
    WITHHOLD,
    PromotionParliamentWithheld,
    SchemaNotFound,
    derive_promotion_parliament,
    evaluate_promotion_parliament,
    parliament_grants_promotion,
    replication_blocking_effect,
)

__all__ = [
    "CONVENE",
    "FINDING_CODES",
    "GATE_NAME",
    "PromotionParliamentWithheld",
    "SchemaNotFound",
    "WITHHOLD",
    "derive_promotion_parliament",
    "evaluate_promotion_parliament",
    "parliament_grants_promotion",
    "replication_blocking_effect",
]
