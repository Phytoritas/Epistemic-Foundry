"""Evolution resume, cancel and evaluator-drift reassessment workflow (W05).

Three moments sit between a search that stopped and a search that may continue,
and each of them is a place where a run can quietly become a different run.

*Resume.*  F05 already knows what a legal return edge is: one that crosses a
committed checkpoint between the endpoints the LoopContract bounds.  Resuming is
that same edge taken across a checkpoint that was committed earlier, so resume
legality is not re-decided here.  The resumed run is handed to the F05 machine
with the return edge crossing *that* checkpoint prepended to the continuation,
and the machine's verdict is the verdict.  Its refusals travel out with their own
codes intact — a caller resuming from an unsealed or partial resume point needs
to read ``RETURN_EDGE_UNCHECKPOINTED`` or ``CHECKPOINT_INCOMPLETE``, not a
W05 paraphrase of them.  What the machine cannot see is whether the record is
canonical and re-derives its own digest, and that is the only part this module
decides for itself.

*Cancel.*  A cancel is a stop, and a stop leaves work behind.  The map of what
remains — candidates proposed but never evaluated, niches mapped but never
assessed — is the most reusable output an interrupted search has, so it is
*derived from the run's own accounting* rather than accepted as an assertion.  A
caller may publish its own disclosure, but a disclosure that omits derived
remaining work is refused: that is precisely the cancel that hides partial
results.  The certificate itself is built through the canonical shape, which
forces ``partial_results_visible``.

*Evaluator drift.*  Drift is the firewall's judgment and nothing else's:
``assert_unchanged`` recomputes the digest from content, so an edit that also
rewrote ``bundle_hash`` is still caught.  When it fires, the comparisons made
under the sealed bundle become *potentially invalid* — a mark, not a deletion and
not a rescore.  Re-scoring completed candidates under a changed evaluator is how
a run retroactively manufactures the outcome it wanted, so the fix is recorded as
a quarantined future-run proposal through the governance module, and applying it
back to a completed run is refused by that module's own rule rather than by a
copy of it here.

Nothing here re-implements what it composes.  The seven checkpoint components and
the stop-reason classification come from ``evolution_chamber.checkpoint``, which
declares them; run legality from ``evolution.v4_f05``; drift from
``verifier_firewall.firewall``; the retroactivity rule from
``governance.quarantine``.  This module holds no canonical schema enum value as a
string literal (EF4-I22).

What this workflow does not do: recover anything physical.  Reading a checkpoint
back out of the object store, replaying a partially written transaction, and the
durability of the records handed to it belong to the runtime that owns that store
(D06).  This module is the workflow logic over records already in hand; it cannot
observe the store itself.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, validate_artifact
from ...domain.hashing import hash_excluding
from ...domain.ids import new_id
from ...evolution.v4_f05 import (
    Transition,
    evaluate_run,
    load_graph,
    load_loop_bound,
    require_valid_run,
    stop_reasons,
)
from ...evolution_chamber.checkpoint import (
    build_stop_certificate,
    missing_components,
    stop_was_orderly,
)
from ...governance.quarantine import (
    build_evaluator_mutation_proposal,
    require_not_retroactive,
)
from ...verifier_firewall.firewall import EvaluatorDrift, VerifierFirewall

#: Every way this workflow refuses, and why that refusal exists.  Refusals that
#: belong to a composed module are deliberately absent: F05's run findings, the
#: checkpoint module's stop-certificate refusal and quarantine's retroactivity
#: violation travel out with their own codes rather than being restated here.
FINDING_CODES: dict[str, str] = {
    "CANCEL_COUNTS_UNRECONCILED": (
        "the cancel reports a candidate evaluated that was never proposed or a "
        "niche assessed that was never mapped, so the run's own accounting "
        "cannot say what work the stop actually left behind"
    ),
    "CANCEL_DISCLOSURE_UNACCOUNTED": (
        "the disclosure names remaining work the run never proposed or mapped, "
        "so the stop certificate would publish a map of a search that did not "
        "happen"
    ),
    "CANCEL_PARTIAL_WORK_HIDDEN": (
        "the disclosure omits work the run's own accounting says was still "
        "unresolved when the cancel landed, and an interrupted search whose "
        "remaining map is hidden cannot be resumed or reasoned about by anyone"
    ),
    "CANCEL_STOP_REASON_UNDECLARED": (
        "the cancel names a stop reason outside the vocabulary the checkpoint "
        "module classifies, so whether the search ended on its own terms or "
        "adversely could not be decided from the certificate"
    ),
    "CHECKPOINT_COMPONENTS_MISSING": (
        "the resume point does not bind every component the checkpoint module "
        "declares, so restoring from it would produce a configuration that "
        "never existed at any instant of the original run"
    ),
    "CHECKPOINT_HASH_MISMATCH": (
        "the checkpoint does not re-derive the digest it publishes, so the "
        "record being resumed or certified is not the record whose components "
        "were sealed together"
    ),
    "CHECKPOINT_NOT_CANONICAL": (
        "the checkpoint does not satisfy its canonical schema, and a resume "
        "point that no contract describes cannot be shown to hold the state it "
        "claims to hold"
    ),
    "CHECKPOINT_RUN_MISMATCHED": (
        "the checkpoint was committed by a different evolution run than the one "
        "being resumed or cancelled, so the state restored or certified would "
        "belong to a search nobody asked about"
    ),
    "DRIFT_ABSENT": (
        "the firewall finds the current evaluator identical to the sealed one, "
        "and issuing a reassessment anyway would mark sound comparisons "
        "doubtful on the strength of a drift that never happened"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this workflow requires, and continuing would "
        "record a resume, a cancel or a reassessment derived from something it "
        "never validated"
    ),
    "REASSESSMENT_COMPARISON_UNBOUND": (
        "a comparison declares no evaluator bundle, so whether the drifted "
        "evaluator produced it cannot be decided; assuming it did not is the "
        "assumption that leaves a contaminated comparison standing"
    ),
    "REASSESSMENT_PROPOSAL_UNBOUND": (
        "the reassessment and the quarantine proposal name different proposal "
        "ids, so the record does not bind the fix whose retroactive use is "
        "being tested"
    ),
}

#: What a reassessment records about a comparison made under a drifted
#: evaluator.  No canonical schema declares a reassessment status, so these are
#: package-local by necessity and are deliberately not schema enum values: a
#: drifted comparison is *not* the schema's invalidated state, because nothing
#: here re-runs the evaluator to establish that.
COMPARISON_POTENTIALLY_INVALID: str = "POTENTIALLY_INVALID"
COMPARISON_UNAFFECTED: str = "UNAFFECTED_BY_DRIFT"

#: What a comparison must declare for the reassessment to place it.
COMPARISON_BINDING_FIELDS: tuple[str, ...] = (
    "comparison_id",
    "evaluator_bundle_id",
)


class RecoveryWorkflowError(ValueError):
    """A resume, a cancel or a drift reassessment was refused."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise RecoveryWorkflowError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise RecoveryWorkflowError(code, message, context)


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


