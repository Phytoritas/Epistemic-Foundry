#!/usr/bin/env python3
"""Run the Y04-0001 50/200/2000 scale-qualification and load-shedding checks.

Required checks from manifests/development_manifest.yaml (Y04):
``scale_qualification`` and ``load_shedding_test``.  Each maps to one product
test module under ``evals/scale``: ``scale_qualification`` ->
``test_scale_qualification.py`` and ``load_shedding_test`` ->
``test_load_shedding.py``.  Together with the harness they compose are the whole
component's test surface (there is no third module), so they are the targeted
coverage rather than a subset of it.

The component sits under ``evals/scale``, carries its own ``pytest.ini`` that
puts the component root on ``pythonpath`` and targets only itself, and lies
outside the repository ``testpaths`` (``tests``), so the repository-wide
``pytest tests`` collection is unchanged by this package (measured 1261 tests,
zero of them under ``evals/``).  ``wire-literal-discipline`` re-runs the
repository EF4-I22 literal-drift gate, and ``full-python-suite``,
``full-node-suite`` and ``git-diff-check`` reproduce the repository gate as the
regression surface.

Y04 depends on Y02 and Y03 at the manifest layer only; the harness imports the
standard library alone and reads the sealed ``schemas/budget-envelope.schema.json``
budget vocabulary (Y01) and re-applies the Y02 honest-state rule without
importing either component's code, so there is no cross-component code surface
to regress and the full suites are the honest regression here.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Y04/attempts/0001"
ATTEMPT_ID = "Y04-0001"
COMPONENT = "evals/scale"
ATTEMPT_DIR = "artifacts/work_packages/Y04/attempts/0001"
WIRE_LITERAL_TEST = "tests/test_wire_literal_discipline.py"
SCALE_QUALIFICATION_TEST = f"{COMPONENT}/test_scale_qualification.py"
LOAD_SHEDDING_TEST = f"{COMPONENT}/test_load_shedding.py"
# The Node implementation and its ``*.test.mjs`` suites are working-tree content
# swept from the same five bases the sealed python-component templates use; the
# count is measured and pinned so a change to the Node surface is caught here.
EXPECTED_NODE_FILE_COUNT = 140
NODE_BASES = ("adapters", "packages", "plugin_blueprint", "tests", "web")


def write_run_result(name: str, command: list[str], exit_code: int) -> None:
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "command": command,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(
    name: str,
    command: list[str],
    *,
    junit_from_stdout: Path | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (ATTEMPT / f"{name}.stdout.log").write_bytes(process.stdout)
    (ATTEMPT / f"{name}.stderr.log").write_bytes(process.stderr)
    if junit_from_stdout is not None:
        junit_from_stdout.write_bytes(process.stdout)
    write_run_result(name, command, process.returncode)
    return process.returncode


def _pytest(name: str, *targets: str) -> int:
    return run(
        name,
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            *targets,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
    )


def scale_qualification() -> int:
    return _pytest("scale-qualification", SCALE_QUALIFICATION_TEST)


def load_shedding_test() -> int:
    return _pytest("load-shedding-test", LOAD_SHEDDING_TEST)


def ruff_check() -> int:
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, ATTEMPT_DIR]
    )


def wire_literal_discipline() -> int:
    return _pytest("wire-literal-discipline", WIRE_LITERAL_TEST)


def python_full() -> int:
    return run(
        "full-python-suite",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'full-python-suite.junit.xml'}",
        ],
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_BASES)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "expected": EXPECTED_NODE_FILE_COUNT,
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != EXPECTED_NODE_FILE_COUNT:
        write_run_result(
            "full-node-suite", ["node", "--test", "<inventory-rejected>"], 2
        )
        print(
            f"expected {EXPECTED_NODE_FILE_COUNT} Node test files, found {len(files)}",
            file=sys.stderr,
        )
        return 2
    node = shutil.which("node")
    if node is None:
        write_run_result("full-node-suite", ["node", "--test", *files], 127)
        return 127
    return run(
        "full-node-suite",
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / "full-node-suite.junit.xml",
    )


def diff_check() -> int:
    return run("git-diff-check", ["git", "diff", "--check"])


def main() -> int:
    parser = argparse.ArgumentParser()
    checks = {
        "scale-qualification": scale_qualification,
        "load-shedding-test": load_shedding_test,
        "ruff-check": ruff_check,
        "wire-literal-discipline": wire_literal_discipline,
        "full-python-suite": python_full,
        "full-node-suite": node_full,
        "git-diff-check": diff_check,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
