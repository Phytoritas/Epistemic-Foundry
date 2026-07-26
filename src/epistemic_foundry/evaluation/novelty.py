"""Novelty assessment that never defaults to novel (EF4-I47).

Contract source: `schemas/novelty-assessment.schema.json`.

`assess_novelty` derives the status from search completeness rather than from the
absence of hits. This is the crux: "we searched thoroughly and found no prior
art" and "our search failed" both produce an empty result set, and only the first
supports a novelty claim. So an incomplete, blocked, or unassessed search yields
`NOT_ASSESSED`, and a search with unsearched sources remaining yields
`SEARCH_CONDITIONAL` rather than a bare novelty verdict.

The promotion ceiling is derived alongside the status, so a weak assessment
cannot be paired with a strong claim downstream.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Novelty statuses that permit any novelty claim at all.
CLAIMABLE_NOVELTY: frozenset[str] = frozenset(
    {"CORPUS_NOVEL_ONLY", "SEARCH_CONDITIONAL", "POTENTIALLY_NOVEL"}
)

#: Search completeness values from `coverage-snapshot`/`hypothesis-passport`.
COMPLETE_SEARCH = "COMPLETE_FOR_POLICY"


class NoveltyAssessmentRefused(ValueError):
    """A novelty assessment is internally inconsistent."""


def assess_novelty(
    *,
    run_id: str,
    subject_ref: str,
    statement_hash: str,
    corpus_snapshot_hash: str,
    search_completeness_certificate_id: str,
    searched_sources: Sequence[str],
    unsearched_sources: Sequence[str],
    closest_prior_art_refs: Sequence[str],
    distinguishing_features: Sequence[str],
    novelty_dimensions: Sequence[str],
    limitations: Sequence[str],
    search_cutoff: str,
    assessor_ref: str,
    search_completeness: str,
    assessment_id: str | None = None,
    assessed_at: str | None = None,
) -> dict[str, Any]:
    """Derive a novelty status and ceiling from the search that was actually run.

    `novelty_status` is never a parameter. Letting a caller pass it in is exactly
    how an unassessed subject acquires a novelty label.
    """
    if not searched_sources:
        status = "NOT_ASSESSED"
        ceiling = "NO_NOVELTY_CLAIM"
    elif closest_prior_art_refs and not distinguishing_features:
        # Prior art found and nothing distinguishes this subject from it.
        status = "KNOWN_PRIOR_ART"
        ceiling = "NO_NOVELTY_CLAIM"
    elif search_completeness != COMPLETE_SEARCH:
        status = "NOT_ASSESSED"
        ceiling = "NO_NOVELTY_CLAIM"
    elif unsearched_sources:
        status = "SEARCH_CONDITIONAL"
        ceiling = "SEARCH_CONDITIONAL"
    elif closest_prior_art_refs:
        status = "CORPUS_NOVEL_ONLY"
        ceiling = "CORPUS_ONLY"
    else:
        status = "POTENTIALLY_NOVEL"
        ceiling = "ELIGIBLE_FOR_HUMAN_REVIEW"

    assessment: dict[str, Any] = {
        "assessment_id": assessment_id or new_id("NA"),
        "run_id": run_id,
        "subject_ref": subject_ref,
        "statement_hash": statement_hash,
        "corpus_snapshot_hash": corpus_snapshot_hash,
        "search_completeness_certificate_id": search_completeness_certificate_id,
        "novelty_status": status,
        "novelty_dimensions": list(novelty_dimensions),
        "closest_prior_art_refs": list(closest_prior_art_refs),
        "distinguishing_features": list(distinguishing_features),
        "searched_sources": list(searched_sources),
        "unsearched_sources": list(unsearched_sources),
        "search_cutoff": search_cutoff,
        "limitations": list(limitations),
        "promotion_ceiling": ceiling,
        "assessor_ref": assessor_ref,
        "assessed_at": assessed_at or utc_now_iso(),
    }
    assessment["assessment_hash"] = hash_excluding(assessment, "assessment_hash")
    validate_artifact("novelty-assessment", assessment)
    return assessment


def novelty_supports_claim(assessment: Mapping[str, Any]) -> bool:
    """True only for a status that permits stating novelty at all.

    `NOT_ASSESSED` and `KNOWN_PRIOR_ART` return False. Novelty is not truth in any
    case, so even True here only means the claim is statable, not supported.
    """
    return str(assessment.get("novelty_status")) in CLAIMABLE_NOVELTY


def unconditional_novelty(assessment: Mapping[str, Any]) -> bool:
    """True only for a complete search with no remaining unsearched sources."""
    return str(assessment.get("novelty_status")) == "POTENTIALLY_NOVEL"
