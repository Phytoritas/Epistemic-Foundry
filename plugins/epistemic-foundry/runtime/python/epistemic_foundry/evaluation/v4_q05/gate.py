"""The multi-objective, hidden-evaluation and selective-inference gate.

A candidate reaches this gate *because* an adaptive evolutionary search chose it
out of many related candidates.  That very selection is the problem the gate
exists to close.  Among many noisy estimates the largest is expected to overstate
the truth (the winner's curse), repeated public or hidden feedback can leak test
information into the search, and a single high score says nothing about whether
the candidate cleared the separate quality dimensions it is judged on.  So the
gate decides one thing and refuses to decide more: is an adaptively-selected
candidate *admissible to be forwarded to promotion review* — statistically
accounted-for, leakage-free, and passing on a real fitness vector rather than a
scalar?  It never promotes anything.  Promotion authority lives in
``governance.promotion`` and takes no score; this gate holds none of it.

It is an *integration* gate: it composes the already-sealed surfaces that each
own one concern and restates none of their vocabularies (EF4-I22).

* **Multi-objective fitness stays a vector.**  The candidate's quality is read
  as a ``fitness-vector`` — fifteen separate dimensions and an explicit hard-gate
  status — through the ``evaluation.fitness`` surface that owns it.  A scalar, or
  a vector missing its dimensions, is refused: a single number is exactly what
  must never stand in for the gates.  ``fitness.may_promote_on_score`` is
  consulted and required to remain ``False``, so a score can order a search but
  never authorize a promotion.

* **Hidden evaluation stays hidden until permitted.**  The evaluator bundle and
  its holdout manifest are handed to the sealed ``VerifierFirewall``, which
  refuses a candidate-readable or run-mutable evaluator and a holdout any
  candidate, model, prompt or backend can reach.  The gate never copies the
  hidden score into its receipt; disclosure requires an explicit unblinding
  approval *and* holdout-read authority, and without both the hidden result stays
  sealed.  Evaluator feedback is treated as a leakage channel: any leaked id that
  touches a bound holdout partition invalidates the comparison — it is never
  laundered into a score adjustment.

* **Adaptive best-of-many selection must be corrected.**  The search must arrive
  with the complete adaptive-search statistical record the specification requires
  (sequential ledger, multiplicity adjustment, selective-inference report, hidden
  exposure log, candidate lineage and replication result), checked through the
  ``statistics.search_record`` surface that owns it.  An uncorrected adaptive
  selection — a missing or partial record — is refused.  The record's own
  selective-inference verdict must match the report it claims to summarize, and a
  candidate clears only when that verdict permits it.

Every decision, allow or refuse, resolves to one immutable receipt that is a pure
function of its inputs: there is no clock and no random draw, the caller supplies
``created_at``, and the gate id and receipt hash re-derive byte for byte from the
receipt's own published fields.  No input is ever mutated.
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
from ...domain.hashing import (
    canonical_json,
    hash_excluding,
    sha256_hex,
    sha256_of_payload,
)
from ...evaluation.fitness import may_promote_on_score
from ...statistics.search_record import (
    missing_statistical_artifacts,
    search_permits_promotion,
)
from ...statistics.selective import (
    build_selective_inference_report,
    permits_promotion_without_replication,
)
from ...verifier_firewall.firewall import (
    CANDIDATE_GENERATING_ROLES,
    EvaluatorDrift,
    FirewallRefusal,
    HoldoutAccessDenied,
    VerifierFirewall,
)

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership
#: and every finding code below is exercised by the negative suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "FITNESS_NOT_VECTOR": (
        "the candidate's fitness is not a multi-objective vector but a scalar or "
        "a vector with no dimensions, and a single number is exactly what must "
        "never stand in for the separate quality gates"
    ),
    "FITNESS_VECTOR_CONTRACT_VIOLATED": (
        "the fitness vector does not satisfy the canonical fitness-vector schema, "
        "so the dimensions and hard-gate status the gate reads are untrustworthy"
    ),
    "FITNESS_HARD_GATE_NOT_PASSED": (
        "the fitness vector's own hard gate did not pass, so the candidate is not "
        "admissible however high its dimensions score"
    ),
    "SCORE_GRANTS_PROMOTION": (
        "the fitness surface reported that a score may promote, which would let a "
        "scalar acquire the promotion authority this gate and governance withhold"
    ),
    "CANDIDATE_IDENTITY_MISMATCH": (
        "the fitness vector, the statistical record and the selective-inference "
        "report do not all describe the one candidate this decision is about"
    ),
    "HIDDEN_EVALUATION_FIREWALL_BROKEN": (
        "the evaluator bundle or its holdout is candidate-readable, run-mutable, "
        "self-inconsistent or drifted, so the hidden evaluation is not sealed"
    ),
    "HIDDEN_RESULT_DISCLOSURE_UNAPPROVED": (
        "disclosure of the hidden-evaluation result was requested without an "
        "unblinding approval or without holdout-read authority, so the result "
        "must stay hidden"
    ),
    "CANDIDATE_ROLE_HOLDS_AUTHORITY": (
        "a candidate-generating role is driving the admissibility decision, and a "
        "role that proposes candidates may never acquire evaluator, holdout or "
        "promotion authority over them"
    ),
    "EVALUATOR_FEEDBACK_LEAKED": (
        "a leaked id touches a bound holdout partition, so the affected "
        "comparison is INVALIDATED and must not be laundered into a score"
    ),
    "SEARCH_RECORD_CONTRACT_VIOLATED": (
        "the adaptive-search statistical record does not re-derive its own hash, "
        "so its statistical accounting has been altered and is untrustworthy"
    ),
    "UNCORRECTED_ADAPTIVE_SELECTION": (
        "the adaptive best-of-many search arrives without the complete required "
        "statistical record, so the winner's estimate is uncorrected and the "
        "selection is refused"
    ),
    "SELECTIVE_ACCOUNTING_MISBOUND": (
        "the selective-inference report is not internally hash/verdict consistent, "
        "or the statistical record's verdict does not match the report it claims "
        "to summarize, so the selective accounting is untrustworthy"
    ),
    "SELECTION_NOT_STATISTICALLY_CLEARED": (
        "the selective-inference verdict does not permit advancement — the "
        "winner's-curse risk demands replication or a lower ceiling first"
    ),
}

#: Canonical schema this gate reads a vocabulary out of rather than restating.
FITNESS_KIND = "fitness-vector"
SELECTIVE_REPORT_KIND = "selective-inference-report"

#: Fitness-vector fields the gate reads.  These are property names, not wire
#: values, so they are named here and verified against the schema at use.
GATE_STATUS_FIELD = "hard_gate_status"
GATE_FAILURES_FIELD = "hard_gate_failures"
DIMENSIONS_FIELD = "dimensions"
FITNESS_ID_FIELD = "fitness_vector_id"
CANDIDATE_FIELD = "candidate_id"

#: Selective-inference / statistical-record fields the gate reads back.
RECOMMENDATION_FIELD = "promotion_recommendation"
RISK_FIELD = "winner_curse_risk"
RECORD_HASH_FIELD = "record_hash"
REPORT_HASH_FIELD = "report_hash"

#: The gate's own decision vocabulary.  Neither token is a canonical schema enum
#: value (verified by the wire-literal discipline suite), so they are the gate's
#: to name: an admissible candidate may be *forwarded to review*, nothing more.
ADMIT = "ADMIT"
REFUSE = "REFUSE"

#: The receipt's stable name and id prefix.
GATE_NAME = "selective-inference-admissibility"
GATE_ID_PREFIX = "SAG-"


class SelectiveAdmissibilityRefused(ValueError):
    """The gate refuses admissibility, or its evidence, with a documented code."""

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
        raise SelectiveAdmissibilityRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise SelectiveAdmissibilityRefused(code, message, context)


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
    contract (EF4-I22), and the ``evaluation.fitness`` surface does not export the
    hard-gate vocabulary as importable constants, so the passing status is read
    out of the canonical fitness-vector schema that declares it.  The passing
    status is the schema's own first declared rung of the status ladder; a reshape
    that empties or reorders the ladder fails closed here rather than silently
    selecting the wrong token.
    """
    document = default_registry().document(FITNESS_KIND)
    status = document.get("properties", {}).get(GATE_STATUS_FIELD, {}).get("enum")
    if not isinstance(status, list) or not status:
        _fail(
            "FITNESS_VECTOR_CONTRACT_VIOLATED",
            "the fitness-vector schema declares no hard-gate status vocabulary",
            {"schema": FITNESS_KIND},
        )
    return {"gate_pass": str(status[0])}


