"""Search-completeness, novelty-failure and prior-art integration gate.

O05 sealed three questions about an evolution run's evidence retrieval: where it
may look, what it learned on each novelty layer, and where the map is still
blind.  Q05 sealed a fourth: whether an adaptively-selected candidate is
statistically admissible without a score ever buying a promotion.  Neither
answers the one question this gate exists to close: *has the search that grounds
a novelty or prior-art claim actually been completed, and does that claim rest on
a statistically-admissible candidate rather than on an absence the search never
earned?*

Novelty is EARNED by a COMPLETE search.  "We searched every required lane and
found nothing" and "our search never reached the required source" both produce an
empty prior-art set, and only the first supports a novelty claim.  So this gate
does two things and refuses to do a third.

*It reconciles a search-completeness certificate.*  The eleven canonical
retrieval lanes O05 emits receipts for are reconciled into the canonical
``search-completeness-certificate``: every lane's reconciled state is *derived*
from its receipt rather than accepted as a parameter, the run's completion state
is derived from the required lanes' reconciled states, and the absence and
novelty claim ceilings are derived from the completion state and whether the
external-novelty lane was conclusively reached.  A caller cannot label a lane it
never queried as complete, and an incomplete run yields the lowest ceiling rather
than a bare claim.

*It gates the claim.*  Given a certificate, a novelty assessment that cites it,
the sources a prior-art determination was required to cover, and a Q05
admissibility receipt, the gate decides one thing: is this claim *admissible to
be forwarded to promotion review*?  It refuses a novelty claim whose certificate
is missing or whose completion did not earn a novelty ceiling; it refuses any
determination that left a required source unsearched; and it composes the sealed
Q05 receipt so a candidate reaches review only when a real fitness vector — never
a scalar score — cleared the statistical gate.  It never promotes anything: the
receipt carries ``admissible_for_promotion_review``, and promotion authority
lives elsewhere and takes no score from here.

It is an *integration* gate (EF4-I22): it composes the already-sealed O05
retrieval surface, the K05/evaluation novelty owners and the Q05 admissibility
gate, and restates none of their vocabularies.  Every canonical enum token it
reasons about — lane states, completion states, claim ceilings, work classes — is
read from the schema that declares it or imported from the surface that owns it,
positionally where the value's own name would be a wire literal elsewhere.  Every
decision, allow or refuse, resolves to one immutable receipt that is a pure
function of its inputs: there is no clock and no random draw, and the certificate
id, certificate hash, gate id and receipt hash re-derive byte for byte.  No input
is ever mutated.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    validate_artifact,
)
from ...domain.hashing import (
    SHA256_PREFIX,
    hash_excluding,
    sha256_of_payload,
)
from ...evaluation.novelty import novelty_supports_claim
from ...evaluation.v4_q05.gate import (
    ADMIT,
    REFUSE,
    GATE_NAME as Q05_GATE_NAME,
)
from ...evidence.v4_k05 import (
    NOVELTY_SCHEMA,
    NOVELTY_STATUS_POSITION,
    scalar_enum_field,
)
from ...verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES
from ..v4_o05 import (
    CERTIFICATE_SCHEMA,
    EXTERNAL_LANE_POSITION,
    RECEIPT_SCHEMA,
    SEARCHED_NONE_STATE_POSITION,
    SEARCHED_WITH_RESULTS_STATE_POSITION,
    SELECTED_DISPOSITION_POSITION,
    UNSEARCHED_STATE_POSITION,
    canonical_lane_order,
    derive_content_addressed_record_identity,
    plan_disposition_vocabulary,
    receipt_state_vocabulary,
    require_plan_identity,
)

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative-and-adversarial
#: suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "reconcile or decide against something it never validated"
    ),
    "RECEIPT_REFUSED": (
        "the canonical schema refused a lane receipt, so the reconciliation "
        "would be built over a receipt no reader can validate"
    ),
    "RECEIPT_NOT_FROM_PLAN": (
        "a lane receipt binds a different retrieval plan than the one this "
        "certificate reconciles, so the two describe different searches"
    ),
    "LANE_UNDECLARED": (
        "a lane receipt names a lane outside the canonical retrieval "
        "vocabulary, or the plan declares no disposition for it"
    ),
    "LANE_COVERAGE_INCOMPLETE": (
        "the receipt set does not account for every canonical lane exactly "
        "once, and an unaccounted lane has no reconciled search state"
    ),
    "LANE_DISPOSITION_CONFLICT": (
        "a lane receipt's search state contradicts the plan's own disposition "
        "for that lane, so what ran disagrees with what was chosen"
    ),
    "WORK_CLASS_UNDECLARED": (
        "the certificate's work class is outside the canonical vocabulary, so "
        "the required-lane rule that governs completion cannot be applied"
    ),
    "REQUIRED_LANE_UNDECLARED": (
        "a required lane is outside the canonical retrieval vocabulary, so a "
        "completion state could never be reconciled against it"
    ),
    "REQUIRED_LANE_NOT_SEARCHED": (
        "a lane the work class requires was not selected and conclusively "
        "searched, so the run cannot certify a completed search over it"
    ),
    "WORK_CLASS_LANE_RULE_VIOLATED": (
        "the required-lane set contradicts the work class's own lane rule — an "
        "exempt class demanded lanes, or a graded class omitted its canonical "
        "floor"
    ),
    "CERTIFICATE_REFUSED": (
        "the reconciled certificate does not satisfy the canonical "
        "search-completeness-certificate schema"
    ),
    "CERTIFICATE_MISSING": (
        "a novelty or prior-art claim was gated without any search-completeness "
        "certificate, so no completed search grounds it"
    ),
    "CERTIFICATE_DRIFT": (
        "the certificate does not re-derive its own identifier or hash, so the "
        "search being certified is not the search that was reconciled"
    ),
    "CLAIM_REFUSED": (
        "the canonical schema refused the novelty assessment, or the assessment "
        "does not re-derive its own hash, so the claim the gate would forward "
        "is not a valid, untampered assessment"
    ),
    "CLAIM_CERTIFICATE_MISMATCH": (
        "the novelty assessment cites a different search-completeness "
        "certificate than the one presented, so its search is not this search"
    ),
    "SUBJECT_IDENTITY_MISMATCH": (
        "the certificate and the novelty assessment do not describe the one "
        "subject this decision is about"
    ),
    "NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH": (
        "a novelty claim was made whose certificate did not earn a novelty "
        "ceiling — the search was incomplete, so the novelty was never earned"
    ),
    "PRIOR_ART_IGNORED_REQUIRED_SOURCE": (
        "a determination was forwarded while a source it was required to search "
        "remained unsearched, so an absence was claimed the search never reached"
    ),
    "ADMISSIBILITY_RECEIPT_REFUSED": (
        "the Q05 admissibility receipt is not an ADMIT for this candidate, is "
        "from a different gate, or does not re-derive its own hash, so the "
        "candidate is not statistically cleared to be forwarded"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the admissibility receipt describes a different candidate than the one "
        "this novelty or prior-art claim is about"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the admissibility decision, and "
        "a role that proposes candidates may never acquire authority over them"
    ),
}

#: Identifier prefixes.  Both are derived from the record's own content, so two
#: runs over equal inputs produce byte-equal records and nothing needs entropy.
CERTIFICATE_ID_PREFIX = "SCC-"
GATE_ID_PREFIX = "SNG-"

#: The gate's own decision receipt name.  Not a canonical schema enum value.
GATE_NAME = "search-completeness-novelty-integration"

#: The canonical schema that owns the E0-E5 required-lane floors.
_QUERY_PLAN_SCHEMA = "query-plan"

#: Positions in the certificate's ``completion_state`` ladder, declared from the
#: not-required state through the passing state to the three degraded states.
#: The schema-and-type suite asserts every position against the schema text.
COMPLETION_NOT_REQUIRED_POSITION = 0
COMPLETION_PASS_POSITION = 1
COMPLETION_PARTIAL_POSITION = 2
COMPLETION_BLOCKED_POSITION = 3
COMPLETION_FAIL_POSITION = 4

#: Positions in the ``absence_claim_ceiling`` vocabulary the reconciliation
#: emits.  ``LOCAL_CORPUS_ONLY`` (position 1) is deliberately never produced:
#: this gate distinguishes only "nothing earned", "corpus searched, outside
#: open" and "outside searched too".
ABSENCE_NONE_POSITION = 0
ABSENCE_CORPUS_CONDITIONAL_POSITION = 2
ABSENCE_EXTERNAL_CONDITIONAL_POSITION = 3

#: Positions in the ``novelty_claim_ceiling`` vocabulary the reconciliation
#: emits.  ``PRIOR_ART_FOUND`` (the last member) is a *finding* an assessment
#: makes, never a ceiling a completeness certificate derives, so it is never
#: produced here.
NOVELTY_NOT_ASSESSED_POSITION = 0
NOVELTY_CORPUS_NOVEL_ONLY_POSITION = 1
NOVELTY_SEARCH_CONDITIONAL_POSITION = 2

#: Positions in the receipt-state vocabulary O05 owns for the three inconclusive
#: outcomes.  The first three (unsearched and the two conclusive ones) are read
#: through O05's exported positions; these three are the degraded tail.
RECEIPT_PARTIAL_POSITION = 3
RECEIPT_BLOCKED_POSITION = 4
RECEIPT_FAILED_POSITION = 5

#: Position of the exempt work class (the one that requires no lanes).  Its rule
#: is asserted against the certificate schema's own E0 branch.
EXEMPT_WORK_CLASS_POSITION = 0

#: Fields the gate reads back off the sealed Q05 admissibility receipt.  These
#: are property names on Q05's own receipt, not wire enum values.
Q05_GATE_FIELD = "gate"
Q05_DECISION_FIELD = "decision"
Q05_CANDIDATE_FIELD = "candidate_id"
Q05_FORWARD_FIELD = "admissible_for_promotion_review"
Q05_RECEIPT_HASH_FIELD = "receipt_hash"


class SearchIntegrityRefused(ValueError):
    """The gate refuses a certificate, a claim or a determination, with a code."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise SearchIntegrityRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise SearchIntegrityRefused(code, message, context)


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


