"""Candidate fan-out reconciliation (EF4-I60).

`Every fan-out reconciles proposed, generated, evaluated, persisted, failed,
cancelled and missing candidate identities.`

The seven categories exist because each gap between them hides a different bug.
Proposed-but-not-generated is a generator failure; generated-but-not-evaluated is
a scheduling failure; evaluated-but-not-persisted is a storage failure that would
silently discard a result. Counting only "how many came back" collapses all three
into one number and makes none of them visible.

`reconcile_candidates` therefore works on identity sets rather than counts, and
reports each gap separately.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: The reconciliation stages, in pipeline order.
STAGES: tuple[str, ...] = ("proposed", "generated", "evaluated", "persisted")

#: Terminal dispositions that legitimately remove a candidate from the pipeline.
TERMINAL_DISPOSITIONS: tuple[str, ...] = ("failed", "cancelled")


class ReconciliationFailed(RuntimeError):
    """A fan-out has unaccounted candidate identities."""


def reconcile_candidates(
    *,
    proposed: Iterable[str],
    generated: Iterable[str],
    evaluated: Iterable[str],
    persisted: Iterable[str],
    failed: Iterable[str] = (),
    cancelled: Iterable[str] = (),
) -> dict[str, Any]:
    """Account for every proposed identity across the pipeline.

    Returns a per-stage gap report rather than a single count, so a storage failure
    cannot be mistaken for a generator failure. `missing` holds identities that
    reached no terminal state and no later stage — the candidates that simply
    vanished, which is the category most easily lost.
    """
    sets = {
        "proposed": {str(item) for item in proposed},
        "generated": {str(item) for item in generated},
        "evaluated": {str(item) for item in evaluated},
        "persisted": {str(item) for item in persisted},
    }
    terminal = {
        "failed": {str(item) for item in failed},
        "cancelled": {str(item) for item in cancelled},
    }
    accounted_terminal = terminal["failed"] | terminal["cancelled"]

    unknown: dict[str, list[str]] = {}
    for index in range(1, len(STAGES)):
        stage = STAGES[index]
        upstream = sets[STAGES[index - 1]]
        extra = sorted(sets[stage] - upstream)
        if extra:
            unknown[stage] = extra

    gaps: dict[str, list[str]] = {}
    for index in range(len(STAGES) - 1):
        stage, nxt = STAGES[index], STAGES[index + 1]
        lost = sets[stage] - sets[nxt] - accounted_terminal
        if lost:
            gaps[f"{stage}_not_{nxt}"] = sorted(lost)

    missing = sorted(
        sets["proposed"] - sets["persisted"] - accounted_terminal
    )

    return {
        "counts": {name: len(values) for name, values in sets.items()}
        | {name: len(values) for name, values in terminal.items()},
        "gaps": gaps,
        "unknown_identities": unknown,
        "missing": missing,
        "reconciled": not gaps and not unknown and not missing,
    }


def require_reconciled(report: Mapping[str, Any]) -> None:
    """Raise unless every proposed identity reached a terminal or final state."""
    if report.get("unknown_identities"):
        raise ReconciliationFailed(
            f"fan-out produced identities absent upstream: {report['unknown_identities']}; a "
            "candidate that appears without being proposed has no provenance"
        )
    if report.get("missing"):
        raise ReconciliationFailed(
            f"{len(report['missing'])} candidate identity/identities vanished without reaching a "
            f"terminal state: {report['missing'][:5]}; a silently dropped candidate is "
            "indistinguishable from one that had nothing to report"
        )
    if report.get("gaps"):
        raise ReconciliationFailed(
            f"pipeline gaps remain unexplained: {sorted(report['gaps'])}; each gap names a "
            "different failure class and none may be collapsed into a count"
        )
