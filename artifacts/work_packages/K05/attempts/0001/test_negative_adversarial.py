"""negative_and_adversarial_tests — every refusal, and the forgeries behind them.

The adversarial cases are the ones that matter here: a snapshot relabelled to
look like a different pin, a partition edited after review, and a holdout that
is internally consistent, has every access flag false, and still conceals
material no snapshot ever pinned.  Each is refused with its declared code.
"""

from __future__ import annotations

from typing import Any

import pytest

from epistemic_foundry.evidence.v4_k05 import (
    CorpusBoundaryError,
    assess_novelty_within_boundary,
    declare_prior_art_boundary,
    holdout_handle,
    license_vocabulary,
    partition_pinned_snapshot,
    pin_corpus_snapshot,
    require_boundary_identity,
    require_holdout_drawn_from_snapshot,
    require_partition_identity,
    require_snapshot_identity,
    revalidate_corpus_snapshot,
    seal_holdout_boundary,
    snapshot_id_for,
)
from fixtures import (
    ADVERSARIAL_ID,
    CORPUS_ID,
    EVALUATED_AT,
    HIDDEN_ID,
    LATE_ID,
    OOD_ID,
    PINNED_AT,
    POLICY_VERSION,
    VISIBLE_ID,
    assessment_arguments,
    boundary,
    document,
    documents,
    holdout,
    observed_hashes,
    partition,
    seal_arguments,
    snapshot,
)

FOREIGN_HASH = "sha256:" + "e" * 64


def refusal(call, *args, **keywords) -> CorpusBoundaryError:
    with pytest.raises(CorpusBoundaryError) as caught:
        call(*args, **keywords)
    return caught.value


def pinned_with(*rows: dict[str, Any]) -> dict[str, Any]:
    return pin_corpus_snapshot(
        corpus_id=CORPUS_ID, documents=list(rows), pinned_at=PINNED_AT
    )


def without(row: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != field}


# -- pinning refusals -----------------------------------------------------


def test_an_empty_corpus_is_not_a_snapshot() -> None:
    error = refusal(
        pin_corpus_snapshot, corpus_id=CORPUS_ID, documents=[], pinned_at=PINNED_AT
    )

    assert error.code == "SNAPSHOT_EMPTY"


def test_a_document_without_a_content_hash_is_refused() -> None:
    row = without(documents()[0], "content_hash")

    assert refusal(pinned_with, row).code == "CONTENT_HASH_MISSING"


def test_a_content_hash_that_is_not_a_canonical_digest_is_refused() -> None:
    row = {**documents()[0], "content_hash": "md5:deadbeef"}

    assert refusal(pinned_with, row).code == "CONTENT_HASH_MISSING"


def test_a_document_without_a_licence_is_refused() -> None:
    row = without(documents()[0], "license_status")

    assert refusal(pinned_with, row).code == "LICENSE_UNDECLARED"


def test_the_licence_that_declares_nothing_is_refused() -> None:
    row = {**documents()[0], "license_status": license_vocabulary()[-1]}

    assert refusal(pinned_with, row).code == "LICENSE_UNDECLARED"


def test_a_licence_outside_the_canonical_vocabulary_is_refused() -> None:
    row = {**documents()[0], "license_status": "invented-licence"}

    error = refusal(pinned_with, row)

    assert error.code == "LICENSE_UNDECLARED"
    assert error.context["declared"] == list(license_vocabulary())


def test_a_document_without_a_date_is_refused() -> None:
    row = without(documents()[0], "source_date")

    assert refusal(pinned_with, row).code == "DOCUMENT_DATE_MISSING"


def test_a_date_that_is_not_a_calendar_date_is_refused() -> None:
    row = {**documents()[0], "source_date": "sometime in 2024"}

    assert refusal(pinned_with, row).code == "DOCUMENT_DATE_MISSING"


def test_one_document_id_with_two_content_hashes_is_refused() -> None:
    first = documents()[0]
    second = {**first, "content_hash": FOREIGN_HASH}

    error = refusal(pinned_with, first, second)

    assert error.code == "DOCUMENT_HASH_CONFLICT"
    assert sorted(error.context["content_hashes"]) == sorted(
        [first["content_hash"], FOREIGN_HASH]
    )


def test_one_document_id_declared_twice_with_different_metadata_is_refused() -> None:
    first = documents()[0]
    second = {**first, "source_date": "2020-01-01"}

    assert refusal(pinned_with, first, second).code == "INPUT_INVALID"


def test_a_document_that_is_not_a_mapping_is_refused() -> None:
    assert refusal(pinned_with, ["not-a-mapping"]).code == "INPUT_INVALID"


