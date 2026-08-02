"""negative_and_adversarial_tests — what the door refuses, and what it cannot be talked into.

The adversarial cases are the ones that matter for an intake: a genome that is
unfalsifiable in substance while passing a schema, a monoculture dressed up as a
population by renaming its members, a kind pushed in from outside the sealed
search space, and a seal that has drifted underneath the intake.  Each produces
a typed refusal rather than an admitted genome.
"""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.intake.v4_i05 import (
    GENOME_KIND,
    GenomeIntakeError,
    bootstrap_seed_population,
    genome_contract,
    genome_signature,
    mutable_genome_kinds,
    require_fully_eligible,
    screen_genome,
    screen_submissions,
)
from epistemic_foundry.intake.v4_i05 import screening as engine
from fixtures import (
    SCREENED_AT,
    bootstrap_arguments,
    diverse_batch,
    genome,
    monoculture_batch,
    submission,
)


def codes(document: object, *, kind: str = GENOME_KIND) -> list[str]:
    return list(screen_genome(document, genome_kind=kind)["reason_codes"])


def test_a_genome_declaring_no_falsifier_is_refused() -> None:
    reasons = codes(genome("HG-1", falsifier_gene_ids=[]))

    assert "FALSIFIER_DECLARATION_EMPTY" in reasons
    assert "GENOME_MALFORMED" in reasons


def test_a_falsifier_list_of_blank_strings_is_not_a_falsifier() -> None:
    reasons = codes(genome("HG-1", falsifier_gene_ids=["   "]))

    assert "FALSIFIER_DECLARATION_EMPTY" in reasons


def test_a_falsifier_field_of_the_wrong_type_is_refused() -> None:
    reasons = codes(genome("HG-1", falsifier_gene_ids="FG-1"))

    assert "FALSIFIER_DECLARATION_EMPTY" in reasons
    assert "GENOME_MALFORMED" in reasons


def test_a_genome_declaring_no_scope_is_refused() -> None:
    reasons = codes(genome("HG-1", scope_vector_id="   "))

    assert reasons == ["SCOPE_UNDECLARED"]


def test_a_kind_outside_the_sealed_search_space_is_refused_categorically() -> None:
    record = screen_genome(genome(), genome_kind="evaluator-bundle")

    assert record["reason_codes"] == ["GENOME_KIND_OUTSIDE_SEARCH_SPACE"]
    assert record["screen_detail"]["mutable_search_space"] == list(
        mutable_genome_kinds()
    )
    # A document of another kind is not additionally judged against a contract
    # it never claimed to satisfy.
    assert "schema_errors" not in record["screen_detail"]


def test_a_mutable_kind_this_intake_does_not_screen_is_refused() -> None:
    other = sorted(set(mutable_genome_kinds()) - {GENOME_KIND})[0]

    record = screen_genome(genome(), genome_kind=other)

    assert record["reason_codes"] == ["GENOME_KIND_NOT_INTAKEABLE"]
    assert record["screen_detail"]["intakeable_kind"] == GENOME_KIND


def test_a_document_that_is_not_a_mapping_is_refused() -> None:
    record = screen_genome(["not", "a", "genome"], genome_kind=GENOME_KIND)

    assert record["reason_codes"] == ["GENOME_MALFORMED"]
    assert record["genome_id"] is None
    assert record["genome_hash"] is None
    assert record["signature"] is None


def test_an_undeclared_property_cannot_be_smuggled_into_a_genome() -> None:
    reasons = codes(genome("HG-1", promotion_authority="granted"))

    assert reasons == ["GENOME_MALFORMED"]


def test_an_envelope_without_a_declared_kind_is_refused() -> None:
    report = screen_submissions(
        [{"genome": genome()}, "not-an-envelope", None],
        screened_at=SCREENED_AT,
        report_id="GSR-N-1",
    )

    assert report["counts"] == {"admitted": 0, "refused": 3, "submitted": 3}
    for record in report["records"]:
        assert record["reason_codes"] == ["SUBMISSION_MALFORMED"]


def test_a_batch_that_is_not_a_sequence_of_envelopes_is_refused() -> None:
    for bad in ({"genome_kind": GENOME_KIND}, "HG-1"):
        with pytest.raises(GenomeIntakeError) as caught:
            screen_submissions(bad, screened_at=SCREENED_AT)
        assert caught.value.code == "INPUT_INVALID"


def test_a_mixed_batch_still_reconciles_exactly() -> None:
    batch = [
        *diverse_batch(),
        submission(genome("HG-4", falsifier_gene_ids=[])),
        submission(genome("HG-5"), kind="prompt-genome"),
        "not-an-envelope",
    ]

    report = screen_submissions(batch, screened_at=SCREENED_AT, report_id="GSR-N-2")

    assert report["counts"]["submitted"] == 6
    assert report["counts"]["admitted"] == 3
    assert report["counts"]["refused"] == 3
    assert sum(report["reason_totals"].values()) >= 3


