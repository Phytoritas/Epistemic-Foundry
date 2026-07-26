"""Novelty is not truth; promotion is not enthusiasm."""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.contracts import repo_root
from epistemic_foundry.hypothesis_passport import (
    PassportViolation,
    build_passport,
    mark_stale,
    status_dimensions_are_independent,
)
from epistemic_foundry.hypothesis_passport.passport import is_reportable


def _sample(**overrides) -> dict:
    payload = json.loads(
        (repo_root() / "examples" / "sample_passport.json").read_text(encoding="utf-8")
    )
    payload.update(overrides)
    return payload


# -- construction -------------------------------------------------------


def test_shipped_sample_passport_validates() -> None:
    passport = build_passport(_sample())
    assert passport["hypothesis_id"]


def test_four_status_axes_are_present_and_distinct() -> None:
    """Novelty, causal identification, support, and promotion stay separate."""
    passport = build_passport(_sample())
    for field in ("epistemic_status", "causal_status", "novelty_status", "promotion_level"):
        assert field in passport


# -- axis independence --------------------------------------------------


def test_underdetermined_support_cannot_carry_a_high_promotion_level() -> None:
    assert (
        status_dimensions_are_independent(
            epistemic_status="UNDERDETERMINED",
            novelty_status="CORPUS_NOVEL",
            promotion_level="REPLICATED",
            unresolved_objection_ids=[],
        )
        is False
    )


def test_contradicted_support_cannot_be_empirically_tested() -> None:
    assert (
        status_dimensions_are_independent(
            epistemic_status="CONTRADICTED",
            novelty_status="NOT_ASSESSED",
            promotion_level="EMPIRICALLY_TESTED",
            unresolved_objection_ids=[],
        )
        is False
    )


def test_novelty_does_not_raise_epistemic_standing() -> None:
    """A CORPUS_NOVEL result with weak support stays weakly supported."""
    assert (
        status_dimensions_are_independent(
            epistemic_status="UNDERDETERMINED",
            novelty_status="CORPUS_NOVEL",
            promotion_level="CANDIDATE",
            unresolved_objection_ids=[],
        )
        is True
    )


def test_entailed_with_open_objections_is_refused() -> None:
    assert (
        status_dimensions_are_independent(
            epistemic_status="ENTAILED",
            novelty_status="NOT_ASSESSED",
            promotion_level="CANDIDATE",
            unresolved_objection_ids=["OBJ-1"],
        )
        is False
    )


def test_build_rejects_a_collapsed_status_combination() -> None:
    with pytest.raises(PassportViolation) as excinfo:
        build_passport(
            _sample(
                epistemic_status="UNDERDETERMINED",
                promotion_level="REPLICATED",
                unresolved_objection_ids=[],
            )
        )
    assert "collapses independent axes" in str(excinfo.value)


def test_untestable_hypothesis_cannot_advance() -> None:
    with pytest.raises(PassportViolation):
        build_passport(_sample(epistemic_status="UNTESTABLE", promotion_level="VALIDATION_SCREENED"))


# -- staleness ----------------------------------------------------------


def test_marking_stale_records_reasons() -> None:
    passport = build_passport(_sample())
    stale = mark_stale(passport, ["EV-0001 invalidated after retraction"])
    assert stale["lifecycle_status"] == "stale"
    assert stale["stale_reasons"] == ["EV-0001 invalidated after retraction"]


def test_unexplained_staleness_is_refused() -> None:
    """Staleness without a reason is indistinguishable from a bug."""
    passport = build_passport(_sample())
    with pytest.raises(PassportViolation):
        mark_stale(passport, [])


def test_stale_passport_preserves_what_was_concluded() -> None:
    """The record shows the conclusion and that it no longer holds."""
    passport = build_passport(_sample())
    original_level = passport["promotion_level"]
    stale = mark_stale(passport, ["search scope widened"])
    assert stale["promotion_level"] == original_level


def test_only_active_passports_are_reportable() -> None:
    passport = build_passport(_sample())
    assert is_reportable(passport) is (passport["lifecycle_status"] == "active")
    stale = mark_stale(passport, ["evidence withdrawn"])
    assert is_reportable(stale) is False
