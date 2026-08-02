"""provenance_and_receipt_audit — the family index accounts for every byte.

The index is the bundle's receipt: every canonical member and every composite
is content-addressed, the generator that produced it is named by hash, the
recorded hashes match the live files, regeneration is byte-identical, and no
file exists in the bundle that the index does not cover.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from c05_schema_bundle import (
    GENERATOR_RELPATH,
    INDEX_NAME,
    _hash_excluding,
    build_composites,
    build_index,
    members,
    render,
    verify,
)
from test_schema_and_type import BUNDLE, COMPOSITE_NAMES, ROOT, load


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_member_hash_matches_the_live_canonical_file() -> None:
    index = load(INDEX_NAME)
    recorded = {
        entry["canonical"]: entry["sha256"]
        for family in index["families"].values()
        for entry in family["members"]
    }

    assert sorted(recorded) == sorted(
        f"schemas/{name}.schema.json" for name in members()
    )
    for canonical, digest in recorded.items():
        assert digest == sha(ROOT / canonical), canonical


def test_every_composite_hash_matches_the_live_file() -> None:
    index = load(INDEX_NAME)

    assert sorted(index["composites"]) == COMPOSITE_NAMES
    for name, digest in index["composites"].items():
        assert digest == sha(BUNDLE / name), name


def test_the_generator_receipt_names_the_file_that_ran() -> None:
    generator = load(INDEX_NAME)["generator"]

    assert generator["path"] == GENERATOR_RELPATH
    assert generator["sha256"] == sha(ROOT / GENERATOR_RELPATH)


def test_the_index_hash_seals_the_receipt() -> None:
    index = load(INDEX_NAME)

    assert _hash_excluding(index, "index_hash") == index["index_hash"]


def test_regeneration_is_byte_identical() -> None:
    composites = build_composites(ROOT)

    for name, document in composites.items():
        assert (BUNDLE / name).read_bytes() == render(document), name
    assert (BUNDLE / INDEX_NAME).read_bytes() == render(build_index(ROOT, composites))


def test_no_file_in_the_bundle_escapes_the_receipt() -> None:
    on_disk = sorted(entry.name for entry in BUNDLE.iterdir())

    assert on_disk == sorted([*COMPOSITE_NAMES, INDEX_NAME])


def test_the_committed_bundle_verifies() -> None:
    report = verify(ROOT)

    assert report["status"] == "PASS"
    assert report["member_count"] == 42
    assert report["composites_verified"] == 5
    assert report["mutable_search_space"] == 4


def test_the_index_is_canonical_json_on_disk() -> None:
    raw = (BUNDLE / INDEX_NAME).read_text(encoding="utf-8")

    assert raw.endswith("\n")
    assert json.loads(raw) == json.loads(
        json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    )
