#!/usr/bin/env python3
"""B06 reproducible build and backend-pin integration gate.

Two questions decide this gate.  Does building the distribution twice from the
same source produce the same bytes?  And is every external thing an execution
would reach pinned by digest rather than by a name that can move underneath it?

The reproducibility half builds the real wheel and sdist twice.  It does not
invent a normalization: the build epoch comes from
``toolchains/toolchain-lock.json`` — the same value ``.github/workflows/ci.yml``
exports and the same value ``scripts/build/canonical_registry/materialize.py``
refuses to build against a mismatch of — and the remaining environment
normalization is the set ``scripts/build/double_build.py`` already applies.
Nothing is rewritten after the fact; no member is excluded from the comparison
because it was inconvenient.  When two builds disagree the gate refuses with
``BUILD_NONDETERMINISTIC`` and names the archive members that differ, so the
next reader debugs a file rather than a hash.

One deviation from B02's script is deliberate and recorded here rather than
hidden: ``scripts/build/double_build.py`` passes ``--wheel``, so the sdist is
never compared.  This gate omits that flag and compares both distributions.
The second deviation is forced: that script stages a source copy that no longer
builds (its ``SOURCE_DIRECTORIES`` omit ``scripts``, ``schemas`` and ``openapi``
which ``pyproject.toml`` and the canonical build hooks now require, and its
ignore filter drops ``scripts/build`` by name), so the staging list here is
derived from what the build hooks declare.  B02 owns that script; this package
only reports it.

The staging is taken **once** and copied, not taken twice.  Two independent
snapshots of a working tree that other work is editing differ for reasons that
have nothing to do with the build, and a gate that reports those as build
nondeterminism is lying about which thing is broken.  The snapshot hash is
recorded so the reader knows exactly which tree the answer is about.

The pin half collects every external execution pin the sealed packages rely on
— the Python and Node lock digests named by the toolchain lock, the pinned build
backend, the PostgreSQL image digest the sealed D05 harness carries, and the
ShinkaEvolve backend manifest's own required pin fields — and refuses a floating
pin.  A pin without a digest may exist, but only as a *blocked* pin carrying the
reason it cannot be honoured; it may never be marked executable.  The ShinkaEvolve
backend is exactly that case: the canonical schema requires an exact revision and
a manifest digest, neither of which any sealed artifact supplies, so the ledger
records it as unpinned and not executable.  This gate grants no backend any
evaluator, holdout or promotion authority; it only says whether a pin is exact.

Every record re-derives its own hash from the fields it publishes, minus the
hash field.  Nothing here reads a clock or a random source: timestamps arrive
from the caller, and the CLI derives its timestamp from the declared build epoch
so a rerun writes byte-identical evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

#: Every way this gate refuses, and why that refusal exists.
FINDING_CODES: Final[dict[str, str]] = {
    "ARCHIVE_UNREADABLE": (
        "a built distribution could not be opened as the archive its suffix "
        "claims, so its members cannot be compared member by member"
    ),
    "BUILD_COMMAND_FAILED": (
        "the build command exited non-zero, and a gate that compared the "
        "artifacts of a failed build would be comparing leftovers"
    ),
    "BUILD_INVENTORY_MISMATCH": (
        "the two builds did not produce the same set of distribution files, so "
        "there is no artifact pairing to compare bytes across"
    ),
    "BUILD_NONDETERMINISTIC": (
        "two builds of one source snapshot produced different bytes after the "
        "declared normalization, so the build is not reproducible"
    ),
    "BUILD_TREE_EMPTY": (
        "a build output directory holds no distribution file, so the build "
        "either produced nothing or wrote it somewhere unrecorded"
    ),
    "BUILD_TREE_MISSING": (
        "a build output directory named for comparison does not exist, so the "
        "comparison would silently pass over a build that never ran"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a verdict derived from something it never validated"
    ),
    "LEDGER_FIELD_UNKNOWN": (
        "the pin ledger carries a field this gate does not publish, so a hash "
        "check would cover content whose meaning is undeclared"
    ),
    "LEDGER_HASH_MISMATCH": (
        "the pin ledger does not re-derive its own recorded hash, so the "
        "record on disk is not the record that was sealed"
    ),
    "NORMALIZATION_UNDECLARED": (
        "a normalization was requested that this gate does not declare, and an "
        "undeclared normalization can hide the difference it normalizes away"
    ),
    "PIN_BLOCK_UNJUSTIFIED": (
        "a pin was marked not executable without a recorded blocking reason, "
        "so nothing states what would have to change to honour it"
    ),
    "PIN_DIGEST_MALFORMED": (
        "a pin digest is not a lowercase sha256 digest, so it cannot be "
        "compared against what an execution would actually fetch"
    ),
    "PIN_DIGEST_MISSING": (
        "an executable pin carries no digest, which is a floating reference "
        "whose contents can change underneath every later replay"
    ),
    "PIN_OVERCLAIM": (
        "a pin claims to be executable while the fields its own contract "
        "requires are still unpinned, which asserts more than the evidence"
    ),
    "PIN_SOURCE_UNREADABLE": (
        "a declaring source this ledger must read is missing or unparseable, "
        "so the pin it would carry cannot be grounded in a sealed artifact"
    ),
    "SOURCE_SNAPSHOT_DIVERGED": (
        "the two build inputs are not the same bytes, so any output difference "
        "would be attributed to the build rather than to the input"
    ),
    "TIMESTAMP_INVALID": (
        "a record timestamp is absent or not a UTC RFC 3339 instant, and this "
        "gate takes timestamps from its caller rather than from a clock"
    ),
    "TOOLCHAIN_LOCK_UNUSABLE": (
        "toolchains/toolchain-lock.json does not declare the build epoch, "
        "lockfiles and backend pin this gate is required to read from it"
    ),
}

#: The declaring source for the build epoch, the lockfile names and the pinned
#: Python build backend.  This gate restates none of those values.
TOOLCHAIN_LOCK_PATH: Final = "toolchains/toolchain-lock.json"
#: B02's double-build script: the declaring source for the build command flags
#: and the environment normalization this gate inherits.
CANONICAL_DOUBLE_BUILD_PATH: Final = "scripts/build/double_build.py"
#: B04's build hooks: the declaring source for the canonical inputs a build
#: reads, which is what the staging list below must cover.
BUILD_HOOKS_PATH: Final = "scripts/build/canonical_registry/build_hooks.py"
#: The sealed D05 harness carries the PostgreSQL image digest D04 qualified.
POSTGRES_PIN_PATH: Final = "artifacts/work_packages/D05/attempts/0001/pg_harness.py"
#: The canonical contract that says what pinning the optional backend requires.
BACKEND_SCHEMA_PATH: Final = "schemas/shinka-backend-manifest.schema.json"

OUTPUT_DIR: Final = "build/v4_b06"
LEDGER_NAME: Final = "pin-ledger.json"
REPRODUCIBILITY_NAME: Final = "reproducible-build.json"
MANIFEST_NAME: Final = "gate-manifest.json"
GENERATOR_RELPATH: Final = "artifacts/work_packages/B06/attempts/0001/b06_gate.py"

#: Files and directories the staged build snapshot must carry.  The build hooks
#: declare schemas, the OpenAPI document, the toolchain files and the canonical
#: registry package; ``pyproject.toml`` declares ``src`` and the ``scripts``
#: package that supplies its cmdclass.  ``README.md`` is included because the
#: default sdist file list picks it up.
SNAPSHOT_FILES: Final = ("README.md", "pyproject.toml", "uv.lock")
SNAPSHOT_DIRECTORIES: Final = ("openapi", "schemas", "scripts", "src", "toolchains")
#: Generated or environment-local names a source snapshot must not carry.
SNAPSHOT_EXCLUDED_NAMES: Final = frozenset(
    {".pytest_cache", ".venv", "__pycache__", "node_modules"}
)
SNAPSHOT_EXCLUDED_SUFFIXES: Final = (".egg-info", ".pyc", ".pyo")

#: The only normalizations this gate applies, and what each one is for.  A
#: build difference that survives these is reported, never normalized away.
DECLARED_NORMALIZATIONS: Final[dict[str, str]] = {
    "no_color": "NO_COLOR=1 keeps tool output free of terminal-dependent escapes",
    "python_hash_seed": "PYTHONHASHSEED=0 fixes the interpreter's string hash order",
    "source_date_epoch": (
        "SOURCE_DATE_EPOCH is the epoch toolchains/toolchain-lock.json declares"
    ),
    "timezone_utc": "TZ=UTC keeps any local-time stamp off the built artifacts",
}
#: Environment variables each declared normalization sets.
NORMALIZATION_VARIABLES: Final[dict[str, str]] = {
    "no_color": "NO_COLOR",
    "python_hash_seed": "PYTHONHASHSEED",
    "source_date_epoch": "SOURCE_DATE_EPOCH",
    "timezone_utc": "TZ",
}
#: Build command flags inherited from B02's script.  ``--wheel`` is deliberately
#: not inherited: this gate compares the sdist as well.
INHERITED_BUILD_FLAGS: Final = (
    "--build-constraints",
    "--require-hashes",
    "--no-python-downloads",
    "--no-build-logs",
)
#: Suffixes that identify a built distribution in an output directory.
DISTRIBUTION_SUFFIXES: Final = (".tar.gz", ".whl")
#: B02's placeholder for the build output directory.  A receipt that recorded
#: the absolute path would carry where this machine built, not what was built.
BUILD_OUTPUT_PLACEHOLDER: Final = "<BUILD_OUTPUT>"

_DIGEST_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
#: A digest-pinned image reference, whether the declaring source writes it on
#: one line or splits it across two adjacent string literals.
_IMAGE_PIN_PATTERN: Final = re.compile(
    r'([A-Za-z0-9._/-]+)@sha256:(?:"\s*")?([0-9a-f]{64})'
)
_TIMESTAMP_PATTERN: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_LEDGER_FIELDS: Final = frozenset(
    {
        "entries",
        "executable_pin_count",
        "generated_at",
        "generator",
        "gate_id",
        "ledger_hash",
        "ledger_id",
        "blocked_pin_count",
    }
)
_ENTRY_FIELDS: Final = frozenset(
    {
        "blocking_reason",
        "digest",
        "execution_permitted",
        "kind",
        "pin_id",
        "required_pin_fields",
        "source_path",
        "source_sha256",
        "subject",
        "unpinned_fields",
    }
)
_REPRODUCIBILITY_FIELDS: Final = frozenset(
    {
        "artifacts",
        "bit_identical",
        "build_command",
        "gate_id",
        "generated_at",
        "generator",
        "normalizations",
        "record_hash",
        "record_id",
        "source_date_epoch",
        "source_snapshot_sha256",
    }
)


class BuildGateError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise BuildGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise BuildGateError(code, message, context)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    """The record's hash over exactly the fields it publishes, minus ``field``."""

    return _digest({key: value for key, value in payload.items() if key != field})


