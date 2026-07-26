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


@pytest.fixture()
def holdout() -> dict:
    return build_holdout_manifest(
        dataset_or_fixture_ids=["DS-hidden-1", "DS-hidden-2"],
        split_strategy="temporal",
        selection_cutoff="2026-01-01",
        access_principal_ids=["PRIN-validator"],
        unblinding_policy="two-person rule, post-promotion only",
        rotation_policy="rotate on any confirmed leak",
    )


@pytest.fixture()
def bundle(holdout: dict) -> dict:
    return build_evaluator_bundle(
        version="1.0.0",
        evaluator_artifact_ids=["EVAL-1"],
        metric_ids=["METRIC-accuracy"],
        holdout_manifest_id=holdout["holdout_manifest_id"],
        environment_manifest_id="ENV-1",
        policy_bundle_id="POL-1",
    )


@pytest.fixture()
def firewall(bundle: dict, holdout: dict) -> VerifierFirewall:
    return VerifierFirewall(bundle, holdout)


def test_sealed_bundle_is_candidate_unreadable_and_immutable(bundle: dict) -> None:
    assert bundle["readable_by_candidates"] is False
    assert bundle["mutable_during_run"] is False


def test_holdout_defaults_to_no_candidate_access(holdout: dict) -> None:
    assert holdout["candidate_access"] == "NONE"


def test_firewall_refuses_a_candidate_readable_bundle(bundle: dict, holdout: dict) -> None:
    leaky = dict(bundle)
    leaky["readable_by_candidates"] = True
    with pytest.raises(FirewallRefusal):
        VerifierFirewall(leaky, holdout)


def test_firewall_refuses_a_run_mutable_bundle(bundle: dict, holdout: dict) -> None:
    mutable = dict(bundle)
    mutable["mutable_during_run"] = True
    with pytest.raises(FirewallRefusal):
        VerifierFirewall(mutable, holdout)


def test_firewall_refuses_a_mismatched_holdout_binding(bundle: dict, holdout: dict) -> None:
    other = build_holdout_manifest(
        dataset_or_fixture_ids=["DS-other"],
        split_strategy="random",
        selection_cutoff="2026-01-01",
        access_principal_ids=[],
        unblinding_policy="none",
        rotation_policy="none",
    )
    with pytest.raises(FirewallRefusal):
        VerifierFirewall(bundle, other)


def test_sealed_bundle_verifies_against_itself(firewall: VerifierFirewall) -> None:
    firewall.verify_self()


def test_metric_swap_is_detected_as_drift(firewall: VerifierFirewall, bundle: dict) -> None:
    tampered = dict(bundle)
    tampered["metric_ids"] = ["METRIC-something-friendlier"]
    with pytest.raises(EvaluatorDrift):
        firewall.assert_unchanged(tampered)


def test_drift_detection_ignores_a_rewritten_bundle_hash(firewall: VerifierFirewall, bundle: dict) -> None:
    """Recomputing from content means a forged digest cannot hide an edit."""
    from epistemic_foundry.domain.hashing import hash_excluding

    tampered = dict(bundle)
    tampered["metric_ids"] = ["METRIC-forged"]
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
    permissive = build_holdout_manifest(
        dataset_or_fixture_ids=holdout["dataset_or_fixture_ids"],
        split_strategy=holdout["split_strategy"],
        selection_cutoff=holdout["selection_cutoff"],
        access_principal_ids=["PRIN-mutator"],
        unblinding_policy=holdout["unblinding_policy"],
        rotation_policy=holdout["rotation_policy"],
        holdout_manifest_id=holdout["holdout_manifest_id"],
    )
    firewall = VerifierFirewall(bundle, permissive)
    assert firewall.may_read_holdout("PRIN-mutator", "hypothesis_mutator") is False
    with pytest.raises(HoldoutAccessDenied) as excinfo:
        firewall.require_holdout_access("PRIN-mutator", "hypothesis_mutator")
    assert "candidate-generating" in str(excinfo.value)


def test_search_backend_is_treated_as_a_generator(firewall: VerifierFirewall) -> None:
    assert firewall.may_read_holdout("PRIN-validator", "search_backend") is False


def test_leakage_reports_the_touched_holdout_datasets(firewall: VerifierFirewall) -> None:
    assert firewall.leakage_invalidates(["DS-public", "DS-hidden-2"]) == ["DS-hidden-2"]
    assert firewall.leakage_invalidates(["DS-public"]) == []
