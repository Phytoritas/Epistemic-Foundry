"""Scientific mutation, typed crossover, mechanism and Aporia operators (R05).

The typed registry evolution proposes through: which genes an operator may
touch on which genome kind, what inference strength it claims, and the descent
record every application has to produce before the child counts as a candidate.
"""

from __future__ import annotations

from .operators import (
    ARGUMENT_KIND,
    DEFEASIBLE_MODE,
    EPISTEMIC_MODES,
    FINDING_CODES,
    GENERATION_STEP,
    LINEAGE_KIND,
    STRICT_MODE,
    GenomeKindContract,
    MutationOperatorError,
    ScientificOperator,
    aporia_citation_shape,
    apply_scientific_mutation,
    apply_typed_crossover,
    genome_kind_contracts,
    genome_kind_of,
    genome_properties,
    immutable_fields,
    kind_contract,
    mechanism_agreement,
    operator_registry,
    operators_for,
    require_aporia_citation,
    resolve_operator,
)

__all__ = [
    "ARGUMENT_KIND",
    "DEFEASIBLE_MODE",
    "EPISTEMIC_MODES",
    "FINDING_CODES",
    "GENERATION_STEP",
    "GenomeKindContract",
    "LINEAGE_KIND",
    "MutationOperatorError",
    "STRICT_MODE",
    "ScientificOperator",
    "aporia_citation_shape",
    "apply_scientific_mutation",
    "apply_typed_crossover",
    "genome_kind_contracts",
    "genome_kind_of",
    "genome_properties",
    "immutable_fields",
    "kind_contract",
    "mechanism_agreement",
    "operator_registry",
    "operators_for",
    "require_aporia_citation",
    "resolve_operator",
]
