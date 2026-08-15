"""Crash recovery, future-only evaluator update and replay integration gate (W06).

Three sealed surfaces already decide the parts of a recovery, and this gate is
what refuses a recovery that is *incoherent across all three at once* — the
failure that none of them can see alone because each sees only its own record.

*The resume itself* is W05's.  ``resume_from_checkpoint`` expresses the return as
an F05 edge across a committed checkpoint and hands the machine's verdict back
with its own codes intact; ``verify_committed_checkpoint`` decides that the resume
point is canonical and re-derives its digest.  This gate does not re-decide any of
that.  What it adds is the crash boundary the resume record cannot describe: a run
that stopped by crashing carried a *roster of work it had committed to*, and the
one question that only appears when that roster is laid beside the resumed
fan-out is whether the resume lost or double-counted any of it.

*Candidate accounting* is the reconciliation module's (EF4-I60).
``reconcile_candidates`` already reconciles proposed, generated, evaluated,
persisted, failed and cancelled identities and names what went missing inside one
fan-out; its disposition vocabulary is authoritative and is composed rather than
restated.  The crash boundary is the layer above it: an ``expected`` roster the
checkpoint promised to carry forward, ``lost`` for a committed candidate the
resume shows no trace of, and ``double_counted`` for a candidate the resume drove
into more than one terminal state — the two ways a resume inflates or deflates a
population without any single fan-out looking wrong.

*Replay honesty* is the release module's (EF4-I39).  A resumed run must be able to
prove it is the run it continues, and ``replay_reproduced`` is true only for a
byte-for-byte ``EXACT`` reproduction; ``require_comparable`` refuses a replay that
could not resolve its pins at all.  A resume that replays as *comparable but not
identical* is a resume that produced a different run, and reporting that as a
recovery would claim a reproducibility the continuation never earned — so it is
refused here rather than folded into success.

*Future-only evaluator update* is the quarantine module's rule, reached through
W05.  An evaluator defect found while recovering a run may never re-score that
run: ``require_evaluator_update_future_only`` delegates to
``require_forward_only_application``, whose ``QuarantineViolation`` travels out
unwrapped, because the prohibition on rewriting a completed judgment is the sealed
owner's to state, not a copy of it here.

*Schedule integration* is N06's.  A run recovered from a crash ran under a
schedule, and ``require_integrated_run`` refuses one whose backpressure, stalls or
locks did not add up; the N06 report asserts no run identity of its own, so this
gate binds the verdict to the recovered run *by construction* — sealing it under
that run id through ``seal_integration_record`` — rather than trusting a run label
the report never carried.  The one run identity a composed record *does* assert on
its own is the replay's ``source_run_id``, and a replay that names a different run
than the checkpoint is ``RECOVERY_RUN_MISBOUND``.

Nothing here re-implements what it composes.  Refusals from the composed
modules — F05 run findings, ``ReconciliationFailed``, ``ReplayVerificationFailed``,
``QuarantineViolation``, N06's ``IntegrationError`` — travel out with their own
types and codes rather than being paraphrased under a W06 code.  This module
holds no canonical schema enum value as a string literal (EF4-I22): the
disposition names come from the reconciliation module that declares them, and the
equivalence vocabulary is never named because the replay module's predicates
encapsulate it.  The gate acquires no evaluator, holdout or promotion authority,
mutates none of its inputs, and derives a receipt that re-hashes from its own
content.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...domain.hashing import hash_excluding
from ...domain.ids import new_id
from ...evolution.v4_f05 import Transition
from ...evolution_chamber.reconciliation import (
    STAGES,
    TERMINAL_DISPOSITIONS,
    reconcile_candidates,
    require_reconciled,
)
from ...release.replay import replay_reproduced, require_comparable
from ...scheduler.v4_n06 import require_integrated_run, seal_integration_record
from ..v4_w05 import require_forward_only_application, resume_from_checkpoint

#: Every way this gate refuses, and why that refusal exists.  Refusals owned by a
#: composed module are deliberately absent: the F05 machine's run findings,
#: ``ReconciliationFailed``, ``ReplayVerificationFailed``, N06's
#: ``IntegrationError`` and quarantine's ``QuarantineViolation`` all reach the
#: caller with their own codes rather than being restated under a W06 name.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a recovery derived from something it never validated"
    ),
    "RECOVERY_CANDIDATE_DOUBLE_COUNTED": (
        "a candidate reached more than one terminal state across the crash "
        "boundary, so the resumed run counted the same work twice and its "
        "population totals are inflated by outcomes the search only reached once"
    ),
    "RECOVERY_CANDIDATE_LOST": (
        "a candidate the run had committed to before the crash is absent from "
        "every disposition the resume produced, so the resume silently dropped "
        "work the checkpoint promised to carry forward and no later stage can "
        "see that it is gone"
    ),
    "RECOVERY_RUN_MISBOUND": (
        "the checkpoint, the resume, the replay and the schedule this gate "
        "composed do not all name one evolution run, so the recovery record "
        "would stitch together the state of searches that never shared one"
    ),
    "REPLAY_NOT_REPRODUCED": (
        "the resumed run replays as comparable but not byte-for-byte identical "
        "to the run it continues, so the resume produced a different run and "
        "reporting it as a recovery would claim a reproducibility the "
        "continuation never earned"
    ),
}

#: The three mutually exclusive terminal states a candidate may end a fan-out in.
#: ``persisted`` is the reconciliation module's last pipeline stage and the two
#: terminal dispositions are its own; a candidate appearing in two of these was
#: driven to more than one final outcome, which is the double count the crash
#: boundary can produce.  Read from the declaring module so a vocabulary change
#: there tracks here rather than drifting (EF4-I22).
_FINAL_STATES: tuple[str, ...] = (STAGES[-1], *TERMINAL_DISPOSITIONS)


class RecoveryGateError(ValueError):
    """A crash recovery, a reconciliation or a replay check was refused."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise RecoveryGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise RecoveryGateError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_id(value: object, label: str) -> str:
    identifier = str(value if value is not None else "").strip()
    if not identifier:
        _fail("INPUT_INVALID", f"{label} must be a non-empty id", {"label": label})
    return identifier