def verify_committed_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, str]:
    """Raise unless `checkpoint` is a resume point that was actually committed.

    Three separate things make a checkpoint resumable, and each is checked
    against its own owner: the components come from the checkpoint module's
    declaration, the shape from the canonical schema, and the digest from the
    record itself.  A record that passes only the first two is a resume point
    that was edited after it was sealed.
    """
    record = _require_mapping(checkpoint, "checkpoint")
    gaps = missing_components(record)
    if gaps:
        _fail(
            "CHECKPOINT_COMPONENTS_MISSING",
            f"the resume point does not bind {gaps}",
            {"checkpoint_id": str(record.get("checkpoint_id") or ""), "missing": gaps},
        )
    try:
        validate_artifact("evolution-checkpoint", dict(record))
    except ContractViolation as error:
        _fail(
            "CHECKPOINT_NOT_CANONICAL",
            f"the checkpoint does not satisfy its canonical schema: {error}",
            {
                "checkpoint_id": str(record.get("checkpoint_id") or ""),
                "errors": list(error.errors),
            },
        )
    declared = str(record.get("checkpoint_hash") or "")
    derived = hash_excluding(dict(record), "checkpoint_hash")
    if declared != derived:
        _fail(
            "CHECKPOINT_HASH_MISMATCH",
            "the checkpoint does not re-derive its own digest",
            {
                "checkpoint_id": str(record["checkpoint_id"]),
                "declared": declared,
                "derived": derived,
            },
        )
    return {
        "checkpoint_hash": derived,
        "checkpoint_id": str(record["checkpoint_id"]),
        "evolution_run_id": str(record["evolution_run_id"]),
    }


