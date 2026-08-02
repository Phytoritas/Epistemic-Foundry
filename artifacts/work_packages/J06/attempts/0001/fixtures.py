"""Fixtures for the J06 integration-gate suites.

Every document here is one the canonical schema accepts and every sealed record
is built through the module that owns it: the prompt genome, proposal and
operator through the J05 lifecycle, the budget envelope through the budget
module, and the context assembly manifest as a schema-valid document.  A fixture
the schema or the sealed builders would refuse tests the fixture rather than the
gate.

The released proposal is a quarantined proposal re-sealed at the approved status,
exactly as J05's own suites do it: J06 does not own the transition out of
quarantine, so the fixture performs it explicitly rather than pretending the gate
can.
"""

from __future__ import annotations

from typing import Any, Sequence

from epistemic_foundry.budgets.envelope import build_budget_envelope
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.operators.v4_j05 import (
    OPERATOR_SPEC_KIND,
    PROMPT_GENOME_KIND,
    MutationOperatorRegistry,
    active_prompt_status,
    build_prompt_genome,
    proposal_status_vocabulary,
    propose_prompt_genome_change,
)

SOURCE_RUN = "ERUN-J06-1"
TARGET_RUN = "ERUN-J06-2"
ACTIVATED_AT = "2026-08-02T01:00:00.000Z"
CREATED_AT = "2026-08-02T00:00:00Z"
PLAN = "QP-J06-1"
EVIDENCE = ("QUAL-J06-1", "QUAL-J06-2")

_OPERATOR_SPEC = default_registry().document(OPERATOR_SPEC_KIND)
OPERATOR_CLASS = _OPERATOR_SPEC["properties"]["operator_class"]["enum"][0]
RISK_CLASS = _OPERATOR_SPEC["properties"]["risk_class"]["enum"][0]

#: The third declared proposal status: the one a released proposal carries.
APPROVED_POSITION = 2

#: A genome kind inside the sealed search space that is not the prompt genome.
HYPOTHESIS_KIND = "hypothesis-genome"

A_HASH = "sha256:" + "a" * 64
PROMPT_OPERATOR_ID = "MOP-J06-PROMPT"
HYPOTHESIS_OPERATOR_ID = "MOP-J06-HYPOTHESIS"


def reseal(document: dict[str, Any], hash_field: str, **changes: Any) -> dict[str, Any]:
    """Apply `changes` and re-derive the document's own digest.

    Used where a fixture stands in for a process J06 does not own — releasing a
    proposal from quarantine, or a genome reaching the active surface.
    """
    sealed = {
        key: value
        for key, value in {**document, **changes}.items()
        if key != hash_field
    }
    sealed[hash_field] = hash_excluding(sealed, hash_field)
    return sealed


def prompt_genome(
    prompt_genome_id: str = "PG-J06-1", **overrides: Any
) -> dict[str, Any]:
    """A schema-valid prompt genome, born quarantined by the lifecycle."""
    arguments: dict[str, Any] = {
        "prompt_genome_id": prompt_genome_id,
        "task_class": "hypothesis_mutation",
        "template": "propose one bounded variant of {claim} and name its falsifier",
        "forbidden_authorities": ["evaluator_bundle", "holdout_manifest"],
        "allowed_context_classes": ["candidate_summary"],
    }
    arguments.update(overrides)
    return build_prompt_genome(**arguments)


def active_genome(
    prompt_genome_id: str = "PG-J06-1", **overrides: Any
) -> dict[str, Any]:
    """A prompt genome on a run's active surface."""
    return reseal(
        prompt_genome(prompt_genome_id, **overrides),
        "prompt_hash",
        status=active_prompt_status(),
    )


def change(**overrides: Any) -> dict[str, Any]:
    """One proposed prompt change, quarantined and gated by the J05 lifecycle."""
    arguments: dict[str, Any] = {
        "source_genome": active_genome(),
        "changes": {"template": "propose two bounded variants of {claim}"},
        "proposed_prompt_genome_id": "PG-J06-2",
        "motivation": "the current template explores one mechanism per candidate",
        "risk_analysis": ["a second variant may widen scope beyond the falsifier"],
        "qualification_plan_id": PLAN,
        "target_run_id": TARGET_RUN,
        "active_prompt_genome_ids": ["PG-J06-1"],
        "proposal_id": "PMP-J06-1",
    }
    arguments.update(overrides)
    return propose_prompt_genome_change(**arguments)


def quarantined_proposal(**overrides: Any) -> dict[str, Any]:
    """The proposal the quarantine module built for that change, still inert."""
    return change(**overrides)["proposal"]


def released_proposal(**overrides: Any) -> dict[str, Any]:
    """The same proposal after an independent qualification released it."""
    return reseal(
        quarantined_proposal(**overrides),
        "proposal_hash",
        status=proposal_status_vocabulary()[APPROVED_POSITION],
    )


