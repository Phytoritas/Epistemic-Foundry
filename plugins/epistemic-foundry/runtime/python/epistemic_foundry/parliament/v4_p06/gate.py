"""No-majority promotion and sealed-candidate attestation referral gate (P06).

A sealed candidate reaches this gate asking to be *forwarded* to the promotion
authority.  The one thing this gate exists to protect is the invariant that a
promotion decision may never be reducible to a single number or a bare majority:
it must rest on independent, multi-dimensional clearance, must preserve the
dissent the deliberation produced, and must carry the sealed-candidate
attestation chain (EF4-I45, EF4-I49, EF4-I58, the constitutional G12 independent
attestation).  So the gate decides one thing and refuses to decide more: is a
sealed candidate's clearance broad, dissent-preserving and independently attested
enough to be **referred** before the promotion authority — or must it be
**withheld**?  It never promotes anything.  Promotion authority lives in
:mod:`epistemic_foundry.governance.promotion` and takes no score; this gate holds
none of it, and :func:`gate_grants_promotion` says so in one place a caller can
find.

It is an *integration* gate: it composes two already-sealed decision organs and
one sealed attestation surface, and restates none of their vocabularies
(EF4-I22).  Every canonical token it reasons about — the attestation's passing
status — is read positionally out of the schema that declares it.  The Parliament
``CONVENE`` token is imported from the P05 gate that owns it; the V05 gate,
however, cannot be imported here without closing a forbidden
``parliament``↔``validation`` component cycle (ADR-034), so the validation organ
is verified as opaque data — its self-declared ``advanced`` flag and its ``gate``
name matched against a pinned boundary constant that a test holds equal to V05's
real gate name.

* **Not a single score.**  Two *independent* organs must both clear the
  candidate: the P05 evolution-promotion Parliament must have **convened** the
  multi-dimensional docket, and the V05 validation cascade must have **advanced**
  the claim.  Each receipt is trusted only once it proves it is the receipt it
  claims to be — produced by the owning gate, re-deriving its own hash — so a
  single organ cannot masquerade as two dimensions, and neither organ alone can
  carry a referral.  The parliament receipt is additionally refused if it ever
  reports that it holds promotion authority, because a deliberative organ may not.

* **Not a bare majority.**  The convened docket must have *preserved dissent*: at
  least one minority report the Parliament carried forward.  A docket that
  preserved no dissent is a bare-majority promotion and is withheld, and the
  preserved dissent is carried into the referral receipt so the record can never
  quietly lose it.

* **The sealed-candidate attestation chain.**  An independent attestation must
  clear the candidate: valid against its canonical schema and re-deriving its own
  hash, naming this candidate as its subject, **passing**, produced by an attestor
  proven independent of the makers (charter section 6, composed through the
  evolution-authority surface that owns that rule), and attesting over *both*
  sealed organ receipts so the chain actually covers the evidence it forwards.

* **The ceiling stays bounded.**  The referral level is capped at the lower of the
  two ceilings the organs already bounded — the Parliament's replication-bounded
  ceiling and the validation cascade's replication ceiling — so a referral can
  never claim a level the independent replication evidence does not support.

Every decision, refer or withhold, resolves to one immutable receipt that is a
pure function of its inputs: there is no clock and no random draw, the caller
supplies ``created_at``, and the gate id and receipt hash re-derive byte for byte
from the receipt's own published fields.  No input is ever mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    validate_artifact,
)
from ...domain.hashing import canonical_json, hash_excluding, sha256_hex
from ...domain.vocabularies import PROMOTION_LADDER, promotion_rank
from ...governance.evolution_authority import (
    EvolutionAuthorityError,
    verify_attestor_independence,
)
from ...governance.promotion import CANONICAL_GATE_IDS
from ...parliament.v4_p05 import (
    CONVENE,
    parliament_grants_promotion,
)
from ...parliament.v4_p05 import GATE_NAME as PARLIAMENT_GATE_NAME
from ...verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES

#: The sealed V05 validation-cascade advancement gate this referral composes as
#: its second independent organ, pinned here at the component boundary.  The V05
#: surface is *not* imported: ``validation`` already imports ``parliament`` (the
#: V06 end-to-end gate composes P05), so importing ``validation`` inward from here
#: would close a forbidden top-level ``parliament``↔``validation`` cycle that
#: the ADR-034 allowlist does not admit.  The gate therefore treats the V05
#: receipt as opaque, integrity-checked data — re-deriving its published hash and
#: matching its self-declared ``gate`` against this pinned name and its own
#: ``advanced`` flag — rather than importing V05's tokens.  Neither value is a
#: canonical schema enum (EF4-I22 is untouched), and a test in the P06 suite pins
#: this constant to V05's real ``GATE_NAME`` so a rename fails loudly instead of
#: drifting silently.
COMPOSED_VALIDATION_GATE_NAME = "validation-cascade-advancement"

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a referral derived from something it never validated"
    ),
    "REQUESTED_LEVEL_INVALID": (
        "the requested promotion level is not a rung of the canonical ladder, so "
        "there is no ceiling to bound the referral against"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the referral, and a role that "
        "proposes candidates may never acquire promotion authority over them"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the parliament receipt, the validation receipt or the attestation does "
        "not describe the one candidate this referral is about"
    ),
    "PARLIAMENT_RECEIPT_TAMPERED": (
        "the parliament receipt was not produced by the evolution-promotion "
        "Parliament gate or does not re-derive its own hash, so the deliberation "
        "it records cannot be trusted as the organ this referral composes"
    ),
    "PARLIAMENT_GRANTS_PROMOTION": (
        "the parliament receipt reports that it holds promotion authority, which a "
        "deliberative organ may never do; a convened docket is never a promotion"
    ),
    "VALIDATION_RECEIPT_TAMPERED": (
        "the validation receipt was not produced by the validation-cascade "
        "advancement gate or does not re-derive its own hash, so its verdict "
        "cannot be trusted as the second independent organ this referral composes"
    ),
    "ATTESTATION_CONTRACT_VIOLATED": (
        "the attestation does not satisfy its canonical schema or does not "
        "re-derive its own hash, so the independent clearance it records was "
        "altered and cannot be the sealed-candidate attestation chain"
    ),
    "ATTESTATION_NOT_INDEPENDENT": (
        "the attestor holds a role it must be independent of, so the attestation "
        "is a self- or conflicted attestation rather than an independent one"
    ),
    "PARLIAMENT_DID_NOT_CONVENE": (
        "the evolution-promotion Parliament did not convene the docket, so one of "
        "the two independent organs did not clear the candidate and a referral "
        "would rest on a single source"
    ),
    "VALIDATION_DID_NOT_ADVANCE": (
        "the validation cascade did not advance the claim, so one of the two "
        "independent organs did not clear the candidate and a referral would rest "
        "on a single source"
    ),
    "MINORITY_DISSENT_NOT_PRESERVED": (
        "the convened docket preserved no minority report, so referring it would "
        "forward a bare-majority promotion with the dissent dropped rather than "
        "preserved"
    ),
    "ATTESTATION_NOT_PASS": (
        "the independent attestation did not pass, so the sealed-candidate "
        "attestation chain refuses rather than clears the candidate for referral"
    ),
    "ATTESTATION_CHAIN_INCOMPLETE": (
        "the attestation does not attest over both sealed organ receipts, so the "
        "chain does not cover the evidence this referral would forward"
    ),
    "FORWARD_LEVEL_EXCEEDS_CEILING": (
        "the referral level is above the lower of the two ceilings the organs "
        "already bounded, so it would claim a level the independent replication "
        "evidence does not support"
    ),
}

#: The canonical schema this gate validates the attestation against, named rather
#: than restated.
ATTESTATION_KIND = "attestation"

#: Property names the gate reads back.  These are schema *field* names, not enum
#: values, so they are named here and read against the schema at use.
CANDIDATE_FIELD = "candidate_id"
DECISION_FIELD = "decision"
GATE_FIELD = "gate"
GATE_ID_FIELD = "gate_id"
RECEIPT_HASH_FIELD = "receipt_hash"
GRANTS_PROMOTION_FIELD = "grants_promotion"
ADVANCED_FIELD = "advanced"
PROMOTION_CEILING_FIELD = "promotion_ceiling"
REPLICATION_CEILING_FIELD = "replication_ceiling"
PRESERVED_MINORITY_FIELD = "preserved_minority_report_ids"
OVERALL_STATUS_FIELD = "overall_status"
ATTESTOR_ID_FIELD = "attestor_id"
SUBJECT_FIELD = "subject_artifact_id"
INPUT_ARTIFACT_IDS_FIELD = "input_artifact_ids"
ATTESTATION_ID_FIELD = "attestation_id"
ATTESTATION_HASH_FIELD = "attestation_hash"

#: The gate's own decision vocabulary.  Neither token is a canonical schema enum
#: value (verified by the wire-literal discipline suite), so they are the gate's
#: to name: a cleared candidate may be *referred* before the promotion authority,
#: and a candidate short of clearance is *withheld* from it.
REFER = "REFER"
WITHHOLD = "WITHHOLD"

#: The dimensions a referral records as cleared, so the receipt states in one
#: place that the decision rests on more than one independent source.  Compound
#: names, none a wire value.
DIMENSION_PARLIAMENT = "parliament_convened"
DIMENSION_VALIDATION = "validation_advanced"
DIMENSION_ATTESTATION = "independent_attestation"
DIMENSION_DISSENT = "preserved_dissent"

#: The receipt's stable name and id prefix.
GATE_NAME = "no-majority-promotion-referral"
GATE_ID_PREFIX = "NMR-"

#: The constitutional gate this referral informs, referenced from the authority
#: that owns the canonical gate ids rather than restated.  Indexing keeps the id
#: in one place: a reorder in ``governance.promotion`` moves this with it.
ATTESTATION_GATE = CANONICAL_GATE_IDS[12]


class NoMajorityPromotionWithheld(ValueError):
    """The gate withholds the referral, or refuses its evidence, with a code."""

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
        raise NoMajorityPromotionWithheld(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise NoMajorityPromotionWithheld(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def gate_grants_promotion() -> bool:
    """Always False: referring a candidate is never itself promotion authority.

    Kept as an explicit predicate rather than an omission so a caller reaching for
    "did this gate promote the candidate?" finds a documented no instead of
    inventing a truthy check on the referred decision.  Promotion authority lives
    in :mod:`epistemic_foundry.governance.promotion`, which takes no score from
    this gate.
    """
    return False


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """The one canonical token the gate needs as a value, read from the schema.

    Holding the passing attestation status as a string literal would be a second
    copy that drifts from the contract (EF4-I22).  It is the attestation schema's
    own first ``overall_status`` rung — the affirmative verdict — so a reshape
    that empties the vocabulary fails closed here rather than silently selecting
    the wrong token.
    """
    document = default_registry().document(ATTESTATION_KIND)
    statuses = document.get("properties", {}).get(OVERALL_STATUS_FIELD, {}).get("enum")
    if not isinstance(statuses, list) or not statuses:
        _fail(
            "ATTESTATION_CONTRACT_VIOLATED",
            "the attestation schema declares no overall-status vocabulary",
            {"schema": ATTESTATION_KIND},
        )
    return {"attestation_pass": str(statuses[0])}


def attestation_pass_status() -> str:
    """The canonical passing attestation status, read from the schema."""
    return _vocab()["attestation_pass"]


@dataclass(frozen=True)
class _Referral:
    """One validated, candidate-bound promotion referral."""

    candidate_id: str
    requested_level: str
    parliament_gate_id: str
    parliament_receipt_hash: str
    parliament_convened: bool
    preserved_minority_report_ids: tuple[str, ...]
    parliament_ceiling: str
    validation_gate_id: str
    validation_receipt_hash: str
    validation_advanced: bool
    validation_ceiling: str
    attestation_id: str
    attestation_hash: str
    attestor_id: str
    attestation_pass: bool
    attestation_chain_complete: bool
    promotion_ceiling: str


def _verify_receipt_hash(receipt: Mapping[str, Any]) -> bool:
    """True when a sealed gate receipt re-derives its own hash from its content."""
    return hash_excluding(dict(receipt), RECEIPT_HASH_FIELD) == receipt.get(
        RECEIPT_HASH_FIELD
    )


def _resolve_parliament(
    parliament_receipt: object, *, expected: str
) -> tuple[str, str, bool, tuple[str, ...], str]:
    """Verify the P05 parliament receipt as an authentic organ for this candidate.

    The receipt is the sealed P05 gate's own output rather than a schema artifact,
    so it is trusted only once it proves it is the receipt it claims to be:
    produced by the evolution-promotion Parliament gate, re-deriving its own hash,
    naming this candidate, and — an authority boundary this gate refuses outright —
    never reporting that it holds promotion authority.
    """
    record = _require_mapping(parliament_receipt, "parliament_receipt")
    if str(record.get(GATE_FIELD)) != PARLIAMENT_GATE_NAME:
        _fail(
            "PARLIAMENT_RECEIPT_TAMPERED",
            "the receipt was not produced by the evolution-promotion Parliament gate",
            {GATE_FIELD: record.get(GATE_FIELD)},
        )
    if not _verify_receipt_hash(record):
        _fail(
            "PARLIAMENT_RECEIPT_TAMPERED",
            "the parliament receipt does not re-derive its own hash",
            {GATE_ID_FIELD: str(record.get(GATE_ID_FIELD) or "")},
        )
    if str(record.get(CANDIDATE_FIELD)) != expected:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the parliament receipt describes a different candidate",
            {"expected": expected, "found": record.get(CANDIDATE_FIELD)},
        )
    # A deliberative organ may never hold promotion authority (EF4-I45).  The
    # owning surface documents this as an always-``False`` predicate; the gate
    # composes it and refuses outright if the receipt or the surface ever weakened
    # it, so a convened docket can never be laundered into a promotion here.
    if bool(record.get(GRANTS_PROMOTION_FIELD)) or parliament_grants_promotion():
        _fail(
            "PARLIAMENT_GRANTS_PROMOTION",
            "the parliament receipt reports that it holds promotion authority",
            {GATE_ID_FIELD: str(record.get(GATE_ID_FIELD) or "")},
        )
    convened = str(record.get(DECISION_FIELD)) == CONVENE
    preserved = tuple(
        str(identifier) for identifier in record.get(PRESERVED_MINORITY_FIELD, [])
    )
    ceiling = _require_text(
        record.get(PROMOTION_CEILING_FIELD), PROMOTION_CEILING_FIELD
    )
    return (
        str(record.get(GATE_ID_FIELD) or ""),
        str(record.get(RECEIPT_HASH_FIELD) or ""),
        convened,
        preserved,
        ceiling,
    )


def _resolve_validation(
    validation_receipt: object, *, expected: str
) -> tuple[str, str, bool, str]:
    """Verify the V05 validation receipt as an authentic second organ.

    Trusted only once it proves it is the receipt it claims to be: produced by the
    validation-cascade advancement gate (matched against the pinned boundary name,
    because the V05 surface cannot be imported without closing a forbidden
    ``parliament``↔``validation`` cycle), re-deriving its own hash, and naming this
    candidate.  Because the parliament receipt is checked against the *parliament*
    gate name and this one against the *validation* gate name, the same organ can
    never be passed twice to fake a second independent dimension.  Whether it
    advanced is read from the receipt's own self-declared ``advanced`` flag.
    """
    record = _require_mapping(validation_receipt, "validation_receipt")
    if str(record.get(GATE_FIELD)) != COMPOSED_VALIDATION_GATE_NAME:
        _fail(
            "VALIDATION_RECEIPT_TAMPERED",
            "the receipt was not produced by the validation-cascade advancement gate",
            {GATE_FIELD: record.get(GATE_FIELD)},
        )
    if not _verify_receipt_hash(record):
        _fail(
            "VALIDATION_RECEIPT_TAMPERED",
            "the validation receipt does not re-derive its own hash",
            {GATE_ID_FIELD: str(record.get(GATE_ID_FIELD) or "")},
        )
    if str(record.get(CANDIDATE_FIELD)) != expected:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the validation receipt describes a different candidate",
            {"expected": expected, "found": record.get(CANDIDATE_FIELD)},
        )
    advanced_value = record.get(ADVANCED_FIELD)
    if type(advanced_value) is not bool:
        _fail(
            "VALIDATION_RECEIPT_TAMPERED",
            "the validation receipt carries no boolean advancement verdict",
            {ADVANCED_FIELD: advanced_value},
        )
    advanced = advanced_value is True
    ceiling = _require_text(
        record.get(REPLICATION_CEILING_FIELD), REPLICATION_CEILING_FIELD
    )
    return (
        str(record.get(GATE_ID_FIELD) or ""),
        str(record.get(RECEIPT_HASH_FIELD) or ""),
        advanced,
        ceiling,
    )


def _resolve_attestation(
    attestation: object,
    *,
    expected: str,
    independence_context: Mapping[str, Any],
    parliament_gate_id: str,
    validation_gate_id: str,
) -> tuple[str, str, str, bool, bool]:
    """Verify the sealed-candidate attestation and its independence.

    The attestation is validated against its canonical schema and required to
    re-derive its own hash, to name this candidate as its subject, and to be
    produced by an attestor proven independent of the makers through the
    evolution-authority surface that owns charter section 6 — the gate does not
    restate that rule, it composes it.  Whether the attestation *passed* and
    whether it *covers both organ receipts* are substantive questions returned to
    the decision phase, not refused here.
    """
    record = _require_mapping(attestation, "attestation")
    try:
        validate_artifact(ATTESTATION_KIND, record)
    except ContractViolation as error:
        _fail(
            "ATTESTATION_CONTRACT_VIOLATED",
            "the attestation does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    recomputed = hash_excluding(record, ATTESTATION_HASH_FIELD)
    if recomputed != record.get(ATTESTATION_HASH_FIELD):
        _fail(
            "ATTESTATION_CONTRACT_VIOLATED",
            "the attestation does not re-derive its own hash",
            {"recorded": record.get(ATTESTATION_HASH_FIELD), "recomputed": recomputed},
        )
    if str(record.get(SUBJECT_FIELD)) != expected:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the attestation names a different candidate as its subject",
            {"expected": expected, "found": record.get(SUBJECT_FIELD)},
        )
    attestor_id = _require_text(record.get(ATTESTOR_ID_FIELD), ATTESTOR_ID_FIELD)
    try:
        verify_attestor_independence(attestor_id, dict(independence_context))
    except EvolutionAuthorityError as error:
        _fail(
            "ATTESTATION_NOT_INDEPENDENT",
            str(error),
            {"attestor_id": attestor_id, "authority_code": error.code},
        )
    covered = {
        str(identifier) for identifier in record.get(INPUT_ARTIFACT_IDS_FIELD, [])
    }
    chain_complete = parliament_gate_id in covered and validation_gate_id in covered
    passed = str(record.get(OVERALL_STATUS_FIELD)) == attestation_pass_status()
    return (
        str(record.get(ATTESTATION_ID_FIELD)),
        str(record.get(ATTESTATION_HASH_FIELD)),
        attestor_id,
        passed,
        chain_complete,
    )


def _lower_ceiling(parliament_ceiling: str, validation_ceiling: str) -> str:
    """The lower of the two ceilings the organs already bounded."""
    if promotion_rank(validation_ceiling) < promotion_rank(parliament_ceiling):
        return validation_ceiling
    return parliament_ceiling


def _decide(referral: _Referral) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message and its context.

    The order is deliberate.  The two independent organs come first — a referral
    that rests on a single source is refused before anything else, because breadth
    is the whole point.  Preserved dissent is next, because a bare-majority
    promotion is refused however well attested.  The attestation chain follows,
    and the replication-bounded ceiling last, so a candidate that clears every
    prior concern but claims a level replication cannot support is named for
    exactly that.
    """
    if not referral.parliament_convened:
        return (
            WITHHOLD,
            "PARLIAMENT_DID_NOT_CONVENE",
            "the evolution-promotion Parliament did not convene the docket",
            {},
        )
    if not referral.validation_advanced:
        return (
            WITHHOLD,
            "VALIDATION_DID_NOT_ADVANCE",
            "the validation cascade did not advance the claim",
            {},
        )
    if not referral.preserved_minority_report_ids:
        return (
            WITHHOLD,
            "MINORITY_DISSENT_NOT_PRESERVED",
            "the convened docket preserved no minority report",
            {},
        )
    if not referral.attestation_pass:
        return (
            WITHHOLD,
            "ATTESTATION_NOT_PASS",
            "the independent attestation did not pass",
            {},
        )
    if not referral.attestation_chain_complete:
        return (
            WITHHOLD,
            "ATTESTATION_CHAIN_INCOMPLETE",
            "the attestation does not attest over both sealed organ receipts",
            {},
        )
    if promotion_rank(referral.requested_level) > promotion_rank(
        referral.promotion_ceiling
    ):
        return (
            WITHHOLD,
            "FORWARD_LEVEL_EXCEEDS_CEILING",
            "the referral level is above the ceiling the organs already bounded",
            {
                "requested_level": referral.requested_level,
                "promotion_ceiling": referral.promotion_ceiling,
            },
        )
    return (
        REFER,
        None,
        "the sealed candidate cleared two independent organs, preserved its "
        "dissent and its attestation chain, and may be referred to the promotion "
        "authority",
        {},
    )


