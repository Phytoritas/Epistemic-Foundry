"""Calibration, winner's-curse and statistical-governance integration gate (Q06).

Q05 sealed the multi-objective, hidden-evaluation and selective-inference gate:
whether an adaptively-selected candidate is statistically *admissible to review*.
V05 sealed the validation-cascade / OOD-challenge / replication-ceiling gate:
whether that same candidate's claim *may advance*.  Each is correct alone, and
neither answers the one question this gate exists for: for a single
adaptively-selected candidate, do the statistical admissibility, the validation
advancement, the confidence calibration and the winner's-curse accounting
*together* describe one coherent, statistically-governed selection — and does the
composition emit an immutable, re-derivable record of that decision?

This is an *integration* gate.  It composes the already-sealed verdicts and
records an integration decision only; it scores nothing, selects nothing,
evaluates nothing, promotes nothing, mutates no input and reads no clock.
Promotion authority lives in ``governance.promotion`` and takes no score; this
gate holds none of it.  No single dimension can carry the decision: a candidate
is governance-cleared only when *all four* orthogonal concerns hold, so a high
score on one can never stand in for the gates on the others (EF4-I45).

* **Statistical admissibility (Q05).**  The Q05 receipt is composed rather than
  re-derived.  It is trusted only once it proves it is the receipt it claims to
  be — produced by the statistical-admissibility gate, re-deriving its own hash,
  and naming this candidate — and its adaptive selection counts as cleared only
  when its decision *admitted* the candidate to review.

* **Validation advancement (V05).**  The V05 receipt is composed *without*
  importing the ``validation`` component: doing so would close a new top-level
  ``evaluation``↔``validation`` import cycle that ADR-034's fingerprinted
  allowlist does not permit.  The receipt is instead verified as a self-sealing
  artifact — it must re-derive its own hash, name this candidate, and carry a
  boolean advancement verdict — and it is *bound* to this exact Q05 clearance:
  the advancement receipt's recorded statistical-admissibility hash must equal
  the Q05 receipt's own hash, so the two sealed verdicts provably describe one
  governed selection rather than two unrelated ones stitched together.

* **Calibration.**  A calibration report is validated against its canonical
  schema and required to describe this candidate's evaluation.  A miscalibrated,
  under-powered or unresolved report — anything but the schema's own passing
  calibration status — refuses governance, because a confidence the model is not
  entitled to must not be governed as promotable.

* **Winner's-curse.**  The selective-inference report is validated against its
  canonical schema, must name this candidate, and must be the *same* report the
  Q05 clearance already accounted for — its content hash must equal the hash Q05
  recorded.  This is the winner's-curse governance the gate enforces directly: a
  candidate reaches promotion review because its estimate was extreme, and the
  deflation that prices that selection in lives in the sealed selective-inference
  report Q05 already admitted against.  Requiring that exact report — rather than
  re-checking a scalar the caller could swap for a rosier one — is what stops a
  cleaner report being laundered in after the deflation was accounted.  Whether
  the report itself permits advancement is not re-litigated here: Q05's admission
  already turns on it, so the gate reads that predicate for the record but gates
  on the binding and on the admission, never on a resupplied number.

Every decision, govern or refuse, resolves to one immutable receipt that is a
pure function of its inputs: there is no clock and no random draw, the caller
supplies ``created_at``, and the gate id and receipt hash re-derive byte for byte
from the receipt's own published fields.  No input is ever mutated.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    validate_artifact,
)
from ...domain.hashing import canonical_json, hash_excluding, sha256_hex
from ...statistics.selective import permits_promotion_without_replication
from ...verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES
from ..v4_q05 import ADMIT as STATISTICAL_ADMIT
from ..v4_q05 import GATE_NAME as STATISTICAL_GATE_NAME

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a governance decision derived from something it never validated"
    ),
    "VOCABULARY_DRIFT": (
        "the calibration-report schema no longer declares its status vocabulary "
        "in the shape this gate reads positionally, so selecting the passing "
        "token by index would pick the wrong value; the gate fails closed"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the governance decision, and a "
        "role that proposes candidates may never acquire evaluator, holdout or "
        "promotion authority over its own selection"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the admissibility receipt, the advancement receipt, the calibration "
        "report or the selective-inference report do not all describe the one "
        "candidate this decision is about"
    ),
    "ADMISSIBILITY_RECEIPT_UNVERIFIED": (
        "the statistical-admissibility receipt was not produced by the "
        "admissibility gate or does not re-derive its own hash, so its verdict "
        "cannot be trusted as the statistical clearance this gate composes"
    ),
    "ADVANCEMENT_RECEIPT_UNVERIFIED": (
        "the validation-advancement receipt does not re-derive its own hash or "
        "carries no boolean advancement verdict, so it is not the self-sealing "
        "advancement record this gate composes"
    ),
    "ADVANCEMENT_ADMISSIBILITY_UNBOUND": (
        "the advancement receipt's recorded statistical-admissibility hash does "
        "not equal this Q05 clearance's own hash, so the two sealed verdicts "
        "describe different selections and were stitched together after the fact"
    ),
    "CALIBRATION_CONTRACT_VIOLATED": (
        "the calibration report does not satisfy its canonical schema, so its "
        "calibration status and evaluation binding would be read from a shape no "
        "contract admits"
    ),
    "CALIBRATION_EVALUATION_MISMATCH": (
        "the calibration report describes a different evaluation than the one "
        "this decision governs, so a calibrated evaluation was borrowed to cover "
        "an uncalibrated one"
    ),
    "SELECTIVE_REPORT_CONTRACT_VIOLATED": (
        "the selective-inference report does not satisfy its canonical schema, so "
        "its winner's-curse verdict would be read from a shape no contract admits"
    ),
    "SELECTIVE_REPORT_MISBOUND": (
        "the selective-inference report is not the report the Q05 clearance "
        "accounted for — its content hash differs from the hash Q05 recorded — so "
        "a cleaner report was substituted after the winner's-curse was priced in"
    ),
    "ADMISSIBILITY_NOT_ADMITTED": (
        "the statistical-admissibility gate did not admit the candidate to "
        "review, so its adaptive selection was never statistically cleared and no "
        "downstream concern can substitute for that clearance"
    ),
    "ADVANCEMENT_NOT_ADVANCED": (
        "the validation-advancement gate did not advance the claim, so its "
        "cascade, OOD challenge or replication ceiling was not satisfied and the "
        "selection is not validation-governed"
    ),
    "CALIBRATION_NOT_PASSED": (
        "the calibration report did not reach the passing calibration status, so "
        "the model's confidence is not one it has earned and must not be governed "
        "as promotable"
    ),
}

#: Canonical schema names this gate reads a vocabulary or a contract out of.
#: These are schema *names*, not wire enum values, and each is verified at use.
CALIBRATION_KIND = "calibration-report"
SELECTIVE_REPORT_KIND = "selective-inference-report"

#: Property names the gate reads back.  These are schema *field* names, not enum
#: values, so they are named here and verified against the schema at use.
CALIBRATION_STATUS_FIELD = "calibration_status"
CALIBRATION_EVALUATION_FIELD = "evaluation_id"
CANDIDATE_FIELD = "candidate_id"

#: Fields the composed Q05 clearance publishes that this gate binds against.
ADMISSIBILITY_RECEIPT_HASH_FIELD = "receipt_hash"
ADMISSIBILITY_SELECTIVE_HASH_FIELD = "selective_report_hash"

#: Fields the composed V05 advancement receipt publishes that this gate reads.
ADVANCEMENT_VERDICT_FIELD = "advanced"
ADVANCEMENT_ADMISSIBILITY_HASH_FIELD = "statistical_admissibility_receipt_hash"
ADVANCEMENT_HASH_FIELD = "receipt_hash"

#: The gate's own decision vocabulary.  Neither token is a canonical schema enum
#: value (verified by the schema-and-type suite), so they are the gate's to name:
#: a coherent selection may be *governed as cleared for promotion review*, and a
#: refused one is stopped short of it.  The gate never promotes on either token.
GOVERN = "GOVERN"
REFUSE = "REFUSE"

#: The concerns this gate reconciles, named so the receipt records which
#: boundaries it composed.  Compound names, none a wire value.
CONCERN_STATISTICAL_ADMISSIBILITY = "statistical_admissibility"
CONCERN_VALIDATION_ADVANCEMENT = "validation_advancement"
CONCERN_CALIBRATION = "confidence_calibration"
CONCERN_WINNER_CURSE = "winner_curse_control"

#: The receipt's stable name and id prefix.
GATE_NAME = "calibration-winner-curse-governance"
GATE_ID_PREFIX = "CWG-"


class GovernanceIntegrationRefused(ValueError):
    """The gate refuses governance, or its evidence, with a documented code."""

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
        raise GovernanceIntegrationRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise GovernanceIntegrationRefused(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """The one canonical token the gate reasons about, read from the schema.

    Holding the passing calibration status as a string literal would be a second
    copy that drifts from the contract (EF4-I22).  It is the calibration-report
    schema's own first declared rung of the status ladder; a reshape that empties
    or reorders the ladder fails closed here rather than silently selecting the
    wrong token.
    """
    document = default_registry().document(CALIBRATION_KIND)
    statuses = (
        document.get("properties", {}).get(CALIBRATION_STATUS_FIELD, {}).get("enum")
    )
    if not isinstance(statuses, list) or not statuses:
        _fail(
            "VOCABULARY_DRIFT",
            "the calibration-report schema declares no calibration status vocabulary",
            {"schema": CALIBRATION_KIND},
        )
    return {"calibration_pass": str(statuses[0])}


def calibration_pass_status() -> str:
    """The canonical passing calibration status, read from the schema."""
    return _vocab()["calibration_pass"]


def _verify_admissibility(
    admissibility_receipt: Mapping[str, Any], *, candidate_id: str
) -> dict[str, Any]:
    """Verify the composed Q05 receipt as an authentic clearance for this claim.

    The receipt is Q05's own output rather than a schema artifact, so it is
    trusted only once it proves it is the receipt it claims to be: produced by the
    statistical-admissibility gate, re-deriving its own hash, and naming this
    candidate.  Whether that receipt *admitted* the candidate is a separate,
    substantive question decided in the governance phase, not here.
    """
    record = _require_mapping(admissibility_receipt, "admissibility_receipt")
    if str(record.get("gate")) != STATISTICAL_GATE_NAME:
        _fail(
            "ADMISSIBILITY_RECEIPT_UNVERIFIED",
            "the receipt was not produced by the statistical-admissibility gate",
            {"gate": record.get("gate")},
        )
    if hash_excluding(dict(record), "receipt_hash") != record.get("receipt_hash"):
        _fail(
            "ADMISSIBILITY_RECEIPT_UNVERIFIED",
            "the admissibility receipt does not re-derive its own hash",
            {"gate_id": str(record.get("gate_id") or "")},
        )
    if str(record.get(CANDIDATE_FIELD)) != candidate_id:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the admissibility receipt describes a different candidate",
            {"expected": candidate_id, "found": record.get(CANDIDATE_FIELD)},
        )
    return record


def _verify_advancement(
    advancement_receipt: Mapping[str, Any],
    *,
    candidate_id: str,
    admissibility: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the composed V05 receipt without importing the ``validation`` graph.

    Importing ``validation.v4_v05`` to reuse its constants would close a new
    top-level ``evaluation``↔``validation`` import cycle outside ADR-034's
    fingerprinted allowlist.  So the advancement receipt is treated as a
    self-sealing artifact: it must re-derive its own hash, carry a boolean
    advancement verdict, and name this candidate.  It is then bound to this exact
    Q05 clearance — its recorded statistical-admissibility hash must equal the
    Q05 receipt's own hash — so a forged advancement record cannot claim a
    clearance it never composed.  Whether the receipt *advanced* is decided in
    the governance phase, not here.
    """
    record = _require_mapping(advancement_receipt, "advancement_receipt")
    if hash_excluding(dict(record), "receipt_hash") != record.get("receipt_hash"):
        _fail(
            "ADVANCEMENT_RECEIPT_UNVERIFIED",
            "the advancement receipt does not re-derive its own hash",
            {"gate_id": str(record.get("gate_id") or "")},
        )
    if not isinstance(record.get(ADVANCEMENT_VERDICT_FIELD), bool):
        _fail(
            "ADVANCEMENT_RECEIPT_UNVERIFIED",
            "the advancement receipt carries no boolean advancement verdict",
            {ADVANCEMENT_VERDICT_FIELD: record.get(ADVANCEMENT_VERDICT_FIELD)},
        )
    if str(record.get(CANDIDATE_FIELD)) != candidate_id:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the advancement receipt describes a different candidate",
            {"expected": candidate_id, "found": record.get(CANDIDATE_FIELD)},
        )
    if str(record.get(ADVANCEMENT_ADMISSIBILITY_HASH_FIELD) or "") != str(
        admissibility.get(ADMISSIBILITY_RECEIPT_HASH_FIELD) or ""
    ):
        _fail(
            "ADVANCEMENT_ADMISSIBILITY_UNBOUND",
            "the advancement receipt does not bind this Q05 clearance by hash",
            {
                "advancement_bound_hash": record.get(
                    ADVANCEMENT_ADMISSIBILITY_HASH_FIELD
                ),
                "admissibility_hash": admissibility.get(
                    ADMISSIBILITY_RECEIPT_HASH_FIELD
                ),
            },
        )
    return record


