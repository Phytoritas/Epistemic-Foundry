"""EF4-I20: resume context is hash-bound, exclusion-aware, and freshness-gated."""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import sha256_of_payload
from epistemic_foundry.memory.capsule import (
    CapsuleRefused,
    CapsuleStale,
    build_context_capsule,
    capsule_is_fresh,
    require_rebuildable,
    stale_artifact_ids,
)

RUN_SPEC_HASH = sha256_of_payload({"run_spec": "RS-1"})
POLICY_HASH = sha256_of_payload({"policy": "PB-1"})
ART_A = sha256_of_payload({"artifact": "A"})
ART_B = sha256_of_payload({"artifact": "B"})


def a_capsule(**overrides: object) -> dict:
    kwargs: dict = {
        "session_id": "SESS-001",
        "phase": "O",
        "purpose": "resume the Observe phase after compaction",
        "run_spec_hash": RUN_SPEC_HASH,
        "policy_hash": POLICY_HASH,
        "artifact_hashes": {"ART-alpha": ART_A, "ART-beta": ART_B},
        "summaries": {"ART-alpha": "three supporting spans, one counter lane empty"},
        "excluded_artifact_ids": ["ART-omega"],
        "open_blockers": ["counter lane unsearched"],
        "allowed_capabilities": ["retrieval_read"],
        "token_budget": 8000,
        "expires_at": "2026-08-01T00:00:00+00:00",
    }
    kwargs.update(overrides)
    return build_context_capsule(**kwargs)  # type: ignore[arg-type]


# -- EF4-I20 canonical context capsule -----------------------------------


def test_i20_capsule_binds_each_summary_to_its_artifact_digest() -> None:
    capsule = a_capsule()
    (record,) = capsule["summaries"]
    assert record["artifact_id"] == "ART-alpha"
    assert record["source_hash"] == ART_A
    assert record["summary_hash"] == sha256_of_payload(record["summary"])


def test_i20_artifact_ids_are_derived_from_the_bound_hashes() -> None:
    """A capsule cannot list an artifact it holds no digest for."""
    capsule = a_capsule()
    assert capsule["artifact_ids"] == ["ART-alpha", "ART-beta"]


def test_i20_summary_for_an_uncarried_artifact_is_refused() -> None:
    with pytest.raises(CapsuleRefused) as excinfo:
        a_capsule(summaries={"ART-ghost": "a summary of something not carried"})
    assert "unbound summary" in str(excinfo.value)


def test_i20_unbound_artifact_digest_is_refused() -> None:
    with pytest.raises(CapsuleRefused) as excinfo:
        a_capsule(artifact_hashes={"ART-alpha": "not-a-digest"}, summaries={})
    assert "not a sha256 digest" in str(excinfo.value)


def test_i20_exclusion_and_inclusion_cannot_name_the_same_artifact() -> None:
    with pytest.raises(CapsuleRefused) as excinfo:
        a_capsule(excluded_artifact_ids=["ART-alpha"])
    assert "two different decisions" in str(excinfo.value)


def test_i20_exclusions_are_recorded_rather_than_omitted() -> None:
    """A withheld artifact is named, so 'not relevant' differs from 'absent'."""
    capsule = a_capsule()
    assert capsule["excluded_artifact_ids"] == ["ART-omega"]


def test_i20_a_prose_only_capsule_is_refused() -> None:
    with pytest.raises(CapsuleRefused) as excinfo:
        a_capsule(artifact_hashes={}, summaries={})
    assert "nothing to verify freshness against" in str(excinfo.value)


def test_i20_untyped_phase_is_refused() -> None:
    with pytest.raises(CapsuleRefused):
        a_capsule(phase="OBSERVE")


def test_i20_purposeless_capsule_is_refused() -> None:
    with pytest.raises(CapsuleRefused):
        a_capsule(purpose="   ")


# -- EF4-I20 freshness ---------------------------------------------------


