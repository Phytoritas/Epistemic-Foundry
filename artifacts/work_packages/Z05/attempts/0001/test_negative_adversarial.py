"""negative_and_adversarial_tests — every refusal fires under attack.

Each declared ``FINDING_CODES`` entry is provoked at least once, and the
adversarial cases are the ones this gate exists to stop: a release presented as
reconciled when it is not, a release that declares itself complete or
production-ready, a signature laundered onto an unverified reference bundle, a
provenance that cannot be described, an audit padded or carrying a failing lens, a
sealed surface bound with no identity, and a release path that tries to acquire
promotion authority or bind a score into a promotion decision.  A refusal that
fired under the wrong code would be as much a defect as no refusal at all, so
every case asserts the exact code.
"""

from __future__ import annotations

import pytest

from v4_z05 import zero_trust_release as mod
from v4_z05.zero_trust_release import (
    compose_lens_audit_attestation,
    compose_sealed_surface_fingerprint,
    require_no_release_authority_capture,
    require_reconciled_release,
    require_unsigned_provenance,
    seal_zero_trust_release,
)
from fixtures import (
    build_checks,
    lens_audit,
    provenance_inputs,
    reconciliation,
    release_kwargs,
)


def _code(caught: pytest.ExceptionInfo) -> str:
    return caught.value.code  # type: ignore[attr-defined]


# --- input integrity ----------------------------------------------------------


def test_empty_release_id_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_reconciled_release(release_id="", reconciliation=reconciliation())
    assert _code(caught) == "INPUT_INVALID"


def test_non_mapping_reconciliation_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_reconciled_release(release_id="R", reconciliation="not-a-mapping")  # type: ignore[arg-type]
    assert _code(caught) == "INPUT_INVALID"


def test_non_sequence_authority_claims_are_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_no_release_authority_capture(authority_claims={"not": "a-sequence"})  # type: ignore[arg-type]
    assert _code(caught) == "INPUT_INVALID"


def test_malformed_decision_basis_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_no_release_authority_capture(
            authority_claims=[
                {
                    "capability_id": "foundry:read",
                    "holder_id": "CAND-1",
                    "holder_is_search_space": False,
                    "decision_basis": "not-a-mapping",
                }
            ]
        )
    assert _code(caught) == "INPUT_INVALID"


def test_reshaped_status_ladder_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRegistry:
        def document(self, kind: str) -> dict:
            return {"properties": {"overall_status": {"enum": []}}}

    mod._pass_status_token.cache_clear()
    monkeypatch.setattr(mod, "default_registry", lambda: FakeRegistry())
    try:
        with pytest.raises(mod.ZeroTrustReleaseError) as caught:
            mod._pass_status_token()
        assert _code(caught) == "STATUS_VOCABULARY_DRIFT"
    finally:
        mod._pass_status_token.cache_clear()


# --- reconciliation -----------------------------------------------------------


def test_release_whose_reconciliation_did_not_pass_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_reconciled_release(
            release_id="R", reconciliation=reconciliation(status="FAIL")
        )
    assert _code(caught) == "RELEASE_NOT_RECONCILED"


def test_release_declaring_completion_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_reconciled_release(
            release_id="R", reconciliation=reconciliation(completion_ready=True)
        )
    assert _code(caught) == "RELEASE_CLAIMS_COMPLETION"


# --- signing provenance -------------------------------------------------------


def test_signature_on_an_unverified_release_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_unsigned_provenance(
            **provenance_inputs(
                signatures=[
                    {"kind": "sigstore", "identity": "ci", "signature": "deadbeef"}
                ]
            )
        )
    assert _code(caught) == "SIGNATURE_ON_UNVERIFIED_RELEASE"


def test_provenance_missing_build_evidence_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_unsigned_provenance(
            **provenance_inputs(checks=build_checks(reproducible_build="NOT_RUN"))
        )
    assert _code(caught) == "PROVENANCE_INCOMPLETE"


