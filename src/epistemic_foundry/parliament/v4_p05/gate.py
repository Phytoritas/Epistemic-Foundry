"""The evolution-promotion Parliament, Red Queen and minority-lineage gate.

A candidate reaches this gate because an adaptive evolutionary search selected it
and now asks to be forwarded to the promotion authority.  Promotion is never one
number.  The specification is explicit: a combined score may order a search but
cannot promote (EF4-I45), high promotion after adaptive search needs independent
replication or an explicit lower ceiling (EF4-I58), the strongest well-grounded
dissent and its unresolved test must be preserved (EF4-I49), and Red Queen
challenges must actually have been weighed (EF4-I52).  So this gate decides one
thing and refuses to decide more: is a sealed candidate's *promotion docket*
complete and clean enough to be **convened** before the promotion authority — a
multi-dimensional review, with its dissent preserved and its ceiling bounded — or
must it be **withheld**?  It never promotes anything.  Promotion authority lives
in :mod:`governance.promotion` and takes no score; this gate holds none of it,
and :func:`parliament_grants_promotion` says so in one place a caller can find.

It is an *integration* gate: it composes the already-sealed surfaces that each
own one concern and restates none of their vocabularies (EF4-I22).

* **The Parliament verdict is deliberation, not authority.**  The adjudication is
  validated against its canonical schema and re-derives its own hash, its
  ``deterministic_gate_override_attempted`` flag is honoured as a withholding
  condition, and ``evidence_parliament.recommendation_is_binding`` is consulted
  and required to stay ``False`` — a Parliament that had acquired promotion
  authority is refused before anything else.

* **Dissent is preserved, never dropped.**  Every minority report the adjudication
  references must be supplied, valid, and re-derive its hash; a referenced
  dissent that is absent is a dropped minority report and withholds the docket.
  Preserved dissent and its unresolved test are carried into the receipt whether
  the docket is convened or withheld, so the record can never quietly lose it.

* **Red Queen evidence must be weighed.**  The adversarial match results are read
  through ``red_queen_lab`` — the surface that already refuses to count a crashed
  or unresolved adversary as a win.  A candidate with no challenge run against it,
  a replicated refutation, or an unresolved match owed a rerun is withheld, and
  the adversarial evidence *lanes* that ``retrieval.v4_o05`` declares must all
  have been searched.

* **Statistical clearance stays a vector, not a score.**  The candidate must
  arrive with the Q05 selective-admissibility receipt that already refused a
  scalar fitness and a score that claims promotion authority; this gate requires
  that receipt to re-derive its hash and to read ``ADMIT``.  A docket missing the
  statistical dimension entirely is refused as a partial, single-source promotion.

* **Replication bounds the ceiling.**  The highest level the available
  replication evidence supports is read from ``validation_bay.replication`` and
  the convened ceiling is capped at it; a replication result that blocks
  promotion withholds the docket outright.

Every decision, convene or withhold, resolves to one immutable receipt that is a
pure function of its inputs: there is no clock and no random draw, the caller
supplies ``created_at``, and the gate id and receipt hash re-derive byte for byte
from the receipt's own published fields.  No input is ever mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    validate_artifact,
)
from ...domain.hashing import canonical_json, hash_excluding, sha256_hex
from ...domain.vocabularies import PROMOTION_LADDER, promotion_rank
from ...evaluation.v4_q05 import ADMIT as STATISTICAL_ADMIT
from ...evidence_parliament.adjudication import recommendation_is_binding
from ...governance.promotion import CANONICAL_GATE_IDS
from ...red_queen_lab.challenges import (
    partition_adverse_outcomes,
    survived_challenges,
    unresolved_matches,
)
from ...retrieval.v4_o05 import adversarial_lanes, lane_vocabulary
from ...validation_bay.replication import promotion_ceiling_after_search
from ...verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "REQUESTED_LEVEL_INVALID": (
        "the requested promotion level is not a rung of the canonical ladder, so "
        "there is no ceiling to bound the convened docket against"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the lineage, adjudication, statistical clearance or a replication result "
        "does not describe the one candidate this docket is convened about"
    ),
    "LINEAGE_CONTRACT_VIOLATED": (
        "the candidate's lineage does not satisfy the canonical lineage schema, so "
        "the minority-lineage the Parliament reviews cannot be trusted or replayed"
    ),
    "ADJUDICATION_CONTRACT_VIOLATED": (
        "the Parliament adjudication does not satisfy its canonical schema or does "
        "not re-derive its own hash, so the deliberation it records was altered"
    ),
    "PARLIAMENT_RECOMMENDATION_NOT_AUTHORITY": (
        "the Parliament recommendation reported itself as binding promotion "
        "authority, which a deliberative verdict may never hold"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the convening decision, and a role "
        "that proposes candidates may never acquire promotion authority over them"
    ),
    "MINORITY_REPORT_CONTRACT_VIOLATED": (
        "a supplied minority report does not satisfy its canonical schema or does "
        "not re-derive its hash, so the dissent it records cannot be preserved"
    ),
    "STATISTICAL_CLEARANCE_CONTRACT_VIOLATED": (
        "the selective-admissibility receipt does not re-derive its own hash, so "
        "the statistical accounting the docket rests on has been altered"
    ),
    "REPLICATION_RESULT_CONTRACT_VIOLATED": (
        "a replication result does not satisfy its canonical schema, or the schema "
        "declares no promotion-effect vocabulary to read the blocking effect from"
    ),
    "PROMOTION_DIMENSION_MISSING": (
        "the statistical-clearance dimension is absent from the docket, so "
        "convening on the remaining evidence would be a partial, single-source "
        "promotion of exactly the kind a multi-dimensional review forbids"
    ),
    "STATISTICAL_CLEARANCE_ABSENT": (
        "the selective-admissibility receipt did not admit the candidate, so the "
        "winner's-curse and leakage accounting has not cleared it for review"
    ),
    "PARLIAMENT_GATE_OVERRIDE": (
        "the adjudication recorded an attempt to advance past a failed "
        "deterministic gate, and a deliberative verdict cannot override a hard gate"
    ),
    "MINORITY_DISSENT_DROPPED": (
        "a minority report the adjudication references was not supplied, so the "
        "docket would convene with dissent that has been dropped rather than "
        "preserved"
    ),
    "RED_QUEEN_EVIDENCE_ABSENT": (
        "no Red Queen challenge was run against the candidate, so its robustness "
        "would be credited on an adversarial test that never happened"
    ),
    "RED_QUEEN_REFUTED": (
        "a Red Queen challenge refuted the candidate, so the adversarial evidence "
        "defeats rather than clears it for promotion review"
    ),
    "RED_QUEEN_UNRESOLVED": (
        "a Red Queen match against the candidate resolved nothing and still owes a "
        "rerun, and an unresolved adversary must never read as a passed test"
    ),
    "ADVERSARIAL_COVERAGE_INCOMPLETE": (
        "an adversarial evidence lane the retrieval surface declares was not "
        "searched, so the challenge evidence the Parliament weighs is incomplete"
    ),
    "REPLICATION_BLOCKED": (
        "a replication result blocks promotion, so the independent replication the "
        "ceiling depends on found against the candidate"
    ),
}

#: Canonical schemas this gate validates against, named rather than restated.
LINEAGE_KIND = "candidate-lineage"
ADJUDICATION_KIND = "adjudication"
MINORITY_REPORT_KIND = "minority-report"
REPLICATION_RESULT_KIND = "replication-result"

#: Property names the gate reads back.  These are field names, not wire values,
#: so they are named here and read against the schema at use.
CANDIDATE_FIELD = "candidate_id"
HYPOTHESIS_FIELD = "hypothesis_id"
OVERRIDE_FIELD = "deterministic_gate_override_attempted"
MINORITY_REPORT_IDS_FIELD = "minority_report_ids"
MINORITY_REPORT_ID_FIELD = "minority_report_id"
PRESERVATION_FIELD = "preservation_status"
UNRESOLVED_TEST_FIELD = "unresolved_test"
ADJUDICATION_HASH_FIELD = "adjudication_hash"
REPORT_HASH_FIELD = "report_hash"
RECEIPT_HASH_FIELD = "receipt_hash"
DECISION_FIELD = "decision"
TARGET_CANDIDATE_FIELD = "target_candidate_id"
PROMOTION_EFFECT_FIELD = "promotion_effect"
GATE_DECISION_IDS_FIELD = "gate_decision_ids"
ADJUDICATION_ID_FIELD = "adjudication_id"
LINEAGE_ID_FIELD = "lineage_id"

#: The gate's own decision vocabulary.  Neither token is a canonical schema enum
#: value (verified by the wire-literal discipline suite), so they are the gate's
#: to name: a complete docket may be *convened* before the promotion authority,
#: nothing more.
CONVENE = "CONVENE"
WITHHOLD = "WITHHOLD"

#: The receipt's stable name and id prefix.
GATE_NAME = "evolution-promotion-parliament"
GATE_ID_PREFIX = "EPP-"

#: The deterministic promotion gates this Parliament informs, referenced from the
#: authority that owns them rather than restated.  Indexing keeps the gate ids in
#: one place: a reorder in ``governance.promotion`` moves these with it.
STATISTICS_GATE = CANONICAL_GATE_IDS[8]
RED_QUEEN_GATE = CANONICAL_GATE_IDS[9]
REPLICATION_GATE = CANONICAL_GATE_IDS[10]
PARLIAMENT_GATE = CANONICAL_GATE_IDS[11]


class PromotionParliamentWithheld(ValueError):
    """The gate withholds the docket, or refuses its evidence, with a code."""

    def __init__(
        self,
        code: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise PromotionParliamentWithheld(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise PromotionParliamentWithheld(code, message, context)


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


def _require_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be an integer", {"label": label})
    return int(value)


def parliament_grants_promotion() -> bool:
    """Always False: convening a docket is never itself promotion authority.

    Kept as an explicit predicate rather than an omission so a caller reaching for
    "did the Parliament promote this?" finds a documented no instead of inventing
    a truthy check on the convened decision.  Promotion authority lives in
    :mod:`governance.promotion`, which takes no score from this gate.
    """
    return False


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """Canonical enum tokens the gate reasons about, read from the schema.

    Only one is needed as a value: the replication promotion-effect that blocks
    promotion.  The replication surface exposes ceilings and qualification as
    functions but does not export the effect vocabulary as importable constants,
    so the blocking effect is read out of the canonical replication-result schema
    that declares it.  It is the ladder's terminal, most-restrictive effect; a
    reshape that empties the ladder fails closed here rather than silently
    selecting the wrong token.
    """
    document = default_registry().document(REPLICATION_RESULT_KIND)
    effects = document.get("properties", {}).get(PROMOTION_EFFECT_FIELD, {}).get("enum")
    if not isinstance(effects, list) or not effects:
        _fail(
            "REPLICATION_RESULT_CONTRACT_VIOLATED",
            "the replication-result schema declares no promotion-effect vocabulary",
            {"schema": REPLICATION_RESULT_KIND},
        )
    return {"blocking_effect": str(effects[-1])}


def replication_blocking_effect() -> str:
    """The replication promotion-effect that blocks promotion, read from schema."""
    return _vocab()["blocking_effect"]


@dataclass(frozen=True)
class _Docket:
    """One validated, candidate-bound promotion docket."""

    candidate_id: str
    candidate_revision: int
    requested_level: str
    lineage_id: str
    adjudication_id: str
    adjudication_hash: str
    minority_report_ids: tuple[str, ...]
    preserved_dissent: tuple[dict[str, Any], ...]
    dropped_dissent: tuple[str, ...]
    statistical_present: bool
    statistical_admitted: bool
    statistical_receipt_hash: str
    override_attempted: bool
    red_queen_survived: bool
    red_queen_refuted: tuple[str, ...]
    red_queen_scope_restricted: tuple[str, ...]
    red_queen_unresolved: tuple[str, ...]
    red_queen_present: bool
    adversarial_lanes_missing: tuple[str, ...]
    adversarial_lanes_covered: tuple[str, ...]
    replication_result_hashes: tuple[str, ...]
    replication_blocked: bool
    promotion_ceiling: str
    ceiling_lowered: bool


def _resolve_lineage(lineage: object, *, expected: str) -> str:
    document = _require_mapping(lineage, "lineage")
    try:
        validate_artifact(LINEAGE_KIND, document)
    except ContractViolation as error:
        _fail(
            "LINEAGE_CONTRACT_VIOLATED",
            "the candidate lineage does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if str(document.get(CANDIDATE_FIELD)) != expected:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the lineage describes a different candidate",
            {"expected": expected, "found": document.get(CANDIDATE_FIELD)},
        )
    return _require_text(document.get(LINEAGE_ID_FIELD), LINEAGE_ID_FIELD)


def _resolve_adjudication(
    adjudication: object, *, expected: str
) -> tuple[str, str, bool]:
    document = _require_mapping(adjudication, "adjudication")
    try:
        validate_artifact(ADJUDICATION_KIND, document)
    except ContractViolation as error:
        _fail(
            "ADJUDICATION_CONTRACT_VIOLATED",
            "the adjudication does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    recomputed = hash_excluding(document, ADJUDICATION_HASH_FIELD)
    if recomputed != document.get(ADJUDICATION_HASH_FIELD):
        _fail(
            "ADJUDICATION_CONTRACT_VIOLATED",
            "the adjudication does not re-derive its own hash",
            {
                "recorded": document.get(ADJUDICATION_HASH_FIELD),
                "recomputed": recomputed,
            },
        )
    # A Parliament recommendation is deliberation, never authority.  The owning
    # surface documents this as an always-``False`` predicate; the gate composes
    # it and refuses outright if that guarantee were ever weakened.
    if recommendation_is_binding(document) is not False:
        _fail(
            "PARLIAMENT_RECOMMENDATION_NOT_AUTHORITY",
            "the adjudication reported its recommendation as binding authority",
            {ADJUDICATION_ID_FIELD: document.get(ADJUDICATION_ID_FIELD)},
        )
    if str(document.get(HYPOTHESIS_FIELD)) != expected:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the adjudication describes a different subject than the candidate",
            {"expected": expected, "found": document.get(HYPOTHESIS_FIELD)},
        )
    return (
        _require_text(document.get(ADJUDICATION_ID_FIELD), ADJUDICATION_ID_FIELD),
        str(document.get(ADJUDICATION_HASH_FIELD)),
        bool(document.get(OVERRIDE_FIELD)),
    )


def _resolve_minority(
    minority_reports: Sequence[Any],
) -> dict[str, dict[str, Any]]:
    """Validate every supplied minority report and index it by id."""
    resolved: dict[str, dict[str, Any]] = {}
    for position, report in enumerate(minority_reports):
        document = _require_mapping(report, f"minority_reports[{position}]")
        try:
            validate_artifact(MINORITY_REPORT_KIND, document)
        except ContractViolation as error:
            _fail(
                "MINORITY_REPORT_CONTRACT_VIOLATED",
                "a minority report does not satisfy its canonical schema",
                {"position": position, "schema_errors": list(error.errors)},
            )
        recomputed = hash_excluding(document, REPORT_HASH_FIELD)
        if recomputed != document.get(REPORT_HASH_FIELD):
            _fail(
                "MINORITY_REPORT_CONTRACT_VIOLATED",
                "a minority report does not re-derive its own hash",
                {"position": position, "recorded": document.get(REPORT_HASH_FIELD)},
            )
        resolved[str(document.get(MINORITY_REPORT_ID_FIELD))] = document
    return resolved


def _resolve_statistical_clearance(
    clearance: object, *, expected: str
) -> tuple[bool, bool, str]:
    """Return (dimension_present, admitted, receipt_hash) for the Q05 receipt.

    The receipt is the sealed Q05 surface's own output, not a registry artifact,
    so its integrity is checked by re-deriving its published hash rather than by a
    schema.  A receipt that carries a decision must carry the candidate it decided
    about and a hash that re-derives; a docket with no decision at all is the
    absent statistical dimension the decision phase refuses as single-source.
    """
    document = _require_mapping(clearance, "selective_admissibility")
    if DECISION_FIELD not in document:
        return (False, False, "")
    if RECEIPT_HASH_FIELD not in document:
        _fail(
            "STATISTICAL_CLEARANCE_CONTRACT_VIOLATED",
            "the selective-admissibility receipt carries a decision but no hash",
            {DECISION_FIELD: document.get(DECISION_FIELD)},
        )
    recomputed = hash_excluding(document, RECEIPT_HASH_FIELD)
    if recomputed != document.get(RECEIPT_HASH_FIELD):
        _fail(
            "STATISTICAL_CLEARANCE_CONTRACT_VIOLATED",
            "the selective-admissibility receipt does not re-derive its own hash",
            {"recorded": document.get(RECEIPT_HASH_FIELD), "recomputed": recomputed},
        )
    if str(document.get(CANDIDATE_FIELD)) != expected:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the statistical clearance describes a different candidate",
            {"expected": expected, "found": document.get(CANDIDATE_FIELD)},
        )
    admitted = str(document.get(DECISION_FIELD)) == STATISTICAL_ADMIT
    return (True, admitted, str(document.get(RECEIPT_HASH_FIELD)))


def _resolve_replication(
    replication_results: Sequence[Any], *, expected: str
) -> tuple[tuple[str, ...], bool]:
    """Validate replication results and report whether any blocks promotion."""
    hashes: list[str] = []
    blocked = False
    blocking = replication_blocking_effect()
    for position, result in enumerate(replication_results):
        document = _require_mapping(result, f"replication_results[{position}]")
        try:
            validate_artifact(REPLICATION_RESULT_KIND, document)
        except ContractViolation as error:
            _fail(
                "REPLICATION_RESULT_CONTRACT_VIOLATED",
                "a replication result does not satisfy its canonical schema",
                {"position": position, "schema_errors": list(error.errors)},
            )
        if str(document.get(CANDIDATE_FIELD)) != expected:
            _fail(
                "CANDIDATE_IDENTITY_MISMATCH",
                "a replication result describes a different candidate",
                {"expected": expected, "found": document.get(CANDIDATE_FIELD)},
            )
        hashes.append(str(document.get("result_hash")))
        if str(document.get(PROMOTION_EFFECT_FIELD)) == blocking:
            blocked = True
    return (tuple(hashes), blocked)


def _resolve_red_queen(
    red_queen_results: Sequence[Any], *, expected: str
) -> tuple[bool, bool, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Read the adversarial evidence through the surface that owns it.

    Survival, refutation, boundary restriction and unresolved matches all come
    from ``red_queen_lab``, which already refuses to count a crashed or
    unresolved adversary as a win; the gate composes those verdicts rather than
    re-deriving the outcome vocabulary here.
    """
    results = [
        _require_mapping(item, "red_queen_results[]") for item in red_queen_results
    ]
    matches = [
        item for item in results if str(item.get(TARGET_CANDIDATE_FIELD)) == expected
    ]
    present = bool(matches)
    adverse = partition_adverse_outcomes(results)
    refuted = tuple(item for item in adverse["refuted"] if item == expected)
    scope_restricted = tuple(
        item for item in adverse["scope_restricted"] if item == expected
    )
    unresolved = tuple(
        str(item.get(TARGET_CANDIDATE_FIELD))
        for item in unresolved_matches(results)
        if str(item.get(TARGET_CANDIDATE_FIELD)) == expected
    )
    survived = survived_challenges(expected, results)
    return (present, survived, refuted, scope_restricted, unresolved)


