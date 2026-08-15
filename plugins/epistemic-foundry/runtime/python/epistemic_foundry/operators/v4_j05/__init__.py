"""Typed mutation-operator registry, prompt genomes and quarantine workflow (J05).

What may be registered as a mutation operator, what a prompt genome is allowed
to become, and what has to be true before a prompt change may act on a run.
The registry types and refuses; the quarantine and the S05 gate decide.
"""

from __future__ import annotations

from .declarations import (
    ACTIVE_POSITION,
    FINDING_CODES,
    FIRST_VERSION,
    OPERATOR_SPEC_KIND,
    PROMPT_GENOME_KIND,
    PROMPT_PROPOSAL_KIND,
    QUARANTINED_POSITION,
    MutationOperatorError,
    active_prompt_status,
    mutable_genome_kinds,
    mutable_prompt_genome_kind,
    operator_contract,
    prompt_genome_contract,
    prompt_proposal_contract,
    prompt_status_vocabulary,
    proposal_status_vocabulary,
    quarantined_prompt_status,
    require_sealed_digest,
)
from .prompt_workflow import (
    GOVERNANCE_WORKFLOW,
    LIFECYCLE_FIELDS,
    RETROACTIVITY_NODE,
    SOURCE_RUN_FIELD,
    build_activation_record,
    build_prompt_genome,
    governance_retroactivity_node,
    propose_prompt_genome_change,
    verify_activation_record,
)
from .registry import MutationOperatorRegistry, operator_genome_kinds

__all__ = [
    "ACTIVE_POSITION",
    "FINDING_CODES",
    "FIRST_VERSION",
    "GOVERNANCE_WORKFLOW",
    "LIFECYCLE_FIELDS",
    "MutationOperatorError",
    "MutationOperatorRegistry",
    "OPERATOR_SPEC_KIND",
    "PROMPT_GENOME_KIND",
    "PROMPT_PROPOSAL_KIND",
    "QUARANTINED_POSITION",
    "RETROACTIVITY_NODE",
    "SOURCE_RUN_FIELD",
    "active_prompt_status",
    "build_activation_record",
    "build_prompt_genome",
    "governance_retroactivity_node",
    "mutable_genome_kinds",
    "mutable_prompt_genome_kind",
    "operator_contract",
    "operator_genome_kinds",
    "prompt_genome_contract",
    "prompt_proposal_contract",
    "prompt_status_vocabulary",
    "proposal_status_vocabulary",
    "propose_prompt_genome_change",
    "quarantined_prompt_status",
    "require_sealed_digest",
    "verify_activation_record",
]
