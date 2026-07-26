"""Passport construction and staleness.

Contract source: `schemas/hypothesis-passport.schema.json`.

The schema keeps four orthogonal status axes. This module refuses the
combinations that would collapse them:

* `CONTRADICTED` or `UNDERDETERMINED` evidence cannot carry a promotion level
  above `CANDIDATE`. Promotion is not a summary of enthusiasm.
* `novelty_status` never raises the epistemic status. A `CORPUS_NOVEL` result
  with `UNDERDETERMINED` support stays underdetermined — novelty is not truth.
* A passport with unresolved objections cannot claim `ENTAILED`.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact

#: Promotion levels ordered from triage to fully replicated.
PROMOTION_ORDER: tuple[str, ...] = (
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
)

#: Epistemic statuses that cannot support advancement beyond CANDIDATE.
NON_ADVANCING_EPISTEMIC_STATUSES = frozenset(
    {"CONTRADICTED", "UNDERDETERMINED", "UNTESTABLE"}
)


class PassportViolation(ValueError):
    """A passport reports a status combination the contract forbids."""


def _rank(level: str) -> int:
    try:
        return PROMOTION_ORDER.index(level)
    except ValueError as exc:  # pragma: no cover - schema enum guards this
        raise PassportViolation(f"unknown promotion level {level!r}") from exc


def status_dimensions_are_independent(
    *,
    epistemic_status: str,
    novelty_status: str,
    promotion_level: str,
    unresolved_objection_ids: Sequence[str],
) -> bool:
    """False when one axis has been allowed to inflate another."""
    if epistemic_status in NON_ADVANCING_EPISTEMIC_STATUSES and _rank(promotion_level) > _rank("CANDIDATE"):
        return False
    if unresolved_objection_ids and epistemic_status == "ENTAILED":
        return False
    return True


def build_passport(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a passport against the schema and the independence rules.

    The passport has 28 required fields, so this takes a payload rather than 28
    keyword arguments: a wrapper enumerating them would drift from the schema at
    the first contract revision.
    """
    record = dict(payload)
    validate_artifact("hypothesis-passport", record)

    if not status_dimensions_are_independent(
        epistemic_status=str(record["epistemic_status"]),
        novelty_status=str(record["novelty_status"]),
        promotion_level=str(record["promotion_level"]),
        unresolved_objection_ids=record.get("unresolved_objection_ids", []),
    ):
        raise PassportViolation(
            f"status combination collapses independent axes: epistemic_status "
            f"{record['epistemic_status']} with promotion_level {record['promotion_level']} "
            f"and {len(record.get('unresolved_objection_ids', []))} unresolved objection(s)"
        )
    return record


def mark_stale(passport: Mapping[str, Any], reasons: Sequence[str]) -> dict[str, Any]:
    """Return a stale copy carrying explicit reasons.

    Staleness without a reason is indistinguishable from a bug, so an empty
    reason list is refused. The promotion level is deliberately preserved: the
    passport records what was concluded and that the conclusion no longer holds,
    rather than rewriting history.
    """
    if not reasons:
        raise PassportViolation(
            "marking a passport stale requires at least one reason; unexplained staleness "
            "is indistinguishable from a bug"
        )
    record = dict(passport)
    record["lifecycle_status"] = "stale"
    record["stale_reasons"] = list(reasons)
    validate_artifact("hypothesis-passport", record)
    return record


def is_reportable(passport: Mapping[str, Any]) -> bool:
    """True only for an active passport.

    Stale, withdrawn, and superseded passports must not be presented as current
    findings.
    """
    return str(passport.get("lifecycle_status")) == "active"
