"""unit_and_contract_tests — the build output is a pure function of its inputs.

Determinism is the contract: emitting twice yields byte-identical files, the
committed output equals what the tracked inputs produce right now, and a
crashed or partially deleted output directory is repaired by re-emitting —
byte-identical again — rather than by trusting whatever survived.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from b05_profile import (
    FEATURE_NAME,
    INPUT_PATHS,
    MANIFEST_NAME,
    OUTPUT_DIR,
    PROFILE_NAME,
    B05BuildError,
    build_documents,
    emit,
    render,
    verify,
)

ROOT = Path(__file__).resolve().parents[5]
OUTPUT_NAMES = (FEATURE_NAME, MANIFEST_NAME, PROFILE_NAME)


def mirror(tmp_path: Path) -> Path:
    """Copy exactly the declared inputs into an isolated root."""

    for relative in INPUT_PATHS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def output_bytes(base: Path) -> dict[str, bytes]:
    return {name: (base / OUTPUT_DIR / name).read_bytes() for name in OUTPUT_NAMES}


def test_two_emits_into_separate_directories_are_byte_identical(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path / "repo")
    emit(base, base / "first")
    emit(base, base / "second")

    for name in OUTPUT_NAMES:
        assert (base / "first" / name).read_bytes() == (
            base / "second" / name
        ).read_bytes(), name


def test_re_emitting_in_place_changes_nothing(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)
    before = output_bytes(base)
    emit(base)

    assert output_bytes(base) == before
    assert verify(base)["status"] == "PASS"


def test_the_committed_output_is_what_the_tracked_inputs_produce() -> None:
    documents = build_documents(ROOT)

    assert (ROOT / OUTPUT_DIR / PROFILE_NAME).read_bytes() == render(
        documents["profile"]
    )
    assert (ROOT / OUTPUT_DIR / FEATURE_NAME).read_bytes() == render(
        documents["feature"]
    )


def test_the_committed_output_verifies() -> None:
    report = verify(ROOT)

    assert report["status"] == "PASS"
    assert report["inputs_verified"] == len(INPUT_PATHS)
    assert report["outputs_verified"] == len(OUTPUT_NAMES)


def test_a_deleted_output_is_refused_then_repaired_byte_identically(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)
    emit(base)
    before = output_bytes(base)
    (base / OUTPUT_DIR / PROFILE_NAME).unlink()

    with pytest.raises(B05BuildError) as caught:
        verify(base)
    assert caught.value.code == "OUTPUT_MISSING"

    emit(base)
    assert output_bytes(base) == before
    assert verify(base)["status"] == "PASS"


def test_a_corrupted_output_is_refused_then_repaired_byte_identically(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)
    emit(base)
    before = output_bytes(base)
    target = base / OUTPUT_DIR / PROFILE_NAME
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(B05BuildError) as caught:
        verify(base)
    assert caught.value.code == "OUTPUT_TAMPERED"

    emit(base)
    assert output_bytes(base) == before


def test_a_crash_before_the_manifest_is_not_a_valid_build(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)
    (base / OUTPUT_DIR / MANIFEST_NAME).unlink()

    with pytest.raises(B05BuildError) as caught:
        verify(base)
    assert caught.value.code == "OUTPUT_MISSING"

    emit(base)
    assert verify(base)["status"] == "PASS"


def test_the_documents_derive_only_from_the_declared_inputs(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    assert build_documents(base) == build_documents(ROOT)


def test_the_profile_records_every_external_package_in_the_lock() -> None:
    profile = build_documents(ROOT)["profile"]
    lock_names = {entry["name"] for entry in profile["locked_packages"]}

    assert len(profile["locked_packages"]) == 20
    assert "epistemic-foundry" not in lock_names
    for dependency in profile["direct_dependencies"]:
        assert dependency["name"] in lock_names


def test_the_emit_summary_names_every_output(tmp_path: Path) -> None:
    summary = emit(mirror(tmp_path))

    assert summary["status"] == "PASS"
    assert summary["outputs"] == sorted(f"{OUTPUT_DIR}/{name}" for name in OUTPUT_NAMES)


def test_the_committed_output_holds_exactly_the_three_receipted_files() -> None:
    names = sorted(entry.name for entry in (ROOT / OUTPUT_DIR).iterdir())

    assert names == sorted(OUTPUT_NAMES)
    assert (
        json.loads((ROOT / OUTPUT_DIR / MANIFEST_NAME).read_text(encoding="utf-8"))[
            "reproducible"
        ]
        is True
    )
