"""Migration safety and transitive downstream invalidation."""

from __future__ import annotations

import pytest

from epistemic_foundry.updates import (
    MigrationRefused,
    build_impact_report,
    build_schema_migration,
    dependent_closure,
    migration_is_reversible,
)
from epistemic_foundry.updates.impact import trigger_invalidates
from epistemic_foundry.updates.migration import has_human_approval, requires_hook_retrust


def _migration(**overrides) -> dict:
    kwargs = dict(
        schema_name="claim-card",
        from_version="4.0.0",
        to_version="4.1.0",
        compatibility="backward_compatible",
        transform_entrypoint="migrations.claim_card:forward",
        reverse_transform_entrypoint="migrations.claim_card:reverse",
        preconditions=["all claim cards validate against 4.0.0"],
        postconditions=["all claim cards validate against 4.1.0"],
        fixture_artifact_ids=["FIX-1"],
        data_loss_possible=False,
        approval_record_id=None,
    )
    kwargs.update(overrides)
    return build_schema_migration(**kwargs)


# -- EF4-I31 migration safety -------------------------------------------


def test_i31_compatible_migration_is_accepted() -> None:
    migration = _migration()
    assert migration["compatibility"] == "backward_compatible"
    assert migration_is_reversible(migration) is True


def test_i31_breaking_migration_needs_a_reverse_transform() -> None:
    """A one-way door leaves no path back when a defect surfaces later."""
    with pytest.raises(MigrationRefused) as excinfo:
        _migration(
            compatibility="breaking",
            reverse_transform_entrypoint=None,
            approval_record_id="APR-1",
        )
    assert "one-way door" in str(excinfo.value)


def test_i31_breaking_migration_needs_human_approval() -> None:
    with pytest.raises(MigrationRefused) as excinfo:
        _migration(compatibility="breaking", approval_record_id=None)
    assert "human approval record" in str(excinfo.value)


def test_i31_data_lossy_migration_needs_approval_even_if_compatible() -> None:
    """Reversible in principle does not restore a dropped field."""
    with pytest.raises(MigrationRefused) as excinfo:
        _migration(data_loss_possible=True, approval_record_id=None)
    assert "data-lossy" in str(excinfo.value)


def test_i31_migration_without_fixtures_is_refused() -> None:
    with pytest.raises(MigrationRefused) as excinfo:
        _migration(fixture_artifact_ids=[])
    assert "claims rather than observations" in str(excinfo.value)


def test_i31_migration_without_postconditions_is_refused() -> None:
    with pytest.raises(MigrationRefused):
        _migration(postconditions=[])


def test_i31_no_op_version_change_is_refused() -> None:
    with pytest.raises(MigrationRefused) as excinfo:
        _migration(to_version="4.0.0")
    assert "hides whether the transform ran" in str(excinfo.value)


def test_i31_data_loss_defeats_reversibility() -> None:
    migration = _migration(data_loss_possible=True, approval_record_id="APR-1")
    assert migration["reverse_transform_entrypoint"]
    assert migration_is_reversible(migration) is False


def test_i31_breaking_change_requires_hook_retrust() -> None:
    breaking = _migration(compatibility="breaking", approval_record_id="APR-1")
    assert requires_hook_retrust(breaking) is True
    assert requires_hook_retrust(_migration()) is False


def test_i31_absence_sentinel_never_reads_as_approval() -> None:
    """The schema forbids a null approval id, so absence uses a sentinel.

    A sentinel is only safe if it cannot be mistaken for a real approval.
    """
    compatible = _migration()
    assert has_human_approval(compatible) is False
    approved = _migration(compatibility="breaking", approval_record_id="APR-1")
    assert has_human_approval(approved) is True


# -- EF4-I38 downstream invalidation ------------------------------------


DEPENDENTS = {
    "DOC-1": ["CLM-1", "CLM-2"],
    "CLM-1": ["EV-1"],
    "EV-1": ["PACK-1"],
    "PACK-1": ["PASSPORT-1"],
    "CLM-2": ["EV-2"],
}


def test_i38_closure_follows_the_whole_chain() -> None:
    """One-hop invalidation leaves Passports asserting a vanished foundation."""
    closure = dependent_closure(["DOC-1"], DEPENDENTS)
    assert closure == ["CLM-1", "CLM-2", "EV-1", "EV-2", "PACK-1", "PASSPORT-1"]


def test_i38_closure_tolerates_a_cycle() -> None:
    cyclic = {"A": ["B"], "B": ["C"], "C": ["A"]}
    assert dependent_closure(["A"], cyclic) == ["B", "C"]


def test_i38_closure_of_a_leaf_is_empty() -> None:
    assert dependent_closure(["PASSPORT-1"], DEPENDENTS) == []


def _report(**overrides) -> dict:
    kwargs = dict(
        trigger_event_id="EVT-1",
        trigger_type="document_retraction",
        affected_claim_ids=["CLM-1"],
        affected_evidence_ids=["EV-1"],
        affected_pack_ids=["PACK-1"],
        affected_passport_ids=["PASSPORT-1"],
        required_actions=["redeliberate", "revalidate"],
    )
    kwargs.update(overrides)
    return build_impact_report(**kwargs)


def test_i38_retraction_invalidates_every_affected_artifact() -> None:
    report = _report()
    assert report["invalidated_artifact_ids"] == ["CLM-1", "EV-1", "PACK-1", "PASSPORT-1"]


def test_i38_invalidating_trigger_cannot_invalidate_nothing() -> None:
    """Recording the trigger is not the same as applying it."""
    with pytest.raises(ValueError) as excinfo:
        _report(invalidated_artifact_ids=[])
    assert "recorded rather" in str(excinfo.value)


def test_i38_new_document_prompts_reassessment_not_invalidation() -> None:
    """New evidence may change a conclusion without making artifacts unsound."""
    report = _report(trigger_type="new_document", required_actions=["redeliberate"])
    assert report["invalidated_artifact_ids"] == []
    assert trigger_invalidates("new_document") is False


def test_i38_new_document_may_require_no_action() -> None:
    """An addition that changes nothing is a legitimate outcome."""
    report = _report(trigger_type="new_document", required_actions=["no_action"])
    assert report["required_actions"] == ["no_action"]


def test_i38_invalidation_cannot_require_no_action() -> None:
    """Voiding dependents without remediation leaves them void and unaddressed."""
    with pytest.raises(ValueError) as excinfo:
        _report(required_actions=["no_action"])
    assert "no remediation" in str(excinfo.value)


@pytest.mark.parametrize(
    "trigger",
    [
        "document_correction",
        "document_retraction",
        "claim_correction",
        "ontology_update",
        "policy_update",
        "schema_migration",
    ],
)
def test_i38_every_invalidating_trigger_propagates(trigger: str) -> None:
    report = _report(trigger_type=trigger)
    assert report["invalidated_artifact_ids"]


def test_i38_report_without_required_actions_is_refused() -> None:
    with pytest.raises(ValueError) as excinfo:
        _report(required_actions=[])
    assert "notification, not a remediation" in str(excinfo.value)
