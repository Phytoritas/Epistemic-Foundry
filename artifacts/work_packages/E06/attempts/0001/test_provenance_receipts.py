"""provenance_and_receipt_audit — every record re-derives from its own content.

A concurrency verdict is only worth as much as its evidence, and the evidence
here is a chain of digests: each settlement hashes its own ledger, the agreement
check hashes the settlements it compared, and the gate hashes the whole thing
including the sealed E05 reconciliation it carried.  Every one of those digests
is recomputed below from the record it claims to describe, so a report edited
after the fact stops matching itself.

The other half is what the gate must *not* do.  It mints no receipt: the effect
receipts it settles are the ledger's own, still schema-valid and still carrying
the `receipt_hash` the ledger gave them.  And it reads no clock and draws no
randomness: given the same ids, two runs an hour apart produce byte-identical
records, which is what makes the digests replayable at all.
"""

from __future__ import annotations

from epistemic_foundry.contracts import validate_artifact
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.effects.v4_e06 import (
    check_serializability,
    require_concurrent_effect_gate,
    run_concurrency_gate,
    settle_interleaving,
)
from fixtures import (
    INITIAL_REVISIONS,
    disjoint_gate,
    interleaved,
    retry_gate,
    serial,
)


def _settlement(events, actions, name="IL-1"):
    return settle_interleaving(
        actions=actions,
        events=events,
        initial_revisions=INITIAL_REVISIONS,
        interleaving_id=name,
    )


def test_a_settlement_hash_re_derives_from_the_settlement() -> None:
    payload = disjoint_gate()
    settlement = _settlement(serial("ACT-1", "ACT-2"), payload["actions"])

    assert settlement["settlement_hash"] == hash_excluding(
        settlement, "settlement_hash"
    )


def test_a_ledger_hash_re_derives_from_the_ledger() -> None:
    payload = disjoint_gate()
    settlement = _settlement(serial("ACT-1", "ACT-2"), payload["actions"])

    assert settlement["ledger_hash"] == sha256_of_payload(settlement["ledger"])


def test_a_concurrency_hash_re_derives_from_the_agreement_check() -> None:
    payload = disjoint_gate()
    report = check_serializability(
        actions=payload["actions"],
        interleavings=payload["interleavings"],
        initial_revisions=payload["initial_revisions"],
    )

    assert report["concurrency_hash"] == hash_excluding(report, "concurrency_hash")


def test_a_gate_hash_re_derives_from_the_whole_report() -> None:
    report = run_concurrency_gate(**disjoint_gate())

    assert report["gate_hash"] == hash_excluding(report, "gate_hash")


def test_the_gate_hash_covers_the_reconciliation_it_carried() -> None:
    """Editing E05's verdict out of the report must break the report's digest."""
    report = run_concurrency_gate(**disjoint_gate())
    tampered = dict(report)
    tampered["effect_reconciliation"] = None

    assert hash_excluding(tampered, "gate_hash") != report["gate_hash"]


def test_every_digest_carries_the_canonical_shape() -> None:
    report = run_concurrency_gate(**disjoint_gate())
    digests = [report["gate_hash"], report["concurrency"]["concurrency_hash"]] + [
        entry["ledger_hash"] for entry in report["concurrency"]["settlements"]
    ]

    for digest in digests:
        assert digest.startswith("sha256:")
        assert len(digest) == len("sha256:") + 64


def test_the_ledger_hash_is_blind_to_which_retry_arrived_first() -> None:
    """Two schedules of one retry are one settled ledger, by digest."""
    payload = retry_gate()
    forward = _settlement(serial("ACT-1", "ACT-1R"), payload["actions"], "IL-A")
    backward = _settlement(serial("ACT-1R", "ACT-1"), payload["actions"], "IL-B")

    assert forward["ledger_hash"] == backward["ledger_hash"]
    assert forward["settlement_hash"] != backward["settlement_hash"]


