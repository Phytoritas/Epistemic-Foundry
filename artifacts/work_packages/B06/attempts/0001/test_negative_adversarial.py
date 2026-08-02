"""negative_and_adversarial_tests — every way the gate is asked to lie, refused.

Two builds that disagree, a build that never happened, an archive that cannot
be opened, an input snapshot that changed between passes, a pin without a
digest, a pin that claims to be executable while its own contract fields are
still open, a ledger edited after it was hashed, and a normalization nobody
declared.  Each input is wrong in exactly one way and is refused by its own
code, and the refusal context is asserted to name the offending thing rather
than only the class of problem.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from b06_gate import (
    BACKEND_SCHEMA_PATH,
    POSTGRES_PIN_PATH,
    TOOLCHAIN_LOCK_PATH,
    BuildGateError,
    archive_members,
    backend_pin_requirements,
    build_gate_manifest,
    build_pin_ledger,
    build_reproducibility_record,
    compare_build_trees,
    normalized_environment,
    read_toolchain_lock,
    require_snapshot_copy,
    run_build,
    sealed_container_pin,
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
    declaring_sources,
    identical_outputs,
    ledger,
    rewrite_json,
    staged_project,
    tampered,
)


def refused(run: Callable[[], object], code: str) -> BuildGateError:
    with pytest.raises(BuildGateError) as caught:
        run()
    assert caught.value.code == code, caught.value.code
    return caught.value


def entry_of(document: dict, pin_id: str) -> dict:
    return next(item for item in document["entries"] if item["pin_id"] == pin_id)


def resealed(document: dict) -> dict:
    from b06_gate import hash_excluding

    document["ledger_hash"] = hash_excluding(document, "ledger_hash")
    return document


# --------------------------------------------------------------------------
# The double build
# --------------------------------------------------------------------------


def test_a_changed_member_is_refused_and_the_member_is_named(tmp_path: Path) -> None:
    first, _ = identical_outputs(tmp_path)
    drifted = dict(DEFAULT_MEMBERS)
    drifted["b06_fixture/__init__.py"] = b"VERSION = '1.0.1'\n"
    second = build_output(tmp_path, "output-drifted", drifted)

    error = refused(
        lambda: compare_build_trees(first, second), "BUILD_NONDETERMINISTIC"
    )

    assert sorted(error.context["artifacts"]) == sorted([SDIST_NAME, WHEEL_NAME])
    assert error.context["differing_members"][WHEEL_NAME] == ["b06_fixture/__init__.py"]
    assert error.context["differing_members"][SDIST_NAME] == ["b06_fixture/__init__.py"]


def test_a_member_that_only_one_build_produced_is_named(tmp_path: Path) -> None:
    first, _ = identical_outputs(tmp_path)
    extra = dict(DEFAULT_MEMBERS)
    extra["b06_fixture/extra.py"] = b"# added by the second build\n"
    second = build_output(tmp_path, "output-extra", extra)

    error = refused(
        lambda: compare_build_trees(first, second), "BUILD_NONDETERMINISTIC"
    )

    assert "b06_fixture/extra.py" in error.context["differing_members"][WHEEL_NAME]


def test_a_different_distribution_set_is_refused_before_bytes(tmp_path: Path) -> None:
    first, second = identical_outputs(tmp_path)
    (second / SDIST_NAME).unlink()

    error = refused(
        lambda: compare_build_trees(first, second), "BUILD_INVENTORY_MISMATCH"
    )

    assert error.context["only_in_first"] == [SDIST_NAME]
    assert error.context["only_in_second"] == []


def test_an_output_directory_with_no_distribution_is_refused(tmp_path: Path) -> None:
    first, _ = identical_outputs(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    error = refused(lambda: compare_build_trees(first, empty), "BUILD_TREE_EMPTY")

    assert error.context["path"].endswith("empty")


def test_a_build_output_directory_that_never_existed_is_refused(
    tmp_path: Path,
) -> None:
    first, _ = identical_outputs(tmp_path)

    error = refused(
        lambda: compare_build_trees(first, tmp_path / "never-ran"), "BUILD_TREE_MISSING"
    )

    assert error.context["label"] == "build output"


def test_a_distribution_that_is_not_its_own_format_is_refused(tmp_path: Path) -> None:
    first, second = identical_outputs(tmp_path)
    (second / WHEEL_NAME).write_bytes(b"not a zip archive")

    refused(lambda: compare_build_trees(first, second), "ARCHIVE_UNREADABLE")
    refused(lambda: archive_members(second / WHEEL_NAME), "ARCHIVE_UNREADABLE")


def test_a_distribution_with_no_comparable_format_is_refused(tmp_path: Path) -> None:
    stray = tmp_path / "artifact.bin"
    stray.write_bytes(b"opaque")

    error = refused(lambda: archive_members(stray), "ARCHIVE_UNREADABLE")

    assert error.context["artifact"] == "artifact.bin"


def test_an_input_copy_that_drifted_is_refused_before_the_build(
    tmp_path: Path,
) -> None:
    project = staged_project(tmp_path)
    digest = stage_snapshot(project, tmp_path / "snapshot")
    (tmp_path / "snapshot" / "src" / "kept.txt").write_text(
        "edited\n", encoding="utf-8"
    )

    error = refused(
        lambda: require_snapshot_copy(tmp_path / "snapshot", digest, "pass-a"),
        "SOURCE_SNAPSHOT_DIVERGED",
    )

    assert error.context["copy"] == "pass-a"
    assert error.context["expected"] == digest
    assert error.context["observed"] != digest


def test_staging_over_an_existing_destination_is_refused(tmp_path: Path) -> None:
    project = staged_project(tmp_path)
    (tmp_path / "snapshot").mkdir()

    refused(lambda: stage_snapshot(project, tmp_path / "snapshot"), "INPUT_INVALID")


def test_staging_a_tree_that_lacks_a_declared_input_is_refused(
    tmp_path: Path,
) -> None:
    project = staged_project(tmp_path)
    (project / "pyproject.toml").unlink()

    error = refused(
        lambda: stage_snapshot(project, tmp_path / "snapshot"), "INPUT_INVALID"
    )

    assert error.context["input"] == "pyproject.toml"


def test_a_build_that_cannot_be_configured_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "pyproject.toml").write_text("this is not toml [\n", encoding="utf-8")

    error = refused(
        lambda: run_build(
            broken,
            tmp_path / "out",
            epoch=EPOCH,
            constraints="toolchains/python-build-constraints.txt",
        ),
        "BUILD_COMMAND_FAILED",
    )

    assert error.context["command"][:2] == ["uv", "build"]


def test_building_from_a_directory_that_does_not_exist_is_refused(
    tmp_path: Path,
) -> None:
    refused(
        lambda: run_build(
            tmp_path / "absent",
            tmp_path / "out",
            epoch=EPOCH,
            constraints="toolchains/python-build-constraints.txt",
        ),
        "BUILD_TREE_MISSING",
    )


def test_hashing_a_tree_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    refused(lambda: tree_sha256(tmp_path / "absent"), "BUILD_TREE_MISSING")


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


def test_an_undeclared_normalization_cannot_be_applied() -> None:
    error = refused(
        lambda: normalized_environment(EPOCH, normalizations=["strip_timestamps"]),
        "NORMALIZATION_UNDECLARED",
    )

    assert error.context["requested"] == ["strip_timestamps"]
    assert "source_date_epoch" in error.context["declared"]


def test_an_undeclared_normalization_cannot_be_recorded() -> None:
    refused(
        lambda: build_reproducibility_record(
            artifacts={WHEEL_NAME: {"bytes": 1, "sha256": "sha256:" + "a" * 64}},
            source_snapshot_sha256="sha256:" + "b" * 64,
            source_date_epoch=EPOCH,
            command=["uv", "build"],
            generated_at=TIMESTAMP,
            normalizations=["rewrite_record_after_the_fact"],
        ),
        "NORMALIZATION_UNDECLARED",
    )


def test_a_record_with_no_artifact_is_refused() -> None:
    refused(
        lambda: build_reproducibility_record(
            artifacts={},
            source_snapshot_sha256="sha256:" + "b" * 64,
            source_date_epoch=EPOCH,
            command=["uv", "build"],
            generated_at=TIMESTAMP,
        ),
        "BUILD_TREE_EMPTY",
    )


def test_a_record_with_a_malformed_snapshot_digest_is_refused() -> None:
    refused(
        lambda: build_reproducibility_record(
            artifacts={WHEEL_NAME: {"bytes": 1, "sha256": "sha256:" + "a" * 64}},
            source_snapshot_sha256="latest",
            source_date_epoch=EPOCH,
            command=["uv", "build"],
            generated_at=TIMESTAMP,
        ),
        "PIN_DIGEST_MALFORMED",
    )


@pytest.mark.parametrize("stamp", ["", "2026-01-01", "2026-01-01T00:00:00+09:00", None])
def test_a_record_without_a_caller_timestamp_is_refused(stamp: object) -> None:
    refused(
        lambda: build_reproducibility_record(
            artifacts={WHEEL_NAME: {"bytes": 1, "sha256": "sha256:" + "a" * 64}},
            source_snapshot_sha256="sha256:" + "b" * 64,
            source_date_epoch=EPOCH,
            command=["uv", "build"],
            generated_at=stamp,  # type: ignore[arg-type]
        ),
        "TIMESTAMP_INVALID",
    )


# --------------------------------------------------------------------------
# The pin ledger
# --------------------------------------------------------------------------


def test_an_executable_pin_without_a_digest_is_refused() -> None:
    document = ledger()
    entry_of(document, "python-lock")["digest"] = None

    error = refused(
        lambda: validate_pin_ledger(resealed(document)), "PIN_DIGEST_MISSING"
    )

    assert error.context["pin_id"] == "python-lock"


@pytest.mark.parametrize(
    "digest", ["latest", "sha256:NOTHEX", "sha1:" + "a" * 40, "sha256:" + "A" * 64]
)
def test_an_executable_pin_with_a_malformed_digest_is_refused(digest: str) -> None:
    document = ledger()
    entry_of(document, "postgres-image")["digest"] = digest

    error = refused(
        lambda: validate_pin_ledger(resealed(document)), "PIN_DIGEST_MALFORMED"
    )

    assert error.context["digest"] == digest


def test_a_backend_pin_promoted_to_executable_is_refused_as_an_overclaim() -> None:
    document = ledger()
    entry = entry_of(document, "shinka-backend")
    entry["execution_permitted"] = True
    entry["blocking_reason"] = None
    entry["digest"] = "sha256:" + "f" * 64
    document["executable_pin_count"] += 1
    document["blocked_pin_count"] -= 1

    error = refused(lambda: validate_pin_ledger(resealed(document)), "PIN_OVERCLAIM")

    assert error.context["pin_id"] == "shinka-backend"
    assert "source_revision" in error.context["unpinned_fields"]


def test_a_blocked_pin_without_a_recorded_reason_is_refused() -> None:
    document = ledger()
    entry_of(document, "shinka-backend")["blocking_reason"] = "unpinned"

    error = refused(
        lambda: validate_pin_ledger(resealed(document)), "PIN_BLOCK_UNJUSTIFIED"
    )

    assert error.context["pin_id"] == "shinka-backend"


def test_a_blocked_pin_that_names_no_open_field_is_refused() -> None:
    document = ledger()
    entry_of(document, "shinka-backend")["unpinned_fields"] = []

    refused(lambda: validate_pin_ledger(resealed(document)), "PIN_BLOCK_UNJUSTIFIED")


def test_a_pin_that_is_executable_and_blocked_at_once_is_refused() -> None:
    document = ledger()
    entry_of(document, "python-lock")["blocking_reason"] = (
        "a reason long enough to pass the justification floor"
    )

    refused(lambda: validate_pin_ledger(resealed(document)), "INPUT_INVALID")


def test_a_ledger_edited_after_it_was_hashed_is_refused() -> None:
    document = tampered(ledger(), ledger_id="v4-b06-pin-ledger-edited")

    refused(lambda: validate_pin_ledger(document), "LEDGER_HASH_MISMATCH")


def test_a_ledger_carrying_an_undeclared_field_is_refused() -> None:
    document = tampered(ledger(), waiver="approved out of band")

    error = refused(lambda: validate_pin_ledger(document), "LEDGER_FIELD_UNKNOWN")

    assert error.context["unexpected"] == ["waiver"]


def test_a_pin_entry_carrying_an_undeclared_field_is_refused() -> None:
    document = ledger()
    entry_of(document, "python-lock")["waived"] = True

    refused(lambda: validate_pin_ledger(resealed(document)), "LEDGER_FIELD_UNKNOWN")


def test_a_ledger_whose_counts_do_not_match_its_entries_is_refused() -> None:
    document = ledger()
    document["blocked_pin_count"] = 0

    error = refused(
        lambda: validate_pin_ledger(resealed(document)), "LEDGER_FIELD_UNKNOWN"
    )

    assert error.context["recorded"] == 0


def test_a_ledger_with_no_entries_is_refused() -> None:
    document = ledger()
    document["entries"] = []
    document["blocked_pin_count"] = 0
    document["executable_pin_count"] = 0

    refused(lambda: validate_pin_ledger(resealed(document)), "INPUT_INVALID")


def test_a_ledger_that_is_not_a_document_is_refused() -> None:
    refused(lambda: validate_pin_ledger([]), "INPUT_INVALID")  # type: ignore[arg-type]


def test_a_ledger_without_a_caller_timestamp_is_refused() -> None:
    refused(lambda: build_pin_ledger(ROOT, generated_at="today"), "TIMESTAMP_INVALID")


# --------------------------------------------------------------------------
# The declaring sources
# --------------------------------------------------------------------------


def test_a_lockfile_the_toolchain_lock_names_but_does_not_ship_is_refused(
    tmp_path: Path,
) -> None:
    mirror = declaring_sources(tmp_path)
    (mirror / read_toolchain_lock(mirror)["lockfiles"]["python"]).unlink()

    error = refused(
        lambda: build_pin_ledger(mirror, generated_at=TIMESTAMP),
        "PIN_SOURCE_UNREADABLE",
    )

    assert error.context["ecosystem"] == "python"


def test_a_build_backend_without_its_constraints_is_refused(tmp_path: Path) -> None:
    mirror = declaring_sources(tmp_path)
    (mirror / read_toolchain_lock(mirror)["backend"]["constraints"]).unlink()

    refused(
        lambda: build_pin_ledger(mirror, generated_at=TIMESTAMP),
        "PIN_SOURCE_UNREADABLE",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: {**document, "source_date_epoch": "1767225600"},
        lambda document: {
            key: value for key, value in document.items() if key != "lockfiles"
        },
        lambda document: {**document, "python_build_backend": {"name": "setuptools"}},
    ],
)
def test_a_toolchain_lock_that_cannot_pin_the_build_is_refused(
    tmp_path: Path, mutation: Callable[[dict], dict]
) -> None:
    mirror = declaring_sources(tmp_path)
    rewrite_json(mirror / TOOLCHAIN_LOCK_PATH, mutation)

    refused(lambda: read_toolchain_lock(mirror), "TOOLCHAIN_LOCK_UNUSABLE")


def test_a_toolchain_lock_that_is_absent_is_refused(tmp_path: Path) -> None:
    refused(lambda: read_toolchain_lock(tmp_path), "TOOLCHAIN_LOCK_UNUSABLE")


def test_a_sealed_harness_without_a_digest_pinned_image_is_refused(
    tmp_path: Path,
) -> None:
    mirror = declaring_sources(tmp_path)
    harness = mirror / POSTGRES_PIN_PATH
    harness.write_text(
        harness.read_text(encoding="utf-8").replace("@sha256:", ":latest#"),
        encoding="utf-8",
    )

    error = refused(lambda: sealed_container_pin(mirror), "PIN_DIGEST_MISSING")

    assert error.context["path"] == POSTGRES_PIN_PATH


def test_a_backend_schema_that_requires_nothing_is_refused(tmp_path: Path) -> None:
    mirror = declaring_sources(tmp_path)
    rewrite_json(
        mirror / BACKEND_SCHEMA_PATH,
        lambda document: {**document, "required": []},
    )

    refused(lambda: backend_pin_requirements(mirror), "PIN_SOURCE_UNREADABLE")


def test_an_unreadable_declaring_source_is_refused(tmp_path: Path) -> None:
    refused(lambda: backend_pin_requirements(tmp_path), "PIN_SOURCE_UNREADABLE")
    refused(lambda: sealed_container_pin(tmp_path), "PIN_SOURCE_UNREADABLE")


def test_a_gate_manifest_that_lists_no_output_is_refused() -> None:
    document = ledger()

    refused(
        lambda: build_gate_manifest(
            outputs={},
            ledger=document,
            reproducibility=build_reproducibility_record(
                artifacts={WHEEL_NAME: {"bytes": 1, "sha256": "sha256:" + "a" * 64}},
                source_snapshot_sha256="sha256:" + "b" * 64,
                source_date_epoch=EPOCH,
                command=["uv", "build"],
                generated_at=TIMESTAMP,
            ),
            generated_at=TIMESTAMP,
        ),
        "INPUT_INVALID",
    )


def test_the_refusals_carry_a_serialisable_context() -> None:
    document = tampered(ledger(), waiver="approved out of band")

    error = refused(lambda: validate_pin_ledger(document), "LEDGER_FIELD_UNKNOWN")

    assert json.loads(json.dumps(error.context)) == error.context
    assert str(error)