def _require_same_run(
    committed: Mapping[str, str], evolution_run_id: str, action: str
) -> None:
    if committed["evolution_run_id"] != evolution_run_id:
        _fail(
            "CHECKPOINT_RUN_MISMATCHED",
            f"the checkpoint {action} belongs to another evolution run",
            {
                "checkpoint_id": committed["checkpoint_id"],
                "checkpoint_run_id": committed["evolution_run_id"],
                "requested_run_id": evolution_run_id,
            },
        )


def resume_from_checkpoint(
    repository_root: str | Path,
    *,
    checkpoint: Mapping[str, Any],
    continuation: Sequence[Transition],
    loop_contract: Mapping[str, Any],
    stop_certificate: Mapping[str, Any],
    resumed_at: str,
    dry_rounds_observed: int = 0,
    resume_id: str | None = None,
) -> dict[str, Any]:
    """Verify a run resumed across `checkpoint` through the F05 machine.

    The resume *is* a return edge, so it is expressed as one: the loop's own
    endpoints, read from the LoopContract the machine binds, with the committed
    checkpoint attached.  Everything after that is the machine's judgment, and
    its refusals are not caught — a resume from an unsealed or partial resume
    point must reach the caller as the machine's own finding, because the code
    is what says which of the two happened.

    The stop certificate is required rather than optional because the machine
    only accounts for a run that ended (EF4-I62).  A resume record over a
    continuation still in flight would be a claim about something that has not
    happened yet, and the only way to accept one would be for this module to
    re-decide a subset of the machine's gate for itself.

    The canonical checks run afterwards for the same reason as everything else
    here: they would mask ``CHECKPOINT_INCOMPLETE`` with a schema complaint
    about the very fields the machine is more precise about.
    """
    record = _require_mapping(checkpoint, "checkpoint")
    graph = load_graph(repository_root)
    bound = load_loop_bound(loop_contract, graph)
    if isinstance(continuation, (str, bytes)) or not isinstance(continuation, Sequence):
        _fail("INPUT_INVALID", "continuation must be a sequence of transitions")

    # An absent id is passed through as absent rather than defaulted, so an
    # uncommitted checkpoint reaches the machine as the uncheckpointed return
    # edge it is instead of being rescued by a fabricated identifier.
    identifier = str(record.get("checkpoint_id") or "").strip() or None
    return_edge = Transition(
        source=bound.exit_node_id,
        target=bound.entry_node_id,
        checkpoint_id=identifier,
        checkpoint=deepcopy(dict(record)),
    )
    report = evaluate_run(
        repository_root,
        transitions=[return_edge, *continuation],
        loop_contract=loop_contract,
        stop_certificate=stop_certificate,
        dry_rounds_observed=dry_rounds_observed,
    )
    require_valid_run(report)

    committed = verify_committed_checkpoint(record)
    certificate = _require_mapping(stop_certificate, "stop_certificate")
    _require_same_run(
        committed,
        _require_id(
            certificate.get("evolution_run_id"), "stop_certificate.evolution_run_id"
        ),
        "resumed from",
    )

    resume: dict[str, Any] = {
        "checkpoint_hash": committed["checkpoint_hash"],
        "checkpoint_id": committed["checkpoint_id"],
        "counts": {
            "continuation_transitions": len(continuation),
            "forward_edges": int(report["counts"]["forward_edges"]),
            "return_edges": int(report["counts"]["return_edges"]),
        },
        "evolution_run_id": committed["evolution_run_id"],
        "generation": int(record["generation"]),
        "loop": dict(report["loop"]),
        "resume_id": resume_id or new_id("EWR"),
        "resumed_at": str(resumed_at),
        "run_report": deepcopy(report),
        "stop_certificate_id": _require_id(
            certificate.get("certificate_id"), "stop_certificate.certificate_id"
        ),
    }
    resume["resume_hash"] = hash_excluding(resume, "resume_hash")
    return resume


