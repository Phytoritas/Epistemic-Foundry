"""The validation-cascade / OOD-challenge / replication-ceiling advancement gate.

A candidate reaches this gate having already been screened by cheaper stages.
What this gate decides — and refuses to decide more than — is whether that
candidate's *claim may advance*: whether the multi-stage validation cascade
actually reached a passing verdict, whether the candidate withstood an
out-of-distribution challenge, whether its adaptive selection was statistically
admitted, and whether it carries enough independent replication to reach the
promotion ceiling the configured level requires.  It never promotes anything and
never orders a search: promotion authority lives in ``governance.promotion`` and
takes no score, and this gate holds none of it.

It is an *integration* gate.  Each of its four concerns is owned by a sealed
surface that this module composes and whose vocabulary it restates nowhere
(EF4-I22):

* **The cascade must actually pass.**  The stage results are reduced by
  ``validation_bay.cascade.aggregate_cascade_status``, which is deliberately
  pessimistic — an absent or incomplete stage can never read as success — and its
  passing token is read from the ``promotion-decision`` schema's own hard-gate
  vocabulary rather than written here.  A cascade that aggregates to anything but
  that token refuses advancement, and a stage that ran out of contract order is
  refused by the cascade owner with its own ``CascadeViolation``.

* **The out-of-distribution challenge must be survived.**  A claim that was never
  challenged out of distribution has demonstrated no robustness to advance on, so
  advancement is refused when no OOD challenge ran; a claim the OOD challenge
  refuted or scope-restricted is refused; and an OOD match that resolved nothing
  is never laundered into survival.  The challenge class is read from the
  ``challenge-genome`` schema and the surviving, adverse and unresolved outcome
  partitions are imported from the Red Queen Lab that declares them.

* **The statistical admissibility must have been granted.**  The gate does not
  re-run the multi-objective, hidden-evaluation and selective-inference checks —
  it composes Q05's receipt, verifies that the receipt re-derives its own hash,
  that it names this candidate, that it was produced by the statistical
  admissibility gate, and that its decision admitted the candidate to review.  A
  candidate Q05 did not admit does not advance here.

* **The replication ceiling must reach the configured level.**  The highest level
  the available replication evidence supports is derived by
  ``validation_bay.replication.promotion_ceiling_after_search``; when that ceiling
  ranks below the configured level on the shared promotion ladder, advancement is
  refused, so a claim that lacks independent preregistered replication at the
  configured level receives an explicit refusal rather than a silent pass.

No candidate, model, prompt, backend or hook may drive the decision: a
candidate-generating requesting role is refused with the set the verifier
firewall declares.  Every decision, advance or refuse, resolves to one immutable
receipt that is a pure function of its inputs — there is no clock and no random
draw, the caller supplies ``created_at``, and the gate id and receipt hash
re-derive byte for byte from the receipt's own published fields.  No input is
ever mutated.
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
from ...domain.hashing import canonical_json, hash_excluding, sha256_hex
from ...domain.vocabularies import PROMOTION_LADDER, promotion_rank
from ...evaluation.v4_q05 import ADMIT as STATISTICAL_ADMIT
from ...evaluation.v4_q05 import GATE_NAME as STATISTICAL_GATE_NAME
from ...red_queen_lab.challenges import (
    partition_adverse_outcomes,
    survived_challenges,
    unresolved_matches,
)
from ...validation_bay.cascade import (
    CascadeViolation,
    aggregate_cascade_status,
)
from ...validation_bay.replication import promotion_ceiling_after_search
from ...verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record an advancement derived from something it never validated"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the advancement decision, and a "
        "role that proposes candidates may never acquire evaluator, holdout or "
        "promotion authority over its own claim"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the cascade results, the challenge record, the admissibility receipt or "
        "the replication plan do not all describe the one candidate this decision "
        "is about"
    ),
    "ADMISSIBILITY_RECEIPT_UNVERIFIED": (
        "the statistical-admissibility receipt was not produced by the "
        "admissibility gate or does not re-derive its own hash, so its verdict "
        "cannot be trusted as the statistical clearance this gate composes"
    ),
    "ADMISSIBILITY_NOT_ADMITTED": (
        "the statistical-admissibility gate did not admit the candidate to "
        "promotion review, so its adaptive selection is not statistically cleared "
        "and no downstream survival can substitute for that clearance"
    ),
    "CASCADE_NOT_PASSED": (
        "the validation cascade did not aggregate to a passing verdict, so a "
        "stage failed, was skipped or never ran, and a later concern cannot "
        "overturn an unfinished or failed cascade"
    ),
    "OOD_CHALLENGE_ABSENT": (
        "no out-of-distribution challenge ran against the candidate, so the claim "
        "has demonstrated no robustness beyond its training distribution to "
        "advance on"
    ),
    "OOD_CHALLENGE_REFUTED": (
        "an out-of-distribution challenge refuted or scope-restricted the "
        "candidate, so the claim fails out of distribution and must not advance"
    ),
    "OOD_CHALLENGE_UNRESOLVED": (
        "an out-of-distribution challenge against the candidate resolved nothing, "
        "and a crashed or inconclusive adversary is not a survival the claim can "
        "advance on"
    ),
    "REPLICATION_CEILING_BELOW_REQUIRED": (
        "the available replication evidence caps the promotion ceiling below the "
        "configured level, so the claim lacks the independent preregistered "
        "replication that level requires and cannot advance to it"
    ),
}

#: Canonical schema names this gate reads a vocabulary or a contract out of.
#: These are schema *names*, not wire enum values, and each is verified at use.
CHALLENGE_GENOME_KIND = "challenge-genome"
CHALLENGE_RESULT_KIND = "challenge-result"
STAGE_RESULT_KIND = "stage-evaluation-result"
CASCADE_PLAN_KIND = "validation-cascade-plan"
REPLICATION_PLAN_KIND = "replication-plan"
PROMOTION_DECISION_KIND = "promotion-decision"

#: Property names the gate reads back.  These are schema *field* names, not enum
#: values, so they are named here and verified against the schema at use.
CHALLENGE_CLASS_FIELD = "challenge_class"
HARD_GATE_STATUS_FIELD = "hard_gate_status"
CANDIDATE_FIELD = "candidate_id"
TARGET_CANDIDATE_FIELD = "target_candidate_id"
CHALLENGE_GENOME_ID_FIELD = "challenge_genome_id"
STAGE_CANDIDATE_FIELD = "candidate_id"
PLAN_ID_FIELD = "cascade_plan_id"

#: The gate's own decision vocabulary.  Neither token is a canonical schema enum
#: value (verified by the wire-literal discipline suite), so they are the gate's
#: to name: a cleared candidate may be *advanced* toward promotion review, and a
#: refused one is stopped short of it.
ADVANCE = "ADVANCE"
REFUSE = "REFUSE"

#: The receipt's stable name and id prefix.
GATE_NAME = "validation-cascade-advancement"
GATE_ID_PREFIX = "VCA-"


class ValidationCascadeRefused(ValueError):
    """The gate refuses advancement, or its evidence, with a documented code."""

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
        raise ValidationCascadeRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ValidationCascadeRefused(code, message, context)


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


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """Every canonical enum token the gate reasons about, read from the schema.

    Holding these as string literals would be a second copy that drifts from the
    contract (EF4-I22).  The out-of-distribution challenge class is the one
    ``challenge-genome`` class whose token names a distribution shift, discovered
    by that description rather than pinned to a spelling, so a schema that renamed
    it keeps working and a schema that declared two or none fails closed here.
    The passing cascade status is the ``promotion-decision`` schema's own first
    hard-gate rung — the exact vocabulary the cascade owner documents its verdict
    in — so a reshape that empties or reorders the ladder fails closed rather than
    silently selecting the wrong token.
    """
    genome = default_registry().document(CHALLENGE_GENOME_KIND)
    classes = genome.get("properties", {}).get(CHALLENGE_CLASS_FIELD, {}).get("enum")
    if not isinstance(classes, list) or not classes:
        _fail(
            "INPUT_INVALID",
            "the challenge-genome schema declares no challenge_class vocabulary",
            {"schema": CHALLENGE_GENOME_KIND},
        )
    distribution_shift = sorted(
        token
        for token in classes  # type: ignore[union-attr]
        if isinstance(token, str) and "ood" in token.lower()
    )
    if len(distribution_shift) != 1:
        _fail(
            "INPUT_INVALID",
            "the challenge-genome schema does not declare exactly one "
            "out-of-distribution challenge class",
            {"matched": distribution_shift},
        )
    decision = default_registry().document(PROMOTION_DECISION_KIND)
    gate_status = (
        decision.get("properties", {}).get(HARD_GATE_STATUS_FIELD, {}).get("enum")
    )
    if not isinstance(gate_status, list) or not gate_status:
        _fail(
            "INPUT_INVALID",
            "the promotion-decision schema declares no hard-gate status vocabulary",
            {"schema": PROMOTION_DECISION_KIND},
        )
    return {
        "ood_challenge_class": str(distribution_shift[0]),
        "cascade_pass": str(gate_status[0]),
    }


def ood_challenge_class_token() -> str:
    """The canonical out-of-distribution challenge class, read from the schema."""
    return _vocab()["ood_challenge_class"]


def cascade_pass_status() -> str:
    """The canonical passing cascade hard-gate status, read from the schema."""
    return _vocab()["cascade_pass"]


def _validate(kind: str, document: Mapping[str, Any], label: str) -> dict[str, Any]:
    """Validate one composed artifact against its canonical schema."""
    record = _require_mapping(document, label)
    try:
        validate_artifact(kind, record)
    except ContractViolation as error:
        _fail(
            "INPUT_INVALID",
            f"{label} does not satisfy the canonical {kind} schema",
            {"schema_errors": list(error.errors)},
        )
    return record


def _resolve_cascade_status(
    plan: Mapping[str, Any],
    stage_results: Sequence[Mapping[str, Any]],
    *,
    candidate_id: str,
) -> str:
    """Validate and aggregate the cascade, bound to one plan and one candidate.

    The aggregation itself is the cascade owner's: a stage that ran out of
    contract order travels out as its own ``CascadeViolation`` rather than being
    paraphrased under a V05 code.  What this adds is the binding the aggregation
    does not check — every stage result must name this candidate and this plan,
    so a coherent-looking cascade assembled from another candidate's stages is
    refused before its verdict is trusted.
    """
    plan_record = _validate(CASCADE_PLAN_KIND, plan, "cascade_plan")
    plan_id = _require_text(plan_record.get(PLAN_ID_FIELD), PLAN_ID_FIELD)
    validated: list[dict[str, Any]] = []
    for position, result in enumerate(stage_results):
        record = _validate(STAGE_RESULT_KIND, result, f"stage_results[{position}]")
        if str(record.get(STAGE_CANDIDATE_FIELD)) != candidate_id:
            _fail(
                "CANDIDATE_IDENTITY_MISMATCH",
                "a stage result describes a different candidate",
                {
                    "expected": candidate_id,
                    "found": record.get(STAGE_CANDIDATE_FIELD),
                },
            )
        if str(record.get(PLAN_ID_FIELD)) != plan_id:
            _fail(
                "INPUT_INVALID",
                "a stage result belongs to a different cascade plan",
                {"expected": plan_id, "found": record.get(PLAN_ID_FIELD)},
            )
        validated.append(record)
    return aggregate_cascade_status(plan_record, validated)


def _resolve_ood(
    challenge_genomes: Sequence[Mapping[str, Any]],
    challenge_results: Sequence[Mapping[str, Any]],
    *,
    candidate_id: str,
) -> tuple[str | None, list[str], bool]:
    """Reduce the OOD challenge record to a refusal code, its ids and survival.

    Only the challenges the ``challenge-genome`` schema types as a distribution
    shift are considered, and only their matches against this candidate.  A match
    counts as survival only when the Red Queen Lab's own surviving-outcome
    partition contains it — an adverse or unresolved outcome never does — so the
    survival read here is exactly the one that surface would report.
    """
    ood_token = ood_challenge_class_token()
    ood_genome_ids: set[str] = set()
    for position, genome in enumerate(challenge_genomes):
        record = _validate(
            CHALLENGE_GENOME_KIND, genome, f"challenge_genomes[{position}]"
        )
        if str(record.get(CHALLENGE_CLASS_FIELD)) == ood_token:
            ood_genome_ids.add(
                _require_text(
                    record.get(CHALLENGE_GENOME_ID_FIELD), CHALLENGE_GENOME_ID_FIELD
                )
            )

    ood_results: list[dict[str, Any]] = []
    for position, result in enumerate(challenge_results):
        record = _validate(
            CHALLENGE_RESULT_KIND, result, f"challenge_results[{position}]"
        )
        if (
            str(record.get(CHALLENGE_GENOME_ID_FIELD)) in ood_genome_ids
            and str(record.get(TARGET_CANDIDATE_FIELD)) == candidate_id
        ):
            ood_results.append(record)

    ids = sorted(str(result["challenge_result_id"]) for result in ood_results)
    if not ood_results:
        return "OOD_CHALLENGE_ABSENT", ids, False
    # The outcome partitions come from the Red Queen Lab that declares them, so
    # no outcome token is read or named here (EF4-I22): a refutation or scope
    # restriction against this candidate is an adverse partition, an inconclusive
    # or errored match is an unresolved one, and survival is the surface's own
    # all-matches-won predicate rather than a token comparison restated here.
    adverse = partition_adverse_outcomes(ood_results)
    if (
        candidate_id in adverse["refuted"]
        or candidate_id in adverse["scope_restricted"]
    ):
        return "OOD_CHALLENGE_REFUTED", ids, False
    if unresolved_matches(ood_results):
        return "OOD_CHALLENGE_UNRESOLVED", ids, False
    survived = survived_challenges(candidate_id, ood_results)
    return (None if survived else "OOD_CHALLENGE_UNRESOLVED"), ids, survived


def _verify_admissibility(
    admissibility_receipt: Mapping[str, Any], *, candidate_id: str
) -> dict[str, Any]:
    """Verify the composed Q05 receipt as an authentic clearance for this claim.

    The receipt is Q05's own output rather than a schema artifact, so it is
    trusted only once it proves it is the receipt it claims to be: produced by the
    statistical admissibility gate, re-deriving its own hash, and naming this
    candidate.  Whether that receipt *admitted* the candidate is a separate,
    substantive question decided in the advancement phase, not here.
    """
    record = _require_mapping(admissibility_receipt, "admissibility_receipt")
    if str(record.get("gate")) != STATISTICAL_GATE_NAME:
        _fail(
            "ADMISSIBILITY_RECEIPT_UNVERIFIED",
            "the receipt was not produced by the statistical admissibility gate",
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


def _resolve_replication(
    *,
    adaptive_search_used: bool,
    replication_plan: Mapping[str, Any] | None,
    candidate_id: str,
) -> tuple[str, str | None]:
    """The ceiling the replication evidence supports, and the plan's id if any.

    The ceiling is the replication owner's: it returns an explicit lower bound
    rather than a refusal a caller might route around.  When a plan is supplied it
    is validated and bound to this candidate first, so a qualifying plan for
    another candidate cannot lift this claim's ceiling.
    """
    plan_id: str | None = None
    plan_record: dict[str, Any] | None = None
    if replication_plan is not None:
        plan_record = _validate(
            REPLICATION_PLAN_KIND, replication_plan, "replication_plan"
        )
        if str(plan_record.get(CANDIDATE_FIELD)) != candidate_id:
            _fail(
                "CANDIDATE_IDENTITY_MISMATCH",
                "the replication plan describes a different candidate",
                {"expected": candidate_id, "found": plan_record.get(CANDIDATE_FIELD)},
            )
        plan_id = str(plan_record["replication_plan_id"])
    ceiling = promotion_ceiling_after_search(
        adaptive_search_used=adaptive_search_used,
        replication_plan=plan_record,
    )
    return ceiling, plan_id


def _decide(
    *,
    cascade_status: str,
    admitted: bool,
    ood_code: str | None,
    ceiling: str,
    required_promotion_level: str,
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message and its context.

    The order is deliberate.  The cascade is the frame: a claim whose cascade
    never passed is refused first, because every later concern presumes a passed
    cascade.  The statistical clearance comes next, because an uncorrected
    adaptive selection is meaningless however robust it looks.  The OOD challenge
    follows, and the replication ceiling last, so a claim that clears every prior
    concern but lacks replication at the configured level is named for exactly
    that and nothing else.
    """
    if cascade_status != cascade_pass_status():
        return (
            REFUSE,
            "CASCADE_NOT_PASSED",
            "the validation cascade did not aggregate to a passing verdict",
            {"cascade_status": cascade_status},
        )
    if not admitted:
        return (
            REFUSE,
            "ADMISSIBILITY_NOT_ADMITTED",
            "the statistical admissibility gate did not admit the candidate",
            {},
        )
    if ood_code is not None:
        return (
            REFUSE,
            ood_code,
            FINDING_CODES[ood_code],
            {},
        )
    if promotion_rank(ceiling) < promotion_rank(required_promotion_level):
        return (
            REFUSE,
            "REPLICATION_CEILING_BELOW_REQUIRED",
            "the replication evidence caps the ceiling below the configured level",
            {"ceiling": ceiling, "required_level": required_promotion_level},
        )
    return (
        ADVANCE,
        None,
        "the claim cleared the cascade, OOD challenge, admissibility and "
        "replication ceiling and may advance toward promotion review",
        {},
    )