def derive_promotion_referral(
    *,
    candidate_id: str,
    requested_level: str,
    parliament_receipt: Mapping[str, Any],
    validation_receipt: Mapping[str, Any],
    attestation: Mapping[str, Any],
    attestor_independence_context: Mapping[str, Any],
    requesting_principal_id: str,
    requesting_role: str,
    created_at: str,
) -> dict[str, Any]:
    """Derive the referral decision and its immutable receipt.

    Input-integrity failures — a candidate-generating requesting role, a receipt
    or attestation that does not describe this candidate, a parliament or
    validation receipt that was not produced by its owning gate or does not
    re-derive its hash, a parliament receipt that claims promotion authority, an
    attestation that fails its schema or its independence — refuse immediately,
    because there is no well-formed referral to record over evidence the gate
    cannot trust.  Once every input is validated and bound, the referral decision
    always produces a receipt, whether it refers or withholds, so every decision
    over well-formed inputs is auditable and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    expected = _require_text(candidate_id, CANDIDATE_FIELD)
    level = _require_text(requested_level, "requested_level")
    principal = _require_text(requesting_principal_id, "requesting_principal_id")
    role = _require_text(requesting_role, "requesting_role")

    if level not in PROMOTION_LADDER:
        _fail(
            "REQUESTED_LEVEL_INVALID",
            "the requested promotion level is not a rung of the canonical ladder",
            {"requested_level": level, "ladder": list(PROMOTION_LADDER)},
        )

    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive a referral",
            {"role": role},
        )

    context = _require_mapping(
        attestor_independence_context, "attestor_independence_context"
    )

    (
        parliament_gate_id,
        parliament_receipt_hash,
        parliament_convened,
        preserved_minority,
        parliament_ceiling,
    ) = _resolve_parliament(parliament_receipt, expected=expected)

    (
        validation_gate_id,
        validation_receipt_hash,
        validation_advanced,
        validation_ceiling,
    ) = _resolve_validation(validation_receipt, expected=expected)

    (
        attestation_id,
        attestation_hash,
        attestor_id,
        attestation_pass,
        attestation_chain_complete,
    ) = _resolve_attestation(
        attestation,
        expected=expected,
        independence_context=context,
        parliament_gate_id=parliament_gate_id,
        validation_gate_id=validation_gate_id,
    )

    ceiling = _lower_ceiling(parliament_ceiling, validation_ceiling)

    referral = _Referral(
        candidate_id=expected,
        requested_level=level,
        parliament_gate_id=parliament_gate_id,
        parliament_receipt_hash=parliament_receipt_hash,
        parliament_convened=parliament_convened,
        preserved_minority_report_ids=preserved_minority,
        parliament_ceiling=parliament_ceiling,
        validation_gate_id=validation_gate_id,
        validation_receipt_hash=validation_receipt_hash,
        validation_advanced=validation_advanced,
        validation_ceiling=validation_ceiling,
        attestation_id=attestation_id,
        attestation_hash=attestation_hash,
        attestor_id=attestor_id,
        attestation_pass=attestation_pass,
        attestation_chain_complete=attestation_chain_complete,
        promotion_ceiling=ceiling,
    )

    decision, finding_code, message, decision_context = _decide(referral)

    dimensions_cleared = sorted(
        dimension
        for dimension, cleared in (
            (DIMENSION_PARLIAMENT, parliament_convened),
            (DIMENSION_VALIDATION, validation_advanced),
            (DIMENSION_DISSENT, bool(preserved_minority)),
            (DIMENSION_ATTESTATION, attestation_pass and attestation_chain_complete),
        )
        if cleared
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "referred_to_promotion_authority": decision == REFER,
        "grants_promotion": gate_grants_promotion(),
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": expected,
        "requested_level": level,
        "requesting_principal_id": principal,
        "requesting_role": role,
        "informs_gate_decision": ATTESTATION_GATE,
        "dimensions_cleared": dimensions_cleared,
        "parliament_gate_id": parliament_gate_id,
        "parliament_receipt_hash": parliament_receipt_hash,
        "parliament_convened": parliament_convened,
        "preserved_minority_report_ids": list(preserved_minority),
        "parliament_ceiling": parliament_ceiling,
        "validation_gate_id": validation_gate_id,
        "validation_receipt_hash": validation_receipt_hash,
        "validation_advanced": validation_advanced,
        "validation_ceiling": validation_ceiling,
        "attestation_id": attestation_id,
        "attestation_hash": attestation_hash,
        "attestor_id": attestor_id,
        "attestation_pass": attestation_pass,
        "attestation_chain_complete": attestation_chain_complete,
        "promotion_ceiling": ceiling,
    }
    receipt["gate_id"] = (
        GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": expected,
                    "created_at": stamp,
                    "decision": decision,
                    "parliament_receipt_hash": parliament_receipt_hash,
                    "validation_receipt_hash": validation_receipt_hash,
                    "attestation_hash": attestation_hash,
                    "requested_level": level,
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_promotion_referral(**kwargs: Any) -> dict[str, Any]:
    """Enforce the gate: return the receipt on refer, raise on any withholding.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the candidate was withheld from promotion review.
    """
    receipt = derive_promotion_referral(**kwargs)
    if receipt["decision"] != REFER:
        raise NoMajorityPromotionWithheld(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a withholding.
__all__ = [
    "FINDING_CODES",
    "GATE_NAME",
    "NoMajorityPromotionWithheld",
    "REFER",
    "SchemaNotFound",
    "WITHHOLD",
    "attestation_pass_status",
    "derive_promotion_referral",
    "evaluate_promotion_referral",
    "gate_grants_promotion",
]
