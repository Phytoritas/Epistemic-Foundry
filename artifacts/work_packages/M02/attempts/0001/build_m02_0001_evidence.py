#!/usr/bin/env python3
"""Build and verify deterministic M02-0001 evidence."""

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
ATTEMPT = ROOT / "artifacts/work_packages/M02/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/M02"
ATTEMPT_ID = "M02-0001"
WORK_PACKAGE_ID = "M02"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "packages/workspace-map/src/ranking/baseline/baseline-centrality.mjs",
    "packages/workspace-map/src/ranking/baseline/index.mjs",
    "packages/workspace-map/src/ranking/baseline/centrality-reference.test.mjs",
    "packages/workspace-map/src/ranking/baseline/uniform-rank-regression.test.mjs",
)
M01_TESTS = (
    "packages/workspace-map/src/inventory/edge-resolution.test.mjs",
    "packages/workspace-map/src/inventory/map-inventory.test.mjs",
)
M02_TESTS = PRODUCT_FILES[-2:]
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
        raise SystemExit("M02 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("M02 attempt metadata has no recorded_at_utc")
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
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "M02"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one M02 row")
    expected = {
        "depends_on": ["M01"],
        "write_scope": ["packages/workspace-map/src/ranking/baseline/**"],
        "independent_review": "required",
        "exit_criteria": [
            "nontrivial graph not uniform-ranked",
            "algorithm inputs recorded",
        ],
        "required_checks": ["centrality_reference_test", "uniform_rank_regression"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"M02 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages/workspace-map/src/ranking/baseline").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"M02 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"M02 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"M02 source must be BOM-less UTF-8: {relative}")
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
    checks = syntax.get("checks", [])
    if not (
        syntax.get("final_status") == "PASS"
        and len(checks) == 4
        and all(row.get("exit_code") == 0 for row in checks)
        and sorted(row.get("path") for row in checks) == sorted(PRODUCT_FILES)
    ):
        raise SystemExit("M02 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-m02-node.junit.xml")
    assert_clean_node(targeted, 25, "M02 targeted")
    names = targeted["test_names"]
    reference = [name for name in names if name.startswith("centrality_reference_test:")]
    uniform = [name for name in names if name.startswith("uniform_rank_regression:")]
    if len(reference) != 13 or len(uniform) != 12 or len(set(names)) != 25:
        raise SystemExit("M02 targeted test-name partition is not exact 13/12")
    if targeted["observed_files"] != sorted(M02_TESTS):
        raise SystemExit(f"M02 targeted JUnit file inventory differs: {targeted['observed_files']}")
    return {
        **targeted,
        "centrality_reference_test_count": len(reference),
        "uniform_rank_regression_count": len(uniform),
    }


def combined_evidence() -> dict[str, Any]:
    combined = node_summary(ATTEMPT / "combined-m01-m02-node.junit.xml")
    assert_clean_node(combined, 47, "M01+M02 combined")
    if combined["observed_files"] != sorted((*M01_TESTS, *M02_TESTS)):
        raise SystemExit("combined M01+M02 JUnit file inventory differs")
    return combined


def centrality_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    test = (ROOT / PRODUCT_FILES[2]).read_text(encoding="utf-8")
    required = (
        'BASELINE_CENTRALITY_ALGORITHM = "WEIGHTED_PAGERANK"',
        'BASELINE_CENTRALITY_VERSION = "4.0.0-m02.1"',
        "alpha: 0.85",
        'dangling_policy: "UNIFORM_REDISTRIBUTION"',
        'edge_weight_policy: "UNIT_PER_RESOLVED_TYPED_EDGE"',
        'direction: "SOURCE_TO_TARGET"',
        "excluded_unresolved_edge_ids",
        "weak_component_id",
        "baseline_centrality",
        "CENTRALITY_NON_CONVERGENCE",
        "CENTRALITY_NORMALIZATION_FAILURE",
        "two-node analytical reference is reproduced",
        "unresolved edges are recorded but never influence scores",
        "validation rejects nested algorithm accessors without invoking them",
    )
    missing = [fragment for fragment in required if fragment not in source + test]
    if missing:
        raise SystemExit(f"M02 centrality contract binding is incomplete: {missing}")
    return {
        "algorithm": "WEIGHTED_PAGERANK",
        "algorithm_inputs_recorded": True,
        "alpha": 0.85,
        "attempt_id": ATTEMPT_ID,
        "canonical_result_order": "UTF8_NODE_ID",
        "convergence_norm": "L1",
        "dangling_policy": "UNIFORM_REDISTRIBUTION",
        "deterministic_input_permutation": "PASS",
        "edge_direction": "SOURCE_TO_TARGET",
        "edge_weight_policy": "UNIT_PER_RESOLVED_TYPED_EDGE",
        "hostile_input_rejection": "PASS",
        "isolates_retained": True,
        "query_risk_or_blast_radius_emitted": False,
        "score_normalization": "PASS",
        "status": "PASS",
        "unresolved_edges_excluded_from_scores": True,
        "unresolved_edges_recorded": True,
        "version": "4.0.0-m02.1",
    }


def uniformity_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    test = (ROOT / PRODUCT_FILES[3]).read_text(encoding="utf-8")
    required = (
        "UNIFORM_RANK_REGRESSION",
        "structurally_asymmetric",
        "guard_threshold",
        "asymmetric star is never uniformly ranked",
        "asymmetric path receives distinct scores",
        "directed regular cycle may have a legitimate tie",
        "all-isolate graph retains normalized uniform scores",
        "parallel typed edges are recorded as unit weights",
        "algorithm does not emit query or risk fields",
    )
    missing = [fragment for fragment in required if fragment not in source + test]
    if missing:
        raise SystemExit(f"M02 uniform-rank contract binding is incomplete: {missing}")
    return {
        "asymmetric_path_nonuniform": "PASS",
        "asymmetric_star_nonuniform": "PASS",
        "attempt_id": ATTEMPT_ID,
        "empty_graph_explicit": "PASS",
        "isolate_only_uniformity_legitimate": True,
        "nonconvergence_fail_closed": "PASS",
        "regular_cycle_uniformity_legitimate": True,
        "status": "PASS",
        "uniform_fake_scorer_regression_count": 0,
        "uniformity_guard": "STRUCTURAL_DEGREE_ASYMMETRY_PLUS_SCORE_SPAN",
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
            raise SystemExit(f"highest {package_id} attempt has no report")
        return latest
    fallback = package_root / "report.json"
    if not fallback.is_file():
        raise SystemExit(f"dependency report missing: {package_id}")
    return fallback


def dependency_evidence() -> dict[str, Any]:
    path = selected_dependency_report("M01")
    report = read_json(path)
    rah = report.get("rah_state")
    if not (
        report.get("attempt_id") == "M01-0001"
        and report.get("status") == "PASS"
        and report.get("package_status") == "PASS"
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0053"
        and rah.get("final_closeout_evidence_id") == "E0054"
        and rah.get("completion_ready") is False
    ):
        raise SystemExit("M02 dependency M01 is not the exact sealed PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "M01": {
                "attempt_id": "M01-0001",
                "core_evidence_id": "E0053",
                "final_closeout_evidence_id": "E0054",
                "report": path.relative_to(ROOT).as_posix(),
                "report_sha256": sha256_id(path),
                "status": "PASS",
            }
        },
        "dependency_count": 1,
        "status": "PASS",
    }