def _unique_ids(values: object, label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence of ids", {"label": label})
    cleaned: list[str] = []
    for position, value in enumerate(values):  # type: ignore[arg-type]
        identifier = _require_id(value, f"{label}[{position}]")
        if identifier in cleaned:
            _fail(
                "INPUT_INVALID",
                f"{label} names {identifier} twice",
                {"duplicate": identifier, "label": label},
            )
        cleaned.append(identifier)
    return tuple(cleaned)


def reconcile_recovery(
    *,
    expected_candidate_ids: Sequence[str],
    proposed: Sequence[str],
    generated: Sequence[str],
    evaluated: Sequence[str],
    persisted: Sequence[str],
    failed: Sequence[str] = (),
    cancelled: Sequence[str] = (),
) -> dict[str, Any]:
    """Reconcile a resumed fan-out against the roster the crash left behind.

    The fan-out itself is reconciled by the sealed EF4-I60 owner, whose report
    is carried under its own key rather than merged in, so a reader can always
    tell an ordinary pipeline gap from a crash-boundary defect.  On top of it two
    things are derived that only the crash makes visible: a committed candidate
    the resume shows nowhere (``lost``) and a candidate the resume drove into
    more than one terminal state (``double_counted``).  Nothing passed in is
    mutated and the identity sets are sorted, so one roster always produces one
    report.
    """
    # The disposition names are canonical enum vocabulary; they are read from the
    # reconciliation owner (``STAGES`` and ``TERMINAL_DISPOSITIONS``) and used as
    # the validation labels too, so no disposition token is a literal here
    # (EF4-I22).
    stage_proposed, stage_generated, stage_evaluated, stage_persisted = STAGES
    terminal_failed, terminal_cancelled = TERMINAL_DISPOSITIONS

    expected = set(_unique_ids(expected_candidate_ids, "expected_candidate_ids"))
    proposed_ids = _unique_ids(proposed, stage_proposed)
    generated_ids = _unique_ids(generated, stage_generated)
    evaluated_ids = _unique_ids(evaluated, stage_evaluated)
    persisted_ids = _unique_ids(persisted, stage_persisted)
    failed_ids = _unique_ids(failed, terminal_failed)
    cancelled_ids = _unique_ids(cancelled, terminal_cancelled)

    fan_out = reconcile_candidates(
        proposed=proposed_ids,
        generated=generated_ids,
        evaluated=evaluated_ids,
        persisted=persisted_ids,
        failed=failed_ids,
        cancelled=cancelled_ids,
    )

    seen = (
        set(proposed_ids)
        | set(generated_ids)
        | set(evaluated_ids)
        | set(persisted_ids)
        | set(failed_ids)
        | set(cancelled_ids)
    )
    lost = sorted(expected - seen)

    final = {
        name: value
        for name, value in zip(
            _FINAL_STATES,
            (
                set(persisted_ids),
                set(failed_ids),
                set(cancelled_ids),
            ),
        )
    }
    double_counted = sorted(
        candidate
        for candidate in seen
        if sum(candidate in members for members in final.values()) > 1
    )

    return {
        "counts": {
            "double_counted": len(double_counted),
            "expected": len(expected),
            "lost": len(lost),
        },
        "double_counted": double_counted,
        "expected": sorted(expected),
        "fan_out": fan_out,
        "lost": lost,
        "recovered": bool(fan_out["reconciled"]) and not lost and not double_counted,
    }


def require_recovered_reconciliation(report: Mapping[str, Any]) -> None:
    """Refuse a recovery whose candidates were lost or double-counted.

    The two crash-boundary findings are checked first, then the sealed fan-out
    owner is asked to refuse its own gaps: a lost or duplicated candidate is
    *why* a resume's totals stopped adding up, and surfacing the fan-out gap
    before it would name the symptom and hide the cause.
    """
    record = _require_mapping(report, "reconciliation")
    double_counted = record.get("double_counted") or ()
    if double_counted:
        _fail(
            "RECOVERY_CANDIDATE_DOUBLE_COUNTED",
            "the resume drove candidates into more than one terminal state",
            {"double_counted": list(double_counted)},
        )
    lost = record.get("lost") or ()
    if lost:
        _fail(
            "RECOVERY_CANDIDATE_LOST",
            "the resume shows no trace of candidates the crash committed to",
            {"lost": list(lost)},
        )
    fan_out = record.get("fan_out")
    if not isinstance(fan_out, Mapping):
        _fail(
            "INPUT_INVALID",
            "the reconciliation carries no fan-out report to verify",
            {"label": "reconciliation.fan_out"},
        )
    require_reconciled(fan_out)


def require_evaluator_update_future_only(
    reassessment: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    recovered_run_id: str,
) -> None:
    """Refuse re-scoring the recovered run under an evaluator update (EF4-I56).

    The rule is quarantine's and the binding is W05's: a proposal may never be
    applied to the run that produced it, and the reassessment must name the
    proposal actually being applied.  Both refusals travel out as
    ``QuarantineViolation`` or ``RecoveryWorkflowError`` from the sealed owner;
    this gate only fixes the target as the run under recovery, which is the run
    an in-flight defect would most want to rewrite.
    """
    require_forward_only_application(
        reassessment,
        proposal,
        target_run_id=_require_id(recovered_run_id, "recovered_run_id"),
    )


def _bind_run(observed: object, label: str, expected_run_id: str) -> None:
    run_id = _require_id(observed, label)
    if run_id != expected_run_id:
        _fail(
            "RECOVERY_RUN_MISBOUND",
            f"{label} names a different evolution run than the recovery",
            {
                "expected_run_id": expected_run_id,
                "observed_run_id": run_id,
                "at": label,
            },
        )


def verify_crash_recovery(
    repository_root: str | Path,
    *,
    checkpoint: Mapping[str, Any],
    continuation: Sequence[Transition],
    loop_contract: Mapping[str, Any],
    stop_certificate: Mapping[str, Any],
    resumed_at: str,
    expected_candidate_ids: Sequence[str],
    proposed: Sequence[str],
    generated: Sequence[str],
    evaluated: Sequence[str],
    persisted: Sequence[str],
    replay_report: Mapping[str, Any],
    failed: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    integration_report: Mapping[str, Any] | None = None,
    dry_rounds_observed: int = 0,
    resume_id: str | None = None,
    recovery_id: str | None = None,
) -> dict[str, Any]:
    """Gate one crash recovery across resume, reconciliation, replay and schedule.

    The steps run in the order a failure should be reported.  The resume is
    verified first, through W05, because a resume the F05 machine rejects is not
    a recovery at all and its own code says why.  The candidate roster is
    reconciled next, because a lost or double-counted candidate is the defect a
    crash most directly causes.  Replay honesty follows: a resume that cannot
    prove it reproduced the run it continues has not recovered it.  The schedule
    verdict and every run binding are checked last, so a coherent recovery whose
    records simply belong to different runs is named for that and nothing else.

    Nothing is mutated, the only records stored are re-derived or hash-bound, and
    the receipt re-hashes from its own content, so two runs over one declaration
    produce byte-equal recoveries when the ids are supplied.
    """
    resume = resume_from_checkpoint(
        repository_root,
        checkpoint=checkpoint,
        continuation=continuation,
        loop_contract=loop_contract,
        stop_certificate=stop_certificate,
        resumed_at=resumed_at,
        dry_rounds_observed=dry_rounds_observed,
        resume_id=resume_id,
    )
    run_id = str(resume["evolution_run_id"])

    reconciliation = reconcile_recovery(
        expected_candidate_ids=expected_candidate_ids,
        proposed=proposed,
        generated=generated,
        evaluated=evaluated,
        persisted=persisted,
        failed=failed,
        cancelled=cancelled,
    )
    require_recovered_reconciliation(reconciliation)

    replay = _require_mapping(replay_report, "replay_report")
    # The replay's equivalence and drift are derived fields; a report whose
    # digest no longer re-derives has had one of them rewritten after the fact,
    # so its verdict is trusted only once the record proves it is authentic.
    if hash_excluding(dict(replay), "report_hash") != replay.get("report_hash"):
        _fail(
            "INPUT_INVALID",
            "the replay report does not re-derive its own digest, so its "
            "equivalence verdict cannot be trusted",
            {"replay_id": str(replay.get("replay_id") or "")},
        )
    # An unmade comparison is refused by its owner as NOT_COMPARABLE; a comparison
    # that resolved but did not reproduce byte-for-byte is this gate's refusal.
    require_comparable(replay)
    if not replay_reproduced(replay):
        _fail(
            "REPLAY_NOT_REPRODUCED",
            "the resumed run did not replay identically to the run it continues",
            {
                "replay_id": str(replay.get("replay_id") or ""),
                "source_run_id": str(replay.get("source_run_id") or ""),
            },
        )
    _bind_run(replay.get("source_run_id"), "replay_report.source_run_id", run_id)

    schedule_integration_hash: str | None = None
    if integration_report is not None:
        integration = _require_mapping(integration_report, "integration_report")
        # N06 refuses an unaccounted schedule with its own codes; the report
        # carries no run identity, so the verdict is bound to the recovered run
        # by sealing it under that id rather than by trusting a label.
        require_integrated_run(integration)
        sealed = seal_integration_record(integration, run_id=run_id)
        schedule_integration_hash = str(sealed["integration_hash"])

    recovery: dict[str, Any] = {
        "counts": {
            "continuation_transitions": int(
                resume["counts"]["continuation_transitions"]
            ),
            "double_counted": int(reconciliation["counts"]["double_counted"]),
            "expected_candidates": int(reconciliation["counts"]["expected"]),
            "lost": int(reconciliation["counts"]["lost"]),
        },
        "evolution_run_id": run_id,
        "reconciliation": deepcopy(reconciliation),
        "recovered": True,
        "recovered_at": str(resumed_at),
        "recovery_id": recovery_id or new_id("RGC"),
        "replay_verification": {
            "replay_id": str(replay.get("replay_id") or ""),
            "replay_report_hash": str(replay.get("report_hash") or ""),
            "reproduced": True,
        },
        "resume_hash": str(resume["resume_hash"]),
        "resume_id": str(resume["resume_id"]),
        "schedule_integration_hash": schedule_integration_hash,
    }
    recovery["recovery_hash"] = hash_excluding(recovery, "recovery_hash")
    return recovery


def recovery_hash_matches(record: Mapping[str, Any]) -> bool:
    """True when a recovery record re-derives its own hash from its content."""
    sealed = _require_mapping(record, "recovery record")
    return hash_excluding(dict(sealed), "recovery_hash") == sealed.get("recovery_hash")


def require_recovered(record: Mapping[str, Any]) -> None:
    """Refuse a recovery record that is unmarked or does not re-derive its hash."""
    sealed = _require_mapping(record, "recovery record")
    if not recovery_hash_matches(sealed):
        _fail(
            "INPUT_INVALID",
            "the recovery record does not re-derive its own digest",
            {"recovery_id": str(sealed.get("recovery_id") or "")},
        )
    if sealed.get("recovered") is not True:
        _fail(
            "INPUT_INVALID",
            "the recovery record is not marked recovered",
            {"recovery_id": str(sealed.get("recovery_id") or "")},
        )
