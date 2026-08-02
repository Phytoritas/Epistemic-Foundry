"""Z02 signature_test: provenance verifies and signing status is honest.

This required-check module proves that the release-provenance record composed by
:mod:`z02_release_engine` conforms to the declaring schema
``schemas/plugin-release-provenance.schema.json``, is hash-re-derivable, and that
signing status is *derived* from the signatures actually present.  The reference
bundle is unsigned, so its status is ``UNSIGNED`` and it is not shippable -- the
fail-closed honesty boundary.  No real signature is fabricated.
"""

from __future__ import annotations

from epistemic_foundry.contracts import validate_artifact

import z02_release_engine as engine

FIXED_TS = "1970-01-01T00:00:00Z"

#: A well-formed but explicitly SYNTHETIC signature entry. It is used only to
#: prove the signing-status derivation is genuine (not vacuously always UNSIGNED);
#: it is never presented as a real cryptographic signature of the bundle.
SYNTHETIC_SIGNATURE = {
    "kind": "reference-detached",
    "identity": "epistemic-foundry-z02-reference",
    "signature": "SYNTHETIC-REFERENCE-SIGNATURE-NOT-CRYPTOGRAPHIC",
}


def _provenance(signatures=()):
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    return engine.build_provenance(
        generated_at=FIXED_TS, sbom=sbom, signatures=signatures
    )


def test_provenance_conforms_to_declaring_schema() -> None:
    provenance = _provenance()
    # Raises if the record violates plugin-release-provenance.schema.json.
    validate_artifact("plugin-release-provenance", provenance)


def test_provenance_is_deterministic_and_hash_rederivable() -> None:
    first = _provenance()
    second = _provenance()
    assert first == second
    report = engine.verify_provenance(first)
    assert report["rederivable"] is True
    assert report["refusals"] == []


def test_unsigned_reference_bundle_derives_unsigned_status() -> None:
    provenance = _provenance()
    assert engine.signing_status_of(provenance) == "UNSIGNED"
    assert provenance["signatures"] == []


def test_unsigned_reference_bundle_is_not_shippable() -> None:
    report = engine.verify_provenance(_provenance())
    assert report["signing_status"] == "UNSIGNED"
    assert report["shippable"] is False


def test_build_evidence_checks_are_all_present_and_pass() -> None:
    provenance = _provenance()
    statuses = {c["check_id"]: c["status"] for c in provenance["checks"]}
    for check_id in (
        "reproducible_build",
        "sbom_generated",
        "manifest_complete",
        "clean_extraction",
    ):
        assert statuses[check_id] == "PASS"
    assert provenance["builder"]["reproducible"] is True


def test_signing_overclaim_is_refused_with_typed_code() -> None:
    provenance = _provenance()
    attestation = engine.attest_signing_status(provenance, claimed_status="SIGNED")
    assert attestation["honest"] is False
    assert attestation["derived_status"] == "UNSIGNED"
    codes = {r["code"] for r in attestation["refusals"]}
    assert "EF_Z02_SIGNATURE_OVERCLAIM" in codes
    reason = attestation["refusals"][0]["reason"]
    assert len(reason) > 50


def test_honest_unsigned_claim_is_accepted() -> None:
    provenance = _provenance()
    attestation = engine.attest_signing_status(provenance, claimed_status="UNSIGNED")
    assert attestation["honest"] is True
    assert attestation["refusals"] == []


def test_signing_derivation_is_genuine_not_vacuous() -> None:
    # With a well-formed (synthetic) signature present, the derivation reports
    # SIGNED -- proving the gate is real and not hard-wired to UNSIGNED. The
    # reference bundle above deliberately ships no such signature.
    provenance = _provenance(signatures=[SYNTHETIC_SIGNATURE])
    assert engine.signing_status_of(provenance) == "SIGNED"
    honest = engine.attest_signing_status(provenance, claimed_status="SIGNED")
    assert honest["honest"] is True


def test_tampered_provenance_hash_is_refused() -> None:
    provenance = dict(_provenance())
    provenance["provenance_hash"] = "sha256:" + "0" * 64
    report = engine.verify_provenance(provenance)
    assert report["rederivable"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_PROVENANCE_NOT_REDERIVABLE" in codes
