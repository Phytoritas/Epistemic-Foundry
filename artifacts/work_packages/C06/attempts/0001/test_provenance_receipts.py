"""provenance_and_receipt_audit — the index accounts for every input and byte.

The integration index is the gate's receipt: it names the generator that
produced it by content hash, the four independent sources it reconciled, and
the exact bytes it wrote.  Every one of those is recomputed here from the live
repository, and the parity record's per-member hashes are checked against both
the canonical files and the generated manifests, so nothing in the receipt is
taken on trust.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from c06_integration_gate import (
    BINDING_NAME,
    C05_INDEX_PATH,
    GENERATOR_RELPATH,
    INDEX_NAME,
    OUTPUT_DIR,
    PARITY_NAME,
    PROJECTION_MANIFESTS,
    _hash_excluding,
    audit_fixtures,
    build_binding,
    build_index,
    reconcile_projections,
    render,
    verify,
)
from test_schema_and_type import BUNDLE, ROOT, load


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_generator_receipt_names_the_file_that_ran() -> None:
    generator = load(INDEX_NAME)["generator"]

    assert generator["path"] == GENERATOR_RELPATH
    assert generator["sha256"] == sha(ROOT / GENERATOR_RELPATH)


def test_every_recorded_source_hash_matches_the_live_file() -> None:
    sources = load(INDEX_NAME)["sources"]

    assert sorted(sources) == sorted([C05_INDEX_PATH, *PROJECTION_MANIFESTS.values()])
    for relative, recorded in sources.items():
        assert recorded == sha(ROOT / relative), relative


def test_every_recorded_output_hash_matches_the_live_file() -> None:
    outputs = load(INDEX_NAME)["outputs"]

    assert sorted(outputs) == sorted(
        [f"{OUTPUT_DIR}/{BINDING_NAME}", f"{OUTPUT_DIR}/{PARITY_NAME}"]
    )
    for relative, recorded in outputs.items():
        assert recorded == sha(ROOT / relative), relative


def test_the_index_hash_seals_the_receipt() -> None:
    index = load(INDEX_NAME)

    assert _hash_excluding(index, "index_hash") == index["index_hash"]


def test_the_parity_hash_seals_the_reconciliation() -> None:
    parity = load(PARITY_NAME)

    assert _hash_excluding(parity, "parity_hash") == parity["parity_hash"]


def test_every_member_hash_matches_both_the_schema_and_the_manifests() -> None:
    parity = load(PARITY_NAME)
    manifests = {
        language: {
            row["schema_file"]: row
            for row in json.loads((ROOT / relative).read_text(encoding="utf-8"))[
                "contracts"
            ]
        }
        for language, relative in PROJECTION_MANIFESTS.items()
    }

    for name, entry in parity["members"].items():
        live = sha(ROOT / entry["canonical"])
        assert entry["canonical_sha256"] == live, name
        assert entry["example_sha256"] == sha(ROOT / entry["example"]), name
        for language, rows in manifests.items():
            row = rows[entry["canonical"]]
            assert row["source_sha256"] == live, (name, language)
            assert row["example_sha256"] == entry["example_sha256"], (name, language)


def test_the_projection_receipts_name_the_manifests_they_read() -> None:
    projections = load(INDEX_NAME)["projections"]

    for language, entry in projections.items():
        assert entry["manifest"] == PROJECTION_MANIFESTS[language]
        assert entry["manifest_sha256"] == sha(ROOT / entry["manifest"])


def test_the_compatibility_receipt_binds_the_binding_it_emitted() -> None:
    compatibility = load(INDEX_NAME)["compatibility"]

    assert compatibility["binding"] == f"{OUTPUT_DIR}/{BINDING_NAME}"
    assert compatibility["binding_sha256"] == sha(BUNDLE / BINDING_NAME)


def test_regeneration_is_byte_identical() -> None:
    parity = reconcile_projections(ROOT)
    binding = build_binding(ROOT)
    fixtures = audit_fixtures(ROOT)

    assert (BUNDLE / BINDING_NAME).read_bytes() == render(binding)
    assert (BUNDLE / PARITY_NAME).read_bytes() == render(parity)
    assert (BUNDLE / INDEX_NAME).read_bytes() == render(
        build_index(ROOT, parity, fixtures, binding)
    )


def test_no_file_in_the_bundle_escapes_the_receipt() -> None:
    on_disk = sorted(path.name for path in BUNDLE.iterdir())
    receipted = sorted(
        relative.rsplit("/", 1)[1] for relative in load(INDEX_NAME)["outputs"]
    )

    assert on_disk == sorted([*receipted, INDEX_NAME])


def test_the_committed_bundle_verifies() -> None:
    report = verify(ROOT)

    assert report["status"] == "PASS"
    assert report["sources_verified"] == 4
