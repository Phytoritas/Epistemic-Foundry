"""Surrogate triage (EF4-I56).

Contract source: `schemas/surrogate-triage-report.schema.json`.

"A surrogate may prioritize direct evaluation but cannot replace required direct,
hidden or replication stages." The distinction is between *ordering* work and
*skipping* it. A surrogate that rejects candidates outright would decide outcomes
using a model that was itself fitted on past evaluations, so its errors would
never be discovered — the candidates that would have exposed them are the ones it
discarded.

`direct_evaluation_required` is therefore forced true, and the only rejection the
schema permits is `REJECT_ONLY_ON_HARD_GATE`, which is a deterministic gate result
rather than a surrogate judgment.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: An out-of-distribution score above this makes the surrogate's prediction
#: uninformative, so the candidate is sampled for calibration rather than ordered
#: by a number the model cannot support.
OOD_CALIBRATION_THRESHOLD = 0.7


class SurrogateOverreach(PermissionError):
    """A surrogate was used to replace a required stage."""


def build_surrogate_triage(
    *,
    candidate_id: str,
    surrogate_model_id: str,
    predicted_utility: float,
    predictive_uncertainty: float,
    ood_score: float,
    calibration_window_id: str,
    hard_gate_failed: bool = False,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Triage a candidate, deriving the decision and forcing direct evaluation.

    `triage_decision` and `direct_evaluation_required` are both derived. A caller
    able to set the latter false could use the surrogate to skip the hidden or
    replication stage entirely.
    """
    if hard_gate_failed:
        decision = "REJECT_ONLY_ON_HARD_GATE"
    elif ood_score > OOD_CALIBRATION_THRESHOLD:
        decision = "SAMPLE_FOR_CALIBRATION"
    elif predictive_uncertainty > 0.5:
        decision = "SAMPLE_FOR_CALIBRATION"
    elif predicted_utility >= 0.5:
        decision = "EVALUATE_NOW"
    else:
        decision = "DEFER"

    report: dict[str, Any] = {
        "report_id": report_id or new_id("STR"),
        "candidate_id": candidate_id,
        "surrogate_model_id": surrogate_model_id,
        "predicted_utility": float(predicted_utility),
        "predictive_uncertainty": float(predictive_uncertainty),
        "ood_score": float(ood_score),
        "triage_decision": decision,
        # Always true: a surrogate orders work, it never removes a stage.
        "direct_evaluation_required": True,
        "calibration_window_id": calibration_window_id,
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("surrogate-triage-report", report)
    return report


def require_direct_stage_intact(
    report: Mapping[str, Any],
    *,
    stage_class: str,
) -> None:
    """Raise when a surrogate result is used to skip a required stage.

    `holdout` and `replication` are named explicitly because those are the two
    stages a surrogate is most tempting to substitute for: they are the slowest and
    the most expensive.
    """
    if stage_class in {"holdout", "replication", "evidence"}:
        raise SurrogateOverreach(
            f"surrogate report {report.get('report_id')} cannot stand in for the {stage_class} "
            "stage; a surrogate fitted on past evaluations would never surface the errors that "
            "the candidates it discarded would have exposed"
        )


def defers_only(report: Mapping[str, Any]) -> bool:
    """True when this report only reorders work rather than removing it."""
    return bool(report.get("direct_evaluation_required"))