def render(document: Mapping[str, Any]) -> bytes:
    """The exact bytes a document is written as; byte-identical on re-emit."""

    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _require_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not _TIMESTAMP_PATTERN.match(value):
        _fail(
            "TIMESTAMP_INVALID",
            f"{label} must be a UTC RFC 3339 instant such as 2026-01-01T00:00:00Z",
            {"label": label, "value": value},
        )
    return value  # type: ignore[return-value]


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        _fail(
            "BUILD_TREE_MISSING",
            f"{label} is not a directory",
            {"label": label, "path": path.as_posix()},
        )
    return path


# --------------------------------------------------------------------------
# Declaring sources
# --------------------------------------------------------------------------


def read_toolchain_lock(root: str | Path) -> dict[str, Any]:
    """The build epoch, lockfile names and pinned backend, read not restated."""

    path = Path(root) / TOOLCHAIN_LOCK_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            "TOOLCHAIN_LOCK_UNUSABLE",
            f"{TOOLCHAIN_LOCK_PATH} could not be read: {error}",
            {"path": TOOLCHAIN_LOCK_PATH},
        )
        raise  # pragma: no cover - _fail always raises
    epoch = document.get("source_date_epoch")
    lockfiles = document.get("lockfiles")
    backend = document.get("python_build_backend")
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        _fail(
            "TOOLCHAIN_LOCK_UNUSABLE",
            "source_date_epoch must be an integer",
            {"source_date_epoch": epoch},
        )
    if not isinstance(lockfiles, Mapping) or not lockfiles:
        _fail("TOOLCHAIN_LOCK_UNUSABLE", "the toolchain lock declares no lockfiles")
    if not isinstance(backend, Mapping):
        _fail("TOOLCHAIN_LOCK_UNUSABLE", "the toolchain lock declares no backend pin")
    for field in ("name", "version", "constraints"):
        if not backend.get(field):  # type: ignore[union-attr]
            _fail(
                "TOOLCHAIN_LOCK_UNUSABLE",
                f"the backend pin declares no {field}",
                {"field": field},
            )
    return {
        "backend": {
            "constraints": str(backend["constraints"]),  # type: ignore[index]
            "name": str(backend["name"]),  # type: ignore[index]
            "version": str(backend["version"]),  # type: ignore[index]
        },
        "lockfiles": {
            str(key): str(value)
            for key, value in sorted(lockfiles.items())  # type: ignore[union-attr]
        },
        "source_date_epoch": int(epoch),  # type: ignore[arg-type]
    }


