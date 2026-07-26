"""An unmade comparison is not a reproduction; reading is not exporting."""

from __future__ import annotations

import pytest

from epistemic_foundry.release import (
    ReplayVerificationFailed,
    SourceAccessDenied,
    build_replay_report,
    build_source_integrity_report,
    export_permitted,
    replay_reproduced,
)
from epistemic_foundry.release.integrity import (
    deletion_propagates_to,
    require_export_permitted,
)
from epistemic_foundry.release.replay import (
    REQUIRED_PIN_CATEGORIES,
    missing_pin_categories,
    require_comparable,
)

FULL_PINS = [f"PIN-{name}" for name in REQUIRED_PIN_CATEGORIES]


def _replay(**overrides) -> dict:
    kwargs = dict(
        source_run_id="RUN-1",
        replay_run_id="RUN-1-replay",
        mode="strict",
        pinned_artifacts=FULL_PINS,
        unavailable_pins=[],
        artifact_hash_matches=2,
        artifact_hash_mismatches=0,
        gate_differences=[],
        verdict_differences=[],
    )
    kwargs.update(overrides)
    return build_replay_report(**kwargs)


# -- EF4-I39 replay sufficiency -----------------------------------------


def test_i39_equivalence_and_drift_are_derived() -> None:
    """The party running the replay must not grade whether it reproduced."""
    import inspect

    params = inspect.signature(build_replay_report).parameters
    assert "event_equivalence" not in params
    assert "drift_classification" not in params


def test_i39_clean_replay_is_exact() -> None:
    report = _replay()
    assert report["event_equivalence"] == "EXACT"
    assert report["drift_classification"] == "NONE"
    assert replay_reproduced(report) is True


def test_i39_unavailable_pin_makes_the_run_not_comparable() -> None:
    """A comparison that could not be made is not a reproduction."""
    report = _replay(unavailable_pins=["corpus snapshot 2026-01"])
    assert report["event_equivalence"] == "NOT_COMPARABLE"
    assert replay_reproduced(report) is False
    with pytest.raises(ReplayVerificationFailed) as excinfo:
        require_comparable(report)
    assert "unmade comparison is not a reproduction" in str(excinfo.value)


def test_i39_unavailable_pin_outranks_a_clean_hash_set() -> None:
    """Matching hashes cannot rescue a run whose pins never loaded."""
    report = _replay(unavailable_pins=["model"], artifact_hash_mismatches=0)
    assert report["event_equivalence"] == "NOT_COMPARABLE"
    assert report["drift_classification"] == "UNKNOWN"


def test_i39_hash_mismatch_is_drift() -> None:
    report = _replay(artifact_hash_mismatches=1, drift_causes=["CORPUS"])
    assert report["event_equivalence"] == "DRIFT"
    assert report["drift_classification"] == "CORPUS"


def test_i39_verdict_difference_is_drift() -> None:
    report = _replay(verdict_differences=["HYP-1 SUPPORTED -> UNDERDETERMINED"], drift_causes=["MODEL"])
    assert report["event_equivalence"] == "DRIFT"
    assert report["drift_classification"] == "MODEL"


def test_i39_several_causes_report_multiple() -> None:
    report = _replay(artifact_hash_mismatches=1, drift_causes=["CORPUS", "MODEL"])
    assert report["drift_classification"] == "MULTIPLE"


def test_i39_unexplained_drift_is_unknown_not_none() -> None:
    report = _replay(artifact_hash_mismatches=1, drift_causes=[])
    assert report["drift_classification"] == "UNKNOWN"


def test_i39_gate_difference_is_drift_in_strict_mode() -> None:
    strict = _replay(gate_differences=["G-1 reason text changed"])
    assert strict["event_equivalence"] == "DRIFT"


def test_i39_gate_difference_is_semantic_equivalence_in_semantic_mode() -> None:
    semantic = _replay(mode="semantic", gate_differences=["G-1 reason text changed"])
    assert semantic["event_equivalence"] == "SEMANTICALLY_EQUIVALENT"
    assert replay_reproduced(semantic) is False