def _remaining(
    started: tuple[str, ...],
    finished: tuple[str, ...],
    whole_label: str,
    done_label: str,
) -> tuple[str, ...]:
    """What the run started and did not finish, derived rather than asserted."""
    unknown = sorted(set(finished) - set(started))
    if unknown:
        _fail(
            "CANCEL_COUNTS_UNRECONCILED",
            f"{done_label} names work {whole_label} never contained",
            {"unaccounted": unknown},
        )
    return tuple(sorted(set(started) - set(finished)))


def _disclosure(
    derived: tuple[str, ...], disclosed: object, label: str
) -> tuple[str, ...]:
    """The published remaining map, refused when it is narrower than the truth."""
    if disclosed is None:
        return derived
    published = _unique_ids(disclosed, label)
    hidden = sorted(set(derived) - set(published))
    if hidden:
        _fail(
            "CANCEL_PARTIAL_WORK_HIDDEN",
            f"{label} omits remaining work the run's own accounting recorded",
            {"hidden": hidden, "label": label},
        )
    invented = sorted(set(published) - set(derived))
    if invented:
        _fail(
            "CANCEL_DISCLOSURE_UNACCOUNTED",
            f"{label} names remaining work the run never started",
            {"label": label, "unaccounted": invented},
        )
    return tuple(sorted(published))


def cancel_evolution_run(
    *,
    evolution_run_id: str,
    stop_reason: str,
    conditions_observed: Sequence[str],
    checkpoint: Mapping[str, Any],
    proposed_candidate_ids: Sequence[str],
    evaluated_candidate_ids: Sequence[str],
    mapped_niche_ids: Sequence[str],
    assessed_niche_ids: Sequence[str],
    recorded_at: str,
    disclosed_unresolved_candidates: Sequence[str] | None = None,
    disclosed_unassessed_niches: Sequence[str] | None = None,
    cancellation_id: str | None = None,
    certificate_id: str | None = None,
) -> dict[str, Any]:
    """Certify a cancelled run through the canonical stop certificate.

    The remaining map is computed from what the run proposed and mapped against
    what it evaluated and assessed, so a cancel cannot report an empty search
    frontier by simply declining to list one.  A caller-supplied disclosure is
    accepted only when it covers that derived set exactly; narrower is a hidden
    partial result and wider is a map of a search that did not happen.

    The certificate is built by the module that owns the shape, which forces
    ``partial_results_visible`` and validates against the canonical schema.  Its
    own refusal — a stop with no observed conditions — travels out unwrapped.
    """
    run_id = _require_id(evolution_run_id, "evolution_run_id")
    committed = verify_committed_checkpoint(checkpoint)
    _require_same_run(committed, run_id, "being cancelled")

    reason = _require_id(stop_reason, "stop_reason")
    declared = stop_reasons()
    if reason not in declared:
        _fail(
            "CANCEL_STOP_REASON_UNDECLARED",
            f"{reason} is not a stop reason the checkpoint module classifies",
            {"declared": list(declared), "stop_reason": reason},
        )

    started_candidates = _unique_ids(proposed_candidate_ids, "proposed_candidate_ids")
    scored_candidates = _unique_ids(evaluated_candidate_ids, "evaluated_candidate_ids")
    started_niches = _unique_ids(mapped_niche_ids, "mapped_niche_ids")
    covered_niches = _unique_ids(assessed_niche_ids, "assessed_niche_ids")
    unresolved = _disclosure(
        _remaining(
            started_candidates,
            scored_candidates,
            "proposed_candidate_ids",
            "evaluated_candidate_ids",
        ),
        disclosed_unresolved_candidates,
        "disclosed_unresolved_candidates",
    )
    unassessed = _disclosure(
        _remaining(
            started_niches,
            covered_niches,
            "mapped_niche_ids",
            "assessed_niche_ids",
        ),
        disclosed_unassessed_niches,
        "disclosed_unassessed_niches",
    )

    certificate = build_stop_certificate(
        evolution_run_id=run_id,
        stop_reason=reason,
        conditions_observed=list(conditions_observed),
        unresolved_candidates=list(unresolved),
        unassessed_niches=list(unassessed),
        checkpoint_id=committed["checkpoint_id"],
        certificate_id=certificate_id,
    )
    # The builder forces visibility; this proves it on the produced record
    # rather than trusting that it stayed forced.
    if certificate.get("partial_results_visible") is not True:
        _fail(
            "CANCEL_PARTIAL_WORK_HIDDEN",
            "the produced certificate does not make partial results visible",
            {"certificate_id": str(certificate.get("certificate_id") or "")},
        )

    cancellation: dict[str, Any] = {
        "cancellation_id": cancellation_id or new_id("EWC"),
        "certificate": deepcopy(certificate),
        "checkpoint_hash": committed["checkpoint_hash"],
        "checkpoint_id": committed["checkpoint_id"],
        "counts": {
            "assessed_niches": len(covered_niches),
            "evaluated_candidates": len(scored_candidates),
            "mapped_niches": len(started_niches),
            "proposed_candidates": len(started_candidates),
            "unassessed_niches": len(unassessed),
            "unresolved_candidates": len(unresolved),
        },
        "evolution_run_id": run_id,
        "orderly": stop_was_orderly(certificate),
        "recorded_at": str(recorded_at),
        "stop_reason": reason,
        "unassessed_niches": list(unassessed),
        "unresolved_candidates": list(unresolved),
    }
    cancellation["cancellation_hash"] = hash_excluding(
        cancellation, "cancellation_hash"
    )
    return cancellation


