"""error_correlation_eval — provider diversity measured, independence refused.

Required check: ``error_correlation_eval``.  Exit criterion under test: "vendor
diversity not assumed independence" (MASTER_SPEC section 19: different providers
are not assumed statistically independent).  The committed fixture of declared,
synthetic per-provider outcomes is evaluated as it stands; the 2x2 error
contingency and the phi coefficient are recomputed here from the raw trials
rather than read back from the report; the observed joint-error rate is shown to
exceed the rate independence would predict, so the measured diversity is a number
rather than an assumption; and the two overclaims this gate exists to refuse — a
provider presented as live, and a fixture asserting independence — are each
refused with their own typed finding.  The committed results artifact is
re-derived from the sealed surfaces and the fixture and any drift is refused.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from provider_parity_harness import (
    ProviderParityError,
    evaluate_correlation,
    evaluate_dataset,
    hash_excluding,
    load_dataset,
    verify_results,
)

ROOT = Path(__file__).resolve().parents[2]


def dataset() -> dict:
    return copy.deepcopy(load_dataset(ROOT))


def resealed(payload: dict) -> dict:
    payload["dataset_hash"] = hash_excluding(payload, "dataset_hash")
    return payload


def refused(payload: dict, code: str) -> ProviderParityError:
    with pytest.raises(ProviderParityError) as caught:
        evaluate_correlation(payload, ROOT)
    assert caught.value.code == code, caught.value.code
    return caught.value


def test_the_committed_fixture_evaluates_and_declares_no_independence() -> None:
    report = evaluate_correlation(dataset(), ROOT)

    assert report["status"] == "PASS"
    assert report["eval_id"] == "X04-ERROR-CORRELATION"
    assert report["synthetic"] is True
    assert report["independence_assumed"] is False
    assert report["diversity_position"] == "not_assumed_independent"


def test_the_contingency_and_phi_are_recomputed_from_the_raw_trials() -> None:
    payload = dataset()
    n11 = n10 = n01 = n00 = 0
    for trial in payload["trials"]:
        codex_error = trial["codex_outcome"] == "error"
        claude_error = trial["claude_outcome"] == "error"
        if codex_error and claude_error:
            n11 += 1
        elif codex_error:
            n10 += 1
        elif claude_error:
            n01 += 1
        else:
            n00 += 1

    report = evaluate_correlation(payload, ROOT)
    assert report["contingency"] == {
        "both_error": n11,
        "claude_only_error": n01,
        "codex_only_error": n10,
        "neither_error": n00,
    }
    denominator = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    expected_phi = (n11 * n00 - n10 * n01) / denominator
    assert report["phi_coefficient"] == pytest.approx(expected_phi)


def test_the_providers_errors_co_occur_more_than_independence_would_predict() -> None:
    report = evaluate_correlation(dataset(), ROOT)

    expected = report["codex_error_rate"] * report["claude_error_rate"]
    assert report["joint_error_expected_if_independent"] == pytest.approx(expected)
    assert report["joint_error_observed"] > report["joint_error_expected_if_independent"]
    assert report["excess_joint_error"] > 0
    assert report["positively_correlated"] is True
    assert report["phi_coefficient"] > 0


def test_a_fixture_asserting_independence_is_refused() -> None:
    payload = dataset()
    payload["diversity_position"] = "assumed_independent"

    error = refused(resealed(payload), "INDEPENDENCE_OVERCLAIM")

    assert error.context["diversity_position"] == "assumed_independent"


def test_a_provider_claimed_live_is_refused() -> None:
    payload = dataset()
    payload["providers"][0]["synthetic"] = False

    error = refused(resealed(payload), "PROVIDER_OVERCLAIM")

    assert error.context["provider_id"] == payload["providers"][0]["provider_id"]


def test_a_trial_outside_the_parity_surface_is_refused() -> None:
    payload = dataset()
    payload["trials"][0]["role_id"] = "not_a_canonical_role"

    error = refused(resealed(payload), "ROLE_NOT_IN_PARITY_SURFACE")

    assert error.context["role_id"] == "not_a_canonical_role"


def test_an_edited_fixture_breaks_its_own_hash() -> None:
    payload = dataset()
    payload["trials"][0]["codex_outcome"] = (
        "correct" if payload["trials"][0]["codex_outcome"] == "error" else "error"
    )

    refused(payload, "DATASET_HASH_MISMATCH")


def test_the_committed_results_artifact_is_the_report_the_sources_produce() -> None:
    derived = verify_results(ROOT)

    assert derived["report_hash"] == hash_excluding(derived, "report_hash")
    assert derived["parity"]["status"] == "PASS"
    assert derived["correlation"]["status"] == "PASS"
