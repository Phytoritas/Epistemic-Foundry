"""Public O04 absence-claim and completeness-gate API."""

from .contracts import (
    ABSENCE_CEILINGS,
    CLAIM_CLASSES,
    CLAIM_KINDS,
    IGNORANCE_STATES,
    NOVELTY_CEILINGS,
    ZERO_EVIDENCE_STATES,
    CompletenessGateError,
    SealedArtifact,
    assert_pack_consistent_with_ignorance,
    lane_evidence_classification,
    seal_absence_claim,
    validate_absence_claim,
    zero_evidence_report,
)

__all__ = [
    "ABSENCE_CEILINGS",
    "CLAIM_CLASSES",
    "CLAIM_KINDS",
    "IGNORANCE_STATES",
    "NOVELTY_CEILINGS",
    "ZERO_EVIDENCE_STATES",
    "CompletenessGateError",
    "SealedArtifact",
    "assert_pack_consistent_with_ignorance",
    "lane_evidence_classification",
    "seal_absence_claim",
    "validate_absence_claim",
    "zero_evidence_report",
]
