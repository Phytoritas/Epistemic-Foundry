"""unit_and_contract_tests — the three moments a stopped search passes through.

A run resumed from a committed checkpoint is accepted by the F05 machine as the
same search continuing; a cancel publishes what it left behind through the
canonical certificate; and a drifted evaluator produces a record that marks the
comparisons it touched and binds the fix to a future run.

These are the paths a healthy runtime takes.  Each of the orderly stop reasons
must be usable for a cancel, because a workflow that admitted only one way to
stop would force runs to misreport why they stopped, and an adverse stop must be
usable too — a run cancelled for safety is still a cancel.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.evolution.v4_f05 import (
    Transition,
    evaluate_run,
    require_valid_run,
)
from epistemic_foundry.evolution_chamber.checkpoint import (
    ADVERSE_STOPS,
    ORDERLY_STOPS,
    search_exhausted_within_scope,
    stop_was_orderly,
)
from epistemic_foundry.recovery.v4_w05 import (
    COMPARISON_POTENTIALLY_INVALID,
    COMPARISON_UNAFFECTED,
    cancel_evolution_run,
    reassess_after_evaluator_drift,
    resume_from_checkpoint,
    verify_committed_checkpoint,
)
from fixtures import (
    LOOP_ENTRY,
    LOOP_EXIT,
    RECORDED_AT,
    ROOT,
    RUN_ID,
    cancel_arguments,
    checkpoint,
    forward_path,
    loop_contract,
    reassessment_arguments,
    resume_arguments,
    stop_certificate,
)

# -- resume --------------------------------------------------------------


def test_a_resume_across_a_committed_checkpoint_is_accepted() -> None:
    record = resume_from_checkpoint(
        ROOT, **resume_arguments(stop_certificate=stop_certificate())
    )

    assert record["checkpoint_id"] == checkpoint()["checkpoint_id"]
    assert record["evolution_run_id"] == RUN_ID
    assert record["run_report"]["valid"] is True


def test_the_resume_is_expressed_as_a_return_edge_across_that_checkpoint() -> None:
    """The resumed run's own accounting must show the edge, not just assert it."""
    record = resume_from_checkpoint(
        ROOT, **resume_arguments(stop_certificate=stop_certificate())
    )

    assert record["counts"]["return_edges"] == 1
    assert record["loop"] == {
        "entry_node_id": LOOP_ENTRY,
        "exit_node_id": LOOP_EXIT,
    }


def test_the_resumed_run_passes_the_machines_own_gate() -> None:
    """The verdict belongs to F05, so it must survive being asked again."""
    record = resume_from_checkpoint(
        ROOT, **resume_arguments(stop_certificate=stop_certificate())
    )

    require_valid_run(record["run_report"])


def test_the_resume_record_names_the_certificate_the_run_left_through() -> None:
    # EF4-I62: a run leaves the machine only through a typed stop certificate,
    # so the resume record binds the one this continuation ended on.
    record = resume_from_checkpoint(ROOT, **resume_arguments())

    assert record["stop_certificate_id"] == stop_certificate()["certificate_id"]
    assert record["run_report"]["terminated"] is True


def test_resuming_twice_from_successive_checkpoints_stays_within_budget() -> None:
    later = checkpoint(2)
    continuation = [
        *forward_path(),
        Transition(
            source=LOOP_EXIT,
            target=LOOP_ENTRY,
            checkpoint_id=str(later["checkpoint_id"]),
            checkpoint=later,
        ),
    ]
    record = resume_from_checkpoint(
        ROOT,
        **resume_arguments(
            continuation=continuation,
            stop_certificate=stop_certificate(
                checkpoint_id=str(later["checkpoint_id"])
            ),
        ),
    )

    assert record["counts"]["return_edges"] == 2
    assert record["run_report"]["iterations"]["over_budget"] is False


def test_the_resume_carries_the_generation_it_restores() -> None:
    record = resume_from_checkpoint(
        ROOT,
        **resume_arguments(
            checkpoint=checkpoint(2),
            stop_certificate=stop_certificate(checkpoint_id="ECP-W05-2"),
        ),
    )

    assert record["generation"] == 2


def test_a_committed_checkpoint_verifies_on_its_own() -> None:
    committed = verify_committed_checkpoint(checkpoint())

    assert committed["checkpoint_id"] == "ECP-W05-1"
    assert committed["evolution_run_id"] == RUN_ID
    assert committed["checkpoint_hash"] == checkpoint()["checkpoint_hash"]


# -- cancel --------------------------------------------------------------


def test_a_cancel_produces_a_certificate_with_partial_work_visible() -> None:
    record = cancel_evolution_run(**cancel_arguments())

    assert record["certificate"]["partial_results_visible"] is True
    assert record["certificate"]["checkpoint_id"] == "ECP-W05-1"


def test_the_remaining_map_is_derived_from_the_runs_own_accounting() -> None:
    """What is left is computed, not asserted, so it cannot be quietly empty."""
    record = cancel_evolution_run(**cancel_arguments())

    assert record["unresolved_candidates"] == ["CAND-2", "CAND-3"]
    assert record["unassessed_niches"] == ["NICHE-2"]


def test_the_cancel_counts_reconcile_exactly() -> None:
    record = cancel_evolution_run(**cancel_arguments())
    counts = record["counts"]

    assert counts["proposed_candidates"] == (
        counts["evaluated_candidates"] + counts["unresolved_candidates"]
    )
    assert counts["mapped_niches"] == (
        counts["assessed_niches"] + counts["unassessed_niches"]
    )


