"""Evolution proposes but cannot certify itself."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from epistemic_foundry.evolution_chamber import (
    FORBIDDEN_MUTATION_PATHS,
    AuthorityMutationRefused,
    apply_mutation,
    build_evolution_run_spec,
    build_mutation_receipt,
)
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.evolution_chamber.run_spec import (
    LEGACY_RUN_SPEC_RESOLUTION_REQUIRED,
    REQUIRED_RESOLVED_REF_KEYS,
    LegacyRunSpecResolutionRequired,
    evaluator_binding_changed,
    migrate_legacy_evolution_run_spec,
    rollback_legacy_evolution_run_spec,
)

CANDIDATE = {
    "genome_id": "HG-0001",
    "canonical_claim": "spaced practice improves delayed recall",
    "complexity_budget": 10,
    "uncertainty_notes": "effect size uncertain below n=100",
    "evaluator_bundle_id": "EB-0001",
    "holdout_manifest_id": "HM-0001",
    "status": "ELIGIBLE",
    "lineage_id": "LIN-0001",
    "provenance_hash": "sha256:" + "e" * 64,
}


# -- authority immutability --------------------------------------------


def test_ordinary_field_mutation_is_allowed() -> None:
    mutated = apply_mutation(CANDIDATE, {"canonical_claim": "spaced practice improves retention"})
    assert mutated["canonical_claim"] == "spaced practice improves retention"
    assert mutated["evaluator_bundle_id"] == CANDIDATE["evaluator_bundle_id"]


def test_evaluator_rebinding_is_refused() -> None:
    """A candidate may not choose the evaluator that judges it."""
    with pytest.raises(AuthorityMutationRefused) as excinfo:
        apply_mutation(CANDIDATE, {"evaluator_bundle_id": "EB-friendlier"})
    assert "may not certify itself" in str(excinfo.value)


def test_holdout_rebinding_is_refused() -> None:
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"holdout_manifest_id": "HM-easier"})


def test_self_promotion_is_refused() -> None:
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"status": "PROMOTED"})


def test_ledger_history_rewrite_is_refused() -> None:
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"ledger_event_ids": []})


def test_no_op_write_to_an_authority_field_is_still_refused() -> None:
    """Otherwise the boundary would depend on the value the operator picked."""
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"evaluator_bundle_id": CANDIDATE["evaluator_bundle_id"]})


def test_forbidden_set_covers_the_named_authority_surfaces() -> None:
    for field in (
        "evaluator_bundle_id",
        "holdout_manifest_id",
        "policy_bundle_id",
        "status",
        "gate_decision_ids",
        "approval_record_ids",
        "ledger_event_ids",
        "random_seed",
    ):
        assert field in FORBIDDEN_MUTATION_PATHS


# -- receipts -----------------------------------------------------------


def test_receipt_diff_is_derived_from_the_candidates() -> None:
    mutated = apply_mutation(CANDIDATE, {"complexity_budget": 12})
    receipt = build_mutation_receipt(
        evolution_run_id="ERS-0001",
        operator_id="OP-tighten-scope",
        input_candidates=[CANDIDATE],
        output_candidate=mutated,
        effect_receipt_id="EF-0001",
    )
    assert receipt["changed_paths"] == ["complexity_budget"]
    assert "evaluator_bundle_id" in receipt["preserved_paths"]


def test_receipt_catches_an_operator_that_edits_more_than_it_admits() -> None:
    """The diff is computed, so a smuggled authority edit is still caught."""
    smuggled = dict(CANDIDATE)
    smuggled["complexity_budget"] = 12
    smuggled["evaluator_bundle_id"] = "EB-smuggled"
    with pytest.raises(AuthorityMutationRefused) as excinfo:
        build_mutation_receipt(
            evolution_run_id="ERS-0001",
            operator_id="OP-sneaky",
            input_candidates=[CANDIDATE],
            output_candidate=smuggled,
            effect_receipt_id="EF-0001",
        )
    assert "evaluator_bundle_id" in str(excinfo.value)


def test_receipt_requires_an_input_candidate() -> None:
    with pytest.raises(ValueError):
        build_mutation_receipt(
            evolution_run_id="ERS-0001",
            operator_id="OP-1",
            input_candidates=[],
            output_candidate=CANDIDATE,
            effect_receipt_id="EF-0001",
        )


# -- run spec -----------------------------------------------------------


def _canonical_sample() -> dict:
    path = Path(__file__).resolve().parents[1] / "examples" / "sample_evolution-run-spec.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _spec_kwargs(**overrides) -> dict:
    sample = _canonical_sample()
    kwargs = {
        key: copy.deepcopy(value)
        for key, value in sample.items()
        if key not in {"evolution_run_id", "spec_hash"}
    }
    kwargs.update(overrides)
    return kwargs


def _spec(**overrides) -> dict:
    return build_evolution_run_spec(**_spec_kwargs(**overrides))


def test_run_spec_pins_evaluator_and_holdout() -> None:
    spec = _spec()
    assert spec["evaluator_bundle_id"] == "EB-FIXTURE-0001"
    assert spec["holdout_manifest_id"] == "HO-FIXTURE-0001"
    assert set(REQUIRED_RESOLVED_REF_KEYS) <= set(spec["resolved_refs"])
    assert spec["resolved_refs"]["evaluator_bundle"]["logical_id"] == spec["evaluator_bundle_id"]
    assert spec["resolved_refs"]["holdout_manifest"]["logical_id"] == spec["holdout_manifest_id"]
    assert spec["spec_hash"].startswith("sha256:")
    assert spec["spec_hash"] == hash_excluding(spec, "spec_hash")


def test_missing_resolved_refs_is_rejected_at_the_write_boundary() -> None:
    kwargs = _spec_kwargs()
    kwargs.pop("resolved_refs")
    with pytest.raises(TypeError):
        build_evolution_run_spec(**kwargs)


@pytest.mark.parametrize("resolved_refs", [None, {}])
def test_empty_or_null_resolved_refs_is_rejected(resolved_refs) -> None:
    with pytest.raises(ValueError, match="non-empty complete mapping"):
        _spec(resolved_refs=resolved_refs)


def test_floating_reference_is_rejected() -> None:
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    refs["selection_policy"]["exact_version_or_revision"] = "main"
    with pytest.raises(ValueError, match="floating or a version range"):
        _spec(resolved_refs=refs)


def test_version_range_is_rejected() -> None:
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    refs["stop_policy"]["exact_version_or_revision"] = ">=4.0,<5"
    with pytest.raises(ValueError, match="floating or a version range"):
        _spec(resolved_refs=refs)


def test_invalid_reference_hash_is_rejected() -> None:
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    refs["policy_bundle"]["content_hash"] = "sha256:not-a-digest"
    with pytest.raises(ValueError, match="64 lowercase hex"):
        _spec(resolved_refs=refs)


def test_unversioned_provider_alias_is_rejected() -> None:
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    refs["provider_adapter_manifest"]["remote_models"][0][
        "exact_exposed_model_identifier"
    ] = "gpt-4o"
    with pytest.raises(ValueError, match="unversioned provider alias"):
        _spec(resolved_refs=refs)


def test_external_backend_requires_an_immutable_source_pin() -> None:
    with pytest.raises(ValueError, match="external_backend_manifest"):
        _spec(external_backend_enabled=True)

    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    external = copy.deepcopy(refs["selection_policy"])
    external.update(
        {
            "logical_id": "BACKEND-FIXTURE-0001",
            "exact_version_or_revision": "backend-revision-0001",
            "resolved_artifact_locator": "artifact://fixture/backend/backend-revision-0001",
            "source_pin": {"exact_source_commit": "a" * 40},
        }
    )
    refs["external_backend_manifest"] = external
    spec = _spec(external_backend_enabled=True, resolved_refs=refs)
    assert spec["resolved_refs"]["external_backend_manifest"]["source_pin"] == {
        "exact_source_commit": "a" * 40
    }


def test_disabled_external_backend_rejects_a_manifest() -> None:
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    external = copy.deepcopy(refs["selection_policy"])
    external.update(
        {
            "logical_id": "BACKEND-FIXTURE-0001",
            "source_pin": {"immutable_package_digest": "sha256:" + "a" * 64},
        }
    )
    refs["external_backend_manifest"] = external
    with pytest.raises(ValueError, match="forbids"):
        _spec(resolved_refs=refs)


def test_top_level_authority_ids_must_match_resolved_refs() -> None:
    with pytest.raises(ValueError, match="does not bind"):
        _spec(evaluator_bundle_id="EB-DIFFERENT")


def test_builder_copies_refs_before_sealing() -> None:
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    spec = _spec(resolved_refs=refs)
    sealed_hash = spec["resolved_refs"]["policy_bundle"]["content_hash"]
    refs["policy_bundle"]["content_hash"] = "sha256:" + "0" * 64
    assert spec["resolved_refs"]["policy_bundle"]["content_hash"] == sealed_hash


def test_unbounded_run_is_refused() -> None:
    """Search-until-something-passes has no stop certificate."""
    with pytest.raises(ValueError) as excinfo:
        _spec(max_candidates=0)
    assert "stop certificate" in str(excinfo.value)


def test_run_without_a_seed_genome_is_refused() -> None:
    with pytest.raises(ValueError):
        _spec(seed_genome_ids=[])


def test_evaluator_swap_between_specs_is_detectable() -> None:
    original = _spec()
    refs = copy.deepcopy(_spec_kwargs()["resolved_refs"])
    refs["evaluator_bundle"]["logical_id"] = "EB-FIXTURE-0002"
    refs["evaluator_bundle"]["content_hash"] = "sha256:" + "b" * 64
    swapped = _spec(evaluator_bundle_id="EB-FIXTURE-0002", resolved_refs=refs)
    assert evaluator_binding_changed(original, swapped) is True
    assert evaluator_binding_changed(original, _spec()) is False


def test_evaluator_content_swap_is_detectable_even_when_logical_id_is_stable() -> None:
    original = _spec()
    swapped = copy.deepcopy(original)
    swapped["resolved_refs"]["evaluator_bundle"]["content_hash"] = "sha256:" + "c" * 64
    assert evaluator_binding_changed(original, swapped) is True


def _legacy_spec() -> dict:
    sample = _canonical_sample()
    for field in ("resolved_refs", "external_backend_enabled", "spec_hash"):
        sample.pop(field)
    return sample


def test_resolvable_legacy_spec_emits_migration_record() -> None:
    refs = copy.deepcopy(_canonical_sample()["resolved_refs"])
    result = migrate_legacy_evolution_run_spec(
        _legacy_spec(),
        resolved_refs=refs,
        external_backend_enabled=False,
        resolution_evidence_artifact_ids=["ART-LEDGER-FIXTURE-0001"],
        target_evolution_run_id="ER-FIXTURE-0001-V4",
        migration_id="MR-EVOLUTION-RUN-SPEC-FIXTURE-0001",
        recorded_at="2026-07-28T00:00:00+00:00",
    )
    migrated = result["evolution_run_spec"]
    record = result["migration_record"]
    assert migrated["evolution_run_id"] == "ER-FIXTURE-0001-V4"
    assert migrated["spec_hash"] == hash_excluding(migrated, "spec_hash")
    assert record["resolution_status"] == "RESOLVED"
    assert record["target_spec_hash"] == migrated["spec_hash"]
    assert record["migration_hash"] == hash_excluding(record, "migration_hash")


def test_unresolvable_legacy_spec_fails_closed() -> None:
    with pytest.raises(LegacyRunSpecResolutionRequired) as excinfo:
        migrate_legacy_evolution_run_spec(
            _legacy_spec(),
            resolved_refs=None,
            external_backend_enabled=False,
            resolution_evidence_artifact_ids=["ART-LEDGER-FIXTURE-0001"],
            target_evolution_run_id="ER-FIXTURE-0001-V4",
        )
    assert LEGACY_RUN_SPEC_RESOLUTION_REQUIRED in str(excinfo.value)


def test_legacy_migration_requires_resolution_evidence() -> None:
    with pytest.raises(LegacyRunSpecResolutionRequired, match="evidence"):
        migrate_legacy_evolution_run_spec(
            _legacy_spec(),
            resolved_refs=_canonical_sample()["resolved_refs"],
            external_backend_enabled=False,
            resolution_evidence_artifact_ids=[],
            target_evolution_run_id="ER-FIXTURE-0001-V4",
        )


def test_legacy_migration_never_overwrites_the_original_run_id() -> None:
    with pytest.raises(LegacyRunSpecResolutionRequired, match="distinct"):
        migrate_legacy_evolution_run_spec(
            _legacy_spec(),
            resolved_refs=_canonical_sample()["resolved_refs"],
            external_backend_enabled=False,
            resolution_evidence_artifact_ids=["ART-LEDGER-FIXTURE-0001"],
            target_evolution_run_id="ER-FIXTURE-0001",
        )


def test_legacy_migration_has_hash_bound_rollback() -> None:
    legacy = _legacy_spec()
    result = migrate_legacy_evolution_run_spec(
        legacy,
        resolved_refs=_canonical_sample()["resolved_refs"],
        external_backend_enabled=False,
        resolution_evidence_artifact_ids=["ART-LEDGER-FIXTURE-0001"],
        target_evolution_run_id="ER-FIXTURE-0001-V4",
    )
    assert rollback_legacy_evolution_run_spec(result, legacy) == legacy
    tampered = copy.deepcopy(legacy)
    tampered["objective"] = "tampered"
    with pytest.raises(LegacyRunSpecResolutionRequired, match="source hash"):
        rollback_legacy_evolution_run_spec(result, tampered)


def test_migration_fixture_executes_forward_transform_and_exact_rollback() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture_root = root / "migrations" / "contracts" / "fixtures"
    legacy = json.loads(
        (fixture_root / "evolution-run-spec-v3.json").read_text(encoding="utf-8")
    )
    resolution = json.loads(
        (fixture_root / "evolution-run-spec-resolution.json").read_text(
            encoding="utf-8"
        )
    )
    expected_record = json.loads(
        (fixture_root / "evolution-run-spec-migration-record.json").read_text(
            encoding="utf-8"
        )
    )
    refs = _canonical_sample()["resolved_refs"]

    result = migrate_legacy_evolution_run_spec(
        legacy,
        resolved_refs=refs,
        external_backend_enabled=resolution["external_backend_enabled"],
        resolution_evidence_artifact_ids=resolution[
            "resolution_evidence_artifact_ids"
        ],
        target_evolution_run_id=resolution["target_evolution_run_id"],
        migration_id=resolution["migration_id"],
        recorded_at=resolution["recorded_at"],
    )

    assert sha256_of_payload(legacy) == resolution["expected_source_artifact_hash"]
    assert result["evolution_run_spec"]["spec_hash"] == resolution[
        "expected_target_spec_hash"
    ]
    assert result["migration_record"]["migration_hash"] == resolution[
        "expected_migration_hash"
    ]
    assert result["migration_record"] == expected_record
    assert rollback_legacy_evolution_run_spec(result, legacy) == legacy

    migration_schema = json.loads(
        (root / "migrations" / "contracts" / "migration-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(migration_schema)
    validator = Draft202012Validator(
        migration_schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    assert list(validator.iter_errors(result["migration_record"])) == []


def test_compatibility_matrix_is_fail_closed_and_has_backfill_rollback() -> None:
    root = Path(__file__).resolve().parents[1]
    matrix = json.loads(
        (root / "migrations" / "contracts" / "compatibility-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    rows = {
        (row["consumer"], row["operation"], row["payload_version"]): row["result"]
        for row in matrix["rows"]
    }
    assert matrix["compatibility_window"]["write_window"] == "v4 only"
    assert matrix["compatibility_window"]["silent_fallback"] is False
    assert rows[("v4_runtime", "new_write", "v3")] == "REJECTED"
    assert rows[("v4_runtime", "legacy_read", "v3_unresolvable")] == (
        LEGACY_RUN_SPEC_RESOLUTION_REQUIRED
    )
    assert rows[("v3_runtime", "read", "v4")] == "UNSUPPORTED"
    assert matrix["backfill"] == {
        "dry_run_before_write": True,
        "unresolved_records_fail_closed": True,
        "partial_success_is_not_batch_success": True,
        "receipts_and_migration_records_required": True,
    }
    assert matrix["rollback"] == {
        "v3_source_retained": True,
        "exact_source_hash_required": True,
        "migration_records_retained": True,
        "promotion_or_effect_history_rewritten": False,
    }