def epoch_timestamp(epoch: int) -> str:
    """The declared build epoch as a UTC instant; a conversion, not a clock."""

    if not isinstance(epoch, int) or isinstance(epoch, bool):
        _fail("INPUT_INVALID", "the build epoch must be an integer", {"epoch": epoch})
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def backend_pin_requirements(root: str | Path) -> tuple[str, ...]:
    """The fields the canonical backend manifest requires before it is pinned."""

    path = Path(root) / BACKEND_SCHEMA_PATH
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            "PIN_SOURCE_UNREADABLE",
            f"{BACKEND_SCHEMA_PATH} could not be read: {error}",
            {"path": BACKEND_SCHEMA_PATH},
        )
        raise  # pragma: no cover - _fail always raises
    required = schema.get("required")
    if not isinstance(required, list) or not required:
        _fail(
            "PIN_SOURCE_UNREADABLE",
            "the backend manifest schema declares no required fields",
            {"path": BACKEND_SCHEMA_PATH},
        )
    return tuple(sorted(str(entry) for entry in required))  # type: ignore[union-attr]


def sealed_container_pin(root: str | Path) -> dict[str, str]:
    """The container image pin the sealed D05 harness carries, read from it."""

    path = Path(root) / POSTGRES_PIN_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        _fail(
            "PIN_SOURCE_UNREADABLE",
            f"{POSTGRES_PIN_PATH} could not be read: {error}",
            {"path": POSTGRES_PIN_PATH},
        )
        raise  # pragma: no cover - _fail always raises
    match = _IMAGE_PIN_PATTERN.search(text)
    if match is None:
        _fail(
            "PIN_DIGEST_MISSING",
            "the sealed harness names no container image pinned by sha256 digest",
            {"path": POSTGRES_PIN_PATH},
        )
        raise  # pragma: no cover - _fail always raises
    return {
        "digest": f"sha256:{match.group(2)}",
        "repository": match.group(1),
        "source_path": POSTGRES_PIN_PATH,
        "source_sha256": _file_sha(path),
    }


