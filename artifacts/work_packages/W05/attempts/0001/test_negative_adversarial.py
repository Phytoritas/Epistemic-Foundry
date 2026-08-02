"""negative_and_adversarial_tests — the refusals, and whose refusals they are.

Two things are being proved here at once.  The first is that each unsafe resume,
cancel or reassessment is refused.  The second is *which module refused it*: a
resume from an unsealed or partial checkpoint must reach the caller carrying the
F05 machine's own code, a stop with no observed conditions the checkpoint
module's own error, and a retroactive fix the quarantine module's own violation.
A W05 paraphrase of any of those would quietly relocate a judgment this package
is supposed to delegate, and the caller would lose the distinction between "the
resume point was never committed" and "the resume point was committed but
partial".

The adversarial cases are the ones a caller with a motive would try: hiding the
remaining map behind an empty disclosure, rewriting an evaluator's digest to
match its edited content, and applying an approved evaluator fix back to the run
that produced it.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f05 import EvolveStateError, Transition
from epistemic_foundry.governance.quarantine import (
    QuarantineViolation,
    build_evaluator_mutation_proposal,
)
from epistemic_foundry.recovery.v4_w05 import (
    RecoveryWorkflowError,
    cancel_evolution_run,
    reassess_after_evaluator_drift,
    require_forward_only_application,
    resume_from_checkpoint,
    verify_committed_checkpoint,
)
from fixtures import (
    LOOP_ENTRY,
    LOOP_EXIT,
    OTHER_RUN_ID,
    ROOT,
    RUN_ID,
    cancel_arguments,
    checkpoint,
    forward_path,
    incomplete_checkpoint,
    loop_contract,
    reassessment_arguments,
    resume_arguments,
    sealed_bundle,
    stop_certificate,
    tampered_checkpoint,
    uncommitted_checkpoint,
)

# -- resume refusals belong to the machine -------------------------------


def test_resuming_from_an_incomplete_checkpoint_is_refused_by_the_machine() -> None:
    with pytest.raises(EvolveStateError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                checkpoint=incomplete_checkpoint(),
                stop_certificate=stop_certificate(),
            ),
        )

    assert caught.value.code == "CHECKPOINT_INCOMPLETE"
    assert not isinstance(caught.value, RecoveryWorkflowError)


def test_resuming_from_an_uncommitted_checkpoint_is_refused_by_the_machine() -> None:
    """No id means the resume point was never committed, not merely malformed."""
    with pytest.raises(EvolveStateError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                checkpoint=uncommitted_checkpoint(),
                stop_certificate=stop_certificate(),
            ),
        )

    assert caught.value.code == "RETURN_EDGE_UNCHECKPOINTED"


def test_the_two_bad_resume_points_are_distinguishable_from_each_other() -> None:
    """Both are schema-invalid, so a schema-first order would conflate them.

    An operator fixing a failed resume needs to know whether the checkpoint was
    never written or was written short, and those are different repairs.
    """
    codes = set()
    for record in (incomplete_checkpoint(), uncommitted_checkpoint()):
        with pytest.raises(EvolveStateError) as caught:
            resume_from_checkpoint(
                ROOT,
                **resume_arguments(
                    checkpoint=record, stop_certificate=stop_certificate()
                ),
            )
        codes.add(caught.value.code)

    assert len(codes) == 2


def test_resuming_from_a_checkpoint_edited_after_sealing_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                checkpoint=tampered_checkpoint(),
                stop_certificate=stop_certificate(),
            ),
        )

    assert caught.value.code == "CHECKPOINT_HASH_MISMATCH"


def test_resuming_from_a_checkpoint_no_schema_describes_is_refused() -> None:
    record = checkpoint()
    record["generation"] = -1
    record["checkpoint_hash"] = hash_excluding(record, "checkpoint_hash")

    with pytest.raises(RecoveryWorkflowError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(checkpoint=record, stop_certificate=stop_certificate()),
        )

    assert caught.value.code == "CHECKPOINT_NOT_CANONICAL"
    assert caught.value.context["errors"]


def test_resuming_another_runs_checkpoint_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                stop_certificate=stop_certificate(run_id=OTHER_RUN_ID),
            ),
        )

    assert caught.value.code == "CHECKPOINT_RUN_MISMATCHED"
    assert caught.value.context["requested_run_id"] == OTHER_RUN_ID


def test_a_continuation_taking_an_undeclared_move_is_refused_by_the_machine() -> None:
    with pytest.raises(EvolveStateError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                continuation=[
                    *forward_path(),
                    Transition(source="no_such_node", target=LOOP_ENTRY),
                ],
                stop_certificate=stop_certificate(),
            ),
        )

    assert caught.value.code == "NODE_UNDECLARED"


def test_a_resume_that_loops_past_its_own_budget_is_refused() -> None:
    later = checkpoint(2)
    with pytest.raises(EvolveStateError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                continuation=[
                    *forward_path(),
                    Transition(
                        source=LOOP_EXIT,
                        target=LOOP_ENTRY,
                        checkpoint_id=str(later["checkpoint_id"]),
                        checkpoint=later,
                    ),
                ],
                loop_contract=loop_contract(max_iterations=1),
                stop_certificate=stop_certificate(),
            ),
        )

    assert caught.value.code == "ITERATION_BUDGET_EXCEEDED"


def test_a_stop_certificate_naming_an_uncommitted_resume_point_is_refused() -> None:
    with pytest.raises(EvolveStateError) as caught:
        resume_from_checkpoint(
            ROOT,
            **resume_arguments(
                stop_certificate=stop_certificate(checkpoint_id="ECP-X")
            ),
        )

    assert caught.value.code == "STOP_CERTIFICATE_INVALID"


def test_a_resume_that_never_ends_cannot_be_certified_at_all() -> None:
    """A continuation still in flight is not a resume anyone can verify.

    The stop certificate is a required argument precisely so that accepting one
    would never mean this module deciding a subset of the machine's gate for
    itself; the machine's own EF4-I62 refusal is what a caller sees.
    """
    arguments = resume_arguments()
    arguments.pop("stop_certificate")

    with pytest.raises(TypeError):
        resume_from_checkpoint(ROOT, **arguments)

    with pytest.raises(EvolveStateError) as caught:
        resume_from_checkpoint(ROOT, **resume_arguments(stop_certificate=None))

    assert caught.value.code == "RUN_UNTERMINATED"


def test_verifying_a_checkpoint_that_lost_a_component_names_the_gap() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        verify_committed_checkpoint(incomplete_checkpoint())

    assert caught.value.code == "CHECKPOINT_COMPONENTS_MISSING"
    assert caught.value.context["missing"]


# -- cancel refusals -----------------------------------------------------


def test_a_cancel_hiding_remaining_candidates_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(
            **cancel_arguments(disclosed_unresolved_candidates=["CAND-2"])
        )

    assert caught.value.code == "CANCEL_PARTIAL_WORK_HIDDEN"
    assert caught.value.context["hidden"] == ["CAND-3"]


def test_a_cancel_publishing_an_empty_remaining_map_is_refused() -> None:
    """The obvious way to hide partial work is to disclose nothing at all."""
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(
            **cancel_arguments(
                disclosed_unresolved_candidates=[],
                disclosed_unassessed_niches=[],
            )
        )

    assert caught.value.code == "CANCEL_PARTIAL_WORK_HIDDEN"


def test_a_cancel_hiding_remaining_niches_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(**cancel_arguments(disclosed_unassessed_niches=[]))

    assert caught.value.code == "CANCEL_PARTIAL_WORK_HIDDEN"
    assert caught.value.context["hidden"] == ["NICHE-2"]


def test_a_cancel_inventing_remaining_work_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(
            **cancel_arguments(
                disclosed_unresolved_candidates=["CAND-2", "CAND-3", "CAND-99"]
            )
        )

    assert caught.value.code == "CANCEL_DISCLOSURE_UNACCOUNTED"
    assert caught.value.context["unaccounted"] == ["CAND-99"]


def test_a_cancel_evaluating_a_candidate_it_never_proposed_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(
            **cancel_arguments(evaluated_candidate_ids=["CAND-1", "CAND-404"])
        )

    assert caught.value.code == "CANCEL_COUNTS_UNRECONCILED"
    assert caught.value.context["unaccounted"] == ["CAND-404"]


def test_a_cancel_naming_a_stop_reason_nobody_classifies_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(**cancel_arguments(stop_reason="operator_changed_mind"))

    assert caught.value.code == "CANCEL_STOP_REASON_UNDECLARED"


def test_a_cancel_with_no_observed_condition_is_refused_by_its_own_builder() -> None:
    with pytest.raises(ValueError) as caught:
        cancel_evolution_run(**cancel_arguments(conditions_observed=[]))

    assert not isinstance(caught.value, RecoveryWorkflowError)
    assert "crash" in str(caught.value)


def test_a_cancel_naming_another_runs_checkpoint_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(
            **cancel_arguments(checkpoint=checkpoint(run_id=OTHER_RUN_ID))
        )

    assert caught.value.code == "CHECKPOINT_RUN_MISMATCHED"


def test_a_cancel_against_an_incomplete_resume_point_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(**cancel_arguments(checkpoint=incomplete_checkpoint()))

    assert caught.value.code == "CHECKPOINT_COMPONENTS_MISSING"


def test_a_cancel_repeating_a_candidate_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        cancel_evolution_run(
            **cancel_arguments(proposed_candidate_ids=["CAND-1", "CAND-1"])
        )

    assert caught.value.code == "INPUT_INVALID"


# -- drift reassessment refusals -----------------------------------------


def test_a_reassessment_without_drift_is_refused() -> None:
    """Marking sound comparisons doubtful is itself a way to rewrite a run."""
    with pytest.raises(RecoveryWorkflowError) as caught:
        reassess_after_evaluator_drift(
            **reassessment_arguments(current_bundle=sealed_bundle())
        )

    assert caught.value.code == "DRIFT_ABSENT"


def test_drift_disguised_by_rewriting_the_recorded_digest_is_still_caught() -> None:
    """The firewall recomputes from content, so the stored hash proves nothing."""
    from fixtures import disguised_bundle

    record = reassess_after_evaluator_drift(
        **reassessment_arguments(current_bundle=disguised_bundle())
    )

    assert record["counts"]["affected"] == 2
    assert record["observed_bundle_hash"] != record["sealed_bundle_hash"]


def test_a_comparison_bound_to_no_evaluator_is_refused_rather_than_assumed_safe() -> (
    None
):
    with pytest.raises(RecoveryWorkflowError) as caught:
        reassess_after_evaluator_drift(
            **reassessment_arguments(
                comparisons=[{"comparison_id": "CMP-9", "candidate_ids": ["CAND-1"]}]
            )
        )

    assert caught.value.code == "REASSESSMENT_COMPARISON_UNBOUND"
    assert caught.value.context["comparison_id"] == "CMP-9"


def test_a_repeated_comparison_id_is_refused() -> None:
    row = {"comparison_id": "CMP-1", "evaluator_bundle_id": "EVAL-W05-1"}
    with pytest.raises(RecoveryWorkflowError) as caught:
        reassess_after_evaluator_drift(
            **reassessment_arguments(comparisons=[row, dict(row)])
        )

    assert caught.value.code == "INPUT_INVALID"


def test_an_unevidenced_defect_is_refused_by_the_quarantine_module() -> None:
    with pytest.raises(QuarantineViolation):
        reassess_after_evaluator_drift(
            **reassessment_arguments(evidence_artifact_ids=[])
        )


def test_an_unknown_defect_class_is_refused_by_the_quarantine_module() -> None:
    with pytest.raises(QuarantineViolation) as caught:
        reassess_after_evaluator_drift(
            **reassessment_arguments(defect_class="evaluator_felt_wrong")
        )

    assert not isinstance(caught.value, RecoveryWorkflowError)


def test_applying_the_fix_to_the_run_that_produced_it_is_refused() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())
    proposal = _proposal()

    with pytest.raises(QuarantineViolation) as caught:
        require_forward_only_application(record, proposal, target_run_id=RUN_ID)

    assert "never rewrite completed judgments" in str(caught.value)


def test_an_approved_fix_still_cannot_reach_the_run_that_produced_it() -> None:
    """Approval authorizes a new sealed run, never a rewrite of a finished one."""
    record = reassess_after_evaluator_drift(**reassessment_arguments())
    approved = {**_proposal(), "status": "APPROVED_FOR_FUTURE"}

    with pytest.raises(QuarantineViolation):
        require_forward_only_application(record, approved, target_run_id=RUN_ID)


def test_a_quarantined_fix_cannot_reach_any_other_run_either() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())

    with pytest.raises(QuarantineViolation) as caught:
        require_forward_only_application(
            record, _proposal(), target_run_id=OTHER_RUN_ID
        )

    assert "may not" in str(caught.value)


def test_a_reassessment_tested_against_somebody_elses_proposal_is_refused() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())
    other = _proposal(proposal_id="EMP-W05-OTHER")

    with pytest.raises(RecoveryWorkflowError) as caught:
        require_forward_only_application(record, other, target_run_id=OTHER_RUN_ID)

    assert caught.value.code == "REASSESSMENT_PROPOSAL_UNBOUND"


def _proposal(proposal_id: str = "EMP-W05-1") -> dict:
    from fixtures import A_DEFECT_CLASS

    return build_evaluator_mutation_proposal(
        source_run_id=RUN_ID,
        current_evaluator_bundle_id="EVAL-W05-1",
        defect_class=A_DEFECT_CLASS,
        evidence_artifact_ids=["EV-1"],
        proposed_change="re-derive the metric contract before the next seal",
        proposal_id=proposal_id,
    )


# -- shape refusals ------------------------------------------------------


@pytest.mark.parametrize("given", [None, "checkpoint", 7, []])
def test_a_checkpoint_that_is_not_a_mapping_is_refused(given: object) -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        verify_committed_checkpoint(given)  # type: ignore[arg-type]

    assert caught.value.code == "INPUT_INVALID"


def test_a_continuation_that_is_not_a_sequence_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        resume_from_checkpoint(ROOT, **resume_arguments(continuation="forward"))

    assert caught.value.code == "INPUT_INVALID"


def test_a_firewall_that_is_not_a_firewall_is_refused() -> None:
    with pytest.raises(RecoveryWorkflowError) as caught:
        reassess_after_evaluator_drift(**reassessment_arguments(firewall=object()))

    assert caught.value.code == "INPUT_INVALID"