def derive_validation_advancement(
    *,
    candidate_id: str,
    cascade_plan: Mapping[str, Any],
    stage_results: Sequence[Mapping[str, Any]],
    challenge_genomes: Sequence[Mapping[str, Any]],
    challenge_results: Sequence[Mapping[str, Any]],
    admissibility_receipt: Mapping[str, Any],
    adaptive_search_used: bool,
    required_promotion_level: str,
    requesting_role: str,
    replication_plan: Mapping[str, Any] | None = None,
    created_at: str,
) -> dict[str, Any]:
    """Derive the advancement decision and its immutable receipt.

    Input-integrity failures — a candidate-generating requesting role, an
    artifact describing a different candidate, an unverifiable admissibility
    receipt, a malformed cascade, challenge or replication artifact — refuse
    immediately, because there is no well-formed decision to record over evidence
    the gate cannot trust.  Once every input is validated and bound, the
    advancement decision always produces a receipt, whether it advances or
    refuses, so every decision over well-formed inputs is auditable and
    re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    candidate = _require_text(candidate_id, CANDIDATE_FIELD)
    role = _require_text(requesting_role, "requesting_role")
    required_level = _require_text(required_promotion_level, "required_promotion_level")
    if required_level not in PROMOTION_LADDER:
        _fail(
            "INPUT_INVALID",
            "required_promotion_level is not a canonical promotion level",
            {"required_promotion_level": required_level},
        )

    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive an advancement decision",
            {"role": role},
        )

    plan_record = _require_mapping(cascade_plan, "cascade_plan")
    stages = _require_sequence(stage_results, "stage_results")
    genomes = _require_sequence(challenge_genomes, "challenge_genomes")
    results = _require_sequence(challenge_results, "challenge_results")

    admissibility = _verify_admissibility(admissibility_receipt, candidate_id=candidate)
    admitted = (
        str(admissibility.get("decision")) == STATISTICAL_ADMIT
        and admissibility.get("admissible_for_promotion_review") is True
    )

    cascade_status = _resolve_cascade_status(
        plan_record, stages, candidate_id=candidate
    )
    ood_code, ood_result_ids, ood_survived = _resolve_ood(
        genomes, results, candidate_id=candidate
    )
    ceiling, replication_plan_id = _resolve_replication(
        adaptive_search_used=bool(adaptive_search_used),
        replication_plan=replication_plan,
        candidate_id=candidate,
    )

    decision, finding_code, message, decision_context = _decide(
        cascade_status=cascade_status,
        admitted=admitted,
        ood_code=ood_code,
        ceiling=ceiling,
        required_promotion_level=required_level,
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "advanced": decision == ADVANCE,
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": candidate,
        "requesting_role": role,
        "cascade_plan_id": str(plan_record.get(PLAN_ID_FIELD) or ""),
        "cascade_status": cascade_status,
        "stage_result_count": len(stages),
        "ood_challenge_class": ood_challenge_class_token(),
        "ood_challenge_result_ids": ood_result_ids,
        "ood_survived": ood_survived,
        "statistical_admissibility_gate_id": str(admissibility.get("gate_id") or ""),
        "statistical_admissibility_receipt_hash": str(
            admissibility.get("receipt_hash") or ""
        ),
        "statistical_admitted": admitted,
        "adaptive_search_used": bool(adaptive_search_used),
        "required_promotion_level": required_level,
        "replication_ceiling": ceiling,
        "replication_plan_id": replication_plan_id,
    }
    receipt["gate_id"] = (
        GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": candidate,
                    "cascade_plan_id": receipt["cascade_plan_id"],
                    "created_at": stamp,
                    "decision": decision,
                    "statistical_admissibility_receipt_hash": receipt[
                        "statistical_admissibility_receipt_hash"
                    ],
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_validation_advancement(
    *,
    candidate_id: str,
    cascade_plan: Mapping[str, Any],
    stage_results: Sequence[Mapping[str, Any]],
    challenge_genomes: Sequence[Mapping[str, Any]],
    challenge_results: Sequence[Mapping[str, Any]],
    admissibility_receipt: Mapping[str, Any],
    adaptive_search_used: bool,
    required_promotion_level: str,
    requesting_role: str,
    replication_plan: Mapping[str, Any] | None = None,
    created_at: str,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on advance, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the claim was stopped short of promotion review.
    """
    receipt = derive_validation_advancement(
        candidate_id=candidate_id,
        cascade_plan=cascade_plan,
        stage_results=stage_results,
        challenge_genomes=challenge_genomes,
        challenge_results=challenge_results,
        admissibility_receipt=admissibility_receipt,
        adaptive_search_used=adaptive_search_used,
        required_promotion_level=required_promotion_level,
        requesting_role=requesting_role,
        replication_plan=replication_plan,
        created_at=created_at,
    )
    if receipt["decision"] != ADVANCE:
        raise ValidationCascadeRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


def advancement_hash_matches(receipt: Mapping[str, Any]) -> bool:
    """True when an advancement receipt re-derives its own hash from its content."""
    sealed = _require_mapping(receipt, "advancement receipt")
    return hash_excluding(dict(sealed), "receipt_hash") == sealed.get("receipt_hash")


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a refusal, and ``CascadeViolation``
# so a caller can catch the cascade owner's own out-of-order refusal by type.
__all__ = [
    "ADVANCE",
    "CascadeViolation",
    "FINDING_CODES",
    "GATE_NAME",
    "REFUSE",
    "SchemaNotFound",
    "ValidationCascadeRefused",
    "advancement_hash_matches",
    "cascade_pass_status",
    "derive_validation_advancement",
    "evaluate_validation_advancement",
    "ood_challenge_class_token",
]
