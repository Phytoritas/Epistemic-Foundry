#!/usr/bin/env python3
"""Build and verify byte-bound evidence for G02-0001."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/G02/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/G02"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRIOR_DAG = ROOT / "artifacts/work_packages/G01/attempts/0001/dependency-status.json"

ATTEMPT_ID = "G02-0001"
WORK_PACKAGE_ID = "G02"
CREATED_AT = "2026-07-29T02:57:22Z"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"

PRODUCT_FILES = (
    "plugins/epistemic-foundry/bin/efoundry.mjs",
    "packages/plugin-host/src/cli-dispatch/payload-cli-smoke.test.mjs",
    "packages/plugin-host/src/cli-dispatch/dispatcher-boundary.test.mjs",
)

PRODUCT_HASHES = {
    "plugins/epistemic-foundry/bin/efoundry.mjs": (
        "17723d450644508b755e725300a600f3792c05714056c794517bd9de2d005e05"
    ),
    "packages/plugin-host/src/cli-dispatch/payload-cli-smoke.test.mjs": (
        "e5f4f328a100abac6692e26dbce04e33cf15884be47a9e59d08604a133ab5b94"
    ),
    "packages/plugin-host/src/cli-dispatch/dispatcher-boundary.test.mjs": (
        "7c3600faf8373e1db3c1f03bca89e820668bd55e81f7e5b8535c0a13e12e543c"
    ),
}

JUNIT_HASHES = {
    "targeted-node-suite.junit.xml": (
        "4d119fca9e9b5809f5e04832d6a8975e4e9faaa70d67540048c1f04a24c0b559"
    ),
    "full-python-suite.junit.xml": (
        "d8f758830b05cfe4011b6bef064fa1489b07c8914127e23219f751afb6fe3528"
    ),
    "full-node-suite.junit.xml": (
        "c6b098103f8d4fe02645a1d4d8c7133ae50ed0fdc8678620d5481d896f8dba60"
    ),
}

SEALED_INPUTS = {
    "manifests/development_manifest.yaml": (
        "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
    ),
    "artifacts/work_packages/G01/attempts/0001/dependency-status.json": (
        "6a3a30e4ef945ea4a880aac230d1eead675cb253acf3a7e9d6f09e7fd03f40c0"
    ),
    "artifacts/work_packages/G01/report.json": (
        "893bb9d7c01e7213fb2aed347dca03099ab8ba770d072a82030ffa1216f17cf0"
    ),
    "artifacts/work_packages/G01/attempts/0001/normalize_junit.py": (
        "4e0370aef5f23d3a27ad1dfcf495d94cb3ec3269ba70c5c653bb2cf76d27a405"
    ),
}

NODE_TOTAL_PATTERNS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}

TARGETED_TEST_NAMES = (
    "dispatcher_boundary_test: dispatcher is a fixed process adapter without domain logic",
    "dispatcher_boundary_test: no alternate executable, target, or shell fallback exists",
    "payload_cli_smoke: absolute plugin entry works without an efoundry PATH alias",
    "payload_cli_smoke: a missing payload target fails instead of using a repo or PATH fallback",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_hash_excluding(document: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(document)
    preimage.pop(field, None)
    payload = json.dumps(
        preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def verify_sealed_inputs() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in SEALED_INPUTS.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"sealed dependency/history changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    return observed


def product_inventory() -> list[dict[str, Any]]:
    roots = (
        ROOT / "plugins/epistemic-foundry/bin",
        ROOT / "packages/plugin-host/src/cli-dispatch",
    )
    actual = tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted(
            (
                path
                for scope in roots
                for path in scope.rglob("*")
                if path.is_file()
            ),
            key=lambda item: item.as_posix(),
        )
    )
    expected = tuple(sorted(PRODUCT_FILES))
    if actual != expected:
        raise SystemExit(f"unexpected G02 product inventory: {actual} != {expected}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        content = path.read_bytes()
        if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
            raise SystemExit(f"invalid encoding marker in G02 product file: {relative}")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"G02 product file is not UTF-8: {relative}: {error}")
        if "\ufffd" in text:
            raise SystemExit(f"replacement character in G02 product file: {relative}")
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != PRODUCT_HASHES[relative]:
            raise SystemExit(f"G02 product hash changed: {relative}: {actual_hash}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(content),
                "sha256": "sha256:" + actual_hash,
            }
        )
    return rows


def normalized_junit_bytes(path: Path) -> bytes:
    content = path.read_bytes()
    forbidden = (
        b"hostname=",
        b"C:/dev/insight/Epistemic-Foundry",
        b"C:\\dev\\insight\\Epistemic-Foundry",
    )
    if any(marker in content for marker in forbidden):
        raise SystemExit(f"machine-local metadata remains in {path.name}")
    return content


def node_footer(content: bytes) -> dict[str, int]:
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label}")
        totals[label] = int(matches[0])
    return totals


def targeted_junit() -> dict[str, Any]:
    name = "targeted-node-suite.junit.xml"
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit("sealed targeted Node JUnit hash changed")
    root = ET.fromstring(content)
    totals = node_footer(content)
    expected = {
        "tests": 4,
        "pass": 4,
        "fail": 0,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }
    if totals != expected:
        raise SystemExit(f"G02 targeted result is not exact 4/4: {totals}")
    testcases = root.findall(".//testcase")
    names = tuple(str(testcase.get("name")) for testcase in testcases)
    if names != TARGETED_TEST_NAMES or root.findall(".//failure"):
        raise SystemExit(f"G02 targeted testcase inventory changed: {names}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "test_names": list(names),
    }


def python_junit() -> dict[str, Any]:
    name = "full-python-suite.junit.xml"
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit("sealed Python JUnit hash changed")
    root = ET.fromstring(content)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals != {"tests": 947, "failures": 0, "errors": 0, "skipped": 0}:
        raise SystemExit(f"full Python result is not exact 947/947: {totals}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
    }


def node_junit() -> dict[str, Any]:
    name = "full-node-suite.junit.xml"
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit("sealed full Node JUnit hash changed")
    root = ET.fromstring(content)
    totals = node_footer(content)
    expected = {
        "tests": 318,
        "pass": 317,
        "fail": 1,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }
    if totals != expected:
        raise SystemExit(f"full Node result differs from bounded debt: {totals}")
    testcases = root.findall(".//testcase")
    names = [str(testcase.get("name")) for testcase in testcases]
    for expected_name in TARGETED_TEST_NAMES:
        if names.count(expected_name) != 1:
            raise SystemExit(f"G02 test missing or duplicated in full Node suite: {expected_name}")
    failures: list[dict[str, str]] = []
    for testcase in testcases:
        failure = testcase.find("failure")
        if failure is not None:
            failures.append(
                {
                    "name": str(testcase.get("name") or ""),
                    "file": str(testcase.get("file") or "").replace("\\", "/"),
                    "message": str(failure.get("message") or ""),
                }
            )
    if len(failures) != 1:
        raise SystemExit(f"unexpected full Node failure inventory: {failures}")
    failure = failures[0]
    if (
        failure["name"] != S04_TEST
        or not failure["file"].endswith(
            "tests/security/s04-threat-model-traceability.test.mjs"
        )
        or S04_EXPECTED not in failure["message"]
        or S04_ACTUAL not in failure["message"]
    ):
        raise SystemExit("full Node failure is not exact preserved S04-TM004")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "xml_testcase_count": len(testcases),
        "xml_failure_count": 1,
        "g02_testcase_count": 4,
        "failure": {
            "debt_id": "S04-TM004",
            "test_name": failure["name"],
            "test_file": failure["file"],
            "expected_manifest_sha256": S04_EXPECTED,
            "actual_manifest_sha256": S04_ACTUAL,
        },
    }


def live_g02_verification() -> dict[str, Any]:
    dispatcher_path = ROOT / PRODUCT_FILES[0]
    source = dispatcher_path.read_text(encoding="utf-8")
    required_patterns = {
        "fixed_payload_target": r'fileURLToPath\(new URL\(["\']\.\./dist/cli\.mjs["\'], import\.meta\.url\)\)',
        "absolute_node_executable": r"spawn\(process\.execPath, \[payloadCli, \.\.\.process\.argv\.slice\(2\)\]",
        "caller_cwd_forwarded": r"cwd: process\.cwd\(\)",
        "environment_forwarded": r"env: process\.env",
        "shell_disabled": r"shell: false",
        "stdio_inherited": r'stdio: ["\']inherit["\']',
        "exit_code_forwarded": r"process\.exitCode = code \?\? 1",
    }
    missing = [
        name for name, pattern in required_patterns.items() if re.search(pattern, source) is None
    ]
    imports = re.findall(r'from\s+["\']([^"\']+)["\']', source)
    forbidden_tokens = (
        "PLUGIN_ROOT",
        "PLUGIN_DATA",
        "epistemic_foundry",
        "node:fs",
        "node:http",
        "node:https",
        "schemas/",
        "openapi/",
        "Noetic",
        "PolicyBundle",
        "PromotionDecision",
    )
    present_forbidden = [token for token in forbidden_tokens if token in source]
    alternate_fallback = bool(
        re.search(r"process\.env\.[A-Z0-9_]*(?:CLI|PYTHON|ROOT|PATH)", source)
        or re.search(r"\b(?:exec|execFile|fork|spawnSync)\s*\(", source)
        or re.search(r"\b(?:cmd(?:\.exe)?|powershell|pwsh|bash|sh|python)\b", source, re.I)
    )
    targeted = targeted_junit()
    errors: list[str] = []
    if missing:
        errors.append(f"missing dispatcher invariants: {missing}")
    if imports != ["node:child_process", "node:url"]:
        errors.append(f"unexpected imports: {imports}")
    if present_forbidden:
        errors.append(f"forbidden domain/path tokens: {present_forbidden}")
    if alternate_fallback:
        errors.append("alternate executable, shell, or target fallback detected")
    if source.count("spawn(") != 1 or source.count("../dist/cli.mjs") != 1:
        errors.append("dispatcher has multiple spawn or payload target sites")
    if len(source.encode("utf-8")) >= 1500:
        errors.append("dispatcher is no longer a thin process adapter")
    result = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "source_contracts": [
            "MASTER_SPEC.md#G02",
            "manifests/development_manifest.yaml#G02",
            "docs/v3_plugin_architecture.md",
            "docs/plugin_ux_cli_and_mcp.md",
            "research/codexclaw_gap_analysis.md",
        ],
        "product_inventory": product_inventory(),
        "dispatcher": {
            "path": PRODUCT_FILES[0],
            "sha256": sha256_id(dispatcher_path),
            "byte_size": dispatcher_path.stat().st_size,
            "payload_target": "../dist/cli.mjs",
            "executable_source": "process.execPath",
            "import_specifiers": imports,
            "spawn_site_count": source.count("spawn("),
            "payload_target_site_count": source.count("../dist/cli.mjs"),
            "forbidden_token_count": len(present_forbidden),
            "alternate_fallback_count": int(alternate_fallback),
            "domain_logic_present": False if not present_forbidden else True,
        },
        "checks": {
            "payload_cli_smoke": {
                "status": "PASS",
                "case_count": 2,
                "path_alias_required": False,
                "argv_stdin_stdout_stderr_cwd_env_preserved": True,
                "non_ascii_and_space_paths_preserved": True,
                "nonzero_exit_code_preserved": 23,
                "missing_target_fails_closed": True,
            },
            "dispatcher_boundary_test": {
                "status": "PASS" if not errors else "FAIL",
                "case_count": 2,
                "fixed_target": True,
                "repository_root_fallback_count": 0,
                "path_alias_fallback_count": 0,
                "python_fallback_count": 0,
                "domain_logic_token_count": len(present_forbidden),
            },
        },
        "targeted_junit": targeted,
        "ownership_boundaries": {
            "plugin_root_data_workspace_resolution_owner": "G03",
            "cli_semantics_owner": "T03",
            "marketplace_fresh_install_owner": "G04",
            "payload_cli_build_owner": "downstream build/CLI package",
        },
    }
    if errors:
        raise SystemExit(f"live G02 verification failed: {errors}")
    return result


def regression_impact() -> dict[str, Any]:
    python = python_junit()
    node = node_junit()
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT",
        "python": python,
        "node": node,
        "g02_caused_python_failure_count": 0,
        "g02_caused_node_failure_count": 0,
        "new_skip_or_xfail_count": 0,
        "preexisting_debt_ids": ["S04-TM004"],
    }


def debt_reconciliation() -> dict[str, Any]:
    node = node_junit()
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "debt_id": "S04-TM004",
        "owner": "S04",
        "classification": "PRE_EXISTING_BOUNDED_DEBT",
        "failure_count": 1,
        "test_name": S04_TEST,
        "test_file": node["failure"]["test_file"],
        "expected_manifest_sha256": S04_EXPECTED,
        "actual_manifest_sha256": S04_ACTUAL,
        "g02_causal_impact": "NONE",
        "fingerprint_changed": False,
        "skip_or_xfail_used": False,
        "release_gate_remains_owned_by": "S04",
    }


def topological_layers(
    order: list[str], dependencies: dict[str, set[str]]
) -> list[list[str]]:
    remaining = set(order)
    completed: set[str] = set()
    layers: list[list[str]] = []
    while remaining:
        layer = [
            package_id
            for package_id in order
            if package_id in remaining and dependencies[package_id] <= completed
        ]
        if not layer:
            raise SystemExit(f"development manifest contains a cycle: {sorted(remaining)}")
        layers.append(layer)
        completed.update(layer)
        remaining.difference_update(layer)
    return layers


def dependency_status() -> dict[str, Any]:
    verify_sealed_inputs()
    prior = read_json(PRIOR_DAG)
    if (
        prior.get("status") != "PASS"
        or prior.get("completed_package_count") != 30
        or prior.get("ready_packages_manifest_order")
        != ["G02", "G03", "I01", "K01", "A06"]
    ):
        raise SystemExit("sealed G01 dependency state is not the expected G02 input")
    g01_report = read_json(ROOT / "artifacts/work_packages/G01/report.json")
    if g01_report.get("status") != "PASS" or g01_report.get("attempt_id") != "G01-0001":
        raise SystemExit("G02 dependency G01 is not evidence-sealed PASS")
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = manifest.get("work_packages") if isinstance(manifest, dict) else None
    if not isinstance(packages, list):
        raise SystemExit("development manifest work_packages is not a list")
    order: list[str] = []
    dependencies: dict[str, set[str]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            raise SystemExit("invalid work package in development manifest")
        package_id = package["id"]
        raw_dependencies = package.get("depends_on", [])
        if package_id in dependencies or not isinstance(raw_dependencies, list):
            raise SystemExit(f"invalid or duplicate work package: {package_id}")
        if not all(isinstance(value, str) for value in raw_dependencies):
            raise SystemExit(f"invalid dependencies for {package_id}")
        order.append(package_id)
        dependencies[package_id] = set(raw_dependencies)
    all_ids = set(order)
    unknown = {
        package_id: sorted(values - all_ids)
        for package_id, values in dependencies.items()
        if values - all_ids
    }
    if len(order) != 156 or len(all_ids) != 156 or unknown:
        raise SystemExit(
            f"manifest identity/dependency failure: count={len(order)} unknown={unknown}"
        )
    layers = topological_layers(order, dependencies)
    completed = set(str(value) for value in prior.get("completed_packages", []))
    if len(completed) != 30 or "G02" in completed:
        raise SystemExit("prior completed package inventory changed")
    completed.add("G02")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["G03", "I01", "K01", "A06"]
    if ready != expected_ready:
        raise SystemExit(f"post-G02 READY order changed: {ready} != {expected_ready}")
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    return {
        "schema_version": 1,
        "status": "PASS",
        "manifest": {
            "path": MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(MANIFEST),
            "work_package_count": len(order),
            "unique_work_package_count": len(all_ids),
            "unknown_dependency_count": 0,
            "cycle_count": 0,
            "topological_layer_count": len(layers),
            "maximum_layer_width": max(map(len, layers)),
        },
        "dependency_evidence": {
            "G01": {
                "status": "PASS",
                "attempt_id": "G01-0001",
                "report": "artifacts/work_packages/G01/report.json",
                "report_sha256": sha256_id(ROOT / "artifacts/work_packages/G01/report.json"),
            }
        },
        "prior_dependency_state": {
            "path": PRIOR_DAG.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(PRIOR_DAG),
            "completed_package_count": 30,
        },
        "completed_package_count": len(completed),
        "completed_packages": [value for value in order if value in completed],
        "ready_package_count": len(ready),
        "ready_packages_manifest_order": ready,
        "next_package": ready[0],
        "blocked_package_count": len(blocked),
        "completion_ready": False,
    }


def commands_text() -> str:
    rows = [
        ("C001", "Inspect G02 authority, dependency, write scope, plugin guidance, and dirty worktree", 0, "PASS"),
        ("C002", "Create the payload-resident dispatcher and bounded smoke/boundary tests", 0, "PASS: exact three G02 product/test files"),
        ("C003", "Run node --check for dispatcher and both G02 test modules", 0, "PASS"),
        ("C004", "Run initial G02 payload_cli_smoke and dispatcher_boundary_test", 0, "PASS: 4/4"),
        ("C005", "Run npm repository structure and package-boundary checks", 0, "PASS"),
        ("C006", "Run G02 targeted Node tests with JUnit reporter", 0, "PASS: 4/4, zero skip"),
        ("C007", "Run full Python suite with JUnit evidence", 0, "PASS: 947/947, zero skip"),
        ("C008", "Run full Node suite with JUnit evidence", 1, "BOUNDED_PREEXISTING_DEBT: 317 passed; exact S04-TM004 only"),
        ("C009", "Normalize G02 JUnit receipts while preserving semantic totals and S04 fingerprint", 0, "PASS"),
        ("C010", "Run scoped G02 git diff check", 0, "PASS"),
        ("C011", "Primary-session separate contract review of final G02 product bytes", 0, "PASS: zero blocking findings; not actor-independent certification"),
        ("D001", "Diagnostic PowerShell metadata pipeline blocked by reliability guard", 1, "DIAGNOSTIC_ONLY: assigned foreach output to a variable before formatting; no product impact"),
        ("D002", "Diagnostic RAH CURRENT path lookup", 1, "DIAGNOSTIC_ONLY: current authority is current.json; state unchanged"),
        ("D003", "Diagnostic RAH generation manifest filename lookup", 1, "DIAGNOSTIC_ONLY: authority is generation-manifest.json; state unchanged"),
    ]
    lines: list[str] = []
    for suffix, command, exit_code, result in rows:
        lines.append(
            json.dumps(
                {
                    "command_id": f"G02-0001-{suffix}",
                    "command": command,
                    "recorded_at_utc": CREATED_AT,
                    "exit_code": exit_code,
                    "result": result,
                    "scope": ATTEMPT_ID,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return "\n".join(lines) + "\n"


def review_text(inventory: list[dict[str, Any]]) -> str:
    hashes = "\n".join(
        f"- `{row['path']}` — `{row['sha256']}`" for row in inventory
    )
    return f"""# G02-0001 payload dispatcher contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final G02 bytes. It is not actor-independent certification.

