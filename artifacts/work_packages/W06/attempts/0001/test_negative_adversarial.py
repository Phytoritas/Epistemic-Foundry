"""negative_and_adversarial_tests — every refusal, and the ones that travel out.

The crash-boundary defects the gate owns — a lost candidate, one driven into two
terminal states, a replay that resolved its pins but did not reproduce, a replay
that names a different run — are each provoked and each named by its own code.
The refusals the gate delegates — an unmade comparison, an unreconciled fan-out, a
retroactive evaluator update, an unaccounted schedule, an F05-illegal resume —
travel out under their owners' types, never a W06 paraphrase.  The adversarial
cases are the ones a version label or a stored verdict cannot catch: a replay
report whose equivalence was rewritten to look exact, and an evaluator update
aimed back at the very run it came from.
"""

from __future__ import annotations

import fixtures as fx
import pytest
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f05 import EvolveStateError
from epistemic_foundry.evolution_chamber.reconciliation import ReconciliationFailed
from epistemic_foundry.governance.quarantine import QuarantineViolation
from epistemic_foundry.recovery.v4_w06 import (
    RecoveryGateError,
    reconcile_recovery,
    require_evaluator_update_future_only,
    require_recovered_reconciliation,
    verify_crash_recovery,
)
from epistemic_foundry.release.replay import ReplayVerificationFailed
from epistemic_foundry.scheduler.v4_n06 import IntegrationError


# -- crash-boundary reconciliation ---------------------------------------


def test_a_candidate_lost_across_the_crash_is_refused() -> None:
    # CAND-4 was committed before the crash but the resume shows no trace of it
    # in any stage or terminal state: the crash dropped it.
    report = reconcile_recovery(
        **fx.reconcile_arguments(
            expected_candidate_ids=["CAND-1", "CAND-2", "CAND-3", "CAND-4"]
        )
    )

    assert report["lost"] == ["CAND-4"]
    assert report["recovered"] is False
    with pytest.raises(RecoveryGateError) as caught:
        require_recovered_reconciliation(report)
    assert caught.value.code == "RECOVERY_CANDIDATE_LOST"
    assert caught.value.context["lost"] == ["CAND-4"]


def test_a_candidate_driven_into_two_terminal_states_is_refused() -> None:
    # CAND-1 is both persisted and failed: the resume counted it twice.
    report = reconcile_recovery(**fx.reconcile_arguments(failed=["CAND-1"]))

    assert report["double_counted"] == ["CAND-1"]
    with pytest.raises(RecoveryGateError) as caught:
        require_recovered_reconciliation(report)
    assert caught.value.code == "RECOVERY_CANDIDATE_DOUBLE_COUNTED"


def test_double_counting_is_reported_before_a_lost_candidate() -> None:
    # A resume can inflate and deflate at once; the double count is the more
    # immediate corruption of the population totals and is named first.
    report = reconcile_recovery(
        **fx.reconcile_arguments(
            expected_candidate_ids=["CAND-1", "CAND-2", "CAND-3", "CAND-9"],
            failed=["CAND-1"],
        )
    )

    with pytest.raises(RecoveryGateError) as caught:
        require_recovered_reconciliation(report)
    assert caught.value.code == "RECOVERY_CANDIDATE_DOUBLE_COUNTED"


def test_an_unreconciled_fanout_travels_out_under_its_owners_type() -> None:
    # A candidate proposed but never persisted, with no terminal disposition, is
    # the reconciliation module's own ``missing`` — its refusal, not the gate's.
    report = reconcile_recovery(
        **fx.reconcile_arguments(
            expected_candidate_ids=["CAND-1", "CAND-2"],
            proposed=["CAND-1", "CAND-2"],
            generated=["CAND-1", "CAND-2"],
            evaluated=["CAND-1", "CAND-2"],
            persisted=["CAND-1"],
        )
    )

    assert report["lost"] == []
    with pytest.raises(ReconciliationFailed):
        require_recovered_reconciliation(report)


def test_the_reconciliation_refuses_a_candidate_named_twice() -> None:
    with pytest.raises(RecoveryGateError) as caught:
        reconcile_recovery(**fx.reconcile_arguments(proposed=["CAND-1", "CAND-1"]))
    assert caught.value.code == "INPUT_INVALID"


# -- replay honesty ------------------------------------------------------


def test_a_replay_that_resolved_but_did_not_reproduce_is_refused() -> None:
    with pytest.raises(RecoveryGateError) as caught:
        verify_crash_recovery(
            fx.ROOT,
            **fx.recovery_arguments(replay_report=fx.replay_report(mismatches=1)),
        )
    assert caught.value.code == "REPLAY_NOT_REPRODUCED"


def test_a_replay_that_could_not_resolve_its_pins_travels_out_as_not_comparable() -> (
    None
):
    with pytest.raises(ReplayVerificationFailed):
        verify_crash_recovery(
            fx.ROOT,
            **fx.recovery_arguments(
                replay_report=fx.replay_report(unavailable_pins=["model:PIN"])
            ),
        )


def test_a_replay_naming_a_different_run_is_refused() -> None:
    with pytest.raises(RecoveryGateError) as caught:
        verify_crash_recovery(
            fx.ROOT,
            **fx.recovery_arguments(
                replay_report=fx.replay_report(source_run_id=fx.OTHER_RUN_ID)
            ),
        )
    assert caught.value.code == "RECOVERY_RUN_MISBOUND"


