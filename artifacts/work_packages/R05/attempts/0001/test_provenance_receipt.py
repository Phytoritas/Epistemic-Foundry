"""provenance_and_receipt_audit — every application is a self-proving receipt.

An operator that scored or promoted anything would be outside R05's remit, so
what R05 must instead prove is that each application re-derives byte for byte
from its own published fields: the record hash covers the record, the child hash
covers the child, the parent hashes cover the parents, and replaying the same
call with the same identifiers reproduces the identical receipt.  There is no
clock and no random draw on the identified path, so determinism here is a
property of the module rather than of the environment it ran in.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.reasoning.v4_r05 import (
    apply_scientific_mutation,
    apply_typed_crossover,
)
from fixtures import (
    OBJECTION,
    citation,
    crossover_arguments,
    genome,
    mutation_arguments,
)


def test_the_record_hash_covers_the_record() -> None:
    record = apply_scientific_mutation(**mutation_arguments())

    assert record["record_hash"] == hash_excluding(record, "record_hash")


def test_the_child_hash_covers_the_child() -> None:
    record = apply_scientific_mutation(**mutation_arguments())

    assert record["child_hash"] == sha256_of_payload(record["child"])


def test_the_parent_hashes_cover_the_parents() -> None:
    parent = genome()
    record = apply_scientific_mutation(**mutation_arguments(parent=parent))

    assert record["parent_genome_hashes"] == [sha256_of_payload(parent)]
    assert record["parent_genome_ids"] == [parent["genome_id"]]


def test_an_identified_mutation_replays_byte_for_byte() -> None:
    first = apply_scientific_mutation(**mutation_arguments())
    second = apply_scientific_mutation(**mutation_arguments())

    assert first == second
    assert first["record_hash"] == second["record_hash"]


def test_an_identified_crossover_replays_byte_for_byte() -> None:
    first = apply_typed_crossover(**crossover_arguments())
    second = apply_typed_crossover(**crossover_arguments())

    assert first == second
    assert first["child_hash"] == second["child_hash"]
    assert first["lineage"] == second["lineage"]


def test_a_crossover_receipt_names_both_parents_and_its_report() -> None:
    record = apply_typed_crossover(**crossover_arguments())

    assert record["parent_genome_ids"] == ["HG-1", "HG-2"]
    assert record["parent_genome_hashes"] == [
        sha256_of_payload(genome("HG-1")),
        sha256_of_payload(genome("HG-2", lineage_id="LIN-R05-2")),
    ]
    assert record["crossover_report_id"] == "CCR-R05-1"


def test_an_aporia_receipt_records_the_question_it_answered() -> None:
    record = apply_scientific_mutation(
        **mutation_arguments(
            operator_id="aporia-response",
            changes={"uncertainty_notes": ["a vapour pressure deficit confound"]},
            aporia_citation=citation(),
        )
    )

    assert record["aporia_open_question_ids"] == [OBJECTION]
    assert record["record_hash"] == hash_excluding(record, "record_hash")


def test_the_ancestry_hashes_are_sorted_for_a_stable_receipt() -> None:
    record = apply_typed_crossover(**crossover_arguments())
    ancestors = record["lineage"]["ancestor_hashes"]

    assert ancestors == sorted(ancestors)


def test_the_application_never_mutates_the_parent_it_was_given() -> None:
    parent = genome()
    before = copy.deepcopy(parent)

    apply_scientific_mutation(**mutation_arguments(parent=parent))

    assert parent == before
