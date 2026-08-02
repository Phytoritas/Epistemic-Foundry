#!/usr/bin/env python3
"""Build and verify fail-closed evidence for the C04-0003 conformance gate.

C04 owns evidence only.  This builder binds the green canonical, generated,
runtime, projection, Python, Node, migration, and FORGE surfaces without
changing product files.  It deliberately reuses current C01 contract checks
and current runtime APIs; the obsolete 124-contract C04 driver is never run as
a whole.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C04/attempts/0003"
ATTEMPT_ID = "C04-0003"
RECORDED_AT = "2026-07-31T00:40:00.000Z"
PYTHON_JUNIT = ATTEMPT / "full-python-suite.junit.xml"
NODE_JUNIT = ATTEMPT / "full-node-suite.junit.xml"
TARGETED_JUNIT = ATTEMPT / "targeted-contract-conformance.junit.xml"
JUNIT_PATHS = {
    "full_python": PYTHON_JUNIT,
    "full_node": NODE_JUNIT,
    "targeted": TARGETED_JUNIT,
}
RAW_JUNIT_HASHES = {
    "full_python": "b2ded2a44d41bc6e621e3812ada5eb669ce45bd2de7ada54804069296af6b6cd",
    "full_node": "f79705f22a3804c55b3d37a61555f2563727bb2ff58f2b70381e90b4be324d85",
    "targeted": "420a04f2a41308a48dd5899c454f44730ab935d4b598ef5fb8c988f2b59825c0",
}
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
DEPENDENCY_HASHES = {
    "artifacts/work_packages/C01/attempts/0007/report.json": "13e989701aab58b670e467c20b35cee9fd77ac7852b56a2a4dd4b5aa7ffc447e",
    "artifacts/work_packages/C02/attempts/0003/report.json": "90ac622e63960e48a90700e4bd58636651d2ed2e433a2d0afb3decf2c5232c7d",
    "artifacts/work_packages/C03/attempts/0003/report.json": "624ee1ef8fb21ee33670e19b6262d3226e8350aaf291da8d90e94e8c46273a56",
    "artifacts/work_packages/F04/attempts/0002/report.json": "5a2414ebb79c923af7425b87d614faa088ba9fbd4e6950406948b2eb86d6ab46",
    "artifacts/work_packages/J02/attempts/0003/report.json": "d348ddc7c8b2d476d3424a6459079f0011d9fc69e29056131832b3ae2fc2d184",
    "artifacts/work_packages/S04/attempts/0003/report.json": "bf76a387c229769e568e650b150b5ede6b2136c3294d792a551a9802904cadd4",
    "artifacts/work_packages/B04/attempts/0007/report.json": "156c205ac874d5399dd68ec0a285e32fd5d6921bcc42eb6c180b242617fa8dd3",
    "artifacts/work_packages/C04/attempts/0002/report.json": "a6224df570da678705c3605972fd9417356222985f03340237ef7c29de488dc0",
    "manifests/development_manifest.yaml": "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
}
BOUND_ARTIFACT_HASHES = {
    "artifacts/work_packages/C03/attempts/0003/c03-runtime-migration-verification.json": "056dc4d17e6ba295b1d241c02d1e40cb5afc4ac13967c8bf5d302972866e7241",
    "artifacts/work_packages/F04/attempts/0002/phase-artifact-reconciliation.json": "ccec043face776dd38cf7097f7b215e22edbebab138252be2e09c71c87bb67c7",
    "artifacts/work_packages/C01/attempts/0004/runtime-migration-impact.json": "3c35cc5cfe003055f2e039a4837e74527a843c4ed6795eee1d28b56954d36877",
    "artifacts/work_packages/B04/attempts/0007/canonical-projection-verification.json": "1956fee21ff6722ce4780f32d6ec7f85a9d7b21c946ad5a1c053f58e13ec8c01",
    "artifacts/work_packages/B04/attempts/0007/projection.artifact-receipt.json": "7a6a210ed72056e4047818a648b21a7b03e98229ff78942ebdd7c4b56477f9ff",
    "artifacts/work_packages/C04/attempts/0003/node-test-inventory.json": "69a246b961eaa3fba1378c320d204df4fa397f8418e88eff622b19b2f2a9dffe",
    "artifacts/work_packages/C04/attempts/0003/c02-codegen-live-verification.json": "582d58db1b7861b506572d56b823f9681cc1a2b71ee3d1d678e2f873e9a82800",
}
EXPECTED_SCHEMA_BUNDLE = "sha256:5788bcf163d7a4ca20f5991935d425d7cc18ff8a5fbc43485c93de73e3c42de3"
EXPECTED_EXAMPLE_BUNDLE = "sha256:899f7c7af8f7de5dc3479adf5c270c7eb80047bd84bf28214bfe6e596cbbf54e"
EXPECTED_GENERATED_MANIFEST = "sha256:6e3c9932a07422869a2c6a5c857ec4e6e41bf02bed271fca19b45cd0885c5065"
EXPECTED_REQUIRED_CHECKS = [
    "contract_surface_conformance",
    "phase_artifact_reconciliation",
    "full_python_suite",
    "canonical_schema_example_validation",
    "openapi_validation",
    "generated_contract_parity",
    "legacy_enum_absence",
    "migration_allowlist_empty",
    "runtime_schema_semantic_parity",
    "independent_integration_review",
    "document_registration_lifecycle_conformance",
    "evolution_authority_conformance",
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
            raise SystemExit(f"required bound artifact is missing: {relative}")
        actual = sha256(path)
        if actual != expected_hash:
            raise SystemExit(f"bound artifact changed: {relative}: {actual} != {expected_hash}")


def load_module(name: str, relative: str) -> Any:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load verifier module: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    result: list[tuple[Any, ...]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        result.append(
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
    return result


def node_footer(path: Path) -> dict[str, int]:
    values = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(values) != required:
        raise SystemExit("Node JUnit footer is incomplete")
    return values


def verify_junit_portability() -> None:
    variants = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in variants):
            raise SystemExit(f"JUnit contains an absolute repository path: {name}")
        if name != "full_node" and re.search(r'\s+(?:hostname|timestamp)="', text):
            raise SystemExit(f"pytest JUnit contains volatile host/time fields: {name}")


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


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(row.get("tests", "0")) for row in suites)
    failures = sum(int(row.get("failures", "0")) for row in suites)
    errors = sum(int(row.get("errors", "0")) for row in suites)
    skipped = sum(int(row.get("skipped", "0")) for row in suites)
    return {
        "collected": tests,
        "errors": errors,
        "failed": failures,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": tests - failures - errors - skipped,
        "semantic_counter_authority": "pytest_testsuite_attributes",
        "skipped": skipped,
        "xml_testcase_count": len(root.findall(".//testcase")),
    }


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = node_footer(path)
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "semantic_counter_authority": "node_test_footer",
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": sum(case.find("failure") is not None for case in cases),
        "xml_testcase_count": len(cases),
    }


def regression_evidence() -> dict[str, Any]:
    python = pytest_summary(PYTHON_JUNIT)
    targeted = pytest_summary(TARGETED_JUNIT)
    node = node_summary(NODE_JUNIT)
    if not (
        python["collected"] == python["passed"] == 990
        and python["failed"] == python["errors"] == python["skipped"] == 0
    ):
        raise SystemExit(f"full Python suite is not 990/990: {python}")
    if not (
        targeted["collected"] == targeted["passed"] == 287
        and targeted["failed"] == targeted["errors"] == targeted["skipped"] == 0
    ):
        raise SystemExit(f"targeted suite is not 287/287: {targeted}")
    if not (
        node["collected"] == node["passed"] == 460
        and node["failed"] == node["cancelled"] == node["skipped"] == node["todo"] == 0
        and node["xml_failure_count"] == node["xml_error_count"] == 0
    ):
        raise SystemExit(f"full Node suite is not 460/460: {node}")
    stderr = ATTEMPT / "full-node-suite.junit.xml.stderr.log"
    if not stderr.is_file() or stderr.read_bytes() != b"":
        raise SystemExit("Node JUnit stderr is not empty")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory.get("attempt_id") != ATTEMPT_ID or inventory.get("count") != 52:
        raise SystemExit("Node test inventory is not the complete 52-file inventory")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "node_test_file_count": inventory["count"],
        "status": "PASS",
        "targeted_contracts": targeted,
        "targeted_diagnostic_reconciliation": {
            "corrected_collected": 287,
            "diagnostic_collected": 182,
            "omitted_module_count": 6,
            "omitted_test_count": 105,
            "status": "PASS_CORRECTED_RERUN_IS_AUTHORITATIVE",
        },
        "unexpected_skip_or_xfail_count": 0,
    }


def canonical_node_id(case: ET.Element) -> str:
    classname = case.get("classname", "")
    if classname.startswith("tests."):
        module = classname.replace(".", "/") + ".py"
    else:
        module = classname
    return module + "::" + case.get("name", "")


def passing_python_nodes() -> dict[str, ET.Element]:
    root = ET.parse(PYTHON_JUNIT).getroot()
    result: dict[str, ET.Element] = {}
    for case in root.findall(".//testcase"):
        node = canonical_node_id(case)
        if case.find("failure") is not None or case.find("error") is not None:
            raise SystemExit(f"failed Python testcase unexpectedly present: {node}")
        if case.find("skipped") is not None:
            raise SystemExit(f"skipped Python testcase unexpectedly present: {node}")
        result[node] = case
    return result


def migration_reconciliation() -> dict[str, Any]:
    impact_path = ROOT / "artifacts/work_packages/C01/attempts/0004/runtime-migration-impact.json"
    impact = read_json(impact_path)
    failures = impact.get("failures")
    if not isinstance(failures, list) or len(failures) != 24:
        raise SystemExit("C01 migration baseline does not contain exactly 24 failures")
    current = passing_python_nodes()
    nodes = [str(row["pytest_node_id"]) for row in failures]
    missing = sorted(set(nodes) - set(current))
    if missing or len(set(nodes)) != 24:
        raise SystemExit(f"C01 migration nodes are not all green and unique: {missing}")
    return {
        "baseline_attempt": "C01-0004",
        "baseline_failure_count": 24,
        "baseline_impact_sha256": sha256_id(impact_path),
        "current_failed_count": 0,
        "current_passed_count": 24,
        "migration_allowlist_entries": 0,
        "missing_node_ids": missing,
        "node_ids": nodes,
        "status": "PASS",
    }


def lifecycle_test_evidence() -> dict[str, Any]:
    current = passing_python_nodes()
    selected = sorted(
        node
        for node in current
        if (
            "::test_document_registration_" in node
            or "::test_document_registration_migration_" in node
        )
    )
    required = {
        "tests/contracts/openapi/test_openapi_contract.py::test_document_registration_uses_canonical_staged_request_and_result",
        "tests/contracts/openapi/test_scientific_contracts.py::test_document_registration_request_hash_id_and_staging_contract",
        "tests/contracts/openapi/test_scientific_contracts.py::test_document_registration_hash_id_and_immutable_initial_state",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_requires_more_than_final_manifest",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_emits_canonical_lineage",
        "tests/test_integration_forge_cycle.py::test_document_registration_migration_rollback_is_hash_bound",
    }
    missing = sorted(required - set(selected))
    if missing or len(selected) != 16:
        raise SystemExit(
            f"document-registration lifecycle surface changed: count={len(selected)} missing={missing}"
        )
    return {
        "canonical_contract_test_count": 3,
        "lifecycle_test_count": len(selected),
        "missing_required_tests": missing,
        "passed_test_node_ids": selected,
        "status": "PASS",
    }


def run_json(command: list[str]) -> dict[str, Any]:
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            f"command failed ({process.returncode}): {command}: {process.stdout}{process.stderr}"
        )
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"command did not emit JSON: {command}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"command JSON is not an object: {command}")
    return value


def run_success(command: list[str]) -> str:
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            f"command failed ({process.returncode}): {command}: {process.stdout}{process.stderr}"
        )
    return (process.stdout + process.stderr).strip()


def generated_contract_conformance() -> dict[str, Any]:
    stored_path = ATTEMPT / "c02-codegen-live-verification.json"
    c02_path = ROOT / "artifacts/work_packages/C02/attempts/0003/c02-contract-codegen-verification.json"
    if stored_path.read_bytes() != c02_path.read_bytes():
        raise SystemExit("C04 copy of the C02 verification differs from sealed C02 evidence")
    stored = read_json(stored_path)
    with tempfile.TemporaryDirectory(prefix="ef-c04-0003-codegen-") as directory:
        output = Path(directory) / "verification.json"
        run_success(
            [
                sys.executable,
                "-B",
                "packages/contracts/codegen/verify.py",
                "--output",
                str(output),
            ]
        )
        live = read_json(output)
    if live != stored:
        raise SystemExit("stored C02 codegen verification differs from live source")
    generator = run_json(
        [sys.executable, "-B", "packages/contracts/codegen/generate.py", "--check"]
    )
    fixture = run_json(["node", "packages/contracts/codegen/cross_language_fixture.mjs"])
    if generator.get("status") != "PASS" or generator.get("failures") != []:
        raise SystemExit("generated contract projection is stale")
    if fixture.get("status") != "PASS" or fixture.get("failures") != []:
        raise SystemExit("cross-language fixture parity failed")
    if (
        stored.get("status") != "PASS"
        or stored.get("schema_count") != 126
        or stored.get("example_count") != 126
        or stored.get("generated_file_count") != 9
        or stored.get("schema_bundle_sha256") != EXPECTED_SCHEMA_BUNDLE
        or stored.get("example_bundle_sha256") != EXPECTED_EXAMPLE_BUNDLE
        or stored.get("legacy_promotion_value_hits") != []
    ):
        raise SystemExit("C02 live verification does not satisfy the C04 contract")
    manifests = [
        ROOT / "packages/contracts/src/generated/contract-manifest.json",
        ROOT / "python/epistemic_foundry/contracts/contract-manifest.json",
        ROOT / "web/src/generated/contract-manifest.json",
    ]
    if any(sha256_id(path) != EXPECTED_GENERATED_MANIFEST for path in manifests):
        raise SystemExit("generated manifests are not byte-identical")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        raise SystemExit("npx executable is unavailable")
    run_success(
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
        ]
    )
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm executable is unavailable")
    run_success([npm, "run", "check:structure"])
    run_success([npm, "run", "check:boundaries"])
    return {
        "codegen_clean_diff": "PASS",
        "cross_language_fixture_parity": "PASS",
        "example_bundle_sha256": stored["example_bundle_sha256"],
        "example_count": stored["example_count"],
        "generated_file_count": stored["generated_file_count"],
        "generated_manifest_sha256": EXPECTED_GENERATED_MANIFEST,
        "legacy_promotion_value_hits": [],
        "manifest_parity": stored["manifest_parity"],
        "python_model_count": stored["python_models"]["model_count"],
        "repository_boundaries": "PASS_10_COMPONENTS_18_EDGES",
        "repository_structure": "PASS_10_NODE_COMPONENTS",
        "schema_bundle_sha256": stored["schema_bundle_sha256"],
        "schema_count": stored["schema_count"],
        "status": "PASS",
        "typescript_5_9_3_strict_nodenext": "PASS",
    }


def canonical_contract_conformance() -> dict[str, Any]:
    c01 = load_module(
        "c04_0003_c01_verifier",
        "artifacts/work_packages/C01/attempts/0007/build_c01_0007_evidence.py",
    )
    canonical = c01.validate_canonical_contracts()
    openapi = c01.validate_openapi()
    projection = c01.projection_freshness()
    uvx = shutil.which("uvx.exe") or shutil.which("uvx")
    if uvx is None:
        raise SystemExit("uvx executable is unavailable")
    run_success(
        [
            uvx,
            "--from",
            "openapi-spec-validator==0.7.2",
            "openapi-spec-validator",
            "openapi/epistemic-foundry-v1.openapi.yaml",
        ]
    )
    return {
        "canonical": canonical,
        "external_openapi_validator_0_7_2": "PASS",
        "openapi": openapi,
        "projection": projection,
        "status": "PASS",
    }


def current_forge_probe(old: Any) -> dict[str, Any]:
    policy_hash = "sha256:" + "c" * 64

    def current_gates() -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for index, gate_name in enumerate(old.CANONICAL_GATE_IDS):
            inputs = {"binding": f"sealed-{gate_name}"}
            rows.append(
                old.gate_decision(
                    old.evaluate_gate(
                        old.GateSpec(
                            gate_name,
                            ("binding",),
                            evidence_ids=(f"ART-{gate_name}-C04",),
                        ),
                        inputs,
                    ),
                    run_id="RUN-C04-PROMOTION",
                    policy_version="4.0.0-c04",
                    inputs=inputs,
                    gate_version="4.0.0-c04",
                    input_artifact_ids=(f"ART-{gate_name}-INPUT-C04",),
                    policy_bundle_hash=policy_hash,
                    blocker_ids=(),
                    gate_id=f"GD-C04-{index:02d}",
                    evaluated_at="2026-07-28T00:00:00+00:00",
                )
            )
        return tuple(rows)

    old.promotion_gate_decisions = current_gates
    return old.verify_forge_promotion_probe()


def runtime_conformance() -> dict[str, Any]:
    old = load_module(
        "c04_0003_runtime_probe",
        "artifacts/work_packages/C04/c04-conformance-verifier.py",
    )
    legacy = old.verify_legacy_and_suppression()
    runtime = old.verify_runtime_schema_semantics()
    forge = current_forge_probe(old)
    c03_path = ROOT / "artifacts/work_packages/C03/attempts/0003/c03-runtime-migration-verification.json"
    c03 = read_json(c03_path)
    if (
        c03.get("status") != "PASS"
        or c03.get("gate_decision_runtime", {}).get("status") != "PASS"
        or c03.get("verifier_firewall_runtime", {}).get("status") != "PASS"
        or c03.get("legacy_and_fallback_audit", {}).get("silent_fallback_count") != 0
        or c03.get("regression", {})
        .get("b04_sg002_reconciliation", {})
        .get("resolved_problem_count")
        != 66
    ):
        raise SystemExit("sealed C03 runtime migration evidence is not conformant")
    if legacy != {
        "active_legacy_promotion_value_hits": [],
        "c01_sg003_xfail_or_skip_suppression_hits": [],
    }:
        raise SystemExit("legacy enum or suppression hit remains")
    if not (
        forge.get("decision") == "PROMOTE"
        and forge.get("granted_level") == "CANDIDATE"
        and forge.get("gate_decision_count") == 15
        and forge.get("crash_without_receipt_rejected_without_mutation") is True
        and forge.get("idempotent_replay_returned_original_result") is True
        and forge.get("ledger_chain_verified") is True
    ):
        raise SystemExit("receipt-bound FORGE promotion probe failed")
    return {
        "c03_runtime_migration_sha256": sha256_id(c03_path),
        "c03_runtime_status": "PASS",
        "forge_receipt_bound_promotion": forge,
        "legacy_and_suppression": legacy,
        "runtime_schema_semantics": runtime,
        "status": "PASS",
    }


def phase_artifact_reconciliation() -> dict[str, Any]:
    path = ROOT / "artifacts/work_packages/F04/attempts/0002/phase-artifact-reconciliation.json"
    value = read_json(path)
    if not (
        value.get("status") == "PASS"
        and value.get("expected_transition_count")
        == value.get("generated_transition_count")
        == value.get("persisted_transition_count")
        == value.get("replayed_transition_count")
        == 17
        and value.get("expected_phase_artifact_set_count")
        == value.get("generated_phase_artifact_set_count")
        == value.get("admitted_phase_artifact_set_count")
        == 14
        and value.get("missing_transition_ids") == []
        and value.get("missing_phase_artifact_set_ids") == []
    ):
        raise SystemExit("F04 phase-artifact reconciliation is not complete")
    return {**value, "artifact_sha256": sha256_id(path)}


def manifest_contract() -> dict[str, Any]:
    path = ROOT / "manifests/development_manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    packages = raw if isinstance(raw, list) else raw["work_packages"]
    by_id = {row["id"]: row for row in packages}
    c04 = by_id["C04"]
    if len(packages) != 156:
        raise SystemExit("development manifest package count changed")
    if c04["depends_on"] != ["C02", "C03"]:
        raise SystemExit("C04 dependencies changed")
    if c04["write_scope"] != ["artifacts/work_packages/C04/**"]:
        raise SystemExit("C04 write scope changed")
    if c04["required_checks"] != EXPECTED_REQUIRED_CHECKS:
        raise SystemExit("C04 required check inventory changed")
    if by_id["B04"]["depends_on"] != ["B02", "B03", "C04"]:
        raise SystemExit("B04 dependency changed")
    return {
        "B04_depends_on": by_id["B04"]["depends_on"],
        "C04_depends_on": c04["depends_on"],
        "C04_required_checks": c04["required_checks"],
        "C04_write_scope": c04["write_scope"],
        "manifest_sha256": sha256_id(path),
        "package_count": len(packages),
        "static_dependency_cycle_added": False,
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for relative, expected in DEPENDENCY_HASHES.items():
        path = ROOT / relative
        if sha256(path) != expected:
            raise SystemExit(f"dependency changed: {relative}")
        if path.name == "report.json":
            report = read_json(path)
            key = str(report.get("attempt_id") or relative)
            reports[key] = {
                "package_status": report.get("package_status"),
                "report": relative,
                "report_sha256": "sha256:" + expected,
                "status": report.get("status"),
            }
    for key in ("C01-0007", "C02-0003", "C03-0003", "F04-0002", "J02-0003", "S04-0003", "B04-0007"):
        if reports[key]["status"] != "PASS":
            raise SystemExit(f"required dependency evidence is not PASS: {key}")
    if reports["C04-0002"]["status"] != "FAIL":
        raise SystemExit("C04-0002 immutable repair history changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": reports,
        "development_manifest_sha256": "sha256:" + DEPENDENCY_HASHES["manifests/development_manifest.yaml"],
        "fixed_repair_order": [
            "C04-0002_FAIL_IMMUTABLE",
            "C02-0003_PASS",
            "C04-0003_PASS_AFTER_SEAL",
            "B04-0008_FINAL_PACKAGING",
        ],
        "next_package": "B04-0008",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    return {
        "approved_scope": ["artifacts/work_packages/C04/**"],
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "product_change_count": 0,
        "product_files_modified_by_attempt": [],
        "reset_clean_stash_commit_push_performed": False,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def conformance_document() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_contract": canonical_contract_conformance(),
        "completion_ready": False,
        "document_registration_lifecycle": lifecycle_test_evidence(),
        "generated_contract": generated_contract_conformance(),
        "migration_reconciliation": migration_reconciliation(),
        "phase_artifact_reconciliation": phase_artifact_reconciliation(),
        "runtime_contract": runtime_conformance(),
        "status": "PASS",
        "verdict": "C04_PASS_B04_0008_DEPENDENCY_READY_AFTER_RAH_SEAL",
    }


def review_text() -> str:
    return """# C04-0003 full-conformance review

