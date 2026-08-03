#!/usr/bin/env python3
"""Fail-closed B02 toolchain and dependency-lock validation."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXACT_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def command_output(command: list[str], cwd: Path) -> str:
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError(f"required executable is not on PATH: {command[0]}")
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(command)} failed ({completed.returncode}): {detail}")
    return completed.stdout.strip()


def active_versions(root: Path) -> dict[str, str]:
    return {
        "node": command_output(["node", "--version"], root).removeprefix("v"),
        "npm": command_output(["npm", "--version"], root),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "uv": command_output(["uv", "--version"], root).split()[1],
    }


def parse_requirement_name(value: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", value)
    if not match:
        raise ValueError(f"cannot parse requirement: {value!r}")
    return normalize_name(match.group(1))


def check_node_lock(root: Path, failures: list[str]) -> dict[str, int]:
    manifest = read_json(root / "package.json")
    lock = read_json(root / "package-lock.json")
    packages = lock.get("packages")
    if lock.get("lockfileVersion") != 3:
        failures.append("package-lock.json must use lockfileVersion 3")
    if not isinstance(packages, dict):
        failures.append("package-lock.json packages map is missing")
        return {"workspaces": 0, "external_packages": 0}

    root_lock = packages.get("") or {}
    for key in ("name", "version", "workspaces"):
        if root_lock.get(key) != manifest.get(key):
            failures.append(f"package-lock root {key} does not match package.json")

    workspace_patterns = manifest.get("workspaces")
    if workspace_patterns != ["packages/*"]:
        failures.append("package.json must declare exactly packages/* for B02 lock coverage")

    workspace_manifests = sorted((root / "packages").glob("*/package.json"))
    workspace_names: dict[str, str] = {}
    for path in workspace_manifests:
        relative_dir = path.parent.relative_to(root).as_posix()
        item = read_json(path)
        name = item.get("name")
        version = item.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            failures.append(f"{relative_dir}/package.json lacks name/version")
            continue
        if not EXACT_VERSION_RE.fullmatch(version):
            failures.append(f"{name} has non-exact package version {version!r}")
        if name in workspace_names:
            failures.append(f"duplicate workspace package name {name}")
        workspace_names[name] = version

        locked = packages.get(relative_dir)
        if not isinstance(locked, dict):
            failures.append(f"package-lock missing workspace entry {relative_dir}")
            continue
        for key in ("name", "version"):
            if locked.get(key) != item.get(key):
                failures.append(f"package-lock {relative_dir} {key} mismatch")
        for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            if locked.get(field, {}) != item.get(field, {}):
                failures.append(f"package-lock {relative_dir} {field} mismatch")

    for name, version in workspace_names.items():
        link = packages.get(f"node_modules/{name}")
        expected = next(
            (path.parent.relative_to(root).as_posix() for path in workspace_manifests if read_json(path).get("name") == name),
            None,
        )
        if not isinstance(link, dict) or link.get("link") is not True or link.get("resolved") != expected:
            failures.append(f"package-lock workspace link for {name} is missing or incorrect")

    external_count = 0
    for key, item in packages.items():
        if not key.startswith("node_modules/") or item.get("link") is True:
            continue
        external_count += 1
        version = item.get("version")
        if not isinstance(version, str) or not EXACT_VERSION_RE.fullmatch(version):
            failures.append(f"{key} lacks an exact locked version")
        if not isinstance(item.get("resolved"), str):
            failures.append(f"{key} lacks a resolved artifact URL")
        integrity = item.get("integrity")
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            failures.append(f"{key} lacks sha512 integrity")

    return {"workspaces": len(workspace_manifests), "external_packages": external_count}


def check_python_lock(root: Path, failures: list[str]) -> dict[str, int]:
    pyproject = read_toml(root / "pyproject.toml")
    lock = read_toml(root / "uv.lock")
    packages = lock.get("package")
    if lock.get("version") != 1 or not isinstance(packages, list):
        failures.append("uv.lock must be version 1 with a package array")
        return {"packages": 0, "registry_packages": 0}
    if lock.get("requires-python") != pyproject.get("project", {}).get("requires-python"):
        failures.append("uv.lock requires-python does not match pyproject.toml")

    by_name = {normalize_name(str(item.get("name"))): item for item in packages}
    project = pyproject.get("project", {})
    project_name = normalize_name(str(project.get("name")))
    locked_project = by_name.get(project_name)
    if not locked_project:
        failures.append(f"uv.lock is missing project package {project_name}")
    elif locked_project.get("version") != project.get("version"):
        failures.append("uv.lock project version does not match pyproject.toml")

    declared = list(project.get("dependencies", []))
    for values in project.get("optional-dependencies", {}).values():
        declared.extend(values)
    tools_requirements = root / "tools" / "requirements.txt"
    if tools_requirements.exists():
        declared.extend(
            line.strip()
            for line in tools_requirements.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    for requirement in declared:
        name = parse_requirement_name(requirement)
        if name not in by_name:
            failures.append(f"uv.lock does not resolve declared requirement {requirement!r}")

    registry_count = 0
    for item in packages:
        source = item.get("source", {})
        if "registry" not in source:
            if normalize_name(str(item.get("name"))) != project_name:
                failures.append(f"non-registry dependency is not hash-qualified: {item.get('name')}")
            continue
        registry_count += 1
        version = item.get("version")
        if not isinstance(version, str) or not EXACT_VERSION_RE.fullmatch(version):
            failures.append(f"uv package {item.get('name')} lacks an exact version")
        artifacts = ([] if item.get("sdist") is None else [item["sdist"]]) + list(item.get("wheels", []))
        if not artifacts:
            failures.append(f"uv package {item.get('name')} has no hashed artifacts")
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not HASH_RE.fullmatch(str(artifact.get("hash", ""))):
                failures.append(f"uv package {item.get('name')} has an invalid artifact hash")

    return {"packages": len(packages), "registry_packages": registry_count}


def check_build_backend(root: Path, toolchain: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    backend = toolchain.get("python_build_backend", {})
    name = normalize_name(str(backend.get("name", "")))
    version = str(backend.get("version", ""))
    constraints_path = root / str(backend.get("constraints", ""))
    pyproject = read_toml(root / "pyproject.toml")
    declared_names = {
        parse_requirement_name(requirement)
        for requirement in pyproject.get("build-system", {}).get("requires", [])
    }
    if name not in declared_names:
        failures.append(f"pinned build backend {name!r} is not declared in pyproject.toml")
    if not EXACT_VERSION_RE.fullmatch(version):
        failures.append("python build backend version must be exact")
    if not constraints_path.is_file():
        failures.append(f"missing Python build constraints {constraints_path}")
        return {"backend": name, "version": version, "hashes": 0}

    text = constraints_path.read_text(encoding="utf-8")
    if f"{name}=={version}" not in text.lower():
        failures.append(f"Python build constraints do not pin {name}=={version}")
    hashes = re.findall(r"--hash=(sha256:[0-9a-f]{64})", text)
    if not hashes:
        failures.append("Python build backend constraint has no SHA-256 artifact hashes")
    return {"backend": name, "version": version, "hashes": len(hashes)}


def validate(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    toolchain_path = root / "toolchains" / "toolchain-lock.json"
    toolchain = read_json(toolchain_path)
    if toolchain.get("schema_version") != 1:
        failures.append("toolchain-lock.json schema_version must be 1")
    if not isinstance(toolchain.get("source_date_epoch"), int):
        failures.append("toolchain-lock.json source_date_epoch must be an integer")

    observed = active_versions(root)
    expected = {
        "node": str(toolchain.get("tools", {}).get("node", {}).get("version", "")),
        "npm": str(toolchain.get("tools", {}).get("npm", {}).get("version", "")),
        "python": str(toolchain.get("tools", {}).get("python", {}).get("version", "")),
        "uv": str(toolchain.get("tools", {}).get("uv", {}).get("version", "")),
    }
    for name in expected:
        if observed[name] != expected[name]:
            failures.append(f"{name} version {observed[name]} != pinned {expected[name]}")

    try:
        command_output(["uv", "lock", "--check"], root)
    except RuntimeError as error:
        failures.append(str(error))

    configured_locks = toolchain.get("lockfiles", {})
    if configured_locks != {"node": "package-lock.json", "python": "uv.lock"}:
        failures.append("toolchain lock must bind package-lock.json and uv.lock")
    node = check_node_lock(root, failures)
    python = check_python_lock(root, failures)
    backend = check_build_backend(root, toolchain, failures)
    return {
        "check": "lockfile_check",
        "status": "FAIL" if failures else "PASS",
        "toolchain": {"expected": expected, "observed": observed},
        "node": node,
        "python": python,
        "python_build_backend": backend,
        "uv_lock_check": "PASS" if not any("uv lock --check" in item for item in failures) else "FAIL",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.root.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