def _digest_body(payload: Any) -> str:
    """The hex body of a canonical digest, used to derive content-bound ids."""
    return sha256_of_payload(payload)[len(SHA256_PREFIX) :]


# -- declared vocabularies, read from the canonical schema ----------------


def _certificate_schema() -> dict[str, Any]:
    return default_registry().document(CERTIFICATE_SCHEMA)


def _scalar_enum(field: str) -> tuple[str, ...]:
    """The declared enum of a scalar certificate property, in schema order."""
    enum = _certificate_schema()["properties"][field].get("enum")
    if not isinstance(enum, list) or not enum:
        _fail(
            "CERTIFICATE_REFUSED",
            f"the certificate schema declares no enum for {field}",
            {"field": field},
        )
    return tuple(str(value) for value in enum)


def completion_state_vocabulary() -> tuple[str, ...]:
    """The run completion states, read from the certificate schema."""
    return _scalar_enum("completion_state")


def absence_ceiling_vocabulary() -> tuple[str, ...]:
    """The absence-claim ceilings, read from the certificate schema."""
    return _scalar_enum("absence_claim_ceiling")


def novelty_ceiling_vocabulary() -> tuple[str, ...]:
    """The novelty-claim ceilings, read from the certificate schema."""
    return _scalar_enum("novelty_claim_ceiling")


