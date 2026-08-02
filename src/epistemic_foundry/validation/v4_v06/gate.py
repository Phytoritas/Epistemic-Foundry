"""Experiment/replication end-to-end integration gate (V06).

Q05 sealed the statistical admissibility of an adaptively-selected candidate:
its fitness stayed a vector, its hidden evaluation stayed sealed, and its
best-of-many selection was corrected.  V05 sealed the validation cascade,
out-of-distribution challenge and replication-ceiling advancement of the same
candidate's claim.  P05 sealed the promotion Parliament docket — the multi-
dimensional review with its dissent preserved and its ceiling bounded — that may
be convened before the promotion authority.  Each surface is correct alone, and
none of them answers the one question this gate exists for: for a single
candidate travelling the experiment/replication path end to end, did the
statistical clearance, the validation advancement and the promotion convening
*all* clear, do they *all* describe the same candidate, and do the two downstream
gates rest on the *same* statistical clearance this gate was handed — and does the
composition emit an immutable, re-derivable record of that decision?

This is an *integration* gate.  It composes the sealed sub-gate receipts and
records an integration decision only.  It scores nothing, selects nothing,
evaluates nothing, and promotes nothing: promotion authority lives in
``governance.promotion`` and takes no score, and :func:`integration_grants_promotion`
says in one place a caller can find that this gate holds none of it.  It also
re-verifies that the Parliament receipt it composes still reports itself as
non-promoting, so a docket that had acquired promotion authority is refused
before its convening is trusted.

Every sub-receipt is re-derived from its own content — the ``gate`` it names must
be the sealed gate that mints it, and its published ``receipt_hash`` must re-hash
byte for byte from the rest of its fields — so a tampered sub-decision cannot be
laundered into the combined record.  The end-to-end binding this adds, that none
of the three gates can see alone, is twofold: every receipt must name the one
candidate the integration is about, and the statistical clearance both the
validation advancement (V05) and the promotion Parliament (P05) composed must be
the *same* Q05 receipt handed to this gate, so a coherent-looking path assembled
from a candidate's advancement over here and a *different* statistical clearance
over there is refused before it reads as an end-to-end pass.

No candidate, model, prompt, backend or hook may drive the decision: a
candidate-generating requesting role is refused with the set the verifier
firewall declares.  Every decision, integrate or refuse, resolves to one
immutable receipt that is a pure function of its inputs — there is no clock and no
random draw, the caller supplies ``created_at``, and the gate id and receipt hash
re-derive byte for byte from the receipt's own published fields.  No input is
ever mutated.
"""

from __future__ import annotations

from typing import Any, Mapping

from ...domain.hashing import canonical_json, hash_excluding, sha256_hex
from ...evaluation.v4_q05 import ADMIT as STATISTICAL_ADMIT
from ...evaluation.v4_q05 import GATE_NAME as STATISTICAL_GATE_NAME
from ...parliament.v4_p05 import CONVENE as PARLIAMENT_CONVENE
from ...parliament.v4_p05 import GATE_NAME as PARLIAMENT_GATE_NAME
from ...parliament.v4_p05 import parliament_grants_promotion
from ...validation.v4_v05 import ADVANCE as VALIDATION_ADVANCE
from ...validation.v4_v05 import GATE_NAME as VALIDATION_GATE_NAME
from ...verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record an integration derived from something it never validated"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the integration decision, and a "
        "role that proposes candidates may never acquire evaluator, holdout or "
        "promotion authority over its own claim's end-to-end path"
    ),
    "SUBGATE_IDENTITY_MISMATCH": (
        "a composed sub-receipt does not name the sealed gate that mints it, so "
        "the integration would bind a record produced by something other than the "
        "statistical, validation or Parliament gate it stands in for"
    ),
    "SUBGATE_RECEIPT_TAMPERED": (
        "a composed sub-receipt does not re-derive its own hash, so its verdict "
        "was altered after the sealed gate produced it and cannot be trusted as "
        "the decision this gate composes"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the statistical clearance, the validation advancement or the promotion "
        "Parliament receipt does not describe the one candidate this integration "
        "is about"
    ),
    "PARLIAMENT_HOLDS_PROMOTION_AUTHORITY": (
        "the composed Parliament receipt reports itself as granting promotion, "
        "which a convening decision may never hold — promotion authority lives in "
        "governance.promotion and this gate refuses to launder a docket that "
        "claimed it"
    ),
    "STATISTICAL_CLEARANCE_INCONSISTENT": (
        "the validation advancement and the promotion Parliament did not compose "
        "the same statistical clearance this gate was handed, so the end-to-end "
        "path does not rest on one coherent Q05 admissibility receipt"
    ),
    "STATISTICAL_ADMISSIBILITY_REFUSED": (
        "the composed Q05 receipt did not admit the candidate to promotion "
        "review, so the earliest link of the experiment/replication path never "
        "cleared and nothing downstream can stand in for it"
    ),
    "VALIDATION_ADVANCEMENT_REFUSED": (
        "the composed V05 receipt did not advance the candidate's claim, so the "
        "validation cascade, out-of-distribution challenge or replication ceiling "
        "refused it and the path is not clear end to end"
    ),
    "PROMOTION_PARLIAMENT_WITHHELD": (
        "the composed P05 receipt withheld the promotion docket, so the multi-"
        "dimensional review the path terminates in was not convened before the "
        "promotion authority"
    ),
}

