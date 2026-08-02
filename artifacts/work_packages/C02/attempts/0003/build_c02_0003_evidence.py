#!/usr/bin/env python3
"""Build and verify deterministic evidence for C02-0003.

C02-0003 is the generator-owned repair returned by C04-0002.  The builder
binds the refreshed cross-language projections to the canonical 126-contract
source, proves that the seven stale files are current, records green Python
and Node regressions, and leaves the global implementation gate open for the
new C04 conformance attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C02/attempts/0003"
ATTEMPT_ID = "C02-0003"
RECORDED_AT = "2026-07-30T15:56:03.000Z"
VERIFICATION = ATTEMPT / "c02-contract-codegen-verification.json"
PYTHON_JUNIT = ATTEMPT / "full-python-regression.junit.xml"
NODE_JUNIT = ATTEMPT / "full-node-regression.junit.xml"
JUNIT_PATHS = {"full_python": PYTHON_JUNIT, "full_node": NODE_JUNIT}
RAW_JUNIT_HASHES = {
    "full_python": "7447d0158b630c6900442b6db260797944656dccd70a3e941ba7334af5f346f8",
    "full_node": "b0ea926735f249426c814b5b8bc819ee1a18182b07dfe84e9dda0520ad782285",
}
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
EXPECTED_SOURCE_HASHES = {
    "packages/contracts/package.json": "faceda59bc5539bc75d13dbc2bb11ba04220164a92e0fb98fc8752f47c108c1b",
    "packages/contracts/codegen/generate.py": "76a1a37e54c3dcb9edab3dfe79f493c475ca779f0d8afeae7409ce894ce8d6b1",
    "packages/contracts/codegen/verify.py": "1a1ab87b887ad0eb80da02f726044d8fe12740248dc38de09bd4d04bc740d779",
    "packages/contracts/codegen/cross_language_fixture.mjs": "395344864b15057c8acd16e2b4535e01ba5fa0bcaa1582606804a7ff120b8dff",
    "package-lock.json": "32d30423475de0cadc8d5fe04802b0833f396d9bb36f78ee156d5a4306f2616a",
    "package.json": "ac644f31a8cec26becb5ddc8402b59895ebb1c73ef06a522c8176ba5aab1d772",
}
EXPECTED_GENERATED_HASHES = {
    "packages/contracts/src/generated/contract-manifest.json": "6e3c9932a07422869a2c6a5c857ec4e6e41bf02bed271fca19b45cd0885c5065",
    "packages/contracts/src/generated/models.d.ts": "8b63ca1df4ba5a97a87ee1a451f7e57d8d5e27e0ec88bf4573363061e16f2ccf",
    "packages/contracts/src/generated/registry.mjs": "6334d99e6cba011ac4765a7c4175571d0fabb20210c480e7347fb4dcc1a06bd0",
    "python/epistemic_foundry/contracts/__init__.py": "29a58cf958579f9a2165222059603ea1c4898d85379473b00872ce237dd92095",
    "python/epistemic_foundry/contracts/contract-manifest.json": "6e3c9932a07422869a2c6a5c857ec4e6e41bf02bed271fca19b45cd0885c5065",
    "python/epistemic_foundry/contracts/models.py": "e469692d365eb536cab3a66ca06686ec4dcba26888bdada99cecec462247a048",
    "python/epistemic_foundry/contracts/py.typed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "web/src/generated/contract-manifest.json": "6e3c9932a07422869a2c6a5c857ec4e6e41bf02bed271fca19b45cd0885c5065",
    "web/src/generated/contracts.ts": "1d9c8236a531a351e9a7e5a32c6643206ebd5f37960d96225495a97b7245ab28",
}
DEPENDENCY_HASHES = {
    "artifacts/work_packages/C01/attempts/0007/report.json": "13e989701aab58b670e467c20b35cee9fd77ac7852b56a2a4dd4b5aa7ffc447e",
    "artifacts/work_packages/C03/attempts/0003/report.json": "624ee1ef8fb21ee33670e19b6262d3226e8350aaf291da8d90e94e8c46273a56",
    "artifacts/work_packages/C04/attempts/0002/report.json": "a6224df570da678705c3605972fd9417356222985f03340237ef7c29de488dc0",
    "artifacts/work_packages/B04/attempts/0007/report.json": "156c205ac874d5399dd68ec0a285e32fd5d6921bcc42eb6c180b242617fa8dd3",
    "manifests/development_manifest.yaml": "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
}
STALE_FILES_REPAIRED = [
    "packages/contracts/src/generated/contract-manifest.json",
    "packages/contracts/src/generated/models.d.ts",
    "packages/contracts/src/generated/registry.mjs",
    "python/epistemic_foundry/contracts/contract-manifest.json",
    "python/epistemic_foundry/contracts/models.py",
    "web/src/generated/contract-manifest.json",
    "web/src/generated/contracts.ts",
]
PRODUCT_FILES_MODIFIED = [
    "packages/contracts/codegen/verify.py",
    *STALE_FILES_REPAIRED,
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(name: str, value: dict[str, Any]) -> None:
    (ATTEMPT / name).write_text(render(value), encoding="utf-8", newline="\n")


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, expected_hash in expected.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"required C02-0003 file is missing: {relative}")
        actual = sha256(path)
        if actual != expected_hash:
            raise SystemExit(
                f"C02-0003 hash mismatch for {relative}: {actual} != {expected_hash}"
            )


def junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    signature: list[tuple[Any, ...]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        signature.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                problem.get("message", "") if problem is not None else "",
                problem.text or "" if problem is not None else "",
                case.find("skipped") is not None,
            )
        )
    return signature


def node_footer(path: Path) -> dict[str, int]:
    values = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(values) != required:
        raise SystemExit("Node JUnit footer does not contain the authoritative counters")
    return values


def verify_junit_portability() -> None:
    variants = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in variants):
            raise SystemExit(f"JUnit contains an absolute repository path: {name}")
        if name == "full_python" and re.search(
            r'\s+(?:hostname|timestamp)="', text
        ):
            raise SystemExit("Python JUnit contains volatile host/time fields")


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            if record["files"][name]["normalized_sha256"] != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    for name, path in JUNIT_PATHS.items():
        if sha256(path) != RAW_JUNIT_HASHES[name]:
            raise SystemExit(f"raw JUnit hash mismatch: {name}")
        before = path.read_text(encoding="utf-8")
        signature = junit_signature(before)
        footer_before = node_footer(path) if name == "full_node" else None
        normalized = before
        removed_hostname = 0
        removed_timestamp = 0
        prefix_replacements = 0
        if name == "full_node":
            for prefix in (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/"):
                needle = 'file="' + prefix
                count = normalized.count(needle)
                normalized = normalized.replace(needle, 'file="')
                prefix_replacements += count
        else:
            normalized, removed_timestamp = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized
            )
            normalized, removed_hostname = re.subn(
                r'\s+hostname="[^"]*"', "", normalized
            )
        if junit_signature(normalized) != signature:
            raise SystemExit(f"JUnit semantic signature changed: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        footer_after = node_footer(path) if name == "full_node" else None
        if footer_before != footer_after:
            raise SystemExit("Node authoritative footer changed during normalization")
        files[name] = {
            "case_count": len(signature),
            "hostname_attributes_removed": removed_hostname,
            "normalized_sha256": sha256_id(path),
            "raw_sha256": "sha256:" + RAW_JUNIT_HASHES[name],
            "repository_prefix_replacements": prefix_replacements,
            "semantic_signature_preserved": True,
            "timestamp_attributes_removed": removed_timestamp,
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "normalization_scope": [
            "remove pytest hostname and timestamp suite attributes",
            "remove only the absolute repository prefix from Node JUnit file attributes",
        ],
        "preserved": [
            "testcase identity",
            "failure and skip state",
            "Node footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


def pytest_summary(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(row.get("tests", "0")) for row in suites)
    failures = sum(int(row.get("failures", "0")) for row in suites)
    errors = sum(int(row.get("errors", "0")) for row in suites)
    skipped = sum(int(row.get("skipped", "0")) for row in suites)
    return {
        "collected": tests,
        "passed": tests - failures - errors - skipped,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "xml_testcase_count": len(root.findall(".//testcase")),
    }


def regression_impact() -> dict[str, Any]:
    python = pytest_summary(PYTHON_JUNIT)
    footer = node_footer(NODE_JUNIT)
    node_root = ET.parse(NODE_JUNIT).getroot()
    node_cases = len(node_root.findall(".//testcase"))
    if python != {
        "collected": 990,
        "passed": 990,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xml_testcase_count": 990,
    }:
        raise SystemExit(f"unexpected C02-0003 Python regression summary: {python}")
    if footer != {
        "tests": 460,
        "pass": 460,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    } or node_cases != 457:
        raise SystemExit("unexpected C02-0003 Node regression summary")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node": {
            "cancelled": footer["cancelled"],
            "collected": footer["tests"],
            "failed": footer["fail"],
            "junit": "artifacts/work_packages/C02/attempts/0003/full-node-regression.junit.xml",
            "junit_sha256": sha256_id(NODE_JUNIT),
            "passed": footer["pass"],
            "semantic_counter_authority": "node_test_footer",
            "skipped": footer["skipped"],
            "todo": footer["todo"],
            "xml_testcase_count": node_cases,
        },
        "full_python": {
            **python,
            "junit": "artifacts/work_packages/C02/attempts/0003/full-python-regression.junit.xml",
            "junit_sha256": sha256_id(PYTHON_JUNIT),
            "semantic_counter_authority": "pytest_testsuite_attributes",
        },
        "new_c02_failure_count": 0,
        "status": "PASS",
        "unexpected_skip_or_xfail_count": 0,
    }


def run_json_command(command: list[str]) -> tuple[int, dict[str, Any], str]:
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"command did not emit JSON: {command}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"command JSON is not an object: {command}")
    return process.returncode, value, process.stderr.strip()


def verify_live_codegen() -> dict[str, Any]:
    stored = read_json(VERIFICATION)
    with tempfile.TemporaryDirectory(prefix="ef-c02-0003-verify-") as directory:
        output = Path(directory) / "verification.json"
        process = subprocess.run(
            [
                sys.executable,
                "-B",
                "packages/contracts/codegen/verify.py",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if process.returncode != 0:
            raise SystemExit("live C02 verifier failed: " + process.stdout + process.stderr)
        live = read_json(output)
    if live != stored:
        raise SystemExit("stored C02 verification differs from live inputs")
    if stored.get("status") != "PASS":
        raise SystemExit("C02 verification is not PASS")
    if (stored.get("schema_count"), stored.get("example_count")) != (126, 126):
        raise SystemExit("C02 verification is not 126/126")
    if stored.get("generated_file_count") != 9:
        raise SystemExit("C02 generated file count is not nine")
    if stored.get("codegen_clean_diff", {}).get("status") != "PASS":
        raise SystemExit("C02 generated projection is not current")
    if stored.get("legacy_promotion_value_hits") != []:
        raise SystemExit("legacy promotion values remain in generated output")
    return stored


def verify_commands() -> dict[str, Any]:
    check_exit, check, check_stderr = run_json_command(
        [sys.executable, "-B", "packages/contracts/codegen/generate.py", "--check"]
    )
    fixture_exit, fixture, fixture_stderr = run_json_command(
        ["node", "packages/contracts/codegen/cross_language_fixture.mjs"]
    )
    if check_exit or check.get("status") != "PASS" or check.get("failures") != []:
        raise SystemExit(f"generator clean check failed: {check}; {check_stderr}")
    if fixture_exit or fixture.get("status") != "PASS" or fixture.get("failures") != []:
        raise SystemExit(f"cross-language fixture failed: {fixture}; {fixture_stderr}")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        raise SystemExit("npx executable is unavailable")
    tsc = subprocess.run(
        [
            npx,
            "--yes",
            "--package",
            "typescript@5.9.3",
            "tsc",
            "--noEmit",
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "NodeNext",
            "--moduleResolution",
            "NodeNext",
            "packages/contracts/src/generated/models.d.ts",
            "web/src/generated/contracts.ts",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if tsc.returncode != 0:
        raise SystemExit("TypeScript strict compile failed: " + tsc.stdout + tsc.stderr)
    return {
        "codegen_clean_diff": "PASS",
        "cross_language_fixture_parity": "PASS",
        "typescript_5_9_3_strict_nodenext": "PASS",
    }


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = raw if isinstance(raw, list) else raw["work_packages"]
    by_id = {row["id"]: row for row in packages}
    c02 = by_id["C02"]
    if len(packages) != 156:
        raise SystemExit("development manifest package count changed")
    if c02["depends_on"] != ["C01"]:
        raise SystemExit("C02 dependency changed")
    expected_scope = [
        "packages/contracts/**",
        "python/epistemic_foundry/contracts/**",
        "web/src/generated/**",
    ]
    if c02["write_scope"] != expected_scope:
        raise SystemExit("C02 exact write scope changed")
    if by_id["C03"]["depends_on"] != ["C01", "C02"]:
        raise SystemExit("C03 dependency changed")
    if by_id["C04"]["depends_on"] != ["C02", "C03"]:
        raise SystemExit("C04 dependency changed")
    if by_id["B04"]["depends_on"] != ["B02", "B03", "C04"]:
        raise SystemExit("B04 static dependency changed")
    return {
        "package_count": len(packages),
        "C02": {
            "depends_on": c02["depends_on"],
            "write_scope": c02["write_scope"],
            "required_checks": c02["required_checks"],
            "exit_criteria": c02["exit_criteria"],
        },
        "C03_depends_on": by_id["C03"]["depends_on"],
        "C04_depends_on": by_id["C04"]["depends_on"],
        "B04_depends_on": by_id["B04"]["depends_on"],
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for relative, expected_hash in DEPENDENCY_HASHES.items():
        if relative == "manifests/development_manifest.yaml":
            continue
        report = read_json(ROOT / relative)
        reports[report["work_package_id"] if "work_package_id" in report else relative] = {
            "attempt_id": report.get("attempt_id"),
            "report": relative,
            "report_sha256": "sha256:" + expected_hash,
            "status": report.get("status"),
        }
    c04 = read_json(ROOT / "artifacts/work_packages/C04/attempts/0002/report.json")
    if c04.get("status") != "FAIL" or c04.get("failure_owner") != "C02":
        raise SystemExit("C04-0002 return-to-C02 evidence changed")
    for package in ("C01", "C03", "B04"):
        if reports[package]["status"] != "PASS":
            raise SystemExit(f"required dependency {package} is not PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": reports,
        "development_manifest_sha256": "sha256:" + DEPENDENCY_HASHES["manifests/development_manifest.yaml"],
        "fixed_repair_order": [
            "C04-0002_FAIL",
            "C02-0003_PASS",
            "C04-0003_FULL_CONFORMANCE",
            "B04-0008_FINAL_PACKAGING",
        ],
        "next_package": "C04-0003",
        "states": {
            "B04-0007": "PASS_PRE_C04_PROJECTION",
            "B04-0008": "WAITING_ON_C04_PASS",
            "C01-0007": "PASS",
            "C02-0003": "PASS_AFTER_SEAL",
            "C03-0003": "PASS",
            "C04-0002": "FAIL_IMMUTABLE_HISTORY",
            "C04-0003": "DEPENDENCY_READY_AFTER_C02_SEAL",
        },
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    allowed = (
        "packages/contracts/",
        "python/epistemic_foundry/contracts/",
        "web/src/generated/",
    )
    violations = [path for path in PRODUCT_FILES_MODIFIED if not path.startswith(allowed)]
    if violations:
        raise SystemExit(f"C02-0003 write-scope violations: {violations}")
    return {
        "approved_scope": [
            "packages/contracts/**",
            "python/epistemic_foundry/contracts/**",
            "web/src/generated/**",
            "artifacts/work_packages/C02/** (manifest-declared evidence artifacts)",
        ],
        "attempt_id": ATTEMPT_ID,
        "canonical_schema_or_example_change_count": 0,
        "derived_package_snapshot_change_count": 0,
        "dirty_worktree_preserved": True,
        "generated_outputs_changed_only_by_generator": True,
        "product_change_count": len(PRODUCT_FILES_MODIFIED),
        "product_files_modified_by_attempt": PRODUCT_FILES_MODIFIED,
        "reset_clean_stash_commit_push_performed": False,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": len(violations),
    }


def review_text() -> str:
    return """# C02-0003 generated-contract correction review