def work_class_vocabulary() -> tuple[str, ...]:
    """The epistemic work classes, read from the certificate schema."""
    return _scalar_enum("work_class")


def _work_class_lane_floor(work_class: str) -> tuple[str, ...]:
    """The non-waivable lane floor declared for one QueryPlan work class."""
    document = default_registry().document(_QUERY_PLAN_SCHEMA)
    for branch in document["allOf"]:
        selector = branch["if"]["properties"]["work_class"]
        declared_classes = selector.get("enum", [selector.get("const")])
        if work_class not in declared_classes:
            continue
        rule = branch["then"]["properties"]["required_lanes"]
        exact_floor = rule.get("const")
        if isinstance(exact_floor, list):
            return tuple(str(lane) for lane in exact_floor)
        floor = tuple(
            str(constraint["contains"]["const"])
            for constraint in rule.get("allOf", [])
        )
        if floor or rule.get("maxItems") == 0:
            return floor
        break

    return _fail(
        "CERTIFICATE_REFUSED",
        "the query-plan schema declares no required-lane floor for the work class",
        {"work_class": work_class},
    )


def _disposition_tokens() -> tuple[str, str, str]:
    """The plan/reconciliation dispositions: selecting, and the two sentinels."""
    declared = plan_disposition_vocabulary()
    selecting = declared[SELECTED_DISPOSITION_POSITION]
    sentinels = tuple(value for value in declared if value != selecting)
    if len(sentinels) < 2:
        _fail(
            "CERTIFICATE_REFUSED",
            "the certificate schema declares fewer than two sentinel dispositions",
            {"dispositions": list(declared)},
        )
    return selecting, sentinels[0], sentinels[1]


@lru_cache(maxsize=1)
def _states() -> dict[str, str]:
    """Every receipt-state token the reconciliation compares, read from O05.

    Holding these as literals would be the second copy EF4-I22 forbids, so the
    six states are read positionally from the vocabulary O05 owns.
    """
    vocabulary = receipt_state_vocabulary()
    # The dict keys are this module's private handles, deliberately *not* the
    # canonical state tokens themselves: a lowercase state token here would be a
    # duplicated wire literal (EF4-I22), so the tokens live only in the values,
    # read positionally from the vocabulary O05 owns.
    positions = {
        "state_unsearched": UNSEARCHED_STATE_POSITION,
        "state_searched_none": SEARCHED_NONE_STATE_POSITION,
        "state_searched_hits": SEARCHED_WITH_RESULTS_STATE_POSITION,
        "state_partial": RECEIPT_PARTIAL_POSITION,
        "state_blocked": RECEIPT_BLOCKED_POSITION,
        "state_failed": RECEIPT_FAILED_POSITION,
    }
    resolved: dict[str, str] = {}
    for name, position in positions.items():
        if position >= len(vocabulary):
            _fail(
                "CERTIFICATE_REFUSED",
                f"the receipt-state vocabulary declares no member at {position}",
                {"vocabulary": list(vocabulary)},
            )
        resolved[name] = vocabulary[position]
    return resolved


