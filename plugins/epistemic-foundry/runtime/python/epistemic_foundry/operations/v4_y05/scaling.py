"""Quality-diversity scaling, surrogate triage, budgets and production load (Y05).

Y01 sealed typed budget enforcement (a label that actually bounds spend versus a
forecast that only looks like one), Y04 sealed the 50/200/2000 corpus scale
qualification and its load-shedding measurement, N05 sealed the bounded
proposal/evaluation/persistence lanes and their exact fan-in accounting, Q05
sealed the multi-objective, hidden-evaluation and selective-inference
admissibility gate, and X05 sealed cross-provider routing.  Underneath them the
``epistemic_species_archive`` package owns quality-diversity coverage and the
rule that negative, null and minority memory is never evicted for capacity;
``evaluation/surrogate.py`` owns that a surrogate orders work but never removes a
stage; and ``budgets/envelope.py`` owns which enforcement labels actually bound
spend.  Each surface is correct alone; none answers the one question this package
exists for: when a run is pushed to production scale — many niches, a surrogate
triaging thousands of candidates, a hard budget, and load being shed under
pressure — does the *composition* still preserve diversity, keep the surrogate
triage-only, keep spend bounded, and shed load honestly rather than dropping work
silently?

This is an *integration* surface.  It composes the sealed modules and refuses the
compositions that would breach a boundary none of them can see alone, restating
none of their vocabularies (EF4-I22): every canonical token it reasons about is
read positionally out of the schema that declares it, and every protected-class
or bounding-enforcement decision is delegated to the module that owns it, so a
reshaped schema or a weakened owner predicate fails closed rather than silently
selecting the wrong value.

*Quality-diversity scaling.*  ``build_scaled_quality_diversity_map`` composes the
archive's coverage summary so a reported coverage figure cannot drift from the
niches actually occupied.  ``plan_diversity_preserving_rebalance`` derives an
archive-rebalance plan that never evicts a protected class — the null,
counterexample, failed-replication, minority-lineage or unsafe memory the
constitution retains (EF4-I48) — and never empties an occupied niche, so scaling
preserves the trade-off frontier rather than collapsing onto a global top score.

*Surrogate triage.*  ``triage_at_scale`` composes the surrogate surface, forcing
direct evaluation to remain required, and ``require_surrogate_never_promotes``
refuses any attempt to use a triage result to skip a required stage or to stand
in for a promotion decision — a surrogate fitted on past evaluations orders work
but never authorizes it (EF4-I57).  ``bind_triage_to_gate`` composes the sealed
Q05 admissibility gate so the promotion-review authority stays with the gate and
its evaluator/holdout, never with the surrogate's score (EF4-I45).

*Budgets and production load.*  ``require_bounded_production_budget`` composes the
Y01 budget surface so a production run advertises a ceiling only when its label
actually bounds spend (EF4-I28).  ``reconcile_shed_load`` composes the N05
schedule gate so a run that sheds load under budget pressure accounts for every
shed candidate rather than reporting a partial fan-out as complete (EF4-I26).

Every decision resolves to an immutable, content-addressed receipt: two runs over
equal inputs produce byte-equal receipts.  Nothing here scores, promotes, mutates
its inputs, or reads a clock; the caller supplies any timestamp a composed gate
requires.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...budgets.envelope import (
    BudgetViolation,
    requires_escalation_on_breach,
    spend_is_bounded,
)
from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...epistemic_species_archive.archive import (
    PROTECTED_ENTRY_CLASSES,
    ArchivePolicyViolation,
    build_quality_diversity_map,
    evictable_entries,
)
from ...evaluation.surrogate import (
    SurrogateOverreach,
    build_surrogate_triage,
    defers_only,
    require_direct_stage_intact,
)
from ...evaluation.v4_q05.gate import ADMIT, REFUSE
from ...scheduler.v4_n05 import (
    ScheduleError,
    require_valid_schedule,
    seal_schedule_verdict,
    verify_schedule,
)

#: Every way this surface refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this surface requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "VOCABULARY_DRIFT": (
        "a canonical schema no longer declares its triage vocabulary in the shape "
        "this surface reads positionally, so selecting a token by index would pick "
        "the wrong value; the surface fails closed rather than guess"
    ),
    "QD_MAP_CONTRACT_VIOLATED": (
        "the quality-diversity map does not satisfy its canonical schema, so the "
        "coverage the rebalance reasons over would be read from a shape no "
        "contract admits"
    ),
    "REBALANCE_EVICTS_PROTECTED_MEMORY": (
        "an eviction target is a protected class — null, counterexample, failed "
        "replication, minority lineage or unsafe — and dropping it to satisfy a "
        "capacity number re-opens a dead end already paid for (EF4-I48)"
    ),
    "DIVERSITY_COLLAPSE_UNDER_SCALING": (
        "an eviction would empty an occupied niche, so scaling would drop a "
        "region of the trade-off frontier rather than preserve the niches the "
        "archive exists to keep (EF4-I48)"
    ),
    "REBALANCE_PLAN_CONTRACT_VIOLATED": (
        "the archive-rebalance plan does not satisfy its canonical schema, so it "
        "could not be replayed as the record of a capacity decision"
    ),
    "SURROGATE_REPORT_CONTRACT_VIOLATED": (
        "the surrogate triage report does not satisfy its canonical schema, so "
        "the ordering it claims cannot be trusted"
    ),
    "SURROGATE_SKIPS_REQUIRED_STAGE": (
        "a surrogate result is being used to skip a required direct, hidden or "
        "replication stage, and a surrogate fitted on past evaluations orders "
        "work but never removes a stage (EF4-I57)"
    ),
    "SURROGATE_DRIVES_PROMOTION": (
        "a surrogate triage result is being routed as a promotion decision, and a "
        "surrogate score may order search but never promote a candidate (EF4-I45)"
    ),
    "SURROGATE_DIRECT_EVALUATION_WAIVED": (
        "the surrogate report no longer requires direct evaluation, so it has "
        "been turned from an ordering into a stage-skipping authority it may "
        "never hold (EF4-I57)"
    ),
    "PROMOTION_AUTHORITY_NOT_FROM_GATE": (
        "the promotion-review decision does not carry the Q05 admissibility gate's "
        "own verdict, so the authority would rest on the surrogate rather than on "
        "the evaluator and holdout the gate protects (EF4-I45)"
    ),
    "TRIAGE_GATE_CANDIDATE_MISMATCH": (
        "the surrogate triage report and the admissibility receipt describe "
        "different candidates, so binding them would attribute one candidate's "
        "gate decision to another's triage"
    ),
    "BUDGET_ENVELOPE_INVALID": (
        "the budget envelope is internally inconsistent or mislabeled, so no "
        "production ceiling can be attested over it"
    ),
    "BUDGET_NOT_BOUNDED_FOR_PRODUCTION": (
        "the budget's enforcement label does not actually bound spend, so a "
        "production-load run under it has no ceiling and a forecast is being "
        "presented as a limit (EF4-I28)"
    ),
    "LOAD_SHED_FANIN_UNACCOUNTED": (
        "the schedule of a load-shedding run does not account for every proposed "
        "candidate, so a partial fan-out would be reported as a complete one "
        "(EF4-I26)"
    ),
    "LOAD_SHED_DISHONEST_COMPLETION": (
        "a candidate was shed but never recorded as cancelled, so the run would "
        "look complete while silently dropping the work it shed"
    ),
}

#: Canonical schema names this surface reads.  Each is a registered canonical
#: contract (a registry key, not a wire enum value), validated before use rather
#: than restated as fields here.
QD_MAP_KIND = "quality-diversity-map"
REBALANCE_KIND = "archive-rebalance-plan"
SURROGATE_KIND = "surrogate-triage-report"

#: Identifier prefixes.  Every identifier this surface mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
QD_MAP_PREFIX = "YQM-"
REBALANCE_PREFIX = "YQR-"
TRIAGE_PREFIX = "YST-"
BUDGET_ATTESTATION_PREFIX = "YBA-"
LOAD_SHED_PREFIX = "YLS-"
GATE_BINDING_PREFIX = "YPB-"

#: The declared shape of the one triage vocabulary this surface reads
#: positionally out of the surrogate schema.
_TRIAGE_DECISION_TOKENS = 4


class OperationsScalingError(ValueError):
    """The surface refuses a scaling, triage, budget or load-shedding decision."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise OperationsScalingError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise OperationsScalingError(code, message, context)


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