def operator_spec(
    operator_id: str = PROMPT_OPERATOR_ID,
    *,
    genome_kind: str = PROMPT_GENOME_KIND,
    input_genome_types: Sequence[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid mutation operator specification."""
    document: dict[str, Any] = {
        "operator_id": operator_id,
        "version": "1.0.0",
        "operator_class": OPERATOR_CLASS,
        "input_genome_types": list(
            input_genome_types if input_genome_types is not None else [genome_kind]
        ),
        "output_genome_type": genome_kind,
        "preconditions": ["the source genome is sealed"],
        "preserved_invariants": ["EF4-I55"],
        "required_audits": ["prompt_genome_auditor"],
        "prompt_ref": "prompts/prompt_genome_auditor.md",
        "risk_class": RISK_CLASS,
        "operator_hash": A_HASH,
    }
    document.update(overrides)
    return document


def hypothesis_operator_spec(
    operator_id: str = HYPOTHESIS_OPERATOR_ID, **overrides: Any
) -> dict[str, Any]:
    """An operator that touches no prompt genome at all."""
    return operator_spec(operator_id, genome_kind=HYPOTHESIS_KIND, **overrides)


def declared_parameters() -> dict[str, Any]:
    """A small, genuinely enforceable parameter contract."""
    return {"candidate_count": {"type": "integer", "minimum": 1, "maximum": 8}}


def prompt_registry(**overrides: Any) -> MutationOperatorRegistry:
    """A registry holding one prompt operator with a released proposal."""
    registry = MutationOperatorRegistry()
    registry.register(
        spec=operator_spec(),
        declared_parameters=declared_parameters(),
        proposal=overrides.get("proposal", released_proposal()),
    )
    return registry


def quarantined_registry() -> MutationOperatorRegistry:
    """A registry whose prompt operator still holds an inert proposal."""
    return prompt_registry(proposal=quarantined_proposal())


def hypothesis_registry() -> MutationOperatorRegistry:
    """A registry holding one operator that touches no prompt genome."""
    registry = MutationOperatorRegistry()
    registry.register(
        spec=hypothesis_operator_spec(),
        declared_parameters=declared_parameters(),
    )
    return registry


def budget_envelope(**overrides: Any) -> dict[str, Any]:
    """A hard-metered budget that actually bounds token spend."""
    arguments: dict[str, Any] = {
        "enforcement": "HARD_METERED",
        "hard_limits": {"tokens": 10_000},
        "soft_cost_currency": "USD",
        "soft_cost_amount": 1.0,
        "metering_authority": "MA-J06-1",
        "breach_policy": "CANCEL",
        "budget_id": "BE-J06-1",
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return build_budget_envelope(**arguments)


def unmetered_budget() -> dict[str, Any]:
    """A budget whose label describes an expectation rather than a bound."""
    return budget_envelope(
        enforcement="SOFT_ESTIMATE",
        hard_limits={"tokens": None},
        breach_policy="WARN",
        budget_id="BE-J06-SOFT",
    )


def context_manifest(
    *,
    instruction_tokens: int = 100,
    evidence_tokens: int = 200,
    tool_tokens: int = 50,
    total_tokens: int | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid context assembly manifest with consistent token accounting.

    ``total_tokens`` defaults to the sum of the three components, which is the
    only figure the gate will admit; a caller passes it explicitly to build the
    inconsistent-accounting fixture.
    """
    resolved_total = (
        instruction_tokens + evidence_tokens + tool_tokens
        if total_tokens is None
        else total_tokens
    )
    document: dict[str, Any] = {
        "manifest_id": "CAM-J06-1",
        "run_id": TARGET_RUN,
        "node_id": "NODE-J06-1",
        "agent_role": "bounded_maker",
        "evidence_ids": [],
        "excluded_evidence_ids": [],
        "query_hashes": [],
        "ranking_version": "1.0.0",
        "ontology_version": "1.0.0",
        "prompt_hash": A_HASH,
        "model_identifier": "model-under-test",
        "model_parameters": {},
        "created_at": CREATED_AT,
        "source_trust_labels": {},
        "injection_scan_report_id": None,
        "redaction_policy_version": "1.0.0",
        "token_accounting": {
            "instruction_tokens": instruction_tokens,
            "evidence_tokens": evidence_tokens,
            "tool_tokens": tool_tokens,
            "total_tokens": resolved_total,
        },
        "context_hash": A_HASH,
        "ordering_strategy": "relevance",
    }
    document.update(overrides)
    return document


def admission_arguments(**overrides: Any) -> dict[str, Any]:
    """One fully-identified admission of the prompt operator, so it replays."""
    arguments: dict[str, Any] = {
        "registry": prompt_registry(),
        "operator_id": PROMPT_OPERATOR_ID,
        "target_run_id": TARGET_RUN,
        "context_manifest": context_manifest(),
        "budget_envelope": budget_envelope(),
        "source_run_id": SOURCE_RUN,
        "qualification_evidence_ids": list(EVIDENCE),
        "activated_at": ACTIVATED_AT,
        "gate_decision_id": "J06GATE-1",
    }
    arguments.update(overrides)
    return arguments


def hypothesis_admission_arguments(**overrides: Any) -> dict[str, Any]:
    """One admission of the non-prompt operator: registration plus budget only."""
    arguments: dict[str, Any] = {
        "registry": hypothesis_registry(),
        "operator_id": HYPOTHESIS_OPERATOR_ID,
        "target_run_id": TARGET_RUN,
        "context_manifest": context_manifest(),
        "budget_envelope": budget_envelope(),
        "gate_decision_id": "J06GATE-HYP-1",
    }
    arguments.update(overrides)
    return arguments