# --------------------------------------------------------------------------
# Source snapshot and the double build
# --------------------------------------------------------------------------


def _snapshot_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in SNAPSHOT_EXCLUDED_NAMES or name.endswith(SNAPSHOT_EXCLUDED_SUFFIXES)
    }


def tree_sha256(tree: str | Path) -> str:
    """A path-and-content digest of a directory; order- and name-sensitive."""

    base = _require_directory(Path(tree), "tree")
    digest = hashlib.sha256()
    for path in sorted(
        (entry for entry in base.rglob("*") if entry.is_file()),
        key=lambda entry: entry.relative_to(base).as_posix(),
    ):
        digest.update(path.relative_to(base).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def stage_snapshot(root: str | Path, destination: str | Path) -> str:
    """Copy one build input snapshot and return its digest.

    Taken once and copied, never taken twice: a working tree that other work is
    editing yields two different snapshots for reasons the build did not cause.
    """

    base = Path(root)
    target = Path(destination)
    if target.exists():
        _fail(
            "INPUT_INVALID",
            "the snapshot destination already exists",
            {"destination": target.as_posix()},
        )
    target.mkdir(parents=True)
    for relative in SNAPSHOT_FILES:
        source = base / relative
        if not source.is_file():
            _fail(
                "INPUT_INVALID",
                f"the snapshot input {relative} is missing",
                {"input": relative},
            )
        shutil.copy2(source, target / relative)
    for relative in SNAPSHOT_DIRECTORIES:
        source = base / relative
        if not source.is_dir():
            _fail(
                "INPUT_INVALID",
                f"the snapshot input directory {relative} is missing",
                {"input": relative},
            )
        shutil.copytree(source, target / relative, ignore=_snapshot_ignore)
    return tree_sha256(target)


def normalized_environment(
    epoch: int, *, normalizations: Sequence[str] | None = None
) -> dict[str, str]:
    """The build environment, carrying exactly the declared normalizations."""

    selected = (
        tuple(DECLARED_NORMALIZATIONS)
        if normalizations is None
        else tuple(normalizations)
    )
    undeclared = sorted(set(selected) - set(DECLARED_NORMALIZATIONS))
    if undeclared:
        _fail(
            "NORMALIZATION_UNDECLARED",
            "a normalization outside the declared set was requested",
            {"declared": sorted(DECLARED_NORMALIZATIONS), "requested": undeclared},
        )
    values = {
        "no_color": "1",
        "python_hash_seed": "0",
        "source_date_epoch": str(epoch),
        "timezone_utc": "UTC",
    }
    environment = dict(os.environ)
    for name in selected:
        environment[NORMALIZATION_VARIABLES[name]] = values[name]
    return environment


def build_command(constraints: str, out_dir: str | Path) -> list[str]:
    """The build invocation, carrying every flag inherited from B02's script."""

    return [
        "uv",
        "build",
        "--build-constraints",
        constraints,
        "--require-hashes",
        "--no-python-downloads",
        "--no-build-logs",
        "--out-dir",
        str(out_dir),
        ".",
    ]


def run_build(
    source: str | Path,
    out_dir: str | Path,
    *,
    epoch: int,
    constraints: str,
    normalizations: Sequence[str] | None = None,
) -> list[str]:
    """Build the distributions once from ``source`` into ``out_dir``."""

    tree = _require_directory(Path(source), "build source")
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    command = build_command(constraints, target)
    # What gets recorded, following B02's placeholder: the absolute output path
    # is where this machine happened to build, not part of the build contract.
    recorded = build_command(constraints, BUILD_OUTPUT_PLACEHOLDER)
    executable = shutil.which(command[0])
    if executable is None:
        _fail(
            "BUILD_COMMAND_FAILED",
            f"the build tool is not on PATH: {command[0]}",
            {"tool": command[0]},
        )
    process = subprocess.run(
        [str(executable), *command[1:]],
        cwd=tree,
        env=normalized_environment(epoch, normalizations=normalizations),
        check=False,
        capture_output=True,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).decode("utf-8", "replace")
        _fail(
            "BUILD_COMMAND_FAILED",
            f"the build exited {process.returncode}",
            {"command": recorded, "detail": detail.strip()[-4000:]},
        )
    return recorded


# --------------------------------------------------------------------------
# The comparator
# --------------------------------------------------------------------------


def _distribution_paths(tree: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in tree.iterdir()
            if path.is_file() and path.name.endswith(DISTRIBUTION_SUFFIXES)
        ),
        key=lambda path: path.name,
    )


