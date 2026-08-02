"""The operator/prompt qualification and context-budget integration gate (J06).

Two independent questions decide whether a mutation operator may be applied to a
run, and neither is answered here from scratch.

The first is *qualification*.  A prompt-affecting operator edits the instruction
a generator receives, so EF4-I55 forbids applying it until a co-evolved mutation
prompt has been qualified in quarantine and released.  The gate asks that of the
surfaces that own it: the J05 registry's ``claim_active_prompt_operator`` runs
the S05 inert-mutations gate against the run's active prompt surface, and the
J05 prompt-workflow's ``build_activation_record`` binds the qualification
evidence and refuses a proposal aimed at the run that produced it.  A refusal is
therefore the composed surfaces' refusal, remapped to this gate's finding codes
so a caller sees one vocabulary.  An operator that touches no prompt genome
needs only to be registered; there is no prompt to qualify.

The second is *context budget*.  Work is admitted only against a budget that
actually bounds spend, and only when its context tokens fit under that bound.
The token figure is re-derived from the manifest's own instruction, evidence and
tool components rather than taken from the total it publishes, the ceiling is
read through the budget module's own ``normalize_hard_limits``, and whether the
envelope bounds anything at all is the budget module's ``spend_is_bounded`` —
never a label restated here.

Admission produces one immutable receipt that re-derives its own digest from the
fields it publishes, so a later reader can prove it is the decision the gate
made.  Nothing here scores, promotes or executes; the receipt carries a verdict,
not a fitness, and inputs are copied rather than mutated.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence, TypeVar

from ...budgets.envelope import (
    BudgetViolation,
    normalize_hard_limits,
    spend_is_bounded,
)
from ...contracts import ContractViolation, validate_artifact
from ...domain.hashing import hash_excluding
from ...domain.ids import new_id
from ..v4_j05 import (
    MutationOperatorError,
    MutationOperatorRegistry,
    build_activation_record,
)
from .declarations import (
    BUDGET_ENVELOPE_KIND,
    BUDGET_HASH_FIELD,
    BUDGET_ID_FIELD,
    COMPONENT_TOKEN_FIELDS,
    CONTEXT_HASH_FIELD,
    CONTEXT_MANIFEST_KIND,
    ENFORCEMENT_FIELD,
    MANIFEST_ID_FIELD,
    TOKEN_ACCOUNTING_FIELD,
    TOKENS_DIMENSION,
    TOTAL_TOKENS_FIELD,
    _fail,
    _require_mapping,
    _require_text,
    budget_envelope_contract,
    context_accounting_contract,
)

__all__ = [
    "assess_context_budget",
    "admit_operator_application",
    "verify_gate_receipt",
]

T = TypeVar("T")

#: How a composed J05 refusal is reported in this gate's own vocabulary.  A
#: refusal without a mapping is not one this gate can classify, so it surfaces as
#: an invalid input naming the underlying code rather than being relabeled.
_J05_TO_J06: dict[str, str] = {
    "OPERATOR_UNREGISTERED": "OPERATOR_UNREGISTERED",
    "PROMPT_MUTATION_INERT": "PROMPT_QUARANTINED",
    "QUALIFICATION_EVIDENCE_MISSING": "OPERATOR_UNQUALIFIED",
    "RETROACTIVE_ACTIVATION": "RETROACTIVE_APPLICATION",
}

#: The outcome an admitted application carries.  It is a decision, never a score.
ADMITTED = "ADMITTED"


def _compose_j05(call: Callable[[], T]) -> T:
    """Run a J05 surface and remap its refusal into this gate's finding codes."""
    try:
        return call()
    except MutationOperatorError as error:
        mapped = _J05_TO_J06.get(error.code)
        if mapped is None:
            _fail(
                "INPUT_INVALID",
                f"the composed qualification surface refused: {error}",
                {"j05_code": error.code, **error.context},
            )
        _fail(mapped, str(error), {"j05_code": error.code, **error.context})
        raise AssertionError  # pragma: no cover - _fail always raises


