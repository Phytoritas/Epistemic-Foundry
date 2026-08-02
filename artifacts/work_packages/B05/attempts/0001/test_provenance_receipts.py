"""provenance_and_receipt_audit — every emitted byte resolves to a receipt.

The build manifest is the immutable receipt for the whole output: it names the
generator that produced it by content hash, the exact inputs it derived from,
and the exact bytes it wrote.  Everything in it is recomputed here from the
live repository rather than trusted, and the receipts must agree with each
other — the profile's input table and the manifest's must be the same table.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from b05_profile import (
    FEATURE_NAME,
    GENERATOR_RELPATH,
    INPUT_PATHS,
    MANIFEST_NAME,
    OUTPUT_DIR,
    PROFILE_NAME,
    B05BuildError,
    _hash_excluding,
    verify,
)
from test_build_determinism import ROOT, OUTPUT_NAMES


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((ROOT / OUTPUT_DIR / name).read_text(encoding="utf-8"))


def test_every_recorded_input_hash_matches_the_live_file() -> None:
    manifest = load(MANIFEST_NAME)

    assert sorted(manifest["inputs"]) == sorted(INPUT_PATHS)
    for relative, recorded in manifest["inputs"].items():
        assert recorded == sha(ROOT / relative), relative


def test_every_recorded_output_hash_matches_the_live_file() -> None:
    manifest = load(MANIFEST_NAME)

    assert sorted(manifest["outputs"]) == sorted(
        [f"{OUTPUT_DIR}/{FEATURE_NAME}", f"{OUTPUT_DIR}/{PROFILE_NAME}"]
    )
    for relative, recorded in manifest["outputs"].items():
        assert recorded == sha(ROOT / relative), relative


def test_the_generator_receipt_names_the_file_that_ran() -> None:
    generator = load(MANIFEST_NAME)["generator"]

    assert generator["path"] == GENERATOR_RELPATH
    assert generator["sha256"] == sha(ROOT / GENERATOR_RELPATH)


def test_the_manifest_hash_seals_the_receipt() -> None:
    manifest = load(MANIFEST_NAME)

    assert _hash_excluding(manifest, "manifest_hash") == manifest["manifest_hash"]


def test_the_profile_and_manifest_agree_on_the_input_table() -> None:
    assert load(PROFILE_NAME)["inputs"] == load(MANIFEST_NAME)["inputs"]


def test_no_file_in_the_output_escapes_the_receipt() -> None:
    on_disk = sorted(entry.name for entry in (ROOT / OUTPUT_DIR).iterdir())
    receipted = sorted(
        relative.rsplit("/", 1)[1] for relative in load(MANIFEST_NAME)["outputs"]
    )

    assert on_disk == sorted([*receipted, MANIFEST_NAME])


def test_the_feature_receipt_binds_the_schema_it_read() -> None:
    readiness = load(FEATURE_NAME)["canonical_manifest_readiness"]

    assert readiness["schema_sha256"] == sha(ROOT / readiness["schema"])
    assert (
        readiness["schema_sha256"] == load(MANIFEST_NAME)["inputs"][readiness["schema"]]
    )


def test_the_registry_receipt_binds_the_registry_it_counted() -> None:
    resources = load(PROFILE_NAME)["canonical_resources"]
    manifest_inputs = load(MANIFEST_NAME)["inputs"]

    assert (
        resources["registry_sha256"]
        == manifest_inputs["src/epistemic_foundry/_canonical/canonical-registry.json"]
    )


def test_a_byte_flip_anywhere_in_the_output_breaks_verification(
    tmp_path: Path,
) -> None:
    replica = tmp_path / OUTPUT_DIR
    replica.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / OUTPUT_DIR, replica)
    for name in OUTPUT_NAMES:
        shutil.copytree(replica, tmp_path / "case" / name)
        target = tmp_path / "case" / name / name
        payload = bytearray(target.read_bytes())
        payload[-2] ^= 0x01
        target.write_bytes(bytes(payload))

        with pytest.raises(B05BuildError):
            verify(ROOT, tmp_path / "case" / name)


def test_verification_of_an_untampered_replica_passes(tmp_path: Path) -> None:
    replica = tmp_path / "replica"
    shutil.copytree(ROOT / OUTPUT_DIR, replica)

    assert verify(ROOT, replica)["status"] == "PASS"