# -- search-completeness certificate reconciliation -----------------------


def _reconcile_lane(
    lane: str,
    receipt: Mapping[str, Any],
    *,
    selecting: str,
    disposition: str,
    searched_scope: list[str],
    unsearched_scope: list[str],
) -> dict[str, Any]:
    """Reconcile one canonical lane's receipt into a certificate reconciliation.

    The reconciled state is the receipt's own search state; the gate never
    relabels it.  A selected lane whose receipt is unsearched, or a sentinel lane
    whose receipt is not, is a conflict between what ran and what was chosen.
    """
    states = _states()
    receipt_state = str(receipt["search_state"])
    receipt_id = str(receipt["receipt_id"])
    selected = disposition == selecting
    if selected:
        if receipt_state == states["state_unsearched"]:
            _fail(
                "LANE_DISPOSITION_CONFLICT",
                f"lane {lane} was selected but its receipt is unsearched",
                {"lane": lane, "search_state": receipt_state},
            )
        return {
            "lane": lane,
            "selected": True,
            "plan_disposition": selecting,
            "receipt_ids": [receipt_id],
            "receipt_states": [receipt_state],
            "reconciled_state": receipt_state,
            "executed_scope_ids": list(searched_scope),
            "unsearched_scope_ids": list(unsearched_scope),
        }
    if receipt_state != states["state_unsearched"]:
        _fail(
            "LANE_DISPOSITION_CONFLICT",
            f"lane {lane} was not selected but its receipt is not unsearched",
            {"lane": lane, "search_state": receipt_state},
        )
    whole_scope = sorted(set(searched_scope) | set(unsearched_scope))
    if not whole_scope:
        _fail(
            "INPUT_INVALID",
            "an unselected lane needs at least one scope id to record as unsearched",
            {"lane": lane},
        )
    return {
        "lane": lane,
        "selected": False,
        "plan_disposition": disposition,
        "receipt_ids": [receipt_id],
        "receipt_states": [states["state_unsearched"]],
        "reconciled_state": states["state_unsearched"],
        "executed_scope_ids": [],
        "unsearched_scope_ids": whole_scope,
    }


def _completion_state(required_reconciled: Sequence[str]) -> str:
    """Derive the run completion from the required lanes' reconciled states."""
    states = _states()
    completion = completion_state_vocabulary()
    present = set(required_reconciled)
    if states["state_failed"] in present:
        return completion[COMPLETION_FAIL_POSITION]
    if states["state_blocked"] in present:
        return completion[COMPLETION_BLOCKED_POSITION]
    if states["state_partial"] in present or states["state_unsearched"] in present:
        return completion[COMPLETION_PARTIAL_POSITION]
    return completion[COMPLETION_PASS_POSITION]


def _claim_ceilings(*, passed: bool, external_covered: bool) -> tuple[str, str]:
    """Derive the absence and novelty ceilings from completion and coverage.

    Fail-closed: an incomplete run earns no claim, a complete run that leaves the
    outside unsearched earns only a conditional one, and only a complete run that
    conclusively reached the external-novelty lane with nothing left unsearched
    earns the corpus-novel ceiling.
    """
    absence = absence_ceiling_vocabulary()
    novelty = novelty_ceiling_vocabulary()
    if not passed:
        return absence[ABSENCE_NONE_POSITION], novelty[NOVELTY_NOT_ASSESSED_POSITION]
    if external_covered:
        return (
            absence[ABSENCE_EXTERNAL_CONDITIONAL_POSITION],
            novelty[NOVELTY_CORPUS_NOVEL_ONLY_POSITION],
        )
    return (
        absence[ABSENCE_CORPUS_CONDITIONAL_POSITION],
        novelty[NOVELTY_SEARCH_CONDITIONAL_POSITION],
    )


