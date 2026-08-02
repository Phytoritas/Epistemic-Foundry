"""provenance_and_receipt_audit — every record re-derives, and nothing drifts.

A record this package emits is only evidence if the same inputs produce the
same bytes and the declared digest can be recomputed from the content.  These
tests re-derive every digest, run each builder twice and compare, prove no
input mapping is mutated on the way through, and show that the command
projection is read from the sealed surface file on each call rather than
carried as a copy inside the module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epistemic_foundry.adapters.v4_t05 import (
    EVOLUTION_SURFACE_PATH,
    AdapterGateError,
    assert_hash_rederives,
    build_executor_registry,
    command_projection,
    import_shinka_run,
    qualify_backend_adapter,
    registrable_commands,
    require_no_imported_authority,
    tool_descriptors,
)
from epistemic_foundry.adapters.v4_t05 import tool_surface as surface_module
from epistemic_foundry.domain.hashing import canonical_json, hash_excluding
from fixtures import (
    backend_manifest,
    binding,
    binding_arguments,
    capability_tests,
    execution_qualification,
    import_arguments,
    imported_run,
)

ROOT = Path(__file__).resolve().parents[5]


def test_the_binding_re_derives_its_own_digest() -> None:
    record = binding()

    assert (
        assert_hash_rederives(record, "binding_hash", "binding")
        == record["binding_hash"]
    )
    assert record["binding_hash"] == hash_excluding(record, "binding_hash")


def test_the_nested_qualification_re_derives_its_own_digest() -> None:
    qualification = binding()["qualification"]

    assert qualification["qualification_hash"] == hash_excluding(
        qualification, "qualification_hash"
    )


def test_the_import_envelope_and_its_record_both_re_derive() -> None:
    envelope = imported_run()

    assert envelope["import_hash"] == hash_excluding(envelope, "import_hash")
    record = envelope["imported_run"]
    assert record["record_hash"] == hash_excluding(record, "record_hash")


def test_the_registry_and_gate_receipts_re_derive() -> None:
    registry = build_executor_registry(
        registry_id="T05-REG-P",
        executors={command: "EXEC-1" for command in registrable_commands()},
    )
    receipt = require_no_imported_authority(imported=imported_run(), bindings={})

    assert registry["registry_hash"] == hash_excluding(registry, "registry_hash")
    assert receipt["gate_hash"] == hash_excluding(receipt, "gate_hash")


def test_every_builder_is_byte_identical_across_calls() -> None:
    for first, second in (
        (binding(), binding()),
        (imported_run(), imported_run()),
        (
            build_executor_registry(registry_id="R", executors={}),
            build_executor_registry(registry_id="R", executors={}),
        ),
        (backend_manifest(), backend_manifest()),
    ):
        assert canonical_json(first) == canonical_json(second)


def test_the_gate_receipt_is_stable_for_the_same_import() -> None:
    envelope = imported_run()
    first = require_no_imported_authority(
        imported=envelope, bindings={"novelty": "search_hint"}
    )
    second = require_no_imported_authority(
        imported=envelope, bindings={"novelty": "search_hint"}
    )

    assert canonical_json(first) == canonical_json(second)


def test_no_builder_mutates_the_mapping_it_was_given() -> None:
    manifest = backend_manifest()
    tests = capability_tests()
    execution = execution_qualification()
    manifest_before = canonical_json(manifest)
    tests_before = canonical_json(tests)
    execution_before = canonical_json(execution)

    qualify_backend_adapter(
        **binding_arguments(
            manifest=manifest, capability_tests=tests, execution_qualification=execution
        )
    )

    assert canonical_json(manifest) == manifest_before
    assert canonical_json(tests) == tests_before
    assert canonical_json(execution) == execution_before


def test_the_import_does_not_mutate_its_identity_lists() -> None:
    arguments = import_arguments()
    before = canonical_json(arguments["candidate_identities"])

    import_shinka_run(**arguments)

    assert canonical_json(arguments["candidate_identities"]) == before


def test_the_gate_does_not_mutate_the_envelope_it_inspects() -> None:
    envelope = imported_run()
    before = canonical_json(envelope)

    require_no_imported_authority(imported=envelope, bindings={"island": "map_hint"})

    assert canonical_json(envelope) == before


def test_the_surface_reader_returns_a_detached_copy() -> None:
    document = surface_module.load_evolution_surface()
    document["skills"].clear()

    assert surface_module.load_evolution_surface()["skills"]


def test_the_projection_is_read_from_the_surface_file_each_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The descriptor table is derived by reading the G05 declaration, not by
    # holding a copy of it.  Pointing the reader at an edited declaration must
    # change the projection.
    original = json.loads((ROOT / EVOLUTION_SURFACE_PATH).read_text(encoding="utf-8"))
    edited = json.loads(json.dumps(original))
    edited["skills"][0]["available_commands"] = ["archive inspect"]
    target = tmp_path / EVOLUTION_SURFACE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(edited), encoding="utf-8")
    monkeypatch.setattr(surface_module, "repo_root", lambda: tmp_path)

    projection = command_projection()

    assert "archive inspect" in projection["available_commands"]
    assert "archive inspect" not in projection["proposed_unavailable_commands"]
    assert len(projection["proposed_unavailable_commands"]) == 24


def test_an_unreadable_surface_refuses_rather_than_projecting_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(surface_module, "repo_root", lambda: tmp_path)

    with pytest.raises(AdapterGateError) as caught:
        tool_descriptors()

    assert caught.value.code == "SURFACE_UNREADABLE"


def test_a_surface_missing_a_declared_field_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = json.loads((ROOT / EVOLUTION_SURFACE_PATH).read_text(encoding="utf-8"))
    del original["skills"][0]["available_commands"]
    target = tmp_path / EVOLUTION_SURFACE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(surface_module, "repo_root", lambda: tmp_path)

    with pytest.raises(AdapterGateError) as caught:
        command_projection()

    assert caught.value.code == "SURFACE_UNREADABLE"
    assert caught.value.context["missing"] == ["available_commands"]


def test_a_surface_with_no_skills_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / EVOLUTION_SURFACE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"surface_id": "S", "surface_version": "1", "skills": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(surface_module, "repo_root", lambda: tmp_path)

    with pytest.raises(AdapterGateError) as caught:
        command_projection()

    assert caught.value.code == "SURFACE_UNREADABLE"


def test_a_record_without_its_hash_field_is_refused() -> None:
    with pytest.raises(AdapterGateError) as caught:
        assert_hash_rederives({"a": 1}, "binding_hash", "binding")

    assert caught.value.code == "RECORD_HASH_MISMATCH"


def test_the_binding_hash_covers_the_unprojected_command_set() -> None:
    # The commands the adapter cannot serve are inside the sealed record, so a
    # later edit that quietly shrinks the list breaks the digest.
    record = binding()
    edited = {**record, "proposed_unavailable_commands": []}

    assert hash_excluding(edited, "binding_hash") != record["binding_hash"]
