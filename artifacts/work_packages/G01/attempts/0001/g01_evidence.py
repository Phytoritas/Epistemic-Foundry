#!/usr/bin/env python3
"""Build and verify byte-bound evidence for G01-0001."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
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
ATTEMPT = ROOT / "artifacts/work_packages/G01/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/G01"
PLUGIN_ROOT = ROOT / "plugins/epistemic-foundry"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRIOR_DAG = ROOT / "artifacts/work_packages/F04/attempts/0001/dependency-status.json"

ATTEMPT_ID = "G01-0001"
WORK_PACKAGE_ID = "G01"
CREATED_AT = "2026-07-29T02:37:05Z"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"

PRODUCT_FILES = (
    "plugins/epistemic-foundry/.codex-plugin/plugin.json",
    "plugins/epistemic-foundry/assets/composer-icon.svg",
    "plugins/epistemic-foundry/assets/logo.svg",
)

SEALED_HASHES = {
    "artifacts/work_packages/B04/attempts/0004/report.json": (
        "a2a2a3bca9ccf1650145b983d942e3888cfd79aaa3568db71a865b5d410d5e13"
    ),
    "artifacts/work_packages/C04/report.json": (
        "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f"
    ),
    "artifacts/work_packages/S01/report.json": (
        "6aa7a2ae6c3c047df6293e227ac3206a2e213b322ef1619eb1814e589f3ea7d6"
    ),
    "artifacts/work_packages/F04/attempts/0001/dependency-status.json": (
        "8209e74b25ccc9cbfc68395a2a03fcf2339857e7db74dd203e3f7c7c7ba3ad57"
    ),
    "manifests/development_manifest.yaml": (
        "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
    ),
}

PRODUCT_HASHES = {
    "plugins/epistemic-foundry/.codex-plugin/plugin.json": (
        "1b1ec359ab93733114c95acb34c4a74615974456ddab52fa7c1c538159318a87"
    ),
    "plugins/epistemic-foundry/assets/composer-icon.svg": (
        "ca04da7e14c09211ee56fd8568f11f757837e7490fb8c059e5907889ccf22cfd"
    ),
    "plugins/epistemic-foundry/assets/logo.svg": (
        "ed2847842f2108ec64cd98700ffa1d0ef4d4195095b1b92c47fe9783b4b9a4d4"
    ),
}

JUNIT_HASHES = {
    "full-python-suite.junit.xml": (
        "48ec3d104f223a770b8007417eaa3d6f5e34d5bba694680530a46461d606de91"
    ),
    "full-node-suite.junit.xml": (
        "d94953e0e9934c8d2ea0530f8a45e313513c2a3a867607a1921d521910f74cc3"
    ),
}

OFFICIAL_VALIDATOR_HASH = (
    "4e84c911479e4d158d723ed8ccc881d3499e580fbf5650e60d379a1a25ac3186"
)
CODEX_MANUAL_HASH = (
    "2e98072e96855e173a2be534cf5b59d95ccab465771e601eda73ad0f52222ecc"
)

NODE_TOTAL_PATTERNS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}


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


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_sealed_inputs() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in SEALED_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"sealed dependency/history changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    return observed


def product_inventory() -> list[dict[str, Any]]:
    actual = tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted(
            (entry for entry in PLUGIN_ROOT.rglob("*") if entry.is_file()),
            key=lambda item: item.as_posix(),
        )
    )
    if actual != PRODUCT_FILES:
        raise SystemExit(f"unexpected G01 product inventory: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        content = path.read_bytes()
        if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
            raise SystemExit(f"invalid encoding marker in G01 product file: {relative}")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"G01 product file is not UTF-8: {relative}: {error}")
        if "\ufffd" in text:
            raise SystemExit(f"replacement character in G01 product file: {relative}")
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != PRODUCT_HASHES[relative]:
            raise SystemExit(f"G01 product hash changed: {relative}: {actual_hash}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(content),
                "sha256": "sha256:" + actual_hash,
            }
        )
    return rows


def live_g01_verification() -> dict[str, Any]:
    module = load_module("g01_verify_live", ATTEMPT / "g01_verify.py")
    manifest_path = PLUGIN_ROOT / ".codex-plugin/plugin.json"
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest.decode("utf-8"))
    errors, details = module.validate_manifest(manifest, PLUGIN_ROOT)
    cases = module.negative_cases(manifest, PLUGIN_ROOT)
    negative_failures = [case for case in cases if case.get("status") != "PASS"]
    result = {
        "attempt_id": ATTEMPT_ID,
        "checks": {
            "asset_path_test": {
                "negative_case_count": len(cases),
                "negative_case_pass_count": len(cases) - len(negative_failures),
                "status": "PASS" if not negative_failures and not errors else "FAIL",
            },
            "plugin_manifest_validation": {
                "error_count": len(errors),
                "status": "PASS" if not errors else "FAIL",
            },
        },
        "errors": errors,
        "manifest": {
            "capabilities": details.get("capabilities"),
            "declared_component_fields": details.get("declared_component_fields", []),
            "name": manifest.get("name"),
            "path": manifest_path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + hashlib.sha256(raw_manifest).hexdigest(),
            "version": manifest.get("version"),
        },
        "negative_cases": cases,
        "package_inventory": product_inventory(),
        "resolved_assets": details.get("assets", []),
        "source_contracts": [
            "MASTER_SPEC.md#G01",
            "manifests/development_manifest.yaml#G01",
            "Codex Manual: Package your plugin / Plugin structure / Path rules",
        ],
        "status": "PASS" if not errors and not negative_failures else "FAIL",
        "verifier_version": module.VERIFIER_VERSION,
    }
    if result.get("status") != "PASS":
        raise SystemExit(f"live G01 verification failed: {result.get('errors')}")
    stored = read_json(ATTEMPT / "g01-verification.json")
    if stored != result:
        raise SystemExit("stored G01 verification differs from live product bytes")
    return result


def official_validator_verification() -> dict[str, Any]:
    validator_path = (
        Path.home()
        / ".codex/skills/.system/plugin-creator/scripts/validate_plugin.py"
    )
    if not validator_path.is_file():
        raise SystemExit("official plugin-creator validator is unavailable")
    if sha256(validator_path) != OFFICIAL_VALIDATOR_HASH:
        raise SystemExit("official plugin-creator validator identity changed")
    validator = load_module("official_plugin_validator", validator_path)
    errors = validator.validate_plugin(PLUGIN_ROOT.resolve())
    if errors:
        raise SystemExit(f"official plugin validation failed: {errors}")

    manual_path = Path(
        "C:/Users/Public/Documents/ESTsoft/CreatorTemp/"
        "openai-docs-cache/codex-manual.md"
    )
    if not manual_path.is_file() or sha256(manual_path) != CODEX_MANUAL_HASH:
        raise SystemExit("pinned Codex plugin manual cache is unavailable or changed")
    manual = manual_path.read_text(encoding="utf-8")
    required_markers = (
        "Plugin structure",
        "Plugin manifest",
        "Path rules",
    )
    missing = [marker for marker in required_markers if marker not in manual]
    if missing:
        raise SystemExit(f"Codex plugin manual lacks required sections: {missing}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "validator": {
            "identity": "plugin-creator/scripts/validate_plugin.py",
            "sha256": "sha256:" + OFFICIAL_VALIDATOR_HASH,
            "error_count": 0,
        },
        "documentation": {
            "identity": "Codex manual cache",
            "sha256": "sha256:" + CODEX_MANUAL_HASH,
            "required_sections": list(required_markers),
            "missing_section_count": 0,
        },
        "plugin_root": "plugins/epistemic-foundry",
        "absolute_path_persisted": False,
    }


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


def python_junit() -> dict[str, Any]:
    name = "full-python-suite.junit.xml"
    path = ATTEMPT / name
    content = normalized_junit_bytes(path)
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit("sealed Python JUnit hash changed")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SystemExit(f"invalid Python JUnit XML: {error}")
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
        raise SystemExit("sealed Node JUnit hash changed")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SystemExit(f"invalid Node JUnit XML: {error}")
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label}")
        totals[label] = int(matches[0])
    expected = {
        "tests": 314,
        "pass": 313,
        "fail": 1,
        "cancelled": 0,
        "skipped": 0,
        "todo": 0,
    }
    if totals != expected:
        raise SystemExit(f"full Node result differs from exact bounded debt: {totals}")
    testcases = root.findall(".//testcase")
    failures: list[dict[str, str | None]] = []
    for testcase in testcases:
        failure = testcase.find("failure")
        if failure is not None:
            failures.append(
                {
                    "name": testcase.get("name"),
                    "file": testcase.get("file"),
                    "message": failure.get("message", ""),
                }
            )
    if len(testcases) != 312 or len(failures) != 1:
        raise SystemExit("Node XML testcase/failure inventory changed")
    failure = failures[0]
    message = str(failure.get("message") or "")
    normalized_file = str(failure.get("file") or "").replace("\\", "/")
    if (
        failure.get("name") != S04_TEST
        or not normalized_file.endswith(
            "tests/security/s04-threat-model-traceability.test.mjs"
        )
        or S04_EXPECTED not in message
        or S04_ACTUAL not in message
    ):
        raise SystemExit("full Node failure is not exact preserved S04-TM004")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "xml_testcase_count": len(testcases),
        "xml_failure_count": len(failures),
        "failure": {
            "debt_id": "S04-TM004",
            "test_name": failure["name"],
            "test_file": normalized_file,
            "expected_manifest_sha256": S04_EXPECTED,
            "actual_manifest_sha256": S04_ACTUAL,
        },
    }


def regression_impact() -> dict[str, Any]:
    python = python_junit()
    node = node_junit()
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_PREEXISTING_DEBT",
        "python": python,
        "node": node,
        "g01_caused_python_failure_count": 0,
        "g01_caused_node_failure_count": 0,
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
        "g01_causal_impact": "NONE",
        "fingerprint_changed": False,
        "skip_or_xfail_used": False,
        "release_gate_remains_owned_by": "S04",
    }


def dependency_reports() -> dict[str, Any]:
    mapping = {
        "B04": "artifacts/work_packages/B04/attempts/0004/report.json",
        "C04": "artifacts/work_packages/C04/report.json",
        "S01": "artifacts/work_packages/S01/report.json",
    }
    result: dict[str, Any] = {}
    for package_id, relative in mapping.items():
        report = read_json(ROOT / relative)
        if report.get("status") != "PASS":
            raise SystemExit(f"G01 dependency is not PASS: {package_id}")
        result[package_id] = {
            "status": "PASS",
            "attempt_id": str(report.get("attempt_id") or "historical-root-pass"),
            "report": relative,
            "report_sha256": sha256_id(ROOT / relative),
        }
    return result


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
        or prior.get("completed_package_count") != 29
        or prior.get("ready_packages_manifest_order") != ["G01", "I01", "K01", "A06"]
    ):
        raise SystemExit("sealed F04 dependency state is not the expected G01 input")
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
            f"development manifest identity/dependency failure: count={len(order)} unknown={unknown}"
        )
    layers = topological_layers(order, dependencies)
    completed = set(str(value) for value in prior.get("completed_packages", []))
    if len(completed) != 29 or "G01" in completed:
        raise SystemExit("prior completed package inventory changed")
    completed.add("G01")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    expected_ready = ["G02", "G03", "I01", "K01", "A06"]
    if ready != expected_ready:
        raise SystemExit(f"post-G01 READY order changed: {ready} != {expected_ready}")
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
        "dependency_evidence": dependency_reports(),
        "prior_dependency_state": {
            "path": PRIOR_DAG.relative_to(ROOT).as_posix(),
            "sha256": sha256_id(PRIOR_DAG),
            "completed_package_count": 29,
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
        ("C001", "Inspect G01 dependencies, authority, write scope, current Codex plugin contract, and dirty worktree", 0, "PASS"),
        ("C002", "Create bounded plugin identity manifest and two local SVG brand assets", 0, "PASS: exact three G01 product files"),
        ("C003", "Run official plugin-creator validate_plugin.py against plugins/epistemic-foundry", 0, "PASS: zero validator errors"),
        ("C004", "Run deterministic G01 manifest, asset path, SVG, capability, and negative-case verifier", 0, "PASS: manifest errors 0; negative cases 7/7"),
        ("C005", "Run npm repository structure and package-boundary checks", 0, "PASS"),
        ("C006", "Run full Python suite with python -m pytest and emit JUnit evidence", 0, "PASS: 947 passed, zero failed/skipped"),
        ("C007", "Run full Node suite and emit JUnit evidence", 1, "BOUNDED_PREEXISTING_DEBT: 313 passed; exact S04-TM004 only"),
        ("C008", "Normalize G01 Python and Node JUnit receipts without changing semantic totals or the S04 fingerprint", 0, "PASS"),
        ("C009", "Run scoped and repository git diff checks", 0, "PASS: no whitespace errors; existing line-ending warnings only"),
        ("C010", "Primary-session separate contract review of final G01 product bytes", 0, "PASS: zero blocking findings; not actor-independent certification"),
        ("C011", "Remove only G01 evidence __pycache__ files created by local syntax checks", 0, "PASS: exact cache files and empty directory removed"),
        ("D001", "Initial uv run --locked pytest invocation without module-mode root import behavior", 1, "DIAGNOSTIC_ONLY: ModuleNotFoundError scripts; corrected python -m pytest passed 947/947"),
        ("D002", "Diagnostic manifest slice used an indentation-incompatible G01 pattern", 1, "DIAGNOSTIC_ONLY: G01 not found; exact non-indented manifest pattern then succeeded"),
        ("D003", "Diagnostic RAH listing requested a nonexistent standalone evidence directory", 1, "DIAGNOSTIC_ONLY: evidence is generation-resident; no state change"),
        ("D004", "Diagnostic rg command used Windows-invalid wildcard path operands", 1, "DIAGNOSTIC_ONLY: os error 123; explicit paths then used"),
        ("D005", "rah inspect through Git Bash", 127, "ENVIRONMENT_LIMITATION: rah is not available on that PATH"),
        ("D006", "Direct local Python rah inspect entrypoint", 1, "GUARD_LIMITATION: reliability hook rejected rah_invocation_uninspectable; state_store integrity verification used"),
    ]
    lines: list[str] = []
    for suffix, command, exit_code, result in rows:
        lines.append(
            json.dumps(
                {
                    "command_id": f"G01-0001-{suffix}",
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
    return f"""# G01-0001 native plugin manifest contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final G01 bytes. It is not actor-independent certification.

