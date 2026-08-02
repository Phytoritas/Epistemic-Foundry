"""E05 candidate action/effect, mutation receipt and count-reconciliation engine.

The chamber already reconciles candidate identities across the pipeline, and the
ledger already mints effect and mutation receipts.  What no one reconciles is the
two against each other, and that gap is where a side effect hides: the chamber
reports eight candidates persisted, the ledger holds nine effect receipts, and
nothing notices that one effect belongs to no candidate at all.

So this engine performs the three-way reconciliation E05 owns.  It is deliberately
composed rather than reimplemented: candidate accounting comes from
``evolution_chamber.reconciliation``, receipt shapes from ``noetic_ledger.receipts``
and ``evolution_chamber.mutation``, and the effect-status vocabulary is imported
from the module that declares it.  This module holds no canonical schema enum value
as a string literal (EF4-I22); the status-to-disposition table lives beside it as
data and is verified to cover the imported vocabulary exactly on every use, so a
status added to the contract fails loudly here instead of falling through.

Three failures are refused rather than reported as counts.  An effect receipt whose
intent names no proposed candidate is an orphan side effect.  A candidate the
ledger says persisted while the chamber says vanished is a silent partial fan-in.
An ``UNKNOWN`` effect leaves its candidate unresolved, and an unresolved candidate
may not be counted as reconciled no matter how the caller labels it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, get_args

from ...evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
    reconcile_candidates,
)
from ...noetic_ledger.receipts import EffectStatus

#: The status-to-disposition table, kept as data so this module stays literal-free.
DISPOSITION_PATH: Final = Path(__file__).with_name("effect-disposition.json")
#: Fields an effect receipt must carry for this engine to account for it.  These
#: are field names, not wire values, so naming them here declares no vocabulary.
_EFFECT_FIELDS: Final = ("receipt_id", "intent_id", "status", "reconciliation_required")
#: Fields a mutation receipt must carry to bind a candidate to its effect.
_MUTATION_FIELDS: Final = (
    "mutation_receipt_id",
    "output_candidate_id",
    "input_candidate_ids",
    "effect_receipt_id",
)


class EffectReconciliationError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise EffectReconciliationError(code, message, context)


@dataclass(frozen=True)
class DispositionTable:
    """Effect status to candidate disposition, verified against the vocabulary."""

    dispositions: Mapping[str, str | None]
    resolving: frozenset[str]

    def disposition_of(self, status: str) -> str | None:
        if status not in self.dispositions:
            _fail(
                "STATUS_UNMAPPED",
                "an effect status has no declared disposition",
                {"status": status},
            )
        return self.dispositions[status]

    def resolves(self, status: str) -> bool:
        return status in self.resolving


def load_disposition_table() -> DispositionTable:
    """Read the table and require it to cover the imported vocabulary exactly."""

    try:
        document = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("DISPOSITION_UNREADABLE", f"the disposition table is unusable: {error}")
        raise  # pragma: no cover - _fail always raises

    entries = document.get("dispositions")
    if not isinstance(entries, Mapping) or not entries:
        _fail("DISPOSITION_UNREADABLE", "the disposition table declares no entries")

    declared = set(get_args(EffectStatus))
    missing = sorted(declared - set(entries))
    unknown = sorted(set(entries) - declared)
    if missing or unknown:
        _fail(
            "DISPOSITION_DRIFT",
            "the disposition table no longer covers the effect status vocabulary",
            {"missing": missing, "unknown": unknown},
        )

    allowed = {*STAGES, *TERMINAL_DISPOSITIONS, None}
    dispositions: dict[str, str | None] = {}
    resolving: set[str] = set()
    for status, entry in entries.items():
        if not isinstance(entry, Mapping):
            _fail("DISPOSITION_UNREADABLE", f"{status} has no disposition record")
        disposition = entry.get("disposition")
        if disposition not in allowed:
            _fail(
                "DISPOSITION_INVALID",
                "a disposition must be a pipeline stage or a terminal state",
                {"disposition": disposition, "status": status},
            )
        if not str(entry.get("reason", "")).strip():
            _fail(
                "DISPOSITION_UNREASONED",
                "every disposition must state why it follows from the status",
                {"status": status},
            )
        resolved = entry.get("resolves")
        if not isinstance(resolved, bool):
            _fail("DISPOSITION_UNREADABLE", f"{status} does not declare resolves")
        if resolved != (disposition is not None):
            _fail(
                "DISPOSITION_INVALID",
                "a status resolves if and only if it names a disposition",
                {"status": status},
            )
        dispositions[str(status)] = disposition
        if resolved:
            resolving.add(str(status))
    return DispositionTable(dispositions, frozenset(resolving))


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    return dict(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _require_fields(
    record: Mapping[str, Any], fields: Sequence[str], label: str
) -> None:
    missing = sorted(name for name in fields if name not in record)
    if missing:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} is missing required fields",
            {"missing": missing},
        )


def _index_effects(
    effect_receipts: Sequence[Mapping[str, Any]], table: DispositionTable
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for position, entry in enumerate(effect_receipts):
        record = _mapping(entry, f"effect_receipts[{position}]")
        _require_fields(record, _EFFECT_FIELDS, f"effect_receipts[{position}]")
        receipt_id = _text(record["receipt_id"], "receipt_id")
        if receipt_id in indexed:
            _fail(
                "DUPLICATE_EFFECT_RECEIPT",
                "an effect receipt id must appear once",
                {"receipt_id": receipt_id},
            )
        status = _text(record["status"], "status")
        # Establish the status is one the contract declares before judging
        # anything derived from it; otherwise an invented status is reported as
        # a flag inconsistency and the real problem is never named.
        table.disposition_of(status)
        resolves = table.resolves(status)
        required = record["reconciliation_required"]
        if not isinstance(required, bool):
            _fail("INPUT_INVALID", "reconciliation_required must be a boolean")
        # The ledger derives this flag from the status; a receipt that disagrees
        # with its own status was assembled by hand and cannot be trusted.
        if required == resolves:
            _fail(
                "RECONCILIATION_FLAG_INCONSISTENT",
                "reconciliation_required contradicts the effect status",
                {"receipt_id": receipt_id, "status": status},
            )
        indexed[receipt_id] = record
    return indexed


def _index_mutations(
    mutation_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_candidate: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for position, entry in enumerate(mutation_receipts):
        record = _mapping(entry, f"mutation_receipts[{position}]")
        _require_fields(record, _MUTATION_FIELDS, f"mutation_receipts[{position}]")
        receipt_id = _text(record["mutation_receipt_id"], "mutation_receipt_id")
        if receipt_id in seen:
            _fail(
                "DUPLICATE_MUTATION_RECEIPT",
                "a mutation receipt id must appear once",
                {"mutation_receipt_id": receipt_id},
            )
        seen.add(receipt_id)
        candidate = _text(record["output_candidate_id"], "output_candidate_id")
        if candidate in by_candidate:
            _fail(
                "CANDIDATE_MUTATED_TWICE",
                "one candidate cannot be the output of two mutations",
                {"candidate_id": candidate},
            )
        by_candidate[candidate] = record
    return by_candidate


def reconcile_effect_ledger(
    *,
    proposed: Sequence[str],
    generated: Sequence[str],
    evaluated: Sequence[str],
    persisted: Sequence[str],
    failed: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Reconcile the candidate fan-out against the effect and mutation ledgers.

    The candidate report comes from the chamber's own accounting; this engine
    adds the two bindings the chamber cannot see: that every generated candidate
    traces to a mutation receipt whose effect receipt exists, and that every
    effect receipt traces back to a proposed candidate.  Both directions matter —
    a missing receipt loses a candidate's provenance, and an extra one is a side
    effect nobody asked for.
    """

    table = load_disposition_table()
    candidates = reconcile_candidates(
        proposed=proposed,
        generated=generated,
        evaluated=evaluated,
        persisted=persisted,
        failed=failed,
        cancelled=cancelled,
    )

    effects = _index_effects(effect_receipts, table)
    mutations = _index_mutations(mutation_receipts)
    proposed_set = {str(item) for item in proposed}
    generated_set = {str(item) for item in generated}
    persisted_set = {str(item) for item in persisted}

    unreceipted = sorted(generated_set - set(mutations))
    orphan_mutations = sorted(set(mutations) - proposed_set)

    # An effect a mutation references is not an orphan even when that mutation
    # itself lacks provenance: the failure there is the missing lineage, and
    # reporting it twice would hide which one to fix.
    bound_effects = {
        _text(record["effect_receipt_id"], "effect_receipt_id")
        for record in mutations.values()
    }

    dangling: list[str] = []
    unresolved: list[str] = []
    disagreements: list[dict[str, Any]] = []
    for candidate in sorted(set(mutations) & proposed_set):
        record = mutations[candidate]
        effect_id = _text(record["effect_receipt_id"], "effect_receipt_id")
        effect = effects.get(effect_id)
        if effect is None:
            dangling.append(candidate)
            continue
        status = str(effect["status"])
        if not table.resolves(status):
            unresolved.append(candidate)
            continue
        disposition = table.disposition_of(status)
        landed = disposition == STAGES[-1]
        if landed != (candidate in persisted_set):
            disagreements.append(
                {
                    "candidate_id": candidate,
                    "effect_status": status,
                    "ledger_disposition": disposition,
                    "pipeline_persisted": candidate in persisted_set,
                }
            )

    orphan_effects = sorted(set(effects) - bound_effects)

    report: dict[str, Any] = {
        "candidates": candidates,
        # The candidate stage counts live in `candidates`; repeating one here
        # would restate vocabulary this engine does not own.
        "counts": {
            "effect_receipts": len(effects),
            "mutation_receipts": len(mutations),
        },
        "dangling_effect_references": dangling,
        "disagreements": disagreements,
        "orphan_effect_receipts": orphan_effects,
        "orphan_mutation_receipts": orphan_mutations,
        "unreceipted_candidates": unreceipted,
        "unresolved_candidates": sorted(unresolved),
    }
    report["reconciled"] = bool(candidates["reconciled"]) and not (
        dangling
        or disagreements
        or orphan_effects
        or orphan_mutations
        or unreceipted
        or unresolved
    )
    return report