def hard_gate_pass_token() -> str:
    """The canonical passing hard-gate status, read from the fitness schema."""
    return _vocab()["gate_pass"]


@lru_cache(maxsize=1)
def _selective_verdict_pairs() -> frozenset[tuple[str, str]]:
    """Risk/recommendation pairs emitted by the owning deterministic builder.

    Q05 must not copy the canonical enum vocabulary or independently restate the
    builder's branch table.  These witnesses execute every current branch of
    ``build_selective_inference_report``, including both outcomes of the one branch
    that depends on replication.  The report does not persist the inputs needed to
    decide which risk applies, but once a risk is declared its recommendation must
    be one of the pairs the owner can actually emit.
    """
    witnesses = (
        (1, 1),
        (1, 0),
        (100, 0),
        (100, 1),
        (0, 0),
    )
    pairs: set[tuple[str, str]] = set()
    for candidates_considered, replication_count in witnesses:
        report = build_selective_inference_report(
            candidate_id=GATE_NAME,
            selection_mechanism=GATE_NAME,
            selection_events=[GATE_NAME],
            naive_estimate=1.0,
            bias_corrected_estimate=0.5,
            correction_method=GATE_NAME,
            uncertainty_interval=[0.0, 1.0],
            candidates_considered=candidates_considered,
            replication_count=replication_count,
            report_id=GATE_ID_PREFIX,
        )
        pairs.add((str(report[RISK_FIELD]), str(report[RECOMMENDATION_FIELD])))
    return frozenset(pairs)


