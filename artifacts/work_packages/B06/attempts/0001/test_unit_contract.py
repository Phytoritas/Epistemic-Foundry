"""unit_and_contract_tests — the comparator and the ledger, on the happy path.

The comparator is exercised against staged archive trees rather than against a
real double build, because a real ``uv build`` pair takes minutes and a unit
suite that slow stops being run.  The real double build is not skipped: it runs
as its own ``reproducible-build`` check in ``run_b06_0001_checks.py``, against
the actual repository, and its receipt lands in ``build/v4_b06``.  What is
proved here is that the comparator accepts identical trees, that the ledger and
the records re-derive their own hashes, that repeated construction is
byte-identical, and that nothing the gate is handed is modified underneath it.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from b06_gate import (
    DECLARED_NORMALIZATIONS,
    INHERITED_BUILD_FLAGS,
    LEDGER_NAME,
    NORMALIZATION_VARIABLES,
    SNAPSHOT_DIRECTORIES,
    archive_members,
    build_command,
    build_gate_manifest,
    build_pin_ledger,
    build_reproducibility_record,
    compare_build_trees,
    emit_pin_ledger,
    hash_excluding,
    inventory,
    normalized_environment,
    render,
    require_snapshot_copy,
    stage_snapshot,
    tree_sha256,
    validate_pin_ledger,
)
from fixtures import (
    DEFAULT_MEMBERS,
    EPOCH,
    ROOT,
    SDIST_NAME,
    TIMESTAMP,
    WHEEL_NAME,
    build_output,
    identical_outputs,
    ledger,
    staged_project,
)


def record(**overrides: object) -> dict:
    payload = {
        "artifacts": {WHEEL_NAME: {"bytes": 10, "sha256": "sha256:" + "a" * 64}},
        "source_snapshot_sha256": "sha256:" + "b" * 64,
        "source_date_epoch": EPOCH,
        "command": build_command("toolchains/python-build-constraints.txt", "out"),
        "generated_at": TIMESTAMP,
    }
    payload.update(overrides)
    return build_reproducibility_record(**payload)  # type: ignore[arg-type]


def test_two_identical_build_trees_compare_equal(tmp_path: Path) -> None:
    first, second = identical_outputs(tmp_path)

    artifacts = compare_build_trees(first, second)

    assert sorted(artifacts) == sorted([SDIST_NAME, WHEEL_NAME])
    assert artifacts[WHEEL_NAME]["sha256"].startswith("sha256:")
    assert artifacts == inventory(first) == inventory(second)


def test_the_comparator_does_not_touch_the_trees_it_compares(tmp_path: Path) -> None:
    first, second = identical_outputs(tmp_path)
    before = (tree_sha256(first), tree_sha256(second))

    compare_build_trees(first, second)

    assert (tree_sha256(first), tree_sha256(second)) == before


def test_archive_members_lists_what_each_distribution_carries(
    tmp_path: Path,
) -> None:
    output = build_output(tmp_path, "output")

    wheel = archive_members(output / WHEEL_NAME)
    sdist = archive_members(output / SDIST_NAME)

    assert set(wheel) == set(DEFAULT_MEMBERS)
    assert set(sdist) == set(DEFAULT_MEMBERS)
    assert wheel == sdist
    assert all(digest.startswith("sha256:") for digest in wheel.values())


def test_the_pin_ledger_re_derives_its_own_hash() -> None:
    document = ledger()

    assert hash_excluding(document, "ledger_hash") == document["ledger_hash"]
    assert validate_pin_ledger(document)["status"] == "PASS"


def test_the_pin_ledger_is_the_same_document_every_time() -> None:
    assert render(ledger()) == render(ledger())


def test_the_pin_ledger_covers_every_external_execution_pin() -> None:
    document = ledger()
    kinds = {entry["kind"] for entry in document["entries"]}

    assert {
        "build_backend",
        "container_image",
        "dependency_lock",
        "external_backend",
        "toolchain_lock",
    } <= kinds
    assert document["executable_pin_count"] + document["blocked_pin_count"] == len(
        document["entries"]
    )
    assert document["blocked_pin_count"] >= 1


def test_the_unqualified_backend_is_recorded_as_blocked_not_executable() -> None:
    entry = next(
        item for item in ledger()["entries"] if item["kind"] == "external_backend"
    )

    assert entry["execution_permitted"] is False
    assert entry["digest"] is None
    assert "source_revision" in entry["unpinned_fields"]
    assert "manifest_hash" in entry["unpinned_fields"]
    assert len(entry["blocking_reason"]) > 20


def test_validating_a_ledger_does_not_modify_it() -> None:
    document = ledger()
    before = json.dumps(document, ensure_ascii=False, sort_keys=True)

    validate_pin_ledger(document)

    assert json.dumps(document, ensure_ascii=False, sort_keys=True) == before


def test_emitting_the_ledger_twice_writes_identical_bytes(tmp_path: Path) -> None:
    first = emit_pin_ledger(ROOT, generated_at=TIMESTAMP, out_dir=tmp_path / "one")
    second = emit_pin_ledger(ROOT, generated_at=TIMESTAMP, out_dir=tmp_path / "two")

    assert first == second
    assert (tmp_path / "one" / LEDGER_NAME).read_bytes() == (
        tmp_path / "two" / LEDGER_NAME
    ).read_bytes()
    assert first["status"] == "PASS"


def test_the_reproducibility_record_re_derives_its_own_hash() -> None:
    document = record()

    assert hash_excluding(document, "record_hash") == document["record_hash"]
    assert document["bit_identical"] is True
    assert document["generated_at"] == TIMESTAMP
    assert document["normalizations"] == dict(DECLARED_NORMALIZATIONS)


def test_the_reproducibility_record_is_deterministic() -> None:
    assert render(record()) == render(record())


def test_the_gate_manifest_binds_both_records_to_the_generator() -> None:
    document = ledger()
    reproducibility = record()
    outputs = {"build/v4_b06/pin-ledger.json": "sha256:" + "c" * 64}

    manifest = build_gate_manifest(
        outputs=outputs,
        ledger=document,
        reproducibility=reproducibility,
        generated_at=TIMESTAMP,
        generator_sha256="sha256:" + "d" * 64,
    )

    assert hash_excluding(manifest, "manifest_hash") == manifest["manifest_hash"]
    assert manifest["pin_ledger_hash"] == document["ledger_hash"]
    assert manifest["reproducibility_record_hash"] == reproducibility["record_hash"]
    assert manifest["reproducible"] is True
    assert manifest["outputs"] == outputs


def test_the_build_environment_carries_the_declared_normalizations() -> None:
    before = dict(os.environ)

    environment = normalized_environment(EPOCH)

    assert environment[NORMALIZATION_VARIABLES["source_date_epoch"]] == str(EPOCH)
    assert environment[NORMALIZATION_VARIABLES["python_hash_seed"]] == "0"
    assert environment[NORMALIZATION_VARIABLES["timezone_utc"]] == "UTC"
    assert environment[NORMALIZATION_VARIABLES["no_color"]] == "1"
    assert dict(os.environ) == before


def test_a_subset_of_normalizations_sets_only_those_variables() -> None:
    environment = normalized_environment(EPOCH, normalizations=["source_date_epoch"])

    assert environment[NORMALIZATION_VARIABLES["source_date_epoch"]] == str(EPOCH)
    assert environment.get("PYTHONHASHSEED") == os.environ.get("PYTHONHASHSEED")


def test_the_build_command_names_the_constraints_and_the_output(tmp_path: Path) -> None:
    command = build_command("toolchains/python-build-constraints.txt", tmp_path)

    assert "toolchains/python-build-constraints.txt" in command
    assert str(tmp_path) in command
    for flag in INHERITED_BUILD_FLAGS:
        assert flag in command


def test_a_source_snapshot_is_taken_once_and_copies_match(tmp_path: Path) -> None:
    project = staged_project(tmp_path)

    digest = stage_snapshot(project, tmp_path / "snapshot")
    shutil.copytree(tmp_path / "snapshot", tmp_path / "copy")

    assert digest.startswith("sha256:")
    assert require_snapshot_copy(tmp_path / "copy", digest, "copy") == digest
    for relative in SNAPSHOT_DIRECTORIES:
        assert (tmp_path / "snapshot" / relative / "kept.txt").is_file()
        assert not (tmp_path / "snapshot" / relative / "__pycache__").exists()


def test_staging_never_modifies_the_tree_it_copies_from(tmp_path: Path) -> None:
    project = staged_project(tmp_path)
    before = tree_sha256(project)

    stage_snapshot(project, tmp_path / "snapshot")

    assert tree_sha256(project) == before


def test_the_ledger_entries_are_ordered_by_pin_identifier() -> None:
    identifiers = [entry["pin_id"] for entry in ledger()["entries"]]

    assert identifiers == sorted(identifiers)
    assert len(set(identifiers)) == len(identifiers)


def test_building_the_ledger_against_a_mirrored_root_gives_the_same_pins(
    tmp_path: Path,
) -> None:
    from fixtures import declaring_sources

    mirror = declaring_sources(tmp_path)

    mirrored = build_pin_ledger(mirror, generated_at=TIMESTAMP)

    assert mirrored["ledger_hash"] == ledger()["ledger_hash"]