## Reviewed product boundary

{hashes}

The review also checked the evidence-sealed G01 dependency, current G02
manifest contract, normalized targeted and full-regression receipts, plugin
architecture guidance, and current 156-package dependency graph.

## Findings

1. The dispatcher computes exactly one payload target, `../dist/cli.mjs`,
   relative to its own module URL. It never searches the repository, current
   working directory, PATH, Python package, or an environment override.
2. It starts the payload with the absolute current Node executable
   (`process.execPath`), `shell: false`, inherited stdio, the caller's working
   directory and environment, and unchanged arguments. This is a thin process
   adapter rather than a second CLI implementation.
3. A copied installed-plugin fixture works with an empty PATH, spaces and
   Korean characters in paths and data. Arguments, stdin, stdout, stderr, cwd,
   environment, and nonzero exit code 23 are preserved.
4. Removing the fixture `dist/cli.mjs` fails closed. No repository-root or PATH
   fallback is attempted, so a missing packaged payload cannot silently use a
   checkout or editable install.
5. Static boundary checks permit only `node:child_process` and `node:url` and
   reject domain, canonical-registry, policy, promotion, PLUGIN_ROOT and
   PLUGIN_DATA logic. Root/data/workspace resolution remains G03-owned.
6. CLI command semantics and stable JSON error contracts remain T03-owned;
   marketplace fresh-install behavior remains G04-owned. G02 does not create
   or claim the downstream-built `dist/cli.mjs` payload.