def test_the_settlement_hash_still_distinguishes_the_two_schedules() -> None:
    """The ledger agrees; the record of how it was reached must not pretend to."""
    payload = retry_gate()
    forward = _settlement(serial("ACT-1", "ACT-1R"), payload["actions"], "IL-A")
    backward = _settlement(serial("ACT-1R", "ACT-1"), payload["actions"], "IL-B")

    assert forward["notices"][0]["conflicting_pair"] == ["ACT-1", "ACT-1R"]
    assert backward["notices"][0]["conflicting_pair"] == ["ACT-1R", "ACT-1"]


def test_the_gate_mints_no_receipt_of_its_own() -> None:
    """Every settled receipt is one the caller's ledger already minted."""
    payload = disjoint_gate()
    report = run_concurrency_gate(**payload)
    supplied = {entry["effect_receipt"]["receipt_id"] for entry in payload["actions"]}

    assert set(report["settled_effect_receipt_ids"]) <= supplied


def test_the_settled_receipts_are_still_schema_valid() -> None:
    payload = disjoint_gate()
    run_concurrency_gate(**payload)

    for entry in payload["actions"]:
        receipt = entry["effect_receipt"]
        validate_artifact("effect-receipt", receipt)
        assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_each_settled_receipt_answers_exactly_one_idempotency_key() -> None:
    report = run_concurrency_gate(**disjoint_gate())
    settlement = report["concurrency"]["settlements"][0]
    bound = [
        entry["effect_receipt_id"]
        for entry in settlement["ledger"]["bindings"].values()
    ]

    assert sorted(bound) == report["settled_effect_receipt_ids"]
    assert len(set(bound)) == len(bound)


def test_a_supplied_gate_id_is_preserved() -> None:
    report = run_concurrency_gate(**(disjoint_gate() | {"gate_id": "ECG-FIXED"}))

    assert report["gate_id"] == "ECG-FIXED"


def test_an_absent_gate_id_falls_back_to_a_minted_one() -> None:
    first = run_concurrency_gate(**disjoint_gate())
    second = run_concurrency_gate(**disjoint_gate())

    assert first["gate_id"].startswith("ECG-")
    assert first["gate_id"] != second["gate_id"]


def test_an_absent_interleaving_id_falls_back_to_a_minted_one() -> None:
    payload = disjoint_gate()
    settlement = settle_interleaving(
        actions=payload["actions"],
        events=serial("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
    )

    assert settlement["interleaving_id"].startswith("EIL-")


def test_the_gate_reads_no_clock() -> None:
    """Identical inputs and ids settle to identical bytes, run to run."""
    payload = disjoint_gate() | {"gate_id": "ECG-FIXED"}
    first = run_concurrency_gate(**payload)
    second = run_concurrency_gate(**payload)

    assert first["gate_hash"] == second["gate_hash"]


def test_the_agreed_ledger_names_a_settlement_that_actually_produced_it() -> None:
    report = run_concurrency_gate(**disjoint_gate())
    agreed = report["concurrency"]["agreed_ledger_hash"]
    producers = [
        entry["interleaving_id"]
        for entry in report["concurrency"]["settlements"]
        if entry["ledger_hash"] == agreed
    ]

    assert producers == report["concurrency"]["admitted_interleaving_ids"]


def test_the_reconciliation_receipt_counts_match_the_settled_ledger() -> None:
    report = run_concurrency_gate(**retry_gate())
    settlement = report["concurrency"]["settlements"][0]

    assert report["effect_reconciliation"]["counts"]["effect_receipts"] == len(
        settlement["ledger"]["bindings"]
    )
    require_concurrent_effect_gate(report)


def test_a_crossed_schedule_leaves_the_same_evidence_as_a_serial_one() -> None:
    payload = disjoint_gate()
    forward = _settlement(serial("ACT-1", "ACT-2"), payload["actions"], "IL-A")
    crossed = _settlement(interleaved("ACT-1", "ACT-2"), payload["actions"], "IL-B")

    assert forward["ledger"] == crossed["ledger"]
    assert forward["ledger_hash"] == crossed["ledger_hash"]