def archive_members(path: str | Path) -> dict[str, str]:
    """Every member of a built distribution mapped to its content digest.

    Directory members are carried with an empty-content digest so a tree that
    gains or loses a directory entry is still a named difference.
    """

    archive = Path(path)
    members: dict[str, str] = {}
    try:
        if archive.name.endswith(".whl"):
            with zipfile.ZipFile(archive) as bundle:
                for info in bundle.infolist():
                    members[info.filename] = (
                        "sha256:"
                        + hashlib.sha256(bundle.read(info.filename)).hexdigest()
                    )
        elif archive.name.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as bundle:
                for member in bundle.getmembers():
                    handle = bundle.extractfile(member) if member.isfile() else None
                    payload = handle.read() if handle is not None else b""
                    members[member.name] = (
                        "sha256:" + hashlib.sha256(payload).hexdigest()
                    )
        else:
            _fail(
                "ARCHIVE_UNREADABLE",
                "the distribution has no comparable archive format",
                {"artifact": archive.name},
            )
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        _fail(
            "ARCHIVE_UNREADABLE",
            f"{archive.name} could not be opened: {error}",
            {"artifact": archive.name},
        )
    return members


def inventory(tree: str | Path) -> dict[str, dict[str, Any]]:
    """The distributions a build produced, by name, with size and digest."""

    base = _require_directory(Path(tree), "build output")
    paths = _distribution_paths(base)
    if not paths:
        _fail(
            "BUILD_TREE_EMPTY",
            "the build output holds no distribution file",
            {"path": base.as_posix()},
        )
    return {
        path.name: {"bytes": path.stat().st_size, "sha256": _file_sha(path)}
        for path in paths
    }


def _differing_members(first: Path, second: Path) -> list[str]:
    left = archive_members(first)
    right = archive_members(second)
    names = sorted(set(left) | set(right))
    return [name for name in names if left.get(name) != right.get(name)]


def compare_build_trees(
    first: str | Path, second: str | Path
) -> dict[str, dict[str, Any]]:
    """Refuse unless both builds produced the same distributions byte for byte.

    Neither directory is modified.  A digest difference is expanded into the
    archive members that actually differ, so the refusal names files.
    """

    left_tree = Path(first)
    right_tree = Path(second)
    left = inventory(left_tree)
    right = inventory(right_tree)
    if set(left) != set(right):
        _fail(
            "BUILD_INVENTORY_MISMATCH",
            "the two builds produced different distribution file sets",
            {
                "only_in_first": sorted(set(left) - set(right)),
                "only_in_second": sorted(set(right) - set(left)),
            },
        )
    mismatched = sorted(name for name in left if left[name] != right[name])
    if mismatched:
        _fail(
            "BUILD_NONDETERMINISTIC",
            "two builds of one source snapshot produced different bytes",
            {
                "artifacts": mismatched,
                "differing_members": {
                    name: _differing_members(left_tree / name, right_tree / name)
                    for name in mismatched
                },
            },
        )
    return left


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


def build_reproducibility_record(
    *,
    artifacts: Mapping[str, Mapping[str, Any]],
    source_snapshot_sha256: str,
    source_date_epoch: int,
    command: Sequence[str],
    generated_at: str,
    normalizations: Sequence[str] | None = None,
    record_id: str = "v4-b06-reproducible-build",
) -> dict[str, Any]:
    """The reproducibility receipt, hashed over exactly what it publishes."""

    _require_timestamp(generated_at, "generated_at")
    if not _DIGEST_PATTERN.match(str(source_snapshot_sha256)):
        _fail(
            "PIN_DIGEST_MALFORMED",
            "the source snapshot digest is not a lowercase sha256 digest",
            {"digest": source_snapshot_sha256},
        )
    selected = (
        sorted(DECLARED_NORMALIZATIONS)
        if normalizations is None
        else sorted(normalizations)
    )
    undeclared = sorted(set(selected) - set(DECLARED_NORMALIZATIONS))
    if undeclared:
        _fail(
            "NORMALIZATION_UNDECLARED",
            "the record names a normalization outside the declared set",
            {"declared": sorted(DECLARED_NORMALIZATIONS), "requested": undeclared},
        )
    if not artifacts:
        _fail("BUILD_TREE_EMPTY", "the record carries no built distribution")
    record: dict[str, Any] = {
        "artifacts": {
            str(name): dict(value) for name, value in sorted(artifacts.items())
        },
        "bit_identical": True,
        "build_command": list(command),
        "gate_id": "v4-b06",
        "generated_at": generated_at,
        "generator": GENERATOR_RELPATH,
        "normalizations": {name: DECLARED_NORMALIZATIONS[name] for name in selected},
        "record_id": record_id,
        "source_date_epoch": int(source_date_epoch),
        "source_snapshot_sha256": str(source_snapshot_sha256),
    }
    if set(record) | {"record_hash"} != set(_REPRODUCIBILITY_FIELDS):
        _fail(
            "LEDGER_FIELD_UNKNOWN",
            "the reproducibility record no longer publishes its declared fields",
            {"fields": sorted(record)},
        )
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record