def test_i39_required_pin_categories_cover_the_invariant() -> None:
    for category in ("run_spec", "context", "model", "tools", "policy", "corpus", "prompts"):
        assert category in REQUIRED_PIN_CATEGORIES
    assert missing_pin_categories(["PIN-model"])
    assert missing_pin_categories(FULL_PINS) == []


# -- EF4-I37 licence propagation ----------------------------------------


def _integrity(**overrides) -> dict:
    kwargs = dict(
        document_id="DOC-1",
        content_hash="sha256:" + "a" * 64,
        checks=[
            {
                "check_id": "hash_stable",
                "status": "PASS",
                "details": "unchanged",
                "evidence_artifact_ids": ["ART-hash"],
            }
        ],
        policy_version="4.0.0",
    )
    kwargs.update(overrides)
    return build_source_integrity_report(**kwargs)


def test_i37_status_is_derived_from_the_checks() -> None:
    passing = _integrity()
    assert passing["overall_status"] == "PASS"
    assert passing["trusted_for_extraction"] is True

    failing = _integrity(
        checks=[
            {
                "check_id": "hash_stable",
                "status": "FAIL",
                "details": "content changed",
                "evidence_artifact_ids": ["ART-hash"],
            }
        ]
    )
    assert failing["overall_status"] == "FAIL"
    assert failing["trusted_for_extraction"] is False


def test_i37_unchecked_source_is_not_trusted() -> None:
    with pytest.raises(SourceAccessDenied) as excinfo:
        _integrity(checks=[])
    assert "not trusted by default" in str(excinfo.value)


def test_i37_quarantine_outranks_a_passing_check() -> None:
    report = _integrity(
        checks=[
            {
                "check_id": "hash_stable",
                "status": "PASS",
                "details": "ok",
                "evidence_artifact_ids": ["ART-hash"],
            },
            {
                "check_id": "malware_scan",
                "status": "FAIL",
                "details": "flagged",
                "evidence_artifact_ids": ["ART-scan"],
            },
        ]
    )
    assert report["overall_status"] == "QUARANTINE"
    assert export_permitted(report, licence="CC0", verbatim=False) is False


def test_i37_ordinary_check_failure_is_fail_not_quarantine() -> None:
    """A formatting failure is not the same as a document that lies about itself."""
    report = _integrity(
        checks=[
            {
                "check_id": "encoding_valid",
                "status": "FAIL",
                "details": "mixed encodings",
                "evidence_artifact_ids": ["ART-enc"],
            }
        ]
    )
    assert report["overall_status"] == "FAIL"


def test_i37_extraction_permission_does_not_imply_verbatim_export() -> None:
    """Many licences allow analysis while forbidding redistribution."""
    report = _integrity()
    assert report["trusted_for_extraction"] is True
    assert export_permitted(report, licence="all-rights-reserved", verbatim=True) is False
    assert export_permitted(report, licence="all-rights-reserved", verbatim=False) is True


def test_i37_permissive_licence_allows_verbatim_export() -> None:
    assert export_permitted(_integrity(), licence="CC-BY", verbatim=True) is True


def test_i37_unrecognized_licence_is_not_permissive() -> None:
    """An unknown licence is treated as forbidding redistribution."""
    assert export_permitted(_integrity(), licence="SomeNewLicence-1.0", verbatim=True) is False


def test_i37_forbidden_export_raises_with_the_licence_named() -> None:
    with pytest.raises(SourceAccessDenied) as excinfo:
        require_export_permitted(_integrity(), licence="proprietary", verbatim=True)
    assert "proprietary" in str(excinfo.value)


def test_i37_deletion_propagates_transitively() -> None:
    """A retraction leaving extracted spans in place has not been honoured."""
    derived = {
        "DOC-1": ["SPAN-1", "SPAN-2"],
        "SPAN-1": ["CLM-1"],
        "CLM-1": ["EV-1"],
    }
    assert deletion_propagates_to("DOC-1", derived) == ["CLM-1", "EV-1", "SPAN-1", "SPAN-2"]


def test_i37_deletion_of_an_unreferenced_document_is_empty() -> None:
    assert deletion_propagates_to("DOC-9", {"DOC-1": ["SPAN-1"]}) == []
