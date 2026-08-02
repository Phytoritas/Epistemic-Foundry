"""Leakage, reward-hacking and evaluator-update governance integration gate (S06).

S05 sealed the evaluator, the hidden holdout and the executable-candidate threat
controls.  J05 sealed the typed operator registry and the prompt-mutation
quarantine, including the reader that proves the evaluator-update governance
workflow still declares its no-retroactivity node.  The governance quarantine
owns what an ``EvaluatorMutationProposal`` is and forces it born future-only.
Each surface is correct alone, and none of them answers the one question this
gate exists for: for a single evolution run, do the reward signal, the evaluator
update and the feedback channel *together* stay inside the invariants EF4-I22,
EF4-I44, EF4-I45, EF4-I54 and EF4-I56 draw — and does the composition emit an
immutable, re-derivable record of that decision?

This is an *integration* gate.  It composes the sealed surfaces and refuses the
compositions that would breach a boundary none of them can see alone, restating
none of their vocabularies (EF4-I22): every canonical token it reasons about is
read positionally out of the schema that declares it, and the shapes it assumes
are asserted against those schemas by the schema-and-type suite.

*Reward-hacking.*  ``refuse_reward_hacking`` refuses to let a proxy score become
authority it does not hold.  A candidate whose hard gates FAILED cannot have its
multi-objective proxy dimensions routed as reward (EF4-I45: a combined score may
order search but never promote), and a routing signal that learns only from the
immediate proxy basis is refused (EF4-I54: reward routing learns from validated
holdout/replication utility, not only immediate proxy score).  The reward
feedback surface is driven through the S05 leakage audit, so feedback carrying
holdout material is refused rather than fed back into the candidate or the
search.

*Evaluator-update governance.*  ``govern_evaluator_update`` composes the
governance quarantine and J05's workflow reader to enforce EF4-I43/EF4-I56: an
evaluator change is a proposal for a *future* sealed run, never an edit to the
run in progress.  The proposal may not waive its own no-retroactivity or
qualification requirement, must be approved for a future run, must target a run
other than the one that produced it, and must be backed by an *independent*
qualification of the future bundle — never a re-qualification of the current one.
The current run's sealed evaluator is re-verified through the S05 firewall so an
update that has already mutated it fails closed, and every candidate-generating
role is probed against the holdout so none silently acquired the evaluator's
authority.

*Composition.*  ``integrate_evolution_security_gate`` binds the sealed sub-gate
receipts into one re-derivable integration receipt, re-deriving each sub-receipt
from its own content so a tampered sub-decision cannot be laundered into the
combined record.

Every decision resolves to an immutable, content-addressed receipt: two runs
over equal inputs produce byte-equal receipts.  Nothing here scores, promotes,
mutates its inputs, or reads a clock.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...governance.quarantine import (
    QuarantineViolation,
    require_not_retroactive,
)
from ...operators.v4_j05 import (
    MutationOperatorError,
    governance_retroactivity_node,
)
from ...security.v4_s05 import ThreatControlError, build_leakage_audit
from ...verifier_firewall.firewall import (
    CANDIDATE_GENERATING_ROLES,
    EvaluatorDrift,
    VerifierFirewall,
)

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "VOCABULARY_DRIFT": (
        "a canonical schema no longer declares its vocabulary in the shape this "
        "gate reads positionally, so selecting a token by index would pick the "
        "wrong value; the gate fails closed rather than guess"
    ),
    "FITNESS_CONTRACT_VIOLATED": (
        "the fitness vector does not satisfy its canonical schema, so its hard "
        "gate status and dimensions would be read from a shape no contract admits"
    ),
    "ROUTING_CONTRACT_VIOLATED": (
        "the model-routing receipt does not satisfy its canonical schema, so its "
        "reward basis would be read from a shape no contract admits"
    ),
    "REWARD_HACKING_HARD_GATE_FAILED": (
        "the candidate failed its hard gates, so routing its proxy dimensions as "
        "reward would let a score the gates rejected acquire search authority — "
        "a combined score may order search but never promote (EF4-I45)"
    ),
    "REWARD_BASIS_IMMEDIATE_PROXY_ONLY": (
        "the reward routing learns only from the immediate proxy basis, which is "
        "the signal a candidate can game; reward must route from validated "
        "holdout or replication utility (EF4-I54)"
    ),
    "REWARD_FEEDBACK_LEAKAGE": (
        "the reward feedback surface intersects the sealed holdout, so admitting "
        "it into the candidate or the search would feed a generator the material "
        "it will be judged against"
    ),
    "LEAKAGE_AUDIT_REFUSED": (
        "the sealed S05 leakage audit refused the feedback surface, and this "
        "gate surfaces that refusal instead of admitting an unaudited channel"
    ),
    "EVALUATOR_PROPOSAL_CONTRACT_VIOLATED": (
        "the evaluator mutation proposal does not satisfy its canonical schema, "
        "so its governance flags and status would be read from an invalid shape"
    ),
    "EVALUATOR_UPDATE_RETROACTIVE_PERMITTED": (
        "the proposal waives its own no-retroactivity or qualification "
        "requirement, which is how a change would rewrite the judgments a "
        "completed run already made"
    ),
    "EVALUATOR_BUNDLE_DRIFT": (
        "the current run's sealed evaluator no longer hashes to its recorded "
        "digest, so an evaluator update has already mutated the run in progress "
        "instead of a future one"
    ),
    "HOLDOUT_REACHABLE": (
        "a candidate-generating role can reach the hidden holdout, which lets a "
        "mutable role acquire the evaluator's own authority over hidden material"
    ),
    "EVALUATOR_UPDATE_NOT_APPROVED": (
        "the proposal is not approved for a future run, so activating the change "
        "would apply an unqualified or still-quarantined evaluator update"
    ),
    "EVALUATOR_UPDATE_RETROACTIVE": (
        "the update targets the run that produced it or a run it may not "
        "influence, which retroactively re-scores sealed results (EF4-I56)"
    ),
    "EVALUATOR_QUALIFICATION_CONTRACT_VIOLATED": (
        "the evaluator qualification report does not satisfy its canonical "
        "schema, so its independent verdict would be read from an invalid shape"
    ),
    "EVALUATOR_QUALIFICATION_NOT_QUALIFIED": (
        "the qualification report did not qualify the future evaluator, so the "
        "change has no independent clearance to become a future version"
    ),
    "EVALUATOR_QUALIFICATION_NOT_INDEPENDENT": (
        "the qualification report re-qualifies the current bundle rather than the "
        "future one, so the change was never independently qualified as required"
    ),
    "WORKFLOW_CONTRACT_DRIFT": (
        "the evaluator-update governance workflow no longer declares its "
        "no-retroactive-effect node, so the rule this gate mirrors is no longer "
        "true of anything and the gate refuses to assert it"
    ),
    "INTEGRATION_SUBGATE_TAMPERED": (
        "a sub-gate receipt does not re-derive its own identifier and hash, so "
        "the combined decision would bind a record the sub-gate did not produce"
    ),
}

#: Canonical schema names this gate reads.  Each is a registered canonical
#: contract, validated before use rather than restated as fields here.
EVALUATOR_PROPOSAL_KIND = "evaluator-mutation-proposal"
EVALUATOR_QUALIFICATION_KIND = "evaluator-qualification-report"
FITNESS_KIND = "fitness-vector"
ROUTING_KIND = "model-routing-receipt"

#: Identifier prefixes.  Every identifier this gate mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
REWARD_RECEIPT_PREFIX = "SRH-"
EVALUATOR_RECEIPT_PREFIX = "SEU-"
INTEGRATION_RECEIPT_PREFIX = "SIG-"
LEAKAGE_AUDIT_PREFIX = "SLA-"

#: The principal id used only to *exercise* the firewall's holdout-read denial
#: for every candidate-generating role.  It is never granted access; the probe
#: proves the separation is enforced rather than assumed.
HOLDOUT_DENIAL_PROBE = "S06-HOLDOUT-DENIAL-PROBE"

#: The concerns this integration gate reconciles, named so the combined receipt
#: records which boundaries it composed.  Compound names, none a wire value.
CONCERN_REWARD_HACKING = "reward_hacking_refusal"
CONCERN_FEEDBACK_ISOLATION = "holdout_feedback_isolation"
CONCERN_EVALUATOR_UPDATE = "evaluator_update_future_only"


class GovernanceGateError(ValueError):
    """The gate refuses a composition, or its evidence, with a documented code."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise GovernanceGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise GovernanceGateError(code, message, context)


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


