"""Source integrity and license propagation (EF4-I37).

Contract source: `schemas/source-integrity-report.schema.json`.

`export_permitted` is separate from `trusted_for_extraction` on purpose. A licence
that allows reading a document for analysis very often forbids redistributing its
text, so a single "may we use this" boolean would let an extraction permission
authorize an export. The two are asked and answered separately, and a
`QUARANTINE` status blocks both.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.time import utc_now_iso

#: Integrity statuses that permit extraction at all.
EXTRACTABLE_STATUSES: frozenset[str] = frozenset({"PASS", "WARN"})

#: Per-check statuses from `source-integrity-report.schema.json`. Note that
#: `QUARANTINE` is an *overall* status only: an individual check reports FAIL and
#: the report escalates, so a single check cannot quarantine a document by itself.
CHECK_STATUSES: tuple[str, ...] = ("PASS", "WARN", "FAIL", "NOT_RUN")

#: Check names whose failure quarantines rather than merely fails. A content or
#: provenance failure means the document is not what it claims to be, which is a
#: different problem from a formatting warning.
QUARANTINING_CHECKS: frozenset[str] = frozenset(
    {"malware_scan", "provenance_verified", "tamper_evident"}
)

#: Licence classes that permit redistributing source text verbatim.
#: Anything absent from this set is treated as export-forbidden, because an
#: unrecognized licence is not a permissive one.
EXPORT_PERMISSIVE_LICENCES: frozenset[str] = frozenset(
    {"CC0", "CC-BY", "CC-BY-SA", "public-domain", "Apache-2.0", "MIT"}
)


class SourceAccessDenied(PermissionError):
    """An access or export was attempted outside the source's licence."""


def build_source_integrity_report(
    *,
    document_id: str,
    content_hash: str,
    checks: Sequence[Mapping[str, Any]],
    policy_version: str,
    report_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Build an integrity report with a derived status and extraction verdict.

    `overall_status` and `trusted_for_extraction` are derived from the checks: a
    caller-supplied status could declare a failing document trustworthy.
    """
    if not checks:
        raise SourceAccessDenied(
            f"document {document_id} has no integrity checks; an unchecked source is not "
            "trusted by default"
        )
    statuses = {str(check.get("status", "FAIL")) for check in checks}
    quarantined = any(
        str(check.get("status")) == "FAIL"
        and str(check.get("check_id")) in QUARANTINING_CHECKS
        for check in checks
    )
    if quarantined:
        overall = "QUARANTINE"
    elif "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "PASS"

    report: dict[str, Any] = {
        "report_id": report_id or f"SIR-{document_id}",
        "document_id": document_id,
        "content_hash": content_hash,
        "checks": [dict(check) for check in checks],
        "overall_status": overall,
        "trusted_for_extraction": overall in EXTRACTABLE_STATUSES,
        "evaluated_at": evaluated_at or utc_now_iso(),
        "policy_version": policy_version,
    }
    validate_artifact("source-integrity-report", report)
    return report


def export_permitted(
    report: Mapping[str, Any],
    *,
    licence: str,
    verbatim: bool,
) -> bool:
    """Whether this source's text may leave the system.

    Extraction permission does not imply export permission: many licences allow
    analysis while forbidding redistribution. A non-verbatim derivative (counts,
    embeddings, summaries) is permitted whenever extraction is, but verbatim text
    additionally requires a permissive licence.
    """
    if str(report.get("overall_status")) == "QUARANTINE":
        return False
    if not report.get("trusted_for_extraction"):
        return False
    if not verbatim:
        return True
    return licence in EXPORT_PERMISSIVE_LICENCES


def require_export_permitted(
    report: Mapping[str, Any],
    *,
    licence: str,
    verbatim: bool,
) -> None:
    """Raise `SourceAccessDenied` when an export is outside the licence."""
    if not export_permitted(report, licence=licence, verbatim=verbatim):
        detail = "verbatim text" if verbatim else "derived data"
        raise SourceAccessDenied(
            f"exporting {detail} from {report.get('document_id')} is not permitted under "
            f"licence {licence!r} with integrity status {report.get('overall_status')}"
        )


def deletion_propagates_to(
    document_id: str,
    derived_artifacts: Mapping[str, Sequence[str]],
) -> list[str]:
    """Artifacts that must be deleted when a source is withdrawn.

    Returned transitively: a retraction that removes the document but leaves its
    extracted spans and evidence in place has not honoured the deletion request.
    """
    seen: set[str] = set()
    frontier = list(derived_artifacts.get(document_id, ()))
    while frontier:
        current = str(frontier.pop())
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(str(child) for child in derived_artifacts.get(current, ()))
    return sorted(seen)
