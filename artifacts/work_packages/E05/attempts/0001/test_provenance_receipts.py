"""provenance_and_receipt_audit — every effect resolves to an immutable receipt.

The engine composes the runtime's own builders, so this audit checks that what
it reconciles is genuinely receipted: each effect receipt carries a self-hash it
can be re-derived from, each mutation receipt binds its effect and derives its
changed paths from the diff rather than the operator's word, and a mutation that
touches an authority field is refused before a receipt for it can exist.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.evolution_chamber.mutation import (
    FORBIDDEN_MUTATION_PATHS,
    AuthorityMutationRefused,
    build_mutation_receipt,
)
from epistemic_foundry.noetic_ledger.receipts import hash_excluding
from epistemic_foundry.effects.v4_e05 import reconcile_effect_ledger
from fixtures import RUN_ID, UNKNOWN, clean_fanout, effect, genome


def test_every_effect_receipt_hash_is_recomputable() -> None:
    for receipt in clean_fanout()["effect_receipts"]:
        assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_every_mutation_receipt_hash_is_recomputable() -> None:
    for receipt in clean_fanout()["mutation_receipts"]:
        assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_every_mutation_receipt_binds_an_effect_receipt_that_exists() -> None:
    payload = clean_fanout()
    known = {receipt["receipt_id"] for receipt in payload["effect_receipts"]}

    for receipt in payload["mutation_receipts"]:
        assert receipt["effect_receipt_id"] in known


def test_every_effect_receipt_is_bound_by_exactly_one_mutation() -> None:
    payload = clean_fanout()
    bound = [receipt["effect_receipt_id"] for receipt in payload["mutation_receipts"]]

    assert sorted(bound) == sorted(
        receipt["receipt_id"] for receipt in payload["effect_receipts"]
    )
    assert len(set(bound)) == len(bound)


def test_the_reconciliation_flag_is_derived_from_the_status() -> None:
    unknown = effect("INT-X", UNKNOWN)
    succeeded = effect("INT-Y")

    assert unknown["reconciliation_required"] is True
    assert succeeded["reconciliation_required"] is False


def test_changed_paths_are_derived_from_the_diff_not_the_operator() -> None:
    receipt = build_mutation_receipt(
        evolution_run_id=RUN_ID,
        operator_id="OP-QUIET",
        input_candidates=[genome("CAND-0")],
        output_candidate=genome("CAND-1", claim="a different claim"),
        effect_receipt_id="EF-1",
    )

    assert "claim" in receipt["changed_paths"]
    assert "genome_id" in receipt["changed_paths"]
    assert "scope" in receipt["preserved_paths"]


@pytest.mark.parametrize(
    "field", sorted(FORBIDDEN_MUTATION_PATHS)[:4] + ["evaluator_bundle_id"]
)
def test_a_mutation_touching_an_authority_field_has_no_receipt(field: str) -> None:
    payload = genome("CAND-1")
    payload[field] = "seized"

    with pytest.raises(AuthorityMutationRefused) as caught:
        build_mutation_receipt(
            evolution_run_id=RUN_ID,
            operator_id="OP-ESCALATE",
            input_candidates=[genome("CAND-0")],
            output_candidate=payload,
            effect_receipt_id="EF-1",
        )
    assert field in str(caught.value)


def test_a_reconciled_report_accounts_for_every_receipt_it_was_given() -> None:
    payload = clean_fanout()
    report = reconcile_effect_ledger(**payload)

    assert report["counts"]["effect_receipts"] == len(payload["effect_receipts"])
    assert report["counts"]["mutation_receipts"] == len(payload["mutation_receipts"])
    assert report["orphan_effect_receipts"] == []


def test_a_result_artifact_is_recorded_only_for_a_landed_effect() -> None:
    landed = effect("INT-1")
    unresolved = effect("INT-2", UNKNOWN)

    assert landed["result_artifact_ids"] == ["ART-1"]
    assert unresolved["result_artifact_ids"] == []


def test_the_report_is_serialisable_evidence() -> None:
    import json

    report = reconcile_effect_ledger(**clean_fanout())
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

    assert json.loads(encoded) == report


def test_the_engine_never_mints_a_receipt_of_its_own() -> None:
    """Reconciliation reads the ledger; it does not add to it."""

    payload = clean_fanout()
    before = [dict(receipt) for receipt in payload["effect_receipts"]]
    reconcile_effect_ledger(**payload)

    assert payload["effect_receipts"] == before
