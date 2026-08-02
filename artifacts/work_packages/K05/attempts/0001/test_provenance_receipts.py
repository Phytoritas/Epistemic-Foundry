"""provenance_and_receipt_audit — every record proves itself from its own content.

Snapshot, partition, boundary and assessment each re-derive their own
identifier and hash from exactly the fields they publish; every canonical
record validates against its schema; the boundaries hold no clock and no
randomness, so two runs over equal inputs produce byte-equal records; and no
input is mutated on the way through.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import validate_artifact
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.evidence.v4_k05 import (
    ASSESSMENT_ID_PREFIX,
    BOUNDARY_ID_PREFIX,
    NOVELTY_SCHEMA,
    PARTITION_ID_PREFIX,
    PROMOTION_CEILING_POSITION,
    REPORT_ID_PREFIX,
    assess_novelty_within_boundary,
    build_snapshot_integrity_reports,
    holdout_handle,
    pinned_documents,
    report_id_for,
    revalidate_corpus_snapshot,
    scalar_enum_field,
    snapshot_id_for,
)
from fixtures import (
    ADVERSARIAL_ID,
    EVALUATED_AT,
    HIDDEN_ID,
    OOD_ID,
    POLICY_VERSION,
    assessment_arguments,
    boundary,
    documents,
    holdout,
    observed_hashes,
    partition,
    seal_arguments,
    snapshot,
)

ROOT = Path(__file__).resolve().parents[5]
BOUNDARIES = ROOT / "src/epistemic_foundry/evidence/v4_k05/boundaries.py"


def test_the_snapshot_re_derives_its_own_hash_and_identifier() -> None:
    pinned = snapshot()

    assert pinned["snapshot_hash"] == hash_excluding(dict(pinned), "snapshot_hash")
    assert pinned["snapshot_id"] == snapshot_id_for(
        [row["content_hash"] for row in pinned["documents"]]
    )


def test_the_partition_re_derives_its_own_hash() -> None:
    split = partition()

    assert split["partition_hash"] == hash_excluding(dict(split), "partition_hash")
    assert split["partition_id"].startswith(PARTITION_ID_PREFIX)


def test_the_boundary_re_derives_its_own_hash() -> None:
    declared = boundary()

    assert declared["boundary_hash"] == hash_excluding(dict(declared), "boundary_hash")
    assert declared["boundary_id"].startswith(BOUNDARY_ID_PREFIX)


def test_the_assessment_re_derives_its_own_hash() -> None:
    assessment = assess_novelty_within_boundary(**assessment_arguments())

    assert assessment["assessment_hash"] == hash_excluding(
        dict(assessment), "assessment_hash"
    )
    assert assessment["assessment_id"].startswith(ASSESSMENT_ID_PREFIX)


def test_every_report_identifier_is_re_derivable() -> None:
    pinned = snapshot()

    reports = revalidate_corpus_snapshot(
        pinned,
        observed_content_hashes=observed_hashes(),
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    for report in reports:
        assert report["report_id"].startswith(REPORT_ID_PREFIX)
        assert report["report_id"] == report_id_for(
            snapshot_id=pinned["snapshot_id"],
            document_id=report["document_id"],
            evaluated_at=EVALUATED_AT,
            policy_version=POLICY_VERSION,
        )


def test_every_holdout_handle_is_re_derivable_from_the_snapshot() -> None:
    pinned = snapshot()
    sealed = holdout(pinned)

    universe = {
        holdout_handle(pinned["snapshot_id"], document_id)
        for document_id in pinned_documents(pinned)
    }
    concealed = {
        *sealed["hidden_partition_handles"],
        *sealed["ood_partition_handles"],
        *sealed["adversarial_partition_handles"],
    }
    assert concealed <= universe
    assert concealed == {
        holdout_handle(pinned["snapshot_id"], document_id)
        for document_id in (HIDDEN_ID, OOD_ID, ADVERSARIAL_ID)
    }


def test_the_holdout_manifest_re_derives_the_firewalls_own_hash() -> None:
    sealed = holdout()

    assert sealed["manifest_hash"] == hash_excluding(dict(sealed), "manifest_hash")
    validate_artifact("holdout-manifest", sealed)


def test_the_holdout_binds_the_snapshots_own_content_hashes() -> None:
    pinned = snapshot()
    sealed = holdout(pinned)
    index = pinned_documents(pinned)

    assert set(sealed["content_hashes"]) <= {
        row["content_hash"] for row in index.values()
    }


def test_the_records_are_reproducible_without_supplied_identifiers() -> None:
    # No identifier is ever supplied by a caller: every one is derived from
    # content, so determinism is a property of the module rather than of the
    # caller's discipline.
    assert snapshot() == snapshot()
    assert partition() == partition()
    assert boundary() == boundary()
    assert holdout() == holdout()
    assert assess_novelty_within_boundary(
        **assessment_arguments()
    ) == assess_novelty_within_boundary(**assessment_arguments())


def test_the_integrity_reports_are_reproducible() -> None:
    def build() -> tuple:
        return build_snapshot_integrity_reports(
            snapshot(),
            observed_content_hashes=observed_hashes(),
            evaluated_at=EVALUATED_AT,
            policy_version=POLICY_VERSION,
        )

    assert build() == build()


def test_the_inputs_are_not_mutated() -> None:
    rows = documents()
    before = [dict(row) for row in rows]
    observed = observed_hashes()
    observed_before = dict(observed)

    pinned = snapshot(documents=rows)
    revalidate_corpus_snapshot(
        pinned,
        observed_content_hashes=observed,
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )
    snapshot_before = sha256_of_payload(pinned)

    arguments = seal_arguments(pinned)
    partition_before = dict(arguments["partition"])
    holdout(pinned)
    declared = boundary(pinned)
    boundary_before = dict(declared)
    assess_novelty_within_boundary(**assessment_arguments(boundary=declared))

    assert rows == before
    assert observed == observed_before
    assert sha256_of_payload(pinned) == snapshot_before
    assert arguments["partition"] == partition_before
    assert declared == boundary_before


def test_the_boundaries_hold_no_clock_and_no_randomness() -> None:
    tree = ast.parse(BOUNDARIES.read_text(encoding="utf-8"))
    called = {
        ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }

    assert "utc_now_iso" not in called
    # Unlike S05 and L05, not even the fallback path mints a random identifier:
    # every identifier here is a digest of the record's own content.
    assert "new_id" not in called
    assert not any(name.startswith("random.") for name in called)
    assert not any(name.startswith("secrets.") for name in called)
    assert "date.today" not in called
    assert "datetime.now" not in called


def test_no_record_carries_a_score_or_a_promotion() -> None:
    assessment = assess_novelty_within_boundary(**assessment_arguments())
    sealed = holdout()

    for record in (assessment, sealed, snapshot(), partition(), boundary()):
        for key in record:
            assert "score" not in key
            assert "fitness" not in key


def test_the_assessment_never_reaches_the_top_of_the_promotion_ladder() -> None:
    field, ceilings = scalar_enum_field(NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION)

    emitted = {
        assess_novelty_within_boundary(**assessment_arguments())[field],
        assess_novelty_within_boundary(
            **assessment_arguments(boundary=boundary(unsearched_sources=[]))
        )[field],
        assess_novelty_within_boundary(
            **assessment_arguments(closest_prior_art_refs=[])
        )[field],
    }

    assert ceilings[-1] not in emitted


def test_the_assessment_binds_the_snapshot_it_was_assessed_against() -> None:
    pinned = snapshot()
    assessment = assess_novelty_within_boundary(
        **assessment_arguments(boundary=boundary(pinned))
    )

    assert assessment["corpus_snapshot_hash"] == pinned["snapshot_hash"]
    validate_artifact(NOVELTY_SCHEMA, assessment)