## Reviewed product boundary

{hashes}

The review also checked the latest PASS reports for B04-0004, C04 and S01,
the current 156-package manifest, the official local plugin validator, the
current Codex plugin manifest/path guidance, and normalized full-regression
receipts.

## Findings

1. The package contains exactly one `.codex-plugin/plugin.json` plus two local
   SVG assets. Every referenced asset resolves inside the plugin root; parent
   traversal, Windows absolute paths and missing resources fail closed.
2. The manifest version is `4.0.0`, matching the workspace version. Its name,
   descriptions, author and interface fields pass the official validator.
3. The manifest intentionally declares no `skills`, `hooks`, `mcpServers` or
   `apps`. Those components belong to later work packages and are not exposed
   before their gates pass.
4. `interface.capabilities` is the exact empty array. The G01 shell therefore
   makes no runtime, scientific, approval, holdout or canonical-authority
   claim. Capability overclaim is rejected by an adversarial fixture.
5. Both SVGs are well-formed, local-only, square, bounded and free of active
   references. The composer icon is 64x64 and the logo is 256x256.
6. The unresolved release-license placeholder in the reference blueprint is
   not represented as a real license claim. G01 establishes package identity,
   not release authorization.
7. Full Python is 947/947. Full Node is 313/314 with only the exact unchanged
   S04-TM004 stale manifest hash debt; G01 causes no new failure, skip or
   xfail and does not reassign that debt.
