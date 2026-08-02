#!/usr/bin/env python3
"""Audit B03 CI cache keys and fail closed on semantic or authority drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(".github/workflows/ci.yml")
EXPECTED_CACHE_ACTION = "actions/cache@caa296126883cff596d87d8935842f9db880ef25"
EXPECTED_PATHS = {
    "${{ runner.temp }}/efoundry-cache/npm",
    "${{ runner.temp }}/efoundry-cache/uv",
}
REQUIRED_HASH_INPUTS = {
    "package-lock.json",
    "uv.lock",
    "toolchains/toolchain-lock.json",
    "toolchains/python-build-constraints.txt",
}
FORBIDDEN_PATH_PARTS = {
    ".git",
    ".rah",
    ".venv",
    "artifacts",
    "build",
    "dist",
    "ledger",
    "node_modules",
    "reports",
    "src",
    "tests",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return value


def list_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def validate(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    workflow = load_yaml(root / WORKFLOW_PATH)
    jobs = workflow.get("jobs")
    job = jobs.get("cross-platform") if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        raise ValueError("missing jobs.cross-platform")
    steps = job.get("steps") if isinstance(job.get("steps"), list) else []
    matches = [step for step in steps if isinstance(step, dict) and step.get("uses") == EXPECTED_CACHE_ACTION]
    if len(matches) != 1:
        failures.append("workflow must contain exactly one reviewed actions/cache step")
        cache_step: dict[str, Any] = {}
    else:
        cache_step = matches[0]

    values = cache_step.get("with") if isinstance(cache_step.get("with"), dict) else {}
    paths = list_paths(values.get("path"))
    if set(paths) != EXPECTED_PATHS or len(paths) != len(EXPECTED_PATHS):
        failures.append(f"cache paths must be exactly {sorted(EXPECTED_PATHS)}")
    for path in paths:
        lowered_parts = {part.lower() for part in path.replace("\\", "/").split("/")}
        overlap = lowered_parts & FORBIDDEN_PATH_PARTS
        if overlap:
            failures.append(f"cache path includes forbidden canonical/output material {sorted(overlap)}: {path}")

    key = values.get("key")
    if not isinstance(key, str):
        failures.append("cache key must be a string")
        key = ""
    if not key.startswith("efoundry-deps-v1-"):
        failures.append("cache key must use the reviewed efoundry-deps-v1 namespace")
    for expression in ("${{ matrix.os }}", "${{ runner.arch }}"):
        if expression not in key:
            failures.append(f"cache key is missing environment identity {expression}")
    if key.count("hashFiles(") != 1:
        failures.append("cache key must contain exactly one hashFiles expression")
    for relative in REQUIRED_HASH_INPUTS:
        if f"'{relative}'" not in key:
            failures.append(f"cache key does not hash required input {relative}")
        if not (root / relative).is_file():
            failures.append(f"cache key input does not exist: {relative}")

    if "restore-keys" in values or "restoreKeys" in values:
        failures.append("prefix restore keys are forbidden; cache restoration must be exact")
    if values.get("enableCrossOsArchive") is not False:
        failures.append("cross-OS cache archives must remain disabled")
    if values.get("fail-on-cache-miss") is not False:
        failures.append("cache miss must remain non-fatal")

    environment = job.get("env") if isinstance(job.get("env"), dict) else {}
    expected_environment = {
        "NPM_CONFIG_CACHE": "${{ runner.temp }}/efoundry-cache/npm",
        "UV_CACHE_DIR": "${{ runner.temp }}/efoundry-cache/uv",
    }
    for name, expected in expected_environment.items():
        if environment.get(name) != expected:
            failures.append(f"{name} must point to the reviewed disposable cache path")

    cache_index = steps.index(cache_step) if cache_step in steps else -1
    install_index = next(
        (
            index
            for index, step in enumerate(steps)
            if isinstance(step, dict) and "npm ci --ignore-scripts" in str(step.get("run", ""))
        ),
        -1,
    )
    if cache_index < 0 or install_index < 0 or cache_index >= install_index:
        failures.append("exact cache restore must occur before locked dependency installation")

    return {
        "check": "cache_key_audit",
        "status": "FAIL" if failures else "PASS",
        "workflow": WORKFLOW_PATH.as_posix(),
        "cache_action": cache_step.get("uses"),
        "paths": paths,
        "key": key,
        "hash_inputs": sorted(REQUIRED_HASH_INPUTS),
        "exact_restore_only": "restore-keys" not in values and "restoreKeys" not in values,
        "cross_os_archive": values.get("enableCrossOsArchive"),
        "cache_miss_is_fatal": values.get("fail-on-cache-miss"),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.root.resolve())
    except Exception as error:
        result = {"check": "cache_key_audit", "status": "FAIL", "error": str(error)}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
