#!/usr/bin/env python3
"""Verify the B02 tokenizer dependency correction without mutating the repo.

The verifier reconstructs the pre-correction lock with the pinned uv resolver,
proves that it matches the preserved pre-correction SHA-256, and then compares
the old and new lock documents structurally.  It is deliberately attempt-local:
B02 owns dependency declarations and evidence, not the J02 runtime verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from importlib import metadata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT_ID = "B02-0002"
EXPECTED_UV_VERSION = "0.7.21"
EXPECTED_OLD_PYPROJECT_SHA256 = (
    "29d7a25d530884a4a2dff3d8ca2d9878717a43a4dc3c2710fc5317f533a7be44"
)
EXPECTED_OLD_LOCK_SHA256 = (
    "728e9d36f966b38a0f86ea5300210760b889110ba5adce5e646efa439ea2efac"
)
EXPECTED_DIRECT = {"tiktoken"}
EXPECTED_TRANSITIVE = {
    "certifi",
    "charset-normalizer",
    "idna",
    "regex",
    "requests",
    "urllib3",
}
DEPENDENCY_GROUP_BLOCK = b'''\n[dependency-groups]\nskill-context = [\n    "tiktoken==0.13.0",\n]\n'''
STAGED_DIRECTORIES = (
    "openapi",
    "schemas",
    "scripts",
    "src",
    "toolchains",
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"TOML root is not an object: {path}")
    return value


def package_map(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise RuntimeError("uv.lock package table is missing")
    result: dict[str, dict[str, Any]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            raise RuntimeError("uv.lock contains an invalid package entry")
        name = package["name"]
        if name in result:
            raise RuntimeError(f"uv.lock contains duplicate package: {name}")
        result[name] = package
    return result


def normalized_root_package(package: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(package))
    normalized.pop("dev-dependencies", None)
    metadata_table = normalized.get("metadata")
    if isinstance(metadata_table, dict):
        metadata_table.pop("requires-dev", None)
    return normalized


def reconstruct_old_lock(current_pyproject: bytes, current_lock: Path) -> tuple[bytes, bytes]:
    if current_pyproject.count(DEPENDENCY_GROUP_BLOCK) != 1:
        raise RuntimeError("pyproject.toml does not contain the exact authorized dependency group")
    old_pyproject = current_pyproject.replace(DEPENDENCY_GROUP_BLOCK, b"", 1)
    if sha256_bytes(old_pyproject) != EXPECTED_OLD_PYPROJECT_SHA256:
        raise RuntimeError("reconstructed pre-correction pyproject hash mismatch")

    with tempfile.TemporaryDirectory(prefix="efoundry-b02-lock-diff-") as temporary:
        staged = Path(temporary)
        (staged / "pyproject.toml").write_bytes(old_pyproject)
        shutil.copy2(current_lock, staged / "uv.lock")
        for relative in STAGED_DIRECTORIES:
            shutil.copytree(
                ROOT / relative,
                staged / relative,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        completed = subprocess.run(
            ["uv", "lock", "--directory", str(staged)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"pre-correction uv lock reconstruction failed: {detail}")
        old_lock = (staged / "uv.lock").read_bytes()
    return old_pyproject, old_lock


def dependency_names(package: dict[str, Any]) -> set[str]:
    dependencies = package.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise RuntimeError(f"invalid dependencies for {package.get('name')}")
    return {
        dependency["name"]
        for dependency in dependencies
        if isinstance(dependency, dict) and isinstance(dependency.get("name"), str)
    }


def closure(packages: dict[str, dict[str, Any]], start: str) -> set[str]:
    pending = [start]
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        package = packages.get(name)
        if package is None:
            raise RuntimeError(f"dependency closure references missing package: {name}")
        visited.add(name)
        pending.extend(sorted(dependency_names(package) - visited))
    return visited


def verify_vectors() -> tuple[list[dict[str, Any]], str]:
    try:
        import tiktoken
    except ImportError as exc:  # pragma: no cover - fail-closed environment guard
        raise RuntimeError("tiktoken is unavailable in the frozen skill-context environment") from exc

    installed = metadata.version("tiktoken")
    if installed != "0.13.0":
        raise RuntimeError(f"installed tiktoken version mismatch: {installed}")
    encoding = tiktoken.get_encoding("o200k_base")
    fixture = json.loads(
        (ROOT / "tests/fixtures/j02/tokenizer-vectors.json").read_text(encoding="utf-8")
    )
    results: list[dict[str, Any]] = []
    for vector in fixture["vectors"]:
        text = vector["text"]
        if vector.get("normalize_nfc"):
            text = unicodedata.normalize("NFC", text)
        observed = encoding.encode(text, disallowed_special=())
        expected = vector["token_ids"]
        if observed != expected:
            raise RuntimeError(f"tokenizer vector mismatch: {vector['id']}")
        results.append(
            {
                "id": vector["id"],
                "status": "PASS",
                "token_count": len(observed),
            }
        )
    return results, encoding.name


def verify() -> dict[str, Any]:
    pyproject_path = ROOT / "pyproject.toml"
    lock_path = ROOT / "uv.lock"
    current_pyproject = pyproject_path.read_bytes()
    old_pyproject, old_lock_bytes = reconstruct_old_lock(current_pyproject, lock_path)
    old_lock_hash = sha256_bytes(old_lock_bytes)
    if old_lock_hash != EXPECTED_OLD_LOCK_SHA256:
        raise RuntimeError(
            "reconstructed pre-correction uv.lock hash mismatch: "
            f"expected={EXPECTED_OLD_LOCK_SHA256} observed={old_lock_hash}"
        )

    with tempfile.TemporaryDirectory(prefix="efoundry-b02-lock-parse-") as temporary:
        old_lock_path = Path(temporary) / "uv.lock"
        old_lock_path.write_bytes(old_lock_bytes)
        old_lock = read_toml(old_lock_path)
    new_lock = read_toml(lock_path)
    pyproject = read_toml(pyproject_path)
    old_packages = package_map(old_lock)
    new_packages = package_map(new_lock)

    added = set(new_packages) - set(old_packages)
    removed = set(old_packages) - set(new_packages)
    expected_added = EXPECTED_DIRECT | EXPECTED_TRANSITIVE
    if added != expected_added or removed:
        raise RuntimeError(
            f"unexpected lock package delta: added={sorted(added)} removed={sorted(removed)}"
        )

    changed_common: list[str] = []
    for name in sorted(set(old_packages) & set(new_packages)):
        old_package = old_packages[name]
        new_package = new_packages[name]
        if name == "epistemic-foundry":
            old_package = normalized_root_package(old_package)
            new_package = normalized_root_package(new_package)
        if old_package != new_package:
            changed_common.append(name)
    if changed_common:
        raise RuntimeError(f"unrelated existing packages changed: {changed_common}")

    dependency_groups = pyproject.get("dependency-groups")
    if dependency_groups != {"skill-context": ["tiktoken==0.13.0"]}:
        raise RuntimeError("pyproject dependency group differs from the authorized exact declaration")
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise RuntimeError("pyproject project table is missing")
    runtime_declarations = list(project.get("dependencies", []))
    for values in project.get("optional-dependencies", {}).values():
        runtime_declarations.extend(values)
    if any(str(value).lower().startswith("tiktoken") for value in runtime_declarations):
        raise RuntimeError("tiktoken was incorrectly exposed as a runtime or optional dependency")

    tokenizer_closure = closure(new_packages, "tiktoken")
    if tokenizer_closure != expected_added:
        raise RuntimeError(f"unexpected tokenizer dependency closure: {sorted(tokenizer_closure)}")
    for name in sorted(expected_added):
        source = new_packages[name].get("source")
        if source != {"registry": "https://pypi.org/simple"}:
            raise RuntimeError(f"unexpected source/index for {name}: {source}")
        if name == "tiktoken" and new_packages[name].get("version") != "0.13.0":
            raise RuntimeError("locked tiktoken version is not exactly 0.13.0")

    root = new_packages.get("epistemic-foundry")
    if root is None:
        raise RuntimeError("root package is missing from uv.lock")
    runtime_lock_names = dependency_names(root)
    if "tiktoken" in runtime_lock_names:
        raise RuntimeError("uv.lock exposes tiktoken through root runtime dependencies")
    groups = root.get("dev-dependencies")
    metadata_table = root.get("metadata")
    requires_dev = metadata_table.get("requires-dev") if isinstance(metadata_table, dict) else None
    if groups != {"skill-context": [{"name": "tiktoken"}]}:
        raise RuntimeError("uv.lock root group membership is not exact")
    if requires_dev != {"skill-context": [{"name": "tiktoken", "specifier": "==0.13.0"}]}:
        raise RuntimeError("uv.lock root group constraint is not exact")

    uv_version = subprocess.run(
        ["uv", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if uv_version != f"uv {EXPECTED_UV_VERSION} (77c771c7f 2025-07-14)":
        raise RuntimeError(f"unexpected uv resolver identity: {uv_version}")

    vectors, encoding_name = verify_vectors()
    return {
        "attempt_id": ATTEMPT_ID,
        "command": 'uv add --group skill-context "tiktoken==0.13.0"',
        "direct_dependency_changes": [
            {"group": "skill-context", "name": "tiktoken", "specifier": "==0.13.0"}
        ],
        "final_status": "PASS",
        "frozen_sync_result": "PASS",
        "installed_tiktoken_version": "0.13.0",
        "new_lock_hash": "sha256:" + sha256_file(lock_path),
        "new_lock_package_count": len(new_packages),
        "old_lock_hash": "sha256:" + old_lock_hash,
        "old_lock_package_count": len(old_packages),
        "old_pyproject_hash": "sha256:" + sha256_bytes(old_pyproject),
        "resolver_version": EXPECTED_UV_VERSION,
        "runtime_dependency_exposure": False,
        "tokenizer_encoding": encoding_name,
        "tokenizer_vector_pass_count": len(vectors),
        "tokenizer_vectors": vectors,
        "transitive_dependency_changes": sorted(EXPECTED_TRANSITIVE),
        "unrelated_dependency_changes": [],
        "unrelated_dependency_change_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify()
    except Exception as error:  # pragma: no cover - evidence fail-closed path
        result = {
            "attempt_id": ATTEMPT_ID,
            "final_status": "FAIL",
            "error": str(error),
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