def test_a_document_without_an_identifier_is_refused() -> None:
    row = {**documents()[0], "document_id": "   "}

    assert refusal(pinned_with, row).code == "INPUT_INVALID"


# -- snapshot drift -------------------------------------------------------


def test_a_relabelled_snapshot_identifier_is_refused() -> None:
    forged = {**snapshot(), "snapshot_id": snapshot_id_for([FOREIGN_HASH])}

    assert refusal(require_snapshot_identity, forged).code == "SNAPSHOT_DRIFT"


def test_recomputing_the_snapshot_hash_does_not_launder_a_relabelling() -> None:
    # The adversarial case: an attacker who understands the hash simply
    # rewrites it too. The identifier is derived from the content, so the
    # forgery still fails.
    from epistemic_foundry.domain.hashing import hash_excluding

    forged = {**snapshot(), "snapshot_id": snapshot_id_for([FOREIGN_HASH])}
    forged["snapshot_hash"] = hash_excluding(forged, "snapshot_hash")

    error = refusal(require_snapshot_identity, forged)

    assert error.code == "SNAPSHOT_DRIFT"
    assert "snapshot_id" in error.context["derived"]


def test_an_edited_document_hash_breaks_the_snapshot_identity() -> None:
    pinned = snapshot()
    rows = [dict(row) for row in pinned["documents"]]
    rows[0]["content_hash"] = FOREIGN_HASH
    forged = {**pinned, "documents": rows}

    assert refusal(require_snapshot_identity, forged).code == "SNAPSHOT_DRIFT"


def test_a_dropped_document_breaks_the_snapshot_identity() -> None:
    pinned = snapshot()
    forged = {**pinned, "documents": list(pinned["documents"])[1:]}

    assert refusal(require_snapshot_identity, forged).code == "SNAPSHOT_DRIFT"


def test_a_pinned_document_missing_a_field_is_refused() -> None:
    pinned = snapshot()
    rows = [dict(row) for row in pinned["documents"]]
    rows[0].pop("license_status")
    forged = {**pinned, "documents": rows}

    error = refusal(require_snapshot_identity, forged)

    assert error.code == "SNAPSHOT_DRIFT"
    assert error.context["missing"] == ["license_status"]


def test_a_snapshot_holding_no_document_is_refused() -> None:
    forged = {**snapshot(), "documents": []}

    assert refusal(require_snapshot_identity, forged).code == "SNAPSHOT_EMPTY"


