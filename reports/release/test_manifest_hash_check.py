"""Z04 manifest_hash_check: canonical manifest hashing and pin reconciliation.

This required-check module composes the deterministic :mod:`z04_release_gate`
engine to prove that the four canonical manifests parse and hash deterministically
(canonical-JSON sha256) and to reconcile the ``PACKAGE_MANIFEST.json`` byte pins.
Where a pin is stale because a later sealed package modified the file within its
own write scope, the row is recorded as owned tracked debt -- not a gate failure
-- because no collected conformance test enforces the pin.  The check mutates no
canonical file.
"""

from __future__ import annotations

import pytest

import z04_release_gate as engine

FIXED_TS = "1970-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def report() -> dict:
    return engine.build_manifest_hash_reconciliation(generated_at=FIXED_TS)


def test_gate_passes(report: dict) -> None:
    assert report["final_status"] == "PASS"


def test_canonical_manifest_hashing_is_deterministic(report: dict) -> None:
    assert report["canonical_hashing_deterministic"] is True
    assert set(report["canonical_manifest_sha256"]) == set(
        engine.CANONICAL_MANIFEST_PATHS
    )
    for path, digest in report["canonical_manifest_sha256"].items():
        assert digest.startswith("sha256:"), path
        assert digest == engine.manifest_canonical_sha256(engine.REPO_ROOT / path)


def test_all_pinned_manifests_are_reconciled(report: dict) -> None:
    reconciled_paths = {row["path"] for row in report["pin_reconciliation"]}
    assert reconciled_paths == set(engine.PINNED_MANIFEST_PATHS)


def test_stale_pins_are_owned_tracked_debt(report: dict) -> None:
    for row in report["stale_pins"]:
        assert row["matches"] is False
        assert row["owner"] == "B04/canonical-registry regeneration (out of Z04 scope)"
        assert row["disposition"] == "tracked_debt"
    assert report["stale_pins_are_tracked_debt"] is True


def test_compatibility_matrix_pin_is_a_recorded_stale_finding(report: dict) -> None:
    # The task calls out the compatibility_matrix pin explicitly: it must appear
    # as a reconciled, owned stale finding rather than silently pass or fail.
    row = next(
        r
        for r in report["pin_reconciliation"]
        if r["path"] == "manifests/compatibility_matrix.yaml"
    )
    assert row["matches"] is False
    assert row["owner"] == "B04/canonical-registry regeneration (out of Z04 scope)"


def test_no_conformance_test_enforces_the_stale_pin(report: dict) -> None:
    assert report["pin_enforcement_references"] == []


def test_record_is_deterministic_and_hash_rederivable(report: dict) -> None:
    again = engine.build_manifest_hash_reconciliation(generated_at=FIXED_TS)
    assert report["record_sha256"] == again["record_sha256"]
    recomputed = engine.record_sha256(
        {k: v for k, v in report.items() if k != "record_sha256"}
    )
    assert recomputed == report["record_sha256"]