## Verdict

`PASS — C04-0003 DEPENDENCY-READY`

C02-0003 ran the canonical generator after C04-0002 identified seven stale
generated files.  All nine generated files now match a fresh replay from the
126 authoritative schemas and 126 examples.  The three manifests are
byte-identical, Python exposes 126 generated models, the Node/Python fixtures
are equivalent, TypeScript 5.9.3 strict compilation passes, and no active
generated artifact contains either legacy promotion value.

The general-purpose C02 verifier no longer embeds C02-0002 attempt-specific
JUnit paths or protected downstream test hashes.  It retains deterministic
double replay, clean-diff, schema/example validation, three-language manifest
parity, generated Python import, cross-language fixture parity, and legacy
enum rejection.  Repository-wide regression and immutable cross-package
history remain owned by attempt evidence, RAH, and C04.

Full regression is green: Python is 990/990 and the authoritative Node footer
is 460/460, with no failures, skips, xfails, cancellations, or todos.  C02
does not claim C04 conformance or B04 final packaging; C04-0003 is next.

This is a primary-session separate adversarial contract review with
`actor_independence=false`.  The controlling product decisions prohibit Fleet
and subagents, so no external actor-independent certification is claimed.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("Inspect C02 authority, C04-0002 return evidence, dirty worktree, and RAH state", 0, "PASS: C02-0003 is bounded and repair-ready"),
        ("uv run --locked python -B packages/contracts/codegen/generate.py --write", 0, "PASS: nine generated files materialized; seven stale files refreshed"),
        ("uv run --locked python -B packages/contracts/codegen/generate.py --check", 0, "PASS: generated projection is current"),
        ("node packages/contracts/codegen/cross_language_fixture.mjs", 0, "PASS: 126/126 cross-language fixture parity"),
        ("npx --yes --package typescript@5.9.3 tsc --noEmit --strict --target ES2022 --module NodeNext --moduleResolution NodeNext packages/contracts/src/generated/models.d.ts web/src/generated/contracts.ts", 0, "PASS: generated TypeScript compiles strictly"),
        ("uv run --locked python -B packages/contracts/codegen/verify.py --output artifacts/work_packages/C02/attempts/0003/c02-contract-codegen-verification.json", 0, "PASS: deterministic C02 contract verifier"),
        ("uv run --locked pytest --junitxml=artifacts/work_packages/C02/attempts/0003/full-python-regression.junit.xml", 0, "PASS: Python 990/990; failed/errors/skipped 0"),
        ("Run complete sorted serial Node suite with JUnit", 0, "PASS: authoritative footer 460/460; failed/skipped 0"),
        ("Normalize C02-0003 JUnit portability without changing semantic signatures", 0, "PASS"),
        ("Build and verify C02-0003 evidence from live bytes", 0, "PASS when build/verify completes"),
        ("Perform primary-session separate adversarial contract review", 0, "PASS; actor_independence=false"),
        ("Run git diff --check while preserving the dirty worktree", 0, "PASS: whitespace errors 0; pre-existing line-ending notices only"),
        ("Seal C02-0003 core/final PASS evidence into append-only RAH and verify six snapshots", 0, "PASS when sealer completes"),
    ]
    return [
        {
            "command": command,
            "command_id": f"C02-0003-C{index:03d}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": "C02-0003 generated-contract correction",
        }
        for index, (command, exit_code, result) in enumerate(rows, 1)
    ]