def assess_context_budget(
    *,
    context_manifest: Mapping[str, Any],
    budget_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Decide whether the work's context tokens fit under a bounded budget.

    The total is re-derived from the manifest's own components, the ceiling is
    read through the budget module's normalizer, and whether the envelope bounds
    spend at all is the budget module's own judgment.  A refusal is raised
    rather than a score returned.
    """
    context_accounting_contract()
    budget_envelope_contract()

    manifest = dict(_require_mapping(context_manifest, "context_manifest"))
    try:
        validate_artifact(CONTEXT_MANIFEST_KIND, manifest)
    except ContractViolation as error:
        _fail(
            "CONTEXT_MANIFEST_MALFORMED",
            "the context assembly manifest does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )

    accounting = dict(
        _require_mapping(manifest[TOKEN_ACCOUNTING_FIELD], "token_accounting")
    )
    components = {field: int(accounting[field]) for field in COMPONENT_TOKEN_FIELDS}
    derived_total = sum(components.values())
    declared_total = int(accounting[TOTAL_TOKENS_FIELD])
    if declared_total != derived_total:
        _fail(
            "CONTEXT_ACCOUNTING_INCONSISTENT",
            "the manifest total does not re-derive from its own token components",
            {"components": components, "declared_total": declared_total},
        )

    envelope = dict(_require_mapping(budget_envelope, "budget_envelope"))
    try:
        validate_artifact(BUDGET_ENVELOPE_KIND, envelope)
    except ContractViolation as error:
        _fail(
            "BUDGET_MALFORMED",
            "the budget envelope does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    _require_sealed_budget(envelope)

    if not spend_is_bounded(envelope):
        _fail(
            "BUDGET_UNENFORCED",
            "the envelope's enforcement label does not bound spend",
            {ENFORCEMENT_FIELD: str(envelope.get(ENFORCEMENT_FIELD))},
        )
    try:
        limits = normalize_hard_limits(dict(envelope["hard_limits"]))
    except BudgetViolation as error:
        _fail(
            "BUDGET_MALFORMED",
            str(error),
            {"hard_limits": dict(envelope["hard_limits"])},
        )
    token_ceiling = limits[TOKENS_DIMENSION]
    if token_ceiling is None:
        _fail(
            "BUDGET_UNENFORCED",
            "the bounded envelope declares no token ceiling to meter against",
            {ENFORCEMENT_FIELD: str(envelope.get(ENFORCEMENT_FIELD))},
        )

    ceiling = int(token_ceiling)
    if declared_total > ceiling:
        _fail(
            "CONTEXT_OVER_BUDGET",
            "the work's context tokens exceed the bounded token ceiling",
            {"token_ceiling": ceiling, TOTAL_TOKENS_FIELD: declared_total},
        )

    assessment: dict[str, Any] = {
        BUDGET_HASH_FIELD: str(envelope[BUDGET_HASH_FIELD]),
        BUDGET_ID_FIELD: str(envelope[BUDGET_ID_FIELD]),
        CONTEXT_HASH_FIELD: str(manifest[CONTEXT_HASH_FIELD]),
        ENFORCEMENT_FIELD: str(envelope[ENFORCEMENT_FIELD]),
        MANIFEST_ID_FIELD: str(manifest[MANIFEST_ID_FIELD]),
        "token_components": dict(sorted(components.items())),
        "token_ceiling": ceiling,
        "token_headroom": ceiling - declared_total,
        TOTAL_TOKENS_FIELD: declared_total,
        "within_budget": True,
    }
    return assessment


def _require_sealed_budget(envelope: Mapping[str, Any]) -> None:
    """Refuse a budget whose own digest does not re-derive from its fields."""
    claimed = envelope.get(BUDGET_HASH_FIELD)
    derived = hash_excluding(dict(envelope), BUDGET_HASH_FIELD)
    if claimed != derived:
        _fail(
            "BUDGET_MALFORMED",
            "the budget envelope digest does not re-derive from its own fields",
            {"claimed": claimed, "derived": derived},
        )


def admit_operator_application(
    *,
    registry: MutationOperatorRegistry,
    operator_id: str,
    target_run_id: str,
    context_manifest: Mapping[str, Any],
    budget_envelope: Mapping[str, Any],
    source_run_id: str | None = None,
    qualification_evidence_ids: Sequence[str] = (),
    activated_at: str | None = None,
    activation_id: str | None = None,
    gate_decision_id: str | None = None,
) -> dict[str, Any]:
    """Admit one operator application against qualification and context budget, or refuse.

    A prompt-affecting operator is admitted only when the composed J05/S05
    surfaces release its proposal from quarantine, bind qualification evidence
    and confirm the target is a future run; an operator that touches no prompt is
    admitted on registration alone.  Either way the context budget must bound
    spend and the work must fit under it.  The result is a self-proving receipt.
    """
    if not isinstance(registry, MutationOperatorRegistry):
        _fail(
            "INPUT_INVALID",
            "a composed J05 mutation-operator registry is required",
            {"registry_type": type(registry).__name__},
        )
    identifier = _require_text(operator_id, "operator_id")
    run = _require_text(target_run_id, "target_run_id")

    record = _compose_j05(lambda: registry.record(identifier))
    prompt_affecting = bool(record["prompt_affecting"])
    evidence = [str(item) for item in qualification_evidence_ids]

    claim_hash: str | None = None
    activation_hash: str | None = None
    bound_source_run: str | None = None
    bound_evidence: list[str] = []

    if prompt_affecting:
        source_run = _require_text(source_run_id, "source_run_id")
        if not evidence:
            _fail(
                "OPERATOR_UNQUALIFIED",
                "a prompt-affecting operator must bind qualification evidence",
                {"operator_id": identifier},
            )
        stamp = _require_text(activated_at, "activated_at")

        claim = _compose_j05(
            lambda: registry.claim_active_prompt_operator(identifier, target_run_id=run)
        )
        proposal = registry.proposal(identifier)
        activation = _compose_j05(
            lambda: build_activation_record(
                proposal=proposal,
                source_run_id=source_run,
                target_run_id=run,
                qualification_evidence_ids=evidence,
                activated_at=stamp,
                operator_id=identifier,
                activation_id=activation_id,
            )
        )
        claim_hash = str(claim["claim_hash"])
        activation_hash = str(activation["activation_hash"])
        bound_source_run = source_run
        bound_evidence = sorted(evidence)
    elif source_run_id is not None or evidence or activated_at is not None:
        _fail(
            "INPUT_INVALID",
            "the operator touches no prompt genome, so no prompt qualification applies",
            {"operator_id": identifier},
        )

    assessment = assess_context_budget(
        context_manifest=context_manifest, budget_envelope=budget_envelope
    )

    receipt: dict[str, Any] = {
        "budget_assessment": assessment,
        "gate_decision_id": gate_decision_id or new_id("J06GATE"),
        "operator_id": identifier,
        "operator_prompt_affecting": prompt_affecting,
        "operator_record_hash": str(record["record_hash"]),
        "prompt_activation_hash": activation_hash,
        "prompt_claim_hash": claim_hash,
        "gate_outcome": ADMITTED,
        "qualification_evidence_ids": bound_evidence,
        "source_run_id": bound_source_run,
        "target_run_id": run,
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def verify_gate_receipt(receipt: Mapping[str, Any]) -> str:
    """Re-derive a gate receipt's digest, or refuse the receipt.

    A receipt whose digest does not re-derive from the fields it publishes is not
    the decision the gate produced, whatever it says about itself.
    """
    document = dict(_require_mapping(receipt, "receipt"))
    claimed = document.get("receipt_hash")
    derived = hash_excluding(document, "receipt_hash")
    if claimed != derived:
        _fail(
            "GATE_RECEIPT_DRIFT",
            "the gate receipt does not re-derive its own digest",
            {"claimed": claimed, "derived": derived},
        )
    return derived
