"""unit_and_contract_tests — the happy path of every T05 surface.

A pinned backend produces a canonical manifest; a qualification binds that
manifest to an S05 execution qualification and carries the unprojected command
set; the descriptor table describes every declared evolution command and marks
which of them an executor may serve; an imported run reconciles and records
itself as non-authoritative; and an advisory binding that stays away from
Foundry authority is accepted.
"""

from __future__ import annotations

from epistemic_foundry.adapters.v4_t05 import (
    assert_backend_pinned,
    build_executor_registry,
    command_projection,
    load_evolution_surface,
    pin_backend,
    registrable_commands,
    require_no_imported_authority,
    tool_descriptors,
)
from epistemic_foundry.domain.status import ForgePhase
from epistemic_foundry.shinka_adapter.backend import ADVISORY_BACKEND_SIGNALS
from fixtures import (
    COMMIT,
    DISABLED_FEATURES,
    ENABLED_FEATURES,
    SANDBOX_PROFILE,
    backend_manifest,
    binding,
    execution_qualification,
    imported_run,
)


def test_a_pinned_manifest_carries_the_exact_build() -> None:
    manifest = backend_manifest()

    assert manifest["source_revision"] == COMMIT
    assert manifest["package_version"] == "0.3.1"
    assert manifest["sandbox_profile_id"] == SANDBOX_PROFILE
    assert manifest["manifest_hash"].startswith("sha256:")


def test_a_content_digest_is_also_an_acceptable_pin() -> None:
    manifest = backend_manifest(source_revision="sha256:" + "e" * 64)

    assert assert_backend_pinned(manifest)["source_revision"].startswith("sha256:")


def test_a_prerelease_version_is_still_an_exact_release() -> None:
    manifest = backend_manifest(package_version="0.4.0-rc.2")

    assert assert_backend_pinned(manifest)["package_version"] == "0.4.0-rc.2"


def test_the_binding_ties_the_qualification_to_the_execution_profile() -> None:
    execution = execution_qualification()
    record = binding(execution_qualification=execution)

    assert record["execution_qualification_hash"] == execution["qualification_hash"]
    assert record["executor_sandbox_profile"] == execution["sandbox_profile"]
    assert record["evaluator_bundle_hash"] == execution["evaluator_bundle_hash"]
    assert record["effect_receipt_channel_id"] == execution["effect_receipt_channel_id"]


def test_the_binding_carries_the_manifest_pin_and_its_hash() -> None:
    manifest = backend_manifest()
    record = binding(manifest=manifest)

    assert record["manifest_hash"] == manifest["manifest_hash"]
    assert record["source_revision"] == manifest["source_revision"]
    assert record["package_version"] == manifest["package_version"]
    assert record["backend_manifest_id"] == manifest["backend_manifest_id"]


def test_the_qualification_records_only_the_tested_capabilities() -> None:
    record = binding()
    tests = record["qualification"]["capability_tests"]

    assert sorted(name for name, held in tests.items() if held) == sorted(
        ENABLED_FEATURES
    )
    assert sorted(name for name, held in tests.items() if not held) == sorted(
        DISABLED_FEATURES
    )


def test_the_qualification_names_the_commands_it_cannot_serve() -> None:
    record = binding()
    projection = command_projection()

    assert (
        record["proposed_unavailable_commands"]
        == projection["proposed_unavailable_commands"]
    )
    assert record["registrable_commands"] == projection["available_commands"]
    assert record["surface_version"] == projection["surface_version"]


def test_the_surface_declaration_is_read_rather_than_summarized() -> None:
    document = load_evolution_surface()

    assert document["surface_id"]
    assert len(document["skills"]) == 15


def test_every_declared_command_has_a_descriptor_row() -> None:
    projection = command_projection()
    descriptors = tool_descriptors()
    commands = {row["command"] for row in descriptors}

    assert commands == set(projection["proposed_commands"]) | set(
        projection["available_commands"]
    )
    assert all(row["owning_skill_ids"] for row in descriptors)


def test_a_descriptor_is_projected_exactly_when_the_surface_projects_it() -> None:
    available = set(command_projection()["available_commands"])

    for row in tool_descriptors():
        assert row["projected"] is (row["command"] in available)


def test_only_projected_commands_are_registrable() -> None:
    assert registrable_commands() == tuple(command_projection()["available_commands"])


def test_an_executor_registry_binds_every_projected_command() -> None:
    executors = {
        command: f"EXEC-{index}" for index, command in enumerate(registrable_commands())
    }
    registry = build_executor_registry(registry_id="T05-REG-1", executors=executors)

    assert registry["registrations"] == executors
    assert registry["proposed_unavailable_commands"]
    assert registry["registry_hash"].startswith("sha256:")


def test_an_empty_registry_is_legal_and_still_names_the_gap() -> None:
    registry = build_executor_registry(registry_id="T05-REG-EMPTY", executors={})

    assert registry["registrations"] == {}
    assert len(registry["proposed_unavailable_commands"]) == 25


def test_an_imported_run_is_idle_and_manufactures_no_receipts() -> None:
    envelope = imported_run()
    record = envelope["imported_run"]

    assert record["derived_phase"] == str(ForgePhase.IDLE)
    assert record["manufactured_receipts"] is False
    assert envelope["authoritative"] is False


def test_an_imported_run_reconciles_its_own_population() -> None:
    envelope = imported_run()
    report = envelope["reconciliation"]

    assert report["reconciled"] is True
    assert report["counts"]["proposed"] == 3
    assert report["counts"]["persisted"] == 3
    assert report["missing"] == []


def test_terminal_dispositions_account_for_candidates_that_stopped() -> None:
    envelope = imported_run(
        candidate_identities={
            "proposed": ["c1", "c2", "c3"],
            "generated": ["c1", "c2", "c3"],
            "evaluated": ["c1", "c2"],
            "persisted": ["c1", "c2"],
            "failed": ["c3"],
        }
    )

    assert envelope["reconciliation"]["reconciled"] is True
    assert envelope["reconciliation"]["counts"]["failed"] == 1


def test_an_advisory_binding_away_from_authority_is_accepted() -> None:
    envelope = imported_run()
    signals = sorted(ADVISORY_BACKEND_SIGNALS)[:3]
    receipt = require_no_imported_authority(
        imported=envelope,
        bindings={signal: "search_hint" for signal in signals},
    )

    assert sorted(receipt["accepted_bindings"]) == signals
    assert receipt["authoritative"] is False
    assert receipt["import_id"] == envelope["imported_run"]["import_id"]


def test_binding_nothing_at_all_is_still_a_recorded_decision() -> None:
    receipt = require_no_imported_authority(imported=imported_run(), bindings={})

    assert receipt["accepted_bindings"] == {}
    assert receipt["gate_hash"].startswith("sha256:")


def test_the_manifest_builder_is_the_adapters_own_contract() -> None:
    # pin_backend forwards to the shinka adapter's builder rather than
    # rebuilding the manifest, so the canonical fields come from one place.
    manifest = pin_backend(
        backend_manifest_id="SBM-T05-2",
        backend_name="ShinkaEvolve",
        source_repository="https://example.invalid/shinka-evolve.git",
        source_revision="f" * 40,
        package_version="1.0.0",
        license="Apache-2.0",
        supported_candidate_types=["hypothesis-genome"],
        enabled_features=[],
        disabled_features=[],
        sandbox_profile_id=SANDBOX_PROFILE,
        adapter_version="4.0.0-t05.1",
    )

    assert manifest["backend_name"] == "ShinkaEvolve"
    assert manifest["license"] == "Apache-2.0"
