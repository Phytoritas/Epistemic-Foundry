"""Z02 zip_integrity_test: deterministic bundle clean-extracts byte-identically.

This required-check module proves, through :mod:`z02_release_engine`, that the
release bundle is a byte-deterministic ZIP, that it clean-extracts to the payload
bytes exactly, and that path-unsafe or content-tampered archives are refused
before or during extraction.  Extraction is performed into pytest's ``tmp_path``;
nothing is written into the repository tree.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import z02_release_engine as engine


def test_bundle_is_byte_deterministic() -> None:
    assert engine.build_bundle_bytes() == engine.build_bundle_bytes()
    assert engine.bundle_is_deterministic() is True


def test_bundle_hash_is_stable() -> None:
    assert engine.bundle_hash() == engine.bundle_hash()
    assert engine.bundle_hash().startswith("sha256:")


def test_bundle_member_count_matches_payload() -> None:
    with zipfile.ZipFile(io.BytesIO(engine.build_bundle_bytes())) as archive:
        names = archive.namelist()
    assert sorted(names) == sorted(e["path"] for e in engine.payload_inventory())


def test_bundle_clean_extracts_byte_identically(tmp_path: Path) -> None:
    report = engine.verify_clean_extraction(engine.build_bundle_bytes(), tmp_path)
    assert report["clean_extract"] is True
    assert report["refusals"] == []
    assert report["mismatched"] == []
    assert report["surplus"] == []
    assert report["member_count"] > 0


def test_bundle_members_are_all_path_safe() -> None:
    with zipfile.ZipFile(io.BytesIO(engine.build_bundle_bytes())) as archive:
        for name in archive.namelist():
            assert engine.is_safe_member(name) is True


def _archive_with_member(name: str, data: bytes = b"payload") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo(filename=name, date_time=engine.FIXED_ZIP_DATE)
        archive.writestr(info, data)
    return buffer.getvalue()


def test_absolute_member_is_refused_before_extraction(tmp_path: Path) -> None:
    report = engine.verify_clean_extraction(
        _archive_with_member("/etc/passwd"), tmp_path
    )
    assert report["clean_extract"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_BUNDLE_PATH_UNSAFE" in codes
    # Nothing was written outside the destination during the refusal.
    assert list(tmp_path.rglob("*")) == []


def test_parent_traversal_member_is_refused_before_extraction(tmp_path: Path) -> None:
    report = engine.verify_clean_extraction(
        _archive_with_member("../escape.txt"), tmp_path
    )
    assert report["clean_extract"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_BUNDLE_PATH_UNSAFE" in codes
    assert list(tmp_path.rglob("*")) == []


def test_content_tampered_bundle_is_refused(tmp_path: Path) -> None:
    inventory = engine.payload_inventory()
    victim = inventory[0]["path"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in inventory:
            info = zipfile.ZipInfo(
                filename=entry["path"], date_time=engine.FIXED_ZIP_DATE
            )
            data = (
                b"TAMPERED"
                if entry["path"] == victim
                else (engine.PLUGIN_ROOT / entry["path"]).read_bytes()
            )
            archive.writestr(info, data)
    report = engine.verify_clean_extraction(buffer.getvalue(), tmp_path)
    assert report["clean_extract"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_BUNDLE_EXTRACT_MISMATCH" in codes
    assert victim in report["mismatched"]


def test_surplus_member_is_refused(tmp_path: Path) -> None:
    inventory = engine.payload_inventory()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in inventory:
            info = zipfile.ZipInfo(
                filename=entry["path"], date_time=engine.FIXED_ZIP_DATE
            )
            archive.writestr(info, (engine.PLUGIN_ROOT / entry["path"]).read_bytes())
        extra = zipfile.ZipInfo(filename="surplus.txt", date_time=engine.FIXED_ZIP_DATE)
        archive.writestr(extra, b"not part of the payload")
    report = engine.verify_clean_extraction(buffer.getvalue(), tmp_path)
    assert report["clean_extract"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_BUNDLE_EXTRACT_MISMATCH" in codes
    assert "surplus.txt" in report["surplus"]