#: The gate's own decision vocabulary.  Neither token is a canonical schema enum
#: value (verified by the wire-literal discipline suite), so they are the gate's
#: to name: a coherent, fully-cleared path may be *integrated* into one end-to-end
#: record, and any other path is *refused* short of it.
INTEGRATE = "INTEGRATE"
REFUSE = "REFUSE"

#: The three sealed concerns this gate reconciles into one end-to-end record,
#: named so the receipt records which boundaries it composed.  Compound names,
#: none a wire value.
CONCERN_STATISTICS = "statistical_admissibility"
CONCERN_VALIDATION = "validation_advancement"
CONCERN_PARLIAMENT = "promotion_parliament_convening"

#: The receipt's stable name and id prefix.
GATE_NAME = "experiment-replication-integration"
GATE_ID_PREFIX = "ERI-"

#: The candidate-identity field every composed sub-receipt publishes.
CANDIDATE_FIELD = "candidate_id"
RECEIPT_HASH_FIELD = "receipt_hash"


class ExperimentReplicationRefused(ValueError):
    """The gate refuses the integration, or its evidence, with a documented code."""

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
        raise ExperimentReplicationRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ExperimentReplicationRefused(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def integration_grants_promotion() -> bool:
    """Always False: integrating a cleared path is never itself promotion authority.

    Kept as an explicit predicate rather than an omission so a caller reaching for
    "did the integration promote this?" finds a documented no instead of inventing
    a truthy check on the integrated decision.  Promotion authority lives in
    :mod:`governance.promotion`, which takes no score from this gate.
    """
    return False


def _resolve_subgate(
    receipt: object,
    *,
    gate_name: str,
    expected_candidate: str,
    label: str,
) -> dict[str, Any]:
    """Re-derive one composed sub-receipt as an authentic decision for this claim.

    The receipt is a sealed gate's own output, so it is trusted only once it
    proves it is the receipt it claims to be: it must name the sealed gate that
    mints it, re-derive its published hash byte for byte from the rest of its
    fields, and describe the one candidate this integration is about.  A receipt
    that fails any of these is refused before its verdict is composed, because a
    later concern cannot rest on a record the gate cannot trust.
    """
    record = _require_mapping(receipt, label)
    if str(record.get("gate")) != gate_name:
        _fail(
            "SUBGATE_IDENTITY_MISMATCH",
            f"the {label} was not produced by the {gate_name} gate",
            {"expected_gate": gate_name, "found_gate": record.get("gate")},
        )
    if hash_excluding(record, RECEIPT_HASH_FIELD) != record.get(RECEIPT_HASH_FIELD):
        _fail(
            "SUBGATE_RECEIPT_TAMPERED",
            f"the {label} does not re-derive its own hash",
            {"gate": gate_name, "gate_id": str(record.get("gate_id") or "")},
        )
    if str(record.get(CANDIDATE_FIELD)) != expected_candidate:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            f"the {label} describes a different candidate",
            {"expected": expected_candidate, "found": record.get(CANDIDATE_FIELD)},
        )
    return record