def _resolve_adversarial_coverage(
    searched_adversarial_lanes: Sequence[Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (covered, missing) adversarial lanes against the O05 vocabulary."""
    declared = set(lane_vocabulary())
    covered: list[str] = []
    for position, lane in enumerate(searched_adversarial_lanes):
        name = _require_text(lane, f"searched_adversarial_lanes[{position}]")
        if name not in declared:
            _fail(
                "INPUT_INVALID",
                "a searched lane is not a declared retrieval lane",
                {"lane": name, "declared": sorted(declared)},
            )
        covered.append(name)
    required = adversarial_lanes()
    missing = tuple(lane for lane in required if lane not in set(covered))
    return (tuple(covered), missing)


def _effective_ceiling(
    requested_level: str,
    *,
    adaptive_search_used: bool,
    replication_plan: Mapping[str, Any] | None,
) -> tuple[str, bool]:
    """Cap the requested level at what replication evidence supports."""
    replication_ceiling = promotion_ceiling_after_search(
        adaptive_search_used=adaptive_search_used,
        replication_plan=replication_plan,
    )
    if promotion_rank(replication_ceiling) < promotion_rank(requested_level):
        return (replication_ceiling, True)
    return (requested_level, False)


def _decide(docket: _Docket) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message and its context.

    The order is deliberate.  A docket missing the statistical dimension is
    refused first as a single-source promotion, because nothing downstream is a
    complete review without it.  A failed statistical clearance is next.  Then the
    Parliament's own integrity — an override attempt and dropped dissent — before
    the adversarial evidence is weighed, and finally the replication block.
    """
    if not docket.statistical_present:
        return (
            WITHHOLD,
            "PROMOTION_DIMENSION_MISSING",
            "the docket carries no statistical-clearance dimension",
            {},
        )
    if not docket.statistical_admitted:
        return (
            WITHHOLD,
            "STATISTICAL_CLEARANCE_ABSENT",
            "the selective-admissibility receipt did not admit the candidate",
            {},
        )
    if docket.override_attempted:
        return (
            WITHHOLD,
            "PARLIAMENT_GATE_OVERRIDE",
            "the adjudication attempted to advance past a failed deterministic gate",
            {},
        )
    if docket.dropped_dissent:
        return (
            WITHHOLD,
            "MINORITY_DISSENT_DROPPED",
            "a minority report the adjudication references was not supplied",
            {MINORITY_REPORT_IDS_FIELD: list(docket.dropped_dissent)},
        )
    if not docket.red_queen_present:
        return (
            WITHHOLD,
            "RED_QUEEN_EVIDENCE_ABSENT",
            "no Red Queen challenge was run against the candidate",
            {},
        )
    if docket.red_queen_refuted:
        return (
            WITHHOLD,
            "RED_QUEEN_REFUTED",
            "a Red Queen challenge refuted the candidate",
            {"refuted": list(docket.red_queen_refuted)},
        )
    if docket.red_queen_unresolved:
        return (
            WITHHOLD,
            "RED_QUEEN_UNRESOLVED",
            "a Red Queen match against the candidate resolved nothing",
            {"unresolved_targets": list(docket.red_queen_unresolved)},
        )
    if docket.adversarial_lanes_missing:
        return (
            WITHHOLD,
            "ADVERSARIAL_COVERAGE_INCOMPLETE",
            "an adversarial evidence lane was not searched",
            {"missing_lanes": list(docket.adversarial_lanes_missing)},
        )
    if docket.replication_blocked:
        return (
            WITHHOLD,
            "REPLICATION_BLOCKED",
            "a replication result blocks promotion",
            {},
        )
    return (
        CONVENE,
        None,
        "the promotion docket is complete and convened before the promotion authority",
        {},
    )


def derive_promotion_parliament(
    *,
    candidate_id: str,
    candidate_revision: int,
    requested_level: str,
    lineage: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    selective_admissibility: Mapping[str, Any],
    red_queen_results: Sequence[Mapping[str, Any]],
    searched_adversarial_lanes: Sequence[str],
    requesting_principal_id: str,
    requesting_role: str,
    adaptive_search_used: bool = True,
    minority_reports: Sequence[Mapping[str, Any]] = (),
    replication_plan: Mapping[str, Any] | None = None,
    replication_results: Sequence[Mapping[str, Any]] = (),
    created_at: str,
) -> dict[str, Any]:
    """Derive the convening decision and its immutable receipt.

    Input-integrity failures — a malformed lineage, adjudication, minority report,
    statistical receipt or replication result, a candidate mismatch, a Parliament
    that claimed authority, or a candidate-generating role driving the decision —
    refuse immediately, because there is no well-formed docket to convene over
    evidence the gate cannot trust.  Once every input is validated and bound, the
    convening decision always produces a receipt, whether it convenes or withholds,
    so every decision over well-formed inputs is auditable and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    expected = _require_text(candidate_id, CANDIDATE_FIELD)
    revision = _require_int(candidate_revision, "candidate_revision")
    principal = _require_text(requesting_principal_id, "requesting_principal_id")
    role = _require_text(requesting_role, "requesting_role")

    if requested_level not in PROMOTION_LADDER:
        _fail(
            "REQUESTED_LEVEL_INVALID",
            "the requested promotion level is not a rung of the canonical ladder",
            {"requested_level": requested_level, "ladder": list(PROMOTION_LADDER)},
        )

    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive a convening decision",
            {"role": role},
        )

    lineage_id = _resolve_lineage(lineage, expected=expected)
    adjudication_id, adjudication_hash, override_attempted = _resolve_adjudication(
        adjudication, expected=expected
    )
    adjudication_document = _require_mapping(adjudication, "adjudication")
    referenced_dissent = [
        str(identifier)
        for identifier in adjudication_document.get(MINORITY_REPORT_IDS_FIELD, [])
    ]

    minority = _resolve_minority(
        _require_sequence(minority_reports, "minority_reports")
    )
    dropped_dissent = tuple(
        identifier for identifier in referenced_dissent if identifier not in minority
    )
    preserved_dissent = tuple(
        {
            MINORITY_REPORT_ID_FIELD: report.get(MINORITY_REPORT_ID_FIELD),
            PRESERVATION_FIELD: report.get(PRESERVATION_FIELD),
            UNRESOLVED_TEST_FIELD: report.get(UNRESOLVED_TEST_FIELD),
        }
        for report in minority.values()
    )

    statistical_present, statistical_admitted, statistical_hash = (
        _resolve_statistical_clearance(selective_admissibility, expected=expected)
    )

    (
        red_queen_present,
        red_queen_survived,
        red_queen_refuted,
        red_queen_scope_restricted,
        red_queen_unresolved,
    ) = _resolve_red_queen(
        _require_sequence(red_queen_results, "red_queen_results"), expected=expected
    )

    covered, missing = _resolve_adversarial_coverage(
        _require_sequence(searched_adversarial_lanes, "searched_adversarial_lanes")
    )

    plan = (
        _require_mapping(replication_plan, "replication_plan")
        if replication_plan
        else None
    )
    replication_hashes, replication_blocked = _resolve_replication(
        _require_sequence(replication_results, "replication_results"), expected=expected
    )
    ceiling, ceiling_lowered = _effective_ceiling(
        requested_level,
        adaptive_search_used=bool(adaptive_search_used),
        replication_plan=plan,
    )

    docket = _Docket(
        candidate_id=expected,
        candidate_revision=revision,
        requested_level=requested_level,
        lineage_id=lineage_id,
        adjudication_id=adjudication_id,
        adjudication_hash=adjudication_hash,
        minority_report_ids=tuple(sorted(minority)),
        preserved_dissent=preserved_dissent,
        dropped_dissent=dropped_dissent,
        statistical_present=statistical_present,
        statistical_admitted=statistical_admitted,
        statistical_receipt_hash=statistical_hash,
        override_attempted=override_attempted,
        red_queen_survived=red_queen_survived,
        red_queen_refuted=red_queen_refuted,
        red_queen_scope_restricted=red_queen_scope_restricted,
        red_queen_unresolved=red_queen_unresolved,
        red_queen_present=red_queen_present,
        adversarial_lanes_missing=missing,
        adversarial_lanes_covered=covered,
        replication_result_hashes=replication_hashes,
        replication_blocked=replication_blocked,
        promotion_ceiling=ceiling,
        ceiling_lowered=ceiling_lowered,
    )

    decision, finding_code, message, decision_context = _decide(docket)

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "convened_for_promotion_authority": decision == CONVENE,
        "grants_promotion": parliament_grants_promotion(),
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": expected,
        "candidate_revision": revision,
        "requested_level": requested_level,
        "promotion_ceiling": ceiling,
        "ceiling_lowered_by_replication": ceiling_lowered,
        "requesting_principal_id": principal,
        "requesting_role": role,
        "lineage_id": lineage_id,
        "adjudication_id": adjudication_id,
        "adjudication_hash": adjudication_hash,
        "informs_gate_decisions": [
            STATISTICS_GATE,
            RED_QUEEN_GATE,
            REPLICATION_GATE,
            PARLIAMENT_GATE,
        ],
        "preserved_minority_report_ids": list(docket.minority_report_ids),
        "preserved_dissent": [dict(entry) for entry in preserved_dissent],
        "dropped_minority_report_ids": list(dropped_dissent),
        "statistical_clearance_present": statistical_present,
        "statistical_clearance_admitted": statistical_admitted,
        "statistical_receipt_hash": statistical_hash,
        "red_queen_challenged": red_queen_present,
        "red_queen_survived": red_queen_survived,
        "red_queen_refuted": list(red_queen_refuted),
        "red_queen_scope_restricted": list(red_queen_scope_restricted),
        "red_queen_unresolved": list(red_queen_unresolved),
        "adversarial_lanes_covered": list(covered),
        "adversarial_lanes_missing": list(missing),
        "replication_result_hashes": list(replication_hashes),
        "replication_blocked": replication_blocked,
    }
    receipt["gate_id"] = (
        GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": expected,
                    "candidate_revision": revision,
                    "created_at": stamp,
                    "decision": decision,
                    "adjudication_hash": adjudication_hash,
                    "statistical_receipt_hash": statistical_hash,
                    "requested_level": requested_level,
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_promotion_parliament(**kwargs: Any) -> dict[str, Any]:
    """Enforce the gate: return the receipt on convene, raise on any withholding.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the docket was withheld from promotion review.
    """
    receipt = derive_promotion_parliament(**kwargs)
    if receipt["decision"] != CONVENE:
        raise PromotionParliamentWithheld(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a withholding.
__all__ = [
    "CONVENE",
    "FINDING_CODES",
    "GATE_NAME",
    "PromotionParliamentWithheld",
    "SchemaNotFound",
    "WITHHOLD",
    "derive_promotion_parliament",
    "evaluate_promotion_parliament",
    "parliament_grants_promotion",
    "replication_blocking_effect",
]