def _enum(kind: str, field: str, expected: int) -> tuple[str, ...]:
    """The declared enum tokens for a schema field, refused on shape drift.

    The tokens are read out of the canonical schema rather than restated here,
    and the count the gate reasons about is checked so a reshaped vocabulary
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
    """Every canonical token the gate selects, read positionally from schema.

    Holding these as string literals would be a second copy that drifts from the
    contract (EF4-I22).  The indices are the schemas' own declared order — the
    proposal-status ladder ``[quarantined, under-review, approved-for-future,
    rejected]``, the qualification ladder ``[qualified, ...]``, the hard-gate
    ladder ``[pass, fail, ...]`` and the reward-basis ladder
    ``[immediate-proxy, ...]`` — each asserted against its schema by the
    schema-and-type suite.
    """
    proposal = _enum(EVALUATOR_PROPOSAL_KIND, "status", 4)
    qualification = _enum(EVALUATOR_QUALIFICATION_KIND, "qualification_status", 4)
    hard_gate = _enum(FITNESS_KIND, "hard_gate_status", 4)
    reward = _enum(ROUTING_KIND, "reward_basis", 5)
    return {
        "proposal_approved": proposal[2],
        "future_qualified": qualification[0],
        "hard_gate_failed": hard_gate[1],
        "reward_immediate_proxy": reward[0],
    }


def _identified(
    record: dict[str, Any], prefix: str, id_field: str, hash_field: str
) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record[id_field] = prefix + sha256_of_payload(record)[len("sha256:") :]
    record[hash_field] = hash_excluding(record, hash_field)
    return record


def _require_receipt_identity(
    record: Mapping[str, Any], prefix: str, id_field: str, hash_field: str, code: str
) -> dict[str, Any]:
    """Re-derive a sub-gate receipt's identifier and hash from its own content."""
    document = _require_mapping(record, "sub_gate_receipt")
    body = {
        key: value
        for key, value in document.items()
        if key not in {id_field, hash_field}
    }
    expected_id = prefix + sha256_of_payload(body)[len("sha256:") :]
    if document.get(id_field) != expected_id or document.get(
        hash_field
    ) != hash_excluding(document, hash_field):
        _fail(
            code,
            "a sub-gate receipt does not re-derive its own identity",
            {"expected_id": expected_id, "stated_id": document.get(id_field)},
        )
    return document


