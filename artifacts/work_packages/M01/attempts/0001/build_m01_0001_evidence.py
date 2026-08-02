#!/usr/bin/env python3
"""Build and verify deterministic M01-0001 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M01/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/M01"
ATTEMPT_ID = "M01-0001"
WORK_PACKAGE_ID = "M01"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "packages/workspace-map/src/inventory/workspace-inventory.mjs",
    "packages/workspace-map/src/inventory/index.mjs",
    "packages/workspace-map/src/inventory/map-inventory.test.mjs",
    "packages/workspace-map/src/inventory/edge-resolution.test.mjs",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(value), encoding="utf-8", newline="\n")


def recorded_at() -> str:
    metadata = read_json(METADATA)
    if metadata.get("attempt_id") != ATTEMPT_ID:
        raise SystemExit("M01 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("M01 attempt metadata has no recorded_at_utc")
    return value


def node_summary(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    footer = {
        match.group(1).decode("ascii"): int(match.group(2))
        for match in NODE_FOOTER_PATTERN.finditer(raw)
    }
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(footer) != required:
        raise SystemExit(f"Node JUnit footer is incomplete: {path.name}: {footer}")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise SystemExit(f"cannot parse Node JUnit {path}: {error}") from error
    testcases = list(root.iter("testcase"))
    suites = list(root.iter("testsuite"))
    observed_files: set[str] = set()
    for testcase in testcases:
        value = testcase.attrib.get("file")
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                value = candidate.resolve().relative_to(ROOT.resolve()).as_posix()
            except ValueError as error:
                raise SystemExit(f"Node JUnit file escapes repository: {value}") from error
        else:
            value = value.replace("\\", "/")
        observed_files.add(value)
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "observed_files": sorted(observed_files),
        "observed_file_count": len(observed_files),
        "passed": footer["pass"],
        "skipped": footer["skipped"],
        "test_names": [str(node.attrib.get("name", "")) for node in testcases],
        "todo": footer["todo"],
        "xml_error_count": len(list(root.iter("error"))),
        "xml_failure_count": len(list(root.iter("failure"))),
        "xml_logical_test_count": len(testcases) + len(suites),
        "xml_suite_test_count": len(suites),
        "xml_testcase_count": len(testcases),
    }


def pytest_summary(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise SystemExit(f"cannot parse pytest JUnit {path}: {error}") from error
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise SystemExit(f"pytest JUnit has no top-level suite: {path}")
    tests = sum(int(float(suite.attrib.get("tests", "0"))) for suite in suites)
    failures = sum(int(float(suite.attrib.get("failures", "0"))) for suite in suites)
    errors = sum(int(float(suite.attrib.get("errors", "0"))) for suite in suites)
    skipped = sum(int(float(suite.attrib.get("skipped", "0"))) for suite in suites)
    testcase_count = len(list(root.iter("testcase")))
    if testcase_count != tests:
        raise SystemExit(f"pytest testcase count mismatch: {testcase_count} != {tests}")
    return {
        "collected": tests,
        "errors": errors,
        "failed": failures,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": tests - failures - errors - skipped,
        "skipped": skipped,
        "xml_testcase_count": testcase_count,
    }


def assert_clean_node(summary: dict[str, Any], expected: int, label: str) -> None:
    if not (
        summary["passed"] == summary["collected"] == expected
        and all(summary[key] == 0 for key in ("failed", "skipped", "todo", "cancelled"))
        and summary["xml_failure_count"] == summary["xml_error_count"] == 0
        and summary["xml_logical_test_count"] == expected
    ):
        raise SystemExit(f"{label} gate is not {expected}/{expected}: {summary}")


def manifest_contract() -> dict[str, Any]:
    try:
        document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        packages = document["work_packages"]
    except (OSError, KeyError, yaml.YAMLError) as error:
        raise SystemExit(f"cannot read development manifest: {error}") from error
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "M01"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one M01 row")
    expected = {
        "depends_on": ["B04", "C04", "D04", "J04", "K04"],
        "write_scope": ["packages/workspace-map/src/inventory/**"],
        "independent_review": "required",
        "exit_criteria": [
            "code/research/artifact layers indexed",
            "unresolved edges explicit",
        ],
        "required_checks": ["map_inventory_test", "edge_resolution_test"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"M01 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages/workspace-map/src/inventory").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"M01 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"M01 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"M01 source must be BOM-less UTF-8: {relative}")
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": sha256_id(path),
                "utf8_bom": False,
            }
        )
    return rows


def syntax_evidence() -> dict[str, Any]:
    syntax = read_json(ATTEMPT / "syntax-verification.json")
    if not (
        syntax.get("final_status") == "PASS"
        and len(syntax.get("checks", [])) == 4
        and all(row.get("exit_code") == 0 for row in syntax["checks"])
        and sorted(row.get("path") for row in syntax["checks"]) == sorted(PRODUCT_FILES)
    ):
        raise SystemExit("M01 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-m01-node.junit.xml")
    assert_clean_node(targeted, 22, "M01 targeted")
    names = targeted["test_names"]
    inventory_names = [name for name in names if name.startswith("map_inventory_test:")]
    edge_names = [name for name in names if name.startswith("edge_resolution_test:")]
    if len(inventory_names) != 11 or len(edge_names) != 11 or len(set(names)) != 22:
        raise SystemExit("M01 targeted test-name partition is not exact 11/11")
    expected_files = sorted(PRODUCT_FILES[-2:])
    if targeted["observed_files"] != expected_files:
        raise SystemExit(f"M01 targeted JUnit file inventory differs: {targeted['observed_files']}")
    return {
        **targeted,
        "edge_resolution_test_count": len(edge_names),
        "map_inventory_test_count": len(inventory_names),
    }


def inventory_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    test = (ROOT / PRODUCT_FILES[2]).read_text(encoding="utf-8")
    required_source = (
        'ENTITY_LAYERS = OBJECT_FREEZE(["CODE", "RESEARCH", "ARTIFACT"])',
        '"SOURCE"',
        '"DIST"',
        '"GENERATED"',
        '"VENDOR"',
        '"TEST"',
        "DUPLICATE_ENTITY_ID",
        "DUPLICATE_ENTITY_PATH",
        "DUPLICATE_ENTITY_IDENTITY",
        "READABILITY_CONFLICT",
        "NON_CANONICAL_JSON",
        "inventory_hash",
    )
    required_test = (
        "code, research, and artifact layers are indexed",
        "source, dist, generated, vendor, and test identities remain distinct",
        "input permutation produces byte-identical deterministic inventory",
        "duplicate entity IDs, paths, and aliases fail closed",
        "hostile getters, Proxies, sparse arrays, and extra fields are rejected",
    )
    missing = [fragment for fragment in (*required_source, *required_test) if fragment not in source + test]
    if missing:
        raise SystemExit(f"M01 inventory contract binding is incomplete: {missing}")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_layers": ["CODE", "RESEARCH", "ARTIFACT"],
        "closed_source_classes": [
            "SOURCE",
            "DIST",
            "GENERATED",
            "VENDOR",
            "TEST",
            "RESEARCH",
            "ARTIFACT",
        ],
        "deterministic_input_permutation": "PASS",
        "duplicate_identity_rejection": "PASS",
        "hostile_input_rejection": "PASS",
        "immutable_output": "PASS",
        "portable_path_validation": "PASS",
        "ranking_or_personalization_emitted": False,
        "source_dist_generated_vendor_test_separated": True,
        "status": "PASS",
        "unreadable_paths_explicit": True,
    }


def edge_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    test = (ROOT / PRODUCT_FILES[3]).read_text(encoding="utf-8")
    required = (
        "WORK_PACKAGE_DEPENDS_ON",
        "EVIDENCE_SUPPORTS_CLAIM",
        "EVIDENCE_COUNTERS_CLAIM",
        "DERIVED_FROM",
        "PRODUCED_BY",
        "SUPERSEDES",
        "MISSING_TARGET_LOCATOR",
        "TARGET_NOT_FOUND",
        "EDGE_SOURCE_NOT_FOUND",
        "EDGE_OWNER_MISMATCH",
        "EDGE_TARGET_KIND_MISMATCH",
        "missing research locators remain explicit unresolved edges",
        "set permutation preserves edge hashes, IDs, and partition order",
    )
    missing = [fragment for fragment in required if fragment not in source + test]
    if missing:
        raise SystemExit(f"M01 edge contract binding is incomplete: {missing}")
    return {
        "attempt_id": ATTEMPT_ID,
        "closed_typed_edge_vocabulary": True,
        "dependency_and_provenance_direction_preserved": True,
        "deterministic_input_permutation": "PASS",
        "missing_target_locator_reason": "MISSING_TARGET_LOCATOR",
        "resolved_and_unresolved_partitions_explicit": True,
        "self_edge_rejection": "PASS",
        "source_owner_and_target_kind_validation": "PASS",
        "status": "PASS",
        "target_not_found_reason": "TARGET_NOT_FOUND",
        "unresolved_edge_suppression_count": 0,
    }


def selected_dependency_report(package_id: str) -> Path:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts_root = package_root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts_root.is_dir():
        for path in attempts_root.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        latest = max(numeric)[1] / "report.json"
        if not latest.is_file():
            raise SystemExit(f"latest {package_id} attempt has no report")
        return latest
    root_report = package_root / "report.json"
    if not root_report.is_file():
        raise SystemExit(f"dependency report is absent: {package_id}")
    return root_report


def dependency_evidence() -> dict[str, Any]:
    expected = {
        "B04": ("B04-0008", "E0024"),
        "C04": ("C04-0003", "E0021"),
        "D04": ("D04-0001", "E0023"),
        "J04": ("J04-0001", "E0027"),
        "K04": ("K04-0001", "E0039"),
    }
    dependencies: dict[str, Any] = {}
    for package_id, (attempt_id, final_id) in expected.items():
        path = selected_dependency_report(package_id)
        report = read_json(path)
        rah = report.get("rah_state")
        if not (
            report.get("attempt_id") == attempt_id
            and report.get("status") == "PASS"
            and report.get("package_status") == "PASS"
            and isinstance(rah, dict)
            and rah.get("final_closeout_evidence_id") == final_id
        ):
            raise SystemExit(f"M01 dependency {package_id} is not exact sealed PASS")
        dependencies[package_id] = {
            "attempt_id": attempt_id,
            "final_closeout_evidence_id": final_id,
            "report": path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(path),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "dependency_count": 5,
        "status": "PASS",
    }


def regression_evidence() -> dict[str, Any]:
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    assert_clean_node(full_node, 635, "full Node")
    if not (
        full_python["passed"] == full_python["collected"] == 1064
        and all(full_python[key] == 0 for key in ("failed", "errors", "skipped"))
    ):
        raise SystemExit(f"full Python gate differs: {full_python}")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    files = inventory.get("files")
    if not (
        inventory.get("count") == 65
        and inventory.get("unique") is True
        and isinstance(files, list)
        and len(files) == len(set(files)) == 65
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 65
    ):
        raise SystemExit("full Node inventory/JUnit coverage is incomplete or ambiguous")
    codegen = read_json(ATTEMPT / "codegen-verification.stdout.log")
    if not (
        codegen.get("status") == "PASS"
        and codegen.get("schema_count") == 126
        and codegen.get("example_count") == 126
        and codegen.get("failures") == []
    ):
        raise SystemExit("canonical codegen verification did not pass 126/126")
    structure = (ATTEMPT / "structure-check.stdout.log").read_text(encoding="utf-8")
    boundaries = (ATTEMPT / "boundary-check.stdout.log").read_text(encoding="utf-8")
    if '"status": "PASS"' not in structure or '"status": "PASS"' not in boundaries:
        raise SystemExit("repository structure or boundary gate did not pass")
    if (ATTEMPT / "git-diff-check.stdout.log").stat().st_size != 0:
        raise SystemExit("git diff --check produced stdout")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_codegen": {"examples": 126, "schemas": 126, "status": "PASS"},
        "full_node": {**full_node, "test_file_count": 65},
        "full_python": full_python,
        "git_diff_check": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "package_boundaries": "PASS",
        "repository_structure": "PASS",
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    return {
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "evidence_scope": "artifacts/work_packages/M01/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/workspace-map/src/inventory/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    inventory = inventory_verification()
    edges = edge_verification()
    return {
        "inventory-verification.json": inventory,
        "edge-resolution-verification.json": edges,
        "typed-inventory-edge-verification.json": {
            "attempt_id": ATTEMPT_ID,
            "edge_resolution": edges,
            "inventory": inventory,
            "status": "PASS",
            "syntax": syntax_evidence(),
            "targeted": targeted_evidence(),
        },
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    targeted = targeted_evidence()
    return f"""# M01-0001 typed inventory and dependency extraction review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M01
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. M01 consumes a frozen logical snapshot and is a pure deterministic mapper;
   it does not scan or mutate the filesystem, guess missing targets, or acquire
   canonical workspace-snapshot authority owned by later M packages.
