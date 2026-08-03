#!/usr/bin/env python3
"""Execute the B04 canonical-registry packaging acceptance contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

EXPECTED_SCHEMA_COUNT = 127
EXPECTED_RESOURCE_COUNT = 128
EXPECTED_PROJECTION_FILE_COUNT = 129
EXPECTED_BUILD_BACKEND = "setuptools"
EXPECTED_BUILD_BACKEND_VERSION = "82.0.1"
EXPECTED_BUILD_REQUIREMENT = "setuptools==82.0.1"
REGISTRY_SCHEMA_VERSION = 2
REGISTRY_FORMAT_VERSION = "2.0.0"
PROJECTION_TOOL_IDENTITY = "epistemic_foundry.canonical_registry.materialize"
PROJECTION_TOOL_VERSION = "2.0.0"
SOURCE_REVISION_KIND = "canonical_source_bundle_sha256"
WHEEL_CANONICAL_PREFIX = PurePosixPath("epistemic_foundry/_canonical")
SDIST_CANONICAL_PREFIX = PurePosixPath("src/epistemic_foundry/_canonical")
HISTORICAL_B04_HASHES = {
    "build-smoke.json": "e9184f3d59b1b7b1d90cfc5ff5b418038a1fb6058fab3b369b325488befc2591",
    "commands.jsonl": "77d10bbf83fb9b734f9a5e6767e7c8a1579ca83964d7df36365006de85c80102",
    "reconciliation.json": "73b9671d6622a42e892e4aab7f4b29b171d3da7b46f42bb818230cc22001e258",
    "report.json": "3b239d90f30257ef79e95caedbeb5d2b020e34710b4ddac3d5ebb07e981d775a",
    "review.md": "5c32fb9c7e811d23ee569bd3202a2176137202e073ef5d357fa72f3de33a819d",
}


class PackagingVerificationError(RuntimeError):
    """A non-waivable B04 packaging acceptance failure."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize(value: str, replacements: list[tuple[str, str]]) -> str:
    normalized = value
    for source, replacement in replacements:
        normalized = normalized.replace(source, replacement)
        normalized = normalized.replace(source.replace("\\", "/"), replacement)
    return normalized


def run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    replacements: list[tuple[str, str]],
    timeout: int = 300,
) -> dict[str, Any]:
    executable = shutil.which(command[0], path=environment.get("PATH"))
    if executable is None:
        raise PackagingVerificationError(
            f"required executable is not on PATH: {command[0]}"
        )
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    recorded_command = [
        _normalize(part, replacements) for part in command
    ]
    if completed.returncode != 0:
        detail = _normalize(
            (completed.stderr or completed.stdout).strip(), replacements
        )
        raise PackagingVerificationError(
            f"command failed ({completed.returncode}): "
            f"{' '.join(recorded_command)}\n{detail[-8000:]}"
        )
    return {
        "command": recorded_command,
        "exit_code": completed.returncode,
    }


def _ignore_source(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in {"__pycache__", ".pytest_cache", "build", "dist"}
        or name.endswith((".egg-info", ".pyc", ".pyo"))
    }
    return ignored


