"""Z04 independent_attestation: attest the release evidence without a transcript.

This required-check module composes the deterministic :mod:`z04_release_gate`
engine to review the structured release evidence: it asserts that the release
label is the UNVERIFIED reference-maturity SPEC_BUNDLE at version 4.0.0 (not a
production/validated/GA release), that ``completion_ready`` is false and the
implementation gate fails in every source, that every declared external
conditional carries an owner, and that a label claiming production readiness is
refused fail-closed.  It seals nothing and mutates no canonical file.
"""

from __future__ import annotations

import pytest

import z04_release_gate as engine

FIXED_TS = "1970-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def report() -> dict:
    return engine.build_independent_attestation(generated_at=FIXED_TS)


def test_attestation_passes_fail_closed(report: dict) -> None:
    assert report["final_status"] == "PASS"
    assert report["refusals"] == []


def test_release_label_is_unverified_reference_maturity(report: dict) -> None:
    assert report["release_label"] == {
        "version": "4.0.0",
        "release_level": "SPEC_BUNDLE",
        "maturity": "UNVERIFIED_REFERENCE",
    }
    assert report["version_consistent"] is True
    assert report["non_production_status"] is True
    assert report["label_matches_evidence"] is True


def test_release_evidence_is_non_production(report: dict) -> None:
    evidence = report["release_label_evidence"]
    assert evidence["compat_status"] == "UNVERIFIED_REFERENCE_MATRIX"
    assert evidence["acceptance_bundle_status"] == "SPEC_BUNDLE"
    assert evidence["readiness"]["production_implementation"] == "NOT_CLAIMED"


def test_completion_ready_is_false_everywhere(report: dict) -> None:
    assert report["any_source_claims_ready"] is False
    assert report["completion_ready_sources"], "expected readiness sources"
    for source in report["completion_ready_sources"]:
        assert source["ready"] is False, source["source"]


def test_a_production_label_is_refused_fail_closed(report: dict) -> None:
    probe = report["overclaim_label_refused"]
    assert probe["decision"] == "REFUSED"
    assert probe["code"] == "EF_Z04_RELEASE_LABEL_OVERCLAIM"
    assert len(probe["reason"]) > 50
    assert report["honest_label_accepted"]["decision"] == "ACCEPT"


def test_overclaim_refusal_is_not_vacuous() -> None:
    for term in ("production", "validated", "GA"):
        decision = engine.refuse_overclaiming_label(
            {"version": "4.0.0", "maturity": f"4.0.0 {term}"}
        )
        assert decision["decision"] == "REFUSED", term


def test_every_conditional_has_an_owner(report: dict) -> None:
    conditionals = report["conditional_owners"]
    assert conditionals["all_owned"] is True
    assert conditionals["unowned"] == []
    assert conditionals["orphan_owners"] == []
    assert conditionals["declared_count"] == len(conditionals["owned"])
    for conditional, owner in conditionals["owned"].items():
        assert owner, conditional


def test_shinka_evolve_conditional_is_owned_and_marked_blocked(report: dict) -> None:
    owned = report["conditional_owners"]["owned"]
    shinka = next(
        (value for key, value in owned.items() if "ShinkaEvolve" in key), None
    )
    assert shinka is not None, "ShinkaEvolve conditional must be enumerated"
    assert "SPECIFIED-not-IMPLEMENTED" in shinka
    assert "BLOCKED" in shinka


def test_attestation_composes_the_other_two_gates(report: dict) -> None:
    assert report["release_reconciliation_status"] == "PASS"
    assert report["manifest_hash_status"] == "PASS"
    assert report["composed_release_reconciliation_sha256"].startswith("sha256:")
    assert report["composed_manifest_hash_reconciliation_sha256"].startswith("sha256:")


def test_assurance_limitation_is_declared(report: dict) -> None:
    assert "author/reviewer" in report["assurance_limitation"]
    assert (
        "external actor-independent certification does not hold"
        in (report["assurance_limitation"])
    )


def test_record_is_deterministic_and_hash_rederivable(report: dict) -> None:
    again = engine.build_independent_attestation(generated_at=FIXED_TS)
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = engine.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]
