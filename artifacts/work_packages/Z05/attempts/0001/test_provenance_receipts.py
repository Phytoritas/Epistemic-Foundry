"""provenance_and_receipt_audit — every effect resolves to an immutable receipt.

The invariants this suite pins are the ones the manifest's exit criteria turn on:
every release decision is a re-derivable, content-addressed receipt; two runs over
equal inputs produce byte-equal receipts; inputs are never mutated; the sealed
release verdict binds every sub-receipt by hash so it cannot be forged without
reproducing the gates it depends on; and the release carries no clock.  It also
composes the *actually-sealed* artifacts — the Z04 final reconciliation and the
288-lens audit read from disk — so a break in a composed surface fails here rather
than only in its own package.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload

from v4_z05.zero_trust_release import (
    RELEASE_RECONCILIATION_PREFIX,
    UNSIGNED_STATUS,
    compose_lens_audit_attestation,
    require_reconciled_release,
    require_unsigned_provenance,
    seal_zero_trust_release,
)
from fixtures import (
    lens_audit,
    load_final_reconciliation,
    load_lens_audit_document,
    provenance_inputs,
    reconciliation,
    release_kwargs,
    sealed_surfaces,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_reconciliation_receipt_rederives_its_own_identity_and_hash() -> None:
    receipt = require_reconciled_release(
        release_id="REL-1", reconciliation=reconciliation()
    )
    body = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_id", "receipt_hash"}
    }
    assert (
        receipt["receipt_id"]
        == RELEASE_RECONCILIATION_PREFIX + sha256_of_payload(body)[len("sha256:") :]
    )
    assert receipt["receipt_hash"] == hash_excluding(dict(receipt), "receipt_hash")


def test_every_gate_receipt_is_content_addressed_and_stable() -> None:
    assert require_reconciled_release(
        release_id="R", reconciliation=reconciliation()
    ) == require_reconciled_release(release_id="R", reconciliation=reconciliation())
    assert require_unsigned_provenance(
        **provenance_inputs()
    ) == require_unsigned_provenance(**provenance_inputs())
    assert compose_lens_audit_attestation(
        audit=lens_audit()
    ) == compose_lens_audit_attestation(audit=lens_audit())


def test_verdict_binds_each_subreceipt_hash() -> None:
    kwargs = release_kwargs()
    verdict = seal_zero_trust_release(**kwargs)

    reconciled = require_reconciled_release(
        release_id=kwargs["release_id"], reconciliation=kwargs["reconciliation"]
    )
    provenance = require_unsigned_provenance(**kwargs["provenance_inputs"])
    lens = compose_lens_audit_attestation(audit=kwargs["audit"])
    # The verdict carries the same sub-receipt hashes the standalone gates emit,
    # so it cannot be sealed without reproducing every gate it depends on.
    assert verdict["reconciliation_receipt_hash"] == reconciled["receipt_hash"]
    assert verdict["provenance_receipt_hash"] == provenance["receipt_hash"]
    assert verdict["audit_receipt_hash"] == lens["receipt_hash"]
    assert _rederives(verdict)


def test_receipts_are_byte_equal_across_equal_runs() -> None:
    assert seal_zero_trust_release(**release_kwargs()) == seal_zero_trust_release(
        **release_kwargs()
    )


def test_seal_does_not_mutate_its_inputs() -> None:
    kwargs = release_kwargs()
    before = copy.deepcopy(kwargs)
    seal_zero_trust_release(**kwargs)
    assert kwargs == before


def test_provenance_receipt_carries_no_timestamp() -> None:
    receipt = require_unsigned_provenance(**provenance_inputs())
    # The receipt binds the provenance hash, not a clock field of its own.
    assert "created_at" not in receipt
    assert _rederives(receipt)


# --- composition over the actually-sealed artifacts ---------------------------


def test_composes_the_sealed_z04_reconciliation() -> None:
    # The real sealed Z04 reconciliation passes and does not claim completion, so
    # composing it produces a reconciled receipt; a regression that flipped its
    # status or completion flag would fail here.
    facts = load_final_reconciliation()
    receipt = require_reconciled_release(
        release_id="REL-Z05-REAL", reconciliation=facts
    )
    assert receipt["reconciled"] is True
    assert facts["completion_ready"] is False
    assert _rederives(receipt)


def test_composes_the_sealed_288_lens_audit() -> None:
    # The real 288-lens audit carries no failing lens and its arithmetic closes.
    audit = load_lens_audit_document()
    receipt = compose_lens_audit_attestation(audit=audit)
    assert receipt["total"] == 288
    assert receipt["families"] == 24
    assert "FAIL" not in receipt["status_counts"]
    assert _rederives(receipt)


def test_seals_a_zero_trust_release_over_the_real_composed_surfaces() -> None:
    verdict = seal_zero_trust_release(
        release_id="REL-Z05-REAL",
        reconciliation=load_final_reconciliation(),
        provenance_inputs=provenance_inputs(),
        audit=load_lens_audit_document(),
        surfaces=sealed_surfaces(),
        authority_claims=[],
    )
    assert verdict["release_passed"] is True
    assert verdict["completion_ready"] is False
    assert verdict["production_ready"] is False
    assert verdict["signing_status"] == UNSIGNED_STATUS
    assert _rederives(verdict)