def build_search_completeness_certificate(
    *,
    plan: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    work_class: str,
    required_lanes: Sequence[str],
    subject_ref: str,
    generated_at: str,
) -> dict[str, Any]:
    """Reconcile O05 lane receipts into a canonical completeness certificate.

    Every canonical lane must carry exactly one receipt bound to ``plan``, each
    lane's reconciled state is the state its own receipt declares, and the
    completion state and both claim ceilings are derived from the reconciliation
    rather than supplied.  The work class fixes the lane rule: the exempt class
    requires no lanes and reconciles every lane as unsearched, and any graded
    class must include its canonical QueryPlan lane floor, each required lane
    having been selected and conclusively searched for the run to complete.
    """
    record = require_plan_identity(plan)
    order = canonical_lane_order()
    selecting, _first_sentinel, _second_sentinel = _disposition_tokens()
    dispositions = _require_mapping(
        record.get("lane_dispositions"), "plan.lane_dispositions"
    )

    classes = work_class_vocabulary()
    work = _require_text(work_class, "work_class")
    if work not in classes:
        _fail(
            "WORK_CLASS_UNDECLARED",
            "the certificate work class is outside the canonical vocabulary",
            {"declared": list(classes), "work_class": work},
        )
    exempt = classes[EXEMPT_WORK_CLASS_POSITION]

    searched_scope = sorted(
        {str(value) for value in record.get("searched_sources") or []}
    )
    unsearched_scope = sorted(
        {str(value) for value in record.get("unsearched_sources") or []}
    )

    rows = _require_sequence(receipts, "receipts")
    by_lane: dict[str, dict[str, Any]] = {}
    for position, candidate in enumerate(rows):
        receipt = _require_mapping(candidate, f"receipts[{position}]")
        try:
            validate_artifact(RECEIPT_SCHEMA, receipt)
        except ContractViolation as error:
            _fail(
                "RECEIPT_REFUSED",
                "a lane receipt does not satisfy its canonical schema",
                {"errors": list(error.errors), "position": position},
            )
        if str(receipt.get("plan_hash")) != str(record["plan_hash"]):
            _fail(
                "RECEIPT_NOT_FROM_PLAN",
                "a lane receipt binds a different retrieval plan",
                {"plan_id": str(record["plan_id"]), "position": position},
            )
        lane = str(receipt["lane"])
        if lane not in order:
            _fail(
                "LANE_UNDECLARED",
                f"{lane} is not a canonical retrieval lane",
                {"declared": list(order), "lane": lane},
            )
        if lane not in dispositions:
            _fail(
                "LANE_UNDECLARED",
                f"the plan declares no disposition for lane {lane}",
                {"lane": lane},
            )
        if lane in by_lane:
            _fail(
                "LANE_COVERAGE_INCOMPLETE",
                f"lane {lane} carries more than one receipt in this certificate",
                {"lane": lane},
            )
        by_lane[lane] = receipt
    missing = [lane for lane in order if lane not in by_lane]
    if missing:
        _fail(
            "LANE_COVERAGE_INCOMPLETE",
            "the receipt set does not account for every canonical lane",
            {"missing": missing},
        )

    reconciliations = [
        _reconcile_lane(
            lane,
            by_lane[lane],
            selecting=selecting,
            disposition=str(dispositions[lane]),
            searched_scope=searched_scope,
            unsearched_scope=unsearched_scope,
        )
        for lane in order
    ]
    reconciled_by_lane = {row["lane"]: row for row in reconciliations}

    declared_required = sorted(
        {
            _require_text(value, f"required_lanes[{position}]")
            for position, value in enumerate(
                _require_sequence(required_lanes, "required_lanes")
            )
        }
    )
    undeclared = sorted(set(declared_required) - set(order))
    if undeclared:
        _fail(
            "REQUIRED_LANE_UNDECLARED",
            "a required lane is outside the canonical retrieval vocabulary",
            {"declared": list(order), "undeclared": undeclared},
        )
    if work == exempt:
        if declared_required:
            _fail(
                "WORK_CLASS_LANE_RULE_VIOLATED",
                "the exempt work class requires no lanes but some were named",
                {"required_lanes": declared_required, "work_class": work},
            )
    else:
        if not declared_required:
            _fail(
                "WORK_CLASS_LANE_RULE_VIOLATED",
                "a graded work class must name at least one required lane",
                {"work_class": work},
            )
        required_floor = _work_class_lane_floor(work)
        missing_floor = [
            lane for lane in required_floor if lane not in declared_required
        ]
        if missing_floor:
            _fail(
                "WORK_CLASS_LANE_RULE_VIOLATED",
                "the required-lane set omits the work class's canonical lane floor",
                {
                    "missing": missing_floor,
                    "required_lanes": declared_required,
                    "work_class": work,
                },
            )
        not_selected = [
            lane
            for lane in declared_required
            if not reconciled_by_lane[lane]["selected"]
        ]
        if not_selected:
            _fail(
                "REQUIRED_LANE_NOT_SEARCHED",
                "a required lane was not selected and conclusively searched",
                {"lanes": not_selected},
            )

    ordered_required = [lane for lane in order if lane in set(declared_required)]
    completion = _completion_state(
        [reconciled_by_lane[lane]["reconciled_state"] for lane in ordered_required]
    )
    completion_vocabulary = completion_state_vocabulary()
    if work == exempt:
        completion = completion_vocabulary[COMPLETION_NOT_REQUIRED_POSITION]
    passed = completion == completion_vocabulary[COMPLETION_PASS_POSITION]

    states = _states()
    conclusive = {states["state_searched_none"], states["state_searched_hits"]}
    external_lane = order[EXTERNAL_LANE_POSITION]
    external_row = reconciled_by_lane[external_lane]
    external_covered = (
        bool(external_row["selected"])
        and external_row["reconciled_state"] in conclusive
        and not unsearched_scope
    )
    absence_ceiling, novelty_ceiling = _claim_ceilings(
        passed=passed, external_covered=external_covered
    )

    def _lanes_in(*state_names: str) -> list[str]:
        wanted = {states[name] for name in state_names}
        return [
            lane
            for lane in order
            if reconciled_by_lane[lane]["reconciled_state"] in wanted
        ]

    known_failures = sorted(
        f"lane {lane} reconciled to {reconciled_by_lane[lane]['reconciled_state']}"
        for lane in order
        if reconciled_by_lane[lane]["reconciled_state"]
        in {states["state_blocked"], states["state_failed"]}
    )

    certificate: dict[str, Any] = {
        "absence_claim_ceiling": absence_ceiling,
        "blocked_lanes": _lanes_in("state_blocked"),
        "completed_lanes": _lanes_in("state_searched_none", "state_searched_hits"),
        "completion_state": completion,
        "failed_lanes": _lanes_in("state_failed"),
        "generated_at": _require_text(generated_at, "generated_at"),
        "known_failures": known_failures,
        "lane_receipt_ids": [
            str(reconciled_by_lane[lane]["receipt_ids"][0]) for lane in order
        ],
        "lane_reconciliations": reconciliations,
        "novelty_claim_ceiling": novelty_ceiling,
        "partial_lanes": _lanes_in("state_partial"),
        "plan_hash": str(record["plan_hash"]),
        "query_plan_id": str(record["query_plan_id"]),
        "required_lanes": ordered_required,
        "run_id": str(record["run_id"]),
        "searched_scope": searched_scope,
        "subject_ref": _require_text(subject_ref, "subject_ref"),
        "unsearched_lanes": _lanes_in("state_unsearched"),
        "unsearched_scope": unsearched_scope,
        "work_class": work,
    }
    certificate["certificate_id"] = CERTIFICATE_ID_PREFIX + _digest_body(certificate)
    certificate["certificate_hash"] = hash_excluding(certificate, "certificate_hash")
    try:
        validate_artifact(CERTIFICATE_SCHEMA, certificate)
    except ContractViolation as error:
        _fail(
            "CERTIFICATE_REFUSED",
            "the reconciled certificate does not satisfy its canonical schema",
            {"errors": list(error.errors)},
        )
    return certificate