def node_files() -> list[str]:
    return sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "packages", ROOT / "tests", ROOT / "web")
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )


def regression_evidence() -> dict[str, Any]:
    full_node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    full_python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    files = node_files()
    assert_clean_node(full_node, 660, "full Node")
    if not (
        len(files) == len(set(files)) == 67
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 67
    ):
        raise SystemExit("full Node inventory/JUnit coverage is incomplete or ambiguous")
    if not (
        full_python["passed"] == full_python["collected"] == 1064
        and full_python["failed"] == full_python["errors"] == full_python["skipped"] == 0
    ):
        raise SystemExit("full Python gate is not 1064/1064")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory != {
        "attempt_id": ATTEMPT_ID,
        "count": 67,
        "files": files,
        "unique": True,
    }:
        raise SystemExit("stored Node inventory differs from live inventory")
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
        "combined_m01_m02": combined_evidence(),
        "full_node": {**full_node, "test_file_count": 67},
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
        "evidence_scope": "artifacts/work_packages/M02/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/workspace-map/src/ranking/baseline/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    centrality = centrality_verification()
    uniformity = uniformity_verification()
    return {
        "centrality-verification.json": centrality,
        "uniform-rank-verification.json": uniformity,
        "baseline-centrality-verification.json": {
            "attempt_id": ATTEMPT_ID,
            "centrality": centrality,
            "status": "PASS",
            "syntax": syntax_evidence(),
            "targeted": targeted_evidence(),
            "uniformity": uniformity,
        },
        "full-regression-impact.json": regression_evidence(),
        "dependency-status.json": dependency_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    targeted = targeted_evidence()
    return f"""# M02-0001 real baseline centrality and graph algorithms review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M02
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. M02 uses deterministic weighted directed PageRank rather than a placeholder
   or uniform scorer. The implementation records algorithm name/version,
   `alpha=0.85`, tolerance, iteration bound, convergence norm, dangling policy,
   direction, edge weighting, node IDs, resolved edges, and excluded unresolved
   edge IDs.
2. The two-node analytical reference, directed chain, asymmetric star, and
   asymmetric path establish non-uniform centrality where topology requires it.
   A structurally asymmetric degree signature with a uniform score fails closed
   as `UNIFORM_RANK_REGRESSION`.
3. Mathematically legitimate ties remain supported for regular directed cycles,
   isolate-only graphs, a singleton, and the explicit empty graph. The manifest
   criterion is therefore enforced against fake uniform ranking without
   corrupting valid PageRank symmetry.
4. Only M01-validated resolved typed edges influence scores. Unresolved edges
   remain explicitly recorded and hash-bound but cannot affect results. Parallel
   resolved typed edges are explicit unit-weight inputs rather than silently
   deduplicated.
5. Isolates, in/out degree, weak-component identity and size, score
   normalization, convergence evidence, stable UTF-8 result order, separate
   score ranking order, immutable output, deterministic permutation behavior,
   and content-bound hash/ID are all verified.
6. Invalid parameters, bounded non-convergence, score/hash tampering, unknown
   fields, accessors, proxies, and noncanonical values fail closed. Nested
   algorithm accessors are rejected without invocation.
7. M02 emits no query relevance, risk score, blast radius, or WorkspaceMapSnapshot;
   those remain bounded to M03 and later integration packages.
8. Required checks pass {targeted['passed']}/{targeted['collected']}: 13
   `centrality_reference_test` and 12 `uniform_rank_regression` cases. M01+M02
   combined passes {regression['combined_m01_m02']['passed']}/{regression['combined_m01_m02']['collected']}.
   Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
9. All four product files are BOM-less UTF-8 and remain inside exact
   `packages/workspace-map/src/ranking/baseline/**` scope. Existing dirty
   worktree changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes deterministic baseline centrality for an M01-validated
logical graph. It does not establish query personalization, risk, blast radius,
WorkspaceMapSnapshot integration, production-scale performance, actor-independent
review, overall product completion, release readiness, or
`completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect M02 manifest, M01 dependency, baseline implementation, dirty worktree, and RAH state", 0, "PASS"),
        ("D001", "Initial M02 targeted execution", 1, "PRESERVED_DIAGNOSTIC: 22/23; permutation fixture encoded array position in source_locator, changing semantic input rather than only order"),
        ("C002", "Correct permutation fixture to bind source_locator to semantic source/target identity", 0, "PASS without production-contract weakening"),
        ("C003", "Add nested algorithm plain-data validation", 0, "PASS"),
        ("C004", "Initial corrected M02 targeted execution", 0, "PASS: 23/23"),
        ("C005", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C006", "Add unresolved-edge score-exclusion and nested-accessor adversarial regressions", 0, "PASS"),
        ("C007", "Run exact M02 targeted JUnit", 0, "PASS: 25/25 (centrality reference 13, uniform-rank regression 12)"),
        ("C008", "Run combined M01+M02 JUnit", 0, "PASS: 47/47"),
        ("C009", "node --check <four M02 product files>", 0, "PASS: 4/4"),
        ("C010", "Capture complete sorted repository Node test inventory", 0, "PASS: 67 unique files"),
        ("C011", "Run complete repository Node test inventory", 0, "PASS: 660/660 across 67 files"),
        ("C012", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C013", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C014", "npm run check:structure", 0, "PASS"),
        ("C015", "npm run check:boundaries", 0, "PASS"),
        ("C016", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C017", "Build and verify deterministic M02 WorkPackageReport evidence", 0, "PASS"),
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
        "artifact_id": "M02-0001-BASELINE-CENTRALITY-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "M02-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-M02-0001-BASELINE-CENTRALITY-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {"check": "centrality_reference_test", "details": "13/13 analytical, input-recording, unresolved-edge, identity, immutability, and fail-closed cases pass", "status": "PASS"},
            {"check": "uniform_rank_regression", "details": "12/12 asymmetric non-uniformity, legitimate symmetry, boundary, and separation cases pass", "status": "PASS"},
            {"check": "full_regression", "details": "Node 660/660 across 67 files, Python 1064/1064, codegen 126/126, no suppression", "status": "PASS"},
        ],
    }
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt)
    )
    if errors:
        raise SystemExit(f"invalid M02 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "centrality-verification.json",
        "uniform-rank-verification.json",
        "baseline-centrality-verification.json",
        "baseline-centrality-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m02-node.junit.xml",
        "combined-m01-m02-node.junit.xml",
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
        "run_m02_0001_checks.py",
        "build_m02_0001_evidence.py",
        "m02_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required M02 evidence artifact is missing: {name}")
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
    receipt = read_json(ATTEMPT / "baseline-centrality-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/M02/attempts/0001/baseline-centrality-verification.artifact-receipt.json",
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
                "classification": "TEST_FIXTURE_SEMANTIC_IDENTITY_DRIFT",
                "result": "initial targeted execution was 22/23 because the permutation fixture used array index in source_locator and therefore changed the canonical M01 edge identity",
                "resolution": "bind fixture source_locator to semantic source/target identity; production centrality and upstream identity contracts remain unchanged",
            }
        ],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "algorithm_inputs_recorded": "PASS",
            "nontrivial_graph_not_uniform_ranked": "PASS",
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
            "query personalization, risk, or blast radius",
            "WorkspaceMapSnapshot integration",
            "production-scale performance",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "rah_state": rah_state,
        "regression": regression,
        "required_checks": {
            "centrality_reference_test": {"failed": 0, "passed": 13, "skipped": 0, "status": "PASS"},
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "uniform_rank_regression": {"failed": 0, "passed": 12, "skipped": 0, "status": "PASS"},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/M02/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Real baseline centrality and graph algorithms",
        "verification": {
            "combined_m01_m02": "47/47",
            "full_node": "660/660 across 67 files",
            "full_python": "1064/1064",
            "targeted_m02": "25/25",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "centrality": documents["centrality-verification.json"],
            "targeted": targeted,
            "uniformity": documents["uniform-rank-verification.json"],
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is None:
        report.pop("rah_state")
    return report


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    manifest_contract()
    syntax_evidence()
    targeted_evidence()
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(
        expected_commands(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    authority_path = ATTEMPT / "baseline-centrality-verification.json"
    write_json(
        ATTEMPT / "baseline-centrality-verification.artifact-receipt.json",
        make_receipt(authority_path),
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
            raise SystemExit(f"stored M02 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored M02 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored M02 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "baseline-centrality-verification.json")
    receipt_path = ATTEMPT / "baseline-centrality-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored M02 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("M02 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored M02 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"M02 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "combined_m01_m02": "47/47",
        "completion_ready": False,
        "full_node": "660/660 across 67 files",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_m02": "25/25",
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