def _verify_calibration(
    calibration_report: Mapping[str, Any], *, evaluation_id: str
) -> dict[str, Any]:
    """Validate the calibration report and bind it to the governed evaluation."""
    record = _require_mapping(calibration_report, "calibration_report")
    try:
        validate_artifact(CALIBRATION_KIND, record)
    except ContractViolation as error:
        _fail(
            "CALIBRATION_CONTRACT_VIOLATED",
            "the calibration report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if str(record.get(CALIBRATION_EVALUATION_FIELD)) != evaluation_id:
        _fail(
            "CALIBRATION_EVALUATION_MISMATCH",
            "the calibration report describes a different evaluation",
            {
                "expected": evaluation_id,
                "found": record.get(CALIBRATION_EVALUATION_FIELD),
            },
        )
    return record


def _verify_selective_report(
    selective_report: Mapping[str, Any],
    *,
    candidate_id: str,
    admissibility: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the selective report and bind it to Q05's own accounting.

    The report must be the one the Q05 clearance priced the winner's-curse over,
    proven by re-deriving its content hash exactly as Q05 did and requiring the
    match, so a cleaner report cannot be substituted after the fact.
    """
    record = _require_mapping(selective_report, "selective_report")
    try:
        validate_artifact(SELECTIVE_REPORT_KIND, record)
    except ContractViolation as error:
        _fail(
            "SELECTIVE_REPORT_CONTRACT_VIOLATED",
            "the selective-inference report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if str(record.get(CANDIDATE_FIELD)) != candidate_id:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the selective-inference report describes a different candidate",
            {"expected": candidate_id, "found": record.get(CANDIDATE_FIELD)},
        )
    recomputed = sha256_hex(canonical_json(record))
    recorded = str(admissibility.get(ADMISSIBILITY_SELECTIVE_HASH_FIELD) or "")
    if recomputed != recorded:
        _fail(
            "SELECTIVE_REPORT_MISBOUND",
            "the selective report is not the one the Q05 clearance accounted for",
            {"recomputed": recomputed, "recorded": recorded},
        )
    return record


def _decide(
    *,
    admitted: bool,
    advanced: bool,
    calibrated: bool,
    calibration_status: str,
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message and its context.

    The order is deliberate and each dimension is separate, so no single one can
    carry the decision.  The statistical admissibility is the frame: a selection
    Q05 never admitted — which already turns on the winner's-curse deflation — is
    refused first.  The validation advancement follows, because an unadvanced
    claim is not validation-governed however calibrated it looks.  Calibration is
    last, so a selection that clears both sealed verdicts but whose confidence is
    not calibrated is named for exactly that and nothing else.  The winner's-curse
    is not a fourth branch here: its governance is the sealed admission above and
    the same-report binding enforced before this decision, never a scalar re-read.
    """
    if not admitted:
        return (
            REFUSE,
            "ADMISSIBILITY_NOT_ADMITTED",
            "the statistical-admissibility gate did not admit the candidate",
            {},
        )
    if not advanced:
        return (
            REFUSE,
            "ADVANCEMENT_NOT_ADVANCED",
            "the validation-advancement gate did not advance the claim",
            {},
        )
    if not calibrated:
        return (
            REFUSE,
            "CALIBRATION_NOT_PASSED",
            "the calibration report did not reach the passing calibration status",
            {CALIBRATION_STATUS_FIELD: calibration_status},
        )
    return (
        GOVERN,
        None,
        "the selection is statistically admitted, validation-advanced and "
        "calibrated, with its winner's-curse deflation bound to the admission, and "
        "may be governed as cleared for promotion review",
        {},
    )


def derive_governance_integration(
    *,
    candidate_id: str,
    evaluation_id: str,
    admissibility_receipt: Mapping[str, Any],
    advancement_receipt: Mapping[str, Any],
    calibration_report: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    requesting_role: str,
    requesting_principal_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Derive the governance-integration decision and its immutable receipt.

    Input-integrity failures — a candidate-generating requesting role, an
    artifact describing a different candidate or evaluation, an unverifiable or
    unbound receipt, a malformed calibration or selective report, a substituted
    selective report — refuse immediately, because there is no well-formed
    decision to record over evidence the gate cannot trust.  Once every input is
    validated and bound, the governance decision always produces a receipt,
    whether it governs or refuses, so every decision over well-formed inputs is
    auditable and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    candidate = _require_text(candidate_id, CANDIDATE_FIELD)
    evaluation = _require_text(evaluation_id, CALIBRATION_EVALUATION_FIELD)
    role = _require_text(requesting_role, "requesting_role")
    principal = _require_text(requesting_principal_id, "requesting_principal_id")

    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive a governance decision",
            {"role": role},
        )

    admissibility = _verify_admissibility(admissibility_receipt, candidate_id=candidate)
    advancement = _verify_advancement(
        advancement_receipt, candidate_id=candidate, admissibility=admissibility
    )
    calibration = _verify_calibration(calibration_report, evaluation_id=evaluation)
    selective = _verify_selective_report(
        selective_report, candidate_id=candidate, admissibility=admissibility
    )

    admitted = (
        str(admissibility.get("decision")) == STATISTICAL_ADMIT
        and admissibility.get("admissible_for_promotion_review") is True
    )
    advanced = advancement.get(ADVANCEMENT_VERDICT_FIELD) is True
    calibration_status = str(calibration.get(CALIBRATION_STATUS_FIELD))
    calibrated = calibration_status == calibration_pass_status()
    winner_curse_controlled = permits_promotion_without_replication(selective)

    decision, finding_code, message, decision_context = _decide(
        admitted=admitted,
        advanced=advanced,
        calibrated=calibrated,
        calibration_status=calibration_status,
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "cleared_for_promotion_review": decision == GOVERN,
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": candidate,
        "evaluation_id": evaluation,
        "requesting_role": role,
        "requesting_principal_id": principal,
        "concerns_gated": sorted(
            (
                CONCERN_STATISTICAL_ADMISSIBILITY,
                CONCERN_VALIDATION_ADVANCEMENT,
                CONCERN_CALIBRATION,
                CONCERN_WINNER_CURSE,
            )
        ),
        "statistical_admissibility_gate_id": str(admissibility.get("gate_id") or ""),
        "statistical_admissibility_receipt_hash": str(
            admissibility.get(ADMISSIBILITY_RECEIPT_HASH_FIELD) or ""
        ),
        "statistical_admitted": admitted,
        "validation_advancement_gate_id": str(advancement.get("gate_id") or ""),
        "validation_advancement_receipt_hash": str(
            advancement.get(ADVANCEMENT_HASH_FIELD) or ""
        ),
        "validation_advanced": advanced,
        "calibration_report_id": str(calibration.get("calibration_report_id") or ""),
        "calibration_status": calibration_status,
        "calibration_passed": calibrated,
        "selective_inference_report_id": str(selective.get("report_id") or ""),
        "selective_report_hash": str(
            admissibility.get(ADMISSIBILITY_SELECTIVE_HASH_FIELD) or ""
        ),
        "winner_curse_risk": str(selective.get("winner_curse_risk") or ""),
        "winner_curse_controlled": winner_curse_controlled,
    }
    receipt["gate_id"] = (
        GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": candidate,
                    "created_at": stamp,
                    "decision": decision,
                    "evaluation_id": evaluation,
                    "statistical_admissibility_receipt_hash": receipt[
                        "statistical_admissibility_receipt_hash"
                    ],
                    "validation_advancement_receipt_hash": receipt[
                        "validation_advancement_receipt_hash"
                    ],
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_governance_integration(
    *,
    candidate_id: str,
    evaluation_id: str,
    admissibility_receipt: Mapping[str, Any],
    advancement_receipt: Mapping[str, Any],
    calibration_report: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    requesting_role: str,
    requesting_principal_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on govern, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the selection was stopped short of promotion review.
    """
    receipt = derive_governance_integration(
        candidate_id=candidate_id,
        evaluation_id=evaluation_id,
        admissibility_receipt=admissibility_receipt,
        advancement_receipt=advancement_receipt,
        calibration_report=calibration_report,
        selective_report=selective_report,
        requesting_role=requesting_role,
        requesting_principal_id=requesting_principal_id,
        created_at=created_at,
    )
    if receipt["decision"] != GOVERN:
        raise GovernanceIntegrationRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


def governance_hash_matches(receipt: Mapping[str, Any]) -> bool:
    """True when a governance receipt re-derives its own hash from its content."""
    sealed = _require_mapping(receipt, "governance receipt")
    return hash_excluding(dict(sealed), "receipt_hash") == sealed.get("receipt_hash")


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a refusal.
__all__ = [
    "FINDING_CODES",
    "GATE_ID_PREFIX",
    "GATE_NAME",
    "GOVERN",
    "GovernanceIntegrationRefused",
    "REFUSE",
    "SchemaNotFound",
    "calibration_pass_status",
    "derive_governance_integration",
    "evaluate_governance_integration",
    "governance_hash_matches",
]
