"""Unit and contract checks for the happy path of the intake gate.

These fix the behaviour a caller depends on when everything binds: an eligible
genome whose scope vector, falsifier genes and prediction genes resolve is
admitted, its receipt records exactly the artifacts it was made from, and the
whole decision is a pure function of its inputs. The batch path reconciles its
counts and leaves every input unmodified.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.intake.v4_i06 import gate as g

import fixtures as fx


def test_a_fully_bound_genome_is_admitted() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments())
    assert receipt["admitted"] is True
    assert receipt["decision"] == g.ADMITTED
    assert receipt["finding_codes"] == []
    assert receipt["findings"] == []
    assert receipt["genome_id"] == fx.GENOME_ID


def test_require_admissible_passes_on_an_admitted_receipt() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments())
    g.require_admissible(receipt)  # does not raise


def test_the_receipt_records_the_hashes_of_the_bound_artifacts() -> None:
    args = fx.gate_arguments()
    receipt = g.gate_genome_intake(**args)
    resolved = receipt["resolved_bindings"]
    assert resolved["scope_vector_hash"] == sha256_of_payload(args["scope_vector"])
    assert resolved["scope_vector_id"] == fx.SCOPE_ID
    assert resolved["falsifier_gene_hashes"] == {
        fx.FALSIFIER_ID: sha256_of_payload(args["falsifier_genes"][0])
    }
    assert resolved["prediction_gene_hashes"] == {
        fx.PREDICTION_ID: sha256_of_payload(args["prediction_genes"][0])
    }


def test_the_receipt_hash_re_derives_from_its_own_fields() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments())
    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_the_decision_is_a_pure_function_of_its_inputs() -> None:
    first = g.gate_genome_intake(**fx.gate_arguments())
    second = g.gate_genome_intake(**fx.gate_arguments())
    assert first == second


def test_the_receipt_id_is_minted_only_when_the_caller_declines_to_name_it() -> None:
    args = fx.gate_arguments()
    del args["receipt_id"]
    receipt = g.gate_genome_intake(**args)
    assert receipt["receipt_id"].startswith("GIR-")


def test_a_falsifier_may_link_several_declared_predictions() -> None:
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(
            submission=fx.submission(
                genome=fx.genome(prediction_ids=[fx.PREDICTION_ID, "PG-I06-2"])
            ),
            falsifier_genes=[
                fx.falsifier_gene(linked_prediction_ids=[fx.PREDICTION_ID, "PG-I06-2"])
            ],
            prediction_genes=[
                fx.prediction_gene(),
                fx.prediction_gene("PG-I06-2"),
            ],
        )
    )
    assert receipt["admitted"] is True


def test_the_batch_reconciles_its_counts_and_orders_its_receipts() -> None:
    report = g.gate_intake_batch(
        [fx.request(), fx.coherent_request("HG-I06-2")],
        decided_at=fx.DECIDED_AT,
        report_id="GIB-I06-1",
    )
    assert report["counts"] == {"admitted": 2, "refused": 0, "submitted": 2}
    assert [row["request_index"] for row in report["receipts"]] == [0, 1]
    assert report["admitted_genome_ids"] == sorted([fx.GENOME_ID, "HG-I06-2"])
    assert report["report_hash"] == hash_excluding(report, "report_hash")


def test_the_batch_hash_is_a_pure_function_of_the_batch() -> None:
    first = g.gate_intake_batch([fx.request()], decided_at=fx.DECIDED_AT, report_id="R")
    second = g.gate_intake_batch(
        [fx.request()], decided_at=fx.DECIDED_AT, report_id="R"
    )
    assert first == second


def test_no_input_is_modified_by_the_gate() -> None:
    args = fx.gate_arguments()
    snapshot = copy.deepcopy(args)
    g.gate_genome_intake(**args)
    assert args == snapshot


def test_an_empty_batch_reconciles_to_nothing() -> None:
    report = g.gate_intake_batch([], decided_at=fx.DECIDED_AT, report_id="R")
    assert report["counts"] == {"admitted": 0, "refused": 0, "submitted": 0}
    assert report["admitted_genome_ids"] == []
    assert report["finding_totals"] == {}
