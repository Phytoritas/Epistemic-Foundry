"""negative_and_adversarial_tests — every refusal fires for the stated reason.

The registry's value is in what it will not do.  Each test here drives one
declared refusal and asserts the operator raises with exactly the finding code
that names it, so a future change that silences a guard or renames a code fails
here rather than shipping a candidate that edited more than it admitted, forged
its own descent, spliced across contracts, or answered a contradiction nobody
recorded.  The most specific refusal wins, so tests that could trip two guards
assert the one the module documents as ordered first.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.reasoning.v4_r05 import (
    MutationOperatorError,
    apply_scientific_mutation,
    apply_typed_crossover,
    require_aporia_citation,
    resolve_operator,
)
from fixtures import (
    OTHER_LINE,
    argument_graph,
    challenge_genome,
    citation,
    compatibility_report,
    crossover_arguments,
    genome,
    lineage,
    mutation_arguments,
)


def _run_refused(code: str, call) -> None:
    with pytest.raises(MutationOperatorError) as caught:
        call()
    assert caught.value.code == code, (
        f"expected {code}, got {caught.value.code}: {caught.value}"
    )


# --- single-parent mutation guards ---------------------------------------


def test_an_undeclared_gene_is_refused() -> None:
    _run_refused(
        "UNDECLARED_FIELD_TOUCHED",
        lambda: apply_scientific_mutation(
            **mutation_arguments(changes={"scope_vector_id": "SV-9"})
        ),
    )


def test_renaming_the_child_itself_is_refused() -> None:
    _run_refused(
        "IDENTITY_FIELD_IMMUTABLE",
        lambda: apply_scientific_mutation(
            **mutation_arguments(changes={"genome_id": "HG-FORGED"})
        ),
    )


def test_rewriting_the_line_it_descends_from_is_refused() -> None:
    _run_refused(
        "LINEAGE_FIELD_IMMUTABLE",
        lambda: apply_scientific_mutation(
            **mutation_arguments(changes={"lineage_id": OTHER_LINE})
        ),
    )


def test_touching_an_authority_field_is_refused() -> None:
    # ``status`` carries gate authority; it is neither the identity nor the
    # lineage field, so the authority guard is the one that must fire.
    _run_refused(
        "AUTHORITY_FIELD_TOUCHED",
        lambda: apply_scientific_mutation(
            **mutation_arguments(changes={"status": "PROMOTED"})
        ),
    )


def test_an_edit_that_changes_no_declared_gene_is_refused() -> None:
    _run_refused(
        "MUTATION_EMPTY",
        lambda: apply_scientific_mutation(
            **mutation_arguments(changes={"mechanism_graph_id": "MG-1"})
        ),
    )


def test_a_strict_operator_may_not_widen_what_the_parent_asserts() -> None:
    parent = genome()
    _run_refused(
        "STRICT_INFERENCE_VIOLATED",
        lambda: apply_scientific_mutation(
            **mutation_arguments(
                operator_id="prediction-restriction",
                changes={
                    "prediction_gene_ids": [*parent["prediction_gene_ids"], "PG-NEW"]
                },
            )
        ),
    )


def test_a_strict_budget_operator_may_not_raise_the_budget() -> None:
    _run_refused(
        "STRICT_INFERENCE_VIOLATED",
        lambda: apply_scientific_mutation(
            **mutation_arguments(
                operator_id="budget-simplification",
                changes={"complexity_budget": genome()["complexity_budget"] + 1},
            )
        ),
    )


def test_a_non_mapping_parent_is_refused() -> None:
    _run_refused(
        "INPUT_INVALID",
        lambda: apply_scientific_mutation(**mutation_arguments(parent="not-a-genome")),
    )


def test_a_parent_that_breaks_its_schema_is_refused() -> None:
    broken = genome()
    broken.pop("canonical_claim")
    _run_refused(
        "PARENT_CONTRACT_VIOLATED",
        lambda: apply_scientific_mutation(**mutation_arguments(parent=broken)),
    )


def test_a_lineage_for_a_different_candidate_is_refused() -> None:
    _run_refused(
        "PARENT_LINEAGE_MISMATCH",
        lambda: apply_scientific_mutation(
            **mutation_arguments(parent_lineage=lineage("HG-OTHER"))
        ),
    )


# --- Aporia grounding guards ---------------------------------------------


def test_an_aporia_operator_without_a_citation_is_refused() -> None:
    _run_refused(
        "APORIA_CITATION_MISSING",
        lambda: apply_scientific_mutation(
            **mutation_arguments(
                operator_id="aporia-response",
                changes={"uncertainty_notes": ["a confound"]},
                aporia_citation=None,
            )
        ),
    )


def test_citing_a_resolved_graph_is_refused() -> None:
    _run_refused(
        "APORIA_CITATION_NOT_OPEN",
        lambda: apply_scientific_mutation(
            **mutation_arguments(
                operator_id="aporia-response",
                changes={"uncertainty_notes": ["a confound"]},
                aporia_citation=citation(argument_graph=argument_graph(resolved=True)),
            )
        ),
    )


def test_citing_a_graph_about_another_hypothesis_is_refused() -> None:
    _run_refused(
        "APORIA_CITATION_SUBJECT_MISMATCH",
        lambda: apply_scientific_mutation(
            **mutation_arguments(
                operator_id="aporia-response",
                changes={"uncertainty_notes": ["a confound"]},
                aporia_citation=citation(
                    argument_graph=argument_graph(hypothesis_id="HG-ELSEWHERE")
                ),
            )
        ),
    )


def test_citing_a_question_the_graph_never_left_open_is_refused() -> None:
    _run_refused(
        "APORIA_CITATION_NOT_OPEN",
        lambda: require_aporia_citation(
            citation(open_question_ids=["OBJ-NEVER-RECORDED"]), subject_id="HG-1"
        ),
    )


def test_a_non_aporia_operator_handed_a_citation_is_refused() -> None:
    _run_refused(
        "INPUT_INVALID",
        lambda: apply_scientific_mutation(
            **mutation_arguments(aporia_citation=citation())
        ),
    )


# --- arity and identity guards -------------------------------------------


def test_a_splice_operator_on_the_mutation_surface_is_refused() -> None:
    _run_refused(
        "OPERATOR_ARITY_MISMATCH",
        lambda: apply_scientific_mutation(
            **mutation_arguments(operator_id="mechanism-preserving-splice")
        ),
    )


def test_a_mutation_operator_on_the_crossover_surface_is_refused() -> None:
    _run_refused(
        "OPERATOR_ARITY_MISMATCH",
        lambda: apply_typed_crossover(
            **crossover_arguments(operator_id="mechanism-refinement")
        ),
    )


def test_an_unknown_operator_is_refused() -> None:
    _run_refused("OPERATOR_UNKNOWN", lambda: resolve_operator("no-such-operator"))


# --- typed crossover guards ----------------------------------------------


def test_splicing_two_different_kinds_is_refused() -> None:
    _run_refused(
        "CROSSOVER_KIND_MISMATCH",
        lambda: apply_typed_crossover(
            **crossover_arguments(
                parents=[genome("HG-1"), challenge_genome("CG-2")],
                parent_lineages=[lineage("HG-1"), lineage("CG-2")],
            )
        ),
    )


def test_splicing_a_candidate_with_itself_is_refused() -> None:
    _run_refused(
        "INPUT_INVALID",
        lambda: apply_typed_crossover(
            **crossover_arguments(
                parents=[genome("HG-1"), genome("HG-1")],
                parent_lineages=[lineage("HG-1"), lineage("HG-1")],
            )
        ),
    )


def test_a_report_that_names_other_parents_is_refused() -> None:
    _run_refused(
        "CROSSOVER_REPORT_MISMATCH",
        lambda: apply_typed_crossover(
            **crossover_arguments(
                compatibility_report=compatibility_report(
                    candidate_ids=("HG-1", "HG-3")
                )
            )
        ),
    )


def test_a_report_that_is_not_an_unconditional_allow_is_refused() -> None:
    _run_refused(
        "CROSSOVER_NOT_PERMITTED",
        lambda: apply_typed_crossover(
            **crossover_arguments(
                compatibility_report=compatibility_report(
                    scope_compatibility="incompatible"
                )
            )
        ),
    )


def test_splicing_parents_whose_mechanisms_disagree_is_refused() -> None:
    _run_refused(
        "MECHANISM_INCOMPATIBLE",
        lambda: apply_typed_crossover(
            **crossover_arguments(
                parents=[
                    genome("HG-1", mechanism="MG-1"),
                    genome("HG-2", mechanism="MG-9", lineage_id=OTHER_LINE),
                ]
            )
        ),
    )


def test_a_splice_that_inherits_nothing_is_refused() -> None:
    _run_refused(
        "MUTATION_EMPTY",
        lambda: apply_typed_crossover(**crossover_arguments(inherited_fields=[])),
    )


def test_a_splice_inheriting_a_gene_the_donor_lacks_is_refused() -> None:
    _run_refused(
        "UNDECLARED_FIELD_TOUCHED",
        lambda: apply_typed_crossover(
            **crossover_arguments(inherited_fields=["no_such_gene"])
        ),
    )
