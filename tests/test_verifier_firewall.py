"""Evaluator immutability, holdout least privilege, leakage invalidation."""

from __future__ import annotations

import pytest

from epistemic_foundry.verifier_firewall import (
    EvaluatorDrift,
    HoldoutAccessDenied,
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)
from epistemic_foundry.verifier_firewall.firewall import FirewallRefusal

HASHES = tuple("sha256:" + digit * 64 for digit in "123456789")


@pytest.fixture()
def holdout() -> dict:
    return build_holdout_manifest(
        evaluator_id="EVAL-1",
        split_strategy="temporal",
        public_partition_refs=["ART-HOLDOUT-PUBLIC-1"],
        hidden_partition_handles=[
            "opaque://holdout/hidden/1",
            "opaque://holdout/hidden/2",
        ],
        ood_partition_handles=["opaque://holdout/ood/1"],
        adversarial_partition_handles=["opaque://holdout/adversarial/1"],
        content_hashes=HASHES[:4],
        acl_policy_hash=HASHES[4],
        log_redaction_policy="redact handles and hidden content from ordinary logs",
        cache_isolation_policy="evaluator-only content-addressed cache",
        holdout_id="HO-1",
        sealed_at="2026-07-28T00:00:00+00:00",
    )


@pytest.fixture()
def bundle(holdout: dict) -> dict:
    return build_evaluator_bundle(
        evaluator_version="1.0.0",
        code_artifact_id="ART-EVALUATOR-CODE-1",
        code_hash=HASHES[0],
        metric_contract_hash=HASHES[1],
        environment_digest=HASHES[2],
        dependency_lock_hash=HASHES[3],
        data_contract_hash=HASHES[4],
        policy_bundle_hash=HASHES[5],
        qualification_report_id="EQR-1",
        holdout_manifest_id=holdout["holdout_id"],
        evaluator_id=holdout["evaluator_id"],
        sealed_at="2026-07-28T00:00:00+00:00",
    )


@pytest.fixture()
def firewall(bundle: dict, holdout: dict) -> VerifierFirewall:
    return VerifierFirewall(
        bundle,
        holdout,
        holdout_read_principal_ids=["PRIN-validator"],
    )


def test_sealed_bundle_is_candidate_unreadable_and_immutable(bundle: dict) -> None:
    assert bundle["candidate_access"] is False
    assert bundle["immutable"] is True
    assert bundle["mutation_allowed_for_current_run"] is False


def test_holdout_defaults_to_no_candidate_access(holdout: dict) -> None:
    assert holdout["candidate_access"] is False
    assert holdout["mutation_model_access"] is False
    assert holdout["prompt_access"] is False
    assert holdout["backend_access"] is False


def test_firewall_refuses_a_candidate_readable_bundle(bundle: dict, holdout: dict) -> None:
    leaky = dict(bundle)
    leaky["candidate_access"] = True
    with pytest.raises(FirewallRefusal):
        VerifierFirewall(leaky, holdout, holdout_read_principal_ids=[])


def test_firewall_refuses_a_run_mutable_bundle(bundle: dict, holdout: dict) -> None:
    mutable = dict(bundle)
    mutable["mutation_allowed_for_current_run"] = True
    with pytest.raises(FirewallRefusal):
        VerifierFirewall(mutable, holdout, holdout_read_principal_ids=[])


def test_firewall_refuses_a_mismatched_holdout_binding(bundle: dict, holdout: dict) -> None:
    other = build_holdout_manifest(
        evaluator_id=holdout["evaluator_id"],
        split_strategy="random",
        public_partition_refs=[],
        hidden_partition_handles=["opaque://holdout/hidden/other"],
        ood_partition_handles=[],
        adversarial_partition_handles=[],
        content_hashes=[HASHES[6]],
        acl_policy_hash=HASHES[7],
        log_redaction_policy="redact all sealed handles",
        cache_isolation_policy="isolated evaluator cache",
        holdout_id="HO-OTHER",
        sealed_at="2026-07-28T00:00:00+00:00",
    )
    with pytest.raises(FirewallRefusal):
        VerifierFirewall(bundle, other, holdout_read_principal_ids=[])


def test_sealed_bundle_verifies_against_itself(firewall: VerifierFirewall) -> None:
    firewall.verify_self()


def test_metric_swap_is_detected_as_drift(firewall: VerifierFirewall, bundle: dict) -> None:
    tampered = dict(bundle)
    tampered["metric_contract_hash"] = HASHES[7]
    with pytest.raises(EvaluatorDrift):
        firewall.assert_unchanged(tampered)