def _pin_entry(
    *,
    pin_id: str,
    kind: str,
    subject: str,
    digest: str | None,
    source_path: str,
    source_sha256: str | None,
    required_pin_fields: Sequence[str] = (),
    unpinned_fields: Sequence[str] = (),
    blocking_reason: str | None = None,
) -> dict[str, Any]:
    entry = {
        "blocking_reason": blocking_reason,
        "digest": digest,
        "execution_permitted": blocking_reason is None,
        "kind": kind,
        "pin_id": pin_id,
        "required_pin_fields": sorted(required_pin_fields),
        "source_path": source_path,
        "source_sha256": source_sha256,
        "subject": subject,
        "unpinned_fields": sorted(unpinned_fields),
    }
    if set(entry) != set(_ENTRY_FIELDS):
        _fail(
            "LEDGER_FIELD_UNKNOWN",
            "a pin entry no longer publishes its declared fields",
            {"fields": sorted(entry)},
        )
    return entry


def build_pin_ledger(
    root: str | Path,
    *,
    generated_at: str,
    ledger_id: str = "v4-b06-pin-ledger",
) -> dict[str, Any]:
    """Collect every external execution pin the sealed packages rely on."""

    _require_timestamp(generated_at, "generated_at")
    base = Path(root)
    toolchain = read_toolchain_lock(base)
    toolchain_path = base / TOOLCHAIN_LOCK_PATH
    entries: list[dict[str, Any]] = [
        _pin_entry(
            pin_id="toolchain-lock",
            kind="toolchain_lock",
            subject=TOOLCHAIN_LOCK_PATH,
            digest=_file_sha(toolchain_path),
            source_path=TOOLCHAIN_LOCK_PATH,
            source_sha256=_file_sha(toolchain_path),
        )
    ]

    for ecosystem, relative in toolchain["lockfiles"].items():
        path = base / relative
        if not path.is_file():
            _fail(
                "PIN_SOURCE_UNREADABLE",
                f"the toolchain lock names a lockfile that is absent: {relative}",
                {"ecosystem": ecosystem, "lockfile": relative},
            )
        entries.append(
            _pin_entry(
                pin_id=f"{ecosystem}-lock",
                kind="dependency_lock",
                subject=relative,
                digest=_file_sha(path),
                source_path=relative,
                source_sha256=_file_sha(path),
            )
        )

    constraints_relative = toolchain["backend"]["constraints"]
    constraints_path = base / constraints_relative
    if not constraints_path.is_file():
        _fail(
            "PIN_SOURCE_UNREADABLE",
            "the pinned build backend names constraints that are absent",
            {"constraints": constraints_relative},
        )
    entries.append(
        _pin_entry(
            pin_id="python-build-backend",
            kind="build_backend",
            subject=(
                f"{toolchain['backend']['name']}=={toolchain['backend']['version']}"
            ),
            digest=_file_sha(constraints_path),
            source_path=constraints_relative,
            source_sha256=_file_sha(constraints_path),
        )
    )

    container = sealed_container_pin(base)
    entries.append(
        _pin_entry(
            pin_id="postgres-image",
            kind="container_image",
            subject=container["repository"],
            digest=container["digest"],
            source_path=container["source_path"],
            source_sha256=container["source_sha256"],
        )
    )

    required = backend_pin_requirements(base)
    schema_path = base / BACKEND_SCHEMA_PATH
    entries.append(
        _pin_entry(
            pin_id="shinka-backend",
            kind="external_backend",
            subject=BACKEND_SCHEMA_PATH,
            digest=None,
            source_path=BACKEND_SCHEMA_PATH,
            source_sha256=_file_sha(schema_path),
            required_pin_fields=required,
            unpinned_fields=required,
            blocking_reason=(
                "no sealed ShinkaBackendManifest exists, so the exact revision "
                "and manifest digest this contract requires are unpinned"
            ),
        )
    )

    ledger: dict[str, Any] = {
        "blocked_pin_count": sum(
            1 for entry in entries if not entry["execution_permitted"]
        ),
        "entries": sorted(entries, key=lambda entry: entry["pin_id"]),
        "executable_pin_count": sum(
            1 for entry in entries if entry["execution_permitted"]
        ),
        "gate_id": "v4-b06",
        "generated_at": generated_at,
        "generator": GENERATOR_RELPATH,
        "ledger_id": ledger_id,
    }
    ledger["ledger_hash"] = hash_excluding(ledger, "ledger_hash")
    validate_pin_ledger(ledger)
    return ledger


