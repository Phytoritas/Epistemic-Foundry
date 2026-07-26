"""Prompt and evaluator mutation quarantine (EF4-I55, EF4-I56).

Contract sources: `schemas/prompt-mutation-proposal.schema.json` and
`schemas/evaluator-mutation-proposal.schema.json`.

Both invariants share one shape: a change to the machinery that judges candidates
is a *proposal for a future sealed run*, never an edit to the run in progress. An
evaluator defect discovered mid-run cannot rewrite the judgments already made,
because re-scoring completed candidates under a new evaluator is how a run
retroactively manufactures the outcome it wanted.

`retroactive_effect_prohibited` is therefore forced true rather than accepted from
the caller, and a proposal starts `QUARANTINED` regardless of what the caller
asks for.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Statuses in which a proposal may not influence any run.
INERT_STATUSES: frozenset[str] = frozenset({"QUARANTINED", "TESTING", "REJECTED"})

#: Defect classes from `evaluator-mutation-proposal.schema.json`. Naming them
#: here keeps a caller from inventing a class the qualification process has no
#: procedure for.
DEFECT_CLASSES: tuple[str, ...] = (
    "false_positive",
    "false_negative",
    "leakage",
    "metric_misalignment",
    "instability",
    "security",
    "coverage_gap",
)


class QuarantineViolation(PermissionError):
    """A mutation proposal was treated as an active change."""


def build_prompt_mutation_proposal(
    *,
    source_prompt_genome_id: str,
    proposed_prompt_genome_id: str,
    motivation: str,
    changed_sections: Sequence[str],
    risk_analysis: Sequence[str],
    qualification_plan_id: str,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Create a prompt mutation proposal, always quarantined.

    `status` is not a parameter: a proposal that could be born `APPROVED` would
    bypass the independent qualification the invariant requires.
    """
    if not changed_sections:
        raise QuarantineViolation(
            "a prompt mutation proposal must name the changed sections; an unspecified change "
            "cannot be qualified"
        )
    if not risk_analysis or not any(str(item).strip() for item in risk_analysis):
        raise QuarantineViolation(
            "a prompt mutation proposal requires a risk analysis; prompts shape what the "
            "evaluator sees, so an unanalyzed change is an unbounded one"
        )

    proposal: dict[str, Any] = {
        "proposal_id": proposal_id or new_id("PMP"),
        "source_prompt_genome_id": source_prompt_genome_id,
        "proposed_prompt_genome_id": proposed_prompt_genome_id,
        "motivation": motivation,
        "changed_sections": list(changed_sections),
        "risk_analysis": [str(item) for item in risk_analysis],
        "qualification_plan_id": qualification_plan_id,
        "status": "QUARANTINED",
    }
    proposal["proposal_hash"] = hash_excluding(proposal, "proposal_hash")
    validate_artifact("prompt-mutation-proposal", proposal)
    return proposal


def build_evaluator_mutation_proposal(
    *,
    source_run_id: str,
    current_evaluator_bundle_id: str,
    defect_class: str,
    evidence_artifact_ids: Sequence[str],
    proposed_change: str,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Record an evaluator defect as a future-run proposal.

    `retroactive_effect_prohibited` and `qualification_required` are both forced
    true. A caller able to set either false could re-score completed candidates
    under a changed evaluator, which is how a run retroactively manufactures its
    preferred outcome.
    """
    if not evidence_artifact_ids:
        raise QuarantineViolation(
            f"evaluator defect {defect_class} is claimed with no evidence artifacts; an "
            "unevidenced defect cannot justify changing the judge"
        )
    if defect_class not in DEFECT_CLASSES:
        raise QuarantineViolation(
            f"unknown evaluator defect class {defect_class!r}; the qualification process has no "
            f"procedure for it. Known classes: {list(DEFECT_CLASSES)}"
        )

    proposal: dict[str, Any] = {
        "proposal_id": proposal_id or new_id("EMP"),
        "source_run_id": source_run_id,
        "current_evaluator_bundle_id": current_evaluator_bundle_id,
        "defect_class": defect_class,
        "evidence_artifact_ids": list(evidence_artifact_ids),
        "proposed_change": proposed_change,
        "retroactive_effect_prohibited": True,
        "qualification_required": True,
        "status": "QUARANTINED",
    }
    proposal["proposal_hash"] = hash_excluding(proposal, "proposal_hash")
    validate_artifact("evaluator-mutation-proposal", proposal)
    return proposal


def may_influence_run(proposal: Mapping[str, Any]) -> bool:
    """Whether this proposal may affect any run at all.

    False for every inert status. Even `APPROVED` only authorizes a *new sealed
    run*, which `applies_to_completed_run` refuses separately.
    """
    return str(proposal.get("status")) not in INERT_STATUSES


def require_not_retroactive(
    proposal: Mapping[str, Any],
    *,
    target_run_id: str,
) -> None:
    """Raise when a proposal is applied to the run that produced it.

    Rewriting the judgments of a completed run is the specific abuse both
    invariants forbid, so the source run is refused as a target even after
    approval.
    """
    if str(proposal.get("source_run_id")) == target_run_id:
        raise QuarantineViolation(
            f"proposal {proposal.get('proposal_id')} cannot be applied to run {target_run_id}, "
            "the run that produced it; approved changes apply to new sealed runs and never "
            "rewrite completed judgments"
        )
    if not may_influence_run(proposal):
        raise QuarantineViolation(
            f"proposal {proposal.get('proposal_id')} is {proposal.get('status')} and may not "
            "influence any run"
        )
