"""schema_and_type_check — the registry is bound to the canonical schemas.

Behaviour tests drive operators; this file checks the shape they are published
under.  Every gene an operator may touch is a property the canonical genome
schema still declares, every kind it targets is one the sealed C05 index still
lists as mutable, and every mode it claims is one of the Aporia Engine's two
edge partitions.  Because the registry re-derives all of this on each call
rather than caching it, a schema rename, a search-space change or an edge-type
change closes the registry here instead of letting an operator edit a field the
contract no longer declares.
"""

from __future__ import annotations

from epistemic_foundry.intake.v4_i05 import mutable_genome_kinds
from epistemic_foundry.reasoning.v4_r05 import (
    DEFEASIBLE_MODE,
    EPISTEMIC_MODES,
    FINDING_CODES,
    STRICT_MODE,
    genome_kind_contracts,
    genome_kind_of,
    genome_properties,
    immutable_fields,
    kind_contract,
    operator_registry,
)
from fixtures import challenge_genome, experiment_genome, genome


def test_every_declared_gene_is_a_property_of_its_genome_schema() -> None:
    registry = operator_registry()
    for operator in registry.values():
        properties = genome_properties(operator.genome_kind)
        undeclared = sorted(set(operator.gene_fields) - set(properties))
        assert not undeclared, (operator.operator_id, undeclared)


def test_every_operator_targets_a_kind_in_the_sealed_search_space() -> None:
    contracts = genome_kind_contracts()
    mutable = set(mutable_genome_kinds())
    assert set(contracts) <= mutable
    for operator in operator_registry().values():
        assert operator.genome_kind in contracts


def test_every_operator_declares_one_of_the_two_edge_partitions() -> None:
    assert EPISTEMIC_MODES == (STRICT_MODE, DEFEASIBLE_MODE)
    assert STRICT_MODE and DEFEASIBLE_MODE
    assert not (STRICT_MODE & DEFEASIBLE_MODE)
    for operator in operator_registry().values():
        assert operator.epistemic_mode in EPISTEMIC_MODES


def test_no_operator_declares_an_identity_lineage_or_authority_field() -> None:
    for operator in operator_registry().values():
        reserved = immutable_fields(kind_contract(operator.genome_kind))
        assert not (set(operator.gene_fields) & reserved), operator.operator_id


def test_the_kind_of_a_document_is_derived_by_validating_it() -> None:
    assert genome_kind_of(genome()) == "hypothesis-genome"
    assert genome_kind_of(challenge_genome()) == "challenge-genome"
    assert genome_kind_of(experiment_genome()) == "experiment-genome"


def test_the_prompt_genome_kind_carries_no_ordinary_operator() -> None:
    # A co-evolved mutation prompt must be qualified in quarantine before it may
    # be applied, so R05 declares no operator that would edit one on this path.
    assert "prompt-genome" not in genome_kind_contracts()
    for operator in operator_registry().values():
        assert operator.genome_kind != "prompt-genome"


def test_each_declared_kind_names_fields_its_schema_declares() -> None:
    for kind, contract in genome_kind_contracts().items():
        properties = genome_properties(kind)
        for field in (
            contract.identity_field,
            contract.mechanism_field,
            contract.lineage_field,
            contract.revision_field,
            contract.stamp_field,
        ):
            if field is not None:
                assert field in properties, (kind, field)


def test_the_finding_codes_are_documented_and_nonempty() -> None:
    assert FINDING_CODES
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(reason, str) and reason.strip()