def _audit_feedback_leakage(
    *,
    firewall: VerifierFirewall,
    run_or_bundle_id: str,
    observed_artifact_ids: Sequence[str],
    surfaces_checked: Sequence[str],
    access_log_artifact_id: str,
    similarity_alerts: Sequence[str],
    exposure_code: str,
) -> dict[str, Any]:
    """Drive the S05 leakage audit over a feedback surface, refusing exposure.

    The audit id is derived from the surface so the receipt embedding it stays
    re-derivable; the S05 builder would otherwise mint a random id that cannot
    replay.  A refusal from the sealed audit is surfaced, and any exposure it
    detects is refused rather than allowed to flow back into the candidate.
    """
    observed = [
        _require_text(value, f"observed_artifact_ids[{position}]")
        for position, value in enumerate(
            _require_sequence(observed_artifact_ids, "observed_artifact_ids")
        )
    ]
    run = _require_text(run_or_bundle_id, "run_or_bundle_id")
    audit_id = (
        LEAKAGE_AUDIT_PREFIX
        + sha256_of_payload(
            {
                "observed_artifact_ids": sorted(observed),
                "run_or_bundle_id": run,
            }
        )[len("sha256:") :]
    )
    try:
        audit = build_leakage_audit(
            firewall=firewall,
            run_or_bundle_id=run,
            surfaces_checked=list(surfaces_checked),
            observed_artifact_ids=observed,
            access_log_artifact_id=_require_text(
                access_log_artifact_id, "access_log_artifact_id"
            ),
            similarity_alerts=list(similarity_alerts),
            leakage_audit_id=audit_id,
        )
    except ThreatControlError as error:
        _fail(
            "LEAKAGE_AUDIT_REFUSED",
            str(error),
            {"threat_context": error.context, "threat_finding_code": error.code},
        )
        raise  # pragma: no cover - _fail always raises
    if audit["detected_exposures"]:
        _fail(
            exposure_code,
            "the feedback surface intersects the sealed holdout",
            {
                "detected_exposures": list(audit["detected_exposures"]),
                "leakage_audit_id": str(audit["leakage_audit_id"]),
            },
        )
    return audit


