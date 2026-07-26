"""The backend adapter fails closed and never carries promotion authority."""

from __future__ import annotations

import pytest

from epistemic_foundry.shinka_adapter import (
    ADVISORY_BACKEND_SIGNALS,
    BackendNotQualified,
    UnmappableBackendSignal,
    build_backend_manifest,
    build_qualification,
    map_backend_signals,
)
from epistemic_foundry.shinka_adapter.backend import (
    REQUIRED_CAPABILITY_TESTS,
    assert_usable,
    signal_is_promotion_authority,
)


def _manifest(**overrides) -> dict:
    kwargs = dict(
        backend_name="ShinkaEvolve",
        source_repository="https://github.com/example/shinka-evolve",
        source_revision="9f2c1ab4d5e6f70819a2b3c4d5e6f708192a3b4c",
        package_version="0.4.2",
        license="Apache-2.0",
        supported_candidate_types=["program"],
        enabled_features=["island_migration"],
        disabled_features=["auto_promotion"],
        sandbox_profile_id="SBX-1",
        adapter_version="1.0.0",
    )
    kwargs.update(overrides)
    return build_backend_manifest(**kwargs)


def _tests(**overrides) -> dict:
    base = {name: True for name in REQUIRED_CAPABILITY_TESTS}
    base.update(overrides)
    return base


def _qualification(manifest: dict, **overrides) -> dict:
    kwargs = dict(
        backend_manifest_id=manifest["backend_manifest_id"],
        capability_tests=_tests(),
        known_limitations=["no native dependency-cluster concept"],
        status="QUALIFIED",
        allowed_release_level="EVOLUTION_MVP_50",
    )
    kwargs.update(overrides)
    return build_qualification(**kwargs)


# -- pinning ------------------------------------------------------------


def test_pinned_manifest_is_accepted() -> None:
    manifest = _manifest()
    assert manifest["license"] == "Apache-2.0"
    assert manifest["manifest_hash"].startswith("sha256:")


@pytest.mark.parametrize("revision", ["main", "HEAD", "latest", "master", ""])
def test_floating_revision_is_refused(revision: str) -> None:
    """A qualification result must describe the build that actually runs."""
    with pytest.raises(BackendNotQualified) as excinfo:
        _manifest(source_revision=revision)
    assert "pin an exact revision" in str(excinfo.value)


def test_missing_license_is_refused() -> None:
    with pytest.raises(BackendNotQualified) as excinfo:
        _manifest(license="  ")
    assert "Apache-2.0 obligations" in str(excinfo.value)


# -- qualification ------------------------------------------------------


def test_omitted_capability_dimension_is_refused() -> None:
    """A qualification must state False, not stay silent about a check."""
    manifest = _manifest()
    partial = _tests()
    del partial["evaluator_separation"]
    with pytest.raises(BackendNotQualified) as excinfo:
        _qualification(manifest, capability_tests=partial)
    assert "missing required dimension" in str(excinfo.value)


@pytest.mark.parametrize(
    "failing", ["sandbox_isolation", "effect_receipts", "evaluator_separation"]
)
def test_qualified_requires_the_critical_capabilities(failing: str) -> None:
    """Search performance cannot buy past isolation, receipts, or separation."""
    manifest = _manifest()
    with pytest.raises(BackendNotQualified) as excinfo:
        _qualification(manifest, capability_tests=_tests(**{failing: False}))
    assert failing in str(excinfo.value)


def test_failing_backend_may_still_be_recorded_as_conditional() -> None:
    """An honest CONDITIONAL record is allowed; a false QUALIFIED is not."""
    manifest = _manifest()
    record = _qualification(
        manifest,
        status="CONDITIONAL",
        capability_tests=_tests(deterministic_seed=False),
    )
    assert record["status"] == "CONDITIONAL"


def test_rejected_backend_may_not_be_used() -> None:
    manifest = _manifest()
    rejected = _qualification(manifest, status="REJECTED")
    with pytest.raises(BackendNotQualified):
        assert_usable(manifest, rejected)


def test_conditional_backend_may_be_used() -> None:
    manifest = _manifest()
    assert_usable(manifest, _qualification(manifest, status="CONDITIONAL"))


def test_qualification_for_another_manifest_is_refused() -> None:
    """A qualification cannot be transplanted onto a different build."""
    manifest = _manifest()
    other = _manifest(source_revision="0011223344556677889900aabbccddeeff001122")
    with pytest.raises(BackendNotQualified) as excinfo:
        assert_usable(other, _qualification(manifest))
    assert "but the manifest is" in str(excinfo.value)


# -- signal mapping -----------------------------------------------------


def test_known_signals_map_to_advisory_only() -> None:
    mapped = map_backend_signals({"combined_score": 0.91, "correct": True, "island": 3})
    assert set(mapped) == {"advisory"}
    assert mapped["advisory"]["combined_score"] == 0.91


def test_there_is_no_evidence_bucket() -> None:
    """No raw backend output may enter as Foundry evidence."""
    mapped = map_backend_signals({"novelty": 0.4})
    assert "evidence" not in mapped
    assert "promotion" not in mapped


def test_unknown_signal_fails_closed() -> None:
    with pytest.raises(UnmappableBackendSignal) as excinfo:
        map_backend_signals({"combined_score": 0.9, "mystery_verdict": "promote"})
    assert "no defined Foundry mapping" in str(excinfo.value)


def test_backend_correct_flag_is_advisory_not_authority() -> None:
    assert "correct" in ADVISORY_BACKEND_SIGNALS
    assert signal_is_promotion_authority("correct") is False
    assert signal_is_promotion_authority("combined_score") is False


def test_empty_signal_set_is_allowed() -> None:
    assert map_backend_signals({}) == {"advisory": {}}