def test_a_replay_report_with_a_forged_verdict_is_refused() -> None:
    # The adversarial case: a report whose equivalence was rewritten to look
    # exact while its pins were never resolved. The gate re-derives the digest
    # and refuses the forgery rather than trusting the rewritten field.
    forged = fx.replay_report(unavailable_pins=["model:PIN"])
    forged["event_equivalence"] = "EXACT"  # a claim the content does not support
    # left with a stale report_hash on purpose: authenticity must catch it
    with pytest.raises(RecoveryGateError) as caught:
        verify_crash_recovery(fx.ROOT, **fx.recovery_arguments(replay_report=forged))
    assert caught.value.code == "INPUT_INVALID"


def test_a_replay_report_forged_and_rehashed_is_still_caught_as_not_reproduced() -> (
    None
):
    # Even a self-consistent forgery cannot manufacture reproduction: rehashing
    # keeps the record honest, but the equivalence the owner derives is still
    # drift, and the gate refuses it.
    forged = fx.replay_report(mismatches=1)
    forged["report_hash"] = hash_excluding(forged, "report_hash")
    with pytest.raises(RecoveryGateError) as caught:
        verify_crash_recovery(fx.ROOT, **fx.recovery_arguments(replay_report=forged))
    assert caught.value.code == "REPLAY_NOT_REPRODUCED"


# -- future-only evaluator update ----------------------------------------


def test_applying_an_update_to_the_recovered_run_is_refused() -> None:
    # The retroactive case: the run being recovered may never be re-scored by an
    # update born from it. The prohibition is quarantine's and travels out.
    with pytest.raises(QuarantineViolation):
        require_evaluator_update_future_only(
            fx.reassessment_for(fx.RUN_ID),
            fx.proposal_for(fx.RUN_ID),
            recovered_run_id=fx.RUN_ID,
        )


def test_an_inert_proposal_may_not_reach_any_run() -> None:
    # A freshly built proposal is quarantined; even a different future run may
    # not apply it until it is qualified.
    with pytest.raises(QuarantineViolation):
        require_evaluator_update_future_only(
            fx.reassessment_for(fx.RUN_ID),
            fx.proposal_for(fx.RUN_ID),
            recovered_run_id=fx.OTHER_RUN_ID,
        )


def test_a_reassessment_bound_to_a_different_proposal_is_refused() -> None:
    # The reassessment names proposal EMP-W06-1; applying an unrelated proposal
    # proves nothing about its own fix, and W05 refuses the mismatch.
    from epistemic_foundry.recovery.v4_w05 import RecoveryWorkflowError

    other = fx.approved_proposal_for(fx.RUN_ID)
    other["proposal_id"] = "EMP-W06-OTHER"
    other["proposal_hash"] = hash_excluding(other, "proposal_hash")
    with pytest.raises(RecoveryWorkflowError) as caught:
        require_evaluator_update_future_only(
            fx.reassessment_for(fx.RUN_ID), other, recovered_run_id=fx.OTHER_RUN_ID
        )
    assert caught.value.code == "REASSESSMENT_PROPOSAL_UNBOUND"


# -- composed resume and schedule ----------------------------------------


def test_a_resume_from_a_tampered_checkpoint_travels_out_from_w05() -> None:
    # A checkpoint edited after sealing is caught by W05's own re-derivation, and
    # its ``RecoveryWorkflowError`` reaches the caller rather than a W06 code.
    from epistemic_foundry.recovery.v4_w05 import RecoveryWorkflowError

    tampered = fx.checkpoint()
    tampered["budget_state_id"] = "BUDGET-EDITED"
    with pytest.raises((RecoveryWorkflowError, EvolveStateError)):
        verify_crash_recovery(fx.ROOT, **fx.recovery_arguments(checkpoint=tampered))


def test_a_resume_over_a_run_the_certificate_disowns_is_refused() -> None:
    from epistemic_foundry.recovery.v4_w05 import RecoveryWorkflowError

    with pytest.raises((RecoveryWorkflowError, EvolveStateError)):
        verify_crash_recovery(
            fx.ROOT,
            **fx.recovery_arguments(
                stop_certificate=fx.stop_certificate(run_id=fx.OTHER_RUN_ID)
            ),
        )


def test_an_unaccounted_schedule_travels_out_from_n06() -> None:
    # A schedule the gate is handed but N06 refuses reaches the caller as an
    # ``IntegrationError``, not a W06 code.
    broken = dict(fx.integration_report())
    broken["shed_admissions"] = [{"candidate_id": "CAND-1"}]
    with pytest.raises(IntegrationError):
        verify_crash_recovery(
            fx.ROOT, integration_report=broken, **fx.recovery_arguments()
        )


# -- shape guards --------------------------------------------------------


def test_a_non_mapping_replay_report_is_refused() -> None:
    with pytest.raises(RecoveryGateError) as caught:
        verify_crash_recovery(
            fx.ROOT, **fx.recovery_arguments(replay_report=["not", "a", "map"])
        )
    assert caught.value.code == "INPUT_INVALID"


def test_a_non_sequence_expected_roster_is_refused() -> None:
    with pytest.raises(RecoveryGateError) as caught:
        reconcile_recovery(**fx.reconcile_arguments(expected_candidate_ids="CAND-1"))
    assert caught.value.code == "INPUT_INVALID"