def validate_pin_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse a ledger that floats a pin, overclaims one, or lost its hash."""

    if not isinstance(ledger, Mapping):
        _fail("INPUT_INVALID", "the pin ledger must be a mapping")
    if set(ledger) != set(_LEDGER_FIELDS):
        _fail(
            "LEDGER_FIELD_UNKNOWN",
            "the pin ledger does not publish exactly its declared fields",
            {
                "missing": sorted(_LEDGER_FIELDS - set(ledger)),
                "unexpected": sorted(set(ledger) - _LEDGER_FIELDS),
            },
        )
    if hash_excluding(ledger, "ledger_hash") != ledger["ledger_hash"]:
        _fail(
            "LEDGER_HASH_MISMATCH",
            "the pin ledger does not re-derive its recorded hash",
            {"ledger_id": ledger.get("ledger_id")},
        )
    _require_timestamp(ledger["generated_at"], "ledger generated_at")

    entries = ledger["entries"]
    if not isinstance(entries, Sequence) or isinstance(entries, str) or not entries:
        _fail("INPUT_INVALID", "the pin ledger carries no entries")
    executable = 0
    blocked = 0
    for index, candidate in enumerate(entries):
        entry = _validated_entry(candidate, index)
        if entry["execution_permitted"]:
            executable += 1
        else:
            blocked += 1
    if executable != ledger["executable_pin_count"]:
        _fail(
            "LEDGER_FIELD_UNKNOWN",
            "the executable pin count does not match the entries",
            {"counted": executable, "recorded": ledger["executable_pin_count"]},
        )
    if blocked != ledger["blocked_pin_count"]:
        _fail(
            "LEDGER_FIELD_UNKNOWN",
            "the blocked pin count does not match the entries",
            {"counted": blocked, "recorded": ledger["blocked_pin_count"]},
        )
    return {
        "blocked_pins": blocked,
        "executable_pins": executable,
        "status": "PASS",
    }


def _validated_entry(candidate: object, index: int) -> Mapping[str, Any]:
    if not isinstance(candidate, Mapping):
        _fail("INPUT_INVALID", f"pin entry {index} is not a mapping", {"index": index})
    entry: Mapping[str, Any] = candidate  # type: ignore[assignment]
    if set(entry) != set(_ENTRY_FIELDS):
        _fail(
            "LEDGER_FIELD_UNKNOWN",
            f"pin entry {index} does not publish exactly its declared fields",
            {
                "missing": sorted(_ENTRY_FIELDS - set(entry)),
                "unexpected": sorted(set(entry) - _ENTRY_FIELDS),
            },
        )
    pin_id = entry["pin_id"]
    if entry["execution_permitted"]:
        digest = entry["digest"]
        if digest is None:
            _fail(
                "PIN_DIGEST_MISSING",
                f"{pin_id} is executable but carries no digest",
                {"pin_id": pin_id},
            )
        if not isinstance(digest, str) or not _DIGEST_PATTERN.match(digest):
            _fail(
                "PIN_DIGEST_MALFORMED",
                f"{pin_id} carries a digest that is not a lowercase sha256 digest",
                {"digest": digest, "pin_id": pin_id},
            )
        if entry["unpinned_fields"]:
            _fail(
                "PIN_OVERCLAIM",
                f"{pin_id} is executable while its own contract fields are unpinned",
                {"pin_id": pin_id, "unpinned_fields": list(entry["unpinned_fields"])},
            )
        if entry["blocking_reason"] is not None:
            _fail(
                "INPUT_INVALID",
                f"{pin_id} is executable and blocked at the same time",
                {"pin_id": pin_id},
            )
    else:
        reason = entry["blocking_reason"]
        if not isinstance(reason, str) or len(reason.strip()) < 20:
            _fail(
                "PIN_BLOCK_UNJUSTIFIED",
                f"{pin_id} is blocked without a recorded reason",
                {"pin_id": pin_id, "blocking_reason": reason},
            )
        if not entry["unpinned_fields"]:
            _fail(
                "PIN_BLOCK_UNJUSTIFIED",
                f"{pin_id} is blocked but names no unpinned field",
                {"pin_id": pin_id},
            )
    return entry


# --------------------------------------------------------------------------
# Gate execution
# --------------------------------------------------------------------------


def require_snapshot_copy(tree: str | Path, expected: str, label: str) -> str:
    """Refuse a build input that is not the snapshot it claims to be."""

    observed = tree_sha256(tree)
    if observed != expected:
        _fail(
            "SOURCE_SNAPSHOT_DIVERGED",
            "a build input copy does not match the source snapshot",
            {"copy": label, "expected": expected, "observed": observed},
        )
    return observed


def build_gate_manifest(
    *,
    outputs: Mapping[str, str],
    ledger: Mapping[str, Any],
    reproducibility: Mapping[str, Any],
    generated_at: str,
    generator_sha256: str | None = None,
) -> dict[str, Any]:
    """The receipt that binds the two records to the generator that wrote them."""

    _require_timestamp(generated_at, "generated_at")
    if not outputs:
        _fail("INPUT_INVALID", "the gate manifest lists no output")
    manifest: dict[str, Any] = {
        "gate_id": "v4-b06",
        "generated_at": generated_at,
        "generator": {
            "path": GENERATOR_RELPATH,
            "sha256": generator_sha256 or _file_sha(Path(__file__)),
        },
        "outputs": {str(name): str(digest) for name, digest in sorted(outputs.items())},
        "pin_ledger_hash": ledger["ledger_hash"],
        "reproducible": reproducibility["bit_identical"],
        "reproducibility_record_hash": reproducibility["record_hash"],
    }
    manifest["manifest_hash"] = hash_excluding(manifest, "manifest_hash")
    return manifest


def run_gate(
    root: str | Path,
    *,
    generated_at: str,
    out_dir: str | Path | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Build twice, compare, collect the pins and write the receipts."""

    _require_timestamp(generated_at, "generated_at")
    base = Path(root)
    target = Path(out_dir) if out_dir is not None else base / OUTPUT_DIR
    work = Path(workspace) if workspace is not None else target / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    toolchain = read_toolchain_lock(base)
    epoch = toolchain["source_date_epoch"]
    constraints = toolchain["backend"]["constraints"]

    snapshot = work / "source"
    snapshot_digest = stage_snapshot(base, snapshot)
    passes: list[Path] = []
    for name in ("pass-a", "pass-b"):
        copy = work / name
        shutil.copytree(snapshot, copy)
        require_snapshot_copy(copy, snapshot_digest, name)
        passes.append(copy)

    command: list[str] = []
    outputs: list[Path] = []
    for index, copy in enumerate(passes):
        output = work / f"output-{'ab'[index]}"
        command = run_build(copy, output, epoch=epoch, constraints=constraints)
        outputs.append(output)

    artifacts = compare_build_trees(outputs[0], outputs[1])
    reproducibility = build_reproducibility_record(
        artifacts=artifacts,
        source_snapshot_sha256=snapshot_digest,
        source_date_epoch=epoch,
        command=command,
        generated_at=generated_at,
    )
    ledger = build_pin_ledger(base, generated_at=generated_at)

    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for name, document in (
        (REPRODUCIBILITY_NAME, reproducibility),
        (LEDGER_NAME, ledger),
    ):
        payload = render(document)
        (target / name).write_bytes(payload)
        written[f"{OUTPUT_DIR}/{name}"] = (
            "sha256:" + hashlib.sha256(payload).hexdigest()
        )

    manifest = build_gate_manifest(
        outputs=written,
        ledger=ledger,
        reproducibility=reproducibility,
        generated_at=generated_at,
    )
    (target / MANIFEST_NAME).write_bytes(render(manifest))
    shutil.rmtree(work, ignore_errors=True)
    return {
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "blocked_pins": ledger["blocked_pin_count"],
        "executable_pins": ledger["executable_pin_count"],
        "outputs": sorted([*written, f"{OUTPUT_DIR}/{MANIFEST_NAME}"]),
        "source_snapshot_sha256": snapshot_digest,
        "status": "PASS",
    }


