"""provenance_and_receipt_audit — every effect resolves to an immutable receipt.

The invariants this suite pins are the ones the manifest's exit criteria and the
Y06 integrity note turn on: every decision is a re-derivable, content-addressed
receipt; two runs over equal inputs produce byte-equal receipts; inputs are never
mutated; and the sealed qualification verdict binds every sub-receipt by hash so
it cannot be forged without reproducing the gates it depends on.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.operations.v4_y06 import (
    qualify_evolution_run,
    reconcile_qualification_counts,
    require_bounded_qualification_budget,
    require_no_scale_authority_capture,
    require_surrogate_within_ceiling,
)
from fixtures import (
    bounded_budget,
    clean_fanout,
    expected_counts,
    measured_usage,
    qualification_kwargs,
    triage,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_count_receipt_rederives_its_own_identity_and_hash() -> None:
    fanout = clean_fanout()
    receipt = reconcile_qualification_counts(
        qualification_run_id="QUAL-1",
        expected_counts=expected_counts(),
        proposed=fanout["proposed"],
        generated=fanout["generated"],
        evaluated=fanout["evaluated"],
        persisted=fanout["persisted"],
        effect_receipts=fanout["effect_receipts"],
        mutation_receipts=fanout["mutation_receipts"],
    )
    body = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_id", "receipt_hash"}
    }
    assert receipt["receipt_id"] == "QIC-" + sha256_of_payload(body)[len("sha256:") :]
    assert receipt["receipt_hash"] == hash_excluding(dict(receipt), "receipt_hash")


def test_every_gate_receipt_is_content_addressed_and_stable() -> None:
    fanout = clean_fanout()
    count_kwargs = dict(
        qualification_run_id="QUAL-1",
        expected_counts=expected_counts(),
        proposed=fanout["proposed"],
        generated=fanout["generated"],
        evaluated=fanout["evaluated"],
        persisted=fanout["persisted"],
        effect_receipts=fanout["effect_receipts"],
        mutation_receipts=fanout["mutation_receipts"],
    )
    assert reconcile_qualification_counts(
        **count_kwargs
    ) == reconcile_qualification_counts(**count_kwargs)

    budget_kwargs = dict(
        budget_envelope=bounded_budget(),
        measured_cost=40.0,
        measured_usage=measured_usage(),
    )
    assert require_bounded_qualification_budget(
        **budget_kwargs
    ) == require_bounded_qualification_budget(**budget_kwargs)

    assert require_surrogate_within_ceiling(
        triage_reports=[triage("CAND-1")], surrogate_ceiling=5
    ) == require_surrogate_within_ceiling(
        triage_reports=[triage("CAND-1")], surrogate_ceiling=5
    )

    authority_claims = [
        {
            "capability_id": "foundry:read",
            "holder_id": "CAND-1",
            "holder_is_search_space": True,
        }
    ]
    assert require_no_scale_authority_capture(
        authority_claims=authority_claims
    ) == require_no_scale_authority_capture(authority_claims=authority_claims)


def test_verdict_binds_each_subreceipt_hash() -> None:
    kwargs = qualification_kwargs()
    verdict = qualify_evolution_run(**kwargs)

    counts = reconcile_qualification_counts(
        qualification_run_id=kwargs["qualification_run_id"],
        expected_counts=kwargs["expected_counts"],
        proposed=kwargs["proposed"],
        generated=kwargs["generated"],
        evaluated=kwargs["evaluated"],
        persisted=kwargs["persisted"],
        effect_receipts=kwargs["effect_receipts"],
        mutation_receipts=kwargs["mutation_receipts"],
    )
    budget = require_bounded_qualification_budget(
        budget_envelope=kwargs["budget_envelope"],
        measured_cost=kwargs["measured_cost"],
        measured_usage=kwargs["measured_usage"],
    )
    # The verdict carries the same sub-receipt hashes the standalone gates emit,
    # so it cannot be sealed without reproducing every gate it depends on.
    assert verdict["count_receipt_hash"] == counts["receipt_hash"]
    assert verdict["budget_receipt_hash"] == budget["receipt_hash"]
    assert _rederives(verdict)


def test_receipts_are_byte_equal_across_equal_runs() -> None:
    assert qualify_evolution_run(**qualification_kwargs()) == qualify_evolution_run(
        **qualification_kwargs()
    )


def test_reconcile_counts_does_not_mutate_its_inputs() -> None:
    fanout = clean_fanout()
    before = copy.deepcopy(fanout)
    reconcile_qualification_counts(
        qualification_run_id="QUAL-1",
        expected_counts=expected_counts(),
        proposed=fanout["proposed"],
        generated=fanout["generated"],
        evaluated=fanout["evaluated"],
        persisted=fanout["persisted"],
        effect_receipts=fanout["effect_receipts"],
        mutation_receipts=fanout["mutation_receipts"],
    )
    assert fanout == before


def test_authority_gate_does_not_mutate_its_inputs() -> None:
    claims = [
        {
            "capability_id": "foundry:read",
            "holder_id": "CAND-1",
            "holder_is_search_space": True,
        }
    ]
    before = copy.deepcopy(claims)
    require_no_scale_authority_capture(authority_claims=claims)
    assert claims == before


def test_budget_receipt_carries_no_timestamp() -> None:
    receipt = require_bounded_qualification_budget(
        budget_envelope=bounded_budget(),
        measured_cost=40.0,
        measured_usage=measured_usage(),
    )
    # The receipt is a pure function of the envelope and measurements: no clock.
    assert "created_at" not in receipt
    assert _rederives(receipt)
