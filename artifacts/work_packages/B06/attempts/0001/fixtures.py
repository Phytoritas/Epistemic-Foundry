"""Fixtures for the B06 build-gate suites.

Two kinds of fixture live here.  Staged *artifact trees* stand in for a build
output directory: they are real zip and gzip-tar archives written
deterministically, so the comparator is exercised against the archive formats
it will actually meet rather than against a mock.  Staged *declaring sources*
mirror only the files the pin ledger reads, so a negative test can remove or
corrupt exactly one of them without touching the repository.

The timestamp is derived from the declared build epoch rather than written as
a literal, for the same reason the gate derives it: a fixture with its own
clock would make its own records irreproducible.
"""

from __future__ import annotations

import gzip
import io
import json
import shutil
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from b06_gate import (
    BACKEND_SCHEMA_PATH,
    POSTGRES_PIN_PATH,
    TOOLCHAIN_LOCK_PATH,
    build_pin_ledger,
    epoch_timestamp,
    read_toolchain_lock,
)

ROOT = Path(__file__).resolve().parents[5]
TOOLCHAIN = read_toolchain_lock(ROOT)
EPOCH = TOOLCHAIN["source_date_epoch"]
TIMESTAMP = epoch_timestamp(EPOCH)

WHEEL_NAME = "b06_fixture-1.0.0-py3-none-any.whl"
SDIST_NAME = "b06_fixture-1.0.0.tar.gz"

#: The member set both fixture distributions carry by default.
DEFAULT_MEMBERS: dict[str, bytes] = {
    "b06_fixture/__init__.py": b"VERSION = '1.0.0'\n",
    "b06_fixture-1.0.0.dist-info/METADATA": b"Name: b06-fixture\n",
    "b06_fixture-1.0.0.dist-info/RECORD": b"b06_fixture/__init__.py,,\n",
}


def write_wheel(path: Path, members: Mapping[str, bytes]) -> Path:
    """A zip whose bytes depend only on the member names and contents."""

    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            bundle.writestr(info, members[name])
    path.write_bytes(raw.getvalue())
    return path


def write_sdist(path: Path, members: Mapping[str, bytes]) -> Path:
    """A gzip tar whose bytes depend only on the member names and contents."""

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as bundle:
        for name in sorted(members):
            payload = members[name]
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = EPOCH
            info.mode = 0o644
            bundle.addfile(info, io.BytesIO(payload))
    path.write_bytes(gzip.compress(raw.getvalue(), compresslevel=9, mtime=0))
    return path


def build_output(
    base: Path, name: str, members: Mapping[str, bytes] | None = None
) -> Path:
    """One staged build output directory holding a wheel and an sdist."""

    target = base / name
    target.mkdir(parents=True)
    payload = dict(DEFAULT_MEMBERS if members is None else members)
    write_wheel(target / WHEEL_NAME, payload)
    write_sdist(target / SDIST_NAME, payload)
    return target


def identical_outputs(base: Path) -> tuple[Path, Path]:
    """Two staged trees that a reproducible build would have produced."""

    return build_output(base, "output-a"), build_output(base, "output-b")


#: The files the pin ledger reads, relative to the repository root.
LEDGER_SOURCES: tuple[str, ...] = (
    TOOLCHAIN_LOCK_PATH,
    TOOLCHAIN["backend"]["constraints"],
    POSTGRES_PIN_PATH,
    BACKEND_SCHEMA_PATH,
    *TOOLCHAIN["lockfiles"].values(),
)


def declaring_sources(base: Path) -> Path:
    """Mirror only the files the pin ledger reads, so one can be broken."""

    mirror = base / "mirror"
    for relative in LEDGER_SOURCES:
        target = mirror / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return mirror


def rewrite_json(path: Path, mutate: Any) -> None:
    """Replace a mirrored JSON document with the mutation a test needs."""

    document = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(mutate(document), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )


def ledger(base: Path | None = None) -> dict[str, Any]:
    """A pin ledger built from the repository, or from a mirrored root."""

    return build_pin_ledger(ROOT if base is None else base, generated_at=TIMESTAMP)


def tampered(document: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    """A copy of a record with fields replaced and its hash left stale."""

    payload = json.loads(json.dumps(document, ensure_ascii=False))
    payload.update(overrides)
    return payload


def staged_project(base: Path) -> Path:
    """A miniature tree carrying every name the snapshot staging requires."""

    from b06_gate import SNAPSHOT_DIRECTORIES, SNAPSHOT_FILES

    project = base / "project"
    project.mkdir(parents=True)
    for relative in SNAPSHOT_FILES:
        (project / relative).write_text(f"# {relative}\n", encoding="utf-8")
    for relative in SNAPSHOT_DIRECTORIES:
        directory = project / relative
        directory.mkdir(parents=True)
        (directory / "kept.txt").write_text(f"{relative}\n", encoding="utf-8")
        cache = directory / "__pycache__"
        cache.mkdir()
        (cache / "dropped.pyc").write_bytes(b"\x00")
    return project