def test_provenance_with_a_floating_revision_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_unsigned_provenance(**provenance_inputs(source_revision="main"))
    assert _code(caught) == "PROVENANCE_INCOMPLETE"


def test_provenance_that_derives_a_signed_status_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If the sealed surface ever derived anything but UNSIGNED for this release,
    # the fail-closed rule refuses it rather than sealing a signed claim.
    monkeypatch.setattr(mod, "signing_status_of", lambda provenance: "SIGNED")
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_unsigned_provenance(**provenance_inputs())
    assert _code(caught) == "SIGNING_STATUS_NOT_UNSIGNED"


# --- 288-lens audit -----------------------------------------------------------


def test_audit_with_broken_arithmetic_is_refused() -> None:
    audit = lens_audit(families=2)
    audit["families"] = 3  # 3*12 != 24
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        compose_lens_audit_attestation(audit=audit)
    assert _code(caught) == "AUDIT_SHAPE_INVALID"


def test_audit_summary_that_does_not_partition_is_refused() -> None:
    audit = lens_audit(families=1, conditional=2)
    audit["summary"] = {"PASS": 12}  # ignores the two conditionals
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        compose_lens_audit_attestation(audit=audit)
    assert _code(caught) == "AUDIT_SHAPE_INVALID"


def test_audit_with_a_failing_lens_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        compose_lens_audit_attestation(audit=lens_audit(families=1, failing=1))
    assert _code(caught) == "AUDIT_HAS_FAILING_LENS"


# --- sealed surfaces ----------------------------------------------------------


def test_no_sealed_surface_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        compose_sealed_surface_fingerprint(surfaces={})
    assert _code(caught) == "SEALED_SURFACE_MISSING"


def test_sealed_surface_with_no_identity_token_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        compose_sealed_surface_fingerprint(surfaces={"security_v4_s05": []})
    assert _code(caught) == "SEALED_SURFACE_MISSING"


# --- authority containment ----------------------------------------------------


def test_search_artifact_granted_promotion_authority_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_no_release_authority_capture(
            authority_claims=[
                {
                    "capability_id": "promotion:commit",
                    "holder_id": "CAND-1",
                    "holder_is_search_space": True,
                }
            ]
        )
    assert _code(caught) == "RELEASE_ACQUIRES_PROMOTION_AUTHORITY"


def test_hook_granted_protected_authority_is_refused() -> None:
    # A caller-declared protected authority to a hook in the search space is
    # refused even when the capability is not the canonical promotion-commit one.
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_no_release_authority_capture(
            authority_claims=[
                {
                    "capability_id": "holdout:read",
                    "holder_id": "post-generate-hook",
                    "holder_is_search_space": True,
                    "protected_authority": True,
                }
            ]
        )
    assert _code(caught) == "RELEASE_ACQUIRES_PROMOTION_AUTHORITY"


def test_score_bound_into_a_promotion_decision_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        require_no_release_authority_capture(
            authority_claims=[
                {
                    "capability_id": "promotion:commit",
                    "holder_id": "gate",
                    "holder_is_search_space": False,
                    "decision_basis": {"predicted_utility": 0.91},
                }
            ]
        )
    assert _code(caught) == "SCORE_BOUND_INTO_PROMOTION_FIELD"


# --- maturity honesty ---------------------------------------------------------


def test_seal_claiming_completion_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        seal_zero_trust_release(**release_kwargs(), completion_ready=True)
    assert _code(caught) == "MATURITY_OVERCLAIM"


def test_seal_claiming_production_readiness_is_refused() -> None:
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        seal_zero_trust_release(**release_kwargs(), production_ready=True)
    assert _code(caught) == "MATURITY_OVERCLAIM"


def test_seal_propagates_a_composed_gate_refusal() -> None:
    # A failing lens in the composed audit fails the whole seal, not just the
    # standalone audit gate.
    with pytest.raises(mod.ZeroTrustReleaseError) as caught:
        seal_zero_trust_release(
            **release_kwargs(audit=lens_audit(families=1, failing=1))
        )
    assert _code(caught) == "AUDIT_HAS_FAILING_LENS"