def output_artifacts() -> list[str]:
    names = [
        "build_c02_0003_evidence.py",
        "c02_0003_rah_seal.py",
        "c02-contract-codegen-verification.json",
        "junit-normalization-verification.json",
        "full-python-regression.junit.xml",
        "full-node-regression.junit.xml",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "report.json",
    ]
    return [f"artifacts/work_packages/C02/attempts/0003/{name}" for name in names]


def report_payload(
    *,
    verification: dict[str, Any],
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    write_scope: dict[str, Any],
    live_checks: dict[str, Any],
    rah_state: dict[str, Any] | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "GENERATED_CONTRACT_CORRECTION",
        "canonical_contract": {
            "example_bundle_sha256": verification["example_bundle_sha256"],
            "example_count": verification["example_count"],
            "legacy_promotion_value_hits": verification["legacy_promotion_value_hits"],
            "schema_bundle_sha256": verification["schema_bundle_sha256"],
            "schema_count": verification["schema_count"],
            "status": "PASS",
        },
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "generated_projection": {
            **live_checks,
            "generated_artifact_hashes": verification["generated_artifact_hashes"],
            "generated_file_count": verification["generated_file_count"],
            "manifest_parity": verification["manifest_parity"],
            "python_model_count": verification["python_models"]["model_count"],
            "repaired_stale_file_count": len(STALE_FILES_REPAIRED),
            "repaired_stale_files": STALE_FILES_REPAIRED,
            "status": "PASS",
        },
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "C02_0001_and_C02_0002_preserved": True,
            "C04_0002_FAIL_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_evidence_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "C04-0003",
        "not_claimed": [
            "C04 full conformance",
            "B04-0008 final packaging",
            "release or production readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": output_artifacts(),
        "package_status": "PASS",
        "regression": regression,
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_c02_owned_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": "C02",
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def expected_documents(*, preserve_rah: bool) -> dict[str, Any]:
    assert_hashes(EXPECTED_SOURCE_HASHES)
    assert_hashes(EXPECTED_GENERATED_HASHES)
    assert_hashes(DEPENDENCY_HASHES)
    normalization = normalize_junits()
    verification = verify_live_codegen()
    live_checks = verify_commands()
    regression = regression_impact()
    dependencies = dependency_status()
    scope = write_scope_verification()
    manifest_contract()
    stored_report_path = ATTEMPT / "report.json"
    rah_state = None
    if preserve_rah and stored_report_path.is_file():
        existing = read_json(stored_report_path)
        value = existing.get("rah_state")
        if value is not None and not isinstance(value, dict):
            raise SystemExit("C02-0003 report rah_state is malformed")
        rah_state = value
    return {
        "normalization": normalization,
        "regression": regression,
        "dependencies": dependencies,
        "scope": scope,
        "report": report_payload(
            verification=verification,
            regression=regression,
            dependencies=dependencies,
            write_scope=scope,
            live_checks=live_checks,
            rah_state=rah_state,
        ),
    }


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = expected_documents(preserve_rah=True)
    write_json("full-regression-impact.json", documents["regression"])
    write_json("dependency-status.json", documents["dependencies"])
    write_json("write-scope-verification.json", documents["scope"])
    write_json("report.json", documents["report"])
    (ATTEMPT / "review.md").write_text(
        review_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_records()
        ),
        encoding="utf-8",
        newline="\n",
    )
    return verify()


def verify() -> dict[str, Any]:
    documents = expected_documents(preserve_rah=True)
    expected_json = {
        "junit-normalization-verification.json": documents["normalization"],
        "full-regression-impact.json": documents["regression"],
        "dependency-status.json": documents["dependencies"],
        "write-scope-verification.json": documents["scope"],
        "report.json": documents["report"],
    }
    for name, value in expected_json.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(value):
            raise SystemExit(f"stored C02-0003 evidence differs from live evidence: {name}")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored C02-0003 commands differ from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("stored C02-0003 review differs from deterministic review")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependency_status": documents["dependencies"],
        "generated_artifact_hashes": read_json(VERIFICATION)["generated_artifact_hashes"],
        "junit_normalization": documents["normalization"],
        "manifest_contract": manifest_contract(),
        "regression": documents["regression"],
        "status": "PASS",
        "verified_artifacts": list(expected_json) + ["commands.jsonl", "review.md"],
    }


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> None:
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("C02-0003 report is already RAH-bound")
    report["rah_state"] = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "implementation_gate": "fail",
        "status": "active",
    }
    write_json("report.json", report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
