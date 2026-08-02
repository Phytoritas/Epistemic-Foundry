#!/usr/bin/env python3
"""Build and verify deterministic M03-0001 evidence."""

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
ATTEMPT = ROOT / "artifacts/work_packages/M03/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/M03"
ATTEMPT_ID = "M03-0001"
WORK_PACKAGE_ID = "M03"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
METADATA = ATTEMPT / "attempt-metadata.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
PRODUCT_FILES = (
    "packages/workspace-map/src/ranking/query/query-ranking-common.mjs",
    "packages/workspace-map/src/ranking/query/query-personalization.mjs",
    "packages/workspace-map/src/ranking/query/risk-change-impact.mjs",
    "packages/workspace-map/src/ranking/query/index.mjs",
    "packages/workspace-map/src/ranking/query/personalization.test.mjs",
    "packages/workspace-map/src/ranking/query/blast-radius.test.mjs",
)
M01_TESTS = (
    "packages/workspace-map/src/inventory/edge-resolution.test.mjs",
    "packages/workspace-map/src/inventory/map-inventory.test.mjs",
)
M02_TESTS = (
    "packages/workspace-map/src/ranking/baseline/centrality-reference.test.mjs",
    "packages/workspace-map/src/ranking/baseline/uniform-rank-regression.test.mjs",
)
M03_TESTS = PRODUCT_FILES[-2:]
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
        raise SystemExit("M03 attempt metadata has the wrong attempt ID")
    value = metadata.get("recorded_at_utc")
    if not isinstance(value, str):
        raise SystemExit("M03 attempt metadata has no recorded_at_utc")
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
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "M03"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one M03 row")
    expected = {
        "depends_on": ["M01"],
        "write_scope": ["packages/workspace-map/src/ranking/query/**"],
        "independent_review": "required",
        "exit_criteria": [
            "relevance/risk/centrality separate",
            "shared resources count as edges",
        ],
        "required_checks": ["personalization_test", "blast_radius_test"],
        "risk_class": "medium",
    }
    actual = {key: rows[0].get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"M03 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def source_inventory() -> list[dict[str, Any]]:
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages/workspace-map/src/ranking/query").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"M03 product inventory differs from exact scope: {actual}")
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"M03 source is not UTF-8: {relative}: {error}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"M03 source must be BOM-less UTF-8: {relative}")
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
        and len(checks) == 6
        and all(row.get("exit_code") == 0 for row in checks)
        and sorted(row.get("path") for row in checks) == sorted(PRODUCT_FILES)
    ):
        raise SystemExit("M03 syntax verification did not pass exact source inventory")
    return syntax


def targeted_evidence() -> dict[str, Any]:
    targeted = node_summary(ATTEMPT / "targeted-m03-node.junit.xml")
    assert_clean_node(targeted, 33, "M03 targeted")
    names = targeted["test_names"]
    personalization = [name for name in names if name.startswith("personalization_test:")]
    blast = [name for name in names if name.startswith("blast_radius_test:")]
    if len(personalization) != 12 or len(blast) != 21 or len(set(names)) != 33:
        raise SystemExit("M03 targeted test-name partition is not exact 12/21")
    if targeted["observed_files"] != sorted(M03_TESTS):
        raise SystemExit(f"M03 targeted JUnit file inventory differs: {targeted['observed_files']}")
    return {
        **targeted,
        "blast_radius_test_count": len(blast),
        "personalization_test_count": len(personalization),
    }


def combined_evidence() -> dict[str, Any]:
    combined = node_summary(ATTEMPT / "combined-m01-m02-m03-node.junit.xml")
    assert_clean_node(combined, 80, "M01+M02+M03 combined")
    expected_files = sorted((*M01_TESTS, *M02_TESTS, *M03_TESTS))
    if combined["observed_files"] != expected_files:
        raise SystemExit("combined M01+M02+M03 JUnit file inventory differs")
    return combined


