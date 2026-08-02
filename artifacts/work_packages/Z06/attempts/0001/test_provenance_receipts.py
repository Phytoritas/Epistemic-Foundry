"""provenance_and_receipt_audit — every effect resolves to an immutable receipt.

The invariants this suite pins are the ones the manifest's exit criteria turn on:
every terminal decision is a re-derivable, content-addressed receipt; two runs over
equal inputs produce byte-equal receipts; inputs are never mutated; the sealed
terminal verdict binds every sub-receipt by hash so it cannot be forged without
reproducing the gates it depends on; and the release carries no clock.  It also
composes the *actually-sealed* artifacts — the frozen Z05 zero-trust release report
and the thirteen sealed ``*06`` reports read from disk — so a break in a composed
surface fails here rather than only in its own package.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload

from v4_z05.zero_trust_release import UNSIGNED_STATUS
from v4_z06.truthful_release import (
    COMPOSED_Z05_PREFIX,
    compose_sealed_z05,
    reconcile_release_accounting,
    require_clean_extraction,
    require_truthful_maturity,
    seal_truthful_release,
)
from fixtures import (
    EXPECTED_PACKAGE_IDS,
    accounting_packages,
    clean_extraction_inputs,
    load_sealed_accounting,
    load_sealed_z05,
    maturity_sources,
    seal_kwargs,
    z05_facts,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_composed_z05_receipt_rederives_its_own_identity_and_hash() -> None:
    receipt = compose_sealed_z05(z05=z05_facts())
    body = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_id", "receipt_hash"}
    }
    assert (
        receipt["receipt_id"]
        == COMPOSED_Z05_PREFIX + sha256_of_payload(body)[len("sha256:") :]
    )
    assert receipt["receipt_hash"] == hash_excluding(dict(receipt), "receipt_hash")


def test_every_gate_receipt_is_content_addressed_and_stable() -> None:
    assert require_clean_extraction(
        **clean_extraction_inputs()
    ) == require_clean_extraction(**clean_extraction_inputs())
    assert require_truthful_maturity(
        sources=maturity_sources()
    ) == require_truthful_maturity(sources=maturity_sources())
    assert reconcile_release_accounting(
        expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=accounting_packages()
    ) == reconcile_release_accounting(
        expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=accounting_packages()
    )


def test_verdict_binds_each_subreceipt_hash() -> None:
    kwargs = seal_kwargs()
    verdict = seal_truthful_release(**kwargs)

    composed = compose_sealed_z05(z05=kwargs["z05"])
    clean = require_clean_extraction(**kwargs["clean_extraction_inputs"])
    maturity = require_truthful_maturity(sources=kwargs["maturity_sources"])
    accounting = reconcile_release_accounting(
        expected_package_ids=kwargs["expected_package_ids"],
        packages=kwargs["accounting_packages"],
    )
    # The verdict carries the same sub-receipt hashes the standalone gates emit,
    # so it cannot be sealed without reproducing every gate it depends on.
    assert verdict["z05_receipt_hash"] == composed["receipt_hash"]
    assert verdict["clean_extraction_receipt_hash"] == clean["receipt_hash"]
    assert verdict["maturity_receipt_hash"] == maturity["receipt_hash"]
    assert verdict["accounting_receipt_hash"] == accounting["receipt_hash"]
    assert _rederives(verdict)


def test_receipts_are_byte_equal_across_equal_runs() -> None:
    assert seal_truthful_release(**seal_kwargs()) == seal_truthful_release(
        **seal_kwargs()
    )


def test_seal_does_not_mutate_its_inputs() -> None:
    kwargs = seal_kwargs()
    before = copy.deepcopy(kwargs)
    seal_truthful_release(**kwargs)
    assert kwargs == before


def test_clean_extraction_receipt_carries_no_timestamp() -> None:
    receipt = require_clean_extraction(**clean_extraction_inputs())
    # The receipt binds the composed provenance hash, not a clock field of its own.
    assert "created_at" not in receipt
    assert _rederives(receipt)


# --- composition over the actually-sealed artifacts ---------------------------


def test_composes_the_sealed_frozen_z05_report() -> None:
    # The real frozen Z05 report is sealed PASS and does not claim completion, so
    # composing it produces a receipt; a regression that flipped its status or
    # completion flag would fail here.
    facts = load_sealed_z05()
    receipt = compose_sealed_z05(z05=facts)
    assert receipt["composed_package"] == "Z05"
    assert facts["completion_ready"] is False
    assert _rederives(receipt)


def test_reconciles_the_real_sealed_composed_packages() -> None:
    # Z05 and the thirteen *06 gates read from disk are each sealed PASS with
    # completion not claimed, so the accounting reconciles the whole composition.
    packages = load_sealed_accounting()
    receipt = reconcile_release_accounting(
        expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
    )
    assert receipt["reconciled_count"] == len(EXPECTED_PACKAGE_IDS)
    assert receipt["all_sealed"] is True
    assert _rederives(receipt)


def test_seals_a_terminal_release_over_the_real_composed_surfaces() -> None:
    verdict = seal_truthful_release(
        release_id="REL-Z06-REAL",
        z05=load_sealed_z05(),
        clean_extraction_inputs=clean_extraction_inputs(),
        maturity_sources=maturity_sources(),
        expected_package_ids=list(EXPECTED_PACKAGE_IDS),
        accounting_packages=load_sealed_accounting(),
    )
    assert verdict["terminal"] is True
    assert verdict["release_passed"] is True
    assert verdict["completion_ready"] is False
    assert verdict["production_ready"] is False
    assert verdict["signing_status"] == UNSIGNED_STATUS
    assert _rederives(verdict)
