"""Stage the plugin-resident Python runtime from the current declared inputs.

The installed plugin must run without a development checkout, so the
application package is copied into ``runtime/python`` and every copied byte is
recorded in ``runtime/runtime-manifest.json``.

Cached/tracked files and non-ignored untracked files under the application
package are staged.  The canonical
``plugins/epistemic-foundry/src/python-bootstrap.py`` is the one additional,
explicit input and is copied byte-for-byte to ``runtime/bootstrap.py``.
Development builds stage dirty declared inputs as they currently are, and their
hashes go in the manifest, so what a build shipped is always recoverable.  The
top-level builder's ``--release`` mode passes ``--require-clean`` and refuses
dirty or untracked inputs before staging.

Usage::

    /absolute/path/to/python3.12 plugins/epistemic-foundry/scripts/build-python-runtime.py
    /absolute/path/to/python3.12 plugins/epistemic-foundry/scripts/build-python-runtime.py --check
    /absolute/path/to/python3.12 plugins/epistemic-foundry/scripts/build-python-runtime.py --require-clean

``--check`` rebuilds into a temporary directory and compares, so CI can prove
the committed payload matches its inputs without writing to the worktree.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = PLUGIN_ROOT.parent.parent
SOURCE_PACKAGE = Path("src/epistemic_foundry")
BOOTSTRAP_SOURCE = Path("plugins/epistemic-foundry/src/python-bootstrap.py")
RUNTIME_DIR = PLUGIN_ROOT / "runtime"
STAGED_PACKAGE = RUNTIME_DIR / "python" / "epistemic_foundry"
STAGED_BOOTSTRAP = RUNTIME_DIR / "bootstrap.py"
MANIFEST_PATH = RUNTIME_DIR / "runtime-manifest.json"
#: Third-party imports the staged package needs from the host interpreter.
#: These are not vendored: both are pure-Python, widely installed, and pinning
#: compiled wheels per platform is a larger decision than this release makes.
#: The launcher probes for them and reports a typed failure when absent.
REQUIRED_THIRD_PARTY = ("jsonschema", "yaml")
#: Files that exist for development and have no meaning inside the payload.
EXCLUDED_SUFFIXES = (".pyc", ".pyo")
EXCLUDED_NAMES = ("conftest.py",)
RUNTIME_ROOT_FILES = frozenset(("bootstrap.py", "runtime-manifest.json"))
RUNTIME_ROOT_DIRECTORIES = frozenset(("python",))
PRIVATE_STAGE_ENV = "EFOUNDRY_PRIVATE_STAGING_ROOT"
PRIVATE_STAGE_PREFIX = ".efoundry-build-"
PRIVATE_STAGE_MARKER = ".epistemic-foundry-private-stage"
PRIVATE_STAGE_MARKER_TEXT = "epistemic-foundry-private-stage-v1\n"


class BuildError(RuntimeError):
    """A build precondition failed; the payload is not written."""


def _is_link_or_junction(path: Path) -> bool:
    """Reject both symbolic links and Windows directory junctions."""
    return path.is_symlink() or path.is_junction()


def _dir_entry_is_link_or_junction(entry: os.DirEntry[str]) -> bool:
    return entry.is_symlink() or Path(entry.path).is_junction()


def _metadata_is_link_or_reparse(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        reparse_flag and file_attributes & reparse_flag
    )


def _source_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _stable_source_error(reason: str) -> BuildError:
    return BuildError(f"source boundary rejected: {reason}")


def validate_authorized_source_path(
    source_relative: Path,
    authorized_relative_root: Path,
    *,
    exact_relative: Path | None = None,
) -> tuple[Path, os.stat_result]:
    """Validate one repo-relative source without following a source link."""
    if (
        source_relative.is_absolute()
        or source_relative.drive
        or source_relative.root
        or not source_relative.parts
        or any(part in ("", ".", "..") for part in source_relative.parts)
    ):
        raise _stable_source_error("declared source path is not repository-relative")
    try:
        source_relative.relative_to(authorized_relative_root)
    except ValueError:
        raise _stable_source_error("declared source is outside its authorized root") from None
    if exact_relative is not None and source_relative != exact_relative:
        raise _stable_source_error("declared source does not match its authorized file")

    try:
        repository_metadata = REPOSITORY_ROOT.lstat()
    except OSError:
        raise _stable_source_error("repository root cannot be inspected") from None
    if _metadata_is_link_or_reparse(repository_metadata) or not stat.S_ISDIR(
        repository_metadata.st_mode
    ):
        raise _stable_source_error("repository root is not an ordinary directory")

    current = REPOSITORY_ROOT
    leaf_metadata: os.stat_result | None = None
    for index, component in enumerate(source_relative.parts):
        current /= component
        is_leaf = index == len(source_relative.parts) - 1
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            reason = (
                "declared source leaf is missing"
                if is_leaf
                else "an intermediate component is missing"
            )
            raise _stable_source_error(reason) from None
        except OSError:
            reason = (
                "declared source leaf cannot be inspected"
                if is_leaf
                else "an intermediate component cannot be inspected"
            )
            raise _stable_source_error(reason) from None
        if _metadata_is_link_or_reparse(metadata):
            reason = (
                "declared source leaf is a link or reparse point"
                if is_leaf
                else "an intermediate component is a link or reparse point"
            )
            raise _stable_source_error(reason)
        if is_leaf:
            if not stat.S_ISREG(metadata.st_mode):
                raise _stable_source_error("declared source leaf is not a regular file")
            leaf_metadata = metadata
        elif not stat.S_ISDIR(metadata.st_mode):
            raise _stable_source_error("an intermediate component is not a directory")

    if leaf_metadata is None:
        raise _stable_source_error("declared source leaf is missing")
    try:
        resolved_leaf = current.resolve(strict=True)
        resolved_authorized_root = (
            REPOSITORY_ROOT / authorized_relative_root
        ).resolve(strict=True)
    except (OSError, RuntimeError):
        raise _stable_source_error("declared source cannot be resolved safely") from None
    if not resolved_leaf.is_relative_to(resolved_authorized_root):
        raise _stable_source_error("resolved source is outside its authorized root")
    if exact_relative is not None:
        try:
            resolved_exact = (REPOSITORY_ROOT / exact_relative).resolve(strict=True)
        except (OSError, RuntimeError):
            raise _stable_source_error("authorized source file cannot be resolved safely") from None
        if resolved_leaf != resolved_exact:
            raise _stable_source_error("resolved source does not match its authorized file")
    return current, leaf_metadata


def read_authorized_source_bytes(
    source_relative: Path,
    authorized_relative_root: Path,
    *,
    exact_relative: Path | None = None,
) -> bytes:
    source, expected_metadata = validate_authorized_source_path(
        source_relative,
        authorized_relative_root,
        exact_relative=exact_relative,
    )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(source, flags)
        opened_metadata = os.fstat(descriptor)
        if (
            _metadata_is_link_or_reparse(opened_metadata)
            or not stat.S_ISREG(opened_metadata.st_mode)
            or _source_identity(opened_metadata) != _source_identity(expected_metadata)
        ):
            raise _stable_source_error("declared source changed before it could be read")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = None
            content = handle.read()
            after_read_metadata = os.fstat(handle.fileno())
    except BuildError:
        raise
    except OSError:
        raise _stable_source_error("declared source could not be read safely") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    try:
        final_metadata = source.lstat()
    except OSError:
        raise _stable_source_error("declared source changed while it was being read") from None
    if (
        _metadata_is_link_or_reparse(final_metadata)
        or not stat.S_ISREG(final_metadata.st_mode)
        or _source_identity(after_read_metadata) != _source_identity(opened_metadata)
        or _source_identity(final_metadata) != _source_identity(opened_metadata)
    ):
        raise _stable_source_error("declared source changed while it was being read")
    return content


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def source_input_files() -> list[Path]:
    """Cached/tracked plus non-ignored untracked source-package files."""
    listed = _git(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        SOURCE_PACKAGE.as_posix(),
    )
    paths: set[Path] = set()
    for entry in listed.split("\0"):
        if not entry:
            continue
        path = Path(entry)
        if path.suffix in EXCLUDED_SUFFIXES or path.name in EXCLUDED_NAMES:
            continue
        paths.add(path)
    if not paths:
        raise BuildError(f"no source files found under {SOURCE_PACKAGE}")
    return sorted(paths, key=lambda path: path.as_posix())


def bootstrap_source_file() -> Path:
    """The explicit canonical bootstrap input, as a repo-relative path."""
    validate_authorized_source_path(
        BOOTSTRAP_SOURCE,
        BOOTSTRAP_SOURCE.parent,
        exact_relative=BOOTSTRAP_SOURCE,
    )
    return BOOTSTRAP_SOURCE


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def head_commit() -> str:
    return _git("rev-parse", "HEAD").strip()


def dirty_inputs() -> list[str]:
    """Every scoped Git status entry that differs from HEAD or is untracked."""
    listed = _git(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        SOURCE_PACKAGE.as_posix(),
        BOOTSTRAP_SOURCE.as_posix(),
    )
    records = listed.split("\0")
    dirty: set[str] = set()
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            raise BuildError("git status returned an invalid porcelain-v1 record")
        status = record[:2]
        dirty.add(record[3:])
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                raise BuildError("git status returned an incomplete rename/copy record")
            dirty.add(records[index])
            index += 1
    return sorted(dirty)


def prepare_outputs(
    files: list[Path], bootstrap_source: Path
) -> list[tuple[Path, Path, bytes, str]]:
    """Read and hash every source before any payload path is written."""
    declarations = []
    for relative in files:
        try:
            package_relative = relative.relative_to(SOURCE_PACKAGE)
        except ValueError:
            raise _stable_source_error(
                "declared package source is outside its authorized root"
            ) from None
        declarations.append(
            (
                relative,
                Path("python") / "epistemic_foundry" / package_relative,
            )
        )
    declarations.append((bootstrap_source, Path("bootstrap.py")))

    output_paths = [output for _, output in declarations]
    if len(output_paths) != len(set(output_paths)):
        raise BuildError("declared runtime output paths are not unique")

    prepared = []
    for source_relative, output_relative in declarations:
        if output_relative == Path("bootstrap.py"):
            content = read_authorized_source_bytes(
                source_relative,
                BOOTSTRAP_SOURCE.parent,
                exact_relative=BOOTSTRAP_SOURCE,
            )
        else:
            content = read_authorized_source_bytes(
                source_relative,
                SOURCE_PACKAGE,
            )
        prepared.append(
            (
                source_relative,
                output_relative,
                content,
                sha256_bytes(content),
            )
        )
    return prepared


def expected_python_inventory(
    prepared: list[tuple[Path, Path, bytes, str]],
) -> tuple[set[Path], set[Path]]:
    """Expected regular files and directories below ``runtime/python``."""
    expected_files: set[Path] = set()
    expected_directories: set[Path] = set()
    for _source, output, _content, _digest in prepared:
        try:
            relative = output.relative_to(Path("python"))
        except ValueError:
            continue
        expected_files.add(relative)
        expected_directories.update(
            parent for parent in relative.parents if parent != Path(".")
        )
    return expected_files, expected_directories


def resolve_runtime_destination() -> tuple[Path, bool]:
    """Resolve the final runtime or a top-builder-owned private staging root."""
    configured = os.environ.get(PRIVATE_STAGE_ENV)
    if not configured:
        return RUNTIME_DIR, False

    candidate = Path(configured)
    if not candidate.is_absolute():
        raise BuildError(f"{PRIVATE_STAGE_ENV} must be an absolute path")
    if _is_link_or_junction(candidate):
        raise BuildError(f"{PRIVATE_STAGE_ENV} must not be a link or junction")
    try:
        stage_root = candidate.resolve(strict=True)
        plugin_root = PLUGIN_ROOT.resolve(strict=True)
    except OSError as error:
        raise BuildError(f"could not resolve {PRIVATE_STAGE_ENV}: {error}") from error
    if stage_root.parent != plugin_root or not stage_root.name.startswith(
        PRIVATE_STAGE_PREFIX
    ):
        raise BuildError(
            f"{PRIVATE_STAGE_ENV} must name a private {PRIVATE_STAGE_PREFIX}* "
            "sibling inside the plugin root"
        )
    if not stage_root.is_dir():
        raise BuildError(f"{PRIVATE_STAGE_ENV} must name an existing directory")
    marker = stage_root / PRIVATE_STAGE_MARKER
    try:
        marker_metadata = marker.lstat()
        marker_text = marker.read_text(encoding="utf-8")
    except OSError as error:
        raise BuildError(
            f"{PRIVATE_STAGE_ENV} does not carry the private staging marker: {error}"
        ) from error
    if _is_link_or_junction(marker) or not marker_metadata.is_file():
        raise BuildError(f"{PRIVATE_STAGE_ENV} staging marker is not a regular file")
    if marker_text != PRIVATE_STAGE_MARKER_TEXT:
        raise BuildError(f"{PRIVATE_STAGE_ENV} staging marker is invalid")
    return stage_root / "runtime", True


def preflight_replaceable_directory(path: Path, label: str) -> bool:
    """Accept an absent or ordinary directory that can be replaced as a whole."""
    if _is_link_or_junction(path):
        raise BuildError(f"existing {label} is a link or junction; refusing to replace")
    if not path.exists():
        return False
    if not path.is_dir():
        raise BuildError(f"existing {label} is not a directory; refusing to replace")
    return True


def preflight_runtime_root(runtime_root: Path, allow_absent: bool) -> bool:
    """Enforce the exact top-level runtime output inventory.

    Returns whether the root exists. An absent root is accepted only when the
    caller explicitly owns a private scratch stage.
    """
    if _is_link_or_junction(runtime_root):
        raise BuildError("existing runtime root is a link or junction; refusing to write")
    if not runtime_root.exists():
        if not allow_absent:
            raise BuildError(
                "runtime output root is missing; only private scratch staging "
                "may create an absent destination"
            )
        return False
    if not runtime_root.is_dir():
        raise BuildError("existing runtime root is not a directory; refusing to write")

    observed: set[str] = set()
    unexpected: list[str] = []
    try:
        with os.scandir(runtime_root) as iterator:
            existing = sorted(iterator, key=lambda entry: entry.name)
    except OSError as error:
        raise BuildError(f"could not inspect runtime output root: {error}") from error
    for entry in existing:
        observed.add(entry.name)
        if _dir_entry_is_link_or_junction(entry):
            unexpected.append(f"{entry.name} (link or junction)")
        elif entry.name in RUNTIME_ROOT_FILES:
            if not entry.is_file(follow_symlinks=False):
                unexpected.append(f"{entry.name} (expected regular file)")
        elif entry.name in RUNTIME_ROOT_DIRECTORIES:
            if not entry.is_dir(follow_symlinks=False):
                unexpected.append(f"{entry.name} (expected directory)")
        elif entry.is_dir(follow_symlinks=False):
            unexpected.append(f"{entry.name}/ (unexpected directory)")
        elif entry.is_file(follow_symlinks=False):
            unexpected.append(f"{entry.name} (unexpected file)")
        else:
            unexpected.append(f"{entry.name} (unexpected special entry)")

    for expected in sorted(RUNTIME_ROOT_FILES | RUNTIME_ROOT_DIRECTORIES):
        if expected not in observed:
            unexpected.append(f"{expected} (missing)")
    if unexpected:
        raise BuildError(
            "runtime root does not match the closed output inventory; refusing "
            f"to write: {'; '.join(unexpected)}"
        )
    return True


def preflight_python_inventory(
    python_root: Path,
    expected_files: set[Path],
    expected_directories: set[Path],
    allow_absent: bool,
) -> None:
    """Require the complete exact runtime/python tree without changing it."""
    if _is_link_or_junction(python_root):
        raise BuildError("existing runtime/python is a link or junction; refusing to write")
    if not python_root.exists():
        if not allow_absent:
            raise BuildError("runtime/python is missing from the closed inventory")
        return
    if not python_root.is_dir():
        raise BuildError(
            "existing runtime/python is not a directory; refusing to write"
        )

    unexpected: list[str] = []
    observed_files: set[Path] = set()
    observed_directories: set[Path] = set()
    pending = [(python_root, Path("."))]
    while pending:
        directory, prefix = pending.pop()
        if _is_link_or_junction(directory):
            raise BuildError(
                f"runtime/python directory is a link or junction: {prefix.as_posix()}"
            )
        try:
            with os.scandir(directory) as iterator:
                existing = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise BuildError(
                f"could not inspect existing runtime/python inventory: {error}"
            ) from error
        for entry in existing:
            relative = Path(entry.name) if prefix == Path(".") else prefix / entry.name
            display = relative.as_posix()
            if _dir_entry_is_link_or_junction(entry):
                unexpected.append(f"{display} (link or junction)")
                continue
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError as error:
                raise BuildError(
                    f"could not inspect runtime/python entry {display}: {error}"
                ) from error
            if is_directory:
                if relative not in expected_directories:
                    unexpected.append(f"{display}/ (directory)")
                else:
                    observed_directories.add(relative)
                    pending.append((Path(entry.path), relative))
            elif is_file:
                if relative not in expected_files:
                    unexpected.append(f"{display} (file)")
                else:
                    observed_files.add(relative)
            else:
                unexpected.append(f"{display} (special entry)")

    for expected in sorted(expected_directories, key=lambda path: path.as_posix()):
        if expected not in observed_directories:
            unexpected.append(f"{expected.as_posix()}/ (missing directory)")
    for expected in sorted(expected_files, key=lambda path: path.as_posix()):
        if expected not in observed_files:
            unexpected.append(f"{expected.as_posix()} (missing file)")

    if unexpected:
        shown = unexpected[:10]
        if len(unexpected) > len(shown):
            shown.append(f"... and {len(unexpected) - len(shown)} more")
        raise BuildError(
            "existing runtime/python contains entries outside the expected "
            f"inventory; refusing to write: {'; '.join(shown)}"
        )


def preflight_replaceable_file(path: Path, label: str) -> None:
    """Require a declared non-tree output to be absent or a regular file."""
    if _is_link_or_junction(path):
        raise BuildError(f"existing {label} is a link or junction; refusing to write")
    if path.exists() and not path.is_file():
        raise BuildError(f"existing {label} is not a regular file; refusing to write")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write bytes through a sibling temporary file and atomically replace."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BuildError(f"could not create payload directory for {path}: {error}") from error

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise BuildError(f"could not atomically write payload file {path}: {error}") from error


def preflight_runtime_payload(
    destination_runtime: Path,
    prepared: list[tuple[Path, Path, bytes, str]],
    *,
    allow_absent: bool,
) -> bool:
    """Complete every read-only runtime preflight before a payload write."""
    expected_files, expected_directories = expected_python_inventory(prepared)
    runtime_exists = preflight_runtime_root(
        destination_runtime, allow_absent=allow_absent
    )
    preflight_python_inventory(
        destination_runtime / "python",
        expected_files,
        expected_directories,
        allow_absent=allow_absent and not runtime_exists,
    )
    preflight_replaceable_file(
        destination_runtime / "bootstrap.py", "runtime/bootstrap.py"
    )
    preflight_replaceable_file(
        destination_runtime / "runtime-manifest.json",
        "runtime/runtime-manifest.json",
    )
    return runtime_exists


def stage(
    destination_runtime: Path,
    files: list[Path],
    bootstrap_source: Path,
    *,
    allow_absent: bool,
) -> dict:
    """Preflight and atomically stage the declared runtime payload."""
    prepared = prepare_outputs(files, bootstrap_source)
    preflight_runtime_payload(
        destination_runtime, prepared, allow_absent=allow_absent
    )

    entries = [
        {
            "path": output.as_posix(),
            "sha256": digest,
            "source": source.as_posix(),
        }
        for source, output, _content, digest in prepared
    ]
    closure_digest = hashlib.sha256()
    for entry in entries:
        closure_digest.update(entry["path"].encode("utf-8"))
        closure_digest.update(b"\0")
        closure_digest.update(entry["sha256"].encode("utf-8"))
        closure_digest.update(b"\0")
    manifest = {
        "canonicality_claim": "NONE",
        "closure_sha256": closure_digest.hexdigest(),
        "dirty_inputs": dirty_inputs(),
        "file_count": len(entries),
        "files": entries,
        "python_requirement": ">=3.12",
        "required_third_party": list(REQUIRED_THIRD_PARTY),
        "schema": "epistemic-foundry/mvp-runtime-manifest/v1",
        "scope": "MVP_RELEASE_ONLY",
        "served_retrieval_lanes": ["lexical", "citation", "entity_variable"],
        "source_commit": head_commit(),
        "source_root": SOURCE_PACKAGE.as_posix(),
    }

    for _source, output, content, _digest in prepared:
        atomic_write_bytes(destination_runtime / output, content)
    return manifest


def write_manifest(path: Path, manifest: dict) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _tree_inventory(root: Path) -> dict[str, str]:
    """Every entry under ``root`` without following symlinks."""
    if _is_link_or_junction(root):
        return {".": "link_or_junction"}
    if not root.exists():
        return {}
    if not root.is_dir():
        if root.is_file():
            return {".": f"file:{sha256_of(root)}"}
        return {".": "special"}

    inventory: dict[str, str] = {}
    pending = [(root, Path("."))]
    while pending:
        directory, prefix = pending.pop()
        if _is_link_or_junction(directory):
            inventory[prefix.as_posix()] = "link_or_junction"
            continue
        try:
            with os.scandir(directory) as iterator:
                existing = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise BuildError(f"could not inventory payload tree {root}: {error}") from error
        for entry in existing:
            relative = Path(entry.name) if prefix == Path(".") else prefix / entry.name
            key = relative.as_posix()
            if _dir_entry_is_link_or_junction(entry):
                inventory[key] = "link_or_junction"
            elif entry.is_dir(follow_symlinks=False):
                inventory[key] = "directory"
                pending.append((Path(entry.path), relative))
            elif entry.is_file(follow_symlinks=False):
                try:
                    inventory[key] = f"file:{sha256_of(Path(entry.path))}"
                except OSError as error:
                    raise BuildError(
                        f"could not hash payload entry {key}: {error}"
                    ) from error
            else:
                inventory[key] = "special"
    return inventory


def tree_differences(left: Path, right: Path) -> list[str]:
    """Every path that differs between two staged trees.

    Content is compared by hash rather than by ``filecmp``: a size-and-mtime
    comparison can call a changed file unchanged, which is exactly the drift
    this check exists to catch.
    """
    if not left.exists() and not _is_link_or_junction(left):
        return ["the committed payload has not been built"]
    committed = _tree_inventory(left)
    rebuilt = _tree_inventory(right)
    differences = [
        f"only in committed payload: {path}"
        for path in sorted(set(committed) - set(rebuilt))
    ]
    differences += [
        f"only in rebuild: {path}" for path in sorted(set(rebuilt) - set(committed))
    ]
    differences += [
        f"content differs: {path}"
        for path in sorted(set(committed) & set(rebuilt))
        if committed[path] != rebuilt[path]
    ]
    return differences


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        print(
            "build failed: the plugin runtime builder requires Python 3.12 or newer",
            file=sys.stderr,
        )
        return 1
    parser = argparse.ArgumentParser(description="build the plugin runtime")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed payload matches a fresh build",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="inspect the final runtime replacement roots without writing payload bytes",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help=(
            "refuse to stage when any declared input differs from HEAD or is "
            "untracked; the top-level builder passes this for --release, "
            "where the payload must be reproducible from a clean checkout"
        ),
    )
    args = parser.parse_args(argv)
    if args.check and args.preflight:
        parser.error("--check and --preflight are mutually exclusive")
    try:
        files = source_input_files()
        bootstrap_source = bootstrap_source_file()
    except BuildError as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    if args.require_clean:
        dirty = dirty_inputs()
        if dirty:
            print(
                f"build refused: {len(dirty)} input file(s) differ from HEAD, so "
                "this payload could not be rebuilt from a clean checkout. "
                "Commit them first, or drop --require-clean for a development "
                "build.",
                file=sys.stderr,
            )
            for path in dirty[:10]:
                print(f"  {path}", file=sys.stderr)
            if len(dirty) > 10:
                print(f"  ... and {len(dirty) - 10} more", file=sys.stderr)
            return 1
    if args.preflight:
        try:
            runtime_exists = preflight_replaceable_directory(
                RUNTIME_DIR, "runtime root"
            )
            preflight_replaceable_directory(
                RUNTIME_DIR / "python", "runtime/python root"
            )
        except BuildError as error:
            print(f"build failed: {error}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {"status": "PREFLIGHT_OK" if runtime_exists else "ABSENT"},
                sort_keys=True,
            )
        )
        return 0
    if args.check:
        try:
            prepared = prepare_outputs(files, bootstrap_source)
            destination_runtime, _private_stage = resolve_runtime_destination()
            preflight_runtime_payload(
                destination_runtime, prepared, allow_absent=False
            )
            with tempfile.TemporaryDirectory() as scratch:
                scratch_runtime = Path(scratch) / "runtime"
                manifest = stage(
                    scratch_runtime,
                    files,
                    bootstrap_source,
                    allow_absent=True,
                )
                rebuilt_manifest = scratch_runtime / "runtime-manifest.json"
                write_manifest(rebuilt_manifest, manifest)
                differences = tree_differences(
                    destination_runtime / "python", scratch_runtime / "python"
                )
                rebuilt_bootstrap = scratch_runtime / "bootstrap.py"
                destination_bootstrap = destination_runtime / "bootstrap.py"
                if not destination_bootstrap.is_file():
                    differences.append(
                        "bootstrap.py is missing from the committed payload"
                    )
                elif sha256_of(destination_bootstrap) != sha256_of(rebuilt_bootstrap):
                    differences.append("content differs: bootstrap.py")
                destination_manifest = destination_runtime / "runtime-manifest.json"
                if not destination_manifest.is_file():
                    differences.append("runtime-manifest.json is missing")
                elif destination_manifest.read_bytes() != rebuilt_manifest.read_bytes():
                    differences.append(
                        "runtime-manifest.json differs from the rebuilt manifest"
                    )
        except BuildError as error:
            print(f"build failed: {error}", file=sys.stderr)
            return 1
        if differences:
            print("payload is out of date:", file=sys.stderr)
            for line in differences:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"payload matches its inputs ({manifest['file_count']} files)")
        return 0
    try:
        destination_runtime, private_stage = resolve_runtime_destination()
        manifest = stage(
            destination_runtime,
            files,
            bootstrap_source,
            allow_absent=private_stage,
        )
        destination_manifest = destination_runtime / "runtime-manifest.json"
        write_manifest(destination_manifest, manifest)
    except BuildError as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    staged_package = destination_runtime / "python" / "epistemic_foundry"
    try:
        staged = staged_package.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        staged = staged_package.as_posix()
    print(f"staged {manifest['file_count']} files into {staged}")
    if manifest["dirty_inputs"]:
        print(
            f"note: {len(manifest['dirty_inputs'])} scoped source path(s) differ "
            "from HEAD; the paths and staged-file hashes are recorded in the "
            "manifest"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
