"""provenance_and_receipt_audit — every gated run is a self-proving receipt.

The integration gate scores nothing and promotes nothing, so what it must prove
instead is that its verdict re-derives byte for byte from its own published
fields.  A sealed record's hash covers the record; the schedule side is not
re-opinionated but chained by carrying the sealed scheduler's own verdict hash;
replaying the same declaration reproduces the identical report and the identical
record; and the declaration handed in is never mutated on the way through.  There
is no clock and no random draw on this path, so determinism is a property of the
module rather than of the machine it ran on.

A completion the gate accepts resolves to an immutable receipt: a record whose
content is changed no longer re-derives its hash, so a tampered receipt is
detectable rather than merely disbelieved.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.scheduler.v4_n05 import seal_schedule_verdict
from epistemic_foundry.scheduler.v4_n06 import (
    FINDING_CODES,
    IntegrationError,
    integration_hash_matches,
    seal_integration_record,
    verify_integration,
)
from fixtures import RUN_ID, ROOT, integration_arguments, lock_arguments


def test_the_record_hash_covers_the_record() -> None:
    report = verify_integration(ROOT, **integration_arguments())
    record = seal_integration_record(report, run_id=RUN_ID)

    assert record["integration_hash"] == hash_excluding(record, "integration_hash")
    assert integration_hash_matches(record)


def test_the_record_chains_the_sealed_schedule_verdict_rather_than_reopining() -> None:
    report = verify_integration(ROOT, **integration_arguments())
    record = seal_integration_record(report, run_id=RUN_ID)

    chained = seal_schedule_verdict(report["schedule"], schedule_id=RUN_ID)
    assert record["schedule_hash"] == chained["verdict_hash"]


def test_the_record_counts_each_finding_class() -> None:
    report = verify_integration(ROOT, **lock_arguments())
    record = seal_integration_record(report, run_id=RUN_ID)

    assert set(record["findings"]) == set(FINDING_CODES)
    assert all(count == 0 for count in record["findings"].values())
    assert record["integrated"] is True


def test_an_identified_run_replays_byte_for_byte() -> None:
    first = verify_integration(ROOT, **integration_arguments())
    second = verify_integration(ROOT, **integration_arguments())

    assert first == second
    assert seal_integration_record(first, run_id=RUN_ID) == seal_integration_record(
        second, run_id=RUN_ID
    )


def test_the_gate_never_mutates_the_declaration_it_was_given() -> None:
    arguments = integration_arguments()
    before = copy.deepcopy(arguments)

    verify_integration(ROOT, **arguments)

    assert arguments == before


def test_a_tampered_record_no_longer_re_derives_its_hash() -> None:
    report = verify_integration(ROOT, **integration_arguments())
    record = seal_integration_record(report, run_id=RUN_ID)

    forged = dict(record)
    forged["integrated"] = not forged["integrated"]
    assert not integration_hash_matches(forged)


def test_a_record_may_only_be_sealed_over_a_report_the_gate_produced() -> None:
    try:
        seal_integration_record({"admission_policy": "deferral"}, run_id=RUN_ID)
    except IntegrationError as error:
        assert error.code == "RECORD_INPUT_INCOMPLETE"
    else:
        raise AssertionError("an incomplete report was sealed")


def test_the_run_id_must_name_the_run() -> None:
    report = verify_integration(ROOT, **integration_arguments())
    try:
        seal_integration_record(report, run_id="  ")
    except IntegrationError as error:
        assert error.code == "INPUT_INVALID"
    else:
        raise AssertionError("a blank run id was accepted")