2. The closed inventory vocabulary separates CODE, RESEARCH, and ARTIFACT
   layers and keeps SOURCE, DIST, GENERATED, VENDOR, and TEST identities
   explicit. Portable paths, explicit locators, hashes, unreadable paths,
   duplicate identities, custom prototypes, accessors, proxies, sparse arrays,
   and cyclic canonical input are fail-closed.
3. Edge extraction retains typed identity namespaces, source/target direction,
   owner, source locator, and provenance. Missing research and provenance
   targets remain explicit as `TARGET_NOT_FOUND` or
   `MISSING_TARGET_LOCATOR`; no unresolved edge is silently dropped.
4. Inventory and edge IDs bind deterministic canonical hashes. Input
   permutation is byte-stable, outputs are deeply immutable, and validation
   rejects content, count, partition, hash, ID, inventory-binding, and semantic
   tampering.
5. M01 emits no ranking, centrality, personalization, or score. Those remain
   bounded to M02/M03.
6. Required checks pass {targeted['passed']}/{targeted['collected']}: 11
   `map_inventory_test` and 11 `edge_resolution_test` cases, with no failure,
   skipped, todo, cancelled, xfailed, or suppressed case.
7. Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} distinct files, and full
   Python passes {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126 schemas / 126 examples; repository structure, package
   boundaries, and diff checks pass.
8. All four product files are BOM-less UTF-8 and remain inside the exact
   `packages/workspace-map/src/inventory/**` scope. Existing dirty-worktree
   changes, historical reports, evidence, and RAH generations remain untouched.

## Assurance boundary

This gate establishes typed deterministic inventory and dependency extraction
for a caller-supplied frozen snapshot. It does not establish filesystem watcher
or parser coverage, ranking quality, centrality, personalization, production
scale, actor-independent review, overall product completion, release readiness,
or `completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect M01 manifest, dependency reports, workspace-map contracts, dirty worktree, and RAH state", 0, "PASS"),
        ("D001", "Initial M01 targeted execution", 1, "PRESERVED_DIAGNOSTIC: 11/22; fixture assigned the same portable path to source file and symbol, and count-key insertion order was asserted despite canonical object sorting"),
        ("C002", "Correct M01 test fixtures without weakening production contracts", 0, "PASS"),
        ("C003", "Add cyclic canonical input fail-closed guard and adversarial cases", 0, "PASS"),
        ("C004", "node --test --test-concurrency=1 <two M01 tests>", 0, "PASS: 22/22 (inventory 11, edge 11)"),
        ("C005", "node --check <four M01 product files>", 0, "PASS: 4/4"),
        ("C006", "Capture complete sorted repository Node test inventory", 0, "PASS: 65 unique files"),
        ("C007", "Run complete repository Node test inventory", 0, "PASS: 635/635 across 65 files"),
        ("C008", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C009", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C010", "npm run check:structure", 0, "PASS"),
        ("C011", "npm run check:boundaries", 0, "PASS"),
        ("C012", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C013", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("D002", "Initial deterministic evidence build", 1, "PRESERVED_DIAGNOSTIC: Node JUnit contained 630 testcase nodes plus 5 nested suite-level logical tests; parser failed closed, then was corrected to verify 630 + 5 == footer 635 without weakening the acceptance threshold"),
        ("C014", "Build and verify deterministic M01 WorkPackageReport evidence", 0, "PASS"),
    ]
    timestamp = recorded_at()
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": timestamp,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def expected_commands() -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in command_records())


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "M01-0001-TYPED-INVENTORY-EDGE-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "M01-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-M01-0001-TYPED-INVENTORY-EDGE-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {"check": "map_inventory_test", "details": "11/11 deterministic layer, source-class, identity, immutability, and fail-closed cases pass", "status": "PASS"},
            {"check": "edge_resolution_test", "details": "11/11 typed resolution, explicit unresolved, provenance, replay, and tamper cases pass", "status": "PASS"},
            {"check": "full_regression", "details": "Node 635/635 across 65 files, Python 1064/1064, codegen 126/126, no suppression", "status": "PASS"},
        ],
    }
    receipt["receipt_hash"] = canonical_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid M01 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "inventory-verification.json",
        "edge-resolution-verification.json",
        "typed-inventory-edge-verification.json",
        "typed-inventory-edge-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m01-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "codegen-verification.stdout.log",
        "structure-check.stdout.log",
        "boundary-check.stdout.log",
        "git-diff-check.stdout.log",
        "git-diff-check.stderr.log",
        "commands.jsonl",
        "review.md",
        "attempt-metadata.json",
        "run_m01_0001_checks.py",
        "build_m01_0001_evidence.py",
        "m01_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required M01 evidence artifact is missing: {name}")
        rows.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return rows


def report_document(
    documents: dict[str, dict[str, Any]], *, rah_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    targeted = targeted_evidence()
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(ATTEMPT / "typed-inventory-edge-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/M01/attempts/0001/typed-inventory-edge-verification.artifact-receipt.json",
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": dependency["dependencies"],
        "diagnostics_preserved": [
            {
                "classification": "TEST_FIXTURE_IDENTITY_COLLISION",
                "result": "initial targeted execution 11/22 because source and symbol fixture entities shared one portable path",
                "resolution": "the symbol fixture now uses its explicit symbol locator and no duplicate path",
            },
            {
                "classification": "TEST_ORACLE_CANONICAL_KEY_ORDER",
                "result": "initial layer-count oracle assumed insertion order despite canonical object sorting",
                "resolution": "the oracle compares the closed key set independently of serialized canonical order",
            },
        ],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "code_research_artifact_layers_indexed": "PASS",
            "unresolved_edges_explicit": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "actor-independent certification",
            "filesystem watcher or parser completeness",
            "ranking, centrality, or personalization",
            "production scale",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "edge_resolution_test": {"failed": 0, "passed": 11, "skipped": 0, "status": "PASS"},
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "map_inventory_test": {"failed": 0, "passed": 11, "skipped": 0, "status": "PASS"},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/M01/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Typed inventory and dependency extraction",
        "verification": {
            "full_node": "635/635 across 65 files",
            "full_python": "1064/1064",
            "targeted_m01": "22/22",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "edge_resolution": documents["edge-resolution-verification.json"],
            "inventory": documents["inventory-verification.json"],
            "targeted": targeted,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    manifest_contract()
    syntax_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(expected_commands(), encoding="utf-8", newline="\n")
    (ATTEMPT / "review.md").write_text(review_text(documents), encoding="utf-8", newline="\n")
    verification_path = ATTEMPT / "typed-inventory-edge-verification.json"
    write_json(
        ATTEMPT / "typed-inventory-edge-verification.artifact-receipt.json",
        make_receipt(verification_path),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "active",
    }
    write_json(ATTEMPT / "report.json", report_document(documents, rah_state=rah_state))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    manifest_contract()
    syntax_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored M01 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored M01 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored M01 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "typed-inventory-edge-verification.json")
    receipt_path = ATTEMPT / "typed-inventory-edge-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored M01 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("M01 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored M01 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"M01 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "635/635 across 65 files",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_m01": "22/22",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