def test_a_disclosure_matching_the_derived_map_is_accepted() -> None:
    record = cancel_evolution_run(
        **cancel_arguments(
            disclosed_unresolved_candidates=["CAND-3", "CAND-2"],
            disclosed_unassessed_niches=["NICHE-2"],
        )
    )

    assert record["unresolved_candidates"] == ["CAND-2", "CAND-3"]


@pytest.mark.parametrize("reason", sorted(ORDERLY_STOPS))
def test_every_orderly_stop_reason_can_carry_a_cancel(reason: str) -> None:
    record = cancel_evolution_run(**cancel_arguments(stop_reason=reason))

    assert record["orderly"] is True
    assert stop_was_orderly(record["certificate"]) is True


@pytest.mark.parametrize("reason", sorted(ADVERSE_STOPS))
def test_an_adverse_cancel_is_recorded_as_adverse_rather_than_refused(
    reason: str,
) -> None:
    # A run cancelled because something went wrong is still a cancel; hiding
    # that it was adverse is what would be wrong.
    record = cancel_evolution_run(**cancel_arguments(stop_reason=reason))

    assert record["orderly"] is False


def test_a_cancel_with_nothing_left_does_not_claim_exhausted_scope_falsely() -> None:
    """An orderly stop with no unassessed niche is the one claim of coverage.

    The judgment is the checkpoint module's; this only shows the certificate
    this workflow produces feeds it correctly in both directions.
    """
    partial = cancel_evolution_run(**cancel_arguments())
    complete = cancel_evolution_run(
        **cancel_arguments(
            evaluated_candidate_ids=["CAND-1", "CAND-2", "CAND-3"],
            assessed_niche_ids=["NICHE-1", "NICHE-2"],
        )
    )

    assert search_exhausted_within_scope(partial["certificate"]) is False
    assert search_exhausted_within_scope(complete["certificate"]) is True
    assert complete["counts"]["unresolved_candidates"] == 0


def test_the_cancel_certificate_is_the_one_the_machine_would_accept() -> None:
    """A cancel that F05 would refuse is a cancel nobody can resume past."""
    record = cancel_evolution_run(**cancel_arguments())
    report = evaluate_run(
        ROOT,
        transitions=[
            *forward_path(),
            Transition(
                source=LOOP_EXIT,
                target=LOOP_ENTRY,
                checkpoint_id=str(record["checkpoint_id"]),
                checkpoint=checkpoint(),
            ),
        ],
        loop_contract=loop_contract(),
        stop_certificate=record["certificate"],
        dry_rounds_observed=1,
    )

    require_valid_run(report)


# -- evaluator drift -----------------------------------------------------


def test_drift_yields_a_reassessment_marking_the_affected_comparisons() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())
    marked = {
        row["comparison_id"]: row["reassessment_status"]
        for row in record["affected_comparisons"]
    }

    assert marked == {
        "CMP-1": COMPARISON_POTENTIALLY_INVALID,
        "CMP-2": COMPARISON_POTENTIALLY_INVALID,
    }


def test_comparisons_under_another_evaluator_are_left_alone() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())

    assert [row["comparison_id"] for row in record["unaffected_comparisons"]] == [
        "CMP-3"
    ]
    assert record["unaffected_comparisons"][0]["reassessment_status"] == (
        COMPARISON_UNAFFECTED
    )


def test_every_reviewed_comparison_survives_the_reassessment() -> None:
    """Marking is not deletion: the record must still hold all three rows."""
    record = reassess_after_evaluator_drift(**reassessment_arguments())

    assert record["counts"] == {"affected": 2, "reviewed": 3, "unaffected": 1}
    assert record["counts"]["reviewed"] == (
        record["counts"]["affected"] + record["counts"]["unaffected"]
    )


def test_the_reassessment_binds_a_quarantined_future_run_proposal() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())

    assert record["quarantine_proposal_id"] == "EMP-W05-1"
    assert record["retroactive_effect_prohibited"] is True
    assert record["source_run_id"] == RUN_ID


def test_the_reassessment_names_both_the_sealed_and_the_observed_evaluator() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())

    assert record["sealed_bundle_id"] == "EVAL-W05-1"
    assert record["sealed_bundle_hash"] != record["observed_bundle_hash"]
    assert record["drift_detail"]


def test_a_reassessment_with_no_comparison_to_place_is_still_recorded() -> None:
    # Drift found before any comparison was made is a real finding: the
    # evaluator is no longer the sealed one, even if nothing was judged yet.
    record = reassess_after_evaluator_drift(**reassessment_arguments(comparisons=[]))

    assert record["counts"] == {"affected": 0, "reviewed": 0, "unaffected": 0}
    assert record["quarantine_proposal_id"] == "EMP-W05-1"


def test_the_reassessment_carries_no_score_of_its_own() -> None:
    """The record must not be a rescoring surface, not even by accident."""
    record = reassess_after_evaluator_drift(**reassessment_arguments())
    scored = sorted(
        key for key in record if "score" in key or "fitness" in key or "rank" in key
    )

    assert scored == []
    assert record["reassessed_at"] == reassessment_arguments()["reassessed_at"]
    assert record["affected_comparisons"][0]["comparison"]["recorded_at"] == RECORDED_AT
