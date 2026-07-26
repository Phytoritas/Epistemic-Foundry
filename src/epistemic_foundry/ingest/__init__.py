"""Intake gating and method comparability.

* EF4-I03 (falsifiable intake): an insight without scope, predictions, and a
  falsifier cannot enter Observe or Parliament. An unfalsifiable proposal cannot
  be wrong, so admitting it would spend evaluation budget on something no
  evidence could ever settle.
* EF4-I07 (method comparability): method-incompatible evidence is stratified and
  may impose a promotion ceiling; it is never silently pooled.
"""

from __future__ import annotations

from .intake import (
    IntakeRejected,
    admit_insight,
    intake_blockers,
)
from .comparability import (
    METHOD_CEILING,
    promotion_ceiling_for,
    stratify_by_method,
)

__all__ = [
    "IntakeRejected",
    "METHOD_CEILING",
    "admit_insight",
    "intake_blockers",
    "promotion_ceiling_for",
    "stratify_by_method",
]