def require_certificate_identity(certificate: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a certificate's identifier and hash from its own content."""
    record = dict(_require_mapping(certificate, "certificate"))
    derived_id, derived_hash = derive_content_addressed_record_identity(
        record, CERTIFICATE_ID_PREFIX, "certificate_id", "certificate_hash"
    )
    if record.get("certificate_id") != derived_id or (
        record.get("certificate_hash") != derived_hash
    ):
        _fail(
            "CERTIFICATE_DRIFT",
            "the certificate does not re-derive its own identity",
            {
                "derived_certificate_hash": derived_hash,
                "derived_certificate_id": derived_id,
                "stated_certificate_id": record.get("certificate_id"),
            },
        )
    return record


def certificate_earns_novelty(certificate: Mapping[str, Any]) -> bool:
    """True when the certificate's completion earned a novelty ceiling.

    An incomplete run leaves the novelty ceiling at its lowest rung; a novelty
    claim standing on such a certificate is exactly the unearned claim this gate
    refuses.  The comparison reads the lowest rung from the schema rather than
    naming it.
    """
    ceiling = str(certificate.get("novelty_claim_ceiling"))
    lowest = novelty_ceiling_vocabulary()[NOVELTY_NOT_ASSESSED_POSITION]
    return ceiling != lowest


# -- the integration gate --------------------------------------------------


def _verify_admissibility_receipt(
    receipt: Mapping[str, Any], *, candidate_id: str
) -> dict[str, Any]:
    """Compose the sealed Q05 receipt: ADMIT, this candidate, and untampered.

    The gate never re-runs Q05 or reads a hidden score; it verifies the receipt
    Q05 already sealed.  A receipt that does not re-derive its own hash, is not an
    ADMIT, or is not from the Q05 gate cannot clear a candidate for forwarding.
    """
    record = _require_mapping(receipt, "admissibility_receipt")
    if str(record.get(Q05_GATE_FIELD)) != Q05_GATE_NAME:
        _fail(
            "ADMISSIBILITY_RECEIPT_REFUSED",
            "the admissibility receipt is not from the Q05 selective gate",
            {"gate": record.get(Q05_GATE_FIELD)},
        )
    stored_hash = record.get(Q05_RECEIPT_HASH_FIELD)
    recomputed = hash_excluding(dict(record), Q05_RECEIPT_HASH_FIELD)
    if not isinstance(stored_hash, str) or stored_hash != recomputed:
        _fail(
            "ADMISSIBILITY_RECEIPT_REFUSED",
            "the admissibility receipt does not re-derive its own hash",
            {"recorded": stored_hash, "recomputed": recomputed},
        )
    if str(record.get(Q05_CANDIDATE_FIELD)) != candidate_id:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the admissibility receipt describes a different candidate",
            {
                "expected": candidate_id,
                "found": record.get(Q05_CANDIDATE_FIELD),
            },
        )
    if str(record.get(Q05_DECISION_FIELD)) != ADMIT or (
        record.get(Q05_FORWARD_FIELD) is not True
    ):
        _fail(
            "ADMISSIBILITY_RECEIPT_REFUSED",
            "the admissibility receipt is not an ADMIT forwarding the candidate",
            {
                "decision": record.get(Q05_DECISION_FIELD),
                "forward": record.get(Q05_FORWARD_FIELD),
            },
        )
    return record


