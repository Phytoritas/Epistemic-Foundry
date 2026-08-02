"""2,000-document evolution qualification and cost/latency integration gate (Y06).

Y05 sealed the production-scale operations surface — quality-diversity scaling, a
triage-only surrogate, a bounded production budget and honest load shedding — and
each of its gates is correct alone.  E05 sealed the three-way count reconciliation
that binds the candidate fan-out to the effect and mutation ledgers, and the
budget module owns which enforcement labels actually bound spend.  What none of
them answers is the question a full 2,000-document qualification run turns on: when
a production run is *declared complete at scale*, do its per-stage counts reconcile
exactly, does its measured cost and latency stay inside the budget it advertised,
did its surrogate accept no more work than its budget allowed, and did the scale
run stay a search — never becoming an authority path that binds a score into a
promotion decision?

This is the *integration* gate over such a run.  No real 2,000-document run is
executed here; the run is modelled as a declared manifest of per-stage counts and
cost/latency measurements the caller supplies, and the gate reconciles that
declaration against the sealed owners it composes.  It restates none of their
vocabularies (EF4-I22): the reconciliation stages come from the chamber, the
budget dimensions from the budget module, the surrogate acceptance token is read
positionally out of the schema that declares it, and the promotion authority is
grounded in the canonical ``promotion:commit`` capability imported from the
evolution-authority registry, so a reshaped schema or a renamed capability fails
closed rather than silently selecting the wrong value.

*Count reconciliation.*  ``reconcile_qualification_counts`` composes the E05
three-way reconciliation and then holds the run's *declared* expected per-stage
counts against the counts actually reconciled — a silent partial fan-in, an orphan
side effect or a declared count that does not match refuses rather than reports a
number.

*Cost and latency.*  ``require_bounded_qualification_budget`` composes the Y05
bounded-budget attestation (the budget must actually bound spend, not merely
forecast it, EF4-I28) and then checks every measured cost and latency dimension
against the ceiling the envelope declares for it, refusing an overrun by name.

*Surrogate ceiling.*  ``require_surrogate_within_ceiling`` composes the surrogate
owner's ordering predicate to keep every triage report triage-only and refuses a
run whose surrogate accepted more candidates for immediate evaluation than its
declared budget ceiling permits (EF4-I57).

*Authority containment.*  ``require_no_scale_authority_capture`` refuses any
qualification record that grants a mutable-search artifact — a candidate, model,
prompt or backend — the canonical promotion authority, or that binds a numeric
score into a promotion decision, so the scale run can never become the authority
path the constitution keeps outside the mutable search space (EF4-I45).

``qualify_evolution_run`` composes the four into one sealed qualification verdict.
Every decision resolves to an immutable, content-addressed receipt: two runs over
equal inputs produce byte-equal receipts.  Nothing here scores, promotes, mutates
its inputs or reads a clock; the caller supplies every identifier a receipt binds.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

from ...budgets.envelope import LIMIT_DIMENSIONS
from ...contracts import default_registry
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...effects.v4_e05 import (
    EffectReconciliationError,
    reconcile_effect_ledger,
    require_effect_reconciliation,
)
from ...evaluation.surrogate import defers_only
from ...evolution_chamber.reconciliation import STAGES, TERMINAL_DISPOSITIONS
from ...governance.evolution_authority.registry import PROMOTION_COMMIT_CAPABILITY
from ...operations.v4_y05 import (
    SURROGATE_KIND,
    OperationsScalingError,
    require_bounded_production_budget,
)

#: Every way this surface refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership and
#: every code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would record "
        "a qualification decision derived from something it never validated"
    ),
    "VOCABULARY_DRIFT": (
        "the surrogate triage vocabulary is no longer the four-token ladder this "
        "gate reads positionally, so selecting the acceptance token by index would "
        "pick the wrong value; the gate fails closed rather than guess"
    ),
    "COUNT_DECLARATION_MISMATCH": (
        "a per-stage count the qualification declared as expected differs from the "
        "count the composed reconciliation actually accounts for, so the run is "
        "reporting a fan-out size it did not achieve"
    ),
    "QUALIFICATION_FANIN_UNRECONCILED": (
        "the composed effect-ledger reconciliation refused the run — a silent "
        "partial fan-in, an orphan side effect or an unresolved candidate — so the "
        "qualification cannot be recorded as a complete run (EF4-I26)"
    ),
    "BUDGET_ENVELOPE_INVALID": (
        "the budget envelope is internally inconsistent or fails its canonical "
        "schema, so no cost or latency ceiling can be attested over it"
    ),
    "BUDGET_NOT_BOUNDED_FOR_QUALIFICATION": (
        "the budget's enforcement label does not actually bound spend, so a "
        "2,000-document qualification run under it has no ceiling and a forecast is "
        "being presented as a limit (EF4-I28)"
    ),
    "BUDGET_DIMENSION_OVERRUN": (
        "a measured cost or latency dimension exceeded the ceiling the declared "
        "budget envelope sets for it, so the run overspent the resource named in "
        "the refusal rather than staying inside its envelope"
    ),
    "SURROGATE_ORDERING_WAIVED": (
        "a surrogate triage report no longer requires direct evaluation, so it has "
        "been turned from an ordering into the stage-skipping authority a surrogate "
        "may never hold (EF4-I57)"
    ),
    "SURROGATE_ACCEPTANCE_EXCEEDS_CEILING": (
        "the surrogate accepted more candidates for immediate evaluation than the "
        "declared surrogate budget ceiling permits at scale, so triage promoted "
        "more work than its budget allows (EF4-I57)"
    ),
    "SCALE_RUN_ACQUIRES_PROMOTION_AUTHORITY": (
        "a candidate, model, prompt or backend in the mutable search space was "
        "granted evaluator, holdout or promotion authority at scale, so the scale "
        "run would itself become an authority path (EF4-I45)"
    ),
    "SCORE_BOUND_INTO_PROMOTION_FIELD": (
        "a qualification record binds a numeric score into a promotion-authority "
        "decision, which would let a proxy score stand in for the sealed gate "
        "verdict the promotion authority must carry (EF4-I45)"
    ),
}

#: Identifier prefixes.  Every identifier this gate mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
QUAL_COUNT_PREFIX = "QIC-"
QUAL_BUDGET_PREFIX = "QBG-"
QUAL_SURROGATE_PREFIX = "QSC-"
QUAL_AUTHORITY_PREFIX = "QAG-"
QUAL_VERDICT_PREFIX = "QVR-"

#: The declared shape of the surrogate triage ladder this gate reads positionally,
#: and the index of the acceptance ("evaluate now") rung within it.
_TRIAGE_DECISION_TOKENS = 4
_TRIAGE_ACCEPT_INDEX = 0

#: The cost dimension is the envelope's soft-cost figure rather than a hard-limit
#: dimension, so it is named here rather than read from ``LIMIT_DIMENSIONS``; it
#: is a report label, not a canonical wire value.
COST_DIMENSION = "cost"


class OperationsQualificationError(ValueError):
    """The gate refuses a count, budget, surrogate or authority qualification."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise OperationsQualificationError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise OperationsQualificationError(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("INPUT_INVALID", f"{label} must be a number", {"label": label})
    return float(value)  # type: ignore[arg-type]


