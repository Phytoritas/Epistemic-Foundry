"""unit_and_contract_tests — the happy path of the three boundaries.

A snapshot pins bytes, licences and dates and derives its identity from the
content; a partition splits it and the firewall seals the hidden side; a
prior-art boundary names a snapshot and a date and the assessment it supports
stays inside both.  These tests state what the boundaries are *for*; the
refusals live in the negative suite.
"""

from __future__ import annotations

from epistemic_foundry.evidence.v4_k05 import (
    HANDLE_DIGEST_LENGTH,
    HANDLE_ID_PREFIX,
    SNAPSHOT_ID_PREFIX,
    assess_novelty_within_boundary,
    build_snapshot_integrity_reports,
    holdout_handle,
    integrity_check_vocabulary,
    integrity_overall_vocabulary,
    partition_pinned_snapshot,
    pin_corpus_snapshot,
    pinned_documents,
    require_boundary_identity,
    require_holdout_drawn_from_snapshot,
    require_partition_identity,
    require_snapshot_identity,
    revalidate_corpus_snapshot,
    scalar_enum_field,
    snapshot_id_for,
)
from epistemic_foundry.evidence.v4_k05 import (
    CORPUS_BOUNDED_POSITION,
    INTEGRITY_FAIL_POSITION,
    INTEGRITY_PASS_POSITION,
    NOVELTY_LADDER,
    NOVELTY_SCHEMA,
    NOVELTY_STATUS_POSITION,
    PRIOR_ART_FOUND_POSITION,
    PROMOTION_CEILING_POSITION,
    SEARCH_BOUNDED_POSITION,
)
from fixtures import (
    ADVERSARIAL_ID,
    AS_OF_DATE,
    CORPUS_ID,
    EVALUATED_AT,
    EVALUATOR_ID,
    HIDDEN_ID,
    LATE_ID,
    OOD_ID,
    PINNED_AT,
    POLICY_VERSION,
    SEARCHED_SOURCES,
    VISIBLE_ID,
    assessment_arguments,
    boundary,
    documents,
    holdout,
    observed_hashes,
    partition,
    snapshot,
)


def status_of(assessment: dict) -> str:
    field, _ = scalar_enum_field(NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION)
    return str(assessment[field])


def ceiling_of(assessment: dict) -> str:
    field, _ = scalar_enum_field(NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION)
    return str(assessment[field])


def ladder_value(position: int) -> tuple[str, str]:
    _, statuses = scalar_enum_field(NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION)
    _, ceilings = scalar_enum_field(NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION)
    return statuses[position], ceilings[NOVELTY_LADDER[position]]


# -- snapshot pinning -----------------------------------------------------


def test_a_snapshot_pins_every_document_by_hash_licence_and_date() -> None:
    pinned = snapshot()

    assert pinned["corpus_id"] == CORPUS_ID
    assert pinned["pinned_at"] == PINNED_AT
    assert pinned["document_count"] == len(documents())
    assert [row["document_id"] for row in pinned["documents"]] == sorted(
        row["document_id"] for row in documents()
    )
    for row in pinned["documents"]:
        assert row["content_hash"].startswith("sha256:")
        assert row["license_status"]
        assert row["source_date"]


def test_the_snapshot_identity_is_its_content() -> None:
    pinned = snapshot()

    assert pinned["snapshot_id"].startswith(SNAPSHOT_ID_PREFIX)
    assert pinned["snapshot_id"] == snapshot_id_for(pinned["content_hashes"])
    # A different corpus label over the same bytes is the same snapshot.
    assert snapshot(corpus_id="OTHER")["snapshot_id"] == pinned["snapshot_id"]


def test_a_repeated_identical_document_is_pinned_once() -> None:
    repeated = [*documents(), documents()[0]]

    pinned = pin_corpus_snapshot(
        corpus_id=CORPUS_ID, documents=repeated, pinned_at=PINNED_AT
    )

    assert pinned["document_count"] == len(documents())
    assert pinned == snapshot()


