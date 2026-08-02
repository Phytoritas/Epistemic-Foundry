"""provenance_and_receipt_audit — every record re-derives, and nothing is edited.

A resume, a cancel and a reassessment are all claims about a run that has already
happened, so each is only worth as much as its own re-derivation.  Every record
this workflow produces carries a digest computed over exactly itself, and the
records it composes — the stop certificate, the quarantine proposal — keep their
own digests intact inside it rather than being flattened into a summary.

Determinism is checked directly, because a record that differs between two
evaluations of the same inputs cannot be replayed.  There is no clock anywhere in
the workflow: every timestamp is a required argument, so a record can never
acquire the moment it was written instead of the moment being described.

And the inputs are compared before and after each call.  A workflow that mutated
the checkpoint or the comparisons it was handed would leave the caller holding a
record of something other than what it passed in.
"""

from __future__ import annotations

import inspect
import json
from copy import deepcopy

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f05 import Transition, evaluate_run
from epistemic_foundry.recovery.v4_w05 import (
    cancel_evolution_run,
    reassess_after_evaluator_drift,
    resume_from_checkpoint,
)
from fixtures import (
    ROOT,
    cancel_arguments,
    checkpoint,
    comparisons,
    reassessment_arguments,
    resume_arguments,
    stop_certificate,
)

ENGINE = ROOT / "src/epistemic_foundry/recovery/v4_w05/workflow.py"


def resumed() -> dict:
    return resume_from_checkpoint(
        ROOT, **resume_arguments(stop_certificate=stop_certificate())
    )


# -- digests -------------------------------------------------------------


def test_the_resume_record_re_derives_its_own_digest() -> None:
    record = resumed()

    assert record["resume_hash"] == hash_excluding(record, "resume_hash")


def test_the_resume_record_carries_the_checkpoints_own_digest() -> None:
    record = resumed()

    assert record["checkpoint_hash"] == checkpoint()["checkpoint_hash"]


def test_the_cancellation_re_derives_its_own_digest() -> None:
    record = cancel_evolution_run(**cancel_arguments())

    assert record["cancellation_hash"] == hash_excluding(record, "cancellation_hash")


def test_the_embedded_stop_certificate_keeps_its_own_digest() -> None:
    """The certificate is composed whole, not summarised into the cancellation."""
    record = cancel_evolution_run(**cancel_arguments())
    certificate = record["certificate"]

    assert certificate["certificate_hash"] == hash_excluding(
        certificate, "certificate_hash"
    )


def test_the_reassessment_re_derives_its_own_digest() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())

    assert record["reassessment_hash"] == hash_excluding(record, "reassessment_hash")


def test_the_resume_record_embeds_the_machines_report_verbatim() -> None:
    """The verdict is quoted, not restated, so it can be re-checked as it stands."""
    arguments = resume_arguments(stop_certificate=stop_certificate())
    record = resume_from_checkpoint(ROOT, **arguments)
    edge = record["run_report"]

    assert edge == evaluate_run(
        ROOT,
        transitions=[
            Transition(
                source=edge["loop"]["exit_node_id"],
                target=edge["loop"]["entry_node_id"],
                checkpoint_id=str(arguments["checkpoint"]["checkpoint_id"]),
                checkpoint=arguments["checkpoint"],
            ),
            *arguments["continuation"],
        ],
        loop_contract=arguments["loop_contract"],
        stop_certificate=arguments["stop_certificate"],
        dry_rounds_observed=arguments["dry_rounds_observed"],
    )


def test_the_affected_comparisons_are_carried_whole() -> None:
    record = reassess_after_evaluator_drift(**reassessment_arguments())
    carried = {
        row["comparison_id"]: row["comparison"]
        for row in record["affected_comparisons"] + record["unaffected_comparisons"]
    }

    assert carried == {row["comparison_id"]: row for row in comparisons()}


# -- determinism ---------------------------------------------------------


def test_a_resume_is_deterministic() -> None:
    assert resumed() == resumed()


def test_a_cancel_is_deterministic() -> None:
    assert cancel_evolution_run(**cancel_arguments()) == cancel_evolution_run(
        **cancel_arguments()
    )


def test_a_reassessment_is_deterministic() -> None:
    assert reassess_after_evaluator_drift(
        **reassessment_arguments()
    ) == reassess_after_evaluator_drift(**reassessment_arguments())


def test_only_the_minted_id_varies_when_the_caller_supplies_none() -> None:
    first = cancel_evolution_run(**cancel_arguments(cancellation_id=None))
    second = cancel_evolution_run(**cancel_arguments(cancellation_id=None))

    assert first["cancellation_id"] != second["cancellation_id"]
    for record in (first, second):
        record.pop("cancellation_id")
        record.pop("cancellation_hash")
    assert first == second


def test_no_record_is_stamped_with_the_moment_it_was_written() -> None:
    """A clock would make every record un-replayable and silently self-dated."""
    source = ENGINE.read_text(encoding="utf-8")

    assert "utc_now_iso" not in source
    assert "datetime" not in source
    assert "time.time" not in source


@pytest.mark.parametrize(
    ("function", "parameter"),
    [
        (resume_from_checkpoint, "resumed_at"),
        (cancel_evolution_run, "recorded_at"),
        (reassess_after_evaluator_drift, "reassessed_at"),
    ],
)
def test_every_timestamp_is_a_required_argument(
    function: object, parameter: str
) -> None:
    signature = inspect.signature(function)  # type: ignore[arg-type]

    assert signature.parameters[parameter].default is inspect.Parameter.empty


# -- inputs are not touched ----------------------------------------------


def test_a_resume_does_not_mutate_the_checkpoint_it_was_given() -> None:
    arguments = resume_arguments(stop_certificate=stop_certificate())
    before = deepcopy(arguments["checkpoint"])

    resume_from_checkpoint(ROOT, **arguments)

    assert arguments["checkpoint"] == before


def test_a_cancel_does_not_mutate_the_accounting_it_was_given() -> None:
    arguments = cancel_arguments()
    before = deepcopy(arguments)

    cancel_evolution_run(**arguments)

    assert arguments == before


def test_a_reassessment_does_not_mutate_the_comparisons_or_the_bundle() -> None:
    arguments = reassessment_arguments()
    before = deepcopy(
        {
            "comparisons": arguments["comparisons"],
            "current_bundle": arguments["current_bundle"],
        }
    )

    reassess_after_evaluator_drift(**arguments)

    assert arguments["comparisons"] == before["comparisons"]
    assert arguments["current_bundle"] == before["current_bundle"]


def test_editing_a_returned_record_cannot_reach_back_into_the_inputs() -> None:
    arguments = reassessment_arguments()
    record = reassess_after_evaluator_drift(**arguments)

    record["affected_comparisons"][0]["comparison"]["candidate_ids"].append("CAND-X")

    assert arguments["comparisons"] == comparisons()


# -- serialisable evidence -----------------------------------------------


@pytest.mark.parametrize(
    "builder",
    [
        lambda: resumed(),
        lambda: cancel_evolution_run(**cancel_arguments()),
        lambda: reassess_after_evaluator_drift(**reassessment_arguments()),
    ],
)
def test_every_record_is_serialisable_evidence(builder: object) -> None:
    record = builder()  # type: ignore[operator]

    assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True)) == record