def _require_count(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(
            "INPUT_INVALID",
            f"{label} must be a non-negative integer",
            {"label": label, "value": value},
        )
    return int(value)  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def _accept_decision_token() -> str:
    """The surrogate acceptance token, read positionally from the schema ladder.

    Holding the token as a literal would be a second copy that drifts from the
    contract (EF4-I22).  The surrogate schema's triage ladder leads with the
    "evaluate now" acceptance rung; a reshape that empties or reorders the ladder
    fails closed here rather than selecting the wrong token.
    """
    document = default_registry().document(SURROGATE_KIND)
    enum = document.get("properties", {}).get("triage_decision", {}).get("enum")
    if not isinstance(enum, list) or len(enum) != _TRIAGE_DECISION_TOKENS:
        _fail(
            "VOCABULARY_DRIFT",
            "the surrogate triage vocabulary is not the expected four-token ladder",
            {"enum": enum, "schema": SURROGATE_KIND},
        )
    return str(enum[_TRIAGE_ACCEPT_INDEX])


def surrogate_acceptance_token() -> str:
    """The canonical surrogate acceptance decision, read from the schema."""
    return _accept_decision_token()


def _identified(record: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record["receipt_id"] = prefix + sha256_of_payload(record)[len("sha256:") :]
    record["receipt_hash"] = hash_excluding(record, "receipt_hash")
    return record


def _carries_score(basis: Mapping[str, Any]) -> bool:
    """Whether a decision basis carries a raw numeric score.

    A promotion decision must be a sealed gate verdict — a reference or a boolean
    admissibility, never a raw number a proxy could produce — so any non-boolean
    numeric value in the basis is a score being bound into the decision.
    """
    for value in basis.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return True
    return False


def reconcile_qualification_counts(
    *,
    qualification_run_id: str,
    expected_counts: Mapping[str, int],
    proposed: Sequence[str],
    generated: Sequence[str],
    evaluated: Sequence[str],
    persisted: Sequence[str],
    failed: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Reconcile a qualification run's declared counts against the sealed ledgers.

    The three-way count reconciliation is delegated to the E05 engine, which binds
    the candidate fan-out to the effect and mutation receipts and refuses a silent
    partial fan-in or an orphan side effect.  This gate adds the one check the
    engine cannot see: the run's *declared* expected per-stage counts must equal
    the counts actually reconciled, so a run cannot advertise a 2,000-document
    fan-out it did not achieve.  The receipt is content-addressed.
    """
    run = _require_text(qualification_run_id, "qualification_run_id")
    declared = _require_mapping(expected_counts, "expected_counts")
    known_stages = {*STAGES, *TERMINAL_DISPOSITIONS}
    unknown_stages = sorted(set(declared) - known_stages)
    if unknown_stages:
        _fail(
            "INPUT_INVALID",
            "an expected-count stage is not a canonical reconciliation stage",
            {"unknown_stages": unknown_stages, "known_stages": sorted(known_stages)},
        )
    for stage, value in declared.items():
        _require_count(value, f"expected_counts[{stage}]")

    try:
        report = reconcile_effect_ledger(
            proposed=proposed,
            generated=generated,
            evaluated=evaluated,
            persisted=persisted,
            failed=failed,
            cancelled=cancelled,
            effect_receipts=effect_receipts,
            mutation_receipts=mutation_receipts,
        )
    except EffectReconciliationError as error:
        _fail(
            "INPUT_INVALID",
            f"the ledger inputs could not be indexed: {error}",
            {"effect_code": error.code, "effect_context": error.context},
        )

    try:
        require_effect_reconciliation(report)
    except EffectReconciliationError as error:
        _fail(
            "QUALIFICATION_FANIN_UNRECONCILED",
            str(error),
            {"fanin_code": error.code, "fanin_context": error.context},
        )

    actual = report["candidates"]["counts"]
    mismatches = [
        {"stage": stage, "declared": declared[stage], "actual": actual.get(stage)}
        for stage in sorted(declared)
        if declared[stage] != actual.get(stage)
    ]
    if mismatches:
        _fail(
            "COUNT_DECLARATION_MISMATCH",
            "the declared expected counts differ from the reconciled per-stage counts",
            {"mismatches": mismatches},
        )

    receipt: dict[str, Any] = {
        "qualification_run_id": run,
        "reconciled": True,
        "stage_counts": dict(actual),
        "ledger_counts": dict(report["counts"]),
        "reconciliation_report_hash": sha256_of_payload(report),
    }
    return _identified(receipt, QUAL_COUNT_PREFIX)


def require_bounded_qualification_budget(
    *,
    budget_envelope: Mapping[str, Any],
    measured_cost: float,
    measured_usage: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Attest that a qualification run stayed inside a budget that bounds spend.

    The Y05 bounded-budget attestation is composed first: a production-scale run
    advertises a ceiling only when its enforcement label actually bounds spend, so
    a forecast can never be presented as a limit.  This gate then holds the run's
    measured cost against the envelope's soft-cost figure and every measured
    latency or resource dimension against the matching hard limit, refusing an
    overrun by the name of the dimension it breached.  The receipt is
    content-addressed.
    """
    envelope = _require_mapping(budget_envelope, "budget_envelope")
    try:
        attestation = require_bounded_production_budget(envelope)
    except OperationsScalingError as error:
        if error.code == "BUDGET_NOT_BOUNDED_FOR_PRODUCTION":
            _fail(
                "BUDGET_NOT_BOUNDED_FOR_QUALIFICATION",
                "a 2,000-document qualification run must operate under a budget whose "
                "enforcement label actually bounds spend",
                {
                    "budget_id": envelope.get("budget_id"),
                    "enforcement": envelope.get("enforcement"),
                },
            )
        _fail("BUDGET_ENVELOPE_INVALID", str(error), dict(error.context))

    cost = _require_number(measured_cost, "measured_cost")
    usage = (
        _require_mapping(measured_usage, "measured_usage")
        if measured_usage is not None
        else {}
    )
    hard_limits = _require_mapping(
        envelope.get("hard_limits"), "budget_envelope.hard_limits"
    )

    overruns: list[dict[str, Any]] = []
    declared_cost = envelope.get("soft_cost_amount")
    if (
        isinstance(declared_cost, (int, float))
        and not isinstance(declared_cost, bool)
        and cost > float(declared_cost)
    ):
        overruns.append(
            {
                "dimension": COST_DIMENSION,
                "measured": cost,
                "limit": float(declared_cost),
            }
        )

    for dimension in sorted(usage):
        if dimension not in LIMIT_DIMENSIONS:
            _fail(
                "INPUT_INVALID",
                "a measured-usage dimension is not a declared budget dimension",
                {"dimension": dimension, "declared_dimensions": list(LIMIT_DIMENSIONS)},
            )
        measured = _require_number(usage[dimension], f"measured_usage[{dimension}]")
        limit = hard_limits.get(dimension)
        if (
            isinstance(limit, (int, float))
            and not isinstance(limit, bool)
            and measured > float(limit)
        ):
            overruns.append(
                {"dimension": dimension, "measured": measured, "limit": float(limit)}
            )

    if overruns:
        _fail(
            "BUDGET_DIMENSION_OVERRUN",
            "a measured cost or latency dimension exceeded the ceiling the declared "
            "budget envelope sets for it",
            {"overruns": overruns},
        )

    receipt: dict[str, Any] = {
        "budget_id": _require_text(
            envelope.get("budget_id"), "budget_envelope.budget_id"
        ),
        "budget_attestation_hash": str(attestation["receipt_hash"]),
        "escalates_on_breach": bool(attestation["escalates_on_breach"]),
        "measured_cost": cost,
        "measured_usage": {dim: float(value) for dim, value in usage.items()},
        "spend_is_bounded": True,
        "within_budget": True,
    }
    return _identified(receipt, QUAL_BUDGET_PREFIX)


def require_surrogate_within_ceiling(
    *,
    triage_reports: Sequence[Mapping[str, Any]],
    surrogate_ceiling: int,
) -> dict[str, Any]:
    """Refuse a run whose surrogate accepted more work than its budget allows.

    Each triage report is held to the surrogate owner's ordering predicate, so a
    report that stopped requiring direct evaluation — an ordering turned into a
    stage-skipping authority — is refused.  The accepted count is the number of
    reports whose decision is the schema's acceptance rung, read positionally; a
    run that accepted more than its declared ceiling permits is refused.  The
    receipt is content-addressed.
    """
    ceiling = _require_count(surrogate_ceiling, "surrogate_ceiling")
    reports = _require_sequence(triage_reports, "triage_reports")
    accept_token = _accept_decision_token()

    accepted = 0
    for index, entry in enumerate(reports):
        report = _require_mapping(entry, f"triage_reports[{index}]")
        if not defers_only(report):
            _fail(
                "SURROGATE_ORDERING_WAIVED",
                "a surrogate triage report no longer requires direct evaluation",
                {"report_id": report.get("report_id")},
            )
        if str(report.get("triage_decision")) == accept_token:
            accepted += 1

    if accepted > ceiling:
        _fail(
            "SURROGATE_ACCEPTANCE_EXCEEDS_CEILING",
            "the surrogate accepted more candidates for immediate evaluation than "
            "the declared surrogate budget ceiling permits",
            {"accepted_count": accepted, "ceiling": ceiling},
        )

    receipt: dict[str, Any] = {
        "accepted_count": accepted,
        "ceiling": ceiling,
        "report_count": len(reports),
        "within_ceiling": True,
    }
    return _identified(receipt, QUAL_SURROGATE_PREFIX)


def require_no_scale_authority_capture(
    *,
    authority_claims: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Refuse the scale run becoming a promotion-authority path.

    Two boundaries are composed and neither substitutes for the other.  A claim
    that grants the canonical ``promotion:commit`` capability — or any authority
    the caller marks protected — to a mutable-search artifact (a candidate, model,
    prompt or backend) is refused: the search space may never acquire evaluator,
    holdout or promotion authority.  And a claim that binds a numeric score into a
    protected authority is refused: a proxy score may order search but never carry
    the promotion verdict.  The canonical promotion capability is always treated
    as protected, so a claim cannot launder it as ordinary.  The receipt is
    content-addressed.
    """
    claims = _require_sequence(authority_claims, "authority_claims")

    summary: list[dict[str, Any]] = []
    for index, entry in enumerate(claims):
        claim = _require_mapping(entry, f"authority_claims[{index}]")
        capability = _require_text(
            claim.get("capability_id"), f"authority_claims[{index}].capability_id"
        )
        holder = _require_text(
            claim.get("holder_id"), f"authority_claims[{index}].holder_id"
        )
        search = bool(claim.get("holder_is_search_space", False))
        protected = bool(claim.get("protected_authority", False))
        basis = claim.get("decision_basis") or {}
        if not isinstance(basis, Mapping):
            _fail(
                "INPUT_INVALID",
                f"authority_claims[{index}].decision_basis must be a mapping",
                {"index": index},
            )
        # Ground the self-reported flag in the canonical capability: the
        # promotion-commit capability is protected authority by definition.
        if capability == PROMOTION_COMMIT_CAPABILITY:
            protected = True

        if protected and search:
            _fail(
                "SCALE_RUN_ACQUIRES_PROMOTION_AUTHORITY",
                "a mutable-search artifact was granted a protected evaluator, "
                "holdout or promotion authority at scale",
                {"capability_id": capability, "holder_id": holder},
            )
        if protected and _carries_score(basis):
            _fail(
                "SCORE_BOUND_INTO_PROMOTION_FIELD",
                "a qualification record binds a numeric score into a "
                "promotion-authority decision",
                {"capability_id": capability, "holder_id": holder},
            )
        summary.append(
            {
                "capability_id": capability,
                "holder_id": holder,
                "holder_is_search_space": search,
                "protected_authority": protected,
            }
        )

    receipt: dict[str, Any] = {
        "authority_claims": summary,
        "no_authority_captured": True,
    }
    return _identified(receipt, QUAL_AUTHORITY_PREFIX)


def qualify_evolution_run(
    *,
    qualification_run_id: str,
    expected_counts: Mapping[str, int],
    proposed: Sequence[str],
    generated: Sequence[str],
    evaluated: Sequence[str],
    persisted: Sequence[str],
    budget_envelope: Mapping[str, Any],
    measured_cost: float,
    surrogate_ceiling: int,
    failed: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
    measured_usage: Mapping[str, float] | None = None,
    triage_reports: Sequence[Mapping[str, Any]] = (),
    authority_claims: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Run the whole qualification gate and seal one verdict over its sub-receipts.

    The four sub-gates each refuse independently; only when the counts reconcile,
    the cost and latency stay inside the budget, the surrogate stayed within its
    ceiling and no authority was captured does this seal a qualification verdict.
    The verdict binds each sub-receipt by hash, so the verdict cannot be forged
    without reproducing every gate it depends on.  The verdict is content-addressed
    and carries no clock or random draw.
    """
    run = _require_text(qualification_run_id, "qualification_run_id")
    counts = reconcile_qualification_counts(
        qualification_run_id=run,
        expected_counts=expected_counts,
        proposed=proposed,
        generated=generated,
        evaluated=evaluated,
        persisted=persisted,
        failed=failed,
        cancelled=cancelled,
        effect_receipts=effect_receipts,
        mutation_receipts=mutation_receipts,
    )
    budget = require_bounded_qualification_budget(
        budget_envelope=budget_envelope,
        measured_cost=measured_cost,
        measured_usage=measured_usage,
    )
    surrogate = require_surrogate_within_ceiling(
        triage_reports=triage_reports,
        surrogate_ceiling=surrogate_ceiling,
    )
    authority = require_no_scale_authority_capture(authority_claims=authority_claims)

    verdict: dict[str, Any] = {
        "qualification_run_id": run,
        "qualification_passed": True,
        "count_receipt_id": counts["receipt_id"],
        "count_receipt_hash": counts["receipt_hash"],
        "budget_receipt_id": budget["receipt_id"],
        "budget_receipt_hash": budget["receipt_hash"],
        "surrogate_receipt_id": surrogate["receipt_id"],
        "surrogate_receipt_hash": surrogate["receipt_hash"],
        "authority_receipt_id": authority["receipt_id"],
        "authority_receipt_hash": authority["receipt_hash"],
    }
    return _identified(verdict, QUAL_VERDICT_PREFIX)


__all__ = [
    "COST_DIMENSION",
    "FINDING_CODES",
    "OperationsQualificationError",
    "QUAL_AUTHORITY_PREFIX",
    "QUAL_BUDGET_PREFIX",
    "QUAL_COUNT_PREFIX",
    "QUAL_SURROGATE_PREFIX",
    "QUAL_VERDICT_PREFIX",
    "qualify_evolution_run",
    "reconcile_qualification_counts",
    "require_bounded_qualification_budget",
    "require_no_scale_authority_capture",
    "require_surrogate_within_ceiling",
    "surrogate_acceptance_token",
]