def _resolve_selective_report(value: object) -> dict[str, Any]:
    """Validate one canonical, self-consistent selective-inference report.

    Schema validity is the first substantive check.  The self-hash then proves
    that the presented bytes have not merely drifted since they were sealed, and
    the owner-derived pair table prevents a recommendation its builder could not
    emit for the declared risk.  Neither check proves which hidden selection
    inputs originally produced that risk; that requires provenance the current
    report contract does not carry.
    """
    document = _require_mapping(value, "selective_report")
    try:
        validate_artifact(SELECTIVE_REPORT_KIND, document)
    except ContractViolation as error:
        _fail(
            "INPUT_INVALID",
            "the selective-inference report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )

    stored_hash = document.get(REPORT_HASH_FIELD)
    recomputed_hash = hash_excluding(document, REPORT_HASH_FIELD)
    if stored_hash != recomputed_hash:
        _fail(
            "SELECTIVE_ACCOUNTING_MISBOUND",
            "the selective-inference report does not re-derive its own hash",
            {"recorded": stored_hash, "recomputed": recomputed_hash},
        )

    verdict = (
        str(document.get(RISK_FIELD)),
        str(document.get(RECOMMENDATION_FIELD)),
    )
    allowed_pairs = _selective_verdict_pairs()
    if verdict not in allowed_pairs:
        _fail(
            "SELECTIVE_ACCOUNTING_MISBOUND",
            "the recommendation is not one the owning builder can emit for the "
            "declared winner's-curse risk",
            {
                RISK_FIELD: verdict[0],
                RECOMMENDATION_FIELD: verdict[1],
                "allowed_recommendations": sorted(
                    recommendation
                    for risk, recommendation in allowed_pairs
                    if risk == verdict[0]
                ),
            },
        )
    return document


@dataclass(frozen=True)
class _Fitness:
    """One validated multi-objective fitness vector."""

    fitness_vector_id: str
    candidate_id: str
    hard_gate_status: str
    hard_gate_passed: bool
    document: dict[str, Any]


def _resolve_fitness(value: object, *, expected_candidate_id: str) -> _Fitness:
    """Validate the fitness vector and confirm it is a vector, not a scalar."""
    if not isinstance(value, Mapping):
        _fail(
            "FITNESS_NOT_VECTOR",
            "the candidate's fitness is not a vector but a scalar or non-mapping",
            {"type": type(value).__name__},
        )
    document = dict(value)  # type: ignore[arg-type]
    dimensions = document.get(DIMENSIONS_FIELD)
    if not isinstance(dimensions, Mapping) or not dimensions:
        _fail(
            "FITNESS_NOT_VECTOR",
            "the fitness carries no separate dimensions, so it is a scalar in "
            "a vector's name",
            {DIMENSIONS_FIELD: dimensions},
        )
    try:
        validate_artifact(FITNESS_KIND, document)
    except ContractViolation as error:
        _fail(
            "FITNESS_VECTOR_CONTRACT_VIOLATED",
            "the fitness vector does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    # A score must never carry promotion authority.  The owning surface documents
    # this as an always-``False`` predicate; the gate composes it rather than
    # re-deciding, and refuses outright if that guarantee were ever weakened.
    if may_promote_on_score(document) is not False:
        _fail(
            "SCORE_GRANTS_PROMOTION",
            "the fitness surface reported that a score may promote a candidate",
            {FITNESS_ID_FIELD: document.get(FITNESS_ID_FIELD)},
        )
    candidate_id = _require_text(document.get(CANDIDATE_FIELD), CANDIDATE_FIELD)
    if candidate_id != expected_candidate_id:
        _fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "the fitness vector describes a different candidate",
            {"fitness_candidate": candidate_id, "expected": expected_candidate_id},
        )
    status = str(document.get(GATE_STATUS_FIELD))
    failures = document.get(GATE_FAILURES_FIELD) or []
    passed = status == hard_gate_pass_token() and not failures
    return _Fitness(
        fitness_vector_id=_require_text(
            document.get(FITNESS_ID_FIELD), FITNESS_ID_FIELD
        ),
        candidate_id=candidate_id,
        hard_gate_status=status,
        hard_gate_passed=passed,
        document=document,
    )


def _seal_firewall(
    evaluator_bundle: Mapping[str, Any],
    holdout_manifest: Mapping[str, Any],
    holdout_read_principal_ids: Sequence[str],
) -> VerifierFirewall:
    """Hand the sealed evaluator to the firewall, mapping its refusals to a code.

    The firewall already refuses a candidate-readable or run-mutable evaluator
    and a holdout any candidate, model, prompt or backend can reach.  The gate
    composes that check rather than repeating it, so the one boundary is enforced
    in one place.
    """
    bundle = _require_mapping(evaluator_bundle, "evaluator_bundle")
    holdout = _require_mapping(holdout_manifest, "holdout_manifest")
    try:
        firewall = VerifierFirewall(
            bundle,
            holdout,
            holdout_read_principal_ids=list(holdout_read_principal_ids),
        )
        firewall.verify_self()
    except (FirewallRefusal, EvaluatorDrift, ContractViolation) as error:
        _fail(
            "HIDDEN_EVALUATION_FIREWALL_BROKEN",
            "the evaluator bundle or holdout is not a sealed hidden evaluation",
            {"firewall_error": str(error)},
        )
        raise AssertionError  # pragma: no cover - _fail always raises
    return firewall


def _guard_authority(role: str) -> None:
    """Refuse a candidate-generating role driving the decision.

    The set of candidate-generating roles comes from the firewall that owns the
    generator/verifier separation, not from a second copy here, so a candidate,
    model, prompt or backend can never acquire authority over its own evaluation.
    """
    if role in CANDIDATE_GENERATING_ROLES:
        _fail(
            "CANDIDATE_ROLE_HOLDS_AUTHORITY",
            "a candidate-generating role may not drive an admissibility decision",
            {"role": role},
        )


def _guard_leakage(firewall: VerifierFirewall, leaked_ids: Sequence[str]) -> None:
    """Refuse when evaluator feedback has touched a bound holdout partition."""
    invalidated = firewall.leakage_invalidates(
        _require_sequence(leaked_ids, "leaked_ids")
    )
    if invalidated:
        _fail(
            "EVALUATOR_FEEDBACK_LEAKED",
            "leaked ids touch bound holdout partitions; the comparison is INVALIDATED",
            {"invalidated_holdouts": invalidated},
        )


def _resolve_disclosure(
    firewall: VerifierFirewall,
    *,
    disclose_hidden_result: bool,
    unblinding_approval_id: str | None,
    requesting_principal_id: str,
    requesting_role: str,
) -> bool:
    """Whether the hidden result may be disclosed; the default keeps it hidden.

    Disclosure needs both an unblinding approval and holdout-read authority; the
    gate never records the hidden score either way, so a refusal here stops an
    unapproved *reveal*, not the admissibility decision itself.
    """
    if not disclose_hidden_result:
        return False
    if not (isinstance(unblinding_approval_id, str) and unblinding_approval_id.strip()):
        _fail(
            "HIDDEN_RESULT_DISCLOSURE_UNAPPROVED",
            "disclosure of the hidden-evaluation result requires an unblinding approval",
            {"unblinding_approval_id": unblinding_approval_id},
        )
    try:
        firewall.require_holdout_access(requesting_principal_id, requesting_role)
    except HoldoutAccessDenied as error:
        _fail(
            "HIDDEN_RESULT_DISCLOSURE_UNAPPROVED",
            "the requesting principal may not read the holdout to disclose a result",
            {"access_error": str(error)},
        )
    return True


def _guard_statistics_integrity(
    record: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    *,
    complete: bool,
) -> None:
    """Re-derive the record hash and confirm its verdict matches the report.

    Both checks run only on a complete record: an incomplete one is refused as an
    uncorrected selection in the decision phase, and there is no bound accounting
    to cross-check on it.
    """
    if not complete:
        return
    stored = record.get(RECORD_HASH_FIELD)
    if not isinstance(stored, str) or not stored:
        _fail(
            "SEARCH_RECORD_CONTRACT_VIOLATED",
            "the complete statistical record carries no sealed record hash",
            {"record_hash": stored},
        )
    recomputed = sha256_of_payload(
        {key: value for key, value in record.items() if key != RECORD_HASH_FIELD}
    )
    if recomputed != stored:
        _fail(
            "SEARCH_RECORD_CONTRACT_VIOLATED",
            "the statistical record does not re-derive its own hash",
            {"recorded": stored, "recomputed": recomputed},
        )
    record_recommendation = str(record.get(RECOMMENDATION_FIELD))
    report_recommendation = str(selective_report.get(RECOMMENDATION_FIELD))
    record_risk = str(record.get(RISK_FIELD))
    report_risk = str(selective_report.get(RISK_FIELD))
    if record_recommendation != report_recommendation or record_risk != report_risk:
        _fail(
            "SELECTIVE_ACCOUNTING_MISBOUND",
            "the record's selective verdict does not match the report it summarizes",
            {
                "record_recommendation": record_recommendation,
                "report_recommendation": report_recommendation,
                "record_risk": record_risk,
                "report_risk": report_risk,
            },
        )


def _decide(
    fitness: _Fitness,
    record: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    *,
    missing_artifacts: Sequence[str],
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message and its context.

    The order is deliberate.  A selection with no statistical correction at all is
    refused first, because nothing downstream is meaningful without it.  Then the
    candidate's own hard gate must pass.  Only then does the selective-inference
    verdict decide, and it must permit advancement on both the record and the
    report it summarizes — neither substitutes for the other.
    """
    if missing_artifacts:
        return (
            REFUSE,
            "UNCORRECTED_ADAPTIVE_SELECTION",
            "the adaptive selection arrives without the complete statistical record",
            {"missing": list(missing_artifacts)},
        )
    if not fitness.hard_gate_passed:
        return (
            REFUSE,
            "FITNESS_HARD_GATE_NOT_PASSED",
            "the candidate's fitness hard gate did not pass",
            {
                GATE_STATUS_FIELD: fitness.hard_gate_status,
                GATE_FAILURES_FIELD: list(
                    fitness.document.get(GATE_FAILURES_FIELD) or []
                ),
            },
        )
    if not (
        search_permits_promotion(record)
        and permits_promotion_without_replication(selective_report)
    ):
        return (
            REFUSE,
            "SELECTION_NOT_STATISTICALLY_CLEARED",
            "the selective-inference verdict does not permit advancement",
            {
                RECOMMENDATION_FIELD: record.get(RECOMMENDATION_FIELD),
                RISK_FIELD: record.get(RISK_FIELD),
            },
        )
    return (
        ADMIT,
        None,
        "the candidate is admissible to be forwarded to promotion review",
        {},
    )


def derive_selective_admissibility(
    *,
    candidate_id: str,
    fitness_vector: Mapping[str, Any],
    evaluator_bundle: Mapping[str, Any],
    holdout_manifest: Mapping[str, Any],
    search_statistics: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    requesting_principal_id: str,
    requesting_role: str,
    holdout_read_principal_ids: Sequence[str] = (),
    leaked_ids: Sequence[str] = (),
    disclose_hidden_result: bool = False,
    unblinding_approval_id: str | None = None,
    created_at: str,
) -> dict[str, Any]:
    """Derive the admissibility decision and its immutable receipt.

    Input-integrity failures — a scalar fitness, a broken firewall, a mismatched
    candidate, a leakage hit, an altered statistical record, a candidate role, or
    an unapproved disclosure — refuse immediately, because there is no well-formed
    decision to record over evidence the gate cannot trust.  Once every input is
    validated and bound, the admissibility decision always produces a receipt,
    whether it admits or refuses, so every decision over well-formed inputs is
    auditable and re-derivable.
    """
    report = _resolve_selective_report(selective_report)
    stamp = _require_text(created_at, "created_at")
    expected = _require_text(candidate_id, CANDIDATE_FIELD)
    principal = _require_text(requesting_principal_id, "requesting_principal_id")
    role = _require_text(requesting_role, "requesting_role")

    fitness = _resolve_fitness(fitness_vector, expected_candidate_id=expected)

    record = _require_mapping(search_statistics, "search_statistics")
    for field, source in ((CANDIDATE_FIELD, record), (CANDIDATE_FIELD, report)):
        if str(source.get(field)) != expected:
            _fail(
                "CANDIDATE_IDENTITY_MISMATCH",
                "a statistical artifact describes a different candidate",
                {"expected": expected, "found": source.get(field)},
            )

    _guard_authority(role)
    firewall = _seal_firewall(
        evaluator_bundle, holdout_manifest, holdout_read_principal_ids
    )
    _guard_leakage(firewall, leaked_ids)
    disclosed = _resolve_disclosure(
        firewall,
        disclose_hidden_result=disclose_hidden_result,
        unblinding_approval_id=unblinding_approval_id,
        requesting_principal_id=principal,
        requesting_role=role,
    )

    missing_artifacts = missing_statistical_artifacts(record)
    _guard_statistics_integrity(record, report, complete=not missing_artifacts)

    decision, finding_code, message, decision_context = _decide(
        fitness, record, report, missing_artifacts=missing_artifacts
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "created_at": stamp,
        "decision": decision,
        "admissible_for_promotion_review": decision == ADMIT,
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_id": expected,
        "requesting_principal_id": principal,
        "requesting_role": role,
        "fitness_vector_id": fitness.fitness_vector_id,
        "fitness_hard_gate_status": fitness.hard_gate_status,
        "evaluator_bundle_hash": firewall.sealed_hash,
        "evaluator_id": firewall.bundle_id,
        "holdout_manifest_hash": str(holdout_manifest["manifest_hash"]),
        "search_statistics_record_hash": sha256_hex(canonical_json(record)),
        "selective_report_hash": sha256_hex(canonical_json(report)),
        "winner_curse_risk": str(report.get(RISK_FIELD)),
        "promotion_recommendation": str(report.get(RECOMMENDATION_FIELD)),
        "hidden_result_disclosed": disclosed,
        "missing_statistical_artifacts": list(missing_artifacts),
    }
    receipt["gate_id"] = (
        GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": expected,
                    "created_at": stamp,
                    "decision": decision,
                    "evaluator_bundle_hash": receipt["evaluator_bundle_hash"],
                    "fitness_vector_id": fitness.fitness_vector_id,
                    "search_statistics_record_hash": receipt[
                        "search_statistics_record_hash"
                    ],
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_selective_admissibility(
    *,
    candidate_id: str,
    fitness_vector: Mapping[str, Any],
    evaluator_bundle: Mapping[str, Any],
    holdout_manifest: Mapping[str, Any],
    search_statistics: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    requesting_principal_id: str,
    requesting_role: str,
    holdout_read_principal_ids: Sequence[str] = (),
    leaked_ids: Sequence[str] = (),
    disclose_hidden_result: bool = False,
    unblinding_approval_id: str | None = None,
    created_at: str,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on admit, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the candidate was stopped short of promotion review.
    """
    receipt = derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=fitness_vector,
        evaluator_bundle=evaluator_bundle,
        holdout_manifest=holdout_manifest,
        search_statistics=search_statistics,
        selective_report=selective_report,
        requesting_principal_id=requesting_principal_id,
        requesting_role=requesting_role,
        holdout_read_principal_ids=holdout_read_principal_ids,
        leaked_ids=leaked_ids,
        disclose_hidden_result=disclose_hidden_result,
        unblinding_approval_id=unblinding_approval_id,
        created_at=created_at,
    )
    if receipt["decision"] != ADMIT:
        raise SelectiveAdmissibilityRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a refusal.
__all__ = [
    "ADMIT",
    "FINDING_CODES",
    "GATE_NAME",
    "REFUSE",
    "SchemaNotFound",
    "SelectiveAdmissibilityRefused",
    "derive_selective_admissibility",
    "evaluate_selective_admissibility",
    "hard_gate_pass_token",
]