def test_the_document_order_of_the_input_does_not_change_the_snapshot() -> None:
    reversed_input = list(reversed(documents()))

    assert (
        pin_corpus_snapshot(
            corpus_id=CORPUS_ID, documents=reversed_input, pinned_at=PINNED_AT
        )
        == snapshot()
    )


def test_a_snapshot_re_derives_its_own_identity() -> None:
    pinned = snapshot()

    assert require_snapshot_identity(pinned) == pinned
    assert sorted(pinned_documents(pinned)) == sorted(
        row["document_id"] for row in documents()
    )


def test_revalidation_returns_a_clean_report_for_every_pinned_document() -> None:
    pinned = snapshot()

    reports = revalidate_corpus_snapshot(
        pinned,
        observed_content_hashes=observed_hashes(),
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    passed = integrity_overall_vocabulary()[INTEGRITY_PASS_POSITION]
    assert len(reports) == len(documents())
    for report in reports:
        assert report["overall_status"] == passed
        assert report["trusted_for_extraction"] is True
        assert report["policy_version"] == POLICY_VERSION
        assert report["evaluated_at"] == EVALUATED_AT
        assert [check["status"] for check in report["checks"]] == [
            integrity_check_vocabulary()[INTEGRITY_PASS_POSITION]
        ] * 2


def test_a_changed_document_is_reported_rather_than_hidden() -> None:
    pinned = snapshot()

    reports = build_snapshot_integrity_reports(
        pinned,
        observed_content_hashes=observed_hashes(**{HIDDEN_ID: "sha256:" + "f" * 64}),
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    failed = integrity_overall_vocabulary()[INTEGRITY_FAIL_POSITION]
    by_id = {report["document_id"]: report for report in reports}
    assert by_id[HIDDEN_ID]["overall_status"] == failed
    assert by_id[HIDDEN_ID]["trusted_for_extraction"] is False
    assert by_id[VISIBLE_ID]["trusted_for_extraction"] is True


# -- holdout boundary -----------------------------------------------------


def test_a_partition_assigns_every_pinned_document_exactly_once() -> None:
    split = partition()

    assigned = [
        *split["visible_document_ids"],
        *split["hidden_document_ids"],
        *split["ood_document_ids"],
        *split["adversarial_document_ids"],
    ]
    assert sorted(assigned) == sorted(row["document_id"] for row in documents())
    assert len(set(assigned)) == len(assigned)


def test_partition_handles_are_derived_from_the_snapshot() -> None:
    pinned = snapshot()
    split = partition(pinned)

    expected = holdout_handle(pinned["snapshot_id"], HIDDEN_ID)
    assert split["hidden_partition_handles"] == [expected]
    assert expected.startswith(HANDLE_ID_PREFIX)
    assert len(expected) == len(HANDLE_ID_PREFIX) + HANDLE_DIGEST_LENGTH
    assert split["ood_partition_handles"] == [
        holdout_handle(pinned["snapshot_id"], OOD_ID)
    ]
    assert split["adversarial_partition_handles"] == [
        holdout_handle(pinned["snapshot_id"], ADVERSARIAL_ID)
    ]


def test_a_partition_re_derives_its_own_identity() -> None:
    split = partition()

    assert require_partition_identity(split) == split


def test_the_seal_is_the_firewalls_own_holdout_manifest() -> None:
    pinned = snapshot()
    sealed = holdout(pinned)

    assert sealed["evaluator_id"] == EVALUATOR_ID
    assert sealed["candidate_access"] is False
    assert sealed["mutation_model_access"] is False
    assert sealed["prompt_access"] is False
    assert sealed["backend_access"] is False
    assert sealed["unblinding_approval_required"] is True
    assert sealed["hidden_partition_handles"] == [
        holdout_handle(pinned["snapshot_id"], HIDDEN_ID)
    ]
    assert sorted(sealed["public_partition_refs"]) == sorted([VISIBLE_ID, LATE_ID])


def test_the_sealed_content_hashes_are_exactly_the_concealed_documents() -> None:
    pinned = snapshot()
    sealed = holdout(pinned)
    index = pinned_documents(pinned)

    assert sealed["content_hashes"] == sorted(
        {
            index[document_id]["content_hash"]
            for document_id in (HIDDEN_ID, OOD_ID, ADVERSARIAL_ID)
        }
    )
    assert index[VISIBLE_ID]["content_hash"] not in sealed["content_hashes"]


def test_a_holdout_drawn_from_the_snapshot_is_accepted() -> None:
    pinned = snapshot()

    assert require_holdout_drawn_from_snapshot(
        snapshot=pinned, holdout=holdout(pinned)
    ) == holdout(pinned)


# -- prior-art boundary ---------------------------------------------------


def test_a_boundary_names_one_snapshot_and_one_as_of_date() -> None:
    pinned = snapshot()
    declared = boundary(pinned)

    assert declared["snapshot_id"] == pinned["snapshot_id"]
    assert declared["corpus_snapshot_hash"] == pinned["snapshot_hash"]
    assert declared["as_of_date"] == AS_OF_DATE
    assert declared["searched_sources"] == sorted(SEARCHED_SOURCES)
    assert require_boundary_identity(declared) == declared


def test_documents_after_the_as_of_bound_are_recorded_as_excluded() -> None:
    declared = boundary()

    assert declared["excluded_document_ids"] == [LATE_ID]
    assert LATE_ID not in declared["in_scope_document_ids"]
    assert sorted(
        [*declared["in_scope_document_ids"], *declared["excluded_document_ids"]]
    ) == sorted(row["document_id"] for row in documents())


def test_an_assessment_with_no_prior_art_stops_at_the_corpus_bounded_rung() -> None:
    assessment = assess_novelty_within_boundary(**assessment_arguments())

    status, ceiling = ladder_value(CORPUS_BOUNDED_POSITION)
    assert status_of(assessment) == status
    assert ceiling_of(assessment) == ceiling
    assert assessment["search_cutoff"] == AS_OF_DATE
    assert assessment["corpus_snapshot_hash"] == snapshot()["snapshot_hash"]


def test_an_exhaustively_searched_boundary_reaches_the_search_bounded_rung() -> None:
    assessment = assess_novelty_within_boundary(
        **assessment_arguments(boundary=boundary(unsearched_sources=[]))
    )

    status, ceiling = ladder_value(SEARCH_BOUNDED_POSITION)
    assert status_of(assessment) == status
    assert ceiling_of(assessment) == ceiling


def test_cited_prior_art_drops_the_assessment_to_the_lowest_rung() -> None:
    assessment = assess_novelty_within_boundary(
        **assessment_arguments(closest_prior_art_refs=[VISIBLE_ID])
    )

    status, ceiling = ladder_value(PRIOR_ART_FOUND_POSITION)
    assert status_of(assessment) == status
    assert ceiling_of(assessment) == ceiling
    assert assessment["closest_prior_art_refs"] == [VISIBLE_ID]


def test_the_assessment_always_states_the_boundary_it_was_made_within() -> None:
    pinned = snapshot()
    assessment = assess_novelty_within_boundary(**assessment_arguments())

    assert any(
        pinned["snapshot_id"] in limitation and AS_OF_DATE in limitation
        for limitation in assessment["limitations"]
    )
    assert assessment["unsearched_sources"]


def test_a_caller_limitation_is_kept_beside_the_declared_one() -> None:
    assessment = assess_novelty_within_boundary(
        **assessment_arguments(limitations=["one parser only"])
    )

    assert assessment["limitations"][0] == "one parser only"
    assert len(assessment["limitations"]) == 2


def test_a_single_document_corpus_still_partitions_and_bounds() -> None:
    only = documents()[1]
    pinned = pin_corpus_snapshot(
        corpus_id=CORPUS_ID, documents=[only], pinned_at=PINNED_AT
    )

    split = partition_pinned_snapshot(
        snapshot=pinned,
        visible_document_ids=[],
        hidden_document_ids=[only["document_id"]],
    )

    assert split["hidden_document_ids"] == [only["document_id"]]
    assert split["visible_document_ids"] == []