#: What each unreconciled finding means, so a refusal names the failure class
#: rather than a count.  Keys are report fields, not wire vocabulary.
FINDING_CODES: Final = {
    "dangling_effect_references": (
        "EFFECT_RECEIPT_MISSING",
        "a mutation receipt references an effect receipt that does not exist, so "
        "the candidate's effect has no evidence",
    ),
    "disagreements": (
        "LEDGER_PIPELINE_DISAGREEMENT",
        "the effect ledger and the candidate pipeline disagree about whether a "
        "candidate persisted, which is a silent partial fan-in",
    ),
    "orphan_effect_receipts": (
        "ORPHAN_SIDE_EFFECT",
        "an effect receipt belongs to no proposed candidate, so an effect was "
        "produced that nothing in the run accounts for",
    ),
    "orphan_mutation_receipts": (
        "MUTATION_WITHOUT_PROVENANCE",
        "a mutation produced a candidate that was never proposed, so the output "
        "has no lineage in this fan-out",
    ),
    "unreceipted_candidates": (
        "MUTATION_RECEIPT_MISSING",
        "a generated candidate has no mutation receipt, so how it came to exist "
        "is unrecorded",
    ),
    "unresolved_candidates": (
        "EFFECT_UNRESOLVED",
        "an effect outcome could not be observed, so its candidate is neither "
        "persisted nor terminal until reconciliation resolves it",
    ),
}


def require_effect_reconciliation(report: Mapping[str, Any]) -> None:
    """Refuse an unreconciled ledger, naming the failure class that stopped it."""

    # The fan-out comes first: if candidates are already unaccounted for, the
    # ledger findings are consequences, and naming a consequence before its
    # cause would send the reader to the wrong place.
    candidates = report.get("candidates")
    if isinstance(candidates, Mapping) and not candidates.get("reconciled"):
        _fail(
            "CANDIDATE_FANOUT_UNRECONCILED",
            "the candidate fan-out itself does not reconcile, so no ledger "
            "agreement can make the run whole",
            {
                "gaps": candidates.get("gaps"),
                "missing": candidates.get("missing"),
                "unknown_identities": candidates.get("unknown_identities"),
            },
        )
    for field, (code, message) in FINDING_CODES.items():
        findings = report.get(field)
        if findings:
            _fail(code, message, {field: findings})
    if not report.get("reconciled"):
        _fail(
            "RECONCILIATION_INCOMPLETE",
            "the report is not marked reconciled and no finding explains why",
        )
