"""Replay verification (EF4-I39).

Contract source: `schemas/replay-report.schema.json`.

`event_equivalence` and `drift_classification` are both derived. The rule that
matters: an unavailable pin makes the run `NOT_COMPARABLE`, not equivalent. A
replay that could not load the original model, prompt, or corpus snapshot has not
demonstrated reproducibility — it has demonstrated that the comparison could not
be made, and reporting that as success is how a run acquires a reproducibility
claim it never earned.

`replay_reproduced` accepts only `EXACT` in strict mode. Semantic equivalence is a
weaker claim and is reported as such rather than folded into reproduction.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Pin categories that must all resolve for a run to be comparable at all.
REQUIRED_PIN_CATEGORIES: tuple[str, ...] = (
    "run_spec",
    "context",
    "model",
    "tools",
    "policy",
    "corpus",
    "prompts",
)

#: Drift causes, in the order they are attributed when several are present.
#: Corpus and ontology precede model because a changed corpus explains a changed
#: answer more directly than a changed model does.
DRIFT_PRECEDENCE: tuple[str, ...] = ("CORPUS", "ONTOLOGY", "POLICY", "PROMPT", "MODEL", "WORKFLOW")


class ReplayVerificationFailed(RuntimeError):
    """A replay report cannot support the claim being made from it."""


def missing_pin_categories(pinned_artifacts: Sequence[str]) -> list[str]:
    """Required pin categories absent from the replay inputs.

    Pins are recorded as opaque identifiers, so a category counts as present when
    a pin names it. This keeps the check useful without inventing a structure the
    schema does not define.
    """
    joined = " ".join(str(pin) for pin in pinned_artifacts)
    return sorted(name for name in REQUIRED_PIN_CATEGORIES if name not in joined)


def build_replay_report(
    *,
    source_run_id: str,
    replay_run_id: str,
    mode: str,
    pinned_artifacts: Sequence[str],
    unavailable_pins: Sequence[str],
    artifact_hash_matches: int,
    artifact_hash_mismatches: int,
    gate_differences: Sequence[str],
    verdict_differences: Sequence[str],
    drift_causes: Sequence[str] = (),
    replay_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a replay report with derived equivalence and drift.

    Neither `event_equivalence` nor `drift_classification` is a parameter: the
    party running the replay must not also grade whether it reproduced.

    `artifact_hash_matches` and `artifact_hash_mismatches` are counts per the
    schema; a non-zero mismatch count is drift regardless of how many matched.
    """
    if unavailable_pins:
        equivalence = "NOT_COMPARABLE"
    elif int(artifact_hash_mismatches) > 0 or verdict_differences:
        equivalence = "DRIFT"
    elif gate_differences:
        # Gates agreed in outcome but differed in detail; the run is not exact.
        equivalence = "SEMANTICALLY_EQUIVALENT" if mode == "semantic" else "DRIFT"
    else:
        equivalence = "EXACT"

    if equivalence in {"EXACT", "NOT_COMPARABLE"}:
        drift = "NONE" if equivalence == "EXACT" else "UNKNOWN"
    else:
        named = [cause for cause in DRIFT_PRECEDENCE if cause in set(drift_causes)]
        if not named:
            drift = "UNKNOWN"
        elif len(named) > 1:
            drift = "MULTIPLE"
        else:
            drift = named[0]

    report: dict[str, Any] = {
        "replay_id": replay_id or new_id("RR"),
        "source_run_id": source_run_id,
        "replay_run_id": replay_run_id,
        "mode": mode,
        "pinned_artifacts": list(pinned_artifacts),
        "unavailable_pins": list(unavailable_pins),
        "event_equivalence": equivalence,
        "artifact_hash_matches": int(artifact_hash_matches),
        "artifact_hash_mismatches": int(artifact_hash_mismatches),
        "gate_differences": list(gate_differences),
        "verdict_differences": list(verdict_differences),
        "drift_classification": drift,
        "created_at": created_at or utc_now_iso(),
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("replay-report", report)
    return report


def replay_reproduced(report: Mapping[str, Any]) -> bool:
    """True only for an exact replay.

    `SEMANTICALLY_EQUIVALENT` is a weaker claim reported separately, and
    `NOT_COMPARABLE` is the absence of a comparison rather than a negative result.
    """
    return str(report.get("event_equivalence")) == "EXACT"


def require_comparable(report: Mapping[str, Any]) -> None:
    """Raise when a report is used to support a claim it cannot bear."""
    if str(report.get("event_equivalence")) == "NOT_COMPARABLE":
        raise ReplayVerificationFailed(
            f"replay {report.get('replay_id')} could not resolve pins "
            f"{report.get('unavailable_pins')}; an unmade comparison is not a reproduction"
        )