def _enum(kind: str, field: str, expected: int) -> tuple[str, ...]:
    """The declared enum tokens for a schema field, refused on shape drift.

    The tokens are read out of the canonical schema rather than restated here,
    and the count this surface reasons about is checked so a reshaped vocabulary
    fails closed instead of silently letting an index select the wrong token.
    """
    document = default_registry().document(kind)
    enum = document.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(enum, list) or len(enum) != expected:
        _fail(
            "VOCABULARY_DRIFT",
            f"{kind}.{field} is not the expected {expected}-token vocabulary",
            {"enum": enum, "field": field, "schema": kind},
        )
    return tuple(str(value) for value in enum)


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """Every canonical token this surface selects, read positionally from schema.

    Holding these as string literals would be a second copy that drifts from the
    contract (EF4-I22).  The surrogate schema's triage ladder is
    ``[EVALUATE_NOW, DEFER, SAMPLE_FOR_CALIBRATION, REJECT_ONLY_ON_HARD_GATE]``;
    its last rung is the only rejection the schema permits, and it is a
    deterministic hard-gate result rather than a surrogate judgment.  A reshape
    that empties or reorders the ladder fails closed here rather than selecting
    the wrong token.
    """
    triage = _enum(SURROGATE_KIND, "triage_decision", _TRIAGE_DECISION_TOKENS)
    return {"triage_reject_on_hard_gate": triage[-1]}


