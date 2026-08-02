"""Fixtures for the J05 operator registry suites.

Every document here is one the canonical schema accepts, because the engine
validates real documents: a fixture the schema would refuse would test the
fixture rather than the registry.  Every status and operator class is read out
of the schema that declares it rather than typed, so a canonical change breaks
these fixtures instead of letting them drift.

The active prompt genome is built by taking a constructed genome — which the
lifecycle always births quarantined — and re-sealing it at the active status.
That is deliberate: J05 does not own the transition out of quarantine, so the
fixture performs it explicitly rather than pretending the engine can.
"""

from __future__ import annotations

from typing import Any, Sequence

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.operators.v4_j05 import (
    OPERATOR_SPEC_KIND,
    PROMPT_GENOME_KIND,
    active_prompt_status,
    build_prompt_genome,
    proposal_status_vocabulary,
    propose_prompt_genome_change,
)

ACTIVATED_AT = "2026-08-02T01:00:00.000Z"
SOURCE_RUN = "ERUN-J05-1"
TARGET_RUN = "ERUN-J05-2"
PLAN = "QP-J05-1"
EVIDENCE = ("QUAL-J05-1", "QUAL-J05-2")

#: The first declared operator class and risk class, read from the schema.
_OPERATOR_SPEC = default_registry().document(OPERATOR_SPEC_KIND)
OPERATOR_CLASS = _OPERATOR_SPEC["properties"]["operator_class"]["enum"][0]
RISK_CLASS = _OPERATOR_SPEC["properties"]["risk_class"]["enum"][0]

#: A genome kind inside the sealed search space that is not the prompt genome,
#: used for operators that touch no prompt at all.
_GENOME_KINDS = default_registry().names()
HYPOTHESIS_KIND = "hypothesis-genome"

#: The third declared proposal status: the one a released proposal carries.
APPROVED_POSITION = 2

A_HASH = "sha256:" + "a" * 64


def prompt_genome(
    prompt_genome_id: str = "PG-J05-1",
    *,
    template: str = "propose one bounded variant of {claim} and name its falsifier",
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid prompt genome, born quarantined by the lifecycle."""
    arguments: dict[str, Any] = {
        "prompt_genome_id": prompt_genome_id,
        "task_class": "hypothesis_mutation",
        "template": template,
        "forbidden_authorities": ["evaluator_bundle", "holdout_manifest"],
        "allowed_context_classes": ["candidate_summary"],
    }
    arguments.update(overrides)
    return build_prompt_genome(**arguments)


def reseal(document: dict[str, Any], hash_field: str, **changes: Any) -> dict[str, Any]:
    """Apply `changes` and re-derive the document's own digest.

    Used where a fixture stands in for a process J05 does not own — releasing a
    proposal from quarantine, or a genome reaching the active surface.
    """
    sealed = {
        key: value
        for key, value in {**document, **changes}.items()
        if key != hash_field
    }
    sealed[hash_field] = hash_excluding(sealed, hash_field)
    return sealed


def active_genome(
    prompt_genome_id: str = "PG-J05-1", **overrides: Any
) -> dict[str, Any]:
    """A prompt genome on a run's active surface."""
    return reseal(
        prompt_genome(prompt_genome_id, **overrides),
        "prompt_hash",
        status=active_prompt_status(),
    )


def change_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "source_genome": active_genome(),
        "changes": {"template": "propose two bounded variants of {claim}"},
        "proposed_prompt_genome_id": "PG-J05-2",
        "motivation": "the current template explores one mechanism per candidate",
        "risk_analysis": ["a second variant may widen scope beyond the falsifier"],
        "qualification_plan_id": PLAN,
        "target_run_id": TARGET_RUN,
        "active_prompt_genome_ids": ["PG-J05-1"],
        "proposal_id": "PMP-J05-1",
    }
    arguments.update(overrides)
    return arguments


def change(**overrides: Any) -> dict[str, Any]:
    """One proposed prompt change, quarantined and gated."""
    return propose_prompt_genome_change(**change_arguments(**overrides))


def quarantined_proposal(**overrides: Any) -> dict[str, Any]:
    """The proposal the quarantine module built for that change."""
    return change(**overrides)["proposal"]


def released_proposal(**overrides: Any) -> dict[str, Any]:
    """The same proposal after an independent qualification released it."""
    return reseal(
        quarantined_proposal(**overrides),
        "proposal_hash",
        status=proposal_status_vocabulary()[APPROVED_POSITION],
    )


def operator_spec(
    operator_id: str = "MOP-J05-PROMPT",
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
    operator_id: str = "MOP-J05-HYPOTHESIS", **overrides: Any
) -> dict[str, Any]:
    """An operator that touches no prompt genome at all."""
    return operator_spec(operator_id, genome_kind=HYPOTHESIS_KIND, **overrides)


def declared_parameters() -> dict[str, Any]:
    """A small, genuinely enforceable parameter contract."""
    return {
        "candidate_count": {"type": "integer", "minimum": 1, "maximum": 8},
        "preserve_falsifier": {"type": "boolean"},
    }


def arguments() -> dict[str, Any]:
    return {"candidate_count": 2, "preserve_falsifier": True}


def activation_arguments(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "proposal": released_proposal(),
        "source_run_id": SOURCE_RUN,
        "target_run_id": TARGET_RUN,
        "qualification_evidence_ids": list(EVIDENCE),
        "activated_at": ACTIVATED_AT,
        "operator_id": "MOP-J05-PROMPT",
        "activation_id": "PGA-J05-1",
    }
    values.update(overrides)
    return values