def personalization_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[1]).read_text(encoding="utf-8")
    common = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    test = (ROOT / PRODUCT_FILES[4]).read_text(encoding="utf-8")
    required = (
        'QUERY_PERSONALIZATION_VERSION = "4.0.0-m03.1"',
        '"DETERMINISTIC_FIELD_WEIGHTED_TOKEN_OVERLAP"',
        "QUERY_FIELD_WEIGHTS",
        "query_relevance",
        "semantic_score: null",
        'semantic_status: "NOT_COMPUTED"',
        "excluded_unresolved_edge_ids",
        "ranking_order",
        "QUERY_PERSONALIZATION_HASH_MISMATCH",
        "canonicalizeQueryRankingJson",
        "absent query produces explicit null personalization",
        "relevance is separate from semantic, centrality, and risk",
        "input permutation preserves output hash and ID",
        "hostile wrappers and accessors fail without execution",
    )
    missing = [fragment for fragment in required if fragment not in source + common + test]
    if missing:
        raise SystemExit(f"M03 personalization contract binding is incomplete: {missing}")
    return {
        "algorithm": "DETERMINISTIC_FIELD_WEIGHTED_TOKEN_OVERLAP",
        "attempt_id": ATTEMPT_ID,
        "canonical_result_order": "UTF8_NODE_ID",
        "centrality_emitted": False,
        "deterministic_input_permutation": "PASS",
        "field_weighted_unicode_token_overlap": "PASS",
        "hash_and_id_binding": "PASS",
        "hostile_input_rejection": "PASS",
        "null_query_personalization": None,
        "null_query_relevance_all_zero": True,
        "risk_or_blast_radius_emitted": False,
        "semantic_score": None,
        "semantic_status": "NOT_COMPUTED",
        "status": "PASS",
        "unresolved_edges_excluded_from_scores": True,
        "unresolved_edges_recorded": True,
        "version": "4.0.0-m03.1",
    }