def test_i20_undeclared_expiry_is_not_fresh() -> None:
    """`expires_at: null` is recordable but not usable for resume."""
    capsule = a_capsule(expires_at=None)
    assert capsule["expires_at"] is None
    assert capsule_is_fresh(capsule, now="2026-07-27T00:00:00+00:00") is False


def test_i20_expired_capsule_is_not_fresh() -> None:
    capsule = a_capsule()
    assert capsule_is_fresh(capsule, now="2026-09-01T00:00:00+00:00") is False


def test_i20_live_capsule_is_fresh() -> None:
    capsule = a_capsule()
    assert capsule_is_fresh(capsule, now="2026-07-27T00:00:00+00:00") is True


# -- EF4-I20 rebuild refusals -------------------------------------------


def test_i20_changed_artifact_is_reported_stale() -> None:
    capsule = a_capsule()
    changed = {"ART-alpha": sha256_of_payload({"artifact": "A-edited"}), "ART-beta": ART_B}
    assert stale_artifact_ids(capsule, changed) == ["ART-alpha"]


def test_i20_deleted_artifact_is_stale_not_unchanged() -> None:
    capsule = a_capsule()
    assert stale_artifact_ids(capsule, {"ART-alpha": ART_A}) == ["ART-beta"]


def test_i20_unchanged_artifacts_report_no_staleness() -> None:
    capsule = a_capsule()
    assert stale_artifact_ids(capsule, {"ART-alpha": ART_A, "ART-beta": ART_B}) == []


def test_i20_rebuild_from_a_changed_artifact_is_refused() -> None:
    capsule = a_capsule()
    with pytest.raises(CapsuleStale) as excinfo:
        require_rebuildable(
            capsule,
            current_hashes={"ART-alpha": sha256_of_payload({"artifact": "edited"}), "ART-beta": ART_B},
            now="2026-07-27T00:00:00+00:00",
            expected_run_spec_hash=RUN_SPEC_HASH,
            expected_policy_hash=POLICY_HASH,
        )
    assert "no longer exists" in str(excinfo.value)


def test_i20_rebuild_from_an_expired_capsule_is_refused() -> None:
    capsule = a_capsule()
    with pytest.raises(CapsuleStale) as excinfo:
        require_rebuildable(
            capsule,
            current_hashes={"ART-alpha": ART_A, "ART-beta": ART_B},
            now="2026-09-01T00:00:00+00:00",
            expected_run_spec_hash=RUN_SPEC_HASH,
            expected_policy_hash=POLICY_HASH,
        )
    assert "freshness window" in str(excinfo.value)


def test_i20_capsule_from_another_run_is_refused() -> None:
    capsule = a_capsule()
    with pytest.raises(CapsuleStale) as excinfo:
        require_rebuildable(
            capsule,
            current_hashes={"ART-alpha": ART_A, "ART-beta": ART_B},
            now="2026-07-27T00:00:00+00:00",
            expected_run_spec_hash=sha256_of_payload({"run_spec": "RS-other"}),
            expected_policy_hash=POLICY_HASH,
        )
    assert "different RunSpec" in str(excinfo.value)


def test_i20_capsule_from_a_superseded_policy_is_refused() -> None:
    capsule = a_capsule()
    with pytest.raises(CapsuleStale) as excinfo:
        require_rebuildable(
            capsule,
            current_hashes={"ART-alpha": ART_A, "ART-beta": ART_B},
            now="2026-07-27T00:00:00+00:00",
            expected_run_spec_hash=RUN_SPEC_HASH,
            expected_policy_hash=sha256_of_payload({"policy": "PB-2"}),
        )
    assert "different policy" in str(excinfo.value)


def test_i20_a_fresh_unchanged_capsule_rebuilds() -> None:
    capsule = a_capsule()
    require_rebuildable(
        capsule,
        current_hashes={"ART-alpha": ART_A, "ART-beta": ART_B},
        now="2026-07-27T00:00:00+00:00",
        expected_run_spec_hash=RUN_SPEC_HASH,
        expected_policy_hash=POLICY_HASH,
    )