def _decide(
    *,
    admitted: bool,
    advanced: bool,
    convened: bool,
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message and its context.

    The order is the experiment/replication path's own.  The statistical
    clearance is the frame: a candidate whose adaptive selection was never
    corrected is refused first, because the validation advancement and the
    Parliament convening both presume it.  The validation advancement follows,
    because a claim the cascade or the OOD challenge refused has nothing coherent
    to convene.  The Parliament convening comes last, so a path that cleared every
    prior link but was withheld from promotion review is named for exactly that
    and nothing else.
    """
    if not admitted:
        return (
            REFUSE,
            "STATISTICAL_ADMISSIBILITY_REFUSED",
            "the composed statistical-admissibility receipt did not admit the candidate",
            {},
        )
    if not advanced:
        return (
            REFUSE,
            "VALIDATION_ADVANCEMENT_REFUSED",
            "the composed validation-advancement receipt did not advance the claim",
            {},
        )
    if not convened:
        return (
            REFUSE,
            "PROMOTION_PARLIAMENT_WITHHELD",
            "the composed promotion-Parliament receipt withheld the docket",
            {},
        )
    return (
        INTEGRATE,
        None,
        "the candidate cleared the statistical, validation and Parliament gates "
        "on one coherent statistical clearance and its end-to-end path is integrated",
        {},
    )


def derive_experiment_replication_integration(
    *,
    candidate_id: str,
    statistical_admissibility_receipt: Mapping[str, Any],
    validation_advancement_receipt: Mapping[str, Any],
    promotion_parliament_receipt: Mapping[str, Any],
    requesting_role: str,
    created_at: str,
) -> dict[str, Any]:
    """Derive the end-to-end integration decision and its immutable receipt.

    Input-integrity failures — a candidate-generating requesting role, a
    sub-receipt that names the wrong gate, that fails to re-derive its hash, that
    describes a different candidate, a Parliament receipt that claimed promotion
    authority, or two downstream gates resting on different statistical clearances
    — refuse immediately, because there is no well-formed end-to-end path to record
    over evidence the gate cannot trust.  Once every sub-receipt is verified and
    bound, the integration decision always produces a receipt, whether it
    integrates or refuses, so every decision over well-formed inputs is auditable
    and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    candidate = _require_text(candidate_id, CANDIDATE_FIELD)
    role = _require_text(requesting_role, "requesting_role")

    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive an integration decision",
            {"role": role},
        )

    statistical = _resolve_subgate(
        statistical_admissibility_receipt,
        gate_name=STATISTICAL_GATE_NAME,
        expected_candidate=candidate,
        label="statistical_admissibility_receipt",
    )
    validation = _resolve_subgate(
        validation_advancement_receipt,
        gate_name=VALIDATION_GATE_NAME,
        expected_candidate=candidate,
        label="validation_advancement_receipt",
    )
    parliament = _resolve_subgate(
        promotion_parliament_receipt,
        gate_name=PARLIAMENT_GATE_NAME,
        expected_candidate=candidate,
        label="promotion_parliament_receipt",
    )

    # The Parliament decides convening, never promotion.  The owning surface
    # documents this as an always-``False`` predicate, composed here rather than
    # restated; a receipt whose own record reports otherwise had acquired an
    # authority a convening verdict may not hold, and is refused before its
    # convening is composed.
    if parliament.get("grants_promotion") is not parliament_grants_promotion():
        _fail(
            "PARLIAMENT_HOLDS_PROMOTION_AUTHORITY",
            "the composed Parliament receipt reports itself as granting promotion",
            {"grants_promotion": parliament.get("grants_promotion")},
        )

    # The one statistical clearance the path must rest on: the Q05 receipt handed
    # to this gate is the clearance both downstream gates recorded composing, or
    # the end-to-end path is stitched from two different admissibility decisions.
    statistical_hash = str(statistical.get(RECEIPT_HASH_FIELD) or "")
    validation_reference = str(
        validation.get("statistical_admissibility_receipt_hash") or ""
    )
    parliament_reference = str(parliament.get("statistical_receipt_hash") or "")
    if (
        validation_reference != statistical_hash
        or parliament_reference != statistical_hash
    ):
        _fail(
            "STATISTICAL_CLEARANCE_INCONSISTENT",
            "the downstream gates did not compose the handed statistical clearance",
            {
                "statistical_receipt_hash": statistical_hash,
                "validation_reference": validation_reference,
                "parliament_reference": parliament_reference,
            },
        )

    admitted = (
        str(statistical.get("decision")) == STATISTICAL_ADMIT
        and statistical.get("admissible_for_promotion_review") is True
    )
    advanced = (
        str(validation.get("decision")) == VALIDATION_ADVANCE
        and validation.get("advanced") is True
    )
    convened = (
        str(parliament.get("decision")) == PARLIAMENT_CONVENE
        and parliament.get("convened_for_promotion_authority") is True
    )

    decision, finding_code, message, decision_context = _decide(
        admitted=admitted,
        advanced=advanced,
        convened=convened,
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "integrated": decision == INTEGRATE,
        "grants_promotion": integration_grants_promotion(),
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": candidate,
        "requesting_role": role,
        "concerns_gated": sorted(
            (CONCERN_STATISTICS, CONCERN_VALIDATION, CONCERN_PARLIAMENT)
        ),
        "statistical_admissibility_gate_id": str(statistical.get("gate_id") or ""),
        "statistical_admissibility_receipt_hash": statistical_hash,
        "statistical_admitted": admitted,
        "validation_advancement_gate_id": str(validation.get("gate_id") or ""),
        "validation_advancement_receipt_hash": str(
            validation.get(RECEIPT_HASH_FIELD) or ""
        ),
        "validation_advanced": advanced,
        "promotion_parliament_gate_id": str(parliament.get("gate_id") or ""),
        "promotion_parliament_receipt_hash": str(
            parliament.get(RECEIPT_HASH_FIELD) or ""
        ),
        "promotion_convened": convened,
        "parliament_grants_promotion": bool(parliament.get("grants_promotion")),
    }
    receipt["gate_id"] = (
        GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": candidate,
                    "created_at": stamp,
                    "decision": decision,
                    "statistical_admissibility_receipt_hash": statistical_hash,
                    "validation_advancement_receipt_hash": receipt[
                        "validation_advancement_receipt_hash"
                    ],
                    "promotion_parliament_receipt_hash": receipt[
                        "promotion_parliament_receipt_hash"
                    ],
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, RECEIPT_HASH_FIELD)
    return receipt


