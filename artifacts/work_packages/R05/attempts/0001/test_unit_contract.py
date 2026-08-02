"""unit_and_contract_tests — the registry works the way R05 claims it works.

A declared operator edits the genes it declared and nothing else; the child it
produces is a real candidate of the same kind; the lineage names its parents and
sits exactly one generation deeper; a typed splice inherits from a second parent
whose mechanism already agrees; and an Aporia operator answers a question some
argument graph actually left open.
"""

from __future__ import annotations

from epistemic_foundry.reasoning.v4_r05 import (
    GENERATION_STEP,
    apply_scientific_mutation,
    apply_typed_crossover,
    genome_kind_of,
    mechanism_agreement,
    operator_registry,
    operators_for,
    require_aporia_citation,
    resolve_operator,
)
from fixtures import (
    CHILD_AT,
    ISLAND,
    LINE,
    OBJECTION,
    challenge_genome,
    citation,
    compatibility_report,
    crossover_arguments,
    experiment_genome,
    genome,
    lineage,
    mutation_arguments,
)


def test_a_declared_mutation_changes_only_the_gene_it_declares() -> None:
    result = apply_scientific_mutation(**mutation_arguments())

    assert result["child"]["mechanism_graph_id"] == "MG-2"
    assert result["operator_id"] == "mechanism-refinement"
    assert "mechanism_graph_id" in result["changed_fields"]
    for field in ("scope_vector_id", "canonical_claim", "falsifier_gene_ids"):
        assert result["child"][field] == genome()[field]


def test_the_engine_names_the_child_and_counts_its_revision() -> None:
    result = apply_scientific_mutation(**mutation_arguments())

    assert result["child"]["genome_id"] == "HG-CHILD"
    assert result["child"]["revision"] == genome()["revision"] + GENERATION_STEP
    assert result["child"]["created_at"] == CHILD_AT


def test_the_child_lineage_records_its_parent_and_one_more_generation() -> None:
    result = apply_scientific_mutation(**mutation_arguments())
    descent = result["lineage"]

    assert descent["candidate_id"] == "HG-CHILD"
    assert descent["parent_ids"] == ["HG-1"]
    assert descent["crossover_parent_ids"] == []
    assert descent["mutation_operator_ids"] == ["mechanism-refinement"]
    assert descent["generation"] == lineage()["generation"] + GENERATION_STEP
    assert descent["island_id"] == ISLAND
    assert descent["lineage_id"] == LINE


def test_the_child_keeps_the_line_and_the_authority_of_its_parent() -> None:
    """Evolution proposes; it never relabels its own status or ancestry."""
    parent = genome()

    result = apply_scientific_mutation(**mutation_arguments())

    assert result["child"]["lineage_id"] == parent["lineage_id"]
    assert result["child"]["status"] == parent["status"]
    assert result["child"]["provenance_hash"] == parent["provenance_hash"]


def test_the_ancestry_accumulates_the_parent_document() -> None:
    first = apply_scientific_mutation(**mutation_arguments())

    second = apply_scientific_mutation(
        **mutation_arguments(
            parent=first["child"],
            parent_lineage=first["lineage"],
            changes={"mechanism_graph_id": "MG-3"},
            child_genome_id="HG-GRANDCHILD",
        )
    )

    assert set(first["lineage"]["ancestor_hashes"]) < set(
        second["lineage"]["ancestor_hashes"]
    )
    assert first["child_hash"] in second["lineage"]["ancestor_hashes"]
    assert second["lineage"]["generation"] == first["lineage"]["generation"] + 1


def test_a_strict_operator_may_only_narrow_what_the_parent_asserts() -> None:
    parent = genome()

    result = apply_scientific_mutation(
        **mutation_arguments(
            operator_id="prediction-restriction",
            changes={"prediction_gene_ids": parent["prediction_gene_ids"][:1]},
        )
    )

    assert result["child"]["prediction_gene_ids"] == parent["prediction_gene_ids"][:1]
    assert result["epistemic_mode"] == sorted(
        resolve_operator("prediction-restriction").epistemic_mode
    )