def _placed_comparisons(
    comparisons: object, sealed_bundle_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split the comparisons into those the drifted evaluator produced and rest.

    Every input row appears in exactly one side.  Nothing is dropped, because a
    reassessment that shortened the record would destroy the evidence that the
    affected comparisons ever existed.
    """
    if isinstance(comparisons, (str, bytes)) or not isinstance(comparisons, Sequence):
        _fail("INPUT_INVALID", "comparisons must be a sequence of rows")
    affected: list[dict[str, Any]] = []
    unaffected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, given in enumerate(comparisons):  # type: ignore[arg-type]
        row = _require_mapping(given, f"comparisons[{index}]")
        identifier = _require_id(
            row.get("comparison_id"), f"comparisons[{index}].comparison_id"
        )
        if identifier in seen:
            _fail(
                "INPUT_INVALID",
                f"comparisons names {identifier} twice",
                {"duplicate": identifier},
            )
        seen.add(identifier)
        # Fail closed: an unbound comparison cannot be shown to be outside the
        # drifted evaluator's reach, and treating it as outside is the
        # assumption that leaves a contaminated comparison standing.
        bundle = str(row.get("evaluator_bundle_id") or "").strip()
        if not bundle:
            _fail(
                "REASSESSMENT_COMPARISON_UNBOUND",
                f"comparison {identifier} declares no evaluator bundle",
                {
                    "comparison_id": identifier,
                    "required_fields": list(COMPARISON_BINDING_FIELDS),
                },
            )
        placed = {
            "comparison": deepcopy(dict(row)),
            "comparison_id": identifier,
            "evaluator_bundle_id": bundle,
            "reassessment_status": (
                COMPARISON_POTENTIALLY_INVALID
                if bundle == sealed_bundle_id
                else COMPARISON_UNAFFECTED
            ),
        }
        (affected if bundle == sealed_bundle_id else unaffected).append(placed)

    def by_id(row: Mapping[str, Any]) -> str:
        return str(row["comparison_id"])

    return sorted(affected, key=by_id), sorted(unaffected, key=by_id)


def reassess_after_evaluator_drift(
    *,
    firewall: VerifierFirewall,
    current_bundle: Mapping[str, Any],
    comparisons: Sequence[Mapping[str, Any]],
    source_run_id: str,
    defect_class: str,
    evidence_artifact_ids: Sequence[str],
    proposed_change: str,
    reassessed_at: str,
    reassessment_id: str | None = None,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Mark what a drifted evaluator touched and bind the fix to a future run.

    Drift is not decided here.  ``assert_unchanged`` is the firewall's own
    check, and it recomputes the digest from content, so an edit that also
    rewrote ``bundle_hash`` still fires.  When it does not fire there is nothing
    to reassess, and issuing a record anyway would cast doubt on sound
    comparisons — so that case is refused rather than recorded.

    The affected comparisons are *marked*, never removed and never re-scored:
    re-scoring completed candidates under a changed evaluator is the retroactive
    rewrite both quarantine invariants exist to forbid.  The fix is therefore a
    quarantined proposal built by the governance module, and this record only
    carries its id.
    """
    if not isinstance(firewall, VerifierFirewall):
        _fail("INPUT_INVALID", "firewall must be a VerifierFirewall")
    observed = _require_mapping(current_bundle, "current_bundle")
    detail = ""
    try:
        firewall.assert_unchanged(dict(observed))
    except EvaluatorDrift as error:
        detail = str(error)
    else:
        _fail(
            "DRIFT_ABSENT",
            "the current evaluator bundle matches the sealed one",
            {"sealed_bundle_hash": firewall.sealed_hash},
        )

    affected, unaffected = _placed_comparisons(comparisons, firewall.bundle_id)
    proposal = build_evaluator_mutation_proposal(
        source_run_id=source_run_id,
        current_evaluator_bundle_id=firewall.bundle_id,
        defect_class=defect_class,
        evidence_artifact_ids=list(evidence_artifact_ids),
        proposed_change=proposed_change,
        proposal_id=proposal_id,
    )

    reassessment: dict[str, Any] = {
        "affected_comparisons": affected,
        "counts": {
            "affected": len(affected),
            "reviewed": len(affected) + len(unaffected),
            "unaffected": len(unaffected),
        },
        "drift_detail": detail,
        # Re-derived with the shared hashing primitive so the record can name
        # what was observed.  The judgment that this is drift stays the
        # firewall's and is never taken here.
        "observed_bundle_hash": hash_excluding(dict(observed), "bundle_hash"),
        "quarantine_proposal_id": str(proposal["proposal_id"]),
        "reassessed_at": str(reassessed_at),
        "reassessment_id": reassessment_id or new_id("EWR"),
        "retroactive_effect_prohibited": bool(
            proposal["retroactive_effect_prohibited"]
        ),
        "sealed_bundle_hash": firewall.sealed_hash,
        "sealed_bundle_id": firewall.bundle_id,
        "source_run_id": str(proposal["source_run_id"]),
        "unaffected_comparisons": unaffected,
    }
    reassessment["reassessment_hash"] = hash_excluding(
        reassessment, "reassessment_hash"
    )
    return reassessment


def require_forward_only_application(
    reassessment: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    target_run_id: str,
) -> None:
    """Raise unless this reassessment's fix may reach `target_run_id` at all.

    The rule is quarantine's, not this module's: a proposal may never be applied
    to the run that produced it, and a proposal that is still inert may not
    influence any run.  Both refusals travel out as ``QuarantineViolation`` with
    their own message.  All this adds is the binding check — a reassessment
    tested against somebody else's proposal proves nothing about its own fix.
    """
    record = _require_mapping(reassessment, "reassessment")
    given = _require_mapping(proposal, "proposal")
    bound = _require_id(
        record.get("quarantine_proposal_id"), "reassessment.quarantine_proposal_id"
    )
    named = _require_id(given.get("proposal_id"), "proposal.proposal_id")
    if bound != named:
        _fail(
            "REASSESSMENT_PROPOSAL_UNBOUND",
            "the reassessment does not bind the proposal being applied",
            {"bound_proposal_id": bound, "given_proposal_id": named},
        )
    require_not_retroactive(given, target_run_id=_require_id(target_run_id, "target"))