def stage_source(root: Path, destination: Path) -> str:
    destination.mkdir(parents=True, exist_ok=False)
    for relative in ("README.md", "pyproject.toml"):
        shutil.copy2(root / relative, destination / relative)

    directories = (
        "src/epistemic_foundry",
        "scripts/build/canonical_registry",
        "schemas",
        "openapi",
    )
    for relative in directories:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root / relative, target, ignore=_ignore_source)

    constraints = destination / "toolchains" / "python-build-constraints.txt"
    constraints.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "toolchains" / "python-build-constraints.txt", constraints)
    shutil.copy2(
        root / "toolchains" / "toolchain-lock.json",
        destination / "toolchains" / "toolchain-lock.json",
    )

    digest = hashlib.sha256()
    for path in sorted(
        (path for path in destination.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(destination).as_posix(),
    ):
        relative = path.relative_to(destination).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_distribution(
    source: Path,
    output: Path,
    *,
    environment: dict[str, str],
    replacements: list[tuple[str, str]],
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    command = [
        "uv",
        "build",
        "--sdist",
        "--wheel",
        "--build-constraints",
        str(source / "toolchains" / "python-build-constraints.txt"),
        "--require-hashes",
        "--no-python-downloads",
        "--no-build-logs",
        "--out-dir",
        str(output),
        str(source),
    ]
    command_result = run_command(
        command,
        cwd=source,
        environment=environment,
        replacements=replacements,
    )
    wheels = sorted(output.glob("*.whl"))
    sdists = sorted(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise PackagingVerificationError(
            f"expected one wheel and one sdist, found {len(wheels)} and {len(sdists)}"
        )
    return {
        "command": command_result,
        "wheel": wheels[0],
        "sdist": sdists[0],
    }


def build_from_sdist(
    extracted_sdist: Path,
    constraints: Path,
    output: Path,
    *,
    environment: dict[str, str],
    replacements: list[tuple[str, str]],
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    command = [
        "uv",
        "build",
        "--wheel",
        "--build-constraints",
        str(constraints),
        "--require-hashes",
        "--no-python-downloads",
        "--no-build-logs",
        "--out-dir",
        str(output),
        str(extracted_sdist),
    ]
    command_result = run_command(
        command,
        cwd=output.parent,
        environment=environment,
        replacements=replacements,
    )
    wheels = sorted(output.glob("*.whl"))
    if len(wheels) != 1:
        raise PackagingVerificationError(
            f"expected one sdist-derived wheel, found {len(wheels)}"
        )
    return {"command": command_result, "wheel": wheels[0]}


def _safe_destination(root: Path, member_name: str) -> Path:
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in member_name:
        raise PackagingVerificationError(f"unsafe archive path: {member_name}")
    destination = root.joinpath(*relative.parts).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise PackagingVerificationError(f"archive path escapes root: {member_name}")
    return destination


def extract_wheel(wheel: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(wheel) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise PackagingVerificationError(f"wheel CRC failure: {bad}")
        seen: set[str] = set()
        for info in archive.infolist():
            _safe_destination(destination, info.filename)
            if info.filename in seen:
                raise PackagingVerificationError(
                    f"wheel contains a duplicate member: {info.filename}"
                )
            seen.add(info.filename)
            unix_type = (info.external_attr >> 16) & 0o170000
            if unix_type == 0o120000:
                raise PackagingVerificationError(
                    f"wheel contains a symlink: {info.filename}"
                )
        archive.extractall(destination)


def extract_sdist(sdist: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        seen: set[str] = set()
        roots: set[str] = set()
        for member in members:
            _safe_destination(destination, member.name)
            path = PurePosixPath(member.name)
            if member.name in seen:
                raise PackagingVerificationError(
                    f"sdist contains a duplicate member: {member.name}"
                )
            seen.add(member.name)
            roots.add(path.parts[0])
            if member.issym() or member.islnk():
                raise PackagingVerificationError(
                    f"sdist contains a link: {member.name}"
                )
            if not (member.isfile() or member.isdir()):
                raise PackagingVerificationError(
                    f"sdist contains a special member: {member.name}"
                )
            if len(path.parts) == 1 and not member.isdir():
                raise PackagingVerificationError(
                    f"sdist contains a root-level file: {member.name}"
                )
        if len(roots) != 1:
            raise PackagingVerificationError(
                f"sdist members do not share exactly one root: {sorted(roots)}"
            )
        archive.extractall(destination, filter="data")
    extracted_roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(extracted_roots) != 1 or len(list(destination.iterdir())) != 1:
        raise PackagingVerificationError(
            "expected exactly one extracted sdist root directory"
        )
    return extracted_roots[0]


def backend_contract_evidence(root: Path, sdist_root: Path) -> dict[str, Any]:
    """Prove that source and sdist use the same exact, hashed backend pin."""

    def build_requirements(source_root: Path) -> list[str]:
        try:
            pyproject = tomllib.loads(
                (source_root / "pyproject.toml").read_text(encoding="utf-8")
            )
            requirements = pyproject["build-system"]["requires"]
            backend = pyproject["build-system"]["build-backend"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
            raise PackagingVerificationError(
                f"cannot read build-system contract from {source_root.name}"
            ) from error
        if requirements != [EXPECTED_BUILD_REQUIREMENT]:
            raise PackagingVerificationError(
                "build-system.requires is not the exact approved backend pin: "
                f"{requirements!r}"
            )
        if backend != "setuptools.build_meta":
            raise PackagingVerificationError(
                f"approved setuptools backend was replaced: {backend!r}"
            )
        return requirements

    source_requirements = build_requirements(root)
    sdist_requirements = build_requirements(sdist_root)
    source_constraints = root / "toolchains/python-build-constraints.txt"
    sdist_constraints = sdist_root / "toolchains/python-build-constraints.txt"
    if not source_constraints.is_file() or not sdist_constraints.is_file():
        raise PackagingVerificationError(
            "source or sdist build-backend constraint file is missing"
        )
    source_constraint_bytes = source_constraints.read_bytes()
    sdist_constraint_bytes = sdist_constraints.read_bytes()
    if source_constraint_bytes != sdist_constraint_bytes:
        raise PackagingVerificationError(
            "sdist build-backend constraints differ from source authority"
        )
    active_lines = [
        line.strip()
        for line in source_constraint_bytes.decode("utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not active_lines or active_lines[0] != EXPECTED_BUILD_REQUIREMENT + " \\":
        raise PackagingVerificationError(
            "hashed backend constraint does not begin with the exact approved pin"
        )
    lock_path = root / "toolchains/toolchain-lock.json"
    sdist_lock_path = sdist_root / "toolchains/toolchain-lock.json"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        sdist_lock = json.loads(sdist_lock_path.read_text(encoding="utf-8"))
        backend_lock = lock["python_build_backend"]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise PackagingVerificationError("build-backend lock is unreadable") from error
    if lock != sdist_lock:
        raise PackagingVerificationError("sdist toolchain lock differs from source")
    if backend_lock != {
        "name": EXPECTED_BUILD_BACKEND,
        "version": EXPECTED_BUILD_BACKEND_VERSION,
        "constraints": "toolchains/python-build-constraints.txt",
    }:
        raise PackagingVerificationError(
            f"toolchain lock does not match approved backend: {backend_lock!r}"
        )
    constraint_hash = sha256_bytes(source_constraint_bytes)
    return {
        "build_backend": "setuptools.build_meta",
        "constraint_sha256": constraint_hash,
        "exact_requirement": source_requirements[0],
        "name": EXPECTED_BUILD_BACKEND,
        "sdist_constraint_embedded": True,
        "sdist_constraint_sha256": sha256_bytes(sdist_constraint_bytes),
        "sdist_exact_requirement": sdist_requirements[0],
        "source_sdist_constraint_byte_equal": True,
        "version": EXPECTED_BUILD_BACKEND_VERSION,
    }


def authority_resources(root: Path) -> dict[str, bytes]:
    schemas = sorted((root / "schemas").glob("*.schema.json"))
    if len(schemas) != EXPECTED_SCHEMA_COUNT:
        raise PackagingVerificationError(
            f"expected {EXPECTED_SCHEMA_COUNT} source schemas, found {len(schemas)}"
        )
    resources = {
        f"schemas/{path.name}": path.read_bytes() for path in schemas
    }
    openapi = root / "openapi" / "epistemic-foundry-v1.openapi.yaml"
    if not openapi.is_file():
        raise PackagingVerificationError("canonical OpenAPI source is missing")
    resources["openapi/epistemic-foundry-v1.openapi.yaml"] = openapi.read_bytes()
    return resources


def _canonical_json_hash(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def source_bundle_hash(resources: list[tuple[str, str, bytes]]) -> str:
    entries = [
        {
            "path": source_path,
            "sha256": "sha256:" + sha256_bytes(content),
            "size": len(content),
            "target_path": package_path,
        }
        for source_path, package_path, content in sorted(
            resources, key=lambda item: item[0]
        )
    ]
    return _canonical_json_hash({"algorithm": "sha256", "entries": entries})


def bundle_hash(resources: dict[str, bytes]) -> str:
    return source_bundle_hash(
        [(path, path, content) for path, content in resources.items()]
    )


def projected_snapshot_bundle_hash(resources: dict[str, bytes]) -> str:
    entries = [
        {
            "byte_size": len(content),
            "path": package_path,
            "sha256": "sha256:" + sha256_bytes(content),
            "target_path": package_path,
        }
        for package_path, content in sorted(resources.items())
    ]
    return _canonical_json_hash({"algorithm": "sha256", "entries": entries})


def snapshot_resources(bundle_root: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    registry_path = bundle_root / "canonical-registry.json"
    if not registry_path.is_file():
        raise PackagingVerificationError(
            f"canonical registry is missing under {bundle_root.name}"
        )
    try:
        manifest = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PackagingVerificationError("canonical registry is invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get(
        "schema_version"
    ) != REGISTRY_SCHEMA_VERSION:
        raise PackagingVerificationError("canonical registry is not schema v2")
    required_top_level = {
        "build_epoch",
        "build_source_revision",
        "build_source_revision_kind",
        "bundle_version",
        "file_count",
        "generated_at",
        "openapi_document_count",
        "projected_snapshot_bundle_hash",
        "projection_tool_identity",
        "projection_tool_version",
        "registry_format_version",
        "resource_count",
        "resources",
        "schema_count",
        "schema_version",
        "source_bundle_hash",
        "source_revision",
        "source_revision_kind",
    }
    missing_top_level = sorted(required_top_level - set(manifest))
    if missing_top_level:
        raise PackagingVerificationError(
            f"canonical registry fields are missing: {missing_top_level}"
        )
    entries = manifest.get("resources")
    if not isinstance(entries, list) or len(entries) != EXPECTED_RESOURCE_COUNT:
        raise PackagingVerificationError(
            f"expected {EXPECTED_RESOURCE_COUNT} registry resources"
        )
    if (
        manifest.get("resource_count") != EXPECTED_RESOURCE_COUNT
        or manifest.get("file_count") != EXPECTED_RESOURCE_COUNT
    ):
        raise PackagingVerificationError("registry file/resource count is inconsistent")
    if manifest.get("schema_count") != EXPECTED_SCHEMA_COUNT:
        raise PackagingVerificationError("registry schema_count is inconsistent")
    if manifest.get("openapi_document_count") != 1:
        raise PackagingVerificationError("registry OpenAPI count is inconsistent")
    if (
        manifest.get("registry_format_version") != REGISTRY_FORMAT_VERSION
        or manifest.get("projection_tool_identity") != PROJECTION_TOOL_IDENTITY
        or manifest.get("projection_tool_version") != PROJECTION_TOOL_VERSION
    ):
        raise PackagingVerificationError(
            "registry format or projection tool identity is inconsistent"
        )
    if (
        manifest.get("build_source_revision_kind") != SOURCE_REVISION_KIND
        or manifest.get("source_revision_kind") != SOURCE_REVISION_KIND
        or manifest.get("build_source_revision")
        != manifest.get("source_bundle_hash")
        or manifest.get("source_revision") != manifest.get("source_bundle_hash")
    ):
        raise PackagingVerificationError(
            "registry source revisions are not content-bound"
        )

    resources: dict[str, bytes] = {}
    identifiers: set[str] = set()
    source_paths: set[str] = set()
    source_bindings: list[tuple[str, str, bytes]] = []
    schema_count = 0
    openapi_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise PackagingVerificationError("registry resource is not an object")
        relative_path = entry.get("relative_path")
        source_path = entry.get("source_path")
        package_path = entry.get("package_path")
        document_id = entry.get("document_id")
        if not all(
            isinstance(value, str)
            for value in (relative_path, source_path, package_path, document_id)
        ):
            raise PackagingVerificationError("registry path or document ID is invalid")
        if relative_path != package_path:
            raise PackagingVerificationError(
                "registry relative_path is not bound to package_path"
            )
        path = PurePosixPath(package_path)
        source = PurePosixPath(source_path)
        if (
            path.is_absolute()
            or source.is_absolute()
            or ".." in path.parts
            or ".." in source.parts
            or "." in path.parts
            or "." in source.parts
            or "\\" in package_path
            or "\\" in source_path
            or package_path in resources
            or source_path in source_paths
        ):
            raise PackagingVerificationError(
                f"unsafe or duplicate registry path: {source_path} -> {package_path}"
            )
        source_paths.add(source_path)
        if document_id in identifiers:
            raise PackagingVerificationError(
                f"duplicate canonical document ID: {document_id}"
            )
        identifiers.add(document_id)
        resource_path = bundle_root.joinpath(*path.parts)
        if not resource_path.is_file():
            raise PackagingVerificationError(
                f"registered resource is missing: {relative_path}"
            )
        content = resource_path.read_bytes()
        if entry.get("byte_size") != len(content):
            raise PackagingVerificationError(
                f"byte-size mismatch: {relative_path}"
            )
        if entry.get("sha256") != "sha256:" + sha256_bytes(content):
            raise PackagingVerificationError(f"hash mismatch: {relative_path}")
        if entry.get("kind") == "json_schema":
            schema_count += 1
            if entry.get("media_type") != "application/schema+json":
                raise PackagingVerificationError(
                    f"packaged schema media type mismatch: {relative_path}"
                )
            try:
                document = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PackagingVerificationError(
                    f"packaged schema is invalid JSON: {relative_path}"
                ) from error
            if document.get("$id") != document_id:
                raise PackagingVerificationError(
                    f"packaged schema ID mismatch: {relative_path}"
                )
        elif entry.get("kind") == "openapi":
            openapi_count += 1
            if (
                entry.get("media_type") != "application/vnd.oai.openapi"
                or not content.startswith(b"openapi: 3.1.1\n")
            ):
                raise PackagingVerificationError(
                    f"packaged OpenAPI metadata mismatch: {relative_path}"
                )
        else:
            raise PackagingVerificationError(
                f"unknown registry resource kind: {entry.get('kind')!r}"
            )
        resources[relative_path] = content
        source_bindings.append((source_path, package_path, content))

    if schema_count != EXPECTED_SCHEMA_COUNT or openapi_count != 1:
        raise PackagingVerificationError(
            "registry resource kinds do not match canonical counts"
        )

    actual_files = {
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_file()
    }
    expected_files = set(resources) | {"canonical-registry.json"}
    if actual_files != expected_files:
        raise PackagingVerificationError(
            "packaged canonical inventory differs from registry: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
    if len(actual_files) != EXPECTED_PROJECTION_FILE_COUNT:
        raise PackagingVerificationError("canonical projection file count is wrong")
    if manifest.get("source_bundle_hash") != source_bundle_hash(source_bindings):
        raise PackagingVerificationError("source bundle hash mismatch")
    if manifest.get(
        "projected_snapshot_bundle_hash"
    ) != projected_snapshot_bundle_hash(resources):
        raise PackagingVerificationError("projected snapshot bundle hash mismatch")
    return resources, manifest


def compare_resource_sets(
    expected: dict[str, bytes], actual: dict[str, bytes], label: str
) -> dict[str, Any]:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = sorted(
        path
        for path in set(expected) & set(actual)
        if expected[path] != actual[path]
    )
    if missing or extra or mismatches:
        raise PackagingVerificationError(
            f"{label} divergence: missing={missing}, extra={extra}, "
            f"hash_mismatches={mismatches}"
        )
    return {
        "extra": 0,
        "hash_mismatches": 0,
        "missing": 0,
        "resource_count": len(actual),
        "status": "PASS",
    }


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def installed_wheel_checks(
    wheel: Path,
    root: Path,
    temporary_root: Path,
    *,
    environment: dict[str, str],
    replacements: list[tuple[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    commands: list[dict[str, Any]] = []
    venv = temporary_root / "installed-venv"
    commands.append(
        run_command(
            [sys.executable, "-m", "venv", str(venv)],
            cwd=temporary_root,
            environment=environment,
            replacements=replacements,
        )
    )
    python = _venv_python(venv)
    commands.append(
        run_command(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--offline",
                "--no-python-downloads",
                str(wheel),
            ],
            cwd=temporary_root,
            environment=environment,
            replacements=replacements,
        )
    )

    empty_cwd = temporary_root / "arbitrary-empty-cwd"
    empty_cwd.mkdir()
    smoke_script = temporary_root / "installed_smoke.py"
    smoke_script.write_text(
        """from __future__ import annotations
import json
import sys
from pathlib import Path
import epistemic_foundry
from epistemic_foundry.contracts import default_registry, validate_artifact

payload = {
    "intent_id": "INTENT-B04-1",
    "run_id": "RUN-B04-1",
    "node_id": "installed_wheel_validation",
    "action_type": "validate_contract",
    "target_ref": "canonical/action-intent",
    "arguments_artifact_id": "ART-B04-ARGS",
    "arguments_hash": "sha256:" + "a" * 64,
    "idempotency_key": "B04:installed-wheel:1",
    "required_capabilities": ["contract:read"],
    "approval_record_ids": [],
    "risk_class": "read_only",
    "created_at": "2026-01-01T00:00:00Z",
    "intent_hash": "sha256:" + "b" * 64,
}
registry = default_registry()
validate_artifact("action-intent", payload, registry=registry)
print(json.dumps({
    "module_file": str(Path(epistemic_foundry.__file__).resolve()),
    "schema_count": len(registry.names()),
    "resource_count": registry.manifest["resource_count"],
    "openapi_3_1_1": registry.openapi_text().startswith("openapi: 3.1.1\\n"),
    "source_tree_paths": [item for item in sys.path if "Epistemic-Foundry" in item],
}, sort_keys=True))
""",
        encoding="utf-8",
        newline="\n",
    )
    smoke = subprocess.run(
        [str(python), "-I", str(smoke_script)],
        cwd=empty_cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    commands.append(
        {
            "command": ["<VENV_PYTHON>", "-I", "<TEMP>/installed_smoke.py"],
            "exit_code": smoke.returncode,
        }
    )
    if smoke.returncode != 0:
        raise PackagingVerificationError(
            "installed-wheel smoke failed: "
            + _normalize((smoke.stderr or smoke.stdout).strip(), replacements)
        )
    try:
        result = json.loads(smoke.stdout)
    except json.JSONDecodeError as error:
        raise PackagingVerificationError(
            "installed-wheel smoke did not emit JSON"
        ) from error
    module_file = Path(result["module_file"])
    if module_file.is_relative_to(root) or result["source_tree_paths"]:
        raise PackagingVerificationError(
            "installed-wheel smoke resolved a source-checkout path"
        )
    if result["schema_count"] != EXPECTED_SCHEMA_COUNT:
        raise PackagingVerificationError("installed wheel schema count is wrong")
    if result["resource_count"] != EXPECTED_RESOURCE_COUNT:
        raise PackagingVerificationError("installed wheel resource count is wrong")
    if result["openapi_3_1_1"] is not True:
        raise PackagingVerificationError("installed wheel cannot load OpenAPI 3.1.1")

    package_root = module_file.parent
    integrity_target = (
        package_root / "_canonical" / "schemas" / "action-intent.schema.json"
    )
    original_content = integrity_target.read_bytes()

    decoy_root = temporary_root / "complete-source-decoy"
    shutil.copytree(root / "schemas", decoy_root / "schemas")
    shutil.copytree(root / "openapi", decoy_root / "openapi")
    decoy_files = [path for path in decoy_root.rglob("*") if path.is_file()]
    if (
        len(decoy_files) != EXPECTED_RESOURCE_COUNT
        or not (decoy_root / "schemas/action-intent.schema.json").is_file()
    ):
        raise PackagingVerificationError("source fallback decoy is incomplete")
    integrity_target.unlink()
    fallback_script = temporary_root / "missing_resource_no_fallback.py"
    fallback_script.write_text(
        """from __future__ import annotations
import json
from epistemic_foundry.contracts.registry import (
    CANONICAL_REGISTRY_MISSING,
    CanonicalRegistryError,
    default_registry,
)
try:
    default_registry()
except CanonicalRegistryError as error:
    print(json.dumps({"error_code": error.code, "fallback_succeeded": False}))
    raise SystemExit(0 if error.code == CANONICAL_REGISTRY_MISSING else 2)
print(json.dumps({"error_code": None, "fallback_succeeded": True}))
raise SystemExit(3)
""",
        encoding="utf-8",
        newline="\n",
    )
    try:
        fallback = subprocess.run(
            [str(python), "-I", str(fallback_script)],
            cwd=decoy_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    finally:
        integrity_target.write_bytes(original_content)
    commands.append(
        {
            "command": [
                "<VENV_PYTHON>",
                "-I",
                "<TEMP>/missing_resource_no_fallback.py",
            ],
            "cwd": "<TEMP>/complete-source-decoy",
            "exit_code": fallback.returncode,
        }
    )
    try:
        fallback_result = json.loads(fallback.stdout)
    except json.JSONDecodeError as error:
        raise PackagingVerificationError(
            "missing-resource fallback probe did not emit JSON"
        ) from error
    if (
        fallback.returncode != 0
        or fallback_result.get("error_code") != "CANONICAL_REGISTRY_MISSING"
        or fallback_result.get("fallback_succeeded") is not False
    ):
        raise PackagingVerificationError(
            "installed package used a source-tree fallback or returned the wrong "
            "missing-resource error: "
            + _normalize((fallback.stderr or fallback.stdout).strip(), replacements)
        )

    tamper_target = integrity_target
    content = bytearray(tamper_target.read_bytes())
    content[-2] = ord(" ") if content[-2] != ord(" ") else ord("\t")
    tamper_target.write_bytes(content)
    tamper_script = temporary_root / "tamper_check.py"
    tamper_script.write_text(
        """from epistemic_foundry.contracts.registry import (
    CANONICAL_REGISTRY_HASH_MISMATCH,
    CanonicalRegistryError,
    default_registry,
)
try:
    default_registry()
except CanonicalRegistryError as error:
    raise SystemExit(0 if error.code == CANONICAL_REGISTRY_HASH_MISMATCH else 2)
raise SystemExit(3)
""",
        encoding="utf-8",
        newline="\n",
    )
    tamper = subprocess.run(
        [str(python), "-I", str(tamper_script)],
        cwd=empty_cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    commands.append(
        {
            "command": ["<VENV_PYTHON>", "-I", "<TEMP>/tamper_check.py"],
            "exit_code": tamper.returncode,
        }
    )
    if tamper.returncode != 0:
        raise PackagingVerificationError(
            "installed resource tamper did not fail with "
            "CANONICAL_REGISTRY_HASH_MISMATCH"
        )
    return (
        {
            "arbitrary_empty_cwd": "PASS",
            "clean_venv_install": "PASS",
            "installed_module_outside_source_tree": True,
            "fallback_attempt_count": 1,
            "fallback_success_count": 0,
            "fallback_decoy_source_present": True,
            "fallback_decoy_source_resource_count": len(decoy_files),
            "missing_packaged_resource_error_code": "CANONICAL_REGISTRY_MISSING",
            "openapi_load": "PASS",
            "representative_schema_validation": "PASS",
            "schema_count": result["schema_count"],
            "tamper_error_code": "CANONICAL_REGISTRY_HASH_MISMATCH",
        },
        commands,
    )


def historical_evidence_check(root: Path) -> dict[str, Any]:
    directory = root / "artifacts" / "work_packages" / "B04"
    actual = {
        name: sha256_file(directory / name) for name in HISTORICAL_B04_HASHES
    }
    mismatches = sorted(
        name
        for name, expected in HISTORICAL_B04_HASHES.items()
        if actual.get(name) != expected
    )
    if mismatches:
        raise PackagingVerificationError(
            f"historical B04 evidence changed: {mismatches}"
        )
    return {
        "artifact_count": len(actual),
        "hashes": actual,
        "mismatches": [],
        "status": "PASS",
    }


def dependency_reconciliation(root: Path) -> dict[str, Any]:
    dependencies = {
        "B02": root / "artifacts/work_packages/B02/report.json",
        "B03": root / "artifacts/work_packages/B03/report.json",
        "C04": root / "artifacts/work_packages/C04/report.json",
    }
    result: dict[str, Any] = {}
    for package, path in dependencies.items():
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PackagingVerificationError(
                f"cannot read dependency report {package}"
            ) from error
        if report.get("status") != "PASS":
            raise PackagingVerificationError(f"dependency {package} is not PASS")
        result[package] = {
            "report_sha256": sha256_file(path),
            "status": "PASS",
        }
    return {"dependencies": result, "status": "PASS"}


def verify(root: Path, dist_directory: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    toolchain = json.loads(
        (root / "toolchains/toolchain-lock.json").read_text(encoding="utf-8")
    )
    epoch = toolchain.get("source_date_epoch")
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        raise PackagingVerificationError("source_date_epoch is not an integer")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update(
        {
            "NO_COLOR": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "SOURCE_DATE_EPOCH": str(epoch),
            "TZ": "UTC",
            "UV_NO_PROGRESS": "1",
        }
    )

    commands: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="efoundry-b04-") as temporary:
        temporary_root = Path(temporary).resolve()
        replacements = [
            (str(temporary_root), "<TEMP>"),
            (str(root), "<REPO_ROOT>"),
            (str(Path(sys.executable).resolve()), "<PYTHON>"),
            (sys.executable, "<PYTHON>"),
            (str(_venv_python(temporary_root / "installed-venv")), "<VENV_PYTHON>"),
        ]
        source_one = temporary_root / "source-one"
        source_two = temporary_root / "source-two"
        source_hash_one = stage_source(root, source_one)
        source_hash_two = stage_source(root, source_two)
        if source_hash_one != source_hash_two:
            raise PackagingVerificationError("clean source stages are not byte-identical")

        first = build_distribution(
            source_one,
            temporary_root / "build-one",
            environment=environment,
            replacements=replacements,
        )
        second = build_distribution(
            source_two,
            temporary_root / "build-two",
            environment=environment,
            replacements=replacements,
        )
        commands.extend([first["command"], second["command"]])
        direct_wheel_equal = sha256_file(first["wheel"]) == sha256_file(second["wheel"])
        direct_sdist_equal = sha256_file(first["sdist"]) == sha256_file(second["sdist"])
        if not direct_wheel_equal or not direct_sdist_equal:
            raise PackagingVerificationError(
                "two clean builds are not byte-reproducible: "
                f"wheel={direct_wheel_equal}, sdist={direct_sdist_equal}"
            )

        sdist_root = extract_sdist(
            first["sdist"], temporary_root / "sdist-unpacked"
        )
        backend_evidence = backend_contract_evidence(root, sdist_root)
        sdist_constraints = sdist_root / "toolchains/python-build-constraints.txt"
        from_sdist = build_from_sdist(
            sdist_root,
            sdist_constraints,
            temporary_root / "sdist-wheel",
            environment=environment,
            replacements=replacements,
        )
        commands.append(from_sdist["command"])
        sdist_wheel_equal = sha256_file(first["wheel"]) == sha256_file(
            from_sdist["wheel"]
        )
        if not sdist_wheel_equal:
            raise PackagingVerificationError(
                "sdist-derived wheel differs from direct clean-source wheel"
            )

        first_wheel_root = temporary_root / "wheel-one-unpacked"
        second_wheel_root = temporary_root / "wheel-two-unpacked"
        sdist_wheel_root = temporary_root / "sdist-wheel-unpacked"
        extract_wheel(first["wheel"], first_wheel_root)
        extract_wheel(second["wheel"], second_wheel_root)
        extract_wheel(from_sdist["wheel"], sdist_wheel_root)
        source_authority = authority_resources(root)
        source_snapshot, source_manifest = snapshot_resources(
            root / "src/epistemic_foundry/_canonical"
        )
        source_registry_sha256 = "sha256:" + sha256_file(
            root / "src/epistemic_foundry/_canonical/canonical-registry.json"
        )
        staged_authority = authority_resources(source_one)
        staged_snapshot, _staged_manifest = snapshot_resources(
            source_one / "src/epistemic_foundry/_canonical"
        )
        sdist_authority = authority_resources(sdist_root)
        sdist_snapshot, _sdist_manifest = snapshot_resources(
            sdist_root / Path(*SDIST_CANONICAL_PREFIX.parts)
        )
        wheel_snapshot, wheel_manifest = snapshot_resources(
            first_wheel_root / Path(*WHEEL_CANONICAL_PREFIX.parts)
        )
        second_wheel_snapshot, _second_manifest = snapshot_resources(
            second_wheel_root / Path(*WHEEL_CANONICAL_PREFIX.parts)
        )
        sdist_wheel_snapshot, _sdist_wheel_manifest = snapshot_resources(
            sdist_wheel_root / Path(*WHEEL_CANONICAL_PREFIX.parts)
        )

        comparisons = {
            "source_projection": compare_resource_sets(
                source_authority, source_snapshot, "source projection"
            ),
            "clean_stage_authority": compare_resource_sets(
                source_authority, staged_authority, "clean-stage authority"
            ),
            "clean_stage_projection": compare_resource_sets(
                source_authority, staged_snapshot, "clean-stage projection"
            ),
            "sdist_authority": compare_resource_sets(
                source_authority, sdist_authority, "sdist authority"
            ),
            "sdist_projection": compare_resource_sets(
                source_authority, sdist_snapshot, "sdist projection"
            ),
            "wheel_projection": compare_resource_sets(
                source_authority, wheel_snapshot, "wheel projection"
            ),
            "second_wheel_projection": compare_resource_sets(
                source_authority, second_wheel_snapshot, "second wheel projection"
            ),
            "sdist_wheel_projection": compare_resource_sets(
                source_authority, sdist_wheel_snapshot, "sdist-derived wheel projection"
            ),
        }
        if source_manifest != wheel_manifest:
            raise PackagingVerificationError(
                "source and wheel canonical-registry.json documents differ"
            )

        installed, installed_commands = installed_wheel_checks(
            first["wheel"],
            root,
            temporary_root,
            environment=environment,
            replacements=replacements,
        )
        commands.extend(installed_commands)

        structure = run_command(
            ["node", "packages/repo-checks/check-structure.mjs"],
            cwd=root,
            environment=environment,
            replacements=replacements,
        )
        boundaries = run_command(
            ["node", "packages/repo-checks/check-boundaries.mjs"],
            cwd=root,
            environment=environment,
            replacements=replacements,
        )
        lock_check = run_command(
            [sys.executable, "scripts/build/check_locks.py", "--root", str(root)],
            cwd=root,
            environment=environment,
            replacements=replacements,
        )
        commands.extend([structure, boundaries, lock_check])

        wheel_hash = sha256_file(first["wheel"])
        sdist_hash = sha256_file(first["sdist"])
        artifact_inventory = {
            first["wheel"].name: {
                "byte_size": first["wheel"].stat().st_size,
                "sha256": wheel_hash,
            },
            first["sdist"].name: {
                "byte_size": first["sdist"].stat().st_size,
                "sha256": sdist_hash,
            },
        }
        if dist_directory is not None:
            dist_directory.mkdir(parents=True, exist_ok=True)
            expected_names = set(artifact_inventory)
            existing_names = {
                path.name for path in dist_directory.iterdir() if path.is_file()
            }
            unexpected = sorted(existing_names - expected_names)
            if unexpected:
                raise PackagingVerificationError(
                    f"unexpected pre-existing dist artifacts: {unexpected}"
                )
            shutil.copy2(first["wheel"], dist_directory / first["wheel"].name)
            shutil.copy2(first["sdist"], dist_directory / first["sdist"].name)

    return {
        "artifact_inventory": artifact_inventory,
        "backend": backend_evidence,
        "canonical_registry": {
            "build_epoch": source_manifest["build_epoch"],
            "bundle_version": source_manifest["bundle_version"],
            "duplicate_document_ids": 0,
            "file_count": source_manifest["file_count"],
            "generated_at": source_manifest["generated_at"],
            "openapi_document_count": source_manifest["openapi_document_count"],
            "projected_snapshot_bundle_hash": source_manifest[
                "projected_snapshot_bundle_hash"
            ],
            "projection_tool_identity": source_manifest["projection_tool_identity"],
            "projection_tool_version": source_manifest["projection_tool_version"],
            "registry_format_version": source_manifest["registry_format_version"],
            "registry_sha256": source_registry_sha256,
            "resource_count": source_manifest["resource_count"],
            "schema_count": source_manifest["schema_count"],
            "schema_version": source_manifest["schema_version"],
            "source_bundle_hash": source_manifest["source_bundle_hash"],
            "source_revision": source_manifest["source_revision"],
        },
        "checks": {
            "b01_boundary_regression": "PASS",
            "b01_structure_regression": "PASS",
            "clean_checkout_equivalent_build": "PASS",
            "installed_wheel": installed,
            "registry_comparisons": comparisons,
            "sdist_to_wheel": "PASS",
            "source_tree_fallback": {
                "attempt_count": installed["fallback_attempt_count"],
                "success_count": installed["fallback_success_count"],
            },
            "two_build_reproducibility": {
                "sdist_byte_equal": direct_sdist_equal,
                "sdist_derived_wheel_byte_equal": sdist_wheel_equal,
                "wheel_byte_equal": direct_wheel_equal,
            },
        },
        "commands": commands,
        "dependency_reconciliation": dependency_reconciliation(root),
        "historical_b04_evidence": historical_evidence_check(root),
        "source_date_epoch": epoch,
        "source_snapshot_sha256": source_hash_one,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--dist-dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.root, args.dist_dir)
    except Exception as error:
        result = {
            "error": str(error),
            "status": "FAIL",
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