def evaluate_experiment_replication_integration(
    *,
    candidate_id: str,
    statistical_admissibility_receipt: Mapping[str, Any],
    validation_advancement_receipt: Mapping[str, Any],
    promotion_parliament_receipt: Mapping[str, Any],
    requesting_role: str,
    created_at: str,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on integrate, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the end-to-end path was stopped short of an integrated pass.
    """
    receipt = derive_experiment_replication_integration(
        candidate_id=candidate_id,
        statistical_admissibility_receipt=statistical_admissibility_receipt,
        validation_advancement_receipt=validation_advancement_receipt,
        promotion_parliament_receipt=promotion_parliament_receipt,
        requesting_role=requesting_role,
        created_at=created_at,
    )
    if receipt["decision"] != INTEGRATE:
        raise ExperimentReplicationRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


def integration_hash_matches(receipt: Mapping[str, Any]) -> bool:
    """True when an integration receipt re-derives its own hash from its content."""
    sealed = _require_mapping(receipt, "integration receipt")
    return hash_excluding(sealed, RECEIPT_HASH_FIELD) == sealed.get(RECEIPT_HASH_FIELD)


__all__ = [
    "CONCERN_PARLIAMENT",
    "CONCERN_STATISTICS",
    "CONCERN_VALIDATION",
    "ExperimentReplicationRefused",
    "FINDING_CODES",
    "GATE_ID_PREFIX",
    "GATE_NAME",
    "INTEGRATE",
    "REFUSE",
    "derive_experiment_replication_integration",
    "evaluate_experiment_replication_integration",
    "integration_grants_promotion",
    "integration_hash_matches",
]