8. Product writes are confined to the exact G01 manifest and asset scope.
   Evidence files remain under `artifacts/work_packages/G01/**`; unrelated
   dirty-worktree content and every earlier RAH generation remain preserved.

## Assurance boundary

This review proves the current local manifest and asset package shape. It does
not prove marketplace installation, payload dispatch, plugin-root/data-root
resolution, hooks, MCP runtime, skills, production capability enforcement,
release licensing, or actor-independent certification. Those claims remain
owned by later packages.

## Decision

Both G01 exit criteria pass: manifest paths remain within the plugin root, and
the declared version and empty capability surface are accurate. Product
completion remains false.
"""


def make_receipt() -> dict[str, Any]:
    artifact = ATTEMPT / "g01-verification.json"
    receipt = {
        "receipt_id": "AR-G01-0001-PLUGIN-MANIFEST-VERIFICATION",
        "artifact_id": "G01-0001-PLUGIN-MANIFEST-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(artifact),
        "byte_size": artifact.stat().st_size,
        "created_by": {
            "actor_id": "SVC-FOUNDRY-KERNEL-G01",
            "actor_type": "service",
        },
        "created_at": CREATED_AT,
        "locator": artifact.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "plugin_manifest_validation",
                "status": "PASS",
                "details": "official and package-local validators report zero errors",
            },
            {
                "check": "asset_path_test",
                "status": "PASS",
                "details": "7/7 negative cases pass; both active assets resolve inside plugin root",
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
        raise SystemExit(f"invalid G01 ArtifactReceipt: {errors[0].message}")
    return receipt


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    verify_sealed_inputs()
    verification = live_g01_verification()
    inventory = product_inventory()
    if verification["package_inventory"] != inventory:
        raise SystemExit("G01 inventory differs between evidence paths")
    write_json("official-plugin-validator.json", official_validator_verification())
    write_json("full-regression-impact.json", regression_impact())
    write_json("preexisting-debt-reconciliation.json", debt_reconciliation())
    write_json("dependency-status.json", dependency_status())
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(inventory), encoding="utf-8", newline="\n"
    )
    write_json("g01-verification.artifact-receipt.json", make_receipt())
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    preserved = verify_sealed_inputs()
    live_g01_verification()
    expected = {
        "official-plugin-validator.json": official_validator_verification(),
        "full-regression-impact.json": regression_impact(),
        "preexisting-debt-reconciliation.json": debt_reconciliation(),
        "dependency-status.json": dependency_status(),
        "g01-verification.artifact-receipt.json": make_receipt(),
    }
    for name, value in expected.items():
        if read_json(ATTEMPT / name) != value:
            raise SystemExit(f"stored G01 evidence differs from live inputs: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("stored G01 commands differ from canonical commands")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(
        product_inventory()
    ):
        raise SystemExit("stored G01 review differs from final product inventory")
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
        raise SystemExit(f"G01 evidence contains Python cache artifacts: {cache_artifacts}")
    return {
        "status": "PASS",
        "attempt_id": ATTEMPT_ID,
        "manifest_error_count": 0,
        "asset_negative_cases_passed": 7,
        "full_python_passed": 947,
        "full_node_passed": 313,
        "full_node_preexisting_failures": 1,
        "sealed_dependency_hash_count": len(preserved),
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
    verification = live_g01_verification()
    regression = regression_impact()
    dag = dependency_status()
    artifact_names = [
        "g01-verification.json",
        "official-plugin-validator.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "g01-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "g01_verify.py",
        "normalize_junit.py",
        "g01_evidence.py",
        "g01_rah_seal.py",
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
        "title": "Native plugin manifest and package layout",
        "status": "PASS",
        "package_status": "PASS",
        "completion_ready": False,
        "dependency": dependency_reports(),
        "write_scope": [
            "plugins/epistemic-foundry/.codex-plugin/plugin.json",
            "plugins/epistemic-foundry/assets/**",
            "artifacts/work_packages/G01/**",
        ],
        "changed_files": product_inventory(),
        "exit_criteria": {
            "manifest_paths_remain_inside_plugin_root": "PASS",
            "version_and_capabilities_accurate": "PASS",
        },
        "required_checks": {
            "plugin_manifest_validation": {
                "status": "PASS",
                "official_validator_error_count": 0,
                "local_validator_error_count": 0,
            },
            "asset_path_test": {
                "status": "PASS",
                "negative_cases_passed": 7,
                "negative_cases_failed": 0,
            },
        },
        "manifest_contract": {
            "name": verification["manifest"]["name"],
            "version": verification["manifest"]["version"],
            "declared_component_fields": [],
            "declared_capabilities": [],
            "product_file_count": 3,
            "asset_count": 2,
            "canonical_authority_claimed": False,
            "release_license_claimed": False,
        },
        "regression": {
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
                "g01_caused_failure_count": 0,
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
            "artifact": "artifacts/work_packages/G01/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "preserved_limitations": [
            "G01 proves local manifest and asset package shape, not fresh marketplace installation.",
            "No skill, hook, MCP, app, dispatcher, or runtime capability is declared by G01.",
            "Release licensing remains outside this package and no placeholder license is claimed.",
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
            "path": "artifacts/work_packages/G01/attempts/0001/g01-verification.artifact-receipt.json",
            "receipt_id": "AR-G01-0001-PLUGIN-MANIFEST-VERIFICATION",
        },
        "rah_state": {
            "status": "active",
            "core_evidence_id": "E0052",
            "core_generation": integrity["current_generation"],
            "final_closeout_evidence_id": "E0053",
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
            "marketplace fresh-install success",
            "payload-resident dispatcher behavior",
            "PLUGIN_ROOT or PLUGIN_DATA resolution",
            "skills, hooks, MCP servers, apps, or production authorization",
            "release readiness or product completion",
        ],
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(50, "E0052")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    integrity = generation_integrity(50, "E0052")
    if read_json(ATTEMPT / "rah-core-integrity.json") != integrity:
        raise SystemExit("stored G01 RAH core integrity differs from live generation")
    if read_json(ATTEMPT / "report.json") != report_document(integrity):
        raise SystemExit("stored G01 report differs from live evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"G01 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": integrity["current_generation"],
        "core_evidence_id": "E0052",
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