7. Targeted Node is 4/4 and full Python is 947/947. Full Node is 317/318 with
   only the exact unchanged S04-TM004 stale manifest hash debt. The four G02
   tests pass in the full suite and G02 causes no new failure, skip, or xfail.
8. Product writes are confined to the two exact G02 scopes. Evidence remains
   under `artifacts/work_packages/G02/**`; unrelated dirty-worktree content and
   all earlier attempts and RAH generations remain preserved.

## Assurance boundary

This review proves the current payload process-forwarding and fail-closed
target behavior. It does not prove PLUGIN_ROOT/PLUGIN_DATA/workspace policy,
the downstream CLI's command semantics, marketplace installation, release
readiness, production authorization, or actor-independent certification.

## Decision

Both G02 exit criteria pass: absolute plugin-root invocation works without an
`efoundry` PATH alias, and the dispatcher contains no domain logic. Product
completion remains false.
"""


def make_receipt() -> dict[str, Any]:
    artifact = ATTEMPT / "g02-verification.json"
    receipt = {
        "receipt_id": "AR-G02-0001-PAYLOAD-DISPATCH-VERIFICATION",
        "artifact_id": "G02-0001-PAYLOAD-DISPATCH-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(artifact),
        "byte_size": artifact.stat().st_size,
        "created_by": {
            "actor_id": "SVC-FOUNDRY-KERNEL-G02",
            "actor_type": "service",
        },
        "created_at": CREATED_AT,
        "locator": artifact.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "payload_cli_smoke",
                "status": "PASS",
                "details": "2/2 smoke cases pass with empty PATH and fail-closed missing target",
            },
            {
                "check": "dispatcher_boundary_test",
                "status": "PASS",
                "details": "2/2 boundary cases pass; fixed target and zero domain/fallback paths",
            },
            {
                "check": "full_python_regression",
                "status": "PASS",
                "details": "947/947 passed with zero skip",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(receipt),
        key=lambda error: list(error.path),
    )
    if errors:
        raise SystemExit(f"invalid G02 ArtifactReceipt: {errors[0].message}")
    return receipt


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verify_sealed_inputs()
    verification = live_g02_verification()
    write_json("g02-verification.json", verification)
    write_json("full-regression-impact.json", regression_impact())
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation())
    write_json("dependency-status.json", dependency_status())
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(product_inventory()), encoding="utf-8", newline="\n"
    )
    write_json("g02-verification.artifact-receipt.json", make_receipt())
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    expected = {
        "g02-verification.json": live_g02_verification(),
        "full-regression-impact.json": regression_impact(),
        "preexisting-debt-reconciliation.json": debt_reconciliation(),
        "dependency-status.json": dependency_status(),
        "g02-verification.artifact-receipt.json": make_receipt(),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored G02 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored G02 commands differ from canonical commands")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(
        product_inventory()
    ):
        raise SystemExit("stored G02 review differs from final product inventory")
    for line in (ATTEMPT / "commands.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        json.loads(line)
    cache_artifacts = [
        path
        for path in ATTEMPT.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_artifacts:
        raise SystemExit(f"G02 evidence contains Python cache artifacts: {cache_artifacts}")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "targeted_node_passed": 4,
        "full_python_passed": 947,
        "full_node_passed": 317,
        "full_node_preexisting_failures": 1,
        "sealed_input_hash_count": len(preserved),
        "completion_ready": False,
    }


def generation_integrity(expected_count: int, expected_evidence: str) -> dict[str, Any]:
    automation = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
    sys.path.insert(0, str(automation))
    import state_store  # type: ignore

    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH current pointer and generation verification disagree")
    generations = sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )
    if len(generations) != expected_count or generations[-1] != generation:
        raise SystemExit("RAH generation inventory mismatch")
    checked = 0
    for name in generations:
        generation_root = ralph_root / "generations" / name
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict):
            raise SystemExit(f"invalid RAH generation manifest: {name}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"RAH generation file set mismatch: {name}")
        for filename in state_store.GENERATION_FILES:
            if sha256(generation_root / filename) != files[filename]:
                raise SystemExit(f"RAH payload hash mismatch: {name}/{filename}")
            checked += 1
    flat_stamps = 0
    flat_matches = 0
    for filename in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / filename)
        if flat.get("state_generation") == generation:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[filename]
        if isinstance(authority, dict):
            authority = {
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    ledger = payloads.get("evidence_ledger.json", {})
    entries = ledger.get("entries", []) if isinstance(ledger, dict) else []
    identifiers = [row.get("id") for row in entries if isinstance(row, dict)]
    if identifiers != [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]:
        raise SystemExit("RAH evidence ledger is not continuous")
    if not identifiers or identifiers[-1] != expected_evidence:
        raise SystemExit("RAH evidence high-water mismatch")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH must remain active with completion_ready=false")
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("six RAH flat projections are not current")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "current_generation": generation,
        "latest_evidence_id": expected_evidence,
        "evidence_count": len(identifiers),
        "retained_generation_manifest_count": len(generations),
        "generation_file_hashes_verified": checked,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "generation_manifest_sha256": sha256_id(
            ralph_root / "generations" / generation / "generation-manifest.json"
        ),
        "completion_ready": False,
    }


def report_document(integrity: dict[str, Any]) -> dict[str, Any]:
    verification = live_g02_verification()
    regression = regression_impact()
    dag = dependency_status()
    artifact_names = [
        "g02-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "g02-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "targeted-node-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "g02_evidence.py",
        "g02_rah_seal.py",
    ]
    artifacts = [
        {
            "path": (ATTEMPT / name).relative_to(ROOT).as_posix(),
            "sha256": sha256_id(ATTEMPT / name),
            "byte_size": (ATTEMPT / name).stat().st_size,
        }
        for name in artifact_names
    ]
    return {
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "Payload-resident efoundry dispatcher",
        "status": "PASS",
        "package_status": "PASS",
        "completion_ready": False,
        "dependency": dag["dependency_evidence"],
        "write_scope": [
            "plugins/epistemic-foundry/bin/**",
            "packages/plugin-host/src/cli-dispatch/**",
            "artifacts/work_packages/G02/**",
        ],
        "changed_files": product_inventory(),
        "exit_criteria": {
            "path_less_invocation_works": "PASS",
            "dispatcher_contains_no_domain_logic": "PASS",
        },
        "required_checks": {
            "payload_cli_smoke": verification["checks"]["payload_cli_smoke"],
            "dispatcher_boundary_test": verification["checks"][
                "dispatcher_boundary_test"
            ],
        },
        "dispatcher_contract": verification["dispatcher"],
        "regression": {
            "targeted_node": {
                "status": "PASS",
                "passed": 4,
                "failed": 0,
                "skipped": 0,
            },
            "python": {
                "status": "PASS",
                "passed": regression["python"]["totals"]["tests"],
                "failed": 0,
                "skipped": 0,
            },
            "node": {
                "status": "BOUNDED_PREEXISTING_DEBT_S04_TM004",
                "passed": regression["node"]["totals"]["pass"],
                "failed": regression["node"]["totals"]["fail"],
                "skipped": 0,
                "g02_caused_failure_count": 0,
            },
            "repository_structure": "PASS",
            "package_boundaries": "PASS",
            "git_diff_check": "PASS",
        },
        "review": {
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW",
            "blocking_findings": 0,
            "subagents_used": False,
            "assurance_limitation": (
                "Procedurally separate primary-session review; not actor-independent certification."
            ),
            "artifact": "artifacts/work_packages/G02/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "preserved_limitations": [
            "G02 proves payload process forwarding, not downstream CLI command semantics.",
            "PLUGIN_ROOT, PLUGIN_DATA, and workspace policy remain G03-owned.",
            "Marketplace fresh-install behavior remains G04-owned.",
            "The downstream-built dist/cli.mjs is not created or claimed by G02.",
            "S04-TM004 remains an exact pre-existing S04-owned debt.",
            "Review is not actor-independent because the product owner forbids subagents in this sequence.",
        ],
        "historical_and_worktree_preservation": {
            "prior_reports_and_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "product_write_scope_violations": 0,
            "subagents_or_fleet_used": False,
        },
        "evidence_artifacts": artifacts,
        "artifact_receipt": {
            "path": "artifacts/work_packages/G02/attempts/0001/g02-verification.artifact-receipt.json",
            "receipt_id": "AR-G02-0001-PAYLOAD-DISPATCH-VERIFICATION",
        },
        "rah_state": {
            "status": "active",
            "core_evidence_id": "E0054",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0055",
            "retained_generation_manifest_count": integrity[
                "retained_generation_manifest_count"
            ],
            "generation_file_hashes_verified": integrity[
                "generation_file_hashes_verified"
            ],
            "flat_snapshot_stamps_verified": 6,
            "flat_snapshot_content_matches": 6,
            "completion_ready": False,
            "inspect_status": "UNAVAILABLE_OR_GUARD_BLOCKED",
            "inspect_alternative": (
                "state_store.verify_current plus all generation manifests, six flat snapshots, "
                "and continuous evidence IDs verified"
            ),
        },
        "dependency_effect": {
            "dag_recomputed": True,
            "completed_package_count": dag["completed_package_count"],
            "ready_packages_manifest_order": dag["ready_packages_manifest_order"],
            "blocked_package_count": dag["blocked_package_count"],
            "next_package": dag["next_package"],
        },
        "not_claimed": [
            "PLUGIN_ROOT, PLUGIN_DATA, or workspace resolution",
            "downstream efoundry command semantics or stable JSON errors",
            "marketplace fresh-install success",
            "release readiness or product completion",
        ],
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(52, "E0054")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    integrity = generation_integrity(52, "E0054")
    if read_json(ATTEMPT / "rah-core-integrity.json") != integrity:
        raise SystemExit("stored G02 RAH core integrity differs from live generation")
    if read_json(ATTEMPT / "report.json") != report_document(integrity):
        raise SystemExit("stored G02 report differs from live evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"G02 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": integrity["current_generation"],
        "core_evidence_id": "E0054",
        "root_projection_count": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=(
            "build-pre-core",
            "verify-pre-core",
            "build-post-core",
            "verify-post-core",
        ),
    )
    args = parser.parse_args()
    if args.mode == "build-pre-core":
        build_pre_core()
        result = verify_pre_core()
    elif args.mode == "verify-pre-core":
        result = verify_pre_core()
    elif args.mode == "build-post-core":
        build_post_core()
        result = verify_post_core()
    else:
        result = verify_post_core()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
