"""provenance_and_receipt_audit — a verdict is evidence, not an assertion.

A scheduler that reported "the run stayed within its bounds" and nothing more
would be asking to be believed.  The verdict sealed here can instead be
recomputed: it carries no timestamp and no minted identifier, so the same
schedule produces a byte-equal record whose hash re-derives from its own content,
and any edit to what it claims breaks that hash.

The receipts the effect-ledger path reconciles against are the ledger's own.
This gate reads them and mints nothing, which is checked here directly: a
scheduler that added to the ledger it audits would be reconciling against itself.
"""

from __future__ import annotations

import json

import pytest
from fixtures import CANDIDATES, ROOT, receipted_arguments, schedule_arguments

from epistemic_foundry.domain.hashing import is_schema_digest
from epistemic_foundry.noetic_ledger.receipts import hash_excluding
from epistemic_foundry.scheduler.v4_n05 import (
    EFFECT_LEDGER_SCOPE,
    FINDING_CODES,
    LANES,
    ScheduleError,
    require_valid_schedule,
    seal_schedule_verdict,
    verdict_hash_matches,
    verify_schedule,
)

SCHEDULE_ID = "SCH-N05-1"


def sealed(**overrides: object) -> dict:
    report = verify_schedule(ROOT, **schedule_arguments(**overrides))  # type: ignore[arg-type]
    require_valid_schedule(report)
    return seal_schedule_verdict(report, schedule_id=SCHEDULE_ID)


def test_the_verdict_hash_is_recomputable_from_its_own_content() -> None:
    verdict = sealed()

    assert verdict_hash_matches(verdict)
    assert hash_excluding(verdict, "verdict_hash") == verdict["verdict_hash"]


def test_the_verdict_hash_has_the_canonical_digest_shape() -> None:
    assert is_schema_digest(sealed()["verdict_hash"])


def test_two_seals_of_the_same_schedule_are_byte_equal() -> None:
    """No clock and no random source, so a replay must produce the same record."""

    first, second = sealed(), sealed()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_a_different_schedule_identity_yields_a_different_verdict() -> None:
    verdict = sealed()
    other = seal_schedule_verdict(
        verify_schedule(ROOT, **schedule_arguments()), schedule_id="SCH-N05-2"
    )

    assert other["verdict_hash"] != verdict["verdict_hash"]


@pytest.mark.parametrize("field", ["bounds", "lane_ledgers", "reconciled", "valid"])
def test_editing_what_the_verdict_claims_breaks_its_hash(field: str) -> None:
    verdict = sealed()
    verdict[field] = "edited"

    assert not verdict_hash_matches(verdict)


def test_the_verdict_counts_every_finding_class() -> None:
    verdict = sealed()

    assert set(verdict["findings"]) == set(FINDING_CODES)
    assert set(verdict["findings"].values()) == {0}


def test_the_verdict_carries_no_clock_and_no_minted_identity() -> None:
    """A timestamp would make an otherwise identical run unverifiable."""

    assert set(sealed()) == {
        "bounds",
        "findings",
        "lane_ledgers",
        "phase_binding",
        "reconciled",
        "reconciliation_scope",
        "schedule_id",
        "valid",
        "verdict_hash",
    }


def test_the_verdict_binds_the_workflow_phases_it_was_judged_against() -> None:
    verdict = sealed()

    assert set(verdict["phase_binding"]) == set(LANES)
    for lane in LANES:
        assert verdict["phase_binding"][lane]


def test_the_verdict_names_which_reconciliation_backed_it() -> None:
    report = verify_schedule(ROOT, **receipted_arguments())
    require_valid_schedule(report)
    verdict = seal_schedule_verdict(report, schedule_id=SCHEDULE_ID)

    assert verdict["reconciliation_scope"] == EFFECT_LEDGER_SCOPE
    assert verdict["reconciled"] is True


def test_the_verdict_is_serialisable_evidence() -> None:
    verdict = sealed()
    encoded = json.dumps(verdict, ensure_ascii=False, sort_keys=True)

    assert json.loads(encoded) == verdict


def test_a_verdict_over_a_report_this_gate_did_not_produce_is_refused() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())
    report.pop("lane_ledgers")

    with pytest.raises(ScheduleError) as caught:
        seal_schedule_verdict(report, schedule_id=SCHEDULE_ID)
    assert caught.value.code == "VERDICT_INPUT_INCOMPLETE"


def test_a_verdict_without_a_schedule_identity_is_refused() -> None:
    report = verify_schedule(ROOT, **schedule_arguments())

    with pytest.raises(ScheduleError) as caught:
        seal_schedule_verdict(report, schedule_id="  ")
    assert caught.value.code == "INPUT_INVALID"


def test_every_effect_receipt_the_gate_reconciled_is_itself_re_derivable() -> None:
    for receipt in receipted_arguments()["effect_receipts"]:
        assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_every_mutation_receipt_binds_an_effect_receipt_that_exists() -> None:
    arguments = receipted_arguments()
    known = {receipt["receipt_id"] for receipt in arguments["effect_receipts"]}

    for receipt in arguments["mutation_receipts"]:
        assert receipt["effect_receipt_id"] in known


def test_the_gate_mints_no_receipt_of_its_own() -> None:
    """It reads the ledger; it does not add to it."""

    arguments = receipted_arguments()
    before = [dict(receipt) for receipt in arguments["effect_receipts"]]

    verify_schedule(ROOT, **arguments)

    assert arguments["effect_receipts"] == before


def test_the_reconciliation_accounts_for_every_receipt_it_was_given() -> None:
    arguments = receipted_arguments()
    report = verify_schedule(ROOT, **arguments)

    counts = report["reconciliation"]["counts"]
    assert counts["effect_receipts"] == len(arguments["effect_receipts"])
    assert counts["mutation_receipts"] == len(arguments["mutation_receipts"])
    assert report["reconciliation"]["orphan_effect_receipts"] == []


def test_the_lane_ledgers_the_verdict_seals_are_the_ones_reconciled() -> None:
    report = verify_schedule(ROOT, **receipted_arguments())
    verdict = seal_schedule_verdict(report, schedule_id=SCHEDULE_ID)

    assert verdict["lane_ledgers"] == report["lane_ledgers"]
    assert verdict["lane_ledgers"][LANES[-1]] == sorted(CANDIDATES)