def test_drift_detection_ignores_a_rewritten_bundle_hash(firewall: VerifierFirewall, bundle: dict) -> None:
    """Recomputing from content means a forged digest cannot hide an edit."""
    from epistemic_foundry.domain.hashing import hash_excluding

    tampered = dict(bundle)
    tampered["metric_contract_hash"] = HASHES[8]
    tampered["bundle_hash"] = hash_excluding(
        {k: v for k, v in tampered.items() if k != "bundle_hash"}, "bundle_hash"
    )
    with pytest.raises(EvaluatorDrift):
        firewall.assert_unchanged(tampered)


def test_listed_validator_may_read_the_holdout(firewall: VerifierFirewall) -> None:
    assert firewall.may_read_holdout("PRIN-validator", "validation_executor") is True
    firewall.require_holdout_access("PRIN-validator", "validation_executor")


def test_unlisted_principal_is_denied(firewall: VerifierFirewall) -> None:
    with pytest.raises(HoldoutAccessDenied):
        firewall.require_holdout_access("PRIN-stranger", "validation_executor")


def test_candidate_generating_role_is_denied_even_when_allowlisted(holdout: dict, bundle: dict) -> None:
    """A misconfigured allowlist must not become a capability."""
    firewall = VerifierFirewall(
        bundle,
        holdout,
        holdout_read_principal_ids=["PRIN-mutator"],
    )
    assert firewall.may_read_holdout("PRIN-mutator", "hypothesis_mutator") is False
    with pytest.raises(HoldoutAccessDenied) as excinfo:
        firewall.require_holdout_access("PRIN-mutator", "hypothesis_mutator")
    assert "candidate-generating" in str(excinfo.value)


def test_search_backend_is_treated_as_a_generator(firewall: VerifierFirewall) -> None:
    assert firewall.may_read_holdout("PRIN-validator", "search_backend") is False


def test_leakage_reports_the_touched_holdout_datasets(firewall: VerifierFirewall) -> None:
    assert firewall.leakage_invalidates(
        ["ART-HOLDOUT-PUBLIC-1", "opaque://holdout/hidden/2"]
    ) == ["opaque://holdout/hidden/2"]
    assert firewall.leakage_invalidates(["ART-HOLDOUT-PUBLIC-1"]) == []


def test_holdout_manifest_requires_explicit_hidden_handle_and_content_hash() -> None:
    common = {
        "evaluator_id": "EVAL-1",
        "split_strategy": "temporal",
        "public_partition_refs": [],
        "ood_partition_handles": [],
        "adversarial_partition_handles": [],
        "acl_policy_hash": HASHES[0],
        "log_redaction_policy": "redact all sealed handles",
        "cache_isolation_policy": "isolated evaluator cache",
    }
    with pytest.raises(FirewallRefusal, match="hidden partition"):
        build_holdout_manifest(
            **common,
            hidden_partition_handles=[],
            content_hashes=[HASHES[1]],
        )
    with pytest.raises(FirewallRefusal, match="content hash"):
        build_holdout_manifest(
            **common,
            hidden_partition_handles=["opaque://holdout/hidden/1"],
            content_hashes=[],
        )


def test_fixed_holdout_and_evaluator_inputs_have_stable_hashes() -> None:
    from epistemic_foundry.domain.hashing import hash_excluding

    first_holdout = holdout.__wrapped__()
    second_holdout = holdout.__wrapped__()
    assert first_holdout == second_holdout
    assert first_holdout["manifest_hash"] == hash_excluding(
        first_holdout, "manifest_hash"
    )
    first_bundle = bundle.__wrapped__(first_holdout)
    second_bundle = bundle.__wrapped__(second_holdout)
    assert first_bundle == second_bundle
    assert first_bundle["bundle_hash"] == hash_excluding(first_bundle, "bundle_hash")


def test_firewall_rejects_forged_recorded_hashes(bundle: dict, holdout: dict) -> None:
    forged_bundle = dict(bundle, bundle_hash=HASHES[8])
    with pytest.raises(FirewallRefusal, match="bundle hash mismatch"):
        VerifierFirewall(
            forged_bundle,
            holdout,
            holdout_read_principal_ids=[],
        )

    forged_holdout = dict(holdout, manifest_hash=HASHES[8])
    with pytest.raises(FirewallRefusal, match="manifest hash mismatch"):
        VerifierFirewall(
            bundle,
            forged_holdout,
            holdout_read_principal_ids=[],
        )


def test_firewall_owns_an_immutable_snapshot_of_holdout_handles(
    bundle: dict, holdout: dict
) -> None:
    firewall = VerifierFirewall(
        bundle,
        holdout,
        holdout_read_principal_ids=[],
    )
    injected_handle = "opaque://holdout/hidden/injected-after-seal"

    holdout["hidden_partition_handles"].append(injected_handle)

    assert firewall.leakage_invalidates([injected_handle]) == []
    assert firewall.leakage_invalidates(["opaque://holdout/hidden/1"]) == [
        "opaque://holdout/hidden/1"
    ]
