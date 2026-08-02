#!/usr/bin/env python3
"""Validate the B03 cross-platform workflow without executing remote CI."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(".github/workflows/ci.yml")
EXPECTED_RUNNERS = {"ubuntu-24.04", "macos-15", "windows-2025"}
ACTION_PINS = {
    "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
    "actions/setup-node": "249970729cb0ef3589644e2896645e5dc5ba9c38",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "astral-sh/setup-uv": "94527f2e458b27549849d47d273a16bec83a01e9",
    "actions/cache": "caa296126883cff596d87d8935842f9db880ef25",
}
REQUIRED_COMMANDS = (
    "python scripts/build/check_locks.py",
    "npm ci --ignore-scripts",
    "uv sync --locked --extra dev --no-python-downloads",
    "npm run check:structure",
    "npm run check:boundaries",
    "uv run --locked python scripts/ci/ci_matrix_lint.py",
    "uv run --locked python scripts/ci/cache_key_audit.py",
    "uv run --locked python scripts/ci/test_ci_policy.py",
    "uv run --locked pytest tests -p no:cacheprovider",
    "uv run --locked python scripts/build/double_build.py",
)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return value


def scalar(value: Any) -> str:
    return "" if value is None else str(value)


def validate(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    workflow_path = root / WORKFLOW_PATH
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = load_yaml(workflow_path)
    toolchain = json.loads((root / "toolchains/toolchain-lock.json").read_text(encoding="utf-8"))

    permissions = workflow.get("permissions")
    if permissions != {"contents": "read"}:
        failures.append("workflow permissions must be exactly contents: read")
    if re.search(r"(?m)^\s*pull_request_target\s*:", workflow_text):
        failures.append("pull_request_target is forbidden for dependency-building CI")
    for trigger in ("push", "pull_request", "workflow_dispatch"):
        if not re.search(rf"(?m)^  {re.escape(trigger)}\s*:\s*$", workflow_text):
            failures.append(f"workflow is missing required trigger {trigger}")

    jobs = workflow.get("jobs")
    job = jobs.get("cross-platform") if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        failures.append("missing jobs.cross-platform")
        job = {}
    if job.get("runs-on") != "${{ matrix.os }}":
        failures.append("cross-platform job must run on matrix.os")
    if job.get("continue-on-error") is not None:
        failures.append("cross-platform job may not suppress failures")
    timeout = job.get("timeout-minutes")
    if not isinstance(timeout, int) or not 1 <= timeout <= 30:
        failures.append("cross-platform timeout-minutes must be between 1 and 30")

    strategy = job.get("strategy") if isinstance(job.get("strategy"), dict) else {}
    if strategy.get("fail-fast") is not False:
        failures.append("matrix fail-fast must be false so every OS produces a result")
    matrix = strategy.get("matrix") if isinstance(strategy.get("matrix"), dict) else {}
    runners = matrix.get("os") if isinstance(matrix.get("os"), list) else []
    if set(runners) != EXPECTED_RUNNERS or len(runners) != len(EXPECTED_RUNNERS):
        failures.append(f"matrix.os must contain exactly {sorted(EXPECTED_RUNNERS)}")
    for runner in runners:
        if not isinstance(runner, str) or runner.endswith("-latest"):
            failures.append(f"runner image must use a versioned label: {runner!r}")

    environment = job.get("env") if isinstance(job.get("env"), dict) else {}
    if scalar(environment.get("SOURCE_DATE_EPOCH")) != str(toolchain.get("source_date_epoch")):
        failures.append("SOURCE_DATE_EPOCH must match toolchain-lock.json")
    if scalar(environment.get("PYTHONHASHSEED")) != "0":
        failures.append("PYTHONHASHSEED must be fixed to 0")

    steps = job.get("steps") if isinstance(job.get("steps"), list) else []
    observed_actions: dict[str, str] = {}
    action_counts: dict[str, int] = {}
    command_text = "\n".join(scalar(step.get("run")) for step in steps if isinstance(step, dict))
    for step in steps:
        if not isinstance(step, dict):
            failures.append("every workflow step must be an object")
            continue
        if step.get("continue-on-error") is not None:
            failures.append(f"step may not suppress failures: {step.get('name')!r}")
        uses = step.get("uses")
        if uses is None:
            continue
        if not isinstance(uses, str) or "@" not in uses:
            failures.append(f"invalid action reference: {uses!r}")
            continue
        action, revision = uses.rsplit("@", 1)
        observed_actions[action] = revision
        action_counts[action] = action_counts.get(action, 0) + 1
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            failures.append(f"action must be pinned to a full commit SHA: {uses}")

    if observed_actions != ACTION_PINS:
        failures.append("workflow action set or commit pins differ from the reviewed B03 allowlist")
    if action_counts != {action: 1 for action in ACTION_PINS}:
        failures.append("each reviewed action must appear exactly once")

    expected_versions = {
        "actions/setup-node": toolchain["tools"]["node"]["version"],
        "actions/setup-python": toolchain["tools"]["python"]["version"],
        "astral-sh/setup-uv": toolchain["tools"]["uv"]["version"],
    }
    version_fields = {
        "actions/setup-node": "node-version",
        "actions/setup-python": "python-version",
        "astral-sh/setup-uv": "version",
    }
    for action, expected in expected_versions.items():
        step = next((item for item in steps if isinstance(item, dict) and scalar(item.get("uses")).startswith(action + "@")), None)
        values = step.get("with", {}) if isinstance(step, dict) else {}
        field = version_fields[action]
        if not isinstance(values, dict) or scalar(values.get(field)) != expected:
            failures.append(f"{action} {field} must equal pinned version {expected}")

    checkout = next((item for item in steps if isinstance(item, dict) and scalar(item.get("uses")).startswith("actions/checkout@")), None)
    checkout_with = checkout.get("with", {}) if isinstance(checkout, dict) else {}
    if not isinstance(checkout_with, dict) or checkout_with.get("persist-credentials") is not False:
        failures.append("checkout must disable persisted credentials")

    for required in REQUIRED_COMMANDS:
        if required not in command_text:
            failures.append(f"cross-platform job is missing required command: {required}")

    return {
        "check": "ci_matrix_lint",
        "status": "FAIL" if failures else "PASS",
        "workflow": WORKFLOW_PATH.as_posix(),
        "runners": runners,
        "action_pins": observed_actions,
        "action_counts": action_counts,
        "required_commands": list(REQUIRED_COMMANDS),
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
        result = {"check": "ci_matrix_lint", "status": "FAIL", "error": str(error)}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