def test_an_aporia_operator_answers_a_question_the_graph_left_open() -> None:
    result = apply_scientific_mutation(
        **mutation_arguments(
            operator_id="aporia-response",
            changes={"uncertainty_notes": ["a vapour pressure deficit confound"]},
            aporia_citation=citation(),
        )
    )

    assert result["aporia_open_question_ids"] == [OBJECTION]
    assert result["child"]["uncertainty_notes"] == [
        "a vapour pressure deficit confound"
    ]


def test_the_cited_graph_is_read_through_the_aporia_engines_accounting() -> None:
    graph, cited = require_aporia_citation(citation(), subject_id="HG-1")

    assert cited == (OBJECTION,)
    assert graph["unresolved_objection_ids"] == [OBJECTION]


def test_a_typed_splice_inherits_from_the_second_parent() -> None:
    result = apply_typed_crossover(**crossover_arguments())

    assert result["child"]["falsifier_gene_ids"] == genome("HG-2")["falsifier_gene_ids"]
    assert result["child"]["mechanism_graph_id"] == genome("HG-1")["mechanism_graph_id"]
    assert result["parent_genome_ids"] == ["HG-1", "HG-2"]


def test_a_spliced_lineage_records_both_parents_below_the_deeper_one() -> None:
    result = apply_typed_crossover(**crossover_arguments())
    descent = result["lineage"]

    assert descent["parent_ids"] == ["HG-1", "HG-2"]
    assert descent["crossover_parent_ids"] == ["HG-1", "HG-2"]
    assert descent["generation"] == 4
    assert descent["lineage_id"] == LINE


def test_mechanism_agreement_is_read_from_the_genomes_themselves() -> None:
    agreed = mechanism_agreement(
        [genome("HG-1"), genome("HG-2")], genome_kind=genome_kind_of(genome())
    )

    assert agreed == genome()["mechanism_graph_id"]


def test_the_kind_of_a_document_is_derived_by_validation() -> None:
    assert genome_kind_of(genome()) == "hypothesis-genome"
    assert genome_kind_of(challenge_genome()) == "challenge-genome"
    assert genome_kind_of(experiment_genome()) == "experiment-genome"


def test_every_declared_kind_publishes_its_own_operators() -> None:
    registry = operator_registry()

    for kind in ("hypothesis-genome", "challenge-genome", "experiment-genome"):
        published = operators_for(kind)
        assert published
        assert {operator.operator_id for operator in published} <= set(registry)
        assert all(operator.genome_kind == kind for operator in published)


def test_a_challenge_genome_mutates_under_its_own_operator() -> None:
    result = apply_scientific_mutation(
        operator_id="challenge-retargeting",
        parent=challenge_genome(),
        parent_lineage=lineage("CG-1"),
        changes={"target_genome_id": "HG-9"},
        created_at=CHILD_AT,
        child_genome_id="CG-CHILD",
    )

    assert result["child"]["challenge_genome_id"] == "CG-CHILD"
    assert result["child"]["target_genome_id"] == "HG-9"
    assert result["genome_kind"] == "challenge-genome"


def test_an_experiment_genome_mutates_under_its_own_operator() -> None:
    result = apply_scientific_mutation(
        operator_id="design-outcome-extension",
        parent=experiment_genome(),
        parent_lineage=lineage("EG-1"),
        changes={"outcomes": ["stomatal conductance", "leaf water potential"]},
        created_at=CHILD_AT,
        child_genome_id="EG-CHILD",
    )

    assert result["child"]["experiment_genome_id"] == "EG-CHILD"
    assert len(result["child"]["outcomes"]) == 2
    assert result["genome_kind"] == "experiment-genome"


def test_the_compatibility_report_decision_is_the_chambers_own() -> None:
    report = compatibility_report()

    assert report["decision"] == "ALLOW"
    assert report["candidate_ids"] == ["HG-1", "HG-2"]
