"""Container-backed execution from trusted in-memory resolver snapshots.

The public factory pins host execution authority once.  Per invocation, trusted
synchronous resolvers provide a detached candidate artifact and the current
execution authority.  Candidate files are serialized into a deterministic,
bounded in-memory tar stream and copied into a stopped container; no caller
path or host candidate mount exists.

This module returns bounded raw observations only.  It does not create an
effect receipt, gate result, scientific value, or acceptance claim.
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import io
import json
import os
import re
import signal
import stat
import subprocess
import tarfile
import threading
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, BinaryIO

from .sandbox import REQUIRED_QUOTAS, require_execution_permitted

__all__ = ["CandidateContainerRefused", "create_candidate_container_executor"]

_IMAGE_REFERENCE = re.compile(
    r"^(?P<name>[A-Za-z0-9][^\s@]*)@(?P<digest>sha256:[0-9a-f]{64})$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
_PORTABLE_FORBIDDEN = re.compile(r"[<>:\"\\|?*\x00-\x1f]")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_CANDIDATE_KEYS = frozenset(
    {"candidate_artifact_id", "files", "reachable_resource_ids"}
)
_CANDIDATE_FILE_KEYS = frozenset({"path", "bytes"})
_READ_CHUNK_BYTES = 64 * 1024
_CONTROL_OUTPUT_BYTES = 1024 * 1024
_CONTROL_TIMEOUT_SECONDS = 10.0
_STATE_INSPECT_TIMEOUT_SECONDS = 1.0
_CLEANUP_TIMEOUT_SECONDS = 3.0
_POLL_SECONDS = 0.01
_TERMINATE_GRACE_SECONDS = 0.5
_KILL_WAIT_SECONDS = 1.0
_THREAD_JOIN_SECONDS = 1.0
_CFS_PERIOD_US = 1_000_000
_CFS_MIN_QUOTA_US = 1_000
_MAX_SIGNED_QUOTA = (1 << 63) - 1
_MAX_TEXT_BYTES = 1024 * 1024
_MAX_ID_BYTES = 128
_MAX_PORTABLE_PATH_BYTES = 100
_TAR_BLOCK_BYTES = 512
_TAR_RECORD_BLOCKS = 20
_CANDIDATE_DIRECTORY = "/candidate"
_DOCKER_CONTEXT_ARGUMENTS = ("--context", "default")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)


class CandidateContainerRefused(RuntimeError):
    """The local adapter refused an unsafe or unlaunchable execution."""


@dataclass(frozen=True, slots=True)
class _PathPin:
    path: str
    device: int
    inode: int
    executable: bool


@dataclass(frozen=True, slots=True)
class _CandidateArtifact:
    artifact_id: str
    files: tuple[tuple[str, bytes], ...]
    directories: tuple[str, ...]
    reachable_resource_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ExecutionAuthority:
    authority_id: str
    profile: dict[str, Any]
    lease: dict[str, Any]
    current_fencing_token: int
    now: str
    evaluator_bundle_id: str
    holdout_manifest_id: str
    requested_capabilities: tuple[str, ...]
    quotas: dict[str, int]


@dataclass(slots=True)
class _PipeCapture:
    retained: bytearray = field(default_factory=bytearray)
    byte_count: int = 0
    digest: Any = field(default_factory=hashlib.sha256)
    truncated: bool = False


@dataclass(slots=True)
class _OutputBudget:
    limit: int
    exceeded: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    observed_bytes: int = 0
    retained_bytes: int = 0

    def observe(self, capture: _PipeCapture, chunk: bytes) -> None:
        capture.byte_count += len(chunk)
        capture.digest.update(chunk)
        with self.lock:
            self.observed_bytes += len(chunk)
            remaining = max(0, self.limit - self.retained_bytes)
            retained = chunk[:remaining]
            if retained:
                capture.retained.extend(retained)
                self.retained_bytes += len(retained)
            if len(retained) != len(chunk):
                capture.truncated = True
            if self.observed_bytes > self.limit:
                self.exceeded.set()


@dataclass(slots=True)
class _StdinWrite:
    byte_count: int = 0
    complete: bool = False


@dataclass(slots=True)
class _ProcessObservation:
    returncode: int | None
    stdout: _PipeCapture
    stderr: _PipeCapture
    output_bytes: int
    retained_output_bytes: int
    stdin_bytes_written: int
    stdin_complete: bool
    timed_out: bool
    output_limit_exceeded: bool
    capture_error: bool
    terminate_sent: bool
    kill_sent: bool
    stopped: bool
    duration_seconds: float


class _BoundedBytesIO(io.BytesIO):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit

    def write(self, value: bytes | bytearray) -> int:
        if self.tell() > self._limit - len(value):
            _refuse("candidate tar exceeds the trusted artifact byte cap")
        return super().write(value)


def _refuse(message: str) -> None:
    raise CandidateContainerRefused(message)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _refuse(f"{label} must be a mapping")
    return value


def _require_text(value: object, label: str, *, maximum: int = _MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        _refuse(f"{label} must be a non-empty string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _refuse(f"{label} must be UTF-8 encodable")
    if len(encoded) > maximum:
        _refuse(f"{label} is too large")
    return value


def _require_id(value: object, label: str) -> str:
    return _require_text(value, label, maximum=_MAX_ID_BYTES)


def _require_text_sequence(
    value: object,
    label: str,
    *,
    nonempty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _refuse(f"{label} must be a sequence of strings")
    result: list[str] = []
    total_bytes = 0
    seen: set[str] = set()
    for item in value:
        text = _require_text(item, label)
        if text in seen:
            _refuse(f"{label} must not contain duplicates")
        seen.add(text)
        total_bytes += len(text.encode("utf-8"))
        if total_bytes > _MAX_TEXT_BYTES:
            _refuse(f"{label} is too large")
        result.append(text)
    if nonempty and not result:
        _refuse(f"{label} must not be empty")
    return tuple(result)


def _require_argv(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _refuse("argv must be a sequence of strings")
    result: list[str] = []
    total_bytes = 0
    for item in value:
        if not isinstance(item, str) or "\x00" in item:
            _refuse("argv must contain only strings without NUL characters")
        try:
            total_bytes += len(item.encode("utf-8"))
        except UnicodeEncodeError:
            _refuse("argv must be UTF-8 encodable")
        if total_bytes > _MAX_TEXT_BYTES:
            _refuse("argv is too large")
        result.append(item)
    return tuple(result)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _refuse(f"{label} must be a positive integer")
    if value > _MAX_SIGNED_QUOTA:
        _refuse(f"{label} cannot be represented safely")
    return value


def _async_callable(value: object) -> bool:
    call = getattr(value, "__call__", None)
    return (
        inspect.iscoroutinefunction(value)
        or inspect.isasyncgenfunction(value)
        or inspect.iscoroutinefunction(call)
        or inspect.isasyncgenfunction(call)
    )


def _trusted_resolver(value: object, label: str) -> Callable[[str], object]:
    if not callable(value) or _async_callable(value):
        _refuse(f"{label} must be a trusted synchronous callable")
    return value


def _resolve_sync(
    resolver: Callable[[str], object],
    identifier: str,
    label: str,
) -> object:
    try:
        result = resolver(identifier)
    except Exception:
        raise CandidateContainerRefused(f"{label} resolver failed") from None
    if inspect.isawaitable(result) or inspect.isasyncgen(result):
        close = getattr(result, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        _refuse(f"{label} resolver returned an asynchronous result")
    return result


def _portable_relative_path(value: object) -> str:
    path = _require_text(value, "candidate file path", maximum=_MAX_PORTABLE_PATH_BYTES)
    if unicodedata.normalize("NFC", path) != path:
        _refuse("candidate file paths must use NFC Unicode normalization")
    if (
        path.startswith("/")
        or path.endswith("/")
        or "//" in path
        or _PORTABLE_FORBIDDEN.search(path)
    ):
        _refuse("candidate file path must be portable and relative")
    components = path.split("/")
    for component in components:
        if component in {"", ".", ".."} or component.endswith((" ", ".")):
            _refuse("candidate file path must be portable and relative")
        if component.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
            _refuse("candidate file path uses a reserved portable name")
    return path


def _implicit_directories(paths: Sequence[str]) -> tuple[str, ...]:
    directories: set[str] = set()
    for path in paths:
        components = path.split("/")[:-1]
        for index in range(1, len(components) + 1):
            directories.add("/".join(components[:index]))
    return tuple(sorted(directories, key=lambda item: (item.count("/"), item)))


def _expected_tar_bytes(
    files: Sequence[tuple[str, bytes]],
    directories: Sequence[str],
) -> int:
    blocks = 2 + len(directories)
    for _, content in files:
        blocks += 1 + (len(content) + _TAR_BLOCK_BYTES - 1) // _TAR_BLOCK_BYTES
    records = (blocks + _TAR_RECORD_BLOCKS - 1) // _TAR_RECORD_BLOCKS
    return records * _TAR_RECORD_BLOCKS * _TAR_BLOCK_BYTES


def _snapshot_candidate_artifact(
    value: object,
    *,
    expected_artifact_id: str,
    trusted_byte_cap: int,
    disk_byte_cap: int,
) -> _CandidateArtifact:
    source = _require_mapping(value, "candidate artifact")
    if frozenset(source.keys()) != _CANDIDATE_KEYS:
        _refuse("candidate artifact mapping must use the closed resolver shape")
    resolved_id = _require_id(
        source.get("candidate_artifact_id"), "resolved candidate_artifact_id"
    )
    if resolved_id != expected_artifact_id:
        _refuse("candidate resolver returned a different artifact identity")
    raw_files = source.get("files")
    if isinstance(raw_files, (str, bytes)) or not isinstance(raw_files, Sequence):
        _refuse("candidate artifact files must be a sequence")
    if not raw_files:
        _refuse("candidate artifact must contain at least one regular file")

    files: list[tuple[str, bytes]] = []
    path_keys: set[str] = set()
    total_bytes = 0
    content_limit = min(trusted_byte_cap, disk_byte_cap)
    for raw_file in raw_files:
        file_source = _require_mapping(raw_file, "candidate file")
        if frozenset(file_source.keys()) != _CANDIDATE_FILE_KEYS:
            _refuse("candidate file mapping must contain only path and bytes")
        path = _portable_relative_path(file_source.get("path"))
        path_key = path.casefold()
        if path_key in path_keys:
            _refuse("candidate artifact contains duplicate portable paths")
        path_keys.add(path_key)
        content = file_source.get("bytes")
        if type(content) is not bytes:
            _refuse("candidate file content must be immutable in-memory bytes")
        total_bytes += len(content)
        if total_bytes > content_limit:
            _refuse("candidate artifact exceeds its trusted or profile byte cap")
        files.append((path, content))

    files.sort(key=lambda item: item[0])
    directories = _implicit_directories([path for path, _ in files])
    file_path_keys = {path.casefold() for path, _ in files}
    if any(directory.casefold() in file_path_keys for directory in directories):
        _refuse("candidate artifact path is both a file and a directory")
    if _expected_tar_bytes(files, directories) > trusted_byte_cap:
        _refuse("candidate tar exceeds the trusted artifact byte cap")

    reachable = set(
        _require_text_sequence(
            source.get("reachable_resource_ids"),
            "reachable_resource_ids",
            nonempty=False,
        )
    )
    reachable.add(resolved_id)
    return _CandidateArtifact(
        artifact_id=resolved_id,
        files=tuple(files),
        directories=directories,
        reachable_resource_ids=tuple(sorted(reachable)),
    )


def _tar_info(name: str, *, directory: bool, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = 0o555
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.size = 0 if directory else size
    return info


def _build_candidate_tar(
    candidate: _CandidateArtifact,
    *,
    trusted_byte_cap: int,
) -> tuple[bytes, str]:
    stream = _BoundedBytesIO(trusted_byte_cap)
    try:
        with tarfile.open(
            fileobj=stream,
            mode="w",
            format=tarfile.USTAR_FORMAT,
        ) as archive:
            for directory in candidate.directories:
                archive.addfile(_tar_info(directory, directory=True))
            for path, content in candidate.files:
                archive.addfile(
                    _tar_info(path, directory=False, size=len(content)),
                    io.BytesIO(content),
                )
        payload = stream.getvalue()
    except CandidateContainerRefused:
        raise
    except (OSError, tarfile.TarError, ValueError):
        raise CandidateContainerRefused(
            "candidate artifact could not be serialized safely"
        ) from None
    return payload, f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _snapshot_profile(value: object) -> tuple[dict[str, Any], dict[str, int]]:
    source = _require_mapping(value, "authority profile")
    quotas_source = _require_mapping(source.get("quotas"), "authority profile quotas")
    quotas = {
        name: _positive_integer(quotas_source.get(name), f"quota {name}")
        for name in REQUIRED_QUOTAS
    }
    profile = {
        "profile_id": _require_id(source.get("profile_id"), "profile_id"),
        "declared_capabilities": _require_text_sequence(
            source.get("declared_capabilities"),
            "declared_capabilities",
            nonempty=True,
        ),
        "network_policy": _require_text(
            source.get("network_policy"), "network_policy", maximum=_MAX_ID_BYTES
        ),
        "quotas": quotas,
    }
    return profile, quotas


def _snapshot_lease(value: object) -> dict[str, Any]:
    source = _require_mapping(value, "authority lease")
    revoked = source.get("revoked")
    if not isinstance(revoked, bool):
        _refuse("lease revoked must be a boolean")
    return {
        "lease_id": _require_id(source.get("lease_id"), "lease_id"),
        "capabilities": _require_text_sequence(
            source.get("capabilities"), "lease capabilities", nonempty=True
        ),
        "expires_at": _require_text(source.get("expires_at"), "lease expires_at"),
        "revoked": revoked,
        "fencing_token": _positive_integer(
            source.get("fencing_token"), "lease fencing_token"
        ),
    }


def _snapshot_execution_authority(
    value: object,
    *,
    authority_id: str,
) -> _ExecutionAuthority:
    source = _require_mapping(value, "execution authority")
    profile, quotas = _snapshot_profile(source.get("profile"))
    lease = _snapshot_lease(source.get("lease"))
    current_fence = _positive_integer(
        source.get("current_fencing_token"), "current fencing token"
    )
    if lease["fencing_token"] != current_fence:
        _refuse("lease fencing token is not current")
    requested = _require_text_sequence(
        source.get("requested_capabilities"),
        "requested_capabilities",
        nonempty=True,
    )
    if "compute" not in requested:
        _refuse("requested_capabilities must include compute")
    return _ExecutionAuthority(
        authority_id=authority_id,
        profile=profile,
        lease=lease,
        current_fencing_token=current_fence,
        now=_require_text(source.get("now"), "authority now"),
        evaluator_bundle_id=_require_id(
            source.get("evaluator_bundle_id"), "evaluator_bundle_id"
        ),
        holdout_manifest_id=_require_id(
            source.get("holdout_manifest_id"), "holdout_manifest_id"
        ),
        requested_capabilities=requested,
        quotas=quotas,
    )


def _permission_guard(
    authority: _ExecutionAuthority,
    reachable_resource_ids: Sequence[str],
) -> None:
    try:
        require_execution_permitted(
            profile=authority.profile,
            lease=authority.lease,
            requested_capabilities=authority.requested_capabilities,
            now=authority.now,
            evaluator_bundle_id=authority.evaluator_bundle_id,
            holdout_manifest_id=authority.holdout_manifest_id,
            reachable_resource_ids=reachable_resource_ids,
        )
    except Exception:
        raise CandidateContainerRefused(
            "candidate execution permission was refused"
        ) from None


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def _is_link_or_junction(path: str, details: os.stat_result) -> bool:
    junction_check = getattr(os.path, "isjunction", None)
    is_junction = bool(junction_check(path)) if junction_check is not None else False
    attributes = int(getattr(details, "st_file_attributes", 0))
    return (
        stat.S_ISLNK(details.st_mode)
        or is_junction
        or bool(attributes & _REPARSE_POINT)
    )


def _is_network_path(raw: str, absolute: str) -> bool:
    if raw.startswith(("\\\\", "//")) or absolute.startswith(("\\\\", "//")):
        return True
    if os.name != "nt":
        return False
    drive, _ = os.path.splitdrive(absolute)
    if not drive:
        return True
    try:
        import ctypes

        drive_type = int(ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\"))
    except Exception:
        _refuse("trusted host path locality could not be verified")
    return drive_type == 4


def _ancestors_are_plain(path: str) -> bool:
    current = path
    while True:
        try:
            details = os.lstat(current)
        except (OSError, ValueError):
            return False
        if _is_link_or_junction(current, details):
            return False
        parent = os.path.dirname(current)
        if _path_key(parent) == _path_key(current):
            return True
        current = parent


def _pin_existing_path(
    value: str | os.PathLike[str],
    *,
    label: str,
    executable: bool = False,
) -> _PathPin:
    try:
        raw = os.fspath(value)
    except TypeError:
        _refuse(f"{label} is invalid")
    if not isinstance(raw, str) or not raw or "\x00" in raw or not os.path.isabs(raw):
        _refuse(f"{label} must be absolute")
    absolute = os.path.abspath(raw)
    if _is_network_path(raw, absolute):
        _refuse(f"{label} must be on a local filesystem")
    try:
        details = os.lstat(absolute)
        canonical = os.path.realpath(absolute, strict=True)
    except (OSError, ValueError):
        _refuse(f"{label} is unavailable")
    if _path_key(absolute) != _path_key(canonical) or not _ancestors_are_plain(absolute):
        _refuse(f"{label} must not cross a link, junction, or reparse point")
    if executable:
        if not stat.S_ISREG(details.st_mode) or not os.access(canonical, os.X_OK):
            _refuse("container runtime must be an executable regular file")
    elif not stat.S_ISDIR(details.st_mode):
        _refuse(f"{label} must be a directory")
    return _PathPin(
        path=canonical,
        device=int(details.st_dev),
        inode=int(details.st_ino),
        executable=executable,
    )


def _verify_pin(pin: _PathPin, label: str) -> None:
    current = _pin_existing_path(
        pin.path,
        label=label,
        executable=pin.executable,
    )
    if current.device != pin.device or current.inode != pin.inode:
        _refuse(f"{label} changed after it was pinned")


def _is_within(path: str, parent: str) -> bool:
    try:
        common = os.path.commonpath((path, parent))
    except ValueError:
        return False
    return _path_key(common) == _path_key(parent) and _path_key(path) != _path_key(
        parent
    )


def _file_identity(details: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(details.st_dev),
        int(details.st_ino),
        int(details.st_mode),
        int(details.st_size),
        int(details.st_mtime_ns),
        int(details.st_ctime_ns),
    )


def _stable_file_digest(path: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        before = os.lstat(path)
        descriptor = os.open(path, flags)
    except (OSError, ValueError):
        _refuse("container runtime could not be verified")
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(opened):
            _refuse("container runtime changed while it was verified")
        while True:
            chunk = os.read(descriptor, _READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        after_open = os.fstat(descriptor)
    except OSError:
        _refuse("container runtime could not be verified")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError:
        _refuse("container runtime changed while it was verified")
    if _file_identity(before) != _file_identity(after_open) or _file_identity(
        before
    ) != _file_identity(after_path):
        _refuse("container runtime changed while it was verified")
    return f"sha256:{digest.hexdigest()}"


def _verify_runtime(
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_digest: str,
) -> None:
    _verify_pin(runtime_parent, "trusted runtime parent")
    _verify_pin(runtime, "container runtime")
    if not _is_within(runtime.path, runtime_parent.path):
        _refuse("container runtime escaped its trusted parent")
    observed = _stable_file_digest(runtime.path)
    if not hmac.compare_digest(observed, expected_digest):
        _refuse("container runtime digest does not match its trusted pin")


def _parse_image_reference(image_reference: object) -> tuple[str, str]:
    if not isinstance(image_reference, str) or "\x00" in image_reference:
        _refuse("container image must be digest-pinned")
    matched = _IMAGE_REFERENCE.fullmatch(image_reference)
    if matched is None:
        _refuse("container image must use <name>@sha256:<64 lowercase hex>")
    return image_reference, matched.group("digest")


def _read_pipe(
    stream: BinaryIO,
    capture: _PipeCapture,
    budget: _OutputBudget,
    capture_error: threading.Event,
    stopping: threading.Event,
) -> None:
    try:
        descriptor = stream.fileno()
        while True:
            chunk = os.read(descriptor, _READ_CHUNK_BYTES)
            if not chunk:
                break
            budget.observe(capture, chunk)
    except Exception:
        if not stopping.is_set():
            capture_error.set()
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _write_stdin(stream: BinaryIO, payload: bytes, state: _StdinWrite) -> None:
    try:
        descriptor = stream.fileno()
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining[:_READ_CHUNK_BYTES])
            if written <= 0:
                break
            state.byte_count += written
            remaining = remaining[written:]
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        state.complete = state.byte_count == len(payload)
        try:
            stream.close()
        except Exception:
            pass


def _send_process_signal(process: subprocess.Popen[bytes], *, kill: bool) -> bool:
    if process.poll() is not None:
        return False
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
        elif kill:
            process.kill()
        else:
            process.terminate()
        return True
    except (OSError, ProcessLookupError):
        return False


def _stop_process(process: subprocess.Popen[bytes]) -> tuple[bool, bool, bool]:
    terminate_sent = _send_process_signal(process, kill=False)
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        return terminate_sent, False, True
    except subprocess.TimeoutExpired:
        kill_sent = _send_process_signal(process, kill=True)
    try:
        process.wait(timeout=_KILL_WAIT_SECONDS)
        stopped = True
    except subprocess.TimeoutExpired:
        stopped = False
    return terminate_sent, kill_sent, stopped


def _close_stream(stream: BinaryIO | None) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except Exception:
        pass


def _popen_kwargs(cwd: str, *, attached_stdin: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bufsize": 0,
        "close_fds": True,
        "cwd": cwd,
        "env": {},
        "shell": False,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE if attached_stdin else subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
    }
    if os.name == "posix":
        result["start_new_session"] = True
    elif os.name == "nt":
        result["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return result


def _run_process(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    arguments: Sequence[str],
    timeout_seconds: float,
    output_byte_cap: int,
    stdin_payload: bytes | None,
) -> _ProcessObservation:
    _verify_runtime(runtime, runtime_parent, expected_runtime_digest)
    _verify_pin(trusted_cwd, "trusted host working directory")
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [runtime.path, *_DOCKER_CONTEXT_ARGUMENTS, *arguments],
            **_popen_kwargs(trusted_cwd.path, attached_stdin=stdin_payload is not None),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise CandidateContainerRefused(
            "container runtime could not be launched"
        ) from None

    stdout_capture = _PipeCapture()
    stderr_capture = _PipeCapture()
    budget = _OutputBudget(output_byte_cap)
    stdin_state = _StdinWrite(complete=stdin_payload is None)
    capture_error = threading.Event()
    stopping = threading.Event()
    terminate_sent = False
    kill_sent = False
    stopped = True

    if process.stdout is None or process.stderr is None or (
        stdin_payload is not None and process.stdin is None
    ):
        stopping.set()
        terminate_sent, kill_sent, stopped = _stop_process(process)
        return _ProcessObservation(
            returncode=process.returncode,
            stdout=stdout_capture,
            stderr=stderr_capture,
            output_bytes=0,
            retained_output_bytes=0,
            stdin_bytes_written=0,
            stdin_complete=stdin_payload is None,
            timed_out=False,
            output_limit_exceeded=False,
            capture_error=True,
            terminate_sent=terminate_sent,
            kill_sent=kill_sent,
            stopped=stopped,
            duration_seconds=max(0.0, time.monotonic() - started),
        )

    stdout_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stdout, stdout_capture, budget, capture_error, stopping),
        daemon=True,
        name="candidate-container-stdout",
    )
    stderr_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stderr, stderr_capture, budget, capture_error, stopping),
        daemon=True,
        name="candidate-container-stderr",
    )
    stdin_thread = None
    if stdin_payload is not None and process.stdin is not None:
        stdin_thread = threading.Thread(
            target=_write_stdin,
            args=(process.stdin, stdin_payload, stdin_state),
            daemon=True,
            name="candidate-container-stdin",
        )
    threads = [stdout_thread, stderr_thread]
    if stdin_thread is not None:
        threads.append(stdin_thread)
    started_threads: list[threading.Thread] = []
    try:
        for thread in threads:
            thread.start()
            started_threads.append(thread)
    except RuntimeError:
        capture_error.set()
        stopping.set()
        terminate_sent, kill_sent, stopped = _stop_process(process)

    timed_out = False
    if len(started_threads) == len(threads):
        while process.poll() is None:
            if budget.exceeded.is_set() or capture_error.is_set():
                stopping.set()
                terminate_sent, kill_sent, stopped = _stop_process(process)
                break
            if time.monotonic() - started >= timeout_seconds:
                timed_out = True
                stopping.set()
                terminate_sent, kill_sent, stopped = _stop_process(process)
                break
            time.sleep(_POLL_SECONDS)

    if stdin_thread is not None:
        stdin_thread.join(timeout=_THREAD_JOIN_SECONDS)
        if stdin_thread.is_alive():
            _close_stream(process.stdin)
            stdin_thread.join(timeout=_THREAD_JOIN_SECONDS)
        if stdin_thread.is_alive():
            capture_error.set()

    for thread, stream in (
        (stdout_thread, process.stdout),
        (stderr_thread, process.stderr),
    ):
        if thread in started_threads:
            thread.join(timeout=_THREAD_JOIN_SECONDS)
            if thread.is_alive():
                stopping.set()
                capture_error.set()
                _close_stream(stream)
                thread.join(timeout=_THREAD_JOIN_SECONDS)
            if thread.is_alive():
                stopped = False

    _close_stream(process.stdin)
    _close_stream(process.stdout)
    _close_stream(process.stderr)
    return _ProcessObservation(
        returncode=process.returncode,
        stdout=stdout_capture,
        stderr=stderr_capture,
        output_bytes=budget.observed_bytes,
        retained_output_bytes=budget.retained_bytes,
        stdin_bytes_written=stdin_state.byte_count,
        stdin_complete=stdin_state.complete,
        timed_out=timed_out,
        output_limit_exceeded=budget.exceeded.is_set(),
        capture_error=capture_error.is_set(),
        terminate_sent=terminate_sent,
        kill_sent=kill_sent,
        stopped=stopped,
        duration_seconds=max(0.0, time.monotonic() - started),
    )


def _control_clean(result: _ProcessObservation) -> bool:
    return (
        result.returncode == 0
        and result.stdin_complete
        and not result.timed_out
        and not result.output_limit_exceeded
        and not result.capture_error
        and result.stopped
    )


def _run_control(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    arguments: Sequence[str],
    timeout_seconds: float,
    stdin_payload: bytes | None = None,
) -> _ProcessObservation:
    return _run_process(
        runtime=runtime,
        runtime_parent=runtime_parent,
        expected_runtime_digest=expected_runtime_digest,
        trusted_cwd=trusted_cwd,
        arguments=arguments,
        timeout_seconds=timeout_seconds,
        output_byte_cap=_CONTROL_OUTPUT_BYTES,
        stdin_payload=stdin_payload,
    )


def _force_remove_container(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    container_reference: str,
) -> bool:
    try:
        _verify_runtime(runtime, runtime_parent, expected_runtime_digest)
        _verify_pin(trusted_cwd, "trusted host working directory")
        kwargs: dict[str, Any] = {
            "close_fds": True,
            "cwd": trusted_cwd.path,
            "env": {},
            "shell": False,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            [
                runtime.path,
                *_DOCKER_CONTEXT_ARGUMENTS,
                "container",
                "rm",
                "-f",
                container_reference,
            ],
            **kwargs,
        )
        try:
            process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            return False
        return process.returncode == 0
    except Exception:
        return False


def _decode_control_json(result: _ProcessObservation) -> object | None:
    if not _control_clean(result):
        return None
    try:
        return json.loads(bytes(result.stdout.retained).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _inspect_image_volumes(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    image_reference: str,
    control_timeout: float,
) -> None:
    result = _run_control(
        runtime=runtime,
        runtime_parent=runtime_parent,
        expected_runtime_digest=expected_runtime_digest,
        trusted_cwd=trusted_cwd,
        arguments=(
            "image",
            "inspect",
            "--format",
            "{{json .Config.Volumes}}",
            image_reference,
        ),
        timeout_seconds=control_timeout,
    )
    volumes = _decode_control_json(result)
    if volumes is None:
        stripped = bytes(result.stdout.retained).strip()
        if _control_clean(result) and stripped == b"null":
            return
        _refuse("container image configuration could not be inspected safely")
    if not isinstance(volumes, Mapping) or volumes:
        _refuse("container image declares writable volumes")


def _cpu_controls(quotas: Mapping[str, int]) -> tuple[int, int]:
    numerator = quotas["cpu_seconds"] * _CFS_PERIOD_US
    quota_us = numerator // quotas["wall_clock_seconds"]
    if quota_us < _CFS_MIN_QUOTA_US or quota_us > _MAX_SIGNED_QUOTA:
        _refuse("CPU quota cannot be represented safely by the container runtime")
    return _CFS_PERIOD_US, quota_us


def _writable_mount_budgets(quotas: Mapping[str, int]) -> tuple[int, int]:
    disk_bytes = quotas["disk_write_bytes"]
    if disk_bytes < 2:
        _refuse("disk quota cannot bound both tmpfs and shared memory")
    tmp_bytes = disk_bytes // 2
    return tmp_bytes, disk_bytes - tmp_bytes


def _container_create_arguments(
    *,
    container_name: str,
    image_reference: str,
    argv: Sequence[str],
    quotas: Mapping[str, int],
) -> tuple[str, ...]:
    cpu_period, cpu_quota = _cpu_controls(quotas)
    tmp_bytes, shm_bytes = _writable_mount_budgets(quotas)
    return (
        "container",
        "create",
        "--name",
        container_name,
        "--pull",
        "never",
        "--network",
        "none",
        "--restart",
        "no",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65532:65532",
        "--pids-limit",
        str(quotas["process_count"]),
        "--memory",
        f"{quotas['memory_bytes']}b",
        "--memory-swap",
        f"{quotas['memory_bytes']}b",
        "--memory-swappiness",
        "0",
        "--cpu-period",
        str(cpu_period),
        "--cpu-quota",
        str(cpu_quota),
        "--ulimit",
        f"cpu={quotas['cpu_seconds']}:{quotas['cpu_seconds']}",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={tmp_bytes},mode=1777",
        "--shm-size",
        f"{shm_bytes}b",
        "--ipc",
        "private",
        "--cgroupns",
        "private",
        "--no-healthcheck",
        "--workdir",
        _CANDIDATE_DIRECTORY,
        "--interactive",
        "--log-driver",
        "none",
        image_reference,
        *argv,
    )


def _create_container(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    arguments: Sequence[str],
    container_name: str,
    control_timeout: float,
) -> str:
    result = _run_control(
        runtime=runtime,
        runtime_parent=runtime_parent,
        expected_runtime_digest=expected_runtime_digest,
        trusted_cwd=trusted_cwd,
        arguments=arguments,
        timeout_seconds=control_timeout,
    )
    identifier = bytes(result.stdout.retained).decode("ascii", errors="ignore").strip()
    if _control_clean(result) and _CONTAINER_ID.fullmatch(identifier):
        return identifier
    cleanup_reference = identifier if _CONTAINER_ID.fullmatch(identifier) else container_name
    if (
        result.returncode == 0
        or result.timed_out
        or result.output_limit_exceeded
        or result.capture_error
    ):
        cleaned = _force_remove_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            container_reference=cleanup_reference,
        )
        if not cleaned:
            _refuse("container creation outcome could not be cleaned up safely")
    _refuse("container could not be created under a known identifier")


def _inspect_container(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    container_id: str,
    timeout_seconds: float,
) -> Mapping[str, Any] | None:
    try:
        result = _run_control(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            arguments=("container", "inspect", container_id),
            timeout_seconds=timeout_seconds,
        )
    except CandidateContainerRefused:
        return None
    payload = _decode_control_json(result)
    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], Mapping)
    ):
        return None
    return payload[0]


def _empty_sequence(value: object) -> bool:
    return value is None or value == [] or value == ()


def _validate_created_container(
    record: Mapping[str, Any],
    *,
    container_id: str,
    container_name: str,
    image_reference: str,
    quotas: Mapping[str, int],
) -> bool:
    host = record.get("HostConfig")
    config = record.get("Config")
    mounts = record.get("Mounts")
    if not isinstance(host, Mapping) or not isinstance(config, Mapping):
        return False
    if not isinstance(mounts, list):
        return False
    cpu_period, cpu_quota = _cpu_controls(quotas)
    tmp_bytes, shm_bytes = _writable_mount_budgets(quotas)
    if record.get("Id") != container_id or record.get("Name") != f"/{container_name}":
        return False
    if config.get("Image") != image_reference:
        return False
    if config.get("User") != "65532:65532" or config.get("WorkingDir") != _CANDIDATE_DIRECTORY:
        return False
    if config.get("OpenStdin") is not True:
        return False
    healthcheck = config.get("Healthcheck")
    if healthcheck is not None and (
        not isinstance(healthcheck, Mapping)
        or healthcheck.get("Test") != ["NONE"]
    ):
        return False
    declared_volumes = config.get("Volumes")
    if declared_volumes is not None and declared_volumes != {}:
        return False
    expected_scalars = {
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "Privileged": False,
        "PidsLimit": quotas["process_count"],
        "Memory": quotas["memory_bytes"],
        "MemorySwap": quotas["memory_bytes"],
        "MemorySwappiness": 0,
        "CpuPeriod": cpu_period,
        "CpuQuota": cpu_quota,
        "ShmSize": shm_bytes,
        "AutoRemove": False,
    }
    if any(host.get(key) != expected for key, expected in expected_scalars.items()):
        return False
    if (
        host.get("PidMode") != ""
        or host.get("IpcMode") != "private"
        or host.get("CgroupnsMode") != "private"
    ):
        return False
    restart_policy = host.get("RestartPolicy")
    if not isinstance(restart_policy, Mapping) or restart_policy.get("Name") not in (
        "",
        "no",
    ):
        return False
    if restart_policy.get("MaximumRetryCount") not in (0, None):
        return False
    if set(host.get("CapDrop") or ()) != {"ALL"} or not _empty_sequence(
        host.get("CapAdd")
    ):
        return False
    security_options = set(host.get("SecurityOpt") or ())
    if not any(option.startswith("no-new-privileges") for option in security_options):
        return False
    if not _empty_sequence(host.get("Devices")) or not _empty_sequence(
        host.get("DeviceRequests")
    ):
        return False
    if not _empty_sequence(host.get("Binds")) or not _empty_sequence(
        host.get("VolumesFrom")
    ):
        return False
    if host.get("PublishAllPorts") not in (False, None) or host.get("PortBindings") not in (
        None,
        {},
    ):
        return False
    log_config = host.get("LogConfig")
    if not isinstance(log_config, Mapping) or log_config.get("Type") != "none":
        return False
    tmpfs = host.get("Tmpfs")
    if not isinstance(tmpfs, Mapping) or set(tmpfs) != {"/tmp"}:
        return False
    tmp_options = set(str(tmpfs["/tmp"]).split(","))
    if not {
        "rw",
        "noexec",
        "nosuid",
        "nodev",
        f"size={tmp_bytes}",
        "mode=1777",
    }.issubset(tmp_options):
        return False
    ulimits = host.get("Ulimits")
    if not isinstance(ulimits, list):
        return False
    cpu_ulimits = [
        item
        for item in ulimits
        if isinstance(item, Mapping) and item.get("Name") == "cpu"
    ]
    if len(cpu_ulimits) != 1 or cpu_ulimits[0].get("Soft") != quotas[
        "cpu_seconds"
    ] or cpu_ulimits[0].get("Hard") != quotas["cpu_seconds"]:
        return False
    for mount in mounts:
        if not isinstance(mount, Mapping):
            return False
        if mount.get("Type") in {"bind", "volume"}:
            return False
        if mount.get("Type") != "tmpfs" or mount.get("Destination") not in {
            "/tmp",
            "/dev/shm",
        }:
            return False
        if mount.get("RW") is not True:
            return False
    return True


def _populate_container(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    container_id: str,
    tar_payload: bytes,
    control_timeout: float,
) -> None:
    result = _run_control(
        runtime=runtime,
        runtime_parent=runtime_parent,
        expected_runtime_digest=expected_runtime_digest,
        trusted_cwd=trusted_cwd,
        arguments=(
            "container",
            "cp",
            "-",
            f"{container_id}:{_CANDIDATE_DIRECTORY}",
        ),
        timeout_seconds=control_timeout,
        stdin_payload=tar_payload,
    )
    if not _control_clean(result):
        _refuse("stopped read-only container could not be populated safely")


def _bounded_redacted_text(payload: bytes, host_paths: Sequence[str]) -> str:
    text = payload.decode("utf-8", errors="replace")
    variants: set[str] = set()
    for path in host_paths:
        if path:
            variants.update(
                {
                    path,
                    path.replace("\\", "/"),
                    path.replace("/", "\\"),
                    path.replace("\\", "\\\\"),
                }
            )
    flags = re.IGNORECASE if os.name == "nt" else 0
    for path in sorted(variants, key=len, reverse=True):
        text = re.sub(re.escape(path), "<host-path>", text, flags=flags)
    maximum = len(payload)
    encoded = text.encode("utf-8")
    if len(encoded) > maximum:
        text = encoded[:maximum].decode("utf-8", errors="ignore")
    return text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _quota_exceeded(observations: Mapping[str, bool | None]) -> bool | None:
    values = tuple(observations.values())
    if any(value is True for value in values):
        return True
    if all(value is False for value in values):
        return False
    return None


def _container_state(
    record: Mapping[str, Any] | None,
) -> tuple[int | None, bool | None, bool | None, bool]:
    if record is None:
        return None, None, None, True
    state = record.get("State")
    if not isinstance(state, Mapping):
        return None, None, None, True
    running = state.get("Running")
    oom_killed = state.get("OOMKilled")
    exit_code = state.get("ExitCode")
    container_status = state.get("Status")
    if (
        not isinstance(running, bool)
        or not isinstance(oom_killed, bool)
        or not isinstance(container_status, str)
    ):
        return None, None, None, True
    if running:
        observed_exit = None
    elif container_status in {"exited", "dead"} and isinstance(
        exit_code, int
    ) and not isinstance(exit_code, bool):
        observed_exit = exit_code
    else:
        observed_exit = None
    state_error = state.get("Error")
    observation_error = (
        not isinstance(state_error, str)
        or bool(state_error)
        or (not running and observed_exit is None)
    )
    return observed_exit, running, oom_killed, observation_error


def _container_name(
    *,
    factory_fingerprint: str,
    candidate_artifact_id: str,
    candidate_tar_digest: str,
    authority: _ExecutionAuthority,
    image_digest: str,
    argv: Sequence[str],
    stdin_payload: bytes,
) -> str:
    payload = json.dumps(
        {
            "argv": list(argv),
            "authority": authority.authority_id,
            "candidate": candidate_artifact_id,
            "candidate_tar": candidate_tar_digest,
            "factory": factory_fingerprint,
            "fence": authority.current_fencing_token,
            "image": image_digest,
            "lease": authority.lease["lease_id"],
            "profile": authority.profile["profile_id"],
            "stdin": f"sha256:{hashlib.sha256(stdin_payload).hexdigest()}",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"efc-{hashlib.sha256(payload).hexdigest()[:48]}"


def _execute_container(
    *,
    runtime: _PathPin,
    runtime_parent: _PathPin,
    expected_runtime_digest: str,
    trusted_cwd: _PathPin,
    image_reference: str,
    image_digest: str,
    argv: Sequence[str],
    stdin_payload: bytes,
    stdin_byte_cap: int,
    output_byte_cap: int,
    tar_payload: bytes,
    quotas: Mapping[str, int],
    container_name: str,
) -> dict[str, Any]:
    control_timeout = min(
        _CONTROL_TIMEOUT_SECONDS, float(quotas["wall_clock_seconds"])
    )
    _inspect_image_volumes(
        runtime=runtime,
        runtime_parent=runtime_parent,
        expected_runtime_digest=expected_runtime_digest,
        trusted_cwd=trusted_cwd,
        image_reference=image_reference,
        control_timeout=control_timeout,
    )
    container_id = _create_container(
        runtime=runtime,
        runtime_parent=runtime_parent,
        expected_runtime_digest=expected_runtime_digest,
        trusted_cwd=trusted_cwd,
        arguments=_container_create_arguments(
            container_name=container_name,
            image_reference=image_reference,
            argv=argv,
            quotas=quotas,
        ),
        container_name=container_name,
        control_timeout=control_timeout,
    )
    cleanup_attempted = False
    cleanup_failed = False
    try:
        created = _inspect_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            container_id=container_id,
            timeout_seconds=control_timeout,
        )
        if created is None or not _validate_created_container(
            created,
            container_id=container_id,
            container_name=container_name,
            image_reference=image_reference,
            quotas=quotas,
        ):
            _refuse("created container did not preserve zero-mount isolation")
        _populate_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            container_id=container_id,
            tar_payload=tar_payload,
            control_timeout=control_timeout,
        )
        populated = _inspect_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            container_id=container_id,
            timeout_seconds=control_timeout,
        )
        if populated is None or not _validate_created_container(
            populated,
            container_id=container_id,
            container_name=container_name,
            image_reference=image_reference,
            quotas=quotas,
        ):
            _refuse("populated container did not preserve zero-mount isolation")

        started_at = _utc_now()
        started_monotonic = time.monotonic()
        try:
            process = _run_process(
                runtime=runtime,
                runtime_parent=runtime_parent,
                expected_runtime_digest=expected_runtime_digest,
                trusted_cwd=trusted_cwd,
                arguments=("container", "start", "--attach", "--interactive", container_id),
                timeout_seconds=float(quotas["wall_clock_seconds"]),
                output_byte_cap=output_byte_cap,
                stdin_payload=stdin_payload,
            )
        except CandidateContainerRefused:
            cleanup_attempted = True
            cleanup_failed = not _force_remove_container(
                runtime=runtime,
                runtime_parent=runtime_parent,
                expected_runtime_digest=expected_runtime_digest,
                trusted_cwd=trusted_cwd,
                container_reference=container_id,
            )
            if cleanup_failed:
                _refuse("container launch failed and daemon cleanup was not confirmed")
            _refuse("container candidate could not be launched safely")

        state_record = _inspect_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            container_id=container_id,
            timeout_seconds=min(control_timeout, _STATE_INSPECT_TIMEOUT_SECONDS),
        )
        exit_code, running, oom_killed, state_error = _container_state(state_record)
        cleanup_attempted = True
        cleanup_failed = not _force_remove_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_digest,
            trusted_cwd=trusted_cwd,
            container_reference=container_id,
        )
        finished_monotonic = time.monotonic()
        finished_at = _utc_now()

        forced_stop = (
            process.timed_out
            or process.output_limit_exceeded
            or process.capture_error
            or process.terminate_sent
            or process.kill_sent
        )
        if not forced_stop and running is not False:
            state_error = True
        elapsed = max(0.0, finished_monotonic - started_monotonic)
        if process.timed_out:
            wall_observation: bool | None = True
        elif running is False and exit_code is not None:
            wall_observation = False
        elif forced_stop and not cleanup_failed and elapsed < quotas["wall_clock_seconds"]:
            wall_observation = False
        else:
            wall_observation = None
        quota_observations: dict[str, bool | None] = {
            "wall_clock_seconds": wall_observation,
            "cpu_seconds": None,
            "memory_bytes": True if oom_killed is True else None,
            "disk_write_bytes": None,
            "process_count": None,
        }
        quota_exceeded = _quota_exceeded(quota_observations)
        observation_error = (
            process.capture_error
            or not process.stopped
            or state_record is None
            or state_error
            or cleanup_failed
        )
        if observation_error:
            status = "OBSERVATION_ERROR"
        elif process.output_limit_exceeded:
            status = "OUTPUT_LIMIT_EXCEEDED"
        elif process.timed_out:
            status = "TIMED_OUT"
        elif quota_exceeded is True:
            status = "QUOTA_EXCEEDED"
        else:
            status = "EXITED"

        host_paths = (runtime.path, runtime_parent.path, trusted_cwd.path)
        return {
            "status": status,
            "exit_code": exit_code,
            "timed_out": process.timed_out,
            "quota_exceeded": quota_exceeded,
            "quota_observations": quota_observations,
            "output_limit_exceeded": process.output_limit_exceeded,
            "capture_error": process.capture_error,
            "state_observation_error": state_record is None or state_error,
            "terminate_sent": process.terminate_sent,
            "kill_sent": process.kill_sent,
            "daemon_cleanup_attempted": cleanup_attempted,
            "daemon_cleanup_failed": cleanup_failed,
            "container_running_when_observed": running,
            "stdin_bytes": len(stdin_payload),
            "stdin_bytes_written": process.stdin_bytes_written,
            "stdin_byte_cap": stdin_byte_cap,
            "stdout": _bounded_redacted_text(bytes(process.stdout.retained), host_paths),
            "stderr": _bounded_redacted_text(bytes(process.stderr.retained), host_paths),
            "stdout_bytes": process.stdout.byte_count,
            "stderr_bytes": process.stderr.byte_count,
            "output_bytes": process.output_bytes,
            "retained_output_bytes": process.retained_output_bytes,
            "output_byte_cap": output_byte_cap,
            "stdout_truncated": process.stdout.truncated,
            "stderr_truncated": process.stderr.truncated,
            "stdout_sha256": f"sha256:{process.stdout.digest.hexdigest()}",
            "stderr_sha256": f"sha256:{process.stderr.digest.hexdigest()}",
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": elapsed,
            "image_digest": image_digest,
        }
    except Exception as error:
        if not cleanup_attempted:
            cleanup_attempted = True
            cleanup_failed = not _force_remove_container(
                runtime=runtime,
                runtime_parent=runtime_parent,
                expected_runtime_digest=expected_runtime_digest,
                trusted_cwd=trusted_cwd,
                container_reference=container_id,
            )
        if cleanup_failed:
            raise CandidateContainerRefused(
                "container lifecycle failed and daemon cleanup was not confirmed"
            ) from None
        if isinstance(error, CandidateContainerRefused):
            raise
        raise CandidateContainerRefused("container lifecycle failed closed") from None


def create_candidate_container_executor(
    *,
    runtime_executable: str | os.PathLike[str],
    trusted_runtime_parent: str | os.PathLike[str],
    expected_runtime_sha256: str,
    trusted_host_cwd: str | os.PathLike[str],
    resolve_candidate_artifact: Callable[[str], Mapping[str, Any]],
    resolve_execution_authority: Callable[[str], Mapping[str, Any]],
    trusted_candidate_artifact_byte_cap: int,
    trusted_stdin_byte_cap: int,
    trusted_output_byte_cap: int,
) -> Callable[..., dict[str, Any]]:
    """Create an executor whose candidate and authority inputs are resolver-owned."""

    if not isinstance(expected_runtime_sha256, str) or not _SHA256.fullmatch(
        expected_runtime_sha256
    ):
        _refuse("expected runtime digest must use sha256:<64 lowercase hex>")
    candidate_cap = _positive_integer(
        trusted_candidate_artifact_byte_cap,
        "trusted candidate artifact byte cap",
    )
    stdin_cap = _positive_integer(trusted_stdin_byte_cap, "trusted stdin byte cap")
    output_cap = _positive_integer(trusted_output_byte_cap, "trusted output byte cap")
    candidate_resolver = _trusted_resolver(
        resolve_candidate_artifact, "candidate artifact"
    )
    authority_resolver = _trusted_resolver(
        resolve_execution_authority, "execution authority"
    )
    runtime_parent = _pin_existing_path(
        trusted_runtime_parent, label="trusted runtime parent"
    )
    runtime = _pin_existing_path(
        runtime_executable, label="container runtime", executable=True
    )
    trusted_cwd = _pin_existing_path(
        trusted_host_cwd, label="trusted host working directory"
    )
    if not _is_within(runtime.path, runtime_parent.path):
        _refuse("container runtime must be below its trusted parent")
    _verify_runtime(runtime, runtime_parent, expected_runtime_sha256)

    fingerprint_payload = json.dumps(
        {
            "candidate_cap": candidate_cap,
            "cwd": trusted_cwd.path,
            "output_cap": output_cap,
            "runtime": expected_runtime_sha256,
            "stdin_cap": stdin_cap,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    factory_fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()

    def execute_candidate(
        *,
        candidate_artifact_id: str,
        execution_authority_id: str,
        image_reference: str,
        argv: Sequence[str],
        stdin_text: str = "",
        network_requested: bool = False,
    ) -> dict[str, Any]:
        candidate_id = _require_id(candidate_artifact_id, "candidate_artifact_id")
        authority_id = _require_id(
            execution_authority_id, "execution_authority_id"
        )
        image, image_digest = _parse_image_reference(image_reference)
        command_argv = _require_argv(argv)
        if not isinstance(stdin_text, str):
            _refuse("stdin_text must be a UTF-8 string")
        try:
            stdin_payload = stdin_text.encode("utf-8")
        except UnicodeEncodeError:
            _refuse("stdin_text must be a UTF-8 string")
        if len(stdin_payload) > stdin_cap:
            _refuse("stdin_text exceeds the trusted adapter byte cap")
        if not isinstance(network_requested, bool):
            _refuse("network_requested must be a boolean")

        authority = _snapshot_execution_authority(
            _resolve_sync(authority_resolver, authority_id, "execution authority"),
            authority_id=authority_id,
        )
        if authority.profile["network_policy"] != "DENY_ALL":
            _refuse("candidate container execution requires a DENY_ALL network policy")
        if network_requested or "network" in authority.requested_capabilities:
            _refuse("candidate container execution refuses requested network access")
        candidate = _snapshot_candidate_artifact(
            _resolve_sync(candidate_resolver, candidate_id, "candidate artifact"),
            expected_artifact_id=candidate_id,
            trusted_byte_cap=candidate_cap,
            disk_byte_cap=authority.quotas["disk_write_bytes"],
        )
        _permission_guard(authority, candidate.reachable_resource_ids)
        tar_payload, tar_digest = _build_candidate_tar(
            candidate,
            trusted_byte_cap=candidate_cap,
        )

        _verify_runtime(runtime, runtime_parent, expected_runtime_sha256)
        _verify_pin(trusted_cwd, "trusted host working directory")
        name = _container_name(
            factory_fingerprint=factory_fingerprint,
            candidate_artifact_id=candidate.artifact_id,
            candidate_tar_digest=tar_digest,
            authority=authority,
            image_digest=image_digest,
            argv=command_argv,
            stdin_payload=stdin_payload,
        )
        return _execute_container(
            runtime=runtime,
            runtime_parent=runtime_parent,
            expected_runtime_digest=expected_runtime_sha256,
            trusted_cwd=trusted_cwd,
            image_reference=image,
            image_digest=image_digest,
            argv=command_argv,
            stdin_payload=stdin_payload,
            stdin_byte_cap=stdin_cap,
            output_byte_cap=output_cap,
            tar_payload=tar_payload,
            quotas=authority.quotas,
            container_name=name,
        )

    return execute_candidate
