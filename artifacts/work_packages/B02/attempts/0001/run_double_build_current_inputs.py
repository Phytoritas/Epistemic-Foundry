#!/usr/bin/env python3
"""Run B02 byte-reproducibility with the current B04 build-hook inputs.

The historical production helper predates the canonical registry build hook
and stages only packages/src/toolchains.  This attempt-local adapter leaves the
historical helper untouched and adds the exact source inputs now referenced by
pyproject.toml: scripts, schemas, and openapi.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
HELPER = ROOT / "scripts/build/double_build.py"
CURRENT_SOURCE_DIRECTORIES = (
    "packages",
    "src",
    "toolchains",
    "scripts",
    "schemas",
    "openapi",
)


def current_ignored(directory: str, names: list[str]) -> set[str]:
    """Preserve ``scripts/build`` while excluding generated build trees.

    The historical helper treats every directory named ``build`` as generated
    output.  Since B04 introduced the authoritative source package at
    ``scripts/build/canonical_registry``, that name-only rule now removes a
    required build input.  Narrow the exception to the repository's scripts
    root; all other historical exclusions remain intact.
    """
    ignored = {
        name
        for name in names
        if name in helper_module.IGNORED_NAMES
        or name.endswith((".egg-info", ".pyc", ".pyo"))
    }
    if Path(directory).resolve() == (ROOT / "scripts").resolve():
        ignored.discard("build")
    return ignored


helper_module: ModuleType


def load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_b02_double_build", HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load B02 double-build helper: {HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run() -> dict[str, Any]:
    global helper_module
    helper = load_helper()
    helper_module = helper
    historical = tuple(helper.SOURCE_DIRECTORIES)
    if historical != ("packages", "src", "toolchains"):
        raise RuntimeError(f"unexpected historical staging contract: {historical}")
    helper.SOURCE_DIRECTORIES = CURRENT_SOURCE_DIRECTORIES
    helper.ignored = current_ignored
    result = helper.compare(ROOT)
    result.update(
        {
            "attempt_id": "B02-0001",
            "check": "double_build_comparison",
            "current_build_inputs": list(CURRENT_SOURCE_DIRECTORIES),
            "historical_build_inputs": list(historical),
            "harness_mode": "ATTEMPT_LOCAL_CURRENT_INPUT_ADAPTER",
            "production_helper_modified": False,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run()
    except Exception as error:  # pragma: no cover - evidence fail-closed path
        result = {
            "attempt_id": "B02-0001",
            "check": "double_build_comparison",
            "harness_mode": "ATTEMPT_LOCAL_CURRENT_INPUT_ADAPTER",
            "status": "FAIL",
            "error": str(error),
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