def emit_pin_ledger(
    root: str | Path,
    *,
    generated_at: str,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Write and immediately re-validate the pin ledger on its own."""

    base = Path(root)
    target = Path(out_dir) if out_dir is not None else base / OUTPUT_DIR
    ledger = build_pin_ledger(base, generated_at=generated_at)
    target.mkdir(parents=True, exist_ok=True)
    payload = render(ledger)
    (target / LEDGER_NAME).write_bytes(payload)
    reloaded = json.loads(payload.decode("utf-8"))
    result = validate_pin_ledger(reloaded)
    return {
        "ledger_hash": ledger["ledger_hash"],
        "output": f"{OUTPUT_DIR}/{LEDGER_NAME}",
        "pin_ids": [entry["pin_id"] for entry in ledger["entries"]],
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="B06 reproducible build gate")
    parser.add_argument("mode", choices=("reproducible-build", "pin-ledger"))
    parser.add_argument(
        "--generated-at",
        default=None,
        help="UTC RFC 3339 instant; defaults to the declared build epoch",
    )
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    try:
        stamp = arguments.generated_at or epoch_timestamp(
            read_toolchain_lock(root)["source_date_epoch"]
        )
        if arguments.mode == "reproducible-build":
            result = run_gate(root, generated_at=stamp)
        else:
            result = emit_pin_ledger(root, generated_at=stamp)
    except BuildGateError as error:
        print(
            json.dumps(
                {
                    "code": error.code,
                    "context": error.context,
                    "message": str(error),
                    "status": "FAIL",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