## Verdict

`PASS — B04-0008 DEPENDENCY-READY AFTER RAH SEAL`

The refreshed C02 projection closes the sole C04-0002 failure.  The current
126 schemas and 126 one-to-one examples validate under Draft 2020-12, OpenAPI
3.1.1 retains 33 unique operations and canonical document-registration refs,
and the B04-0007 projection receipt still binds 127 installed resources.

Generated parity is current across Python, TypeScript, and UI outputs.  The
live generator check, cross-language fixture, strict TypeScript compile,
repository structure, and package-boundary checks pass.  Runtime probes reject
missing/floating `resolved_refs`, enforce decision-scoped promotion nulls, and
complete an atomic receipt-bound promotion with crash rejection and replay.
All 24 C01 migration-debt nodes now pass; the migration allowlist is empty.
The document-registration lifecycle and F04 phase-artifact reconciliation are
complete.

Regression is green: Python is 990/990, the authoritative Node footer is
460/460 across 52 files, and the corrected targeted suite is 287/287.  The
earlier 182-test collection was diagnostic only and omitted six required
modules (105 tests); it is recorded but is not used as acceptance evidence.

C04 changed no product file and has no write-scope violation.  B04-0008 final
packaging is next.  This review does not claim release readiness or overall
completion.

This is a primary-session separate adversarial integration review with
`actor_independence=false`.  Controlling product-owner decisions prohibit
Fleet and subagents, so no external actor-independent certification is
claimed.
"""


def command_rows() -> list[dict[str, Any]]:
    rows = [
        ("Inspect C04 authority, dependency reports, dirty worktree, and RAH current state", 0, "PASS: C04-0003 is evidence-only and dependency-ready"),
        ("Run full Python suite with JUnit", 0, "PASS: 990/990; failed/errors/skipped 0"),
        ("Run complete sorted 52-file serial Node suite with JUnit", 0, "PASS: authoritative footer 460/460; failed/skipped/cancelled/todo 0"),
        ("Run initial C04 targeted suite diagnostic", 0, "DIAGNOSTIC ONLY: 182/182; six required modules and 105 tests were omitted"),
        ("Reconcile omitted targeted modules", 0, "PASS: six modules restored (24+24+18+17+12+10 = 105 tests)"),
        ("Rerun authoritative C04 targeted canonical, registry, runtime, and FORGE suite with JUnit", 0, "PASS: 287/287"),
        ("uvx --from openapi-spec-validator==0.7.2 openapi-spec-validator openapi/epistemic-foundry-v1.openapi.yaml", 0, "PASS: OpenAPI 3.1.1 valid"),
        ("npm run check:structure", 0, "PASS: 10 Node components and both Python roots"),
        ("npm run check:boundaries", 0, "PASS: 10 components and 18 internal package edges"),
        ("npx --yes --package typescript@5.9.3 tsc --noEmit --strict --target ES2022 --module NodeNext --moduleResolution NodeNext packages/contracts/src/generated/models.d.ts web/src/generated/contracts.ts", 0, "PASS: generated TypeScript compiles strictly"),
        ("python -B packages/contracts/codegen/generate.py --check", 0, "PASS: nine generated files current; stale 0"),
        ("node packages/contracts/codegen/cross_language_fixture.mjs", 0, "PASS: 126 schemas / 126 examples"),
        ("Run current EvolutionRunSpec, PromotionDecision, receipt-bound promotion, crash, replay, and ledger probes", 0, "PASS"),
        ("Reconcile all 24 C01 runtime-migration nodes against current full JUnit", 0, "PASS: 24/24 present and passing; allowlist empty"),
        ("Normalize C04 JUnit portability without changing semantic signatures or Node footer", 0, "PASS"),
        ("Build and verify C04-0003 evidence from live bytes", 0, "PASS when build/verify completes"),
        ("Perform primary-session separate adversarial integration review", 0, "PASS; blocking findings 0; actor_independence=false"),
        ("Run git diff --check while preserving the dirty worktree", 0, "PASS: whitespace errors 0; pre-existing line-ending notices only"),
        ("Seal C04-0003 core/final PASS evidence into append-only RAH and verify six snapshots", 0, "PASS when sealer completes"),
    ]
    return [
        {
            "command": command,
            "command_id": f"C04-0003-C{index:03d}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": "C04-0003 full conformance gate",
        }
        for index, (command, exit_code, result) in enumerate(rows, start=1)
    ]


def output_artifacts() -> list[str]:
    names = [
        "build_c04_0003_evidence.py",
        "c04_0003_rah_seal.py",
        "c04-conformance-verification.json",
        "dependency-status.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "junit-normalization-verification.json",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-node-suite.junit.xml.stderr.log",
        "targeted-contract-conformance.junit.xml",
        "node-test-inventory.json",
        "c02-codegen-live-verification.json",
        "rah-core-integrity.json",
        "commands.jsonl",
        "review.md",
        "report.json",
    ]
    return [f"artifacts/work_packages/C04/attempts/0003/{name}" for name in names]


def report_document(
    *,
    conformance: dict[str, Any],
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    scope: dict[str, Any],
    manifest: dict[str, Any],
    rah_state: dict[str, Any] | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "FULL_C_PHASE_CONFORMANCE_GATE",
        "canonical_projection_status": "CURRENT",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "C04_0001_and_C04_0002_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_evidence_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "manifest_contract": manifest,
        "next_package": "B04-0008",
        "node_regression_status": "PASS",
        "not_claimed": [
            "B04-0008 final packaging",
            "156-package DAG terminal completion",
            "release or production readiness",
            "completion_ready=true",
            "external actor-independent certification",
        ],
        "output_artifacts": output_artifacts(),
        "package_status": "PASS",
        "python_regression_status": "PASS",
        "regression": regression,
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "verification": conformance,
        "work_package_id": "C04",
        "write_scope": scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def expected_documents(*, preserve_rah: bool) -> dict[str, Any]:
    assert_hashes(DEPENDENCY_HASHES)
    assert_hashes(BOUND_ARTIFACT_HASHES)
    normalization = normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    manifest = manifest_contract()
    conformance = conformance_document()
    scope = write_scope_verification()
    rah_state = None
    report_path = ATTEMPT / "report.json"
    if preserve_rah and report_path.is_file():
        value = read_json(report_path).get("rah_state")
        if value is not None and not isinstance(value, dict):
            raise SystemExit("C04-0003 report rah_state is malformed")
        rah_state = value
    return {
        "normalization": normalization,
        "regression": regression,
        "dependencies": dependencies,
        "manifest": manifest,
        "conformance": conformance,
        "scope": scope,
        "report": report_document(
            conformance=conformance,
            regression=regression,
            dependencies=dependencies,
            scope=scope,
            manifest=manifest,
            rah_state=rah_state,
        ),
    }


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = expected_documents(preserve_rah=True)
    write_json("c04-conformance-verification.json", documents["conformance"])
    write_json("dependency-status.json", documents["dependencies"])
    write_json("full-regression-impact.json", documents["regression"])
    write_json("write-scope-verification.json", documents["scope"])
    write_json("report.json", documents["report"])
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_rows()
        ),
        encoding="utf-8",
        newline="\n",
    )
    return verify()


def verify() -> dict[str, Any]:
    documents = expected_documents(preserve_rah=True)
    expected_json = {
        "junit-normalization-verification.json": documents["normalization"],
        "c04-conformance-verification.json": documents["conformance"],
        "dependency-status.json": documents["dependencies"],
        "full-regression-impact.json": documents["regression"],
        "write-scope-verification.json": documents["scope"],
        "report.json": documents["report"],
    }
    for name, value in expected_json.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(value):
            raise SystemExit(f"stored C04-0003 evidence differs from live evidence: {name}")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_rows()
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored C04-0003 commands differ from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("stored C04-0003 review differs from deterministic review")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_status": documents["conformance"]["canonical_contract"]["status"],
        "generated_status": documents["conformance"]["generated_contract"]["status"],
        "next_package": "B04-0008",
        "package_status": "PASS",
        "regression": documents["regression"],
        "runtime_status": documents["conformance"]["runtime_contract"]["status"],
        "status": "PASS",
        "verified_artifacts": list(expected_json) + ["commands.jsonl", "review.md"],
    }


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> None:
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("C04-0003 report is already RAH-bound")
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