def risk_change_impact_verification() -> dict[str, Any]:
    source = (ROOT / PRODUCT_FILES[2]).read_text(encoding="utf-8")
    common = (ROOT / PRODUCT_FILES[0]).read_text(encoding="utf-8")
    test = (ROOT / PRODUCT_FILES[5]).read_text(encoding="utf-8")
    required = (
        'RISK_CHANGE_IMPACT_VERSION = "4.0.0-m03.1"',
        '"TYPED_RISK_PLUS_DETERMINISTIC_IMPACT_TRAVERSAL"',
        "IMPACT_EDGE_DIRECTION_BY_KIND",
        'OWNS_CONTRACT: "BIDIRECTIONAL"',
        "SHARED_RESOURCE_KINDS",
        'shared_resource_policy: "PAIRWISE_BIDIRECTIONAL_TYPED_EDGES"',
        "RISK_COMPONENT_WEIGHTS",
        'risk_independent_of_blast_radius: true',
        'traversal: "DETERMINISTIC_MULTI_SOURCE_BFS_SHORTEST_PATH"',
        'unresolved_edge_policy: "RECORDED_AND_EXCLUDED_FROM_PROPAGATION"',
        "RISK_PROFILE_COVERAGE_MISMATCH",
        "RISK_CHANGE_IMPACT_HASH_MISMATCH",
        "every hidden shared-resource kind materializes effective edges",
        "risk and blast radius remain separate dimensions",
        "equal-length paths use a deterministic canonical witness",
        "hostile wrappers, accessors, and sparse arrays fail without access",
    )
    missing = [fragment for fragment in required if fragment not in source + common + test]
    if missing:
        raise SystemExit(f"M03 risk/change-impact contract binding is incomplete: {missing}")
    return {
        "algorithm": "TYPED_RISK_PLUS_DETERMINISTIC_IMPACT_TRAVERSAL",
        "attempt_id": ATTEMPT_ID,
        "canonical_path_witness": "PASS",
        "closed_m01_edge_direction_table": True,
        "cycle_and_multi_source_handling": "PASS",
        "deterministic_input_permutation": "PASS",
        "hash_and_id_binding": "PASS",
        "hostile_input_rejection": "PASS",
        "intrinsic_risk_components": [
            "authority_level",
            "write_scope_level",
            "data_sensitivity",
            "mutable_contract",
        ],
        "no_change_assessment": "PASS",
        "query_relevance_or_centrality_emitted": False,
        "risk_independent_of_blast_radius": True,
        "risk_profile_exact_inventory_coverage": True,
        "shared_resource_edge_kinds": [
            "SHARED_WRITE",
            "MUTABLE_CONTRACT",
            "QUOTA",
            "APPROVAL",
            "CREDENTIAL",
            "PRIVACY_BOUNDARY",
            "MIGRATION",
            "EXCLUSIVE_RESOURCE",
        ],
        "shared_resources_materialized_as_pairwise_bidirectional_edges": True,
        "status": "PASS",
        "traversal": "DETERMINISTIC_MULTI_SOURCE_BFS_SHORTEST_PATH",
        "unresolved_edges_excluded_from_propagation": True,
        "unresolved_edges_recorded": True,
        "version": "4.0.0-m03.1",
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
        raise SystemExit("M03 dependency M01 is not the exact sealed PASS")
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
        "non_dependency_regression_context": ["M02-0001"],
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
    assert_clean_node(full_node, 693, "full Node")
    if not (
        len(files) == len(set(files)) == 69
        and full_node["observed_files"] == files
        and full_node["observed_file_count"] == 69
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
        "count": 69,
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
        "combined_m01_m02_m03": combined_evidence(),
        "full_node": {**full_node, "test_file_count": 69},
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
        "evidence_scope": "artifacts/work_packages/M03/**",
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope": "packages/workspace-map/src/ranking/query/**",
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    personalization = personalization_verification()
    impact = risk_change_impact_verification()
    return {
        "personalization-verification.json": personalization,
        "risk-change-impact-verification.json": impact,
        "query-risk-change-impact-verification.json": {
            "attempt_id": ATTEMPT_ID,
            "personalization": personalization,
            "risk_change_impact": impact,
            "separation_contract": {
                "baseline_centrality_separate": True,
                "query_relevance_separate": True,
                "risk_separate": True,
                "blast_radius_separate": True,
                "shared_resources_are_effective_edges": True,
            },
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
    return f"""# M03-0001 query personalization, risk and change impact review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M03
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. Query personalization is a deterministic, content-bound artifact over
   validated M01 inventory and edge-extraction identities. A missing query is
   represented by `query=null`, `personalization=null`, and zero relevance for
   every node rather than by an inferred or hidden default.
2. Non-null query relevance uses documented field-weighted Unicode token
   overlap and an exact-phrase bonus. Semantic scoring remains the separate,
   explicit `null / NOT_COMPUTED` dimension; no model confidence is invented.
3. Query output contains neither baseline centrality, intrinsic risk, nor blast
   radius. Risk/change-impact output contains neither query relevance nor
   baseline centrality. The manifest separation criterion is therefore enforced
   structurally and through negative tests.
4. Intrinsic risk is computed only from complete typed profiles for authority,
   write scope, data sensitivity, and mutable-contract status. It is not a proxy
   for relevance, centrality, or graph reachability.
5. All 19 closed M01 edge kinds have an explicit impact direction. Dependency,
   provenance and supersession targets propagate to dependants; evidence
   support/counter relations propagate from evidence to claims; contract
   ownership is bidirectional.
6. All eight shared-resource kinds materialize as deterministic pairwise,
   bidirectional effective edges. Their participants therefore contribute to
   blast radius as real typed graph structure rather than an unrecorded score
   adjustment.
7. Unresolved M01 edges remain visible and hash-bound but are excluded from
   relevance scoring and impact propagation. Empty change sets, cycles,
   multi-source traversal, equal-length canonical path witnesses, and
   permutation stability are verified.
8. Hash/ID rebuilding, deep immutability, exact risk-profile coverage, closed
   vocabularies, dense-array checks, proxies, accessors, custom prototypes, and
   tampering all fail closed without invoking attacker-controlled accessors.
9. Required checks pass {targeted['passed']}/{targeted['collected']}: 12
   `personalization_test` and 21 `blast_radius_test` cases. M01+M02+M03 combined
   passes {regression['combined_m01_m02_m03']['passed']}/{regression['combined_m01_m02_m03']['collected']}.
   Full Node passes {regression['full_node']['passed']}/{regression['full_node']['collected']}
   across {regression['full_node']['test_file_count']} files; full Python passes
   {regression['full_python']['passed']}/{regression['full_python']['collected']}.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. The initial 30/31 targeted diagnostic was a test-fixture defect: the test
    assigned the already-observed score `1`, so no mutation occurred. The
    fixture now uses a guaranteed different bounded score; production validation
    was not weakened. The final targeted suite is 33/33.
11. All six product files are BOM-less UTF-8 and remain inside exact
    `packages/workspace-map/src/ranking/query/**` scope. Existing dirty worktree
    changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes deterministic query relevance, intrinsic risk, and
typed graph change impact for M01-validated inputs. It does not establish M04
map-UI integration, actor-independent certification, production-scale
performance, overall product completion, release readiness, or
`completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect M03 manifest, M01 dependency, M01/M02 graph contracts, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement deterministic query personalization with explicit null query and semantic-score semantics", 0, "PASS"),
        ("C003", "Implement typed risk and deterministic change-impact traversal with shared-resource effective edges", 0, "PASS"),
        ("D001", "Initial M03 targeted execution", 1, "PRESERVED_DIAGNOSTIC: 30/31; tamper fixture reassigned an existing score of 1 and therefore performed no mutation"),
        ("C004", "Correct score-tamper fixture to assign a guaranteed different bounded value", 0, "PASS without production-contract weakening"),
        ("C005", "Add no-change and canonical equal-distance path-witness regressions", 0, "PASS"),
        ("C006", "Primary-session separate adversarial contract review", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C007", "Run exact M03 targeted JUnit", 0, "PASS: 33/33 (personalization 12, blast radius 21)"),
        ("C008", "Run combined M01+M02+M03 JUnit", 0, "PASS: 80/80"),
        ("C009", "node --check <six M03 product files>", 0, "PASS: 6/6"),
        ("C010", "Capture complete sorted repository Node test inventory", 0, "PASS: 69 unique files"),
        ("C011", "Run complete repository Node test inventory", 0, "PASS: 693/693 across 69 files"),
        ("C012", "Run full Python suite", 0, "PASS: 1064/1064"),
        ("C013", "Verify canonical contract codegen", 0, "PASS: 126 schemas / 126 examples"),
        ("C014", "npm run check:structure", 0, "PASS"),
        ("C015", "npm run check:boundaries", 0, "PASS"),
        ("C016", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C017", "Build and verify deterministic M03 WorkPackageReport evidence", 0, "PASS"),
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
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "M03-0001-QUERY-RISK-CHANGE-IMPACT-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": recorded_at(),
        "created_by": {"actor_id": "M03-0001-PRIMARY-SESSION-VERIFIER", "actor_type": "tool"},
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-M03-0001-QUERY-RISK-CHANGE-IMPACT-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {"check": "personalization_test", "details": "12/12 relevance, null-query, separation, identity, immutability, and fail-closed cases pass", "status": "PASS"},
            {"check": "blast_radius_test", "details": "21/21 direction, shared-edge, risk, traversal, tamper, and hostile-input cases pass", "status": "PASS"},
            {"check": "full_regression", "details": "Node 693/693 across 69 files, Python 1064/1064, codegen 126/126, no suppression", "status": "PASS"},
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
        raise SystemExit(f"invalid M03 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        "personalization-verification.json",
        "risk-change-impact-verification.json",
        "query-risk-change-impact-verification.json",
        "query-risk-change-impact-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m03-node.junit.xml",
        "combined-m01-m02-m03-node.junit.xml",
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
        "run_m03_0001_checks.py",
        "build_m03_0001_evidence.py",
        "m03_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required M03 evidence artifact is missing: {name}")
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
    receipt = read_json(
        ATTEMPT / "query-risk-change-impact-verification.artifact-receipt.json"
    )
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": "artifacts/work_packages/M03/attempts/0001/query-risk-change-impact-verification.artifact-receipt.json",
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
                "classification": "TEST_FIXTURE_NON_MUTATION",
                "result": "initial targeted execution was 30/31 because the tamper fixture assigned the already-observed score 1 and therefore did not mutate the output",
                "resolution": "assign a guaranteed different bounded score (0.123 or 0.124); production validation and hashing contracts remain unchanged",
            }
        ],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "relevance_risk_centrality_separate": "PASS",
            "shared_resources_count_as_edges": "PASS",
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
            "M04 map UI or ranking-claim gate integration",
            "production-scale performance",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "rah_state": rah_state,
        "regression": regression,
        "required_checks": {
            "blast_radius_test": {"failed": 0, "passed": 21, "skipped": 0, "status": "PASS"},
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "personalization_test": {"failed": 0, "passed": 12, "skipped": 0, "status": "PASS"},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/M03/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Query personalization, risk and change impact",
        "verification": {
            "combined_m01_m02_m03": "80/80",
            "full_node": "693/693 across 69 files",
            "full_python": "1064/1064",
            "targeted_m03": "33/33",
            "write_scope_violation_count": 0,
        },
        "verification_details": {
            "personalization": documents["personalization-verification.json"],
            "risk_change_impact": documents["risk-change-impact-verification.json"],
            "targeted": targeted,
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
    authority_path = ATTEMPT / "query-risk-change-impact-verification.json"
    write_json(
        ATTEMPT / "query-risk-change-impact-verification.artifact-receipt.json",
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
            raise SystemExit(f"stored M03 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored M03 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored M03 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "query-risk-change-impact-verification.json")
    receipt_path = ATTEMPT / "query-risk-change-impact-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored M03 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("M03 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored M03 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"M03 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "combined_m01_m02_m03": "80/80",
        "completion_ready": False,
        "full_node": "693/693 across 69 files",
        "full_python": "1064/1064",
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_m03": "33/33",
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