def test_a_seed_population_cannot_be_empty() -> None:
    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(**bootstrap_arguments(submissions=[]))

    assert caught.value.code == "SEED_POPULATION_EMPTY"


def test_a_batch_where_nothing_survives_screening_cannot_seed_a_run() -> None:
    batch = [submission(genome("HG-1", falsifier_gene_ids=[]))]

    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(**bootstrap_arguments(submissions=batch))

    assert caught.value.code == "SEED_POPULATION_EMPTY"
    assert caught.value.context["submitted"] == 1


def test_two_submissions_claiming_one_genome_id_are_refused() -> None:
    batch = [*diverse_batch(), submission(genome("HG-1", mechanism="MG-7"))]

    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(**bootstrap_arguments(submissions=batch))

    assert caught.value.code == "GENOME_ID_DUPLICATED"
    assert caught.value.context["duplicated"] == ["HG-1"]


def test_a_duplicate_id_is_refused_even_when_one_copy_is_ineligible() -> None:
    """An id that names two documents is ambiguous however the second scored."""
    batch = [*diverse_batch(), submission(genome("HG-2", falsifier_gene_ids=[]))]

    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(**bootstrap_arguments(submissions=batch))

    assert caught.value.code == "GENOME_ID_DUPLICATED"


def test_renaming_a_monoculture_does_not_buy_diversity() -> None:
    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(
            **bootstrap_arguments(
                submissions=monoculture_batch(), minimum_signature_diversity=3
            )
        )

    assert caught.value.code == "SEED_DIVERSITY_INSUFFICIENT"
    assert caught.value.context["distinct_signatures"] == 1


def test_a_diversity_floor_must_be_a_positive_integer() -> None:
    for bad in (0, -1, 1.5, True, "3"):
        with pytest.raises(GenomeIntakeError) as caught:
            bootstrap_seed_population(
                **bootstrap_arguments(minimum_signature_diversity=bad)
            )
        assert caught.value.code == "INPUT_INVALID", bad


def test_a_seed_population_needs_a_declared_island() -> None:
    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(**bootstrap_arguments(island_id="  "))

    assert caught.value.code == "INPUT_INVALID"


def test_require_fully_eligible_names_the_first_reason_it_found() -> None:
    report = screen_submissions(
        [submission(genome("HG-1", falsifier_gene_ids=[]))],
        screened_at=SCREENED_AT,
        report_id="GSR-N-3",
    )

    with pytest.raises(GenomeIntakeError) as caught:
        require_fully_eligible(report)

    assert caught.value.code == "FALSIFIER_DECLARATION_EMPTY"
    assert caught.value.context["genome_id"] == "HG-1"


def test_a_signature_cannot_be_derived_without_mechanism_and_scope() -> None:
    with pytest.raises(GenomeIntakeError) as caught:
        genome_signature({"mechanism_graph_id": "MG-1"})

    assert caught.value.code == "INPUT_INVALID"


def test_an_unreadable_seal_closes_the_door_rather_than_opening_it(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(engine, "repo_root", lambda: tmp_path)

    with pytest.raises(GenomeIntakeError) as caught:
        mutable_genome_kinds()

    assert caught.value.code == "SEARCH_SPACE_DRIFT"


def test_a_seal_that_declares_no_mutable_space_closes_the_door(
    tmp_path, monkeypatch
) -> None:
    index = tmp_path / "schemas/v4_c05"
    index.mkdir(parents=True)
    (index / "family-index.json").write_text(
        json.dumps({"mutable_search_space": []}), encoding="utf-8"
    )
    monkeypatch.setattr(engine, "repo_root", lambda: tmp_path)

    with pytest.raises(GenomeIntakeError) as caught:
        screen_genome(genome(), genome_kind=GENOME_KIND)

    assert caught.value.code == "SEARCH_SPACE_DRIFT"


def test_a_seal_that_drops_this_genome_kind_admits_nothing(
    tmp_path, monkeypatch
) -> None:
    index = tmp_path / "schemas/v4_c05"
    index.mkdir(parents=True)
    (index / "family-index.json").write_text(
        json.dumps({"mutable_search_space": ["schemas/prompt-genome.schema.json"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(engine, "repo_root", lambda: tmp_path)

    with pytest.raises(GenomeIntakeError) as caught:
        bootstrap_seed_population(**bootstrap_arguments())

    assert caught.value.code == "SEARCH_SPACE_DRIFT"


def test_a_renamed_screened_field_is_caught_as_contract_drift(monkeypatch) -> None:
    monkeypatch.setattr(engine, "FALSIFIER_FIELD", "falsifier_declarations")

    with pytest.raises(GenomeIntakeError) as caught:
        genome_contract()

    assert caught.value.code == "GENOME_CONTRACT_DRIFT"
    assert caught.value.context["missing"] == ["falsifier_declarations"]
