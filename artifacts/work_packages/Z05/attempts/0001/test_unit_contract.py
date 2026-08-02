"""unit_and_contract_tests — the happy paths hold their contracts.

Every gate produces a content-addressed receipt that re-derives its own
identifier and hash, and every receipt is a pure function of its inputs.  These
tests exercise the compositions the way a whole zero-trust release would:
reconcile the sealed final release gate, derive an unsigned provenance through the
sealed release-provenance surface, compose the 288-lens audit, bind the sealed
security/tool/operations surfaces, contain authority, and seal the whole release
into one verdict that never claims completion or production-readiness.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import hash_excluding

from v4_z05.zero_trust_release import (
    RELEASE_AUDIT_PREFIX,
    RELEASE_AUTHORITY_PREFIX,
    RELEASE_PROVENANCE_PREFIX,
    RELEASE_RECONCILIATION_PREFIX,
    RELEASE_SURFACE_PREFIX,
    RELEASE_VERDICT_PREFIX,
    UNSIGNED_STATUS,
    compose_lens_audit_attestation,
    compose_sealed_surface_fingerprint,
    release_level_floor,
    require_no_release_authority_capture,
    require_reconciled_release,
    require_unsigned_provenance,
    seal_zero_trust_release,
)
from fixtures import (
    clean_authority_claims,
    lens_audit,
    provenance_inputs,
    reconciliation,
    release_kwargs,
    sealed_surfaces,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_reconciled_release_is_recorded_when_the_gate_passes() -> None:
    receipt = require_reconciled_release(
        release_id="REL-1", reconciliation=reconciliation()
    )
    assert receipt["reconciled"] is True
    assert receipt["completion_ready"] is False
    assert receipt["reconciliation_hash"].startswith("sha256:")
    assert receipt["receipt_id"].startswith(RELEASE_RECONCILIATION_PREFIX)
    assert _rederives(receipt)


def test_unsigned_provenance_derives_the_fail_closed_status() -> None:
    receipt = require_unsigned_provenance(**provenance_inputs())
    assert receipt["signing_status"] == UNSIGNED_STATUS
    assert receipt["reproducible"] is True
    assert receipt["provenance_hash"].startswith("sha256:")
    assert receipt["receipt_id"].startswith(RELEASE_PROVENANCE_PREFIX)
    assert _rederives(receipt)


def test_lens_audit_binds_when_no_lens_fails() -> None:
    receipt = compose_lens_audit_attestation(audit=lens_audit(families=2))
    assert receipt["total"] == 24
    assert receipt["families"] == 2
    assert "FAIL" not in receipt["status_counts"]
    assert receipt["audit_content_hash"].startswith("sha256:")
    assert receipt["receipt_id"].startswith(RELEASE_AUDIT_PREFIX)
    assert _rederives(receipt)


def test_conditional_lens_is_owned_not_failing() -> None:
    # A conditional lens is an owned, non-blocking remaining item; it binds.
    receipt = compose_lens_audit_attestation(
        audit=lens_audit(families=1, conditional=12)
    )
    assert receipt["status_counts"] == {"CONDITIONAL": 12}


def test_authority_claim_without_capture_is_recorded() -> None:
    receipt = require_no_release_authority_capture(
        authority_claims=[
            {
                "capability_id": "foundry:read",
                "holder_id": "CAND-1",
                "holder_is_search_space": True,
            },
            {
                "capability_id": "promotion:commit",
                "holder_id": "deterministic-gate-node",
                "holder_is_search_space": False,
                "decision_basis": {"gate_verdict_hash": "sha256:" + "0" * 64},
            },
        ]
    )
    assert receipt["no_authority_captured"] is True
    protected = [c for c in receipt["authority_claims"] if c["protected_authority"]]
    assert len(protected) == 1
    assert receipt["receipt_id"].startswith(RELEASE_AUTHORITY_PREFIX)
    assert _rederives(receipt)


def test_sealed_surface_fingerprint_binds_every_surface() -> None:
    receipt = compose_sealed_surface_fingerprint(surfaces=sealed_surfaces())
    assert receipt["surface_count"] == 3
    for entry in receipt["surfaces"].values():
        assert entry["token_count"] > 0
        assert entry["identity_hash"].startswith("sha256:")
    assert receipt["receipt_id"].startswith(RELEASE_SURFACE_PREFIX)
    assert _rederives(receipt)


def test_seal_binds_every_subreceipt_and_holds_the_maturity_floor() -> None:
    verdict = seal_zero_trust_release(**release_kwargs())
    assert verdict["release_passed"] is True
    assert verdict["completion_ready"] is False
    assert verdict["production_ready"] is False
    assert verdict["release_level"] == release_level_floor()
    assert verdict["signing_status"] == UNSIGNED_STATUS
    assert verdict["receipt_id"].startswith(RELEASE_VERDICT_PREFIX)
    for field in (
        "reconciliation_receipt_hash",
        "provenance_receipt_hash",
        "audit_receipt_hash",
        "authority_receipt_hash",
        "surface_receipt_hash",
    ):
        assert verdict[field].startswith("sha256:")
    assert _rederives(verdict)


def test_seal_is_a_pure_function_of_its_inputs() -> None:
    assert seal_zero_trust_release(**release_kwargs()) == seal_zero_trust_release(
        **release_kwargs()
    )


def test_empty_authority_claims_capture_nothing() -> None:
    receipt = require_no_release_authority_capture(authority_claims=[])
    assert receipt["authority_claims"] == []
    assert receipt["no_authority_captured"] is True


def test_default_seal_authority_claims_are_optional() -> None:
    kwargs = release_kwargs()
    kwargs.pop("authority_claims")
    verdict = seal_zero_trust_release(
        **kwargs, authority_claims=clean_authority_claims()
    )
    assert verdict["release_passed"] is True
