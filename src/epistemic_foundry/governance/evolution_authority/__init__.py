"""A05 evolution-authority gate registry and promotion-workflow binding."""

from .nodes import NODE_ENTRYPOINTS, resolve_node_executor
from .registry import (
    ADVISORY_LLM_OUTPUT_SCHEMAS,
    CONDITIONAL_RESOLVED_REF_KEYS,
    EVOLUTION_PROMOTION_WORKFLOW_ID,
    EXPECTED_PROMOTION_NODE_COUNT,
    GATE_APPLICABILITY,
    GATE_NODE_BINDINGS,
    PROMOTION_COMMIT_CAPABILITY,
    PROMOTION_WORKFLOW_STEPS,
    REQUIRED_RESOLVED_REF_KEYS,
    RESOLVED_REF_TUPLE_FIELDS,
    EvolutionAuthorityError,
    applicability,
    resolve_references,
    verify_approval_independence,
    verify_attestor_independence,
    verify_evolution_chamber_binding,
    verify_promotion_workflow_binding,
)

__all__ = [
    "ADVISORY_LLM_OUTPUT_SCHEMAS",
    "CONDITIONAL_RESOLVED_REF_KEYS",
    "EVOLUTION_PROMOTION_WORKFLOW_ID",
    "EXPECTED_PROMOTION_NODE_COUNT",
    "GATE_APPLICABILITY",
    "GATE_NODE_BINDINGS",
    "NODE_ENTRYPOINTS",
    "PROMOTION_COMMIT_CAPABILITY",
    "PROMOTION_WORKFLOW_STEPS",
    "REQUIRED_RESOLVED_REF_KEYS",
    "RESOLVED_REF_TUPLE_FIELDS",
    "EvolutionAuthorityError",
    "applicability",
    "resolve_references",
    "resolve_node_executor",
    "verify_approval_independence",
    "verify_attestor_independence",
    "verify_evolution_chamber_binding",
    "verify_promotion_workflow_binding",
]
