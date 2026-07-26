"""Selective inference and the winner's curse.

Contract source: `schemas/selective-inference-report.schema.json`.

A candidate reaches promotion review *because* its estimate was extreme. That
selection is itself information: among many noisy estimates, the largest is
expected to overstate the true effect. So the naive estimate is biased upward by
construction, and `build_selective_inference_report` refuses to record a
bias-corrected estimate that exceeds the naive one — a "correction" that moves
the estimate away from the null is not a correction.

`winner_curse_risk_for` derives risk from the selection pressure actually applied
rather than accepting a caller's assessment, because the party reporting the
result is the one with an interest in calling the risk low.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Recommendations that permit advancement without further evidence.
PERMISSIVE_RECOMMENDATIONS: frozenset[str] = frozenset({"ALLOW"})


class SelectiveInferenceRefused(ValueError):
    """A selective-inference report is internally inconsistent."""


def winner_curse_risk_for(
    *,
    candidates_considered: int,
    selection_events: int,
    replication_count: int,
) -> str:
    """Derive winner's-curse risk from the selection pressure applied.

    Replication is the only thing that genuinely reduces the risk: an independent
    repeat of the measurement is not subject to the selection that produced the
    original estimate. Absent replication, more candidates and more selection
    steps mean more upward bias.
    """
    if candidates_considered <= 0:
        return "unknown"
    if replication_count >= 2:
        return "low"
    if candidates_considered <= 5 and selection_events <= 1:
        return "low" if replication_count >= 1 else "medium"
    if candidates_considered > 50 or selection_events > 3:
        return "high"
    return "medium"


def build_selective_inference_report(
    *,
    candidate_id: str,
    selection_mechanism: str,
    selection_events: Sequence[str],
    naive_estimate: float,
    bias_corrected_estimate: float,
    correction_method: str,
    uncertainty_interval: Sequence[float],
    candidates_considered: int,
    replication_count: int = 0,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Record a selection-aware estimate with a derived risk and recommendation.

    `winner_curse_risk` and `promotion_recommendation` are both derived. Letting a
    caller supply them would let the party that selected the candidate also grade
    the bias its selection introduced.
    """
    if abs(bias_corrected_estimate) > abs(naive_estimate) + 1e-12:
        raise SelectiveInferenceRefused(
            f"bias-corrected estimate {bias_corrected_estimate} exceeds the naive estimate "
            f"{naive_estimate} in magnitude; a correction that moves the estimate away from the "
            "null is not a correction"
        )
    if not correction_method.strip():
        raise SelectiveInferenceRefused(
            "a selective-inference report must name its correction method; an unnamed correction "
            "cannot be reproduced or challenged"
        )

    risk = winner_curse_risk_for(
        candidates_considered=candidates_considered,
        selection_events=len(selection_events),
        replication_count=replication_count,
    )
    if risk == "low":
        recommendation = "ALLOW"
    elif risk == "medium":
        recommendation = "REPLICATE_FIRST"
    elif risk == "high":
        recommendation = "REPLICATE_FIRST" if replication_count else "BLOCK"
    else:
        recommendation = "BLOCK"

    report: dict[str, Any] = {
        "report_id": report_id or new_id("SIR"),
        "candidate_id": candidate_id,
        "selection_mechanism": selection_mechanism,
        "selection_events": [str(event) for event in selection_events],
        "naive_estimate": float(naive_estimate),
        "bias_corrected_estimate": float(bias_corrected_estimate),
        "correction_method": correction_method,
        "uncertainty_interval": [float(bound) for bound in uncertainty_interval],
        "winner_curse_risk": risk,
        "promotion_recommendation": recommendation,
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("selective-inference-report", report)
    return report


def permits_promotion_without_replication(report: Mapping[str, Any]) -> bool:
    """True only for an ALLOW recommendation."""
    return str(report.get("promotion_recommendation")) in PERMISSIVE_RECOMMENDATIONS