def test_revalidation_refuses_a_changed_document() -> None:
    error = refusal(
        revalidate_corpus_snapshot,
        snapshot(),
        observed_content_hashes=observed_hashes(**{OOD_ID: FOREIGN_HASH}),
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    assert error.code == "SNAPSHOT_DRIFT"
    assert error.context["drifted_document_ids"] == [OOD_ID]


def test_revalidation_refuses_a_vanished_document() -> None:
    observed = observed_hashes()
    observed.pop(HIDDEN_ID)

    error = refusal(
        revalidate_corpus_snapshot,
        snapshot(),
        observed_content_hashes=observed,
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    assert error.code == "SNAPSHOT_DRIFT"
    assert error.context["drifted_document_ids"] == [HIDDEN_ID]


def test_revalidation_refuses_a_document_nobody_pinned() -> None:
    error = refusal(
        revalidate_corpus_snapshot,
        snapshot(),
        observed_content_hashes=observed_hashes(**{"DOC-SMUGGLED": FOREIGN_HASH}),
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    assert error.code == "SNAPSHOT_DRIFT"
    assert error.context["drifted_document_ids"] == ["DOC-SMUGGLED"]


# -- partition refusals ---------------------------------------------------


def test_a_document_that_is_both_visible_and_hidden_is_leakage() -> None:
    error = refusal(
        partition,
        visible_document_ids=[VISIBLE_ID, HIDDEN_ID, LATE_ID],
        hidden_document_ids=[HIDDEN_ID],
    )

    assert error.code == "PARTITION_LEAKAGE"
    assert error.context["document_ids"] == [HIDDEN_ID]


def test_a_document_in_two_concealed_partitions_is_refused() -> None:
    error = refusal(
        partition,
        hidden_document_ids=[HIDDEN_ID, OOD_ID],
        ood_document_ids=[OOD_ID],
    )

    assert error.code == "PARTITION_OVERLAP"


def test_a_partition_list_naming_one_document_twice_is_refused() -> None:
    error = refusal(partition, hidden_document_ids=[HIDDEN_ID, HIDDEN_ID])

    assert error.code == "PARTITION_OVERLAP"


def test_a_partition_naming_an_unpinned_document_is_refused() -> None:
    error = refusal(partition, hidden_document_ids=[HIDDEN_ID, "DOC-ELSEWHERE"])

    assert error.code == "DOCUMENT_UNPINNED"
    assert error.context["unpinned"] == ["DOC-ELSEWHERE"]


def test_leaving_a_pinned_document_unassigned_is_refused() -> None:
    error = refusal(partition, adversarial_document_ids=[])

    assert error.code == "PARTITION_INCOMPLETE"
    assert error.context["unassigned"] == [ADVERSARIAL_ID]


def test_a_tampered_partition_is_refused_before_it_is_sealed() -> None:
    forged = {**partition(), "hidden_document_ids": [HIDDEN_ID, VISIBLE_ID]}

    assert refusal(require_partition_identity, forged).code == "PARTITION_DRIFT"


# -- seal refusals --------------------------------------------------------


def test_sealing_a_partition_from_another_snapshot_is_refused() -> None:
    other = pinned_with(
        document(
            "DOC-OTHER",
            fill="7",
            license_status="open_access",
            source_date="2024-03-04",
        )
    )
    arguments = seal_arguments()
    arguments["snapshot"] = other

    assert refusal(seal_holdout_boundary, **arguments).code == "PARTITION_DRIFT"


def test_sealing_a_partition_whose_snapshot_hash_was_swapped_is_refused() -> None:
    pinned = snapshot()
    forged = {**partition(pinned), "snapshot_hash": FOREIGN_HASH}
    arguments = seal_arguments(pinned)
    arguments["partition"] = forged

    assert refusal(seal_holdout_boundary, **arguments).code == "PARTITION_DRIFT"


def test_a_partition_that_conceals_nothing_cannot_be_sealed() -> None:
    pinned = snapshot()
    arguments = seal_arguments(pinned)
    arguments["partition"] = partition(
        pinned,
        visible_document_ids=[VISIBLE_ID, HIDDEN_ID, OOD_ID, ADVERSARIAL_ID, LATE_ID],
        hidden_document_ids=[],
        ood_document_ids=[],
        adversarial_document_ids=[],
    )

    assert refusal(seal_holdout_boundary, **arguments).code == "PARTITION_INCOMPLETE"


def test_the_firewalls_own_refusal_is_surfaced_not_worked_around() -> None:
    pinned = snapshot()
    arguments = seal_arguments(pinned)
    # Nothing hidden, but OOD and adversarial material still concealed: the
    # firewall requires at least one hidden handle and refuses the manifest.
    arguments["partition"] = partition(
        pinned,
        visible_document_ids=[VISIBLE_ID, HIDDEN_ID, LATE_ID],
        hidden_document_ids=[],
    )

    error = refusal(seal_holdout_boundary, **arguments)

    assert error.code == "HOLDOUT_SEAL_REFUSED"
    assert "hidden partition handle" in str(error)


# -- holdout provenance refusals -----------------------------------------


def test_a_holdout_from_another_snapshot_is_refused() -> None:
    other = pinned_with(
        document(
            "DOC-OTHER-A",
            fill="7",
            license_status="open_access",
            source_date="2024-03-04",
        ),
        document(
            "DOC-OTHER-B",
            fill="8",
            license_status="licensed",
            source_date="2024-03-05",
        ),
    )
    arguments = seal_arguments()
    arguments["snapshot"] = other
    arguments["partition"] = partition_pinned_snapshot(
        snapshot=other,
        visible_document_ids=["DOC-OTHER-A"],
        hidden_document_ids=["DOC-OTHER-B"],
    )
    foreign = seal_holdout_boundary(**arguments)

    error = refusal(
        require_holdout_drawn_from_snapshot, snapshot=snapshot(), holdout=foreign
    )

    assert error.code == "HOLDOUT_HANDLE_UNPINNED"


def test_a_holdout_binding_an_unpinned_content_hash_is_refused() -> None:
    pinned = snapshot()
    forged = dict(holdout(pinned))
    forged["content_hashes"] = [*forged["content_hashes"], FOREIGN_HASH]

    error = refusal(
        require_holdout_drawn_from_snapshot, snapshot=pinned, holdout=forged
    )

    assert error.code == "HOLDOUT_CONTENT_UNPINNED"
    assert error.context["content_hashes"] == [FOREIGN_HASH]


def test_a_holdout_publishing_an_unpinned_document_is_refused() -> None:
    pinned = snapshot()
    forged = dict(holdout(pinned))
    forged["public_partition_refs"] = [*forged["public_partition_refs"], "DOC-INVENTED"]

    error = refusal(
        require_holdout_drawn_from_snapshot, snapshot=pinned, holdout=forged
    )

    assert error.code == "DOCUMENT_UNPINNED"


def test_a_holdout_that_conceals_what_it_also_publishes_is_leakage() -> None:
    pinned = snapshot()
    forged = dict(holdout(pinned))
    forged["hidden_partition_handles"] = [
        *forged["hidden_partition_handles"],
        holdout_handle(pinned["snapshot_id"], VISIBLE_ID),
    ]

    error = refusal(
        require_holdout_drawn_from_snapshot, snapshot=pinned, holdout=forged
    )

    assert error.code == "PARTITION_LEAKAGE"
    assert error.context["document_ids"] == [VISIBLE_ID]


# -- prior-art refusals ---------------------------------------------------


def test_a_boundary_without_a_parseable_as_of_date_is_refused() -> None:
    assert refusal(boundary, as_of_date="recently").code == "AS_OF_UNDECLARED"


def test_a_boundary_that_names_no_searched_source_is_refused() -> None:
    assert refusal(boundary, searched_sources=[]).code == "SEARCH_SCOPE_UNDECLARED"


def test_a_source_cannot_be_both_searched_and_unsearched() -> None:
    error = refusal(
        boundary, searched_sources=["one-index"], unsearched_sources=["one-index"]
    )

    assert error.code == "SEARCH_SCOPE_UNDECLARED"
    assert error.context["sources"] == ["one-index"]


def test_an_as_of_bound_before_every_document_leaves_nothing_to_search() -> None:
    assert refusal(boundary, as_of_date="1990-01-01").code == "SNAPSHOT_EMPTY"


def test_a_boundary_declared_over_an_unpinned_snapshot_is_refused() -> None:
    forged = {**snapshot(), "snapshot_id": snapshot_id_for([FOREIGN_HASH])}

    error = refusal(
        declare_prior_art_boundary,
        snapshot=forged,
        as_of_date="2026-01-01",
        searched_sources=["one-index"],
    )

    assert error.code == "SNAPSHOT_DRIFT"


def test_a_tampered_boundary_is_refused() -> None:
    forged = {**boundary(), "as_of_date": "2030-01-01"}

    assert refusal(require_boundary_identity, forged).code == "BOUNDARY_DRIFT"


def test_an_assessment_over_a_tampered_boundary_is_refused() -> None:
    forged = {**boundary(), "in_scope_document_ids": ["DOC-ANYTHING"]}

    error = refusal(
        assess_novelty_within_boundary, **assessment_arguments(boundary=forged)
    )

    assert error.code == "BOUNDARY_DRIFT"


def test_prior_art_the_boundary_does_not_contain_is_refused() -> None:
    error = refusal(
        assess_novelty_within_boundary,
        **assessment_arguments(closest_prior_art_refs=["DOC-NOWHERE"]),
    )

    assert error.code == "PRIOR_ART_OUTSIDE_BOUNDARY"
    assert error.context["document_ids"] == ["DOC-NOWHERE"]


def test_prior_art_dated_after_the_as_of_bound_is_refused() -> None:
    error = refusal(
        assess_novelty_within_boundary,
        **assessment_arguments(closest_prior_art_refs=[LATE_ID]),
    )

    assert error.code == "PRIOR_ART_AFTER_AS_OF"
    assert error.context["document_ids"] == [LATE_ID]


def test_a_novelty_dimension_outside_the_vocabulary_is_refused() -> None:
    error = refusal(
        assess_novelty_within_boundary,
        **assessment_arguments(novelty_dimensions=["VIBES"]),
    )

    assert error.code == "NOVELTY_DIMENSION_UNDECLARED"
    assert error.context["undeclared"] == ["VIBES"]


def test_a_statement_hash_that_is_not_a_digest_is_refused() -> None:
    error = refusal(
        assess_novelty_within_boundary,
        **assessment_arguments(statement_hash="not-a-digest"),
    )

    assert error.code == "INPUT_INVALID"


def test_an_assessment_without_an_assessor_is_refused() -> None:
    error = refusal(
        assess_novelty_within_boundary, **assessment_arguments(assessor_ref="  ")
    )

    assert error.code == "INPUT_INVALID"


def test_a_partition_over_something_that_is_not_a_snapshot_is_refused() -> None:
    error = refusal(
        partition_pinned_snapshot,
        snapshot="not-a-snapshot",
        visible_document_ids=[],
        hidden_document_ids=[],
    )

    assert error.code == "INPUT_INVALID"