def surrogate_hard_gate_reject_token() -> str:
    """The canonical hard-gate rejection decision, read from the surrogate schema."""
    return _vocab()["triage_reject_on_hard_gate"]


def _identified(record: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record["receipt_id"] = prefix + sha256_of_payload(record)[len("sha256:") :]
    record["receipt_hash"] = hash_excluding(record, "receipt_hash")
    return record


def _entry_id(entry: Mapping[str, Any]) -> str:
    """The stable identity of an archive entry, preferring its archive-entry id."""
    identifier = entry.get("archive_entry_id") or entry.get("candidate_id")
    return _require_text(identifier, "archive entry identity")


def build_scaled_quality_diversity_map(
    *,
    evolution_run_id: str,
    generation: int,
    niche_ids: Sequence[str],
    occupied_niche_ids: Sequence[str],
    lineage_entropy: float,
    stagnant_niche_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Summarize niche coverage at scale, composing the archive's owner surface.

    The archive module owns the coverage derivation — ``coverage_ratio`` is
    computed from the niche sets rather than supplied, so a reported figure cannot
    drift from the niches actually occupied.  This surface adds only a
    content-derived ``map_id`` so two runs over equal inputs produce a byte-equal
    map; it introduces no clock and no random draw.
    """
    run = _require_text(evolution_run_id, "evolution_run_id")
    niches = [
        _require_text(value, f"niche_ids[{index}]")
        for index, value in enumerate(_require_sequence(niche_ids, "niche_ids"))
    ]
    occupied = [
        _require_text(value, f"occupied_niche_ids[{index}]")
        for index, value in enumerate(
            _require_sequence(occupied_niche_ids, "occupied_niche_ids")
        )
    ]
    stagnant = [
        _require_text(value, f"stagnant_niche_ids[{index}]")
        for index, value in enumerate(
            _require_sequence(stagnant_niche_ids, "stagnant_niche_ids")
        )
    ]
    entropy = _require_number(lineage_entropy, "lineage_entropy")
    map_id = (
        QD_MAP_PREFIX
        + sha256_of_payload(
            {
                "evolution_run_id": run,
                "generation": int(generation),
                "lineage_entropy": entropy,
                "niche_ids": list(niches),
                "occupied_niche_ids": sorted(set(occupied)),
                "stagnant_niche_ids": sorted(set(stagnant)),
            }
        )[len("sha256:") :]
    )
    try:
        return build_quality_diversity_map(
            evolution_run_id=run,
            generation=int(generation),
            niche_ids=niches,
            occupied_niche_ids=occupied,
            lineage_entropy=entropy,
            stagnant_niche_ids=stagnant,
            map_id=map_id,
        )
    except ArchivePolicyViolation as error:
        _fail("QD_MAP_CONTRACT_VIOLATED", str(error), {"evolution_run_id": run})
    except ContractViolation as error:
        _fail(
            "QD_MAP_CONTRACT_VIOLATED",
            "the quality-diversity map does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )


def plan_diversity_preserving_rebalance(
    *,
    quality_diversity_map: Mapping[str, Any],
    archive_entries: Sequence[Mapping[str, Any]],
    capacity: int,
    requested_eviction_ids: Sequence[str] | None = None,
    migration_actions: Sequence[Mapping[str, Any]] = (),
    capacity_changes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a rebalance plan that preserves negative memory and niche coverage.

    Two boundaries are composed and neither substitutes for the other: the
    archive module's protected classes are never evicted for capacity, and no
    eviction may empty an occupied niche.  When the caller names the evictions,
    each named target is checked against both boundaries; otherwise the safe
    evictions are derived — oldest evictable first, skipping any drop that would
    take a niche's last occupant — so reaching capacity never costs a niche.  The
    plan is content-addressed and validated against its canonical schema.
    """
    qd_map = _require_mapping(quality_diversity_map, "quality_diversity_map")
    try:
        validate_artifact(QD_MAP_KIND, dict(qd_map))
    except ContractViolation as error:
        _fail(
            "QD_MAP_CONTRACT_VIOLATED",
            "the quality-diversity map does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    map_id = _require_text(qd_map.get("map_id"), "quality_diversity_map.map_id")

    entries = [
        _require_mapping(entry, f"archive_entries[{index}]")
        for index, entry in enumerate(
            _require_sequence(archive_entries, "archive_entries")
        )
    ]
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 0:
        _fail(
            "INPUT_INVALID",
            "capacity must be a non-negative integer",
            {"capacity": capacity},
        )

    by_id: dict[str, Mapping[str, Any]] = {_entry_id(entry): entry for entry in entries}
    protected_ids = sorted(
        identity
        for identity, entry in by_id.items()
        if str(entry.get("entry_class")) in PROTECTED_ENTRY_CLASSES
    )
    # Occupancy per niche is used to refuse any eviction that would empty a niche.
    occupants: dict[str, list[str]] = {}
    for identity, entry in by_id.items():
        niche = str(entry.get("niche_id"))
        occupants.setdefault(niche, []).append(identity)

    def _would_empty_niche(identity: str, already_removed: set[str]) -> bool:
        niche = str(by_id[identity].get("niche_id"))
        remaining = [
            member
            for member in occupants.get(niche, ())
            if member != identity and member not in already_removed
        ]
        return not remaining

    if requested_eviction_ids is None:
        removed: set[str] = set()
        eviction_candidates: list[str] = []
        for entry in evictable_entries(entries, capacity=capacity):
            identity = _entry_id(entry)
            if _would_empty_niche(identity, removed):
                continue
            removed.add(identity)
            eviction_candidates.append(identity)
    else:
        eviction_candidates = [
            _require_text(value, f"requested_eviction_ids[{index}]")
            for index, value in enumerate(
                _require_sequence(requested_eviction_ids, "requested_eviction_ids")
            )
        ]
        removed = set()
        for identity in eviction_candidates:
            if identity not in by_id:
                _fail(
                    "INPUT_INVALID",
                    "a requested eviction names an entry not in the archive",
                    {"eviction_id": identity},
                )
            if str(by_id[identity].get("entry_class")) in PROTECTED_ENTRY_CLASSES:
                _fail(
                    "REBALANCE_EVICTS_PROTECTED_MEMORY",
                    "an eviction target is a protected class and is never dropped "
                    "for capacity",
                    {
                        "eviction_id": identity,
                        "entry_class": by_id[identity].get("entry_class"),
                    },
                )
            if _would_empty_niche(identity, removed):
                _fail(
                    "DIVERSITY_COLLAPSE_UNDER_SCALING",
                    "an eviction would empty an occupied niche",
                    {
                        "eviction_id": identity,
                        "niche_id": by_id[identity].get("niche_id"),
                    },
                )
            removed.add(identity)

    actions = [
        _require_mapping(action, f"migration_actions[{index}]")
        for index, action in enumerate(
            _require_sequence(migration_actions, "migration_actions")
        )
    ]

    plan: dict[str, Any] = {
        "quality_diversity_map_id": map_id,
        "eviction_candidates": list(eviction_candidates),
        "protected_entry_ids": protected_ids,
        "migration_actions": actions,
        "capacity_changes": dict(capacity_changes or {}),
        # Evicting archived knowledge is a governance-relevant action, so a plan
        # that drops anything always requires approval before it is applied.
        "approval_required": bool(eviction_candidates) or bool(actions),
    }
    plan["plan_id"] = REBALANCE_PREFIX + sha256_of_payload(plan)[len("sha256:") :]
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    try:
        validate_artifact(REBALANCE_KIND, dict(plan))
    except ContractViolation as error:
        _fail(
            "REBALANCE_PLAN_CONTRACT_VIOLATED",
            "the archive-rebalance plan does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    return plan


def triage_at_scale(
    *,
    candidate_id: str,
    surrogate_model_id: str,
    predicted_utility: float,
    predictive_uncertainty: float,
    ood_score: float,
    calibration_window_id: str,
    hard_gate_failed: bool = False,
) -> dict[str, Any]:
    """Triage one candidate, composing the surrogate surface, with a stable id.

    The surrogate surface owns the decision derivation and forces
    ``direct_evaluation_required`` true, so the triage can only order work.  This
    surface adds a content-derived ``report_id`` so two runs over equal inputs
    produce a byte-equal report; it introduces no clock and no random draw and
    holds no promotion authority of its own.
    """
    candidate = _require_text(candidate_id, "candidate_id")
    model = _require_text(surrogate_model_id, "surrogate_model_id")
    window = _require_text(calibration_window_id, "calibration_window_id")
    utility = _require_number(predicted_utility, "predicted_utility")
    uncertainty = _require_number(predictive_uncertainty, "predictive_uncertainty")
    ood = _require_number(ood_score, "ood_score")
    report_id = (
        TRIAGE_PREFIX
        + sha256_of_payload(
            {
                "calibration_window_id": window,
                "candidate_id": candidate,
                "hard_gate_failed": bool(hard_gate_failed),
                "ood_score": ood,
                "predicted_utility": utility,
                "predictive_uncertainty": uncertainty,
                "surrogate_model_id": model,
            }
        )[len("sha256:") :]
    )
    try:
        report = build_surrogate_triage(
            candidate_id=candidate,
            surrogate_model_id=model,
            predicted_utility=utility,
            predictive_uncertainty=uncertainty,
            ood_score=ood,
            calibration_window_id=window,
            hard_gate_failed=bool(hard_gate_failed),
            report_id=report_id,
        )
    except ContractViolation as error:
        _fail(
            "SURROGATE_REPORT_CONTRACT_VIOLATED",
            "the surrogate triage report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    # The owner forces this true; a report that arrived otherwise would be an
    # ordering turned into a stage-skipping authority, so it is refused here.
    if not defers_only(report):
        _fail(
            "SURROGATE_DIRECT_EVALUATION_WAIVED",
            "the surrogate report no longer requires direct evaluation",
            {"report_id": report_id},
        )
    return report


def require_surrogate_never_promotes(
    report: Mapping[str, Any],
    *,
    stage_class: str,
    drives_promotion: bool = False,
) -> Mapping[str, Any]:
    """Refuse using a surrogate result to skip a stage or to promote.

    The stage-intactness check is delegated to the surrogate surface that owns
    it, so the two modules agree on which stages a surrogate may never replace.
    A caller that routes the triage result as a promotion decision is refused
    outright: a surrogate score may order search but never promote.
    """
    triage = _require_mapping(report, "report")
    if not defers_only(triage):
        _fail(
            "SURROGATE_DIRECT_EVALUATION_WAIVED",
            "the surrogate report does not require direct evaluation",
            {"report_id": triage.get("report_id")},
        )
    if drives_promotion:
        _fail(
            "SURROGATE_DRIVES_PROMOTION",
            "a surrogate triage result may order search but never promote",
            {"report_id": triage.get("report_id")},
        )
    try:
        require_direct_stage_intact(
            triage, stage_class=_require_text(stage_class, "stage_class")
        )
    except SurrogateOverreach as error:
        _fail(
            "SURROGATE_SKIPS_REQUIRED_STAGE",
            str(error),
            {"report_id": triage.get("report_id"), "stage_class": stage_class},
        )
    # The guard returns the caller's own report object unchanged: it decides only
    # whether the report may be used, never rewrites it.
    return report


def bind_triage_to_gate(
    *,
    triage_report: Mapping[str, Any],
    gate_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a triage result to the Q05 admissibility gate that holds the authority.

    A surrogate orders the candidate toward evaluation, but the promotion-review
    decision must carry the sealed Q05 gate's own verdict, derived over the
    evaluator and holdout the gate protects.  This surface refuses a binding whose
    "decision" is anything but the gate's own ``ADMIT``/``REFUSE`` verdict, and one
    where the triage and the gate describe different candidates, so the surrogate
    can never stand in for the gate.  The binding receipt is content-addressed.
    """
    triage = _require_mapping(triage_report, "triage_report")
    receipt = _require_mapping(gate_receipt, "gate_receipt")
    if not defers_only(triage):
        _fail(
            "SURROGATE_DIRECT_EVALUATION_WAIVED",
            "the surrogate report bound to the gate does not require direct evaluation",
            {"report_id": triage.get("report_id")},
        )
    decision = str(receipt.get("decision"))
    if decision not in (ADMIT, REFUSE):
        _fail(
            "PROMOTION_AUTHORITY_NOT_FROM_GATE",
            "the promotion-review decision does not carry the Q05 gate's verdict",
            {"decision": receipt.get("decision")},
        )
    triage_candidate = _require_text(
        triage.get("candidate_id"), "triage_report.candidate_id"
    )
    gate_candidate = _require_text(
        receipt.get("candidate_id"), "gate_receipt.candidate_id"
    )
    if triage_candidate != gate_candidate:
        _fail(
            "TRIAGE_GATE_CANDIDATE_MISMATCH",
            "the triage report and the admissibility receipt describe different candidates",
            {"triage_candidate": triage_candidate, "gate_candidate": gate_candidate},
        )

    binding: dict[str, Any] = {
        "candidate_id": gate_candidate,
        "gate_decision": decision,
        "admissible_for_promotion_review": decision == ADMIT,
        "gate_receipt_hash": sha256_of_payload(receipt),
        "surrogate_orders_only": True,
        "surrogate_report_hash": sha256_of_payload(triage),
        "surrogate_report_id": _require_text(
            triage.get("report_id"), "triage_report.report_id"
        ),
    }
    return _identified(binding, GATE_BINDING_PREFIX)


def require_bounded_production_budget(
    budget_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Attest that a production-load run operates under a budget that bounds spend.

    The budget surface owns which enforcement labels actually bound spend; a
    ``SOFT_ESTIMATE`` is a forecast and ``UNMETERED`` is nothing at all.  A
    production run under either has no ceiling, so this surface composes the owner
    predicate and refuses an unbounded budget, returning a content-addressed
    attestation that records whether a breach must interrupt rather than warn.
    """
    envelope = _require_mapping(budget_envelope, "budget_envelope")
    try:
        validate_artifact("budget-envelope", dict(envelope))
    except ContractViolation as error:
        _fail(
            "BUDGET_ENVELOPE_INVALID",
            "the budget envelope does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    except BudgetViolation as error:  # pragma: no cover - schema catches first
        _fail("BUDGET_ENVELOPE_INVALID", str(error))
    if not spend_is_bounded(envelope):
        _fail(
            "BUDGET_NOT_BOUNDED_FOR_PRODUCTION",
            "the budget's enforcement label does not bound spend, so a "
            "production-load run under it has no ceiling",
            {
                "budget_id": envelope.get("budget_id"),
                "enforcement": envelope.get("enforcement"),
            },
        )

    attestation: dict[str, Any] = {
        "budget_id": _require_text(
            envelope.get("budget_id"), "budget_envelope.budget_id"
        ),
        "budget_hash": sha256_of_payload(envelope),
        "enforcement": str(envelope.get("enforcement")),
        "escalates_on_breach": bool(requires_escalation_on_breach(envelope)),
        "spend_is_bounded": True,
    }
    return _identified(attestation, BUDGET_ATTESTATION_PREFIX)


def reconcile_shed_load(
    repository_root: str | Path,
    *,
    budget_envelope: Mapping[str, Any],
    proposed: Sequence[str],
    events: Sequence[Any],
    lane_limits: Mapping[str, Mapping[str, Any]],
    schedule_id: str,
    shed_candidate_ids: Sequence[str] = (),
    failure_ledger: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Attest that a load-shedding run under a bounded budget sheds work honestly.

    Three boundaries are composed.  The budget must actually bound spend, because
    a run that sheds load without a ceiling is shedding under no meter.  Every
    candidate the caller says it shed must be recorded as cancelled, so a shed
    candidate cannot be dropped silently while the run looks complete.  And the
    whole schedule is driven through the N05 gate, which refuses a partial
    provider fan-out that reported itself complete.  The attestation is
    content-addressed and carries the sealed schedule verdict's own hash.
    """
    envelope = _require_mapping(budget_envelope, "budget_envelope")
    try:
        validate_artifact("budget-envelope", dict(envelope))
    except ContractViolation as error:
        _fail(
            "BUDGET_ENVELOPE_INVALID",
            "the budget envelope does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if not spend_is_bounded(envelope):
        _fail(
            "BUDGET_NOT_BOUNDED_FOR_PRODUCTION",
            "a load-shedding run must operate under a budget that bounds spend",
            {
                "budget_id": envelope.get("budget_id"),
                "enforcement": envelope.get("enforcement"),
            },
        )

    shed = [
        _require_text(value, f"shed_candidate_ids[{index}]")
        for index, value in enumerate(
            _require_sequence(shed_candidate_ids, "shed_candidate_ids")
        )
    ]
    cancelled_ids = [
        _require_text(value, f"cancelled_ids[{index}]")
        for index, value in enumerate(_require_sequence(cancelled, "cancelled_ids"))
    ]
    undeclared_shed = sorted(set(shed) - set(cancelled_ids))
    if undeclared_shed:
        _fail(
            "LOAD_SHED_DISHONEST_COMPLETION",
            "a candidate was shed but never recorded as cancelled",
            {"undeclared_shed": undeclared_shed},
        )

    report = verify_schedule(
        repository_root,
        proposed=proposed,
        events=events,
        lane_limits=lane_limits,
        failure_ledger=failure_ledger,
        cancelled=cancelled_ids,
        effect_receipts=effect_receipts,
        mutation_receipts=mutation_receipts,
    )
    try:
        require_valid_schedule(report)
    except ScheduleError as error:
        _fail(
            "LOAD_SHED_FANIN_UNACCOUNTED",
            str(error),
            {"scheduler_code": error.code, "scheduler_context": error.context},
        )
    verdict = seal_schedule_verdict(
        report, schedule_id=_require_text(schedule_id, "schedule_id")
    )

    attestation: dict[str, Any] = {
        "budget_id": _require_text(
            envelope.get("budget_id"), "budget_envelope.budget_id"
        ),
        "budget_hash": sha256_of_payload(envelope),
        "escalates_on_breach": bool(requires_escalation_on_breach(envelope)),
        "schedule_id": str(verdict["schedule_id"]),
        "schedule_valid": bool(verdict["valid"]),
        "shed_candidate_ids": sorted(set(shed)),
        "shed_recorded_as_cancelled": True,
        "verdict_hash": str(verdict["verdict_hash"]),
    }
    return _identified(attestation, LOAD_SHED_PREFIX)


__all__ = [
    "FINDING_CODES",
    "OperationsScalingError",
    "QD_MAP_KIND",
    "REBALANCE_KIND",
    "SURROGATE_KIND",
    "bind_triage_to_gate",
    "build_scaled_quality_diversity_map",
    "plan_diversity_preserving_rebalance",
    "reconcile_shed_load",
    "require_bounded_production_budget",
    "require_surrogate_never_promotes",
    "surrogate_hard_gate_reject_token",
    "triage_at_scale",
]
