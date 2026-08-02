#!/usr/bin/env python3
"""Run L02-0001 verification into attempt-local evidence files only."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/L02/attempts/0001"
ATTEMPT_ID = "L02-0001"

TARGETED_NODE = (
    "packages/foundry-kernel/src/memory/index/memory-scope.test.mjs",
    "packages/foundry-kernel/src/memory/index/retrieval-receipt.test.mjs",
)
PREDECESSOR_NODE = (
    "packages/foundry-kernel/src/memory/policy/consent-policy.test.mjs",
    "packages/foundry-kernel/src/memory/policy/retention.test.mjs",
)
PRODUCT_FILES = (
    "packages/foundry-kernel/src/memory/index/memory-index.mjs",
    "packages/foundry-kernel/src/memory/index/index.mjs",
    "packages/foundry-kernel/src/memory/index/memory-index-test-support.mjs",
    *TARGETED_NODE,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def ensure_attempt_metadata() -> None:
    path = ATTEMPT / "attempt-metadata.json"
    if path.is_file():
        return
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    write_json(
        path,
        {
            "attempt_id": ATTEMPT_ID,
            "recorded_at_utc": recorded_at,
            "work_package_id": "L02",
        },
    )


def run(
    command: list[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> int:
    executable = command
    if sys.platform == "win32" and command[0] == "npm":
        executable = ["cmd.exe", "/d", "/c", "npm.cmd", *command[1:]]
    completed = subprocess.run(
        executable,
        cwd=ROOT,
        stdout=subprocess.PIPE if stdout_path is not None else None,
        stderr=subprocess.PIPE if stderr_path is not None else None,
        check=False,
    )
    if stdout_path is not None:
        stdout_path.write_bytes(completed.stdout)
    if stderr_path is not None:
        stderr_path.write_bytes(completed.stderr)
    return completed.returncode


def node_test(paths: tuple[str, ...], name: str) -> int:
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *paths],
        stdout_path=ATTEMPT / f"{name}.junit.xml",
        stderr_path=ATTEMPT / f"{name}.junit.xml.stderr.log",
    )


def syntax() -> int:
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    checks: list[dict[str, object]] = []
    final = 0
    for relative in PRODUCT_FILES:
        completed = subprocess.run(
            [node, "--check", relative],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        checks.append(
            {
                "exit_code": completed.returncode,
                "path": relative,
                "stderr": completed.stderr,
                "stdout": completed.stdout,
            }
        )
        final = max(final, completed.returncode)
    write_json(
        ATTEMPT / "syntax-verification.json",
        {
            "attempt_id": ATTEMPT_ID,
            "checks": checks,
            "final_status": "PASS" if final == 0 else "FAIL",
        },
    )
    return final


def targeted() -> int:
    return node_test(TARGETED_NODE, "targeted-l02-node")


def coverage() -> int:
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    return run(
        [
            node,
            "--test",
            "--experimental-test-coverage",
            "--test-concurrency=1",
            *TARGETED_NODE,
        ],
        stdout_path=ATTEMPT / "targeted-l02-coverage.stdout.log",
        stderr_path=ATTEMPT / "targeted-l02-coverage.stderr.log",
    )


def predecessor() -> int:
    return node_test(PREDECESSOR_NODE, "predecessor-l02-node")


def full_node() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    write_json(
        ATTEMPT / "node-test-inventory.json",
        {
            "attempt_id": ATTEMPT_ID,
            "count": len(files),
            "files": files,
            "unique": len(files) == len(set(files)),
        },
    )
    if len(files) != len(set(files)):
        print("duplicate Node test path in inventory", file=sys.stderr)
        return 2
    return node_test(tuple(files), "full-node-suite")


def full_python() -> int:
    return run(
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
        stdout_path=ATTEMPT / "full-python-suite.junit.xml.stdout.log",
        stderr_path=ATTEMPT / "full-python-suite.junit.xml.stderr.log",
    )


def schema_runtime() -> int:
    node = shutil.which("node")
    if node is None:
        print("node executable not found", file=sys.stderr)
        return 127
    program = r'''
import {
  retrievePermittedMemory,
  validateMemoryRetrievalReceipt,
} from "./packages/foundry-kernel/src/memory/index/index.mjs";
import {
  makeIndex,
  makeRequest,
} from "./packages/foundry-kernel/src/memory/index/memory-index-test-support.mjs";
const result = retrievePermittedMemory({ index: makeIndex(), request: makeRequest() });
const receipt = validateMemoryRetrievalReceipt(result.receipt);
process.stdout.write(JSON.stringify({ receipt }));
'''
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", program],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    result: dict[str, object] = {
        "attempt_id": ATTEMPT_ID,
        "node_exit_code": completed.returncode,
        "node_stderr": completed.stderr,
        "schema": "schemas/memory-retrieval-receipt.schema.json",
    }
    status = completed.returncode
    if status == 0:
        try:
            values = json.loads(completed.stdout)
            receipt = values["receipt"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            result["parse_error"] = str(error)
            status = 2
        else:
            schema = json.loads(
                (ROOT / "schemas/memory-retrieval-receipt.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            Draft202012Validator.check_schema(schema)
            errors = sorted(
                Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                    receipt
                ),
                key=lambda item: list(item.absolute_path),
            )
            result["error_count"] = len(errors)
            result["errors"] = [error.message for error in errors]
            result["sealed_receipt"] = receipt
            if errors:
                status = 1
    result["final_status"] = "PASS" if status == 0 else "FAIL"
    write_json(ATTEMPT / "schema-runtime-verification.json", result)
    return status


def codegen() -> int:
    return run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "packages/contracts/codegen/verify.py",
            "--repo-root",
            ".",
        ],
        stdout_path=ATTEMPT / "codegen-verification.stdout.log",
        stderr_path=ATTEMPT / "codegen-verification.stderr.log",
    )


def structure() -> int:
    return run(
        ["npm", "run", "check:structure"],
        stdout_path=ATTEMPT / "structure-check.stdout.log",
        stderr_path=ATTEMPT / "structure-check.stderr.log",
    )


def boundaries() -> int:
    return run(
        ["npm", "run", "check:boundaries"],
        stdout_path=ATTEMPT / "boundary-check.stdout.log",
        stderr_path=ATTEMPT / "boundary-check.stderr.log",
    )


def diff_check() -> int:
    return run(
        ["git", "diff", "--check"],
        stdout_path=ATTEMPT / "git-diff-check.stdout.log",
        stderr_path=ATTEMPT / "git-diff-check.stderr.log",
    )


CHECKS = {
    "syntax": syntax,
    "targeted": targeted,
    "coverage": coverage,
    "schema-runtime": schema_runtime,
    "predecessor": predecessor,
    "full-node": full_node,
    "full-python": full_python,
    "codegen": codegen,
    "structure": structure,
    "boundaries": boundaries,
    "diff-check": diff_check,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=tuple(CHECKS))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    ensure_attempt_metadata()
    return CHECKS[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
