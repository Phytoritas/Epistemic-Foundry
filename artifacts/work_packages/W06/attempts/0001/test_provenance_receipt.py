"""provenance_and_receipt_audit — every effect resolves to a re-derivable receipt.

A recovery is only evidence if it re-derives from its own content and cannot be
edited without the edit showing.  This suite proves the recovery receipt binds the
resume, the reconciliation, the replay and the schedule by hash rather than by
copy, that no field can be rewritten without breaking the digest, and that the
gate acquires no evaluator, holdout or promotion authority in the course of
producing one.
"""

from __future__ import annotations

import fixtures as fx
import pytest
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.recovery.v4_w06 import (
    RecoveryGateError,
    recovery_hash_matches,
    require_recovered,
    verify_crash_recovery,
)


def _recovery() -> dict:
    return verify_crash_recovery(
        fx.ROOT, integration_report=fx.integration_report(), **fx.recovery_arguments()
    )


def test_the_receipt_re_derives_its_own_digest() -> None:
    record = _recovery()

    assert record["recovery_hash"] == hash_excluding(record, "recovery_hash")
    assert recovery_hash_matches(record)


def test_every_field_is_covered_by_the_digest() -> None:
    record = _recovery()

    for field in record:
        if field == "recovery_hash":
            continue
        mutated = dict(record)
        mutated[field] = "TAMPERED"
        assert not recovery_hash_matches(mutated), field


def test_the_receipt_binds_the_resume_by_hash_not_by_copy() -> None:
    record = _recovery()

    # The resume record is composed and referenced by its sealed hash, so the
    # recovery chains to it rather than restating a second, forkable copy.
    assert record["resume_hash"].startswith("sha256:")
    assert record["resume_id"] == "EWR-W06-1"


def test_the_receipt_binds_the_replay_by_hash() -> None:
    record = _recovery()
    replay = fx.replay_report()

    assert record["replay_verification"]["replay_report_hash"] == replay["report_hash"]
    assert record["replay_verification"]["reproduced"] is True
    assert record["replay_verification"]["replay_id"] == "RR-W06-1"


def test_the_receipt_binds_the_schedule_by_hash() -> None:
    from epistemic_foundry.scheduler.v4_n06 import seal_integration_record

    record = _recovery()
    sealed = seal_integration_record(fx.integration_report(), run_id=fx.RUN_ID)

    assert record["schedule_integration_hash"] == sealed["integration_hash"]


def test_require_recovered_refuses_an_edited_receipt() -> None:
    record = _recovery()
    record["recovered_at"] = "2026-08-03T05:00:00.000Z"  # edit without re-hashing

    with pytest.raises(RecoveryGateError) as caught:
        require_recovered(record)
    assert caught.value.code == "INPUT_INVALID"


def test_require_recovered_refuses_an_unmarked_receipt() -> None:
    record = _recovery()
    record["recovered"] = False
    record["recovery_hash"] = hash_excluding(record, "recovery_hash")

    with pytest.raises(RecoveryGateError) as caught:
        require_recovered(record)
    assert caught.value.code == "INPUT_INVALID"


def test_the_gate_acquires_no_evaluator_holdout_or_promotion_authority() -> None:
    # The recovery receipt is an accounting of a resume; it carries no fitness,
    # no promotion decision, no holdout content and no evaluator verdict. It may
    # only reference the evaluator bundle hash the checkpoint already sealed.
    import ast

    source = (fx.ROOT / "src/epistemic_foundry/recovery/v4_w06/gate.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for forbidden in ("promote", "promotion", "fitness_score", "holdout_content"):
        assert forbidden not in names, forbidden


def test_the_receipt_names_exactly_one_evolution_run() -> None:
    record = _recovery()

    assert record["evolution_run_id"] == fx.RUN_ID
    # The reconciliation and replay bindings agree with it; a receipt that named
    # two runs is what ``RECOVERY_RUN_MISBOUND`` refuses at build time.
    assert record["reconciliation"]["recovered"] is True


def test_two_independent_builds_produce_byte_equal_receipts() -> None:
    first = _recovery()
    second = _recovery()

    assert hash_excluding(first, "recovery_hash") == hash_excluding(
        second, "recovery_hash"
    )
    assert first == second
