"""Provenance and receipt checks: every decision resolves to an immutable receipt.

The gate's contract is that admit and refuse alike produce a receipt whose hash
re-derives from its own fields, that the receipt is a pure function of the
canonical inputs, and that a crashed decision can be resumed by replaying those
inputs into a byte-identical receipt. These tests hold that contract, including
that a refusal carries the same re-derivable provenance an admission does and
that no input is mutated on either path.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.intake.v4_i06 import gate as g

import fixtures as fx


def test_an_admit_receipt_re_derives_its_hash() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments())
    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_a_refuse_receipt_re_derives_its_hash() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments(scope_vector=None))
    assert receipt["admitted"] is False
    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_a_refuse_receipt_still_binds_the_genome_it_refused() -> None:
    args = fx.gate_arguments(scope_vector=None)
    receipt = g.gate_genome_intake(**args)
    assert receipt["genome_id"] == fx.GENOME_ID
    assert receipt["genome_hash"] == sha256_of_payload(args["submission"]["genome"])


def test_a_screening_refusal_carries_the_screened_genome_hash() -> None:
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(submission=fx.submission(genome_kind="not-a-real-kind"))
    )
    # The screen record's own genome hash travels into the receipt, so even a
    # refused-at-screening genome is provenanced.
    assert receipt["genome_hash"] == sha256_of_payload(fx.genome())


def test_the_decision_is_replayable_after_a_crash() -> None:
    # A crash between deciding and persisting loses the receipt; the gate reads
    # no clock and draws no random value when the caller names the receipt, so
    # replaying the same canonical inputs re-derives a byte-identical receipt.
    args = fx.gate_arguments()
    before = g.gate_genome_intake(**args)
    after = g.gate_genome_intake(**args)
    assert before == after
    assert before["receipt_hash"] == after["receipt_hash"]


def test_a_refused_decision_is_replayable_after_a_crash() -> None:
    args = fx.gate_arguments(
        scope_vector=None, prediction_genes=[fx.prediction_gene(genome_id="HG-OTHER")]
    )
    before = g.gate_genome_intake(**args)
    after = g.gate_genome_intake(**args)
    assert before == after


def test_no_input_is_mutated_on_the_refusal_path() -> None:
    args = fx.gate_arguments(
        scope_vector={"domain": None},
        falsifier_genes=[fx.falsifier_gene(genome_id="HG-OTHER")],
    )
    snapshot = copy.deepcopy(args)
    g.gate_genome_intake(**args)
    assert args == snapshot


def test_the_resolved_bindings_hash_exactly_the_bound_artifacts() -> None:
    args = fx.gate_arguments(
        submission=fx.submission(
            genome=fx.genome(
                prediction_ids=[fx.PREDICTION_ID, "PG-I06-2"],
                falsifier_ids=[fx.FALSIFIER_ID, "FG-I06-2"],
            )
        ),
        falsifier_genes=[
            fx.falsifier_gene(),
            fx.falsifier_gene("FG-I06-2"),
        ],
        prediction_genes=[
            fx.prediction_gene(),
            fx.prediction_gene("PG-I06-2"),
        ],
    )
    receipt = g.gate_genome_intake(**args)
    resolved = receipt["resolved_bindings"]
    assert set(resolved["falsifier_gene_hashes"]) == {fx.FALSIFIER_ID, "FG-I06-2"}
    assert set(resolved["prediction_gene_hashes"]) == {fx.PREDICTION_ID, "PG-I06-2"}
    for gene in args["falsifier_genes"]:
        key = gene["falsifier_gene_id"]
        assert resolved["falsifier_gene_hashes"][key] == sha256_of_payload(gene)


def test_the_batch_report_hash_re_derives_and_replays() -> None:
    first = g.gate_intake_batch(
        [fx.request(), fx.request(scope_vector=None)],
        decided_at=fx.DECIDED_AT,
        report_id="GIB-PROV",
    )
    second = g.gate_intake_batch(
        [fx.request(), fx.request(scope_vector=None)],
        decided_at=fx.DECIDED_AT,
        report_id="GIB-PROV",
    )
    assert first == second
    assert first["report_hash"] == hash_excluding(first, "report_hash")


def test_every_batch_receipt_carries_its_own_re_derivable_hash() -> None:
    report = g.gate_intake_batch(
        [fx.request(), fx.request(scope_vector=None)],
        decided_at=fx.DECIDED_AT,
        report_id="GIB-PROV-2",
    )
    for receipt in report["receipts"]:
        stripped = {k: v for k, v in receipt.items() if k != "request_index"}
        assert stripped["receipt_hash"] == hash_excluding(stripped, "receipt_hash")


def test_the_receipt_records_the_timestamp_the_caller_supplied() -> None:
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(decided_at="2030-01-01T00:00:00Z")
    )
    assert receipt["decided_at"] == "2030-01-01T00:00:00Z"
