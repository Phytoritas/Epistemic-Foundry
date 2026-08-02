#!/usr/bin/env python3
"""Expose full backend output for one current-input B02 staged build."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
HELPER_PATH = ROOT / "scripts/build/double_build.py"
SOURCE_DIRECTORIES = ("packages", "src", "toolchains", "scripts", "schemas", "openapi")


def main() -> int:
    spec = importlib.util.spec_from_file_location("_b02_double_build_diagnostic", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load B02 double-build helper")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.SOURCE_DIRECTORIES = SOURCE_DIRECTORIES

    with tempfile.TemporaryDirectory(prefix="efoundry-b02-stage-diagnostic-") as temporary:
        temporary_root = Path(temporary)
        source = temporary_root / "source"
        output = temporary_root / "output"
        helper.stage_source(ROOT, source)
        output.mkdir()
        environment = os.environ.copy()
        environment.update(
            {
                "SOURCE_DATE_EPOCH": "1767225600",
                "PYTHONHASHSEED": "0",
                "TZ": "UTC",
                "NO_COLOR": "1",
            }
        )
        executable = shutil.which("uv", path=environment.get("PATH"))
        if executable is None:
            raise RuntimeError("uv unavailable")
        command = [
            executable,
            "build",
            "--wheel",
            "--build-constraints",
            "toolchains/python-build-constraints.txt",
            "--require-hashes",
            "--no-python-downloads",
            "--out-dir",
            str(output),
            ".",
        ]
        completed = subprocess.run(
            command,
            cwd=source,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        result = {
            "attempt_id": "B02-0002",
            "command": ["uv", *command[1:-2], "<OUTPUT>", "."],
            "exit_code": completed.returncode,
            "staged_directories": list(SOURCE_DIRECTORIES),
            "stderr": completed.stderr,
            "stdout": completed.stdout,
        }
    path = Path(__file__).with_name("staged-build-diagnostic.json")
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
