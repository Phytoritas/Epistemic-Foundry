"""Role separation and evidence-class integrity.

* EF4-I11 (evidence-class separation): simulation, formal derivation, benchmark,
  and review-derived evidence never become empirical observation by relabeling.
  An upgrade across the empirical boundary is refused; a downgrade is honest and
  allowed.
* EF4-I12 (no self-approval): makers cannot approve their own work, claim
  promotion, validation, or release. Self-approval is the cheapest way to bypass
  every other gate, so the check is on actor identity rather than on declared
  role.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..domain.vocabularies import (
    EMPIRICAL_EVIDENCE_CLASSES,
    NON_EMPIRICAL_EVIDENCE_CLASSES,
)

#: Evidence classes that record direct empirical observation.
EMPIRICAL_CLASSES = EMPIRICAL_EVIDENCE_CLASSES

#: Classes that are derived, simulated, formal, or secondhand. Promoting one of
#: these into an empirical class is relabeling, not reclassification. Derived
#: from the shared vocabulary so a new evidence class cannot be silently absent
#: from this boundary.
NON_EMPIRICAL_CLASSES = NON_EMPIRICAL_EVIDENCE_CLASSES


class SelfApprovalRefused(PermissionError):
    """An actor attempted to approve work it authored."""


class RelabelingRefused(ValueError):
    """An evidence class change would launder derived evidence as empirical."""


def require_independent_approval(
    *,
    author_ids: Sequence[str],
    approver_id: str,
    subject: str = "work package",
) -> None:
    """Raise `SelfApprovalRefused` when the approver authored the subject."""
    authors = {str(item) for item in author_ids}
    if str(approver_id) in authors:
        raise SelfApprovalRefused(
            f"{approver_id} authored this {subject} and cannot approve it; independent review "
            "is what makes every other gate meaningful"
        )
    if not authors:
        raise SelfApprovalRefused(
            f"cannot verify independence for this {subject}: no author is recorded"
        )


def require_no_empirical_relabeling(from_class: str, to_class: str) -> None:
    """Refuse a class change that crosses into empirical territory.

    A downgrade (empirical -> modeling) is a legitimate correction, and a change
    within a tier is fine. Only the upgrade is refused, because that is the one
    that manufactures observational standing the evidence never had.
    """
    if from_class == to_class:
        return
    if from_class in NON_EMPIRICAL_CLASSES and to_class in EMPIRICAL_CLASSES:
        raise RelabelingRefused(
            f"refusing to reclassify {from_class} evidence as {to_class}: simulation, formal "
            "derivation, benchmark and review evidence do not become empirical observation by "
            "relabeling"
        )


def approval_is_independent(record: Mapping[str, Any]) -> bool:
    """Non-raising check over an approval record carrying author and approver."""
    try:
        require_independent_approval(
            author_ids=record.get("author_ids", []),
            approver_id=str(record.get("approver_id", "")),
        )
    except SelfApprovalRefused:
        return False
    return True