def refuse_reward_hacking(
    *,
    fitness_vector: Mapping[str, Any],
    routing_receipt: Mapping[str, Any],
    firewall: VerifierFirewall,
    run_or_bundle_id: str,
    feedback_artifact_ids: Sequence[str],
    surfaces_checked: Sequence[str],
    access_log_artifact_id: str,
    similarity_alerts: Sequence[str] = (),
) -> dict[str, Any]:
    """Refuse a proxy score acquiring reward authority it does not hold.

    Three boundaries are composed: a candidate that failed its hard gates cannot
    have its proxy dimensions rewarded (EF4-I45), a reward that learns only from
    the immediate proxy basis is refused (EF4-I54), and the reward feedback
    surface is driven through the S05 leakage audit (EF4-I44).  A clean audit is
    embedded so the receipt carries the evidence of its own clearance.
    """
    vocab = _vocab()
    fitness = _require_mapping(fitness_vector, "fitness_vector")
    try:
        validate_artifact(FITNESS_KIND, dict(fitness))
    except ContractViolation as error:
        _fail(
            "FITNESS_CONTRACT_VIOLATED",
            "the fitness vector does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    routing = _require_mapping(routing_receipt, "routing_receipt")
    try:
        validate_artifact(ROUTING_KIND, dict(routing))
    except ContractViolation as error:
        _fail(
            "ROUTING_CONTRACT_VIOLATED",
            "the model-routing receipt does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )

    if str(fitness["hard_gate_status"]) == vocab["hard_gate_failed"]:
        _fail(
            "REWARD_HACKING_HARD_GATE_FAILED",
            "a hard-gate-failed candidate's proxy dimensions may not be rewarded",
            {
                "candidate_id": str(fitness["candidate_id"]),
                "hard_gate_status": str(fitness["hard_gate_status"]),
            },
        )
    if str(routing["reward_basis"]) == vocab["reward_immediate_proxy"]:
        _fail(
            "REWARD_BASIS_IMMEDIATE_PROXY_ONLY",
            "reward routing may not learn only from the immediate proxy basis",
            {
                "reward_basis": str(routing["reward_basis"]),
                "routing_receipt_id": str(routing["receipt_id"]),
            },
        )

    audit = _audit_feedback_leakage(
        firewall=firewall,
        run_or_bundle_id=run_or_bundle_id,
        observed_artifact_ids=feedback_artifact_ids,
        surfaces_checked=surfaces_checked,
        access_log_artifact_id=access_log_artifact_id,
        similarity_alerts=similarity_alerts,
        exposure_code="REWARD_FEEDBACK_LEAKAGE",
    )

    receipt: dict[str, Any] = {
        "candidate_id": str(fitness["candidate_id"]),
        "fitness_vector_id": str(fitness["fitness_vector_id"]),
        "hard_gate_status": str(fitness["hard_gate_status"]),
        "leakage_audit": dict(audit),
        "leakage_audit_id": str(audit["leakage_audit_id"]),
        "reward_basis": str(routing["reward_basis"]),
        "routing_receipt_id": str(routing["receipt_id"]),
        "run_or_bundle_id": _require_text(run_or_bundle_id, "run_or_bundle_id"),
    }
    return _identified(receipt, REWARD_RECEIPT_PREFIX, "receipt_id", "receipt_hash")


def _governance_node() -> str:
    """The workflow node this gate mirrors, composed from J05, refused if gone."""
    try:
        return governance_retroactivity_node()
    except MutationOperatorError as error:
        _fail(
            "WORKFLOW_CONTRACT_DRIFT",
            str(error),
            {"j05_finding_code": error.code},
        )
        raise  # pragma: no cover - _fail always raises


def govern_evaluator_update(
    *,
    proposal: Mapping[str, Any],
    target_run_id: str,
    qualification_report: Mapping[str, Any],
    firewall: VerifierFirewall,
) -> dict[str, Any]:
    """Admit an evaluator update only as a governed, future-only change.

    The proposal may not waive its own no-retroactivity or qualification
    requirement, the current run's sealed evaluator must be intact, no
    candidate-generating role may reach the holdout, the proposal must be
    approved for a future run other than the one that produced it, and the
    change must carry an independent qualification of the *future* bundle rather
    than a re-qualification of the current one.
    """
    vocab = _vocab()
    node = _governance_node()

    document = _require_mapping(proposal, "proposal")
    try:
        validate_artifact(EVALUATOR_PROPOSAL_KIND, dict(document))
    except ContractViolation as error:
        _fail(
            "EVALUATOR_PROPOSAL_CONTRACT_VIOLATED",
            "the evaluator mutation proposal does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if (
        document.get("retroactive_effect_prohibited") is not True
        or document.get("qualification_required") is not True
    ):
        _fail(
            "EVALUATOR_UPDATE_RETROACTIVE_PERMITTED",
            "the proposal waives its no-retroactivity or qualification requirement",
            {
                "qualification_required": document.get("qualification_required"),
                "retroactive_effect_prohibited": document.get(
                    "retroactive_effect_prohibited"
                ),
            },
        )

    try:
        firewall.verify_self()
    except EvaluatorDrift as error:
        _fail(
            "EVALUATOR_BUNDLE_DRIFT",
            str(error),
            {"evaluator_id": firewall.bundle_id},
        )
    reachable = sorted(
        role
        for role in CANDIDATE_GENERATING_ROLES
        if firewall.may_read_holdout(HOLDOUT_DENIAL_PROBE, role)
    )
    if reachable:
        _fail(
            "HOLDOUT_REACHABLE",
            "candidate-generating roles can read the hidden holdout",
            {"roles": reachable},
        )

    status = str(document["status"])
    if status != vocab["proposal_approved"]:
        _fail(
            "EVALUATOR_UPDATE_NOT_APPROVED",
            "the proposal is not approved for a future run",
            {"status": status},
        )
    target = _require_text(target_run_id, "target_run_id")
    try:
        require_not_retroactive(document, target_run_id=target)
    except QuarantineViolation as error:
        _fail(
            "EVALUATOR_UPDATE_RETROACTIVE",
            str(error),
            {"source_run_id": document.get("source_run_id"), "target_run_id": target},
        )

    report = _require_mapping(qualification_report, "qualification_report")
    try:
        validate_artifact(EVALUATOR_QUALIFICATION_KIND, dict(report))
    except ContractViolation as error:
        _fail(
            "EVALUATOR_QUALIFICATION_CONTRACT_VIOLATED",
            "the evaluator qualification report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if str(report["qualification_status"]) != vocab["future_qualified"]:
        _fail(
            "EVALUATOR_QUALIFICATION_NOT_QUALIFIED",
            "the qualification report did not qualify the future evaluator",
            {"qualification_status": str(report["qualification_status"])},
        )
    if str(report["evaluator_bundle_id"]) == str(
        document["current_evaluator_bundle_id"]
    ):
        _fail(
            "EVALUATOR_QUALIFICATION_NOT_INDEPENDENT",
            "the qualification report re-qualifies the current bundle, not the future one",
            {"evaluator_bundle_id": str(report["evaluator_bundle_id"])},
        )

    receipt: dict[str, Any] = {
        "current_evaluator_bundle_id": str(document["current_evaluator_bundle_id"]),
        "future_evaluator_bundle_id": str(report["evaluator_bundle_id"]),
        "governance_node_id": node,
        "leakage_audit_id": str(report["leakage_audit_id"]),
        "proposal_hash": str(document["proposal_hash"]),
        "proposal_id": str(document["proposal_id"]),
        "qualification_report_id": str(report["report_id"]),
        "qualification_status": str(report["qualification_status"]),
        "source_run_id": str(document["source_run_id"]),
        "status": status,
        "target_run_id": target,
    }
    return _identified(receipt, EVALUATOR_RECEIPT_PREFIX, "receipt_id", "receipt_hash")


def integrate_evolution_security_gate(
    *,
    run_id: str,
    reward_receipt: Mapping[str, Any],
    evaluator_update_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind the sealed sub-gate receipts into one re-derivable integration record.

    Each sub-receipt is re-derived from its own content, so a tampered sub-gate
    decision cannot be laundered into the combined record.  The evaluator-update
    receipt is optional because a run may propose no evaluator change; when it is
    present the composition also records the future-only governance concern.
    """
    run = _require_text(run_id, "run_id")
    reward = _require_receipt_identity(
        reward_receipt,
        REWARD_RECEIPT_PREFIX,
        "receipt_id",
        "receipt_hash",
        "INTEGRATION_SUBGATE_TAMPERED",
    )
    components: dict[str, Any] = {
        "leakage_audit_id": str(reward["leakage_audit_id"]),
        "reward_hacking_receipt_id": str(reward["receipt_id"]),
    }
    concerns = [CONCERN_REWARD_HACKING, CONCERN_FEEDBACK_ISOLATION]
    if evaluator_update_receipt is not None:
        update = _require_receipt_identity(
            evaluator_update_receipt,
            EVALUATOR_RECEIPT_PREFIX,
            "receipt_id",
            "receipt_hash",
            "INTEGRATION_SUBGATE_TAMPERED",
        )
        components["evaluator_update_receipt_id"] = str(update["receipt_id"])
        concerns.append(CONCERN_EVALUATOR_UPDATE)

    receipt: dict[str, Any] = {
        "components": dict(sorted(components.items())),
        "concerns_gated": sorted(concerns),
        "run_id": run,
    }
    return _identified(
        receipt, INTEGRATION_RECEIPT_PREFIX, "receipt_id", "receipt_hash"
    )
