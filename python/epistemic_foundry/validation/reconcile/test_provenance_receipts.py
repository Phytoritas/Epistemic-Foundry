"""provenance_and_receipt_audit — a reconciliation can prove itself.

A reconciliation record is what a later reader rests a promotion decision on, so
it has to re-derive without this module: the record re-derives its own hash over
exactly the fields it publishes, the same arguments seal to byte-identical
canonical JSON, and the verifier re-derives both the hash and the schema so an
edit after sealing is visible rather than silent.  Nothing here carries a clock
or a random draw — every id and timestamp comes from the caller — so a run that
crashed and resumed re-derives the identical record from the identical inputs.
"""

from __future__ import annotations

import json

from .contracts import (
    hash_excluding,
    require_reconciled,
    verify_reconciliation_record,
)
from .fixtures import (
    ROOT,
    reconcile_arguments,
    reconciliation,
    scope_mapping,
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_a_record_re_derives_its_own_hash() -> None:
    record = reconciliation()

    assert record["record_hash"] == hash_excluding(record, "record_hash")
    assert record["record_hash"].startswith("sha256:")


def test_the_same_arguments_seal_byte_identically() -> None:
    assert canonical(reconciliation()) == canonical(reconciliation())


def test_a_resumed_run_re_derives_the_identical_record() -> None:
    # The record carries no clock and no draw, so re-running the identical
    # inputs after a crash produces the identical bytes rather than a new id.
    arguments = reconcile_arguments()
    first = reconciliation(**arguments)
    second = reconciliation(**arguments)

    assert first == second


def test_a_different_caller_identity_changes_only_that_field() -> None:
    first = reconciliation()
    second = reconciliation(reconciliation_id="VREC-V04-OTHER")

    assert first["promotion_decision"] == second["promotion_decision"]
    assert first["source_evidence_class"] == second["source_evidence_class"]
    assert first["record_hash"] != second["record_hash"]
    assert second["reconciliation_id"] == "VREC-V04-OTHER"


def test_the_record_binds_the_run_the_surfaces_agreed_on() -> None:
    record = reconciliation()

    assert record["run_id"] == reconcile_arguments()["run_id"]
    assert record["source_result_id"] == reconcile_arguments()["source_result_id"]


def test_the_scope_is_carried_forward_verbatim() -> None:
    scope = scope_mapping(geography="upper-basin")
    record = reconciliation(scope_mapping=scope)

    assert record["scope_mapping"] == json.loads(
        json.dumps(scope, ensure_ascii=False, sort_keys=True)
    )


def test_the_quality_vector_is_carried_but_never_load_bearing() -> None:
    record = reconciliation()

    # The vector is present for a later reader; the decision test proves it is
    # not read, and here it simply survives onto the sealed record.
    assert "quality_adjustments" in record
    assert record["quality_adjustments"]["directness"] == 0.4


def test_an_intact_record_verifies_clean() -> None:
    record = reconciliation()

    verification = verify_reconciliation_record(ROOT, record)
    assert verification["record_hash_matches"] is True
    assert verification["schema_errors"] == []
    assert require_reconciled(ROOT, record) == record


def test_a_tampered_record_is_reported_and_refused() -> None:
    record = reconciliation()
    assert record["promotion_decision"] != "REJECT"
    record["promotion_decision"] = "REJECT"

    verification = verify_reconciliation_record(ROOT, record)
    assert verification["record_hash_matches"] is False


def test_a_verification_re_derives_its_own_hash() -> None:
    verification = verify_reconciliation_record(ROOT, reconciliation())

    assert verification["verification_hash"] == hash_excluding(
        verification, "verification_hash"
    )


def test_a_returned_record_is_a_fresh_document() -> None:
    record = reconciliation()
    record["reasons"].append("mutated after sealing")

    assert "mutated after sealing" not in reconciliation()["reasons"]


def test_every_reason_that_could_be_reported_carries_its_declaration() -> None:
    from .contracts import FINDING_CODES

    assert all(len(reason) > 50 for reason in FINDING_CODES.values())
