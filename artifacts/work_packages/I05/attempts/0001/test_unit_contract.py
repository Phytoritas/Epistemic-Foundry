"""unit_and_contract_tests — the door works the way intake claims it works.

A falsifiable, scoped genome of a mutable kind is admitted; a batch reconciles;
and the survivors become a seed population whose lineages are first-generation
and whose diversity is counted over mechanism-and-scope signatures rather than
over names.
"""

from __future__ import annotations

from epistemic_foundry.intake.v4_i05 import (
    GENOME_KIND,
    SEED_GENERATION,
    bootstrap_seed_population,
    genome_signature,
    require_fully_eligible,
    screen_genome,
    screen_submissions,
)
from fixtures import (
    ISLAND,
    SCREENED_AT,
    bootstrap_arguments,
    diverse_batch,
    genome,
    monoculture_batch,
    submission,
)


def test_a_falsifiable_scoped_genome_of_a_mutable_kind_is_admitted() -> None:
    record = screen_genome(genome("HG-A"), genome_kind=GENOME_KIND)

    assert record["admitted"] is True
    assert record["reason_codes"] == []
    assert record["reasons"] == {}
    assert record["genome_id"] == "HG-A"
    assert record["genome_kind"] == GENOME_KIND
    assert record["signature"] is not None


def test_the_signature_is_a_pure_function_of_mechanism_and_scope() -> None:
    first = genome_signature(genome("HG-1", mechanism="MG-1", scope="SV-1"))
    same = genome_signature(genome("HG-9", mechanism="MG-1", scope="SV-1"))

    assert first == same
    assert first != genome_signature(genome("HG-1", mechanism="MG-2", scope="SV-1"))
    assert first != genome_signature(genome("HG-1", mechanism="MG-1", scope="SV-2"))


def test_rewording_a_claim_does_not_change_the_signature() -> None:
    """Diversity is over what is proposed, not over how it is written."""
    original = genome("HG-1")
    reworded = genome("HG-1", canonical_claim="the identical mechanism, restated")

    assert genome_signature(original) == genome_signature(reworded)


def test_a_batch_reconciles_submitted_against_admitted_and_refused() -> None:
    batch = [*diverse_batch(), submission(genome("HG-4", falsifier_gene_ids=[]))]

    report = screen_submissions(batch, screened_at=SCREENED_AT, report_id="GSR-U-1")

    assert report["counts"]["submitted"] == 4
    assert report["counts"]["admitted"] == 3
    assert report["counts"]["refused"] == 1
    assert (
        report["counts"]["submitted"]
        == report["counts"]["admitted"] + report["counts"]["refused"]
    )
    assert report["admitted_genome_ids"] == ["HG-1", "HG-2", "HG-3"]
    assert report["reason_totals"]["FALSIFIER_DECLARATION_EMPTY"] == 1


def test_records_keep_submission_order_and_derived_lists_are_sorted() -> None:
    batch = [
        submission(genome("HG-9", mechanism="MG-9")),
        submission(genome("HG-2", mechanism="MG-2")),
    ]

    report = screen_submissions(batch, screened_at=SCREENED_AT, report_id="GSR-U-2")

    assert [record["submission_index"] for record in report["records"]] == [0, 1]
    assert [record["genome_id"] for record in report["records"]] == ["HG-9", "HG-2"]
    assert report["admitted_genome_ids"] == ["HG-2", "HG-9"]
    assert report["signatures"] == sorted(report["signatures"])


def test_an_empty_batch_screens_to_an_empty_reconciled_report() -> None:
    report = screen_submissions([], screened_at=SCREENED_AT, report_id="GSR-U-3")

    assert report["counts"] == {"admitted": 0, "refused": 0, "submitted": 0}
    assert report["records"] == []


def test_require_fully_eligible_accepts_a_clean_report() -> None:
    report = screen_submissions(
        diverse_batch(), screened_at=SCREENED_AT, report_id="GSR-U-4"
    )

    require_fully_eligible(report)


def test_the_seed_population_carries_its_screening_and_its_lineages() -> None:
    population = bootstrap_seed_population(**bootstrap_arguments())

    assert population["population_id"] == "SPB-I05-1"
    assert population["generation"] == SEED_GENERATION
    assert population["island_id"] == ISLAND
    assert population["seed_genome_ids"] == ["HG-1", "HG-2", "HG-3"]
    assert population["signature_diversity"] == 3
    assert population["counts"] == {
        "admitted": 3,
        "refused": 0,
        "seeded": 3,
        "submitted": 3,
    }
    assert population["screening"]["report_id"] == "GSR-I05-1"
    assert [lineage["candidate_id"] for lineage in population["seed_lineages"]] == [
        "HG-1",
        "HG-2",
        "HG-3",
    ]


def test_each_seed_lineage_uses_the_genome_s_own_declared_lineage_id() -> None:
    population = bootstrap_seed_population(**bootstrap_arguments())

    assert [lineage["lineage_id"] for lineage in population["seed_lineages"]] == [
        "LIN-HG-1",
        "LIN-HG-2",
        "LIN-HG-3",
    ]
    for lineage in population["seed_lineages"]:
        assert lineage["ancestor_hashes"] == []
        assert lineage["island_id"] == ISLAND


def test_the_seed_ids_are_exactly_the_admitted_ids() -> None:
    """These are the ids a run spec's seed field carries into the F05 machine."""
    batch = [*diverse_batch(), submission(genome("HG-4", scope_vector_id=" "))]

    population = bootstrap_seed_population(
        **bootstrap_arguments(submissions=batch, minimum_signature_diversity=2)
    )

    assert (
        population["seed_genome_ids"] == population["screening"]["admitted_genome_ids"]
    )
    assert population["counts"]["seeded"] == population["counts"]["admitted"]
    assert population["counts"]["refused"] == 1


def test_the_declared_diversity_floor_is_enforced_at_its_boundary() -> None:
    population = bootstrap_seed_population(
        **bootstrap_arguments(
            submissions=monoculture_batch(), minimum_signature_diversity=1
        )
    )

    assert population["signature_diversity"] == 1
    assert population["minimum_signature_diversity"] == 1
    assert len(population["seed_lineages"]) == 3


def test_a_signature_is_recorded_for_every_seeded_genome() -> None:
    population = bootstrap_seed_population(**bootstrap_arguments())

    assert sorted(population["signature_by_genome_id"]) == population["seed_genome_ids"]
    assert (
        len(set(population["signature_by_genome_id"].values()))
        == population["signature_diversity"]
    )


def test_identifiers_fall_back_to_minted_ids_only_when_not_supplied() -> None:
    population = bootstrap_seed_population(
        **bootstrap_arguments(population_id=None, report_id=None)
    )

    assert population["population_id"].startswith("SPB-")
    assert population["screening"]["report_id"].startswith("GSR-")