def _resolve_certificate(certificate: object) -> dict[str, Any]:
    """Validate the presented certificate and confirm it re-derives its identity."""
    if certificate is None:
        _fail(
            "CERTIFICATE_MISSING",
            "no search-completeness certificate was presented to ground the claim",
        )
    record = _require_mapping(certificate, "certificate")
    try:
        validate_artifact(CERTIFICATE_SCHEMA, record)
    except ContractViolation as error:
        _fail(
            "CERTIFICATE_REFUSED",
            "the presented certificate does not satisfy its canonical schema",
            {"errors": list(error.errors)},
        )
    return require_certificate_identity(record)


def _decide(
    *,
    certificate: Mapping[str, Any],
    assessment: Mapping[str, Any],
    required_source_ids: Sequence[str],
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the search-completeness / novelty / prior-art decision.

    A novelty claim standing on a certificate that earned no novelty ceiling is
    refused first: the search was incomplete and the novelty was never earned.
    Then any determination that left a required source unsearched is refused,
    because an absence was claimed the search never reached.  Only a claim that
    clears both, over a statistically-admissible candidate, is forwarded.
    """
    if novelty_supports_claim(assessment) and not certificate_earns_novelty(
        certificate
    ):
        return (
            REFUSE,
            "NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH",
            "a novelty claim rests on a certificate that earned no novelty ceiling",
            {
                "novelty_claim_ceiling": certificate.get("novelty_claim_ceiling"),
                "completion_state": certificate.get("completion_state"),
            },
        )
    searched = {str(value) for value in certificate.get("searched_scope") or []}
    required = [
        _require_text(value, f"required_source_ids[{position}]")
        for position, value in enumerate(
            _require_sequence(required_source_ids, "required_source_ids")
        )
    ]
    ignored = sorted(source for source in required if source not in searched)
    if ignored:
        return (
            REFUSE,
            "PRIOR_ART_IGNORED_REQUIRED_SOURCE",
            "a determination was forwarded while a required source stayed unsearched",
            {"ignored_sources": ignored, "searched_scope": sorted(searched)},
        )
    return (
        ADMIT,
        None,
        "the claim rests on a complete search and may be forwarded to review",
        {},
    )


def derive_search_integrity_admissibility(
    *,
    candidate_id: str,
    subject_ref: str,
    certificate: Mapping[str, Any] | None,
    novelty_assessment: Mapping[str, Any],
    admissibility_receipt: Mapping[str, Any],
    requesting_role: str,
    required_source_ids: Sequence[str] = (),
    created_at: str,
) -> dict[str, Any]:
    """Derive the admissibility decision and its immutable receipt.

    Input-integrity failures — a missing or drifted certificate, a claim that
    cites a different certificate or subject, an admissibility receipt that is
    not an untampered ADMIT for this candidate, or a candidate-generating role —
    refuse immediately, because there is no well-formed decision to record over
    evidence the gate cannot trust.  Once every input is validated and bound, the
    decision always produces a receipt, whether it admits or refuses, so every
    decision over well-formed inputs is auditable and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    candidate = _require_text(candidate_id, "candidate_id")
    subject = _require_text(subject_ref, "subject_ref")
    role = _require_text(requesting_role, "requesting_role")

    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive an admissibility decision",
            {"role": role},
        )

    record = _resolve_certificate(certificate)

    assessment = _require_mapping(novelty_assessment, "novelty_assessment")
    try:
        validate_artifact(NOVELTY_SCHEMA, assessment)
    except ContractViolation as error:
        _fail(
            "CLAIM_REFUSED",
            "the novelty assessment does not satisfy its canonical schema",
            {"errors": list(error.errors)},
        )
    recorded_hash = assessment.get("assessment_hash")
    recomputed_hash = hash_excluding(dict(assessment), "assessment_hash")
    if recorded_hash != recomputed_hash:
        _fail(
            "CLAIM_REFUSED",
            "the novelty assessment does not re-derive its own hash",
            {"recorded": recorded_hash, "recomputed": recomputed_hash},
        )
    if str(assessment.get("search_completeness_certificate_id")) != str(
        record["certificate_id"]
    ):
        _fail(
            "CLAIM_CERTIFICATE_MISMATCH",
            "the novelty assessment cites a different completeness certificate",
            {
                "assessment_certificate": assessment.get(
                    "search_completeness_certificate_id"
                ),
                "certificate_id": record["certificate_id"],
            },
        )
    if str(assessment.get("subject_ref")) != subject or (
        str(record.get("subject_ref")) != subject
    ):
        _fail(
            "SUBJECT_IDENTITY_MISMATCH",
            "the certificate and the assessment do not describe the one subject",
            {
                "assessment_subject": assessment.get("subject_ref"),
                "certificate_subject": record.get("subject_ref"),
                "subject_ref": subject,
            },
        )

    sealed = _verify_admissibility_receipt(
        admissibility_receipt, candidate_id=candidate
    )

    decision, finding_code, message, decision_context = _decide(
        certificate=record,
        assessment=assessment,
        required_source_ids=required_source_ids,
    )

    # The assessment's status field name is itself a canonical enum value in
    # another schema, so it is read from the assessment schema rather than named
    # here (EF4-I22); the value it points at is the assessment's own verdict.
    status_field, _status_ladder = scalar_enum_field(
        NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "admissible_for_promotion_review": decision == ADMIT,
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": candidate,
        "subject_ref": subject,
        "requesting_role": role,
        "certificate_id": str(record["certificate_id"]),
        "certificate_hash": str(record["certificate_hash"]),
        "completion_state": str(record["completion_state"]),
        "novelty_claim_ceiling": str(record["novelty_claim_ceiling"]),
        "absence_claim_ceiling": str(record["absence_claim_ceiling"]),
        status_field: str(assessment.get(status_field)),
        "novelty_assessment_id": str(assessment.get("assessment_id")),
        "novelty_claim_stated": bool(novelty_supports_claim(assessment)),
        "required_source_ids": sorted(
            {str(value) for value in required_source_ids or ()}
        ),
        "admissibility_receipt_hash": str(sealed[Q05_RECEIPT_HASH_FIELD]),
        "admissibility_gate": str(sealed[Q05_GATE_FIELD]),
    }
    receipt["gate_id"] = GATE_ID_PREFIX + _digest_body(
        {
            "candidate_id": candidate,
            "certificate_hash": receipt["certificate_hash"],
            "created_at": stamp,
            "decision": decision,
            "novelty_assessment_id": receipt["novelty_assessment_id"],
            "subject_ref": subject,
        }
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_search_integrity_admissibility(
    *,
    candidate_id: str,
    subject_ref: str,
    certificate: Mapping[str, Any] | None,
    novelty_assessment: Mapping[str, Any],
    admissibility_receipt: Mapping[str, Any],
    requesting_role: str,
    required_source_ids: Sequence[str] = (),
    created_at: str,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on admit, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the claim was stopped short of promotion review.
    """
    receipt = derive_search_integrity_admissibility(
        candidate_id=candidate_id,
        subject_ref=subject_ref,
        certificate=certificate,
        novelty_assessment=novelty_assessment,
        admissibility_receipt=admissibility_receipt,
        requesting_role=requesting_role,
        required_source_ids=required_source_ids,
        created_at=created_at,
    )
    if receipt["decision"] != ADMIT:
        raise SearchIntegrityRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a refusal.
__all__ = [
    "ABSENCE_CORPUS_CONDITIONAL_POSITION",
    "ABSENCE_EXTERNAL_CONDITIONAL_POSITION",
    "ABSENCE_NONE_POSITION",
    "ADMIT",
    "CERTIFICATE_ID_PREFIX",
    "COMPLETION_BLOCKED_POSITION",
    "COMPLETION_FAIL_POSITION",
    "COMPLETION_NOT_REQUIRED_POSITION",
    "COMPLETION_PARTIAL_POSITION",
    "COMPLETION_PASS_POSITION",
    "EXEMPT_WORK_CLASS_POSITION",
    "FINDING_CODES",
    "GATE_ID_PREFIX",
    "GATE_NAME",
    "NOVELTY_CORPUS_NOVEL_ONLY_POSITION",
    "NOVELTY_NOT_ASSESSED_POSITION",
    "NOVELTY_SEARCH_CONDITIONAL_POSITION",
    "RECEIPT_BLOCKED_POSITION",
    "RECEIPT_FAILED_POSITION",
    "RECEIPT_PARTIAL_POSITION",
    "REFUSE",
    "SchemaNotFound",
    "SearchIntegrityRefused",
    "absence_ceiling_vocabulary",
    "build_search_completeness_certificate",
    "certificate_earns_novelty",
    "completion_state_vocabulary",
    "derive_search_integrity_admissibility",
    "evaluate_search_integrity_admissibility",
    "novelty_ceiling_vocabulary",
    "require_certificate_identity",
    "work_class_vocabulary",
]
